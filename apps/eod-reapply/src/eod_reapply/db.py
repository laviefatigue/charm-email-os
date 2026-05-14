"""DB access — minimal. Reads workspace + workspace_api_keys + the
campaign_reapply_jobs queue introduced by migration 111.

The CLI v1 only needs workspace+key lookup. The v2 daemon adds the
job-queue helpers (enqueue + claim + complete) below. Both share the
same module to keep all DB shape in one place.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

import asyncpg


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: UUID
    workspace_name: str
    emailbison_workspace_id: str | None
    api_key: str


@dataclass(frozen=True)
class EnabledWorkspace:
    """A workspace with EOD reapply enabled. Returned by list_enabled_workspaces.

    `eod_reapply_enabled` is the per-workspace rollout flag added in migration 111.
    Daemon iterates these on every enqueue pass.
    """
    workspace_id: UUID
    workspace_name: str
    api_key: str


@dataclass(frozen=True)
class ActiveCampaign:
    """An active emailbison_campaigns row. Used by the daemon's enqueuer."""
    campaign_id: UUID
    workspace_id: UUID
    emailbison_campaign_id: str  # numeric id as string in our DB


@dataclass(frozen=True)
class PendingJob:
    """A row claimed from campaign_reapply_jobs ready to run."""
    job_id: UUID
    workspace_id: UUID
    workspace_name: str
    api_key: str
    campaign_id: UUID
    emailbison_campaign_id: int
    scheduled_for: datetime
    run_local_date: date
    run_local_tz: str


async def fetch_workspace_context(
    conn: asyncpg.Connection,
    workspace_name: str,
) -> WorkspaceContext | None:
    """Look up an active workspace by name and return its API key context.

    Returns None if the workspace doesn't exist, isn't active, or has no
    active API key.
    """
    row = await conn.fetchrow(
        """
        SELECT
            w.id AS workspace_id,
            w.workspace_name,
            w.emailbison_workspace_id,
            k.key_token AS api_key
        FROM workspaces w
        JOIN workspace_api_keys k
            ON k.workspace_id = w.id
            AND k.is_active = TRUE
        WHERE w.workspace_name = $1
            AND w.is_active = TRUE
        LIMIT 1
        """,
        workspace_name,
    )
    if row is None:
        return None
    return WorkspaceContext(
        workspace_id=row["workspace_id"],
        workspace_name=row["workspace_name"],
        emailbison_workspace_id=row["emailbison_workspace_id"],
        api_key=row["api_key"],
    )


# ============================================================================
# Daemon helpers — campaign_reapply_jobs queue
# ============================================================================

async def list_enabled_workspaces(conn: asyncpg.Connection) -> list[EnabledWorkspace]:
    """Workspaces with eod_reapply_enabled=TRUE AND is_active=TRUE that also
    have an active API key. Daemon's enqueue loop calls this once per pass.
    """
    rows = await conn.fetch(
        """
        SELECT
            w.id AS workspace_id,
            w.workspace_name,
            k.key_token AS api_key
        FROM workspaces w
        JOIN workspace_api_keys k
            ON k.workspace_id = w.id
            AND k.is_active = TRUE
        WHERE w.is_active = TRUE
            AND w.eod_reapply_enabled = TRUE
        ORDER BY w.workspace_name
        """,
    )
    return [
        EnabledWorkspace(
            workspace_id=r["workspace_id"],
            workspace_name=r["workspace_name"],
            api_key=r["api_key"],
        )
        for r in rows
    ]


async def list_active_campaigns(
    conn: asyncpg.Connection,
    workspace_id: UUID,
) -> list[ActiveCampaign]:
    """Active emailbison_campaigns rows for a workspace.

    'Active' here matches what the orchestrator's status check accepts:
    campaign_status in ('active', 'queued', 'sending'), case-insensitive,
    and is_active=TRUE on the row.
    """
    rows = await conn.fetch(
        """
        SELECT
            id AS campaign_id,
            workspace_id,
            emailbison_campaign_id
        FROM emailbison_campaigns
        WHERE workspace_id = $1
            AND is_active = TRUE
            AND LOWER(COALESCE(campaign_status, '')) IN ('active', 'queued', 'sending')
        ORDER BY emailbison_campaign_id
        """,
        workspace_id,
    )
    return [
        ActiveCampaign(
            campaign_id=r["campaign_id"],
            workspace_id=r["workspace_id"],
            emailbison_campaign_id=r["emailbison_campaign_id"],
        )
        for r in rows
    ]


async def enqueue_job(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    scheduled_for: datetime,
    run_local_date: date,
    run_local_tz: str,
) -> UUID | None:
    """Insert a pending job row. Returns the new job id, or None if a row
    for (campaign_id, run_local_date) already exists.

    The unique constraint on (campaign_id, run_local_date) makes this
    idempotent — re-running the enqueuer for the same day is a no-op.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO campaign_reapply_jobs
            (workspace_id, campaign_id, scheduled_for, run_local_date, run_local_tz)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (campaign_id, run_local_date) DO NOTHING
        RETURNING id
        """,
        workspace_id, campaign_id, scheduled_for, run_local_date, run_local_tz,
    )
    return row["id"] if row else None


