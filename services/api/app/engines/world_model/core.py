"""World Model, in-process backend (Python port of the Meterless reference).

Follows engines-ts/world-model/reference/src/{stableIds,resolve,store,index}.ts
(Meterless @1742dec, Apache-2.0):

- stable ids: `normalizeName` = NFKD -> strip combining marks -> strip zero-width ->
  lowercase -> collapse whitespace; name-keyed ids are `ent_` + first 16 hex of
  sha256(f"{type}:{normalized}"); externally keyed ids use the literal grammar
  `type:system:id`; relationship ids are `rel_` + sha256(from|type|to|context|validFrom).
- resolution bands: similarity >= 0.85 auto-merges, [0.82, 0.85) queues for review.
- every write carries provenance; no provenance, no write.

Nexus mapping (spec E4): plates, phones, H3 cells, FIRs, evidence and series are
externally keyed (a plate one character off is a different vehicle, so it must never
go through name resolution). People are name-keyed and go through resolution.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

ENTITY_TYPES = ("crime", "person", "vehicle", "place", "phone", "evidence", "series")
EDGE_TYPES = ("involves", "used_vehicle", "seen_at", "described_as", "linked_to", "member_of")

# type -> external key system. Types not listed are name-keyed (resolution applies).
KEY_SYSTEMS = {
    "crime": "fir",
    "vehicle": "plate",
    "phone": "msisdn",
    "place": "h3",
    "evidence": "evidence",
    "series": "series",
}

AUTO_MERGE_AT = 0.85
REVIEW_LOWER = 0.82

# --------------------------------------------------------------------------- ids

_ZERO_WIDTH = re.compile("[​-‍﻿]")
_WS = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not ("̀" <= ch <= "ͯ"))
    s = _ZERO_WIDTH.sub("", s)
    return _WS.sub(" ", s.lower()).strip()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    """Sorted keys, no whitespace, None members of dicts dropped (mirrors canonicalJson)."""
    if isinstance(value, dict):
        items = sorted((k, v) for k, v in value.items() if v is not None)
        return "{" + ",".join(json.dumps(k) + ":" + canonical_json(v) for k, v in items) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def entity_id_from_name(type_: str, name: str) -> str:
    return "ent_" + sha256_hex(f"{type_}:{normalize_name(name)}")[:16]


def external_id(type_: str, system: str, id_: str) -> str:
    return f"{type_}:{system}:{id_}"


def relationship_id(from_: str, type_: str, to: str, context: str | None = None, valid_from: str | None = None) -> str:
    return "rel_" + sha256_hex(f"{from_}|{type_}|{to}|{context or ''}|{valid_from or ''}")[:16]


def canonical_key(type_: str, key: str) -> str:
    """Normalise an external key so every writer spelling converges on one id."""
    key = str(key).strip()
    if type_ == "vehicle":
        return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKD", key).upper())
    if type_ == "phone":
        digits = re.sub(r"\D", "", key)
        return digits[-10:] if len(digits) >= 10 else digits
    if type_ == "place":
        return key.lower()
    return key


def entity_id(type_: str, key: str) -> str:
    if type_ not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type {type_!r}; expected one of {ENTITY_TYPES}")
    if type_ in KEY_SYSTEMS:
        ck = canonical_key(type_, key)
        if not ck:
            raise ValueError(f"empty key for {type_}")
        return external_id(type_, KEY_SYSTEMS[type_], ck)
    return entity_id_from_name(type_, key)


# ---------------------------------------------------------------- resolution


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = curr
    return prev[-1]


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    longest = max(len(na), len(nb))
    return 1.0 if longest == 0 else 1 - levenshtein(na, nb) / longest


def decide(similarity: float, auto_merge_at: float = AUTO_MERGE_AT, review_lower: float = REVIEW_LOWER) -> str:
    if similarity >= auto_merge_at:
        return "auto-merge"
    if similarity >= review_lower:
        return "review"
    return "new"


# --------------------------------------------------------------------- store


@dataclass
class Entity:
    id: str
    type: str
    key: str
    attrs: dict[str, Any] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "key": self.key,
            "attrs": dict(self.attrs),
            "aliases": list(self.aliases),
            "provenance": [dict(p) for p in self.provenance],
        }


@dataclass
class Edge:
    id: str
    from_id: str
    type: str
    to_id: str
    provenance: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "from": self.from_id, "type": self.type, "to": self.to_id,
                "provenance": [dict(p) for p in self.provenance]}


class WorldStore:
    """In-memory store: entities, edges and content-addressed observations."""

    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.edges: dict[str, Edge] = {}
        self.observations: dict[str, dict[str, Any]] = {}
        self.aliases: dict[str, str] = {}
        self.merge_queue: list[dict[str, Any]] = []

    # -- helpers
    def resolve(self, id_: str) -> str:
        seen = set()
        while id_ in self.aliases and id_ not in seen:
            seen.add(id_)
            id_ = self.aliases[id_]
        return id_

    def _observe(self, subject: str, source: str, payload: Any) -> tuple[str, bool]:
        obs_id = "obs_" + sha256_hex(f"{subject}|{source}|{canonical_json(payload)}")[:16]
        if obs_id in self.observations:
            return obs_id, False
        self.observations[obs_id] = {"id": obs_id, "subject": subject, "source": source, "payload": payload}
        return obs_id, True

    # -- writes
    def upsert(self, type_: str, key: str, attrs: dict[str, Any], source: str) -> str:
        if not source or not str(source).strip():
            raise ValueError("World Model: every write carries provenance. No provenance, no write.")
        attrs = {k: v for k, v in (attrs or {}).items() if v is not None}
        new_id = entity_id(type_, key)
        target = self.resolve(new_id)
        if type_ not in KEY_SYSTEMS and target not in self.entities:
            for other in self.entities.values():
                if other.type != type_ or other.id == target:
                    continue
                sim = name_similarity(key, other.key)
                verdict = decide(sim)
                if verdict == "auto-merge":
                    self.aliases[new_id] = other.id
                    target = other.id
                    break
                if verdict == "review" and not any(
                    {p["left"], p["right"]} == {new_id, other.id} for p in self.merge_queue
                ):
                    self.merge_queue.append({"left": new_id, "right": other.id, "similarity": round(sim, 3),
                                             "status": "pending"})
        obs_id, is_new = self._observe(target, source, {"type": type_, "key": key, "attrs": attrs})
        ent = self.entities.get(target)
        if ent is None:
            ent = Entity(id=target, type=type_, key=canonical_key(type_, key) if type_ in KEY_SYSTEMS else key)
            self.entities[target] = ent
        if is_new:
            ent.attrs.update(attrs)
            if key not in ent.aliases:
                ent.aliases.append(key)
            ent.provenance.append({"source": source, "observation_id": obs_id})
        return target

    def relate(self, from_id: str, type_: str, to_id: str, source: str) -> str:
        if type_ not in EDGE_TYPES:
            raise ValueError(f"unknown edge type {type_!r}; expected one of {EDGE_TYPES}")
        if not source:
            raise ValueError("World Model: every write carries provenance. No provenance, no write.")
        f, t = self.resolve(from_id), self.resolve(to_id)
        for end in (f, t):
            if end not in self.entities:
                raise KeyError(f"edge endpoint {end} does not exist")
        rid = relationship_id(f, type_, t)
        edge = self.edges.get(rid)
        if edge is None:
            edge = self.edges[rid] = Edge(rid, f, type_, t)
        obs_id, is_new = self._observe(rid, source, {"edge": [f, type_, t]})
        if is_new:
            edge.provenance.append({"source": source, "observation_id": obs_id})
        return rid

    # -- reads
    def state_canonical(self) -> str:
        """Canonical JSON of the whole state (for idempotency checks)."""
        return canonical_json({
            "entities": [e.as_dict() for e in sorted(self.entities.values(), key=lambda e: e.id)],
            "edges": [e.as_dict() for e in sorted(self.edges.values(), key=lambda e: e.id)],
            "aliases": self.aliases,
            "merge_queue": self.merge_queue,
        })

    def neighbours(self, id_: str) -> list[tuple[Edge, str]]:
        out = []
        for e in self.edges.values():
            if e.from_id == id_:
                out.append((e, e.to_id))
            elif e.to_id == id_:
                out.append((e, e.from_id))
        return out

    def context(self, crime_keys: list[str], budget: int) -> dict[str, Any]:
        """Selection with reasons: requested crimes, then shared neighbours, then direct ones."""
        requested = [self.resolve(entity_id("crime", c)) for c in crime_keys]
        found = [r for r in requested if r in self.entities]
        missing = [c for c, r in zip(crime_keys, requested) if r not in self.entities]
        reasons: dict[str, str] = {r: "requested crime" for r in found}
        touch: dict[str, set[str]] = {}
        rels: dict[str, Edge] = {}
        for crime in found:
            for edge, other in self.neighbours(crime):
                touch.setdefault(other, set()).add(crime)
                rels[edge.id] = edge
        shared = sorted((o for o, cs in touch.items() if len(cs) > 1 and o not in reasons),
                        key=lambda o: (-len(touch[o]), o))
        direct = sorted(o for o, cs in touch.items() if len(cs) == 1 and o not in reasons)
        for o in shared:
            reasons[o] = f"shared by {len(touch[o])} requested crimes"
        for o in direct:
            via = next(e.type for e in rels.values() if o in (e.from_id, e.to_id))
            reasons[o] = f"{via} of a requested crime"
        order = found + shared + direct
        chosen = order[:budget]
        chosen_set = set(chosen)
        entities = [self.entities[i].as_dict() for i in chosen]
        relations = [e.as_dict() for e in rels.values() if e.from_id in chosen_set and e.to_id in chosen_set]
        return {
            "entities": entities,
            "relations": sorted(relations, key=lambda r: r["id"]),
            "provenance": {i: [p["source"] for p in self.entities[i].provenance] for i in chosen},
            "selection": [{"id": i, "reason": reasons[i]} for i in chosen],
            "missing": missing,
            "truncated": len(order) > budget,
        }
