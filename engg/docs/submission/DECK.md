---
tags: [nexus, deliverables]
---

# Slide deck content (WS5-06)

Thirteen slides: the spec's 12 (L2) plus one on responsible AI. Each slide gives the title, the on-slide text (short; the speaker notes carry the rest), the screenshot or visual it needs, and a fallback screen if the planned one isn't on `main` by freeze. Claims come from [EVIDENCE](EVIDENCE.md), checked against `origin/main` @ `c686f0c` (rechecked at `0177339`).
Related: [EVIDENCE](EVIDENCE.md) · [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md) · [VIDEO_SCRIPT](VIDEO_SCRIPT.md) · [README_DRAFT](README_DRAFT.md) · [DELIVERABLES](../DELIVERABLES.md)

## The 8 required points → slides

The Submission Requirements ask the deck to cover 8 points ([DIGEST](../hackathon/DIGEST.md)):

| # | Required point | Slides |
|---|---|---|
| 1 | Problem and target users | 2 |
| 2 | Solution | 3 |
| 3 | Agent workflow / architecture | 4, 5 |
| 4 | Technical stack | 5 |
| 5 | How Zetaris and Meterless were used | 6, 7, 8 |
| 6 | What was unique about the sponsor tech use | 9 |
| 7 | Product visuals | 10 |
| 8 | Future enhancements | 13 |

Slides 11 (results) and 12 (responsible AI) are extra. Judges score Impact 30 · Technical 20 · Innovation 15 · Demo 15 · Product & UX 10 · Sponsor Tech 10.

## Screenshot rules (every slide)

- **Check no secrets are visible.** Before a screenshot goes in, look for:
  - Nightshift's Providers and Console tabs (they show the NVIDIA key and tokens);
  - terminals (`env`, `echo`, `.env` contents, the token-file path is fine but never its contents);
  - the Supabase dashboard (API keys page, connection strings);
  - Zetaris settings pages (API token);
  - browser address bars with tokens in the URL.
- Use synthetic case data only (all crime, person and tip data is). Where a map or weather shows, carry the attribution: Map data © OpenStreetMap contributors (ODbL). Ward boundaries © DataMeet / Transparent Chennai (CC BY-SA 2.5 IN). Weather data by Open-Meteo.com (CC BY 4.0). Use browser zoom 110–125%.
- Crop out bookmarks, other tabs and OS notifications.

---

## Slide 1 · Title

- **On slide:** "Nexus Chennai: city-wide crime linking agents" · Track 1, Solving Fragmented Intelligence · team Heisenbugs · Open Agent Hackathon 2026
- **Sponsor strip:** Zetaris · Meterless (Nightshift + engines) · NVIDIA Nemotron
- **Visual:** Pulse Map of Chennai, darkened, as background (`/console/map`).
- **Check no secrets visible:** console header shows the signed-in user. Use a synthetic demo account.

## Slide 2 · Problem and users (point 1)

- **On slide:**
  - "Every station sees only its own cases."
  - A chain-snatching gang works Adyar on Monday and Velachery on Friday: two stations each file one robbery, and nobody connects them.
  - The evidence is fragmented too: case files, legacy station exports, ANPR cameras, 112 calls, tips, news.
  - **What linking finds (live demo data, synthetic):** one proposed series, "Red two-wheeler chain snatchings · 3 stations": 9 cases across Adyar, Thiruvanmiyur and Velachery. Its top pair (Adyar ↔ Velachery) shares a partial plate and the same red Bajaj Pulsar 150, high 0.789. `[AT BUILD: the hero is decided on camera at 15:30; say "approved by the analyst on camera" if so, otherwise "waiting for an analyst"]`. Say "proposed", never "caught".
- **Users:** crime analysts (find and decide links), station officers (capture cases, act on alerts), supervisors, and the public (send tips safely).
- **Numbers (synthetic city):** 14,000 FIRs over 24 months across 70 stations, with 30 planted series, decoys and duplicates (`cities/chennai/generator/`). Say "synthetic" on the slide.
- **Visual:** two station icons with the same red motorcycle, no line between them.

## Slide 3 · The solution in one picture (point 2)

