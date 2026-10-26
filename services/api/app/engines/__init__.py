"""Meterless engines facade (LANES.md section 2). Owned by the engines lane (nexus-2).

    from app.engines import world_model, hmem, markovian, scout_intent, use_tracer

    with use_tracer(tracer):           # bind the run's Tracer; every call emits one event
        ids = world_model.ingest(entities, source="Extractor")
        ctx = world_model.context(crime_ids)
        adj = hmem.adjust(pair)        # abs(adj["delta"]) <= 0.08
        hmem.record_decision(alert_id, "reject", "different_offenders", note, pair)
        d = markovian.dossier(series_id, records)
        r = scout_intent.classify(text, "tip")

Trace events: agent_name "Engines", action = function name, engine in
{"world_model", "hmem", "markovian", "scout_intent"}.
Backend: env ENGINES_BACKEND = "sample" (default, in-process) or "sidecar" (the vendored
TypeScript references in engines-ts/, over HTTP at ENGINES_SIDECAR_URL).
"""

from app.engines import hmem, markovian, scout_intent, world_model
from app.engines._runtime import ENGINE_NAMES, backend, get_tracer, set_tracer, use_tracer

__all__ = ["world_model", "hmem", "markovian", "scout_intent", "use_tracer", "set_tracer", "get_tracer",
           "backend", "ENGINE_NAMES"]
