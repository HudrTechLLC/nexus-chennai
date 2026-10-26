-- 0004_01 · Police console: Realtime + decider names. Owner: nexus-4 (Web). Needs 0002_core.
--
-- 1. Realtime (WS3-07): link_alerts, alert_decisions, tips and notifications join the
--    supabase_realtime publication. Realtime postgres_changes applies each table's RLS, so an
--    officer only hears about rows they may already read. anon reads nothing (D-003).
-- 2. officer_names(uuid[]): rejected alerts show WHO decided (spec F4) to every police role, but
--    profiles RLS lets station officers and analysts read only their own row. This narrow
--    security-definer function returns just user_id, name and role, and only to police users.

-- ---------- 1. Realtime publication (idempotent) ----------
do $$
declare t text;
begin
  if not exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    create publication supabase_realtime;
  end if;
  foreach t in array array['link_alerts', 'alert_decisions', 'tips', 'notifications'] loop
    if not exists (
      select 1 from pg_publication_tables
      where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t
    ) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;

-- ---------- 2. officer_names ----------
create or replace function public.officer_names(p_ids uuid[])
returns table (user_id uuid, name text, role text)
language sql stable security definer set search_path = public as $$
  select p.user_id, p.name, p.role
  from public.profiles p
  where p.user_id = any(p_ids)
    and public.current_role_name() is not null
$$;
revoke all on function public.officer_names(uuid[]) from public, anon;
grant execute on function public.officer_names(uuid[]) to authenticated;

-- Rollback:
--   drop function if exists public.officer_names(uuid[]);
--   alter publication supabase_realtime drop table public.link_alerts, public.alert_decisions,
--     public.tips, public.notifications;
