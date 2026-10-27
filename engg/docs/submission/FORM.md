---
tags: [nexus, deliverables]
---

# HackOS submission form answers

Paste-ready answers for the HackOS submission form. Every claim comes from [EVIDENCE](EVIDENCE.md). Before pasting, replace each `<…>` placeholder, and resolve or delete any sentence still marked as pending.
Related: [COMPLIANCE](COMPLIANCE.md) · [EVIDENCE](EVIDENCE.md) · [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md) · [README_DRAFT](README_DRAFT.md) · [RULES_CHECK](../hackathon/RULES_CHECK.md) · [DELIVERABLES](../DELIVERABLES.md)

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

Agents that link crimes across police stations by querying fragmented records through Zetaris, reasoning with NVIDIA Nemotron through Meterless Nightshift, with a Skeptic agent's second opinion and a human analyst deciding every link.

## Short description (≈ 50 words)

Each police station sees only its own cases, so a gang working across a city looks like unrelated crimes. Nexus reads case files, legacy exports and ANPR records through Zetaris, scores likely links in code, and explains each one with Nemotron. A Skeptic gives a second opinion on every link, and analysts decide. Their decisions teach the system.

## Long description

**The problem.** A city's police stations each keep their own records. A chain-snatching gang that strikes near one station on Wednesday and another two days later produces two unrelated robbery files. The evidence that would connect them is spread across case files, statements, news reports and public tips, and no station sees all of it.

**What Nexus does.** For each new case, a LangGraph team of agents finds candidate cases city-wide, scores each pair on nine factors in code (modus operandi, place and time, vehicle, suspect description, weapon, target, forensics, corroboration, offender return), and writes a link alert. Each alert carries a plain reason for every factor and the Zetaris query and row behind it. The models write labels, plans and reasons; they never set a number.

**A second opinion, and a human decides.** A Skeptic agent runs its own Zetaris queries, critiques each pair, and can send it back for a narrower search or drop it. It is not a guarantee: in a pre-registered test it dropped none of 24 planted look-alike false links, and we publish that. An analyst approves or rejects every alert. That decision goes to the Meterless H-MEM engine, so the next similar pair is scored with it, within a hard ±0.08 bound, and the alert says "memory applied".

**New sources and plain questions.** Fragmented data keeps arriving in new shapes. An admin uploads an unseen station export; Zetaris profiles and checks it in place, Nemotron Lightning proposes the column mapping, a person approves it, and it becomes a Zetaris view. In a live run on 150 synthetic rows, the data-quality checks found every planted fault (for example 4 of 4 likely duplicates of existing cases). Analysts can also ask **Ask Nexus** a question in plain words ("chain snatchings on a red Pulsar in the last 90 days"): Nemotron writes only a plan, code checks it, and an allow-listed Zetaris query answers. Its counts matched independent SQL counts every time we checked, and it refuses questions it can't answer from the data.

**The public can help safely.** Anyone can send an anonymous tip through the public portal. Photos are stripped of metadata, and the tipster gets a tip code. The Meterless Scout Intent engine (Tip Guard) screens every tip for injection, threats and spam before any agent reads it, and fails closed.

**Sponsor technology is load-bearing:**
- **Zetaris** is the only way agents read crime data (registered named queries over federated sources).
- **Meterless Nightshift** is the only model path, on pinned NVIDIA Nemotron lanes (Ultra 550B, Lightning 30B and Super VL for evidence stills), with the model logged on every call. 190 of 193 traced model calls carry a Nightshift receipt, and all 190 signatures verify.
- **All four Meterless engines** run in features. World Model, H-MEM and Markovian pass their official conformance suites unchanged (8/8, 13/13, 8/8). Scout Intent scores 0.975 route accuracy and catches 7/7 injections on a held-out set it was never tuned on (23/23 on the set its rules were tuned on), and on 40 live seeded tips it falsely quarantined none of the 30 genuine tips. It first missed 1 of 4 injections and 3 of 4 spam tips. We fixed the rules for those shapes, and they now catch all 8, but that figure isn't independent, because those misses shaped the fix.

