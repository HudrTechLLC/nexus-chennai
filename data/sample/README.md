# Sample bundle (synthetic)

A small bundle, committed to the repo, used when `SAMPLE_MODE=true` (spec P1). The DuckDB twins of the
named queries read it with `file_search_path = data/sample`; `views.sql` is loaded on the first sample
query (`adapters/zetaris.py`). Every row carries `synthetic: true`.

| Path | What | Owner |
|---|---|---|
| `sb/*.parquet` | crimes, crime_vehicles, statements, stations, tips, evidence_media, forensics, crime_features, crime_feature_reviews, with the Supabase column types | nexus-1 |
| `ref/` | place_aliases.csv, calendar.csv, osm_pois.parquet, releases.csv, history_sheets.csv | nexus-1 |
| `anpr/reads.parquet` | ANPR reads near bundle scenes, every read of a planted plate, and 3,000 background reads | nexus-1 |
| `calls/calls.parquet` | 112 calls near bundle scenes, plus 2,000 background calls | nexus-1 |
| `_truth/` | series, decoys, duplicates, dq, pairs, tips: restricted to this subset | nexus-1 |
| `legacy/` | the legacy CCTNS CSVs and archive parquet, whole, for `v_crime_unified`'s union | nexus-1 |
| `sb/section_map.parquet` | IPC/BNS map, for `sections_raw` | nexus-1 |
| `views.sql` | `v_crime_unified`: Supabase + legacy, same union and columns as `zetaris/10_views.sql` | nexus-1 |
| `model_fixtures/` | recorded **live** Nightshift calls | nexus-3 |
| `crime_features.jsonl`, `news/`, `social/` | other lanes' fixtures | their lanes |

**Which crimes.** The judge cases (CHN-AD-2026-001182, CHN-KU-2025-000078, CHN-GU-2025-000945), their
series (Red Pulsar, Grille Cutters, Night Cab) and decoys, and every crime `q_candidates` would return for
any of them (same category, at most 45 days, 6 km). The judge path therefore sees the same candidates as
live. Duplicate pairs and DQ defects are added so every DQ rule has work. There are also 40 public tips,
unscreened.

**Rebuild** (never edit by hand):

    NEXUS_DB_PASSWORD="$(tr -d '\r\n' < <password file>)" python -m data.generator.sample --from data/generated

The same generated data gives the same bytes, except `sb/crime_features.parquet`. That file is the live
crime_features rows for the subset (real model and receipt ids), so it follows the extractor.
