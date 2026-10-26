-- 0004_03 · Public portal RPCs and tip intake (spec G1, J1, D3.6, D3.13; tracker WS4-02).
-- Owner: nexus-4 (Web). Needs 0002_core.
--
-- anon still has NO table access (D-003). The portal reaches data only through these narrow
-- SECURITY DEFINER functions, each returning the minimum:
--   public_appeals / public_appeal   published, sanitised appeals + tip count (never tip content)
--   public_map_cells                 H3 r8 crime counts with a minimum-count cutoff, no points
--   submit_tip                       stores a tip: no IP, user agent, contact or exact time
--   tip_status / tip_reply           tip code + passphrase; bcrypt verified inside Postgres
-- Passphrases are hashed with pgcrypto bcrypt (cost 12) inside the database, so the hash never
-- leaves it (DECISIONS D-023, deviation from J1's Argon2id). Wrong code and wrong passphrase give
-- the same answer; 5 failures lock a code for 15 minutes.
-- Tip files go to a private Storage bucket that anon may only INSERT into (write-only).

-- ---------- attempt counter for tip_status / tip_reply ----------
create table if not exists public.tip_attempts (
  tip_id       text primary key,
  failures     integer not null default 0,
  locked_until timestamptz
);
alter table public.tip_attempts enable row level security;
revoke all on public.tip_attempts from anon, authenticated;

-- ---------- helpers ----------
-- ISO week label ('2026-W43') in the given timezone; falls back to UTC for an unknown zone.
create or replace function public.iso_week(p_at timestamptz, p_tz text) returns text
language sql stable set search_path = public as $$
  select to_char(p_at at time zone coalesce(
           (select name from pg_timezone_names where name = p_tz limit 1), 'UTC'), 'IYYY-"W"IW')
$$;

-- Coarse status a tipster may see (never reveals quarantine or Guard verdicts).
create or replace function public.tip_public_status(p_status text) returns text
language sql immutable as $$
  select case p_status
    when 'reviewed' then 'reviewed'
    when 'closed' then 'closed'
    else 'received'
  end
$$;

-- ---------- appeals ----------
create or replace function public.public_appeals()
returns jsonb
language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', p.public_incident_id, 'title', p.title, 'category', p.category, 'area', p.area_label,
    'cell', p.cell, 'week', p.week, 'time_window', p.time_window, 'summary', p.summary,
    'looking_for', to_jsonb(p.looking_for),
    'images', coalesce((select jsonb_agg(i) from jsonb_array_elements(p.images) i
                        where coalesce((i ->> 'blurred')::boolean, false)), '[]'::jsonb),
    'tip_count', (select count(*) from public.tips t where t.public_incident_id = p.public_incident_id),
    'published_at', p.published_at
  ) order by p.published_at desc nulls last), '[]'::jsonb)
  from public.public_incidents p
  where p.status = 'published'
$$;

create or replace function public.public_appeal(p_id text)
returns jsonb
language sql stable security definer set search_path = public as $$
  select x from jsonb_array_elements(public.public_appeals()) x where x ->> 'id' = p_id limit 1
$$;

-- ---------- public hex map ----------
-- Counts per H3 r8 cell and category over the last p_days (7..90). Cells under the cutoff
-- (at least 3, or more if the caller asks) are dropped. 'appeal' marks cells with an open appeal.
create or replace function public.public_map_cells(p_days integer default 30, p_min integer default 3)
returns jsonb
language sql stable security definer set search_path = public as $$
  with d as (select least(greatest(coalesce(p_days, 30), 7), 90) as days, greatest(coalesce(p_min, 3), 3) as min_n),
  agg as (
    select c.h3_r8 as cell, c.category, count(*)::int as n
    from public.crimes c, d
    where c.h3_r8 is not null and c.occurred_from >= now() - make_interval(days => d.days)
    group by c.h3_r8, c.category
  ),
  tot as (
    select cell, sum(n)::int as n from agg group by cell
  )
  select jsonb_build_object(
    'days', (select days from d),
    'min_count', (select min_n from d),
    'cells', coalesce((
      select jsonb_agg(jsonb_build_object(
        'cell', t.cell, 'n', t.n,
        -- per-category counts obey the same cutoff, so a rare crime type in a cell is never revealed
        'by_category', coalesce((select jsonb_object_agg(a.category, a.n) from agg a
                                 where a.cell = t.cell and a.n >= d.min_n), '{}'::jsonb),
        'appeal', exists (select 1 from public.public_incidents p where p.status = 'published' and p.cell = t.cell)))
      from tot t, d where t.n >= d.min_n), '[]'::jsonb)
  )
