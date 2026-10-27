---
tags: [nexus, deliverables]
---

# Sponsor technology explanation: final draft (WS5-04)

This is the text for the HackOS form's sponsor-technology field. Paste everything below the line. Every claim comes from [EVIDENCE](EVIDENCE.md), checked against `origin/main` @ `6b71108` (26 Oct, after the reboot). Claims added tonight carry their PR numbers; the rest trace to [EVIDENCE](EVIDENCE.md). Nothing in it is marked pending.
Related: [EVIDENCE](EVIDENCE.md) · [SPONSOR_TECH](../SPONSOR_TECH.md) · [README_DRAFT](README_DRAFT.md) · [DECK](DECK.md) · [RULES_CHECK](../hackathon/RULES_CHECK.md)

> **Notes for the chief, not form text:**
> - **NVIDIA Embed is not claimed** (D-027). Nightshift 1.2.7 exposes no embeddings route (`/v1/embeddings` returns 404 for every model), so similar-MO and text search use TF-IDF plus feature vectors in code (`services/api/app/engines/similarity.py`, tested), the spec E2 fallback.
> - **Vision: claim the one verified run.** Super VL is served through a Nightshift cloud lane (D-036) and read a still in live run `reextract_vis_1793040194`. Claim that run; don't claim a success rate, because the free route is rate-limited.
> - **The form may have a length limit.** If it does, keep the first paragraph of each section and the evidence lines, and drop the rest.

---

## Zetaris: the data layer

Every crime fact an agent reads comes through **Zetaris**: federated live from Postgres and REST feeds; station file exports staged in Zetaris's file store.

- **Sources federated today:**
  - **Supabase Postgres**, registered as datasource `sb` under a read-only role (`zetaris_reader`: SELECT only, no RLS bypass). It covers 17 tables (crimes, statements, evidence, forensics, persons, alerts, decisions, series, …) plus 5 datasource views (`stations`, `wards`, `crime_features_v`, `tips_v`, `case_bundle_v`) where JDBC can't map a type or one read needs a join.
  - **REST feeds served by the Nexus API**, registered as Lightning REST tables: weather (`weather_hourly`), news (`news_items`) and social (`social_posts`), with `v_news_mentions` over news and social.
  - **CSV and Parquet file sources** in Zetaris's internal file store: 8 CSV tables (legacy CCTNS exports, CCTV and ANPR camera lists, vehicles, prison releases, history sheets, place aliases, calendar) and 4 Parquet tables (ANPR reads, 112 calls, the legacy archive, map POIs).
