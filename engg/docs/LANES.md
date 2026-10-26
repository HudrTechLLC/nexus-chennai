---
tags: [nexus, plan]
---

# Build lanes: who builds what

Four Claude Code lanes build Nexus in parallel; **nexus-chief** coordinates. Every lane reads this note first and again after any restart. It is the single source for ownership, interfaces and rules.
Related: [workstreams.json](workstreams.json) (live chart at `/docs/progress`) · [SPEC](SPEC.md) · [DECISIONS](DECISIONS.md) · [00-INDEX](00-INDEX.md)

**Goal: deliver the whole spec.** Nothing is cut. Deadline is 27 Oct 23:45 UTC, and the team submits at **Tue 27 Oct 23:15 IST**. Feature freeze is **Tue 14:00 IST** (moved from 12:00 by Ravee, 27 Oct); in-flight work must be merged by **11:00 IST**.

## 1. Lanes

| Lane | Owns (paths) | Builds | Tracker tasks |
|---|---|---|---|
| **nexus-1 · Data & Zetaris** | `services/api/app/models/`, `supabase/migrations/0002*`–`0003*`, `data/`, `cities/`, `zetaris/`, `services/api/app/adapters/zetaris.py` (registry + DuckDB sample queries), `tests/data/`, `tests/zetaris/` | Domain models (D3), core schema + RLS (Part I), reference data, seeded generator (Part D), sample bundle, Supabase seed, Zetaris sources/views/DQ, 12 named queries + DuckDB twins, storage for Zetaris CSV/Parquet | WS1-* |
| **nexus-2 · Meterless engines** | `engines-ts/` (TypeScript sidecar), `services/api/app/engines/`, `tests/engines/`, `supabase/migrations/0005*` | World Model, H-MEM, Markovian, Scout Intent: vendored TS references + official conformance runs, a sidecar service, the Python facade below, Tip Guard rules, feature tests | WS2-06, WS2-08, WS2-12, WS2-15, WS2-17 |
| **nexus-3 · Agents & graph** | `services/api/app/agents/`, `app/graph/`, `app/scoring/`, `app/eval/`, `app/main.py`, `app/worker.py`, `input_examples/`, `output_examples/`, `tests/agents/`, `tests/scoring/`, `tests/graph/`, `supabase/migrations/0006*`, `apps/web/app/console/system/**` + `console/trace/**` (WS3-08) | All 11 agents (E3), F2 scoring, LangGraph (C4) with caps, real `/run` + `/api/*` (Part H), worker queue, eval vs baseline (F3), judge examples | WS2-07, WS2-09…11, WS2-13, WS2-14, WS2-16, WS2-18…20 |
| **nexus-4 · Web** | `apps/web/**` (incl. `package.json`), `supabase/migrations/0004*` | Police console (G2) incl. Pulse Map in full (G3), alert inbox/detail, case, search, series, memory, graph explorer, system/trace, FIR form (G4); public portal (G1) incl. tip flow; public RPCs | WS3-*, WS4-* |
| **nexus-5 · Console: cases & FIR** (added 26 Oct) | `apps/web/app/console/(app)/cases/**`, `console/search/**`, `console/fir/**` or `cases/new`, `supabase/migrations/0007*`, `apps/web/lib/{cases,casesData,fir,search*}.ts` | Case file page + search (WS3-06), FIR capture form + `file_fir` RPC (WS3-10) | WS3-06, WS3-10 |
| **nexus-6 · Console: intelligence** (added 26 Oct) | `apps/web/app/console/(app)/series/**`, `stations/**` (link matrix), `memory/**`, `graph/**` | Series pages, station link matrix, H-MEM memory page, World Model graph explorer (WS3-11) | WS3-11 |
| **nexus-chief** | `engg/docs/workstreams.json`, `PROGRESS.md`, `DECISIONS.md`, `LANES.md`, README, `SPONSOR_TECH.md`, `metadata.json` | Coordination, reviews, Nightshift setup, tracker, decisions, submission docs | WS5-* |

## 2. Interfaces between lanes (code against these now; the owner implements them)

**Domain models (nexus-1).** `services/api/app/models/` has Pydantic v2 models named after spec D3:
- `Crime`, `CrimeFeatures`, `Tip`, `LinkAlert`, `LinkFactor`, `TraceEvent`, `PublicIncident`, …
- Field names exactly as in D3.

nexus-1 lands this **first** (target: within 90 min). Until then, others use the D3 field names directly.

**Database (nexus-1).** `0002_core.sql` creates every Part I table with RLS, following the Part I policies and DECISIONS D-003:
- `anon` gets no table access;
- the public portal uses narrow `security definer` RPCs, which nexus-4 adds in `0004_public_rpcs.sql`.

Migration numbers are reserved per lane (above). Never renumber another lane's file.

**Zetaris named queries (nexus-1).** These are the spec E5 names: `q_case`, `q_candidates`, `q_features`, `q_vehicle_trail`, `q_offender_return`, `q_calls_near`, `q_tip_corroboration`, `q_news`, `q_context`, `q_search`, `q_dq_flags`, `q_station_matrix`.
- Call them through `ZetarisClient.named(name, agent=..., **params)`.
- Each has a DuckDB twin over `data/sample/` so sample mode works.

**Engines facade (nexus-2).** Import from `app.engines`. Every call emits a trace event with `engine` set.

