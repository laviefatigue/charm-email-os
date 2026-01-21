"""
Database connection and utilities for Charm Email OS API
Uses asyncpg for async PostgreSQL queries
"""

import asyncio
import asyncpg
import json
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import logging

from config import settings

logger = logging.getLogger(__name__)

# Connection pool
_pool: Optional[asyncpg.Pool] = None

# Connection timeout in seconds
CONNECTION_TIMEOUT = 10.0


async def _init_connection(conn: asyncpg.Connection):
    """Initialize connection with JSONB codec for proper JSON handling"""
    await conn.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )
    await conn.set_type_codec(
        'json',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )


async def create_pool() -> asyncpg.Pool:
    """Create database connection pool with timeout to prevent hanging"""
    global _pool
    if _pool is None:
        try:
            # Wrap pool creation with timeout to prevent indefinite hanging
            _pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    host=settings.POSTGRES_HOST,
                    port=settings.POSTGRES_PORT,
                    database=settings.POSTGRES_DB,
                    user=settings.POSTGRES_USER,
                    password=settings.POSTGRES_PASSWORD,
                    min_size=1,
                    max_size=10,
                    command_timeout=60,
                    init=_init_connection,  # Set up JSONB codec for each connection
                ),
                timeout=CONNECTION_TIMEOUT
            )
            logger.info(f"Database pool created: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")
        except asyncio.TimeoutError:
            logger.error(f"Database connection timed out after {CONNECTION_TIMEOUT} seconds")
            raise
    return _pool


async def close_pool():
    """Close database connection pool"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def get_pool() -> asyncpg.Pool:
    """Get or create connection pool"""
    if _pool is None:
        await create_pool()
    return _pool


@asynccontextmanager
async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a database connection from the pool"""
    pool = await get_pool()
    async with pool.acquire() as connection:
        yield connection


async def fetch_all(query: str, *args) -> list[dict]:
    """Execute query and return all rows as dicts"""
    async with get_connection() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]


async def fetch_one(query: str, *args) -> Optional[dict]:
    """Execute query and return first row as dict"""
    async with get_connection() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def execute(query: str, *args) -> str:
    """Execute query and return status"""
    async with get_connection() as conn:
        return await conn.execute(query, *args)


async def execute_many(query: str, args_list: list) -> None:
    """Execute query for multiple sets of arguments"""
    async with get_connection() as conn:
        await conn.executemany(query, args_list)


