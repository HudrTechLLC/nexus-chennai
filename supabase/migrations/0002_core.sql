-- 0002 · Core schema (spec Part I, formats D3). Owner: nexus-1.
-- Every Part I table not created in 0001, with RLS:
--   station_officer: full rows of own station; city-wide summary via crimes_citywide;
--                    reads all link_alerts / alert_decisions (including rejected).
--   analyst, supervisor, admin: read all police tables; analysts and up decide alerts.
--   anon: NO access to any table, view, sequence or function (DECISIONS D-003). Public
--         data reaches the portal only through narrow RPCs that nexus-4 adds in 0004.
--   zetaris_reader: SELECT only, on the tables Zetaris federates.
-- Writes by the agents and the worker use the service role (bypasses RLS).
-- Coordinates are plain lat/lon doubles (Zetaris reads them over JDBC); geom is generated
-- from them for PostGIS. H3 / geohash cells are precomputed text columns so Zetaris can
-- join on equality (spec E5). Tips store no exact time, IP, user agent or contact (J1).

-- ---------- helpers ----------
create or replace function public.current_station_id() returns text
language sql stable security definer set search_path = public as $$
  select station_id from public.profiles where user_id = auth.uid()
$$;

-- ---------- reference ----------
create table if not exists public.section_map (
  id             bigint generated always as identity primary key,
  ipc_code       text,                 -- null for BNS sections with no IPC equivalent
  bns_code       text,                 -- null for repealed IPC sections
  title          text not null,
  category_group text not null,        -- e.g. robbery, theft, house_break, homicide
  source         text not null default 'bns_text',
  verified       boolean not null default false,
  unique (ipc_code, bns_code),
  check (ipc_code is not null or bns_code is not null)
);

-- ---------- crimes ----------
create table if not exists public.crimes (
  crime_id            text primary key,
  source              text not null default 'sb.crimes',
  source_row_id       text not null default gen_random_uuid()::text,
  station_id          text not null references public.stations (station_id),
  fir_no              text not null,
  category            text not null,
  sub_type            text,
  sections            jsonb not null default '[]'::jsonb,   -- [{code, ipc_equiv}]
  occurred_from       timestamptz not null,
  occurred_to         timestamptz,
  reported_at         timestamptz not null,
  lat                 double precision not null check (lat between -90 and 90),
  lon                 double precision not null check (lon between -180 and 180),
  geom                extensions.geometry(Point, 4326)
                        generated always as (extensions.st_setsrid(extensions.st_makepoint(lon, lat), 4326)) stored,
  address             text,
  ward_no             integer references public.wards (ward_no),
  h3_r9               text,
  h3_r8               text,
  geohash7            text,
  week                text,                                  -- ISO week in city time, e.g. 2026-W42
  severity            smallint not null check (severity between 1 and 5),
  property            jsonb not null default '[]'::jsonb,
  weapon              text,
  offenders_described jsonb not null default '[]'::jsonb,
  victims             jsonb not null default '[]'::jsonb,
  status              text not null default 'registered' check (status in
                        ('registered', 'under_investigation', 'charge_sheeted', 'undetected', 'closed', 'transferred')),
  narrative           text,
  synthetic           boolean not null default false,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (station_id, fir_no),
  check (occurred_to is null or occurred_to >= occurred_from)
);
create index if not exists idx_crimes_station   on public.crimes (station_id);
create index if not exists idx_crimes_occurred  on public.crimes (occurred_from);
create index if not exists idx_crimes_category  on public.crimes (category, occurred_from);
create index if not exists idx_crimes_h3_r9     on public.crimes (h3_r9);
create index if not exists idx_crimes_geohash7  on public.crimes (geohash7 text_pattern_ops);
create index if not exists idx_crimes_geom      on public.crimes using gist (geom);
create index if not exists idx_crimes_narrative on public.crimes using gin (narrative extensions.gin_trgm_ops);

drop trigger if exists trg_crimes_updated on public.crimes;
create trigger trg_crimes_updated before update on public.crimes
  for each row execute function public.touch_updated_at();

