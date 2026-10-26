-- 0004_06_02 · Read RPCs for /console/memory and /console/graph (spec G2, E4; D-020; WS3-11). Owner: nexus-6 (web).
--
-- SECURITY INVOKER, so the 0002 / 0005 RLS still decides what each officer sees, and jsonb
-- results, so PostgREST's 1000-row cap never truncates them silently. Read-only.

-- ---------- H-MEM: where memories changed later scores ----------
-- One entry per (alert, memory) where the Linker applied an H-MEM adjustment: the alert's
-- memory_applied[] carries memory_id (the raw 'mem-N' id, = hmem_memories.memory_id) and,
-- when present, memory_ids[] for every memory behind one adjustment.
create or replace function public.hmem_effects()
returns jsonb
language sql stable security invoker set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
      'alert_id', x.alert_id, 'memory_id', x.memory_id, 'effect', x.effect, 'text', x.text,
      'score', x.score, 'band', x.band, 'status', x.status, 'kind', x.kind,
      'crimes', to_jsonb(x.crimes), 'stations', to_jsonb(x.stations), 'created_at', x.created_at)
    order by x.created_at, x.alert_id, x.memory_id), '[]'::jsonb)
  from (
    select distinct on (a.alert_id, mid.memory_id)
           a.alert_id, mid.memory_id, e ->> 'effect' as effect, e ->> 'text' as text,
           a.score, a.band, a.status, a.kind, a.crimes, a.stations, a.created_at
    from public.link_alerts a
    cross join lateral jsonb_array_elements(
      case when jsonb_typeof(a.memory_applied) = 'array' then a.memory_applied else '[]'::jsonb end) e
    cross join lateral (
      select v as memory_id
      from jsonb_array_elements_text(
        case when jsonb_typeof(e -> 'memory_ids') = 'array' and jsonb_array_length(e -> 'memory_ids') > 0
             then e -> 'memory_ids'
             when e ? 'memory_id' and jsonb_typeof(e -> 'memory_id') = 'string' then jsonb_build_array(e -> 'memory_id')
             else '[]'::jsonb end) v
    ) mid
    order by a.alert_id, mid.memory_id
  ) x
$$;
revoke all on function public.hmem_effects() from public, anon;
grant execute on function public.hmem_effects() to authenticated;

-- ---------- World Model neighbourhood ----------
-- p_seed: an entity id, or a canonical key / alias (plate, crime_id, phone, h3 cell, name).
--         Without a seed: the most-connected entities (optionally of p_types) as the starting set.
-- p_hops: 1..3 rings of neighbours around the seed set. p_types filters which entity types are added.
-- p_limit: node cap (1..600). Edges are those among the returned nodes. Provenance is aggregated
-- from wm_observations per subject (entity or edge) and source: count, first and last seen.
create or replace function public.wm_graph(p_seed text default null, p_hops int default 1,
                                           p_types text[] default null, p_limit int default 200)
returns jsonb
language plpgsql stable security invoker set search_path = public as $$
declare
  v_limit int := least(greatest(coalesce(p_limit, 200), 1), 600);
  v_hops  int := least(greatest(coalesce(p_hops, 1), 0), 3);
  v_types text[] := case when p_types is null or cardinality(p_types) = 0 then null else p_types end;
  v_ids   text[];
  v_front text[];
  v_edges text[];
  v_found boolean := true;
begin
  if p_seed is null or btrim(p_seed) = '' then
    select coalesce(array_agg(id order by deg desc, id), '{}') into v_ids from (
      select e.id, (select count(*) from public.wm_edges r where r.from_id = e.id or r.to_id = e.id) as deg
      from public.wm_entities e
      where v_types is null or e.type = any (v_types)
      order by deg desc, e.id
      limit least(v_limit, 40)
    ) t;
  else
    select coalesce(array_agg(id order by id), '{}') into v_ids from (
      select e.id from public.wm_entities e
      where e.id = btrim(p_seed) or e.key = btrim(p_seed) or btrim(p_seed) = any (e.aliases)
         or upper(regexp_replace(e.key, '\s', '', 'g')) = upper(regexp_replace(p_seed, '\s', '', 'g'))
      order by e.id limit 10
    ) t;
    v_found := cardinality(v_ids) > 0;
  end if;

  v_front := v_ids;
  for i in 1..v_hops loop
    exit when cardinality(v_front) = 0 or cardinality(v_ids) >= v_limit;
    select coalesce(array_agg(n order by n), '{}') into v_front from (
      select distinct x.n from (
        select r.to_id as n from public.wm_edges r where r.from_id = any (v_front)
        union
        select r.from_id from public.wm_edges r where r.to_id = any (v_front)
      ) x
      join public.wm_entities en on en.id = x.n
      where not (x.n = any (v_ids)) and (v_types is null or en.type = any (v_types))
      order by x.n
      limit greatest(v_limit - cardinality(v_ids), 0)
    ) t;
    v_ids := v_ids || v_front;
  end loop;

  select coalesce(array_agg(r.id), '{}') into v_edges
  from (select r.id from public.wm_edges r
        where r.from_id = any (v_ids) and r.to_id = any (v_ids) order by r.id limit 3000) r;

  return jsonb_build_object(
    'seed', p_seed, 'found', v_found, 'hops', v_hops, 'limit', v_limit,
    'truncated', cardinality(v_ids) >= v_limit,
    'nodes', coalesce((select jsonb_agg(jsonb_build_object(
        'id', e.id, 'type', e.type, 'key', e.key, 'attrs', e.attrs, 'aliases', to_jsonb(e.aliases),
        'synthetic', e.synthetic, 'created_at', e.created_at, 'updated_at', e.updated_at,
        'degree', (select count(*) from public.wm_edges r where r.from_id = e.id or r.to_id = e.id)) order by e.id)
      from public.wm_entities e where e.id = any (v_ids)), '[]'::jsonb),
    'edges', coalesce((select jsonb_agg(jsonb_build_object(
        'id', r.id, 'from', r.from_id, 'to', r.to_id, 'type', r.type, 'crime_id', r.crime_id,
        'synthetic', r.synthetic, 'created_at', r.created_at) order by r.id)
      from public.wm_edges r where r.id = any (v_edges)), '[]'::jsonb),
    'provenance', coalesce((select jsonb_agg(jsonb_build_object(
        'subject', p.subject_id, 'source', p.source, 'n', p.n, 'first', p.first_at, 'last', p.last_at)
        order by p.subject_id, p.source)
      from (select o.subject_id, o.source, count(*)::int as n, min(o.observed_at) as first_at, max(o.observed_at) as last_at
            from public.wm_observations o
            where o.subject_id = any (v_ids) or o.subject_id = any (v_edges)
            group by o.subject_id, o.source) p), '[]'::jsonb),
    'totals', jsonb_build_object(
      'entities', (select count(*) from public.wm_entities),
      'edges', (select count(*) from public.wm_edges),
      'by_type', coalesce((select jsonb_object_agg(type, n) from
                  (select type, count(*)::int as n from public.wm_entities group by type) t), '{}'::jsonb))
  );
end
$$;
revoke all on function public.wm_graph(text, int, text[], int) from public, anon;
grant execute on function public.wm_graph(text, int, text[], int) to authenticated;

-- Rollback:
--   drop function if exists public.hmem_effects(), public.wm_graph(text, int, text[], int);
