---
tags: [nexus, eval, results]
---

# Nemotron alone: results

The pre-registered baseline ([NEMOTRON_ALONE_PREREG](NEMOTRON_ALONE_PREREG.md), merged in #366 before any
model call) has been run once, from `main` at `063dfc0`. The raw output, one row per pair with the model's
answer, confidence, reason, receipt id and time, is in `output_examples/nemotron_alone.json`. It is
published as it came out; nothing was re-run or tuned.

Related: [00-INDEX](../00-INDEX.md) · [NEMOTRON_ALONE_PREREG](NEMOTRON_ALONE_PREREG.md) · [EVIDENCE](../submission/EVIDENCE.md)

## Run

| | |
|---|---|
| Model | `nvidia/nemotron-3-ultra-550b-a55b` (every reply routed to it), reason lane, temperature 0 |
| When | 27 Oct 2026, 02:29 to 03:37 IST, serial, after nexus-3's planted-Skeptic test freed Nightshift |
| Cases / pairs | **20 of 20 cases completed, 182 of 182 pairs scored**; no early stop |
| Failed calls | **0** (no timeouts, no unparsable or replayed replies) |
| Model time | 67.9 min in total; per pair p50 16.5 s, p90 43.5 s |
| Supabase writes | 0 (sample data, local output file) |

## Same pairs, same truth (the pre-registered metric)

Both systems are scored on exactly the 182 committed pairs, duplicates excluded as in the headline.

| On the 182 pairs (14 true links among them) | TP | FP | FN | Precision (95% CI) | Recall (95% CI) | F1 |
|---|---|---|---|---|---|---|
| Nemotron Ultra alone | 14 | 7 | 0 | 0.667 (0.45–0.83) | 1.000 (0.78–1.00) | 0.800 |
| Full Nexus system | 11 | 7 | 3 | 0.611 (0.39–0.80) | 0.786 (0.52–0.92) | 0.688 |

**Only 14 true links, so the error bars are wide.** The intervals (Wilson, 95%) describe each system on its
own. Because both judged the *same* pairs, the right comparison is paired (McNemar, exact two-sided):

- The two agreed on 171 of 182 pairs. Nemotron alone linked 7 pairs the system did not; the system linked 4
  the model did not. p = 0.55.
- Among the 14 true links, the model alone found 3 the system missed, and the system alone found 0 the model
  missed. p = 0.25.

Neither difference is significant. Read it as "the model alone judges a shown pair about as well as the full
system", not as a ranking. The model's mean stated confidence on its links was 0.90 (reported, never
thresholded).

## Reach: what the 10-pair cap hid

| All 49 true links touching the 20 cases | Found | Share (95% CI) |
|---|---|---|
| Full Nexus system (its whole headline alert set, any candidate rank) | 41 | 0.84 (0.71–0.91) |
| Nemotron Ultra alone (only the 10 nearest candidates per case were shown) | 14 | 0.29 (0.18–0.42) |

35 of the 49 true links are not among each case's 10 nearest candidates. They **are** in the same blocker's
candidate set; what kept them from the model is this experiment's own cap of 10 pairs per case, a call-budget
choice, not anything the model got wrong. The system scores every candidate (median 108 per case), so it
reaches them. This table is about coverage under a budget, not judgement quality.

## What this says

- **On a pair it is shown, Ultra alone is as good a judge as the full pipeline.** We don't claim the agents
  beat the model at judging one pair.
- **The pipeline's value is in cost and coverage, and in everything around the judgement:**
  - It scores every candidate with 0 model calls, about 0.83 s per case in the headline. Here the model needed
    about 3.4 min of Ultra time per case for about 9 pairs.
  - Showing the model every candidate instead (5,750 unique candidate pairs across the 60 headline cases)
    would take roughly 26 hours of serial Ultra time at the observed p50. Under any realistic budget, the
    model alone sees a fraction of the pairs, which is the 14 of 49 above.
  - Evidence, traceability, and the officer-facing explanation the pipeline adds.

## Disclosures

- Pair count K = 10 per case was set by the Nightshift call budget. While sizing it, I saw how many truth
  positives fall in the first K candidates for several K (pre-registration §2).
- The trace file `logs/trace-nemotron_alone.jsonl` on the run machine also holds earlier mocked test calls
  (01:39–01:50 IST). The run's own calls are the receipts in the output JSON, all after 02:29 IST.
- Synthetic sample data (the headline's), not live crime data.
