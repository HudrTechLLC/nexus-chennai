---
tags: [nexus, deliverables]
---

# HackOS submission form answers

Paste-ready answers for the HackOS submission form. Every claim comes from [EVIDENCE](EVIDENCE.md). Before pasting, replace each `<…>` placeholder and resolve each `[PENDING: id]`, or delete that sentence.
Related: [EVIDENCE](EVIDENCE.md) · [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md) · [README_DRAFT](README_DRAFT.md) · [RULES_CHECK](../hackathon/RULES_CHECK.md) · [DELIVERABLES](../DELIVERABLES.md)

> **Notes for the chief, not form text:**
> - The field list follows the Submission Requirements as summarised in [DIGEST](../hackathon/DIGEST.md). The locally saved `submission-requirements.pdf` printed blank (title only), so **check the field names and any length limits against the live form** when you create the draft.
> - **The roster locks when the submission is first created**, so confirm the team members first (WS5-10).
> - **Submit by Tue 27 Oct 23:15 IST**; the hard deadline is 27 Oct 23:45 UTC (28 Oct 05:15 IST). Updates are allowed until the deadline, so create the draft early.

---

## Project name

Nexus Chennai

## Track (one primary track)

Track 1 · Solving Fragmented Intelligence

## Team

Heisenbugs · members: `<names as on HackOS>`

## One-line description

Agents that link crimes across police stations by querying fragmented records through Zetaris, reasoning with NVIDIA Nemotron through Meterless Nightshift, and letting a Skeptic agent and a human analyst decide every link.

## Short description (≈ 50 words)

Each police station sees only its own cases, so a gang working across a city looks like unrelated crimes. Nexus reads case files and live feeds through Zetaris, scores likely links in code, and explains each one with Nemotron. A Skeptic re-checks every link against the data, and analysts decide. Their decisions teach the system.

## Long description

**The problem.** A city's police stations each keep their own records. A chain-snatching gang that strikes near one station on Wednesday and another two days later produces two unrelated robbery files. The evidence that would connect them is spread across case files, statements, news reports and public tips, and no station sees all of it.

**What Nexus does.** For each new case, a LangGraph team of agents finds candidate cases city-wide, scores each pair on nine factors in code (modus operandi, place and time, vehicle, suspect description, weapon, target, forensics, corroboration, offender return), and writes a link alert. Each alert carries a plain reason for every factor and the Zetaris query and row behind it. The models write labels, plans and reasons; they never set a number.

**It checks its own work.** Before any human sees an alert, a Skeptic agent runs its own Zetaris queries, strikes factors its rows don't support, and can send a pair back for a narrower search or drop it. Only what survives reaches an analyst, who approves or rejects. That decision goes to the Meterless H-MEM engine, so the next similar pair is scored with it, within a hard ±0.08 bound, and the alert says "memory applied".

**The public can help safely.** Anyone can send an anonymous tip through the public portal. Photos are stripped of metadata, and the tipster gets a tip code. The Meterless Scout Intent engine (Tip Guard) screens every tip for injection, threats and spam before any agent reads it, and fails closed.

**Sponsor technology is load-bearing:**
- **Zetaris** is the only way agents read crime data (registered named queries over federated sources).
- **Meterless Nightshift** is the only model path, on pinned NVIDIA Nemotron lanes, with the model logged on every call.
- **All four Meterless engines** run in features. World Model, H-MEM and Markovian pass their official conformance suites unchanged (8/8, 13/13, 8/8), and Scout Intent passes its fixture evaluation (route accuracy 1.000 on 120 fixtures, 0.950 held-out). On the 40 live seeded tips it quarantined 3 of 4 injections and 1 of 4 spam tips and flagged both emergencies; the misses were stored only as vocabulary-only summaries, and fixes are in progress.

**Built to be checked.** Judges can run it with Docker or a Python virtual environment, post an input to `POST /run`, and read a JSONL trace of every agent step, Zetaris query, engine call and model. `SAMPLE_MODE=true` runs the same agent logic without credentials, on a committed synthetic sample `[PENDING: WS1-11]`. All data is synthetic.

## Links

| Field | Value |
|---|---|
| Public GitHub repository | https://github.com/HudrTechLLC/nexus-chennai (make public first: WS5-09) |
| Demo video (1–4 min) | `<YouTube unlisted URL>`; backup `<Drive URL>`. Test both logged out, in a private window |
| Slide deck | `<deck URL or upload>` (content: [DECK](DECK.md)) |
| Live app (optional) | `<Vercel portal URL>` · `<Vercel console URL>` |

## Sponsor technology explanation

Paste the text of [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md), from the line down. Resolve its `[PENDING]` items first.

## Cursor

Not used. Nexus was built with Claude Code as a development tool. Claude Code is not in the product's request path.

## Pre-existing components (declaration)

1. **Meterless reference engines and conformance suites.** The World Model, H-MEM and Markovian TypeScript reference implementations and their conformance suites are vendored unmodified from github.com/Meterless/Meterless @ `1742dec56a66e58eef9dda2d2b865823758ca8cd` (Apache-2.0), in `engines-ts/` (see `engines-ts/NOTICE`). Scout Intent is implemented by Nexus from the Meterless Scout spec. The Python backends in `services/api/app/engines/*/core.py` are Nexus ports of the reference algorithms, written during the build window.
2. **Open-source libraries** used as dependencies: FastAPI, LangGraph, DuckDB, Next.js, MapLibre GL, deck.gl and others, listed in the README.
3. **Nothing else is pre-existing.** The repository, code and product specification were all written inside the build window; the spec was started on 23 Oct and completed on 26 Oct 2026. All data is synthetic, generated during the window and labelled `synthetic: true`. No real crime or personal data is used.

## AI usage

- **In the product:** every model call goes through Meterless Nightshift to pinned NVIDIA Nemotron models: Nemotron 3.5 Lightning 30B for extraction and drafting, and Nemotron 3 Ultra 550B for planning, reasons and the Skeptic. The model and a receipt id are logged on every call. No embedding model is claimed (see the sponsor text).
- **In development:** Claude Code (Anthropic) wrote and reviewed code; it is not part of the running product.
- **In the demo:** the narration voice was generated with ElevenLabs, which is not part of the running product.

## Responsible AI (if the form asks)

Nexus suggests and people decide. An analyst decides every link, and an officer publishes every public appeal. Each alert shows its evidence and the query behind it. Numbers come from code, never from a model. Public tips are screened before any agent reads them. The public map uses coarse cells with a minimum-count cutoff. Protected attributes are never used. All data is synthetic.
