---
tags: [nexus, eval, results]
---

# Model-in-the-loop eval: results

A side result, published as pre-registered in [[MODEL_IN_LOOP_PREREG]] whatever it shows. The headline eval stays the code-only `python -m app.eval` (0 model calls).

Run at `339c274` (code_dirty = false), sample data, in-memory store, engines off, live Nightshift. Output: `output_examples/model_in_loop_eval.json`.

## Pair metrics (same positives, same `pair_metrics`)

| Arm | Cases | TP | FP | FN | Precision | Recall | F1 | Model calls |
|---|---|---|---|---|---|---|---|---|
| A, code only | 10 | 35 | 15 | 2 | 0.700 | 0.946 | 0.805 | 0 |
| B, model in the loop | 10 | 9 | 3 | 28 | 0.750 | 0.243 | 0.367 | 47 |

## Loop activity (arm B)

- Planner rounds: 13 in total; Skeptic send-backs: 3; pairs dropped: 2; factors struck on written alerts: 0.
- Model calls: 47; **replayed: 0**; cases fully live (0 replayed, not failed): 10 of 10.
- Receipts: 47 of 47 receipt ids verified against the local Nightshift log.
- Time: arm B 2499.2 s in total; **4 of 10 cases ended with status `deadline`** (the product's 300 s run deadline; `totals.deadline_hits` = 2 counts only the skip-model event). Arm A 13.9 s for all 10.

## Per case (arm B)

| Case | Status | Pairs written | Plan rounds | Send-backs | Dropped | Model calls | Replayed | Seconds |
|---|---|---|---|---|---|---|---|---|
| `CHN-AD-2026-001071` | success | 4 | 1 | 0 | 0 | 5 | 0 | 354.3 |
| `CHN-AD-2026-001078` | deadline | 0 | 1 | 0 | 0 | 4 | 0 | 314.3 |
| `CHN-AD-2026-001084` | deadline | 2 | 2 | 1 | 0 | 5 | 0 | 313.9 |
| `CHN-AD-2026-001182` | success | 3 | 1 | 0 | 0 | 5 | 0 | 266.2 |
| `CHN-AM-2024-001346` | success | 0 | 1 | 0 | 1 | 4 | 0 | 140.8 |
| `CHN-AM-2025-000865` | success | 0 | 1 | 0 | 0 | 2 | 0 | 65.2 |
| `CHN-AM-2025-001042` | deadline | 2 | 2 | 1 | 0 | 5 | 0 | 331.4 |
| `CHN-AM-2025-001062` | success | 1 | 2 | 1 | 1 | 7 | 0 | 184.9 |
| `CHN-AS-2025-000080` | deadline | 0 | 1 | 0 | 0 | 6 | 0 | 354.8 |
| `CHN-AV-2026-000609` | success | 1 | 1 | 0 | 0 | 4 | 0 | 173.4 |

## Reading it

- **The live model loop found far fewer true links than the code path on the same 10 cases:** recall 0.243 vs 0.946 (9 vs 35 true links). Its precision was similar (0.750 vs 0.700), but on 12 written links that difference means nothing.
- **The run deadline explains a large part of it.** 4 of 10 cases hit the product's 300 s deadline with live Nightshift latency (case times 65–355 s). The deadline cases with truth links lost the most: `CHN-AD-2026-001078` wrote 0 of its 8 truth links, `CHN-AS-2025-000080` 0 of 7, and `CHN-AM-2025-001042` 2 of 5.
- **Cases that finished also wrote fewer links than the code path,** all of them correct: `CHN-AD-2026-001071` 4 of 8, `CHN-AD-2026-001182` 3 of 8, `CHN-AM-2025-000865` 0 of 5 (the code path found 3). The cause was **not diagnosed** in this run: it could be the model Planner's plans, the Skeptic's critique, or the per-run pair caps. It is reported as observed.
- **The loop is live and traceable:** 47 model calls, 0 replayed, all 47 receipts verified. The Skeptic sent pairs back 3 times and dropped 2; the Planner ran 13 rounds across the 10 cases.
- **What this means for the product:** on this data the code path is the stronger linker, and the models' value is the explanations and critique, not better recall. This is consistent with the design (R7: models explain, code scores). The headline numbers stay code-only.

### Per case, both arms (exploratory, not pre-registered)

Arm A scored per case by the same code path (no model calls), to see where arm B's recall went. Source: `output_examples/model_in_loop_percase_exploratory.json`. Per-case counts include every truth link that touches the case, so a link between two of the 10 cases is counted under both; the columns do not sum to the pair totals above (37 truth pairs).

| Case | Truth links | A written / correct | B written / correct | B status | B plan rounds | B seconds |
|---|---|---|---|---|---|---|
| `CHN-AD-2026-001071` | 8 | 8 / 8 | 4 / 4 | success | 1 | 354.3 |
| `CHN-AD-2026-001078` | 8 | 9 / 8 | 0 / 0 | deadline | 1 | 314.3 |
| `CHN-AD-2026-001084` | 0 | 9 / 0 | 2 / 0 | deadline | 2 | 313.9 |
| `CHN-AD-2026-001182` | 8 | 9 / 8 | 3 / 3 | success | 1 | 266.2 |
| `CHN-AM-2024-001346` | 0 | 1 / 0 | 0 / 0 | success | 1 | 140.8 |
| `CHN-AM-2025-000865` | 5 | 4 / 3 | 0 / 0 | success | 1 | 65.2 |
| `CHN-AM-2025-001042` | 5 | 5 / 5 | 2 / 2 | deadline | 2 | 331.4 |
| `CHN-AM-2025-001062` | 0 | 2 / 0 | 1 / 0 | success | 2 | 184.9 |
| `CHN-AS-2025-000080` | 7 | 8 / 7 | 0 / 0 | deadline | 1 | 354.8 |
| `CHN-AV-2026-000609` | 0 | 1 / 0 | 1 / 0 | success | 1 | 173.4 |

## Limits

- 10 cases, synthetic data, one run; model output is not deterministic, so a re-run can differ.
- No significance claim is made, as pre-registered.

**Related:** [[MODEL_IN_LOOP_PREREG]] · [[PLANTED_SKEPTIC_PREREG]] · [[TIMED_TASK_RESULTS]]
