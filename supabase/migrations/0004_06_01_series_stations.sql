-- 0004_06_01 · Read RPCs for /console/series and /console/stations (spec G2; WS3-11). Owner: nexus-6 (web).
--
-- Both functions are SECURITY INVOKER: they run as the signed-in officer, so the 0002 RLS on
-- link_alerts, series, series_members and crimes_citywide still decides what comes back.
-- They return one jsonb value, so PostgREST's 1000-row cap never truncates them silently,
-- and the console needs one round-trip instead of paging thousands of alert rows.
-- Read-only: neither function writes anything.

-- ---------- station × station link matrix ----------
-- cells: one row per unordered station pair (a <= b) × status × kind, with up to 25 alert ids
--        (newest first). An alert inside one station sits on the diagonal (a = b). A series alert
--        spanning n stations counts in every pair it spans.
-- per_station: distinct alerts per station × status, so a 3-station alert counts once per station.
create or replace function public.station_link_matrix(p_since timestamptz default null)
returns jsonb
language sql stable security invoker set search_path = public as $$
  with a as (
    select alert_id, kind, status, created_at,
           array(select distinct s from unnest(stations) s where s is not null) as st
    from public.link_alerts
    where p_since is null or created_at >= p_since
  ),
  per as (
    select a.alert_id, a.kind, a.status, a.created_at, s as station_id, cardinality(a.st) as n_st
    from a cross join lateral unnest(a.st) s
  ),
  pairs as (
    select x.alert_id, x.kind, x.status, x.created_at, x.station_id as sa, y.station_id as sb
    from per x join per y on y.alert_id = x.alert_id and x.station_id < y.station_id
    union all
    select alert_id, kind, status, created_at, station_id, station_id from per where n_st = 1
  )
  select jsonb_build_object(
    'alerts', (select count(*)::int from a),
    'cells', coalesce((
      select jsonb_agg(jsonb_build_object('a', sa, 'b', sb, 'status', status, 'kind', kind, 'n', n,
                                          'alert_ids', to_jsonb(ids[1:25]))
                       order by sa, sb, status, kind)
      from (select sa, sb, status, kind, count(*)::int as n,
                   array_agg(alert_id order by created_at desc) as ids
            from pairs group by sa, sb, status, kind) g), '[]'::jsonb),
    'per_station', coalesce((
      select jsonb_agg(jsonb_build_object('station', station_id, 'status', status, 'n', n) order by station_id, status)
      from (select station_id, status, count(distinct alert_id)::int as n from per group by station_id, status) p),
      '[]'::jsonb),
    'stations', coalesce((
      select jsonb_agg(jsonb_build_object('id', s.station_id, 'name', s.name, 'zone', s.zone) order by s.zone, s.name)
      from public.stations s), '[]'::jsonb)
  )
$$;
revoke all on function public.station_link_matrix(timestamptz) from public, anon;
grant execute on function public.station_link_matrix(timestamptz) to authenticated;

-- ---------- series list ----------
-- One entry per series with member counts and the city-wide summary of its members (station,
-- category, week, H3 r8 cell). crimes_citywide is readable by every police role, so the list is
-- the same for everyone and never exposes FIR text or exact points.
create or replace function public.series_overview()
returns jsonb
language sql stable security invoker set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
      'series_id', s.series_id, 'name', s.name, 'status', s.status,
      'created_at', s.created_at, 'updated_at', s.updated_at, 'synthetic', s.synthetic,
      'has_dossier', coalesce(s.dossier ? 'text', false),
      'dossier_at', s.dossier ->> 'generated_at',
      'members', m.n, 'stations', m.stations, 'categories', m.categories,
      'week_from', m.week_from, 'week_to', m.week_to, 'cells', m.cells)
    order by s.updated_at desc, s.series_id), '[]'::jsonb)
  from public.series s
  cross join lateral (
    select count(*)::int as n,
           coalesce(jsonb_agg(distinct cw.station_id) filter (where cw.station_id is not null), '[]'::jsonb) as stations,
           coalesce(jsonb_agg(distinct cw.category) filter (where cw.category is not null), '[]'::jsonb) as categories,
           min(cw.week) as week_from, max(cw.week) as week_to,
           coalesce(jsonb_agg(cw.cell) filter (where cw.cell is not null), '[]'::jsonb) as cells
    from public.series_members sm
    left join public.crimes_citywide cw on cw.crime_id = sm.crime_id
    where sm.series_id = s.series_id
  ) m
$$;
revoke all on function public.series_overview() from public, anon;
grant execute on function public.series_overview() to authenticated;

-- Rollback:
--   drop function if exists public.station_link_matrix(timestamptz), public.series_overview();
