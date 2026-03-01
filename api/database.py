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

    # Initialize strategies table columns
    await _ensure_strategies_table_columns()

    # Initialize strategy generation tables (Phase 3)
    await _init_strategy_tables()


async def _ensure_strategies_table_columns() -> None:
    """Ensure strategies table has all required columns"""

    # Check if strategies table exists
    check_table = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'strategies'
        ) as table_exists;
    """
    result = await fetch_one(check_table)
    if not result or not result.get("table_exists", False):
        logger.info("Strategies table does not exist, skipping column initialization")
        return

    # Add missing columns
    columns_to_add = [
        ("submission_id", "UUID"),
        ("emailbison_campaign_id", "VARCHAR(255)"),
    ]

    for col_name, col_def in columns_to_add:
        check_col = f"""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'strategies' AND column_name = '{col_name}'
            ) as col_exists;
        """
        col_result = await fetch_one(check_col)
        if col_result and not col_result.get("col_exists", False):
            try:
                await execute(f"ALTER TABLE strategies ADD COLUMN {col_name} {col_def}")
                logger.info(f"Added column {col_name} to strategies table")
            except Exception as e:
                logger.warning(f"Failed to add column {col_name} to strategies: {e}")

    # Initialize domain sourcing columns (Phase 3)
    await _init_domain_columns()

    # Initialize subscription tables (Phase 6B)
    await _init_subscription_tables()


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

    # Fix for trigger referencing non-existent is_active column
    # First, list and drop any problematic triggers
    try:
        triggers = await fetch_all("""
            SELECT tgname FROM pg_trigger
            WHERE tgrelid = 'strategy_suggestions'::regclass
            AND NOT tgisinternal
        """)
        for trigger in triggers:
            trigger_name = trigger['tgname']
            logger.warning(f"Dropping trigger {trigger_name} on strategy_suggestions")
            await execute(f'DROP TRIGGER IF EXISTS "{trigger_name}" ON strategy_suggestions')
        if triggers:
            logger.info(f"Dropped {len(triggers)} trigger(s) on strategy_suggestions")
    except Exception as e:
        logger.warning(f"Trigger cleanup note: {e}")

    # Add is_active column if missing
    try:
        await execute("""
            ALTER TABLE strategy_suggestions
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true
        """)
        logger.info("Strategy suggestions is_active column ready")
    except Exception as e:
        logger.warning(f"Strategy suggestions is_active column note: {e}")

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

    # Add dual provider pricing columns and other required columns
    columns_to_add = [
        # Original pricing columns (from migration 006)
        ("cached_price", "DECIMAL(10,2)"),
        ("price_checked_at", "TIMESTAMP"),
        ("purchased_at", "TIMESTAMP"),
        # Dual provider pricing columns (from migration 007)
        ("porkbun_price", "DECIMAL(10,2)"),
        ("porkbun_available", "BOOLEAN"),
        ("dynadot_price", "DECIMAL(10,2)"),
        ("dynadot_available", "BOOLEAN"),
        ("selected_provider", "VARCHAR(20)"),
        ("job_id", "UUID"),
        # Nameserver tracking for Hypertide readiness (24-48hr propagation)
        ("nameservers_updated_at", "TIMESTAMP"),
        # Nameserver verification status: pending, verified, failed, mismatch
        ("nameserver_status", "VARCHAR(20) DEFAULT 'pending'"),
        ("nameserver_verified_at", "TIMESTAMP"),
        ("current_nameservers", "TEXT[]"),  # Array of current NS from registrar
        # Infrastructure type tracking (Entra or Google) - set when inboxes are provisioned
        ("infrastructure_type", "VARCHAR(20)"),  # 'entra' or 'google'
        ("infrastructure_set_at", "TIMESTAMP"),  # When infrastructure was assigned
        # Purchase job locking (domain reserved by active purchase job)
        ("purchase_job_id", "UUID"),
        ("purchase_job_status", "TEXT"),
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


async def _init_subscription_tables() -> None:
    """Initialize subscription management tables (Phase 6B)"""

    # Package templates table
    create_templates_table = """
        CREATE TABLE IF NOT EXISTS package_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(100) NOT NULL UNIQUE,
            entra_packages INTEGER NOT NULL DEFAULT 6,
            entra_domains_per_package INTEGER DEFAULT 2,
            entra_inboxes_per_domain INTEGER DEFAULT 52,
            google_packages INTEGER NOT NULL DEFAULT 5,
            google_domains_per_package INTEGER DEFAULT 5,
            google_inboxes_per_domain INTEGER DEFAULT 3,
            total_domains INTEGER GENERATED ALWAYS AS (
                (entra_packages * entra_domains_per_package) +
                (google_packages * google_domains_per_package)
            ) STORED,
            total_inboxes INTEGER GENERATED ALWAYS AS (
                (entra_packages * entra_domains_per_package * entra_inboxes_per_domain) +
                (google_packages * google_domains_per_package * google_inboxes_per_domain)
            ) STORED,
            monthly_price DECIMAL(10,2),
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """
    try:
        await execute(create_templates_table)
        logger.info("Package templates table ready")

        # Seed default packages
        await execute("""
            INSERT INTO package_templates (name, entra_packages, google_packages, monthly_price)
            VALUES
                ('Starter', 6, 5, NULL),
                ('Growth', 12, 10, NULL)
            ON CONFLICT (name) DO NOTHING
        """)
        logger.info("Default package templates seeded")
    except Exception as e:
        logger.warning(f"Package templates table note: {e}")

    # Client subscriptions table
    create_subscriptions_table = """
        CREATE TABLE IF NOT EXISTS client_subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            package_template_id UUID REFERENCES package_templates(id),
            entra_packages INTEGER NOT NULL DEFAULT 6,
            entra_domains_per_package INTEGER DEFAULT 2,
            entra_inboxes_per_domain INTEGER DEFAULT 52,
            google_packages INTEGER NOT NULL DEFAULT 5,
            google_domains_per_package INTEGER DEFAULT 5,
            google_inboxes_per_domain INTEGER DEFAULT 3,
            spare_ratio DECIMAL(3,2) DEFAULT 0.15,
            status VARCHAR(20) DEFAULT 'active',
            started_at TIMESTAMP DEFAULT NOW(),
            cancelled_at TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_subscriptions_client ON client_subscriptions(client_id);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON client_subscriptions(status);
    """
    try:
        await execute(create_subscriptions_table)
        logger.info("Client subscriptions table ready")
    except Exception as e:
        logger.warning(f"Client subscriptions table note: {e}")

    # Subscription changes table
    create_changes_table = """
        CREATE TABLE IF NOT EXISTS subscription_changes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subscription_id UUID NOT NULL REFERENCES client_subscriptions(id) ON DELETE CASCADE,
            change_type VARCHAR(20) NOT NULL,
            previous_entra_packages INTEGER,
            previous_google_packages INTEGER,
            new_entra_packages INTEGER,
            new_google_packages INTEGER,
            reason TEXT,
            changed_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_subscription_changes_subscription ON subscription_changes(subscription_id);
        CREATE INDEX IF NOT EXISTS idx_subscription_changes_created ON subscription_changes(created_at);
    """
    try:
        await execute(create_changes_table)
        logger.info("Subscription changes table ready")
    except Exception as e:
        logger.warning(f"Subscription changes table note: {e}")

    # Initialize inbox purchase jobs table (Feature 11)
    await _init_purchase_jobs_table()


async def _init_purchase_jobs_table() -> None:
    """Initialize inbox purchase jobs table for job persistence and retry capability"""

    create_jobs_table = """
        CREATE TABLE IF NOT EXISTS inbox_purchase_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            workspace_id UUID REFERENCES workspaces(id),
            status VARCHAR(50) DEFAULT 'pending',
            current_step TEXT,
            provider_type VARCHAR(20),
            domain_ids UUID[],
            domain_names TEXT[],
            entra_orders INTEGER DEFAULT 0,
            google_orders INTEGER DEFAULT 0,
            orders_completed INTEGER DEFAULT 0,
            orders_total INTEGER DEFAULT 0,
            total_inboxes INTEGER DEFAULT 0,
            monthly_cost DECIMAL(10,2),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            results JSONB,
            errors TEXT[],
            request_data JSONB,
            override_age_check BOOLEAN DEFAULT FALSE,
            custom_purchase BOOLEAN DEFAULT FALSE
        );
        CREATE INDEX IF NOT EXISTS idx_purchase_jobs_client ON inbox_purchase_jobs(client_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_purchase_jobs_status ON inbox_purchase_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_purchase_jobs_retry ON inbox_purchase_jobs(status) WHERE status = 'failed';
    """
    try:
        await execute(create_jobs_table)
        logger.info("Inbox purchase jobs table ready")
    except Exception as e:
        logger.warning(f"Inbox purchase jobs table note: {e}")

    # Add purchase worker columns (for AI container-based purchasing)
    worker_columns = [
        ("hypertide_email", "TEXT"),
        ("hypertide_password", "TEXT"),
        ("company_name", "TEXT"),
        ("forwarding_domain", "TEXT"),
        ("bison_username", "TEXT"),
        ("bison_password", "TEXT"),
        ("bison_workspace_name", "TEXT"),
        ("bison_url", "TEXT DEFAULT 'https://spellcast.hirecharm.com'"),
        ("sender_names", "JSONB"),
        ("use_saved_payment", "BOOLEAN DEFAULT TRUE"),
        ("order_count", "INTEGER DEFAULT 1"),
        ("worker_mode", "VARCHAR(20) DEFAULT 'api'"),
        ("hypertide_order_id", "TEXT"),
        ("error_type", "TEXT"),
        ("checkout_url", "TEXT"),
    ]

    for col_name, col_def in worker_columns:
        check_col = f"""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'inbox_purchase_jobs' AND column_name = '{col_name}'
            ) as col_exists;
        """
        col_result = await fetch_one(check_col)
        if col_result and not col_result.get("col_exists", False):
            try:
                await execute(f"ALTER TABLE inbox_purchase_jobs ADD COLUMN {col_name} {col_def}")
                logger.info(f"Added column {col_name} to inbox_purchase_jobs table")
            except Exception as e:
                logger.warning(f"Failed to add column {col_name} to inbox_purchase_jobs: {e}")

    # Create partial index for worker job polling
    try:
        await execute("""
            CREATE INDEX IF NOT EXISTS idx_purchase_jobs_worker_pending
            ON inbox_purchase_jobs(status, worker_mode)
            WHERE status = 'pending' AND worker_mode = 'worker'
        """)
    except Exception as e:
        logger.warning(f"Worker pending index note: {e}")

    # Create purchase_job_steps audit table
    create_steps_table = """
        CREATE TABLE IF NOT EXISTS purchase_job_steps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id UUID NOT NULL REFERENCES inbox_purchase_jobs(id) ON DELETE CASCADE,
            step_name TEXT NOT NULL,
            screenshot_base64 TEXT,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_purchase_steps_job ON purchase_job_steps(job_id, created_at);
    """
    try:
        await execute(create_steps_table)
        logger.info("Purchase job steps audit table ready")
    except Exception as e:
        logger.warning(f"Purchase job steps table note: {e}")

    # Ensure infrastructure waterfall view is up to date
    await _ensure_infrastructure_waterfall_view()


async def _ensure_infrastructure_waterfall_view() -> None:
    """Ensure v_infrastructure_waterfall view exists with all required columns."""
    # Check if view has domain_purchase_job_id column
    check_col = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'v_infrastructure_waterfall'
            AND column_name = 'domain_purchase_job_id'
        ) as col_exists
    """
    view_needs_update = True
    try:
        result = await fetch_one(check_col)
        if result and result.get("col_exists"):
            logger.info("Infrastructure waterfall view already up to date")
            view_needs_update = False
    except Exception:
        pass  # View might not exist, we'll create it

    # Drop and recreate view with latest schema if needed
    if view_needs_update:
        logger.info("Recreating v_infrastructure_waterfall view...")
    create_view_sql = """
        DROP VIEW IF EXISTS v_infrastructure_waterfall;

        CREATE VIEW v_infrastructure_waterfall AS
        SELECT
            d.id AS domain_id,
            d.workspace_id,
            d.domain_name,
            d.approval_status,
            d.created_at AS generated_at,
            d.legitimacy_score,
            COALESCE(d.domain_source, 'legacy') AS domain_source,
            d.price_checked_at,
            d.cached_price,
            d.selected_provider,
            d.porkbun_price,
            d.porkbun_available,
            d.dynadot_price,
            d.dynadot_available,
            CASE
                WHEN d.price_checked_at IS NULL THEN 'not_checked'
                WHEN d.price_checked_at < NOW() - INTERVAL '24 hours' THEN 'stale'
                WHEN d.porkbun_available = false AND d.dynadot_available = false THEN 'unavailable'
                ELSE 'valid'
            END AS price_status,
            d.purchased_at,
            d.job_id AS domain_purchase_job_id,
            d.purchase_job_id,
            d.nameservers_updated_at,
            d.current_nameservers,
            CASE
                WHEN d.nameservers_updated_at IS NULL THEN 'not_set'
                WHEN d.nameservers_updated_at > NOW() - INTERVAL '24 hours' THEN 'propagating'
                ELSE 'propagated'
            END AS dns_migration_status,
            d.nameserver_status,
            d.nameserver_verified_at,
            COALESCE(d.spf_configured, false) AS spf_configured,
            COALESCE(d.dkim_configured, false) AS dkim_configured,
            COALESCE(d.dmarc_configured, false) AS dmarc_configured,
            COALESCE(d.mx_configured, false) AS mx_configured,
            COALESCE(d.dns_records_configured, false) AS dns_records_configured,
            COALESCE(d.infrastructure_type, inbox_stats.detected_provider::varchar) AS assigned_provider,
            inbox_stats.detected_provider,
            ipj.id AS hypertide_order_job_id,
            ipj.status AS hypertide_order_status,
            ipj.current_step AS hypertide_current_step,
            ipj.created_at AS hypertide_ordered_at,
            COALESCE(inbox_stats.live_count, 0) AS live_inbox_count,
            COALESCE(inbox_stats.dead_count, 0) AS dead_inbox_count,
            COALESCE(inbox_stats.total_count, 0) AS synced_inbox_count,
            inbox_stats.last_synced_at AS last_inbox_synced_at,
            COALESCE(inbox_stats.connected_count, 0) AS connected_inbox_count,
            COALESCE(inbox_stats.disconnected_count, 0) AS disconnected_inbox_count,
            CASE
                WHEN COALESCE(inbox_stats.total_count, 0) > 0 THEN 9
                WHEN ipj.status = 'completed' THEN 8
                WHEN ipj.id IS NOT NULL THEN 7
                WHEN d.infrastructure_type IS NOT NULL THEN 6
                WHEN d.nameserver_status = 'verified' THEN 5
                WHEN d.nameservers_updated_at IS NOT NULL THEN 4
                WHEN d.purchased_at IS NOT NULL THEN 3
                WHEN d.price_checked_at IS NOT NULL THEN 2
                ELSE 1
            END AS current_stage,
            d.approval_status = 'owned' AS owned_by_client,
            COALESCE(inbox_stats.total_count, 0) > 0 AS deployed_to_production
        FROM domains d
        LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.purchase_job_id
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (WHERE sa.inbox_state <> 'dead' OR sa.inbox_state IS NULL) AS live_count,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') AS dead_count,
                COUNT(*) AS total_count,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') AS connected_count,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status IN ('Not connected', 'Disconnected')) AS disconnected_count,
                MAX(sa.created_at) AS last_synced_at,
                CASE
                    WHEN COUNT(*) FILTER (WHERE sa.esp = 'microsoft') > 0 THEN 'entra'
                    WHEN COUNT(*) FILTER (WHERE sa.esp = 'gmail') > 0 THEN 'google'
                    ELSE NULL
                END AS detected_provider
            FROM sender_accounts sa
            WHERE sa.domain_id = d.id
        ) inbox_stats ON true
        WHERE d.is_active = true;
    """
    if view_needs_update:
        try:
            await execute(create_view_sql)
            logger.info("Infrastructure waterfall view created successfully")
        except Exception as e:
            logger.error(f"Failed to create infrastructure waterfall view: {e}")

    # Backfill Charm's purchase record if missing (always runs)
    await _backfill_charm_purchase_record()


