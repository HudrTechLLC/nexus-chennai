-- 0007_14 · Data-quality flags snapshot for live scoring (chief + Ravee, 27 Oct; nexus-2, Zetaris side reviewed by nexus-1).
--
-- Live, the Planner's q_dq_flags timed out on every case run: it filtered nexus.dq_flags by id, and Zetaris cannot
-- push that filter through the sorted UNION of rule views / the duplicate-FIR self-join (D-031), so every call
-- computed every flag (55-80 s; PATH2 §3). app.dq_status already runs the full pass; it now also stores the flags
-- here, and live q_dq_flags reads this table through Zetaris (R1) with `crime_id IN (...)`, which Spark JDBC pushes
-- down to Postgres. Sample mode and the files-mode path keep reading the rule views.
--
-- Shape (two deviations from the first sketch, both deliberate):
--   * PK (crime_id, rule, other_id), not (crime_id, rule): duplicate_fir yields one row per other crime, so a
--     crime with two duplicates would collide. other_id is '' for the single-record rules (q_dq_flags returns NULL
--     for '' so its output is unchanged). The PK leads with crime_id, so it is also the index the IN filter uses.
--   * detail is text, not jsonb: it is plain text today, and a plain text column maps over Spark JDBC without a
--     datasource view.
-- Access: RLS on. Only zetaris_reader may read (column grant + SELECT policy; it has no BYPASSRLS). No anon or
-- authenticated access. Only the service role writes, through replace_dq_flags_snapshot(), which swaps every row in
-- one transaction (PostgREST cannot run a multi-statement transaction).

create table if not exists public.dq_flags_snapshot (
  crime_id    text        not null,
  rule        text        not null check (rule in ('duplicate_fir', 'bad_geo', 'time_inconsistent', 'unmapped_section')),
  other_id    text        not null default '',
  severity    text        not null check (severity in ('info', 'warn')),
  detail      text        not null,
  computed_at timestamptz not null,
  primary key (crime_id, rule, other_id)
);
comment on table public.dq_flags_snapshot is
  'Crime-level data-quality flags from the last full app.dq_status pass (nexus.dq_flags), read by live q_dq_flags';

alter table public.dq_flags_snapshot enable row level security;
revoke all on public.dq_flags_snapshot from public, anon, authenticated;
grant select on public.dq_flags_snapshot to zetaris_reader;
drop policy if exists "zetaris reads dq_flags_snapshot" on public.dq_flags_snapshot;
create policy "zetaris reads dq_flags_snapshot" on public.dq_flags_snapshot for select to zetaris_reader using (true);

-- Replace the whole snapshot in one transaction. p_rows: [{crime_id, rule, other_id, severity, detail}, ...].
create or replace function public.replace_dq_flags_snapshot(p_rows jsonb, p_computed_at timestamptz)
returns integer
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_n integer;
begin
  if jsonb_typeof(p_rows) <> 'array' then
    raise exception 'p_rows must be a JSON array' using errcode = '22023';
  end if;
  delete from public.dq_flags_snapshot where true;
  insert into public.dq_flags_snapshot (crime_id, rule, other_id, severity, detail, computed_at)
  select r ->> 'crime_id', r ->> 'rule', coalesce(r ->> 'other_id', ''), r ->> 'severity', r ->> 'detail', p_computed_at
  from jsonb_array_elements(p_rows) r;
  get diagnostics v_n = row_count;
  return v_n;
end;
$$;
revoke execute on function public.replace_dq_flags_snapshot(jsonb, timestamptz) from public, anon, authenticated;
grant execute on function public.replace_dq_flags_snapshot(jsonb, timestamptz) to service_role;

-- Rollback:
--   drop function if exists public.replace_dq_flags_snapshot(jsonb, timestamptz);
--   drop table if exists public.dq_flags_snapshot;
--   (and on Zetaris: the sb registration of dq_flags_snapshot is dropped with it; live q_dq_flags then fails fast and
--   the Planner degrades, as before this migration)
