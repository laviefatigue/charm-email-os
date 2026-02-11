"""
Onboarding submission routes.

API endpoints for retrieving and editing comprehensive onboarding form data.
"""

from fastapi import APIRouter, HTTPException
from uuid import UUID, uuid4
from datetime import datetime
import logging
from typing import Optional, Any
from pydantic import BaseModel

from database import fetch_all, fetch_one, execute
from models.onboarding import (
    OnboardingSubmission,
    OnboardingSubmissionUpdate,
    OnboardingSubmissionList,
    ClientSegment,
    ClientPersona,
)


class OnboardingSubmissionCreate(BaseModel):
    """Create a new onboarding submission."""
    # Section 1: Foundation
    company_name: str
    website: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    employee_count: Optional[str] = None
    funding_stage: Optional[str] = None
    hq_location: Optional[str] = None

    # Section 2: Offering
    core_product: Optional[str] = None
    target_customer: Optional[str] = None
    acv: Optional[str] = None
    sales_cycle_length: Optional[str] = None
    annual_revenue: Optional[str] = None
    self_serve_pct: Optional[str] = None
    industry: Optional[str] = None

    # Section 3: Market Signals
    signals: list[str] = []

    # Section 4: Audience
    job_titles: list[str] = []
    competitors: list[str] = []
    key_differentiators: Optional[str] = None
    common_objections: Optional[str] = None
    buying_triggers_global: Optional[str] = None

    # Section 5: Process
    outbound_tools: list[str] = []
    crm: Optional[str] = None
    monthly_volume: Optional[str] = None
    current_open_rate: Optional[str] = None
    current_reply_rate: Optional[str] = None
    other_channels: Optional[str] = None
    messages_worked: Optional[str] = None
    approaches_failed: Optional[str] = None

    # Section 6: Messaging
    customer_voice: Optional[str] = None
    roi_results: Optional[str] = None
    tone_style: Optional[str] = None
    case_studies: Optional[Any] = None
    industry_jargon: Optional[str] = None
    core_vendors: list[str] = []

    # Section 7: Goals
    primary_gtm_objective: Optional[str] = None
    success_metrics: list[str] = []
    success_definition: Optional[str] = None
    engagement_win: Optional[str] = None
    additional_context: Optional[str] = None

    # Nested data
    segments: list[dict] = []
    personas: list[dict] = []

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/clients/{client_id}/submissions")
async def create_onboarding_submission(client_id: UUID, data: OnboardingSubmissionCreate):
    """
    Create a new onboarding submission for a client.
    Used for testing and direct data entry.
    """
    # Verify client exists
    client = await fetch_one("SELECT id, name FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    submission_id = uuid4()
    now = datetime.utcnow()

    # Insert main submission with all fields
    await execute("""
        INSERT INTO client_onboarding_submissions (
            id, client_id, company_name, website, contact_name, contact_email,
            employee_count, funding_stage, hq_location,
            core_product, target_customer, acv, sales_cycle_length,
            annual_revenue, self_serve_pct, industry,
            signals, job_titles,
            competitors, key_differentiators, common_objections, buying_triggers_global,
            outbound_tools, crm,
            monthly_volume, current_open_rate, current_reply_rate, other_channels,
            messages_worked, approaches_failed,
            customer_voice, roi_results, tone_style,
            case_studies, industry_jargon, core_vendors,
            primary_gtm_objective, success_metrics, success_definition,
            engagement_win, additional_context,
            submission_status, submitted_at, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9,
            $10, $11, $12, $13,
            $14, $15, $16,
            $17, $18,
            $19, $20, $21, $22,
            $23, $24,
            $25, $26, $27, $28,
            $29, $30,
            $31, $32, $33,
            $34, $35, $36,
            $37, $38, $39,
            $40, $41,
            $42, $43, $44
        )
    """,
        submission_id, client_id,
        data.company_name, data.website, data.contact_name, data.contact_email,
        data.employee_count, data.funding_stage, data.hq_location,
        data.core_product, data.target_customer, data.acv, data.sales_cycle_length,
        data.annual_revenue, data.self_serve_pct, data.industry,
        data.signals, data.job_titles,
        data.competitors, data.key_differentiators, data.common_objections, data.buying_triggers_global,
        data.outbound_tools, data.crm,
        data.monthly_volume, data.current_open_rate, data.current_reply_rate, data.other_channels,
        data.messages_worked, data.approaches_failed,
        data.customer_voice, data.roi_results, data.tone_style,
        data.case_studies, data.industry_jargon, data.core_vendors,
        data.primary_gtm_objective, data.success_metrics, data.success_definition,
        data.engagement_win, data.additional_context,
        "submitted", now, now
    )
    logger.info(f"Created onboarding submission {submission_id} for client {client['name']}")

    # Insert segments
    for seg in data.segments:
        segment_id = uuid4()
        await execute("""
            INSERT INTO client_segments (
                id, submission_id, segment_name, revenue_percentage,
                unique_characteristics, pain_points, buying_triggers
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
            segment_id, submission_id,
            seg.get("segment_name", "Unknown"),
            seg.get("revenue_percentage", 0),
            seg.get("unique_characteristics"),
            seg.get("pain_points"),
            seg.get("buying_triggers")
        )

    # Insert personas
    for persona in data.personas:
        persona_id = uuid4()
        await execute("""
            INSERT INTO client_personas (
                id, submission_id, job_title, primary_segment, seniority_level,
                pain_before_buying, aha_moment, objections
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            persona_id, submission_id,
            persona.get("job_title", "Unknown"),
            persona.get("primary_segment"),
            persona.get("seniority_level"),
            persona.get("pain_before_buying"),
            persona.get("aha_moment"),
            persona.get("objections")
        )

    return {
        "submission_id": str(submission_id),
        "client_id": str(client_id),
        "client_name": client["name"],
        "company_name": data.company_name,
        "status": "submitted",
        "message": "Onboarding submission created successfully"
    }


@router.get("/clients/{client_id}/submissions", response_model=OnboardingSubmissionList)
async def get_client_onboarding_submissions(client_id: UUID):
    """
    Get all onboarding submissions for a client.
    Returns submissions with their segments and personas.
    """
    # Verify client exists
    client = await fetch_one("SELECT id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get all submissions for this client with all fields
    submissions_query = """
        SELECT
            id, client_id, company_name, website, contact_name, contact_email,
            employee_count, funding_stage, hq_location,
            core_product, target_customer, acv, sales_cycle_length,
            annual_revenue, self_serve_pct, industry,
            signals, job_titles,
            competitors, key_differentiators, common_objections, buying_triggers_global,
            outbound_tools, crm,
            monthly_volume, current_open_rate, current_reply_rate, other_channels,
            messages_worked, approaches_failed,
            customer_voice, roi_results, tone_style,
            case_studies, industry_jargon, core_vendors,
            primary_gtm_objective, success_metrics, success_definition,
            engagement_win, additional_context,
            submission_status, submitted_at, created_at
        FROM client_onboarding_submissions
        WHERE client_id = $1
        ORDER BY created_at DESC
    """
    submissions = await fetch_all(submissions_query, client_id)

    if not submissions:
        return OnboardingSubmissionList(
            client_id=client_id,
            submissions=[],
            total=0
        )

    # For each submission, get segments and personas
    result = []
    for sub in submissions:
        sub_dict = dict(sub)

        # Get segments
        segments = await fetch_all(
            """
            SELECT id, segment_name, revenue_percentage, unique_characteristics,
                   pain_points, buying_triggers
            FROM client_segments
            WHERE submission_id = $1
            """,
            sub_dict["id"]
        )
        sub_dict["segments"] = [ClientSegment(**dict(s)) for s in segments] if segments else []

        # Get personas
        personas = await fetch_all(
            """
            SELECT id, job_title, primary_segment, seniority_level,
                   pain_before_buying, aha_moment, objections
            FROM client_personas
            WHERE submission_id = $1
            """,
            sub_dict["id"]
        )
        sub_dict["personas"] = [ClientPersona(**dict(p)) for p in personas] if personas else []

        # Handle array fields that might be None
        sub_dict["signals"] = sub_dict.get("signals") or []
        sub_dict["job_titles"] = sub_dict.get("job_titles") or []
        sub_dict["outbound_tools"] = sub_dict.get("outbound_tools") or []
        sub_dict["success_metrics"] = sub_dict.get("success_metrics") or []
        sub_dict["competitors"] = sub_dict.get("competitors") or []
        sub_dict["core_vendors"] = sub_dict.get("core_vendors") or []

        result.append(OnboardingSubmission(**sub_dict))

    return OnboardingSubmissionList(
        client_id=client_id,
        submissions=result,
        total=len(result)
    )


@router.get("/submissions/{submission_id}", response_model=OnboardingSubmission)
async def get_onboarding_submission(submission_id: UUID):
    """
    Get a single onboarding submission with all details.
    """
    # Get submission with all fields
    submission = await fetch_one(
        """
        SELECT
            id, client_id, company_name, website, contact_name, contact_email,
            employee_count, funding_stage, hq_location,
            core_product, target_customer, acv, sales_cycle_length,
            annual_revenue, self_serve_pct, industry,
            signals, job_titles,
            competitors, key_differentiators, common_objections, buying_triggers_global,
            outbound_tools, crm,
            monthly_volume, current_open_rate, current_reply_rate, other_channels,
            messages_worked, approaches_failed,
            customer_voice, roi_results, tone_style,
            case_studies, industry_jargon, core_vendors,
            primary_gtm_objective, success_metrics, success_definition,
            engagement_win, additional_context,
            submission_status, submitted_at, created_at
        FROM client_onboarding_submissions
        WHERE id = $1
        """,
        submission_id
    )

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    sub_dict = dict(submission)

    # Get segments
    segments = await fetch_all(
        """
        SELECT id, segment_name, revenue_percentage, unique_characteristics,
               pain_points, buying_triggers
        FROM client_segments
        WHERE submission_id = $1
        """,
        submission_id
    )
    sub_dict["segments"] = [ClientSegment(**dict(s)) for s in segments] if segments else []

    # Get personas
    personas = await fetch_all(
        """
        SELECT id, job_title, primary_segment, seniority_level,
               pain_before_buying, aha_moment, objections
        FROM client_personas
        WHERE submission_id = $1
        """,
        submission_id
    )
    sub_dict["personas"] = [ClientPersona(**dict(p)) for p in personas] if personas else []

    # Handle array fields
    sub_dict["signals"] = sub_dict.get("signals") or []
    sub_dict["job_titles"] = sub_dict.get("job_titles") or []
    sub_dict["outbound_tools"] = sub_dict.get("outbound_tools") or []
    sub_dict["success_metrics"] = sub_dict.get("success_metrics") or []
    sub_dict["competitors"] = sub_dict.get("competitors") or []
    sub_dict["core_vendors"] = sub_dict.get("core_vendors") or []

    return OnboardingSubmission(**sub_dict)


@router.put("/submissions/{submission_id}", response_model=OnboardingSubmission)
async def update_onboarding_submission(submission_id: UUID, update: OnboardingSubmissionUpdate):
    """
    Update an onboarding submission.
    Only non-None fields are updated.
    """
    # Verify submission exists
    existing = await fetch_one(
        "SELECT id FROM client_onboarding_submissions WHERE id = $1",
        submission_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Build dynamic UPDATE
    set_parts = []
    params = []
    param_idx = 1

    update_data = update.model_dump(exclude_none=True)
    for field, value in update_data.items():
        set_parts.append(f"{field} = ${param_idx}")
        params.append(value)
        param_idx += 1

    if not set_parts:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Add updated_at
    set_parts.append("updated_at = NOW()")

    # Execute update
    params.append(submission_id)
    query = f"""
        UPDATE client_onboarding_submissions
        SET {', '.join(set_parts)}
        WHERE id = ${param_idx}
        RETURNING id
    """
    result = await fetch_one(query, *params)

    if not result:
        raise HTTPException(status_code=500, detail="Failed to update submission")

    # Return updated submission
    return await get_onboarding_submission(submission_id)


@router.get("/clients/{client_id}/contact-names")
async def get_client_contact_names(client_id: UUID):
    """
    Get contact first names from onboarding data.
    Used for generating inbox email addresses.
    Returns names from both simplified onboarding_data and comprehensive submissions.
    """
    # Get from clients.onboarding_data (simplified)
    client = await fetch_one(
        "SELECT onboarding_data FROM clients WHERE id = $1",
        client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    names = []

    # Extract from simplified onboarding_data
    if client.get("onboarding_data"):
        import json
        onboarding = client["onboarding_data"]
        if isinstance(onboarding, str):
            onboarding = json.loads(onboarding)
        # Get contactFirstNames array
        contact_names = onboarding.get("contactFirstNames", [])
        if contact_names:
            names.extend(contact_names)

    # Get from comprehensive submission personas
    personas = await fetch_all(
        """
        SELECT DISTINCT cp.job_title
        FROM client_personas cp
        JOIN client_onboarding_submissions cos ON cp.submission_id = cos.id
        WHERE cos.client_id = $1
        """,
        client_id
    )
    # Note: Personas have job_titles, not first names
    # The contact_name field in submissions could provide names

    # Get contact_name from submissions
    contacts = await fetch_all(
        """
        SELECT contact_name
        FROM client_onboarding_submissions
        WHERE client_id = $1 AND contact_name IS NOT NULL
        """,
        client_id
    )
    for c in contacts or []:
        if c.get("contact_name"):
            # Extract first name
            first_name = c["contact_name"].split()[0] if c["contact_name"] else None
            if first_name and first_name not in names:
                names.append(first_name)

    return {
        "client_id": str(client_id),
        "contact_names": names,
        "job_titles": [p["job_title"] for p in personas] if personas else []
    }