-- Helpers that need public.crimes (SQL function bodies are checked at creation).
-- True when the caller may read a crime's full row (and its child rows).
create or replace function public.can_read_crime(p_crime_id text) returns boolean
language sql stable security definer set search_path = public as $$
  select case public.current_role_name()
    when 'analyst' then true
    when 'supervisor' then true
    when 'admin' then true
    when 'station_officer' then exists (
      select 1 from public.crimes c
      where c.crime_id = p_crime_id and c.station_id = public.current_station_id())
    else false
  end
$$;

-- True when the caller may add records to a crime (FIR form, case diary, statements).
create or replace function public.can_write_crime(p_crime_id text) returns boolean
language sql stable security definer set search_path = public as $$
  select case public.current_role_name()
    when 'admin' then true
    when 'supervisor' then true
    when 'station_officer' then exists (
      select 1 from public.crimes c
      where c.crime_id = p_crime_id and c.station_id = public.current_station_id())
    else false
  end
$$;

create table if not exists public.crime_features (
  crime_id          text primary key references public.crimes (crime_id) on delete cascade,
  extractor_version text not null,
  mo                jsonb not null default '{}'::jsonb,
  visual_tags       text[] not null default '{}',
  entities          jsonb not null default '{}'::jsonb,
  model             text not null,
  receipt_id        text,
  confidence        real check (confidence between 0 and 1),
  reviewed_by       uuid references public.profiles (user_id),
  reviewed_at       timestamptz,
  synthetic         boolean not null default false,
  created_at        timestamptz not null default now()
);

create table if not exists public.crime_vehicles (
  id            bigint generated always as identity primary key,
  crime_id      text not null references public.crimes (crime_id) on delete cascade,
  role          text not null,              -- used_by_offender, stolen, victim_vehicle
  vehicle_type  text not null,              -- motorcycle, car, auto, ...
  plate_pattern text,                       -- "TN09??4471" (spaces removed, ? = unread)
  make_model    text,
  colour        text,
  synthetic     boolean not null default false
);
create index if not exists idx_crime_vehicles_crime on public.crime_vehicles (crime_id);
create index if not exists idx_crime_vehicles_plate on public.crime_vehicles (plate_pattern text_pattern_ops);

-- ---------- persons ----------
create table if not exists public.persons (
  person_id     text primary key,
  name          text,
  aliases       text[] not null default '{}',
  descriptors   jsonb not null default '{}'::jsonb,   -- height band, build, marks, clothing
  residence_ward integer references public.wards (ward_no),
  source        text not null default 'sb.persons',
  source_row_id text,
  synthetic     boolean not null default false,
  created_at    timestamptz not null default now()
);
create index if not exists idx_persons_name on public.persons using gin (name extensions.gin_trgm_ops);

create table if not exists public.person_links (
  person_id text not null references public.persons (person_id) on delete cascade,
  crime_id  text not null references public.crimes (crime_id) on delete cascade,
  role      text not null check (role in ('accused', 'suspect', 'victim', 'witness', 'complainant')),
  synthetic boolean not null default false,
  primary key (person_id, crime_id, role)
);
create index if not exists idx_person_links_crime on public.person_links (crime_id);

-- ---------- evidence, statements, diary, forensics ----------
create table if not exists public.evidence_media (
  evidence_id   text primary key,
  crime_id      text not null references public.crimes (crime_id) on delete cascade,
  kind          text not null check (kind in ('cctv_still', 'cctv_clip', 'photo', 'scan', 'audio', 'document')),
  storage_path  text not null,
  sha256        text not null,
  captured_at   timestamptz,
  camera_id     text,
  uploaded_by   text not null,
  vision        jsonb,
  custody       jsonb not null default '[]'::jsonb,
  source        text not null default 'sb.evidence_media',
  source_row_id text,
  synthetic     boolean not null default false,
  created_at    timestamptz not null default now()
);
create index if not exists idx_evidence_crime on public.evidence_media (crime_id);

create table if not exists public.statements (
  statement_id     text primary key,
  crime_id         text not null references public.crimes (crime_id) on delete cascade,
  witness_ref      text not null,
  mode             text not null check (mode in ('text', 'audio')),
  text             text,
  audio_path       text,
  transcript_model text,
  recorded_at      timestamptz not null,
  source           text not null default 'sb.statements',
  source_row_id    text,
  synthetic        boolean not null default false
);
create index if not exists idx_statements_crime on public.statements (crime_id);

