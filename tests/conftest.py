"""
Pytest fixtures for integration tests against a real Postgres.

Two ways to provide a database for tests:
  1. Testcontainers (default if Docker is available): a fresh Postgres
     container is spun up for the test session and torn down at the end.
  2. TEST_DATABASE_URL env var (fallback): point at any reachable
     Postgres; the session will create a temporary database on it,
     apply migrations, and drop it at session end.

In both cases, every migration in `migrations/*.sql` is applied in
filename order to give the tests the same schema as production.

Per-test isolation: each test runs inside its own asyncpg.Pool that
TRUNCATEs the load-bearing tables before yielding. This is faster than
recreating the database for every test and keeps the fixture surface
small.

Tests are intentionally NOT isolated via SAVEPOINT/ROLLBACK because the
production code uses asyncpg.Pool (multiple connections) and cross-
connection transactions are awkward to reason about. TRUNCATE is
sufficient because the data we load per-test is small.
"""
from __future__ import annotations

import asyncio
import os
import socket
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

import asyncpg
import pytest
import pytest_asyncio


# ──────────────────────────────────────────────────────────────────────────
# Database container / URL resolution
# ──────────────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_MIGRATIONS_DIR = _REPO_ROOT / "migrations"
# Base schema files applied BEFORE migrations. The production schema dump
# at docker/init/00_public_schema.sql is the canonical "snapshot" that the
# incremental migrations build on top of.
_BASE_SCHEMA_DIR = _REPO_ROOT / "docker" / "init"


def _docker_available() -> bool:
    """Detect whether a Docker daemon is reachable."""
    try:
        import docker  # type: ignore

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session.

    pytest-asyncio defaults to function-scope, which would force a new
    asyncpg pool per test and fight with our session-scope DB fixture.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def db_url(request) -> str:
    """
    Resolve a Postgres URL for the test session.

    Preference order:
      1. TEST_DATABASE_URL env var (developer-provided)
      2. Testcontainers Postgres (requires Docker)

    If neither is available, skip the entire integration test suite —
    we do not run mocked-DB tests masquerading as integration tests.
    """
    env_url = os.environ.get("TEST_DATABASE_URL")
    if env_url:
        return env_url

    if not _docker_available():
        pytest.skip(
            "No TEST_DATABASE_URL set and Docker is not running. "
            "Either start Docker Desktop or export TEST_DATABASE_URL "
            "pointing at a reachable Postgres."
        )

    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("postgres:15-alpine")
    container.start()
    request.addfinalizer(container.stop)

    return container.get_connection_url().replace("+psycopg2", "")


def _strip_psql_directives(sql: str) -> str:
    """
    Strip psql-only directives that psycopg2 cannot execute.

    pg_dump emits `\\restrict <token>` / `\\unrestrict <token>` markers in
    recent Postgres versions to protect against malicious SQL injection in
    dump files. These are interpreted by the psql client, not the server,
    so psycopg2 sees them as syntax errors. We strip them out before
    feeding the SQL to a real connection.
    """
    cleaned_lines = []
    for line in sql.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("\\restrict") or stripped.startswith("\\unrestrict"):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _apply_migrations_sync(url: str) -> None:
    """
    Build the test schema in two passes:
      1. Apply docker/init/*.sql (production schema dump + seed data).
      2. Apply migrations/*.sql in filename order.

    psycopg2 is required because asyncpg cannot execute the multi-statement
    schema dump in one shot.
    """
    import psycopg2

    conn = psycopg2.connect(url) if not url.startswith("postgres+") else psycopg2.connect(
        url.replace("postgresql+psycopg2", "postgresql")
    )
    conn.autocommit = True

    # Only apply schema-defining files from docker/init — skip seed data
    # (01_public_data.sql is a pg_dump COPY block that requires psql, not
    # psycopg2, and we insert our own test fixtures anyway). The phased-
    # generation file (02_*.sql) is also schema, so we keep anything that
    # is not a `*data*` file.
    base_files = (
        sorted(p for p in _BASE_SCHEMA_DIR.glob("*.sql") if "data" not in p.name)
        if _BASE_SCHEMA_DIR.exists()
        else []
    )

    # The base schema dump (docker/init) is a pg_dump capture from some
    # known production point in time, not necessarily current head. To bring
    # the test DB up to current schema we replay every migration on top of
    # the dump. Some migrations will collide with state already in the
    # dump ("relation already exists", "ON CONFLICT no matching constraint")
    # — those are tolerable for testing since we only need the FINAL
    # post-applied state. We log+continue on collisions and re-raise only
    # if a migration we explicitly need (094+, the overhaul migrations)
    # fails.
    _OVERHAUL_MIGRATIONS_START = 94

    def _migration_number(p: Path) -> Optional[int]:
        head = p.stem.split("_", 1)[0]
        return int(head) if head.isdigit() else None

    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))

    try:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO public, pg_catalog")
            for sql_file in base_files + migration_files:
                sql = _strip_psql_directives(sql_file.read_text(encoding="utf-8"))
                if not sql.strip():
                    continue
                is_base = sql_file in base_files
                num = _migration_number(sql_file) if not is_base else None
                is_critical = is_base or (
                    num is not None and num >= _OVERHAUL_MIGRATIONS_START
                )
                try:
                    cur.execute(sql)
                    cur.execute("SET search_path TO public, pg_catalog")
                except Exception as e:
                    if is_critical:
                        # Schema dump or overhaul migrations: hard failure.
                        raise RuntimeError(
                            f"Failed to apply {sql_file.name}: {e}"
                        ) from e
                    # Pre-overhaul migration collided with the dump; that's
                    # expected when re-applying on top of a captured state.
                    # Skip and keep going. A real ordering bug in 094+ will
                    # surface as the actual test failure.
                    print(f"  [test-conftest] skip pre-overhaul {sql_file.name}: {e}")
                    # Reset the connection — psycopg2 aborts the txn on error.
                    conn.rollback()
                    cur.execute("SET search_path TO public, pg_catalog")
    finally:
        conn.close()


