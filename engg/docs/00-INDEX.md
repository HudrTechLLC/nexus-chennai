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
- [WS5-08 results](validation/WS5-08-2026-10-27.md): the checklist run; part 1 pre-run (secrets incl. full history, hygiene, README, licences, vendored engines), part 2 on Tuesday

## Hackathon
- [DIGEST](hackathon/DIGEST.md): rules, scoring, disqualifiers, resource links
- [RULES_CHECK](hackathon/RULES_CHECK.md): our plan checked against the four official documents, with gaps and owners
- [EVIDENCE](submission/EVIDENCE.md): every submission claim with the file, test or CI job that proves it (PENDING rows show what's still open)
- [README_DRAFT](submission/README_DRAFT.md): superseded; the public README is the root `README.md`
- [SPONSOR_TECH_FINAL](submission/SPONSOR_TECH_FINAL.md): paste-ready sponsor technology text for the form
- [FORM](submission/FORM.md): paste-ready HackOS form answers (description, links, pre-existing declaration)
- [DECK](submission/DECK.md): slide-by-slide deck content, with the screenshot each slide needs
- [VIDEO_SCRIPT](submission/VIDEO_SCRIPT.md): demo video script (Red Pulsar story) and ElevenLabs narration
- [SPONSOR_TECH](SPONSOR_TECH.md): sponsor technology text for the form (draft, evidence-backed only)

## Diagrams
- `diagrams/c1-layers.svg` · `diagrams/c3-request-flow.svg` · `diagrams/c4-agent-graph.svg`