- **On slide:** "Agents read every source through Zetaris, think with Nemotron through Nightshift, and raise link alerts that a Skeptic gives a second opinion on and a human decides."
- **Three outputs:** a link alert (score, per-factor evidence, Zetaris query id) → a series with a dossier → a public appeal an officer publishes.
- **Two more ways into fragmented data:**
  - **Ask Nexus:** an analyst asks in plain words ("chain snatchings on a red Pulsar in the last 90 days"); Nemotron writes only a plan, code checks it, an allow-listed Zetaris query answers. Live: 16 / 4 / 3 cases for the three sample questions, the same count on 5 runs each, and every count equal to an independent SQL count. It refuses what it can't answer.
  - **New source onboarding:** an unseen station export is profiled in place by Zetaris; Nemotron proposes the column mapping; a person approves; it becomes a Zetaris view. Live: 150 synthetic rows, every planted fault found (incl. 4/4 likely duplicates of existing cases); registered, not linked.
  - Sources: EVIDENCE rows "Ask Nexus" and "New source onboarding" (#391).
- **Visual:** alert detail page (`/console/alerts/[alertId]`) showing the factor bars and evidence.
- **Check no secrets visible:** none on this page beyond the user menu.

## Slide 4 · Agent workflow (point 3)

- **On slide:** the LangGraph graph with its loops highlighted:
  - router → **tip** (Tip Guard → extract) | **search** | **case**;
  - case: load → extract → **plan** → link → **skeptic** → write;
  - loops: Planner ≤ 3 rounds; Skeptic **sends back** to the Planner ≤ 2 times or **drops** a pair; a human approves or rejects; H-MEM feeds that back.
- **Callout:** "Not a fixed chain: routing, re-planning, critique and a human gate."
- **Visual:** `engg/docs/diagrams/c4-agent-graph.svg` (check it matches `services/api/app/graph/pipeline.py`; edit labels if not).

## Slide 5 · Architecture and stack (points 3 + 4)

- **On slide:**
  - **Web (Vercel):** Next.js 14, MapLibre GL + deck.gl, H3 hex cells; reads Supabase under row-level security.
  - **Laptop:** FastAPI + LangGraph agents; Meterless engines (TypeScript references in a sidecar, Python ports in process); Zetaris; Nightshift.
  - **Cloud:** Supabase (system of record, RLS per role, realtime); NVIDIA Nemotron behind Nightshift.
  - **Judge path:** `docker build` + `docker run -e SAMPLE_MODE=true`, `POST /run`, JSONL traces.
- **Visual:** `engg/docs/diagrams/c1-layers.svg`.

## Slide 6 · How Zetaris is used (point 5)

- **On slide:**
  - **Federated today:** Supabase Postgres (17 tables + 5 views, read-only role), 12 file tables in Zetaris's file store (8 CSV + 4 Parquet: legacy CCTNS exports, ANPR, 112 calls, releases…) and REST feeds served by the Nexus API (weather, news, social). One semantic view, `v_crime_unified`, over every crime record shape.
  - **Governed:** agents may run only registered named queries: **13 the agents run**, plus 4 system queries for health, data quality and the Data sources page. Each one's id lands in the trace.
  - **Data quality:** 8 DQ views, e.g. one incident filed by two stations.
  - **Trust boundary:** tips reach Zetaris only through a safe-column view.
  - **The Skeptic re-runs Zetaris queries itself** for its second opinion on each pair.
- **Visual:** the Zetaris UI (`localhost:3000`) running a live `q_candidates` or `q_case` query, with the result grid.
- **Check no secrets visible:** Zetaris UI must not show a settings/API-token page; crop the URL bar.

## Slide 7 · How Meterless is used (point 5)

- **On slide (engines):**
  - World Model: one entity per plate, person, place. **8/8** official conformance.
  - H-MEM: human decisions shift the next similar score (±0.08 max) with a trust ledger, visible in the trace (`run_9e0e99ba`: mem-1, -0.055). **13/13**.
  - Markovian: bounded-chunk series dossier. **8/8**.
  - Scout Intent: search routing + Tip Guard. Held-out **0.975** (never tuned on), injections **7/7**; tuned set injections **23/23** (label it tuned); live: **0/30 genuine tips falsely quarantined**, emergencies **2/2**. Live misses fixed by #128: injections 3/4 → 4/4, spam 1/4 → 4/4 (label it: "not independent; these misses shaped the rules"). Never show the fixture 1.000 alone.
  - Official references vendored unmodified; suites re-run in CI on every PR.
- **On slide (Nightshift):** the only model path; pinned lanes, never `meterless/auto`; model and receipt logged per call; NVIDIA key only inside Nightshift.
- **Visual:** a terminal crop of `logs/conformance_hmem.txt` ("13/13 checks passed") next to a trace viewer crop.
- **Check no secrets visible:** terminal shows only the log file; no prompt with env vars.

## Slide 8 · NVIDIA Nemotron (point 5)

- **On slide:**

| Lane | Model | Job |
|---|---|---|
| fast | Nemotron 3.5 Lightning 30B | MO extraction, appeal drafts, briefings, Ask Nexus plans, onboarding column mapping |
| reason | Nemotron 3 Ultra 550B | query planning, per-factor reasons, the Skeptic's second opinion |
| vision | Nemotron 3.5 Super VL 120B | reading CCTV and evidence stills (one verified live run; rate-limited free route) |

  "Every trace line names the model that handled the request." Receipts: 190 of 193 traced model calls carry a Nightshift receipt, and all 190 signatures verify (the other 3 failed with no reply). Footnote: "Vision: Nemotron Super VL through a Nightshift cloud lane (verified 27 Oct). If the lane can't be reached, the Extractor uses the officer's caption, traced as `vision_unavailable`." Verified in live run `reextract_vis_1793040194` (Extractor `model_call`, lane `vision`, receipt `chatcmpl-5dfe68c6-…`). Say "reads CCTV stills"; don't quote a success rate (free route, rate-limited).
- **Visual:** trace viewer (`/console/system/trace/[runId]`) with the model column showing `nvidia/nemotron-3-ultra-550b-a55b` on a Skeptic line.
- **Check no secrets visible:** trace summaries are redacted (D-025), but scan for any token-like string anyway.

## Slide 9 · What was unique (point 6)

- **On slide (three lines, big):**
  1. "The data layer is also the second opinion: the Skeptic re-queries Zetaris itself, and the officer decides."
  2. "Rejected links stay visible and teach the system through H-MEM."
  3. "The public can help without steering it: Scout Intent screens every tip first."
- **Visual:** trace crop from `run_da0092da` (`/console/system/trace/run_da0092da`, demo **admin** login; steps #46–#50) showing the Skeptic's own Zetaris queries and then **dropping** CHN-CM-2025-000450 ↔ CHN-CM-2025-000461 (0.694, medium, would have alerted; a pair that differs on crime type, not a look-alike), next to the H-MEM trace row (`/console/system/trace/run_9e0e99ba`, row #61: memory_applied, mem-1 rejected, delta -0.055; no alert was written for that pair, so don't caption it as an alert). Never show or caption a factor strike: none has occurred.

## Slide 10 · Product visuals (point 7)

- **Use the polished screens (#400, f48e92f), all synthetic, all read-only:**
  - `C:/Apps/Nexus-handover/console-polish-400/hero-detail-1536.png`: alert detail (factor bars, evidence, How this alert was made, Skeptic panel);
  - `…/alerts-1536.png`: the alert inbox; `…/alerts-375.png`: the same on a phone (responsive);
  - `…/ask-form-1536.png` + `…/ask-result-1536.png`: Ask Nexus question and answer;
  - frames from nexus-4's clips in `C:/Apps/Nexus-handover/clips/console/`: `s1_map` (Pulse Map), `s8_series` / `s8_map` (series), `onboard_run` (onboarding), `bk_tipguard` (Tip Guard quarantine).
  - **At build:** prefer the recorded take's frames for the hero (after the on-camera decision); check every frame for secrets (no settings page, no tokens, no `.env`).
- **Earlier tile plan (fallback):**
  - **Pulse Map** (`/console/map`): hex layer, crime-type filter, time scrubber.
  - **Alert card** (`/console/alerts/[alertId]`): factors, evidence, Zetaris query ids, approve/reject.
  - **Tip flow** (`/tip/new` → `/tip/sent` → `/tip/status`): anonymous, EXIF stripped, tip code.
  - **Tip triage** (`/console/tips`): quarantined tips visible to police.
- **Optional fifth tile:** series page with its Markovian dossier (`/console/series/[seriesId]`, on main). Use it only once nexus-6's live check shows real rows; fallback: public appeal page (`/appeals/[publicId]`).
- **Check no secrets visible:** tip status page shows a tip code. Use a throwaway synthetic tip, never a real passphrase you reuse.

## Slide 11 · Results

- **On slide:** precision and recall on the planted truth (60 cases), from `output_examples/eval_report.json`: **Nexus 0.59 / 0.86 (F1 0.70) vs rules-only 0.09 / 0.30 (F1 0.13)**. HIGH alerts 10 of 10 correct; MEDIUM 56%, which is why an analyst decides every alert. No model calls in the eval. Footnote: 13 of 60 cases had model features.
  - **What's new compared with established linkage:** established systems rely on structured case forms and analysts comparing cases by hand. Nexus reads sources in place through Zetaris, cites the query and row behind every factor, lets a Skeptic send back or drop a pair, feeds screened public tips back as corroboration, and learns from analyst decisions within ±0.08. Don't name or characterise any specific outside system on the slide.
- **Live result (nexus-qa, label it "live"):** hero alert LA-2026-E38C6B38B865, Adyar ↔ Velachery, **high 0.789**, coverage 0.72, `[AT BUILD: pending → decided on camera?]`, with five factors (MO 0.885, vehicle 0.85 on a partial plate, suspect 1, target 1, space–time 0.328). nexus-3 DB read after the re-run, 26 Oct 23:02.
- **Judge-path result (confirmed @ `de8e666`; label it "fresh clone, sample mode"):** from a fresh clone with no credentials, the hero case gets **3 cross-station links, 2 of them high** (Adyar ↔ Thiruvanmiyur 0.819, Adyar ↔ Velachery 0.789), and a 3-station series. Use this line even if the eval table doesn't land.
- **Nemotron Ultra alone (pre-registered, #405), honest framing:** on the 178 scored pairs it was shown, Ultra alone scores a **higher** F1 than the pipeline (0.80 vs 0.69), not a significant difference (McNemar p = 0.55). The pipeline's edge is coverage at zero model cost: it scores every candidate (~0.83 s per case), where the model alone would need ~26 h for all 5,750 pairs; under a 10-pair budget it reached 14 of 49 true links vs the system's 41. **Never "agents beat the LLM".**
- **Skeptic planted test (pre-registered, #392):** dropped 0 of 24 planted look-alike false links (named the planted fact in 19/24, exploratory). **Re-test of the fix: `[TBD: fresh pre-registered set, nexus-3/nexus-1]`**; publish it either way.
- **Also:** `/run` takes seconds per example on replay (sample mode); live, a single filed FIR reaches its alert in ~4.6 min (the reasoning lane is Nemotron Ultra 550B); tests: 5 CI jobs green on every PR; conformance 8/8 · 13/13 · 8/8.
- **Visual:** the eval page or a clean table. No chart without real numbers.

## Slide 12 · Responsible AI (extra)

- **On slide:**
  - **Human gate:** Nexus suggests, people decide. An analyst decides every link; an officer publishes every appeal.
  - **Explanations:** every alert shows each factor's score, a plain reason, and the Zetaris query and row behind it, plus the Skeptic's verdict.
  - **Numbers from code, not models:** a model can't set a score; any number it returns is ignored.
  - **Tips screened:** Tip Guard fails closed; agents read only the redacted text of clean tips.
  - **Public privacy:** the public map is fuzzed (coarse H3 cells, no points, a minimum-count cutoff, and rare crime types hidden per cell); tip photos have EXIF stripped; passphrases are hashed inside the database.
  - **Synthetic crime, person and tip data only** (map, ward, station and weather reference data is real public open data); protected attributes (religion, caste, community) are never used or written.
- **Visual:** public map (`/map`) showing coarse cells, next to a quarantined tip in `/console/tips`.
- **Check no secrets visible:** the quarantined tip may contain a synthetic injection string. That's fine, but make sure it isn't a key-shaped string.

## Slide 13 · Future enhancements + limitations (point 8)

- **Next:**
  - vision on an in-house lane instead of a third-party free route;
  - Zetaris reading files straight from object storage (fix the S3 TLS handshake);
  - more named queries and semantic views across sources `[drop the ones that land before freeze]`;
  - a pilot on real, consented data with police oversight.
- **Limitations (stated plainly):**
  - synthetic data;
  - vision runs on a rate-limited third-party free route (fine for synthetic stills, not for real evidence);
  - the Skeptic is a second opinion, not a guarantee: on a pre-registered planted test it dropped 0 of 24 look-alike false links (#392); fix re-test `[TBD]`;
  - the reasoning lane is Ultra 550B because Super 120B isn't served to our key;
  - bcrypt instead of Argon2id for tip passphrases;
  - model-written explanations can be imperfect, but the numbers can't (code computes them).
- **Visual:** none, or the team photo.
