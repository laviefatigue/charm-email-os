"""
Campaign routes - Maps to OwnRBL emailbison_campaigns table
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
import logging

from database import fetch_all, fetch_one, execute
from models.campaign import (
    Campaign, CampaignCreate, CampaignList,
    CampaignMetrics, CampaignStatusUpdate
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=CampaignList)
async def list_campaigns(
    workspace_id: Optional[UUID] = None,
    client_id: Optional[UUID] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """List campaigns, optionally filtered"""
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
        conditions.append(f"c.workspace_id = ${param_idx}")
        params.append(workspace_id)
        param_idx += 1

    if status:
        conditions.append(f"c.campaign_status = ${param_idx}")
        params.append(status)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Get total count
    count_query = f"SELECT COUNT(*) as total FROM emailbison_campaigns c {where_clause}"
    count_result = await fetch_one(count_query, *params)
    total = count_result["total"] if count_result else 0

    # Get status counts
    status_counts_query = f"""
        SELECT
            COUNT(*) FILTER (WHERE campaign_status = 'active') as active,
            COUNT(*) FILTER (WHERE campaign_status = 'paused') as paused,
            COUNT(*) FILTER (WHERE campaign_status = 'completed') as completed
        FROM emailbison_campaigns c
        {where_clause}
    """
    status_counts = await fetch_one(status_counts_query, *params[:param_idx-1] if params else [])

    # Get campaigns - join latest snapshot for metrics not on emailbison_campaigns
    query = f"""
        SELECT
            c.id,
            c.workspace_id,
            c.emailbison_campaign_id,
            c.campaign_name,
            NULL as industry,
            NULL as segment,
            NULL as angle,
            COALESCE(c.campaign_status, 'active') as campaign_status,
            COALESCE(c.total_leads, 0) as total_leads,
            COALESCE(c.total_leads_contacted, 0) as total_leads_contacted,
            0 as leads_capacity,
            COALESCE(cs.emails_sent, c.emails_sent, 0) as emails_sent,
            COALESCE(cs.unique_opens, 0) as unique_opens,
            COALESCE(cs.unique_replies, 0) as unique_replies,
            COALESCE(cs.bounced, 0) as bounced,
            COALESCE(cs.unsubscribed, 0) as unsubscribed,
            0 as spam_complaints,
            COALESCE(cs.reply_rate, 0) as reply_rate,
            COALESCE(cs.open_rate, 0) as open_rate,
            COALESCE(cs.bounce_rate, 0) as bounce_rate,
            c.created_at,
            c.updated_at,
            c.last_snapshot_at
        FROM emailbison_campaigns c
        LEFT JOIN LATERAL (
            SELECT s.emails_sent, s.unique_opens, s.unique_replies,
                   s.bounced, s.unsubscribed, s.reply_rate, s.open_rate, s.bounce_rate
            FROM campaign_snapshots s
            WHERE s.campaign_id = c.id
            ORDER BY s.snapshot_timestamp DESC
            LIMIT 1
        ) cs ON true
        {where_clause}
        ORDER BY c.created_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([page_size, offset])

    rows = await fetch_all(query, *params)

    # Calculate completion percentage
    items = []
    for row in rows:
        campaign = dict(row)
        total_leads = campaign.get("total_leads") or 0
        contacted = campaign.get("total_leads_contacted") or 0
        campaign["completion_percentage"] = (contacted / total_leads * 100) if total_leads > 0 else 0
        items.append(Campaign(**campaign))

    return CampaignList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        active_count=status_counts["active"] if status_counts else 0,
        paused_count=status_counts["paused"] if status_counts else 0,
        completed_count=status_counts["completed"] if status_counts else 0
    )


@router.get("/{campaign_id}", response_model=Campaign)
async def get_campaign(campaign_id: UUID):
    """Get a campaign by ID"""
    query = """
        SELECT
            c.id,
            c.workspace_id,
            c.emailbison_campaign_id,
            c.campaign_name,
            NULL as industry,
            NULL as segment,
            NULL as angle,
            COALESCE(c.campaign_status, 'active') as campaign_status,
            COALESCE(c.total_leads, 0) as total_leads,
            COALESCE(c.total_leads_contacted, 0) as total_leads_contacted,
            0 as leads_capacity,
            COALESCE(cs.emails_sent, c.emails_sent, 0) as emails_sent,
            COALESCE(cs.unique_opens, 0) as unique_opens,
            COALESCE(cs.unique_replies, 0) as unique_replies,
            COALESCE(cs.bounced, 0) as bounced,
            COALESCE(cs.unsubscribed, 0) as unsubscribed,
            0 as spam_complaints,
            COALESCE(cs.reply_rate, 0) as reply_rate,
            COALESCE(cs.open_rate, 0) as open_rate,
            COALESCE(cs.bounce_rate, 0) as bounce_rate,
            c.created_at,
            c.updated_at,
            c.last_snapshot_at
        FROM emailbison_campaigns c
        LEFT JOIN LATERAL (
            SELECT s.emails_sent, s.unique_opens, s.unique_replies,
                   s.bounced, s.unsubscribed, s.reply_rate, s.open_rate, s.bounce_rate
            FROM campaign_snapshots s
            WHERE s.campaign_id = c.id
            ORDER BY s.snapshot_timestamp DESC
            LIMIT 1
        ) cs ON true
        WHERE c.id = $1
    """
    row = await fetch_one(query, campaign_id)

    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign = dict(row)
    total_leads = campaign.get("total_leads") or 0
    contacted = campaign.get("total_leads_contacted") or 0
    campaign["completion_percentage"] = (contacted / total_leads * 100) if total_leads > 0 else 0

    return Campaign(**campaign)