create table if not exists public.case_diary (
  entry_id      text primary key,
  crime_id      text not null references public.crimes (crime_id) on delete cascade,
  at            timestamptz not null,
  kind          text not null,       -- visit, lead, arrest, request, note, ...
  text          text not null,
  author        text not null,
  source        text not null default 'sb.case_diary',
  source_row_id text,
  synthetic     boolean not null default false
);
create index if not exists idx_case_diary_crime on public.case_diary (crime_id, at);

create table if not exists public.forensics (
  forensic_id   text primary key,
  crime_id      text not null references public.crimes (crime_id) on delete cascade,
  kind          text not null check (kind in ('fingerprint', 'ballistics', 'dna', 'toolmark')),
  match_code    text,                -- equal codes across crimes = forensic match
  reported_at   timestamptz,
  source        text not null default 'sb.forensics',
  source_row_id text,
  synthetic     boolean not null default false
);
create index if not exists idx_forensics_crime on public.forensics (crime_id);
create index if not exists idx_forensics_match on public.forensics (match_code) where match_code is not null;

create table if not exists public.missing_persons (
  mp_id          text primary key,
  reported_at    timestamptz not null,
  station_id     text references public.stations (station_id),
  last_seen_lat  double precision,
  last_seen_lon  double precision,
  last_seen_geom extensions.geometry(Point, 4326) generated always as (
                   case when last_seen_lat is null or last_seen_lon is null then null
                   else extensions.st_setsrid(extensions.st_makepoint(last_seen_lon, last_seen_lat), 4326) end) stored,
  last_seen_h3_r9 text,
  descriptors    jsonb not null default '{}'::jsonb,
  status         text not null default 'open' check (status in ('open', 'traced', 'closed')),
  source         text not null default 'sb.missing_persons',
  source_row_id  text,
  synthetic      boolean not null default false
);

-- ---------- public incidents and tips ----------
create table if not exists public.public_incidents (
  public_incident_id text primary key,
  crime_id           text references public.crimes (crime_id) on delete set null,
  title              text not null,
  category           text not null,
  area_label         text not null,
  cell               text not null,          -- H3 r8 only, never a point
  week               text not null,
  time_window        text not null,
  summary            text not null,
  looking_for        text[] not null default '{}',
  images             jsonb not null default '[]'::jsonb,
  approved_by        text,
  sanitiser_model    text,
  status             text not null default 'draft' check (status in ('draft', 'published', 'withdrawn')),
  published_at       timestamptz,
  synthetic          boolean not null default false
);
create index if not exists idx_public_incidents_crime on public.public_incidents (crime_id);

-- No created_at, IP, user agent or contact columns, on purpose (spec J1, D3.6).
create table if not exists public.tips (
  tip_id             text primary key,
  public_incident_id text references public.public_incidents (public_incident_id) on delete set null,
  channel            text not null check (channel in ('web', 'voice', 'whatsapp')),
  category           text not null,
  text               text not null,
  follow_up_enabled  boolean not null default false,
  tip_code_hash      text,
  guard              jsonb,                   -- null until Tip Guard screens it
  approx_cell        text,                    -- H3 r8
  received_week      text not null check (received_week ~ '^\d{4}-W\d{2}$'),
  status             text not null default 'new' check (status in ('new', 'screened', 'quarantined', 'urgent', 'reviewed', 'closed')),
  source             text not null default 'sb.tips',
  source_row_id      text,
  synthetic          boolean not null default false
);
create index if not exists idx_tips_incident on public.tips (public_incident_id);
create index if not exists idx_tips_status on public.tips (status);

create table if not exists public.tip_media (
  media_id      text primary key,
  tip_id        text not null references public.tips (tip_id) on delete cascade,
  kind          text not null check (kind in ('image', 'video', 'audio')),
  path          text not null,
  exif_stripped boolean not null,
  faces_blurred boolean not null,
  synthetic     boolean not null default false
);
create index if not exists idx_tip_media_tip on public.tip_media (tip_id);

-- Part I names the column "from"; it is "sender" because from is a reserved word.
create table if not exists public.tip_messages (
  message_id bigint generated always as identity primary key,
  tip_id     text not null references public.tips (tip_id) on delete cascade,
  sender     text not null check (sender in ('police', 'tipster')),
  text       text not null,
  at         timestamptz not null default now(),
  author     uuid references public.profiles (user_id),  -- police sender only; null for tipster
  synthetic  boolean not null default false
);
create index if not exists idx_tip_messages_tip on public.tip_messages (tip_id, at);

