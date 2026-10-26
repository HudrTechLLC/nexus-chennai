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
| D-006 | 2026-10-26 | ✅ (see D-017) | Nightshift model ids: confirm on `GET /v1/models` whether pinned `nvidia/*` ids are accepted |
| D-007 | 2026-10-26 | ✅ | Repo `HudrTechLLC/nexus-chennai`, **private until submission**, then public |
| D-008 | 2026-10-26 | ✅ | Meterless engines are **ported to Python** from the Apache-2.0 TypeScript references at commit `1742dec` |
| D-009 | 2026-10-26 | 🟡 | Scope for the deadline: P0–P6 + **P7 (Pulse Map, lean)** + **P8 (portal, lean)** + P10; cut data-source breadth first |
| D-010 | 2026-10-26 | ⏳ | Vercel request logs record IP addresses, which conflicts with the WS4 "no IP in logs" check |
| D-011 | 2026-10-26 | ✅ | Zetaris REST format confirmed from `zetaris/getting-started` @ `6a2fbaa` |
| D-012 | 2026-10-26 | ✅ | Web app stays on **Next.js 14** (14.2.35, the latest 14.x patch), as the spec says |
| D-018 | 2026-10-26 | ✅ | Schema deviations: tip_messages.sender, factor weapon_tool, history-sheet columns, anon revoked in public (RPCs grant explicitly) |
| D-017 | 2026-10-26 | ✅ | Nightshift live: fast=Lightning 30B, reason=Ultra 550B (Super 120B not served to our key), vision=Super VL excluded (opt-in pending); token read from runtime file |
| D-016 | 2026-10-26 | ✅ | Scoring details from PR #8 + evidence-coverage guard (single-factor pairs cannot reach high) |
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

## D-016 · Scoring details (from PR #8, nexus-3) (2026-10-26)
- **Struck factors:** a struck factor keeps its weight with value 0, so a Skeptic strike can never raise a score.
- **Order of operations:** base weighted score → H-MEM delta (summed, capped ±0.08) → forensic floor 0.8 → clamp to [0,1] → round to 4 dp → band (high ≥ 0.75, medium ≥ 0.55).
- **Space–time:** the same time band gives a ×1.2 boost on space_time.
- **Vehicle:**
  - partial plate = 0.6 + 0.3 × known/len;
  - ANPR at both scenes = 0.85;
  - a match on description only is capped at 0.5.
- **Missing data:** corroboration and offender_return return `None` (no data), not 0, when nothing is found, so missing evidence doesn't count against a pair.
- **Evidence-coverage guard** (added by the chief): coverage is the sum of the weights of factors that have data.
  - If coverage < 0.50, the band is capped at medium.
  - If fewer than 2 factors have data, no alert is raised.
  - Coverage is shown on the alert.
  - Why: renormalisation could otherwise let a pair with a single factor reach "high". This is a guard, not a weight change.

## D-017 · Nightshift lanes verified on the live runtime (2026-10-26)
**Setup.** Nightshift 1.2.7 runs locally at `http://127.0.0.1:8088/v1`, with the NVIDIA provider connected.
- The app reads the runtime's own token file through `METERLESS_RUNTIME_TOKEN_FILE=%LOCALAPPDATA%/ai.meterless.runtime/proxy-token`. Nobody copies the token by hand.
- `GET /v1/models` lists 86 ids: `meterless/*` routing modes, `local-runtime/*`, and 13 `nvidia/*` models.
- **This settles D-006: pinned `nvidia/*` ids are accepted, and the response's `model` field echoes the pinned id.**

Each lane was tested with a real chat request:

| Lane | Pinned model | Result |
|---|---|---|
| fast | `nvidia/nemotron-3.5-lightning-30b-a3b` | ✅ 200, about 7 s for one sentence (reasoning model: about 435 completion tokens) |
| reason | `nvidia/nemotron-3-ultra-550b-a55b` | ✅ 200, about 1–3 s. **Replaces** `nvidia/nemotron-3-super-120b-a12b`, which returns 404 "not served to the configured key" |
| vision | `nvidia/nemotron-3.5-super-vl-120b-a12b` | ❌ 400: Nightshift has excluded it after repeated NVIDIA failures. Opt-in via `NVIDIA_SUPER_VL=true` is pending. Until then the E2 fallback applies (officer caption, logged as degraded) |
| embed | `nvidia/nemotron-3.5-embed-1b` | available |

**Agent call rules (for all agents):**
- `max_tokens` ≥ 1024;
- ask for JSON only and parse the last JSON object in the content;
- retry transport errors and 5xx (incl. a 502 `provider_error`) up to 3 attempts in total, as the adapter does, then degrade;
- never use `meterless/auto` (R2).

