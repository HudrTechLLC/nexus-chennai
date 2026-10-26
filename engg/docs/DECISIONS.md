---
tags: [nexus, adr]
---

# Decisions log

Every decision that changes or clarifies the [SPEC](SPEC.md) is recorded here: the date, what was decided and why. Things the spec says to *verify* are also recorded here once checked (model ids, Zetaris DDL).
Related: [ARCHITECTURE](ARCHITECTURE.md) · [PROGRESS](PROGRESS.md) · [00-INDEX](00-INDEX.md)

Status: ✅ decided · 🟡 provisional (revisit) · ⏳ to verify on the live system

| ID | Date | Status | Decision |
|---|---|---|---|
| D-001 | 2026-10-26 | ✅ | Backend in **Python 3.11 + FastAPI + LangGraph**, as the spec says |
| D-002 | 2026-10-26 | ✅ | Project documentation lives in **`engg/docs/`**, not `docs/` |
| D-003 | 2026-10-26 | ✅ | Web app (public portal + police console + Pulse Map) **deployed on Vercel**; agents stay local |
| D-004 | 2026-10-26 | ✅ | All city-specific data and settings go in a **city pack** (`cities/<city>/`), selected by `CITY` |
| D-005 | 2026-10-26 | 🟡 | Claim **H-MEM + World Model** first; Scout Intent and Markovian only if built *and* tested |
| D-006 | 2026-10-26 | ⏳ | Nightshift model ids: confirm on `GET /v1/models` whether pinned `nvidia/*` ids are accepted |
| D-007 | 2026-10-26 | ✅ | Repo `HudrTechLLC/nexus-chennai`, **private until submission**, then public |
| D-008 | 2026-10-26 | ✅ | Meterless engines are **ported to Python** from the Apache-2.0 TypeScript references at commit `1742dec` |
| D-009 | 2026-10-26 | 🟡 | Scope for the deadline: P0–P6 + **P7 (Pulse Map, lean)** + **P8 (portal, lean)** + P10; cut data-source breadth first |
| D-010 | 2026-10-26 | ⏳ | Vercel request logs record IP addresses, which conflicts with the WS4 "no IP in logs" check |
| D-011 | 2026-10-26 | ✅ | Zetaris REST format confirmed from `zetaris/getting-started` @ `6a2fbaa` |
| D-012 | 2026-10-26 | ✅ | Web app stays on **Next.js 14** (14.2.35, the latest 14.x patch), as the spec says |
| D-015 | 2026-10-26 | ✅ | Four build lanes (nexus-1…4) with full scope; engines run as the TypeScript references in a sidecar so official conformance runs (revises D-008) |
| D-014 | 2026-10-26 | ✅ | Supabase project is **`nexus-qa`** (`ukrujnsjucwvytnokbtw`) in **Singapore** (`ap-southeast-1`), HUDR LLC org; Vercel functions moved to `sin1` |
| D-013 | 2026-10-26 | ✅ | Engg Docs (16 spec tabs, notes, progress tracker) published in the web app at `/docs`; production URL public, previews need Vercel login |

---

## D-001 · Python backend
The spec's stack (C2) is Python. Porting the Meterless TypeScript references to Python costs some time. But it keeps LangGraph, Pydantic and DuckDB in one runtime, and matches every phase prompt in Part K.

## D-002 · Docs in `engg/docs/`
The team asked for all progress, architecture and spec documents under `engg/docs/`. Read every spec mention of `docs/X` as `engg/docs/X`, including `hackathon/`, `validation/`, `SPONSOR_TECH.md` and `PROGRESS.md`. Links between notes use standard Markdown links so they work on GitHub (for judges) and in Obsidian.

