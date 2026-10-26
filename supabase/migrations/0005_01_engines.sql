-- 0005_01 · Meterless engine stores (spec E4; engg/docs/ENGINES.md). Owner: engines lane (nexus-2).
--
-- World Model: wm_entities, wm_edges, wm_observations. H-MEM: hmem_memories, hmem_ledger.
-- Tables live in `public` because PostgREST exposes only `public` (the 0001 `wm`/`hmem`
-- schemas stay empty). The API writes them with the service role through the engines
-- write-through (ENGINES_PERSIST=supabase); the console reads them under RLS:
--   * analyst / supervisor / admin read the whole graph;
--   * a station_officer reads crime entities they can read (public.can_read_crime), the
--     edges attached to those crimes, and the entities at the other end of those edges.
--     No walking into another station's cases.
--   * hmem_* are readable by every police role (as link_alerts are).
-- Observations and the ledger are append-only: a trigger rejects UPDATE and DELETE, which
-- also stops the service role (it bypasses RLS, not triggers).

-- ---------- World Model ----------
create table if not exists public.wm_entities (
  id          text primary key,                   -- 'vehicle:plate:TN09AB1234', 'crime:fir:<crime_id>', 'ent_<sha16>'
  type        text not null check (type in ('crime', 'person', 'vehicle', 'place', 'phone', 'evidence', 'series')),
  key         text not null,                      -- canonical key (plate, crime_id, h3 cell, phone, name)
  attrs       jsonb not null default '{}'::jsonb, -- merged across observations (World Model fold: later keys win)
  aliases     text[] not null default '{}',       -- every spelling a source used
  synthetic   boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists idx_wm_entities_type_key on public.wm_entities (type, key);

create table if not exists public.wm_edges (
  id          text primary key,                   -- 'rel_<sha16>' = hash(from|type|to)
  from_id     text not null references public.wm_entities (id) on delete cascade,
  type        text not null check (type in ('involves', 'used_vehicle', 'seen_at', 'described_as', 'linked_to',
                                              'member_of')),
  to_id       text not null references public.wm_entities (id) on delete cascade,
  crime_id    text,                               -- crime_id of the crime endpoint, when one end is a crime
  synthetic   boolean not null default false,
  created_at  timestamptz not null default now()
);
create index if not exists idx_wm_edges_from on public.wm_edges (from_id);
create index if not exists idx_wm_edges_to on public.wm_edges (to_id);
create index if not exists idx_wm_edges_crime on public.wm_edges (crime_id);

create table if not exists public.wm_observations (
  id          text primary key,                   -- 'obs_<sha16>' = hash(subject|source|payload); content-addressed
  subject_id  text not null,                      -- entity id or edge id
  source      text not null,                      -- writing agent or feed (provenance)
  synthetic   boolean not null default false,
  observed_at timestamptz not null default now()
);
create index if not exists idx_wm_observations_subject on public.wm_observations (subject_id);

-- ---------- H-MEM ----------
create table if not exists public.hmem_memories (
  id          text primary key,                   -- '<store>:mem-N' (memory ids are per store)
  store       text not null,
  memory_id   text not null,
  content     text not null,
  tags        text[] not null default '{}',
  confidence  numeric(5, 4) not null check (confidence between 0 and 1),
  layer       text not null check (layer in ('short_term', 'working', 'long_term')),
  decision    text,
  polarity    integer check (polarity in (-1, 0, 1)),
  reason_code text,
  alert_id    text,
  note        text,
  synthetic   boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (store, memory_id)
);
create index if not exists idx_hmem_memories_alert on public.hmem_memories (alert_id);

create table if not exists public.hmem_ledger (
  id          bigserial primary key,
  store       text not null,
  memory_id   text not null,
  action      text not null,
  actor       text not null,
  at          timestamptz not null,
  details     jsonb not null default '{}'::jsonb,
  entry_hash  text not null unique,               -- sha256 of the ledger line; makes the sync idempotent
  synthetic   boolean not null default false
);
create index if not exists idx_hmem_ledger_memory on public.hmem_ledger (store, memory_id, at);

-- ---------- triggers ----------
drop trigger if exists trg_wm_entities_updated on public.wm_entities;
create trigger trg_wm_entities_updated before update on public.wm_entities
  for each row execute function public.touch_updated_at();
drop trigger if exists trg_hmem_memories_updated on public.hmem_memories;
create trigger trg_hmem_memories_updated before update on public.hmem_memories
  for each row execute function public.touch_updated_at();

create or replace function public.engines_append_only() returns trigger
language plpgsql as $$
begin
  raise exception '% is append-only', tg_table_name;
end $$;
revoke all on function public.engines_append_only() from public, anon;

drop trigger if exists trg_wm_observations_append_only on public.wm_observations;
create trigger trg_wm_observations_append_only before update or delete on public.wm_observations
  for each row execute function public.engines_append_only();
drop trigger if exists trg_hmem_ledger_append_only on public.hmem_ledger;
create trigger trg_hmem_ledger_append_only before update or delete on public.hmem_ledger
  for each row execute function public.engines_append_only();

-- ---------- RLS helpers ----------
-- True when the caller may read this World Model entity.
create or replace function public.wm_can_read_entity(p_id text, p_type text, p_key text) returns boolean
language sql stable security definer set search_path = public as $$
  select case
    when public.current_role_name() in ('analyst', 'supervisor', 'admin') then true
    when public.current_role_name() = 'station_officer' then
      (p_type = 'crime' and public.can_read_crime(p_key))
      or exists (
        select 1 from public.wm_edges e
        where (e.from_id = p_id or e.to_id = p_id)
          and e.crime_id is not null and public.can_read_crime(e.crime_id))
    else false
  end
$$;
revoke all on function public.wm_can_read_entity(text, text, text) from public, anon;
grant execute on function public.wm_can_read_entity(text, text, text) to authenticated;

-- ---------- RLS ----------
alter table public.wm_entities     enable row level security;
alter table public.wm_edges        enable row level security;
alter table public.wm_observations enable row level security;
alter table public.hmem_memories   enable row level security;
alter table public.hmem_ledger     enable row level security;

revoke all on public.wm_entities, public.wm_edges, public.wm_observations, public.hmem_memories,
  public.hmem_ledger from anon, authenticated;
revoke all on sequence public.hmem_ledger_id_seq from anon, authenticated;
grant select on public.wm_entities, public.wm_edges, public.wm_observations, public.hmem_memories,
  public.hmem_ledger to authenticated;

create policy "read wm_entities by role" on public.wm_entities for select to authenticated
  using (public.wm_can_read_entity(id, type, key));
create policy "read wm_edges by role" on public.wm_edges for select to authenticated
  using ((select public.current_role_name()) in ('analyst', 'supervisor', 'admin')
         or (crime_id is not null and public.can_read_crime(crime_id)));
create policy "read wm_observations by subject" on public.wm_observations for select to authenticated
  using (exists (select 1 from public.wm_entities e where e.id = subject_id)
         or exists (select 1 from public.wm_edges r where r.id = subject_id));
create policy "police read hmem_memories" on public.hmem_memories for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read hmem_ledger" on public.hmem_ledger for select to authenticated
  using ((select public.current_role_name()) is not null);

-- Rollback:
--   drop table if exists public.hmem_ledger, public.hmem_memories, public.wm_observations,
--     public.wm_edges, public.wm_entities cascade;
--   drop function if exists public.wm_can_read_entity(text, text, text), public.engines_append_only();
