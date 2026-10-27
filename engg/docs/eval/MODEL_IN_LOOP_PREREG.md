---
tags: [nexus, eval, prereg]
---

# Model-in-the-loop eval: pre-registration (task #21)

Decided by Ravee and the chief, 27 Oct 2026. Written and committed **before any model call** of this eval. The
results will be published whatever they are, as a **side result**. The headline eval stays the code-only
`python -m app.eval` (0 model calls); this eval only measures what the live model loop adds or costs on a small,
fixed set.

## Why

The headline eval (`output_examples/eval_report.json`) runs blocking → F2 code scoring → the Skeptic's code
re-check, with **no model calls**. The product's case path also runs the models: the Planner plans Zetaris queries
(up to 3 rounds), the Linker explains each pair, and the Skeptic critiques and may strike factors, drop pairs or
send them back to the Planner (up to 2 send-backs). This eval measures that loop on the same cases as a code-only
run.

## Cases (fixed rule, stated in advance)

The **first 10 crimes of `load_truth(data/sample/_truth).crimes()`**, which is exactly what
`python -m app.eval --truth data/sample/_truth --limit 10` evaluates (`pairs.csv` sha256 starts `852e1cb21f1f82f8`):

`CHN-AD-2026-001071`, `CHN-AD-2026-001078`, `CHN-AD-2026-001084`, `CHN-AD-2026-001182`, `CHN-AM-2024-001346`,
`CHN-AM-2025-000865`, `CHN-AM-2025-001042`, `CHN-AM-2025-001062`, `CHN-AS-2025-000080`, `CHN-AV-2026-000609`.

37 truth-positive pairs touch these 10 cases.

## Arms

- **A, code only:** `Evaluator.run(ids)` from `app/eval/core.py`, unchanged (default plan → code scoring →
  `Skeptic.check`). 0 model calls.
- **B, model in the loop:** for each case, `AgentGraph(deps).run("case", {"crime_id": id})`: the product case path
  with the model Planner, Linker explanations and the Skeptic's critique with send-backs. Predicted links are the
  alerts the graph writes (approved by the Skeptic).
- **Both arms:** sample data (DuckDB twins of the named queries, `SAMPLE_MODE=true`), `engines=None` (no H-MEM
  adjustment, so memory on this machine cannot shift scores), and an in-memory store. Arm B runs one case at a
  time, sequentially, against the local Nightshift (`:8088`).

## Safety (enforced in code before any call)

The run refuses to start unless:

- `SAMPLE_MODE=true`;
- the store is in memory;
- no Supabase or Zetaris key is set or resolvable;
- fixture recording and `ENGINES_PERSIST` are off;
- a live Nightshift token is present (the same guard as `PLANTED_SKEPTIC_PREREG`).

Nothing is written to the live app: no alerts, memories, runs or traces in Supabase. Trace files go to a temp
folder, not the repo.

## Metrics

1. **Pair precision / recall / F1** for each arm, with the same `pair_metrics` and the same positives (truth pairs
   touching the 10 cases). Reported side by side, with the TP / FP / FN counts.
2. **Skeptic activity (arm B):** strikes, drops and send-backs.
3. **Planner activity (arm B):** plan rounds.
4. **Model calls (arm B):** count by lane and model, errors, and **replayed** calls. In sample mode the client falls
   back to a recorded reply when Nightshift is unreachable; any replayed call is reported, and arm B is called
   "live" only for cases with 0 replayed calls.
5. **Receipts (arm B):** how many model calls carry a Nightshift receipt, and how many of those verify with
   `scripts/verify_receipts.py`.
6. **Time:** wall time per case and in total, for each arm.

There is **no pass/fail threshold**. 10 cases cannot support a significance claim, and none will be made.

## Limits (stated before the run)

- 10 cases, synthetic data, a single run. Model output is not deterministic.
- Arm B uses the product deadline (300 s per run); a case that hits it is reported as such.
- **Hard stop 22:20 IST:** whatever has finished is committed and labelled **partial**, with the unfinished case
  ids listed.

## Output

- `output_examples/model_in_loop_eval.json`: per case and totals for both arms.
- `engg/docs/eval/MODEL_IN_LOOP_RESULTS.md`: a short results note.

Harness: `services/api/app/eval/model_in_loop.py`.

**Related:** [[PLANTED_SKEPTIC_PREREG]] · [[SKEPTIC_CONTRADICTION_PREREG]]
