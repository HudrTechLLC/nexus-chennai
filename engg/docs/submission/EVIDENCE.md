---
tags: [nexus, deliverables]
---

# Submission claims ledger

This note lists every claim the submission drafts make, with the file, test or CI job that proves it. The four drafts ([README_DRAFT](README_DRAFT.md), [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md), [DECK](DECK.md), [VIDEO_SCRIPT](VIDEO_SCRIPT.md)) take their claims only from here. When a `[PENDING: id]` task lands, flip its row here first, then the drafts. `grep -rn "PENDING:" engg/docs/submission/` lists everything still open.

**Verified against `origin/main` @ `54013e3`** (26 Oct 2026; first pass @ `c686f0c`, where CI was green on all five jobs: `api` (ruff + pytest), `engines` (official conformance + E4 tests on the TypeScript references), `judge-path` (docker build + start with `SAMPLE_MODE=true`, no credentials), `web` (typecheck, lint, vitest, `next build`) and `secrets`). Re-check CI on the freeze commit.
Related: [RULES_CHECK](../hackathon/RULES_CHECK.md) · [DELIVERABLES](../DELIVERABLES.md) · [SPONSOR_TECH](../SPONSOR_TECH.md) · [ENGINES](../ENGINES.md) · [AGENTS](../AGENTS.md) · [DECISIONS](../DECISIONS.md)

## Re-verify at freeze (about 2 minutes)

Main keeps moving until 12:00 IST. Run this from a fresh checkout of `origin/main`. For each item that now exists, flip its row below, then the matching `[PENDING]` in the four drafts.

```bash
ls input_examples output_examples data/sample data/sample/model_fixtures 2>&1   # WS2-16, WS1-11
ls output_examples/eval_report.json 2>&1                                        # WS2-14
PYTHONPATH=services/api python -c "from app.adapters.zetaris import NAMED_QUERIES as N; print(sorted(N))"   # WS1-15 (13 + q_ping when done)
ls zetaris/10_views.sql 2>&1; grep -ci 'file\|parquet\|csv' zetaris/00_sources.sql                       # WS1-13, WS1-12
find apps/web/app/console -name page.tsx | sed 's#apps/web/app##' | sort                                 # WS3-06/10/11 (cases, search, fir, series, stations, memory, graph)
grep -rn embed_fallback services/api/app | head -3                                                      # embed stays fallback-only (D-027)
grep -rn "PENDING:" engg/docs/submission/                                                               # what's still open
```

Then check CI on the freeze commit (all five jobs green) and update the "Verified against" line above.

## Judge path

