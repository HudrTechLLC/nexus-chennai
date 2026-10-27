---
tags: [nexus, testcases]
---

# Validation gate reports

One file per gate run: `<WS>-<YYYY-MM-DD>.md`. Each line says PASS or FAIL with its evidence: file path, test output, trace line or Zetaris query id. A FAIL blocks the next phase unless the team accepts it in [DECISIONS](../DECISIONS.md). Checklist: [SPEC O6](../SPEC.md#claude-code).
Related: [DELIVERABLES](../DELIVERABLES.md) · [WS5-08 checklist](WS5-08-checklist.md) · [WS5-08 results](WS5-08-2026-10-27.md) · [WS3-06/WS3-10 gate](WS3-06-WS3-10-2026-10-26.md) · [00-INDEX](../00-INDEX.md)

| Gate | Date | Result |
|---|---|---|
| [WS3-06 / WS3-10](WS3-06-WS3-10-2026-10-26.md) case file, search, FIR capture | 2026-10-26 | 10 PASS · 5 PARTIAL · 1 FAIL (accepted, D-029) · 1 N/A |
| [WS5-08](WS5-08-2026-10-27.md) fresh-clone validation (L3), part 1 pre-run | 2026-10-26 | 14 PASS · 1 OPEN (video link) · 0 FAIL, history scan clean, 3 hygiene fixes (#316); part 2 Tue 27 Oct |
| [WS5-08](WS5-08-2026-10-27.md) part 3, final fresh clone on `5a7c549` | 2026-10-27 | Every runnable step PASS · 0 FAIL; sample mode EXACT (venv, no `.env`) and offline in CI; docker via CI stand-in (0.2 not met: local RAM 1.5 GB); carried to `10cd04d` (web/docs only since); README workers gap fixed (#410) |
