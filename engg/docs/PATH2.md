---
tags: [nexus, plan]
---

# Path 2: after the hackathon

What Nexus becomes once the submission is in: one self-contained stack that anyone can start, with the cloud as just one place to deploy it. This is a plan, not a status report; nothing here is claimed as built unless the "Today" section says so.
Related: [00-INDEX](00-INDEX.md) · [DECISIONS](DECISIONS.md) · [workstreams.json](workstreams.json) · [SETUP](SETUP.md) · [ARCHITECTURE](ARCHITECTURE.md) · [PROGRESS](PROGRESS.md)

## 1. Goal

`docker compose up` brings up the whole system on one machine, with no team cloud account:

- **Local Supabase:** Postgres, Auth, REST (PostgREST), Storage and Realtime, with every migration in `supabase/migrations/` applied.
- **Data:** on first start, the deterministic generator (seed 42) writes the full dataset (about 14,000 crimes, see [data/README](../../data/README.md)) into a volume, and the seed loads it.
- **Zetaris:** the sponsor's own compose, with sources, file tables, views and named-query objects registered by one command (`python -m data.setup_live`, merged in #280, see [data/README](../../data/README.md) §5; its model-output fixtures are merged (#293), and a clean-machine run passed (#325, `79478cf`: fresh clone + fresh venv into throwaway `nexus_fs2`; about 10 min including install; hero via `q_case` and 106 candidates via `q_candidates`, through Zetaris)).
- **Nexus:** the API, the worker and the web console.
- **Nightshift** stays on the host, as today, because it serves the models.

The hosted setup (cloud Supabase + Vercel, [D-003](DECISIONS.md)) becomes one deploy target chosen by environment variables, not the only way to run the console.

## 2. Today (26 Oct 2026)