async def fetch_next_scheduled_at(conn: asyncpg.Connection) -> datetime | None:
    """MIN(scheduled_for) among pending jobs. Used by the daemon to decide
    how long to sleep before the next wake. Returns None if no pending jobs.

    Backed by idx_campaign_reapply_jobs_pending (partial index on status='pending').
    """
    val = await conn.fetchval(
        "SELECT MIN(scheduled_for) FROM campaign_reapply_jobs WHERE status = 'pending'"
    )
    # asyncpg types fetchval as Any. Postgres MIN over TIMESTAMPTZ returns datetime or None.
    if val is None:
        return None
    assert isinstance(val, datetime)
    return val


async def claim_due_job(conn: asyncpg.Connection, now: datetime) -> PendingJob | None:
    """Atomically claim the next pending job whose scheduled_for has arrived.

    Uses SELECT FOR UPDATE SKIP LOCKED so multiple daemon instances are
    crash-safe even if we never run more than one. Flips status to
    'flagged' on the same transaction.

    Returns None if no due jobs are pending (caller should sleep until
    fetch_next_scheduled_at()).
    """
    row = await conn.fetchrow(
        """
        WITH claimed AS (
            SELECT j.id
            FROM campaign_reapply_jobs j
            WHERE j.status = 'pending' AND j.scheduled_for <= $1
            ORDER BY j.scheduled_for
            LIMIT 1
            FOR UPDATE OF j SKIP LOCKED
        )
        UPDATE campaign_reapply_jobs j
        SET status = 'flagged'
        FROM claimed
        WHERE j.id = claimed.id
        RETURNING
            j.id AS job_id,
            j.workspace_id,
            j.campaign_id,
            j.scheduled_for,
            j.run_local_date,
            j.run_local_tz
        """,
        now,
    )
    if row is None:
        return None

    # Resolve workspace + api_key + numeric EB campaign id in a second query.
    # Keeping the claim small lets us hold the row lock for the shortest possible time.
    enrich = await conn.fetchrow(
        """
        SELECT
            w.workspace_name,
            k.key_token AS api_key,
            ec.emailbison_campaign_id
        FROM workspaces w
        JOIN workspace_api_keys k
            ON k.workspace_id = w.id AND k.is_active = TRUE
        JOIN emailbison_campaigns ec
            ON ec.id = $2
        WHERE w.id = $1
        LIMIT 1
        """,
        row["workspace_id"], row["campaign_id"],
    )
    if enrich is None:
        # Shouldn't happen given FK constraints + the enabled-workspace check,
        # but guard against it: mark the job as skipped and return None.
        await conn.execute(
            """
            UPDATE campaign_reapply_jobs
            SET status = 'skipped',
                completed_at = NOW(),
                error_message = 'workspace or api key no longer resolvable at claim time'
            WHERE id = $1
            """,
            row["job_id"],
        )
        return None

    return PendingJob(
        job_id=row["job_id"],
        workspace_id=row["workspace_id"],
        workspace_name=enrich["workspace_name"],
        api_key=enrich["api_key"],
        campaign_id=row["campaign_id"],
        emailbison_campaign_id=int(enrich["emailbison_campaign_id"]),
        scheduled_for=row["scheduled_for"],
        run_local_date=row["run_local_date"],
        run_local_tz=row["run_local_tz"],
    )


async def emit_event_log_due(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    job_id: UUID,
    payload: dict,  # type: ignore[type-arg]
) -> UUID:
    """Insert the past-tense audit row in event_log for a claimed job.
    Returns the event_log row id, which the daemon stores on the job row.

    `event_type` = 'campaign_reapply_due'. The CHECK constraint introduced
    by migration 111 requires workspace_id IS NOT NULL for this event_type.
    The event is keyed to the campaign (entity_type='emailbison_campaign').
    """
    import json
    val = await conn.fetchval(
        """
        INSERT INTO event_log
            (event_type, entity_type, entity_id, workspace_id,
             payload, status, emitted_at, handler_started_at, handler_name)
        VALUES
            ('campaign_reapply_due', 'emailbison_campaign', $2, $1,
             $3::jsonb, 'processing', NOW(), NOW(), 'eod_reapply_daemon')
        RETURNING id
        """,
        workspace_id,
        campaign_id,
        json.dumps({"job_id": str(job_id), **payload}),
    )
    assert isinstance(val, UUID)
    return val


async def finalize_job(
    conn: asyncpg.Connection,
    *,
    job_id: UUID,
    event_log_id: UUID,
    job_status: str,           # 'completed' / 'failed' / 'skipped'
    event_log_status: str,     # 'completed' / 'failed'
    error_message: str | None,
    result_meta: dict | None,  # type: ignore[type-arg]
) -> None:
    """Close out a claimed job: stamp the job row + update the event_log row.

    Single transaction so the two rows are consistent. The daemon calls
    this exactly once per claim.
    """
    import json
    async with conn.transaction():
        await conn.execute(
            """
            UPDATE campaign_reapply_jobs
            SET status = $2,
                triggered_event_id = $3,
                completed_at = NOW(),
                error_message = $4
            WHERE id = $1
            """,
            job_id, job_status, event_log_id, error_message,
        )
        await conn.execute(
            """
            UPDATE event_log
            SET status = $2,
                handler_completed_at = NOW(),
                error_message = $3,
                metadata = COALESCE($4::jsonb, metadata)
            WHERE id = $1
            """,
            event_log_id,
            event_log_status,
            error_message,
            json.dumps(result_meta) if result_meta is not None else None,
        )
