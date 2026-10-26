---
tags: [nexus, deliverables]
---

# README draft (WS5-03)

This is the draft of the root `README.md`, for nexus-chief to review and fold in. Everything below the line is README text. Each claim comes from [EVIDENCE](EVIDENCE.md), which was verified against `origin/main` @ `c686f0c`. `[PENDING: id]` marks something that isn't on main yet: replace it when the task lands, or delete the sentence before submission.
Related: [EVIDENCE](EVIDENCE.md) · [README_DRAFT_AGENTS](../README_DRAFT_AGENTS.md) · [DELIVERABLES](../DELIVERABLES.md) · [RULES_CHECK](../hackathon/RULES_CHECK.md) · [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md)

> **Notes for the chief, not README text:**
> - Relative links below are written for the repo root (`engg/docs/...`), not for this folder.
> - The Participant Setup Guide is only in the HackOS Resource Center (login). I linked the Resource Center. Swap in a direct link if the guide has a public one.
> - The demo video link and the live Vercel URLs are yours to fill in.

---

# Nexus Chennai

**Track 1 · Solving Fragmented Intelligence** · Open Agent Hackathon 2026 · team Heisenbugs

Each police station in a city sees only its own cases. A gang that snatches chains near one station on Monday and another on Friday looks like two unrelated robberies. Nexus is a set of agents that read the city's fragmented records through **Zetaris**, think with **NVIDIA Nemotron** through **Meterless Nightshift**, and raise *link alerts* for crimes that are probably related across stations. Each alert shows its score, the evidence for each reason and the Zetaris query behind it. A Skeptic agent re-checks every link against fresh rows before a human decides, and the human's decision teaches the system through the Meterless **H-MEM** engine.

> **All data in this repository is synthetic** (`synthetic: true` on every row). No real people, cases or police systems are involved.

Demo video: `[PENDING: WS5-07 link]` · Live portal and console: `[PENDING: chief, Vercel URLs]`

