"""
Inbox routes - Maps to OwnRBL sender_accounts table
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
import logging

from database import fetch_all, fetch_one, execute
from models.inbox import (
    Inbox, InboxCreate, InboxList, InboxHealth,
    InboxKillRequest, InboxGenerateRequest
)

router = APIRouter()
logger = logging.getLogger(__name__)


def calculate_inbox_health_state(inbox: dict) -> str:
    """Calculate inbox health state from metrics"""
    if inbox.get("inbox_state") == "dead":
        return "dead"

    hard_bounces_24h = inbox.get("hard_bounces_24h") or 0
    hard_bounces_7d = inbox.get("hard_bounces_7d") or 0

    # Critical conditions
    if hard_bounces_24h >= 3:
        return "critical"

    # Warning conditions
    if hard_bounces_24h >= 1 or hard_bounces_7d >= 5:
        return "warning"

    return "healthy"


@router.get("", response_model=InboxList)
async def list_inboxes(
    workspace_id: Optional[UUID] = None,
    client_id: Optional[UUID] = None,
    domain_id: Optional[UUID] = None,
    status: Optional[str] = None,
    inbox_state: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """List inboxes (sender_accounts), optionally filtered"""
    offset = (page - 1) * page_size

    # Build WHERE clause
    conditions = []
    params = []
    param_idx = 1

    # If client_id provided, get workspace_id from client
    if client_id:
        client = await fetch_one("SELECT workspace_id FROM clients WHERE id = $1", client_id)
        if client and client["workspace_id"]:
            workspace_id = client["workspace_id"]

    if workspace_id:
        conditions.append(f"sa.workspace_id = ${param_idx}")
        params.append(workspace_id)
        param_idx += 1

    if domain_id:
        # Get domain name
        domain = await fetch_one("SELECT domain_name FROM domains WHERE id = $1", domain_id)
        if domain:
            conditions.append(f"SPLIT_PART(sa.email_address, '@', 2) = ${param_idx}")
            params.append(domain["domain_name"])
            param_idx += 1

    if status:
        conditions.append(f"sa.status = ${param_idx}")
        params.append(status)
        param_idx += 1

    if inbox_state:
        conditions.append(f"sa.inbox_state = ${param_idx}")
        params.append(inbox_state)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Save condition params before adding LIMIT/OFFSET
    condition_params = params.copy()

    # Get total count
    count_query = f"SELECT COUNT(*) as total FROM sender_accounts sa {where_clause}"
    count_result = await fetch_one(count_query, *condition_params)
    total = count_result["total"] if count_result else 0

    # Get health counts (removed_at column doesn't exist, using inbox_state only)
    health_counts_query = f"""
        SELECT
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND COALESCE(hard_bounces_24h, 0) = 0) as healthy,
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND (COALESCE(hard_bounces_24h, 0) >= 1 OR COALESCE(hard_bounces_7d, 0) >= 5)) as warning,
            COUNT(*) FILTER (WHERE COALESCE(hard_bounces_24h, 0) >= 3) as critical,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead
        FROM sender_accounts sa
        {where_clause}
    """
    health_counts = await fetch_one(health_counts_query, *condition_params)

    # Get inboxes - using only columns that definitely exist in sender_accounts
    query = f"""
        SELECT
            sa.id,
            sa.workspace_id,
            sa.emailbison_account_id,
            sa.email_address,
            NULL as first_name,
            NULL as last_name,
            NULL as display_name,
            'active' as status,
            COALESCE(sa.inbox_state, 'live') as inbox_state,
            NULL as esp_type,
            false as warmup_enabled,
            NULL as warmup_score,
            NULL as warmup_progress,
            sa.daily_send_limit,
            sa.hard_bounces_24h,
            sa.hard_bounces_7d,
            sa.soft_bounces_7d,
            sa.total_sends_7d,
            NULL as removal_tag,
            NULL as removal_tagged_at,
            NULL as removed_at,
            sa.created_at,
            sa.updated_at,
            SPLIT_PART(sa.email_address, '@', 2) as domain_name
        FROM sender_accounts sa
        {where_clause}
        ORDER BY sa.email_address
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([page_size, offset])

    rows = await fetch_all(query, *params)

    # Add computed health_state
    items = []
    for row in rows:
        inbox = dict(row)
        inbox["health_state"] = calculate_inbox_health_state(inbox)
        # Calculate bounce_rate_7d
        total_sends = inbox.get("total_sends_7d") or 0
        hard_bounces = inbox.get("hard_bounces_7d") or 0
        inbox["bounce_rate_7d"] = (hard_bounces / total_sends * 100) if total_sends > 0 else 0
        items.append(Inbox(**inbox))

    return InboxList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        healthy_count=health_counts["healthy"] if health_counts else 0,
        warning_count=health_counts["warning"] if health_counts else 0,
        critical_count=health_counts["critical"] if health_counts else 0,
        dead_count=health_counts["dead"] if health_counts else 0
    )


