"""
Lead routes - CRUD for the new leads table
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
import json
import logging

from database import fetch_all, fetch_one, execute, execute_many
from models.lead import (
    Lead, LeadCreate, LeadUpdate, LeadBulkCreate,
    LeadList, LeadStatusUpdate, LeadBulkUploadResult
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=LeadList)
async def list_leads(
    campaign_id: Optional[UUID] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """List leads, optionally filtered by campaign or status"""
    offset = (page - 1) * page_size

    # Build WHERE clause
    conditions = []
    params = []
    param_idx = 1

    if campaign_id:
        conditions.append(f"l.campaign_id = ${param_idx}")
        params.append(campaign_id)
        param_idx += 1

    if status:
        conditions.append(f"l.status = ${param_idx}")
        params.append(status)
        param_idx += 1

    if search:
        conditions.append(f"(l.email ILIKE ${param_idx} OR l.first_name ILIKE ${param_idx} OR l.company ILIKE ${param_idx})")
        params.append(f"%{search}%")
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Get total count
    count_query = f"SELECT COUNT(*) as total FROM leads l {where_clause}"
    count_result = await fetch_one(count_query, *params)
    total = count_result["total"] if count_result else 0

    # Get status counts
    status_counts_query = f"""
        SELECT
            COUNT(*) FILTER (WHERE status = 'queued') as queued,
            COUNT(*) FILTER (WHERE status = 'contacted') as contacted,
            COUNT(*) FILTER (WHERE status = 'replied') as replied,
            COUNT(*) FILTER (WHERE status = 'bounced') as bounced,
            COUNT(*) FILTER (WHERE status = 'unsubscribed') as unsubscribed
        FROM leads l
        {where_clause}
    """
    status_counts = await fetch_one(status_counts_query, *params[:param_idx-1] if params else [])

    # Get leads
    query = f"""
        SELECT
            l.id,
            l.campaign_id,
            l.email,
            l.first_name,
            l.last_name,
            l.company,
            l.title,
            l.linkedin_url,
            l.phone,
            l.website,
            l.location,
            l.industry,
            l.company_size,
            l.notes,
            l.tags,
            l.custom_fields,
            l.status,
            l.source,
            l.contacted_at,
            l.enriched_at,
            l.raw_data,
            l.created_at,
            l.updated_at
        FROM leads l
        {where_clause}
        ORDER BY l.created_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([page_size, offset])

    rows = await fetch_all(query, *params)

    return LeadList(
        items=[Lead(**row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        queued_count=status_counts["queued"] if status_counts else 0,
        contacted_count=status_counts["contacted"] if status_counts else 0,
        replied_count=status_counts["replied"] if status_counts else 0,
        bounced_count=status_counts["bounced"] if status_counts else 0,
        unsubscribed_count=status_counts["unsubscribed"] if status_counts else 0
    )


@router.get("/{lead_id}", response_model=Lead)
async def get_lead(lead_id: UUID):
    """Get a lead by ID"""
    query = """
        SELECT
            id,
            campaign_id,
            email,
            first_name,
            last_name,
            company,
            title,
            linkedin_url,
            phone,
            website,
            location,
            industry,
            company_size,
            notes,
            tags,
            custom_fields,
            status,
            source,
            contacted_at,
            enriched_at,
            raw_data,
            created_at,
            updated_at
        FROM leads
        WHERE id = $1
    """
    row = await fetch_one(query, lead_id)

    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")

    return Lead(**row)


@router.post("", response_model=Lead)
async def create_lead(lead: LeadCreate):
    """Create a single lead"""
    # Verify campaign exists
    campaign = await fetch_one("SELECT id FROM emailbison_campaigns WHERE id = $1", lead.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Check for duplicate
    existing = await fetch_one(
        "SELECT id FROM leads WHERE campaign_id = $1 AND email = $2",
        lead.campaign_id, lead.email
    )
    if existing:
        raise HTTPException(status_code=409, detail="Lead with this email already exists in campaign")

    query = """
        INSERT INTO leads (
            campaign_id, email, first_name, last_name, company, title,
            linkedin_url, phone, website, location, industry, company_size,
            notes, tags, custom_fields, source
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        RETURNING *
    """
    row = await fetch_one(
        query,
        lead.campaign_id, lead.email, lead.first_name, lead.last_name,
        lead.company, lead.title, lead.linkedin_url, lead.phone,
        lead.website, lead.location, lead.industry, lead.company_size,
        lead.notes, lead.tags,
        json.dumps(lead.custom_fields) if lead.custom_fields else None,
        lead.source
    )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create lead")

    return Lead(**row)


@router.post("/bulk", response_model=LeadBulkUploadResult)
async def bulk_create_leads(bulk: LeadBulkCreate):
    """Bulk create leads from CSV upload"""
    # Verify campaign exists
    campaign = await fetch_one("SELECT id FROM emailbison_campaigns WHERE id = $1", bulk.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Get existing emails in campaign
    existing = await fetch_all(
        "SELECT email FROM leads WHERE campaign_id = $1",
        bulk.campaign_id
    )
    existing_emails = {r["email"].lower() for r in existing}

    successful = 0
    failed = 0
    duplicates_skipped = 0
    errors = []

    for lead in bulk.leads:
        # Skip duplicates
        if lead.email.lower() in existing_emails:
            duplicates_skipped += 1
            continue

        try:
            await execute("""
                INSERT INTO leads (campaign_id, email, first_name, last_name, company, title, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                bulk.campaign_id, lead.email, lead.first_name, lead.last_name,
                lead.company, lead.title, bulk.source
            )
            existing_emails.add(lead.email.lower())
            successful += 1
        except Exception as e:
            failed += 1
            errors.append({"email": lead.email, "error": str(e)})
            logger.error(f"Failed to insert lead {lead.email}: {e}")

    # Update campaign lead count
    await execute("""
        UPDATE emailbison_campaigns
        SET total_leads = (SELECT COUNT(*) FROM leads WHERE campaign_id = $1),
            updated_at = NOW()
        WHERE id = $1
    """, bulk.campaign_id)

    return LeadBulkUploadResult(
        total_uploaded=len(bulk.leads),
        successful=successful,
        failed=failed,
        duplicates_skipped=duplicates_skipped,
        errors=errors if errors else None
    )


@router.put("/{lead_id}", response_model=Lead)
async def update_lead(lead_id: UUID, update: LeadUpdate):
    """Update a lead"""
    # Build SET clause dynamically
    set_parts = []
    params = []
    param_idx = 1

    fields = [
        "first_name", "last_name", "company", "title",
        "linkedin_url", "phone", "website", "location",
        "industry", "company_size", "notes", "status"
    ]

    for field in fields:
        value = getattr(update, field, None)
        if value is not None:
            set_parts.append(f"{field} = ${param_idx}")
            params.append(value)
            param_idx += 1

    if update.tags is not None:
        set_parts.append(f"tags = ${param_idx}")
        params.append(update.tags)
        param_idx += 1

    if update.custom_fields is not None:
        set_parts.append(f"custom_fields = ${param_idx}")
        params.append(json.dumps(update.custom_fields))
        param_idx += 1

    if not set_parts:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_parts.append("updated_at = NOW()")

    params.append(lead_id)
    query = f"UPDATE leads SET {', '.join(set_parts)} WHERE id = ${param_idx} RETURNING id"
    result = await fetch_one(query, *params)

    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")

    return await get_lead(lead_id)


@router.put("/{lead_id}/status", response_model=Lead)
async def update_lead_status(lead_id: UUID, update: LeadStatusUpdate):
    """Update lead status"""
    set_parts = ["status = $1", "updated_at = NOW()"]
    params = [update.status]

    if update.contacted_at:
        set_parts.append("contacted_at = $2")
        params.append(update.contacted_at)

    params.append(lead_id)
    query = f"UPDATE leads SET {', '.join(set_parts)} WHERE id = ${len(params)} RETURNING id"
    result = await fetch_one(query, *params)

    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")

    return await get_lead(lead_id)


@router.delete("/{lead_id}")
async def delete_lead(lead_id: UUID):
    """Delete a lead"""
    # Get campaign_id first for updating count
    lead = await fetch_one("SELECT campaign_id FROM leads WHERE id = $1", lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    await execute("DELETE FROM leads WHERE id = $1", lead_id)

    # Update campaign lead count
    await execute("""
        UPDATE emailbison_campaigns
        SET total_leads = (SELECT COUNT(*) FROM leads WHERE campaign_id = $1),
            updated_at = NOW()
        WHERE id = $1
    """, lead["campaign_id"])

    return {"message": "Lead deleted successfully"}


@router.get("/campaign/{campaign_id}", response_model=LeadList)
async def get_campaign_leads(
    campaign_id: UUID,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """Get leads for a specific campaign"""
    return await list_leads(campaign_id=campaign_id, status=status, page=page, page_size=page_size)
