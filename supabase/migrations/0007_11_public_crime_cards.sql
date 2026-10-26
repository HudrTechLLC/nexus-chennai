-- 0007_11 · Public per-crime cards on /map and tips linked to a crime (WS4-11; spec G1, J5, PUB rules).
-- Owner: nexus-5. Needs 0004_03 (public RPCs, submit_tip), 0004_04 (tip_nearby_crimes), 0007_08 (appeal_case_leak).
--
-- anon still has NO table access (D-003). Two new SECURITY DEFINER reads, and nothing else, are granted to anon:
--   public_hex_crimes(cell, days, category)  the cards for one hex: safe fields only, same >=3 rule as the map
--   public_crime(public_id)                  one card by its opaque public id, or null
-- A card holds: opaque public id, category + sub-type, ISO week, time-of-day window, the hex's area label
-- (station locality, never a street/landmark/door), status in plain words, "part of a pattern" yes/no
-- (confirmed series only, no series id), an MO sentence built ONLY from allow-listed phrases, and links to
-- published appeals for that crime. Never: narrative, persons, points, address, plates, evidence, statements.
--
-- Public id = 'PC-' + 12 hex chars of HMAC-SHA256(crime_id, secret). The secret lives in a table no API role
-- can read, and the id helper is not executable by anon, so a guessed crime id cannot be confirmed.
-- Eligibility mirrors public_map_cells exactly: occurred in the last p_days (clamped 7..90), the hex has >=3
-- crimes in that window AND the crime's category has >=3 in that hex (so a card never reveals a rare type).
-- Cards sort by week desc then public id: never by time or crime id (they would leak time and FIR order).
--
-- Tips: submit_tip gains p_about (a crime public id), resolved here to tips.about_crime_id; the client never
-- sees a crime id. tip_nearby_crimes lists that crime first (from_about), so it lands in the case's triage.

-- ---------- secret for public ids (set once; a replay never rotates it, so shared links keep working) ----------
create table if not exists public.public_id_secret (
  id     boolean primary key default true check (id),
  secret bytea not null
);
insert into public.public_id_secret (id, secret)
select true, extensions.gen_random_bytes(32)
where not exists (select 1 from public.public_id_secret);
alter table public.public_id_secret enable row level security;
revoke all on public.public_id_secret from public, anon, authenticated;

