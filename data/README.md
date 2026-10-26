# Data sources

Every source Nexus reads, where it comes from, how many rows it holds, and its licence. **All crime,
person, vehicle, camera, call, tip, statement, evidence, news and social data is synthetic**: the
seeded generator made it inside the hackathon window, and every row carries `synthetic: true`
(rule R9). Real public data appears in only three places: map geometry and points of interest
(OpenStreetMap, DataMeet), the station list, and weather (Open-Meteo). Each is listed with its
licence below.

Counts are from the QA database and the live Zetaris instance on 26 Oct 2026 (generator seed 42,
scale 1.0, crimes 24 Oct 2024 to 25 Oct 2026). Agents reach crime data only through Zetaris named
queries (rule R1). Each source's path is shown below.

## 1. Synthetic generator: `python -m data.generator`

The generator writes one city to `data/generated/` (not committed; rebuild with the command). Its
`MANIFEST.json` records the seed, the window and every count. `_truth/` holds the planted answers
(series, decoys, duplicates, DQ defects, offender returns, vehicle chains, tips). Evaluation reads it;
agents never do.

| Output | Rows | Lands in |
|---|---|---|
| `supabase/crimes.jsonl` | 14,038 | Supabase `crimes` |
| `supabase/statements.jsonl` | 21,127 | Supabase `statements` |
| `supabase/crime_vehicles.jsonl` | 5,215 | Supabase `crime_vehicles` |
| `supabase/persons.jsonl`, `person_links.jsonl` | 9,000 / 5,540 | Supabase `persons`, `person_links` |
| `supabase/tips.jsonl` | 40 (24 corroborating, 6 unrelated, 4 prompt-injection, 2 emergency, 4 spam) | Supabase `tips` |
| `supabase/stations.jsonl`, `wards.jsonl`, `section_map.jsonl` | 70 / 201 / 82 | Supabase (built from the city pack, §4) |
| `supabase/map_*.jsonl` | 2,500 CCTV, 140 ANPR, 102 reads, 119,971 call cells, 200 release cells | Supabase `map_*` (map layers for the console only) |
| `supabase/evidence_media.jsonl` + `evidence/<crime_id>/<uuid>.jpg` | 49 | Supabase `evidence_media` + private bucket `evidence` (§2) |
| `ref/cctv_cameras.csv`, `anpr_cameras.csv`, `vehicles.csv` | 2,500 / 140 / 25,000 | Zetaris file store (§3) |
| `ref/releases.csv`, `history_sheets.csv` | 1,800 / 1,200 | Zetaris file store |
| `ref/place_aliases.csv`, `calendar.csv` | 62 / 45 | Zetaris file store (copied from the city pack) |
| `anpr/reads_YYYY_MM.parquet` | 600,000 | Zetaris file store |
| `calls/calls_YYYY_MM.parquet` | 120,000 | Zetaris file store |
| `legacy/cctns_*.csv` | 3,000 (8 files, legacy CCTNS shape, 20 unmapped sections planted) | Zetaris file store |
| `legacy/archive.parquet` | 2,500 | Zetaris file store |

`python -m data.seed --in data/generated` loads the Supabase part:
- It runs in one transaction.
- It upserts generator rows, which are keyed by `source_row_id = uuid5(…, crime_id)`.
- It never touches FIRs filed in the console.
- It refuses to retire crimes without `--retire`.
- Tips, crime_vehicles and evidence_media are insert-only.

`python -m zetaris.stage_files` copies the file-store part into Zetaris.

CCTV stills (`data/generator/stills.py`, WS1-09) are rendered images, not photographs. They show a
street, a silhouette of the series vehicle, faceless figures, a camera id with an IST timestamp,
and a "SYNTHETIC - NEXUS DEMO" stamp. The images are not committed; the generator recreates them
byte for byte.

## 2. Supabase (Postgres + Storage)

Zetaris reads these tables through the `sb` source (zetaris/00_sources.sql). The console reads them
directly under row-level security.

