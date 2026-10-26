-- 0004_06_03 · Joint task forces (spec G2 /console/taskforces, LNK-09, A4 roles; WS3-13). Owner: nexus-6 (web).
--
-- Lifecycle: an analyst, supervisor or admin PROPOSES a task force (from a series, an approved
-- alert, or neither) → a supervisor or admin APPROVES it (active) or DECLINES it → later CLOSES it.
-- Members, linked cases and notes hang off it. Every write goes through a SECURITY DEFINER RPC that
-- checks the caller's role, takes the actor from auth.uid() (never a parameter) and writes audit_log
-- (NFR-08). Direct INSERT / UPDATE grants from 0002 are revoked, so RLS-by-RPC is the only write path.
-- Write RPCs are VOLATILE (PostgREST runs STABLE functions read-only).
--
-- NOTE: alters 0002 tables owned by nexus-1 (taskforces status check + columns; grants), agreed via
-- nexus-chief. Both tables were empty when this was written.

-- ---------- schema ----------
alter table public.taskforces drop constraint if exists taskforces_status_check;
alter table public.taskforces add constraint taskforces_status_check
  check (status in ('proposed', 'active', 'closed', 'declined'));
alter table public.taskforces alter column status set default 'proposed';
alter table public.taskforces add column if not exists purpose     text;
alter table public.taskforces add column if not exists alert_id    text;             -- plain text, like hmem (alerts may be re-run)
alter table public.taskforces add column if not exists decided_by  uuid references public.profiles (user_id);
alter table public.taskforces add column if not exists decided_at  timestamptz;
alter table public.taskforces add column if not exists closed_at   timestamptz;
alter table public.taskforces add column if not exists synthetic   boolean not null default false;
create index if not exists idx_taskforces_series on public.taskforces (series_id);
create index if not exists idx_taskforces_status on public.taskforces (status, created_at desc);

alter table public.taskforce_members add column if not exists added_by uuid references public.profiles (user_id);
alter table public.taskforce_members add column if not exists added_at timestamptz not null default now();
create index if not exists idx_taskforce_members_user on public.taskforce_members (user_id);

create table if not exists public.taskforce_cases (
  taskforce_id text not null references public.taskforces (taskforce_id) on delete cascade,
  crime_id     text not null references public.crimes (crime_id) on delete cascade,
  added_by     uuid references public.profiles (user_id),
  added_at     timestamptz not null default now(),
  primary key (taskforce_id, crime_id)
);
create index if not exists idx_taskforce_cases_crime on public.taskforce_cases (crime_id);

create table if not exists public.taskforce_notes (
  note_id      bigint generated always as identity primary key,
  taskforce_id text not null references public.taskforces (taskforce_id) on delete cascade,
  author       uuid not null references public.profiles (user_id),
  kind         text not null default 'note' check (kind in ('note', 'decision')),
  text         text not null check (char_length(text) between 1 and 2000),
  at           timestamptz not null default now()
);
create index if not exists idx_taskforce_notes_tf on public.taskforce_notes (taskforce_id, at);

-- Notes are a record: append-only, even for the service role (same pattern as 0005).
drop trigger if exists trg_taskforce_notes_append_only on public.taskforce_notes;
create trigger trg_taskforce_notes_append_only before update or delete on public.taskforce_notes
  for each row execute function public.engines_append_only();

-- ---------- access ----------
alter table public.taskforce_cases enable row level security;
alter table public.taskforce_notes enable row level security;
revoke all on public.taskforce_cases, public.taskforce_notes from anon, authenticated;
revoke all on sequence public.taskforce_notes_note_id_seq from anon, authenticated;
revoke insert, update, delete on public.taskforces, public.taskforce_members from anon, authenticated;
grant select on public.taskforce_cases, public.taskforce_notes to authenticated;

drop policy if exists "supervisors manage taskforces" on public.taskforces;
drop policy if exists "supervisors edit taskforces" on public.taskforces;
drop policy if exists "supervisors add taskforce_members" on public.taskforce_members;
drop policy if exists "police read taskforce_cases" on public.taskforce_cases;
create policy "police read taskforce_cases" on public.taskforce_cases for select to authenticated
  using ((select public.current_role_name()) is not null);
drop policy if exists "police read taskforce_notes" on public.taskforce_notes;
create policy "police read taskforce_notes" on public.taskforce_notes for select to authenticated
  using ((select public.current_role_name()) is not null);

-- ---------- helpers ----------
create or replace function public.tf_require(p_roles text[]) returns text
language plpgsql stable security definer set search_path = public as $$
declare r text := public.current_role_name();
begin
  if r is null or not (r = any (p_roles)) then
    raise exception 'not allowed for role %', coalesce(r, 'none') using errcode = '42501';
  end if;
  return r;
end $$;
revoke all on function public.tf_require(text[]) from public, anon, authenticated;

create or replace function public.tf_audit(p_what text, p_id text, p_details jsonb) returns void
language sql security definer set search_path = public as $$
  insert into public.audit_log (who, what, object_type, object_id, details) values (auth.uid(), p_what, 'taskforce', p_id, p_details)
