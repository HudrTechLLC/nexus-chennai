---
tags: [nexus, eval, prereg]
---

# Planted false-link test for the Skeptic: pre-registration

Related: [00-INDEX](../00-INDEX.md) · [AGENTS](../AGENTS.md) · [DECISIONS](../DECISIONS.md)

**Status: pre-registered, not yet run.** This note, the case file and the harness are committed **before any model
call** for this test. The results will be published as `output_examples/planted_skeptic.json` whatever they are, in a
later commit. Approved by Ravee and the chief (27 Oct 2026). Owner: nexus-3. Independent reviewer: nexus-5.

**Revision 2 (before any run), after nexus-5's review and the chief's requests:**
- The vehicle plant became `vehicle_identity`: a *different vehicle*, so B's partial plate and B's ANPR reads change
  too. A colour-only plant left B with A's plate, which is a contestable label.
- The run guard checks the *resolved* settings (.env and `*_FILE`), not just environment variables.
- The base was widened from 10 pairs over 5 crimes in one series to 8 pairs over 16 distinct crimes in 5 series.
- The independence and rationale-path notes below were added.

## Question

When a pair *looks* like a true link but one fact makes the link false, does the Skeptic reject it? Does it still
approve the same pair without the false fact?

## What is measured, exactly

- **The unit is `Skeptic.review` called directly**, round 1, `critique=True`, on the pair as the Linker scored it. In
  production the Skeptic only sees pairs above the alert threshold, so the pairs are fed to its function rather than
  through the agent graph. This measures **the Skeptic's verdict on alerting pairs**, not the whole pipeline.
- **The code re-check cannot reject a planted pair.** The Skeptic re-reads both crimes (q_case, q_features and the
  ANPR trail), but it reads the same planted rows the Linker did, so its recompute matches and no factor is struck.
  **Every rejection comes from the model critique** (`reason` lane).
- **What the model sees.** Both the Linker rationale and the Skeptic critique are built from `factor_payload`: when,
  where, vehicles, described offenders, weapon, MO, visual tags, factor values and evidence row ids. The narrative and
  witness statements are **not** in either prompt. They are rewritten anyway so B stays coherent, but they don't reach
  the model directly or through the rationale.
- **Production settings, held fixed.**
  - Linker rationale: `Linker.explain` at temperature 0.2, as in production; the Skeptic's prompt includes it.
  - Skeptic critique: temperature 0, budget `reason_budget(1)` = 3,584 tokens, one pair per call.
  - Pair support: the Planner's deterministic default plan (no Planner model call).
  - H-MEM and the World Model are **off** (engines = None).
- **Data:** the bundled sample (`data/sample/`; the Zetaris named queries run on their DuckDB twins). No Zetaris load,
  no Supabase writes, no alerts, no notifications, no fixtures recorded; the memory store only.

## Design: paired, single planted fact

- **Population.** Ground-truth SERIES pairs from `data/sample/_truth/pairs.csv`, with neither crime excluded:
  - the hero pair (CHN-AD-2026-001182, CHN-VL-2026-000877);
  - C802 (LA-2026-C802D4F2E02B = AD-001182 + CHN-AD-2026-001231);
  - the held cases (CHN-CM-2025-000450, CHN-TU-2025-000437);
  - **every crime id in the judge inputs and outputs**.

  The list is built from the files and recorded in the case file.
- **Twins (controls), one per crime.** Pairs are taken per series in file order, and only if neither crime is
  already used and the Linker alerts on the unaltered pair. The result is **8 twins over 16 distinct crimes in 5
  series and 3 crime types**:

  | Series | Twins | Crime type |
  |---|---|---|
  | Red Pulsar (not the hero pair) | 2 | chain snatching |
  | G19 | 2 | chain snatching |
  | G01 | 2 | chain snatching |
  | G06 | 1 | street robbery |
  | G02 | 1 | mobile snatching |

  Expected verdict for a twin: **approve**.
- **Features:** stored features where they exist (the 4 Red Pulsar crimes). The other 12 crimes have none stored in
  the sample, so they use their series' **generator ground-truth MO** (`_truth/series.json`, `true_mo`), with no
  visual tags. That means no extraction and no model call. The case file marks each crime's `features_source`. Twin and
  near-miss share the same features, so this cannot favour either arm.
- **Near-misses:** each twin with **exactly one planted false fact in crime B**. Three per twin, each a different
  fact, give **24 near-misses**. Expected verdict: **drop**.
