"""WS5-12: compare offline /run outputs with the committed output_examples (CI job judge-offline).

Two checks per example:
  strict - the whole JSON after removing only execution_time_seconds (the one wall-clock field;
           run_id comes from the input, so trace_id / log_file are stable too)
  stable - status, summary, and per alert: crimes, band, score, stations, kind; plus series and hotspot ids
Usage: python scripts/judge_compare.py <repo> <dir with got_N.json>
Exit 1 when a stable field differs. A strict-only difference is printed but does not fail.
"""
import json
import sys
from pathlib import Path

repo, got_dir = Path(sys.argv[1]), Path(sys.argv[2])
VOLATILE = {"execution_time_seconds"}


def strip(d):
    return {k: v for k, v in d.items() if k not in VOLATILE}


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


ok = True
for n in (1, 2, 3):
    want = json.loads((repo / "output_examples" / f"example_{n}.json").read_text(encoding="utf-8"))
    got = json.loads((got_dir / f"got_{n}.json").read_text(encoding="utf-8"))
    s_ok = stable(want) == stable(got)
    x_ok = strip(want) == strip(got)
    ok &= s_ok
    print(f"example_{n}: stable={'MATCH' if s_ok else 'DIFF'} strict={'MATCH' if x_ok else 'DIFF'} "
          f"status={got['status']} alerts={len(got['output'].get('alerts') or [])} "
          f"t={got.get('execution_time_seconds')}s | {got['output'].get('summary', '')[:90]}")
    if not s_ok:
        for k in stable(want):
            if stable(want)[k] != stable(got)[k]:
                print(f"   {k}: want={stable(want)[k]!s:.300}\n   {k}:  got={stable(got)[k]!s:.300}")
    elif not x_ok:
        diff = [k for k in set(strip(want)) | set(strip(got)) if strip(want).get(k) != strip(got).get(k)]
        print(f"   strict differs only in: {diff}")
sys.exit(0 if ok else 1)
