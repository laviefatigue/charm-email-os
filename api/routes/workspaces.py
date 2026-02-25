"""
Workspace routes - Read-only from OwnRBL workspaces table
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
import logging

from database import fetch_all, fetch_one
from models.workspace import Workspace, WorkspaceList, WorkspaceSummary

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=WorkspaceList)
async def list_workspaces(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = None
):
    """List all OwnRBL workspaces"""
    offset = (page - 1) * page_size

    # Base query
    where_clause = ""
    params = []
    param_idx = 1

    if search:
        where_clause = f"WHERE workspace_name ILIKE ${param_idx}"
        params.append(f"%{search}%")
        param_idx += 1

    # Get total count
    count_query = f"""
        SELECT COUNT(*) as total
        FROM workspaces
        {where_clause}
    """
    count_result = await fetch_one(count_query, *params)
    total = count_result["total"] if count_result else 0

    # Get workspaces with counts
    query = f"""
        SELECT
            w.id,
            w.workspace_name,
            w.emailbison_workspace_id,
            w.sender_account_count,
            w.automation_enabled,
            w.created_at,
            w.updated_at,
            COALESCE(
                (SELECT COUNT(*) FROM emailbison_campaigns ec WHERE ec.workspace_id = w.id),
                0
            ) as campaign_count
        FROM workspaces w
        {where_clause}
        ORDER BY w.workspace_name
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([page_size, offset])

    rows = await fetch_all(query, *params)

    return WorkspaceList(
        items=[Workspace(**row) for row in rows],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/summary", response_model=list[WorkspaceSummary])
async def list_workspaces_summary():
    """Get compact workspace list for dropdowns"""
    query = """
        SELECT
            w.id,
            w.workspace_name,
            w.sender_account_count,
            COALESCE(
                (SELECT COUNT(*) FROM emailbison_campaigns ec WHERE ec.workspace_id = w.id),
                0
            ) as campaign_count
        FROM workspaces w
        ORDER BY w.workspace_name
    """
    rows = await fetch_all(query)
    return [WorkspaceSummary(**row) for row in rows]


@router.get("/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: UUID):
    """Get a single workspace by ID"""
    query = """
        SELECT
            w.id,
            w.workspace_name,
            w.emailbison_workspace_id,
            w.sender_account_count,
            w.automation_enabled,
            w.created_at,
            w.updated_at,
            COALESCE(
                (SELECT COUNT(*) FROM emailbison_campaigns ec WHERE ec.workspace_id = w.id),
                0
            ) as campaign_count
        FROM workspaces w
        WHERE w.id = $1
    """
    row = await fetch_one(query, workspace_id)

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return Workspace(**row)


@router.get("/{workspace_id}/stats")
async def get_workspace_stats(workspace_id: UUID):
    """Get detailed statistics for a workspace"""
    # Verify workspace exists
    workspace = await fetch_one("SELECT id FROM workspaces WHERE id = $1", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Get inbox stats
    inbox_stats = await fetch_one("""
        SELECT
            COUNT(*) as total_inboxes,
            COUNT(*) FILTER (WHERE inbox_state = 'live') as live_inboxes,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_inboxes,
            COUNT(*) FILTER (WHERE warmup_enabled = true) as warmup_inboxes
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    # Get domain stats
    domain_stats = await fetch_one("""
        SELECT
            COUNT(*) as total_domains,
            COUNT(*) FILTER (WHERE is_clean = true) as clean_domains,
            AVG(latest_health_score) as avg_health_score
        FROM domains
        WHERE workspace_id = $1
    """, workspace_id)

    # Get campaign stats
    campaign_stats = await fetch_one("""
        SELECT
            COUNT(*) as total_campaigns,
            COUNT(*) FILTER (WHERE campaign_status = 'active') as active_campaigns,
            SUM(total_leads) as total_leads,
            SUM(emails_sent) as total_emails_sent
        FROM emailbison_campaigns
        WHERE workspace_id = $1
    """, workspace_id)

    return {
        "workspace_id": workspace_id,
        "inboxes": inbox_stats or {},
        "domains": domain_stats or {},
        "campaigns": campaign_stats or {}
    }
