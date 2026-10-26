---
tags: [nexus, eval, prereg]
---

# Planted false-link test for the Skeptic: pre-registration

Related: [00-INDEX](../00-INDEX.md) · [AGENTS](../AGENTS.md) · [DECISIONS](../DECISIONS.md)

**Status: pre-registered, not yet run.** This note, the case file and the harness are committed **before any model
call** for this test. The results will be published as `output_examples/planted_skeptic.json` whatever they are, in a
later commit. Approved by Ravee and the chief (27 Oct 2026). Owner: nexus-3. Independent reviewer: nexus-5.

## Question

When a pair *looks* like a true link but one fact makes the link false, does the Skeptic reject it? Does it still
approve the same pair without the false fact?

## What is measured, exactly

- **The unit is `Skeptic.review` called directly**, round 1, `critique=True`, on the pair as the Linker scored it. In
  production the Skeptic only sees pairs above the alert threshold, so the pairs are fed to its function rather than
  through the agent graph. This measures **the Skeptic's verdict on alerting pairs**, not the whole pipeline.
- **The code re-check cannot reject a planted pair.** The Skeptic re-reads both crimes, but it reads the same planted
  rows the Linker did, so its recompute matches and no factor is struck. **Every rejection comes from the model
  critique** (`reason` lane).
- **Production settings, held fixed.**
  - Linker rationale: `Linker.explain` at temperature 0.2, as in production, because the Skeptic's prompt includes it.
  - Skeptic critique: temperature 0, budget `reason_budget(1)` = 3,584 tokens, one pair per call.
  - Pair support: the Planner's deterministic default plan (no Planner model call).
  - H-MEM and the World Model are **off** (engines = None), so no memory delta moves any score.
- **Data:** the bundled sample (`data/sample/`; the Zetaris named queries run on their DuckDB twins). No Zetaris load,
  no Supabase writes, no alerts, no notifications, no fixtures recorded. The run uses the memory store.

## Design: paired, single planted fact

- **Population.** Ground-truth SERIES pairs from `data/sample/_truth/pairs.csv`, keeping only pairs where:
  - **neither crime is excluded:** the hero pair (CHN-AD-2026-001182, CHN-VL-2026-000877), C802
    (LA-2026-C802D4F2E02B = AD-001182 + CHN-AD-2026-001231), the held cases (CHN-CM-2025-000450,
    CHN-TU-2025-000437), and **every crime id in the judge inputs and outputs** (`input_examples/`,
    `output_examples/example_*.json`). The full list is in the case file;
  - **both crimes have stored features.** There is no extraction, so no model call is made while building the set;
  - **the Linker alerts on the unaltered pair.**
  - Result: 28 eligible series pairs, of which **10 qualify, all members of the Red Pulsar series (none of them the
    hero pair)**. 18 were skipped for missing stored features (legacy 2025 crimes); each is listed with its reason
    in the case file.
- **Twin (control):** each of the 10 base pairs, unaltered. Expected: **approve**.
- **Near-miss:** the same pair with **exactly one planted false fact in crime B**. Two near-misses per base pair, with
  different facts, give **20 near-misses**. Expected: **drop**.
- **Plant kinds**, 4 each, assigned by a fixed rotation and never retried:

  | Kind | B is rewritten to say | Where it appears |
  |---|---|---|
  | `vehicle_colour` | a different vehicle colour (red → blue) | `vehicles[].colour`, "red motorcycle" / `red_motorcycle` in statements, narrative and tags; the helmet's "red stripe" is untouched |
  | `vehicle_make` | a different make (Bajaj Pulsar 150 → Hero Splendor Plus) | `make_model`, narrative, statements, tags |
  | `offender_count` | a different number of offenders (2 → 1; 4 would make B implausible on its own) | `offenders_described[].count`, `mo.offender_count`, "two unknown persons" / "I saw two men" (singular) |
  | `offender_age` | a different age band (20-30 → 50-60) | `offenders_described[].age_band`, "aged about 20 to 30"; the victim's age is untouched |
  | `helmet` | a different helmet (black with red stripe → plain yellow) | `offenders_described[].helmet`, `mo.disguise`, tags, narrative, statements |

  A sixth kind, `simultaneous` (B moved to 2 minutes after A while ≥ 5 km away), applied to **no** eligible pair, as
  all are under 5 km apart. It stays in the code, unused.
