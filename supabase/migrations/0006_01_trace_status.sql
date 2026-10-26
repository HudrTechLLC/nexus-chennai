-- 0006_01 · Agent traces and system status for the console (spec G2 /console/system, D3.12).
-- Owner: agents lane (nexus-3), DECISIONS D-025.
--
-- trace_events: one row per line of logs/trace-<run_id>.jsonl, copied by the API's store when
--   a run finishes (rule R3: rows come only from the tracer's JSONL, never hand-made). Summaries
--   pass a redaction step before they get here (no keys or tokens, no tip text or passphrases).
-- system_status: one row per component (zetaris, nightshift lanes, engines, supabase, worker),
--   written by the worker heartbeat.
-- Read: analyst / supervisor / admin. anon and authenticated get no writes; the API writes with
-- the service role.

create table if not exists public.trace_events (
  run_id            text not null references public.runs (run_id) on delete cascade
                      deferrable initially deferred,   -- a late runs row never blocks a trace write
  seq               integer not null check (seq >= 0),
  ts                timestamptz not null,
  agent_name        text not null,
  action            text not null,
  input_summary     text,
  output_summary    text,
  target_agent      text,
  model             text,
  routed_model      text,
  receipt_id        text,
  zetaris_query_ids text[] not null default '{}',
  engine            text,
  confidence        real check (confidence is null or confidence between 0 and 1),
  retry_count       integer,
  status            text,
  extra             jsonb,
  primary key (run_id, seq)
);
create index if not exists idx_trace_events_run on public.trace_events (run_id, seq);
create index if not exists idx_trace_events_ts on public.trace_events (ts desc);

create table if not exists public.system_status (
  component  text primary key,          -- e.g. zetaris, nightshift:fast, engines, supabase, worker
  state      text not null check (state in ('live', 'sample', 'degraded', 'down', 'off')),
  detail     jsonb not null default '{}'::jsonb,
  checked_at timestamptz not null default now()
);

alter table public.trace_events  enable row level security;
alter table public.system_status enable row level security;

revoke all on public.trace_events, public.system_status from anon, authenticated;
grant select on public.trace_events, public.system_status to authenticated;

drop policy if exists "read trace_events (analyst+)" on public.trace_events;
create policy "read trace_events (analyst+)" on public.trace_events for select to authenticated
  using ((select public.current_role_name()) in ('analyst', 'supervisor', 'admin'));

drop policy if exists "read system_status (analyst+)" on public.system_status;
create policy "read system_status (analyst+)" on public.system_status for select to authenticated
  using ((select public.current_role_name()) in ('analyst', 'supervisor', 'admin'));

-- Rollback:
--   drop table if exists public.trace_events;
--   drop table if exists public.system_status;