async def health_check() -> bool:
    """Check database connectivity"""
    try:
        result = await fetch_one("SELECT 1 as ok")
        return result is not None and result.get("ok") == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def init_schema() -> None:
    """Initialize required tables and columns if they don't exist"""
    # Check if clients table exists and has the right columns
    check_table = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'clients'
        ) as table_exists;
    """
    result = await fetch_one(check_table)
    table_exists = result and result.get("table_exists", False)

    if not table_exists:
        # Create clients table from scratch
        create_clients_table = """
            CREATE TABLE clients (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,
                logo_url TEXT,
                onboarding_complete BOOLEAN DEFAULT FALSE,
                onboarding_data JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            CREATE INDEX idx_clients_workspace_id ON clients(workspace_id);
        """
        try:
            await execute(create_clients_table)
            logger.info("Created clients table")
        except Exception as e:
            logger.error(f"Failed to create clients table: {e}")
            return
    else:
        # Table exists - ensure all required columns exist
        columns_to_add = [
            ("workspace_id", "UUID REFERENCES workspaces(id) ON DELETE SET NULL"),
            ("logo_url", "TEXT"),
            ("onboarding_complete", "BOOLEAN DEFAULT FALSE"),
            ("onboarding_data", "JSONB"),
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            # Profile columns (Phase 1)
            ("contact_name", "VARCHAR(255)"),
            ("contact_email", "VARCHAR(255)"),
            ("website", "VARCHAR(255)"),
            ("industry", "VARCHAR(100)"),
            ("domain_pattern", "VARCHAR(255)"),
        ]

        for col_name, col_def in columns_to_add:
            check_col = f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'clients' AND column_name = '{col_name}'
                ) as col_exists;
            """
            col_result = await fetch_one(check_col)
            if col_result and not col_result.get("col_exists", False):
                try:
                    await execute(f"ALTER TABLE clients ADD COLUMN {col_name} {col_def}")
                    logger.info(f"Added column {col_name} to clients table")
                except Exception as e:
                    logger.error(f"Failed to add column {col_name}: {e}")

        # Create index if not exists
        try:
            await execute("CREATE INDEX IF NOT EXISTS idx_clients_workspace_id ON clients(workspace_id)")
        except Exception as e:
            logger.warning(f"Index creation note: {e}")

    logger.info("Database schema initialized (clients table ready)")

    # Initialize strategy generation tables (Phase 3)
    await _init_strategy_tables()

    # Initialize domain sourcing columns (Phase 3)
    await _init_domain_columns()


async def _init_strategy_tables() -> None:
    """Initialize strategy generation tables if they don't exist"""

    # Strategy generation jobs table
    create_jobs_table = """
        CREATE TABLE IF NOT EXISTS strategy_generation_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID NOT NULL REFERENCES clients(id),
            submission_id UUID,
            status VARCHAR(50) DEFAULT 'pending',
            generation_round INTEGER DEFAULT 1,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_jobs_status ON strategy_generation_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_strategy_jobs_client ON strategy_generation_jobs(client_id);
    """
    try:
        await execute(create_jobs_table)
        logger.info("Strategy generation jobs table ready")
    except Exception as e:
        logger.warning(f"Strategy jobs table note: {e}")

    # Strategy suggestions table
    create_suggestions_table = """
        CREATE TABLE IF NOT EXISTS strategy_suggestions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
            client_id UUID NOT NULL REFERENCES clients(id),
            variant_number INTEGER NOT NULL,
            subject_line TEXT NOT NULL,
            email_body TEXT NOT NULL,
            score INTEGER,
            rationale TEXT,
            used_variables JSONB,
            missing_variables JSONB,
            campaign_type VARCHAR(50),
            status VARCHAR(50) DEFAULT 'pending',
            human_comment TEXT,
            reviewed_by VARCHAR(255),
            reviewed_at TIMESTAMP,
            generation_round INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_suggestions_job ON strategy_suggestions(job_id);
        CREATE INDEX IF NOT EXISTS idx_suggestions_client ON strategy_suggestions(client_id);
        CREATE INDEX IF NOT EXISTS idx_suggestions_status ON strategy_suggestions(status);
    """
    try:
        await execute(create_suggestions_table)
        logger.info("Strategy suggestions table ready")
    except Exception as e:
        logger.warning(f"Strategy suggestions table note: {e}")

    # Strategy revision requests table
    create_revisions_table = """
        CREATE TABLE IF NOT EXISTS strategy_revision_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
            client_id UUID NOT NULL REFERENCES clients(id),
            variant_id UUID REFERENCES strategy_suggestions(id),
            instruction TEXT NOT NULL,
            processed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_revision_requests_job ON strategy_revision_requests(job_id);
        CREATE INDEX IF NOT EXISTS idx_revision_requests_client ON strategy_revision_requests(client_id);
    """
    try:
        await execute(create_revisions_table)
        logger.info("Strategy revision requests table ready")
    except Exception as e:
        logger.warning(f"Strategy revisions table note: {e}")


async def _init_domain_columns() -> None:
    """Initialize domain table columns for dual provider pricing"""

    # Check if domains table exists
    check_table = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'domains'
        ) as table_exists;
    """
    result = await fetch_one(check_table)
    if not result or not result.get("table_exists", False):
        logger.info("Domains table does not exist, skipping column initialization")
        return

    # Add dual provider pricing columns
    columns_to_add = [
        ("porkbun_price", "DECIMAL(10,2)"),
        ("porkbun_available", "BOOLEAN"),
        ("dynadot_price", "DECIMAL(10,2)"),
        ("dynadot_available", "BOOLEAN"),
        ("selected_provider", "VARCHAR(20)"),
        ("job_id", "UUID"),
    ]

    for col_name, col_def in columns_to_add:
        check_col = f"""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'domains' AND column_name = '{col_name}'
            ) as col_exists;
        """
        col_result = await fetch_one(check_col)
        if col_result and not col_result.get("col_exists", False):
            try:
                await execute(f"ALTER TABLE domains ADD COLUMN {col_name} {col_def}")
                logger.info(f"Added column {col_name} to domains table")
            except Exception as e:
                logger.warning(f"Failed to add column {col_name} to domains: {e}")

    # Create index for job_id if it doesn't exist
    try:
        await execute("CREATE INDEX IF NOT EXISTS idx_domains_job_id ON domains(job_id)")
    except Exception as e:
        logger.warning(f"Domain index creation note: {e}")

    logger.info("Domain table columns initialized for dual provider pricing")