@pytest_asyncio.fixture(scope="session")
async def session_pool(db_url: str) -> AsyncIterator[asyncpg.Pool]:
    """
    Session-scoped asyncpg pool with all migrations applied.

    Tests share this pool; per-test isolation is provided by `db_pool`
    which TRUNCATEs key tables before yielding.
    """
    # Normalize "postgresql+psycopg2://..." form (testcontainers default) to
    # the asyncpg-native "postgresql://..." form.
    asyncpg_url = db_url.replace("postgresql+psycopg2", "postgresql")

    # Apply migrations using psycopg2 (sync) since asyncpg doesn't run
    # multi-statement files easily.
    try:
        _apply_migrations_sync(db_url)
    except ModuleNotFoundError:
        # psycopg2 not installed — try asyncpg one statement at a time.
        await _apply_migrations_async(asyncpg_url)

    pool = await asyncpg.create_pool(asyncpg_url, min_size=2, max_size=5)
    try:
        yield pool
    finally:
        await pool.close()


async def _apply_migrations_async(url: str) -> None:
    """Fallback migration runner using asyncpg only."""
    conn = await asyncpg.connect(url)
    try:
        for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            sql = sql_file.read_text(encoding="utf-8")
            if not sql.strip():
                continue
            try:
                await conn.execute(sql)
            except Exception as e:
                raise RuntimeError(f"Failed to apply {sql_file.name}: {e}") from e
    finally:
        await conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Per-test fixtures
# ──────────────────────────────────────────────────────────────────────────
_TABLES_TO_TRUNCATE = (
    # Order doesn't matter when CASCADE is used.
    "kill_queue",
    "campaign_inboxes",
    "campaign_burn_events",
    "inbox_rotation_history",
    "domain_rotation_events",
    "response_messages",
    "sender_accounts",
    "domains",
    "workspace_api_keys",
    "workspaces",
    "clients",
    "instances",
)


@pytest_asyncio.fixture
async def db_pool(session_pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Pool]:
    """
    Per-test pool: TRUNCATE before yielding so each test starts clean.

    We accept the small dirty-yield cost of running TRUNCATE inside the
    same pool the production code uses, in exchange for not having to
    spin up per-test pools and connections.
    """
    async with session_pool.acquire() as conn:
        # Quote each table; ignore tables that don't exist (older migration set).
        existing = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_name = ANY($1::text[])
        """, list(_TABLES_TO_TRUNCATE))
        names = [r["table_name"] for r in existing]
        if names:
            await conn.execute(
                f"TRUNCATE {', '.join(names)} RESTART IDENTITY CASCADE"
            )

    yield session_pool


@pytest.fixture
def fake_client():
    """A fresh in-memory FakeEmailBisonClient for each test."""
    from tests.fakes import FakeEmailBisonClient

    return FakeEmailBisonClient()


# ──────────────────────────────────────────────────────────────────────────
# Convenience helpers for fixtures-of-fixtures patterns
# ──────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def workspace_factory(db_pool: asyncpg.Pool):
    """
    Returns an async factory function that inserts a workspace + API key
    and returns its UUID. Lets tests stand up minimal fixtures inline.
    """
    async def _make(
        name: str = "test-workspace",
        eb_id: int = 1,
        a_set_tag: str = "live",
        b_set_tag: str = "reserve",
    ):
        # Many environments require an `instances` row first.
        instance_id = await db_pool.fetchval("""
            INSERT INTO instances (name, instance_type, base_url)
            VALUES ($1, 'emailbison', 'https://test.example')
            RETURNING instance_id
        """, f"test-instance-{uuid.uuid4().hex[:8]}")

        ws_id = await db_pool.fetchval("""
            INSERT INTO workspaces
                (workspace_name, emailbison_workspace_id, instance_id,
                 is_active, automation_enabled, a_set_tag_name, b_set_tag_name)
            VALUES ($1, $2, $3, TRUE, TRUE, $4, $5)
            RETURNING id
        """, name, str(eb_id), instance_id, a_set_tag, b_set_tag)

        await db_pool.execute("""
            INSERT INTO workspace_api_keys
                (workspace_id, emailbison_workspace_id, key_name, key_token)
            VALUES ($1, $2, 'test', $3)
        """, ws_id, eb_id, f"test-key-{uuid.uuid4().hex[:8]}")

        return ws_id

    return _make
