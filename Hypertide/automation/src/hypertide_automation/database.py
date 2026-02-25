"""
Database connection and operations for Hypertide automation.

Connects to DBon PostgreSQL (charmdemon schema) for:
- Reading approved domains from domain_approval_requests
- Tracking purchased domains in domain_purchases
- Managing provisioned inboxes in client_inboxes
"""

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

import asyncpg
import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class DatabaseConfig(BaseModel):
    """Database configuration."""
    host: str = "localhost"
    port: int = 5433
    database: str = "brainon"
    user: str = "brainon"
    password: str = "brainon2025"
    schema: str = "charmdemon"

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Load from environment variables."""
        # Try DATABASE_URL first
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            # Parse postgres://user:pass@host:port/database
            from urllib.parse import urlparse
            parsed = urlparse(database_url)
            return cls(
                host=parsed.hostname or "localhost",
                port=parsed.port or 5433,
                database=parsed.path.lstrip("/") or "brainon",
                user=parsed.username or "brainon",
                password=parsed.password or "brainon2025",
            )

        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5433")),
            database=os.getenv("DB_NAME", "brainon"),
            user=os.getenv("DB_USER", "brainon"),
            password=os.getenv("DB_PASSWORD", "brainon2025"),
            schema=os.getenv("DB_SCHEMA", "charmdemon"),
        )

    @property
    def dsn(self) -> str:
        """Get connection DSN string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class Database:
    """
    Async database connection manager for Hypertide automation.

    Usage:
        async with Database() as db:
            domains = await db.get_approved_domains(client_id)
    """

    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig.from_env()
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.config.dsn,
                min_size=1,
                max_size=5,
            )
            logger.info("Database pool created", host=self.config.host, port=self.config.port)

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @asynccontextmanager
    async def connection(self):
        """Get a connection from the pool."""
        async with self._pool.acquire() as conn:
            # Set search path to charmdemon schema
            await conn.execute(f"SET search_path TO {self.config.schema}, public")
            yield conn

    # =========================================================================
    # Domain Operations
    # =========================================================================

    async def get_approved_domains(
        self,
        client_id: Optional[str] = None,
        status: str = "approved",
    ) -> List[Dict[str, Any]]:
        """
        Get domains approved for purchase.

        Args:
            client_id: Filter by specific client
            status: Filter by approval status (default: approved)

        Returns:
            List of domain records
        """
        async with self.connection() as conn:
            if client_id:
                rows = await conn.fetch("""
                    SELECT dar.*, c.name as client_name, c.slug as client_slug
                    FROM domain_approval_requests dar
                    JOIN clients c ON dar.client_id = c.id
                    WHERE dar.client_id = $1 AND dar.status = $2
                    ORDER BY dar.created_at DESC
                """, UUID(client_id), status)
            else:
                rows = await conn.fetch("""
                    SELECT dar.*, c.name as client_name, c.slug as client_slug
                    FROM domain_approval_requests dar
                    JOIN clients c ON dar.client_id = c.id
                    WHERE dar.status = $1
                    ORDER BY dar.created_at DESC
                """, status)

            return [dict(row) for row in rows]

    async def get_client_by_id(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get client details by ID."""
        async with self.connection() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM clients WHERE id = $1
            """, UUID(client_id))
            return dict(row) if row else None

    async def record_domain_purchase(
        self,
        client_id: str,
        domain_name: str,
        tld: str,
        registrar: str,
        purchase_price: float,
        success: bool,
        hypertide_domain_id: Optional[str] = None,
        assigned_provider: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> str:
        """
        Record a domain purchase attempt.

        Returns:
            UUID of the created record
        """
        async with self.connection() as conn:
            row = await conn.fetchrow("""
                INSERT INTO domain_purchases (
                    client_id, domain_name, tld, registrar,
                    purchase_price, success, hypertide_domain_id,
                    assigned_provider, error_message, purchased_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """,
                UUID(client_id), domain_name, tld, registrar,
                purchase_price, success, hypertide_domain_id,
                assigned_provider, error_message,
                datetime.utcnow() if success else None
            )
            return str(row["id"])

    async def get_purchased_domains(
        self,
        client_id: str,
        success_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get purchased domains for a client."""
        async with self.connection() as conn:
            query = """
                SELECT dp.*, c.name as client_name
                FROM domain_purchases dp
                JOIN clients c ON dp.client_id = c.id
                WHERE dp.client_id = $1
            """
            if success_only:
                query += " AND dp.success = true"
            query += " ORDER BY dp.purchased_at DESC"

            rows = await conn.fetch(query, UUID(client_id))
            return [dict(row) for row in rows]

    # =========================================================================
    # Inbox Operations
    # =========================================================================

    async def record_inbox(
        self,
        client_id: str,
        email_address: str,
        domain_name: str,
        provider: str,
        display_name: Optional[str] = None,
        hypertide_inbox_id: Optional[str] = None,
        domain_purchase_id: Optional[str] = None,
        status: str = "pending",
    ) -> str:
        """
        Record a provisioned inbox.

        Returns:
            UUID of the created record
        """
        async with self.connection() as conn:
            row = await conn.fetchrow("""
                INSERT INTO client_inboxes (
                    client_id, email_address, domain_name, provider,
                    display_name, hypertide_inbox_id, domain_purchase_id,
                    status, warmup_status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'not_started', NOW())
                RETURNING id
            """,
                UUID(client_id), email_address, domain_name, provider,
                display_name, hypertide_inbox_id,
                UUID(domain_purchase_id) if domain_purchase_id else None,
                status
            )
            return str(row["id"])

    async def get_client_inboxes(
        self,
        client_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get inboxes for a client."""
        async with self.connection() as conn:
            query = """
                SELECT ci.*, c.name as client_name, c.emailbison_workspace
                FROM client_inboxes ci
                JOIN clients c ON ci.client_id = c.id
                WHERE ci.client_id = $1
            """
            params = [UUID(client_id)]

            if status:
                query += " AND ci.status = $2"
                params.append(status)

            query += " ORDER BY ci.created_at DESC"

            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def update_inbox_status(
        self,
        inbox_id: str,
        status: str,
        hypertide_inbox_id: Optional[str] = None,
        warmup_status: Optional[str] = None,
    ) -> None:
        """Update inbox status."""
        async with self.connection() as conn:
            updates = ["status = $2", "updated_at = NOW()"]
            params = [UUID(inbox_id), status]

            if hypertide_inbox_id:
                updates.append(f"hypertide_inbox_id = ${len(params) + 1}")
                params.append(hypertide_inbox_id)

            if warmup_status:
                updates.append(f"warmup_status = ${len(params) + 1}")
                params.append(warmup_status)

            if status == "active" and "provisioned_at" not in updates:
                updates.append("provisioned_at = NOW()")

            query = f"UPDATE client_inboxes SET {', '.join(updates)} WHERE id = $1"
            await conn.execute(query, *params)

    async def update_domain_approval_status(
        self,
        approval_id: str,
        status: str,
    ) -> None:
        """Update domain approval request status."""
        async with self.connection() as conn:
            await conn.execute("""
                UPDATE domain_approval_requests
                SET status = $2, updated_at = NOW()
                WHERE id = $1
            """, UUID(approval_id), status)


# Convenience function for one-off operations
async def get_database() -> Database:
    """Get a connected database instance."""
    db = Database()
    await db.connect()
    return db
