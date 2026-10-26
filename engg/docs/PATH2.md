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
- **Zetaris:** the sponsor's own compose, with sources, file tables, views and named-query objects registered by one command (`python -m data.setup_live`, being built in WS1-19).
- **Nexus:** the API, the worker and the web console.
- **Nightshift** stays on the host, as today, because it serves the models.

The hosted setup (cloud Supabase + Vercel, [D-003](DECISIONS.md)) becomes one deploy target chosen by environment variables, not the only way to run the console.

## 2. Today (26 Oct 2026)

- **The judge path needs nothing external.** The Docker image runs in sample mode with no credentials and no Supabase; models replay recorded fixtures. A fully offline check (`--network none`) is on the Tuesday checklist ([WS5-08](validation/WS5-08-checklist.md), section 3b).
- **Live mode is being made Zetaris-only:** WS1-19 (generate the dataset and load it into the judge's own Zetaris, no Supabase) and WS2-22 (a local result store for `/run` and the worker) are in progress.
- **The console still needs the cloud.** The police console, Auth, Storage and RLS run on our hosted Supabase; that is what Path 2 replaces.

## 3. Backlog (WS6, from the tracker)

All are marked `cut` for the hackathon and parked here.

| Task | What | Why |
|---|---|---|
| WS6-01 | Local Supabase stack in compose | The console runs without our cloud; cloud Supabase becomes one deploy target |
| WS6-02 | Full 14k dataset in sample mode; fixtures and eval rebuilt | The sample bundle is a 1,275-crime slice; eval numbers today are on that slice |
| WS6-03 | Positive-only corroboration rule | One corroborating news item can lower a strong pair's score; the rule was evaluated and parked ([D-032](DECISIONS.md)) |
| WS6-04 | Fold `_aged_NN` target labels | Changes MO matching, so it waits until after the video is recorded |
| WS6-05 | Worker-side face/plate blur (OpenCV) for public stills, with a service-role-only writer | Closes the known gap that an officer could upload an unblurred still straight to storage (WS4-09, README Limitations) |
| WS6-06 | Route-signed evidence hashes | The database doesn't re-verify the upload hash today ([D-029](DECISIONS.md) limit) |
| WS6-07 | Full lazy news generator over the live crime set | 5 sample articles match more than one live crime today ([D-032](DECISIONS.md), known live limit) |
| WS6-08 | Column-limited persons view for `zetaris_reader` | Hardening: Zetaris should see only the columns agents need |
| WS6-09 | Vision and audio lanes once Nightshift routes them | Images are refused today and no audio model is pinned (WS2-05, CAP-03, CAP-09) |

## 4. Hardware

- **Zetaris alone wants 8 GB RAM and 4 CPUs given to Docker** (16 GB laptop, ~15 GB disk; see [SETUP](SETUP.md)). Local Supabase, the API, the worker and the web app add to that (estimate a few GB more; not yet measured). Plan for a 32 GB machine for the full stack, or run Zetaris on the managed cluster.
- **One Docker owner at a time.** On a shared machine, claim the Docker slot (`C:/Apps/_docker-slot/owner.txt` on our laptop, as in [PROGRESS](PROGRESS.md)) before starting containers, don't start with under 2 GB free RAM, and release the slot when done.

## 5. Phases (rough order)

1. **Finish WS1-19 and WS2-22.** Live mode with only Zetaris and Nightshift. Everything later builds on this.
2. **Local Supabase in compose (WS6-01).** Migrations on start, seed into a volume, Auth with the demo roles, Storage buckets. Same env names as the cloud, so switching target is a `.env` change.
3. **Full dataset everywhere (WS6-02).** Rebuild fixtures and re-run the eval on 14k crimes; publish both slices' numbers.
4. **Safety items (WS6-05, WS6-06, WS6-08).** Close the known limits the README lists.
5. **Scoring and data quality (WS6-03, WS6-04, WS6-07).** Each one changes scores, so each re-runs the eval and records a decision.
6. **Model lanes (WS6-09)** when Nightshift serves vision and audio; the Extractor code paths already exist.
