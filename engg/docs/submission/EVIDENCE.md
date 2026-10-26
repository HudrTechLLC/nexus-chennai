---
tags: [nexus, deliverables]
---

# Submission claims ledger

This note lists every claim the submission drafts make, with the file, test or CI job that proves it. The four drafts ([README_DRAFT](README_DRAFT.md), [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md), [DECK](DECK.md), [VIDEO_SCRIPT](VIDEO_SCRIPT.md)) take their claims only from here. When a `[PENDING: id]` task lands, flip its row here first, then the drafts. `grep -rn "PENDING:" engg/docs/submission/` lists everything still open.

**Verified against `origin/main` @ `c686f0c`** (26 Oct 2026). CI on that commit is green on all five jobs: `api` (ruff + pytest), `engines` (official conformance + E4 tests on the TypeScript references), `judge-path` (docker build + start with `SAMPLE_MODE=true`, no credentials), `web` (typecheck, lint, vitest, `next build`) and `secrets`.
Related: [RULES_CHECK](../hackathon/RULES_CHECK.md) · [DELIVERABLES](../DELIVERABLES.md) · [SPONSOR_TECH](../SPONSOR_TECH.md) · [ENGINES](../ENGINES.md) · [AGENTS](../AGENTS.md) · [DECISIONS](../DECISIONS.md)

## Judge path

| Claim | Evidence | Status |
|---|---|---|
| Root `Dockerfile` + `requirements.txt`; `docker build -t oah-submission .` works from a clean checkout | `Dockerfile`, `requirements.txt` (→ `services/api/requirements.txt`); CI `judge-path` | ✅ |
| Starts with `SAMPLE_MODE=true` and no credentials, and `/health` answers | `.github/workflows/docker.yml` step "start with SAMPLE_MODE=true and no credentials" | ✅ |
| `python run.py` serves on :8000; `python run.py --once <file>` posts one input to `/run` | `run.py` (sets its own import path; no `PYTHONPATH` needed) | ✅ |
| `docker-compose.yml`: API on :8000, reaches Zetaris and Nightshift on the host through `host.docker.internal`; optional `worker` profile | `docker-compose.yml` | ✅ (live compose run: `[PENDING: WS5-11]`) |
| `POST /run` returns `run_id, status, output{alerts, series, hotspots, summary}, agents, engines, trace_id, log_file, execution_time_seconds` | `services/api/app/main.py`; `tests/graph/test_graph_pipeline.py`; bad input → 422 in `tests/test_tracing_and_api.py` | ✅ |
| 3 inputs in `input_examples/` + real outputs in `output_examples/` | not on main | `[PENDING: WS2-16]` |
| Sample bundle in `data/sample/` (≈600 crimes, 3 series, 40 tips, recorded model fixtures) | only `data/sample/README.md` is on main | `[PENDING: WS1-11]` |
| Sample mode with Zetaris + Nightshift stopped and no `.env` runs example 1 end to end | depends on the two rows above | `[PENDING: WS5-08]` |
| `.env.example` with placeholders only; both `METERLESS_RUNTIME_TOKEN` and `METERLESS_RUNTIME_TOKEN_FILE` are accepted | `.env.example`; `services/api/app/config.py` | ✅ |
| No secrets tracked | CI `secrets` (file names + value patterns) | ✅ |

## Agents, graph and traces

