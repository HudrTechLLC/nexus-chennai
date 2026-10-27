# Timed analyst task: pre-registration

Written 27 Oct 2026, before any session is run. Judges asked for a measure of analyst value beyond P/R on planted
truth (fix #24). This is a small, honest version that can run in about 30 minutes with one or two people.

## Who
One or two people who have **not** seen Nexus's alerts or the planted truth for the task case (for example a member
of another team). Not the authors of the data generator. Their role (and that they are not police analysts) is
reported with the result.

## Task
Case **CHN-KU-2025-000078** (night house break with a grille cutter, Pongal week 2025; `input_examples/example_2.json`).
Question: *which other recorded cases are most likely the same offenders?* List case ids, most likely first.

## Two conditions (each person does both, order alternated between people)
- **Manual:** the police console's case list and search only (filters by station, date, crime type, MO text);
  alerts, series and the Ask Nexus page are hidden. Time cap 15 minutes.
- **Nexus:** the alert list and alert pages for the same case. Time cap 15 minutes.

To limit learning between conditions, a second case of the same kind (chosen by rule: the next night house-break
case id in the planted truth after the first) is used for whichever condition comes second.

## Measured
- Time to the first correct linked case, and total time used.
- Correct cases found (against the planted truth) and wrong cases listed.
- One line from the person on what helped or got in the way.

## Reporting
Results are committed as `TIMED_TASK_RESULTS.md` whatever they show, including if manual search wins. With one or
two people this is an anecdote, not a statistic, and will be described that way. All data is synthetic.

## Addendum, 27 Oct 2026, ~22:10 IST: agent-proxy run (committed before any participant runs)

No people were available, so Ravee and the chief decided to run the task with **fresh AI agents standing in for
analysts**. This is an **agent-proxy test, not a human study**, and the results will say so in their first line:
"agent proxy, not evidence of human analyst value".

What changes:
- **Participants:** fresh Claude general-purpose subagents (A and B) with no prior context. They get the task text
  and a small read-only wrapper, never the repo path, the truth files, `output_examples` or alert lists for Manual.
  - Each agent's working folder is an empty temp folder outside the repo, holding only the wrapper and the data its
    condition allows.
  - The agents have general tools, so "use only the wrapper" is instructed, not enforced. Their transcripts are
    checked afterwards for any other file reads, and the results report what was found.
- **One fresh agent per condition (4 sessions).** The pre-registered assignment is kept: A = Manual on case 1, then
  Nexus on case 2; B = Nexus on case 1, then Manual on case 2. A fresh session per condition removes carry-over
  between them.
- **Second case, by the stated rule:** the next night house-break case id in the planted truth after the first is
  **CHN-KU-2025-000082**. It is in the same series as the first (the sample truth has only one night house-break
  series, `SER-GRILLE-CUTTERS`). That's why carry-over is removed with fresh sessions instead.
- **Data:** the sample bundle, read-only, not the live app. The live app has no alerts for CHN-KU-2025-000078, and
  creating them would write into the app judges are using. Nothing is written anywhere.
  - **Manual:** a wrapper over a copy of the sample crimes with the console search's filters (station, date range,
    crime type, text over the narrative and MO), plus opening one case's file. No alerts, series or Ask Nexus.
  - **Nexus:** the alert list and alert detail that a sample-mode `/run` of the case produces (code-only scoring,
    no live model calls), plus opening the case's own file.
- **Scoring:** against `data/sample/_truth/pairs.csv`. True links are the case's `series` pairs; listed `decoy`
  pairs and any other case count as wrong. The cap (15 minutes per condition) and the measures are unchanged:
  - time to the first correct case listed, and total time;
  - correct cases found, and wrong cases listed;
  - one line from the agent on what helped or got in the way.
  - Time is wall clock from the wrapper's `start` to its `answer`, plus the number of wrapper calls.

**Related:** [[TIMED_TASK_RESULTS]]