The sponsor text names Ultra 550B as the reasoning model, because it is what actually runs.

## D-018 · Schema deviations from the spec text (PR #10, nexus-1) (2026-10-26)
- **`tip_messages`:** the sender column is named `sender`, not `from`, because `from` is a reserved word.
- **Weapon factor:** named `weapon_tool` everywhere, following F2 and the scoring code. D3.11's example says `weapon`.
- **History sheets:** D3.10 gives no columns, so these were chosen: `sheet_id`, `person_ref`, `station_id`, `opened_on`, `category`, `mo_tags`, `residence_ward`, `active`.
- **Anon access:** `0002` revokes anon in schema `public`, including default privileges. Every public RPC must `grant execute ... to anon` explicitly.
- **One copy of the weights:** `app.models` imports the F2 weights and bands from `app.scoring`.
- **`crimes_citywide`:** a `security_invoker` view over a definer function. Columns: crime_id, station_id, category, sub_type, cell (H3 r8), week, mo_tags, visual_tags.
- **Live RLS tests pass 4/4:**
  - anon sees 0 relations and 0 functions;
  - an officer sees only own-station crimes;
  - the citywide view hides narrative and address.

## D-019 · Pulse Map layers come from display-only projection tables (nexus-1, approved) (2026-10-26)
- **The problem:** the Pulse Map (G3) needs CCTV/ANPR cameras, ANPR reads, 112 calls and release density. Those live in the generated S3-style files (D1), which Zetaris federates. The Vercel app cannot reach Zetaris.
- **The decision:** `0003_map_layers.sql` adds the projection tables `map_cctv_cameras`, `map_anpr_cameras`, `map_anpr_reads` (only reads linked to a crime or alert), `map_call_cells` (H3 r9 × category × hour) and `map_release_density` (per ward). The seed loads them from the same generated files. Police read them under RLS; anon cannot.
- **The rule:** these tables are a **UI cache, never an agent source**. Agents read the originals only through Zetaris (R1), just as `public_map_cells` serves the public map (D-003).

## D-020 · Engine state persisted in `public` with `wm_` / `hmem_` tables (nexus-2, approved) (2026-10-26)
- **Where:** `0005_01_engines.sql` creates `wm_entities`, `wm_edges`, `wm_observations`, `hmem_memories` and `hmem_ledger` in `public`, not in the `wm` / `hmem` schemas. PostgREST exposes only `public`, and project settings stay unchanged.
- **Access:** RLS is on and anon is revoked. Analyst, supervisor and admin read all `wm_*`. A station officer reads only entities and edges attached to a crime they can read. Any police role can read `hmem_*`.
- **Integrity:** `hmem_ledger` is append-only; a trigger rejects UPDATE and DELETE.
- **Writes:** only the API's service role writes, through `ENGINES_PERSIST=supabase` (off by default and in tests). `alert_id` is plain text, with no foreign key.

## D-021 · Official rules checked; vision lane finding (2026-10-26)
- **Rules:** checked all four official HackOS documents against the plan; see [RULES_CHECK](hackathon/RULES_CHECK.md). Every hard requirement is met by design. Five process gaps have owners: a root Dockerfile, input/output examples, a sample-mode test with services stopped, a secret check of the video and deck, and testing the video link logged out. The organiser PDFs stay local and are gitignored, because the repo goes public.
- **Super VL is now enabled.** The `NVIDIA_SUPER_VL` gate is read from Nightshift's engine-kv store, not from the environment. The value was set with Nightshift stopped, and a backup of the store was kept.
- **Images still fail.** Text calls to `nvidia/nemotron-3.5-super-vl-120b-a12b` succeed. **Every request with an image is refused by Nightshift with `no_vision_model`, on every route**, including local PaddleOCR-VL. This has been reported to Meterless.
- **Effect on the product:** the Extractor records an honest "vision unavailable" trace and falls back to the caption text, so no visual extraction is ever faked. Vision is not a rule requirement.

## D-022 · Zetaris file storage is Supabase Storage, not AWS (2026-10-26)
- **What:** the generated CSV and Parquet files live in a private Supabase Storage bucket, `nexus-chennai-data`, on `nexus-qa`. Zetaris registers them in place through the S3-compatible endpoint (`https://ukrujnsjucwvytnokbtw.storage.supabase.co/storage/v1/s3`, path-style, `ap-southeast-1`), using its `s3Endpoint` and `useS3PathStyleAccess` options. Recommended by nexus-1 and approved.
- **Why:** it costs $0 (the bucket is about 60–100 MB, inside the free tier), needs no new account, and stays a separate object store that Zetaris federates. That keeps the data-layer story intact.
- **Keys:** the access key is read from `~/.secrets/nexus-s3.key` only, and redacted in every log. The team accepted that this key appeared in a chat transcript; it is short-lived and is **deleted after the hackathon**.
- **Fallback:** AWS S3 in `ap-south-1`, only if Zetaris cannot sign requests for Supabase's endpoint. That would need the team's approval and an account.

