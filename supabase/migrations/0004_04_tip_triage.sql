-- 0004_04 · Tip triage in the console (spec G2 /console/tips, tracker WS4-08). Owner: nexus-4.
-- Needs 0002_core and 0004_03.
--
-- 0002 lets police read tips and reply (tip_messages) but not change a tip. Triage adds:
--   tip_reviews        one row per officer verdict: useful / not useful, optional linked crime, note
--   review_tip(...)    records the verdict as the signed-in officer and marks the tip 'reviewed'
--   tip_nearby_crimes  cases in the tip's H3 r8 cell within -2..+3 weeks of the week it arrived
--                      (SECURITY INVOKER, so a station officer only sees their own station's cases)
-- Tips stay untrusted data: nothing here interprets their text.

create table if not exists public.tip_reviews (
  review_id bigint generated always as identity primary key,
  tip_id    text not null references public.tips (tip_id) on delete cascade,
  useful    boolean not null,
  crime_id  text references public.crimes (crime_id) on delete set null,
  note      text check (note is null or length(note) <= 2000),
  by        uuid not null default auth.uid() references public.profiles (user_id),
  at        timestamptz not null default now()
);
create index if not exists idx_tip_reviews_tip on public.tip_reviews (tip_id, at desc);

alter table public.tip_reviews enable row level security;
revoke all on public.tip_reviews from anon, authenticated;
grant select on public.tip_reviews to authenticated;
create policy "police read tip_reviews" on public.tip_reviews for select to authenticated
  using ((select public.current_role_name()) is not null);
-- Inserts go only through review_tip(), which also updates the tip status.

create or replace function public.review_tip(p_tip_id text, p_useful boolean, p_crime_id text default null, p_note text default null)
returns jsonb
language plpgsql volatile security definer set search_path = public as $$
declare
  v_role text := public.current_role_name();
begin
  if v_role is null then
    raise exception 'not a police user' using errcode = '42501';
  end if;
  if p_useful is null then
    raise exception 'useful must be true or false' using errcode = '22023';
  end if;
  if not exists (select 1 from public.tips where tip_id = p_tip_id) then
    raise exception 'unknown tip' using errcode = '22023';
  end if;
  -- a linked case must be one the officer may read
  if p_crime_id is not null and not public.can_read_crime(p_crime_id) then
    raise exception 'you cannot link that case' using errcode = '42501';
  end if;
  insert into public.tip_reviews (tip_id, useful, crime_id, note, by)
  values (p_tip_id, p_useful, p_crime_id, nullif(btrim(coalesce(p_note, '')), ''), auth.uid());
  update public.tips set status = 'reviewed' where tip_id = p_tip_id and status <> 'closed';
  insert into public.audit_log (who, what, object_type, object_id, details)
  values (auth.uid(), 'review_tip', 'tip', p_tip_id, jsonb_build_object('useful', p_useful, 'crime_id', p_crime_id));
  return jsonb_build_object('ok', true);
end
$$;
revoke all on function public.review_tip(text, boolean, text, text) from public, anon;
grant execute on function public.review_tip(text, boolean, text, text) to authenticated;

create or replace function public.tip_nearby_crimes(p_tip_id text)
returns jsonb
language sql stable security invoker set search_path = public as $$
  with t as (
    select approx_cell, to_date(received_week, 'IYYY-"W"IW') as wk, public_incident_id
    from public.tips where tip_id = p_tip_id
  ),
  appeal_crime as (
    select p.crime_id from public.public_incidents p, t where p.public_incident_id = t.public_incident_id
  ),
  hits as (
    select c.crime_id, c.station_id, c.fir_no, c.category, c.sub_type, c.occurred_from,
           (c.crime_id in (select crime_id from appeal_crime)) as from_appeal
    from public.crimes c, t
    where c.crime_id in (select crime_id from appeal_crime)
       or (t.approx_cell is not null and c.h3_r8 = t.approx_cell
           and c.occurred_from >= t.wk - interval '14 days' and c.occurred_from < t.wk + interval '21 days')
  )
  select coalesce(jsonb_agg(jsonb_build_object(
    'crime_id', crime_id, 'station_id', station_id, 'fir_no', fir_no, 'category', category,
    'sub_type', sub_type, 'occurred_from', occurred_from, 'from_appeal', from_appeal)
    order by from_appeal desc, occurred_from desc), '[]'::jsonb)
  from (select * from hits order by from_appeal desc, occurred_from desc limit 12) h
$$;
revoke all on function public.tip_nearby_crimes(text) from public, anon;
grant execute on function public.tip_nearby_crimes(text) to authenticated;

-- Rollback:
--   drop function if exists public.review_tip(text, boolean, text, text), public.tip_nearby_crimes(text);
--   drop table if exists public.tip_reviews;