| Function | Returns |
|---|---|
| `world_model.ingest(entities: list[dict], source: str)` | `list[str]` (stable entity ids) |
| `world_model.context(crime_ids: list[str])` | `dict` (entities, relations, provenance) |
| `hmem.adjust(pair: dict)` | `{"delta": float, "memory_ids": [...], "reason": str}`, with abs(delta) ≤ 0.08 |
| `hmem.record_decision(alert_id, decision, reason_code, note, pair)` | `None`; writes memory + ledger |
| `markovian.dossier(series_id, records: list[dict])` | `{"text", "cited_ids", "chunks", "tokens_projected", "tokens_actual"}` |
| `scout_intent.classify(text: str, kind: str)` | `{"route", "intent", "risk": [...], "action": "clean"\|"quarantine"\|"urgent"}` |

The engines run as the TypeScript references in a local sidecar, so the **official conformance suites run unchanged** (DECISIONS D-008, revised). Python talks to the sidecar over HTTP. Each function also has a sample-mode backend that runs the same logic.

**Web ↔ backend.** The website on Vercel can't reach the laptop API. So:
- the web app reads alerts, cases and series from Supabase under RLS;
- it writes analyst decisions to `alert_decisions`;
- it writes tips through the `submit_tip` RPC;
- the worker (nexus-3) picks those up, feeds H-MEM and screens tips.

**Nightshift (nexus-chief).** It's being installed now. Until it's up:
- code the agents against `NightshiftClient.chat(lane, ...)`;
- test with mocked transports;
- use recorded fixtures for sample mode.

The chief announces the live base URL and token file when ready.

## 3. Rules every lane follows
1. **Work in your own worktree.** `git -C C:/Apps/Nexus worktree add -b <type>/<name> C:/Apps/Nexus-<lane>-<name> origin/main`.
   - Make a fresh `.venv` per worktree (`python -m venv .venv` + `pip install -r services/api/requirements-dev.txt`).
   - For web: `npm ci` in `apps/web`, so it's a real folder, not a junction.
2. **Stay in your owned paths.** You may make additive one-line edits to `services/api/requirements*.txt` and `.env.example`. Anything else outside your paths: message **nexus-chief** first.
3. **Merge and deploy rights.** Merge your own PR (squash) when **all** of these hold (rule updated 26 Oct, because main moves faster than a rebase-and-CI round):
   - CI is green on your diff;
   - commits on main since your merge base touch **none** of your files (`git diff --name-only <merge-base> origin/main`);
   - the full suite passes locally on your tree rebased onto current main;
   - the diff stays in your paths.

   If main's CI after the merge goes red because of your change, fixing it is your **first** priority.

   **Merge safety (added 26 Oct after a wrong-PR merge):** merge only PRs **you own**. Resolve the PR by its **head branch**, never a typed number. Before merging, confirm that the required checks (`api`, `web`, `engines`, `secrets`) are all **present and green**; Vercel alone reporting is not enough. Vercel deploys `main` automatically.
   - Apply migrations to Supabase **only after they are merged**, with `scripts/db_migrate.py` (dry run first). Any lane may run it once its own migration is merged; it applies **all** merged pending migrations in order. Check `schema_migrations` first, and never run it at the same moment as another lane.
   - Don't change Vercel or Supabase project settings. Ask the chief.
4. **Don't edit** `workstreams.json`, `PROGRESS.md`, `DECISIONS.md` or `LANES.md`. Send the chief the task ids you finished and any decision you need. The chief updates the tracker with `scripts/tracker.py`.
5. **Secrets: read from files, never inline, never echoed, never in a repo file** (global CLAUDE.md). Paths:
   - Supabase DB password: `C:/Apps/healgrid-app/.secrets/nexus-db.txt` (nexus-1 for migrations; nexus-2/nexus-4 ask nexus-1 to apply theirs, or use it the same way for their own merged migration)
   - Supabase secret key: `~/.secrets/nexus-service-role.key` → `SUPABASE_SERVICE_ROLE_KEY_FILE`
   - Zetaris token: `~/.secrets/nexus-zetaris.key` → `ZETARIS_API_KEY_FILE`; `ZETARIS_ORG_ID=1`; REST `http://localhost:8888/api/v1.0`; UI `http://localhost:3000`
   - Supabase URL `https://ukrujnsjucwvytnokbtw.supabase.co`; the publishable key is in Vercel env.
6. **Spec ground rules R1–R12 are non-negotiable:**
   - Zetaris for every agent read;
   - pinned Nemotron lanes;
   - no faked outputs;
   - scores computed in code;
   - tips untrusted;
   - `synthetic: true` on every synthetic row;
   - every claimed engine has a feature + a passing test;
   - ask (via the chief) before Zetaris CREATE, deletes, weight changes or spend.
7. **Machine limits.**
   - Only **nexus-4** runs `next build`. All other lanes (incl. nexus-5, nexus-6) run typecheck, lint and vitest only. nexus-4 owns shared web layout, components and `package.json`.
   - Don't start or stop Docker containers. Zetaris is running; the slot is owned by nexus-chief.
8. **Every PR:** tests for what it adds, `pytest -q` / `npm run typecheck && npm run lint` green, one logical change, conventional commit, and this trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use the advisor tool before committing to an approach and before declaring done, if it's available.

## 4. Reporting
Message **nexus-chief** (SendMessage):
- **at start:** your first 3 steps;
- **on every merge:** PR number, task ids done, anything the next lane needs;
- **immediately when blocked;**
- **otherwise every ~2 h:** a 3-line status.

Keep each message short. Details belong in the PR.
