-- 0007_15 · New source onboarding (WS1-23; chief + Ravee, 27 Oct; nexus-1 lead, console UI nexus-6).
--
-- An admin brings in a new station's export (an uploaded CSV, or the bundled synthetic sample). The console cannot
-- reach Zetaris (D-019), so it only writes here; the worker does the rest:
--   uploaded -> profiling -> proposed      worker: stages the file in Zetaris, profiles it THROUGH Zetaris, asks the
--                                          fast lane for a column mapping (traced, with receipts), runs DQ checks
--   proposed -> approved | rejected        admin, through onboarding_decide() (edits only while proposed)
--   approved -> registering -> registered  worker: registers the mapped Zetaris view onboard_<source_key>
--   any worker step -> failed (error text)
-- A registered source is "registered, not linked": it is NOT part of v_crime_unified or linking.
-- linking_enabled is pinned false by a CHECK so nothing can turn it on without a new migration.
--
-- Access: admin only. RLS lets admins SELECT; every write goes through SECURITY DEFINER RPCs that check the role.
-- The worker writes with the service role. Files go to the PRIVATE bucket `onboarding` at <uuid>/source.csv.

-- ---------- reference: the unified fields a column may map to ----------
create table if not exists public.onboarding_fields (
  field     text primary key,
  label     text not null,
  required  boolean not null default false,
  kind      text not null check (kind in ('text', 'timestamp', 'number', 'lat', 'lon')),
  sort      integer not null
);
insert into public.onboarding_fields (field, label, required, kind, sort) values
  ('fir_no',        'FIR number',                true,  'text',      1),
  ('occurred_from', 'Date/time of occurrence',   true,  'timestamp', 2),
  ('occurred_to',   'Occurrence ended',          false, 'timestamp', 3),
  ('reported_at',   'Date/time reported',        false, 'timestamp', 4),
  ('category',      'Crime category',            true,  'text',      5),
  ('sub_type',      'Crime sub-type',            false, 'text',      6),
  ('sections_raw',  'Sections (as written)',     false, 'text',      7),
  ('lat',           'Latitude',                  true,  'lat',       8),
  ('lon',           'Longitude',                 true,  'lon',       9),
  ('address',       'Place / address',           false, 'text',      10),
  ('narrative',     'Brief facts',               false, 'text',      11),
  ('status',        'Case status',               false, 'text',      12)
on conflict (field) do update set label = excluded.label, required = excluded.required, kind = excluded.kind,
  sort = excluded.sort;

-- ---------- one onboarding run per new source ----------
create table if not exists public.onboarding_runs (
  run_id           uuid primary key default gen_random_uuid(),
  source_key       text not null unique check (source_key ~ '^[a-z0-9_]{3,30}$'),
  label            text not null check (length(label) between 3 and 80),
  station_name     text,
  file_path        text check (file_path is null or file_path ~ '^[0-9a-f-]{36}/source\.csv$'),
  use_sample       boolean not null default false,
  status           text not null default 'uploaded'
                   check (status in ('uploaded', 'profiling', 'proposed', 'approved', 'registering', 'registered',
                                     'rejected', 'failed')),
  error            text,
  row_count        integer,
  profile          jsonb,      -- [{column, type, non_null, distinct, examples[]}] from Zetaris
  dq               jsonb,      -- [{rule, severity, count, sample_rows[]}]
  mapping_source   text check (mapping_source in ('model', 'rules')),
  trace_run_id     text,       -- the worker run whose trace holds the Zetaris query ids and model receipts
  view_name        text check (view_name is null or view_name ~ '^onboard_[a-z0-9_]{3,30}$'),
  linking_enabled  boolean not null default false check (linking_enabled = false),
  reject_reason    text,
  created_by       uuid default auth.uid(),
  decided_by       uuid,
  decided_at       timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  check ((file_path is null) = use_sample)
);
create index if not exists idx_onboarding_runs_status on public.onboarding_runs (status, created_at);
drop trigger if exists trg_onboarding_runs_updated on public.onboarding_runs;
create trigger trg_onboarding_runs_updated before update on public.onboarding_runs
  for each row execute function public.touch_updated_at();

