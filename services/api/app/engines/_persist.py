"""Write-through from the engines to Supabase (migration 0005_01_engines.sql, DECISIONS D-020).

Off by default. Enabled only with ENGINES_PERSIST=supabase, and then it needs SUPABASE_URL and the
service-role key (SUPABASE_SERVICE_ROLE_KEY_FILE, read by app.config). Works for both backends:
it reads the engine state through the facade (`world_model.store()`, `hmem.instance()`).

- World Model: after each ingest, the touched entities, their edges, the entities at the other
  end, and their observations (provenance) are upserted. Entities and edges merge (the engine's
  folded state wins); observations are append-only and insert-or-ignore.
- H-MEM: after each decision, all memories of the store are upserted, and ledger lines not yet
  sent are inserted (idempotent on entry_hash).

Every row is `synthetic: true` unless ENGINES_SYNTHETIC=false (all Nexus data is synthetic, R9).
Each sync emits one trace event (engine set, action "persist"). A failure is traced with status
"error" and re-raised: a silent gap between the engine and the console is worse than a loud one.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from app.engines import _runtime

_client: httpx.Client | None = None


def enabled() -> bool:
    return os.environ.get("ENGINES_PERSIST", "").strip().lower() == "supabase"


def synthetic() -> bool:
    return os.environ.get("ENGINES_SYNTHETIC", "true").strip().lower() != "false"


def set_client(client: httpx.Client | None) -> None:
    """Inject a client (tests use httpx.MockTransport)."""
    global _client
    _client = client


def _http() -> httpx.Client:
    global _client
    if _client is None:
        from app.config import get_settings

        s = get_settings()
        if not (s.supabase_url and s.supabase_service_role_key):
            raise RuntimeError("ENGINES_PERSIST=supabase needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY(_FILE)")
        key = s.supabase_service_role_key
        _client = httpx.Client(base_url=s.supabase_url.rstrip("/"), timeout=30, trust_env=False,
                               headers={"apikey": key, "Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json"})
    return _client


def _upsert(table: str, rows: list[dict[str, Any]], on_conflict: str, ignore: bool = False) -> int:
    if not rows:
        return 0
    resolution = "ignore-duplicates" if ignore else "merge-duplicates"
    resp = _http().post(f"/rest/v1/{table}", params={"on_conflict": on_conflict}, json=rows,
                        headers={"Prefer": f"resolution={resolution},return=minimal"})
    if resp.status_code >= 400:
        raise RuntimeError(f"engines persist {table}: HTTP {resp.status_code} {resp.text[:300]}")
    return len(rows)


# ------------------------------------------------------------------ World Model

def world(touched_ids: list[str]) -> dict[str, int] | None:
    if not enabled():
        return None
    from app.engines import world_model

    store = world_model.store()
    touched = {store.resolve(i) for i in touched_ids}
    edges = [e for e in store.edges.values() if e.from_id in touched or e.to_id in touched]
    ids = touched | {e.from_id for e in edges} | {e.to_id for e in edges}
    ents = [store.entities[i] for i in sorted(ids) if i in store.entities]
    by_id = {e.id: e for e in ents}
    syn = synthetic()

    def crime_of(edge) -> str | None:
        for end in (edge.from_id, edge.to_id):
            ent = by_id.get(end) or store.entities.get(end)
            if ent is not None and ent.type == "crime":
                return ent.key
        return None

    entity_rows = [{"id": e.id, "type": e.type, "key": e.key, "attrs": e.attrs, "aliases": e.aliases,
                    "synthetic": syn} for e in ents]
    edge_rows = [{"id": e.id, "from_id": e.from_id, "type": e.type, "to_id": e.to_id, "crime_id": crime_of(e),
                  "synthetic": syn} for e in sorted(edges, key=lambda x: x.id)]
    obs_rows = [{"id": p["observation_id"], "subject_id": s.id, "source": p["source"], "synthetic": syn}
                for s in [*ents, *edges] for p in s.provenance]
    return _traced("world", lambda: {
        "wm_entities": _upsert("wm_entities", entity_rows, "id"),
        "wm_edges": _upsert("wm_edges", edge_rows, "id"),
        "wm_observations": _upsert("wm_observations", obs_rows, "id", ignore=True),
    })


# ------------------------------------------------------------------------ H-MEM

_sent_ledger: dict[str, int] = {}


def _tag(tags: list[str], prefix: str) -> str | None:
    return next((t.split(":", 1)[1] for t in tags if t.startswith(prefix + ":")), None)


def hmem(store_name: str | None = None) -> dict[str, int] | None:
    if not enabled():
        return None
    store_name = store_name or os.environ.get("ENGINES_HMEM_STORE", "nexus")
    from app.engines import hmem as hmem_facade

    mem = hmem_facade.instance()
    syn = synthetic()
    memory_rows = []
    for r in mem.records():
        tags = list(r["tags"])
        prov = r.get("provenance") or {}
        polarity = _tag(tags, "polarity")
        memory_rows.append({
            "id": f"{store_name}:{r['id']}", "store": store_name, "memory_id": r["id"], "content": r["content"],
            "tags": tags, "confidence": round(float(r["confidence"]), 4), "layer": r["layer"],
            "decision": _tag(tags, "decision"), "polarity": int(polarity) if polarity is not None else None,
            "reason_code": _tag(tags, "reason"), "alert_id": _tag(tags, "alert"), "note": prov.get("note"),
            "synthetic": syn,
        })
    entries = mem.ledger_entries()
    start = _sent_ledger.get(store_name, 0)
    ledger_rows = []
    for e in entries[start:]:
        line = json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        ledger_rows.append({
            "store": store_name, "memory_id": e["memoryId"], "action": e["action"], "actor": e["actor"],
            "at": datetime.fromtimestamp(e["timestamp"] / 1000, tz=timezone.utc).isoformat(),
            "details": {k: v for k, v in e.items() if k not in ("memoryId", "action", "actor", "timestamp")},
            "entry_hash": hashlib.sha256(f"{store_name}|{line}".encode()).hexdigest(), "synthetic": syn,
        })
    out = _traced("hmem", lambda: {
        "hmem_memories": _upsert("hmem_memories", memory_rows, "id"),
        "hmem_ledger": _upsert("hmem_ledger", ledger_rows, "entry_hash", ignore=True),
    })
    _sent_ledger[store_name] = len(entries)
    return out


def reset() -> None:
    _sent_ledger.clear()


def _traced(engine_part: str, fn) -> dict[str, int]:
    engine = "world_model" if engine_part == "world" else "hmem"
    try:
        counts = fn()
    except Exception as exc:
        _runtime.emit(engine, "persist", "write-through to Supabase", str(exc)[:200], status="error")
        raise
    _runtime.emit(engine, "persist", "write-through to Supabase",
                  ", ".join(f"{k} {v}" for k, v in counts.items()))
    return counts