-- ---------- allow-listed MO phrases (the ONLY text that reaches the public MO sentence) ----------
-- Verb phrases for approach / verbal / violence / escape, noun phrases for target_item. Never target or
-- place_type (they carry ages, gender and places). A tag not listed here is simply left out.
create table if not exists public.public_mo_phrases (
  field  text not null check (field in ('approach', 'verbal', 'target_item', 'violence', 'escape')),
  tag    text not null,
  phrase text not null check (phrase !~ '[0-9]'),
  primary key (field, tag)
);
alter table public.public_mo_phrases enable row level security;
revoke all on public.public_mo_phrases from public, anon, authenticated;
insert into public.public_mo_phrases (field, tag, phrase) values
  ('approach', 'two_wheeler_from_behind', 'came up from behind on a two-wheeler'),
  ('approach', 'on_foot', 'came on foot'),
  ('approach', 'on_foot_from_front', 'came on foot'),
  ('approach', 'walked_up_on_foot', 'came on foot'),
  ('approach', 'poses_as_ride_hailing_cab', 'posed as a ride-hailing cab'),
  ('approach', 'posed_as_ride_hailing_cab', 'posed as a ride-hailing cab'),
  ('approach', 'lift_offer', 'offered a lift'),
  ('approach', 'offered_lift_then_robbed', 'offered a lift'),
  ('approach', 'claiming_to_be_police_checking_documents', 'posed as police checking documents'),
  ('verbal', 'asked_for_directions', 'asked for directions'),
  ('verbal', 'claiming_to_be_police_checking_documents', 'claimed to be police checking documents'),
  ('target_item', 'gold_chain', 'a gold chain'),
  ('target_item', 'mobile_phone', 'a mobile phone'),
  ('target_item', 'cash_and_mobile_phone', 'cash and a mobile phone'),
  ('target_item', 'cash_and_mobile', 'cash and a mobile phone'),
  ('target_item', 'cash_mobile', 'cash and a mobile phone'),
  ('target_item', 'gold_jewellery_and_cash', 'gold jewellery and cash'),
  ('violence', 'push_and_fall', 'pushed the victim to the ground'),
  ('violence', 'pushed_and_fell', 'pushed the victim to the ground'),
  ('violence', 'push_causing_fall', 'pushed the victim to the ground'),
  ('violence', 'push', 'pushed the victim'),
  ('violence', 'threatened_with_knife', 'threatened the victim with a knife'),
  ('violence', 'threatened_with_a_knife', 'threatened the victim with a knife'),
  ('violence', 'knife_shown_to_threaten', 'threatened the victim with a knife'),
  ('violence', 'knife_threatened', 'threatened the victim with a knife'),
  ('violence', 'knife_threat', 'threatened the victim with a knife'),
  ('escape', 'on_two_wheeler_towards_main_road', 'fled on a two-wheeler'),
  ('escape', 'two_wheeler_towards_main_road', 'fled on a two-wheeler'),
  ('escape', 'on_the_two_wheeler_towards_main_road', 'fled on a two-wheeler'),
  ('escape', 'on_the_two_wheeler_towards_the_main_road', 'fled on a two-wheeler'),
  ('escape', 'on_two_wheeler', 'fled on a two-wheeler'),
  ('escape', 'on_a_two_wheeler', 'fled on a two-wheeler'),
  ('escape', 'two_wheeler', 'fled on a two-wheeler'),
  ('escape', 'on_motorcycle', 'fled on a motorcycle'),
  ('escape', 'on_foot', 'fled on foot'),
  ('escape', 'ran', 'fled on foot'),
  ('escape', 'fled_on_foot', 'fled on foot'),
  ('escape', 'ran_on_foot', 'fled on foot'),
  ('escape', 'autorickshaw', 'fled in an autorickshaw')
on conflict (field, tag) do update set phrase = excluded.phrase;

-- ---------- tips linked to a crime from its public card ----------
alter table public.tips add column if not exists about_crime_id text references public.crimes (crime_id) on delete set null;
create index if not exists idx_tips_about_crime on public.tips (about_crime_id);

-- ---------- private helpers (never executable by API roles) ----------
create or replace function public.crime_public_id(p_crime_id text) returns text
language sql stable security definer set search_path = public, extensions as $$
  select 'PC-' || upper(substr(encode(extensions.hmac(convert_to(p_crime_id, 'UTF8'),
                                                      (select secret from public.public_id_secret), 'sha256'), 'hex'), 1, 12))
$$;

-- Crimes a public card may show for a window: same predicate and cutoff as public_map_cells.
create or replace function public.public_card_pool(p_days integer)
returns table (crime_id text, cell text, category text)
language sql stable security definer set search_path = public as $$
  with d as (select least(greatest(coalesce(p_days, 30), 7), 90) as days, 3 as min_n),
  w as (
    select c.crime_id, c.h3_r8 as cell, c.category
    from public.crimes c, d
    where c.h3_r8 is not null and c.occurred_from >= now() - make_interval(days => d.days)
  ),
  tot as (select cell, count(*) as n from w group by cell),
  cat as (select cell, category, count(*) as n from w group by cell, category)
  select w.crime_id, w.cell, w.category
  from w
  join tot using (cell)
  join cat using (cell, category), d
  where tot.n >= d.min_n and cat.n >= d.min_n
$$;

-- Area label of a hex: the station nearest the centre of all crimes in it, without the "(E4)" code.
create or replace function public.public_area_label(p_cell text) returns text
language sql stable security definer set search_path = public, extensions as $$
  with ctr as (
    select st_setsrid(st_makepoint(avg(lon), avg(lat)), 4326) as g from public.crimes where h3_r8 = p_cell
  )
  select btrim(regexp_replace(s.name, '\s*\(.*\)\s*$', ''))
  from public.stations s, ctr
  where ctr.g is not null and s.centroid is not null
  order by st_distance(s.centroid, ctr.g), s.station_id
  limit 1
$$;

