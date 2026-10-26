-- 0007_16 · Ask Nexus: plain-English questions answered from named registry queries (WS3-30, chief + Ravee, 27 Oct;
-- nexus-5 backend, nexus-4 UI).
--
-- Vercel cannot reach Zetaris (D-019), so the console only writes a question row and polls it. The worker claims the
-- row, asks the fast lane (Nemotron Lightning) for a PLAN of named registry queries with parameters (never SQL, R1),
-- runs them through Zetaris and writes the answer back here. Linking, scoring and the judge path are untouched.
--
-- What the answer holds: crime ids and a short reason per row, never case details. The console reads the display
-- fields from `crimes` with the asker's own client, so crimes RLS (can_read_crime) decides what each user sees; an
-- id the user cannot read is counted, never shown.
--
-- Access:
--   * analyst, supervisor, admin may INSERT a question (only the `question` column; everything else is defaulted)
--     and SELECT their own rows. Station officers and anon: nothing.
--   * no UPDATE or DELETE for API roles; only the service role (the worker) writes status, plan and answer.
--   * at most 3 unanswered questions per user (ask_questions_guard), so a stuck worker cannot pile up a queue.

create table if not exists public.ask_questions (
  question_id  uuid        primary key default gen_random_uuid(),
  asked_by     uuid        not null default auth.uid() references public.profiles (user_id) on delete cascade,
  question     text        not null check (char_length(btrim(question)) between 3 and 300),
  status       text        not null default 'queued'
                           check (status in ('queued', 'planning', 'running', 'answered', 'unmappable', 'failed')),
  plan         jsonb,
  answer       jsonb,
  run_id       text,
  model        text,
  routed_model text,
  receipt_id   text,
  error        text,
  created_at   timestamptz not null default now(),
  started_at   timestamptz,
  answered_at  timestamptz
);
comment on table public.ask_questions is
  'Ask Nexus (WS3-30): an analyst''s question, the worker''s plan of named registry queries and the cited answer';
create index if not exists idx_ask_questions_queue on public.ask_questions (created_at) where status = 'queued';
create index if not exists idx_ask_questions_mine on public.ask_questions (asked_by, created_at desc);

alter table public.ask_questions enable row level security;
revoke all on public.ask_questions from anon, authenticated;
grant select on public.ask_questions to authenticated;
grant insert (question) on public.ask_questions to authenticated;

drop policy if exists "analysts read own questions" on public.ask_questions;
create policy "analysts read own questions" on public.ask_questions for select to authenticated
  using (asked_by = auth.uid() and (select public.current_role_name()) in ('analyst', 'supervisor', 'admin'));
drop policy if exists "analysts ask questions" on public.ask_questions;
create policy "analysts ask questions" on public.ask_questions for insert to authenticated
  with check (asked_by = auth.uid() and status = 'queued'
              and (select public.current_role_name()) in ('analyst', 'supervisor', 'admin'));

-- At most 3 unanswered questions per user. SECURITY DEFINER so the count sees the user's rows regardless of RLS;
-- search_path pinned (0007_11 condition).
create or replace function public.ask_questions_guard() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if new.asked_by is not null and (
       select count(*) from public.ask_questions q
       where q.asked_by = new.asked_by and q.status in ('queued', 'planning', 'running')) >= 3 then
    raise exception 'you already have 3 questions waiting; wait for an answer first'
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;
revoke execute on function public.ask_questions_guard() from public, anon, authenticated;

drop trigger if exists trg_ask_questions_guard on public.ask_questions;
create trigger trg_ask_questions_guard before insert on public.ask_questions
  for each row execute function public.ask_questions_guard();

-- Rollback:
--   drop trigger if exists trg_ask_questions_guard on public.ask_questions;
--   drop function if exists public.ask_questions_guard();
--   drop table if exists public.ask_questions;
