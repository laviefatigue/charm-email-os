"""
Database connection and utilities for Charm Email OS API
Uses asyncpg for async PostgreSQL queries
"""

import asyncio
import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import logging

from config import settings

logger = logging.getLogger(__name__)

# Connection pool
_pool: Optional[asyncpg.Pool] = None

# Connection timeout in seconds
CONNECTION_TIMEOUT = 10.0


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
    """Initialize required tables if they don't exist"""
    # Create clients table if it doesn't exist
    create_clients_table = """
        CREATE TABLE IF NOT EXISTS clients (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,
            logo_url TEXT,
            onboarding_complete BOOLEAN DEFAULT FALSE,
            onboarding_data JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        -- Create index on workspace_id for faster joins
        CREATE INDEX IF NOT EXISTS idx_clients_workspace_id ON clients(workspace_id);
    """
    try:
        await execute(create_clients_table)
        logger.info("Database schema initialized (clients table ready)")
    except Exception as e:
        logger.error(f"Failed to initialize schema: {e}")
