---
tags: [nexus, release-notes]
---

# Sponsor technology explanation (draft)

This text is pasted into the HackOS submission form. **Rule R10:** each claim is written here only after a trace or test proves it, and each one links to its evidence. Until then it stays a placeholder.
Related: [DELIVERABLES](DELIVERABLES.md) · [SPEC Part P](SPEC.md#products) · [SPEC Part E](SPEC.md#sponsors) · [00-INDEX](00-INDEX.md)

## Zetaris: data layer
_Pending P2._ To write up:

- the registered sources and storage types;
- the semantic views (`v_crime_unified`, `v_vehicle_trail`, …);
- the data-quality views;
- the 12 named queries;
- the evidence that every agent read goes through `app/adapters/zetaris.py`.

> Draft line from the spec: "Every fact in a Nexus link alert traces back to a row Zetaris returned from the source that holds it: Supabase, S3 or a live feed."

## Meterless engines
Only engines with a passing test are listed (D-005).

| Engine | Feature | Test | Result |
|---|---|---|---|
| World Model | Case graph + Linker/Skeptic context | idempotent re-ingest; two writers converge; provenance kept | ⏳ |
| H-MEM | Memory chips that change scores; `/console/memory` | three-session changed-score test | ⏳ |
| Scout Intent | Search router + Tip Guard | 120 fixtures, route accuracy ≥ 0.9, all injections quarantined | ⏳ optional |
| Markovian | Series dossier | chunk and carryover limits, real record ids only, savings logged | ⏳ optional |

## Meterless Nightshift: primary AI provider
_Pending P0 smoke test._ To write up:

- the single adapter `app/adapters/nightshift.py`;
- the pinned lanes;
- the headers sent;
- that the NVIDIA key lives only in Nightshift;
- what each trace line logs: lane, pinned model, routed model.

## NVIDIA Nemotron
_Pending D-006 verification._

| Lane | Model | Job |
|---|---|---|
| fast | Nemotron 3.5 Lightning 30B | MO extraction at volume, appeal drafts |
| vision | Nemotron 3.5 Super VL 120B | CCTV stills, evidence photos |
| reason | Nemotron 3 Super 120B | Query planning, factor rationale, Skeptic |

## Cursor
Not used. Built with Claude Code as a development tool. Claude Code is never in the product's request path.

## What was unique
- The Skeptic re-runs Zetaris queries itself and can strike a link the data doesn't support.
- Rejected links stay visible to every police role and, through H-MEM, change the next score.
- Public tips feed linking only after Scout Intent screening.