-- One plain-English MO sentence from allow-listed phrases only, or null when none apply.
create or replace function public.public_mo_summary(p_crime_id text) returns text
language sql stable security definer set search_path = public as $$
  with mo as (select cf.mo from public.crime_features cf where cf.crime_id = p_crime_id),
  ph as (
    select f.ord, coalesce(case when f.field = 'target_item' then 'took ' || p.phrase else p.phrase end, null) as phrase
    from mo,
         (values (1, 'approach'), (2, 'verbal'), (3, 'target_item'), (4, 'violence'), (5, 'escape')) f(ord, field)
    join public.public_mo_phrases p on p.field = f.field
    where p.tag = mo.mo ->> f.field
  ),
  parts as (select array_agg(phrase order by ord) as a from (select distinct on (phrase) ord, phrase from ph order by phrase, ord) x),
  subj as (
    select case when (mo.mo ->> 'offender_count') ~ '^[0-9]+$' then
             case (mo.mo ->> 'offender_count')::int when 1 then 'One person' when 2 then 'Two people'
                                                    when 3 then 'Three people' else 'Several people' end
           else 'Someone' end as s
    from mo
  )
  select case
    when parts.a is null or cardinality(parts.a) = 0 then null
    when cardinality(parts.a) = 1 then subj.s || ' ' || parts.a[1] || '.'
    else subj.s || ' ' || array_to_string(parts.a[1:cardinality(parts.a) - 1], ', ') || ' and ' || parts.a[cardinality(parts.a)] || '.'
  end
  from parts, subj
$$;

-- The public card for one crime (caller has already checked eligibility).
create or replace function public.public_crime_card(p_crime_id text, p_cell text) returns jsonb
language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'public_id', public.crime_public_id(c.crime_id),
    'category', c.category,
    'sub_type', c.sub_type,
    'week', c.week,
    'time_window', case
       when extract(hour from c.occurred_from at time zone 'Asia/Kolkata') between 5 and 11 then 'morning'
       when extract(hour from c.occurred_from at time zone 'Asia/Kolkata') between 12 and 16 then 'afternoon'
       when extract(hour from c.occurred_from at time zone 'Asia/Kolkata') between 17 and 20 then 'evening'
       else 'night' end,
    'cell', p_cell,
    'area', public.public_area_label(p_cell),
    'status', case c.status when 'charge_sheeted' then 'charge-sheeted' when 'closed' then 'closed' else 'open' end,
    'in_pattern', exists (select 1 from public.series_members m join public.series s using (series_id)
                          where m.crime_id = c.crime_id and s.status = 'confirmed'),
    'mo_summary', public.public_mo_summary(c.crime_id),
    'appeals', coalesce((select jsonb_agg(jsonb_build_object('id', p.public_incident_id, 'title', p.title)
                                          order by p.published_at desc nulls last, p.public_incident_id)
                         from public.public_incidents p
                         where p.crime_id = c.crime_id and p.status = 'published'), '[]'::jsonb))
  from public.crimes c
  where c.crime_id = p_crime_id
$$;

-- ---------- the two public reads ----------
create or replace function public.public_hex_crimes(p_cell text, p_days integer default 30, p_category text default null)
returns jsonb
language sql stable security definer set search_path = public as $$
  with cards as (
    select public.public_crime_card(pool.crime_id, pool.cell) as card
    from public.public_card_pool(p_days) pool
    where p_cell ~ '^88[0-9a-f]{13}$' and pool.cell = p_cell
      and (p_category is null or pool.category = p_category)
  )
  select jsonb_build_object(
    'cell', p_cell,
    'days', least(greatest(coalesce(p_days, 30), 7), 90),
    'area', case when exists (select 1 from cards) then public.public_area_label(p_cell) end,
    'cards', coalesce((select jsonb_agg(card order by card ->> 'week' desc, card ->> 'public_id') from cards), '[]'::jsonb))
$$;

create or replace function public.public_crime(p_public_id text) returns jsonb
language sql stable security definer set search_path = public as $$
  select public.public_crime_card(pool.crime_id, pool.cell)
  from public.public_card_pool(90) pool
  where p_public_id ~ '^PC-[0-9A-F]{12}$' and public.crime_public_id(pool.crime_id) = p_public_id
  limit 1