- **Coherence.** B is rewritten everywhere the fact appears, so it stays internally consistent and conflicts only
  with A. Narrative pronouns ("They used…") are not rewritten for the count plant. The narrative and statements are
  not part of what the Skeptic's prompt shows (`factor_payload`: when, where, vehicles, described offenders, weapon,
  MO, visual tags).
- **Planted scores, recorded now (code only).** All 20 near-misses still alert, so all reach the Skeptic. None was
  stopped by the Linker. Colour and make plants move the Linker's score by at most 0.001 (the code factors barely use
  them); count, age and helmet plants lower it by 0.04–0.09. Every score is in the case file.

## Metrics and labels, fixed now

- **Primary:** the share of near-misses the Skeptic **drops while it approves their twin**. The denominator is
  near-misses where both arms got an applied model critique.
- **`send_back` does not count as a rejection in the primary metric.** Since #358, a send-back whose re-score is
  unchanged ends approved by the revision cap, so in production it does not remove the link.
- **Secondary:**
  - planted dropped (twin ignored);
  - planted dropped or sent back;
  - twins approved / sent back / dropped;
  - each of these by plant kind.
- **Unavailable critiques** (`critique_failed`, `critique_missing`, a failed call) are **listed by id** and leave
  the denominator. They are never counted as either verdict.
- **Pass threshold:** **primary rate ≥ 0.60** (at least 12 of 20). The result is reported whatever it is, with the
  per-kind breakdown and every critique text.
- **One pass, fixed order** (twin, then its two near-misses, then the next case). **No re-runs** of any arm.

## Pinned inputs

| What | Value |
|---|---|
| Case file | `engg/docs/eval/planted_skeptic_cases.json` |
| Case file sha256 | `f57cc57fc246504720acfd82302cf1685bf39bfcbc56d8068e42badf742b56fd` |
| Skeptic prompt sha256 (`SKEPTIC_PROMPT`) | `ae5cc6e2528372964eda33089c762dd2ffe5468638aa516bfae5bbf672ff46a2` |
| Linker rationale prompt sha256 (`RATIONALE_PROMPT`) | `7f3d160cb19cd9583da460820447962afe523c781990ce5de4add02a6d08b6c9` |
| Reason lane | `nvidia/nemotron-3-ultra-550b-a55b` (Nightshift, pinned) |
| Code base | the merge commit of this PR on `main`, recorded in the report as `code_sha` (the branch is cut from `ae5c8e2`) |
| Harness | `services/api/app/eval/planted_skeptic.py`; tests in `tests/eval/test_planted_skeptic.py` |

The tests check that the case file is byte-for-byte what `prepare` produces, that its sha256 is the one above, that
the prompt hashes are unchanged, and that each near-miss changes only its own fact in B.

## How it runs (step 2, after this note merges)

    cd services/api
    SAMPLE_MODE=true NEXUS_STORE=memory METERLESS_RUNTIME_TOKEN_FILE=<Nightshift token path> \
      python -m app.eval.planted_skeptic run --cases ../../engg/docs/eval/planted_skeptic_cases.json \
        --expect-sha f57cc57fc246504720acfd82302cf1685bf39bfcbc56d8068e42badf742b56fd \
        --out ../../output_examples/planted_skeptic.json

The harness refuses to run if:
- the case file hash differs;
- `SAMPLE_MODE` is not true;
- any of `SUPABASE_*`, `ZETARIS_API_KEY*`, `NEXUS_RECORD_FIXTURES` or `ENGINES_PERSIST` is set;
- the store is not memory;
- there is no Nightshift token. Without one the critique would be a replay, not a live call.

After the run, `git status` must show no change under `data/sample/model_fixtures/` or `output_examples/example_*`.
About 30 arms × 2 Ultra calls ≈ 40–60 min. Nightshift then goes to nexus-2 for the Nemotron-alone baseline.

## Limits, stated before the result

- **One series.** All 10 base pairs are Red Pulsar chain snatchings, so the result says nothing about other crime
  types.
- **The planted facts are clean, structured contradictions.** Real false links are messier; this is a floor test of
  "does the Skeptic notice a stated mismatch", not a field accuracy figure.
- **No memory, one pair per call.** Production batches pairs into one critique call and may add H-MEM context.
- **Round 1 only.** The send-back loop and the revision cap are out of scope.
