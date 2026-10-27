---
tags: [nexus, eval, prereg]
---

# Stronger baseline (rules + vehicle): pre-registration

The judges called the rules-only baseline a strawman (same category, ≤ 2 km, ≤ 14 days: P 0.09 / R 0.30). This adds a **second, stronger baseline** that also uses the vehicle and plate evidence an analyst would cross-check. Everything below is fixed **before the first run**, and the result is published whatever it shows. The rules-only baseline and every existing key in `eval_report.json` stay unchanged.

1. **Population and truth:** the same evaluation as the headline: the same 60 cases, the same candidate pairs (the `q_candidates` blocking of the default plan), the same truth (`data/sample/_truth`). Offline, sample mode, **no model calls**.
2. **Vehicle match** between two crimes means: each has at least one offender vehicle (`role = used_by_offender`), and some pair of them either
   - has **both plates present** and compatible, right-aligned, with **≥ 4 known characters agreeing and none conflicting** (e.g. `TN09??4471` ~ `TN09B?4471`); or,
   - when either plate is missing, has the **same vehicle type and the same colour**.

   Plates that conflict mean no match, even when colour and type agree.
3. **Primary, `baseline_rules_plus_vehicle`:** link = same category **AND** (≤ 2 km and ≤ 14 days **OR** vehicle match). **Secondary, `strict`:** same category **AND** ≤ 2 km and ≤ 14 days **AND** vehicle match. Both are reported; the primary is the one to quote.
4. **Metrics:** precision, recall and F1 over pairs (the same `pair_metrics` as the headline), plus alerts and false alerts per 100 cases, added to `output_examples/eval_report.json` as one new key. No threshold or definition is tuned after seeing results.
5. **Reported to the chief whatever the numbers are**, including if this baseline beats the agent on either metric.

Related: [NEMOTRON_ALONE_PREREG](NEMOTRON_ALONE_PREREG.md) · [00-INDEX](../00-INDEX.md)
