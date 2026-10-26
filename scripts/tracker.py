"""Update engg/docs/workstreams.json. The "updated" time always comes from the clock, never typed.

    python scripts/tracker.py set WS1-05 done --note "Zetaris running; verify.sh 9/9"
    python scripts/tracker.py set WS2-06 in_progress --ref "#7"
    python scripts/tracker.py touch          # just stamp the current time
    python scripts/tracker.py list           # show every task and status
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRACKER = Path(__file__).resolve().parents[1] / "engg" / "docs" / "workstreams.json"
IST = timezone(timedelta(hours=5, minutes=30))
STATUSES = ("done", "in_progress", "blocked", "todo", "cut")


def now_ist() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def load() -> dict:
    return json.loads(TRACKER.read_text(encoding="utf-8"))


def save(data: dict) -> None:
    data["updated"] = now_ist()
    TRACKER.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"saved; updated = {data['updated']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("task_id")
    s.add_argument("status", choices=STATUSES)
    s.add_argument("--note")
    s.add_argument("--ref")
    sub.add_parser("touch")
    sub.add_parser("list")
    args = ap.parse_args()

    data = load()
    if args.cmd == "list":
        for ws in data["workstreams"]:
            for t in ws["tasks"]:
                print(f"{t['id']:7} {t['phase']:4} {t['status']:12} {t['title']}")
        return 0
    if args.cmd == "set":
        task = next((t for ws in data["workstreams"] for t in ws["tasks"] if t["id"] == args.task_id), None)
        if task is None:
            raise SystemExit(f"unknown task {args.task_id}")
        task["status"] = args.status
        if args.note is not None:
            task["note"] = args.note
        if args.ref is not None:
            task["ref"] = args.ref
    save(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
