-- 0006_04 · runs.status gains 'interrupted' (agents lane, nexus-3; D-025 range). Approved by nexus-chief.
--
-- A run whose process was stopped (killed batch, crashed worker) never reaches finish_run and stayed
-- 'running' forever. The worker's stale-run sweep now marks a 'running' run with no trace event for
-- 15 minutes as 'interrupted' (trace event run_interrupted {last_event_at}). Check-constraint change
-- only: no data is rewritten here, no policies change.

do $$
declare c text;
begin
  -- The 0001 check was declared inline, so its name is generated; drop whichever check guards status.
  for c in
    select conname from pg_constraint
    where conrelid = 'public.runs'::regclass and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%status%'
  loop
    execute format('alter table public.runs drop constraint %I', c);
  end loop;
end $$;

alter table public.runs add constraint runs_status_check
  check (status in ('running', 'success', 'failed', 'not_implemented', 'interrupted'));

-- Rollback:
--   update public.runs set status = 'failed' where status = 'interrupted';
--   alter table public.runs drop constraint if exists runs_status_check;
--   alter table public.runs add constraint runs_status_check
--     check (status in ('running', 'success', 'failed', 'not_implemented'));
