---
tags: [nexus, eval, results]
---

Agent-proxy run: fresh AI agents stood in for analysts; this is not a human study.

# Timed analyst task: results (agent proxy, task #24)

Published as pre-registered in [[TIMED_TASK_PREREG]] (see its 27 Oct addendum) whatever it shows. These results are
an agent proxy, not evidence of human analyst value. There were four sessions on one synthetic series, so read them
as an anecdote, not a statistic.

- **Pre-registration:** the addendum commit `b26c8dd` was made at 21:58:52 IST. That is 4 minutes before the first
  session started at 22:02:55 IST; the addendum's own heading says "~22:10", which was an estimate.
- **Participants:** four fresh Claude general-purpose subagents, one per session. Each got only the task text and a
  read-only wrapper (`tt.py`) in an empty temp folder outside the repo.
- **Data:** the sample bundle only. Nothing was written to the live app.
- **Scoring:** against `data/sample/_truth/pairs.csv`, done after all four sessions had finished.

## Results

| Session | Condition | Case | Answer at | First correct case on screen | Wrapper calls | Correct | Wrong | Missed |
|---|---|---|---|---|---|---|---|---|
| A1 | Manual | CHN-KU-2025-000078 | 80.3 s | 7.1 s | 16 | 7 / 7 | 0 | 0 |
| B1 | Nexus | CHN-KU-2025-000078 | 42.7 s | 0.2 s | 16 | 1 / 7 | 0 | 6 |
| A2 | Nexus | CHN-KU-2025-000082 | 36.9 s | 4.8 s | 19 | 7 / 7 | 0 | 0 |
| B2 | Manual | CHN-KU-2025-000082 | 24.9 s | 5.5 s | 14 | 7 / 7 | 0 | 0 |

- **Totals:** Manual found 14 of 14 correct links; Nexus found 8 of 14. No session listed a wrong case or a decoy.
- **Time:** every session answered within 81 s, far inside the 15-minute cap. Manual took 25 s and 80 s; Nexus took
  37 s and 43 s.
- **"Time to the first correct case listed":** each agent listed cases only once, in its final answer, so this
  equals the answer time.
- **"First correct case on screen":** extra and not pre-registered. It is computed by replaying each logged call
  against the same data.

What each agent said helped or got in the way, in its own words:

- **A1 (Manual):** "Unique MO (window grille cut with cutter, 2 medium-build 30-40, on foot, ~03:00) matched exactly
  8 of ~125 night house breaks; other cases lacked structured MO fields so text search was key"
- **B1 (Nexus):** "All 7 alerts rest on a generic template MO (2 men, cutter, grille, on foot); only KU-82 has
  0.2km/72min proximity plus tip/112 corroboration; the same-night MG/AS/VI hits are minutes apart km away on foot,
  so not one crew"
- **A2 (Nexus):** said the case files and KU-78's corroboration helped. What got in the way: the alert factors were
  generic, and there was no model rationale or reviewer critique.
- **B2 (Manual):** "grille", "cutting tool" and "cutter" each returned the same cluster. What got in the way: search
  results don't show the MO, so each case had to be opened.

## Reading

1. **The system's alerts had the answer both times.**
   - For KU-78 it raised 7 alerts, all true series members.
   - For KU-82 it raised 8: the 7 members plus one false alert, CHN-AS-2025-000141. A2 rejected that one correctly
     (a daytime duplicate-key entry).
   - B1's low score is the agent's own judgement, not missing alerts. It decided that one pair on foot could not have
     done five break-ins in about 35 minutes across four neighbourhoods. It also judged the shared MO to be
     boilerplate. So it kept only the strongest, corroborated link.
   - That reasoning is defensible on its face; it fails here because the synthetic series has a tight timeline.
2. **Manual search was easy on this case.** The series' MO is distinctive, worded the same way in every case, and
   absent from the other ~125 night house breaks. So a one-word text search ("grille" or "cutter") returns exactly the
   series. This case tests whether an analyst can find a series with a unique keyword, which keyword search does
   well. It does not test the harder situations where the system should help.
3. **The Nexus condition was the code-only alert view.** As pre-registered, it came from a sample-mode `/run` with no
   live model calls. Every alert read "model rationale unavailable"; the Skeptic verdict was `approved` with
   `model_critique: unavailable` and no factors struck. Both Nexus agents named the missing explanation as what got in
   the way.
4. **Nothing here supports a speed or accuracy claim for Nexus over manual search.** On this one series, a fresh agent
   with keyword search was at least as accurate and about as fast.

## Transcript check (the chief's tightening)

Each agent's full transcript was checked after the run for any file access outside the wrapper: **clean.**

- **Tool calls:** 22 in all, every one a Bash command (A1: 6, A2: 6, B1: 5, B2: 5). Each command `cd`s into the
  agent's own temp workspace and runs `python tt.py`.
- **Paths:** no command names a path outside the workspace. No Read, Glob, Grep or web tool was used.
- **Pattern hits:** an automatic pattern check hit 5 commands. All 5 are the wrapper's own `--type` flag, or
  `p['type']` inside a stdout filter.
- **Deviations from "use only tt.py":**
  - All four agents piped tt.py's printed output into `python -c` or `grep` one-liners, and used shell `for` loops to
    run several tt.py calls at once. These only reshape what the wrapper printed. A1 and B2 said so themselves.
  - A1 called the `advisor` tool once before answering. The advisor sees only that agent's own conversation and has no
    file access.
- **The full command list for each session** is in `timed_task/timed_task_results.json`, with the temp path replaced
  by `<tmp>`.

## Limits

- **Size:** four sessions, one series, synthetic data, one run each. Fresh AI agents are not analysts.
- **Case choice:** the second case comes from the same series as the first, by the pre-registered rule. The sample
  truth has only one night house-break series.
- **Enforcement:** "use only the wrapper" was instructed, not enforced, and was then checked as described above.
- **Pairing:** each session used a fresh agent, so the A/B order pairing did not carry over within an agent.

## Files

- **Call logs:** `engg/docs/eval/timed_task/calls_A1.jsonl`, `calls_B1.jsonl`, `calls_A2.jsonl`, `calls_B2.jsonl`.
  These are the wrapper's own logs, one line per call. They hold no credentials.
- **Scores and transcript audit:** `engg/docs/eval/timed_task/timed_task_results.json`.

**Related:** [[TIMED_TASK_PREREG]] · [[MODEL_IN_LOOP_RESULTS]]
