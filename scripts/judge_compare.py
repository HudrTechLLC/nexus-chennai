"""WS5-12: compare offline /run outputs with the committed output_examples (CI job judge-offline).

The gate is EXACT: the whole response must equal output_examples/example_N.json after removing only the
per-run values, execution_time_seconds (wall clock) and every Zetaris query_id (a fresh UUID per query by
design: it is the audit id an alert card cites). run_id, trace_id and log_file come from the input, so they
must match too. A stable-field summary (status, summary, alert pairs, bands, scores, series, hotspots) is
printed alongside to make a failure easy to read.

Usage: python scripts/judge_compare.py <repo> <dir with got_N.json>
"""
import json
import sys
from pathlib import Path

repo, got_dir = Path(sys.argv[1]), Path(sys.argv[2])
PER_RUN = {"execution_time_seconds", "query_id"}


def norm(v):
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items() if k not in PER_RUN}
    if isinstance(v, list):
        return [norm(x) for x in v]
    return v


def stable(d):
    o = d["output"]
    return {
        "status": d["status"],
        "summary": o.get("summary"),
        "alerts": sorted((tuple(a["crimes"]), a["band"], a["score"], tuple(a.get("stations") or []), a["kind"])
                         for a in o.get("alerts") or []),
        "series": sorted(json.dumps(s, sort_keys=True) for s in o.get("series") or []),
        "hotspots": sorted(json.dumps(h, sort_keys=True) for h in o.get("hotspots") or []),
    }


def diffs(a, b, path=""):
    if type(a) is not type(b):
        yield f"{path}: {a!r:.80} != {b!r:.80}"
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            yield from diffs(a.get(k), b.get(k), f"{path}.{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            yield f"{path}: {len(a)} items != {len(b)}"
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                yield from diffs(x, y, f"{path}[{i}]")
    elif a != b:
        yield f"{path}: {a!r:.80} != {b!r:.80}"


ok = True
for n in (1, 2, 3):
    want = json.loads((repo / "output_examples" / f"example_{n}.json").read_text(encoding="utf-8"))
    got = json.loads((got_dir / f"got_{n}.json").read_text(encoding="utf-8"))
    exact = norm(want) == norm(got)
    ok &= exact
    print(f"example_{n}: {'EXACT' if exact else 'DIFF'} (stable fields {'match' if stable(want) == stable(got) else 'DIFFER'}) "
          f"status={got['status']} alerts={len(got['output'].get('alerts') or [])} t={got.get('execution_time_seconds')}s"
          f" | {got['output'].get('summary', '')[:90]}")
    for line in list(diffs(norm(want), norm(got)))[:15]:
        print("   " + line)
sys.exit(0 if ok else 1)