async def _backfill_charm_purchase_record() -> None:
    """Ensure activatecharm.com has proper purchase record (only actual purchase)."""
    charm_client_id = "4bd07dc0-059a-448b-b6f4-3275d0c104a9"

    # Check if activatecharm.com already has a job_id
    check_sql = """
        SELECT d.id, d.job_id
        FROM domains d
        JOIN clients c ON d.workspace_id = c.workspace_id
        WHERE c.id = $1
        AND d.domain_name = 'activatecharm.com'
    """
    try:
        result = await fetch_one(check_sql, charm_client_id)
        if not result:
            logger.info("activatecharm.com not found for Charm")
            return
        if result.get("job_id"):
            logger.info("activatecharm.com purchase record already exists")
            return
    except Exception as e:
        logger.warning(f"Could not check activatecharm.com: {e}")
        return

    # Create purchase job for activatecharm.com only (purchased via Porkbun)
    backfill_sql = """
        WITH new_job AS (
            INSERT INTO domain_purchase_jobs (
                id, client_id, workspace_id, domain_ids, domain_names,
                registrar, status, successful_count, failed_count, total_cost,
                results, created_at, started_at, completed_at
            )
            SELECT
                gen_random_uuid(),
                c.id,
                c.workspace_id,
                ARRAY[d.id],
                ARRAY['activatecharm.com'],
                'porkbun',
                'completed',
                1,
                0,
                9.99,
                jsonb_build_object('note', 'activatecharm.com purchased via Porkbun'),
                '2026-02-28 00:00:00+00'::timestamptz,
                '2026-02-28 00:00:00+00'::timestamptz,
                '2026-02-28 00:00:00+00'::timestamptz
            FROM domains d
            JOIN clients c ON d.workspace_id = c.workspace_id
            WHERE c.id = $1 AND d.domain_name = 'activatecharm.com'
            RETURNING id, domain_ids
        )
        UPDATE domains
        SET job_id = new_job.id, selected_provider = 'porkbun'
        FROM new_job
        WHERE domains.id = ANY(new_job.domain_ids)
    """
    try:
        await execute(backfill_sql, charm_client_id)
        logger.info("Created purchase record for activatecharm.com")
    except Exception as e:
        logger.warning(f"Could not create activatecharm.com purchase record: {e}")
