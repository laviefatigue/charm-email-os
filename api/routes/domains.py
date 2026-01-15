"""
Domain routes - Read from OwnRBL domains table
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
import logging

from database import fetch_all, fetch_one, execute
from models.domain import Domain, DomainCreate, DomainList, DomainHealth, DomainGenerateRequest

router = APIRouter()
logger = logging.getLogger(__name__)


def calculate_health_state(health_score: Optional[float], blacklist_count: int) -> str:
    """Calculate domain health state from metrics"""
    if health_score is None:
        return "unknown"
    if blacklist_count > 5 or health_score < 50:
        return "critical"
    if blacklist_count > 0 or health_score < 80:
        return "warning"
    return "healthy"


@router.get("", response_model=DomainList)
async def list_domains(
    workspace_id: Optional[UUID] = None,
    client_id: Optional[UUID] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """List domains, optionally filtered by workspace or client"""
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
        conditions.append(f"d.workspace_id = ${param_idx}")
        params.append(workspace_id)
        param_idx += 1

    # Note: status column doesn't exist in DB, skip filtering by status
    # The status parameter is accepted but not used in the query

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Get total count
    count_query = f"SELECT COUNT(*) as total FROM domains d {where_clause}"
    count_result = await fetch_one(count_query, *params)
    total = count_result["total"] if count_result else 0

    # Get domains with health metrics (using only columns that exist in DB)
    # Join with clients to get client_id for frontend filtering
    # Include inbox health breakdown counts and blacklist names
    query = f"""
        SELECT
            d.id,
            d.workspace_id,
            c.id as client_id,
            d.domain_name,
            'active' as status,
            d.latest_health_score,
            d.latest_blacklist_count,
            d.latest_whitelist_count,
            d.is_clean,
            d.last_checked_at,
            NULL as flagged_at,
            NULL as dead_at,
            d.created_at,
            d.updated_at,
            COALESCE(
                (SELECT COUNT(*) FROM sender_accounts sa
                 WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
                 AND sa.workspace_id = d.workspace_id),
                0
            ) as inbox_count,
            COALESCE(
                (SELECT COUNT(*) FROM sender_accounts sa
                 WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
                 AND sa.workspace_id = d.workspace_id
                 AND COALESCE(sa.inbox_state, 'live') = 'live'),
                0
            ) as live_inbox_count,
            COALESCE(
                (SELECT COUNT(*) FROM sender_accounts sa
                 WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
                 AND sa.workspace_id = d.workspace_id
                 AND sa.inbox_state = 'dead'),
                0
            ) as dead_inbox_count,
            (SELECT ARRAY_AGG(rd.rbl_name ORDER BY rd.severity DESC, rd.rbl_name)
             FROM domain_check_results dcr
             JOIN rbl_definitions rd ON dcr.rbl_id = rd.id
             WHERE dcr.domain_id = d.id AND dcr.is_listed = true
            ) as blacklist_names
        FROM domains d
        LEFT JOIN clients c ON c.workspace_id = d.workspace_id
        {where_clause}
        ORDER BY d.domain_name
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([page_size, offset])

    rows = await fetch_all(query, *params)

    # Add computed health_state
    items = []
    for row in rows:
        domain = dict(row)
        domain["health_state"] = calculate_health_state(
            domain.get("latest_health_score"),
            domain.get("latest_blacklist_count", 0) or 0
        )
        items.append(Domain(**domain))

    return DomainList(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{domain_id}", response_model=Domain)
async def get_domain(domain_id: UUID):
    """Get a domain by ID"""
    query = """
        SELECT
            d.id,
            d.workspace_id,
            d.domain_name,
            'active' as status,
            d.latest_health_score,
            d.latest_blacklist_count,
            d.latest_whitelist_count,
            d.is_clean,
            d.last_checked_at,
            NULL as flagged_at,
            NULL as dead_at,
            d.created_at,
            d.updated_at,
            COALESCE(
                (SELECT COUNT(*) FROM sender_accounts sa
                 WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
                 AND sa.workspace_id = d.workspace_id),
                0
            ) as inbox_count
        FROM domains d
        WHERE d.id = $1
    """
    row = await fetch_one(query, domain_id)

    if not row:
        raise HTTPException(status_code=404, detail="Domain not found")

    domain = dict(row)
    domain["health_state"] = calculate_health_state(
        domain.get("latest_health_score"),
        domain.get("latest_blacklist_count", 0) or 0
    )

    return Domain(**domain)


@router.get("/{domain_id}/health", response_model=DomainHealth)
async def get_domain_health(domain_id: UUID):
    """Get detailed health information for a domain"""
    # Get domain with health metrics
    domain = await fetch_one("""
        SELECT
            id as domain_id,
            domain_name,
            COALESCE(latest_health_score, 100) as health_score,
            COALESCE(latest_blacklist_count, 0) as blacklist_count,
            COALESCE(latest_whitelist_count, 0) as whitelist_count,
            COALESCE(is_clean, true) as is_clean,
            last_checked_at
        FROM domains
        WHERE id = $1
    """, domain_id)

    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Get RBL check results
    rbl_results = await fetch_all("""
        SELECT
            rd.rbl_name,
            rd.severity,
            dcr.is_listed,
            dcr.checked_at
        FROM domain_check_results dcr
        JOIN rbl_definitions rd ON dcr.rbl_id = rd.id
        WHERE dcr.domain_id = $1
        ORDER BY rd.severity DESC, rd.rbl_name
        LIMIT 50
    """, domain_id)

    # Get critical listings
    critical_listings = [
        r["rbl_name"] for r in rbl_results
        if r["is_listed"] and r["severity"] in ("critical", "high")
    ]

    health_state = calculate_health_state(
        domain["health_score"],
        domain["blacklist_count"]
    )

    return DomainHealth(
        **domain,
        health_state=health_state,
        rbl_results=[dict(r) for r in rbl_results],
        critical_listings=critical_listings if critical_listings else None
    )


@router.get("/{domain_id}/inboxes")
async def get_domain_inboxes(domain_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    """Get inboxes for a domain"""
    # Get domain name first
    domain = await fetch_one("SELECT domain_name, workspace_id FROM domains WHERE id = $1", domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    offset = (page - 1) * page_size

    # Get inboxes where email ends with domain - join warmup snapshots for warmup data
    query = """
        SELECT
            sa.id,
            sa.workspace_id,
            sa.emailbison_account_id,
            sa.email_address,
            NULL as first_name,
            NULL as last_name,
            sa.display_name,
            COALESCE(sa.status, 'active') as status,
            COALESCE(sa.inbox_state, 'live') as inbox_state,
            NULL as esp_type,
            COALESCE(ws.warmup_enabled, false) as warmup_enabled,
            ws.warmup_score,
            NULL as daily_send_limit,
            COALESCE(sa.hard_bounces_24h, 0) as hard_bounces_24h,
            COALESCE(sa.hard_bounces_7d, 0) as hard_bounces_7d,
            0 as soft_bounces_7d,
            COALESCE(sa.total_sends_7d, 0) as total_sends_7d,
            NULL as removal_tag,
            NULL as removal_tagged_at,
            NULL as removed_at,
            sa.created_at,
            sa.updated_at,
            sa.health_score
        FROM sender_accounts sa
        LEFT JOIN LATERAL (
            SELECT warmup_enabled, warmup_score
            FROM sender_warmup_snapshots
            WHERE sender_account_id = sa.id
            ORDER BY snapshot_timestamp DESC
            LIMIT 1
        ) ws ON true
        WHERE sa.workspace_id = $1
        AND SPLIT_PART(sa.email_address, '@', 2) = $2
        ORDER BY sa.email_address
        LIMIT $3 OFFSET $4
    """
    rows = await fetch_all(query, domain["workspace_id"], domain["domain_name"], page_size, offset)

    # Get count
    count = await fetch_one("""
        SELECT COUNT(*) as total
        FROM sender_accounts
        WHERE workspace_id = $1
        AND SPLIT_PART(email_address, '@', 2) = $2
    """, domain["workspace_id"], domain["domain_name"])

    return {
        "items": [dict(r) for r in rows],
        "total": count["total"] if count else 0,
        "page": page,
        "page_size": page_size
    }


@router.post("/{domain_id}/approve", response_model=Domain)
async def approve_domain(domain_id: UUID):
    """Approve a pending domain (status column doesn't exist, just update updated_at)"""
    result = await fetch_one(
        "UPDATE domains SET updated_at = NOW() WHERE id = $1 RETURNING id",
        domain_id
    )

    if not result:
        raise HTTPException(status_code=404, detail="Domain not found")

    return await get_domain(domain_id)


@router.post("/generate")
async def generate_domains(request: DomainGenerateRequest):
    """Generate domain entries from onboarding data"""
    # Get client's workspace
    client = await fetch_one("SELECT workspace_id FROM clients WHERE id = $1", request.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client not linked to a workspace")

    # Check if domain already exists
    existing = await fetch_one(
        "SELECT id FROM domains WHERE workspace_id = $1 AND domain_name = $2",
        client["workspace_id"],
        request.primary_domain
    )

    if existing:
        return {"message": "Domain already exists", "domain_id": existing["id"]}

    # Create domain (status column doesn't exist, just insert workspace_id and domain_name)
    result = await fetch_one("""
        INSERT INTO domains (workspace_id, domain_name)
        VALUES ($1, $2)
        RETURNING id, workspace_id, domain_name, created_at, updated_at
    """, client["workspace_id"], request.primary_domain)

    return {
        "message": "Domain created",
        "domain": dict(result)
    }
