"""H-MEM facade (spec P4/E4): analyst decisions become bounded score adjustments.

    from app.engines import hmem
    hmem.record_decision("LA-913", "reject", "different_offenders", "one used a car", pair)
    adj = hmem.adjust(pair)   # {"delta": -0.04, "memory_ids": ["mem-1"], "reason": "..."}

`pair` describes the two crimes of a candidate link: `{"a": {...features}, "b": {...features}}`
(`left`/`right` or `crimes: [a, b]` also work). Ids, timestamps, coordinates and free text
are ignored; the MO features (crime type, area, entry method, vehicle, weapon, time band,
...) are what memories match on.

Rules:
- a decision becomes a memory tagged with its polarity (approve +1, reject -1, other 0),
  and reinforces earlier memories of the same pattern (same polarity: helpful,
  opposite: not_helpful), all written to the trust ledger;
- adjust() sums polarity x relevance x STEP over the retrieved memories and clamps the
  result to +-MAX_DELTA (0.08). The clamp is applied in code, always.

Shared memory across processes: the API scores pairs while the worker records analyst decisions, both
over the same directory (logs/hmem). Each backend reopens the store whenever state.json or ledger.jsonl
changed since it last loaded (one stat per call), so a decision written by the worker shapes the API's
very next score with no restart. record_decision holds a lock file for its read-modify-write, so two
writers never overwrite each other's records.
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from app.engines import _runtime
from app.engines.hmem.core import HMEM

__all__ = ["adjust", "record_decision", "configure", "instance", "pair_text", "MAX_DELTA", "STEP"]

ENGINE = "hmem"
MAX_DELTA = 0.08
STEP = 0.1
# An explicit analyst decision starts above the reference default (0.7): it is direct human input.
DECISION_CONFIDENCE = 0.8
POLARITY = {"approve": 1, "approved": 1, "confirm": 1, "reject": -1, "rejected": -1}

_IGNORED_KEY_PARTS = ("id", "_at", "date", "time_utc", "lat", "lon", "lng", "h3", "text", "narrative",
                      "summary", "note", "url", "synthetic", "score")

STORE_FILES = ("state.json", "ledger.jsonl")
LOCK_FILE = ".write.lock"
LOCK_WAIT_S = 10.0
LOCK_STALE_S = 30.0


def _fingerprint(persist_dir: Path | None) -> tuple:
    """(mtime_ns, size) of the store files; changes whenever another process writes them."""
    if persist_dir is None:
        return ()
    out: list[tuple[int, int] | None] = []
    for name in STORE_FILES:
        try:
            st = os.stat(persist_dir / name)
            out.append((st.st_mtime_ns, st.st_size))
        except FileNotFoundError:
            out.append(None)
    return tuple(out)


_dir_locks: dict[str, threading.RLock] = {}
_held = threading.local()  # per thread: {dir: depth}


@contextmanager
def _write_lock(persist_dir: Path | None) -> Iterator[None]:
    """Lock for a read-modify-write of the store, across processes (O_EXCL lock file; stale locks expire) and
    threads (an RLock per directory). Re-entrant in one thread: record_decision queries while holding it."""
    if persist_dir is None:
        yield
        return
    key = str(persist_dir)
    with _dir_locks.setdefault(key, threading.RLock()):
        depth = getattr(_held, "d", None)
        if depth is None:
            depth = _held.d = {}
        if depth.get(key):
            depth[key] += 1
            try:
                yield
            finally:
                depth[key] -= 1
            return
        with _file_lock(persist_dir):
            depth[key] = 1
            try:
                yield
            finally:
                depth[key] = 0


@contextmanager
def _file_lock(persist_dir: Path) -> Iterator[None]:
    persist_dir.mkdir(parents=True, exist_ok=True)
    lock = persist_dir / LOCK_FILE
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.stat(lock).st_mtime > LOCK_STALE_S:
                    os.remove(lock)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"H-MEM store {persist_dir} is locked by another writer")
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            os.remove(lock)
        except FileNotFoundError:
            pass


class _Shared:
    """Reopens the backend when another process changed the store files."""

    dir: Path | None
    _seen: tuple = ()

    def _open(self) -> None:  # pragma: no cover - each backend implements it
        raise NotImplementedError

    def _load(self) -> None:
        # A writer may be mid-append on the ledger: retry a half-written file briefly.
        for attempt in range(5):
            seen = _fingerprint(self.dir)
            try:
                self._open()
            except (json.JSONDecodeError, ValueError, KeyError, PermissionError):
                if attempt == 4:
                    raise
                time.sleep(0.05)
                continue
            self._seen = seen
            return

    def refresh(self) -> None:
        if _fingerprint(self.dir) != self._seen:
            self._load()

    def wrote(self) -> None:
        self._seen = _fingerprint(self.dir)


class _Local(_Shared):
    """Sample backend: the Python port in core.py."""

    def __init__(self, persist_dir, clock):
        self.dir = Path(persist_dir) if persist_dir else None
        self.clock = clock
        self._load()

    def _open(self) -> None:
        self.mem = HMEM(persist_dir=self.dir, clock=self.clock, actor="analyst")

    def query(self, text: str) -> list[tuple[str, list[str], float]]:
        # Not read-only: retrieval writes "read" ledger entries and rewrites state.json, so it takes the lock.
        with _write_lock(self.dir):
            self.refresh()
            out = [(m["id"], list(m["tags"]), s) for m, s in self.mem.query(text)]
            self.wrote()
        return out

    def add(self, content: str, source: str, tags: list[str], confidence: float, provenance: dict) -> str:
        out = self.mem.add(content, source=source, tags=tags, confidence=confidence, provenance=provenance)["id"]
        self.wrote()
        return out

    def feedback(self, memory_id: str, kind: str) -> None:
        self.mem.feedback(memory_id, kind)
        self.wrote()

    def ledger_entries(self) -> list[dict]:
        self.refresh()
        return list(self.mem.ledger.entries)

    def records(self) -> list[dict]:
        self.refresh()
        return [{k: v for k, v in r.items() if k != "embedding"} for r in self.mem.records.values()]


class _Sidecar(_Shared):
    """Sidecar backend: the vendored TypeScript HMEM (engines-ts/hmem/reference)."""

    def __init__(self, persist_dir, clock):
        from app.engines import _sidecar

        self.call = _sidecar.call
        self.dir = Path(persist_dir) if persist_dir else None
        self.clock = clock
        self._load()

    def _open(self) -> None:
        # hmem/open builds a new HMEM over the directory, which re-reads state.json and the ledger.
        self.call("hmem/open", {"dir": str(self.dir) if self.dir else None,
                                "now_ms": self.clock() if self.clock else None})

    def query(self, text: str) -> list[tuple[str, list[str], float]]:
        with _write_lock(self.dir):  # the TS query also writes the ledger and state
            self.refresh()
            hits = self.call("hmem/query", {"text": text})["hits"]
            self.wrote()
        return [(h["id"], h["tags"], float(h["relevance"])) for h in hits]

    def add(self, content: str, source: str, tags: list[str], confidence: float, provenance: dict) -> str:
        out = self.call("hmem/add", {"content": content, "source": source, "tags": tags,
                                     "confidence": confidence, "provenance": provenance})["id"]
        self.wrote()
        return out

    def feedback(self, memory_id: str, kind: str) -> None:
        self.call("hmem/feedback", {"id": memory_id, "kind": kind})
        self.wrote()

    def ledger_entries(self) -> list[dict]:
        self.refresh()
        return self.call("hmem/ledger", {})["entries"]

    def records(self) -> list[dict]:
        self.refresh()
        return self.call("hmem/records", {})["records"]


_instance: _Local | _Sidecar | None = None


def configure(persist_dir: str | Path | None = None, clock: Callable[[], int] | None = None) -> _Local | _Sidecar:
    """(Re)open the memory over `persist_dir` (default logs/hmem). A new call = a new session."""
    global _instance
    if persist_dir is None:
        from app.config import get_settings

        persist_dir = get_settings().logs_dir / "hmem"
    cls = _Sidecar if _runtime.backend() == "sidecar" else _Local
    _instance = cls(persist_dir, clock)
    return _instance


def instance() -> _Local | _Sidecar:
    want = _Sidecar if _runtime.backend() == "sidecar" else _Local
    return _instance if isinstance(_instance, want) else configure()


def _tag(tags: list[str], prefix: str, default: str = "") -> str:
    return next((t.split(":", 1)[1] for t in tags if t.startswith(prefix + ":")), default)


def _sides(pair: dict[str, Any]) -> tuple[dict, dict]:
    if "a" in pair and "b" in pair:
        return pair["a"], pair["b"]
    if "left" in pair and "right" in pair:
        return pair["left"], pair["right"]
    crimes = pair.get("crimes")
    if isinstance(crimes, list) and len(crimes) == 2:
        return crimes[0], crimes[1]
    raise ValueError("pair needs a/b, left/right or crimes=[a, b]")


def _features(side: dict[str, Any], prefix: str = "") -> list[str]:
    out: list[str] = []
    for key in sorted(side):
        k = key.lower()
        if any(part == k or k.endswith(part) or k.startswith(part + "_") for part in _IGNORED_KEY_PARTS):
            continue
        value = side[key]
        if isinstance(value, dict):
            out += _features(value, f"{prefix}{key}.")
        elif isinstance(value, (list, tuple)):
            out += [str(v) for v in value if isinstance(v, (str, int)) and not isinstance(v, bool)]
        elif isinstance(value, str) and value.strip():
            out.append(value.strip())
    return out


def pair_text(pair: dict[str, Any]) -> str:
    """Deterministic MO description of a pair: shared features first, then each side's own."""
    a, b = (_features(s) for s in _sides(pair))
    shared = [f for f in dict.fromkeys(a) if f in b]
    only_a = [f for f in dict.fromkeys(a) if f not in b]
    only_b = [f for f in dict.fromkeys(b) if f not in a]
    parts = [f"Shared: {', '.join(shared) or 'none'}."]
    if only_a or only_b:
        parts.append(f"Differs: {', '.join(only_a) or 'none'} versus {', '.join(only_b) or 'none'}.")
    return " ".join(parts)


