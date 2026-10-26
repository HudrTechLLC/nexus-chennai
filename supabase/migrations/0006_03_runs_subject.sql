-- 0006_03 · runs.subject: which crime a run was about (agents lane, nexus-3; D-025 range).
--
-- The FIR form (WS3-10) toasts a link to the trace of the run that processed the new case. The
-- worker and /run set subject = crime_id for case runs; the console finds the newest run with
--   select run_id, status from runs where subject = $1 order by started desc limit 1
-- No new policies: runs keeps its 0001/0006_01 read rules; the API writes with the service role.
-- series.dossier (0002) already exists, so the Series analyst needs no column here.

alter table public.runs add column if not exists subject text;
create index if not exists idx_runs_subject on public.runs (subject, started desc) where subject is not null;

-- Rollback:
--   drop index if exists public.idx_runs_subject;
--   alter table public.runs drop column if exists subject;
