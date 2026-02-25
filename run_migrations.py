#!/usr/bin/env python
"""
Migration runner for Charm Email OS.
Runs SQL migrations from the migrations/ directory against the configured PostgreSQL database.

Usage:
    python run_migrations.py              # Run all pending migrations
    python run_migrations.py --dry-run    # Show what would be run without executing
    python run_migrations.py --single 015 # Run only migration 015
"""

import asyncio
import os
import sys
import argparse
from pathlib import Path

# Add api directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "api"))

import asyncpg

# Load .env file if it exists
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


async def get_connection():
    """Create direct database connection using environment variables."""
    return await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


async def get_applied_migrations(conn: asyncpg.Connection) -> set:
    """Get list of already applied migrations."""
    # Create migrations tracking table if it doesn't exist
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            name VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)

    rows = await conn.fetch("SELECT name FROM _migrations")
    return {row["name"] for row in rows}


async def run_migration(conn: asyncpg.Connection, migration_path: Path, dry_run: bool = False):
    """Run a single migration file."""
    migration_name = migration_path.name
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Running migration: {migration_name}")

    sql = migration_path.read_text(encoding="utf-8")

    if dry_run:
        print(f"  Would execute:\n{sql[:500]}{'...' if len(sql) > 500 else ''}")
        return True

    try:
        # Execute migration in a transaction
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO _migrations (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
                migration_name
            )
        print(f"  [OK] Successfully applied: {migration_name}")
        return True
    except Exception as e:
        print(f"  [FAILED] {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be run without executing")
    parser.add_argument("--single", type=str, help="Run only a specific migration (e.g., 015)")
    parser.add_argument("--force", action="store_true", help="Re-run migrations even if already applied")
    args = parser.parse_args()

    # Find migrations directory
    migrations_dir = Path(__file__).parent / "migrations"
    if not migrations_dir.exists():
        print(f"Error: Migrations directory not found: {migrations_dir}")
        sys.exit(1)

    # Get all migration files sorted by number
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print("No migration files found.")
        sys.exit(0)

    # Filter to single migration if specified
    if args.single:
        migration_files = [f for f in migration_files if f.name.startswith(args.single)]
        if not migration_files:
            print(f"No migration found matching: {args.single}")
            sys.exit(1)

    print(f"Found {len(migration_files)} migration file(s)")
    print(f"Database: {os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', 'postgres')}")

    try:
        conn = await get_connection()
        print("[OK] Connected to database")
    except Exception as e:
        print(f"[FAILED] Could not connect to database: {e}")
        sys.exit(1)

    try:
        applied = await get_applied_migrations(conn)
        print(f"Already applied: {len(applied)} migrations")

        pending = [f for f in migration_files if f.name not in applied]

        if args.force:
            pending = migration_files
            print("Force mode: re-running all migrations")

        if not pending:
            print("\nNo pending migrations to run.")
            return

        print(f"\nPending migrations: {len(pending)}")
        for mf in pending:
            print(f"  - {mf.name}")

        success_count = 0
        fail_count = 0

        for migration_path in pending:
            if await run_migration(conn, migration_path, args.dry_run):
                success_count += 1
            else:
                fail_count += 1
                if not args.dry_run:
                    print("\nStopping due to failed migration.")
                    break

        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Summary: {success_count} succeeded, {fail_count} failed")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