-- ---------- the proposed (and edited) column mapping ----------
create table if not exists public.onboarding_mappings (
  run_id          uuid not null references public.onboarding_runs (run_id) on delete cascade,
  source_col      text not null check (length(source_col) between 1 and 80),
  proposed_field  text references public.onboarding_fields (field),   -- what the model (or rules) proposed
  unified_field   text references public.onboarding_fields (field),   -- current choice; null = ignore column
  transform       text not null default 'none'
                  check (transform in ('none', 'date_dmy', 'datetime_dmy_hm', 'latlong_lat', 'latlong_lon', 'trim_upper')),
  confidence      numeric check (confidence between 0 and 1),
  reason          text check (length(reason) <= 300),
  edited          boolean not null default false,
  primary key (run_id, source_col)
);

-- ---------- RLS: admins read; nobody writes directly ----------
alter table public.onboarding_fields enable row level security;
alter table public.onboarding_runs enable row level security;
alter table public.onboarding_mappings enable row level security;
revoke all on public.onboarding_fields, public.onboarding_runs, public.onboarding_mappings from public, anon, authenticated;
grant select on public.onboarding_fields, public.onboarding_runs, public.onboarding_mappings to authenticated;

drop policy if exists "admins read onboarding fields" on public.onboarding_fields;
create policy "admins read onboarding fields" on public.onboarding_fields for select to authenticated
  using (public.current_role_name() = 'admin');
drop policy if exists "admins read onboarding runs" on public.onboarding_runs;
create policy "admins read onboarding runs" on public.onboarding_runs for select to authenticated
  using (public.current_role_name() = 'admin');
drop policy if exists "admins read onboarding mappings" on public.onboarding_mappings;
create policy "admins read onboarding mappings" on public.onboarding_mappings for select to authenticated
  using (public.current_role_name() = 'admin');