- **Plant kinds**, assigned by a fixed rotation over the kinds that apply to the pair and never retried:

  | Kind | n | B is rewritten to say | Where it appears |
  |---|---|---|---|
  | `vehicle_identity` | 3 | a **different vehicle**: its colour (red → blue) or its make (Yamaha FZ → Bajaj Platina), alternating, **and**, when both crimes record matching plate digits, a different partial plate | `vehicles[]` colour or make and plate, B's **ANPR reads**, entities, tags, narrative, statements; the helmet's "red stripe" is never touched. Applies only when the plates agree (same digits) or are both absent |
  | `offender_count` | 7 | a different number of offenders (2 → 1; 4 on a two-wheeler would make B implausible on its own) | `offenders_described[].count`, `mo.offender_count`, an MO label that states it (`knife_threat_two_men` → `…one_man`), "two unknown persons" / "I saw two men" |
  | `offender_age` | 7 | a different age band (20-30 → 50-60) | `offenders_described[].age_band`, "aged about 20 to 30"; the victim's age is untouched |
  | `helmet` | 7 | a different helmet (black with red stripe → plain yellow; no helmet → white full-face) | `offenders_described[].helmet`, `mo.disguise`, tags, narrative, statements |

  `vehicle_identity` is the smallest group (3): the plates of most G-series pairs disagree, are missing on one side,
  or have unread digits. Its per-kind rate is too small to interpret alone. `simultaneous` (B moved to 2 minutes after
  A while ≥ 5 km away) applied to no pair and is unused.
- **Planted scores, recorded now (code only).**
  - All 24 near-misses still alert, so all reach the Skeptic; the Linker stopped none.
  - `vehicle_identity` with a plate change lowers the score by 0.15–0.18. Without a plate it moves the score by
    about 0.03.
  - Count, age and helmet plants lower it by 0.04–0.14.
  - Every score is in the case file.

## Independence (read before quoting a rate)

The **8 twins are the independent units**: 16 distinct crimes, none shared between twins. The 24 near-misses are 3
variations of each twin's pair, so they are **not** 24 independent trials. Results are reported per twin as well as
per near-miss.

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
- **Pass threshold:** **primary rate ≥ 0.60** (at least 15 of 24). The result is reported whatever it is, with the
  per-kind and per-twin breakdowns and every critique text.
- **One pass, fixed order** (each twin, then its three near-misses). **No re-runs** of any arm.

## Pinned inputs

| What | Value |
|---|---|
| Case file | `engg/docs/eval/planted_skeptic_cases.json` |
| Case file sha256 | `0e975d821aaf31c1e2e807b7b8a91128d2a062f373cf685773c0c65ff75f3c4f` |
| Skeptic prompt sha256 (`SKEPTIC_PROMPT`) | `ae5cc6e2528372964eda33089c762dd2ffe5468638aa516bfae5bbf672ff46a2` |
| Linker rationale prompt sha256 (`RATIONALE_PROMPT`) | `7f3d160cb19cd9583da460820447962afe523c781990ce5de4add02a6d08b6c9` |
| Reason lane | `nvidia/nemotron-3-ultra-550b-a55b` (Nightshift, pinned) |
| Code base | the merge commit of this PR on `main`, recorded in the report as `code_sha`, with `code_dirty` |
| Harness | `services/api/app/eval/planted_skeptic.py`; tests in `tests/eval/test_planted_skeptic.py` |

The tests check:
- the case file is byte-for-byte what `prepare` produces, and its sha256 is the one above;
- the prompt hashes are unchanged;
- each near-miss changes only its own fact in B. The allowed paths are listed per kind, and A's plate is gone from B
  for a plate plant;
- B's ANPR reads carry the planted plate while A's don't;
- the guards refuse to run.

## How it runs (step 2, after this note merges)

    cd services/api
    SAMPLE_MODE=true NEXUS_STORE=memory METERLESS_RUNTIME_TOKEN_FILE=<Nightshift token path> \
      python -m app.eval.planted_skeptic run --cases ../../engg/docs/eval/planted_skeptic_cases.json \
        --expect-sha 0e975d821aaf31c1e2e807b7b8a91128d2a062f373cf685773c0c65ff75f3c4f \
        --out ../../output_examples/planted_skeptic.json

The harness refuses to run if:
- the case file hash differs;
- `SAMPLE_MODE` is not true;
- any of `SUPABASE_*`, `ZETARIS_API_KEY*`, `NEXUS_RECORD_FIXTURES` or `ENGINES_PERSIST` is set in the environment;
- the **resolved settings** carry a Zetaris key, a Supabase URL or key, or a non-memory store. These can come from
  `.env` or a `*_FILE` path; a Zetaris key would make "sample mode" query live Zetaris;
- there is no Nightshift token. Without one the critique would be a replay, not a live call.

After the run, `git status` must show no change under `data/sample/model_fixtures/` or `output_examples/example_*`.
About 32 arms × 2 Ultra calls ≈ 45–70 min. Nightshift then goes to nexus-2 for the Nemotron-alone baseline.

## Limits, stated before the result

- **Small and synthetic.** There are 8 independent twins, all two-wheeler snatchings or robberies from the
  generator's series. Nothing here generalises to house breaks, cab robberies or messy real FIRs.
- **Generator-truth features** for 12 of the 16 crimes stand in for extracted ones. These MO labels are cleaner than
  live extraction.
- **The planted facts are clean, structured contradictions.** This is a floor test of "does the Skeptic notice a
  stated mismatch", not a field accuracy figure.
- **No memory, one pair per call, round 1 only.** Production batches pairs, may add H-MEM context, and loops on
  send-backs.