- **Governed access.** Agents can run only registered *named queries*, through one adapter (`services/api/app/adapters/zetaris.py`). Every query id goes into the trace and into the alert's evidence. Live today, each with Lightning SQL and a DuckDB twin for sample mode:
  - `q_case`: one case with its vehicles, statements, evidence and forensics;
  - `q_candidates`: blocking, i.e. same-category cases within a distance and time window;
  - `q_features`: extracted MO features;
  - `q_dq_flags`: data-quality flags;
  - `q_news`: news that mentions a case's place;
  - `q_hex_counts`: counts per H3 cell, for the hotspot test;
  - `q_search`: text and filter search over crimes and statements, for the console search box;
  - `q_station_matrix`: approved alerts station × station;
  - `q_tip_corroboration`: screened public tips in a crime's area and time window;
  - `q_context`: calendar, nearby place types and hourly weather for one crime;
  - `q_cases`: full case details for up to 25 crimes in one trip (Planner candidates, Skeptic pairs);
  - `q_vehicle_trail`: ANPR reads of a plate pattern in a time window, each tied to the nearest crime scene within 1.5 km and 2 h;
  - `q_offender_return`: offenders released in the last 60 days whose earlier MO shares the case's MO tags, home ward first; in the default plan this call currently fails on cases with MO tags, a disclosed bug (README Limitations, #451);
  - `q_calls_near`: 112 emergency calls within a set distance and time of a crime;
  - `q_dq_summary`: row count of each data-quality rule view, for the System page (via `app.dq_status`, since Vercel can't reach Zetaris).
  - Count (recounted on main, 27 Oct): **18 registered**: **13 the agents run**, 4 system queries (`q_ping`, `q_dq_flags_all`, `q_dq_summary`, `q_source_counts`) and 1 registered but not called (`q_station_matrix`). Source onboarding uses its own fixed templates. Live check on 26 Oct: the 15 registered then all returned rows on Zetaris.
  - Semantic layer live: 13 views in the `nexus` container. `v_crime_unified` puts every crime record shape in one view (Supabase FIRs + legacy CCTNS CSV + Parquet archive, 19,540 rows). 8 data-quality views are summed up by `dq_flags`. 4 feed views include `v_news_mentions`, which `q_news` reads. Vehicle trail, offender return, tip corroboration and calls-near are named queries that join sources directly, not views.
- **Data quality is part of the evidence.** Eight data-quality views: duplicate FIRs filed by two stations, bad geo, inconsistent times, unmapped IPC/BNS sections, orphan evidence, tips without an incident, stale cameras, and a combined flag view. Live data-quality flags come from a snapshot taken by the last data-quality pass (`app.dq_status`, as of the time shown in each run's trace); the per-case lookup takes about 1 s through Zetaris (#348). A FIR filed after that pass shows no flags until the next pass.
- **Untrusted input stays out.** Public tips reach Zetaris only through `tips_v`, a view of safe columns. The passphrase hash and raw tip text are never exposed to the data layer.
- **The Skeptic uses Zetaris too.** It runs its own named queries to re-check the Linker's pairs, then critiques each one. It can send a pair back for a narrower search or drop it, as a second opinion; the officer decides. On the judge path, example 3 shows a drop: different crime types, 4.1 km apart, day vs night (`output_examples/example_3.json`, #283). **Measured limit:** on a pre-registered planted test its model critique dropped 0 of 24 look-alike false links (sent back 10), so it is not a guarantee (#392). Since ~07:20 IST on 27 Oct a deterministic contradiction check runs on new cases (#422): 24/24 planted false links dropped with 0/8 twin false-drops on a fresh pre-registered set. That passes by construction on generator data; the only non-planted evidence is an offline what-if (9 false alerts dropped, 0 true links lost). On an independent hand-written look-alike set it failed: 10 of 24 dropped, 2 of 8 true twins wrongly dropped (#444).
- **Judges can load the same data into their own Zetaris.** `python -m data.setup_live` generates the dataset, stages it in Zetaris's file store and registers it, so agents read with no Supabase (`ZETARIS_DATA=files`; #280, `data/README.md` §5). Its model-output fixtures are merged too (#293), and a clean-machine run passed (#325: fresh clone into a throwaway store, about 10 minutes including install).

## Meterless engines: all four, each in a feature, each with a passing test

| Engine | Feature it powers | Test | Result |
|---|---|---|---|
| **World Model** | One canonical entity per plate, person, phone, place and FIR, with stable ids and provenance; context for the Linker and Skeptic | Official Meterless conformance suite, unchanged, against the vendored reference; plus Nexus feature tests | **8/8** |
| **H-MEM** | Analyst approvals and rejections become memories that shift a similar pair's score by at most ±0.08 ("memory applied" on the alert), with an append-only trust ledger | Official conformance suite; plus feature tests | **13/13** |
| **Markovian** | Series dossier: reads a whole series in bounded chunks with a capped carryover; logs projected vs actual tokens | Official conformance suite; plus feature tests | **8/8** |
| **Scout Intent** | Routes analyst searches; **Tip Guard** screens every public tip for injection, threats, abuse and spam before any agent reads it, and flags emergencies | A 40-item held-out set written after tuning; the 40 live seeded tips; a 153-item tuned fixture set | **Independent:** held-out 40 (never tuned on): route accuracy **0.975**, injections **7/7**, 0 false quarantines (0.950 before #144, a routing fix prompted by a console search, not by the held-out set). On the 40 live seeded tips, **0 of 30 genuine tips falsely quarantined** and emergencies **2/2** urgent. **Live misses and the fix:** before #128, injections **3/4** and spam **1/4** quarantined; after rules for those four shapes, **4/4** and **4/4**. That after-number is **not independent recall**, because those four misses shaped the rules (and the labels beyond the four were inferred from the text). Tuned fixture set (153: 66 queries + 87 tips; the rules were tuned on it): route accuracy **1.000** (the old rules scored 0.871 on the first 147), injections **23/23**, emergencies **8/8**. Re-run on a fresh clone in WS5-08 part 2. |

- **How they run.** World Model, H-MEM and Markovian are the official TypeScript references, vendored unmodified from github.com/Meterless/Meterless @ `1742dec5` (Apache-2.0). They are served to the Python agents by a small local sidecar, so the official conformance suites run unchanged. Scout Intent has no runnable reference, so Nexus implements it from the Meterless Scout spec.
- **Ports.** Python ports of the three references are the default in-process backend, and a parity test checks that both backends agree.
- **CI.** CI runs the conformance suites and the feature tests on both backends on every pull request.
- **Persistence.** Engine state can be written to Supabase (`wm_*` and `hmem_*` tables, ledger append-only), so the police console shows it.
- **Evidence files:** `logs/conformance_world_model.txt`, `logs/conformance_hmem.txt`, `logs/conformance_markovian.txt`, `logs/feature_scout_intent.txt`.

## Meterless Nightshift: the primary AI provider

- **Every model call in the product goes to Nightshift**, through one adapter (`services/api/app/adapters/nightshift.py`). It uses Nightshift's OpenAI-compatible `/v1/chat/completions` with the runtime token and the `meterless-app` / `meterless-scope` headers.
- **The NVIDIA key lives only in Nightshift.** The app holds only the Nightshift URL and the runtime token, which it can read from the token file Nightshift writes itself. Every call still goes through Nightshift. For vision, Nightshift routes Super VL through OpenRouter, and that key is also held only in Nightshift (D-036).
- **Pinned lanes, never `meterless/auto`.** The adapter refuses an unpinned or auto model. Each agent role uses a fixed lane.
- **Every call is traced:** the lane, the pinned model, the model Nightshift reports back, a receipt id (a Meterless receipt header if present, otherwise the response id), the latency and the status. The trace goes to `logs/trace-<run_id>.jsonl`, to stdout and to the console's trace viewer.
- **Receipts verified (#363).** 190 of 193 traced model calls carry a Nightshift receipt, and all 190 signatures verify (Ed25519, one key, fingerprint `c9f71fd6…`); the other 3 calls failed with no reply. 30/30 replayed fixture receipts also verify. Signatures verify against the receipt's embedded Ed25519 key, and every receipt uses the same key (sha256 fingerprint `c9f71fd60dad62bbcb260065a6c4be439dc4997b65785a0e083541b4061c7865`; the runtime's `/v1/meterless/receipts` serves the same key). The replayed fixtures keep synthetic prompt previews inside their signed bodies. Re-run: `python scripts/verify_receipts.py` (needs the Supabase URL and a service-role key file; result in `logs/receipts_verification.json`, #363). Without credentials: `python scripts/verify_receipts.py --fixtures-only` (30 of 30 valid, #453). Since #455 the adapter also checks each reply's receipt at call time, in degraded mode: a failed check is traced as `receipt unverified (degraded)`, never refused.
- **Failures are honest.** Transport errors and 5xx responses are retried, up to 3 attempts with backoff. After that, the agent degrades to a traced code-only path. Sample mode replays output recorded from live Nightshift calls, labelled `replayed`. It never invents an answer.
- **Judges can check every model step without Nightshift.** `output_examples/` holds three runs made through Nightshift: example 1 recorded live, examples 2 and 3 regenerated by replaying their live-recorded replies on the send-back fix (#358; results unchanged). `data/sample/model_fixtures/` holds their 30 model responses (#283, #358). The sample-mode Docker container answers all three examples with **no network at all** (`--network none`) and matches the recorded outputs, apart from run timings and the per-query Zetaris ids. CI job `judge-offline` checks this on every push to main (#285). Replay is time-zone safe: sample data runs in the city's time zone, not the host's (#290).

## NVIDIA Nemotron: where it contributes

| Lane | Model (pinned, through Nightshift) | Job in Nexus |
|---|---|---|
| `fast` | `nvidia/nemotron-3.5-lightning-30b-a3b` | Extractor: modus operandi labels from FIR narratives, statements, tips and news; Sanitiser: public appeal drafts; Briefer: zone briefing prose |
| `reason` | `nvidia/nemotron-3-ultra-550b-a55b` | Planner: picks and orders Zetaris queries; Linker: one plain reason per factor; Skeptic: the critique that can send back or drop a link (a second opinion); Series analyst: dossier notes |
| `vision` | `nvidia/nemotron-3.5-super-vl-120b-a12b`, served through a Nightshift cloud lane (OpenRouter free route) | CCTV stills and evidence photos. Verified in a live Nexus run: run `reextract_vis_1793040194` (27 Oct): an Extractor `model_call` on lane `vision`, model `nvidia/nemotron-3.5-super-vl-120b-a12b`, receipt `chatcmpl-5dfe68c6-80f5-4c50-8962-d45f726a7cb4`, status ok, 24 s; the extracted features had no `degraded` entries and carried `visual_tags` read from the still. If the route refuses or rate-limits, the Extractor traces `vision_unavailable` and uses the officer's caption. No visual result is faked |

- **No embedding model is claimed.** Nightshift 1.2.7 exposes no embeddings route, so similar-MO search and text search use TF-IDF and feature vectors computed in code (the spec's fallback), traced as `embed_fallback`. The Nemotron embed model is not claimed.
- **Every trace line names the Nemotron model** that handled the request, and the model Nightshift reports back.
- **Why Ultra:** the spec planned Nemotron Super 120B for reasoning, but it isn't served to our key, so the reasoning lane runs Ultra 550B.
- **Numbers come from code.** Models write labels, plans and reasons; any number a model returns is ignored.

## Cursor

Not used. Nexus was built with Claude Code as a development tool. Claude Code is not in the product's request path.

## Measured result

On 60 synthetic cases with planted ground truth, code scoring (0 model calls) links with **precision 0.59, recall 0.86 (F1 0.70)** (model in the loop (#21, pre-registered side eval): P 0.75 / R 0.24 / F1 0.37 on 10 cases, 4 of which hit the 300 s run deadline), against 0.09 / 0.30 (F1 0.13) for a rules-only baseline (same category, ≤ 2 km, ≤ 14 days). A stronger pre-registered baseline that also matches vehicles and plates (#454) reaches F1 0.24; its strict variant is more precise than the agents (0.71) at recall 0.15. **HIGH-band alerts were correct 10 of 10 times**; MEDIUM 56%, which is why an analyst decides every alert. The eval makes no model calls; 13 of the 60 cases had model-extracted features, and the rest were scored without them (`output_examples/eval_report.json`, #275; reproducible from a fresh clone with the command in the README's Evaluation section).

## What was unique about our use of the sponsor technology

1. **The data layer is also the second opinion.** The Skeptic doesn't trust the Linker. It re-runs Zetaris named queries itself, critiques each pair against its own rows, and can send a pair back for a narrower search or drop it; the officer decides. Every reason carries the Zetaris query id and the row behind it. We measured its limit too: it dropped none of 24 planted look-alike false links (#392).
2. **Human decisions change the next score.** Rejected links stay visible to every police role. Through H-MEM, a rejection ("same street, different entry method") lowers the score of the next similar pair, within a hard ±0.08 bound, and the alert says "memory applied". Each step is in a trust ledger.
3. **The public can help without steering the system.** Scout Intent screens every anonymous tip before any agent reads it, and fails closed. Zetaris sees tips only through a safe-column view.
4. **The official engines run unchanged.** The Meterless references are vendored unmodified and pass their own conformance suites, which CI re-runs on every pull request alongside our feature tests.
5. **Every model call is accountable.** Pinned Nemotron lanes through Nightshift, with the model and receipt logged per call, mean a judge can see which model wrote which sentence of an alert.
