---
tags: [nexus, deliverables]
---

# HackOS compliance map

Every HackOS requirement, mapped to where Nexus meets it. Requirements come from [DIGEST](../hackathon/DIGEST.md) ("Required submission components", "Required sponsor technology", "Strongly recommended"). Status: ✅ met on `main` · 🟡 met, with a risk noted · 🔴 **not met yet**.
Related: [FORM](FORM.md) · [DECK](DECK.md) · [VIDEO_SCRIPT](VIDEO_SCRIPT.md) · [SPONSOR_TECH_FINAL](SPONSOR_TECH_FINAL.md) · [EVIDENCE](EVIDENCE.md) · [RULES_CHECK](../hackathon/RULES_CHECK.md)

Written 27 Oct (nexus-7); statuses updated after recording. Video timestamps are from the **final cut** (3:14, nexus-2's timeline), checked frame by frame by nexus-7.

## 1. Demo video (1–4 min)

Final length **3:14** (narration ElevenLabs voice Adam). Status: ✅ **recorded and final**. Take B (the Zetaris UI running `q_candidates`) was skipped by the chief, so the Zetaris UI itself is not shown; agents querying Zetaris is shown in the trace instead (row below).

| Required | Segment · planned time | What is on screen | Status |
|---|---|---|---|
| The problem | seg 1 · 0:03–0:23 | Pulse Map: 70 station silos, one city | ✅ |
| Main workflow | seg 3 → seg 8 · 0:43–3:00 | live FIR → extraction → Zetaris → Nightshift → Skeptic → analyst → series → task force | ✅ |
| How the agent solves Track 1 (fragmented sources) | seg 2 · 0:23–0:43, seg 4 · 1:03–1:24, seg 8 · 2:37–3:00 | sources stay in place and are federated by Zetaris; one series across 3 stations | ✅ |
| Key features | seg 6 · 1:44–2:13, seg 7 · 2:13–2:37, seg 8 · 2:37–3:00 | Skeptic second opinion, analyst decision + H-MEM, map + task force (approved on camera) | ✅ |
| Agent querying Zetaris | seg 3 · ~0:52–1:03 (Extractor `zetaris_query` rows, `via=zetaris`, query ids); seg 5 · ~1:34–1:45 and seg 6 · ~1:57–2:13 (Skeptic's own `zetaris_query` rows #46–#48, `via=zetaris`, query ids, then the drop citing them); seg 7 · ~2:28–2:37 (Linker `zetaris_query` #59). Context: seg 4 · 1:03–1:24 Data sources ("federated by Zetaris", counts "via Zetaris"); seg 5 card "31 Zetaris queries" | trace lines, not the Zetaris UI (take B skipped) | ✅ |
| The feature an engine powers | seg 7 · ~2:28–2:37 (`s7_hmem_trace`) | the hero approved on camera (09:00:51 IST), then the trace row #61 `memory_applied` (mem-1 rejected, delta -0.055, within ±0.08) | ✅ landed |
| One real request through Nightshift, model named | seg 5 · 1:24–1:44 | *How this alert was made* card, then the Skeptic `model_call` #49 in `run_da0092da` (Nemotron Ultra, receipt id) | ✅ |
| 1–4 minutes | whole | 3:14 | ✅ |
| Link works logged out (YouTube unlisted + Drive) | — | — | 🔴 after upload (Ravee) |

## 2. Slide deck (8 points)

Content is in [DECK](DECK.md). Status: ✅ **built**: 15 slides as a Claude artifact, exported by Ravee.

| Point | Slide | Status |
|---|---|---|
| 1. Problem and target users | Slide 2 | ✅ content |
| 2. Solution | Slide 3 | ✅ content |
| 3. Agent workflow / architecture | Slides 4, 5 | ✅ content |
| 4. Technical stack | Slide 5 | ✅ content |
| 5. How Zetaris and Meterless were used | Slides 6, 7 (+ 8, NVIDIA) | ✅ content (slide 6: 13 agent-facing queries + 4 system) |
| 6. What was unique about the sponsor tech use | Slide 9 | ✅ content (Skeptic framed as a second opinion) |
| 7. Product visuals | Slide 10 (+ screenshots from the recording) | ✅ |
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
| Disqualifiers (runs, no hardcoding, traces, sponsor tech, no secrets, synthetic data, declarations) | [WS5-08 checklist and results](../validation/WS5-08-2026-10-27.md) | ✅ part 3 PASS on `5a7c549` (#416); hard-freeze diff check at 19:00 (nexus-7) |

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

The remaining 🔴 items are all Ravee's: make the repo public, the team roster, the form, and submit (plus the video link once the HQ upload is done).


1. **Team roster names** on HackOS. The roster **locks when the draft is first created**, so confirm the members first (WS5-10).
2. **Check the live form's field names and length limits** against [FORM](FORM.md) when creating the draft.
3. **Upload the video** (YouTube unlisted + Drive backup), test both logged out, and paste the links into the README and the form.
4. **Make the repo public** (WS5-09) and open it logged out.
5. **Upload the deck.**
6. **Enter the demo accounts** (officer, analyst, supervisor; never admin) in the form only.
7. **Submit** by 23:15 IST (hard deadline 23:45 UTC).

## Gaps (red), in order

Closed after recording: ✅ video recorded and final (3:14) · ✅ deck built (15 slides) · ✅ H-MEM beat landed (seg 7, `s7_hmem_trace`).

1. 🔴 Video link: HQ render re-uploaded by Ravee, then README line 9 and the form (chief sends the link).
2. 🔴 Repo still private (Ravee, at submission).
3. 🔴 Team roster names (Ravee).
4. 🔴 Form filled and submitted (Ravee, by 23:15 IST).