$$;
revoke all on function public.tf_audit(text, text, jsonb) from public, anon, authenticated;

-- Adds cases that exist; returns how many were new.
create or replace function public.tf_add_cases(p_id text, p_crime_ids text[]) returns int
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  insert into public.taskforce_cases (taskforce_id, crime_id, added_by)
  select p_id, c.crime_id, auth.uid() from public.crimes c
  where c.crime_id = any (coalesce(p_crime_ids, '{}'))
  on conflict do nothing;
  get diagnostics n = row_count;
  return n;
end $$;
revoke all on function public.tf_add_cases(text, text[]) from public, anon, authenticated;

-- ---------- RPCs (the only write path) ----------
-- Propose: analyst, supervisor, admin. From a series (its members become the linked cases), an
-- alert (its crimes), and/or explicit crime ids. Returns the new taskforce_id.
create or replace function public.taskforce_propose(p_name text, p_purpose text default null, p_series_id text default null,
                                                    p_alert_id text default null, p_crime_ids text[] default null)
returns text
language plpgsql security definer set search_path = public as $$
declare
  v_id    text;
  v_ids   text[] := coalesce(p_crime_ids, '{}');
  v_syn   boolean := false;
begin
  perform public.tf_require(array['analyst', 'supervisor', 'admin']);
  if p_name is null or char_length(btrim(p_name)) not between 3 and 120 then
    raise exception 'name must be 3–120 characters' using errcode = '22023';
  end if;
  if p_series_id is not null then
    if not exists (select 1 from public.series where series_id = p_series_id) then
      raise exception 'unknown series %', p_series_id using errcode = '22023';
    end if;
    v_ids := v_ids || array(select crime_id from public.series_members where series_id = p_series_id);
    select v_syn or s.synthetic into v_syn from public.series s where s.series_id = p_series_id;
  end if;
  if p_alert_id is not null then
    if not exists (select 1 from public.link_alerts where alert_id = p_alert_id) then
      raise exception 'unknown alert %', p_alert_id using errcode = '22023';
    end if;
    v_ids := v_ids || (select crimes from public.link_alerts where alert_id = p_alert_id);
    select v_syn or a.synthetic into v_syn from public.link_alerts a where a.alert_id = p_alert_id;
  end if;
  select v_syn or coalesce(bool_or(c.synthetic), false) into v_syn from public.crimes c where c.crime_id = any (v_ids);

  v_id := 'TF-' || to_char(now() at time zone 'Asia/Kolkata', 'YYYY') || '-' || upper(substr(md5(gen_random_uuid()::text), 1, 8));
  insert into public.taskforces (taskforce_id, name, purpose, series_id, alert_id, status, created_by, synthetic)
  values (v_id, btrim(p_name), nullif(btrim(coalesce(p_purpose, '')), ''), p_series_id, p_alert_id, 'proposed', auth.uid(), v_syn);
  perform public.tf_add_cases(v_id, v_ids);
  perform public.tf_audit('propose_taskforce', v_id, jsonb_build_object('series_id', p_series_id, 'alert_id', p_alert_id,
                          'cases', (select count(*) from public.taskforce_cases where taskforce_id = v_id)));
  return v_id;
end $$;

-- Decide: supervisor, admin. approve (proposed → active), decline (proposed → declined), close (active → closed).
-- An optional note is stored as a 'decision' note.
create or replace function public.taskforce_decide(p_id text, p_decision text, p_note text default null)
returns text
language plpgsql security definer set search_path = public as $$
declare v_status text; v_new text;
begin
  perform public.tf_require(array['supervisor', 'admin']);
  select status into v_status from public.taskforces where taskforce_id = p_id for update;
  if v_status is null then raise exception 'unknown task force %', p_id using errcode = '22023'; end if;
  v_new := case
    when p_decision = 'approve' and v_status = 'proposed' then 'active'
    when p_decision = 'decline' and v_status = 'proposed' then 'declined'
    when p_decision = 'close'   and v_status = 'active'   then 'closed'
  end;
  if v_new is null then
    raise exception 'cannot % a % task force', p_decision, v_status using errcode = '22023';
  end if;
  update public.taskforces
     set status = v_new,
         decided_by = case when p_decision in ('approve', 'decline') then auth.uid() else decided_by end,
         decided_at = case when p_decision in ('approve', 'decline') then now() else decided_at end,
         closed_at  = case when v_new = 'closed' then now() else closed_at end
   where taskforce_id = p_id;
  if nullif(btrim(coalesce(p_note, '')), '') is not null then
    insert into public.taskforce_notes (taskforce_id, author, kind, text) values (p_id, auth.uid(), 'decision', left(btrim(p_note), 2000));
  end if;
  perform public.tf_audit(p_decision || '_taskforce', p_id, jsonb_build_object('from', v_status, 'to', v_new));
  return v_new;
end $$;