def _clamp(x: float) -> float:
    return max(-MAX_DELTA, min(MAX_DELTA, x))


def adjust(pair: dict) -> dict:
    """Bounded score adjustment from memories similar to this pair."""
    query = pair_text(pair)
    raw, used, reasons = 0.0, [], []
    for mem_id, tags, relevance in instance().query(query):
        polarity = int(_tag(tags, "polarity", "0"))
        if polarity == 0:
            continue
        raw += polarity * relevance * STEP
        used.append(mem_id)
        reason = _tag(tags, "reason")
        reasons.append(f"{mem_id} {'approved' if polarity > 0 else 'rejected'}"
                       f"{' (' + reason + ')' if reason else ''} relevance {relevance:.2f}")
    out = {"delta": round(_clamp(raw), 3), "memory_ids": used,
           "reason": "; ".join(reasons) if reasons else "no similar analyst decisions in memory",
           "raw_delta": round(raw, 4)}
    _runtime.emit(ENGINE, "adjust", query[:200], f"delta {out['delta']:+.3f} from {len(used)} memories")
    return out


def record_decision(alert_id: str, decision: str, reason_code: str | None, note: str | None, pair: dict) -> None:
    """Store an analyst decision as a memory, reinforce similar ones, write the ledger."""
    decision = decision.lower().strip()
    polarity = POLARITY.get(decision, 0)
    # The memory content is the pattern itself, so later pairs match on MO, not on the
    # decision wording. Decision, reason and note travel in tags and provenance.
    content = pair_text(pair)
    tags = [f"decision:{decision}", f"polarity:{polarity}", f"alert:{alert_id}"]
    if reason_code:
        tags.append(f"reason:{reason_code}")
    mem = instance()
    reinforced = []
    with _write_lock(mem.dir):
        mem.refresh()  # inside the lock: build on every decision written so far, by any process
        if polarity:
            for mem_id, prior_tags, _ in mem.query(content):
                prior = int(_tag(prior_tags, "polarity", "0"))
                if prior:
                    mem.feedback(mem_id, "helpful" if prior == polarity else "not_helpful")
                    reinforced.append(mem_id)
        mem_id = mem.add(content, source=f"analyst-decision:{alert_id}", tags=tags,
                         confidence=DECISION_CONFIDENCE,
                         provenance={"origin": "analyst_decision", "alert_id": alert_id, "decision": decision,
                                     "reason_code": reason_code, "note": note})
    _runtime.emit(ENGINE, "record_decision", f"{alert_id} {decision} {reason_code or ''}".strip(),
                  f"memory {mem_id}; reinforced {len(reinforced)}")
    from app.engines import _persist

    _persist.hmem()
