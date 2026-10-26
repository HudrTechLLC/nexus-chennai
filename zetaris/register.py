"""Run zetaris/*.sql one statement at a time through the Zetaris REST API (spec E5, rule R12).

    python zetaris/register.py --dry-run                 # print every statement, secrets masked
    python zetaris/register.py --file 00_sources.sql     # run one file
    python zetaris/register.py --file 00_sources.sql --from 3   # resume at statement 3 (1-based)

File format
- A statement ends at a line whose last non-space character is `;` (stripped before sending).
- Full-line `--` comments are skipped.
- Placeholders:
    {{secret:NAME}}   value read from the file in SECRETS[NAME]; masked in every print and log
    {{city:a.b.0}}    value from cities/<CITY>/city.yaml by dotted path (list indices allowed)
    {{since}} {{until}}  ISO dates from --since/--until (default: 30 days before the generator end date)
- A statement that fails with "already exists" is reported and skipped, so re-runs are safe.
Every call is logged to logs/zetaris-register-<stamp>.jsonl with its secrets masked.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SECRETS = {  # name -> (file, line index)
    "zetaris_reader": ("~/.secrets/nexus-zetaris-reader.txt", 0),
    "s3_key_id": ("~/.secrets/nexus-s3.key", 0),
    "s3_secret": ("~/.secrets/nexus-s3.key", 1),
}
PH = re.compile(r"\{\{(secret|city):([A-Za-z0-9_.]+)\}\}|\{\{(since|until)\}\}")


def read_secret(name: str) -> str:
    path, idx = SECRETS[name]
    lines = [ln.strip() for ln in Path(os.path.expanduser(path)).read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines[idx]


def city_value(city: dict, dotted: str):
    v = city
    for part in dotted.split("."):
        v = v[int(part)] if isinstance(v, list) else v[part]
    return v


def statements(text: str) -> list[str]:
    out, cur = [], []
    for line in text.splitlines():
        if line.strip().startswith("--") and not cur:
            continue
        if line.strip().startswith("--"):
            continue
        cur.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(cur).rstrip()[:-1].strip()
            if stmt:
                out.append(stmt)
            cur = []
    if "".join(cur).strip():
        raise ValueError("last statement has no terminating ';'")
    return out


def fill(stmt: str, city: dict, since: str, until: str) -> tuple[str, str, list[str]]:
    """Returns (real sql, masked sql, secret values used)."""
    secrets: list[str] = []

    def sub(m: re.Match, masked: bool) -> str:
        kind, name, window = m.group(1), m.group(2), m.group(3)
        if window:
            return since if window == "since" else until
        if kind == "city":
            return str(city_value(city, name))
        val = read_secret(name)
        if not masked:
            secrets.append(val)
        return f"<secret:{name}>" if masked else val

    real = PH.sub(lambda m: sub(m, False), stmt)
    shown = PH.sub(lambda m: sub(m, True), stmt)
    return real, shown, secrets


def mask(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "<redacted>")
    return text


def run(sql: str, token: str, base: str, org: str, timeout: float) -> httpx.Response:
    return httpx.post(f"{base.rstrip('/')}/sql-editor/sqls/run",
                      headers={"Authorization": f"Bearer {token}", "X-Org-ID": org, "X-Request-ID": str(uuid.uuid4())},
                      json={"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": 200},
                      timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file", action="append", help="file name in zetaris/ (repeatable); default: all *.sql")
    ap.add_argument("--from", dest="start", type=int, default=1, help="1-based statement to start at (single file)")
    ap.add_argument("--only", type=int, help="run only this 1-based statement (single file)")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--timeout", type=float, default=600)
    a = ap.parse_args()

    city_name = os.environ.get("CITY", "chennai")
    city = yaml.safe_load((ROOT / "cities" / city_name / "city.yaml").read_text(encoding="utf-8"))
    gen = yaml.safe_load((ROOT / "cities" / city_name / "generator" / "config.yaml").read_text(encoding="utf-8"))
    end = date.fromisoformat(gen["end_date"])
    since, until = a.since or (end - timedelta(days=30)).isoformat(), a.until or end.isoformat()

    files = [HERE / f for f in a.file] if a.file else sorted(HERE.glob("*.sql"))
    token = ""
    if not a.dry_run:
        tf = os.environ.get("ZETARIS_API_KEY_FILE", "~/.secrets/nexus-zetaris.key")
        token = Path(os.path.expanduser(tf)).read_text(encoding="utf-8").strip()
    base = os.environ.get("ZETARIS_REST_URL", "http://localhost:8888/api/v1.0")
    org = os.environ.get("ZETARIS_ORG_ID", "1")
    (ROOT / "logs").mkdir(exist_ok=True)
    log = ROOT / "logs" / f"zetaris-register-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"

    failures = 0
    for f in files:
        stmts = statements(f.read_text(encoding="utf-8"))
        print(f"== {f.name}: {len(stmts)} statements")
        for i, stmt in enumerate(stmts, 1):
            if (a.only and i != a.only) or i < a.start:
                continue
            real, shown, secrets = fill(stmt, city, since, until)
            print(f"-- [{f.name} #{i}]\n{shown};")
            if a.dry_run:
                continue
            t0 = time.perf_counter()
            r = run(real, token, base, org, a.timeout)
            ms = int((time.perf_counter() - t0) * 1000)
            body = mask(r.text, secrets)
            ok = r.status_code == 200
            exists = (not ok) and "already exist" in body.lower()
            rows = None
            if ok:
                try:
                    rows = len(r.json().get("data") or [])
                except ValueError:
                    pass
            status = "ok" if ok else ("exists" if exists else "error")
            print(f"   -> {status} HTTP {r.status_code} {ms} ms" + (f" rows={rows}" if rows is not None else "")
                  + ("" if ok else f"\n   {body[:400]}"))
            with log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"file": f.name, "n": i, "sql": shown, "status": status, "http": r.status_code,
                                     "ms": ms, "rows": rows, "error": None if ok else body[:2000]}) + "\n")
            if status == "error":
                failures += 1
                print("stopping at the first error (fix, then resume with --from)")
                return 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