-- ---------- link alerts and decisions ----------
create table if not exists public.link_alerts (
  alert_id           text primary key,
  kind               text not null check (kind in ('pair', 'series', 'hotspot')),
  crimes             text[] not null check (cardinality(crimes) >= 1),
  stations           text[] not null default '{}',
  score              real not null check (score between 0 and 1),
  band               text not null check (band in ('high', 'medium')),
  memory_applied     jsonb not null default '[]'::jsonb,
  skeptic            jsonb,
  rationale          text not null,
  recommended_action text,
  status             text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  run_id             text references public.runs (run_id) on delete set null,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  synthetic          boolean not null default false
);
create index if not exists idx_link_alerts_status on public.link_alerts (status, created_at desc);
create index if not exists idx_link_alerts_crimes on public.link_alerts using gin (crimes);

drop trigger if exists trg_link_alerts_updated on public.link_alerts;
create trigger trg_link_alerts_updated before update on public.link_alerts
  for each row execute function public.touch_updated_at();

create table if not exists public.link_factors (
  alert_id          text not null references public.link_alerts (alert_id) on delete cascade,
  factor            text not null check (factor in ('mo_similarity', 'space_time', 'vehicle', 'suspect_description',
                      'weapon_tool', 'target_profile', 'forensic', 'corroboration', 'offender_return')),
  weight            real not null check (weight between 0 and 1),
  value             real not null check (value between 0 and 1),
  evidence          jsonb not null default '[]'::jsonb,   -- [{view, row}]
  reason            text not null,
  struck_by_skeptic boolean not null default false,
  primary key (alert_id, factor)
);

create table if not exists public.alert_decisions (
  decision_id  bigint generated always as identity primary key,
  alert_id     text not null references public.link_alerts (alert_id) on delete cascade,
  decision     text not null check (decision in ('approve', 'reject')),
  reason_code  text check (reason_code in ('different_offenders', 'coincidental_location', 'already_linked',
                 'data_error', 'insufficient_evidence', 'different_mo', 'duplicate_fir', 'other')),
  note         text,
  by           uuid not null default auth.uid() references public.profiles (user_id),
  at           timestamptz not null default now(),
  processed_at timestamptz,               -- set by the worker after H-MEM + status update
  check (decision = 'approve' or reason_code is not null)
);
create index if not exists idx_alert_decisions_alert on public.alert_decisions (alert_id, at desc);
create index if not exists idx_alert_decisions_unprocessed on public.alert_decisions (at) where processed_at is null;

