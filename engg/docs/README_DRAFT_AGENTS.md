---
tags: [nexus, deliverables]
---

# README draft: agents, /run, sample mode, limitations

These are draft README sections from the agents lane (nexus-3), for nexus-chief to merge into the root `README.md`. Numbers marked **TBD** come from real runs and are filled in only from `output_examples/` (rule R10).
Related: [AGENTS](AGENTS.md) · [ENGINES](ENGINES.md) · [SPEC](SPEC.md) (C4, E3, F, H)

---

## How Nexus links crimes

A new FIR goes through a graph of agents (LangGraph). Agents read data only through **Zetaris** named queries, and every model call goes to **NVIDIA Nemotron** through **Meterless Nightshift** on a pinned model per role. Scores are computed in code. The models label, plan and explain, but never set a number.

| Agent | Model lane | Its job |
|---|---|---|
| **Scout Intent** | Meterless engine | Routes each event and search, and screens public tips for injection, spam and threats |
| **Tip Guard** | Scout Intent engine | Quarantines unsafe tips before any agent reads them (fails closed) |
| **Extractor** | Nemotron Lightning (fast) | Turns FIR narratives, statements, tips and news into modus operandi (MO) labels; CCTV stills go to Super VL; adds entities to the World Model |
| **Planner** | Nemotron Ultra (reason) | Picks and orders the Zetaris named queries (at most 3 rounds) |
| **Linker** | code + Nemotron Ultra | Scores 9 weighted factors in code (MO, space–time, vehicle/ANPR, suspect description, weapon, target, forensic, corroboration, offender return), applies H-MEM memory (max ±0.08), and writes one plain reason per factor |
| **Skeptic** | code + Nemotron Ultra | Re-queries Zetaris itself, strikes any factor its own rows don't support, and can send a pair back (at most 2 times) or drop it. The model may only downgrade a pair |
| **Alert writer** | code | Writes alerts with score, band, coverage, per-factor evidence (view, row, Zetaris query id), Skeptic verdict and memory applied |
| **Series analyst** | Markovian + Nemotron Ultra | Groups 3+ linked cases into a series and builds a dossier over hundreds of records in bounded chunks |
| **Hotspot detector** | code | Poisson test on hex-cell × time-window counts |
| **Sanitiser** | Nemotron Lightning | Drafts a public appeal from redacted facts; code checks for leaks; an officer must publish it |
| **Briefer** | Nemotron Nano or Lightning | Writes a zone briefing in which every number comes from code |

Analyst decisions (approve, or reject with a reason) go back into **H-MEM**, so the next similar pair scores differently and its alert card shows "memory applied".

## Run it (judges)

```bash
python -m venv .venv && .venv/bin/pip install -r services/api/requirements.txt   # Windows: .venv\Scripts\pip
SAMPLE_MODE=true python run.py --once input_examples/example_1.json
```

or, with the API running (`python run.py`):

```bash
curl -s -X POST localhost:8000/run -H "Content-Type: application/json" -d @input_examples/example_1.json
```

| Input | What it shows |
|---|---|
| `example_1.json`: case CHN-AD-2026-001182 | Red Pulsar Duo: a cross-station chain-snatching link through a partial plate and two ANPR cameras; the Skeptic's strikes are in the trace |
| `example_2.json`: case CHN-KU-2025-000078 | Grille Cutters: night house breaks across 6 stations in Pongal week |
| `example_3.json`: batch of 2 cases | Night Cab (fake cab, knife, white Swift Dzire) and a ligature homicide pair |

Each response has `run_id`, `status`, `output.alerts`, `output.series`, `output.hotspots`, `output.summary`, `agents`, `engines`, `trace_id`, `log_file` and `execution_time_seconds`. `logs/trace-<run_id>.jsonl` has one line per step: agent, action, model and routed model, Nightshift receipt, Zetaris query ids, engine, confidence, retries and status. The real outputs are in `output_examples/`.

## Sample mode vs live

| | Sample mode (`SAMPLE_MODE=true`) | Live |
|---|---|---|
| Data | `data/sample/` (about 600 synthetic crimes, 3 series, 40 tips); named queries run on DuckDB twins of the Zetaris views | Zetaris federates Supabase, S3 CSV/Parquet and the REST feeds |
| Models | Replays model output **recorded from live Nightshift calls** (`data/sample/model_fixtures/`); trace lines say `replayed` | Nightshift on pinned Nemotron lanes |
| Agents | Same graph, same scoring, same Skeptic | same |
| If a recording is missing | The documented fallback runs and is traced: default query plan, code-written reasons, code-only Skeptic verdicts. It never invents an answer | — |
| Engine state | In memory | `ENGINES_PERSIST=supabase` writes World Model and H-MEM state to the `wm_*` / `hmem_*` tables the console reads |
| Alerts | Returned in the response (and in Supabase if configured) | Written to Supabase; the console updates in real time |

## Measured quality

`python -m app.eval` compares the linker against a rules-only baseline (same category, ≤ 2 km, ≤ 14 days) on the planted ground truth: 30 series, decoys and duplicates. It measures exactly the code that produces alerts, with no model calls. Report: `output_examples/eval_report.json`.

| | Precision | Recall | Alerts |
|---|---|---|---|
| Nexus | **TBD** | **TBD** | **TBD** |
| Rules-only baseline | **TBD** | **TBD** | **TBD** |

The alert card states each band's measured precision ("alerts in the high band were correct N% of the time on the evaluation set").

## Limitations

- **All data is synthetic**, generated for this hackathon. Quality numbers are measured on planted structure, not on real police data.
- **Vision:** at the time of writing, Nightshift returns `no_vision_model` for image requests. The Extractor then falls back to the officer's caption or recorded tags, and the trace says `vision_unavailable`.
- **Model choice:** the spec's Nemotron Super 120B isn't served to our key, so the `reason` lane uses Nemotron Ultra 550B (DECISIONS D-017). It's slower, and the 5-minute run deadline reserves 45 s, below which the code results stand without model explanations.
- **Explanations are model-written**, and the Linker's reasons can be imperfect. Numbers can't be, because they come from code, and the Skeptic re-checks every factor against fresh rows.
- **Hotspots** use a simple Poisson test against the cell's own recent history. They flag concentrations, not causes.
- **Human in the loop:** Nexus raises alerts and drafts appeals. It never acts on its own. An analyst decides every link, and an officer publishes every appeal.
- **Protected attributes** (religion, caste, community) are never used for scoring or written into public text. Physical descriptions are used only from witnesses and CCTV of a specific incident (LNK-13).
