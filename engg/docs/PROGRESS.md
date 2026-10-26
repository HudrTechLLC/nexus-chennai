---
tags: [nexus, plan]
---

# Progress

Updated at the end of every session (spec O2). Newest first. Phase definitions: [SPEC Part K](SPEC.md#phases).
Related: [DECISIONS](DECISIONS.md) · [DELIVERABLES](DELIVERABLES.md) · [00-INDEX](00-INDEX.md) · [PATH2](PATH2.md)

**Deadline:** 27 Oct 2026 23:45 UTC (28 Oct 05:15 IST). **Target submit:** 27 Oct 17:45 UTC or earlier.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| P0 | Foundations: skeleton, adapters, smoke test, Supabase, Vercel | 🟡 smoke: all PASS except vision lane (Super VL opt-in pending) |
| P1 | Synthetic Chennai generator | ⏳ |
| P2 | Zetaris data layer | ⏳ blocked: Zetaris install |
| P3 | Extraction + World Model (+ Scout Intent) | ⏳ blocked: Nightshift |
| P4 | Linking core + H-MEM (+ Markovian) + eval | ⏳ |
| P5 | Police console core | ⏳ |
| P6 | Judge-path hardening | ⏳ |
| P7 | Pulse Map (lean) | ⏳ |
| P8 | Public portal (lean) | ⏳ |
| P9 | FIR form + remaining sources | ✂️ cut unless time allows |
| P10 | Submission package | ⏳ |

## Blockers

| Vision lane: Nightshift excludes Super VL after NVIDIA failures | Team: opt in via `NVIDIA_SUPER_VL=true`, restart Nightshift | P3 vision extraction |

| Blocker | Owner | Needed for |
|---|---|---|
| NVIDIA API key (`nvapi-…`): created; to be entered in Nightshift only | Team | P3+ |
| AWS S3 bucket `nexus-chennai-data` (or a Zetaris-supported alternative) | Team | P2 |

## Log

> Live progress chart and full task list: `/docs/progress` in the web app (source `workstreams.json`).

### 2026-10-26 · Zetaris live (branch `chore/zetaris-live`)
- **Memory fixed:** Reason/RAV antivirus (`rsEngineSvc`, 10.5 GB) was uninstalled by the team. Free RAM went from 0.3 GB to 11.2 GB, and Windows Defender is now active.
- **Zetaris started:** `docker compose up -d` in `C:\Apps\zetaris-platform`, with the Docker slot claimed in `C:/Apps/_docker-slot/owner.txt`.
  - `verify.sh` passes 8/9. The ninth item (`bootstrap`) is still loading Zetaris's own sample data.
- **API access:** token created (org ID 1).
- **Smoke check:**
  - Zetaris REST `SELECT 1`: PASS
  - Supabase: PASS
  - sample mode: PASS
  - Nightshift: SKIP (not installed)
- **Fix:** the sample-mode smoke check now also ignores `ZETARIS_API_KEY_FILE`.

### 2026-10-26 · Supabase live (branch `feat/supabase-setup`)
- **Project:** `nexus-qa` (`ukrujnsjucwvytnokbtw`, Singapore), created by the team in the dashboard.
- **Migration:** `0001` applied with the new `scripts/db_migrate.py`. RLS is verified and anon is denied everywhere (D-014).
- **Secrets from files:** the backend reads secrets via `*_FILE` settings, so no secret goes into a repo `.env`.
- **Smoke check:**
  - Supabase: PASS
  - city pack and sample mode: PASS
  - Zetaris and Nightshift: SKIP
- **Vercel:** function region moved to `sin1`.
- PR #2 merged. Engg Docs are live at https://nexus-chennai.vercel.app/docs/progress

### 2026-10-26 · Engg Docs + tracker in the web app (branch `feat/engg-docs`)
- PR #1 merged.
- **Vercel:** project `nexus-chennai` created in the HUDR team.
  - Framework set to Next.js.
  - Build allowed to read `engg/docs`.
  - Vercel login now applies to previews only, so the production URL is public.
- **Engg Docs in the app:**
  - `/docs` menu with Progress plus the 16 spec tabs;
  - project notes;
  - `/docs/progress`: overall %, countdown to the target and the deadline, stacked bars by workstream and by phase, blockers, and the full task list.
- **Diagrams:** re-exported as strict XML so they render as images.
- **Zetaris:** registry sign-in done and preflight passes; images are downloading. Start is waiting for ≥ 2 GB free RAM.
- **Supabase:** still blocked. The CLI token is invalid and the Supabase MCP is read-only and scoped to another project.

### 2026-10-26 · P0 scaffold (branch `feat/p0-scaffold`)
- **API:** FastAPI app with `/health` (shows each connector as live, sample or down) and an honest `/run`. `/run` returns 501 "not_implemented" until the agent graph exists in P4, so no output is faked.
- **Nightshift connector:**
  - pinned lanes; `meterless/auto` refused (R2);
  - sends the `meterless-app` and `meterless-scope` headers;
  - logs pinned model, routed model and receipt on every call;
  - retries server errors twice;
  - in sample mode, replays only fixtures recorded from live calls and fails if none exist.
- **Zetaris connector:**
  - uses the confirmed REST format (D-011);
  - agents can run only named queries;
  - logs query id, row count and time;
  - falls back to DuckDB in sample mode.
- **Supabase connector:** write-side only, using the service role, in the API process only.
- **Other:**
  - tracing to `logs/trace-<run_id>.jsonl` and stdout, with the full D3.12 fields;
  - `run.py`, `scripts/smoke.py`, Dockerfile, `docker-compose.yml`;
  - `cities/chennai/city.yaml`.
- **Tests:** `pytest -q` gives 15 passed; ruff is clean.
- **Smoke check:**
  - city pack: PASS
  - sample mode: PASS
  - Supabase, Zetaris and Nightshift: SKIP (no credentials yet)
- **Web:** Next.js 14.2.35 shell with the public portal (`/`, `/appeals`, `/map`, `/tip`) and `/console`. Screens not built yet are labelled with the phase that builds them. `tsc`, lint and build all pass. `vercel.json` sets region `bom1`.
- **Database:** migration `0001_foundation.sql` creates stations, wards, profiles and runs, plus the `wm` / `hmem` schemas and the `zetaris_reader` role. RLS is on and anon has no access. Not applied yet: the Supabase project doesn't exist.

### 2026-10-26 · docs
- Read and converted all 16 spec tabs into [SPEC](SPEC.md). Exported the three architecture diagrams to `diagrams/`.
- Created GitHub repo `HudrTechLLC/nexus-chennai` (private until submission).
- Created this docs folder: index, decisions D-001…D-010, architecture with the Vercel shape, city packs, setup, deliverables, hackathon digest, sponsor-tech draft.
- Studied the Meterless engines repo at commit `1742dec`: reference code exists for H-MEM, World Model and Markovian; Scout Intent has docs and evals only.
- **Next:** P0 scaffold (FastAPI `/health` + `/run`, adapters, tracing, `smoke.py`, Next.js shell), Vercel project linked to the repo, Supabase migrations once the project exists.
