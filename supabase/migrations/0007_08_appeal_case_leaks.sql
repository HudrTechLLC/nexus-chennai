-- 0007_08 · The appeal publish guard also blocks names of people in the case and its address (nexus-5).
-- Appeals audit item 3 (chief, 26 Oct). Extends 0006_02's public_incidents_publish_guard; the pattern
-- checks (plate, internal id, FIR number, long number) are unchanged.
--
-- Per-case terms, built from the appeal's own crime (same rule in app/agents/sanitiser.py case_terms and
-- apps/web/lib/appeals.ts caseTerms; shared fixture tests/agents/appeal_leaks.json → case_leaks):
--   * every person linked to the crime (person_links, any role): the name, the name without leading
--     initials ("B. Karthik" → "Karthik"), each part around " alias ", and each alias; 3+ characters;
--   * from the crime's address, the landmark after near / opp / opposite / behind / next to, up to the next
--     comma ("near Saligramam Bus Depot, Vadapalani" → "Saligramam Bus Depot"), and, when the address starts
--     with a door number, the door number plus the street ("12/4, 1st Cross Street"); 6+ characters.
--     A plain road or locality is NOT a term: the Sanitiser's area label names the road on purpose.
-- A term matches as a whole word, ignoring case and runs of whitespace. Names are checked first.
-- The helpers are security definer and NOT callable by API roles: called directly, they would tell a
-- caller whether a word is the name of someone in a case. The definer trigger calls them as owner.

create or replace function public.appeal_case_terms(p_crime text)
returns table (term text, kind text)
language sql stable security definer set search_path = public as $$
  with names as (
    select lower(regexp_replace(trim(t), '\s+', ' ', 'g')) as term
    from person_links l
    join persons p on p.person_id = l.person_id
    cross join lateral unnest(
      array[coalesce(p.name, ''), regexp_replace(coalesce(p.name, ''), '^(\s*[A-Za-z]\.)+\s*', '')]
      || regexp_split_to_array(coalesce(p.name, ''), '\s+alias\s+', 'i')
      || coalesce(p.aliases, '{}'::text[])
    ) as t
    where l.crime_id = p_crime
  ),
  addr as (
    select lower(regexp_replace(trim(coalesce(c.address, '')), '\s+', ' ', 'g')) as a
    from crimes c where c.crime_id = p_crime
  ),
  places as (
    -- the landmark: "near saligramam bus depot, vadapalani" -> "saligramam bus depot"
    select trim(substring(a from '(?:^|[ ,])(?:near|opp\.?|opposite|behind|next to)\s+([^,]+)')) as term from addr
    union
    -- a door address: "12/4, 1st cross street, kodungaiyur" -> "12/4, 1st cross street"
    select trim((regexp_match(a, '^(\d+[a-z0-9/-]*\s*,\s*[^,]+)'))[1]) from addr
  )
  select distinct n.term, 'person name from the case' from names n where length(n.term) >= 3
  union
  select p.term, 'place from the case address' from places p
  where length(p.term) >= 6 and p.term not in (select n.term from names n)
$$;

create or replace function public.appeal_case_leak(p_crime text, p_text text) returns text
language sql stable security definer set search_path = public as $$
  select t.kind
  from public.appeal_case_terms(p_crime) t
  where lower(regexp_replace(coalesce(p_text, ''), '\s+', ' ', 'g'))
        ~ ('(^|[^a-z0-9])' || regexp_replace(t.term, '([.^$*+?()\[\]{}|\\-])', '\\\1', 'g') || '($|[^a-z0-9])')
  order by (t.kind = 'person name from the case') desc
  limit 1
$$;

revoke all on function public.appeal_case_terms(text) from public, anon, authenticated;
revoke all on function public.appeal_case_leak(text, text) from public, anon, authenticated;

-- Same guard as 0006_02, plus the per-case check after the pattern check.
create or replace function public.public_incidents_publish_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_leak text;
  v_item text;
  v_role text;
  v_station text;
begin
  if new.status <> 'published' then
    return new;
  end if;
  v_leak := coalesce(public.appeal_text_leaks(new.title), public.appeal_text_leaks(new.summary));
  if v_leak is null then
    foreach v_item in array coalesce(new.looking_for, '{}'::text[]) loop
      v_leak := public.appeal_text_leaks(v_item);
      exit when v_leak is not null;
    end loop;
  end if;
  if v_leak is null and new.crime_id is not null then
    v_leak := coalesce(public.appeal_case_leak(new.crime_id, new.title), public.appeal_case_leak(new.crime_id, new.summary));
    if v_leak is null then
      foreach v_item in array coalesce(new.looking_for, '{}'::text[]) loop
        v_leak := public.appeal_case_leak(new.crime_id, v_item);
        exit when v_leak is not null;
      end loop;
    end if;
  end if;
  if v_leak is not null then
    raise exception 'appeal text contains a %; remove it before publishing', v_leak using errcode = 'check_violation';
  end if;
  if auth.uid() is not null then
    select p.role, p.station_id into v_role, v_station from public.profiles p where p.user_id = auth.uid();
    if v_role is null then
      raise exception 'only a police user can publish an appeal' using errcode = 'insufficient_privilege';
    end if;
    new.approved_by := v_role || ':' || coalesce(v_station, auth.uid()::text);
  elsif new.approved_by is null then
    raise exception 'approved_by is required to publish' using errcode = 'not_null_violation';
  end if;
  if tg_op = 'INSERT' or old.status is distinct from 'published' then
    new.published_at := now();
  else
    new.published_at := old.published_at;
  end if;
  return new;
end
$$;
revoke all on function public.public_incidents_publish_guard() from public, anon;

-- Rollback:
--   re-run the public_incidents_publish_guard definition from 0006_02_appeals.sql;
--   drop function if exists public.appeal_case_leak(text, text);
--   drop function if exists public.appeal_case_terms(text);
