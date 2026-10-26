---
tags: [nexus, plan]
---

# Progress

Updated at the end of every session (spec O2). Newest first. Phase definitions: [SPEC Part K](SPEC.md#phases).
Related: [DECISIONS](DECISIONS.md) · [DELIVERABLES](DELIVERABLES.md) · [00-INDEX](00-INDEX.md)

**Deadline:** 27 Oct 2026 23:45 UTC (28 Oct 05:15 IST). **Target submit:** 27 Oct 17:45 UTC or earlier.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| P0 | Foundations: skeleton, adapters, smoke test, Supabase, Vercel | 🟡 code done; waiting on Supabase project, Vercel link, live Zetaris/Nightshift |
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

| Blocker | Owner | Needed for |
|---|---|---|
| Supabase CLI token invalid (`Invalid access token`) | Team: run `npx supabase login`, or create project `nexus-chennai` (free, Mumbai) in the dashboard and share the project ref | P0 |
| meterless.ai resets the connection, so Nightshift can't be downloaded | Team: ask in HackOS Help Meterless | P0 smoke, P3+ |
| Nightshift may need a dedicated GPU; the laptop has an integrated Intel Arc | Team: confirm cloud lanes (NVIDIA hosted) work from Nightshift | P3+ |
| Zetaris platform download + registry login | Team: Zetaris Cloud account | P2 |
| NVIDIA API key (`nvapi-…`), entered in Nightshift only | Team | P3+ |
| AWS S3 bucket `nexus-chennai-data` (or a Zetaris-supported alternative) | Team | P2 |

## Log

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
