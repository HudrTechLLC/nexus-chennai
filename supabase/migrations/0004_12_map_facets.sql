-- 0004_12 · Pulse Map filter facets (spec DASH-04: station, zone, status, weapon, vehicle type, MO tag).
-- Owner: nexus-4 (Web). Needs 0002 (crimes, crime_vehicles, stations, crimes_citywide).
--
-- map_crimes() (0004_02) already carries station and status. This adds what it does not, WITHOUT
-- touching the map's load path: the console fetches map_facets() only when "More filters" is opened.
--
-- SECURITY INVOKER: every part is read under the caller's RLS.
--   * stations: id, name, zone (zone groups the station picker; null zone = "Unknown" in the UI);
--   * mo:      MO tag -> crime ids, from crimes_citywide.mo_tags (the city-wide summary every police
--              role may read, the same source as the console's MO chips);
--   * weapon:  crimes.weapon -> crime ids, and vehicle: crime_vehicles.vehicle_type -> crime ids.
--              These are full-row fields, so a station officer gets them only for cases they can read;
--              the map says so when such a filter is on.
-- jsonb result (no PostgREST row cap). Values are trimmed and lower-cased so filters match regardless
-- of how a source spelled them.

create or replace function public.map_facets()
returns jsonb
language sql stable security invoker set search_path = public as $$
  select jsonb_build_object(
    'stations', coalesce((select jsonb_agg(jsonb_build_array(station_id, name, zone) order by name) from public.stations), '[]'::jsonb),
    'weapon', coalesce((select jsonb_object_agg(w, ids) from (
                select lower(btrim(weapon)) as w, jsonb_agg(crime_id order by crime_id) as ids
                from public.crimes where nullif(btrim(weapon), '') is not null group by 1) x), '{}'::jsonb),
    'vehicle', coalesce((select jsonb_object_agg(v, ids) from (
                select lower(btrim(vehicle_type)) as v, jsonb_agg(distinct crime_id) as ids
                from public.crime_vehicles where nullif(btrim(vehicle_type), '') is not null group by 1) x), '{}'::jsonb),
    'mo', coalesce((select jsonb_object_agg(t, ids) from (
                select lower(btrim(tag)) as t, jsonb_agg(distinct crime_id) as ids
                from public.crimes_citywide, unnest(mo_tags) as tag
                where nullif(btrim(tag), '') is not null group by 1) x), '{}'::jsonb)
  )
$$;

revoke all on function public.map_facets() from public, anon;
grant execute on function public.map_facets() to authenticated;

-- Rollback:
--   drop function if exists public.map_facets();
