---
tags: [nexus, architecture]
---

# Agents, graph, scoring and eval

How Nexus turns a case into checked link alerts. Owner: the agents lane (nexus-3).
Related: [ENGINES](ENGINES.md) · [LANES](LANES.md) · [SPEC](SPEC.md) (C4, E2–E3, F, H) · [DECISIONS](DECISIONS.md) (D-016, D-017)

Code: `services/api/app/agents/`, `app/graph/`, `app/scoring/`, `app/eval/`, `app/worker.py`, `app/main.py`.

## Ground rules as built

- **R1, reads.** Agents read crime data only through `deps.query(name, ...)`, which calls Zetaris named queries. A test checks that no agent imports a DB or HTTP client.
- **R2, models.** Every model call goes through `NightshiftClient.chat(lane, ...)` on a pinned lane. Lanes are set by D-017: `fast` = Lightning and `reason` = Ultra; `vision`, `audio` and `tiny` fall back as in E2.
- **R7, numbers.** Every number is computed in `app/scoring`. Models write labels, plans and reasons only. Any number a model returns is ignored. The Briefer rejects prose that contains a number not in its facts.
- **R8, tips.** Every tip passes Tip Guard (Scout Intent) first, and failures fail closed. The Extractor reads only the redacted text of tips that passed.
- **R6, sample mode.** Sample mode runs the same graph. Prompts carry no per-call ids, so recorded fixtures replay. When a fixture is missing, the documented fallback runs (default plan, code reasons, code verdicts) and is traced. Nothing is canned.

## Scoring (F2)

- **Factors.** Nine factor functions over D3-shaped dicts. A factor returns `None` when there is no data (it then leaves the renormalisation) and `0` when the data disagrees.
- **Order of operations.** Base weighted sum → H-MEM (the sum of deltas is capped at ±0.08) → forensic floor 0.8 → clamp → round to 4 dp → band (high ≥ 0.75, medium ≥ 0.55).
- **Strikes.** A struck factor keeps its weight at value 0, so a Skeptic strike can never raise a score.
- **Coverage guard (D-016).** Coverage is the summed weight of unstruck factors that have data.
  - Coverage < 0.50 caps the band at medium.
  - Fewer than 2 such factors means no alert.
  - An unstruck forensic match is exempt, but only after the Skeptic has re-checked it from its own rows.
- **Choices recorded in D-016.** A same time band multiplies space_time by 1.2. A partial plate scores 0.6 + 0.3 × known/len, and ANPR near both scenes scores 0.85. Corroboration and offender return are positive-only. Suspect description reads an allow-list only (LNK-13).

## Agents (E3)

