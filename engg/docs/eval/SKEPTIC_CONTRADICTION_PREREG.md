---
tags: [nexus, eval, prereg]
---

# Skeptic hard-contradiction rule: pre-registration of the fresh planted test

Related: [00-INDEX](../00-INDEX.md) · [PLANTED_SKEPTIC_PREREG](PLANTED_SKEPTIC_PREREG.md) · [AGENTS](../AGENTS.md) · [DECISIONS](../DECISIONS.md)

**Status: pre-registered, not yet run.** This note is committed before the fresh case set is opened and before
any run. The results will be published whatever they are. Decided by Ravee and the chief (27 Oct 2026).
- Owner: nexus-3.
- Fresh set: built by nexus-1, blind to the rule.
- Independent reviewer: nexus-5.

## Why

The first planted test ([PLANTED_SKEPTIC_PREREG](PLANTED_SKEPTIC_PREREG.md), #392) failed: 0 of 24 planted
near-misses were dropped. The Skeptic chose `drop` on none of 32 arms, although its critique named the planted
fact in 19 of 24. That result stays published unchanged. This note pre-registers a fix and a **fresh** test of it.

## The rule (fixed now; code pinned below)

A **hard contradiction** is a stated difference between crime A and crime B on a distinctive descriptor:

| Kind | Fields | Contradiction when |
|---|---|---|
| `offender_count` | `offenders_described[].count` | both stated (> 0) and different |
| `offender_age` | `offenders_described[].age_band` | both stated and the ranges **do not overlap** (touching ranges overlap). Wordings: "20-30"/"20 to 30"; "20s" = 20-29; "30+"/"above 30" = 30-99; "under 18" = 0-18; a single age = ±5 |
| `helmet` | `offenders_described[].helmet` | both stated and incompatible |
| `vehicle_identity` | the offender vehicle's `colour`, `make_model`, `plate` | colour or make stated on both and incompatible; or the partial plates disagree on at least one of ≥ 2 positions read on both (right-aligned, `?` = unread). Plates are compared only when **both end in the plate number** (a trailing run of ≥ 4 digits or `?`), so a prefix-only plate such as "TN09B" is never compared |

**Compatible, so never a contradiction:**
- missing or unknown values ("unknown", "not seen", …);
- **less detail**: free text is compared by its content words, ignoring filler such as "with" and "helmet",
  and one set must contain the other. So "Bajaj Pulsar" fits "Bajaj Pulsar 150", and "black" fits "black helmet
  with red stripe";
- colour aliases (grey/gray, …).

"No helmet" is its own value: it contradicts any described helmet. Only **absence** phrases count ("no helmet", "without a helmet", "not wearing helmet", "bare head", "none"). "No visor" or "no sticker" describes a helmet. When a crime describes several offenders, a
field contradicts only if **no** pair of entries is compatible.

**The decision:**
- A pair the Skeptic would **approve** is **dropped in code** if it has a hard contradiction, unless the evidence
  reconciles it.
- **Reconciled** means a `forensic` or `offender_return` factor that the Skeptic's **own re-check confirmed**
  (re-checked value ≥ 0.5, not struck). Physical or identity evidence outranks witness descriptions.
- A code drop never goes to the model (`model_critique = "not_sent"`, `drop_source = "contradiction"`). Its
  critique states the contradiction.
- Pairs that are already send-back or drop are untouched. The model can still downgrade the pairs it sees, as
  before.

**Where it runs:** a separate step in `Skeptic.review()`, after `check()` and before the model critique, on
the Skeptic's own fresh rows for A and B.
- `check()` is **unchanged**, so the linking eval (`eval/core.py`) and the published `eval_report.json` do not
  include the rule (chief, decision 1).
- The step runs only in new Skeptic reviews. A review starts only from `worker.process_new_cases` (new FIRs) or
  the API `/run` endpoint (`main.py:139`, on demand). No path re-reviews or re-scores an existing alert.
- No API process auto-deploys from `main`; Vercel serves the web app only (D-019). The rule reaches production
  only on a worker restart, which needs the chief's OK **after** this test.

**Deviation from the chief's plan, approved:** the plan said "the contradiction check in code, plus the
prompt". **The prompt is unchanged** (chief, decision 2). Nightshift fixtures are keyed by a hash of the full
messages, so any prompt edit would force a live re-record of judge examples 1–3 while the reason lane is busy
with the Nemotron-alone baseline.

## Pinned inputs

| What | Value |
|---|---|
| Rule commit | `fa6445e9d96ebfd25f8a7c8d3774d8ae711b31e5` on branch `feat/skeptic-contradiction-drop` (**not merged**: it merges only if the test passes) |
| `services/api` tree at that commit | `faae63b867de44d386c1c3c50937b32ea22e9840`. The run must report this tree with `code_dirty = false`; **no rule edit after this note merges** |
| `agents/contradiction.py` sha256 | `9e088b135744b383861c7726317dbb283c2082fe645bfd0a89423764912930ac` |
| `agents/skeptic.py` sha256 | `b4ba5ded77295a3316c1235de36d7f4b6db597d2577360a8491701d16128ba9e` |
| `eval/planted_skeptic.py` sha256 | `0403f39b5420b5aca1b3c7199ceed3b6ae2d884d8c73f2e9cc3b586821f5a095` |
| Skeptic prompt sha256 (unchanged from #370) | `ae5cc6e2528372964eda33089c762dd2ffe5468638aa516bfae5bbf672ff46a2` |
| Linker rationale prompt sha256 (unchanged) | `7f3d160cb19cd9583da460820447962afe523c781990ce5de4add02a6d08b6c9` |
| Reason lane | `nvidia/nemotron-3-ultra-550b-a55b` (Nightshift) |
| Fresh case file | built by nexus-1 and pinned by sha256 in **its own PR**, merged before the run; this note does not know its contents |

The settings are the same as #370: `Skeptic.review` round 1, `critique=True`, `Linker.explain` at 0.2, sample data,
memory store, engines off. The guards are also the same.

## The fresh set (blind)

- nexus-1 builds the set with the #370 recipe (`prepare()`: series twins, one planted fact per near-miss, the
  four kinds above, each near-miss must still alert). It uses **new twins and new seeds**; set #1's crimes serve
  only as an exclusion list.
- nexus-1 has **not** seen this rule or this note. The sample has only 28 eligible pairs and set #1 used 16
  crimes, so the set will likely need newly generated series. nexus-1 reports the achievable shape before pinning.
- The target shape is 8 twins and 24 near-misses. **A smaller shape is accepted if it is pinned before the run.**

## Metrics, fixed now

- **Primary (chief):** the **planted drop rate**: near-misses dropped (by code **or** model) / near-misses
  decided. **Pass: ≥ 0.60.**
- **Guard (chief):** the **twin false-drop**: twins dropped (by code or model; a send-back is not a drop) / twins
  decided. **Pass: ≤ 1 of 8**, or a rate ≤ 0.125 for any other shape.
- **"Decided"** means a model critique was applied, or the code dropped the pair. "Unavailable" (failed or
  missing critique) is listed by id and leaves both denominators.
- **The rule ships to product only if the primary AND the guard both pass.** Then it also needs:
  - CI `judge-path` and `judge-offline` EXACT ×3 green on the PR;
  - merged by **13:30 IST**;
  - the chief's OK to restart the worker.
  If judge outputs ever change, they are regenerated by replay as in #358, labelled honestly. Otherwise this stays
  a published negative result.
- **Secondary**, all reported:
  - #370's paired metric (dropped while the twin is approved), for comparison with #392;
  - drops by source (code vs model);
  - the rates per plant kind and per twin;
  - twins approved, sent back and dropped;
  - the `features_source` split.
- **Secondary, decoy drops (chief):** the offline what-if on the linking eval. Results already known are below.
  Re-run it on the final commit and report it with the results. It never regenerates `eval_report.json`.
- **One pass, fixed order. No re-runs.**

## Known before this note (disclosed; these shaped the rule)

These checks used no model and did not touch the fresh set. I ran them while designing the rule, so they are
**not** independent evidence.
1. **The sample's true series pairs never contradict:** 0 of 97 `series` pairs in `_truth/pairs.csv`. All 49
   `decoy` pairs do, on offender count, which is how the generator builds decoys. So the twin guard will probably
   hold on generator data. Real FIRs have messier witness descriptions, and **this test cannot measure that.**
2. **Live C802 (AD-001182 ↔ AD-001231):** a first draft flagged "Bajaj Pulsar 150" vs "Bajaj Pulsar". That led to
   the less-detail rule. nexus-5's review then fixed three wordings real FIRs use: age ranges like "20s"/"30+", prefix-only
   plates, and "no visor". On the final rule, **the hero pair and C802 have no contradiction**, on sample and on live
   data (read-only `q_case`).
3. **Judge examples 1–3:** no pair among their crimes contradicts. The gate on the final rule commit gave 443 tests
   passing, ruff clean, verify_replay, and **ex1–3 EXACT**.
4. **OR-04, the one `offender_return` truth pair, DOES contradict** (count 1 vs 3, age 18-20 vs 40-50). It does not
   alert today (score 0.07), so the rule cannot change it. The reconcile clause is unit-tested, but not exercised
   through the real path on this sample: the default plan rarely computes `offender_return`.
5. **Offline what-if on the published linking eval** (sample, 60 cases, no model calls):

   | | TP | FP | FN | Precision | Recall | Alerts |
   |---|---|---|---|---|---|---|
   | As published (reproduced exactly) | 84 | 58 | 14 | 0.5915 | 0.8571 | 148 |
   | With the contradiction step | 84 | **49** | 14 | **0.6316** | 0.8571 | 139 |

   The rule dropped **9 false alerts and no true link**: 7 on offender count and 2 on age band (unique pairs). Only 1
   of the 9 is a labelled decoy; the other 8 are unlisted pairs, which the eval counts as false.

## Limits, stated before the result

- **Both numbers are weak evidence on generator data** (nexus-5's correction, adopted).
  - **The primary passes largely by construction.** The rule targets exactly the recipe's four plant kinds, and I
    designed it knowing them. A high planted drop rate mostly shows that the code does what it says, not that the
    Skeptic generalises to other false links.
  - **The guard is also close to guaranteed.** Item 1 found 0/97 generator series pairs contradict, and the fresh
    twins come from the same generator. So the guard shows only that the rule doesn't drop generator-clean twins.
  - **The real risk is not measured here:** messy witness descriptions in real FIRs.
  - **The linking what-if (item 5) is the only evidence on non-planted pairs.**
- **Deck wording (chief):** "a deterministic contradiction check drops planted false links". **Not** "the Skeptic
  now catches false links".
- Generator data is cleaner than real witness descriptions. A real series with one witness saying "two men" and
  another "one man" would be dropped unless forensic or known-offender evidence confirms it. That trade-off is
  deliberate and stated.
- As in #370: small, synthetic, two-wheeler street crime, round 1 only.

## Addendum before the run (27 Oct 2026, committed before any call on set #2)

**Declared deviation: the code was rebased; the rule is unchanged.** nexus-1's set #2 (#402) comes from a new
eval-only bundle that is selected by `NEXUS_SAMPLE_DIR`. That variable exists only from #402 on. Without it, the
same crime ids would resolve to different crimes in `data/sample`. So the rule commit was rebased onto `main` at
#402 (`5a7c549`). The only conflict was the report line, which keeps both `prereg` and #402's `sample_dir`.

| What | Pre-registered | Run commit |
|---|---|---|
| Commit | `fa6445e9d96ebfd25f8a7c8d3774d8ae711b31e5` | **`9259e78fbd7743d22ef8b1d92e9771f468f68993`** (same branch, rebased) |
| `services/api` tree | `faae63b8…` | **`e8371adc3ab378a4d3d8f9760fe3508bbf9beee2`** (includes #402) |
| `agents/contradiction.py` sha256 | `9e088b13…930ac` | `9e088b135744b383861c7726317dbb283c2082fe645bfd0a89423764912930ac` (**byte-identical**) |
| `agents/skeptic.py` sha256 | `b4ba5ded…128ba9e` | `b4ba5ded77295a3316c1235de36d7f4b6db597d2577360a8491701d16128ba9e` (**byte-identical**) |
| `tests/agents/test_contradiction.py` sha256 | (at fa6445e) | `1372c8638ac8f1a4f6168d2e9635abb70dd66837f27b4634e26daa072b770961` (byte-identical to fa6445e) |
| `eval/planted_skeptic.py` sha256 | `0403f39b…` | **`ee536e3d8ebe192263986c2c9ab58ece9caab3f6f618d8f1b6478f4c30ebead0`** (mine merged with #402's bundle loader and its refusal guard) |

The gate on `9259e78`: 443 tests passed, ruff clean, verify_replay, judge ex1–3 EXACT. The prompts are unchanged.

**The fresh set, as nexus-1 delivered it** (#402, merged as `5a7c549`):

| What | Value |
|---|---|
| Case file | `engg/docs/eval/planted_skeptic_cases_set2.json` |
| sha256 | `b77276cb21809dd7b5e3a7c5a7bf7c8e42989c1e180a031d1eacecc00989a85f` |
| Bundle | `data/eval/planted2/sample`, generator seed 1027 (eval-only); `run()` refuses any other bundle |
| Shape | 8 twins and 24 near-misses (the full target), all of which reach the Skeptic; 16 distinct crimes, none from set #1; 5 series |
| Kinds | `offender_count` 8, `offender_age` 8, `vehicle_identity` 5, `helmet` 3 (same fixed rotation as set #1) |
| `features_source` | **all `generator_truth`**. The bundle has no stored extractions, so the by-source split has one bucket |
| Dry run (nexus-1) | all 32 arms ran with the model stubbed to fail: no traceback, all alert, critique "unavailable" as expected |

**The run** (clean shell, no live credentials loaded; the harness guard refuses otherwise):

    cd services/api
    SAMPLE_MODE=true NEXUS_STORE=memory NEXUS_SAMPLE_DIR=data/eval/planted2/sample \
      METERLESS_RUNTIME_TOKEN_FILE=<Nightshift token path> \
      python -m app.eval.planted_skeptic run --cases ../../engg/docs/eval/planted_skeptic_cases_set2.json \
        --expect-sha b77276cb21809dd7b5e3a7c5a7bf7c8e42989c1e180a031d1eacecc00989a85f \
        --out ../../output_examples/skeptic_contradiction.json \
        --prereg engg/docs/eval/SKEPTIC_CONTRADICTION_PREREG.md

The report must show `code_sha = 9259e78…` and `code_dirty = false`. The metrics, pass rules and "publish whatever
happens" are exactly as above; nothing is changed by this addendum.
