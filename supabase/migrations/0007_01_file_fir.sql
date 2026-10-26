-- 0007_01 · FIR capture (spec G4, task WS3-10) and officer review of extracted MO (nexus-5).
--
-- 1. file_fir(p jsonb) -> crime_id. One transaction writes the crime, its vehicles and its typed
--    statements, so the worker (process_new_cases: newest crimes without crime_features) never
--    sees a half-filed FIR. Security definer because officers have no INSERT grant on
--    crime_vehicles; the function re-checks the same rule as the policy
--    "officers file FIRs for own station" (0002). It never writes crime_features (Extractor's job).
-- 2. fir_place_check(lat, lon): ward and station whose polygons contain a point, for the form's
--    "outside your jurisdiction" warning.
-- 3. crime_feature_reviews + review_features(): officer corrections to the Extractor's MO are
--    stored separately and append-only, so the model output keeps its provenance (R3).
--    The latest row wins. nexus-1 exposes it to agents through Zetaris (q_features).
--
-- Ids follow the seed (nexus-1): crime_id = <prefix>-<station short code>-<year>-<n:06d>,
-- fir_no = '<n>/<year>', n = next number above the station-year's highest. Prefix and short code
-- come from the station's existing crimes (city pack data; nothing city-specific here, D-004).
-- Every row is synthetic in this build (R6).

-- ---------- 1. file_fir ----------
create or replace function public.file_fir(p jsonb) returns text
language plpgsql security definer set search_path = public, extensions as $$
declare
  v_role     text := public.current_role_name();
  v_station  text;
  v_tz       text;
  v_reported timestamptz := coalesce((p->>'reported_at')::timestamptz, now());
  v_from     timestamptz := (p->>'occurred_from')::timestamptz;
  v_to       timestamptz := nullif(p->>'occurred_to', '')::timestamptz;
  v_lat      double precision := (p->>'lat')::double precision;
  v_lon      double precision := (p->>'lon')::double precision;
  v_year     text;
  v_prefix   text;
  v_short    text;
  v_n        integer;
  v_crime_id text;
  v_sections jsonb := '[]'::jsonb;
  v_code     text;
  v_hit      record;
  v_item     jsonb;
  v_i        integer := 0;
begin
  -- Who may file, and for which station (same rule as the crimes insert policy).
  if v_role = 'admin' then
    v_station := p->>'station_id';
  elsif v_role in ('station_officer', 'supervisor') then
    v_station := public.current_station_id();
    if v_station is null then raise exception 'your profile has no station' using errcode = '42501'; end if;
    if coalesce(p->>'station_id', v_station) <> v_station then
      raise exception 'you can file FIRs only for your own station' using errcode = '42501';
    end if;
  else
    raise exception 'your role cannot file FIRs' using errcode = '42501';
  end if;
  if v_station is null or not exists (select 1 from stations where station_id = v_station) then
    raise exception 'unknown station' using errcode = '22023';
  end if;

  -- Required facts.
  if coalesce(trim(p->>'category'), '') = '' then raise exception 'category is required' using errcode = '22023'; end if;
  if v_from is null then raise exception 'occurred_from is required' using errcode = '22023'; end if;
  if v_to is not null and v_to < v_from then raise exception 'occurred_to is before occurred_from' using errcode = '22023'; end if;
  if v_from > v_reported then raise exception 'the incident cannot be after the report' using errcode = '22023'; end if;
  if v_lat is null or v_lon is null then raise exception 'place (lat, lon) is required' using errcode = '22023'; end if;
  if coalesce(trim(p->>'narrative'), '') = '' then raise exception 'narrative is required' using errcode = '22023'; end if;
  if (p->>'severity')::int not between 1 and 5 then raise exception 'severity must be 1-5' using errcode = '22023'; end if;

  -- City time zone comes from the app (city pack); fall back to UTC if unknown.
  select name into v_tz from pg_timezone_names where name = p->>'tz' limit 1;
  v_tz := coalesce(v_tz, 'UTC');
  v_year := to_char(v_reported at time zone v_tz, 'YYYY');

  -- Sections: accept BNS or IPC codes, store [{code: BNS, ipc_equiv: IPC}] from section_map.
  for v_code in select jsonb_array_elements_text(coalesce(p->'sections', '[]'::jsonb)) loop
    select bns_code, ipc_code into v_hit from section_map
      where bns_code = trim(v_code) or ipc_code = trim(v_code)
      order by (bns_code = trim(v_code)) desc nulls last limit 1;
    if not found then raise exception 'unknown section %', v_code using errcode = '22023'; end if;
    v_sections := v_sections || jsonb_build_array(jsonb_build_object('code', coalesce(v_hit.bns_code, v_hit.ipc_code), 'ipc_equiv', v_hit.ipc_code));
  end loop;

  -- Next FIR number for this station-year. The lock serialises two officers filing at once.
  perform pg_advisory_xact_lock(hashtext('file_fir:' || v_station || ':' || v_year));
  select split_part(crime_id, '-', 1), split_part(crime_id, '-', 2) into v_prefix, v_short
    from crimes where station_id = v_station and crime_id ~ '^[A-Z]+-[A-Z0-9]+-\d{4}-\d+$' limit 1;
  if v_prefix is null then
    raise exception 'no crime id prefix is known for station % yet', v_station using errcode = '22023';
  end if;
  select coalesce(max(split_part(fir_no, '/', 1)::int), 0) + 1 into v_n
    from crimes where station_id = v_station and split_part(fir_no, '/', 2) = v_year and split_part(fir_no, '/', 1) ~ '^\d+$';
  v_crime_id := format('%s-%s-%s-%s', v_prefix, v_short, v_year, lpad(v_n::text, 6, '0'));

  insert into crimes (crime_id, station_id, fir_no, category, sub_type, sections, occurred_from, occurred_to,
                      reported_at, lat, lon, address, ward_no, h3_r9, h3_r8, geohash7, week, severity, property,
                      weapon, offenders_described, victims, status, narrative, synthetic)
  values (v_crime_id, v_station, v_n || '/' || v_year, trim(p->>'category'), nullif(trim(p->>'sub_type'), ''), v_sections,
          v_from, v_to, v_reported, v_lat, v_lon, nullif(trim(p->>'address'), ''),
          (select w.ward_no from wards w where st_contains(w.geom, st_setsrid(st_makepoint(v_lon, v_lat), 4326)) limit 1),
          nullif(p->>'h3_r9', ''), nullif(p->>'h3_r8', ''), nullif(p->>'geohash7', ''),
          public.iso_week(v_from, v_tz), (p->>'severity')::smallint,
          coalesce(p->'property', '[]'::jsonb), nullif(trim(p->>'weapon'), ''),
          coalesce(p->'offenders_described', '[]'::jsonb), coalesce(p->'victims', '[]'::jsonb),
          'registered', trim(p->>'narrative'), true);

  for v_item in select * from jsonb_array_elements(coalesce(p->'vehicles', '[]'::jsonb)) loop
    insert into crime_vehicles (crime_id, role, vehicle_type, plate_pattern, make_model, colour, synthetic)
    values (v_crime_id, coalesce(nullif(v_item->>'role', ''), 'used_by_offender'), coalesce(nullif(v_item->>'vehicle_type', ''), 'unknown'),
            nullif(upper(regexp_replace(coalesce(v_item->>'plate_pattern', ''), '[^A-Za-z0-9?]', '', 'g')), ''),
            nullif(trim(v_item->>'make_model'), ''), nullif(lower(trim(v_item->>'colour')), ''), true);
  end loop;

  -- Typed statements. Witness names never reach the table: refs are masked (J5).
  for v_item in select * from jsonb_array_elements(coalesce(p->'statements', '[]'::jsonb)) loop
    continue when coalesce(trim(v_item->>'text'), '') = '';
    v_i := v_i + 1;
    insert into statements (statement_id, crime_id, witness_ref, mode, text, recorded_at, synthetic)
    values ('ST-' || v_crime_id || '-' || v_i, v_crime_id, 'W-' || v_i || ' (masked)', 'text', trim(v_item->>'text'), v_reported, true);
  end loop;

  insert into audit_log (what, object_type, object_id, details)
  values ('file_fir', 'crime', v_crime_id, jsonb_build_object('station_id', v_station, 'vehicles', jsonb_array_length(coalesce(p->'vehicles', '[]'::jsonb)), 'statements', v_i));
  return v_crime_id;
end
$$;
revoke all on function public.file_fir(jsonb) from public, anon;
grant execute on function public.file_fir(jsonb) to authenticated;

-- ---------- 2. fir_place_check ----------
create or replace function public.fir_place_check(p_lat double precision, p_lon double precision)
returns table (ward_no integer, ward_name text, station_id text, station_name text)
language sql stable security definer set search_path = public, extensions as $$
  select w.ward_no, w.name, s.station_id, s.name
  from (select st_setsrid(st_makepoint(p_lon, p_lat), 4326) as pt) x
  left join wards w on st_contains(w.geom, x.pt)
  left join stations s on s.geom is not null and st_contains(s.geom, x.pt)
  where public.current_role_name() is not null
  limit 1
$$;
revoke all on function public.fir_place_check(double precision, double precision) from public, anon;
grant execute on function public.fir_place_check(double precision, double precision) to authenticated;

-- ---------- 3. officer review of extracted MO ----------
create table if not exists public.crime_feature_reviews (
  review_id   bigint generated always as identity primary key,
  crime_id    text not null references public.crimes (crime_id) on delete cascade,
  corrections jsonb not null check (jsonb_typeof(corrections) = 'object'),  -- partial D3.2 "mo" keys
  note        text,
  reviewed_by uuid not null default auth.uid() references public.profiles (user_id),
  reviewed_at timestamptz not null default now(),
  synthetic   boolean not null default true
);
create index if not exists idx_crime_feature_reviews_crime on public.crime_feature_reviews (crime_id, reviewed_at desc);

alter table public.crime_feature_reviews enable row level security;
revoke all on public.crime_feature_reviews from public, anon, authenticated;
grant select on public.crime_feature_reviews to authenticated;
drop policy if exists "read crime_feature_reviews" on public.crime_feature_reviews;
create policy "read crime_feature_reviews" on public.crime_feature_reviews for select to authenticated
  using (public.can_read_crime(crime_id));

-- Append-only: history is the provenance.
create or replace function public.crime_feature_reviews_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'crime_feature_reviews is append-only' using errcode = '42501';
end
$$;
drop trigger if exists trg_crime_feature_reviews_append_only on public.crime_feature_reviews;
create trigger trg_crime_feature_reviews_append_only before update or delete on public.crime_feature_reviews
  for each row execute function public.crime_feature_reviews_append_only();

-- Agents read corrections through Zetaris; no officer ids leave (nexus-1).
grant select (review_id, crime_id, corrections, note, reviewed_at, synthetic) on public.crime_feature_reviews to zetaris_reader;
drop policy if exists "zetaris reads crime_feature_reviews" on public.crime_feature_reviews;
create policy "zetaris reads crime_feature_reviews" on public.crime_feature_reviews for select to zetaris_reader using (true);

create or replace function public.review_features(p_crime_id text, p_corrections jsonb, p_note text default null)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_id bigint;
  v_allowed text[] := array['approach', 'offender_count', 'target', 'target_item', 'escape', 'violence',
                            'time_band', 'place_type', 'disguise', 'verbal'];
  v_key text;
begin
  if not public.can_write_crime(p_crime_id) then
    raise exception 'you can review features only for cases your station may write' using errcode = '42501';
  end if;
  if not exists (select 1 from crime_features where crime_id = p_crime_id) then
    raise exception 'nothing to review: the Extractor has not run on this case yet' using errcode = '22023';
  end if;
  if p_corrections is null or jsonb_typeof(p_corrections) <> 'object' then
    raise exception 'corrections must be an object' using errcode = '22023';
  end if;
  for v_key in select jsonb_object_keys(p_corrections) loop
    if not v_key = any (v_allowed) then raise exception 'unknown MO field %', v_key using errcode = '22023'; end if;
  end loop;
  if length(p_corrections::text) > 4000 or length(coalesce(p_note, '')) > 1000 then
    raise exception 'review is too long' using errcode = '22023';
  end if;

  insert into crime_feature_reviews (crime_id, corrections, note) values (p_crime_id, p_corrections, nullif(trim(p_note), ''))
  returning review_id into v_id;
  update crime_features set reviewed_by = auth.uid(), reviewed_at = now() where crime_id = p_crime_id;
  insert into audit_log (what, object_type, object_id, details)
  values ('review_features', 'crime', p_crime_id, jsonb_build_object('review_id', v_id, 'fields', (select jsonb_agg(k) from jsonb_object_keys(p_corrections) k)));
  return v_id;
end
$$;
revoke all on function public.review_features(text, jsonb, text) from public, anon;
grant execute on function public.review_features(text, jsonb, text) to authenticated;

-- Rollback:
--   drop function if exists public.review_features(text, jsonb, text);
--   drop table if exists public.crime_feature_reviews;
--   drop function if exists public.crime_feature_reviews_append_only();
--   drop function if exists public.fir_place_check(double precision, double precision);
--   drop function if exists public.file_fir(jsonb);
