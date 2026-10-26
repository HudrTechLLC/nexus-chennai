-- 0004_11 · Public appeal images expose only what the page needs (PUB-02 blurred stills; nexus-6 request).
-- Owner: nexus-4 (Web). Replaces public_appeals() from 0004_03; public_appeal(text) reads through it.
--
-- public_incidents.images entries (written by nexus-6's blur step) carry internal fields such as
-- evidence_id, method and added_at. The public payload now returns ONLY {path, width, height}:
--   * still only entries with blurred = true;
--   * path must look like '<id>/<name>.jpg|jpeg|png|webp' (no '..', no leading '/', no scheme),
--     because the page builds the storage URL from bucket + path and never from a stored URL;
--   * width / height only when they are positive integers, else null.
-- Grants are unchanged (create or replace keeps them).

create or replace function public.public_appeals()
returns jsonb
language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', p.public_incident_id, 'title', p.title, 'category', p.category, 'area', p.area_label,
    'cell', p.cell, 'week', p.week, 'time_window', p.time_window, 'summary', p.summary,
    'looking_for', to_jsonb(p.looking_for),
    'images', coalesce((
      select jsonb_agg(jsonb_build_object(
               'path', i ->> 'path',
               'width',  case when (i ->> 'width')  ~ '^[1-9][0-9]{0,4}$' then (i ->> 'width')::int  end,
               'height', case when (i ->> 'height') ~ '^[1-9][0-9]{0,4}$' then (i ->> 'height')::int end))
      from jsonb_array_elements(case when jsonb_typeof(p.images) = 'array' then p.images else '[]'::jsonb end) i
      where jsonb_typeof(i) = 'object'
        and coalesce((i ->> 'blurred')::boolean, false)
        and (i ->> 'path') ~ '^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+\.(jpg|jpeg|png|webp)$'), '[]'::jsonb),
    'tip_count', (select count(*) from public.tips t where t.public_incident_id = p.public_incident_id),
    'published_at', p.published_at
  ) order by p.published_at desc nulls last), '[]'::jsonb)
  from public.public_incidents p
  where p.status = 'published'
$$;

-- Rollback: re-run the public_appeals() definition from 0004_03_public_rpcs.sql.
