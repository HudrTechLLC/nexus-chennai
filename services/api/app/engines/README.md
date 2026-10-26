# Meterless engines facade (`app.engines`)

Owned by the engines lane (nexus-2). Contract: `engg/docs/LANES.md` section 2. Spec: Parts P3–P6 and E4.

| Call | Returns | Engine |
|---|---|---|
| `world_model.ingest(entities, source)` | stable ids, input order | `world_model` |
| `world_model.context(crime_ids)` | `entities`, `relations`, `provenance`, `selection` (id + reason), `missing`, `truncated` | `world_model` |
| `hmem.adjust(pair)` | `delta` (clamped to ±0.08), `memory_ids`, `reason`, `raw_delta` | `hmem` |
| `hmem.record_decision(alert_id, decision, reason_code, note, pair)` | `None` (memory + trust ledger) | `hmem` |
| `markovian.dossier(series_id, records)` | `text`, `cited_ids`, `chunks`, `tokens_projected`, `tokens_actual`, plus `tokens_saved`, `token_label`, `status`, `unread_ids`, `chunk_log` | `markovian` |
| `scout_intent.classify(text, kind)` | `route`, `intent`, `risk`, `action` (`clean`/`quarantine`/`urgent`) | `scout_intent` |

Every call emits one trace event: `agent_name="Engines"`, `action=<function>`, `engine=<engine>`.
Bind the run's tracer with `with use_tracer(tracer): ...` (or `set_tracer`); without one, events go to
`logs/trace-engines_*.jsonl`.

## Backends

`ENGINES_BACKEND=sample` (default) runs the logic in-process: Python ports of the Meterless TypeScript
references (World Model, H-MEM, Markovian) and a spec implementation of Scout Intent. `ENGINES_BACKEND=sidecar`
calls the vendored TypeScript references in `engines-ts/` over HTTP (`ENGINES_SIDECAR_URL`).

## Ids and inputs

- World Model ids: plates, phones, H3 cells, FIRs, evidence and series are externally keyed
  (`vehicle:plate:TN09AB1234`; plates normalised to upper-case alphanumerics, phones to the last 10 digits).
  People are name-keyed (`ent_<sha256[:16]>`) and resolved by name similarity (≥ 0.85 merge, 0.82–0.85 review).
- H-MEM `pair`: `{"a": {...}, "b": {...}}` of MO features. Ids, timestamps, coordinates and free text are ignored.
  Memories live in `logs/hmem/` (`state.json`, `ledger.jsonl`).
- Markovian records: `{"id", "kind", "date", "text", "mo_tags", "status"}`. Citations not in the input are removed.
  Runs are logged to `logs/markovian_runs.jsonl` (projected vs actual tokens, estimated as chars/4).
- Scout Intent `kind`: `query` (routes `case`, `entity`, `similar_mo`, `map`, `image`, `series`, `stats`) or `tip`
  (routes `tip_intake`, `quarantine`, `emergency`). Trace events never contain the tip text.

Source: github.com/Meterless/Meterless @ `1742dec56a66e58eef9dda2d2b865823758ca8cd`, Apache-2.0
(see `engines-ts/NOTICE`).
