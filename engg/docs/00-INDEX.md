---
tags: [nexus, index]
---

# Nexus Chennai · engineering docs

Entry point for every project document. **Start here, then read the note for your area.** Links are plain Markdown, so they work on GitHub and in Obsidian (open `engg/docs/` as a vault).

**Project:** city-wide crime-linking agents for Chennai · Open Agent Hackathon 2026 · Track 1 (Solving Fragmented Intelligence) · team Heisenbugs
**Deadline:** 27 Oct 2026 23:45 UTC. Submit ≥ 6 h early.

## Specification
- [SPEC](SPEC.md): the full product and build spec, all 16 parts. Single source of truth.
  - [A Overview](SPEC.md#overview) · [P Products](SPEC.md#products) · [O Claude Code manual](SPEC.md#claude-code) · [B Requirements](SPEC.md#requirements)
  - [C Architecture](SPEC.md#architecture) · [D Data](SPEC.md#data) · [E Agents & sponsors](SPEC.md#sponsors) · [F Linking](SPEC.md#linking)
  - [G Screens](SPEC.md#screens) · [H API](SPEC.md#api) · [I Database](SPEC.md#database) · [J Security](SPEC.md#security)
  - [K Phases](SPEC.md#phases) · [L Deliverables](SPEC.md#deliverables) · [M Demo](SPEC.md#demo) · [N Risks](SPEC.md#risks)

## Design and decisions
- [ARCHITECTURE](ARCHITECTURE.md): what runs where (Vercel + laptop + Supabase), diagrams, tip path
- [DECISIONS](DECISIONS.md): every decision and verification (D-001…)
- [CITY_PACKS](CITY_PACKS.md): how another city is added without code changes
- [ENGINES](ENGINES.md): the four Meterless engines, what each powers, how they run and how they're tested
- [AGENTS](AGENTS.md): the agents, the LangGraph flow, caps and the API routes
- [ASK_NEXUS](ASK_NEXUS.md): plain-English questions → a checked plan of named queries → a cited answer (WS3-30)

## Plan and status
- [LANES](LANES.md): the 4 build lanes, what each owns, interfaces between them, merge rules
- **[workstreams.json](workstreams.json)**: every workstream and task with its status; rendered as the live progress chart at `/docs/progress` in the web app
- [PROGRESS](PROGRESS.md): phase status, blockers, session log
- [DELIVERABLES](DELIVERABLES.md): submission and eligibility checklist
- [PATH2](PATH2.md): after the hackathon: a self-contained `docker compose up` stack (local Supabase + Zetaris + Nexus), the WS6 backlog and phases

## Runbooks
- [SETUP](SETUP.md): accounts, services, environment variables, Nightshift and Zetaris contracts
- [TOOLING](TOOLING.md): Claude Code skills, subagents and hooks for this repo
- [validation](validation/README.md): gate reports
- [WS3-06 / WS3-10 gate](validation/WS3-06-WS3-10-2026-10-26.md): case file, search and FIR capture vs CAP-01…10 and SRCH-01…07, with live evidence and open gaps
- [WS5-08 checklist](validation/WS5-08-checklist.md): Tuesday fresh-clone validation (L3), every Disqualification Checklist item with its command and PASS rule
- [PLANTED_SKEPTIC_PREREG](eval/PLANTED_SKEPTIC_PREREG.md): planted false-link test for the Skeptic, pre-registered before any model call (paired: 8 twins over 16 distinct crimes in 5 series + 24 single-fact near-misses; primary = near-miss dropped while its twin is approved). **Run 27 Oct: FAIL, 0/24.** The Skeptic never chose drop; results in the note and `output_examples/planted_skeptic.json`
- [SKEPTIC_CONTRADICTION_PREREG](eval/SKEPTIC_CONTRADICTION_PREREG.md): pre-registered fix for #392. A deterministic hard-contradiction rule (offender count, age band, helmet, vehicle) drops approved pairs in code. It is tested on a FRESH blind planted set: primary drop ≥ 0.60, twin false-drop ≤ 1/8. **Run 27 Oct: PASS, 24/24 dropped, 0/8 twin false-drops** (by construction on generator data). The rule ships in the same PR as the results
- [INDEPENDENT_LOOKALIKE_PREREG](eval/INDEPENDENT_LOOKALIKE_PREREG.md): pre-registered independent test of the contradiction rule on hand-written look-alikes (not from the generator), offline, rule only (no model critique). Primary drop ≥ 0.60 over 24, twin false-drop ≤ 1/8. **Run 27 Oct: FAIL on both, as predicted: 10/24 dropped (S1 8/8, S2 2/8, S3 0/8); twins 2/8 wrongly dropped (both witness-error twins).**
- [DUPLICATE_CORROBORATION_PREREG](eval/DUPLICATE_CORROBORATION_PREREG.md): pre-registered offline measurement (task #18). How many eval alerts' corroboration rests on duplicate or derivative reports (a news, social, call or tip item re-reporting an FIR already in the pair), and the share of alerts that would lose a band without them. **Run 27 Oct: 9 of 148 alerts have corroboration; 7 of those rest partly (4 wholly) on derivative 112 calls; 0 alerts would lose a band.**
- [WS5-08 results](validation/WS5-08-2026-10-27.md): the checklist run; part 1 pre-run (secrets incl. full history, hygiene, README, licences, vendored engines), part 2 on Tuesday
- [NEMOTRON_ALONE_PREREG](eval/NEMOTRON_ALONE_PREREG.md): pre-registered baseline, Nemotron Ultra alone vs the full system on the same 182 headline pairs (case list, prompt, scoring and stop rules fixed before any call)
- [STRONGER_BASELINE_PREREG](eval/STRONGER_BASELINE_PREREG.md): pre-registered second baseline, rules + vehicle/plate matching (primary: same category AND (≤ 2 km and ≤ 14 days OR vehicle match); secondary: strict AND), P/R/F1 on the same 60 cases, offline, no model calls; fixed before the run
- [NEMOTRON_ALONE_RESULTS](eval/NEMOTRON_ALONE_RESULTS.md): the run: same 182 pairs, Ultra alone F1 0.80 vs full system 0.69 (14 positives, McNemar n.s.); under the 10-pair budget cap the model reached 14/49 true links vs the system's 41/49

## Hackathon
- [DIGEST](hackathon/DIGEST.md): rules, scoring, disqualifiers, resource links
- [RULES_CHECK](hackathon/RULES_CHECK.md): our plan checked against the four official documents, with gaps and owners
- [EVIDENCE](submission/EVIDENCE.md): every submission claim with the file, test or CI job that proves it (PENDING rows show what's still open)
- [README_DRAFT](submission/README_DRAFT.md): superseded; the public README is the root `README.md`
- [SPONSOR_TECH_FINAL](submission/SPONSOR_TECH_FINAL.md): paste-ready sponsor technology text for the form
- [FORM](submission/FORM.md): paste-ready HackOS form answers (description, links, pre-existing declaration)
- [COMPLIANCE](submission/COMPLIANCE.md): every HackOS requirement mapped to where we meet it, with the red gaps and what only Ravee can do
- [DECK](submission/DECK.md): slide-by-slide deck content, with the screenshot each slide needs
- [VIDEO_SCRIPT](submission/VIDEO_SCRIPT.md): demo video script (Red Pulsar story) and ElevenLabs narration
- [SPONSOR_TECH](SPONSOR_TECH.md): sponsor technology text for the form (draft, evidence-backed only)

## Diagrams
- `diagrams/c1-layers.svg` · `diagrams/c3-request-flow.svg` · `diagrams/c4-agent-graph.svg`
