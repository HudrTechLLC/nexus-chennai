-- 0007_13 · public_map_cells carries each hex's area label (keyboard list of areas on the public map).
-- Owner: nexus-4 (Web). Needs 0004_03 (public_map_cells) and 0007_11 (public_area_label); numbered after
-- 0007_12 so a fresh replay creates the 0007_11 objects first.
--
-- The public map's "Areas with crimes" list (keyboard access to the crime cards) names each hexagon.
-- The name is the SAME label the card panel already shows for that hex (public_hex_crimes -> 'area',
-- i.e. public.public_area_label): the police station nearest the centre of ALL the hex's crimes, without
-- its "(E4)" code. Nothing new is revealed: the label is added only to cells that have cards (a category
-- passing the >=3 cutoff), exactly when public_hex_crimes would return it. Cells without cards get none.
--
-- Performance: this runs on every public map load. Calling public_area_label() per cell scans crimes once
-- per cell (+130 ms at 30 days, +750 ms at 90). Here the same expression is computed set-based instead:
-- one grouped pass over the card cells' crimes for the centres, then the nearest station per centre.
-- Output is identical to public_area_label() (parity checked for every card cell before applying).
-- Everything else in the function is unchanged (same window, same cutoff, same fields, same grants), except
-- that it now pins search_path = public, pg_temp like every SECURITY DEFINER function since 0007_11.

create or replace function public.public_map_cells(p_days integer default 30, p_min integer default 3)
returns jsonb
language sql stable security definer set search_path = public, pg_temp as $$
  with d as (select least(greatest(coalesce(p_days, 30), 7), 90) as days, greatest(coalesce(p_min, 3), 3) as min_n),
  agg as (
    select c.h3_r8 as cell, c.category, count(*)::int as n
    from public.crimes c, d
    where c.h3_r8 is not null and c.occurred_from >= now() - make_interval(days => d.days)
    group by c.h3_r8, c.category
  ),
  tot as (
    select cell, sum(n)::int as n from agg group by cell
  ),
  cells as (
    select t.cell, t.n,
      -- per-category counts obey the same cutoff, so a rare crime type in a cell is never revealed
      coalesce((select jsonb_object_agg(a.category, a.n) from agg a
                where a.cell = t.cell and a.n >= d.min_n), '{}'::jsonb) as by_category
    from tot t, d where t.n >= d.min_n
  ),
  -- centre of all crimes in each card cell (as public_area_label: every crime in the hex, not just the window)
  ctr as (
    select c.h3_r8 as cell, extensions.st_setsrid(extensions.st_makepoint(avg(c.lon), avg(c.lat)), 4326) as g
    from public.crimes c
    where c.h3_r8 in (select cell from cells where by_category <> '{}'::jsonb)
    group by c.h3_r8
  ),
  -- nearest station to that centre, without its code (as public_area_label)
  labels as (
    select ctr.cell,
      (select btrim(regexp_replace(s.name, '\s*\(.*\)\s*$', ''))
       from public.stations s
       where ctr.g is not null and s.centroid is not null
       order by extensions.st_distance(s.centroid, ctr.g), s.station_id
       limit 1) as area
    from ctr
  )
  select jsonb_build_object(
    'days', (select days from d),
    'min_count', (select min_n from d),
    'cells', coalesce((
      select jsonb_agg(jsonb_build_object(
        'cell', c.cell, 'n', c.n, 'by_category', c.by_category,
        -- the card panel's own label, only where the panel would show cards
        'area', l.area,
        'appeal', exists (select 1 from public.public_incidents p where p.status = 'published' and p.cell = c.cell)))
      from cells c left join labels l on l.cell = c.cell), '[]'::jsonb)
  )
$$;

-- grants are unchanged by create or replace (0004_03: anon + authenticated may execute)

-- Rollback:
--   re-apply the public_map_cells definition from 0004_03_public_rpcs.sql (identical, without 'area').
