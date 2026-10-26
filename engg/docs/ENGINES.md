---
tags: [nexus, architecture]
---

# Meterless engines in Nexus

Nexus uses four Meterless engines. Each one has a job no other part does, a feature that uses it, and a test that proves it (rule R5). Owner: the engines lane (nexus-2).
Related: [LANES](LANES.md) · [SPEC](SPEC.md) (P3–P6, E4) · [DECISIONS](DECISIONS.md) (D-008, D-015) · contract in code: `services/api/app/engines/README.md`

## How they run

The source is github.com/Meterless/Meterless at commit `1742dec5`, under Apache-2.0. `engines-ts/NOTICE` lists exactly what was copied.

- **World Model, H-MEM and Markovian** are vendored unchanged as TypeScript references in `engines-ts/<engine>/reference`. A local sidecar (`engines-ts/sidecar`, port 8790) serves them to Python.
- **Scout Intent** has no runnable reference, so Nexus implements it from the Meterless Scout spec, in Python.
- **Python facade.** Agents call `app.engines` and never call the sidecar directly. Every call writes one trace event with `engine` set.
- **Backends.** `ENGINES_BACKEND=sidecar` uses the TypeScript references. `sample` (the default) uses in-process Python ports of the same algorithms.
- **Parity.** A test checks that both backends give the same ids, scores and dossiers.

## The engines

| Engine | What it does in Nexus | Feature it powers | Facade |
|---|---|---|---|
| World Model | One canonical entity per real-world thing: plate, person, phone, place, FIR. Stable ids, provenance, and name resolution for people. | `/console/graph`, and the Linker/Skeptic context | `world_model.ingest`, `world_model.context` |
| H-MEM | Turns analyst approvals and rejections into memories. A later, similar pair gets a bounded score change (±0.08), and every step goes to a trust ledger. | "Memory applied" chips on alerts, `/console/memory` | `hmem.adjust`, `hmem.record_decision` |
| Markovian | Reads a whole crime series in bounded chunks. Only a capped carryover passes between chunks. Logs projected vs actual tokens. | "Build series dossier" on `/console/series/[id]` | `markovian.dossier` |
| Scout Intent | Routes analyst searches to the right tool. Tip Guard quarantines injection, threats, abuse and spam in public tips, and flags emergencies. | Console search box; tip intake (`/api/public/tips`) | `scout_intent.classify` |

## Tests and evidence

| What | Command | Result |
|---|---|---|
| Official conformance suites, unchanged | `node engines-ts/scripts/run-conformance.mjs` | `logs/conformance_world_model.txt` (8/8), `logs/conformance_hmem.txt` (13/13), `logs/conformance_markovian.txt` (8/8) |
| E4 feature tests, sample backend | `pytest tests/engines -q` | pytest output |
| E4 feature tests on the TypeScript references | `cd engines-ts && npm run sidecar`, then `ENGINES_BACKEND=sidecar pytest tests/engines -q` | pytest output; the CI `engines` job runs both steps on every PR |
| Markovian runs | any dossier | `logs/markovian_runs.jsonl` (projected vs actual tokens, labelled estimated) |
| H-MEM ledger | any decision | `logs/hmem/ledger.jsonl` |

**Setup, once:** `cd engines-ts && npm ci && npm run install:references`.
