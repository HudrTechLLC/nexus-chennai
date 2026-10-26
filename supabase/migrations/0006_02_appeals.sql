-- 0006_02 · Public appeal drafts and the publish guard (spec G1/G2, D3.13, WS4-07). Owner: nexus-3.
--
-- Flow: an officer requests a draft for a crime they may write (appeal_requests). The worker runs the
-- Sanitiser and writes public_incidents status='draft' with the service role. The officer edits and
-- publishes it in /console/appeals under the existing can_write_crime policies (0002). nexus-4's anon RPC
-- public_appeals() shows status='published' rows.
--
-- Guard: whenever a row IS published (insert, the draft -> published transition, or any later edit
-- of a published row), the trigger
--   * rejects text matching plate, phone/long-number, FIR-number or internal-id patterns;
--   * sets approved_by from the caller's profile ('<role>:<station or user>', D3.13), ignoring the form;
--     the service-role path (no auth.uid()) must supply it;
--   * sets published_at on the transition only (edits keep the original time).
-- Clock times are allowed: D3.13's own example asks for CCTV "between 7:30 and 8:00 pm".
-- The same leak list is checked in Python (app/agents/sanitiser.py) and TS (apps/web/lib/appeals.ts),
-- against one shared fixture (tests/agents/appeal_leaks.json).

create table if not exists public.appeal_requests (
  request_id         bigint generated always as identity primary key,
  crime_id           text not null references public.crimes (crime_id) on delete cascade,
  requested_by       uuid not null default auth.uid() references public.profiles (user_id),
  status             text not null default 'requested' check (status in ('requested', 'drafted', 'failed')),
  public_incident_id text references public.public_incidents (public_incident_id) on delete set null,
  error              text,
  requested_at       timestamptz not null default now(),
  processed_at       timestamptz
);
create index if not exists idx_appeal_requests_open on public.appeal_requests (requested_at) where status = 'requested';
create index if not exists idx_appeal_requests_crime on public.appeal_requests (crime_id);

alter table public.appeal_requests enable row level security;
revoke all on public.appeal_requests from anon, authenticated;
grant select, insert on public.appeal_requests to authenticated;

drop policy if exists "police read appeal_requests" on public.appeal_requests;
create policy "police read appeal_requests" on public.appeal_requests for select to authenticated
  using (public.can_read_crime(crime_id));
drop policy if exists "officers request appeal drafts" on public.appeal_requests;
create policy "officers request appeal drafts" on public.appeal_requests for insert to authenticated
  with check (public.can_write_crime(crime_id) and requested_by = auth.uid() and status = 'requested');

-- ---------- publish guard ----------
create or replace function public.appeal_text_leaks(p_text text) returns text
language sql immutable as $$
  select case
    when p_text is null then null
    -- plates, full or partial (upper case, as written on plates): TN 09 BX 4471, TN09??4471
    when p_text ~ '(^|[^A-Za-z0-9])[A-Z]{2} ?[0-9]{1,2} ?[A-Z?]{0,3} ?[0-9]{3,4}([^0-9]|$)' then 'plate'
    when p_text ~ '(^|[^A-Za-z])(CHN|PS)-[A-Z0-9-]+' then 'internal id'
    when p_text ~ '(^|[^0-9])[0-9]{1,5}/[0-9]{4}([^0-9]|$)' then 'FIR number'
    when p_text ~ '[0-9]{6,}' then 'phone or long number'
    else null
  end
$$;

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
revoke all on function public.appeal_text_leaks(text) from public, anon;
grant execute on function public.appeal_text_leaks(text) to authenticated;

drop trigger if exists trg_public_incidents_publish_guard on public.public_incidents;
create trigger trg_public_incidents_publish_guard before insert or update on public.public_incidents
  for each row execute function public.public_incidents_publish_guard();

-- Rollback:
--   drop trigger if exists trg_public_incidents_publish_guard on public.public_incidents;
--   drop function if exists public.public_incidents_publish_guard();
--   drop function if exists public.appeal_text_leaks(text);
--   drop table if exists public.appeal_requests;
