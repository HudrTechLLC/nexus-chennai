-- 0004_08 · Pulse Map data-source layers (spec G3 layers toggle, "show trail"; WS3-09 slice C).
-- Owner: nexus-4 (Web). Needs 0003_map_layers (nexus-1) and 0004_03.
--
-- SECURITY INVOKER (RLS of the signed-in officer applies), jsonb results (no 1000-row cap).
--   map_layers()       CCTV cameras (for view cones), ANPR cameras, 112 calls per H3 r9 cell per
--                      ISO week, tips per H3 r8 cell per week, released-offender density per ward
--                      (aggregate only, as the spec requires). Compact arrays; the client filters by
--                      the scrubber window.
--   map_trail(crime)   ANPR reads of the crime's offender vehicle plate pattern ('?' = unread digit)
--                      from 6 h before to 6 h after the crime, plus reads already linked to it.

create or replace function public.map_layers()
returns jsonb
language sql stable security invoker set search_path = public as $$
  select jsonb_build_object(
    'cctv', coalesce((select jsonb_agg(jsonb_build_array(camera_id, round(lon::numeric, 6), round(lat::numeric, 6),
                        heading_deg, fov_deg, range_m, owner_type)) from public.map_cctv_cameras), '[]'::jsonb),
    'anpr', coalesce((select jsonb_agg(jsonb_build_array(camera_id, round(lon::numeric, 6), round(lat::numeric, 6)))
                      from public.map_anpr_cameras), '[]'::jsonb),
    'calls', coalesce((select jsonb_agg(jsonb_build_array(h3_r9, wk, n)) from (
                        select h3_r9, to_char(hour_bucket, 'IYYY-"W"IW') as wk, sum(n)::int as n
                        from public.map_call_cells group by 1, 2) c), '[]'::jsonb),
    'tips', coalesce((select jsonb_agg(jsonb_build_array(approx_cell, received_week, n)) from (
                       select approx_cell, received_week, count(*)::int as n
                       from public.tips where approx_cell is not null and status <> 'quarantined'
                       group by 1, 2) t), '[]'::jsonb),
    'release', coalesce((select jsonb_agg(jsonb_build_array(ward_no, n, last_release_week))
                         from public.map_release_density), '[]'::jsonb)
  )
$$;

create or replace function public.map_trail(p_crime_id text)
returns jsonb
language sql stable security invoker set search_path = public as $$
  with c as (
    select crime_id, occurred_from from public.crimes where crime_id = p_crime_id
  ),
  pats as (
    select distinct replace(replace(upper(v.plate_pattern), ' ', ''), '?', '_') as pat, v.plate_pattern as shown
    from public.crime_vehicles v, c
    where v.crime_id = c.crime_id and v.plate_pattern is not null and v.role = 'used_by_offender'
  ),
  reads as (
    select r.read_id, r.camera_id, r.read_at, r.plate_text, r.plate_confidence, r.lon, r.lat
    from public.map_anpr_reads r, c
    where r.crime_id = c.crime_id
       or (r.read_at between c.occurred_from - interval '6 hours' and c.occurred_from + interval '6 hours'
           and exists (select 1 from pats p where replace(upper(r.plate_text), ' ', '') like p.pat))
  )
  select jsonb_build_object(
    'crime_id', p_crime_id,
    'plates', coalesce((select jsonb_agg(shown) from pats), '[]'::jsonb),
    'reads', coalesce((select jsonb_agg(jsonb_build_object(
               'read_id', read_id, 'camera_id', camera_id, 'read_at', read_at, 'plate', plate_text,
               'conf', plate_confidence, 'lon', lon, 'lat', lat) order by read_at) from reads), '[]'::jsonb)
  )
$$;

revoke all on function public.map_layers(), public.map_trail(text) from public, anon;
grant execute on function public.map_layers(), public.map_trail(text) to authenticated;

-- Rollback:
--   drop function if exists public.map_layers(), public.map_trail(text);