| Table | Rows | Origin |
|---|---|---|
| `crimes` | 14,040 | generator (14,038) + FIRs filed in the console (2) |
| `statements` | 21,131 | generator + console |
| `crime_vehicles` | 5,216 | generator + console |
| `persons`, `person_links` | 9,000 / 5,540 | generator |
| `tips` | 40 | generator; Tip Guard writes the verdicts |
| `evidence_media` | 53 | generator stills (49) + console uploads |
| `crime_features` | 421 | Extractor agent (Nightshift), written by the worker |
| `stations`, `wards`, `section_map` | 70 / 201 / 82 | city pack (§4) |
| `map_cctv_cameras`, `map_anpr_cameras`, `map_anpr_reads`, `map_call_cells`, `map_release_density` | 2,500 / 140 / 102 / 119,971 / 200 | generator; map layers only, not read by agents |
| `link_alerts`, `link_factors`, `series`, `series_members` | 26 / 125 / 1 / 10 | agent runs |
| `public_incidents`, `appeal_requests` | 4 / 5 | console (supervisor-approved appeals) |
| `wm_entities`, `wm_edges`, `wm_observations`, `hmem_*` | 791 / 517 / 1,361 / 1 | agent memory (world model, H-MEM) |
| `runs`, `trace_events`, `system_status`, `audit_log`, `notifications`, `outbox` | runtime | app and worker |

Storage buckets:
- `evidence` (private): 55 objects. 49 are generator stills, keyed `<crime_id>/<uuid>.jpg`; the rest are console uploads.
- `tip-media` (private): empty.
- `appeal-public` (public): blurred appeal stills only.
- `nexus-chennai-data` (private): 1 reference file.

## 3. Zetaris

The registration SQL lives in `zetaris/`; see `zetaris/README.md`.

**File-store tables** (`zetaris/01_files.sql`). These are files in Zetaris's internal file store. The
names `s3csv` and `s3pq` look like S3, but they are not S3 (D-022a).

| Table | Rows | Format |
|---|---|---|
| `s3csv.cctv_cameras` | 2,500 | CSV |
| `s3csv.anpr_cameras` | 140 | CSV |
| `s3csv.vehicles` | 25,000 | CSV |
| `s3csv.releases` | 1,800 | CSV |
| `s3csv.history_sheets` | 1,200 | CSV |
| `s3csv.place_aliases` | 62 | CSV |
| `s3csv.calendar` | 45 | CSV |
| `s3csv.cctns` | 3,000 | CSV |
| `s3pq.anpr_reads` | 600,000 | Parquet |
| `s3pq.calls` | 120,000 | Parquet |
| `s3pq.archive` | 2,500 | Parquet |
| `s3pq.osm_pois` | 8,616 | Parquet (OpenStreetMap, §4) |

**REST tables** (`zetaris/40_feeds.sql`, Lightning database `nexus_feeds`):

| Table | Rows | Origin |
|---|---|---|
| `rest_news` → `nexus.news_items` | 47 | synthetic. Nexus API `GET /mock-feeds/news`, generated by `services/api/app/feeds_gen.py` |
| `rest_social` → `nexus.social_posts` | 61 | synthetic. Nexus API `GET /mock-feeds/social` |
| `rest_weather` → `nexus.weather_hourly` | 744 | **real**: Open-Meteo forecast API, hourly, city centre, no key |

**Semantic views** (schema-store container `nexus`), 13 in all:
- `v_crime_unified` (19,540 rows): Supabase crimes ∪ CCTNS ∪ archive.
- 8 data-quality views (`20_dq.sql`).
- `news_items`, `social_posts`, `v_news_mentions`, `weather_hourly`.

Agents call only the 14 named queries in `services/api/app/adapters/zetaris*.py`. Each one has a
DuckDB twin that runs over `data/sample/` in sample mode.

## 4. Real public reference data (city pack `cities/<city>/`)

`python -m data.reference.fetch` downloads the raw inputs to `data/reference/raw/` (not committed).
`python -m data.reference.build` writes the files below, and `data/reference/MANIFEST.json` records
their sha256.

