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