@router.get("/{campaign_id}/metrics", response_model=CampaignMetrics)
async def get_campaign_metrics(campaign_id: UUID):
    """Get detailed metrics for a campaign"""
    campaign = await get_campaign(campaign_id)

    # Note: campaign_snapshots and campaign_events tables don't exist in OwnRBL
    # Return metrics based on campaign data only

    # Calculate days active and daily rate
    days_active = 0
    daily_send_rate = 0.0
    if campaign.created_at:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        created = campaign.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        days_active = max(1, (now - created).days)
        daily_send_rate = (campaign.emails_sent or 0) / days_active

    return CampaignMetrics(
        campaign_id=campaign.id,
        campaign_name=campaign.campaign_name,
        emails_sent=campaign.emails_sent or 0,
        total_leads=campaign.total_leads or 0,
        leads_contacted=campaign.total_leads_contacted or 0,
        unique_opens=campaign.unique_opens or 0,
        unique_replies=campaign.unique_replies or 0,
        interested_replies=0,
        automated_replies=0,
        bounced=campaign.bounced or 0,
        unsubscribed=campaign.unsubscribed or 0,
        spam_complaints=campaign.spam_complaints or 0,
        reply_rate=campaign.reply_rate or 0.0,
        open_rate=campaign.open_rate or 0.0,
        bounce_rate=campaign.bounce_rate or 0.0,
        interested_rate=0.0,
        days_active=days_active,
        daily_send_rate=daily_send_rate,
        snapshots=None
    )


@router.post("", response_model=Campaign)
async def create_campaign(campaign: CampaignCreate):
    """Create a new campaign (from idea)"""
    query = """
        INSERT INTO emailbison_campaigns (
            workspace_id, campaign_name, campaign_status
        )
        VALUES ($1, $2, 'draft')
        RETURNING id, workspace_id, campaign_name,
                  NULL as industry, NULL as segment, NULL as angle,
                  campaign_status,
                  COALESCE(total_leads, 0) as total_leads,
                  COALESCE(total_leads_contacted, 0) as total_leads_contacted,
                  0 as leads_capacity,
                  COALESCE(emails_sent, 0) as emails_sent,
                  0 as unique_opens, 0 as unique_replies,
                  0 as bounced, 0 as unsubscribed, 0 as spam_complaints,
                  0.0 as reply_rate, 0.0 as open_rate, 0.0 as bounce_rate,
                  created_at, updated_at
    """
    row = await fetch_one(
        query,
        campaign.workspace_id,
        campaign.campaign_name,
    )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create campaign")

    return Campaign(**row, completion_percentage=0)


@router.put("/{campaign_id}/status", response_model=Campaign)
async def update_campaign_status(campaign_id: UUID, update: CampaignStatusUpdate):
    """Update campaign status (run/pause/complete)"""
    result = await fetch_one(
        "UPDATE emailbison_campaigns SET campaign_status = $1, updated_at = NOW() WHERE id = $2 RETURNING id",
        update.status,
        campaign_id
    )

    if not result:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return await get_campaign(campaign_id)


@router.post("/{campaign_id}/run", response_model=Campaign)
async def run_campaign(campaign_id: UUID):
    """Start/resume a campaign"""
    return await update_campaign_status(campaign_id, CampaignStatusUpdate(status="active"))


@router.post("/{campaign_id}/pause", response_model=Campaign)
async def pause_campaign(campaign_id: UUID):
    """Pause a campaign"""
    return await update_campaign_status(campaign_id, CampaignStatusUpdate(status="paused"))


@router.get("/{campaign_id}/events")
async def get_campaign_events(
    campaign_id: UUID,
    event_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """Get campaign events (replies, bounces, etc.)"""
    offset = (page - 1) * page_size

    conditions = ["campaign_id = $1"]
    params = [campaign_id]
    param_idx = 2

    if event_type:
        conditions.append(f"event_type = ${param_idx}")
        params.append(event_type)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}"

    # Get count
    count = await fetch_one(f"SELECT COUNT(*) as total FROM campaign_events {where_clause}", *params)

    # Get events
    query = f"""
        SELECT
            id,
            campaign_id,
            event_type,
            lead_email,
            lead_name,
            lead_company,
            event_data,
            event_timestamp,
            created_at
        FROM campaign_events
        {where_clause}
        ORDER BY event_timestamp DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([page_size, offset])

    rows = await fetch_all(query, *params)

    return {
        "items": [dict(r) for r in rows],
        "total": count["total"] if count else 0,
        "page": page,
        "page_size": page_size
    }
