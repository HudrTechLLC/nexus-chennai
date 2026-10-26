-- 0004_02 · Pulse Map read RPCs (spec G3, tracker WS3-09). Owner: nexus-4 (Web). Needs 0002 + 0003.
--
-- All functions are SECURITY INVOKER: they run as the signed-in officer, so the 0002 RLS
-- policies decide what comes back (a station officer gets full points for their own station
-- only; other stations appear via the crimes_citywide summary, i.e. H3 r8 cells). They return
-- one jsonb value, so PostgREST's max-rows cap can never truncate a month of points.
-- anon cannot execute any of them (D-003).

-- ---------- crimes for one time window, columnar ----------
-- mod = minute of day in the city's timezone (p_tz from the city pack), for the clock dial.
create or replace function public.map_crimes(p_from timestamptz, p_to timestamptz, p_tz text default 'UTC')
returns jsonb
language sql stable security invoker set search_path = public, extensions as $$
  with c as (
    select c.crime_id, c.lon, c.lat, c.occurred_from, c.category, c.sub_type, c.severity, c.station_id, c.status,
           exists (select 1 from public.link_alerts la
                   where c.crime_id = any (la.crimes) and la.status <> 'rejected') as linked,
           (select sm.series_id from public.series_members sm
             where sm.crime_id = c.crime_id order by sm.added_at, sm.series_id limit 1) as series,
           (c.occurred_from at time zone p_tz) as local_ts
    from public.crimes c
    where c.occurred_from >= p_from and c.occurred_from < p_to
  )
  select jsonb_build_object(
    'id',     coalesce(jsonb_agg(crime_id order by occurred_from, crime_id), '[]'::jsonb),
    'lon',    coalesce(jsonb_agg(round(lon::numeric, 6) order by occurred_from, crime_id), '[]'::jsonb),
    'lat',    coalesce(jsonb_agg(round(lat::numeric, 6) order by occurred_from, crime_id), '[]'::jsonb),
    't',      coalesce(jsonb_agg((extract(epoch from occurred_from) * 1000)::bigint order by occurred_from, crime_id), '[]'::jsonb),
    'mod',    coalesce(jsonb_agg((extract(hour from local_ts) * 60 + extract(minute from local_ts))::int order by occurred_from, crime_id), '[]'::jsonb),
    'cat',    coalesce(jsonb_agg(category order by occurred_from, crime_id), '[]'::jsonb),
    'sub',    coalesce(jsonb_agg(sub_type order by occurred_from, crime_id), '[]'::jsonb),
    'sev',    coalesce(jsonb_agg(severity order by occurred_from, crime_id), '[]'::jsonb),
    'st',     coalesce(jsonb_agg(station_id order by occurred_from, crime_id), '[]'::jsonb),
    'status', coalesce(jsonb_agg(status order by occurred_from, crime_id), '[]'::jsonb),
    'linked', coalesce(jsonb_agg(linked order by occurred_from, crime_id), '[]'::jsonb),
    'series', coalesce(jsonb_agg(series order by occurred_from, crime_id), '[]'::jsonb)
  )
  from c
$$;

-- ---------- extent of what the caller may see ----------
create or replace function public.map_extent()
returns jsonb
language sql stable security invoker set search_path = public as $$
  select jsonb_build_object(
    'min', (extract(epoch from min(occurred_from)) * 1000)::bigint,
    'max', (extract(epoch from max(occurred_from)) * 1000)::bigint,
    'n', count(*))
  from public.crimes
$$;

-- ---------- city-wide hex counts (H3 r8, by category and ISO week) ----------
-- Same for every police role: built from the crimes_citywide summary only.
create or replace function public.map_hexes(p_week_from text default '0000-W00', p_week_to text default '9999-W99')
returns jsonb
language sql stable security invoker set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_array(cell, category, sub_type, week, n)), '[]'::jsonb)
  from (
    select cw.cell, cw.category, cw.sub_type, cw.week, count(*)::int as n
    from public.crimes_citywide cw
    where cw.cell is not null and cw.week between p_week_from and p_week_to
    group by cw.cell, cw.category, cw.sub_type, cw.week
  ) h
$$;

-- ---------- link arcs and series hulls ----------
-- points: exact lon/lat where the caller may read the crime, otherwise only its H3 r8 cell.
create or replace function public.map_links()
returns jsonb
language sql stable security invoker set search_path = public as $$
  with a as (
    select alert_id, kind, crimes, score, band, status from public.link_alerts
  ),
  ids as (
    select distinct unnest(crimes) as cid from a
    union
    select crime_id from public.series_members
  ),
  pts as (
    select i.cid, c.lon, c.lat, (extract(epoch from c.occurred_from) * 1000)::bigint as t, cw.cell, cw.week,
           coalesce(c.station_id, cw.station_id) as st, coalesce(c.category, cw.category) as cat
    from ids i
    left join public.crimes c on c.crime_id = i.cid
    left join public.crimes_citywide cw on cw.crime_id = i.cid
  )
  select jsonb_build_object(
    'alerts', coalesce((select jsonb_agg(jsonb_build_object(
                'id', alert_id, 'kind', kind, 'crimes', to_jsonb(crimes), 'score', score, 'band', band, 'status', status))
              from a), '[]'::jsonb),
    'series', coalesce((select jsonb_agg(jsonb_build_object(
                'id', s.series_id, 'name', s.name, 'status', s.status,
                'members', (select coalesce(jsonb_agg(sm.crime_id order by sm.crime_id), '[]'::jsonb)
                            from public.series_members sm where sm.series_id = s.series_id)))
              from public.series s), '[]'::jsonb),
    'points', coalesce((select jsonb_object_agg(cid, jsonb_build_object(
                'lon', lon, 'lat', lat, 't', t, 'cell', cell, 'week', week, 'st', st, 'cat', cat))
              from pts where cid is not null), '{}'::jsonb)
  )
$$;

-- ---------- station and ward boundaries as GeoJSON ----------
create or replace function public.map_boundaries()
returns jsonb
language sql stable security invoker set search_path = public, extensions as $$
  select jsonb_build_object(
    'stations', jsonb_build_object('type', 'FeatureCollection', 'features', coalesce((
      select jsonb_agg(jsonb_build_object(
        'type', 'Feature',
        'properties', jsonb_build_object('id', s.station_id, 'name', s.name, 'zone', s.zone),
        'geometry', st_asgeojson(st_simplifypreservetopology(s.geom, 0.0003), 5)::jsonb))
      from public.stations s where s.geom is not null), '[]'::jsonb)),
    'wards', jsonb_build_object('type', 'FeatureCollection', 'features', coalesce((
      select jsonb_agg(jsonb_build_object(
        'type', 'Feature',
        'properties', jsonb_build_object('ward_no', w.ward_no, 'name', w.name, 'zone', w.zone),
        'geometry', st_asgeojson(st_simplifypreservetopology(w.geom, 0.0003), 5)::jsonb))
      from public.wards w where w.geom is not null), '[]'::jsonb))
  )
$$;

revoke all on function public.map_crimes(timestamptz, timestamptz, text), public.map_extent(),
  public.map_hexes(text, text), public.map_links(), public.map_boundaries() from public, anon;
grant execute on function public.map_crimes(timestamptz, timestamptz, text), public.map_extent(),
  public.map_hexes(text, text), public.map_links(), public.map_boundaries() to authenticated;

-- Rollback:
--   drop function if exists public.map_crimes(timestamptz, timestamptz, text), public.map_extent(),
--     public.map_hexes(text, text), public.map_links(), public.map_boundaries();
