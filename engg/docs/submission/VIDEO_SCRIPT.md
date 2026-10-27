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
| Key features | 6–8 (Skeptic as a second opinion, analyst decision + H-MEM, series + task force); optional Ask Nexus and source onboarding |

## Changes from SPEC M2 (on purpose)

- **Never say the Skeptic catches or stops false links** (#392: 0 of 24 planted). Say "second opinion; the officer decides".
- **"Super VL reads the CCTV still" only with a real trace.** Since D-036 a Nightshift cloud lane serves Super VL, and a live run has shown it (`reextract_vis_1793040194`), so **variant A is the plan** for segment 3. Still check the take: the free route is rate-limited, and if the recorded take's trace shows `vision_unavailable`, use variant B.
- **Reasoning model is Nemotron Ultra 550B**, not Super 120B (D-017).
- **Eval numbers are on main** (`output_examples/eval_report.json`: P 0.59 / R 0.86 vs rules-only 0.09 / 0.30; HIGH 10/10). The close doesn't depend on them. If you say one, say it with the baseline, never as a bare accuracy figure.
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
   3. **Done (27 Oct, nexus-6, Ravee-approved):** the demo FIR `CHN-TU-2026-001211` ran as `run_9e0e99ba`. Its trace shows Linker `memory_applied` on all 25 scored pairs. TU-425 pair: "mem-1 rejected (different_offenders) relevance 0.55", −0.055; TU-431: relevance 0.46, −0.046. **No alert was written** (coverage guard / below threshold), so segment 7 films the trace, not an alert card. Kept for reference: run a **second, similar Red Pulsar case** that was not part of the first alert (pick a `SER-RED-PULSAR` member from the generated data). Existing alerts are not rescored; only an alert created *after* the decision can show "Memory applied".
   4. nexus-4 films `/console/system/trace/run_9e0e99ba` landing on row #61, for the end of segment 7 (clip: `C:/Apps/Nexus-handover/clips/console/s7_hmem_trace.mp4`).
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
8. **Segment 3 needs a real vision step in the trace.** File the live FIR with a CCTV still, and check the trace. A vision `model_call` (lane `vision`, Super VL, a receipt) means narrate **variant A**; `vision_unavailable` means **variant B**. The free route is rate-limited and can refuse during recording, so check the trace of the take you use. Variant A is planned: live run `reextract_vis_1793040194` shows the vision `model_call` (seq 3, receipt `chatcmpl-5dfe68c6-…`).
9. **Task force (segment 8):** no task force may exist on the Red Pulsar series when recording starts. There is only one series in the database (SER-B687C36CFC), so **rehearse without writing**: in dry run #2, walk up to the *Propose task force* dialog and stop (cancel; nothing is created). The first real creation happens on camera. Have the supervisor login ready for an off-camera cut. After recording, add the task force to the cleanup list as KEEP-LABELLED.
10. **Refresh the live DQ flags first:** `python -m app.dq_status --only snapshot` (about 90 s; reads Zetaris only and replaces the live DQ flags snapshot, so FIRs filed since the last pass get their flags; nexus-2). Run it before the live FIR of segment 3, so the trace's `as_of` is fresh.
11. **Ask Nexus (only if the beat is used):**
   - **Clear the demo accounts' test questions** in `ask_questions` first, but **only after Ravee approves** (they are on the cleanup list). The page shows each user's last 5 questions on camera ("Your recent questions"), and each unanswered question counts toward a cap of 3 per user.
   - **Ask worker running (nexus-3):** `python -m app.ask_worker`. Without it, a question stays at "Waiting for the worker…".
   - **Allow for the wait:** answers usually take 10–20 s, and one took 28 s (the planning model varies). Cut the wait in editing, or pre-ask the chip once so it already shows in "Your recent questions".
   - **Re-sign-in the supervisor demo browser.** A probe signed supervisor out once around 01:50 IST on 27 Oct.
   - **Final chips** (nexus-5; each checked 5× live, same count each time, 4–12 s). Read the count off the screen when recording; don't script it:
     - a. "Chain snatchings on a red Pulsar in the last 90 days" → 16 cases (1 test filing excluded). It lists the hero pair as read-only rows; nothing is decided there.
     - b. "Chain snatchings in Adyar after 7 pm in the last 90 days" → 4 cases.
     - c. "Robberies in Velachery that are still undetected since 1 September" → 3 cases.
     - Off-topic, to show it never guesses: "Who will commit the next robbery in Adyar?" → "I can only search crimes by type, police station area, time, case status and words written in the FIR."
   - Analyst or above only.

## Script

**Total: 3:30.** The word counts are the narration only.

### 1 · The problem · 0:00–0:18 (18 s, ~40 words)

- **Screen:** Pulse Map (`/console/map`), time scrubber playing over Chennai. Start recording at least 30 s after the map opens (Before recording, step 6).
- **Narration:**
  > Chennai's police stations each see only their own cases. A gang that snatches a chain in Adyar on a Wednesday evening and another in Velachery two days later looks like two unrelated robberies. Nexus connects them. This is our entry for Solving Fragmented Intelligence.
- **Check no secrets visible:** console header shows the demo user only. No other tabs in frame.

### 2 · How it's built · 0:18–0:35 (17 s, ~41 words)

- **Screen:** architecture diagram (`engg/docs/diagrams/c1-layers.svg`), with each layer highlighted as named.
- **Narration:**
  > Case files, legacy exports, ANPR reads and live feeds stay where they are. Zetaris federates them, and agents read only through its named queries. Every model call goes to NVIDIA Nemotron through Meterless Nightshift, and four Meterless engines give agents memory.
- **Check no secrets visible:** a static diagram. Nothing to check beyond desktop notifications.

### 3 · A new case arrives · 0:35–1:00 (25 s, ~60 words)

- **Screen:**
  - **Planned (on main, #73):** the officer saves the FIR in the console form (`/console/cases/new`), attaching the CCTV still (#88). Then trigger the run: the worker picks up new crimes, or `POST /api/cases/<id>/process`.
  - **Fallback:** a terminal running `curl -s -X POST localhost:8000/run -H "Content-Type: application/json" -d '{"input":{"kind":"case","crime_id":"CHN-AD-2026-001182"}}'`, with stdout trace lines scrolling. Then cut to the trace viewer `/console/system/trace/<run_id>`, scrolled to the Extractor lines. The CCTV-still sentence needs the vision step from a live FIR filed with a still (Before recording, step 8): a `model_call` for variant A, or `vision_unavailable` for variant B.
- **Narration:**
  > An Adyar officer files a chain snatching: two riders on a red motorcycle, a partial plate. Nemotron Lightning extracts the modus operandi. [A] Nexus reads the CCTV still with Nemotron Super VL. [B] This time the vision model couldn't be reached, so Nexus says so in the trace and uses the officer's caption instead. The World Model files the plate and place as entities every agent shares.
- **Check no secrets visible:**
  - the terminal shows only the `curl` command and its trace lines;
  - no shell history with `env`, `echo $…` or token paths being read;
  - the trace viewer shows the demo user.

### 4 · Zetaris, live · 1:00–1:20 (20 s, ~44 words)

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

### 5 · One real Nightshift request · 1:20–1:40 (20 s, ~46 words)

- **Screen:** trace viewer `/console/system/trace/run_da0092da` (sign in as the **demo admin**: system pages are admin-only), step #49 expanded: Skeptic `model_call` on lane `reason`, model `nvidia/nemotron-3-ultra-550b-a55b`, receipt `chatcmpl-…`, status `ok` (**not** `replayed`). This one trace serves segments 5 and 6.
- **Narration:**
  > Every model call is accountable. This is the Skeptic's critique, sent through Nightshift on the pinned reasoning lane. The trace records the model, Nemotron Ultra, and the receipt Nightshift returned for this exact request. The NVIDIA key lives only inside Nightshift, never in our app.
- **Check no secrets visible:**
  - **do not open Nightshift's own Console or Providers tabs for this shot**; the trace viewer is enough;
  - make sure the receipt id isn't mistaken for a token: it's a request id, which is fine to show.

### 6 · A second opinion: the Skeptic · 1:40–2:10 (30 s, ~68 words)

- **Screen:** same trace, steps #45–#50. #45 is the Linker's reason (CMBT area, close in time and space, two thin males). #46–#48 are the Skeptic's own Zetaris queries (`via=zetaris`). #50 is **drop · rejected · 0.69**, with its reason: age bands differ, different crime categories, no vehicle or MO overlap. No alert is written for that pair. The line shows `struck=[]`; don't zoom on it and don't say "strike".
- **Narration:**
  > The Linker scores each pair on nine factors, in code. Two thefts near the CMBT bus terminus look close: same area, same hour, two thin men. The Skeptic runs its own Zetaris queries: the ages differ, and one is a shop theft, the other a two-wheeler theft. It drops this link. It is a second opinion, not a guarantee: in our planted test it missed look-alike false links, so the officer decides.
- **Check no secrets visible:** the trace summaries are redacted by design (D-025). Scan the expanded rows for any key-shaped string anyway.

### 7 · The analyst decides, and H-MEM learns · 2:10–2:45 (35 s, ~80 words)

- **Screen:**
  - the alert inbox (`/console/alerts`), then click the hero card **directly**: LA-2026-E38C6B38B865, Adyar–Velachery. In the dry run it was the **3rd card by Score**, not the first, and some other Red Pulsar cards showed "model rationale unavailable", so don't open those. Then the alert detail: factor bars, the evidence with each Zetaris query id, the Skeptic verdict;
  - the analyst clicks **Approve**;
  - cut to the trace `/console/system/trace/run_9e0e99ba` at row **#61** (Linker · memory_applied, with #60 Engines adjust and #62 score_pair 0.35 in frame; the viewer has no filter): on screen: `out: {"delta": -0.055, "memory_ids": ["mem-1"], "reason": "mem-1 rejected (different_offenders) relevance 0.55", …}` (filmed by nexus-4). The pair ends at 0.35, band None, so no alert: the narration says the score was lowered, never that an alert changed. The memory comes from an earlier **rejection** (LA-2026-266EFBCEEBBE), which is why the narration says "an earlier rejection".
  - Fallback if no affected alert exists: the H-MEM ledger lines from the worker run (`logs/hmem/ledger.jsonl`). Or the memory page (`/console/memory`): live on real rows, and it already shows a real reject turned into a memory with its ledger row. Its "Changed later scores" list fills only after step 3 of Before recording.
- **Narration:**
  > The analyst sees why: each reason, its evidence, and the Zetaris query behind it. She approves the link. That decision isn't just stored. The Meterless H-MEM engine turns it into a memory. On the next similar case, the trace shows it applied: an earlier rejection lowered this pair's score by a small, capped amount.
- **Check no secrets visible:**
  - the console shows the demo analyst's name only;
  - if you show the ledger file, use a terminal with no env output above it.

### 8 · The series on the map, and a task force · 2:45–3:12 (27 s, ~64 words)

- **Screen:** Pulse Map with **series only** on: the Red Pulsar members joined across stations in time order. **Widen the scrubber window so every member shows** before playing. The series is labelled on screen **"Red two-wheeler chain snatchings · 3 stations"** (9 cases), not "Red Pulsar Duo". The narration says "this series" and doesn't name it. Optional: the series page with its dossier (`/console/series/[seriesId]`, on main since #70); use it only if it shows real rows.
- **Then, live (on main: #154, #178):** on the series, the **analyst** clicks *Propose task force*; cut (off camera: sign in as the **supervisor**); the supervisor approves it on `/console/taskforces`. This creates the task force on camera. **No task force exists beforehand** (none is seeded), and this does **not** decide the hero alert, which stays its own moment in segment 7.
- **Narration:**
  > Approved links grow into a series. On the map, this series appears as one trail across three stations in Chennai's south, instead of separate robberies in separate registers. The Markovian engine can read the whole series in bounded steps to write its dossier. From the series, an analyst proposes a joint task force, and a supervisor approves it.
- **Check no secrets visible:** the map tiles carry no key in view; crop the URL bar (a MapTiler key can sit in tile URLs in devtools, so keep devtools closed).

### 9 · Close · 3:12–3:30 (18 s, ~42 words)

- **Screen:** the title card: Nexus Chennai, Track 1, the sponsor strip and the repo URL. Optional: "All data synthetic" in small print.
- **Narration:**
  > Zetaris finds the facts, Nemotron reads and reasons, the Skeptic gives a second opinion, and every human decision teaches the next alert. All data here is synthetic, and every alert is a suggestion for a person to decide.
- **Check no secrets visible:** a static card.

## Swap-in shots once their features merge (no extra time)

Each replaces part of an existing segment's screen; the narration and timing stay the same. Use one only if it is on `main` and deployed when you record; until then, film the default shot.

| Segment | Swap-in shot | Feature | Status |
|---|---|---|---|
| 4 · Zetaris | the console's *Data sources* page (`/console/system/sources`, admin): 23 sources in 8 types, with counts | WS3-27 (#327) | merged; check on the deployed console before filming (admin view) |
| 5 · Nightshift | the alert's *How this alert was made* card. On the hero alert it starts collapsed and reads **"How this alert was made · Show steps · 9 steps · 4 model calls · 31 Zetaris queries · Nemotron 3 Ultra 550B · Skeptic's final verdict: approved"**; click *Show steps* to open the per-step lane, pinned model and receipt | WS3-25 (#333) | ✅ usable: live, read by nexus-4 as analyst on 27 Oct |
| 6 · Skeptic | the alert page's Skeptic panel. On the hero alert it reads **"Reviewed in 1 round · verdict: approved · nothing struck · model critique applied"**, with a one-step timeline below (Approved · round 1 · score 0.79 · the critique). Show the summary line and the badge; **don't zoom on the critique text**, which the trace stores cut off with "…". The drop itself is still shown in the trace viewer (`run_da0092da`) | WS3-26 (#326) | ✅ usable: live, read by nexus-4 as analyst on 27 Oct |
| 7 · Analyst | the *From the public* panel with a real tip: see **Optional beat 7a** below | WS3-28 (#320) | merged; needs a screened tip on screen (beat 7a) |
| 4 · Zetaris (new) | *New source onboarding*: a new source registered through Zetaris and showing up in the agents' reads | WS1-23 (#368, #376; live run `f2ef9778`) | ✅ usable: merged; clip `clips/console/onboard_run.mp4` (nexus-4). Profiling and registration take ~31 s each, so cut the waits |
| 9 · Close, or after 8 (new) | *Ask Nexus*: a question in plain words answered from Zetaris with its query cited | WS3-30 (#374 worker, #375 screen, #379) | ✅ usable: live on production; chips a/b/c checked by nexus-5 (16 / 4 / 3 cases). Pre-flight step 11 |

### Optional beat 7a · A tip from the public reaches the analyst (WS3-28 merged in #320; film only with a screened tip on screen)

Use it only if #320 ("From the public" on alert and series pages) is merged and deployed. #320 reads tips tied to a crime through `tips.about_crime_id`, which a crime card's tip link sets.

- **Crime:** **CHN-TI-2026-001134** (Thiruvanmiyur), a Red Pulsar series member that is **not** in the hero pair. Its public card is on the default 30-day map: `/map/crime/PC-998D5DCC9560`, with the tip link `/tip/new?about=PC-998D5DCC9560` (nexus-5, read-only check). **Never use the hero's cases** (CHN-AD-2026-001182, CHN-VL-2026-000877).
- **Before recording (off camera):**
  1. In a logged-out browser, open the card and use *Share a tip about this*. Send a short, clean tip that starts with **"[test tip]"**. Tip Guard must pass it: a quarantined tip is counted but never listed.
  2. Keep the worker running so Tip Guard screens it. Note the tip id, and add it to the cleanup list as KEEP-LABELLED or DELETE (Ravee decides).
  3. Check that it appears under *From the public* on the series page (`/console/series/SER-B687C36CFC`).
- **Screen (about 6 s, inside segment 7):** a quick cut of the public card's *Share a tip* form (pre-recorded, logged out), then the series page's *From the public* block listing that tip.
- **Narration:** replace segment 7's last sentence ("Rejections work the same way, and they stay visible to every station.") with:
  > A tip a member of the public sent about one of these crimes shows up here too, screened before any agent read it.
  That's about 7 words more (≈ 3 s), so the video runs about 3:33, still under the 3:40 limit.
- **Safe for the hero:** the tip is tied to one crime that is not in the hero pair. The corroboration factor only counts items that mention both crimes of a pair, and alerts aren't re-scored without a run, so the hero alert doesn't change.

## ElevenLabs narration text (one block per segment)

`demo/narrate.py` reads these blocks directly and writes `demo/out/seg_NN.mp3` through the ElevenLabs API: `python demo/narrate.py --key-file ~/.secrets/elevenlabs.key --voice <id>` (`--list-voices` to pick, `--only seg_03` to redo one, `--dry-run` for word counts and timings). The key is read from the file and never printed. Settings: one voice, Indian English if available, stability ~0.5, similarity ~0.75. These blocks are identical to the narration above; if you edit one, edit both.

```
[seg_01]
Chennai's police stations each see only their own cases. A gang that snatches a chain in Adyar on a Wednesday evening and another in Velachery two days later looks like two unrelated robberies. Nexus connects them. This is our entry for Solving Fragmented Intelligence.

[seg_02]
Case files, legacy exports, ANPR reads and live feeds stay where they are. Zetaris federates them, and agents read only through its named queries. Every model call goes to NVIDIA Nemotron through Meterless Nightshift, and four Meterless engines give agents memory.

[seg_03]
An Adyar officer files a chain snatching: two riders on a red motorcycle, a partial plate. Nemotron Lightning extracts the modus operandi. [A] Nexus reads the CCTV still with Nemotron Super VL. [B] This time the vision model couldn't be reached, so Nexus says so in the trace and uses the officer's caption instead. The World Model files the plate and place as entities every agent shares.

[seg_04]
Here is the same question in Zetaris: same-category crimes within a few kilometres and days of the Adyar case, across every station. One query over the federated sources, no warehouse. The Planner chooses queries like this, and each query's id is kept as evidence.

[seg_05]
Every model call is accountable. This is the Skeptic's critique, sent through Nightshift on the pinned reasoning lane. The trace records the model, Nemotron Ultra, and the receipt Nightshift returned for this exact request. The NVIDIA key lives only inside Nightshift, never in our app.

[seg_06]
The Linker scores each pair on nine factors, in code. Two thefts near the CMBT bus terminus look close: same area, same hour, two thin men. The Skeptic runs its own Zetaris queries: the ages differ, and one is a shop theft, the other a two-wheeler theft. It drops this link. It is a second opinion, not a guarantee: in our planted test it missed look-alike false links, so the officer decides.

[seg_07]
The analyst sees why: each reason, its evidence, and the Zetaris query behind it. She approves the link. That decision isn't just stored. The Meterless H-MEM engine turns it into a memory. On the next similar case, the trace shows it applied: an earlier rejection lowered this pair's score by a small, capped amount.

[seg_08]
Approved links grow into a series. On the map, this series appears as one trail across three stations in Chennai's south, instead of separate robberies in separate registers. The Markovian engine can read the whole series in bounded steps to write its dossier. From the series, an analyst proposes a joint task force, and a supervisor approves it.

[seg_09]
Zetaris finds the facts, Nemotron reads and reasons, the Skeptic gives a second opinion, and every human decision teaches the next alert. All data here is synthetic, and every alert is a suggestion for a person to decide.
```

## Narration facts to re-check at recording time

| Line | Depends on | If it isn't true in your run |
|---|---|---|
| "Adyar on a Wednesday evening… Velachery two days later" | hero pair in `series.yaml`: CHN-AD-2026-001182 on Wed 14 Oct 19:40 IST, CHN-VL-2026-000877 on Fri 16 Oct 19:55 IST (checked) | Change the weekday words to match the dates on screen |
| "two riders on a red motorcycle, a partial plate" | the hero case narrative in `series.yaml` | Read the narrative shown and match it |
| Hero alert is Adyar ↔ Velachery, high | **Live:** LA-2026-E38C6B38B865, **high 0.7887, pending** (nexus-3 DB read, 26 Oct 22:56, after rp7). **Judge path (sample mode, fresh clone @ `de8e666`):** the same pair, high 0.789 (the top link there is Adyar ↔ Thiruvanmiyur, high 0.819) | Read the score shown on screen; never the number from this table |
| "across three stations" | Live series SER-B687C36CFC, "Red two-wheeler chain snatchings · 3 stations": 9 cases across PS-ADYAR / THIRUVANMIYUR / VELACHERY (nexus-3 DB read, 26 Oct 22:56, after D-033 removed test FIR AD-2026-001231 and the naming fix #245) | Say the station count shown on screen, or just "across stations" |
| Seg 3: variant A "Nexus reads the CCTV still with Nemotron Super VL" / variant B "…couldn't be reached…" | A: a vision `model_call` (Super VL, receipt) in the recorded take's trace. B: a `vision_unavailable` step | Say only the variant the trace shows; read one sentence, not both. If the trace has neither, cut the sentence |
| Seg 7: the hero card | LA-2026-E38C6B38B865 still `pending`; 3rd by Score in the dry run | Click it directly wherever it sits; never approve another card |
| Seg 6: "the ages differ… shop theft… two-wheeler theft… It drops this link… in our planted test it missed look-alike false links" | `run_da0092da` step #50: age bands 40-50 vs 18-20, shop_theft vs two_wheeler_theft, no vehicle or MO overlap, drop 0.69 (verified in the trace viewer) | If the recorded trace differs, narrate exactly what it shows. **Never a strike** |
| "the trace shows it applied: an earlier rejection lowered this pair's score" | `run_9e0e99ba` Linker `memory_applied`, TU-425 pair: mem-1 rejected, −0.055 (within ±0.08) | If the shot isn't available, use the memory page (`/console/memory`, mem-1) and end at "turns it into a memory" |
| Zetaris "across every station"; seg 2 "legacy exports and ANPR reads in files" | `sb` + the 12 file-store tables (#140) | If the file tables aren't registered on the recording laptop, cut "legacy exports and ANPR reads in files" |

## After export

- **Frame-by-frame secrets check** of the final MP4 (RULES_CHECK gap 4): every terminal, every browser tab strip, every URL bar.
- **Upload** as YouTube unlisted plus a Drive backup. Open both links in a **private window, logged out** (gap 5).
- **Name:** `OAH2026-Nexus-FragmentedIntelligence-Demo.mp4`. Put the link in the README.
- **Disclose in the README:** "Narration voice generated with ElevenLabs. ElevenLabs is not part of the running product."
