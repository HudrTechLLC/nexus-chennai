"""Extractor backfill (spec P3 "batch backfill job for all crimes").

    python -m app.graph.backfill --ids CHN-AD-2026-001182,CHN-VL-2026-000877
    python -m app.graph.backfill --priority-file ids.txt --all --concurrency 4

- Reads each case through Zetaris (`q_case`, R1) and runs the Extractor live on Nightshift (R2).
- Writes `crime_features` to Supabase and appends the same record (model + receipt id) to
  `data/sample/crime_features.jsonl`, so sample mode has real extracted MO without re-running
  the model (R3/R6; the JSONL path was granted to this lane by nexus-1).
- Resumable: ids already in the JSONL, or already extracted in Supabase by this extractor version, are
  skipped. One failing case never stops the batch.
- `--export-jsonl` rebuilds the JSONL from Supabase `crime_features` (after a re-seed remaps crime ids):
  the local-only fields (routed_model, degraded) are joined back by receipt_id, which survives a remap.
- `--all` lists crime ids from Supabase `crimes` (ids only, for orchestration; agents still
  read case content only through Zetaris).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .. import engines as default_engines
from ..adapters.nightshift import NightshiftClient
from ..adapters.supabase import SupabaseClient
from ..adapters.zetaris import ZetarisClient
from ..config import REPO_ROOT, Settings, get_settings
from ..tracing import Tracer, new_run_id
from ..agents.base import AgentDeps, AgentError, MemoryStore, crime_from_row, features_from_row
from ..agents.extractor import COMPATIBLE_VERSIONS, Extractor

DEFAULT_JSONL = REPO_ROOT / "data" / "sample" / "crime_features.jsonl"
JSONL_FIELDS = ("crime_id", "extractor_version", "model", "routed_model", "receipt_id", "mo", "visual_tags",
                "entities", "confidence", "degraded", "synthetic")


def done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.add(json.loads(line)["crime_id"])
            except (ValueError, KeyError):
                continue
    return out


def all_crime_ids(sb: SupabaseClient, page: int = 1000) -> list[str]:
    ids: list[str] = []
    offset = 0
    while True:
        rows = sb.select("crimes", {"select": "crime_id", "order": "crime_id.asc", "limit": str(page),
                                    "offset": str(offset)})
        ids += [r["crime_id"] for r in rows]
        if len(rows) < page:
            return ids
        offset += page


def _paged(sb: SupabaseClient, table: str, params: dict[str, str], page: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    while True:
        got = sb.select(table, {**params, "limit": str(page), "offset": str(len(rows))})
        rows += got
        if len(got) < page:
            return rows


def stored_ids(sb: SupabaseClient) -> set[str]:
    """Crimes already extracted by a compatible extractor version with a model receipt (a model call happened)."""
    return {r["crime_id"] for r in _paged(sb, "crime_features", {
        "select": "crime_id", "extractor_version": f"in.({','.join(COMPATIBLE_VERSIONS)})", "receipt_id": "not.is.null",
        "order": "crime_id.asc"})}


def export_jsonl(sb: SupabaseClient, path: Path) -> int:
    """Rewrite the JSONL from Supabase rows; routed_model/degraded come from the old file by receipt_id."""
    local: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("receipt_id"):
                local[rec["receipt_id"]] = rec
    rows = _paged(sb, "crime_features", {
        "select": "crime_id,extractor_version,model,receipt_id,mo,visual_tags,entities,confidence,synthetic",
        "extractor_version": f"in.({','.join(COMPATIBLE_VERSIONS)})", "receipt_id": "not.is.null", "order": "crime_id.asc"})
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            old = local.get(r["receipt_id"], {})
            rec = {**r, "routed_model": old.get("routed_model"), "degraded": old.get("degraded")}
            fh.write(json.dumps({k: rec.get(k) for k in JSONL_FIELDS}, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return len(rows)


class Backfill:
    def __init__(self, settings: Settings, jsonl: Path, store: Any = None, zetaris: Any = None,
                 nightshift: Any = None, tracer: Tracer | None = None, engines: Any = default_engines) -> None:
        self.tracer = tracer or Tracer(new_run_id("backfill"), settings.logs_dir, echo=False)
        self.zetaris = zetaris or ZetarisClient(settings, self.tracer)
        self.nightshift = nightshift or NightshiftClient(settings, self.tracer)
        self.store = store or MemoryStore()
        self.jsonl = jsonl
        self._lock = threading.Lock()
        # engines: the Extractor's World Model ingest (and _persist.world with ENGINES_PERSIST=supabase)
        # is skipped when deps.engines is None; that is how wm_* stayed empty (nexus-6 / nexus-2, 26 Oct).
        self.engines = engines
        self.deps = AgentDeps(tracer=self.tracer, zetaris=self.zetaris, nightshift=self.nightshift, store=self.store,
                              engines=engines)

    def _traced(self):
        use = getattr(self.engines, "use_tracer", None)
        return use(self.tracer) if use else contextlib.nullcontext()

    def one(self, crime_id: str) -> dict[str, Any]:
        rows, _ = self.deps.query("q_case", agent="Extractor", crime_id=crime_id)
        if not rows:
            raise AgentError(f"case {crime_id} not found")
        with self._traced():
            feats = Extractor(self.deps).extract_case(crime_from_row(rows[0]), write=False)
        self.store.upsert_features(feats)
        with self._lock:
            self.jsonl.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({k: feats.get(k) for k in JSONL_FIELDS}, ensure_ascii=False) + "\n")
        return feats

    def replay_world(self, crime_id: str) -> None:
        """World Model ingest from STORED features (no model call): for crimes extracted before the fix."""
        rows, _ = self.deps.query("q_case", agent="Extractor", crime_id=crime_id)
        frows, _ = self.deps.query("q_features", agent="Extractor", ids=crime_id)
        if not rows or not frows:
            raise AgentError(f"case or features missing for {crime_id}")
        with self._traced():
            Extractor(self.deps)._ingest_world_model(crime_from_row(rows[0]), features_from_row(frows[0]))

    def replay(self, ids: list[str], concurrency: int = 4) -> dict[str, Any]:
        ok, failed = 0, []
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {pool.submit(self.replay_world, cid): cid for cid in dict.fromkeys(ids)}
            for fut in as_completed(futures):
                try:
                    fut.result()
                    ok += 1
                except Exception as exc:
                    failed.append((futures[fut], str(exc)[:200]))
        return {"requested": len(ids), "ok": ok, "failed": failed, "run_id": self.tracer.run_id}

    def run(self, ids: list[str], concurrency: int = 4, skip_also: set[str] | None = None) -> dict[str, Any]:
        skip = done_ids(self.jsonl) | (skip_also or set())
        todo = [i for i in dict.fromkeys(ids) if i not in skip]
        ok, failed, started = 0, [], time.perf_counter()
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {pool.submit(self.one, cid): cid for cid in todo}
            for n, fut in enumerate(as_completed(futures), start=1):
                cid = futures[fut]
                try:
                    fut.result()
                    ok += 1
                except Exception as exc:
                    failed.append((cid, str(exc)[:200]))
                    self.tracer.emit("Extractor", "backfill_failed", input_summary=cid, output_summary=str(exc)[:300],
                                     status="error")
                if n % 10 == 0 or n == len(todo):
                    rate = (time.perf_counter() - started) / n
                    print(f"{n}/{len(todo)} done ({ok} ok, {len(failed)} failed), {rate:.1f}s/case, "
                          f"~{rate * (len(todo) - n) / 60:.0f} min left", flush=True)
        return {"requested": len(ids), "skipped": len(ids) - len(todo), "ok": ok, "failed": failed,
                "seconds": round(time.perf_counter() - started, 1), "run_id": self.tracer.run_id}


def main() -> int:
    ap = argparse.ArgumentParser(description="Extractor backfill over crimes (live Nightshift)")
    ap.add_argument("--ids", default="", help="comma-separated crime ids (processed first)")
    ap.add_argument("--priority-file", type=Path, help="file with one crime id per line (processed first)")
    ap.add_argument("--all", action="store_true", help="then every crime id in Supabase")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    ap.add_argument("--no-supabase", action="store_true", help="write only the JSONL")
    ap.add_argument("--export-jsonl", action="store_true", help="rebuild the JSONL from Supabase, then exit")
    ap.add_argument("--wm-replay", action="store_true",
                    help="World Model ingest for already-extracted crimes (stored features, no model calls), then exit")
    args = ap.parse_args()

    s = get_settings()
    sb = SupabaseClient(s)
    if args.export_jsonl:
        print(json.dumps({"exported": export_jsonl(sb, args.jsonl), "jsonl": str(args.jsonl)}), flush=True)
        return 0
    if args.wm_replay:
        tracer = Tracer(new_run_id("wmreplay"), s.logs_dir, echo=False)
        ids = [i.strip() for i in args.ids.split(",") if i.strip()] or sorted(stored_ids(sb))
        out = Backfill(s, args.jsonl, tracer=tracer).replay(ids, args.concurrency)
        print(json.dumps({k: v for k, v in out.items() if k != "failed"}), flush=True)
        for cid, err in out["failed"][:20]:
            print(f"FAILED {cid}: {err}", flush=True)
        return 0 if not out["failed"] else 1
    ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    if args.priority_file:
        ids += [line.strip() for line in args.priority_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.all:
        ids += all_crime_ids(sb)
    if args.limit:
        ids = ids[: args.limit]
    from .store import SupabaseStore
    tracer = Tracer(new_run_id("backfill"), s.logs_dir, echo=False)
    store = SupabaseStore(sb, tracer) if (sb.configured and not args.no_supabase) else MemoryStore()
    skip = stored_ids(sb) if isinstance(store, SupabaseStore) else set()
    out = Backfill(s, args.jsonl, store=store, tracer=tracer).run(ids, args.concurrency, skip_also=skip)
    print(json.dumps({k: v for k, v in out.items() if k != "failed"}), flush=True)
    for cid, err in out["failed"][:20]:
        print(f"FAILED {cid}: {err}", flush=True)
    return 0 if not out["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