@router.get("/{inbox_id}", response_model=Inbox)
async def get_inbox(inbox_id: UUID):
    """Get an inbox by ID"""
    query = """
        SELECT
            sa.id,
            sa.workspace_id,
            sa.emailbison_account_id,
            sa.email_address,
            NULL as first_name,
            NULL as last_name,
            NULL as display_name,
            'active' as status,
            COALESCE(sa.inbox_state, 'live') as inbox_state,
            NULL as esp_type,
            false as warmup_enabled,
            NULL as warmup_score,
            NULL as warmup_progress,
            sa.daily_send_limit,
            sa.hard_bounces_24h,
            sa.hard_bounces_7d,
            sa.soft_bounces_7d,
            sa.total_sends_7d,
            NULL as removal_tag,
            NULL as removal_tagged_at,
            NULL as removed_at,
            sa.created_at,
            sa.updated_at,
            SPLIT_PART(sa.email_address, '@', 2) as domain_name
        FROM sender_accounts sa
        WHERE sa.id = $1
    """
    row = await fetch_one(query, inbox_id)

    if not row:
        raise HTTPException(status_code=404, detail="Inbox not found")

    inbox = dict(row)
    inbox["health_state"] = calculate_inbox_health_state(inbox)
    total_sends = inbox.get("total_sends_7d") or 0
    hard_bounces = inbox.get("hard_bounces_7d") or 0
    inbox["bounce_rate_7d"] = (hard_bounces / total_sends * 100) if total_sends > 0 else 0

    return Inbox(**inbox)


@router.get("/{inbox_id}/health", response_model=InboxHealth)
async def get_inbox_health(inbox_id: UUID):
    """Get detailed health metrics for an inbox"""
    inbox = await get_inbox(inbox_id)

    # Determine if at risk (approaching kill threshold)
    at_risk = (
        (inbox.hard_bounces_24h or 0) >= 2 or
        (inbox.hard_bounces_7d or 0) >= 4 or
        (inbox.bounce_rate_7d or 0) >= 3.0
    )

    return InboxHealth(
        inbox_id=inbox.id,
        email_address=inbox.email_address,
        health_state=inbox.health_state,
        inbox_state=inbox.inbox_state,
        warmup_enabled=inbox.warmup_enabled or False,
        warmup_score=inbox.warmup_score,
        warmup_progress=inbox.warmup_progress,
        hard_bounces_24h=inbox.hard_bounces_24h or 0,
        hard_bounces_7d=inbox.hard_bounces_7d or 0,
        soft_bounces_7d=inbox.soft_bounces_7d or 0,
        total_sends_7d=inbox.total_sends_7d or 0,
        bounce_rate_7d=inbox.bounce_rate_7d or 0.0,
        removal_tag=inbox.removal_tag,
        removal_tagged_at=inbox.removal_tagged_at,
        at_risk=at_risk
    )


@router.post("/{inbox_id}/kill")
async def kill_inbox(inbox_id: UUID, request: InboxKillRequest):
    """Manually kill an inbox"""
    # Get inbox to verify it exists
    inbox = await fetch_one("SELECT id, email_address, workspace_id FROM sender_accounts WHERE id = $1", inbox_id)
    if not inbox:
        raise HTTPException(status_code=404, detail="Inbox not found")

    # Update inbox state (only inbox_state column exists)
    await execute("""
        UPDATE sender_accounts
        SET
            inbox_state = 'dead',
            updated_at = NOW()
        WHERE id = $1
    """, inbox_id)

    return {"message": f"Inbox {inbox['email_address']} killed", "kill_trigger": request.kill_trigger}


@router.post("/{inbox_id}/approve", response_model=Inbox)
async def approve_inbox(inbox_id: UUID):
    """Approve a pending inbox"""
    result = await fetch_one(
        "UPDATE sender_accounts SET status = 'active', updated_at = NOW() WHERE id = $1 RETURNING id",
        inbox_id
    )

    if not result:
        raise HTTPException(status_code=404, detail="Inbox not found")

    return await get_inbox(inbox_id)


@router.post("/generate")
async def generate_inboxes(request: InboxGenerateRequest):
    """Generate inbox entries from onboarding data"""
    # Get client's workspace
    client = await fetch_one("SELECT workspace_id FROM clients WHERE id = $1", request.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client not linked to a workspace")

    # Get domain
    domain = await fetch_one("SELECT domain_name FROM domains WHERE id = $1", request.domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    created = []
    for first_name in request.first_names:
        email = f"{first_name.lower()}@{domain['domain_name']}"

        # Check if exists
        existing = await fetch_one(
            "SELECT id FROM sender_accounts WHERE workspace_id = $1 AND email_address = $2",
            client["workspace_id"], email
        )

        if existing:
            continue

        # Create inbox
        result = await fetch_one("""
            INSERT INTO sender_accounts (workspace_id, email_address, first_name, status, inbox_state)
            VALUES ($1, $2, $3, 'pending', 'live')
            RETURNING id, email_address, first_name
        """, client["workspace_id"], email, first_name)

        if result:
            created.append(dict(result))

    return {
        "message": f"Created {len(created)} inboxes",
        "inboxes": created
    }