| File | Rows | Source | Licence |
|---|---|---|---|
| `wards.geojson` | 201 | DataMeet Municipal_Spatial_Data, Chennai wards (Transparent Chennai) | **CC BY-SA 2.5 IN**. © DataMeet / Transparent Chennai |
| `data/reference/osm_pois.parquet` | 8,616 | OpenStreetMap via Overpass (amenities, shops, transport, hotels in the city bounds) | **ODbL 1.0**. © OpenStreetMap contributors |
| `stations.geojson` | 70 | `stations_seed.csv` (public station names and codes, approximate points), 54 snapped to OSM `amenity=police`; jurisdictions are a **synthetic** Voronoi split | station points: ODbL (OSM) where snapped; polygons: synthetic |
| `police.yaml`, `stations_seed.csv` | 70 | compiled by hand from the public Greater Chennai Police station list | facts only; marked approximate |
| `law_sections.csv` | 82 | IPC → BNS section map, compiled by hand | public law text; `verified=false` |
| `calendar.csv` | 45 | public holidays and festivals, compiled by hand | facts only; `verified=false` |
| `place_aliases.csv` | 62 | local spellings of places, written for the demo | project-authored |
| weather (`rest_weather`) | 744 | Open-Meteo, queried live by Zetaris | **CC BY 4.0**. Weather data by Open-Meteo.com |

**Attribution** (the UI and submission must carry it wherever the map or weather is shown): "Map data
© OpenStreetMap contributors (ODbL). Ward boundaries © DataMeet / Transparent Chennai (CC BY-SA
2.5 IN). Weather data by Open-Meteo.com (CC BY 4.0)."

## 5. Live mode on your own Zetaris (no Supabase)

All crime data can live in your own Zetaris instead of our hosted Supabase. The named queries return
the same answers either way; `tests/zetaris/test_files_parity_live.py` checks this on the judge cases.

**You need:**
- A local Zetaris in Docker. The Participant Setup Guide has everyone run Zetaris locally in Docker,
  and files are copied into its container.
- Its API key in a file.
- Python with `services/api/requirements-dev.txt` installed.

**Steps:**

    export ZETARIS_API_KEY_FILE=/path/to/your/zetaris.key   # the path only, never the key itself
    # optional, if yours differ: ZETARIS_REST_URL (http://localhost:8888/api/v1.0), ZETARIS_ORG_ID (1),
    #                            ZETARIS_DRIVER_CONTAINER (zetaris-driver-1)
    python -m data.setup_live          # a few minutes; add --dry-run to see every step and SQL statement first

Then run the API with `ZETARIS_DATA=files`, plus your Nightshift settings.

`setup_live` does the following:
1. Generates the city with `python -m data.generator`. It is deterministic (seed 42) and identical to the
   rows we seeded.
2. Renders the synthetic CCTV stills.
3. Exports the crime data as Parquet (`data/fs_export.py`), using the same names, columns and Spark types
   as the Supabase objects. It adds the committed model-output fixtures in `data/fixtures/` (MO features
   and Tip Guard verdicts), so nothing needs re-extracting.
4. Copies everything into Zetaris's file store (`zetaris/stage_files.py --fs`).
5. Registers it with `zetaris/register.py --data files`. This creates database `nexus_fs` (11 tables) and
   the views in container `nexusfs`, next to the 12 file tables of §3.
6. Smoke-tests the hero case through the named queries.

Nothing it generates is committed (`data/generated/` is gitignored). Re-running it is safe.

`ZETARIS_DATA` switches the source (`services/api/app/adapters/zetaris_sources.py`):

| `ZETARIS_DATA` | Crime data | Views |
|---|---|---|
| `supabase` (default) | `sb` datasource on our Supabase | container `nexus` |
| `files` | Parquet in `nexus_fs` | container `nexusfs` |

Two kinds of data exist only in a live system, so a fresh file store starts without them. Link alerts
are written by agent runs, and FIRs filed in the console are not part of the generator.

## 6. Sample bundle (`data/sample/`)

`data/sample/` is a committed subset of about 1.4 MB, used when `SAMPLE_MODE=true` and Zetaris is
unreachable. It contains:
- 1,275 crimes: the three judge cases and their series, their decoys and candidates, plus DQ rows;
- 6,501 ANPR reads, 4,270 calls and 40 tips;
- 47 news items and 61 social posts;
- the full legacy CCTNS and archive.

`data/sample/README.md` explains what is in it and how to rebuild it.