| Claim | Evidence | Status |
|---|---|---|
| LangGraph graph with a router and three paths (tip, search, case); case path `load_case → extract → plan → link → skeptic → write`; Skeptic can loop back to `plan` | `services/api/app/graph/pipeline.py` (`add_node` / `add_conditional_edges`); `tests/graph/test_graph_pipeline.py` | ✅ |
| Caps: Planner ≤ 3 rounds, Skeptic send-back ≤ 2, run deadline 300 s with a 45 s reserve | [AGENTS](../AGENTS.md) Graph; `pipeline.py` | ✅ |
| 10 agent modules: Tip Guard, Extractor, Planner, Linker, Skeptic, Alert writer, Series analyst, Hotspot detector, Sanitiser, Briefer | `services/api/app/agents/*.py`; `tests/agents/` | ✅ |
| Skeptic re-queries Zetaris itself, strikes unsupported factors, rescored in code; verdict `approve` / `send_back` / `drop`; the model may only downgrade | `agents/skeptic.py` (`factors_to_strike`, `strike`, `VERDICT_TO_STATUS`); `tests/agents/test_agents_linking.py` | ✅ |
| Nine factors scored in code; strikes keep weight at 0; H-MEM capped ±0.08; coverage guard | `app/scoring/`; `tests/scoring/`; D-016 | ✅ |
| Extractor: when Nightshift refuses an image, it traces `vision_unavailable` and falls back to the caption | `agents/extractor.py` lines ~138–141; D-021 | ✅ |
| Every model call is traced with lane, pinned model, routed model and receipt id | `adapters/nightshift.py` (`chat`, `_trace`, `_receipt_id`); `tests/adapters/test_nightshift.py` | ✅ |
| Receipt id: a `meterless-receipt*` header if present, else a `receipt*` field, else the response `id` | `adapters/nightshift.py::_receipt_id` | ✅ (say exactly this) |
| JSONL trace per run at `logs/trace-<run_id>.jsonl`, also on stdout; copied to Supabase `trace_events` for the console | `app/tracing.py`; D-025; `tests/graph/test_trace_store.py` | ✅ |
| Worker: `alert_decisions` → H-MEM; new tips → Tip Guard; un-featured crimes → graph | `app/worker.py`; `tests/graph/test_worker_store.py` | ✅ |
| Eval vs rules-only baseline, `output_examples/eval_report.json`, precision/recall numbers | `app/eval/` + `tests/eval/test_eval_core.py` exist; no report on main | `[PENDING: WS2-14]` |

## Zetaris

| Claim | Evidence | Status |
|---|---|---|
| Every agent read goes through `ZetarisClient.named(...)`; registry only, query id traced | `adapters/zetaris.py`; `tests/adapters/test_zetaris.py` | ✅ |
| Source `sb`: Supabase Postgres over the session pooler as read-only `zetaris_reader`; 17 tables + datasource views `stations`, `wards`, `crime_features_v`, `tips_v` | `zetaris/00_sources.sql`; `zetaris/README.md` "Live state" | ✅ |
| Tips reach Zetaris only through `tips_v` (safe columns; no passphrase hash, no raw text) | `zetaris/README.md`; migration `0003_zetaris_reader_tips.sql` | ✅ |
| REST feeds: `rest_news`, `rest_social` (Lightning REST tables) + views `news_items`, `social_posts`, `v_news_mentions` | `zetaris/40_feeds.sql` | ✅ |
| Data-quality views (8): `dq_duplicate_firs`, `dq_bad_geo`, `dq_time_inconsistent`, `dq_unmapped_sections`, `dq_flags`, `dq_orphan_evidence`, `dq_tip_without_incident`, `dq_stale_cameras` | `zetaris/20_dq.sql`; `tests/engines/test_dq.py` | ✅ |
| Named queries registered with live SQL + DuckDB twin: `q_case`, `q_candidates`, `q_features`, `q_dq_flags`, `q_news`, `q_hex_counts` (plus `q_ping`) | `NAMED_QUERIES` in `adapters/zetaris.py`, `zetaris_queries_n1.py`, `zetaris_queries_n2.py`; `tests/zetaris/` | ✅ (6 of 13) |
| `q_vehicle_trail`, `q_offender_return`, `q_calls_near`, `q_tip_corroboration`, `q_context`, `q_search`, `q_station_matrix` | named by the Planner but not registered on main | `[PENDING: WS1-15]` |
| Semantic views `v_crime_unified`, `v_vehicle_trail`, `v_offender_return`, `v_tip_corroboration` (`10_views.sql`) | file not on main | `[PENDING: WS1-13]` |
| CSV / Parquet file sources (legacy exports, ANPR, 112 calls) in Zetaris's internal file store | not in `00_sources.sql` on main; D-022a explains the store | `[PENDING: WS1-12]` |
| Live `SELECT count(*) FROM sb.crimes` = 14000 | `zetaris/README.md` (recorded by nexus-1) | ✅ (recorded, not CI) |

## Meterless engines and Nightshift

