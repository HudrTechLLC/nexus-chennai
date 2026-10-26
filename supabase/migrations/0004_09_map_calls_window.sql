-- 0004_09 · Pulse Map: fetch 112 calls per window instead of in bulk (WS3-09). Owner: nexus-4.
-- With the seeded data, map_layers() returned ~89k weekly call buckets (3.1 MB) on every map load.
-- Calls now come from map_calls(week_from, week_to), aggregated per H3 r9 cell for the scrubber window
-- and requested only while the 112 layer is switched on. map_layers() keeps its signature and
-- returns an empty 'calls' array, so older clients keep working.

create or replace function public.map_calls(p_week_from text, p_week_to text)
returns jsonb
language sql stable security invoker set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_array(h3_r9, n)), '[]'::jsonb)
  from (
    select h3_r9, sum(n)::int as n
    from public.map_call_cells
    where hour_bucket >= to_date(p_week_from, 'IYYY-"W"IW')
      and hour_bucket <  to_date(p_week_to, 'IYYY-"W"IW') + 7
    group by h3_r9
  ) c
$$;
revoke all on function public.map_calls(text, text) from public, anon;
grant execute on function public.map_calls(text, text) to authenticated;

create index if not exists idx_map_call_cells_hour on public.map_call_cells (hour_bucket);

create or replace function public.map_layers()
returns jsonb
language sql stable security invoker set search_path = public as $$
  select jsonb_build_object(
    'cctv', coalesce((select jsonb_agg(jsonb_build_array(camera_id, round(lon::numeric, 6), round(lat::numeric, 6),
                        heading_deg, fov_deg, range_m, owner_type)) from public.map_cctv_cameras), '[]'::jsonb),
    'anpr', coalesce((select jsonb_agg(jsonb_build_array(camera_id, round(lon::numeric, 6), round(lat::numeric, 6)))
                      from public.map_anpr_cameras), '[]'::jsonb),
    'calls', '[]'::jsonb,
    'tips', coalesce((select jsonb_agg(jsonb_build_array(approx_cell, received_week, n)) from (
                       select approx_cell, received_week, count(*)::int as n
                       from public.tips where approx_cell is not null and status <> 'quarantined'
                       group by 1, 2) t), '[]'::jsonb),
    'release', coalesce((select jsonb_agg(jsonb_build_array(ward_no, n, last_release_week))
                         from public.map_release_density), '[]'::jsonb)
  )
$$;

-- Rollback: drop function public.map_calls(text, text); drop index idx_map_call_cells_hour;
--           re-run map_layers() from 0004_08.
