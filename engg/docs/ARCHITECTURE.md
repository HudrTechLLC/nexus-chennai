---
tags: [nexus, architecture]
---

# Architecture

How Nexus is built and deployed. The authoritative design is [SPEC Part C](SPEC.md#architecture). This note adds the deployment shape agreed in [DECISIONS](DECISIONS.md) D-003 and D-004.
Related: [SPEC](SPEC.md) · [DECISIONS](DECISIONS.md) · [SETUP](SETUP.md) · [CITY_PACKS](CITY_PACKS.md) · [00-INDEX](00-INDEX.md)

## 1. Deployment: what runs where

```
                 INTERNET                                   TEAM LAPTOP (never exposed)
┌──────────────────────────────────────┐        ┌───────────────────────────────────────────┐
│ Vercel  (team HUDR, region bom1)     │        │ services/api  FastAPI + LangGraph  :8000  │
│  apps/web  Next.js                   │        │ worker        same image, queue jobs      │
│   /            public portal         │        │ Zetaris       local Docker  REST :8888    │
│   /appeals     police-approved posts │        │ Nightshift    Meterless runtime   :8088   │
│   /map         fuzzed hex map        │        │      └─▶ NVIDIA Nemotron (key only here)  │
│   /tip         anonymous tip + CCTV  │        └───────────────┬───────────────────────────┘
│   /console/*   police console        │                        │ writes alerts, appeals,
│   /console/map Pulse Map             │                        │ map cells, series, features
└───────────────┬──────────────────────┘                        │ reads via Zetaris (R1)
                │ anon key + user JWT (RLS)                      │
                ▼                                                ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ Supabase  nexus-chennai  (ap-south-1 Mumbai)                 │
        │  Postgres+PostGIS · Auth · RLS · Realtime · Storage          │
        └──────────────────────────────────────────────────────────────┘
                ▲  registered as a source (read-only role zetaris_reader)
                │
            Zetaris ──also federates──▶ S3 nexus-chennai-data (CSV, Parquet) · REST feeds
```

- **Same app locally:** `docker compose up` serves `apps/web` on 3001 against the same Supabase project. Judges can run everything without Vercel.
- **Data flow rules:**
  - Agents read only through Zetaris named queries (R1).
  - All writes go to Supabase.
  - The browser talks only to Supabase, through RLS, and to the Vercel route handlers.

## 2. Layers (spec C1)

![C1 layers](diagrams/c1-layers.svg)

## 3. Request flow: new FIR to link alert (spec C3)

![C3 request flow](diagrams/c3-request-flow.svg)

## 4. Agent graph (spec C4)

![C4 agent graph](diagrams/c4-agent-graph.svg)

- **Not a fixed chain.** The graph has:
  - a Scout Intent router;
  - a Planner ↔ Zetaris loop of up to 3 rounds;
  - a Linker that scores in code;
  - a Skeptic that re-queries, strikes or sends back, up to 2 rounds;
  - a human approve / reject gate;
  - H-MEM feedback.
- **Hard deadline:** 5 minutes per run.

## 5. Public tip path (R8 kept on a public host)

1. Browser → `POST /api/public/tips` (Vercel route handler).
2. The handler enforces size, type and rate limits, strips EXIF and video metadata, and issues a tip code. It stores no IP or user agent.
3. It inserts the tip with `screen_status='pending'` using the anon key. `anon` has INSERT only. The file goes to the private `tips` bucket.
4. The local worker runs Scout Intent / Tip Guard and face blur, then sets `clean` or `quarantined`.
5. The Zetaris `v_tip_*` views select only `clean` tips, so agents never see unscreened text.
6. `GET /tip/status?code=…` calls a `security definer` RPC that returns only the status and any police reply.

## 6. City packs

Nothing about Chennai is hard-coded. `CITY=chennai` selects `cities/chennai/`. See [CITY_PACKS](CITY_PACKS.md).

## 7. Ports

| Service | Port |
|---|---|
| web (local) | 3001 |
| api | 8000 |
| Zetaris UI / REST / JDBC | 3000 / 8888 / 10000 |
| Nightshift | 8088 |

## 8. Repository layout

The layout follows [SPEC C5](SPEC.md#architecture). Two differences:

- docs live in `engg/docs/`;
- city data lives in `cities/<city>/`.