## Contents
[What it does](#what-it-does) · [Architecture](#architecture) · [Agents](#agents) · [Meterless engines](#meterless-engines) · [Sponsor technology](#sponsor-technology) · [Setup](#setup) · [Run](#run) · [Sample mode vs live](#sample-mode-vs-live) · [Examples](#examples) · [Traces and logs](#traces-and-logs) · [Tests](#tests) · [Evaluation](#evaluation) · [Limitations](#limitations) · [Responsible AI](#responsible-ai) · [Third-party code and pre-existing work](#third-party-code-and-pre-existing-work) · [AI and model usage](#ai-and-model-usage)

## What it does

- **Links cases across stations.** For a new case, agents find candidate cases city-wide, score each pair on nine factors in code, and write an alert with per-factor evidence.
- **Checks its own work.** The Skeptic re-queries Zetaris itself, strikes any factor its own rows don't support, and can send a pair back for a narrower search or drop it.
- **Keeps a human in charge.** Every alert waits for an analyst. Approvals and rejections go to H-MEM, so a similar pair scores differently next time.
- **Lets the public help safely.** Anyone can send an anonymous tip. Tip Guard (Meterless Scout Intent) screens it for injection, threats and spam before any agent reads it.
- **Groups links into series** and builds a dossier with the Meterless Markovian engine.

## Architecture

```
 Vercel (Next.js)                       Team laptop                                  Cloud
 ┌──────────────────────┐       ┌─────────────────────────────────────┐      ┌──────────────────┐
 │ Public portal        │       │ Nexus API (FastAPI + LangGraph)     │      │ Supabase         │
 │ Police console       │◄─────►│  agents ── named queries ──► Zetaris│◄────►│ (system of record│
 │ (reads Supabase      │ Supa- │  agents ── model calls ──► Nightshift──────►│  + RLS)          │
 │  under RLS)          │ base  │  engines (Meterless) ── TS sidecar  │      │ NVIDIA Nemotron  │
 └──────────────────────┘       └─────────────────────────────────────┘      │ (via Nightshift) │
                                                                             └──────────────────┘
```

- **Zetaris** is the data layer. It federates Supabase Postgres and REST news/social feeds today, and agents may only run registered named queries. More detail under [Sponsor technology](#sponsor-technology).
- **Nightshift** is the only path for model calls. The NVIDIA key lives only in Nightshift.
- **Supabase** holds what police and the public create (cases, tips, alerts, decisions), with row-level security per role. It also holds trace copies and engine state so the Vercel console can show them.
- The **website can't reach the laptop**, so it reads alerts and traces from Supabase and writes decisions and tips there. A worker on the laptop picks them up.

Diagrams and the full design: [engg/docs/ARCHITECTURE.md](engg/docs/ARCHITECTURE.md).

## Agents

A LangGraph graph routes each input down one of three paths:

- **case:** `load_case → extract → plan → link → skeptic → write`; the Skeptic can send pairs back to `plan`.
- **tip:** `tip_guard → tip_extract` (clean tips only).
- **search:** Scout Intent picks the route, then the query runs.

Caps: the Planner runs at most 3 rounds, the Skeptic sends back at most 2 times, and a run has a 300-second deadline. With under 45 seconds left, model calls are skipped and the code results stand.

| Agent | Runs on | Code decides | Model decides | Can block a link? |
|---|---|---|---|---|
| Tip Guard | Scout Intent engine | verdict, fails closed | — | blocks a tip |
| Extractor | Nemotron Lightning (`fast`) | schema, confidence, protected-attribute drop, World Model ingest | modus operandi labels | no |
| Planner | Nemotron Ultra (`reason`) | allow-listed queries, clamps, default plan | query order and windows | no |
| Linker | code + Ultra | all nine factor scores, evidence, H-MEM adjustment | one plain reason per factor | no |
| Skeptic | code + Ultra | its own re-query, strikes, rescoring, drop | critique; may only downgrade | **yes** |
| Alert writer | code | the alert record, coverage, notifications | — | no |
| Series analyst | code + Markovian + Ultra | series of 3+ connected links | dossier chunk notes | no |
| Hotspot detector | code (Poisson test) | everything | — | no |
| Sanitiser | Lightning | allowed facts, leak check | public appeal wording (draft; an officer publishes) | no |
| Briefer | Lightning | every number | prose (rejected if it invents a number) | no |
| **Analyst (human)** | console | — | — | **yes, always** |

Scores are computed in code: the nine factors are modus operandi, space–time, vehicle, suspect description, weapon/tool, target, forensic, corroboration and offender return. The models write labels, plans and reasons, and any number a model returns is ignored. Details: [engg/docs/AGENTS.md](engg/docs/AGENTS.md).

## Meterless engines

| Engine | What it does in Nexus | Test evidence |
|---|---|---|
| **World Model** | One canonical entity per real-world thing (plate, person, phone, place, FIR), with stable ids and provenance, so agents agree on what a fact refers to | Official conformance **8/8** (`logs/conformance_world_model.txt`) + E4 feature tests |
| **H-MEM** | Turns analyst decisions into memories that shift a similar pair's score by at most ±0.08; every step goes to an append-only trust ledger | Official conformance **13/13** (`logs/conformance_hmem.txt`) + E4 feature tests |
| **Markovian** | Reads a whole series in bounded chunks with a capped carryover for the dossier; logs projected vs actual tokens | Official conformance **8/8** (`logs/conformance_markovian.txt`) + E4 feature tests |
| **Scout Intent** | Routes analyst searches; Tip Guard quarantines injection, threats, abuse and spam in public tips and flags emergencies | 120 fixtures: route accuracy **1.000**, injections quarantined **18/18**, emergencies 8/8, no false quarantines. Held-out 40: route accuracy **0.950**, injections 7/7 (`logs/feature_scout_intent.txt`) |

World Model, H-MEM and Markovian run as the vendored TypeScript references in a local sidecar (`engines-ts/`), so the official suites run unchanged. Python ports of the same algorithms are the default in-process backend, and a parity test checks that the two backends agree. CI runs the conformance suites and the feature tests on both backends on every PR. Details: [engg/docs/ENGINES.md](engg/docs/ENGINES.md).

## Sponsor technology

| Sponsor | How Nexus uses it |
|---|---|
| **Zetaris** (data layer) | Source `sb` is Supabase Postgres, read as a read-only role: 17 tables plus 4 datasource views. Tips are exposed only as `tips_v`, a view of safe columns. REST news and social feeds are registered as Lightning REST tables. There are 8 data-quality views (duplicate FIRs across stations, bad geo, time inconsistencies and more). Agents run only registered named queries; live today are `q_case`, `q_candidates`, `q_features`, `q_dq_flags`, `q_news`, `q_hex_counts`, `q_search` and `q_station_matrix`, each with a DuckDB twin for sample mode. The rest of the planned set is `[PENDING: WS1-15]`; semantic views are `[PENDING: WS1-13]`; CSV/Parquet file sources are `[PENDING: WS1-12]`. |
| **Meterless Nightshift** (primary AI provider) | `services/api/app/adapters/nightshift.py` is the only model path. It uses Nightshift's OpenAI-compatible API on pinned lanes, never `meterless/auto`. Every call logs the lane, the pinned model, the model Nightshift reports back and a receipt id. |
| **Meterless engines** | All four, as above. |
| **NVIDIA Nemotron** | `fast` = `nvidia/nemotron-3.5-lightning-30b-a3b` and `reason` = `nvidia/nemotron-3-ultra-550b-a55b`, both through Nightshift. The model is named on every trace line. |

Full text: [engg/docs/SPONSOR_TECH.md](engg/docs/SPONSOR_TECH.md).

## Setup

You need Python 3.11, Git, and Docker Desktop (for the container path). Live mode also needs Zetaris and Meterless Nightshift running locally. Install both by following the **Participant Setup Guide** in the HackOS Resource Center (<https://hackathon.genai.works/resources>, login needed). The Zetaris guides are at <https://zetaris.github.io/getting-started> and Nightshift is at <https://meterless.ai>.

### Option A: Docker (the judge path)

```bash
git clone https://github.com/HudrTechLLC/nexus-chennai.git && cd nexus-chennai
docker build -t oah-submission .
docker run --rm -p 8000:8000 -e SAMPLE_MODE=true oah-submission     # no credentials needed
curl http://localhost:8000/health
```

For live mode, copy `.env.example` to `.env`, fill it in, and run `docker compose up`. Compose points the API at Zetaris (`:8888`) and Nightshift (`:8088`) on your machine through `host.docker.internal`.

### Option B: Python virtual environment

```bash
git clone https://github.com/HudrTechLLC/nexus-chennai.git && cd nexus-chennai
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip install -r requirements.txt
SAMPLE_MODE=true .venv/bin/python run.py           # serves on http://127.0.0.1:8000
```

`run.py` sets its own import path, so no `PYTHONPATH` is needed.

### Live configuration

Copy `.env.example` to `.env` and set these:

- **Zetaris:** `ZETARIS_REST_URL` (default `http://localhost:8888/api/v1.0`) and `ZETARIS_ORG_ID`. For the API key, set either `ZETARIS_API_KEY` or `ZETARIS_API_KEY_FILE` (a path to a file holding it; preferred).
- **Nightshift:** `METERLESS_BASE_URL` (default `http://127.0.0.1:8088/v1`). For the runtime token, **either** export `METERLESS_RUNTIME_TOKEN` in your shell (a `.env` file doesn't export it for other tools) **or** set `METERLESS_RUNTIME_TOKEN_FILE` to the token file Nightshift writes itself (on Windows, `%LOCALAPPDATA%/ai.meterless.runtime/proxy-token`). Lanes: `LANE_FAST`, `LANE_REASON` (and `LANE_VISION`, see [Limitations](#limitations)). Pin exact `nvidia/*` ids; `meterless/auto` is refused.
- **Supabase:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY_FILE` for the worker.
- **News and social feeds:** live runs need the Nexus API running on :8000 (`python run.py`) before Zetaris reads the news and social feeds, because Zetaris fetches `/mock-feeds/*` from the API. If the API is down, runs still complete, just without news evidence.
- **Engines:** `ENGINES_BACKEND=sample` (default, in-process) or `sidecar` (the TypeScript references: `cd engines-ts && npm ci && npm run install:references && npm run sidecar`).

## Run

```bash
# one input through the full graph, printed as JSON
python run.py --once input_examples/example_1.json

# or against the running API
curl -s -X POST http://localhost:8000/run -H "Content-Type: application/json" -d @input_examples/example_1.json
```

`POST /run` takes `{"run_id"?, "input": {"kind": "case" | "batch" | "tip" | "search", ...}, "options": {...}}` and returns `run_id`, `status`, `output` (`alerts`, `series`, `hotspots`, `summary`), `agents`, `engines`, `trace_id`, `log_file` and `execution_time_seconds`. Bad input returns a 422; it never returns a made-up answer.

Other routes: `POST /api/cases/{id}/process`, `POST /api/batch/link`, `POST /api/cases/{id}/public-draft`, `POST /api/series/{id}/dossier`, `POST /api/briefing`, `GET /api/traces/{run_id}`. The worker (`python -m app.worker`, or `docker compose --profile worker up`) handles analyst decisions, new tips and new cases.

## Sample mode vs live

| | Sample mode (`SAMPLE_MODE=true`) | Live |
|---|---|---|
| Data | Each named query runs as its DuckDB twin over `data/sample/` | Zetaris runs the named query over the federated sources |
| Models | Replays model output **recorded from live Nightshift calls** (`data/sample/model_fixtures/`); trace lines say `replayed` | Nightshift on pinned Nemotron lanes |
| Agents, scoring, Skeptic | the same code | the same code |
| Missing recording | A documented fallback runs and is traced (default plan, code-written reasons, code-only Skeptic verdict). It never invents an answer | — |
| Engines | in-process | in-process or the TypeScript sidecar; state written to Supabase with `ENGINES_PERSIST=supabase` |

Fixtures replay only when Nightshift can't be reached, and they are never keyed to an example id, so different inputs give different outputs. The committed sample bundle (≈600 crimes, 3 series, 40 tips) is `[PENDING: WS1-11]`. The end-to-end check with Zetaris and Nightshift stopped and no `.env` is `[PENDING: WS5-08]`.

## Examples

`[PENDING: WS2-16]`: three inputs in `input_examples/` and their real outputs in `output_examples/`. When they land, the planned set is:

| Input | What it shows |
|---|---|
| `example_1.json`: case CHN-AD-2026-001182 | Red Pulsar Duo: a cross-station chain-snatching link; the Skeptic's strikes are in the trace |
| `example_2.json`: case CHN-KU-2025-000078 | Grille Cutters: night house breaks across several stations |
| `example_3.json`: batch of 2 cases | Night Cab and a second pair |

Fill this table from the committed files, not from the plan.

## Traces and logs

Every run writes `logs/trace-<run_id>.jsonl` and echoes each line to stdout. Each line records the agent, the action, the model lane, the pinned model, the model Nightshift reports, the receipt id, the Zetaris query ids, the engine, confidence, retries and status. Receipt id means a `meterless-receipt` header if Nightshift sends one, otherwise a receipt field, otherwise the response id. The same events are copied (with redaction) to Supabase `trace_events`, and the console trace viewer at `/console/system/trace/<run_id>` shows them. Engine evidence is under `logs/`: `conformance_*.txt` and `feature_scout_intent.txt`.

## Tests

```bash
pip install -r services/api/requirements-dev.txt
pytest -q                                   # all Python tests
pytest tests/engines -q                     # engine feature tests (sample backend)
(cd engines-ts && npm ci && npm run install:references)   # once
node engines-ts/scripts/run-conformance.mjs  # official Meterless conformance suites
```

CI runs on every PR: `api` (ruff + pytest), `engines` (conformance + feature tests against the TypeScript references), `judge-path` (docker build, start with `SAMPLE_MODE=true` and no credentials, POST each input example), `web` (typecheck, lint, vitest, build) and `secrets` (no secret files or values tracked).

## Evaluation

`python -m app.eval` (from `services/api`) compares the linker against a rules-only baseline (same category, ≤ 2 km, ≤ 14 days) on the planted ground truth. It makes no model calls. Results: `[PENDING: WS2-14]` (`output_examples/eval_report.json`). Fill them in from the report only.

## Limitations

- **Synthetic data.** All data is generated for this hackathon. Any quality number is measured on planted structure, not on real police data.
- **Vision via Nightshift.** Nightshift refuses every request that carries an image (`no_vision_model`) on every route, though text calls to the Super VL model work. This was reported to Meterless. The Extractor traces `vision_unavailable` and falls back to the officer's caption. No visual extraction is faked.
- **Reasoning model.** The spec planned Nemotron Super 120B, but our key isn't served it, so the `reason` lane runs Nemotron Ultra 550B. It is slower, so the run deadline keeps a 45-second reserve.
- **Zetaris and Supabase Storage (S3) TLS.** Zetaris's S3 client can't complete a TLS handshake with Supabase Storage's S3 endpoint. CSV and Parquet files therefore go into Zetaris's own internal file store instead, still registered as file sources. The fix is documented in `zetaris/README.md`. We didn't apply it because it means restarting Zetaris mid-build.
- **Tip passphrases use bcrypt, not Argon2id.** The spec said Argon2id. We hash with pgcrypto bcrypt inside Postgres so the hash never leaves the database. Tip codes are random and attempts are limited.
- **Explanations are model-written** and can be imperfect. Numbers can't be, because code computes them, and the Skeptic re-checks factors against fresh rows.
- **Hotspots** use a Poisson test against each cell's own recent history. They flag concentrations, not causes.
- **Work still landing** at the time of writing is marked `[PENDING]` in this README.

## Responsible AI

- **Human gate.** Nexus suggests; people decide. An analyst decides every link, and an officer publishes every public appeal. Rejected alerts stay visible to all police roles.
- **Explanations.** Every alert shows each factor's score, a plain reason and the Zetaris query and row behind it, plus the Skeptic's verdict and any memory applied.
- **Tips are untrusted.** Tip Guard screens every tip and fails closed. Agents read only the redacted text of tips that passed. Zetaris sees tips only through a view of safe columns.
- **Public privacy.** The public map uses fuzzed hex cells with a minimum-count cutoff. Tip photos have their EXIF metadata stripped.
- **Protected attributes** (religion, caste, community) are never used for scoring or written into public text.
- **Synthetic data only.** No real personal data is used anywhere.

## Third-party code and pre-existing work

- **Meterless engines.** The World Model, H-MEM and Markovian TypeScript reference implementations and their conformance suites are vendored unmodified from github.com/Meterless/Meterless @ `1742dec56a66e58eef9dda2d2b865823758ca8cd` (Apache-2.0) in `engines-ts/` (see `engines-ts/NOTICE`). Scout Intent is implemented by Nexus from the Meterless Scout spec. The Python sample backends in `services/api/app/engines/*/core.py` are Nexus ports of the reference algorithms.
- **Pre-existing components:** only the vendored Meterless engines above. The repository and the product spec were written inside the build window (spec 23–26 Oct 2026). All data is synthetic and was generated during the window.
- **Open-source libraries:** FastAPI, Uvicorn, Pydantic, httpx, tenacity, DuckDB, PyYAML, h3 and LangGraph (Python); Next.js, React, Supabase JS, MapLibre GL, deck.gl and h3-js (web). Licences: `[PENDING: chief]`.

## AI and model usage

- Product model calls go only through Meterless Nightshift, on pinned NVIDIA Nemotron lanes.
- Claude Code (Anthropic) was used as a development tool. It is not in the product's request path.
- The demo narration voice was generated with ElevenLabs, which is not part of the running product.
- Cursor was not used.

## Docs

Everything else is in [engg/docs/](engg/docs/00-INDEX.md): spec, architecture, decisions, engines, agents and progress.