## D-023 · Tip passphrases hashed with bcrypt inside the database (deviation from J1) (2026-10-26)
- **Spec J1 says Argon2id.** Doing that in the Next.js route handler would mean the handler needs the stored hash to verify a tip-status lookup. The only way to get it would be an anon-callable RPC that returns the hash.
- **The decision:** `submit_tip` and `tip_status` (security-definer RPCs) hash and verify with pgcrypto bcrypt (`crypt(p, gen_salt('bf', 12))`), so the hash never leaves Postgres.
- **Safeguards:**
  - one generic error for both a wrong code and a wrong passphrase;
  - an attempt limit per tip code;
  - the route handler only rate-limits and strips EXIF;
  - passphrases are never logged.
- **Trade-off:** bcrypt is weaker than Argon2id against GPU cracking, but each tip code is random and attempts are limited online. The README states the deviation.

## D-024 · A 13th named query, `q_hex_counts` (nexus-2, #35) (2026-10-26)
The spec's E5 list has 12 named queries. The Hotspot detector (WS2-18) adds `q_hex_counts`: crime counts per H3 cell per time window, read through Zetaris, with a DuckDB twin.
- **Statistics:** a Poisson upper-tail test against each cell's own baseline of 8 windows, shrunk toward the citywide rate. No model is involved.
- **Code:** it lives in `adapters/zetaris_queries_n2.py` and is merged into `NAMED_QUERIES`, a file split agreed between nexus-1 and nexus-2.

## D-025 · Traces and system status are stored in Supabase for the web console (nexus-3, migration 0006) (2026-10-26)
- **The problem:** the Vercel console cannot read the laptop's `logs/trace-*.jsonl`.
- **The decision:** `0006` adds two tables.
  - `trace_events`: key `(run_id, seq)`. It holds every D3.12 field (agent, action, model, routed model, receipt id, Zetaris query ids, engine, confidence, retry count, status).
  - `system_status`: one row per component, with its state and the time it was checked.
- **Who can access them:** police roles can read; anon cannot; only the service role writes.
- **How rows are written:** they are **copied from the tracer's JSONL by `SupabaseStore.finish_run`, never hand-made** (R3).
  - Before upsert, summaries go through redaction: no secrets, no tip passphrases, and no raw tip text.
  - The worker writes a heartbeat into `system_status` on every pass. A failed heartbeat never fails the pass.
- **Ownership:** the `0006` migration range is assigned to nexus-3.

## D-022a · Amendment: Zetaris reads its files from its own internal file store (2026-10-26)
- **What happened:** Zetaris could not read Supabase Storage over S3. The driver log shows `SdkClientException ... Received fatal alert: handshake_failure` from `S3AFileSystem` (hadoop-aws 3.3.5). The JVM inside the Zetaris container cannot complete a TLS handshake with `*.storage.supabase.co`. This is a container TLS/cipher problem, not a signing problem; the boto3 SigV4 check against the same key works.
- **The decision:** CSV and Parquet files go into **Zetaris's internal file store** and are still registered as file sources, so Zetaris still federates them alongside Supabase Postgres. The Supabase bucket stays as a backup copy.
- **Not done:** we will not change the Zetaris container's JVM/TLS settings during the build, because restarting Zetaris would put every lane at risk. The fix (a newer JDK or `-Djdk.tls.client.protocols`) plus a one-line endpoint switch is documented in `zetaris/README` as a future option and stated as a limitation.
- **Still true:** no AWS, no spend.

## D-026 · Lightning runs with thinking off for extraction-type agents (nexus-3, #58) (2026-10-26)
- **The finding:** with thinking on, Nemotron 3.5 Lightning spent its whole `max_tokens` budget reasoning and returned a 502 `empty_response`, taking about 56 s and 4,088 tokens.
- **The fix:** sending `chat_template_kwargs.enable_thinking=false` makes the same extraction take about 12 s and 110 tokens.
- **Where it applies:** the Extractor, Sanitiser and Briefer (structured-output jobs) run Lightning with thinking **off**. The Planner on Nemotron Ultra keeps reasoning on.
- **Supersedes:** the D-017 rule "`max_tokens` ≥ 1024", for thinking-off calls only.
- **Traceability:** the trace records the model and the receipt on every call.