-- ---------- private bucket for uploaded exports ----------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('onboarding', 'onboarding', false, 2097152, array['text/csv', 'application/vnd.ms-excel', 'text/plain'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "admins upload onboarding exports" on storage.objects;
create policy "admins upload onboarding exports" on storage.objects for insert to authenticated
  with check (bucket_id = 'onboarding' and name ~ '^[0-9a-f-]{36}/source\.csv$'
              and public.current_role_name() = 'admin');
drop policy if exists "admins read onboarding exports" on storage.objects;
create policy "admins read onboarding exports" on storage.objects for select to authenticated
  using (bucket_id = 'onboarding' and public.current_role_name() = 'admin');

-- ---------- RPCs (admin only) ----------
create or replace function public.onboarding_start(p_source_key text, p_label text, p_file_path text,
                                                   p_use_sample boolean default false)
returns uuid
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_id uuid;
begin
  if public.current_role_name() is distinct from 'admin' then
    raise exception 'only an admin can onboard a source' using errcode = '42501';
  end if;
  if p_use_sample then
    p_file_path := null;
  elsif p_file_path is null or p_file_path !~ '^[0-9a-f-]{36}/source\.csv$' then
    raise exception 'upload the file to onboarding/<uuid>/source.csv first' using errcode = '22023';
  elsif not exists (select 1 from storage.objects o where o.bucket_id = 'onboarding' and o.name = p_file_path) then
    raise exception 'the uploaded file was not found' using errcode = '22023';
  end if;
  if exists (select 1 from onboarding_runs where source_key = p_source_key) then
    raise exception 'a source with this key already exists' using errcode = '23505';
  end if;
  insert into onboarding_runs (source_key, label, file_path, use_sample)
  values (p_source_key, trim(p_label), p_file_path, p_use_sample)
  returning run_id into v_id;
  return v_id;
end;
$$;

-- p_edits: [{source_col, unified_field (null = ignore), transform}]. Only while the run is 'proposed'.
create or replace function public.onboarding_save_mapping(p_run_id uuid, p_edits jsonb)
returns integer
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_n integer;
begin
  if public.current_role_name() is distinct from 'admin' then
    raise exception 'only an admin can edit a mapping' using errcode = '42501';
  end if;
  if not exists (select 1 from onboarding_runs where run_id = p_run_id and status = 'proposed') then
    raise exception 'the mapping can be edited only while the run is proposed' using errcode = '22023';
  end if;
  if jsonb_typeof(p_edits) <> 'array' then
    raise exception 'p_edits must be a JSON array' using errcode = '22023';
  end if;
  update onboarding_mappings m
     set unified_field = nullif(e ->> 'unified_field', ''),
         transform = coalesce(nullif(e ->> 'transform', ''), 'none'),
         edited = true
    from jsonb_array_elements(p_edits) e
   where m.run_id = p_run_id and m.source_col = e ->> 'source_col';
  get diagnostics v_n = row_count;
  return v_n;
end;
$$;

-- p_decision: 'approve' | 'reject'. Approve needs every required field mapped exactly once.
create or replace function public.onboarding_decide(p_run_id uuid, p_decision text, p_reason text default null)
returns text
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_missing text;
  v_dup text;
begin
  if public.current_role_name() is distinct from 'admin' then
    raise exception 'only an admin can decide' using errcode = '42501';
  end if;
  if not exists (select 1 from onboarding_runs where run_id = p_run_id and status = 'proposed') then
    raise exception 'only a proposed run can be approved or rejected' using errcode = '22023';
  end if;
  if p_decision = 'reject' then
    update onboarding_runs set status = 'rejected', reject_reason = left(p_reason, 300), decided_by = auth.uid(),
           decided_at = now() where run_id = p_run_id;
    return 'rejected';
  elsif p_decision <> 'approve' then
    raise exception 'decision must be approve or reject' using errcode = '22023';
  end if;
  select string_agg(f.field, ', ' order by f.sort) into v_missing
    from onboarding_fields f
   where f.required
     and not exists (select 1 from onboarding_mappings m where m.run_id = p_run_id and m.unified_field = f.field);
  if v_missing is not null then
    raise exception 'required fields not mapped: %', v_missing using errcode = '22023';
  end if;
  select string_agg(unified_field, ', ') into v_dup from (
    select unified_field from onboarding_mappings where run_id = p_run_id and unified_field is not null
     group by unified_field having count(*) > 1) d;
  if v_dup is not null then
    raise exception 'fields mapped more than once: %', v_dup using errcode = '22023';
  end if;
  update onboarding_runs set status = 'approved', decided_by = auth.uid(), decided_at = now()
   where run_id = p_run_id;
  return 'approved';
end;
$$;

revoke all on function public.onboarding_start(text, text, text, boolean) from public, anon;
revoke all on function public.onboarding_save_mapping(uuid, jsonb) from public, anon;
revoke all on function public.onboarding_decide(uuid, text, text) from public, anon;
grant execute on function public.onboarding_start(text, text, text, boolean) to authenticated;
grant execute on function public.onboarding_save_mapping(uuid, jsonb) to authenticated;
grant execute on function public.onboarding_decide(uuid, text, text) to authenticated;

-- Rollback:
--   drop function if exists public.onboarding_decide(uuid, text, text);
--   drop function if exists public.onboarding_save_mapping(uuid, jsonb);
--   drop function if exists public.onboarding_start(text, text, text, boolean);
--   drop policy if exists "admins upload onboarding exports" on storage.objects;
--   drop policy if exists "admins read onboarding exports" on storage.objects;
--   delete from storage.buckets where id = 'onboarding';  -- only when empty
--   drop table if exists public.onboarding_mappings;
--   drop table if exists public.onboarding_runs;
--   drop table if exists public.onboarding_fields;
--   (and on Zetaris: drop the onboard_* views and onboard_*_raw tables the worker registered)
