---
tags: [nexus, deliverables]
---

# Demo video script (WS5-07)

One story, **the Red Pulsar Duo series**, in **3:30** (hard limit 3:40; the rules allow 1–4 min). The narration is written for ElevenLabs at about 2.4 words per second, and each block fits its segment. Every screen has a **check no secrets visible** note. Claims come from [EVIDENCE](EVIDENCE.md), checked against `origin/main` @ `0177339`.
Related: [EVIDENCE](EVIDENCE.md) · [DECK](DECK.md) · [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md) · [SPEC Part M](../SPEC.md#demo) · [RULES_CHECK](../hackathon/RULES_CHECK.md)

## What the rules ask the video to show

From the Submission Requirements ([DIGEST](../hackathon/DIGEST.md)): the problem, the main workflow, how the agent solves the track, key features, and how Zetaris and Meterless are integrated. That means an agent querying Zetaris, the feature an engine powers, and **one real request through Nightshift**.

| Required | Segment |
|---|---|
| Problem | 1 |
| Main workflow / how it solves Track 1 | 3–8 |
| Agent querying Zetaris | 4 (20-second live query) and 6 (Skeptic re-query) |
| Feature an engine powers | 3 (World Model), 7 (H-MEM) |
| One real request through Nightshift, model named | 5 |
| Key features | 6–8 |

## Changes from SPEC M2 (on purpose)

- **No "Super VL reads the CCTV still".** Nightshift refuses image input (D-021). Segment 3 shows the honest caption fallback, traced as `vision_unavailable`.
- **Reasoning model is Nemotron Ultra 550B**, not Super 120B (D-017).
- **No eval numbers** unless `output_examples/eval_report.json` lands (`[PENDING: WS2-14]`). The close doesn't depend on them.
- **One story**, not a tour: the public-tip and appeal segments are cut to keep under 3:40. They are covered in the deck.

## Before recording

0. **The hero alert must be `pending` when recording starts.** LA-2026-E38C6B38B865 (Adyar ↔ Velachery) is decided **on camera only**. Nobody approves or rejects it beforehand, and no test touches it. Check its status in `/console/alerts` just before recording.
0b. **Pause background extraction before filing the live FIR.** Ask nexus-3, or stop them yourself: the backfill (`python -m app.graph.backfill`) and any series batch run. Nightshift serves one model call at a time, so a running batch makes the FIR's calls wait behind it. **Keep the worker running** (`python -m app.worker` with `ENGINES_PERSIST=supabase`). It picks up a new FIR on its next pass, 15 s between passes by default (`--interval`). Measured end-to-end times (filed → features → alert) come from nexus-3 after their worker change; quote only those, never an estimate.
1. **Run the story live once,** with Zetaris and Nightshift up and `SAMPLE_MODE` off, so the trace shows real Nightshift calls and not `replayed`. Note the `run_id`.
2. **Segment 6 uses the live Skeptic drop in `run_da0092da`** (`/console/system/trace/run_da0092da`): CHN-CM-2025-000450 ↔ CHN-CM-2025-000461, 0.694 medium, dropped, no alert written. **No factor strike has occurred anywhere, so never show, say or caption a strike.** Backup beat: decoy TU-425 ↔ TU-431, sent back twice, rejected by the analyst (LA-2026-266EFBCEEBBE). Hold any line about the hero's Skeptic re-check until nexus-3 re-runs it with verified ANPR.
3. **Set up H-MEM so the decision reaches the next run** (segment 7). Since #82, a running API picks up a decision the worker recorded with no restart: both reopen the store when `logs/hmem/state.json` or `ledger.jsonl` changes. #83 tests the whole path, worker decision → next `/run` → alert row with `memory_applied`. The API and worker must share `logs/hmem/`. Plain Python from one checkout does this, and so does `docker compose --profile worker up`, because the worker mounts `./logs` too since #97.

   **Recipe:**
   1. Start the API and the worker: `python run.py` + `python -m app.worker` from one checkout, or `docker compose --profile worker up`.
   2. **Record segment 7's approval on camera** (the hero must still be pending, see step 0). Then let the worker pass once off camera (it calls `hmem.record_decision`).
   3. Off camera, run a **second, similar Red Pulsar case** that was not part of the first alert (pick a `SER-RED-PULSAR` member from the generated data). Existing alerts are not rescored; only an alert created *after* the decision can show "Memory applied".
   4. Check that alert's "Memory applied" section in the console is non-empty, then record the cut for the end of segment 7. If it is empty, use the ledger fallback in segment 7.
   - **Never rehearse step 2 on the hero.** If you must rehearse, use another pending alert.
4. **Hide everything that can hold a secret** before you press record:
   - Nightshift's Providers and Console tabs;
   - the Supabase dashboard;
   - Zetaris settings;
   - any terminal that has run `env`;
   - `.env`.
   Use a clean browser profile with a synthetic demo account.
5. **1080p (OBS), browser zoom 110–125%, terminal font enlarged.**
6. **Open the Pulse Map at least 30 s before recording segment 1** (it took ~25 s to load in nexus-4's dry run).
7. **Whoever records checks the Zetaris UI on `localhost:3000`** before segment 4: it opens, the `nexus` container is visible, and the rendered `q_candidates` SQL runs and returns rows.
8. **Segment 3 needs a real `vision_unavailable` trace step.** It comes only from a live FIR filed with a CCTV still (nexus-3 / nexus-5 are producing one). Note its `run_id`. If there is no such trace when you record, cut the CCTV-still sentence from the segment 3 narration.

## Script

**Total: 3:30.** The word counts are the narration only.

### 1 · The problem · 0:00–0:18 (18 s, ~40 words)

- **Screen:** Pulse Map (`/console/map`), time scrubber playing over Chennai. Start recording at least 30 s after the map opens (Before recording, step 6).
- **Narration:**
  > Chennai's police stations each see only their own cases. A gang that snatches a chain in Adyar on a Wednesday evening and another in Velachery two days later looks like two unrelated robberies. Nexus connects them. This is our entry for Solving Fragmented Intelligence.
- **Check no secrets visible:** console header shows the demo user only. No other tabs in frame.

### 2 · How it's built · 0:18–0:40 (22 s, ~52 words)

- **Screen:** architecture diagram (`engg/docs/diagrams/c1-layers.svg`), with each layer highlighted as named.
- **Narration:**
  > Case files live in Supabase, legacy exports and ANPR reads in files, weather in a live feed. Zetaris federates them all in place, and our agents read only through its named queries. Every model call goes to NVIDIA Nemotron through Meterless Nightshift, and four Meterless engines give the agents memory and shared context.
- **Check no secrets visible:** a static diagram. Nothing to check beyond desktop notifications.

### 3 · A new case arrives · 0:40–1:05 (25 s, ~60 words)

- **Screen:**
  - **Planned (on main, #73):** the officer saves the FIR in the console form (`/console/cases/new`), attaching the CCTV still (#88). Then trigger the run: the worker picks up new crimes, or `POST /api/cases/<id>/process`.
  - **Fallback:** a terminal running `curl -s -X POST localhost:8000/run -H "Content-Type: application/json" -d '{"input":{"kind":"case","crime_id":"CHN-AD-2026-001182"}}'`, with stdout trace lines scrolling. Then cut to the trace viewer `/console/system/trace/<run_id>`, scrolled to the Extractor lines. The CCTV-still sentence needs the `vision_unavailable` step from a live FIR filed with a still (Before recording, step 8).
- **Narration:**
  > An Adyar officer files a chain snatching: two riders on a red motorcycle, a partial plate. Nemotron Lightning extracts the modus operandi. The CCTV still can't be read today, because our runtime refuses images, so Nexus says so in the trace and uses the officer's caption instead. The World Model files the plate and place as entities every agent shares.
- **Check no secrets visible:**
  - the terminal shows only the `curl` command and its trace lines;
  - no shell history with `env`, `echo $…` or token paths being read;
  - the trace viewer shows the demo user.

### 4 · Zetaris, live · 1:05–1:25 (20 s, ~44 words)

- **Screen:** Zetaris UI (`localhost:3000`) running the SQL of `q_candidates` for the Adyar case; the result grid appears with candidate cases from other stations. The registry SQL has `:crime_id` / `:days` / `:ring` placeholders and won't run raw. Print the rendered query and paste that, using the `days` / `ring` the Planner used in the recorded run's trace (14 / 5 shown here):
  ```bash
  PYTHONPATH=services/api python -c "from app.adapters.zetaris import NAMED_QUERIES, render; print(render(NAMED_QUERIES['q_candidates'].lightning, {'crime_id':'CHN-AD-2026-001182','days':14,'ring':5}))"
  ```
- **Narration:**
  > Here is the same question in Zetaris: same-category crimes within a few kilometres and days of the Adyar case, across every station. One query over the federated sources, no warehouse. The Planner chooses queries like this, and each query's id is kept as evidence.
- **Check no secrets visible:**
  - Zetaris settings and API-token pages closed;
  - crop the browser URL bar;
  - the connection panel must not show the Supabase pooler password.

### 5 · One real Nightshift request · 1:25–1:45 (20 s, ~46 words)

- **Screen:** trace viewer `/console/system/trace/run_da0092da` (sign in as the **demo admin**: system pages are admin-only), step #49 expanded: Skeptic `model_call` on lane `reason`, model `nvidia/nemotron-3-ultra-550b-a55b`, receipt `chatcmpl-…`, status `ok` (**not** `replayed`). This one trace serves segments 5 and 6.
- **Narration:**
  > Every model call is accountable. This is the Skeptic's critique, sent through Nightshift on the pinned reasoning lane. The trace records the model, Nemotron Ultra, and the receipt Nightshift returned for this exact request. The NVIDIA key lives only inside Nightshift, never in our app.
- **Check no secrets visible:**
  - **do not open Nightshift's own Console or Providers tabs for this shot**; the trace viewer is enough;
  - make sure the receipt id isn't mistaken for a token: it's a request id, which is fine to show.

### 6 · The Skeptic drops a false link · 1:45–2:15 (30 s, ~70 words)

- **Screen:** same trace, steps #45–#50. #45 is the Linker's reason (CMBT area, close in time and space, two thin males). #46–#48 are the Skeptic's own Zetaris queries (`via=zetaris`). #50 is **drop · rejected · 0.69**, with its reason: age bands differ, different crime categories, no vehicle or MO overlap. No alert is written for that pair. The line shows `struck=[]`; don't zoom on it and don't say "strike".
- **Narration:**
  > The Linker scores each pair on nine factors, in code. Here, two thefts near the CMBT bus terminus look close: same area, same hour, two thin men. The Skeptic runs its own Zetaris queries and disagrees. The ages don't match, one is a shop theft and one a two-wheeler theft, and nothing else overlaps. It drops the link, and no alert is written.
- **Check no secrets visible:** the trace summaries are redacted by design (D-025). Scan the expanded rows for any key-shaped string anyway.

### 7 · The analyst decides, and H-MEM learns · 2:15–2:50 (35 s, ~80 words)

- **Screen:**
  - the alert inbox (`/console/alerts`), then click the hero card **directly**: LA-2026-E38C6B38B865, Adyar–Velachery. In the dry run it was the **3rd card by Score**, not the first, and some other Red Pulsar cards showed "model rationale unavailable", so don't open those. Then the alert detail: factor bars, the evidence with each Zetaris query id, the Skeptic verdict;
  - the analyst clicks **Approve**;
  - cut to the alert for the second, similar Red Pulsar case (run after the decision; see Before recording, step 3), whose "Memory applied" section shows the memory from that decision.
  - Fallback if no affected alert exists: the H-MEM ledger lines from the worker run (`logs/hmem/ledger.jsonl`). Or the memory page (`/console/memory`): live on real rows, and it already shows a real reject turned into a memory with its ledger row. Its "Changed later scores" list fills only after step 3 of Before recording.
- **Narration:**
  > The analyst sees why: each reason, its evidence, and the Zetaris query behind it. She approves the link. That decision isn't just stored. The Meterless H-MEM engine turns it into a memory, so the next similar pair is scored with it, by a small, capped amount, and the alert says so. Rejections work the same way, and they stay visible to every station.
- **Check no secrets visible:**
  - the console shows the demo analyst's name only;
  - if you show the ledger file, use a terminal with no env output above it.

### 8 · The series on the map · 2:50–3:12 (22 s, ~50 words)

- **Screen:** Pulse Map with **series only** on: the Red Pulsar members joined across stations in time order. **Widen the scrubber window so every member shows** before playing. The series is labelled on screen by its generated name ("10 linked cases (…)"), not "Red Pulsar Duo", so the narration doesn't name it. Optional: the series page with its dossier (`/console/series/[seriesId]`, on main since #70); use it only if it shows real rows.
- **Narration:**
  > Approved links grow into a series. On the map, this series appears as one trail across three stations in Chennai's south, instead of separate robberies in separate registers. The Markovian engine can read the whole series in bounded steps to write its dossier.
- **Check no secrets visible:** the map tiles carry no key in view; crop the URL bar (a MapTiler key can sit in tile URLs in devtools, so keep devtools closed).

### 9 · Close · 3:12–3:30 (18 s, ~42 words)

- **Screen:** the title card: Nexus Chennai, Track 1, the sponsor strip and the repo URL. Optional: "All data synthetic" in small print.
- **Narration:**
  > Zetaris finds the facts, Nemotron reads and reasons, the Skeptic refuses what the data can't support, and every human decision teaches the next alert. All data here is synthetic, and every alert is a suggestion for a person to decide.
- **Check no secrets visible:** a static card.

## ElevenLabs narration text (one block per segment)

Paste each block into `demo/script.md` for `demo/narrate.py` (SPEC M1). Settings: one voice, Indian English if available, stability ~0.5, similarity ~0.75. These blocks are identical to the narration above; if you edit one, edit both.

```
[seg_01]
Chennai's police stations each see only their own cases. A gang that snatches a chain in Adyar on a Wednesday evening and another in Velachery two days later looks like two unrelated robberies. Nexus connects them. This is our entry for Solving Fragmented Intelligence.

[seg_02]
Case files live in Supabase, legacy exports and ANPR reads in files, weather in a live feed. Zetaris federates them all in place, and our agents read only through its named queries. Every model call goes to NVIDIA Nemotron through Meterless Nightshift, and four Meterless engines give the agents memory and shared context.

[seg_03]
An Adyar officer files a chain snatching: two riders on a red motorcycle, a partial plate. Nemotron Lightning extracts the modus operandi. The CCTV still can't be read today, because our runtime refuses images, so Nexus says so in the trace and uses the officer's caption instead. The World Model files the plate and place as entities every agent shares.

[seg_04]
Here is the same question in Zetaris: same-category crimes within a few kilometres and days of the Adyar case, across every station. One query over the federated sources, no warehouse. The Planner chooses queries like this, and each query's id is kept as evidence.

[seg_05]
Every model call is accountable. This is the Skeptic's critique, sent through Nightshift on the pinned reasoning lane. The trace records the model, Nemotron Ultra, and the receipt Nightshift returned for this exact request. The NVIDIA key lives only inside Nightshift, never in our app.

[seg_06]
The Linker scores each pair on nine factors, in code. Here, two thefts near the CMBT bus terminus look close: same area, same hour, two thin men. The Skeptic runs its own Zetaris queries and disagrees. The ages don't match, one is a shop theft and one a two-wheeler theft, and nothing else overlaps. It drops the link, and no alert is written.

[seg_07]
The analyst sees why: each reason, its evidence, and the Zetaris query behind it. She approves the link. That decision isn't just stored. The Meterless H-MEM engine turns it into a memory, so the next similar pair is scored with it, by a small, capped amount, and the alert says so. Rejections work the same way, and they stay visible to every station.

[seg_08]
Approved links grow into a series. On the map, this series appears as one trail across three stations in Chennai's south, instead of separate robberies in separate registers. The Markovian engine can read the whole series in bounded steps to write its dossier.

[seg_09]
Zetaris finds the facts, Nemotron reads and reasons, the Skeptic refuses what the data can't support, and every human decision teaches the next alert. All data here is synthetic, and every alert is a suggestion for a person to decide.
```

## Narration facts to re-check at recording time

| Line | Depends on | If it isn't true in your run |
|---|---|---|
| "Adyar on a Wednesday evening… Velachery two days later" | hero pair in `series.yaml`: CHN-AD-2026-001182 on Wed 14 Oct 19:40 IST, CHN-VL-2026-000877 on Fri 16 Oct 19:55 IST (checked) | Change the weekday words to match the dates on screen |
| "two riders on a red motorcycle, a partial plate" | the hero case narrative in `series.yaml` | Read the narrative shown and match it |
| Hero alert is Adyar ↔ Velachery, high | **Live:** LA-2026-E38C6B38B865, high 0.787, coverage 0.72, pending. **Judge path (sample mode, fresh clone @ `7534e9e`):** the same pair, high 0.787 | Read the score shown on screen; never the number from this table |
| "across three stations" | Live series SER-B687C36CFC: 10 cases across PS-ADYAR / THIRUVANMIYUR / VELACHERY (nexus-6, 26 Oct). Final count after nexus-3's D-033 (test FIR removed) and the series-naming fix | Say the station count shown on screen, or just "across stations" |
| Seg 3: "The CCTV still can't be read today…" | a `vision_unavailable` step in the live FIR-with-still run (none yet at the dry run) | Cut that sentence |
| Seg 7: the hero card | LA-2026-E38C6B38B865 still `pending`; 3rd by Score in the dry run | Click it directly wherever it sits; never approve another card |
| Seg 6: "ages don't match… shop theft… two-wheeler theft… nothing else overlaps… drops the link" | `run_da0092da` step #50: age bands 40-50 vs 18-20, shop_theft vs two_wheeler_theft, no vehicle or MO overlap, drop 0.69 (verified in the trace viewer) | If the recorded trace differs, narrate exactly what it shows. **Never a strike** |
| "the next similar pair is scored with it" | an alert whose Memory applied section is non-empty | Use the ledger fallback and say "is ready to score the next similar pair" |
| Zetaris "across every station"; seg 2 "legacy exports and ANPR reads in files" | `sb` + the 12 file-store tables (#140) | If the file tables aren't registered on the recording laptop, cut "legacy exports and ANPR reads in files" |

## After export

- **Frame-by-frame secrets check** of the final MP4 (RULES_CHECK gap 4): every terminal, every browser tab strip, every URL bar.
- **Upload** as YouTube unlisted plus a Drive backup. Open both links in a **private window, logged out** (gap 5).
- **Name:** `OAH2026-Nexus-FragmentedIntelligence-Demo.mp4`. Put the link in the README.
- **Disclose in the README:** "Narration voice generated with ElevenLabs. ElevenLabs is not part of the running product."
