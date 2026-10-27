# Nexus Chennai

**Track 1 · Solving Fragmented Intelligence** · Open Agent Hackathon 2026 · team Heisenbugs

Each police station in a city sees only its own cases. A gang that snatches chains near one station on Monday and another on Friday looks like two unrelated robberies. Nexus is a set of agents that read the city's fragmented records through **Zetaris**, think with **NVIDIA Nemotron** through **Meterless Nightshift**, and raise *link alerts* for crimes that are probably related across stations. Each alert shows its score, the evidence for each reason and the Zetaris query behind it. A Skeptic agent re-checks every link against fresh rows before a human decides, and the human's decision teaches the system through the Meterless **H-MEM** engine.

> **All crime, person, case and tip data in this repository is synthetic.** Database rows carry `synthetic: true`; the 8 legacy station CSV exports have no per-row flag, but they are generated too and are labelled synthetic in [data/README.md](data/README.md) and `data/sample/MANIFEST.json`. Map, ward, police-station and weather reference data is real public open data ([data/README.md](data/README.md)). No real people, cases or police systems are involved.

Demo video: <https://www.youtube.com/watch?v=LtisPFLVUwQ> · Live app: <https://nexus-chennai.vercel.app>. Demo sign-ins for judges are in the submission form; see [Live app](#live-app).

