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
| P0 | Foundations: skeleton, adapters, smoke test, Supabase, Vercel | 🟡 in progress |
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

### 2026-10-26
- Read and converted all 16 spec tabs into [SPEC](SPEC.md). Exported the three architecture diagrams to `diagrams/`.
- Created GitHub repo `HudrTechLLC/nexus-chennai` (private until submission).
- Created this docs folder: index, decisions D-001…D-010, architecture with the Vercel shape, city packs, setup, deliverables, hackathon digest, sponsor-tech draft.
- Studied the Meterless engines repo at commit `1742dec`: reference code exists for H-MEM, World Model and Markovian; Scout Intent has docs and evals only.
- **Next:** P0 scaffold (FastAPI `/health` + `/run`, adapters, tracing, `smoke.py`, Next.js shell), Vercel project linked to the repo, Supabase migrations once the project exists.
