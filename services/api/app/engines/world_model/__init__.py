"""World Model facade (spec P3/E4): one canonical entity per real-world thing.

    from app.engines import world_model
    ids = world_model.ingest([{"type": "vehicle", "key": "TN 09 AB 1234",
                               "attrs": {"colour": "red", "make": "Pulsar"},
                               "edges": [{"type": "used_vehicle", "from": {"type": "crime", "key": "ADY-1182-2026"}}]}],
                             source="Extractor")
    ctx = world_model.context(["ADY-1182-2026", "VEL-0877-2026"])

Entity dict: `type` (crime|person|vehicle|place|phone|evidence|series), `key` (plate, FIR id,
H3 cell, phone, name...; `name` is accepted as an alias), optional `attrs`, optional
`edges`: each `{"type": <edge type>, "to"|"from": {"type", "key"} | "<entity id>"}`.
`source` is the provenance (the writing agent or feed); it is required.
"""

from __future__ import annotations

from typing import Any

from app.engines import _runtime
from app.engines.world_model.core import EDGE_TYPES, ENTITY_TYPES, WorldStore, entity_id

__all__ = ["ingest", "context", "store", "reset", "ENTITY_TYPES", "EDGE_TYPES", "entity_id"]

ENGINE = "world_model"
DEFAULT_CONTEXT_BUDGET = 40

_store = WorldStore()


def _sidecar_call(path: str, payload: dict) -> dict:
    from app.engines import _sidecar

    return _sidecar.call(path, payload)


def store() -> WorldStore:
    """The current store: in-process (sample), or a snapshot view of the TypeScript engine (sidecar)."""
    if _runtime.backend() == "sidecar":
        return WorldStore.from_snapshot(_sidecar_call("world_model/snapshot", {}))
    return _store


def reset() -> None:
    """Drop all state (tests and sample runs start clean)."""
    global _store
    _store = WorldStore()
    if _runtime.backend() == "sidecar":
        _sidecar_call("world_model/reset", {})


def _key_of(ent: dict[str, Any]) -> str:
    key = ent.get("key", ent.get("name"))
    if key is None or str(key).strip() == "":
        raise ValueError(f"entity needs a key or name: {ent!r}")
    return str(key)


def _endpoint(ref: Any, source: str) -> str:
    if isinstance(ref, str):
        return ref
    if isinstance(ref, dict):
        return _store.upsert(ref["type"], _key_of(ref), ref.get("attrs") or {}, source)
    raise ValueError(f"edge endpoint must be an entity id or a {{type, key}} dict, got {ref!r}")


def _counts(s: WorldStore) -> tuple[int, int, int]:
    return len(s.entities), len(s.edges), sum(len(e.provenance) for e in s.entities.values())


def ingest(entities: list[dict], source: str) -> list[str]:
    """Upsert entities (and their edges). Idempotent; returns stable ids in input order."""
    if not source or not str(source).strip():
        raise ValueError("World Model: every write carries provenance. No provenance, no write.")
    for e in entities:
        _key_of(e)
    before = _counts(store())
    if _runtime.backend() == "sidecar":
        ids = _sidecar_call("world_model/ingest", {"entities": entities, "source": source})["ids"]
    else:
        ids = [_store.upsert(e["type"], _key_of(e), e.get("attrs") or {}, source) for e in entities]
        for eid, ent in zip(ids, entities):
            for edge in ent.get("edges") or []:
                if "to" in edge:
                    _store.relate(eid, edge["type"], _endpoint(edge["to"], source), source)
                elif "from" in edge:
                    _store.relate(_endpoint(edge["from"], source), edge["type"], eid, source)
                else:
                    raise ValueError(f"edge needs 'to' or 'from': {edge!r}")
    after = _counts(store())
    _runtime.emit(ENGINE, "ingest", f"{len(entities)} entities from {source}",
                  f"{len(set(ids))} entities; +{after[0] - before[0]} new entities, +{after[1] - before[1]} edges, "
                  f"+{after[2] - before[2]} observations")
    return ids


def context(crime_ids: list[str], budget: int = DEFAULT_CONTEXT_BUDGET) -> dict:
    """Entities, relations and provenance around the given crimes, at most `budget` entities, with reasons."""
    out = store().context(list(crime_ids), budget)
    _runtime.emit(
        ENGINE, "context", f"crimes {', '.join(crime_ids)[:200]}",
        f"{len(out['entities'])} entities, {len(out['relations'])} relations; missing {len(out['missing'])}",
    )
    return out
