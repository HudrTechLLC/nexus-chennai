---
tags: [nexus, deliverables]
---

# HackOS compliance map

Every HackOS requirement, mapped to where Nexus meets it. Requirements come from [DIGEST](../hackathon/DIGEST.md) ("Required submission components", "Required sponsor technology", "Strongly recommended"). Status: ✅ met on `main` · 🟡 met, with a risk noted · 🔴 **not met yet**.
Related: [FORM](FORM.md) · [DECK](DECK.md) · [VIDEO_SCRIPT](VIDEO_SCRIPT.md) · [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md) · [EVIDENCE](EVIDENCE.md) · [RULES_CHECK](../hackathon/RULES_CHECK.md)

Written 27 Oct (nexus-7). Video timestamps are the script's planned slots; the cut-sheet from dry-run #3 (10:30 IST) replaces them.

## 1. Demo video (1–4 min)

Planned length 3:30 (narration rendered: ~3:16, ElevenLabs voice Adam). Status: 🔴 **not recorded yet** (recording 15:30 IST).

| Required | Segment · planned time | What is on screen | Status |
|---|---|---|---|
| The problem | seg_01 · 0:00–0:18 | Pulse Map: 70 station silos, one city | ✅ scripted |
| Main workflow | seg_03 → seg_08 · 0:35–3:12 | live FIR → extraction → Zetaris → Nightshift → Skeptic → analyst → series | ✅ scripted |
| How the agent solves Track 1 (fragmented sources) | seg_02 · 0:18–0:35, seg_04 · 1:00–1:20, seg_08 · 2:45–3:12 | sources stay in place and are federated; one series across 3 stations | ✅ scripted |
| Key features | seg_06 · 1:40–2:10, seg_07 · 2:10–2:45, seg_08 · 2:45–3:12 (+ optional Ask Nexus, source onboarding) | Skeptic second opinion, analyst decision + H-MEM, map + task force | ✅ scripted |
| Agent querying Zetaris | seg_04 · 1:00–1:20 (also seg_06: the Skeptic's own queries) | Zetaris UI running `q_candidates`; trace lines `via=zetaris` | ✅ scripted |
| The feature an engine powers | seg_07 · 2:10–2:45 (H-MEM "Memory applied") | the analyst decides the hero on camera, and the next run shows memory applied | 🟡 **risk:** needs an un-rehearsed on-camera approve plus an off-camera step (pre-flight 3). **Fallback shot:** Tip Guard quarantining an injected tip (Scout Intent), or the series dossier (Markovian) |
| One real request through Nightshift, model named | seg_05 · 1:20–1:40 | *How this alert was made* card (model, receipt), and the Skeptic `model_call` in `run_da0092da` | ✅ scripted |
| 1–4 minutes | whole | 3:30 planned, hard limit 3:40 | ✅ planned |
| Link works logged out (YouTube unlisted + Drive) | — | — | 🔴 after upload (Ravee) |

## 2. Slide deck (8 points)

Content is in [DECK](DECK.md). Status: 🔴 **deck file not built yet** (slides after recording, 19:00+).

| Point | Slide | Status |
|---|---|---|
| 1. Problem and target users | Slide 2 | ✅ content |
| 2. Solution | Slide 3 | ✅ content |
| 3. Agent workflow / architecture | Slides 4, 5 | ✅ content |
| 4. Technical stack | Slide 5 | ✅ content |
| 5. How Zetaris and Meterless were used | Slides 6, 7 (+ 8, NVIDIA) | ✅ content (slide 6: 13 agent-facing queries + 4 system) |
| 6. What was unique about the sponsor tech use | Slide 9 | ✅ content (Skeptic framed as a second opinion) |
| 7. Product visuals | Slide 10 (+ screenshots from the recording) | 🟡 screenshots come from the recording |
| 8. Future enhancements | Slide 13 (with limitations, incl. the planted Skeptic test) | ✅ content |

## 3. Public GitHub repo with README

| Required | Where | Status |
|---|---|---|
| Public repo | `HudrTechLLC/nexus-chennai` | 🔴 **private until submission** (WS5-09, Ravee) |
| README: setup | README "Setup" (Docker, venv, live configuration) | ✅ |
| README: usage | README "Run", "Examples", "Live app" | ✅ |
| README: dependencies | README "Setup" (Python 3.11+, Docker) and "Licences" (every library) | ✅ |
| README: video link | README line 9 | 🔴 `[PENDING: video link]` until upload |
| Strongly recommended: `run.py`, `POST /run`, Docker, JSONL traces in `logs/` + stdout, ≥ 3 inputs with real outputs, `SAMPLE_MODE` with no credentials, capped loops and timeouts, `.env.example`, `metadata.json` | README; `input_examples/`, `output_examples/`; CI `judge-offline` | ✅ (WS5-08) |
| Disqualifiers (runs, no hardcoding, traces, sponsor tech, no secrets, synthetic data, declarations) | [WS5-08 checklist and results](../validation/WS5-08-2026-10-27.md) | ✅ part 2 PASS; the final pass on the polished main is pending (nexus-6) |

## 4. Sponsor technology explanation (form)

Text: [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md).

| Required | Section | Status |
|---|---|---|
| Zetaris integration | "Zetaris: the data layer" (23 sources in 8 types; 18 registered named queries: 13 agent-facing) | ✅ |
| Which Meterless engines, what each does, the test | "Meterless engines: all four" (8/8, 13/13, 8/8; Scout Intent held-out 0.975, 7/7) | ✅ |
| How the app connects to Nightshift | "Meterless Nightshift: the primary AI provider" (pinned lanes; 190/193 calls with a receipt, all 190 verify) | ✅ |
| Where NVIDIA contributes | "NVIDIA Nemotron" (Ultra 550B, Lightning 30B, Super VL; model logged per call) | ✅ |
| What was unique | "What was unique about our use of the sponsor technology" | ✅ |

**Eligibility (missing any = not eligible):** Zetaris as the data layer ✅ · a Meterless engine in a working feature with a passing test ✅ (all four) · Nightshift as the primary AI provider ✅ · Nemotron through Nightshift with the model shown per request (DGX Spark) ✅.

## 5. Form declarations

| Required | Where | Status |
|---|---|---|
| Pre-existing components declared | [FORM](FORM.md) "Pre-existing components" | ✅ |
| Cursor field | [FORM](FORM.md) "Cursor": not used (Claude Code as a dev tool) | ✅ |
| AI usage | [FORM](FORM.md) "AI usage" (product, development, ElevenLabs narration) | ✅ |

## 6. Only Ravee can do these

1. **Team roster names** on HackOS. The roster **locks when the draft is first created**, so confirm the members first (WS5-10).
2. **Check the live form's field names and length limits** against [FORM](FORM.md) when creating the draft.
3. **Upload the video** (YouTube unlisted + Drive backup), test both logged out, and paste the links into the README and the form.
4. **Make the repo public** (WS5-09) and open it logged out.
5. **Upload the deck.**
6. **Enter the demo accounts** (officer, analyst, supervisor; never admin) in the form only.
7. **Submit** by 23:15 IST (hard deadline 23:45 UTC).

## Gaps (red), in order

1. 🔴 Video not recorded (15:30), uploaded or linked (README L9, form).
2. 🔴 Deck file not built (19:00+).
3. 🔴 Repo still private (Ravee, at submission).
4. 🔴 Team roster names (Ravee).
5. 🟡 The engine-feature video beat (H-MEM) depends on an un-rehearsed on-camera approve; keep the Scout Intent / Markovian fallback shot ready.
