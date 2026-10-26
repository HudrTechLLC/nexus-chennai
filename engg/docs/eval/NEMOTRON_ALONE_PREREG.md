---
tags: [nexus, eval, prereg]
---

# Nemotron alone: pre-registration

Does Nexus add anything over just asking the strongest model? This baseline gives the reason-lane model
(Nemotron Ultra) each candidate pair's raw evidence and asks it, with no Nexus scoring at all, whether
the same offender or group committed both crimes. It's scored against the full system **on the same pairs,
with the same truth**. Everything below is fixed before any model call. The result is published whatever
it shows.

Related: [00-INDEX](../00-INDEX.md) · [EVIDENCE](../submission/EVIDENCE.md) · [DECISIONS](../DECISIONS.md) · [AGENTS](../AGENTS.md)

## 1. What is held fixed

| Item | Value | Where |
|---|---|---|
| Truth | `data/sample/_truth`, the headline's truth. sha256 of every file recorded. | `nemotron_alone/cases.json` → `truth_sha256` |
| Headline | `output_examples/eval_report.json`, run `eval_ad27b22c`, code `8d8e789`: TP 84 / FP 58 / FN 14, 148 alerts | `cases.json` → `headline` |
| Cases and pairs | 20 cases, 182 pairs, each with the full system's decision | `nemotron_alone/cases.json` |
| Prompt | Exact system and user text, model, temperature | `nemotron_alone/prompt.json` |
| Model | `nvidia/nemotron-3-ultra-550b-a55b` on the `reason` lane, temperature 0, thinking on (the lane default) | `prompt.json` |
| Code | `python -m app.eval.nemotron_alone select` / `run` | `services/api/app/eval/nemotron_alone.py` |

## 2. How the pairs were chosen (no model output involved)

- **Pairs are not re-derived.** `select` reruns the headline evaluator itself (`Evaluator.evaluate_case`,
  sample data, no Zetaris key, no model calls). It refuses to write anything unless it reproduces the
  headline exactly: TP 84 / FP 58 / FN 14 and 148 alerts.
  - The headline report has counts but no pair list, so these counts are the comparison point.
  - A separate census run at the headline's commit `8d8e789` and at `570e177` produced byte-identical
    candidates and decisions for all 60 cases, so blocking has not changed since the headline.
- **Cases:** every 3rd of the 60 headline cases in sorted order (indices 0, 3, …, 57), 20 cases.
- **Pairs:** each case's first 10 candidates in the blocker's own order (`q_candidates`: `km_apart`,
  then `crime_id`), which means the 10 nearest. This depends only on the blocker, never on truth or on
  either system's answer. A pair reached from two cases is listed once.
- **Why 10:** the call budget, not results. Ultra's past calls in this project's traces have p50 32 s and
  p90 66 s (186 calls). Nightshift is serial and shared, so ~180 pairs (1.6 h at p50, 3.3 h at p90) is
  what fits after nexus-3's planted test without crowding the 15:30 screen freeze.
  - Stated openly: while sizing this, I saw how many truth positives fall in the first K candidates for
    several K. K was set by the budget.
- **`generated_at_commit`** in `cases.json` is the `main` commit the PR branch was based on when
  `select` ran (the selector code itself is in this PR). It is excluded from the byte check.
- **System decision per pair:** `system_linked` is whether the pair is in the headline's alert set over
  all 60 cases (linker alert and Skeptic approve). These are the same decisions the headline counted.

## 3. What the model sees

One call per pair. The user message is `prompt.json` → `user_template`, with `{evidence}` replaced by a
JSON object:

- per crime (A, B): category, sub type, occurred from/to, address, weapon, offenders described,
  victims, vehicles, property, narrative, witness statement texts, and the extracted MO features
  (`mo`, `visual_tags`, `entities`) where the headline had them;
- `distance_km` (haversine) and `hours_between_start_times`.

Left out on purpose: crime id, FIR number, station, source ids, H3/geohash cells, extractor receipts,
any Nexus score, band, rationale or Skeptic verdict. `run` asserts, before every call, that the payload
contains no crime id of the pair and no truth key, label, group id, series id or series name from
`_truth/`. A failed assert stops the run.

## 4. Scoring

- **Link** is the model's boolean `link`. Confidence is reported, never thresholded.
- **Metric:** precision, recall and F1 with the headline's `pair_metrics`, on exactly the scored pair set,
  for both the model and the full system. Truth `duplicate` pairs are excluded, as in the headline.
- **Recall is reported twice:**
  - against the positives inside the pair set;
  - against all positives that touch the completed cases. Here the full system counts its **whole**
    headline alert set for those cases (`system_alerts_touching_cases` in `cases.json`, any candidate rank),
    while the model has only seen the 10 nearest. This line shows what blocking plus scoring reach
    beyond the pairs the model was shown.
- Counts (TP/FP/FN) are always shown next to the ratios. With ~20 positive pairs the error bars are wide.

## 5. Failure and stop rules

- A call goes through the project's standard `chat_json` handling: one corrective retry on invalid JSON,
  and one doubling of `max_tokens` if the reply is cut off.
  - If it still fails, or the reply was replayed rather than live, the pair counts as **no link**, with
    `status: failed`.
  - The number of failed calls is reported.
- Cases run in the committed order. Three consecutive failed calls stop the run (Nightshift is down;
  carrying on would just add no-links).
- `--stop-at` sets a time after which no new case starts.
- **Only fully completed cases are scored**, for both systems, on the same subset. A resumed run reuses
  completed cases verbatim.

## 6. Isolation

- Sample mode only: `run` exits unless `SAMPLE_MODE=true` with no Zetaris key, and it needs a live
  Nightshift token (otherwise sample mode would replay fixtures).
- **No Supabase writes:** the module never imports the Supabase client (a test enforces this). Output is a
  local file.
- The judge outputs (`eval_report.json` and others) are not touched.

## 7. Order of events

1. Commit 1: `nemotron_alone/cases.json` alone. It contains no model output, and no model call for
   this baseline had been made.
2. Commit 2: the prompt, the code, tests and this note.
3. That PR merges.
4. After nexus-3's planted test frees Nightshift: `run`, from `main`.
5. A **separate, later PR** publishes `output_examples/nemotron_alone.json` and the comparison, before
   the 19:00 IST evidence freeze.

To check this (reviewer nexus-6):

- `git log --follow` on `cases.json` against the results file;
- `python -m app.eval.nemotron_alone select` from `main` must reproduce `cases.json` byte for byte
  (except `generated_at_commit`). It always writes LF line endings, on every OS;
- `pytest tests/eval/test_nemotron_alone.py`.
