---
tags: [nexus, plan]
---

# Submission deliverables checklist

What we hand in, and what must be true for the entry to be eligible. Source: [SPEC Part L](SPEC.md#deliverables), [Part M](SPEC.md#demo) and [hackathon digest](hackathon/DIGEST.md).
Related: [PROGRESS](PROGRESS.md) · [SPONSOR_TECH](SPONSOR_TECH.md) · [00-INDEX](00-INDEX.md)

## A. Submitted on HackOS

| # | Deliverable | Detail | Status |
|---|---|---|---|
| 1 | Demo video, 1–4 min | About 3:40 with ElevenLabs narration per the Part M script; YouTube unlisted + Drive backup; plays logged out | ⏳ |
| 2 | Slide deck | 12 slides covering the 8 required points (L2) | ⏳ |
| 3 | Public GitHub repo | README with all L2 sections; repo made public | ⏳ |
| 4 | Sponsor technology text | [SPONSOR_TECH](SPONSOR_TECH.md), pasted into the form | ⏳ draft |
| 5 | Pre-existing components | Declared in the form: Meterless reference engines (Apache-2.0), public reference data | ⏳ |
| 6 | Cursor field | "Not used; built with Claude Code" | ⏳ |

## B. Eligibility (missing any = not eligible)

- [ ] Zetaris is the data layer: every agent read goes through named queries (R1)
- [ ] ≥1 Meterless engine in a working feature with a passing test (`pytest tests/engines -q`)
- [ ] Nightshift is the primary AI provider; every call logs lane, pinned model and routed model
- [ ] Nemotron named on every trace line (DGX Spark award)
- [ ] No secrets committed; `.env.example` only
- [ ] No hard-coded outputs; sample mode runs real agent logic
- [ ] Traces show how the agent got there (`logs/*.jsonl`, trace viewer)

## C. In the repo

- [ ] `run.py`, `POST /run`, `docker-compose.yml`
- [ ] `SAMPLE_MODE=true` works with Zetaris and Nightshift stopped and no `.env`
- [ ] `input_examples/` (3) + matching real `output_examples/` + `eval_report.json`
- [ ] `metadata.json` (claims only what passes)
- [ ] `.env.example`
- [ ] README sections (L2):
  - Track · Problem · What it does · Architecture · Agents
  - Sponsor technology · Setup · Run · Sample mode · Examples
  - Evaluation · Logs · Tests · AI and Model Usage
  - Data sources and licences · Third-party code · Limitations
  - Pre-existing components · Demo video link
- [ ] Live URLs: Vercel portal + console (D-003)

## D. Final validation, the day before (L3)

1. Fresh clone → `cp .env.example .env` → fill in.
2. `docker compose build && docker compose up`.
3. `curl -X POST localhost:8000/run -d @input_examples/example_1.json`, then examples 2 and 3.
4. Read `logs/`: router, Planner revise, Skeptic strike, engine events, model on every call.
5. `pytest tests/engines -q` passes.
6. Secret scan (O6 grep patterns).
7. Stop Zetaris and Nightshift, remove `.env`, `SAMPLE_MODE=true docker compose up`, rerun example 1.
8. Open the repo logged out; play the video in a private window.

## E. Scoring reminder

Impact 30 · Technical 20 · Innovation 15 · Demo 15 · Product & UX 10 · Sponsor Tech 10.
