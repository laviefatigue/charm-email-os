"""
Onboarding submission routes.

API endpoints for retrieving and editing comprehensive onboarding form data.
"""

from fastapi import APIRouter, HTTPException
from uuid import UUID
import logging

from database import fetch_all, fetch_one, execute
from models.onboarding import (
    OnboardingSubmission,
    OnboardingSubmissionUpdate,
    OnboardingSubmissionList,
    ClientSegment,
    ClientPersona,
)

router = APIRouter()
logger = logging.getLogger(__name__)


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

    # Get all submissions for this client
    # Note: Table schema from hirecharm-onboarding project
    submissions_query = """
        SELECT
            id, client_id, company_name, website, contact_name, contact_email,
            employee_count, funding_stage, hq_location,
            core_product, target_customer, acv, sales_cycle_length,
            signals, job_titles,
            outbound_tools, crm,
            customer_voice, roi_results, tone_style,
            primary_gtm_objective, success_metrics, success_definition,
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
    # Get submission
    submission = await fetch_one(
        """
        SELECT
            id, client_id, company_name, website, contact_name, contact_email,
            employee_count, funding_stage, hq_location,
            core_product, target_customer, acv, sales_cycle_length,
            signals, job_titles,
            outbound_tools, crm,
            customer_voice, roi_results, tone_style,
            primary_gtm_objective, success_metrics, success_definition,
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
