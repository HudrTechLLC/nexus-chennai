---
tags: [nexus, plan]
---

# Rules check: our plan against the official documents

Checked on 2026-10-26 against the four official HackOS documents: Official Rules, Submission Requirements, Disqualification Checklist and Participant Setup Guide. Where the documents differ, the **Official Rules apply**.
Related: [DIGEST](DIGEST.md) · [DELIVERABLES](../DELIVERABLES.md) · [LANES](../LANES.md) · [SPONSOR_TECH](../SPONSOR_TECH.md) · [00-INDEX](../00-INDEX.md)

> **The PDFs are not committed.** They are the organiser's material and the repo goes public at submission, so they stay local in this folder and are gitignored. This note quotes only what we need.

## Verdict

The plan meets every hard requirement. No spec change is needed. There are **five gaps**, all about the delivery process rather than scope. Each one has an owner and a task (below).

## Dates (UTC is binding)

| Item | Official | Our plan |
|---|---|---|
| Submissions close | 27 Oct 23:45 UTC (28 Oct 05:15 IST), hard | Submit by **27 Oct 23:15 IST**, which leaves 6 h spare ✅ |
| Advice on validation | "Run the full flow on day four" | Moved earlier: a first clean-clone dry run on **Mon 26 Oct** (WS5-11). The final L3 run stays Tue 15:00 IST |
| Roster | Locks when the first submission is *created* | Confirm the roster before creating the draft (WS5-10) |
| Updates | Allowed until the deadline | Create the draft early and update it |

## Hard requirements (missing any of these = disqualified)

| Requirement | Where we meet it | Status |
|---|---|---|
| Zetaris is the data layer, load-bearing | Every agent read goes through named Zetaris queries (R1; nexus-1, `adapters/zetaris.py`) | 🟡 adapter live; named queries landing |
| ≥ 1 Meterless Engine in a working feature, with a passing test | All four engines. World Model, H-MEM and Markovian pass the official conformance suites (8/8, 13/13, 8/8; PR #19). Scout Intent: 120 fixtures (WS2-08) | ✅ / 🟡 |
| Nightshift is the primary AI provider | Every model call goes through `NightshiftClient` with pinned lanes (R2, D-017) | ✅ |
| Demo video 1–4 min, slide deck, public repo + README, sponsor-tech text | WS5-03…07, WS5-09 | ⏳ |
| Pre-existing work declared | The repo started 26 Oct, inside the build window. Declare: Meterless engines vendored from upstream (Apache-2.0). The spec was written inside the window (23–26 Oct), so it is not pre-existing | ⏳ WS5-09 |
| One primary track | Track 1, Solving Fragmented Intelligence | ⏳ set on HackOS |

**Declarations for the submission form (draft):**
1. Meterless reference engines and conformance suites, vendored unmodified from github.com/Meterless/Meterless @ `1742dec5` (Apache-2.0), in `engines-ts/`.
2. ~~The product spec~~ **Not pre-existing.** The team confirmed the spec was first written on 23 Oct and completed on 26 Oct, both inside the build window, so it needs no declaration.
3. Standard open-source libraries (FastAPI, LangGraph, Next.js and others). They're listed in the README.
4. No real crime data. All crime, person, case and tip data is synthetic, generated during the build window and labelled `synthetic: true`. Public reference data is used with attribution: OpenStreetMap places (ODbL), DataMeet ward boundaries, the public police-station list and live Open-Meteo weather. Sources and licences are in `data/README.md`.

## What judges check, and our status

| Check (Disqualification Checklist) | Our status | Gap → owner |
|---|---|---|
| Judge can run it from a fresh clone; `docker build` + `docker run -p 8000:8000` | ✅ The root `Dockerfile` and `requirements.txt` exist. CI job `docker-judge-path` builds from the root, starts with `SAMPLE_MODE=true` and no credentials, and POSTs every `input_examples/example_*.json` | Gap 1 closed. Still to do by hand: a live run through `host.docker.internal` on the dry run (WS5-11) |
| `curl -X POST :8000/run -d @input_examples/example_1.json` | `/run` is real since PR #20 / graph PR; `input_examples/` doesn't exist yet | **Gap 2:** 3 inputs + 3 outputs → nexus-3, WS2-16 |
| `SAMPLE_MODE=true` with an empty `.env` and Zetaris + Nightshift **stopped** runs real logic | Sample mode exists (DuckDB twins, recorded fixtures, engine sample backends) | **Gap 3:** test it exactly as step 10 (`rm .env`, services stopped) → chief, WS5-11 + WS5-08 |
| Traces: ≥ 2 named agents, handoffs, critique/retry, Zetaris queries, engine activity, **model per request**, stdout + `logs/` | D3.12 tracer writes all of these; the Skeptic loop gives critique/retry | ✅ verify on the dry run |
| No hardcoded outputs, no demo-only branch, outputs differ across inputs | R3 / R6: fixtures replay only on transport errors, never keyed to example ids | ✅ verify by running 3 different inputs |
| Each sponsor call has a timeout and a fallback | Retries plus sample fallback on Zetaris/Nightshift; nexus-3 added fallbacks for Nightshift errors (PR #20) | ✅ |
| No secrets anywhere, including the video, deck and Nightshift Console/Providers tabs on screen | CI secret scan; secrets read from files only | **Gap 4:** frame-by-frame check of the video and deck for Nightshift tabs, terminals and the Supabase dashboard → video owner, WS5-07 |
| README: setup, usage, dependencies, agent roles, examples, limitations; links the Setup Guide for Zetaris/Nightshift | WS5-03 | ⏳ chief |
| NVIDIA award: a Nemotron model in a working feature, with the model shown per request | Pinned lanes are Lightning / Ultra / Embed (Nemotron); the trace logs the model on every call | ✅ |
| Responsible AI: human review for high-risk outputs, limitations, input validation | Human gate on every alert, tips untrusted (Scout Intent), limitations in the README | ✅ / README |
| Repo light, no large datasets | The generator creates data at run time; only a small sample bundle is committed | ✅ keep it so (no PDFs, no dumps) |
| Link to the video works in a private window | — | **Gap 5:** test the YouTube/Drive link logged out → WS5-07 |

## Notes from the Setup Guide

- "Zetaris and Meterless must be running on your machine to be eligible." Both are running on the team laptop ✅.
- `meterless/auto` may route to a non-NVIDIA model. We never use it (R2) ✅.
- `$METERLESS_RUNTIME_TOKEN` must be exported in the shell; a `.env` file doesn't export it. Our app reads the token file path instead (`METERLESS_RUNTIME_TOKEN_FILE`). The README must say both ways work.

## Open item outside the rules

**Nightshift vision (WS2-05).** Super VL is now enabled. The gate sits in Nightshift's own store; the `NVIDIA_SUPER_VL` environment variable is not read. Text calls to Super VL work, but **every request with an image is refused by Nightshift (`no_vision_model`) on every route**, including local PaddleOCR-VL. It has been reported to Meterless. Vision is not a rule requirement. The Extractor records an honest "vision unavailable" trace and falls back to the caption text. Nothing is faked.
