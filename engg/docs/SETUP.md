---
tags: [nexus, runbook]
---

# Setup: accounts, services and environment

Every account and service Nexus needs, where each credential goes, and current status. Source: [SPEC O7](SPEC.md#claude-code) and [L5](SPEC.md#deliverables).
Related: [ARCHITECTURE](ARCHITECTURE.md) · [PROGRESS](PROGRESS.md) · [00-INDEX](00-INDEX.md)

> **Credentials never go in the repo, in chat, or inline in a command.** Only `.env.example` with placeholders is committed. The NVIDIA key lives **only** in Nightshift → Setup → Providers → NVIDIA.

| # | Service | Status | Credential goes to |
|---|---|---|---|
| 1 | HackOS (GenAI Works) | ✅ team registered | — |
| 2 | GitHub `HudrTechLLC/nexus-chennai` | ✅ created (private) | — |
| 3 | Vercel (team HUDR, project `nexus-chennai`, root `apps/web`, region `bom1`) | ✅ linked; production public, previews behind Vercel login | Vercel env: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (public values only) |
| 4 | Supabase `nexus-qa` (`ukrujnsjucwvytnokbtw`, Singapore `ap-southeast-1`) | ✅ migration 0001 applied; RLS verified; smoke PASS | app `.env`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (local only, never Vercel) |
| 5 | Zetaris local platform (`C:\Apps\zetaris-platform`, UI http://localhost:3000, REST :8888) | ✅ running; live `SELECT 1` PASS; org ID `1` | app `.env`: `ZETARIS_REST_URL`, `ZETARIS_ORG_ID=1`, `ZETARIS_API_KEY_FILE=~/.secrets/nexus-zetaris.key` |
| 6 | Meterless Nightshift 1.2.7 | ✅ running; NVIDIA connected; lanes per D-017 | app `.env`: `METERLESS_BASE_URL`, `METERLESS_RUNTIME_TOKEN` |
| 7 | NVIDIA build.nvidia.com | ✅ key in Nightshift Providers only | Nightshift Providers tab only |
| 8 | AWS S3 `nexus-chennai-data` | ⏳ | generator `.env`: `AWS_*`; read-only keys in the Zetaris source definition |
| 9 | ElevenLabs | ⏳ | build-time `.env`: `ELEVENLABS_API_KEY` |
| 10 | YouTube (unlisted) + Drive | ⏳ | README + form |
| 11 | Map tiles (Protomaps PMTiles or MapTiler) | ⏳ | `NEXT_PUBLIC_MAPTILER_KEY` if MapTiler |

## Local machine requirements

- **Zetaris:** 16 GB RAM laptop (8 GB and 4 CPUs given to Docker, 15 GB disk), or the AWS managed cluster.
- **Docker discipline:** check that ≥ 2 GB RAM is free before starting containers, and stop them when done.
- **Tooling installed (2026-10-26):** Node 24.6, pnpm 9.15, Python 3.13.7 (the spec targets 3.11; Docker images pin 3.11), Docker 29.8, git 2.49. GitHub CLI is not installed.

## Nightshift contract (to verify, D-006)

| Item | Value |
|---|---|
| Base URL | `http://127.0.0.1:8088/v1`, OpenAI-compatible |
| Auth | Bearer runtime token (`<stateDir>/proxy-token`) |
| Headers | `meterless-app: nexus-chennai`, `meterless-scope: user` |
| Discovery | `GET /v1/models` |
| Status codes | 200 = online; 401/403 = bad token |
| Timeout | 180 s |

## Zetaris REST (spec P0 prompt)

| Item | Value |
|---|---|
| Endpoint | `POST {ZETARIS_REST_URL}/sql-editor/sqls/run` |
| Headers | `Authorization: Bearer <key>`, `X-Org-ID`, a fresh UUID `X-Request-ID` per call |
| Timeout and retries | 60 s, 2 retries |
| DDL | one statement at a time, dry-run before any CREATE (R12) |
| API reference | `http://localhost:8888/redoc/index.html` after install |