| Claim | Evidence | Status |
|---|---|---|
| World Model, H-MEM, Markovian TS references + conformance suites vendored unmodified @ `1742dec5`, Apache-2.0 | `engines-ts/NOTICE`, `engines-ts/LICENSE` | ✅ |
| Official conformance: World Model 8/8, H-MEM 13/13, Markovian 8/8 | `logs/conformance_*.txt` (exit 0); re-run in CI `engines` every PR | ✅ |
| E4 feature tests pass on both the sample backend and the TS references through the sidecar | CI `api` (`pytest -q`) and CI `engines` (`ENGINES_BACKEND=sidecar pytest tests/engines -q`); `tests/engines/test_backend_parity.py` | ✅ |
| Scout Intent (Nexus implementation of the Meterless Scout spec): 120 E4 fixtures, route accuracy 1.000, injections quarantined 18/18, emergencies 8/8, 0 false quarantines; held-out 40: route 0.950, injections 7/7 | `logs/feature_scout_intent.txt` (run 2026-10-26 06:27 UTC); gated in `tests/engines/test_scout_intent.py` | ✅ |
| Engine state persisted to Supabase `wm_*` / `hmem_*` (append-only ledger) when `ENGINES_PERSIST=supabase` | migration `0005_01_engines.sql`; D-020; `tests/engines/test_migration_0005.py`, `test_persist.py` | ✅ |
| Nightshift is the only model path; pinned lanes; `meterless/auto` refused | `adapters/nightshift.py::model_for`, `config.FORBIDDEN_MODELS`; `tests/adapters/test_nightshift.py` | ✅ |
| Lanes: `fast` = `nvidia/nemotron-3.5-lightning-30b-a3b`, `reason` = `nvidia/nemotron-3-ultra-550b-a55b` (Super 120B is 404 for our key) | D-017; `.env.example` | ✅ |
| `vision` = `nvidia/nemotron-3.5-super-vl-120b-a12b`: text calls work, image calls refused (`no_vision_model`) | D-021 | ⚠️ limitation, never claim visual extraction |
| Embed lane `nvidia/nemotron-3.5-embed-1b` | configured in `.env.example` / `config.py`; no call site on main. nexus-2 building similar-MO search per spec E2 (Nemotron embed lane if Nightshift `/v1/embeddings` works, which returned 404 for every model at the time; TF-IDF otherwise) | `[PENDING: WS2-embed]` |
| NVIDIA key lives only in Nightshift; the app holds the Nightshift URL + runtime token | `adapters/nightshift.py` docstring; `.env.example` | ✅ |

## Web (Vercel)

| Claim | Evidence | Status |
|---|---|---|
| Public portal: home, appeals list + detail, fuzzed hex map, CCTV page, anonymous tip (EXIF stripped, tip code, status, replies), privacy | `apps/web/app/(public)/**`; WS4-01…06 done | ✅ |
| Console: sign-in + roles, alerts inbox + detail, map, appeals, tip triage, system status + trace viewer | `apps/web/app/console/(app)/**` pages exist; CI `web` green | ✅ pages exist; completeness of WS3-04/05/07/08/09 and WS4-07/08: `[PENDING]` per task |
| Case file + search; FIR capture form | not on main | `[PENDING: WS3-06]`, `[PENDING: WS3-10]` |
| Series pages, station link matrix, memory page, graph explorer | not on main | `[PENDING: WS3-11]` |
| Tip passphrases hashed with pgcrypto bcrypt inside Postgres (deviation from spec Argon2id) | D-023; migration `0004_03_public_rpcs.sql` (`gen_salt('bf', …)`) | ✅ |

## Libraries (for the README dependency list)

Python (`services/api/requirements.txt`): FastAPI 0.115.6, Uvicorn 0.32.1, Pydantic 2.10.4, pydantic-settings 2.7.0, httpx 0.28.1, tenacity 9.0.0, DuckDB 1.1.3, PyYAML 6.0.2, h3 4.5.0, LangGraph 1.2.17.
Web (`apps/web/package.json`): Next.js 14.2.35, React 18, @supabase/supabase-js 2, @supabase/ssr 0.6.1, MapLibre GL 4.7.1, deck.gl 9.1.15, h3-js 4.1.0; Vitest 2.1.9 (dev).
Licences: `[PENDING: chief]` — read each package's licence from its metadata before the README states them; do not copy from SPEC P11.

## Spec text that main contradicts (do not reuse)

- "Nemotron 3 Super 120B" as the reasoning model (SPEC L4, L5, M2, P7; `metadata.json` `nvidia[2]`). Main runs **Ultra 550B** (D-017). `metadata.json` is WS5-05, the chief's file.
- "Super VL reads the CCTV still" (SPEC M2). Images are refused (D-021).
- "12 named queries", "25 sources, 4+ storage types", "S3 CSV / S3 Parquet". See the Zetaris rows above.
- "Nexus beats a rules-only baseline" (SPEC M2). No numbers on main (`[PENDING: WS2-14]`).
- `metadata.json` lists engines `["world_model", "hmem"]`; all four pass on main.

## Tracker drift seen while verifying (for the chief)

- WS1-16 (feeds) says `todo`, but #54 merged `40_feeds.sql` + `q_news`.
- WS1-15 / WS1-12 say `in_progress`; #56 merged `q_candidates` live + `tips_v` (partial).
