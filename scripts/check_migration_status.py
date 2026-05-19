#!/usr/bin/env python3
"""
check_migration_status.py — read-only audit of migration state on the connected
CharmDB. Shows what's applied, what's pending, and a one-line summary per pending
file (extracted from the leading comment block).

Use this before ANY production deploy that includes new migrations, so you can
see exactly what will run against CharmDB on charm-api startup.

Usage
-----
    py scripts/check_migration_status.py [--show-applied]

This script is READ-ONLY. No DB writes.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Set, Tuple

# Add api/ to path so we can reuse the production connection config
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

import asyncpg  # noqa: E402

# Import settings from the production config so this script connects exactly
# the way charm-api would on startup. Falls back to env vars if config import
# fails (e.g. running outside the api/ venv).
try:
    from config import settings  # type: ignore
    DB_HOST = settings.POSTGRES_HOST
    DB_PORT = settings.POSTGRES_PORT
    DB_NAME = settings.POSTGRES_DB
    DB_USER = settings.POSTGRES_USER
    DB_PASS = settings.POSTGRES_PASSWORD
except Exception:
    DB_HOST = os.environ.get("POSTGRES_HOST", "postgres")
    DB_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
    DB_NAME = os.environ.get("POSTGRES_DB", "postgres")
    DB_USER = os.environ.get("POSTGRES_USER", "postgres")
    DB_PASS = os.environ.get("POSTGRES_PASSWORD", "localdevpassword")


MIGRATIONS_DIR = ROOT / "migrations"


def extract_summary(path: Path) -> str:
    """Pull the first non-empty comment line after the '-- Migration NNN: <title>' line."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return f"<unreadable: {e}>"

    # Find the title line
    title = ""
    for line in lines[:10]:
        stripped = line.strip()
        if stripped.startswith("-- Migration"):
            # "-- Migration 119: Anchor task comments to documents + revisions"
            after_colon = stripped.split(":", 1)
            if len(after_colon) == 2:
                title = after_colon[1].strip()
                break
    return title or "<no title comment>"


async def fetch_applied(conn: asyncpg.Connection) -> Set[str]:
    """Return the set of migration filenames recorded in _migrations."""
    # Don't create the table here — we want to see if production has it.
    exists = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '_migrations')"
    )
    if not exists:
        return set()
    rows = await conn.fetch("SELECT name FROM _migrations ORDER BY name")
    return {row["name"] for row in rows}


async def main(show_applied: bool) -> int:
    if not MIGRATIONS_DIR.exists():
        print(f"ERROR: migrations directory not found at {MIGRATIONS_DIR}", file=sys.stderr)
        return 1

    on_disk: List[Path] = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not on_disk:
        print("No migration files on disk.")
        return 0

    print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER}…")
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASS,
            ),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        print(f"ERROR: connection timed out after 10s — is {DB_HOST}:{DB_PORT} reachable?", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: connection failed — {e}", file=sys.stderr)
        return 2

    try:
        applied = await fetch_applied(conn)
    finally:
        await conn.close()

    on_disk_names = {p.name for p in on_disk}
    pending = [p for p in on_disk if p.name not in applied]
    missing_from_disk = sorted(n for n in applied if n not in on_disk_names)

    print()
    print(f"On disk:  {len(on_disk)} migration(s)")
    print(f"Applied:  {len(applied)} migration(s)")
    print(f"Pending:  {len(pending)} migration(s)")
    if missing_from_disk:
        print(f"WARNING:  {len(missing_from_disk)} migration(s) applied but missing from disk:")
        for name in missing_from_disk:
            print(f"  • {name}")
    print()

    if pending:
        print("PENDING — will run on next charm-api startup:")
        print("─" * 80)
        for path in pending:
            print(f"  {path.name}")
            print(f"      → {extract_summary(path)}")
        print()

    if show_applied and applied:
        print("APPLIED (most recent last):")
        print("─" * 80)
        for name in sorted(applied):
            on_disk_path = MIGRATIONS_DIR / name
            summary = extract_summary(on_disk_path) if on_disk_path.exists() else "<file gone>"
            print(f"  {name}")
            print(f"      → {summary}")
        print()

    if pending:
        print("Next charm-api deploy will execute the pending list above.")
        print("Review each file before deploying. Migrations run inside a transaction;")
        print("any failure rolls back that migration but doesn't reverse earlier ones.")
    else:
        print("CharmDB is up to date — no pending migrations.")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    parser.add_argument(
        "--show-applied",
        action="store_true",
        help="Also print the full list of already-applied migrations",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.show_applied)))