- **The judge path needs nothing external.** The Docker image runs in sample mode with no credentials and no Supabase; models replay recorded fixtures. A fully offline check (`--network none`) is on the Tuesday checklist ([WS5-08](validation/WS5-08-checklist.md), section 3b).
- **Live agent reads on your own Zetaris, no Supabase (WS1-19, done):** `python -m data.setup_live` (#280) with its model-output fixtures (#293); a clean-machine run passed (#325, `79478cf`: fresh clone + fresh venv into throwaway `nexus_fs2`; about 10 min including install; hero via `q_case` and 106 candidates via `q_candidates`, through Zetaris). WS2-22 is done: `/run` keeps its results in local files when Supabase isn't configured (`NEXUS_STORE=local`, #273); the worker stays Supabase-only.
- **The judge path is proven offline:** the sample-mode container answers all three examples with `--network none` in CI (`judge-offline`, #285).
- **The console still needs the cloud.** The police console, Auth, Storage and RLS run on our hosted Supabase; that is what Path 2 replaces.

## 3. Backlog (WS6, from the tracker)

### First after the freeze: live data-quality flags in scoring

Today live scoring runs **without** data-quality flags (README Known limitations). The Planner's `q_dq_flags`
step times out on every live case run, even with Zetaris idle. Since #334 it is given 30 s, traced
`step_degraded`, and skipped. The hero numbers were produced the same way, so they stand. Sample mode, the DQ views
and the console pages are unaffected.

- **Why it is slow:** `q_dq_flags` filters `array_contains(split(:ids, ','), crime_id)` on top of
  `nexus.dq_flags`, a UNION of four sorted rule views (the sort is required by D-031). One of them is the
  duplicate-FIR self-join of `v_crime_unified` (about 19,500 rows) against `sb.crimes`. Zetaris cannot push the id
  filter through the sorted UNION and self-join, so every call computes every flag: the full pass takes
  55–80 s live (`q_dq_summary`).
- **Fix (chosen, option A):** `app.dq_status` already runs the full pass. It should also write the resulting flags
  (a few hundred rows) to a small Supabase snapshot table, with read access for the API role only, so the Planner
  reads them in one fast lookup, stamped with the snapshot time. This needs one migration, which is why it waited
  for after the freeze.
- **Rejected for now:** rewriting `q_dq_flags` to filter inside each rule (B). Zetaris allows one reference to a
  schema-store view per query, so legacy-to-legacy duplicates would drop out. Leaving it degraded (C) is the
  freeze decision, not the end state.

### First agent-speed item: end the Skeptic send-back loop when a re-score brings nothing new

A filed FIR takes about **8 minutes** from filing to alert live today: worker pickup 12 s, extraction with live vision 37 s,
and the case run 436 s (`run_e18df7ca`, CHN-VL-2026-001221, 420 s deadline). Its alert is written as `needs_revision` by the
deadline partial write (#347), not approved. Most of that time is spent on rounds that cannot change anything:

- The Skeptic sent the pair back; round 2 re-scored the **identical** 0.603 with the same factor values, and the Skeptic sent
  back the same critique. Round 3's plan then hit the deadline. Rounds 2–3 took about 4 of the 7 minutes (two Ultra critiques
  of 32 s and 69 s, two re-explanations, and plans of 29 s and 110 s).
- The judge examples run the same empty loop: 6 of 7 alerts in example 2 and 1 of 2 in example 3 show `skeptic.rounds: 3`,
  approved by the revision cap after identical re-scores.

**Fix (built, held):** branch `fix/sendback-no-new-evidence`. When a sent-back pair's re-score is identical (score, band and
every factor value), skip the next critique and apply the existing revision-cap verdict now, traced
`sendback_no_new_evidence`. Same verdicts and scores; **3 Skeptic rounds → 1**; about **4 min saved per such case** live.
Tests pass; verify_replay passes. It was cut for the freeze because it changes judge outputs 2 and 3 (`skeptic.rounds` 3 → 1,
and factor reasons and rationale from the round-2 explanation instead of round 3's). Shipping it means re-recording those two
examples (about 20 min of live Ultra) and re-checking the docs.

All are marked `cut` for the hackathon and parked here.

| Task | What | Why |
|---|---|---|
| post-freeze, first | Live DQ flags in scoring via a snapshot table written by `app.dq_status` | The live `q_dq_flags` query takes 55–80 s against a 30 s Planner budget, so live runs skip it today (#334) |
| post-freeze, agent speed | End the send-back loop on an identical re-score (`fix/sendback-no-new-evidence`) and re-record judge examples 2 and 3 | Live filing → alert is ~8 min and ends `needs_revision` on the deadline; rounds 2–3 re-score the same 0.603 (`run_e18df7ca`) |
| WS6-01 | Local Supabase stack in compose | The console runs without our cloud; cloud Supabase becomes one deploy target |
| WS6-02 | Full 14k dataset in sample mode; fixtures and eval rebuilt | The sample bundle is a 1,275-crime slice; eval numbers today are on that slice |
| WS6-03 | Positive-only corroboration rule | One corroborating news item can lower a strong pair's score; the rule was evaluated and parked ([D-032](DECISIONS.md)) |
| WS6-04 | Fold `_aged_NN` target labels | Changes MO matching, so it waits until after the video is recorded |
| WS6-05 | Worker-side face/plate blur (OpenCV) for public stills, with a service-role-only writer | Closes the known gap that an officer could upload an unblurred still straight to storage (WS4-09, README Limitations) |
| WS6-06 | Route-signed evidence hashes | The database doesn't re-verify the upload hash today ([D-029](DECISIONS.md) limit) |
| WS6-07 | Full lazy news generator over the live crime set | 5 sample articles match more than one live crime today ([D-032](DECISIONS.md), known live limit) |
| WS6-08 | Column-limited persons view for `zetaris_reader` | Hardening: Zetaris should see only the columns agents need |
| WS6-09 | Vision on an in-house lane; an audio lane once Nightshift routes one | Vision works through a rate-limited third-party free route (D-036, verified in run `reextract_vis_1793040194`); no audio model is pinned (WS2-05, CAP-03, CAP-09) |

## 4. Hardware

- **Zetaris alone wants 8 GB RAM and 4 CPUs given to Docker** (16 GB laptop, ~15 GB disk; see [SETUP](SETUP.md)). Local Supabase, the API, the worker and the web app add to that (estimate a few GB more; not yet measured). Plan for a 32 GB machine for the full stack, or run Zetaris on the managed cluster.
- **One Docker owner at a time.** On a shared machine, claim the Docker slot (`C:/Apps/_docker-slot/owner.txt` on our laptop, as in [PROGRESS](PROGRESS.md)) before starting containers, don't start with under 2 GB free RAM, and release the slot when done.

## 5. Phases (rough order)

1. **Live DQ flags back in scoring** (a snapshot table written by `app.dq_status`, so the Planner reads it in one fast query). Then **move the worker off Supabase** (WS1-19 done: #280, #293, clean-machine run #325; WS2-22 done in #273). Live mode with only Zetaris and Nightshift. Everything later builds on this.
2. **Local Supabase in compose (WS6-01).** Migrations on start, seed into a volume, Auth with the demo roles, Storage buckets. Same env names as the cloud, so switching target is a `.env` change.
3. **Full dataset everywhere (WS6-02).** Rebuild fixtures and re-run the eval on 14k crimes; publish both slices' numbers.
4. **Safety items (WS6-05, WS6-06, WS6-08).** Close the known limits the README lists.
5. **Scoring and data quality (WS6-03, WS6-04, WS6-07).** Each one changes scores, so each re-runs the eval and records a decision.
6. **Model lanes (WS6-09):** move vision to an in-house lane, and add audio when Nightshift serves it; the Extractor code paths already exist.
