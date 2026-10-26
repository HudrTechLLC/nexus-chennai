-- 0007_03 · audit_log is append-only (spec J4; chief's decision D-030; nexus-5).
--
-- Every case-file view, export, decision, publish and FIR filing is audited (J4). For a police
-- system that record must not be editable or removable, not even for test data and not even by
-- the service role: RLS is bypassed by the service role, triggers are not. A clean-up therefore
-- leaves the original entries and ADDS an entry saying what it removed.
--
-- Rejects UPDATE and DELETE per row, and TRUNCATE per statement, for every role. audit_log has no
-- foreign keys pointing at other tables, so no cascade can try to delete from it.

create or replace function public.audit_log_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'audit_log is append-only: add a new entry instead of changing or removing one'
    using errcode = '42501';
end
$$;
revoke all on function public.audit_log_append_only() from public, anon, authenticated;

drop trigger if exists trg_audit_log_append_only on public.audit_log;
create trigger trg_audit_log_append_only before update or delete on public.audit_log
  for each row execute function public.audit_log_append_only();

drop trigger if exists trg_audit_log_no_truncate on public.audit_log;
create trigger trg_audit_log_no_truncate before truncate on public.audit_log
  for each statement execute function public.audit_log_append_only();

-- Rollback (needs the chief's OK, D-030):
--   drop trigger if exists trg_audit_log_no_truncate on public.audit_log;
--   drop trigger if exists trg_audit_log_append_only on public.audit_log;
--   drop function if exists public.audit_log_append_only();
