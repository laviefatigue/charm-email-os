"""
Lead routes - CRUD for the new leads table
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
import json
import logging
import re

from database import fetch_all, fetch_one, execute, execute_many
from models.lead import (
    Lead, LeadCreate, LeadUpdate, LeadBulkCreate,
    LeadList, LeadStatusUpdate, LeadBulkUploadResult
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Suppression gate helpers ──────────────────────────────────────────────────
# Lightweight domain cleaner used to normalise domains before the suppression
# check. Mirrors the logic in routes/suppression.py — kept here to avoid a
# cross-module import between two route modules.

_SUPPRESSION_DOMAIN_RE = re.compile(
    r'^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$'
)


def _clean_candidate_domain(raw: str) -> Optional[str]:
    if not raw:
        return None
    d = raw.strip().lower()
    d = re.sub(r'^https?://', '', d)
    d = re.sub(r'^www\.', '', d)
    d = re.sub(r':\d+', '', d)
    d = d.split('/')[0].split('?')[0].split('#')[0].strip()
    if '@' in d or not d or not _SUPPRESSION_DOMAIN_RE.match(d) or len(d) > 253:
        return None
    return d


def _build_suppression_candidates(email: str, company_domain: Optional[str]) -> list[str]:
    candidates: list[str] = []
    if email and '@' in email:
        ed = _clean_candidate_domain(email.rsplit('@', 1)[1])
        if ed:
            candidates.append(ed)
    if company_domain:
        cd = _clean_candidate_domain(company_domain)
        if cd and cd not in candidates:
            candidates.append(cd)
    return candidates


async def _run_suppression_check(client_id: UUID, candidates: list[str]) -> Optional[dict]:
    """Returns first matching suppression rule row, or None."""
    return await fetch_one(
        """
        SELECT domain, umbrella_domain
        FROM client_suppression_domains
        WHERE client_id = $1
          AND (
            domain = ANY($2::text[])
            OR umbrella_domain = ANY($2::text[])
            OR EXISTS (
                SELECT 1
                FROM unnest($2::text[]) AS c(d)
                WHERE umbrella_domain IS NOT NULL
                  AND c.d LIKE '%.' || umbrella_domain
            )
          )
        LIMIT 1
        """,
        client_id, candidates
    )


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
            COUNT(*) FILTER (WHERE status = 'unsubscribed') as unsubscribed,
            COUNT(*) FILTER (WHERE status = 'suppressed') as suppressed
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
            l.updated_at,
            l.company_domain,
            l.suppression_status,
            l.suppressed_at,
            l.suppressed_by_domain
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
        unsubscribed_count=status_counts["unsubscribed"] if status_counts else 0,
        suppressed_count=status_counts["suppressed"] if status_counts else 0,
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
            updated_at,
            company_domain,
            suppression_status,
            suppressed_at,
            suppressed_by_domain
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

    # ── Suppression gate ──────────────────────────────────────────────────────
    suppression_status = None
    suppressed_at_val = None
    suppressed_by_domain_val = None
    lead_status = "queued"

    suppression_cfg = await fetch_one(
        """
        SELECT csc.client_id, csc.is_enabled
        FROM emailbison_campaigns ec
        JOIN client_suppression_configs csc ON csc.workspace_id = ec.workspace_id
        WHERE ec.id = $1
        """,
        lead.campaign_id
    )
    if suppression_cfg and suppression_cfg["is_enabled"]:
        candidates = _build_suppression_candidates(str(lead.email), lead.company_domain)
        if candidates:
            match = await _run_suppression_check(suppression_cfg["client_id"], candidates)
            if match:
                suppression_status = "suppressed"
                suppressed_at_val = datetime.now(timezone.utc)
                suppressed_by_domain_val = match["umbrella_domain"] or match["domain"]
                lead_status = "suppressed"
            else:
                suppression_status = "allowed"
        else:
            suppression_status = "allowed"
    # ── End suppression gate ──────────────────────────────────────────────────

    query = """
        INSERT INTO leads (
            campaign_id, email, first_name, last_name, company, title,
            linkedin_url, phone, website, location, industry, company_size,
            notes, tags, custom_fields, source,
            company_domain, suppression_status, suppressed_at, suppressed_by_domain,
            status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                $17, $18, $19, $20, $21)
        RETURNING *
    """
    row = await fetch_one(
        query,
        lead.campaign_id, lead.email, lead.first_name, lead.last_name,
        lead.company, lead.title, lead.linkedin_url, lead.phone,
        lead.website, lead.location, lead.industry, lead.company_size,
        lead.notes, lead.tags,
        json.dumps(lead.custom_fields) if lead.custom_fields else None,
        lead.source,
        lead.company_domain, suppression_status, suppressed_at_val, suppressed_by_domain_val,
        lead_status
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

    # Look up suppression config once for this campaign's workspace
    suppression_cfg = await fetch_one(
        """
        SELECT csc.client_id, csc.is_enabled
        FROM emailbison_campaigns ec
        JOIN client_suppression_configs csc ON csc.workspace_id = ec.workspace_id
        WHERE ec.id = $1
        """,
        bulk.campaign_id
    )
    suppression_active = suppression_cfg is not None and suppression_cfg["is_enabled"]
    suppression_client_id = suppression_cfg["client_id"] if suppression_active else None

    successful = 0
    failed = 0
    duplicates_skipped = 0
    errors = []

    for lead in bulk.leads:
        # Skip duplicates
        if lead.email.lower() in existing_emails:
            duplicates_skipped += 1
            continue

        # ── Suppression gate ──────────────────────────────────────────────────
        suppression_status = None
        suppressed_at_val = None
        suppressed_by_domain_val = None
        lead_status = "queued"

        if suppression_active:
            candidates = _build_suppression_candidates(str(lead.email), lead.company_domain)
            if candidates:
                match = await _run_suppression_check(suppression_client_id, candidates)
                if match:
                    suppression_status = "suppressed"
                    suppressed_at_val = datetime.now(timezone.utc)
                    suppressed_by_domain_val = match["umbrella_domain"] or match["domain"]
                    lead_status = "suppressed"
                else:
                    suppression_status = "allowed"
            else:
                suppression_status = "allowed"
        # ── End suppression gate ──────────────────────────────────────────────

        try:
            await execute("""
                INSERT INTO leads (campaign_id, email, first_name, last_name, company, title,
                                   source, company_domain, suppression_status, suppressed_at,
                                   suppressed_by_domain, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
                bulk.campaign_id, lead.email, lead.first_name, lead.last_name,
                lead.company, lead.title, bulk.source,
                lead.company_domain, suppression_status, suppressed_at_val,
                suppressed_by_domain_val, lead_status
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
