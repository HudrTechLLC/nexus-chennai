"""H-MEM, in-process backend (Python port of the Meterless reference).

Follows engines-ts/hmem/reference/src/{embeddings,memoryStore,memoryRetrieval,trustLedger}.ts
(Meterless @1742dec, Apache-2.0):

- deterministic embedder: FNV-1a per token into 64 dims, signed, L2-normalised;
- hybrid score: raw = 0.35*semantic + 0.20*keyword + 0.10*tag + 0.10*domain + 0.15*entity
  + 0.05*layer + 0.05*recency - 0.20*superseded; score = clamp01(raw) * confidence;
  threshold 0.35 on the final score, top 5;
- feedback deltas: helpful +0.05, not_helpful -0.03, wrong -0.20;
- append-only trust ledger (ledger.jsonl) and a state file (state.json) in one directory,
  so a new instance over the same directory continues the previous session.

Mining, sleep cycle, dreaming and conflict detection are not ported: Nexus feeds
memories from analyst decisions directly (spec E4), and the TypeScript reference
(sidecar backend) carries those services for the conformance suite.
"""

from __future__ import annotations

import copy
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Callable

FEEDBACK_DELTAS = {"helpful": 0.05, "not_helpful": -0.03, "wrong": -0.2}
RETRIEVAL_TOP_N = 5
RETRIEVAL_THRESHOLD = 0.35
ENTITY_CAP = 10
RELATED_CAP = 5
RECENCY_DAYS = 14
DAY_MS = 24 * 60 * 60 * 1000
DIM = 64
LAYER_WEIGHT = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}

TECH_TERMS = [
    "react", "python", "typescript", "javascript", "rust", "sqlite", "postgres", "indexeddb",
    "node", "docker", "graphql", "redis", "webrtc", "tauri", "electron", "llm", "embedding",
]
DOMAIN_KEYWORDS = {
    "tech": ["code", "bug", "api", "database", "deploy", "framework", "library", "server", *TECH_TERMS],
    "work": ["meeting", "deadline", "client", "project", "sprint", "review", "report"],
    "personal": ["family", "hobby", "prefer", "like", "dislike", "morning", "evening"],
}
_CAPITALISED = re.compile(r"\b([A-Z][a-zA-Z]{2,})\b")
_CORRECTION = re.compile(r"\b(actually|instead|no longer|not anymore|changed to|correction)\b", re.I)


def clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return [t for t in cleaned.split() if len(t) > 1]


def _fnv1a(s: str) -> int:
    h = 0x811C9DC5
    for unit in _utf16_units(s):  # JS charCodeAt walks UTF-16 code units
        h ^= unit
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def _utf16_units(s: str) -> list[int]:
    data = s.encode("utf-16-le")
    return [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]


def embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for token in tokenize(text):
        h = _fnv1a(token)
        idx = h % DIM
        sign = 1 if (h >> 8) % 2 == 0 else -1
        mag = 1 + ((h >> 16) % 8) / 8
        vec[idx] += sign * mag
    norm = math.sqrt(sum(v * v for v in vec))
    return vec if norm == 0 else [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def jaccard(a, b) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / (len(sa) + len(sb) - inter)


def _snapshot(rec: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(rec)
    out.pop("embedding", None)
    return out


class TrustLedger:
    """Append-only; entries are never mutated or deleted."""

    def __init__(self, clock: Callable[[], int], persist_dir: Path | None) -> None:
        self.clock = clock
        self.entries: list[dict[str, Any]] = []
        self.file = persist_dir / "ledger.jsonl" if persist_dir else None
        if self.file and self.file.exists():
            self.entries = [json.loads(line) for line in self.file.read_text(encoding="utf-8").splitlines() if line]

    def log(self, memory_id: str, action: str, actor: str, **extra: Any) -> dict[str, Any]:
        entry = {"memoryId": memory_id, "action": action, "actor": actor, "timestamp": self.clock(),
                 **{k: v for k, v in extra.items() if v is not None}}
        self.entries.append(entry)
        if self.file:
            with self.file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        return [e for e in self.entries if e["memoryId"] == memory_id]


class HMEM:
    def __init__(self, persist_dir: str | Path | None = None, clock: Callable[[], int] | None = None,
                 actor: str = "system") -> None:
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.actor = actor
        self.dir = Path(persist_dir) if persist_dir else None
        if self.dir:
            self.dir.mkdir(parents=True, exist_ok=True)
        self.ledger = TrustLedger(self.clock, self.dir)
        self.records: dict[str, dict[str, Any]] = {}
        self.seq = 0
        self.state_file = self.dir / "state.json" if self.dir else None
        if self.state_file and self.state_file.exists():
            saved = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.seq = saved["seq"]
            self.records = {r["id"]: r for r in saved["records"]}

    # ------------------------------------------------------------ store
    def persist(self) -> None:
        if not self.state_file:
            return
        records = sorted(self.records.values(), key=lambda r: r["id"])
        self.state_file.write_text(json.dumps({"seq": self.seq, "records": records}, indent=2) + "\n",
                                   encoding="utf-8")

    def classify_domain(self, content: str, tags: list[str], type_: str) -> str:
        for t in tags:
            if t.startswith("project:"):
                return t[len("project:"):]
            if t.startswith("tech:"):
                return "tech"
        tokens = set(tokenize(content))
        best, best_score = "general", 0
        for domain, kws in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in kws if kw in tokens)
            if domain == "personal" and type_ in ("personal", "preference"):
                score += 1
            if score > best_score:
                best, best_score = domain, score
        return best if best_score > 0 else "general"

    def extract_entities(self, content: str) -> list[str]:
        ents: dict[str, None] = {}
        for t in tokenize(content):
            if t in TECH_TERMS:
                ents[t] = None
        for m in _CAPITALISED.finditer(content):
            norm = m.group(1).lower()
            if norm not in ("the", "this", "that", "with"):
                ents[norm] = None
        return list(ents)[:ENTITY_CAP]

    def add(self, content: str, source: str, *, type_: str = "general", layer: str = "working",
            tags: list[str] | None = None, confidence: float = 0.7, provenance: dict | None = None) -> dict[str, Any]:
        if not source or not source.strip():
            raise ValueError("H-MEM: a memory record with no source must be rejected by construction")
        now = self.clock()
        self.seq += 1
        tags = list(tags or [])
        domain = self.classify_domain(content, tags, type_)
        bucket = "profile" if type_ in ("preference", "personal") else "facts" if type_ == "factual" else "notes"
        rec: dict[str, Any] = {
            "id": f"mem-{self.seq}", "content": content, "type": type_, "layer": layer,
            "timestamp": now, "lastAccessed": now, "accessCount": 0, "tags": tags,
            "embedding": embed(content), "confidence": clamp01(confidence), "source": source,
            "provenance": provenance or {"origin": "manual", "learnedAt": now, "label": source},
            "domain": domain, "namespace": f"{domain}/{bucket}",
            "entities": self.extract_entities(content), "relatedTo": [], "supersedes": None, "supersededBy": None,
        }
        for other in self.records.values():
            if len(rec["relatedTo"]) >= RELATED_CAP:
                break
            sim = cosine(rec["embedding"], other["embedding"])
            if not rec["supersedes"] and sim > 0.85 and _CORRECTION.search(content):
                rec["supersedes"] = other["id"]
                continue
            if set(other["entities"]) & set(rec["entities"]) and other["domain"] == rec["domain"]:
                rec["relatedTo"].append(other["id"])
                if len(other["relatedTo"]) < RELATED_CAP and rec["id"] not in other["relatedTo"]:
                    other["relatedTo"].append(rec["id"])
        self.records[rec["id"]] = rec
        self.ledger.log(rec["id"], "create", self.actor, newState=_snapshot(rec))
        self.persist()
        return rec

    # -------------------------------------------------------- retrieval
    def _score(self, m: dict[str, Any], q_emb, q_tokens, q_entities, q_domain) -> float:
        semantic = clamp01(cosine(q_emb, m["embedding"]))
        keyword = jaccard(q_tokens, tokenize(m["content"]))
        tag = jaccard(q_tokens, [t.lower() for t in m["tags"]])
        domain = 1 if m["domain"] == q_domain else 0
        entity = jaccard(q_entities, m["entities"])
        layer = LAYER_WEIGHT[m["layer"]]
        age_days = (self.clock() - m["lastAccessed"]) / DAY_MS
        recency = math.exp(-age_days / RECENCY_DAYS)
        superseded = 1 if m.get("supersededBy") else 0
        raw = (0.35 * semantic + 0.2 * keyword + 0.1 * tag + 0.1 * domain + 0.15 * entity
               + 0.05 * layer + 0.05 * recency - 0.2 * superseded)
        return clamp01(raw) * m["confidence"]

    def query(self, text: str, top_n: int = RETRIEVAL_TOP_N, threshold: float = RETRIEVAL_THRESHOLD,
              where: Callable[[dict[str, Any]], bool] | None = None) -> list[tuple[dict[str, Any], float]]:
        q_emb, q_tokens = embed(text), tokenize(text)[:8]
        q_entities, q_domain = self.extract_entities(text), self.classify_domain(text, [], "general")
        scored = []
        for m in self.records.values():
            if where and not where(m):
                continue
            s = self._score(m, q_emb, q_tokens, q_entities, q_domain)
            if s >= threshold:
                scored.append((m, s))
        scored.sort(key=lambda t: (-t[1], t[0]["id"]))
        top = scored[:top_n]
        for m, _ in top:
            m["lastAccessed"] = self.clock()
            m["accessCount"] += 1
            self.ledger.log(m["id"], "read", self.actor, details={"query": text})
        if top:
            self.persist()
        return top

    def feedback(self, memory_id: str, kind: str) -> None:
        m = self.records.get(memory_id)
        if m is None:
            raise KeyError(f"H-MEM: unknown memory id {memory_id}")
        prev = _snapshot(m)
        if kind == "helpful":
            m["accessCount"] += 1
        m["confidence"] = clamp01(m["confidence"] + FEEDBACK_DELTAS[kind])
        if kind == "wrong" and "review" not in m["tags"]:
            m["tags"].append("review")
        self.ledger.log(memory_id, "feedback", self.actor, previousState=prev, newState=_snapshot(m),
                        details={"kind": kind, "delta": FEEDBACK_DELTAS[kind]})
        self.persist()
