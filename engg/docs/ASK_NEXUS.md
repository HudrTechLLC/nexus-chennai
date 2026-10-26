---
tags: [nexus, design]
---

# Ask Nexus: plain-English questions over the registry (WS3-30)

Related: [00-INDEX](00-INDEX.md) · [AGENTS](AGENTS.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DECISIONS](DECISIONS.md)

An analyst types a question at `/console/ask`, such as *"Chain snatchings in Adyar after 7 pm in the last 90 days"*.
The answer is a short summary, a cited table (every row links to its case), a map of the hits, and "how this was
answered": the plan, the named queries with their Zetaris query ids, and the model and receipt.

## Flow

1. The console inserts `{question}` into `ask_questions` (migration 0007_16) and polls the row. Vercel cannot reach
   Zetaris (D-019), so the console never answers a question itself.
2. `python -m app.ask_worker` is a separate process beside the main worker. It claims the oldest queued question
   with a conditional update (`queued` → `planning`), so two copies never answer the same one.
3. **The model plans and code decides.** Nemotron Lightning (fast lane, temperature 0, thinking off) returns only a
   JSON plan with these fields: category, sub type, station names, status, time window, hours of day, and words to
   find. `app.ask.resolve_plan` checks each field:
   - Category, sub type and status come from fixed lists. A sub type fixes its own category, and is used only
     when the question names it ("robberies" searches all robberies, not street robberies); the plan's `notes`
     say when a model choice was not used.
   - Station names are mapped to ids from the city pack (stations plus place aliases), so the model never writes an id.
   - "This month", "last 90 days" and "after 7 pm" are resolved to dates and hours in code, in city time. A question
     with no time searches the last 90 days, and the summary says so.
   - Anything that does not resolve makes the question `unmappable`, with the specific reason. A filter is never
     dropped silently.
4. **Named queries only (R1).** The only query on the allow-list is `q_search`, with one call per station (up to 3).
   Each call has a 30 s fail-fast timeout. If a page comes back full (1,000 rows, newest first, D-031), the next
   call asks for the older part, up to 5 pages, so a broad question is answered in full. Code then applies the
   plan's remaining filters: sub type, every word as a **whole word in the FIR narrative** (not the address: "red"
   must not match "Red Hills"), and hours of day.
   **Test filings are excluded** by the D-033 rule (same regex as series membership), and the summary says how
   many were left out. If a query returns its full page of 1,000 rows, the answer says "at least N".
5. **The answer is templated.** The summary and each row's reason are built from row fields, with no model prose,
   so the answer cannot claim anything the rows don't show. Rows carry only `crime_id` and `why`. The console reads
   display fields with the asker's own client, so crimes RLS applies. Analysts, supervisors and admins can read
   every crime (`can_read_crime`); station officers cannot ask at all.
6. Each question gets its own trace run `ask_<8hex>` (runs.kind `search`), with its own Zetaris and Nightshift
   clients. Linking, scoring, the Skeptic and the judge path never call this code.

## Guards

- Only analysts, supervisors and admins may ask. They insert only the `question` column and read only their own
  rows. Only the service role writes status, plan and answer.
- A user can have at most 3 unanswered questions (`ask_questions_guard`).
- On every pass, questions stuck in planning or running for more than 3 minutes become `failed` ("timed out").

## Live check (27 Oct 2026, nexus-qa)

| Question (sample chip) | Answer | Independent SQL count |
|---|---|---|
| Chain snatchings on a red Pulsar in the last 90 days | 16 cases, 1 test filing excluded | 16 |
| Robberies mentioning a red Pulsar in the last 2 years (not a chip; 2 pages) | 115 cases | 115 |
| Chain snatchings in Adyar after 7 pm in the last 90 days | 4 cases | 4 |
| Robberies in Velachery that are still undetected since 1 September | 3 cases | 3 |
| Who will commit the next robbery in Adyar? | unmappable: "I can only search crimes by type, …" | n/a |

Each chip ran 5 times live: the same count every time, 4–12 s end to end. The planning call took 1–52 s. The slow calls went to the same model, so the variation is on the provider side.
Each `q_search` call took 4–6 s.

## Limits

- Only `q_search` is allowed. Questions about vehicles' ANPR trails, offender returns or station-to-station links
  are refused rather than half-answered.
- Words must be in the FIR narrative. Witness statements are not searched by Ask, so a word count can be lower
  than the console Search page's, which also searches statements.
- Errors shown to the analyst are plain sentences. The detail (HTTP, SQL, Zetaris) stays in the run's trace.