| Claim | Evidence | Status |
|---|---|---|
| Root `Dockerfile` + `requirements.txt`; `docker build -t oah-submission .` works from a clean checkout | `Dockerfile`, `requirements.txt` (→ `services/api/requirements.txt`); CI `judge-path` | ✅ |
| Starts with `SAMPLE_MODE=true` and no credentials, and `/health` answers | `.github/workflows/docker.yml` step "start with SAMPLE_MODE=true and no credentials" | ✅ |
| `python run.py` serves on :8000; `python run.py --once <file>` posts one input to `/run` | `run.py` (sets its own import path; no `PYTHONPATH` needed) | ✅ |
| `docker-compose.yml`: API on :8000, reaches Zetaris and Nightshift on the host through `host.docker.internal`; optional `worker` profile | `docker-compose.yml` | ✅ (live compose run: `[PENDING: WS5-11]`) |
| `docker compose up` = API :8000 **+ web :3001** (NFR-03 / D-003): `web` service from `Dockerfile.web` (#241); server secrets kept out of the web container (#247) | GitHub Actions `docker-web-image`, job `web-image`, run 40337596467 (success): built the image in 2m08s, started it with an empty env, HTTP 200 on `/about/privacy`, `/` and `/console/login`; green again on #247 (nexus-6, 26 Oct) | ✅ |
| `POST /run` returns `run_id, status, output{alerts, series, hotspots, summary}, agents, engines, trace_id, log_file, execution_time_seconds` | `services/api/app/main.py`; `tests/graph/test_graph_pipeline.py`; bad input → 422 in `tests/test_tracing_and_api.py` | ✅ |
| Judge path (fresh clone @ `de8e666`, #283; Windows venv, Python 3.13, `SAMPLE_MODE=true`, no `.env`): all three `input_examples` **match `output_examples` exactly** (status, summary, every alert's pair, band, score and coverage, series). Ex 1: 3 cross-station links, Adyar ↔ Thiruvanmiyur (CHN-TI-2026-001148) high 0.819, Adyar ↔ Velachery (CHN-VL-2026-000877) high 0.7887, CHN-TI-2026-001134 medium 0.6924; series "Red two-wheeler chain snatchings · 3 stations" (4 cases). Ex 2: 7 links (6 cross-station), all medium (coverage cap); series "Night house breaks · 6 stations" (8 cases). Ex 3: 2 medium cross-station links, and a **Skeptic drop** of CHN-GU-2025-000945 ↔ CHN-VL-2025-000926 (different crime types, 4.1 km, day vs night). All 45 model steps `replayed` from fixtures. Install 137 s; `execution_time_seconds` 11.9 / 7.7 / 6.8 (replay) | nexus-7 judge's-eye run, 26 Oct after the reboot (outputs and traces in a local clone, not committed) | ✅ |
| **Judge path runs fully offline** (WS5-12): image from the root Dockerfile, `docker run --network none -e SAMPLE_MODE=true`, empty env (NetworkMode `none`); the 3 examples posted from inside via `docker exec` all return 200 success (1.2 / 1.8 / 1.2 s); `scripts/judge_compare.py`: **exact 3/3** vs `output_examples` after removing only `execution_time_seconds` and the per-query Zetaris `query_id`; 0 network-attempt log lines | CI job `judge-offline` (https://github.com/HudrTechLLC/nexus-chennai/actions/runs/40361549939/job/121708042721, success, head `3cb98b4`), merged as #285 (`b407bd8`); runs on every push to main; nexus-6, 26 Oct. Root cause of an earlier miss fixed in #290: sample DuckDB followed the host time zone (fixtures recorded on IST, CI on UTC) | ✅ |
| Live mode on the judge's own Zetaris, no Supabase (WS1-19): `python -m data.setup_live` generates the city, exports Parquet, stages and registers `nexus_fs` + container `nexusfs`, smoke-tests the hero case; `ZETARIS_DATA=files` switches the source | #280 (`8fbbd86`); `data/README.md` §5; `tests/zetaris/test_files_parity_live.py` (nexus-1) | 🟡 setup_live merged (#280) and its model-output fixtures merged (#293, `f7ea5c2`); a clean-machine run is `[PENDING: WS1-19]` (nexus-1). Not re-run by nexus-7. `/run` can keep results locally (`NEXUS_STORE=local`, #273); the console and worker still use Supabase |
| **Live hero alert, now:** **LA-2026-E38C6B38B865**, CHN-AD-2026-001182 ↔ CHN-VL-2026-000877 (Adyar ↔ Velachery), **high 0.7887, coverage 0.72, status pending**, weights `f2-default-v1`. Factors: MO 0.8848, vehicle **0.85**, suspect description 1, target 1, space–time 0.3279. Skeptic critique applied, **no factor struck**. Last scored by `run_866f913f` (the Red Pulsar re-run, 26 Oct 21:54–22:53; with `run_b6ed1246` it re-scored all 24 Red Pulsar alerts, all pending). Also LA-2026-C802D4F2E02B: pending, medium 0.6794 | nexus-3 DB read, 26 Oct 23:02 | ✅ live |
| Hero alert as first written (26 Oct 10:31 UTC, run `run_c8937dd0`, superseded by rp7): high 0.7867, coverage 0.72; factors MO 0.885, vehicle 0.84 (partial plates TN09??4471 / TN09B?4471, same red Bajaj Pulsar 150), suspect description 1, target 1, space–time 0.328 (3.5 km, 2 days, both evening); Skeptic 1 round, approved, no factor struck. | read-only `link_alerts` + `link_factors` query (nexus-7) at the time | history |
| **Live Skeptic drop** (video seg 6), run `run_da0092da`, **verified in the trace viewer**: step #50 "drop · rejected · 0.69" for CHN-CM-2025-000450 ↔ CHN-CM-2025-000461 (score 0.6937, `struck=[]`). The reason shown: age bands differ (40-50 vs 18-20), different crime categories (shop_theft vs two_wheeler_theft), no vehicle or MO overlap. Before it: the Skeptic's own live Zetaris queries (#46–#48, `via=zetaris`: q_case ×2, q_features) and its critique call (#49, `nvidia/nemotron-3-ultra-550b-a55b`, receipt `chatcmpl-b496ce3a…`). Run header: Skeptic strikes 0 · 2 sent back · 2 alerts written · 93 Zetaris queries. The stored reason is cut with "…" by the tracer's summary limit (`trace_events.output_summary`) | nexus-4, deployed console as **demo admin** (`/console/system/**` is admin-only), 26 Oct; screenshot `trace-skeptic.png` (nexus-4's local scratchpad, steps #45–#50), viewed by nexus-7 | ✅ verified |
| 3 inputs in `input_examples/` + real outputs in `output_examples/` (recorded live with the pinned models; `execution_time_seconds` 236 / 1,046 / 315 s live) + 45 model fixtures in `data/sample/model_fixtures/` | #283 on main | ✅ |
| Sample bundle in `data/sample/`: 1,275 crimes, 1,895 statements, 40 tips, 3 judge series (SER-GRILLE-CUTTERS, SER-NIGHT-CAB, SER-RED-PULSAR) and 3 judge cases, plus ANPR, calls, legacy CCTNS/archive, news and social slices; seed 42, `synthetic: true` | `data/sample/MANIFEST.json` on main | ✅ bundle; recorded model fixtures `[PENDING: nexus-3 judge PR]` |
| Sample mode with Zetaris + Nightshift stopped and no `.env` runs example 1 end to end | depends on the two rows above | `[PENDING: WS5-08]` |
| `.env.example` with placeholders only; both `METERLESS_RUNTIME_TOKEN` and `METERLESS_RUNTIME_TOKEN_FILE` are accepted | `.env.example`; `services/api/app/config.py` | ✅ |
| No secrets tracked | CI `secrets` (file names + value patterns) | ✅ |


## Known limitations (README "Known limitations, in numbers")

| Limitation | Number | Source | Status |
|---|---|---|---|
| Synthetic data, no real-officer trial | 14,040 synthetic crimes in nexus-qa (generator 14,038 + 2 console FIRs); no field trial | `data/README.md` §2 (nexus-1 counts, 26 Oct) | ✅ stated |
| Medium band | 56% (74/132 scored pairs); HIGH 10/10 | `output_examples/eval_report.json` (#275) | ✅ |
| Live speed | 236 / 1,046 / 315 s for the three recorded examples; `run_866f913f` ~59 min for 4 cases, one case at the 3,600 s deadline; replay 6.8–11.9 s | `output_examples/*.json`; nexus-3 (26 Oct 23:02); nexus-7 fresh-clone run @ `de8e666` | ✅ measured (the chief's "~25 min/case" estimate is not used) |
| Vision lane unavailable | `no_vision_model` on every image request; captions used; `vision_unavailable` traced | D-021; README Limitations | ✅ |
| Worker Supabase-only | `/run` local store `NEXUS_STORE=local` (#273, `tests/graph/test_local_store.py`); worker + console need Supabase | `services/api/app/graph/local_store.py` docstring | ✅ |
| Zetaris pushdown workaround | deterministic `ORDER BY` before every limit (#170, #174); `zetaris_result_truncated` event; live parity test | D-031 | ✅ |

## Agents, graph and traces

| Claim | Evidence | Status |
|---|---|---|
| LangGraph graph with a router and three paths (tip, search, case); case path `load_case → extract → plan → link → skeptic → write`; Skeptic can loop back to `plan` | `services/api/app/graph/pipeline.py` (`add_node` / `add_conditional_edges`); `tests/graph/test_graph_pipeline.py` | ✅ |
| Caps: Planner ≤ 3 rounds, Skeptic send-back ≤ 2, run deadline 300 s with a 45 s reserve | [AGENTS](../AGENTS.md) Graph; `pipeline.py` | ✅ |
| 10 agent modules: Tip Guard, Extractor, Planner, Linker, Skeptic, Alert writer, Series analyst, Hotspot detector, Sanitiser, Briefer | `services/api/app/agents/*.py`; `tests/agents/` | ✅ |
| Skeptic re-queries Zetaris itself; verdict `approve` / `send_back` / `drop`, rescored in code; the model may only downgrade. The code can also strike an unsupported factor (`factors_to_strike`, tested), **but no strike has occurred in any run, so public docs never claim strikes** (nexus-chief rule, 26 Oct) | `agents/skeptic.py`; `tests/agents/test_agents_linking.py` | ✅ (drop/send-back); strikes: capability only |
| Nine factors scored in code; a struck factor would keep its weight at 0 (D-016); H-MEM capped ±0.08; coverage guard | `app/scoring/`; `tests/scoring/`; D-016 | ✅ |
| Extractor: when Nightshift refuses an image, it traces `vision_unavailable` and falls back to the caption | `agents/extractor.py` lines ~138–141; D-021 | ✅ |
| Every model call is traced with lane, pinned model, routed model and receipt id | `adapters/nightshift.py` (`chat`, `_trace`, `_receipt_id`); `tests/adapters/test_nightshift.py` | ✅ |
| Receipt id: a `meterless-receipt*` header if present, else a `receipt*` field, else the response `id` | `adapters/nightshift.py::_receipt_id` | ✅ (say exactly this) |
| JSONL trace per run at `logs/trace-<run_id>.jsonl`, also on stdout; copied to Supabase `trace_events` for the console | `app/tracing.py`; D-025; `tests/graph/test_trace_store.py` | ✅ |
| Worker: `alert_decisions` → H-MEM; new tips → Tip Guard; un-featured crimes → graph | `app/worker.py`; `tests/graph/test_worker_store.py` | ✅ |
| Eval vs rules-only baseline (WS2-14): agents P 0.5915 / R 0.8571 / F1 0.70 (148 alerts; HIGH 10/10 correct, MEDIUM 0.5606 = 74 of 132 scored pairs; 6 alerts are flagged duplicates); baseline P 0.0866 / R 0.2959 / F1 0.1339 (341 alerts); 60 truth cases, 98 true pairs; 13 of 60 cases with model features; empty H-MEM, no model calls | `output_examples/eval_report.json` on main @ `b5c5374` (#275, re-run after the sample-mode date fix #270; nexus-2); **reproduced by nexus-7 from fresh clones @ `ea75fff` (119 s) and @ `b5c5374` (292 s), same figures as the committed report each time**, with `cd services/api && SAMPLE_MODE=true python -m app.eval --truth ../../data/sample/_truth --mo-cosine all` | ✅ |
| Live spot-check (WS2-14, separate from the headline): 20 cases (3 judge cases + the first 17 generated-truth crimes) on live Zetaris + nexus-qa, `SAMPLE_MODE=false`, MO mode "off" (the headline's default; `on`/`tfidf` were stopped for Zetaris contention), code-only scoring, 0 model calls, no DB writes: **P 0.6087 / R 0.6364 / F1 0.622** (TP 42 / FP 27 / FN 24, 71 alerts, 2,369 s); reproduced identically before the reboot. Not like-for-like with the sample eval (20 vs 60 cases, different truth set, ~14,040-crime live pool vs 1,275); the recall gap is not yet explained | `output_examples/live_spot_off.json`; code `de8e666` (before #313); nexus-2, 26 Oct 23:36 IST | ✅ (as a separate line, never the headline) |
| Eval page `/console/system/eval` (admin) + P/R card on the System tab (LNK-10, #244) | `apps/web/app/console/(app)/system/eval/page.tsx`, `EvalSummary.tsx`; it renders the committed `output_examples/eval_report.json` (#258), and Vercel built #258 (nexus-6) ; **verified live 26 Oct by nexus-4** as demo admin (read-only pre-check): HTTP 200, 0 console errors; agents 59.2% / 85.7%, F1 70.0%, TP 84 / FP 58 / FN 14 vs baseline 8.7% / 29.6% (F1 13.4%); the provenance block and System-tab card render; no horizontal scroll at 375 px | ✅ verified live. The Tuesday morning dry run repeats it |

## Zetaris

| Claim | Evidence | Status |
|---|---|---|
| Every agent read goes through `ZetarisClient.named(...)`; registry only, query id traced | `adapters/zetaris.py`; `tests/adapters/test_zetaris.py` | ✅ |
| Source `sb`: Supabase Postgres over the session pooler as read-only `zetaris_reader`; 17 tables + 5 datasource views `stations`, `wards`, `crime_features_v`, `tips_v`, `case_bundle_v` (nexus-1 live list, 26 Oct) | `zetaris/00_sources.sql`; `zetaris/README.md` "Live state" | ✅ |
| Tips reach Zetaris only through `tips_v` (safe columns; no passphrase hash, no raw text) | `zetaris/README.md`; migration `0003_zetaris_reader_tips.sql` | ✅ |
| REST feeds served by the Nexus API, all **live**: `nexus_feeds` db + `rest_weather` / `weather_hourly` (744 rows); `rest_news`, `rest_social`, `news_items` (47), `social_posts` (61), `v_news_mentions` (68), from `zetaris/40_feeds.sql` #2–#9 | weather: nexus-2 earlier; news/social: nexus-2, 26 Oct: `news_items` 47, `social_posts` 61, `v_news_mentions` 68; live `q_news` for the hero case CHN-AD-2026-001182 returned 1 row (NEWS-CHN-AD-2026-001182), source `zetaris`, 4.4 s | ✅ |
| Data-quality views (8): `dq_duplicate_firs`, `dq_bad_geo`, `dq_time_inconsistent`, `dq_unmapped_sections`, `dq_flags`, `dq_orphan_evidence`, `dq_tip_without_incident`, `dq_stale_cameras` | `zetaris/20_dq.sql`; `tests/engines/test_dq.py` | ✅ |
| Named-query registry: 15 queries, all with a DuckDB twin (15/15 in sample mode). **Live on Zetaris: 15** (`q_case`, `q_cases`, `q_candidates`, `q_features`, `q_dq_flags`, `q_hex_counts`, `q_tip_corroboration`, `q_vehicle_trail`, `q_offender_return`, `q_calls_near`, `q_station_matrix`, `q_search`, `q_context`, `q_news`, `q_dq_summary`) | `NAMED_QUERIES` on main (14 besides `q_ping`; `q_calls_near` #160); live parity run by nexus-1 for the first 13, 26 Oct; `q_news` live by nexus-2 after WS1-16, 26 Oct; `q_dq_summary` (#252) live via `app.dq_status` by nexus-1, 26 Oct (wrote `system_status` 'zetaris:dq': 230 across 7 rules, 55 s); count of 15 checked by nexus-7 from `NAMED_QUERIES` on main @ `8c52852` | ✅ (15 live / 15 sample) |
| `q_news` live | Live since WS1-16 registered the news feed: nexus-2, 26 Oct: `news_items` 47, `social_posts` 61, `v_news_mentions` 68; live `q_news` for the hero case CHN-AD-2026-001182 returned 1 row (NEWS-CHN-AD-2026-001182), source `zetaris`, 4.4 s. (Before that, on 26 Oct, it got `400 TABLE_OR_VIEW_NOT_FOUND nexus.v_news_mentions` and fell back to "no news"; a live count must still exclude that fallback if it ever recurs) | ✅ |
| Semantic view `v_crime_unified` in the `nexus` container (`zetaris/10_views.sql`, #121; DQ and news views read it since #129); one-trip case view `case_bundle_v` (`zetaris/30_case.sql`, #125) | files on main | ✅ |
| Zetaris semantic layer, live on main (`c0068bd`): **13 schemastore views** in container `nexus`. These are `v_crime_unified` (19,540 rows: `sb.crimes` ∪ `s3csv.cctns` ∪ `s3pq.archive`, `10_views.sql`); 8 DQ views (`20_dq.sql`: dq_duplicate_firs 30, dq_bad_geo 5, dq_time_inconsistent 5, dq_unmapped_sections 20, dq_orphan_evidence 0, dq_tip_without_incident 36, dq_stale_cameras 134, dq_flags 60); and 4 feed views (`40_feeds.sql`: news_items 47, social_posts 61, v_news_mentions 68, weather_hourly 744). On `sb` there are 5 datasource views: stations, wards, crime_features_v, tips_v, case_bundle_v. Vehicle trail, offender return, tip corroboration and calls-near are **named queries that join sources directly, not views** (e.g. `q_vehicle_trail` = `s3pq.anpr_reads` × `sb.crimes`) | nexus-1, live `count(*)` on each, 26 Oct; `zetaris/*.sql`; `services/api/app/adapters/zetaris_queries_n1.py` | ✅ (the planned `v_vehicle_trail` / `v_offender_return` / `v_tip_corroboration` views were not built; that logic is in the named queries) |
| File sources in Zetaris's internal file store (D-022a): 8 CSV tables (`cctv_cameras`, `anpr_cameras`, `vehicles`, `releases`, `history_sheets`, `place_aliases`, `calendar`, `cctns`) + 4 Parquet tables (`anpr_reads`, `calls`, `archive`, `osm_pois`) | `zetaris/01_files.sql`, `stage_files.py` (#140); `zetaris/README.md`: "12 tables, live 2026-10-26, counts in the PR" | ✅ |
| Live `SELECT count(*) AS n FROM sb.crimes` through Zetaris = **14,039** (14,038 generated + 1 console-filed FIR), matching the Postgres count after the additive re-seed | run by nexus-1 on Lightning REST `POST /api/v1.0/sql-editor/sqls/run`, 2026-10-26 08:59:09–08:59:22 UTC (~13 s), source `sb` via `zetaris_reader` | ✅ (recorded, not CI) |

## Meterless engines and Nightshift

| Claim | Evidence | Status |
|---|---|---|
| World Model, H-MEM, Markovian TS references + conformance suites vendored unmodified @ `1742dec5`, Apache-2.0 | `engines-ts/NOTICE`, `engines-ts/LICENSE` | ✅ |
| Official conformance: World Model 8/8, H-MEM 13/13, Markovian 8/8 | `logs/conformance_*.txt` (exit 0); re-run in CI `engines` every PR | ✅ |
| E4 feature tests pass on both the sample backend and the TS references through the sidecar | CI `api` (`pytest -q`) and CI `engines` (`ENGINES_BACKEND=sidecar pytest tests/engines -q`); `tests/engines/test_backend_parity.py` | ✅ |
| Scout Intent (Nexus implementation of the Meterless Scout spec): tuned set 147 (60 queries + 87 tips) route accuracy 1.000 (old rules 0.871), injections 23/23, emergencies 8/8, 0 false quarantines; held-out 40 (untouched): route 0.950, injections 7/7, 0 false quarantines | `logs/feature_scout_intent.txt` (run 2026-10-26 09:28 UTC, after #128); gated in `tests/engines/test_scout_intent.py`; before/after table in PR #128 | ✅ |
| Tip Guard **live** on the 40 seeded tips: 40/40 screened; **0/30 genuine tips falsely quarantined** (before and after #128); emergencies 2/2 urgent. Misses before #128: injections 3/4, spam 1/4 quarantined (misses held as vocabulary-only summaries, no leak to Zetaris). After #128's rules for those shapes: 4/4 and 4/4, **not independent recall** (the misses shaped the rules; labels beyond the four inferred from text). **Always quote held-out + 0/30 first, and never the fixture number alone.** | nexus-chief's live check (26 Oct); `tips` table read-only: 34 screened / 4 quarantined / 2 urgent before #128 (nexus-7); after-numbers from PR #128's table (same 40 tips, offline). Live DB re-screen by nexus-3 after merge `[PENDING]` | ✅ |
| Engine state persisted to Supabase `wm_*` / `hmem_*` (append-only ledger) when `ENGINES_PERSIST=supabase` | migration `0005_01_engines.sql`; D-020; `tests/engines/test_migration_0005.py`, `test_persist.py` | ✅ |
| H-MEM: a decision recorded by the worker reaches the API's next score without a restart (store reopened when `state.json`/`ledger.jsonl` change; lock file for concurrent writers); the next alert row carries `memory_applied` | #82 `tests/engines/test_hmem_shared.py`; #83 `tests/graph/test_hmem_e2e.py` | ✅ |
| Nightshift is the only model path; pinned lanes; `meterless/auto` refused | `adapters/nightshift.py::model_for`, `config.FORBIDDEN_MODELS`; `tests/adapters/test_nightshift.py` | ✅ |
| Lanes: `fast` = `nvidia/nemotron-3.5-lightning-30b-a3b`, `reason` = `nvidia/nemotron-3-ultra-550b-a55b` (Super 120B is 404 for our key) | D-017; `.env.example` | ✅ |
| `vision` = `nvidia/nemotron-3.5-super-vl-120b-a12b`: text calls work, image calls refused (`no_vision_model`) | D-021 | ⚠️ limitation, never claim visual extraction |
| Embed lane `nvidia/nemotron-3.5-embed-1b` | **Not claimed** (D-027): Nightshift 1.2.7 has no `/v1/embeddings` route (404 for every model). Similar-MO and text search use TF-IDF + feature vectors in code (spec E2 fallback), traced `embed_fallback`: `services/api/app/engines/similarity.py`; `tests/engines/test_similarity.py` | ✅ fallback in code; ❌ model not claimed |
| NVIDIA key lives only in Nightshift; the app holds the Nightshift URL + runtime token | `adapters/nightshift.py` docstring; `.env.example` | ✅ |

## Web (Vercel)

| Claim | Evidence | Status |
|---|---|---|
| Public portal: home, appeals list + detail, fuzzed hex map, CCTV page, anonymous tip (EXIF stripped, tip code, status, replies), privacy | `apps/web/app/(public)/**`; WS4-01…06 done | ✅ |
| Console: sign-in + roles, alerts inbox + detail, map, appeals, tip triage, system status + trace viewer | `apps/web/app/console/(app)/**` pages exist; CI `web` green | ✅ pages exist; completeness of WS3-04/05/07/08/09 and WS4-07/08: `[PENDING]` per task |
| Tip triage live on the deployed console (nexus-chennai.vercel.app): All tab = 40 tips; tabs To triage 34 / Urgent 2 / Quarantined 4 / Reviewed 0, matching the DB; quarantined tips visible to police with a "never passed to the agents" banner and the tip text fenced as untrusted; detail opens for analyst and station officer | nexus-4 headless Chromium check, 2026-10-26 ~09:20 UTC, screenshots `tips1.png` (queue) + `tip-detail-quarantined.png` (TIP-YVSHFQLY), viewed by nexus-7. Note: the queue frame shows a missed spam tip marked `Guard: clean`; caption it honestly | ✅ |
| Case list + case file (#61); unified search with facets (#78); FIR capture form + `file_fir` RPC (#73); evidence and audio-statement upload, evidence gallery (#88) | `console/(app)/cases/**`, `search/page.tsx`; CI `web` | ✅ built |
| Evidence keeps its original bytes; sha256 over the original + custody step at upload; stored object = recorded hash; direct insert, other station, anon, overwrite and public URL refused | `apps/web/scripts/evidence-check.mjs` 9/9 live (26 Oct, after 0007_06); `supabase/tests/0007_06_record_evidence_rls.py` 16/16; D-029 | ✅, **with a limit:** the upload route computes sha256 server-side; the database enforces that the evidence row matches a storage object the caller uploaded (owner, size, mime) and sets uploaded_by + custody itself; the hash itself is not re-verified in the database. Never call it "tamper-proof". |
| Public appeal stills (PUB-02): the app blurs the whole image (`whole_image_downscale_v1`, long side 48 px) and re-encodes it with no metadata; the public `appeal-public` bucket takes small JPEGs only, and only officers who can write the case may add or remove stills; a trigger on `public_incidents.images` requires every still to be under this appeal's prefix, marked blurred, present in the bucket and taken from this case's evidence | `supabase/migrations/0004_06_05_appeal_stills.sql` (applied, nexus-6, 26 Oct); `tests/console/test_appeal_stills_rls_live.py` 4/4 live; `apps/web/lib/__tests__/stillBlur.test.ts`, `appealStills.test.ts` (CI web job); #197 | ✅, **with a limit:** blur, not face/plate detection; an officer with case write access could upload an unblurred JPEG straight through the storage API (README Limitations). First live attach, a chief-approved test never published (nexus-6, 26 Oct). Seeded still EV-3775afea… on CHN-KA-2025-000077 was downloaded and whole-image blurred (68.9 KB → 12.8 KB, 640×360). The public copy returned HTTP 200 anonymously with no EXIF. The trigger refused a path to the original. Audit recorded `attach_still`. Withdrawing removed the copy (listing empty). The original stays private (public URL 400) |
| Series list + series page with Markovian dossier, station link matrix (#70); H-MEM memory page + World Model graph explorer (#85). RPCs `station_link_matrix`, `series_overview`, `hmem_effects`, `wm_graph` (security invoker, read-only, jsonb; anon refused; D-028) | `console/(app)/{series,stations,memory,graph}/**`; migrations `0004_06_01_series_stations.sql`, `0004_06_02_memory_graph.sql`; vitest `series`, `stationMatrix`, `memory`, `worldGraph` (CI `web`) | ✅ built |
| **Live on real nexus-qa rows (nexus-6, 26 Oct):** `/console/stations` shows the real alerts for all 5 demo roles; `/console/graph` shows the World Model with provenance (analyst view 124 nodes at check time; station officers see only their crimes' entities, by RLS); `/console/memory` shows a real analyst reject (LA-2026-266EFBCEEBBE, `different_offenders`) turned by the worker into H-MEM memory `nexus:mem-1` + a ledger row. "Changed later scores" is empty until a similar pair is scored | nexus-6 live check; read-only counts (nexus-7, later the same day): `wm_entities` 756, `wm_edges` 496, `wm_observations` 1,260 (backfill growing), `hmem_memories` 1, `hmem_ledger` 1, `alert_decisions` 1 | ✅ |
| `/console/series` and `/console/series/[id]` on real rows | Series SER-B687C36CFC, shown as **"Red two-wheeler chain snatchings · 3 stations"** (Red Pulsar; 9 cases across PS-ADYAR / THIRUVANMIYUR / VELACHERY after D-033 removed the test FIR; status `candidate`), written by nexus-3's live batch with a Markovian dossier (model `nvidia/nemotron-3-ultra-550b-a55b`, `run_id` set). `series_overview` returns it to every police role through PostgREST. The detail path was checked as the analyst (full rows) and as the Adyar officer (full row only for its own station, a city-wide summary for the rest: RLS as designed) | nexus-6, 26 Oct (chief OK) | ✅ (all four WS3-11 screens live: stations, graph, memory, series). Dossier quality is not claimed |
| Pulse Map data-source layers + vehicle trail | #86 | ✅ built |
| Tip passphrases hashed with pgcrypto bcrypt inside Postgres (deviation from spec Argon2id) | D-023; migration `0004_03_public_rpcs.sql` (`gen_salt('bf', …)`) | ✅ |

## Libraries (for the README dependency list)

Python (`services/api/requirements.txt`): FastAPI 0.115.6, Uvicorn 0.32.1, Pydantic 2.10.4, pydantic-settings 2.7.0, httpx 0.28.1, tenacity 9.0.0, DuckDB 1.1.3, PyYAML 6.0.2, h3 4.5.0, LangGraph 1.2.17.
Web (`apps/web/package.json`): Next.js 14.2.35, React 18, @supabase/supabase-js 2, @supabase/ssr 0.6.1, MapLibre GL 4.7.1, deck.gl 9.1.15, h3-js 4.1.0; Vitest 2.1.9 (dev).
Licences: `[PENDING: chief]` — read each package's licence from its metadata before the README states them; do not copy from SPEC P11.

## Spec text that main contradicts (do not reuse)

- "Nemotron 3 Super 120B" as the reasoning model (SPEC L4, L5, M2, P7; `metadata.json` `nvidia[2]`). Main runs **Ultra 550B** (D-017). `metadata.json` is WS5-05, the chief's file.
- "Super VL reads the CCTV still" (SPEC M2). Images are refused (D-021).
- "12 named queries", "25 sources, 4+ storage types", "S3 CSV / S3 Parquet". See the Zetaris rows above.
- ~~"Nexus beats a rules-only baseline"~~: now on main (WS2-14, P 0.59 vs 0.09, R 0.86 vs 0.30). Say it with the numbers and the 10/10 HIGH, 56% MEDIUM split, never as an unqualified accuracy claim.
- `metadata.json` lists engines `["world_model", "hmem"]`; all four pass on main.

## Tracker drift seen while verifying (for the chief)

- ~~WS1-16 drift~~: wrong at the time. #54 merged the SQL, but news/social were registered only later; nexus-2 confirmed them live on 26 Oct.
- WS1-15 / WS1-12 say `in_progress`; #56 merged `q_candidates` live + `tips_v` (partial).