-- Members: supervisor, admin. p_role 'lead' | 'member' adds or changes; null removes.
create or replace function public.taskforce_set_member(p_id text, p_user uuid, p_role text default 'member')
returns void
language plpgsql security definer set search_path = public as $$
begin
  perform public.tf_require(array['supervisor', 'admin']);
  if not exists (select 1 from public.taskforces where taskforce_id = p_id and status in ('proposed', 'active')) then
    raise exception 'task force % is not open', p_id using errcode = '22023';
  end if;
  if p_role is null then
    delete from public.taskforce_members where taskforce_id = p_id and user_id = p_user;
  else
    if p_role not in ('lead', 'member') then raise exception 'role must be lead or member' using errcode = '22023'; end if;
    if not exists (select 1 from public.profiles where user_id = p_user) then
      raise exception 'unknown officer' using errcode = '22023';
    end if;
    insert into public.taskforce_members (taskforce_id, user_id, role, added_by) values (p_id, p_user, p_role, auth.uid())
    on conflict (taskforce_id, user_id) do update set role = excluded.role;
  end if;
  perform public.tf_audit('set_taskforce_member', p_id, jsonb_build_object('user_id', p_user, 'role', p_role));
end $$;

-- Notes: members of the task force, supervisors and admins. Append-only.
create or replace function public.taskforce_add_note(p_id text, p_text text)
returns bigint
language plpgsql security definer set search_path = public as $$
declare v_role text := public.current_role_name(); v_note bigint;
begin
  if v_role is null then raise exception 'not allowed' using errcode = '42501'; end if;
  if not (v_role in ('supervisor', 'admin')
          or exists (select 1 from public.taskforce_members where taskforce_id = p_id and user_id = auth.uid())) then
    raise exception 'only members and supervisors add notes' using errcode = '42501';
  end if;
  if not exists (select 1 from public.taskforces where taskforce_id = p_id and status in ('proposed', 'active')) then
    raise exception 'task force % is not open', p_id using errcode = '22023';
  end if;
  if p_text is null or char_length(btrim(p_text)) not between 1 and 2000 then
    raise exception 'note must be 1–2000 characters' using errcode = '22023';
  end if;
  insert into public.taskforce_notes (taskforce_id, author, text) values (p_id, auth.uid(), btrim(p_text)) returning note_id into v_note;
  perform public.tf_audit('note_taskforce', p_id, jsonb_build_object('note_id', v_note));
  return v_note;
end $$;

-- Linked cases: supervisors, admins and the task force's leads. Returns how many were added.
create or replace function public.taskforce_link_cases(p_id text, p_crime_ids text[])
returns int
language plpgsql security definer set search_path = public as $$
declare v_role text := public.current_role_name(); n int;
begin
  if v_role is null or not (v_role in ('supervisor', 'admin')
      or exists (select 1 from public.taskforce_members where taskforce_id = p_id and user_id = auth.uid() and role = 'lead')) then
    raise exception 'only leads and supervisors link cases' using errcode = '42501';
  end if;
  if not exists (select 1 from public.taskforces where taskforce_id = p_id and status in ('proposed', 'active')) then
    raise exception 'task force % is not open', p_id using errcode = '22023';
  end if;
  n := public.tf_add_cases(p_id, p_crime_ids);
  perform public.tf_audit('link_taskforce_cases', p_id, jsonb_build_object('added', n));
  return n;
end $$;

revoke all on function public.taskforce_propose(text, text, text, text, text[]), public.taskforce_decide(text, text, text),
  public.taskforce_set_member(text, uuid, text), public.taskforce_add_note(text, text), public.taskforce_link_cases(text, text[])
  from public, anon;
grant execute on function public.taskforce_propose(text, text, text, text, text[]), public.taskforce_decide(text, text, text),
  public.taskforce_set_member(text, uuid, text), public.taskforce_add_note(text, text), public.taskforce_link_cases(text, text[])
  to authenticated;

-- Rollback:
--   drop function if exists public.taskforce_propose(text, text, text, text, text[]), public.taskforce_decide(text, text, text),
--     public.taskforce_set_member(text, uuid, text), public.taskforce_add_note(text, text), public.taskforce_link_cases(text, text[]),
--     public.tf_add_cases(text, text[]), public.tf_audit(text, text, jsonb), public.tf_require(text[]);
--   drop table if exists public.taskforce_notes, public.taskforce_cases;
--   alter table public.taskforces drop column if exists purpose, drop column if exists alert_id, drop column if exists decided_by,
--     drop column if exists decided_at, drop column if exists closed_at, drop column if exists synthetic;
--   alter table public.taskforce_members drop column if exists added_by, drop column if exists added_at;
--   alter table public.taskforces drop constraint if exists taskforces_status_check;
--   alter table public.taskforces add constraint taskforces_status_check check (status in ('active', 'closed'));
--   alter table public.taskforces alter column status set default 'active';
--   grant insert, update on public.taskforces to authenticated; grant insert on public.taskforce_members to authenticated;
--   (and re-create the three 0002 write policies)
