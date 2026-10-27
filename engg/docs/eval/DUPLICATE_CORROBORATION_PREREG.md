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
