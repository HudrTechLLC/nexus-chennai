---
tags: [nexus, eval, prereg]
---

# Duplicate and derivative corroboration: pre-registration (task #18)

Related: [00-INDEX](../00-INDEX.md) · [AGENTS](../AGENTS.md) · [INDEPENDENT_LOOKALIKE_PREREG](INDEPENDENT_LOOKALIKE_PREREG.md)

**Pre-registered before any run (nexus-7, 27 Oct 2026). Offline metric only. It changes no scoring or eval code (`linker.py` and `eval/core.py` are untouched), and results are published whatever they are.**

1. **Population:** the approved alerts of the headline linking eval. That is the 60 truth cases of `data/sample/_truth`, `SAMPLE_MODE=true`, `mo_cosine=off`, empty H-MEM, no model calls. The same flow as `Evaluator.evaluate_case`, re-run in a new module so that each alert's factor rows are kept.
2. **Definitions:** an alert's corroboration items are the tips, 112 calls and news rows counted in its `corroboration` factor.
   - **Derivative:** a news article (`NEWS-<crime_id>`), social post (`POST-<crime_id>`), 112 call (`calls.crime_id`) or tip (`source_row_id`) whose own source crime is **one of the two crimes in the pair**. It re-reports that FIR rather than adding independent evidence.
   - **Duplicate:** two counted items with the same normalised text. Only one counts.
3. **Metrics:**
   - (a) alerts whose corroboration factor has data;
   - (b) alerts with ≥ 1 duplicate or derivative item;
   - (c) alerts where **every** counted item is duplicate or derivative;
   - (d) **the headline:** the share of all alerts that would **lose a band** (high → medium, or medium → no alert) when the corroboration factor is recomputed with duplicates and derivatives removed and the pair is re-scored with the same `score_pair`.
4. **Prediction:** the corroboration weight is small (0.07), so (d) will be ≤ 5% of alerts. (b) is unknown, and is what this test measures. No pass/fail threshold: this is a measurement, not a gate.
5. **One pass.** The results go below a line in this note plus a JSON next to it. Any README line states the number as measured.

---

## Results (27 Oct 2026, one pass; the text above is unchanged)

Run: `cd services/api && SAMPLE_MODE=true python -m app.eval.duplicate_corroboration`. Output: `engg/docs/eval/duplicate_corroboration_results.json`.

The population matches the headline eval: **148 approved alerts** (10 high, 138 medium), the same count as `eval_report.json`.

| Metric | Result |
|---|---|
| (a) alerts whose corroboration factor has data | **9 of 148** |
| (b) alerts with ≥ 1 duplicate or derivative item | **7 of 9** |
| (c) alerts where every counted item is duplicate or derivative | **4 of 9** |
| **(d) alerts that would lose a band** | **0 of 148 (0%)** |

**What the counted items were:**
- 14 112-calls. **13 are derivative**: the call reporting one of the two crimes in the pair.
- 4 tips, all independent.
- No news article and no duplicate text among the counted items of any alert.
- Every item was found in the sample sources (0 unknown).

**Reading it:**
- Corroboration is thin in the eval: 9 of 148 alerts have it at all. Where it exists, it mostly rests on derivative evidence. In 7 of 9 alerts, at least one counted "corroborating" call is just the 112 call that reported one of the two crimes. In 4 of 9, that is all there is.
- **No band changes, for two reasons.** The weight is small (0.07). And all 9 alerts are medium, most of them held there by the coverage cap, so the score moves but the band does not.
- **Removing derivatives does not only lower scores.** When no independent item is left, the factor becomes "no data" and drops out of the weighted mean, and the pair's score can **rise**. Scores went up for 4 alerts (for example 0.924 → 1.0), down for 3 (for example 0.963 → 0.899), and stayed the same for 2. So a fix should not just delete derivative items. It should stop counting the call that reported a pair's own crime, and think about what "no corroboration" should do to the score.
- Prediction (d ≤ 5%): met (0%).

**Not done:** the linker and eval code are unchanged; nexus-3 owns those for #16. This only measures.