## D-027 · The embed lane uses TF-IDF and feature vectors in code (nexus-2) (2026-10-26)
- **The finding:** Nightshift 1.2.7's local API (`engine/server.mjs`) serves only `POST /v1/chat/completions` for model calls.
  - `POST /v1/embeddings` returns 404 for every embed model it lists.
  - Those models are internal R11 "scribe" lanes (`js/engine/genverify.js`, `lane-state.js --embeddings`).
  - The in-app embedder (`js/engine/embed.js`) uses a local Ollama with no models installed.
- **The decision:** `services/api/app/engines/similarity.py` serves `embed(texts)` with the spec E2 fallback: TF-IDF plus feature vectors, with no model call. It traces each use as `embed_fallback`. Similar-MO matching and text search use it.
- **What we don't do:** call scribe or Ollama ports directly, which would bypass Nightshift (R2).
- **Later:** if Nightshift exposes `/v1/embeddings`, pinning `LANE_EMBED` turns the live path on with no code change.
- **Submission:** the Nemotron embed model is **not** claimed.

## D-028 · Console reads for series, stations, memory and graph go through jsonb RPCs (nexus-6) (2026-10-26)
- **The RPCs:**
  - `0004_06_01`: `station_link_matrix`, `series_overview`;
  - `0004_06_02`: `hmem_effects`, `wm_graph`.
- **How they work:** they are **security invoker** (RLS still applies to the caller), read-only, and return `jsonb`.
- **Why:** PostgREST's 1,000-row cap and multiple round-trips; one call per page.
- **Checked:** all four return 200 for the five demo users (200–450 ms), and anon is refused (42501).
- **Owner:** nexus-6. The migrations use nexus-4's `0004_06_*` sub-range, by agreement.

## D-029 · FIR capture, evidence and search details (nexus-5) (2026-10-26)
- **FIR ids:** `file_fir` gives each new FIR the next number for its station and year (max+1, e.g. `CHN-AD-2026-001231`) and a random `source_row_id`. So the generator re-seed (which keys its rows by `uuid5(crime_id)`) never retires or overwrites a console-filed FIR, and a clash refuses (#87).
- **Evidence keeps the original bytes:** no re-encoding and no EXIF stripping.
  - A server-side sha256 is taken over the original.
  - Each upload adds a custody entry `{at, by, action:"uploaded", sha256}`.
  - **What the database enforces (0007_06, #167, applied 26 Oct):** the upload route computes sha256 server-side; the database enforces that the evidence row matches a storage object the caller uploaded (owner, size, mime) and sets uploaded_by + custody itself; the hash itself is not re-verified in the database. Direct INSERT on `evidence_media` / `statements` is revoked; rows go in only through `record_evidence`. `case_diary.author` is set from the signed-in officer by a trigger, not by the client.
  - **Post-hackathon hardening:** have the upload route sign `(path, sha256, bytes)` with a server-only key, and have `record_evidence` accept only a valid signature. Then a direct RPC call can no longer supply a wrong hash for the caller's own file.
  - `captured_at` is read from EXIF.
  - Files are capped at 4 MB, the Vercel body limit.
  - This supersedes the chief's earlier "strip EXIF" instruction, which applies only to **public tips and appeal images**. Re-encoding would break integrity and the chain of custody.
  - Private bucket `evidence`; RLS by `can_write_crime` / `can_read_crime`; anon none.
- **Officer MO corrections** go to `crime_feature_reviews` through `review_features()`, never into the Extractor's row, which keeps its provenance (R3). `zetaris_reader` has a SELECT grant on `crime_feature_reviews` so agents can see reviewed MO.
- **Search provenance (deviation from SRCH-07):** Vercel cannot reach Zetaris, so console search reads Supabase under RLS. Its footer lists the **tables and row counts** it used instead of Zetaris query ids. Agent-side search (`q_search`, D-024 family) still goes through Zetaris.
- **Standing live checks:** `apps/web/scripts/rls-check.mjs` and `apps/web/scripts/evidence-check.mjs` (stored sha256 = recorded = custody; overwrite, other station, anon and public URL all refused; 8/8 on 26 Oct; 9/9 after 0007_06, adding "direct insert refused").

## D-030 · `audit_log` is append-only (nexus-5) (2026-10-26)
- **Rule:** no role, including the service role, can UPDATE or DELETE `audit_log` rows. Only INSERT is allowed. Migration `0007_03` (#124), applied 26 Oct.
- **Checked live as the service role:** insert → 201; DELETE and PATCH → 403 / `42501 "audit_log is append-only"`.
- **Why:** a lane deleted an audit row during testing. An audit trail that can be edited is not evidence.
- **Tests clean up by recording, not deleting:** the e2e suite inserts a `cleanup_test_record` entry instead of removing its audit rows (#126). The final pre-freeze cleanup never touches `audit_log`.
- **Related:** [D-029](#d-029--fir-capture-evidence-and-search-details-nexus-5-2026-10-26) · [LANES](LANES.md)
