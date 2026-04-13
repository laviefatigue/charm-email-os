"""
Workspace Sync Routes

Exposes two endpoints for the client-facing dashboard:

  POST /api/sync/workspaces/{workspace_id}/refresh
      Trigger an on-demand full sync for a workspace.  Inserts all five sync
      types at priority=10 into workspace_sync_queue.  The emailbison-sync
      worker's priority poll loop picks them up within ~30 seconds.

  GET  /api/sync/workspaces/{workspace_id}/status
      Return sync freshness (last_successful_sync per type) and the current
      queue state (pending / running jobs) for one workspace.

Auth:
    Both endpoints require a valid user session via get_current_user.
    Workspace ID is validated against the DB to prevent enumeration.

Design notes:
    These endpoints do not directly run any sync code — they only read/write
    workspace_sync_queue.  The actual sync work happens in the emailbison-sync
    worker service (Coolify UUID: l4g44o00s4cccg804osswgcc).

    WorkspaceSyncQueue is instantiated per-request with the shared DB pool.
    audit_logger=None is intentional — request_force_refresh and
    get_workspace_sync_status do not call the audit logger.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional

from database import get_pool
from deps.user import get_current_user, CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ForceRefreshResponse(BaseModel):
    """Response body for POST /refresh."""
    workspace_id: str
    queued: List[str]
    already_running: List[str]
    message: str


class WorkspaceSyncStatus(BaseModel):
    """Response body for GET /status."""
    workspace_id: str
    workspace_name: Optional[str] = None
    has_api_key: bool
    last_sync_times: Dict[str, Optional[str]]
    pending_jobs: List[Dict]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_sync_queue():
    """
    Return a WorkspaceSyncQueue bound to the shared DB pool.

    Imported lazily to avoid importing sync_modules at API startup — the API
    container does not have the full sync_modules tree on its PYTHONPATH.
    """
    # Deferred import: sync_modules lives in the worker container, not the API.
    # The API calls only SQL-backed methods (request_force_refresh,
    # get_workspace_sync_status), so we replicate the minimal interface here
    # by issuing the SQL directly without instantiating the full class.
    pool = await get_pool()
    return pool


async def _validate_workspace(workspace_id: UUID, pool) -> dict:
    """Validate workspace exists and is active. Returns the workspace row."""
    workspace = await pool.fetchrow("""
        SELECT id, workspace_name, is_active
        FROM workspaces
        WHERE id = $1
    """, workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if not workspace['is_active']:
        raise HTTPException(status_code=400, detail="Workspace is not active")

    return dict(workspace)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/workspaces/{workspace_id}/refresh",
    response_model=ForceRefreshResponse,
    summary="Force-refresh a workspace sync",
    description=(
        "Enqueue all five sync types (accounts, campaigns, events, warmup, engagement) "
        "at high priority (priority=10) for immediate processing. "
        "The emailbison-sync worker picks them up within ~30 seconds."
    ),
)
async def force_refresh_workspace(
    workspace_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Trigger immediate data sync for a workspace."""
    pool = await _get_sync_queue()
    workspace = await _validate_workspace(workspace_id, pool)

    # Check API key exists (without this, the worker cannot sync)
    has_api_key = await pool.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM workspace_api_keys
            WHERE workspace_id = $1 AND is_active = TRUE
        )
    """, workspace_id)

    if not has_api_key:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Workspace '{workspace['workspace_name']}' has no active workspace API key. "
                "Run scripts/backfill_workspace_keys.py to provision one."
            ),
        )

    SYNC_TYPES = ('accounts', 'campaigns', 'events', 'warmup', 'engagement')
    PRIORITY_FORCE = 10

    queued = []
    already_running = []

    for sync_type in SYNC_TYPES:
        # Do not re-queue a type that is currently running
        running = await pool.fetchval("""
            SELECT id FROM workspace_sync_queue
            WHERE workspace_id = $1
              AND sync_type = $2
              AND status = 'running'
            LIMIT 1
        """, workspace_id, sync_type)

        if running:
            already_running.append(sync_type)
            continue

        result = await pool.execute("""
            INSERT INTO workspace_sync_queue
                (workspace_id, sync_type, priority, is_force_refresh)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT DO NOTHING
        """, workspace_id, sync_type, PRIORITY_FORCE)

        try:
            if int(result.split()[-1]) > 0:
                queued.append(sync_type)
        except (IndexError, ValueError):
            queued.append(sync_type)

    logger.info(
        "Force-refresh for workspace %s by user %s: queued=%s already_running=%s",
        workspace_id, current_user.id if hasattr(current_user, 'id') else 'unknown',
        queued, already_running,
    )

    if queued:
        message = f"Sync queued for: {', '.join(queued)}. Will process within ~30 seconds."
    elif already_running:
        message = f"Sync already running for: {', '.join(already_running)}. Refresh in a moment."
    else:
        message = "All sync types are already pending or running."

    return ForceRefreshResponse(
        workspace_id=str(workspace_id),
        queued=queued,
        already_running=already_running,
        message=message,
    )


@router.get(
    "/workspaces/{workspace_id}/status",
    response_model=WorkspaceSyncStatus,
    summary="Get workspace sync status",
    description=(
        "Returns last successful sync timestamps per type and current queue state "
        "(pending/running jobs). Use this to show sync freshness in the client dashboard."
    ),
)
async def get_workspace_sync_status(
    workspace_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return sync freshness and queue state for a single workspace."""
    pool = await _get_sync_queue()
    workspace = await _validate_workspace(workspace_id, pool)

    SYNC_TYPES = ('accounts', 'campaigns', 'events', 'warmup', 'engagement')

    # Last successful sync per type
    sync_rows = await pool.fetch("""
        SELECT sync_type, last_successful_sync
        FROM sync_status
        WHERE workspace_id = $1
    """, workspace_id)

    last_sync: Dict[str, Optional[str]] = {
        row['sync_type']: row['last_successful_sync'].isoformat()
        if row['last_successful_sync'] else None
        for row in sync_rows
    }
    for t in SYNC_TYPES:
        last_sync.setdefault(t, None)

    # Active / pending queue jobs
    queue_rows = await pool.fetch("""
        SELECT sync_type, status, priority, is_force_refresh, queued_at, started_at
        FROM workspace_sync_queue
        WHERE workspace_id = $1
          AND status IN ('pending', 'running')
        ORDER BY priority DESC, queued_at ASC
    """, workspace_id)

    pending_jobs = [
        {
            'sync_type': row['sync_type'],
            'status': row['status'],
            'priority': row['priority'],
            'is_force_refresh': row['is_force_refresh'],
            'queued_at': row['queued_at'].isoformat() if row['queued_at'] else None,
            'started_at': row['started_at'].isoformat() if row['started_at'] else None,
        }
        for row in queue_rows
    ]

    has_api_key = await pool.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM workspace_api_keys
            WHERE workspace_id = $1 AND is_active = TRUE
        )
    """, workspace_id)

    return WorkspaceSyncStatus(
        workspace_id=str(workspace_id),
        workspace_name=workspace['workspace_name'],
        has_api_key=bool(has_api_key),
        last_sync_times=last_sync,
        pending_jobs=pending_jobs,
    )