**Measured honestly.** On planted synthetic truth the agents reach precision 0.59 and recall 0.86 against 0.09 and 0.30 for a rules-only baseline. In a pre-registered comparison, Nemotron Ultra alone scored a higher F1 than the pipeline on the pairs it was shown (0.80 vs 0.69), but the difference is not significant. The pipeline's edge is coverage at no model cost: it scores every candidate, where the model alone would need about 26 hours for all of them. We also publish a failed test: the Skeptic dropped none of 24 planted look-alike false links.

**Built to be checked.** Judges can run it with Docker or a Python virtual environment, post an input to `POST /run`, and read a JSONL trace of every agent step, Zetaris query, engine call and model. `SAMPLE_MODE=true` runs the same agent logic without credentials, on the committed synthetic sample in `data/sample/`, and the container answers all three examples with no network at all (CI job `judge-offline`). All crime, person, case and tip data is synthetic.

## Links

| Field | Value |
|---|---|
| Public GitHub repository | https://github.com/HudrTechLLC/nexus-chennai (make public first: WS5-09) |
| Demo video (1–4 min) | `<YouTube unlisted URL>`; backup `<Drive URL>`. Test both logged out, in a private window |
| Slide deck | `<deck URL or upload>` (content: [DECK](DECK.md)) |
| Live app (optional) | Portal https://nexus-chennai.vercel.app · console https://nexus-chennai.vercel.app/console/login |

## Demo police accounts (judges only)

**Form only, never in the README or any repo file**, because the repo is public and these accounts can decide alerts. nexus-chief fills these in with Ravee at submit time. Officer, analyst and supervisor only: **the admin account is never shared** (Ravee, 27 Oct).

| Role | Login | Password |
|---|---|---|
| Station officer (Adyar) | `<email>` | `<password>` |
| Analyst | `<email>` | `<password>` |
| Supervisor | `<email>` | `<password>` |

Sign in at https://nexus-chennai.vercel.app/console/login.

## Sponsor technology explanation

Paste the text of [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md), from the line down. Resolve or delete anything still marked as pending first.

## Cursor

Not used. Nexus was built with Claude Code as a development tool. Claude Code is not in the product's request path.

## Pre-existing components (declaration)

1. **Meterless reference engines and conformance suites.** The World Model, H-MEM and Markovian TypeScript reference implementations and their conformance suites are vendored unmodified from github.com/Meterless/Meterless @ `1742dec56a66e58eef9dda2d2b865823758ca8cd` (Apache-2.0), in `engines-ts/` (see `engines-ts/NOTICE`). Scout Intent is implemented by Nexus from the Meterless Scout spec. The Python backends in `services/api/app/engines/*/core.py` are Nexus ports of the reference algorithms, written during the build window.
2. **Open-source libraries** used as dependencies: FastAPI, LangGraph, DuckDB, Next.js, MapLibre GL, deck.gl and others, listed in the README.
3. **Nothing else is pre-existing.** The repository, code and product specification were all written inside the build window; the spec was started on 23 Oct and completed on 26 Oct 2026. All crime, person, case and tip data is synthetic, generated during the window and labelled `synthetic: true`. No real crime or personal data is used. The only real data is third-party public reference data, listed with its licence in `data/README.md`: OpenStreetMap places (ODbL), DataMeet ward boundaries (CC BY-SA 2.5 IN), the public police-station list, and live Open-Meteo weather (CC BY 4.0).

## AI usage

- **In the product:** every model call goes through Meterless Nightshift to pinned NVIDIA Nemotron models: Nemotron 3.5 Lightning 30B for extraction, drafting, Ask Nexus plans and onboarding column mapping; Nemotron 3 Ultra 550B for planning, reasons and the Skeptic; and Nemotron 3.5 Super VL for reading CCTV and evidence stills (verified in one live run, `reextract_vis_1793040194`; a rate-limited free route, so a run can fall back to the officer's caption). The model and a receipt id are logged on every call. No embedding model is claimed (see the sponsor text).
- **In development:** Claude Code (Anthropic) wrote and reviewed code; it is not part of the running product.
- **In the demo:** the narration voice was generated with ElevenLabs, which is not part of the running product.

## Responsible AI (if the form asks)

Nexus suggests and people decide. An analyst decides every link, and an officer publishes every public appeal. Each alert shows its evidence and the query behind it. Numbers come from code, never from a model. Public tips are screened before any agent reads them. The public map uses coarse cells with a minimum-count cutoff. Protected attributes are never used. All crime, person, case and tip data is synthetic; only public reference data (map, wards, stations, weather) is real.
