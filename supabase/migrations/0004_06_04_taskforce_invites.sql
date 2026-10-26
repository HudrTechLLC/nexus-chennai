-- 0004_06_04 · Task-force invite notifications (spec NOT-01 "task-force invites"; WS3-13/WS3-12). Owner: nexus-6 (web).
--
-- Redefines taskforce_set_member (0004_06_03) so that ADDING an officer to a task force also writes
-- one in-app notification for them: kind 'taskforce_invite' (nexus-4's notifications page labels it,
-- and their 0004_10 outbox trigger adds the mock email / WhatsApp rows). Changing a member's role or
-- removing them sends nothing. Same role check, audit row and signature as before.

create or replace function public.taskforce_set_member(p_id text, p_user uuid, p_role text default 'member')
returns void
language plpgsql security definer set search_path = public as $$
declare
  v_name    text;
  v_purpose text;
  v_new     boolean;
begin
  perform public.tf_require(array['supervisor', 'admin']);
  select name, purpose into v_name, v_purpose from public.taskforces where taskforce_id = p_id and status in ('proposed', 'active');
  if v_name is null then
    raise exception 'task force % is not open', p_id using errcode = '22023';
  end if;
  if p_role is null then
    delete from public.taskforce_members where taskforce_id = p_id and user_id = p_user;
  else
    if p_role not in ('lead', 'member') then raise exception 'role must be lead or member' using errcode = '22023'; end if;
    if not exists (select 1 from public.profiles where user_id = p_user) then
      raise exception 'unknown officer' using errcode = '22023';
    end if;
    v_new := not exists (select 1 from public.taskforce_members where taskforce_id = p_id and user_id = p_user);
    insert into public.taskforce_members (taskforce_id, user_id, role, added_by) values (p_id, p_user, p_role, auth.uid())
    on conflict (taskforce_id, user_id) do update set role = excluded.role;
    if v_new then
      insert into public.notifications (user_id, kind, title, body, link)
      values (p_user, 'taskforce_invite', left('Invited to task force ' || v_name, 200),
              case when v_purpose is null then null else left(v_purpose, 280) end,
              '/console/taskforces/' || p_id);
    end if;
  end if;
  perform public.tf_audit('set_taskforce_member', p_id, jsonb_build_object('user_id', p_user, 'role', p_role));
end $$;

revoke all on function public.taskforce_set_member(text, uuid, text) from public, anon;
grant execute on function public.taskforce_set_member(text, uuid, text) to authenticated;

-- Rollback: re-run the taskforce_set_member definition from 0004_06_03 (no notification insert).
