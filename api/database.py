"""
Database connection and utilities for Charm Email OS API
Uses asyncpg for async PostgreSQL queries
"""

import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import logging

from config import settings

logger = logging.getLogger(__name__)

# Connection pool
_pool: Optional[asyncpg.Pool] = None


async def create_pool() -> asyncpg.Pool:
    """Create database connection pool"""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info(f"Database pool created: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")
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
