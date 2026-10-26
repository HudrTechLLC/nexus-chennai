-- 0003 · Map layer projections for the Pulse Map (G3). Owner: nexus-1. DECISIONS D-019.
--
-- UI PROJECTION CACHE, NEVER AN AGENT SOURCE.
-- The originals live in the object store (CCTV registry, ANPR reads, 112 calls, releases;
-- spec D1) and every agent reads them only through Zetaris (rule R1). These tables are a
-- display-only copy that the seed loads from the same generated files, because the web app
-- on Vercel cannot reach Zetaris. No agent, named query or scoring code may read them.
-- Police roles read; anon has no access (D-003). Every row carries synthetic.

create table if not exists public.map_cctv_cameras (
  camera_id      text primary key,
  owner_type     text not null,
  lat            double precision not null,
  lon            double precision not null,
  heading_deg    real,
  fov_deg        real,
  range_m        real,
  h3_r9          text,
  contact_station text references public.stations (station_id),
  synthetic      boolean not null default true
);

create table if not exists public.map_anpr_cameras (
  camera_id text primary key,
  lat       double precision not null,
  lon       double precision not null,
  h3_r9     text,
  synthetic boolean not null default true
);

-- Only reads linked to a crime or an alert (the "show trail" path), not the full feed.
create table if not exists public.map_anpr_reads (
  read_id          text primary key,
  camera_id        text not null references public.map_anpr_cameras (camera_id) on delete cascade,
  read_at          timestamptz not null,
  plate_text       text not null,
  plate_confidence real,
  direction        text,
  lat              double precision not null,
  lon              double precision not null,
  crime_id         text references public.crimes (crime_id) on delete cascade,
  synthetic        boolean not null default true
);
create index if not exists idx_map_anpr_reads_plate on public.map_anpr_reads (plate_text, read_at);
create index if not exists idx_map_anpr_reads_crime on public.map_anpr_reads (crime_id);

-- 112 calls aggregated: no caller, no exact point.
create table if not exists public.map_call_cells (
  h3_r9       text not null,
  category    text not null,
  hour_bucket timestamptz not null,
  n           integer not null check (n > 0),
  synthetic   boolean not null default true,
  primary key (h3_r9, category, hour_bucket)
);
create index if not exists idx_map_call_cells_hour on public.map_call_cells (hour_bucket);

-- Released offenders aggregated per ward: never a person.
create table if not exists public.map_release_density (
  ward_no           integer primary key references public.wards (ward_no),
  n                 integer not null check (n >= 0),
  last_release_week text,
  synthetic         boolean not null default true
);

alter table public.map_cctv_cameras    enable row level security;
alter table public.map_anpr_cameras    enable row level security;
alter table public.map_anpr_reads      enable row level security;
alter table public.map_call_cells      enable row level security;
alter table public.map_release_density enable row level security;

revoke all on public.map_cctv_cameras, public.map_anpr_cameras, public.map_anpr_reads,
  public.map_call_cells, public.map_release_density from anon, authenticated;
grant select on public.map_cctv_cameras, public.map_anpr_cameras, public.map_anpr_reads,
  public.map_call_cells, public.map_release_density to authenticated;

create policy "police read map_cctv_cameras" on public.map_cctv_cameras for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read map_anpr_cameras" on public.map_anpr_cameras for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read map_anpr_reads" on public.map_anpr_reads for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read map_call_cells" on public.map_call_cells for select to authenticated
  using ((select public.current_role_name()) is not null);
create policy "police read map_release_density" on public.map_release_density for select to authenticated
  using ((select public.current_role_name()) is not null);

-- Deliberately NOT granted to zetaris_reader: Zetaris federates the originals, not this cache.

-- Rollback:
--   drop table if exists public.map_release_density, public.map_call_cells, public.map_anpr_reads,
--     public.map_anpr_cameras, public.map_cctv_cameras;
