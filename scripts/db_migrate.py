"""Apply supabase/migrations/*.sql in order, once each, recording them in public.schema_migrations.

The password is read from an environment variable set for this one process only,
from a file, never typed inline:

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python scripts/db_migrate.py [--dry-run]

Connects through the Supabase session pooler (IPv4). Each migration runs in its own
transaction; a failure rolls that migration back and stops.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
PROJECT_REF = os.environ.get("NEXUS_SUPABASE_REF", "ukrujnsjucwvytnokbtw")
POOLER_HOSTS = [
    os.environ.get("NEXUS_DB_HOST", ""),
    "aws-0-ap-southeast-1.pooler.supabase.com",
    "aws-1-ap-southeast-1.pooler.supabase.com",
]


def connect() -> psycopg.Connection:
    password = os.environ.get("NEXUS_DB_PASSWORD")
    if not password:
        sys.exit("NEXUS_DB_PASSWORD is not set (read it from the password file for this command only)")
    last: Exception | None = None
    for host in [h for h in POOLER_HOSTS if h]:
        try:
            conn = psycopg.connect(
                host=host, port=5432, dbname="postgres", user=f"postgres.{PROJECT_REF}",
                password=password, sslmode="require", connect_timeout=15,
            )
            print(f"connected via {host}")
            return conn
        except psycopg.OperationalError as exc:
            last = exc
            print(f"could not connect via {host}: {str(exc).splitlines()[0]}")
    sys.exit(f"no pooler host worked: {last}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="list pending migrations without applying")
    args = ap.parse_args()

    files = sorted(MIGRATIONS.glob("*.sql"))
    with connect() as conn:
        conn.autocommit = True  # each migration gets its own explicit transaction below
        conn.execute(
            "create table if not exists public.schema_migrations "
            "(version text primary key, applied_at timestamptz not null default now())"
        )
        conn.execute("alter table public.schema_migrations enable row level security")
        conn.execute("revoke all on public.schema_migrations from anon, authenticated")
        done = {r[0] for r in conn.execute("select version from public.schema_migrations")}
        pending = [f for f in files if f.stem not in done]
        print(f"{len(done)} applied, {len(pending)} pending: {[f.name for f in pending]}")
        if args.dry_run:
            return 0
        for f in pending:
            print(f"applying {f.name} ...")
            try:
                with conn.transaction():
                    conn.execute("set local search_path = public, extensions")
                    conn.execute(f.read_text(encoding="utf-8"))
                    conn.execute("insert into public.schema_migrations (version) values (%s)", (f.stem,))
            except psycopg.Error as exc:
                print(f"FAILED {f.name}: {exc}")
                return 1
            print(f"applied {f.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