$$;

-- ---------- submit_tip ----------
-- p_code / p_passphrase: only when the tipster wants replies; the code becomes the tip id.
-- p_media: [{"path":"tips/<uuid>.<ext>","kind":"image|audio","faces_blurred":bool}], files the
-- route handler already uploaded after stripping metadata.
create or replace function public.submit_tip(
  p_appeal text, p_category text, p_text text, p_cell text, p_follow_up boolean,
  p_code text, p_passphrase text, p_media jsonb, p_tz text
) returns jsonb
language plpgsql volatile security definer set search_path = public, extensions as $$
declare
  v_week text := public.iso_week(now(), p_tz);
  v_id   text;
  v_hash text;
  m      jsonb;
  i      int := 0;
begin
  if p_category is null or p_category not in ('vehicle_seen', 'person_seen', 'have_cctv', 'item_for_sale', 'something_else') then
    raise exception 'invalid category' using errcode = '22023';
  end if;
  if p_text is null or length(btrim(p_text)) < 3 or length(p_text) > 4000 then
    raise exception 'text must be 3 to 4000 characters' using errcode = '22023';
  end if;
  if p_cell is not null and p_cell !~ '^88[0-9a-f]{13}$' then
    raise exception 'area must be an H3 resolution-8 cell' using errcode = '22023';
  end if;
  if p_appeal is not null and not exists (
       select 1 from public.public_incidents where public_incident_id = p_appeal and status = 'published') then
    raise exception 'unknown appeal' using errcode = '22023';
  end if;
  if jsonb_typeof(coalesce(p_media, '[]'::jsonb)) <> 'array' or jsonb_array_length(coalesce(p_media, '[]'::jsonb)) > 5 then
    raise exception 'at most 5 files' using errcode = '22023';
  end if;
  -- per-cell weekly cap (throttling without identity, J1)
  if p_cell is not null and (select count(*) from public.tips where approx_cell = p_cell and received_week = v_week) >= 200 then
    raise exception 'too many tips for this area this week, please try later' using errcode = 'P0001';
  end if;

  if coalesce(p_follow_up, false) then
    if p_code is null or p_code !~ '^[A-HJ-NP-Z2-9]{8}$' then
      raise exception 'invalid tip code' using errcode = '22023';
    end if;
    if p_passphrase is null or length(p_passphrase) < 8 or length(p_passphrase) > 128 then
      raise exception 'passphrase must be 8 to 128 characters' using errcode = '22023';
    end if;
    v_id := 'TIP-' || p_code;
    v_hash := crypt(p_passphrase, gen_salt('bf', 12));
  else
    v_id := 'TIP-' || upper(encode(gen_random_bytes(5), 'hex'));
    v_hash := null;
  end if;

  insert into public.tips (tip_id, public_incident_id, channel, category, text, follow_up_enabled,
                           tip_code_hash, guard, approx_cell, received_week, status, synthetic)
  values (v_id, p_appeal, 'web', p_category, btrim(p_text), coalesce(p_follow_up, false),
          v_hash, null, p_cell, v_week, 'new', false);

  for m in select * from jsonb_array_elements(coalesce(p_media, '[]'::jsonb)) loop
    i := i + 1;
    if (m ->> 'path') !~ '^tips/[0-9a-f-]{36}\.(jpg|png|webp|mp3|m4a|ogg|webm)$'
       or (m ->> 'kind') not in ('image', 'audio') then
      raise exception 'invalid file reference' using errcode = '22023';
    end if;
    insert into public.tip_media (media_id, tip_id, kind, path, exif_stripped, faces_blurred, synthetic)
    values (v_id || '-M' || i, v_id, m ->> 'kind', m ->> 'path', true,
            coalesce((m ->> 'faces_blurred')::boolean, false), false);
  end loop;

  return jsonb_build_object('tip_id', v_id, 'received_week', v_week);
exception
  when unique_violation then
    raise exception 'tip code already used, please try again' using errcode = 'P0001';
end
$$;

-- ---------- tip status and reply ----------
-- Verifies code + passphrase inside Postgres. Returns {ok:false,error:'not_found'|'locked'} with the
-- same shape for a wrong code and a wrong passphrase; a dummy bcrypt runs when the code is unknown.
create or replace function public.tip_check(p_code text, p_passphrase text) returns text
language plpgsql volatile security definer set search_path = public, extensions as $$
declare
  v_id   text := 'TIP-' || upper(coalesce(p_code, ''));
  v_hash text;
  v_lock timestamptz;
  dummy  constant text := '$2a$12$RcLraqC5bJQPBZd7Yk6JB.5jo/bJOrBpP3.YDTE/0wFkTjHEcXlEu';
