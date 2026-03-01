"""
Automatic migration runner for Charm Email OS API.
Runs pending SQL migrations from the migrations/ directory on API startup.
"""

import asyncio
import logging
from pathlib import Path
from typing import Set

import asyncpg

logger = logging.getLogger(__name__)


async def get_applied_migrations(conn: asyncpg.Connection) -> Set[str]:
    """Get set of already applied migration names."""
    # Create migrations tracking table if it doesn't exist
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            name VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)

    rows = await conn.fetch("SELECT name FROM _migrations")
    return {row["name"] for row in rows}


async def run_single_migration(conn: asyncpg.Connection, migration_path: Path) -> bool:
    """Run a single migration file."""
    migration_name = migration_path.name

    try:
        sql = migration_path.read_text(encoding="utf-8")

        # Execute migration in a transaction
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO _migrations (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
                migration_name
            )

        logger.info(f"Applied migration: {migration_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to apply migration {migration_name}: {e}")
        return False


async def run_pending_migrations(pool: asyncpg.Pool) -> int:
    """
    Run all pending migrations.
    Returns the number of migrations applied.
    """
    # Find migrations directory (relative to api/)
    migrations_dir = Path(__file__).parent.parent / "migrations"

    if not migrations_dir.exists():
        logger.warning(f"Migrations directory not found: {migrations_dir}")
        return 0

    # Get all migration files sorted by number
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        logger.info("No migration files found")
        return 0

    async with pool.acquire() as conn:
        applied = await get_applied_migrations(conn)
        pending = [f for f in migration_files if f.name not in applied]

        if not pending:
            logger.info(f"All {len(applied)} migrations already applied")
            return 0

        logger.info(f"Found {len(pending)} pending migration(s)")

        applied_count = 0
        for migration_path in pending:
            if await run_single_migration(conn, migration_path):
                applied_count += 1
            else:
                # Stop on first failure
                logger.error("Stopping migrations due to failure")
                break

        return applied_count