$$;

-- ---------- submit_tip with p_about (old signature dropped: two overloads would make every call ambiguous) ----------
drop function if exists public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text);
create or replace function public.submit_tip(
  p_appeal text, p_category text, p_text text, p_cell text, p_follow_up boolean,
  p_code text, p_passphrase text, p_media jsonb, p_tz text, p_about text default null
) returns jsonb
language plpgsql volatile security definer set search_path = public, extensions as $$
declare
  v_week  text := public.iso_week(now(), p_tz);
  v_id    text;
  v_hash  text;
  v_about text;
  m       jsonb;
  i       int := 0;
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
  if p_about is not null then
    select pool.crime_id into v_about from public.public_card_pool(90) pool
     where p_about ~ '^PC-[0-9A-F]{12}$' and public.crime_public_id(pool.crime_id) = p_about limit 1;
    if v_about is null then
      raise exception 'unknown crime' using errcode = '22023';
    end if;
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

  insert into public.tips (tip_id, public_incident_id, about_crime_id, channel, category, text, follow_up_enabled,
                           tip_code_hash, guard, approx_cell, received_week, status, synthetic)
  values (v_id, p_appeal, v_about, 'web', p_category, btrim(p_text), coalesce(p_follow_up, false),
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

-- ---------- triage: the crime a tip was sent about comes first ----------
create or replace function public.tip_nearby_crimes(p_tip_id text)
returns jsonb
language sql stable security invoker set search_path = public as $$
  with t as (
    select approx_cell, to_date(received_week, 'IYYY-"W"IW') as wk, public_incident_id, about_crime_id
    from public.tips where tip_id = p_tip_id
  ),
  appeal_crime as (
    select p.crime_id from public.public_incidents p, t where p.public_incident_id = t.public_incident_id
  ),
  hits as (
    select c.crime_id, c.station_id, c.fir_no, c.category, c.sub_type, c.occurred_from,
           (c.crime_id in (select crime_id from appeal_crime)) as from_appeal,
           (c.crime_id = (select about_crime_id from t)) is true as from_about
    from public.crimes c, t
    where c.crime_id in (select crime_id from appeal_crime)
       or c.crime_id = t.about_crime_id
       or (t.approx_cell is not null and c.h3_r8 = t.approx_cell
           and c.occurred_from >= t.wk - interval '14 days' and c.occurred_from < t.wk + interval '21 days')
  )
  select coalesce(jsonb_agg(jsonb_build_object(
    'crime_id', crime_id, 'station_id', station_id, 'fir_no', fir_no, 'category', category,
    'sub_type', sub_type, 'occurred_from', occurred_from, 'from_appeal', from_appeal, 'from_about', from_about)
    order by from_about desc, from_appeal desc, occurred_from desc), '[]'::jsonb)
  from (select * from hits order by from_about desc, from_appeal desc, occurred_from desc limit 12) h
$$;

-- ---------- grants: anon gets the two reads and submit_tip, nothing else ----------
revoke all on function public.crime_public_id(text), public.public_card_pool(integer), public.public_area_label(text),
  public.public_mo_summary(text), public.public_crime_card(text, text) from public, anon, authenticated;
revoke all on function public.public_hex_crimes(text, integer, text), public.public_crime(text),
  public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text, text) from public;
grant execute on function public.public_hex_crimes(text, integer, text), public.public_crime(text),
  public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text, text) to anon, authenticated;
revoke all on function public.tip_nearby_crimes(text) from public, anon;
grant execute on function public.tip_nearby_crimes(text) to authenticated;

-- Rollback:
--   drop function if exists public.public_hex_crimes(text, integer, text), public.public_crime(text),
--     public.public_crime_card(text, text), public.public_mo_summary(text), public.public_area_label(text),
--     public.public_card_pool(integer), public.crime_public_id(text);
--   drop function if exists public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text, text);
--   then re-run the submit_tip definition and grants from 0004_03, and tip_nearby_crimes from 0004_04;
--   alter table public.tips drop column if exists about_crime_id;
--   drop table if exists public.public_mo_phrases, public.public_id_secret;