## D-003 · Vercel hosting for the web app
The spec lists Vercel as optional (O7 #12). The team wants the Pulse Map and the public portal online.

- **Vercel** hosts one Next.js app (`apps/web`): the public portal at `/` and the police console at `/console`. Function region is `bom1` (Mumbai), next to Supabase `ap-south-1`.
- **The laptop runs** FastAPI, LangGraph, the worker, Zetaris and Nightshift. None of them is exposed to the internet: no tunnel, no public `:8000`.
- **Supabase is the bridge.**
  - The local pipeline writes alerts, published appeals, public map cells and series into Supabase.
  - The web app reads them through RLS, and alerts arrive live via Realtime.
- **Public map** reads only a dedicated `public_map_cells` table: H3 cell, crime type, week and count, with a minimum-count cutoff. It never reads a view over FIRs, because a plain view runs with the owner's rights and could leak rows to `anon`.
- **Tip intake** is a Next.js route handler.
  - It does only the deterministic steps: size and type limits, metadata (EXIF) stripping, rate limiting and issuing the tip code.
  - It then calls the `submit_tip` RPC, which stores the tip with `screen_status='pending'`.
  - Scout Intent / Tip Guard runs in the local worker.
  - The Zetaris tip views exclude anything not screened clean, so rule R8 still holds.
  - Face blur (OpenCV) runs in the worker. Raw uploads go to a private bucket.
- **Keys on Vercel:** only the Supabase URL and the anon / publishable key. The service-role key never goes to Vercel.
- **`anon` has no access to any table** (spec Part I). It can only `EXECUTE` a few narrow `security definer` functions, each returning or accepting a fixed shape:
  - `submit_tip` (insert only);
  - `tip_status(code, passphrase)`;
  - `public_incidents_list`;
  - `public_map_cells`.
- **How this differs from Part J:** the spec routes tips through FastAPI. On a public host that would mean exposing the laptop. These RPCs keep the same guarantees: no table access for `public`, and no IP stored by the app.
- **The local run is unchanged.** `docker compose up` still serves the web app on 3001 against the same Supabase, so the fresh-clone check (L3) does not depend on Vercel.

## D-004 · City packs
The spec is written for Chennai, and a second city should not need code changes. The `cities/chennai/` pack holds:

- `city.yaml`: name, map centre and bounds, H3 resolution, timezone, region
- `stations.geojson` and `wards.geojson`
- `law_sections.csv`: the IPC ↔ BNS mapping
- `generator/`: vocabulary for names, places, vehicles, festivals and the planted series
- `sources.yaml`: which feeds exist and their Zetaris names
- `i18n/`: UI text and appeal templates

Code reads the pack named by `CITY`. Another Indian city needs only a new pack. Another country also needs new law codes, source adapters and privacy rules.

## D-005 · Engines claimed
- World Model and H-MEM have TypeScript reference code in `Meterless/Meterless` (`engines/world-model/reference`, `engines/hmem/reference`).
- Markovian also has reference code.
- Scout Intent has only docs, evals and examples.

The rules disqualify an engine that is claimed but not working and tested (R5). So `metadata.json` lists only engines with a passing test, and this entry is updated as engines land.

## D-006 · Nightshift model ids (to verify)
The spec pins `nvidia/nemotron-3.5-lightning-30b-a3b`, `nvidia/nemotron-3.5-super-vl-120b-a12b` and `nvidia/nemotron-3-super-120b-a12b`. Two documents disagree:

- The Meterless repo's agent guide (`docs/agent-ready/add-meterless-provider.md`, Runtime 0.90.0) describes model ids as routing modes (`meterless/*`), discovered via `GET /v1/models`.
- The same contract specifies:
  - base URL `http://127.0.0.1:8088/v1`;
  - a Bearer token from `<stateDir>/proxy-token`;
  - headers `meterless-app` and `meterless-scope: user`;
  - HTTP 401/403 means unauthorized;
  - a 180 s timeout.

**To do when Nightshift is running:** list the models, try a pinned `nvidia/*` id, and record which id each lane uses and the routed model Nightshift returns. Rule R2 (never `meterless/auto`) stands.

## D-007 · Repository
`HudrTechLLC/nexus-chennai` was created on 2026-10-26 as private and must be made public before submission (WS5 gate). Vercel team: **HUDR** (`team_xGybk0LHvMWcZDgjkpnGL5P9`), which has the HudrTechLLC GitHub namespace installed.

## D-008 · Meterless engines are ported, not vendored
Source: `github.com/Meterless/Meterless`, commit `1742dec56a66e58eef9dda2d2b865823758ca8cd`, Apache-2.0. The Python ports live in `services/api/app/engines/*`. Each file header names the reference file it follows. The README's "Third-party code and licences" section credits it, and the submission form lists it as pre-existing third-party code.

## D-009 · Scope for the deadline
The deadline is 27 Oct 23:45 UTC, and the spec says to submit ≥ 6 h early. The order of work:

1. **Must:** P0–P6 + P10.
2. **Also wanted:** lean P7 and lean P8.
   - Pulse Map: H3 hex layer, crime-type filter, time scrubber.
   - Portal: appeals list, fuzzed map, tip form, tip status.
3. **Cut first if late:** number of data sources (keep at least 4 storage types), P9 FIR form, constellation mode, voice tips.

## D-010 · IP addresses in Vercel logs (to resolve)
WS4 requires "No IP / user agent in logs for `/api/public/*`". Vercel's platform request logs record client IPs, and the app cannot turn that off. Mitigations:

- The app never logs or stores IP or user agent.
- Rate limiting uses a short-lived salted hash.
- Log drains stay off.
- The limitation is disclosed in the README and in [SPEC Part J](SPEC.md#security).

If the gate needs a strict pass, the local Docker portal (no platform logs) is what the gate is run against.

## D-011 · Zetaris REST format
Read from `scripts/zetaris_sql.py` in `github.com/zetaris/getting-started`, commit `6a2fbaa47c32c9ac33f6584c64b43b146c621bed`:

- **Endpoint:** `POST {ZETARIS_REST_URL}/sql-editor/sqls/run`
- **Body:** `{"queryId": <uuid>, "sql", "source": "SqlEditor", "limit"}`
- **Headers:**
  - `Authorization: Bearer <api key>`
  - `X-Org-ID` (numeric)
  - a fresh UUID `X-Request-ID`
- **Response:** `{"data": [[...]]}`
- **Errors:** 401 = bad key; 400 = bad org id or a non-UUID request id.
- **SQL:** one statement per call, no trailing semicolon.

The adapter uses our generated `queryId` as the Zetaris query id shown in traces and on alert cards. The `AGENTS.md` safety rules in that repo also apply here:

- start read-only;
- dry-run every create script;
- never call port 8889.

## D-013 · Engg Docs in the web app
The team wants one shareable link to the spec and to live progress.

- **What is published:** the web app serves `/docs`:
  - all 16 spec tabs;
  - the project notes;
  - `/docs/progress`, built from `workstreams.json`.
- **How it stays in sync:** `apps/web/scripts/sync-docs.mjs` copies `engg/docs` into the app at build time. `engg/docs` stays the only source; generated copies are gitignored. Every merge to `main` redeploys.
- **Access:**
  - Vercel's login wall is now on **preview deployments only**, so the production URL can be shared with the team.
  - The repo itself stays private until submission.
  - The docs contain no secrets: CI runs a secret scan and SETUP.md lists only placeholder names.
- **Updating progress:** edit the task status in `workstreams.json` and merge. The chart and the task list update on the next deploy.

## D-014 · Supabase project and region
The team created the project in the dashboard:

- **Name and ref:** `nexus-qa`, ref `ukrujnsjucwvytnokbtw`, in the HUDR LLC organisation (Pro plan, micro compute).
- **Region:** Singapore (`ap-southeast-1`), not Mumbai as the spec assumed.
  - The extra latency from India is about 30–40 ms per request, which is acceptable for the hackathon.
  - Recreating the project to move it isn't worth the time.
  - The Vercel function region is now `sin1` to sit next to the database, and the city pack records both regions.

**How the migration was applied:**
- `scripts/db_migrate.py` connects through the session pooler and applies each file in its own transaction. Applied migrations are recorded in `public.schema_migrations`, which has RLS on and no anon or authenticated access.
- `0001` now installs `postgis`, `pgcrypto` and `pg_trgm` into the `extensions` schema, as Supabase recommends.
- Verified after applying:
  - all tables have RLS on;
  - 6 policies are in place;
  - the anon role is denied on every table;
  - the `wm` and `hmem` schemas exist;
  - the `zetaris_reader` role exists (no login yet).

**Where the credentials are:**
- **Database password:** `C:/Apps/healgrid-app/.secrets/nexus-db.txt` (gitignored there).
- **Secret key:** `~/.secrets/nexus-service-role.key`.

The backend reads keys through `*_FILE` settings, so no secret sits in a repo `.env`.

## D-015 · Four build lanes, full scope, engines as a TypeScript sidecar (2026-10-26)
The team asked to deliver the whole spec with nothing cut, using four Claude Code lanes (nexus-1…4). nexus-chief coordinates. Ownership, interfaces and merge rights are in [LANES](LANES.md).

**Scope.** All tasks previously marked "cut" are back in scope. These were added:
- domain models + core schema;
- storage for Zetaris;
- the engines sidecar;
- Hotspot, Sanitiser and Briefer agents;
- series/memory/graph pages.

**D-008 revised.** The official Meterless conformance runners expect a TypeScript implementation module, so the engines are **vendored TypeScript references run as a local sidecar** instead of Python ports. The conformance suites then run unchanged, and the Python agents call the sidecar through `app.engines`.

**Merge rights.** Lanes merge their own PRs when CI is green and the diff stays in their owned paths. Migrations are applied only after merge, by the owning lane. Vercel deploys `main` automatically.