-- ---------- series and task forces ----------
create table if not exists public.series (
  series_id  text primary key,
  name       text not null,
  status     text not null default 'candidate' check (status in ('candidate', 'confirmed', 'closed')),
  dossier    jsonb,
  run_id     text references public.runs (run_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  synthetic  boolean not null default false
);
drop trigger if exists trg_series_updated on public.series;
create trigger trg_series_updated before update on public.series
  for each row execute function public.touch_updated_at();

create table if not exists public.series_members (
  series_id text not null references public.series (series_id) on delete cascade,
  crime_id  text not null references public.crimes (crime_id) on delete cascade,
  added_at  timestamptz not null default now(),
  primary key (series_id, crime_id)
);
create index if not exists idx_series_members_crime on public.series_members (crime_id);

create table if not exists public.taskforces (
  taskforce_id text primary key,
  name         text not null,
  series_id    text references public.series (series_id) on delete set null,
  status       text not null default 'active' check (status in ('active', 'closed')),
  created_by   uuid references public.profiles (user_id),
  created_at   timestamptz not null default now()
);

create table if not exists public.taskforce_members (
  taskforce_id text not null references public.taskforces (taskforce_id) on delete cascade,
  user_id      uuid not null references public.profiles (user_id) on delete cascade,
  role         text not null default 'member' check (role in ('lead', 'member')),
  primary key (taskforce_id, user_id)
);

-- ---------- notifications, outbox, audit ----------
create table if not exists public.notifications (
  notification_id bigint generated always as identity primary key,
  user_id         uuid not null references public.profiles (user_id) on delete cascade,
  kind            text not null,
  title           text not null,
  body            text,
  link            text,
  read_at         timestamptz,
  created_at      timestamptz not null default now()
);
create index if not exists idx_notifications_user on public.notifications (user_id, created_at desc);

create table if not exists public.outbox (
  outbox_id  bigint generated always as identity primary key,
  channel    text not null check (channel in ('email', 'whatsapp', 'in_app')),
  recipient  text not null,
  payload    jsonb not null,
  status     text not null default 'queued' check (status in ('queued', 'sent', 'failed')),
  created_at timestamptz not null default now(),
  sent_at    timestamptz
);

create table if not exists public.audit_log (
  audit_id    bigint generated always as identity primary key,
  who         uuid default auth.uid(),
  what        text not null,              -- view_case, export, decide_alert, publish, ...
  object_type text not null,
  object_id   text not null,
  details     jsonb,
  at          timestamptz not null default now()
);
create index if not exists idx_audit_log_object on public.audit_log (object_type, object_id, at desc);

-- ---------- city-wide crime summary for station officers ----------
-- Only summary columns leave this function: no narrative, address, point, property or victims.
create or replace function public.crimes_citywide_rows()
returns table (crime_id text, station_id text, category text, sub_type text, cell text, week text,
               mo_tags text[], visual_tags text[])
language sql stable security definer set search_path = public as $$
  select c.crime_id, c.station_id, c.category, c.sub_type, c.h3_r8, c.week,
         coalesce(array(
           select v from jsonb_each(cf.mo) e(k, j),
                lateral (select case jsonb_typeof(j)
                                  when 'string' then array[j #>> '{}']
                                  when 'array' then array(select jsonb_array_elements_text(j))
                                  else array[]::text[] end) a(vals),
                unnest(a.vals) v
           where k not in ('offender_count')), '{}'::text[]) as mo_tags,
         coalesce(cf.visual_tags, '{}'::text[]) as visual_tags
  from public.crimes c
  left join public.crime_features cf on cf.crime_id = c.crime_id
  where public.current_role_name() is not null
$$;

create or replace view public.crimes_citywide with (security_invoker = true) as
  select * from public.crimes_citywide_rows();

-- ---------- RLS ----------
alter table public.section_map       enable row level security;
alter table public.crimes            enable row level security;
alter table public.crime_features    enable row level security;
alter table public.crime_vehicles    enable row level security;
alter table public.persons           enable row level security;
alter table public.person_links      enable row level security;
alter table public.evidence_media    enable row level security;
alter table public.statements        enable row level security;
alter table public.case_diary        enable row level security;
alter table public.forensics         enable row level security;
alter table public.missing_persons   enable row level security;
alter table public.public_incidents  enable row level security;
alter table public.tips              enable row level security;
alter table public.tip_media         enable row level security;
alter table public.tip_messages      enable row level security;
alter table public.link_alerts       enable row level security;
alter table public.link_factors      enable row level security;
alter table public.alert_decisions   enable row level security;
alter table public.series            enable row level security;
alter table public.series_members    enable row level security;
alter table public.taskforces        enable row level security;
alter table public.taskforce_members enable row level security;
alter table public.notifications     enable row level security;
alter table public.outbox            enable row level security;
alter table public.audit_log         enable row level security;

-- Start from nothing for authenticated, then grant only what the policies use.
revoke all on public.section_map, public.crimes, public.crime_features, public.crime_vehicles,
  public.persons, public.person_links, public.evidence_media, public.statements, public.case_diary,
  public.forensics, public.missing_persons, public.public_incidents, public.tips, public.tip_media,
  public.tip_messages, public.link_alerts, public.link_factors, public.alert_decisions, public.series,
  public.series_members, public.taskforces, public.taskforce_members, public.notifications,
  public.outbox, public.audit_log, public.crimes_citywide
  from anon, authenticated;

grant select on public.section_map, public.crimes, public.crime_features, public.crime_vehicles,
  public.persons, public.person_links, public.evidence_media, public.statements, public.case_diary,
  public.forensics, public.missing_persons, public.public_incidents, public.tips, public.tip_media,
  public.tip_messages, public.link_alerts, public.link_factors, public.alert_decisions, public.series,
  public.series_members, public.taskforces, public.taskforce_members, public.notifications,
  public.outbox, public.audit_log, public.crimes_citywide
  to authenticated;
grant insert, update on public.crimes, public.public_incidents, public.taskforces to authenticated;
grant insert on public.case_diary, public.statements, public.evidence_media, public.tip_messages,
  public.alert_decisions, public.audit_log, public.taskforce_members to authenticated;
grant update (read_at) on public.notifications to authenticated;
grant update (reviewed_by, reviewed_at) on public.crime_features to authenticated;

-- Reference data: any police role.
create policy "police read section_map" on public.section_map for select to authenticated
  using ((select public.current_role_name()) is not null);

-- Crimes: own station for officers, everything for analysts and up.
create policy "read crimes by role" on public.crimes for select to authenticated
  using ((select public.current_role_name()) in ('analyst', 'supervisor', 'admin')
         or ((select public.current_role_name()) = 'station_officer'
             and station_id = (select public.current_station_id())));
create policy "officers file FIRs for own station" on public.crimes for insert to authenticated
  with check ((select public.current_role_name()) = 'admin'
              or ((select public.current_role_name()) in ('station_officer', 'supervisor')
                  and station_id = (select public.current_station_id())));
create policy "officers update own station crimes" on public.crimes for update to authenticated
  using ((select public.current_role_name()) in ('supervisor', 'admin')
         or ((select public.current_role_name()) = 'station_officer'
             and station_id = (select public.current_station_id())))
  with check ((select public.current_role_name()) in ('supervisor', 'admin')
              or station_id = (select public.current_station_id()));

-- Child rows of a crime follow the crime.
create policy "read crime_features" on public.crime_features for select to authenticated
  using (public.can_read_crime(crime_id));
create policy "officer reviews features" on public.crime_features for update to authenticated
  using (public.can_write_crime(crime_id)) with check (public.can_write_crime(crime_id));
create policy "read crime_vehicles" on public.crime_vehicles for select to authenticated
  using (public.can_read_crime(crime_id));
create policy "read person_links" on public.person_links for select to authenticated
  using (public.can_read_crime(crime_id));
create policy "read evidence" on public.evidence_media for select to authenticated
  using (public.can_read_crime(crime_id));
create policy "add evidence" on public.evidence_media for insert to authenticated
  with check (public.can_write_crime(crime_id));
create policy "read statements" on public.statements for select to authenticated
  using (public.can_read_crime(crime_id));
create policy "add statements" on public.statements for insert to authenticated
  with check (public.can_write_crime(crime_id));
create policy "read case_diary" on public.case_diary for select to authenticated
  using (public.can_read_crime(crime_id));
create policy "add case_diary" on public.case_diary for insert to authenticated
  with check (public.can_write_crime(crime_id));
create policy "read forensics" on public.forensics for select to authenticated
  using (public.can_read_crime(crime_id));

-- Registers used for entity search: any police role.
create policy "police read persons" on public.persons for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read missing_persons" on public.missing_persons for select to authenticated
  using ((select public.current_role_name()) is not null);

-- Public incidents: police read all; officers draft/publish for own station's crimes.
create policy "police read public_incidents" on public.public_incidents for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "officers draft public_incidents" on public.public_incidents for insert to authenticated
  with check (crime_id is not null and public.can_write_crime(crime_id));
create policy "officers edit public_incidents" on public.public_incidents for update to authenticated
  using (crime_id is not null and public.can_write_crime(crime_id))
  with check (crime_id is not null and public.can_write_crime(crime_id));

-- Tips: police read; tips themselves arrive only through the 0004 RPC / service role.
create policy "police read tips" on public.tips for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read tip_media" on public.tip_media for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read tip_messages" on public.tip_messages for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police reply to tips" on public.tip_messages for insert to authenticated
  with check ((select public.current_role_name()) is not null and sender = 'police' and author = auth.uid());

-- Alerts: every police role reads all of them, including rejected (Part I, F4).
create policy "police read link_alerts" on public.link_alerts for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read link_factors" on public.link_factors for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read alert_decisions" on public.alert_decisions for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "analysts decide alerts" on public.alert_decisions for insert to authenticated
  with check ((select public.current_role_name()) in ('analyst', 'supervisor', 'admin')
              and by = auth.uid() and processed_at is null);

create policy "police read series" on public.series for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read series_members" on public.series_members for select to authenticated
  using ((select public.current_role_name()) is not null);

create policy "police read taskforces" on public.taskforces for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "supervisors manage taskforces" on public.taskforces for insert to authenticated
  with check ((select public.current_role_name()) in ('supervisor', 'admin') and created_by = auth.uid());
create policy "supervisors edit taskforces" on public.taskforces for update to authenticated
  using ((select public.current_role_name()) in ('supervisor', 'admin'));
create policy "police read taskforce_members" on public.taskforce_members for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "supervisors add taskforce_members" on public.taskforce_members for insert to authenticated
  with check ((select public.current_role_name()) in ('supervisor', 'admin'));

-- Notifications: your own only.
create policy "read own notifications" on public.notifications for select to authenticated
  using (user_id = auth.uid());
create policy "mark own notifications read" on public.notifications for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- Outbox: admins only (the worker writes with the service role).
create policy "admins read outbox" on public.outbox for select to authenticated
  using ((select public.current_role_name()) = 'admin');

-- Audit log: append-only for police; supervisors and admins read.
create policy "police append audit" on public.audit_log for insert to authenticated
  with check ((select public.current_role_name()) is not null and who = auth.uid());
create policy "supervisors read audit" on public.audit_log for select to authenticated
  using ((select public.current_role_name()) in ('supervisor', 'admin'));

-- ---------- Zetaris federation (read-only, spec E5 / Part I) ----------
grant select on public.section_map, public.crimes, public.crime_features, public.crime_vehicles,
  public.persons, public.person_links, public.evidence_media, public.statements, public.case_diary,
  public.forensics, public.missing_persons, public.public_incidents, public.tips, public.link_alerts,
  public.link_factors, public.alert_decisions, public.series, public.series_members
  to zetaris_reader;
do $$
declare t text;
begin
  foreach t in array array['stations', 'wards', 'runs', 'section_map', 'crimes', 'crime_features',
    'crime_vehicles', 'persons', 'person_links', 'evidence_media', 'statements', 'case_diary', 'forensics',
    'missing_persons', 'public_incidents', 'tips', 'link_alerts', 'link_factors', 'alert_decisions',
    'series', 'series_members']
  loop
    execute format('drop policy if exists "zetaris reads %1$s" on public.%1$I', t);
    execute format('create policy "zetaris reads %1$s" on public.%1$I for select to zetaris_reader using (true)', t);
  end loop;
end $$;

-- ---------- functions: police only, never anon ----------
revoke all on function public.current_station_id(), public.can_read_crime(text), public.can_write_crime(text),
  public.crimes_citywide_rows() from public, anon;
grant execute on function public.current_station_id(), public.can_read_crime(text), public.can_write_crime(text),
  public.crimes_citywide_rows() to authenticated;

-- ---------- anon gets nothing (D-003) ----------
-- Supabase grants anon on new objects by default; remove every grant in public, now and for
-- objects created later by this role. 0004 grants EXECUTE on its public RPCs explicitly.
revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;
revoke all on all functions in schema public from anon;
-- 0001's trigger helper still had PUBLIC execute (which anon inherits); triggers do not need it.
revoke all on function public.touch_updated_at() from public, anon;
alter default privileges in schema public revoke all on tables from anon;
alter default privileges in schema public revoke all on sequences from anon;
alter default privileges in schema public revoke all on functions from anon;

-- Rollback:
--   drop view if exists public.crimes_citywide;
--   drop function if exists public.crimes_citywide_rows(), public.can_read_crime(text),
--     public.can_write_crime(text), public.current_station_id();
--   drop table if exists public.audit_log, public.outbox, public.notifications, public.taskforce_members,
--     public.taskforces, public.series_members, public.series, public.alert_decisions, public.link_factors,
--     public.link_alerts, public.tip_messages, public.tip_media, public.tips, public.public_incidents,
--     public.missing_persons, public.forensics, public.case_diary, public.statements, public.evidence_media,
--     public.person_links, public.persons, public.crime_vehicles, public.crime_features, public.crimes,
--     public.section_map cascade;
--   alter default privileges in schema public grant all on tables, sequences, functions to anon;
