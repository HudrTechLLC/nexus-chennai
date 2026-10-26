# Nexus Chennai

**Track 1 · Solving Fragmented Intelligence** · Open Agent Hackathon 2026 · team Heisenbugs

Each police station in a city sees only its own cases. A gang that snatches chains near one station on Monday and another on Friday looks like two unrelated robberies. Nexus is a set of agents that read the city's fragmented records through **Zetaris**, think with **NVIDIA Nemotron** through **Meterless Nightshift**, and raise *link alerts* for crimes that are probably related across stations. Each alert shows its score, the evidence for each reason and the Zetaris query behind it. A Skeptic agent re-checks every link against fresh rows before a human decides, and the human's decision teaches the system through the Meterless **H-MEM** engine.

> **All crime, person, case and tip data in this repository is synthetic** (`synthetic: true` on every such row). Map, ward, police-station and weather reference data is real public open data ([data/README.md](data/README.md)). No real people, cases or police systems are involved.

Demo video: `[PENDING: video link]` · Live app: <https://nexus-chennai.vercel.app> (see [Live app](#live-app))

**What linking finds.** In the live demo data, Nexus proposes one series that no single station's register shows: **"Red two-wheeler chain snatchings · 3 stations"**, 9 chain snatchings across Adyar, Thiruvanmiyur and Velachery. Its strongest cross-station pair, Adyar ↔ Velachery two days apart, shares a partial plate and the same red Bajaj Pulsar 150 and scores **high (0.789)**. The series and every alert in it are proposals: each waits for an analyst's decision. On the judge path (a fresh clone, sample data) the same series shows 4 cases (see [Examples](#examples)). All of it is planted synthetic data.

**What's new compared with established crime linkage.** Established linkage systems rely on structured case forms and analysts comparing cases by hand. Nexus instead:
- reads every source where it already lives (case files, legacy station exports, ANPR, 112 calls, tips, feeds) through Zetaris, with no central copy;
- has agents cite the Zetaris query and row behind every factor in an alert;
- has a Skeptic that re-queries the data itself and sends a pair back or drops it before a person sees it;
- feeds screened public tips back in as corroborating evidence on a link (the corroboration factor);
- learns from each analyst decision within a capped ±0.08 (H-MEM).

## Contents
[What it does](#what-it-does) · [Architecture](#architecture) · [Agents](#agents) · [Meterless engines](#meterless-engines) · [Sponsor technology](#sponsor-technology) · [Setup](#setup) · [Run](#run) · [Sample mode vs live](#sample-mode-vs-live) · [Examples](#examples) · [Traces and logs](#traces-and-logs) · [Tests](#tests) · [Evaluation](#evaluation) · [Limitations](#limitations) · [Responsible AI](#responsible-ai) · [Live app](#live-app) · [Third-party code and pre-existing work](#third-party-code-and-pre-existing-work) · [Licences](#licences) · [AI and model usage](#ai-and-model-usage)

## What it does

- **Links cases across stations.** For a new case, agents find candidate cases city-wide, score each pair on nine factors in code, and write an alert with per-factor evidence.
- **Checks its own work.** The Skeptic re-queries Zetaris itself, critiques each pair against its own rows, and can send a pair back for a narrower search or drop it.
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

Caps: the Planner runs at most 3 rounds, the Skeptic sends back at most 2 times, and a run has a 300-second deadline. With under 45 seconds left, model calls are skipped and the code results stand.

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

| Engine | What it does in Nexus | Test evidence |
|---|---|---|
| **World Model** | One canonical entity per real-world thing (plate, person, phone, place, FIR), with stable ids and provenance, so agents agree on what a fact refers to | Official conformance **8/8** (`logs/conformance_world_model.txt`) + E4 feature tests |
| **H-MEM** | Turns analyst decisions into memories that shift a similar pair's score by at most ±0.08; every step goes to an append-only trust ledger | Official conformance **13/13** (`logs/conformance_hmem.txt`) + E4 feature tests |
| **Markovian** | Reads a whole series in bounded chunks with a capped carryover for the dossier; logs projected vs actual tokens | Official conformance **8/8** (`logs/conformance_markovian.txt`) + E4 feature tests |
| **Scout Intent** | Routes analyst searches; Tip Guard quarantines injection, threats, abuse and spam in public tips and flags emergencies | **Independent:** held-out 40 (never tuned on): route accuracy **0.950**, injections **7/7**, 0 false quarantines. On the 40 live seeded tips, **0 of 30 genuine tips falsely quarantined** and emergencies **2/2** urgent. **Live misses and the fix:** before #128, injections **3/4** and spam **1/4** quarantined; after rules for those four shapes, **4/4** and **4/4**. That after-number is **not independent recall**, because those four misses shaped the rules (and the labels beyond the four were inferred from the text). Tuned fixture set (147: 60 queries + 87 tips): route accuracy **1.000** (the old rules scored 0.871 on it), injections **23/23**. Sources: `logs/feature_scout_intent.txt`, PR #128. |

World Model, H-MEM and Markovian run as the vendored TypeScript references in a local sidecar (`engines-ts/`), so the official suites run unchanged. Python ports of the same algorithms are the default in-process backend, and a parity test checks that the two backends agree. CI runs the conformance suites and the feature tests on both backends on every PR. Details: [engg/docs/ENGINES.md](engg/docs/ENGINES.md).

## Sponsor technology

| Sponsor | How Nexus uses it |
|---|---|
| **Zetaris** (data layer) | Federates three kinds of source in place: <ul><li>**Supabase Postgres** (`sb`), read as a read-only role: 17 tables plus 5 datasource views. Tips are exposed only as `tips_v`, a view of safe columns.</li><li>**File sources** in Zetaris's internal file store: 8 CSV and 4 Parquet tables (legacy CCTNS exports and archive, ANPR cameras and reads, 112 calls, releases, history sheets).</li><li>**REST feeds served by the Nexus API**, as Lightning REST tables (`zetaris/40_feeds.sql`): weather, news and social, with the view `v_news_mentions` that `q_news` reads.</li></ul>The semantic view `v_crime_unified` gives one shape over every crime record, and 8 data-quality views flag issues such as duplicate FIRs across stations. Agents run only registered named queries: 15 named queries (plus the health check `q_ping`), each with Lightning SQL and a DuckDB twin for sample mode. All 15 return rows live on Zetaris (26 Oct). `q_dq_summary` counts the rows of each data-quality rule view for the System page; it runs through `app.dq_status`, because Vercel can't reach Zetaris. |
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
- **Nightshift:** `METERLESS_BASE_URL` (default `http://127.0.0.1:8088/v1`). For the runtime token, **either** export `METERLESS_RUNTIME_TOKEN` in your shell (a `.env` file doesn't export it for other tools) **or** set `METERLESS_RUNTIME_TOKEN_FILE` to the token file Nightshift writes itself (on Windows, `%LOCALAPPDATA%/ai.meterless.runtime/proxy-token`). Lanes: `LANE_FAST`, `LANE_REASON` (and `LANE_VISION`, see [Limitations](#limitations)). Pin exact `nvidia/*` ids; `meterless/auto` is refused.
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

Other routes: `POST /api/cases/{id}/process`, `POST /api/batch/link`, `POST /api/cases/{id}/public-draft`, `POST /api/series/{id}/dossier`, `POST /api/briefing`, `GET /api/traces/{run_id}`. The worker (`python -m app.worker`, or `docker compose --profile worker up`) handles analyst decisions, new tips and new cases.

## Sample mode vs live

| | Sample mode (`SAMPLE_MODE=true`) | Live |
|---|---|---|
| Data | Each named query runs as its DuckDB twin over `data/sample/` | Zetaris runs the named query over the federated sources |
| Models | Replays model output **recorded from live Nightshift calls** (`data/sample/model_fixtures/`); trace lines say `replayed` | Nightshift on pinned Nemotron lanes |
| Agents, scoring, Skeptic | the same code | the same code |
| Missing recording | A documented fallback runs and is traced (default plan, code-written reasons, code-only Skeptic verdict). It never invents an answer | — |
| Engines | in-process | in-process or the TypeScript sidecar; state written to Supabase with `ENGINES_PERSIST=supabase` |

Fixtures replay only when Nightshift can't be reached, and they are never keyed to an example id, so different inputs give different outputs. The committed sample bundle (`data/sample/`, see its `MANIFEST.json`) holds 759 synthetic crimes around the three judge series, 172 extracted feature rows, 1,108 statements, 373 vehicles and 40 tips. A fresh clone with no `.env` and Zetaris and Nightshift unreachable runs all three judge cases end to end. Until recorded model replies are committed, alerts carry code-written reasons ("model rationale unavailable") instead of model text.

**The judge path runs fully offline:** the sample-mode container answers all three examples with `--network none` (no network at all) and matches `output_examples/` (CI job `judge-offline`, on every push to main; validated at `b407bd8`).

## Examples

`input_examples/` holds three judge inputs, and `output_examples/` holds the real output of each, recorded with the pinned Nightshift models. In sample mode the same calls are replayed from `data/sample/model_fixtures/`, so a fresh clone with no credentials gives the same result:

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
| Medium alerts are leads, not answers | MEDIUM band correct **56%** (74 of 132 scored pairs); HIGH 10 of 10 | `output_examples/eval_report.json` |
| Live runs are slow on the reasoning model | **4–17 min** per recorded example (236 / 1,046 / 315 s); a 4-case live batch took ~59 min, and one case hit the 60-min run deadline in its own planning round. The judge path replays the same calls in **7–12 s** | `output_examples/*.json` `execution_time_seconds`; nexus-3's `run_866f913f`; fresh-clone run |
| Images are not read by a model | 0 vision tags: Nightshift 1.2.7 refuses images (`no_vision_model`); the officer's caption is used, and each is traced `vision_unavailable` | trace steps; D-021 |
| The worker needs Supabase | `/run` can store results locally (`NEXUS_STORE=local`, #273); the worker and the police console use Supabase only | `services/api/app/graph/local_store.py`; [PATH2](engg/docs/PATH2.md) |
| A Zetaris query-pushdown bug is worked around, not fixed | Every named query and data-quality view orders rows before the limit; a `zetaris_result_truncated` event fires whenever rows = limit | D-031 (`engg/docs/DECISIONS.md`) |

Details:

- **Synthetic data.** All crime, person, vehicle, call, tip, statement, evidence, news and social data is generated for this hackathon. Any quality number is measured on planted structure, not on real police data. The only real data is public reference data: map places, ward boundaries, the station list and weather (see [data/README.md](data/README.md)).
- **Audio statements and evidence photos are not read by a model yet.** The Extractor has both paths wired: an audio lane would transcribe recordings, and the vision lane (Nemotron Super VL, pinned by default) would tag what a photo shows.
  - No audio model is pinned on our Nightshift, so audio statements use the transcript recorded with them.
  - The Nightshift build we run (1.2.7) refuses every image request (`no_vision_model`, reported to Meterless), so photos get no new vision tags. They keep the officer's caption and any tags already on record.
  - Neither case is hidden or made up. Each shows in the trace as a `degraded` step (`audio_fallback`, `vision_unavailable`) with no model receipt, and the extracted record lists it under `degraded`.
  - The rest of the case (narrative, typed statements, vehicles, forensics) is extracted and linked as normal. Once Nightshift serves these models, the same code uses them with no change.
- **Reasoning model.** The spec planned Nemotron Super 120B, but our key isn't served it, so the `reason` lane runs Nemotron Ultra 550B. It is slower, so the run deadline keeps a 45-second reserve.
- **Zetaris and Supabase Storage (S3) TLS.** Zetaris's S3 client can't complete a TLS handshake with Supabase Storage's S3 endpoint. CSV and Parquet files therefore go into Zetaris's own internal file store instead, still registered as file sources. The fix is documented in `zetaris/README.md`. We didn't apply it because it means restarting Zetaris mid-build.
- **Tip passphrases use bcrypt, not Argon2id.** The spec said Argon2id. We hash with pgcrypto bcrypt inside Postgres so the hash never leaves the database. Tip codes are random and attempts are limited.
- **Explanations are model-written** and can be imperfect. Numbers can't be, because code computes them, and the Skeptic re-checks factors against fresh rows.
- **Hotspots** use a Poisson test against each cell's own recent history. They flag concentrations, not causes.
- **News corroboration can lower a score.** A single corroborating news item can lower a strong pair's renormalised score (on the sample, the hero pair would fall from 0.787 to 0.752). Corroborating news roundups are therefore off (`ROUNDUPS = False` in `services/api/app/feeds_gen.py`) until a positive-only rule is adopted. That rule was evaluated on the full sample and is not merged; scoring is unchanged for the freeze (D-032).
- **Live news is a small synthetic slice.** Live news uses the committed synthetic slice (47 articles), placed to match one crime each in the 1,275-crime sample. Against the full live crime set, 5 articles also match two or more same-category crimes, so they can add corroboration to those pairs (none on the judge path) until the post-freeze full feed generator guards against every live crime.
- **CCTV stills are synthetic renders.** The stills on the judge-series cases are generated frames (street, vehicle silhouette, faceless figures, a SYNTHETIC stamp), not real footage. They carry no vision tags, because our Nightshift refuses image requests.
- **Appeal stills are blurred, not detected.** Appeal stills are anonymised by a whole-image heavy blur (shrink to 48 px, re-encode with no metadata), not by face or plate detection. The app path always blurs, and a database check ties every published still to its own case. But an officer with write access to a case could still upload an unblurred image directly via the storage API. Future fix: worker-side blur with face detection (OpenCV) and a service-role-only writer.

## Responsible AI

- **Human gate.** Nexus suggests; people decide. An analyst decides every link, and an officer publishes every public appeal. Rejected alerts stay visible to all police roles.
- **Explanations.** Every alert shows each factor's score, a plain reason and the Zetaris query and row behind it, plus the Skeptic's verdict and any memory applied.
- **Tips are untrusted.** Tip Guard screens every tip and fails closed. Agents read only the redacted text of tips that passed. Zetaris sees tips only through a view of safe columns.
- **Public privacy.** The public map uses fuzzed hex cells with a minimum-count cutoff. Tip photos have their EXIF metadata stripped.
- **Protected attributes** (religion, caste, community) are never used for scoring or written into public text.
- **No real personal or crime data.** Every person, case and tip is synthetic. The real data used is public reference data only: map places, ward boundaries, station names and weather.

## Live app

The web app is deployed on Vercel at <https://nexus-chennai.vercel.app>. It reads from Supabase, so it shows the shared synthetic dataset, not your local run.

Demo police accounts (station officer, analyst, supervisor) are provided to judges in the submission form.

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

**Web, development:** typescript 5 (Apache-2.0), eslint 8 and eslint-config-next 14.2.35, tailwindcss 3.4, postcss 8, vitest 2.1.9, @types/node, @types/react, @types/react-dom, @types/pngjs 6.0.5 (all MIT).

**Engines sidecar** (`engines-ts/package.json`, development): tsx 4.20.6 (MIT).

## AI and model usage

- Product model calls go only through Meterless Nightshift, on pinned NVIDIA Nemotron lanes.
- Claude Code (Anthropic) was used as a development tool. It is not in the product's request path.
- The demo narration voice was generated with ElevenLabs, which is not part of the running product.
- Cursor was not used.

## Docs

Everything else is in [engg/docs/](engg/docs/00-INDEX.md): spec, architecture, decisions, engines, agents and progress.