**What linking finds.** In the live demo data, Nexus proposes one series that no single station's register shows: **"Red two-wheeler chain snatchings · 3 stations"**, 10 chain snatchings across Adyar, Thiruvanmiyur and Velachery (the 10th is the FIR filed on camera on 27 Oct). One of its high cross-station pairs, Adyar ↔ Velachery two days apart, shares a partial plate and the same red Bajaj Pulsar 150 and scores **high (0.789)**; the analyst approved it on camera on 27 Oct. The series and every other alert in it are proposals: each waits for an analyst's decision. On the judge path (a fresh clone, sample data) the same series shows 4 cases (see [Examples](#examples)). All of it is planted synthetic data.

**What's new compared with established crime linkage.** Established linkage systems rely on structured case forms and analysts comparing cases by hand. Nexus instead:
- reads every source where it already lives (case files, legacy station exports, ANPR, 112 calls, tips, feeds) through Zetaris, with no central copy;
- has agents cite the Zetaris query and row behind every factor in an alert;
- has a Skeptic that re-queries the data itself and gives a second opinion on each pair (send back or drop); the officer decides;
- feeds screened public tips back in as corroborating evidence on a link (the corroboration factor);
- learns from each analyst decision within a capped ±0.08 (H-MEM).

## Contents
[What it does](#what-it-does) · [Architecture](#architecture) · [Agents](#agents) · [Meterless engines](#meterless-engines) · [Sponsor technology](#sponsor-technology) · [Setup](#setup) · [Run](#run) · [Sample mode vs live](#sample-mode-vs-live) · [Examples](#examples) · [Traces and logs](#traces-and-logs) · [Tests](#tests) · [Evaluation](#evaluation) · [Limitations](#limitations) · [Responsible AI](#responsible-ai) · [Live app](#live-app) · [Third-party code and pre-existing work](#third-party-code-and-pre-existing-work) · [Licences](#licences) · [AI and model usage](#ai-and-model-usage)

## What it does

- **Links cases across stations.** For a new case, agents find candidate cases city-wide, score each pair on nine factors in code, and write an alert with per-factor evidence.
- **Gives a second opinion.** The Skeptic re-queries Zetaris itself, critiques each pair against its own rows, and can send a pair back for a narrower search or drop it. It is not a guarantee: on a planted test its model critique dropped none of 24 look-alike false links. Since ~07:20 IST on 27 Oct a deterministic contradiction check also runs on new cases (Known limitations). The officer decides.
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

- **Zetaris** is the data layer. It federates Supabase Postgres and CSV/Parquet file sources, plus REST feeds served by the Nexus API (weather, news and social), and agents may only run registered named queries. More detail under [Sponsor technology](#sponsor-technology).
- **Nightshift** is the only path for model calls. The NVIDIA key lives only in Nightshift.
- **Supabase** holds what police and the public create (cases, tips, alerts, decisions), with row-level security per role. It also holds trace copies and engine state so the Vercel console can show them.
- The **website can't reach the laptop**, so it reads alerts and traces from Supabase and writes decisions and tips there. A worker on the laptop picks them up.

Diagrams and the full design: [engg/docs/ARCHITECTURE.md](engg/docs/ARCHITECTURE.md).

## Agents

A LangGraph graph routes each input down one of three paths:

- **case:** `load_case → extract → plan → link → skeptic → write`; the Skeptic can send pairs back to `plan`.
- **tip:** `tip_guard → tip_extract` (clean tips only).
- **search:** Scout Intent picks the route, then the query runs.

Caps: the Planner runs at most 3 rounds and the Skeptic sends back at most 2 times. A `/run` or batch run has a 300-second deadline; a worker run for one console-filed FIR has 420 seconds. With under 45 seconds left, model calls are skipped, no more send-backs happen, and the code results stand. The deadline is checked between steps, so a run can overrun by one in-flight model call (a filing run finished at 436 s against 420). Past the deadline, approved pairs are written, and pairs still sent back are written as `needs_revision` (never approved). Optional Planner queries get 30 s and one attempt, then are skipped for the rest of the run.

| Agent | Runs on | Code decides | Model decides | Can block a link? |
|---|---|---|---|---|
| Tip Guard | Scout Intent engine | verdict, fails closed | — | blocks a tip |
| Extractor | Nemotron Lightning (`fast`) | schema, confidence, protected-attribute drop, World Model ingest | modus operandi labels | no |
| Planner | Nemotron Ultra (`reason`) | allow-listed queries, clamps, default plan | query order and windows | no |
| Linker | code + Ultra | all nine factor scores, evidence, H-MEM adjustment | one plain reason per factor | no |
| Skeptic | code + Ultra | its own re-query, rescoring, send-back, drop | critique; may only downgrade | **yes** |
| Alert writer | code | the alert record, coverage, notifications | — | no |
| Series analyst | code + Markovian + Ultra | series of 3+ connected links | dossier chunk notes | no |
| Hotspot detector | code (Poisson test) | everything | — | no |
| Sanitiser | Lightning | allowed facts, leak check | public appeal wording (draft; an officer publishes) | no |
| Briefer | Lightning | every number | prose (rejected if it invents a number) | no |
| **Analyst (human)** | console | — | — | **yes, always** |

Scores are computed in code: the nine factors are modus operandi, space–time, vehicle, suspect description, weapon/tool, target, forensic, corroboration and offender return. The models write labels, plans and reasons, and any number a model returns is ignored. Each alert also shows its **coverage**: the share of the factor weights that had data for this pair. Under 50% coverage the band is capped at medium, so a pair can score 1.0 on the few factors it has and still be medium. Details: [engg/docs/AGENTS.md](engg/docs/AGENTS.md).

## Meterless engines

Nexus uses **all four** Meterless engines, each in a product feature with a passing test.

| Engine | What it does in Nexus | Test evidence |
|---|---|---|
| **World Model** | One canonical entity per real-world thing (plate, person, phone, place, FIR), with stable ids and provenance, so agents agree on what a fact refers to | Official conformance **8/8** (`logs/conformance_world_model.txt`) + E4 feature tests |
| **H-MEM** | Turns analyst decisions into memories that shift a similar pair's score by at most ±0.08; every step goes to an append-only trust ledger | Official conformance **13/13** (`logs/conformance_hmem.txt`) + E4 feature tests |
| **Markovian** | Reads a whole series in bounded chunks with a capped carryover for the dossier; logs projected vs actual tokens | Official conformance **8/8** (`logs/conformance_markovian.txt`) + E4 feature tests |
| **Scout Intent** | Routes analyst searches; Tip Guard quarantines injection, threats, abuse and spam in public tips and flags emergencies | **Independent:** held-out 40 (never tuned on): route accuracy **0.975**, injections **7/7**, 0 false quarantines (0.950 before #144, a routing fix prompted by a console search, not by the held-out set). On the 40 live seeded tips, **0 of 30 genuine tips falsely quarantined** and emergencies **2/2** urgent. **Live misses and the fix:** before #128, injections **3/4** and spam **1/4** quarantined; after rules for those four shapes, **4/4** and **4/4**. That after-number is **not independent recall**, because those four misses shaped the rules (and the labels beyond the four were inferred from the text). Tuned fixture set (153: 66 queries + 87 tips; the rules were tuned on it): route accuracy **1.000** (the old rules scored 0.871 on the first 147), injections **23/23**, emergencies **8/8**. Re-run on a fresh clone in WS5-08 part 2. Sources: `logs/feature_scout_intent.txt`, PR #128. |

World Model, H-MEM and Markovian run as the vendored TypeScript references in a local sidecar (`engines-ts/`), so the official suites run unchanged. Python ports of the same algorithms are the default in-process backend, and a parity test checks that the two backends agree. CI runs the conformance suites and the feature tests on both backends on every PR. Details: [engg/docs/ENGINES.md](engg/docs/ENGINES.md).

## Sponsor technology

| Sponsor | How Nexus uses it |
|---|---|
| **Zetaris** (data layer) | Federates three kinds of source (Postgres and REST feeds read live, files staged in its file store): <ul><li>**Supabase Postgres** (`sb`), read as a read-only role: 17 tables plus 5 datasource views. Tips are exposed only as `tips_v`, a view of safe columns.</li><li>**File sources** in Zetaris's internal file store: 8 CSV and 4 Parquet tables (legacy CCTNS exports and archive, ANPR cameras and reads, 112 calls, releases, history sheets).</li><li>**REST feeds served by the Nexus API**, as Lightning REST tables (`zetaris/40_feeds.sql`): weather, news and social, with the view `v_news_mentions` that `q_news` reads.</li></ul>The semantic view `v_crime_unified` gives one shape over every crime record, and 8 data-quality views flag issues such as duplicate FIRs across stations. Agents run only registered named queries. The registry (`NAMED_QUERIES`) holds 18: **13 agent-facing + 4 system** (`q_ping` health check, `q_dq_flags_all`, `q_dq_summary`, `q_source_counts`), plus `q_station_matrix`, registered but not called. Each has Lightning SQL and a DuckDB twin for sample mode. The 15 registered on 26 Oct all returned rows live on Zetaris. `q_dq_summary` counts the rows of each data-quality rule view for the System page; it runs through `app.dq_status`, because Vercel can't reach Zetaris. |
| **Meterless Nightshift** (primary AI provider) | `services/api/app/adapters/nightshift.py` is the only model path. It uses Nightshift's OpenAI-compatible API on pinned lanes, never `meterless/auto`. Every call logs the lane, the pinned model, the model Nightshift reports back and a receipt id. |
| **Meterless engines** | All four, as above. |
| **NVIDIA Nemotron** | `fast` = `nvidia/nemotron-3.5-lightning-30b-a3b` and `reason` = `nvidia/nemotron-3-ultra-550b-a55b`, both through Nightshift. The model is named on every trace line. |

Full text: [engg/docs/submission/SPONSOR_TECH_FINAL.md](engg/docs/submission/SPONSOR_TECH_FINAL.md).

## Setup

You need Python 3.11 or newer (3.13 tested on Windows), Git, and Docker Desktop (for the container path). Live mode also needs Zetaris and Meterless Nightshift running locally. Install both by following the **Participant Setup Guide** in the HackOS Resource Center: <https://hackathon.genai.works/resources>. The guide sits behind the HackOS login, so you need a HackOS account to open it. The Zetaris guides are at <https://zetaris.github.io/getting-started> and Nightshift is at <https://meterless.ai>.

### Option A: Docker (the judge path)

```bash
git clone https://github.com/HudrTechLLC/nexus-chennai.git && cd nexus-chennai
docker build -t oah-submission .
docker run --rm -p 8000:8000 -e SAMPLE_MODE=true oah-submission     # no credentials needed
curl http://localhost:8000/health
```

For live mode, copy `.env.example` to `.env`, fill it in, and run `docker compose up`. That starts the API on `:8000` and the web app on `:3001` (the same Next.js app as the Vercel deployment; server secrets stay out of the web container). Compose points the API at Zetaris (`:8888`) and Nightshift (`:8088`) on your machine through `host.docker.internal`.

### Option B: Python virtual environment

macOS / Linux (bash):

```bash
git clone https://github.com/HudrTechLLC/nexus-chennai.git && cd nexus-chennai
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
SAMPLE_MODE=true .venv/bin/python run.py           # serves on http://127.0.0.1:8000
```

Windows (PowerShell):

```powershell
git clone https://github.com/HudrTechLLC/nexus-chennai.git; cd nexus-chennai
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
$env:SAMPLE_MODE = "true"
.venv\Scripts\python run.py                        # serves on http://127.0.0.1:8000
```

The install takes a few minutes. On Windows it includes `tzdata`, because Windows Python has no time-zone database of its own.

`run.py` sets its own import path, so no `PYTHONPATH` is needed.

### Live configuration

Copy `.env.example` to `.env` and set these:

- **Zetaris:** `ZETARIS_REST_URL` (default `http://localhost:8888/api/v1.0`) and `ZETARIS_ORG_ID`. For the API key, set either `ZETARIS_API_KEY` or `ZETARIS_API_KEY_FILE` (a path to a file holding it; preferred).
- **Nightshift:** `METERLESS_BASE_URL` (default `http://127.0.0.1:8088/v1`). For the runtime token, **either** export `METERLESS_RUNTIME_TOKEN` in your shell (a `.env` file doesn't export it for other tools) **or** set `METERLESS_RUNTIME_TOKEN_FILE` to the token file Nightshift writes itself (on Windows, `%LOCALAPPDATA%/ai.meterless.runtime/proxy-token`). Lanes: `LANE_FAST`, `LANE_REASON` and `LANE_VISION` (images need a vision lane seated in Nightshift: see the next item). Pin exact `nvidia/*` ids; `meterless/auto` is refused.
- **Vision (live mode only; never needed for the judge path):** Nightshift serves images only from a seated vision lane. Enabling the model in the catalogue is not enough. In Nightshift 1.2.7: LANES → Lanes & memory → + Add lane → Vision → "Analyze images" → Find a model → Where it runs: Cloud model → "Nemotron 3.5 Super VL (Free)" (OpenRouter) → add **your own** OpenRouter key → Duty: RACE → Add lane. Requests keep naming `nvidia/nemotron-3.5-super-vl-120b-a12b`; `meterless/vision` does not route to this lane. Without it, the Extractor traces `vision_unavailable` and uses the officer's caption (D-036).
- **Supabase:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY_FILE` for the worker.
- **Your own Zetaris, no Supabase:** `python -m data.setup_live` generates the dataset and loads it into your local Zetaris, then run the API with `ZETARIS_DATA=files`. Steps and options: [data/README.md §5](data/README.md#5-live-mode-on-your-own-zetaris-no-supabase). Agent reads then need only Zetaris and Nightshift, and `/run` can keep its results in local files (`NEXUS_STORE=local`, #273). The police console and the worker still use Supabase.
- **REST feeds:** Zetaris fetches its REST feeds (`/mock-feeds/*`: weather, news, social) from the Nexus API, so start the API (`python run.py`) before a live run. If the API is down, runs still complete, just without feed evidence.
- **Engines:** `ENGINES_BACKEND=sample` (default, in-process) or `sidecar` (the TypeScript references: `cd engines-ts && npm ci && npm run install:references && npm run sidecar`).

## Run

```bash
# one input through the full graph, printed as JSON
python run.py --once input_examples/example_1.json

# or against the running API
curl -s -X POST http://localhost:8000/run -H "Content-Type: application/json" -d @input_examples/example_1.json
```

On Windows PowerShell, `curl` is an alias for `Invoke-WebRequest`, so call `curl.exe` instead (same arguments), or:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/run -ContentType "application/json" -InFile input_examples\example_1.json | ConvertTo-Json -Depth 8
```

`run.py --once` prints only the JSON result on stdout, so you can pipe it to `jq`. The trace lines go to stderr and to `logs/trace-<run_id>.jsonl`.

`POST /run` takes `{"run_id"?, "input": {"kind": "case" | "batch" | "tip" | "search", ...}, "options": {...}}` and returns `run_id`, `status`, `output` (`alerts`, `series`, `hotspots`, `summary`), `agents`, `engines`, `trace_id`, `log_file` and `execution_time_seconds`. Bad input returns a 422; it never returns a made-up answer.

Other routes: `POST /api/cases/{id}/process`, `POST /api/batch/link`, `POST /api/cases/{id}/public-draft`, `POST /api/series/{id}/dossier`, `POST /api/briefing`, `GET /api/traces/{run_id}`.

**Workers.** The console on Vercel writes to Supabase, and two processes on the laptop pick the work up. Run exactly **one** main worker. A second Ask worker would be safe, because it claims each question atomically, but there's no point running one.
- **Main worker**, `python -m app.worker`: analyst decisions, new tips, new cases, and new source onboarding (`/console/system/sources/onboard`, WS1-23). Its other queues, such as decisions and tips, are not claimed atomically, which is why only one may run.
- **Ask worker**, `python -m app.ask_worker`: answers Ask Nexus questions (`/console/ask`; see [ASK_NEXUS](engg/docs/ASK_NEXUS.md)). Start it beside the main worker, with the same environment. Without it, questions stay queued.
- **`docker compose --profile worker up` starts only the main worker.** It does not start the Ask worker, so run `python -m app.ask_worker` separately.
- **Onboarding staging needs the main worker on the host.** Each uploaded export is copied into the Zetaris driver container with `docker cp` (`ZETARIS_DRIVER_CONTAINER`, default `zetaris-driver-1`). The compose worker container has no Docker access, so it can't stage onboarding uploads: a run there ends as `failed`. Onboarding also needs live Zetaris. The column mapping comes from the Nightshift fast lane; without it, the worker maps by header rules and labels the run `rules`. The sample export is in the repo (`data/onboarding/sample_new_station.csv`).

## Sample mode vs live

| | Sample mode (`SAMPLE_MODE=true`) | Live |
|---|---|---|
| Data | Each named query runs as its DuckDB twin over `data/sample/` | Zetaris runs the named query over the federated sources |
| Models | Replays model output **recorded from live Nightshift calls** (`data/sample/model_fixtures/`); trace lines say `replayed` | Nightshift on pinned Nemotron lanes |
| Agents, scoring, Skeptic | the same code | the same code |
| Missing recording | A documented fallback runs and is traced (default plan, code-written reasons, code-only Skeptic verdict). It never invents an answer | — |
| Engines | in-process | in-process or the TypeScript sidecar; state written to Supabase with `ENGINES_PERSIST=supabase` |

Fixtures replay only when Nightshift can't be reached, and they are never keyed to an example id, so different inputs give different outputs. The committed sample bundle (`data/sample/`, see its `MANIFEST.json`) holds 1,275 synthetic crimes around the three judge series, 276 extracted feature rows, 1,895 statements, 689 crime-vehicle rows and 40 tips. A fresh clone with no `.env` and Zetaris and Nightshift unreachable runs all three judge cases end to end. 30 recorded model replies are committed (`data/sample/model_fixtures/`); where no fixture matches a request, the alert carries a code-written reason ("model rationale unavailable") instead of model text.

**The judge path runs fully offline:** the sample-mode container answers all three examples with `--network none` (no network at all) and matches `output_examples/` (CI job `judge-offline`, on every push to main; validated at `b407bd8`).

## Examples

`input_examples/` holds three judge inputs, and `output_examples/` holds the real output of each, made with the pinned Nightshift models. `example_1` was recorded live on 26 Oct; `example_2` and `example_3` were regenerated on 27 Oct by replaying their live-recorded model replies on the current code (the send-back fix, #358), so their times are replay times. Their links, scores, bands, verdicts and series did not change (`input_examples/README.md`). In sample mode the same calls are replayed from `data/sample/model_fixtures/`, so a fresh clone with no credentials gives the same result:

```bash
SAMPLE_MODE=true .venv/bin/python run.py --once input_examples/example_1.json
```

```powershell
$env:SAMPLE_MODE = "true"; .venv\Scripts\python run.py --once input_examples\example_1.json
```

| Input | What it is | Result (fresh clone, sample mode, no credentials) |
|---|---|---|
| `example_1.json`: case CHN-AD-2026-001182 | Chain snatching on LB Road, Adyar (the Red Pulsar hero case) | 3 links, all cross-station: Adyar ↔ Thiruvanmiyur (CHN-TI-2026-001148) **high, 0.819**; Adyar ↔ Velachery (CHN-VL-2026-000877) **high, 0.789**; Adyar ↔ Thiruvanmiyur (CHN-TI-2026-001134) medium, 0.692. Series "Red two-wheeler chain snatchings · 3 stations" (4 cases) |
| `example_2.json`: case CHN-KU-2025-000078 | Night house break with a grille cutter, Pongal week 2025 | 7 links (6 cross-station), all **medium**: only 3–4 of the 9 factors have data, so the coverage cap holds the band at medium even for high scores (up to 0.963). Series "Night house breaks · 6 stations" (8 cases) |
| `example_3.json`: batch of 3 night robberies | Fake cab, knife, white Swift Dzire | 2 cross-station links, medium (0.732, 0.632). **The Skeptic drops one pair** (CHN-GU-2025-000945 ↔ CHN-VL-2025-000926: different crime types, 4.1 km apart, day vs night), so no alert is written for it |

Each run also writes `logs/trace-<run_id>.jsonl`. In sample mode every model step shows `replayed`, with the recorded model id.

## Traces and logs

Every run writes `logs/trace-<run_id>.jsonl` and echoes each line to stdout. Each line records the agent, the action, the model lane, the pinned model, the model Nightshift reports, the receipt id, the Zetaris query ids, the engine, confidence, retries and status. Receipt id means a `meterless-receipt` header if Nightshift sends one, otherwise a receipt field, otherwise the response id. The same events are copied (with redaction) to Supabase `trace_events`, and the console trace viewer at `/console/system/trace/<run_id>` shows them. Engine evidence is under `logs/`: `conformance_*.txt` and `feature_scout_intent.txt`.

**Receipts verified.** 190 of 193 traced model calls carry a Nightshift receipt, and all 190 signatures verify (Ed25519, one key, fingerprint `c9f71fd6…`); the other 3 calls failed with no reply. 30/30 replayed fixture receipts also verify. Signatures verify against the receipt's embedded Ed25519 key, and every receipt uses the same key (sha256 fingerprint `c9f71fd60dad62bbcb260065a6c4be439dc4997b65785a0e083541b4061c7865`; the runtime's `/v1/meterless/receipts` serves the same key). The replayed fixtures keep synthetic prompt previews inside their signed bodies. Re-run: `python scripts/verify_receipts.py` (needs the Supabase URL and a service-role key file; result in `logs/receipts_verification.json`, #363).

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

`python -m app.eval` compares the linker against a rules-only baseline (same category, ≤ 2 km, ≤ 14 days) on the planted ground truth. It runs with empty memory (H-MEM) and makes no model calls: models only explain. The report is `output_examples/eval_report.json`.

| | Precision | Recall | F1 |
|---|---|---|---|
| **Nexus agents** | **0.59** | **0.86** | **0.70** |
| Rules-only baseline | 0.09 | 0.30 | 0.13 |

- 60 synthetic truth cases, 98 planted true pairs.
- **HIGH-band alerts were correct 10 of 10 times.** MEDIUM-band alerts were correct 56% of the time (74 of 132 scored pairs; 138 medium alerts, including 6 flagged duplicates that are neither right nor wrong; about one false medium alert per case evaluated). They are leads that need the analyst's decision, which is why every alert has a human gate.
- Only 13 of the 60 cases had model-extracted MO features when the report was made; the other 47 were scored without them.
- **Series purity is 0.35** (mean over 10 predicted series, `eval_report.json`): on average about a third of a proposed series belongs to its main planted series. Series are proposals an analyst reviews, never verdicts.
- **Live spot-check (separate from the headline):** 20 cases on live Zetaris and the QA database, default MO mode, code-only scoring, 0 model calls: **precision 0.61 / recall 0.64 / F1 0.62** (code `de8e666`, before #313; `output_examples/live_spot_off.json`). It is not like-for-like with the sample eval: 20 live cases vs 60 sample cases, a different truth set (the live seed's generated truth vs `data/sample/_truth`), and a larger candidate pool (about 14,000 live crimes plus legacy rows vs the 1,275-crime sample). Precision is close (0.61 vs 0.59); the recall gap (0.64 vs 0.86) is not yet explained.
- **Nemotron Ultra alone (pre-registered baseline, #366/#405):** the same 20 headline cases, synthetic data, 182 candidate pairs shown and 178 scored (4 truth-duplicate pairs excluded, as in the headline; 14 true links). On the pairs it is shown, Ultra alone scores a higher F1 than the pipeline (**0.80 vs 0.69**; the 0.69 is the full system on these same pairs, not the 60-case 0.70), but the difference is not significant (paired McNemar p = 0.55 over all disagreements, 7 vs 4; p = 0.25 on true links only, 3 vs 0). We don't claim the agents judge a pair better than the model. The pipeline's advantage is cost and coverage: it scores every candidate with 0 model calls (about 0.83 s per case), while Ultra needed about 3.4 min per case for about 9 pairs, and covering all 5,750 candidate pairs that way would take roughly 26 h. Under this experiment's 10-pairs-per-case budget the model reached 14 of the 49 true links; the system's alerts cover 41 (`output_examples/nemotron_alone.json`, `engg/docs/eval/NEMOTRON_ALONE_RESULTS.md`).
- Two similar-MO variants were trialled and left off: a feature cosine without IDF (more false positives) and a fixed-IDF TF-IDF (no change on this set).

Reproduce from a fresh clone (after Setup, a few minutes):

```bash
cd services/api && SAMPLE_MODE=true python -m app.eval --truth ../../data/sample/_truth --mo-cosine all
```


## Limitations

**Known limitations, in numbers:**

| Limitation | Number | Source |
|---|---|---|
| Synthetic data, no trial with real officers | about 14,000 synthetic crimes (14,040 in the QA database on 26 Oct); 0 real cases; no field trial | `data/README.md`; [Evaluation](#evaluation) is on planted truth |
| The Skeptic does not catch look-alike false links | Planted false-link test (pre-registered, #370/#392): the Skeptic dropped **0 of 24** planted near-miss false links (8 twin pairs × 3 plants, so not 24 independent trials). It sent 10 back and approved 14. In an exploratory hand reading (not pre-registered; two readers agree), its critique named the planted fact in 19 of 24 but still dropped none. **Inferred, not run:** under the revision cap (#358), a sent-back pair that re-scores the same ends approved, so in production these would likely become approved alerts. The Skeptic is a second opinion; the officer decides. **Since ~07:20 IST on 27 Oct** (#422, live on new runs only; existing alerts untouched), a deterministic contradiction check runs in the Skeptic. On a fresh pre-registered planted set it dropped 24/24 planted false links with 0/8 twin false-drops. That passes by construction on generator data (the rule targets the same four plant kinds). The only non-planted evidence is an offline what-if on the sample linking eval: 9 false alerts dropped, 0 true links lost (precision 0.59 → 0.63, recall unchanged). The published eval numbers do not include it. The model critique's 0/24 above stands as published. **One real-data signal (read-only, nexus-3, 27 Oct):** checked against the 27 live alert pairs, the rule would flag 2. One is LA-2026-266EFBCEEBBE, which an analyst had already rejected as different offenders (the rule agrees with the human call); the other is the test-derived LA-2026-3C71799A1C7A. Existing alerts are never re-reviewed. **Independent look-alike test (pre-registered, hand-written, not from the generator; rule only, offline, no model critique):** **FAIL** on both numbers, as predicted. It dropped 10 of 24 look-alike false links: 8 of 8 where the difference sits in the rule's fields in a form it parses, 2 of 8 where it is worded as an extractor might (ages or counts in words are not read), and 0 of 8 where the difference lies outside its fields (time, weapon, target, approach). It wrongly dropped 2 of 8 true twins, both where witnesses disagree (ages 25 vs 38; red vs maroon), and 0 of 6 clean twins. So the 24/24 shows the rule working on the generator's plants, not general catching of false links | `output_examples/planted_skeptic.json` (run `planted_a329010d`); `engg/docs/eval/PLANTED_SKEPTIC_PREREG.md` (Results); `engg/docs/eval/SKEPTIC_CONTRADICTION_PREREG.md` (Results); `output_examples/skeptic_contradiction.json`; `engg/docs/eval/INDEPENDENT_LOOKALIKE_PREREG.md` (Results); `engg/docs/eval/independent_lookalike_results.json` |
| Medium alerts are leads, not answers | MEDIUM band correct **56%** (74 of 132 scored pairs); HIGH 10 of 10 | `output_examples/eval_report.json` |
| Live Zetaris REST returns values as text | Live Zetaris REST returns values as text; coerced at the adapter since #430, after one live crash (take A's first run `run_2743a75c`, 27 Oct: `q_offender_return.mo_overlap` arrived as a string). The re-run `run_0a2af3e9` succeeded; the failed run is kept as a record. Sample mode was not affected. The crash is **fixed**. What remains: other live columns that nothing reads as numbers or flags today (`q_news` hours_after / category_hint, `q_calls_near` km / minutes, `q_tip` tags) still arrive as text and are not typed yet; that audit is after recording | #430 (`c6af812`); nexus-3 |
| Live runs are slow on the reasoning model | A single filed FIR reaches its alert in **~4.6 min** live (about 278 s: 12 s worker pickup, 37 s extraction including the live vision call, 229 s case run `run_caea00c0` on main `71fac4c`, no deadline hit). Before the send-back fix (#358) the same FIR took about 8 min and ended `needs_revision`. The live recordings on 26 Oct took 4–17 min per example (236 / 1,046 / 315 s), before the fix; a 4-case live batch took ~59 min. The judge path replays in seconds | nexus-3's `run_caea00c0` (27 Oct); `output_examples/example_1.json`; nexus-3's `run_866f913f` |
| Image reading is verified in one live run so far | Nightshift serves image requests on `nvidia/nemotron-3.5-super-vl-120b-a12b` through a cloud vision lane (OpenRouter free route, rate-limited; the key is held only in Nightshift; D-036). Verified in a live Nexus run: run `reextract_vis_1793040194` (27 Oct): an Extractor `model_call` on lane `vision`, model `nvidia/nemotron-3.5-super-vl-120b-a12b`, receipt `chatcmpl-5dfe68c6-80f5-4c50-8962-d45f726a7cb4`, status ok, 24 s; the extracted features had no `degraded` entries and carried `visual_tags` read from the still. The free route can refuse or rate-limit, so a given run may still fall back to the caption. The judge path and sample mode still trace `vision_unavailable` and use the caption: they run offline, and the recorded fixtures hold no vision call | D-036; D-021 |
| The worker needs Supabase | `/run` can store results locally (`NEXUS_STORE=local`, #273); the worker and the police console use Supabase only | `services/api/app/graph/local_store.py`; [PATH2](engg/docs/PATH2.md) |
| A Zetaris query-pushdown bug is worked around, not fixed | Every named query and data-quality view orders rows before the limit; a `zetaris_result_truncated` event fires whenever rows = limit | D-031 (`engg/docs/DECISIONS.md`) |
| Live data-quality flags come from a snapshot | Live data-quality flags come from a snapshot taken by the last data-quality pass (`app.dq_status`, as of the time shown in each run's trace). A FIR filed after that pass shows no flags until the next pass. The lookup takes about 1 s (in `run_caea00c0`: `q_dq_flags` ok, 883 ms) | #348 (migration 0007_14); nexus-1's live timings; `run_caea00c0` |

Details:

- **Synthetic data.** All crime, person, vehicle, call, tip, statement, evidence, news and social data is generated for this hackathon. Any quality number is measured on planted structure, not on real police data. The only real data is public reference data: map places, ward boundaries, the station list and weather (see [data/README.md](data/README.md)).
- **Audio statements are not read by a model, and image reading is new.** The Extractor has both paths wired: an audio lane would transcribe recordings, and the vision lane tags what a photo shows. Vision runs as a Nightshift cloud lane routed to Nemotron 3.5 Super VL through OpenRouter's free route (D-036): verified in one live run, rate-limited.
  - No audio model is pinned on our Nightshift, so audio statements use the transcript recorded with them.
  - **Vision:** until 26 Oct, Nightshift refused every image request (`no_vision_model`) because no vision lane was seated. Nightshift now serves image requests on `nvidia/nemotron-3.5-super-vl-120b-a12b` through a cloud vision lane (OpenRouter free route, rate-limited; the key is held only in Nightshift). Verified by a direct Nightshift test on 27 Oct (a red test image answered "Red"; D-036). Verified in a live Nexus run: run `reextract_vis_1793040194` (27 Oct): an Extractor `model_call` on lane `vision`, model `nvidia/nemotron-3.5-super-vl-120b-a12b`, receipt `chatcmpl-5dfe68c6-80f5-4c50-8962-d45f726a7cb4`, status ok, 24 s; the extracted features had no `degraded` entries and carried `visual_tags` read from the still. In sample mode and on the judge path, photos keep the officer's caption and any tags already on record. If the free route refuses or rate-limits a request, the Extractor traces `vision_unavailable` and uses the caption.
  - Neither case is hidden or made up. Each shows in the trace as a `degraded` step (`audio_fallback`, `vision_unavailable`) with no model receipt, and the extracted record lists it under `degraded`.
  - The rest of the case (narrative, typed statements, vehicles, forensics) is extracted and linked as normal. The same code uses an audio model once Nightshift serves one.
- **Reasoning model.** The spec planned Nemotron Super 120B, but our key isn't served it, so the `reason` lane runs Nemotron Ultra 550B. It is slower, so the run deadline keeps a 45-second reserve.
- **Zetaris and Supabase Storage (S3) TLS.** Zetaris's S3 client can't complete a TLS handshake with Supabase Storage's S3 endpoint. CSV and Parquet files therefore go into Zetaris's own internal file store instead, still registered as file sources. The fix is documented in `zetaris/README.md`. We didn't apply it because it means restarting Zetaris mid-build.
- **Tip passphrases use bcrypt, not Argon2id.** The spec said Argon2id. We hash with pgcrypto bcrypt inside Postgres so the hash never leaves the database. Tip codes are random and attempts are limited.
- **Explanations are model-written** and can be imperfect. Numbers can't be, because code computes them. The Skeptic re-checks pairs against fresh rows, but it does not reliably catch look-alike false links (Known limitations).
- **Hotspots** use a Poisson test against each cell's own recent history. They flag concentrations, not causes.
- **News corroboration can lower a score.** A single corroborating news item can lower a strong pair's renormalised score (on the sample, the hero pair would fall from 0.787 to 0.752). Corroborating news roundups are therefore off (`ROUNDUPS = False` in `services/api/app/feeds_gen.py`) until a positive-only rule is adopted. That rule was evaluated on the full sample and is not merged; scoring is unchanged for the freeze (D-032).
- **Live news is a small synthetic slice.** Live news uses the committed synthetic slice (47 articles), placed to match one crime each in the 1,275-crime sample. Against the full live crime set, 5 articles also match two or more same-category crimes, so they can add corroboration to those pairs (none on the judge path) until the post-freeze full feed generator guards against every live crime.
- **CCTV stills are synthetic renders.** The stills on the judge-series cases are generated frames (street, vehicle silhouette, faceless figures, a SYNTHETIC stamp), not real footage. They were seeded with no vision tags (`vision=null`), because they were rendered before the vision lane worked (D-036).
- **Appeal stills are blurred, not detected.** Appeal stills are anonymised by a whole-image heavy blur (shrink to 48 px, re-encode with no metadata), not by face or plate detection. The app path always blurs, and a database check ties every published still to its own case. But an officer with write access to a case could still upload an unblurred image directly via the storage API. Future fix: worker-side blur with face detection (OpenCV) and a service-role-only writer.

## Responsible AI

- **Human gate.** Nexus suggests; people decide. An analyst decides every link, and an officer publishes every public appeal. Rejected alerts stay visible to all police roles.
- **Explanations.** Every alert shows each factor's score, a plain reason and the Zetaris query and row behind it, plus the Skeptic's verdict and any memory applied.
- **Tips are untrusted.** Tip Guard screens every tip and fails closed. Agents read only the redacted text of tips that passed. Zetaris sees tips only through a view of safe columns.
- **Public privacy.** The public map uses fuzzed hex cells with a minimum-count cutoff. Tip photos have their EXIF metadata stripped.
- **Where images go.** The vision lane is a third-party route: Nightshift sends the image to Super VL through OpenRouter. That is acceptable for this project's synthetic stills. Real evidence would need a vision lane that does not leave the force's own infrastructure.
- **Protected attributes** (religion, caste, community) are never used for scoring or written into public text.
- **No real personal or crime data.** Every person, case and tip is synthetic. The real data used is public reference data only: map places, ward boundaries, station names and weather.

## Live app

The web app is deployed on Vercel at <https://nexus-chennai.vercel.app>. It reads from Supabase, so it shows the shared synthetic dataset, not your local run.

Demo police accounts (station officer, analyst, supervisor) are provided to judges in the submission form. The sign-in page shows the demo accounts as one row of tiles (#431, #437): one click signs in as station officer, analyst or supervisor. The admin tile fills the email only; the admin password is not shared.

**What the police console does** (beyond alerts and the map):
- **Case file:** narrative and statements, with phone and Aadhaar numbers masked; vehicles; an evidence gallery; the MO that Nemotron extracted, with officer corrections stored separately; linked alerts, series, similar cases and the World Model graph; case diary and status.
- **Evidence (with a limit):** stored with its original bytes. The upload route computes sha256 server-side; the database enforces that the evidence row matches a storage object the caller uploaded (owner, size, mime) and sets uploaded_by + custody itself; the hash itself is not re-verified in the database. A check confirms each stored file equals its recorded hash (`apps/web/scripts/evidence-check.mjs`). Do not read this as tamper-proof.
- **FIR form** (`/console/cases/new`): one atomic `file_fir` call saves the crime, vehicles and statements together, and the worker then picks the case up and extracts its MO.
- **Search:** one box for a case id, FIR number, plate fragment (`?` for an unread character) or free words, with facets (zone, weapon, MO or visual tag, time of day, linked). It lists every table it read, with row counts. Web search reads Supabase under row-level security, not Zetaris (D-029); agents still read only through Zetaris.
- **Privacy:** victims, witnesses and complainants are never named; lists show the ward, not the address; `audit_log` is append-only for every role (D-030).

| Area | Routes |
|---|---|
| **Public portal** (no sign-in) | `/` home · `/appeals` and `/appeals/<id>` public appeals · `/map` fuzzed crime map · `/cctv` · `/tip/new` → `/tip/sent` → `/tip/status` anonymous tips · `/about/privacy` |
| **Police console** (sign-in at `/console/login`) | `/console` overview · `/console/alerts` and `/console/alerts/<id>` link alerts · `/console/cases`, `/console/cases/<id>` (+ `/evidence`), `/console/cases/new` (FIR form) · `/console/search` · `/console/map` Pulse Map · `/console/series` and `/console/series/<id>` · `/console/stations` link matrix · `/console/memory` (H-MEM) · `/console/graph` (World Model) · `/console/tips` and `/console/tips/<id>` tip triage · `/console/appeals` · `/console/system` and `/console/system/trace/<run_id>` |
| **Engineering docs** | `/docs` (spec tabs) · `/docs/notes/<note>` · `/docs/progress` (build tracker) |

## Third-party code and pre-existing work

- **Meterless engines.** The World Model, H-MEM and Markovian TypeScript reference implementations and their conformance suites are vendored unmodified from github.com/Meterless/Meterless @ `1742dec56a66e58eef9dda2d2b865823758ca8cd` (Apache-2.0) in `engines-ts/` (see `engines-ts/NOTICE`). Scout Intent is implemented by Nexus from the Meterless Scout spec. The Python sample backends in `services/api/app/engines/*/core.py` are Nexus ports of the reference algorithms.
- **Pre-existing components:** only the vendored Meterless engines above. The repository and the product spec were written inside the build window (spec 23–26 Oct 2026). All crime, person, case and tip data is synthetic and was generated during the window; real public reference data (OpenStreetMap places, DataMeet ward boundaries, the public police-station list and live Open-Meteo weather) is listed with its licence in [data/README.md](data/README.md).
- **Open-source libraries:** FastAPI, Uvicorn, Pydantic, httpx, tenacity, DuckDB, PyYAML, h3 and LangGraph (Python); Next.js, React, Supabase JS, MapLibre GL, deck.gl and h3-js (web). Licences: see [Licences](#licences).

## Licences

Versions are pinned in `services/api/requirements*.txt` and `apps/web/package.json`. Licences are read from each package's own metadata.

**Data:** data sources, counts and licences: [data/README.md](data/README.md). Attribution: Map data © OpenStreetMap contributors (ODbL). Ward boundaries © DataMeet / Transparent Chennai (CC BY-SA 2.5 IN). Weather data by Open-Meteo.com (CC BY 4.0).

**Vendored code:** Meterless World Model, H-MEM and Markovian reference engines and conformance suites, vendored unmodified @ `1742dec5` (Apache-2.0); see `engines-ts/NOTICE` and `engines-ts/LICENSE`.

**Python, runtime** (`services/api/requirements.txt`)

| Package | Version | Licence |
|---|---|---|
| fastapi | 0.115.6 | MIT |
| uvicorn | 0.32.1 | BSD-3-Clause |
| pydantic | 2.10.4 | MIT |
| pydantic-settings | 2.7.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| tenacity | 9.0.0 | Apache-2.0 |
| duckdb | 1.1.3 | MIT |
| PyYAML | 6.0.2 | MIT |
| h3 | 4.5.0 | Apache-2.0 |
| langgraph | 1.2.17 | MIT |
| pytz | 2024.2 | MIT |
| tzdata | 2025.2 | Apache-2.0 |

**Python, development and tests** (`services/api/requirements-dev.txt`): pytest 8.3.4 (MIT), ruff 0.8.4 (MIT), psycopg 3.2.3 (LGPL-3.0), shapely 2.2.0 (BSD-3-Clause), pillow 10.4.0 (HPND).

**Web, runtime** (`apps/web/package.json`)

| Package | Version | Licence |
|---|---|---|
| next | 14.2.35 | MIT |
| react, react-dom | 18.3.1 | MIT |
| @supabase/supabase-js | 2.47.10 | MIT |
| @supabase/ssr | 0.6.1 | MIT |
| maplibre-gl | 4.7.1 | BSD-3-Clause |
| @deck.gl/core, extensions, geo-layers, layers, mapbox, mesh-layers | 9.1.15 | MIT |
| h3-js | 4.1.0 | Apache-2.0 |
| react-markdown | 9.0.1 | MIT |
| remark-gfm | 4.0.0 | MIT |
| rehype-slug | 6.0.0 | MIT |
| github-slugger | 2.0.0 | ISC |
| yaml | 2.6.1 | ISC |
| jpeg-js | 0.4.4 | BSD-3-Clause |
| pngjs | 7.0.0 | MIT |
| @tailwindcss/typography | 0.5.15 | MIT |
| server-only | 0.0.1 | MIT |
| lucide-react (icons) | 0.468.0 | ISC |
| Inter, JetBrains Mono (fonts, self-hosted at build by `next/font`) | Google Fonts | SIL OFL 1.1 |

**Web, development:** typescript 5 (Apache-2.0), eslint 8 and eslint-config-next 14.2.35, tailwindcss 3.4, postcss 8, vitest 2.1.9, @types/node, @types/react, @types/react-dom, @types/pngjs 6.0.5 (all MIT).

**Engines sidecar** (`engines-ts/package.json`, development): tsx 4.20.6 (MIT).

## AI and model usage

- Product model calls go only through Meterless Nightshift, on pinned NVIDIA Nemotron lanes.
- Claude Code (Anthropic) was used as a development tool. It is not in the product's request path.
- The demo narration voice was generated with ElevenLabs, which is not part of the running product.
- Cursor was not used.

## Docs

Everything else is in [engg/docs/](engg/docs/00-INDEX.md): spec, architecture, decisions, engines, agents and progress.
