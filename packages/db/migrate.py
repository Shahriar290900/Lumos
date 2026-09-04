#!/usr/bin/env python3
"""
migrate.py — minimal forward/backward SQL migration runner for Lumos.

Deliberately small. Migrations are plain `.up.sql` / `.down.sql` pairs, applied
in filename order, each inside its own transaction, and recorded in
`schema_migrations`. There is no ORM and no DSL: the schema is the SQL file, and
what an external reviewer reads is what actually runs.

Usage
-----
    python packages/db/migrate.py up                 # apply all pending
    python packages/db/migrate.py down               # revert the latest applied
    python packages/db/migrate.py down --to 0000     # revert everything
    python packages/db/migrate.py status

Connection comes from $DATABASE_URL. There is no default and no fallback: a
missing variable is an error, not a silent connection to something unexpected
(ADR-012).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL is not set.\n"
            "Lumos never falls back to a default connection string — set it explicitly."
        )
    return url


def discover() -> list[tuple[str, Path, Path | None]]:
    """Return [(version, up_path, down_path|None)] sorted by version."""
    out = []
    for up in sorted(MIGRATIONS_DIR.glob("*.up.sql")):
        version = up.name[: -len(".up.sql")]
        down = up.with_name(f"{version}.down.sql")
        out.append((version, up, down if down.exists() else None))
    return out


def applied_versions(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'schema_migrations')"
        )
        if not cur.fetchone()[0]:
            return []
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        return [r[0] for r in cur.fetchall()]


def cmd_up(conn: psycopg.Connection) -> int:
    done = set(applied_versions(conn))
    pending = [(v, up) for v, up, _ in discover() if v not in done]
    if not pending:
        print("nothing to apply — schema is up to date")
        return 0
    for version, up in pending:
        print(f"applying   {version}")
        with conn.cursor() as cur:
            cur.execute(up.read_text(encoding="utf-8"))
        conn.commit()
        print(f"applied    {version}")
    return 0


def cmd_down(conn: psycopg.Connection, to: str | None) -> int:
    done = applied_versions(conn)
    if not done:
        print("nothing applied — nothing to revert")
        return 0
    downs = {v: d for v, _, d in discover()}
    # Revert newest first, stopping once we reach `to` (exclusive).
    targets = [v for v in reversed(done) if to is None or v > to]
    if to is None:
        targets = targets[:1]
    for version in targets:
        down = downs.get(version)
        if down is None:
            print(f"ERROR: no down migration for {version}", file=sys.stderr)
            return 1
        print(f"reverting  {version}")
        with conn.cursor() as cur:
            cur.execute(down.read_text(encoding="utf-8"))
        conn.commit()
        print(f"reverted   {version}")
    return 0


def cmd_status(conn: psycopg.Connection) -> int:
    done = set(applied_versions(conn))
    all_versions = discover()
    if not all_versions:
        print("no migrations found")
        return 0
    for version, _, down in all_versions:
        mark = "applied" if version in done else "pending"
        rev = "" if down else "   (no down migration)"
        print(f"  [{mark:<7}] {version}{rev}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("up")
    d = sub.add_parser("down")
    d.add_argument("--to", default=None,
                   help="revert every migration with a version greater than this")
    sub.add_parser("status")
    args = ap.parse_args()

    with psycopg.connect(database_url()) as conn:
        if args.command == "up":
            return cmd_up(conn)
        if args.command == "down":
            return cmd_down(conn, args.to)
        return cmd_status(conn)


if __name__ == "__main__":
    raise SystemExit(main())
