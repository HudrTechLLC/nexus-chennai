---
tags: [nexus, eval, prereg]
---

# Independent look-alike test of the Skeptic contradiction rule: pre-registration

Related: [00-INDEX](../00-INDEX.md) · [SKEPTIC_CONTRADICTION_PREREG](SKEPTIC_CONTRADICTION_PREREG.md) · [PLANTED_SKEPTIC_PREREG](PLANTED_SKEPTIC_PREREG.md) · [AGENTS](../AGENTS.md)

**Status: pre-registered 27 Oct 2026, 14:52 IST, before any case was written and before any run.** The results will be published whatever they are, below a line added after the run. The text above that line will not change.
- Asked for by: the chief (task #19), after judges said the 24/24 result ([SKEPTIC_CONTRADICTION_PREREG](SKEPTIC_CONTRADICTION_PREREG.md)) only shows the rule working on look-alikes from our own generator.
- Owner and sole case author: nexus-7.

## What this test can and cannot show (read first)

- **It tests the deterministic contradiction rule only, offline.** The Skeptic's model critique is **not** exercised. Hand-written pairs have no recorded Nightshift reply (fixtures are keyed by a hash of the full messages), and this test makes no live model calls.
- **It is independent of the generator, not blind to the rule.** The author read the published rule specification in [SKEPTIC_CONTRADICTION_PREREG](SKEPTIC_CONTRADICTION_PREREG.md) and the rule's code (`agents/contradiction.py`, to learn which fields it reads) before writing the cases. The author has **not** opened the generator's plant code: `cities/chennai/generator/`, `eval/planted_skeptic.py` (`prepare()`), or `planted_skeptic_cases*.json`. Those files are opened only after the run, to label any overlap.
- **The Extractor is bypassed.** The rule reads extracted, structured fields (`offenders_described[]`: `count`, `age_band`, `helmet`; offender `vehicles[]`: `colour`, `make_model`, `plate`). The cases are written at that level, so robustness to narrative wording in an FIR is **not** tested. The variation is in the **values** an extractor could plausibly produce.
- **One author wrote every case.** No second builder or reviewer is involved.

## Hypothesis

The 24/24 drop rate was by construction: the planted facts were exactly the rule's four kinds, in the generator's wording. On look-alike false links written independently, the rule will drop **fewer**:
- it should catch differences in its own fields when the values parse (digits, plain colours, makes);
- it should miss differences stated in wording it can't parse (ages in words, counts as text);
- it should miss, by design, differences outside its fields (time of day, weapon, target, approach).

It may also wrongly drop some true pairs whose witnesses disagree.

## The rule under test (pinned, unchanged)

| What | Value |
|---|---|
| `main` at pre-registration | `2f9b415c9d798f8d762e99f7f00d538762f0697a` |
| `services/api` tree | `ecb60b9f95600c121de420f928e4ea0fdba11646` |
| `agents/contradiction.py` sha256 | `9e088b135744b383861c7726317dbb283c2082fe645bfd0a89423764912930ac` (the same as pinned in #422) |
| `agents/skeptic.py` sha256 | `b4ba5ded77295a3316c1235de36d7f4b6db597d2577360a8491701d16128ba9e` (the same as pinned in #422) |

**How it is run.** A new script, `services/api/app/eval/independent_lookalike.py`, calls `contradiction.contradictions(a, b)` on each pair's two feature records. It applies the same decision as `Skeptic.contradiction_step`: a pair is **dropped** when it has at least one hard contradiction and nothing reconciles it.
- Every pair is treated as one the Skeptic would otherwise approve. This is the most favourable case for the rule: the code step only runs on approved pairs.
- No reconciling factor is confirmed: `rechecked = {}`, nothing struck.
- This skips the Skeptic's own re-query step. The fields are given directly.
- No database, Zetaris or Nightshift access. `SAMPLE_MODE=true`, no `.env`, nothing written outside the results file.
- No rule code is edited.

## The case set (fixed now; written after this note is pushed)

Path: `engg/docs/eval/independent_lookalike_cases.json`.
- Every crime carries `synthetic: true`, and so does the file.
- Each pair has an id, a stratum, a one-line description of what differs, and the two crimes' feature records.
- Its sha256 will be pinned in a short addendum to this note, committed **before** the run.

**24 look-alike false links** (a different offender; everything else close: same area and week, same crime type, similar MO), in three strata of 8:

| Stratum | What differs | Example kinds of value |
|---|---|---|
| **S1 · in scope, parseable** | one of the rule's fields, in values it can read but in wording the generator may not use | "Pulsar 220" vs "Pulsar 150"; "Apache RTR" vs "Pulsar"; plates written "TN-09-AB-4471" vs "TN 09 AB 4417"; "early 20s" vs "about 45"; "no helmet" vs "white helmet"; colours that are not aliases |
| **S2 · in scope, hard to parse** | one of the rule's fields, worded as a real extractor might word it | ages in words ("mid-twenties", "around forty-five", "teenager", "elderly"); counts as text ("two", "a pair"); colour only inside `make_model` ("red Splendor" vs "black Splendor"); a short plate fragment |
| **S3 · out of scope** | something the rule does not read: time of day, weapon, target, approach or escape, MO detail | 2 a.m. vs 2 p.m.; knife vs no weapon; shop vs pedestrian; on foot vs on a bike. The rule's fields are left compatible or blank |

**8 true twins** (the same offender in two crimes):
- **6 clean twins**: compatible but different on the surface, e.g. "Bajaj" vs "Bajaj Pulsar 150"; grey/gray; "20-30" vs "about 25"; "TN09AB44?1" vs "TN09AB4471"; "black" vs "black with red stripe"; a count stated vs not stated.
- **2 witness-error twins**: the same offender, but the witnesses disagree as real witnesses do. One gives ages that don't overlap ("about 25" vs "38"); one gives a colour that is not an alias ("red" vs "maroon"). They are labelled as such in the file.

## Metrics, fixed now (the same definitions as #422, for comparison)

- **Primary: drop rate over all 24 look-alikes.** Pass: **≥ 0.60.**
- **Guard: twin false-drop over all 8 twins.** Pass: **≤ 1 of 8.**
- **Every pair is "decided".** The rule is deterministic and nothing can be unavailable.
- **Also reported:**
  - the drop rate per stratum (S1, S2, S3);
  - the false-drops among the 6 clean twins, and the 2 witness-error twins separately;
  - for every dropped pair, the contradiction found (kind, field, values);
  - for every missed pair, which field held the difference.
- **One pass, fixed order, no re-runs, no edits to cases after the pin.**

## Prediction (stated now)

- **S1:** most or all of 8 dropped.
- **S2:** a minority dropped. Ages and counts in words are not parsed; colour inside `make_model` likely is.
- **S3:** 0 of 8. Out of scope by design.
- **Overall:** about 9–12 of 24 (0.38–0.50), so the primary is **predicted to FAIL**.
- **Twins:** 0 of 6 clean twins dropped; both witness-error twins dropped. So 2 of 8, and the guard is **predicted to FAIL**.

## After the run

- The results go below a line in this note, plus a results JSON next to the case file.
- The author then opens the generator's plant code and the #422 case files, and labels any case whose variation matches a generator plant kind or wording. Those cases are reported, not removed.
- Any EVIDENCE or README line states the result as measured. Never "the Skeptic now catches false links".

## Addendum: case file pinned (committed before the run)

- `engg/docs/eval/independent_lookalike_cases.json` sha256 `93f72b97baaee720f93e2a0c3dca7ebe2d1c4e0b2d2c7e9ff9d18937b1ea9ece`.
- Shape as pre-registered: 24 look-alikes (S1 8, S2 8, S3 8) and 8 twins (6 clean, 2 witness-error).
- No case was run before this commit.
- **Clock correction:** the status line above says "14:52 IST". That was a wrong local clock reading. The pre-registration was pushed at **20:23 IST** (commit `11acb84`). The commit timestamps are the record of order.

---

## Results (27 Oct 2026, one pass after the pin; the text above is unchanged)

Run: `cd services/api && SAMPLE_MODE=true python -m app.eval.independent_lookalike`, run once. Output: `engg/docs/eval/independent_lookalike_results.json`. The pinned sha256s of the cases and `contradiction.py` were checked by the script before running.

**Both pre-registered numbers FAIL, as predicted.**

| Metric | Result | Threshold | Verdict |
|---|---|---|---|
| **Primary: look-alikes dropped** | **10 of 24 (0.42)** | ≥ 0.60 | **FAIL** |
| **Guard: twins wrongly dropped** | **2 of 8** | ≤ 1 of 8 | **FAIL** |

| Breakdown | Dropped |
|---|---|
| S1 · in scope, parseable | **8 of 8** |
| S2 · in scope, hard to parse | **2 of 8**: colour inside `make_model` ("red Splendor" vs "black Splendor") and helmet "dark" vs "bright yellow" |
| S3 · out of scope | **0 of 8** |
| Clean twins | **0 of 6** |
| Witness-error twins | **2 of 2**: ages "about 25" vs "38"; colour "red" vs "maroon" |

**Missed by the rule (14):**
- S2, ages in words: "mid-twenties" vs "around forty-five"; "teenager" vs "elderly"; "college-going boy" vs "man in his fifties". The rule reads an age only from digits.
- S2, counts as text: "two" vs "one"; "a pair of men" vs "lone rider". The rule compares counts only when both are integers.
- S2, a short plate fragment: "71" vs "17". The rule compares plates only when both end in at least 4 characters.
- S3, all 8: time of day, weapon, target, approach, escape, MO detail, stolen item and build. The rule does not read these fields.

**What this means:**
- The rule does what it says on the fields it reads, when the values come in a form it parses. That held on independent wording too: 8 of 8 in S1, including makes, plates, ages and colours the generator never uses.
- It is **not** a general look-alike detector. It missed everything outside its four kinds, and in-scope values it doesn't parse (ages and counts in words; see the post-run checks on whether the product produces those).
- It also drops true pairs when witnesses disagree on age or on colours that are not aliases. Real witness descriptions vary like that.
- So the #422 result (24/24 dropped, 0/8 twin false-drops) shows the rule working on the generator's plants. It does **not** show general catching of false links.
- **Not tested here:** the Skeptic's model critique, and the Extractor turning FIR narratives into these fields.

**Post-run checks (added after the run, not part of the pre-registered text):**
- **Where these field values come from in the product.** In the console FIR form the offender age is a fixed dropdown and the count is converted to a number (`apps/web/lib/fir.ts`). The 1,275 sample crimes hold only bands such as "20-30" and only integer counts. So the S2 misses on **ages and counts in words** (S2-01 to S2-04, S2-07) are gaps in the rule's parser that the console form does not produce today. They would matter only for a source that passes such text through (legacy imports, newly onboarded sources), which was **not tested**. The remaining S2 miss (the short plate fragment, S2-06) and the two S2 drops (helmet wording, colour inside `make_model`) use free-text fields the form does allow.
- **The pairs were never scored by the Linker.** Every pair was assumed to be one the Skeptic would approve. Some look-alikes, such as several S3 pairs (02:10 vs 14:10; chain vs phone snatching), might never alert at all. So "0 of 8 out of scope" describes the rule, not which false links would reach an analyst.

### Overlap with the generator (labelled after the run, as pre-registered)

After the run I opened `eval/planted_skeptic.py` (the plant recipe: `COLOUR_SWAP`, `MAKE_SWAP`, `COUNT_SWAP`, `AGE_SWAP`, `HELMET_SWAP`).
- **All 8 S1 cases share a plant kind with the generator.** That was by design (S1 = the rule's fields).
- **Values that also appear in the generator's maps:**
  - S1-02 uses "Hero Splendor Plus", a `MAKE_SWAP` target;
  - S1-05 is 1 vs 3 offenders (`COUNT_SWAP` maps 3 → 1);
  - S1-06 is "no helmet" vs "white", close to the `HELMET_SWAP` pair "no helmet" → "white full-face";
  - S2-08's "bright yellow" is near the generator's "plain yellow".
- **Different from the generator in value or form:**
  - Pulsar 220 vs 150, green/orange, hyphenated and spaced plates, "early 20s" vs "about 45", "under 18";
  - every S2 wording;
  - every S3 difference. The generator's fifth kind, `simultaneous`, is a time that makes the same offenders impossible. No S3 case uses it.
- The twins are not the generator's series twins: they differ on the surface by design.
- No case was removed.