| Agent | Lane | Code decides | Model decides |
|---|---|---|---|
| Tip Guard | Scout Intent engine | verdict applied, fail closed | — |
| Extractor | fast / vision / audio | schema, protected-attribute drop, confidence, World Model ingest | MO labels |
| Planner | reason | allow-listed queries, forced crime_id, clamps, drops empty parameters, default plan | query order and windows |
| Linker | code + reason | all factor values, evidence `{view,row,query,query_id}`, H-MEM | one reason per factor, rationale, action |
| Skeptic | code + reason | own re-query, strikes, drop; **hard-contradiction drop** (stated offender count, non-overlapping age band, helmet, or the offender vehicle's colour/make/plate differ; reconciled only by Skeptic-confirmed forensic or offender_return evidence) | may only downgrade: approve → send back or drop |
| Alert writer | code | `LinkAlert` (D3.11) with coverage, stable id, notifications | — |
| Series analyst | Markovian + reason | 3+ connected links → series | chunk notes (citations checked by the engine) |
| Sanitiser | fast | allowed facts, leak check, template fallback | appeal wording (draft only) |
| Briefer | tiny → fast | all numbers | prose (rejected if it invents a number) |
| Hotspot detector | code | Poisson test on hex-time counts | — (owner: nexus-2) |

## Graph (C4)

`router` sends each input down one of three paths:

- **tip** → `tip_guard` → `tip_extract` (clean tips only)
- **search** → Scout Intent query route → `q_search`
- **case** → `load_case` → `extract` → `plan` → `link` → `skeptic`
  - `skeptic` either sends pairs back to `plan` or passes them on to `write`.

Caps:

- the Planner runs at most 3 rounds;
- the Skeptic sends back at most 2 times (its `requery` days/ring override the model's);
- a hard contradiction (`agents/contradiction.py`) drops the pair in `Skeptic.review()` before the model sees it, with `drop_source: contradiction` in the alert's `skeptic` block. It is pre-registered and tested in [SKEPTIC_CONTRADICTION_PREREG](eval/SKEPTIC_CONTRADICTION_PREREG.md);
- the run deadline is `RUN_DEADLINE_SECONDS` (300) for `/run` and batch runs, and `CASE_RUN_DEADLINE_SECONDS` (420) for the worker's per-case (filing) runs. With under 45 s left, the model calls are skipped and the code results stand. Past the deadline, Skeptic-approved pairs are written, and pairs the Skeptic sent back that no later round resolved are written as `needs_revision` (traced `deadline_partial_write`), never as approved.

## API (Part H)

| Route | What it does |
|---|---|
| `POST /run` | Judge entry point. Takes `{run_id?, input: {kind: case\|batch\|tip\|search, ...}, options: {sample_mode, force_extract, persist}}` and returns `run_id, status, output{alerts, series, hotspots, summary}, agents, engines, trace_id, log_file, execution_time_seconds`. |
| `POST /api/cases/{id}/process` | One case through the graph. |
| `POST /api/batch/link` | A batch of cases through the graph. |
| `POST /api/cases/{id}/public-draft` | Sanitiser appeal draft. |
| `POST /api/series/{id}/dossier` | Series dossier. |
| `POST /api/briefing` | Zone briefing. |
| `GET /api/traces/{run_id}` | The trace events of one run. |

## Worker and store

`python -m app.worker [--once]` works three queues:

1. `alert_decisions` → `hmem.record_decision`, plus alert status, notifications, and a joint-case proposal on approval.
2. New `tips` → Tip Guard verdict and status.
3. New crimes with no features → the graph.

`SupabaseStore` writes the `runs` row first. It never writes alert `status`, so a re-run cannot undo an analyst's decision.

**Which store a run uses (WS2-22).** One function, `store_kind(settings)` in `app/graph/local_store.py`, decides for both `/run` and `/health`:

| Setting | Store |
|---|---|
| `NEXUS_STORE=supabase` / `local` / `memory` | That store. `supabase` without keys, or an unknown value, fails loudly |
| unset, Supabase keys present | `SupabaseStore` |
| unset, no keys, live mode | `LocalStore`: JSON files under `data/local/` (gitignored; `NEXUS_LOCAL_DIR` overrides) |
| unset, no keys, `SAMPLE_MODE=true` | `MemoryStore`, so the judge fixtures stay byte-stable |

`LocalStore` keeps alerts with their factors, series and members (with D-033 removal), Extractor features and runs. It behaves like `SupabaseStore`: it never overwrites `status`, and a dossier only lands on a stored series. Notifications stay in memory. The Extractor reads local features before extracting again, so a restart reuses them; `force_extract` still re-extracts. With no keys in live mode, `/health` reports Supabase as `not_configured (local store)`, not `down`. The worker is Supabase-only, because the console writes its queues there. Backfill and the eval keep `MemoryStore`, so the eval report stays reproducible.

## Eval (F3)

`python -m app.eval` runs blocking, then F2 scoring, then the Skeptic's re-check against `_truth/`. It makes no model calls. The output is `output_examples/eval_report.json`. It calls `Skeptic.check()`, so it does **not** include the hard-contradiction step; an offline what-if of that step is in [SKEPTIC_CONTRADICTION_PREREG](eval/SKEPTIC_CONTRADICTION_PREREG.md) (precision 0.5915 → 0.6316, recall unchanged).

- **Precision and recall:** positives are series, vehicle chains and offender returns; decoys are negatives.
- **Duplicates:** reported separately.
- **Baseline:** rules only (same category, ≤ 2 km, ≤ 14 days).
- **Also reported:** precision by band and the card text that goes with it ("high band correct N%"), results by crime type, false alerts per 100 cases, and series purity.
