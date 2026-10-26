-- 0001 · Foundation tables for P0 (spec Part I, Part K P0).
-- stations, wards, profiles, runs. RLS is on for every table; the anon role gets no
-- table access (spec Part I; public data arrives later via narrow RPCs, DECISIONS D-003).
-- All seeded rows are synthetic or public reference data.

create extension if not exists postgis;
create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create schema if not exists wm;    -- World Model engine
create schema if not exists hmem;  -- H-MEM engine

-- ---------- reference ----------
create table if not exists public.stations (
  station_id text primary key,
  name       text not null,
  type       text not null check (type in ('law_and_order', 'crime', 'traffic', 'all_women')),
  zone       text,
  district   text,
  region     text,
  geom       geometry(MultiPolygon, 4326),
  centroid   geometry(Point, 4326),
  synthetic  boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.wards (
  ward_no    integer primary key,
  name       text not null,
  zone       text,
  geom       geometry(MultiPolygon, 4326),
  created_at timestamptz not null default now()
);

create index if not exists idx_stations_geom on public.stations using gist (geom);
create index if not exists idx_wards_geom on public.wards using gist (geom);

-- ---------- people ----------
create table if not exists public.profiles (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  name       text not null,
  role       text not null check (role in ('station_officer', 'analyst', 'supervisor', 'admin')),
  station_id text references public.stations (station_id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------- runs ----------
create table if not exists public.runs (
  run_id    text primary key,
  kind      text not null check (kind in ('case', 'batch', 'tip', 'search', 'sweep')),
  started   timestamptz not null default now(),
  finished  timestamptz,
  status    text not null default 'running' check (status in ('running', 'success', 'failed', 'not_implemented')),
  log_path  text
);
create index if not exists idx_runs_started on public.runs (started desc);

-- ---------- helpers ----------
create or replace function public.current_role_name() returns text
language sql stable security definer set search_path = public as $$
  select role from public.profiles where user_id = auth.uid()
$$;
revoke all on function public.current_role_name() from public, anon;
grant execute on function public.current_role_name() to authenticated;

create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists trg_profiles_updated on public.profiles;
create trigger trg_profiles_updated before update on public.profiles
  for each row execute function public.touch_updated_at();

-- ---------- RLS ----------
alter table public.stations enable row level security;
alter table public.wards    enable row level security;
alter table public.profiles enable row level security;
alter table public.runs     enable row level security;

revoke all on public.stations, public.wards, public.profiles, public.runs from anon;
grant select on public.stations, public.wards, public.profiles, public.runs to authenticated;
grant update on public.profiles to authenticated;

-- Any police role can read reference data and run history.
create policy "police read stations" on public.stations for select to authenticated
  using (public.current_role_name() is not null);
create policy "police read wards" on public.wards for select to authenticated
  using (public.current_role_name() is not null);
create policy "police read runs" on public.runs for select to authenticated
  using (public.current_role_name() is not null);

-- Profiles: everyone reads their own; supervisors and admins read all; only admins change roles.
create policy "read own profile" on public.profiles for select to authenticated
  using (user_id = auth.uid());
create policy "supervisors read profiles" on public.profiles for select to authenticated
  using (public.current_role_name() in ('supervisor', 'admin'));
create policy "admins update profiles" on public.profiles for update to authenticated
  using (public.current_role_name() = 'admin');

-- Read-only role for Zetaris federation (spec O7 #6). Password is set out of band, never here.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'zetaris_reader') then
    create role zetaris_reader nologin;
  end if;
end $$;
grant usage on schema public to zetaris_reader;
grant select on public.stations, public.wards, public.runs to zetaris_reader;

-- Rollback:
--   drop table if exists public.runs, public.profiles, public.wards, public.stations cascade;
--   drop function if exists public.current_role_name(), public.touch_updated_at();
--   drop schema if exists wm cascade; drop schema if exists hmem cascade;
--   drop role if exists zetaris_reader;