begin
  select locked_until into v_lock from public.tip_attempts where tip_id = v_id;
  if v_lock is not null and v_lock > now() then
    return 'locked';
  end if;
  select tip_code_hash into v_hash from public.tips where tip_id = v_id and follow_up_enabled;
  if v_hash is null then
    perform crypt(coalesce(p_passphrase, ''), dummy); -- same cost as a real check
  end if;
  if v_hash is not null and crypt(coalesce(p_passphrase, ''), v_hash) = v_hash then
    delete from public.tip_attempts where tip_id = v_id;
    return v_id;
  end if;
  insert into public.tip_attempts (tip_id, failures) values (v_id, 1)
  on conflict (tip_id) do update set
    failures = case when public.tip_attempts.locked_until < now() then 1 else public.tip_attempts.failures + 1 end,
    locked_until = case when (case when public.tip_attempts.locked_until < now() then 1 else public.tip_attempts.failures + 1 end) >= 5
                        then now() + interval '15 minutes' else null end;
  return 'not_found';
end
$$;
revoke all on function public.tip_check(text, text) from public, anon, authenticated;

create or replace function public.tip_status(p_code text, p_passphrase text)
returns jsonb
language plpgsql volatile security definer set search_path = public as $$
declare
  v text := public.tip_check(p_code, p_passphrase);
begin
  if v in ('not_found', 'locked') then
    return jsonb_build_object('ok', false, 'error', v);
  end if;
  return (
    select jsonb_build_object(
      'ok', true, 'tip_id', t.tip_id, 'status', public.tip_public_status(t.status), 'received_week', t.received_week,
      'messages', coalesce((select jsonb_agg(jsonb_build_object('sender', m.sender, 'text', m.text, 'on', m.at::date) order by m.at)
                            from public.tip_messages m where m.tip_id = t.tip_id), '[]'::jsonb))
    from public.tips t where t.tip_id = v);
end
$$;

create or replace function public.tip_reply(p_code text, p_passphrase text, p_text text)
returns jsonb
language plpgsql volatile security definer set search_path = public as $$
declare
  v text;
begin
  if p_text is null or length(btrim(p_text)) < 1 or length(p_text) > 2000 then
    return jsonb_build_object('ok', false, 'error', 'invalid_text');
  end if;
  v := public.tip_check(p_code, p_passphrase);
  if v in ('not_found', 'locked') then
    return jsonb_build_object('ok', false, 'error', v);
  end if;
  insert into public.tip_messages (tip_id, sender, text, at, author, synthetic)
  values (v, 'tipster', btrim(p_text), date_trunc('day', now()), null, false);
  return jsonb_build_object('ok', true);
end
$$;

-- ---------- grants: these and nothing else for anon ----------
revoke all on function public.public_appeals(), public.public_appeal(text), public.public_map_cells(integer, integer),
  public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text),
  public.tip_status(text, text), public.tip_reply(text, text, text),
  public.iso_week(timestamptz, text), public.tip_public_status(text) from public;
grant execute on function public.public_appeals(), public.public_appeal(text), public.public_map_cells(integer, integer),
  public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text),
  public.tip_status(text, text), public.tip_reply(text, text, text) to anon, authenticated;

-- ---------- tip files: private bucket, anon may only upload ----------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('tip-media', 'tip-media', false, 15728640,
        array['image/jpeg', 'image/png', 'image/webp', 'audio/mpeg', 'audio/mp4', 'audio/ogg', 'audio/webm'])
on conflict (id) do nothing;

drop policy if exists "anon uploads tip media" on storage.objects;
create policy "anon uploads tip media" on storage.objects for insert to anon
  with check (bucket_id = 'tip-media' and name ~ '^tips/[0-9a-f-]{36}\.(jpg|png|webp|mp3|m4a|ogg|webm)$');
drop policy if exists "police read tip media" on storage.objects;
create policy "police read tip media" on storage.objects for select to authenticated
  using (bucket_id = 'tip-media' and public.current_role_name() is not null);

-- Rollback:
--   drop policy if exists "anon uploads tip media" on storage.objects;
--   drop policy if exists "police read tip media" on storage.objects;
--   delete from storage.buckets where id = 'tip-media';  -- only when empty
--   drop function if exists public.public_appeals(), public.public_appeal(text), public.public_map_cells(integer, integer),
--     public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text), public.tip_check(text, text),
--     public.tip_status(text, text), public.tip_reply(text, text, text), public.iso_week(timestamptz, text),
--     public.tip_public_status(text);
--   drop table if exists public.tip_attempts;
