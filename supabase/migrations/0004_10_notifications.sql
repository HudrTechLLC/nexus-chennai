-- 0004_10 · Notifications and the mock outbox (spec B7 NOT-01 MUST, NOT-02 SHOULD; G2 /console/notifications; WS3-12).
-- Owner: nexus-4 (Web). Needs 0002 (notifications, outbox; nexus-1), 0004_04 (tip_reviews).
--
-- 1. outbox gains user_id (nullable, additive) so each officer can read their own mock messages.
--    The 0002 policy "admins read outbox" is unchanged.
-- 2. After every notification insert, mock outbox rows are written: email always, WhatsApp for the
--    urgent kinds. Status stays 'queued': NOTHING IS SENT (NOT-02). The trigger body cannot fail the
--    notification insert (the alert writer and the worker insert notifications mid-run).
--    Existing notifications are backfilled once (payload.backfilled = true).
-- 3. A tip marked useful AND linked to a case notifies the police users of that case's station
--    (NOT-01 "useful tips"). Without a linked case nothing is written.

-- ---------- 1. outbox.user_id ----------
alter table public.outbox add column if not exists user_id uuid references public.profiles (user_id) on delete cascade;
create index if not exists idx_outbox_user on public.outbox (user_id, created_at desc);

drop policy if exists "read own outbox" on public.outbox;
create policy "read own outbox" on public.outbox for select to authenticated
  using (user_id = auth.uid());

-- ---------- 2. mock outbox from notifications ----------
create or replace function public.mask_email(p_email text) returns text
language sql immutable set search_path = public as $$
  select case when p_email is null or position('@' in p_email) < 2 then null
              else left(p_email, 1) || '•••' || substr(p_email, position('@' in p_email)) end
$$;

create or replace function public.notification_to_outbox() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_name  text;
  v_email text;
  v_payload jsonb;
begin
  begin
    select p.name, u.email into v_name, v_email
    from public.profiles p left join auth.users u on u.id = p.user_id
    where p.user_id = new.user_id;

    v_payload := jsonb_build_object('notification_id', new.notification_id, 'kind', new.kind,
                                    'title', new.title, 'body', new.body, 'link', new.link, 'mock', true);

    insert into public.outbox (channel, recipient, payload, user_id)
    values ('email', coalesce(public.mask_email(v_email), coalesce(v_name, 'officer') || ' (no email on file)'),
            v_payload, new.user_id);

    if new.kind in ('link_alert', 'joint_case_proposal', 'taskforce_invite') then
      insert into public.outbox (channel, recipient, payload, user_id)
      values ('whatsapp', coalesce(v_name, 'officer') || ' (mock: no number on file)', v_payload, new.user_id);
    end if;
  exception when others then
    -- the mock outbox must never block a real notification
    raise warning 'notification_to_outbox skipped for notification %: %', new.notification_id, sqlerrm;
  end;
  return new;
end;
$$;

drop trigger if exists trg_notification_to_outbox on public.notifications;
create trigger trg_notification_to_outbox after insert on public.notifications
  for each row execute function public.notification_to_outbox();

-- Backfill (chief-approved): mock outbox rows for notifications written before this migration.
-- Derived rows, idempotent (skips any notification/channel pair already present), marked backfilled.
insert into public.outbox (channel, recipient, payload, user_id, created_at)
select ch.channel,
       case when ch.channel = 'email'
            then coalesce(public.mask_email(u.email), coalesce(p.name, 'officer') || ' (no email on file)')
            else coalesce(p.name, 'officer') || ' (mock: no number on file)' end,
       jsonb_build_object('notification_id', n.notification_id, 'kind', n.kind, 'title', n.title, 'body', n.body,
                          'link', n.link, 'mock', true, 'backfilled', true),
       n.user_id, n.created_at
from public.notifications n
join public.profiles p on p.user_id = n.user_id
left join auth.users u on u.id = n.user_id
cross join (values ('email'), ('whatsapp')) as ch (channel)
where (ch.channel = 'email' or n.kind in ('link_alert', 'joint_case_proposal', 'taskforce_invite'))
  and not exists (select 1 from public.outbox o
                  where o.channel = ch.channel and o.payload->>'notification_id' = n.notification_id::text);

-- ---------- 3. useful tip linked to a case -> its station ----------
create or replace function public.tip_review_notify() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.useful and new.crime_id is not null then
    begin
      insert into public.notifications (user_id, kind, title, body, link)
      select p.user_id, 'tip_useful',
             'Useful tip linked to ' || new.crime_id,
             'A tip was marked useful and linked to this case.',
             '/console/tips/' || new.tip_id
      from public.crimes c
      join public.profiles p on p.station_id = c.station_id
      where c.crime_id = new.crime_id and p.user_id is distinct from new."by";
    exception when others then
      raise warning 'tip_review_notify skipped for review %: %', new.review_id, sqlerrm;
    end;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_tip_review_notify on public.tip_reviews;
create trigger trg_tip_review_notify after insert on public.tip_reviews
  for each row execute function public.tip_review_notify();

revoke all on function public.notification_to_outbox(), public.tip_review_notify() from public, anon, authenticated;

-- Rollback:
--   drop trigger if exists trg_tip_review_notify on public.tip_reviews;
--   drop trigger if exists trg_notification_to_outbox on public.notifications;
--   drop function if exists public.tip_review_notify(), public.notification_to_outbox(), public.mask_email(text);
--   drop policy if exists "read own outbox" on public.outbox;
--   drop index if exists public.idx_outbox_user;
--   delete from public.outbox where payload->>'mock' = 'true';  -- rows this migration and its trigger wrote
--   alter table public.outbox drop column if exists user_id;
