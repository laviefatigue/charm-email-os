"""
Strategy Generation Routes - AI-powered email campaign generation.

Manages strategy generation jobs and suggestions for human review.
Works with the strategy_worker.py daemon which spawns Claude Code.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from uuid import UUID
from datetime import datetime
from database import fetch_one, fetch_all, execute
import logging
import os

# EmailBison API configuration
import httpx

EMAILBISON_API_URL = os.getenv("EMAILBISON_API_URL", "https://spellcast.hirecharm.com")
EMAILBISON_API_KEY = os.getenv("EMAILBISON_API_KEY", "")

from models.strategy import (
    StrategyJobCreate,
    StrategyJobResponse,
    StrategySuggestionResponse,
    SuggestionReviewRequest,
    RevisionRequestCreate,
    RevisionRequestResponse,
    ClientSuggestionsResponse,
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    SuggestionEditRequest,
    # Sequence models
    SequenceEmail,
    CampaignSequenceResponse,
    ClientSequencesResponse,
    SequenceReviewRequest,
    SequenceEmailEditRequest,
    SequenceRevisionRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# Strategy Management (NEW)
# ============================================================================

@router.post("/strategies/{client_id}")
async def create_strategy(client_id: UUID, request: StrategyCreate):
    """
    Create a new strategy for a client.

    Strategies group related campaign suggestions together.
    Optionally linked to a client onboarding submission.
    """
    # Verify client exists
    client = await fetch_one(
        "SELECT id, name FROM clients WHERE id = $1",
        client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # If submission_id provided, verify it exists
    submission_created_at = None
    if request.submission_id:
        submission = await fetch_one(
            "SELECT id, created_at FROM client_onboarding_submissions WHERE id = $1 AND client_id = $2",
            request.submission_id, client_id
        )
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found for this client")
        submission_created_at = submission.get("created_at")

    # Create strategy with optional submission_id
    strategy = await fetch_one("""
        INSERT INTO strategies (client_id, name, description, status, submission_id)
        VALUES ($1, $2, $3, 'draft', $4)
        RETURNING id, client_id, name, description, status, submission_id, emailbison_campaign_id, created_at, updated_at
    """, client_id, request.name, request.description, request.submission_id)

    logger.info(f"Created strategy '{request.name}' for client {client['name']}")

    return StrategyResponse(
        id=strategy["id"],
        client_id=strategy["client_id"],
        name=strategy["name"],
        description=strategy.get("description"),
        status=strategy["status"],
        submission_id=strategy.get("submission_id"),
        submission_created_at=submission_created_at,
        emailbison_campaign_id=strategy.get("emailbison_campaign_id"),
        created_at=strategy["created_at"],
        updated_at=strategy["updated_at"],
    )


@router.get("/strategies/{client_id}")
async def get_client_strategies(client_id: UUID):
    """
    Get all strategies for a client with linked submission info.
    """
    strategies = await fetch_all("""
        SELECT s.*,
               (SELECT COUNT(*) FROM strategy_suggestions ss WHERE ss.strategy_id = s.id) as suggestion_count,
               sub.created_at as submission_created_at
        FROM strategies s
        LEFT JOIN client_onboarding_submissions sub ON sub.id = s.submission_id
        WHERE s.client_id = $1
        ORDER BY s.created_at DESC
    """, client_id)

    return {
        "client_id": str(client_id),
        "strategies": [
            {
                "id": str(s["id"]),
                "name": s["name"],
                "description": s.get("description"),
                "status": s["status"],
                "submission_id": str(s["submission_id"]) if s.get("submission_id") else None,
                "submission_created_at": s["submission_created_at"].isoformat() if s.get("submission_created_at") else None,
                "emailbison_campaign_id": s.get("emailbison_campaign_id"),
                "suggestion_count": s.get("suggestion_count", 0),
                "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
                "updated_at": s["updated_at"].isoformat() if s.get("updated_at") else None,
            }
            for s in (strategies or [])
        ],
        "total": len(strategies or [])
    }


@router.put("/strategies/{strategy_id}")
async def update_strategy(strategy_id: UUID, request: StrategyUpdate):
    """
    Update a strategy.
    """
    # Get current strategy
    strategy = await fetch_one(
        "SELECT * FROM strategies WHERE id = $1",
        strategy_id
    )
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Build update query
    updates = []
    params = []
    param_num = 1

    if request.name is not None:
        updates.append(f"name = ${param_num}")
        params.append(request.name)
        param_num += 1

    if request.description is not None:
        updates.append(f"description = ${param_num}")
        params.append(request.description)
        param_num += 1

    if request.status is not None:
        updates.append(f"status = ${param_num}")
        params.append(request.status)
        param_num += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append(f"updated_at = NOW()")
    params.append(strategy_id)

    query = f"UPDATE strategies SET {', '.join(updates)} WHERE id = ${param_num} RETURNING *"
    updated = await fetch_one(query, *params)

    return StrategyResponse(
        id=updated["id"],
        client_id=updated["client_id"],
        name=updated["name"],
        description=updated.get("description"),
        status=updated["status"],
        emailbison_campaign_id=updated.get("emailbison_campaign_id"),
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
    )


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: UUID):
    """
    Delete a strategy and unlink its suggestions.
    """
    strategy = await fetch_one(
        "SELECT id, name FROM strategies WHERE id = $1",
        strategy_id
    )
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Unlink suggestions (don't delete them)
    await execute(
        "UPDATE strategy_suggestions SET strategy_id = NULL WHERE strategy_id = $1",
        strategy_id
    )

    # Delete strategy
    await execute("DELETE FROM strategies WHERE id = $1", strategy_id)

    logger.info(f"Deleted strategy '{strategy['name']}'")

    return {"message": f"Strategy '{strategy['name']}' deleted", "id": str(strategy_id)}


# ============================================================================
# Strategy Generation Jobs
# ============================================================================

@router.post("/jobs/{client_id}")
async def create_strategy_job(client_id: UUID, request: Optional[StrategyJobCreate] = None):
    """
    Create a new strategy generation job for the Claude Code worker.

    This queues a job that will be picked up by strategy_worker.py,
    which spawns Claude Code to generate email campaign variants.

    Args:
        client_id: The client UUID to generate strategy for
        request: Optional request with submission_id and strategy_id

    Returns:
        Job ID and status information
    """
    # Verify client exists
    client = await fetch_one(
        "SELECT id, name, workspace_id FROM clients WHERE id = $1",
        client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    submission_id = request.submission_id if request else None
    strategy_id = request.strategy_id if request else None

    # If no strategy specified, use or create default
    if not strategy_id:
        default_strategy = await fetch_one("""
            SELECT id FROM strategies
            WHERE client_id = $1
            ORDER BY created_at ASC
            LIMIT 1
        """, client_id)

        if default_strategy:
            strategy_id = default_strategy["id"]
        else:
            # Create default strategy
            new_strategy = await fetch_one("""
                INSERT INTO strategies (client_id, name, status)
                VALUES ($1, 'Default Strategy', 'active')
                RETURNING id
            """, client_id)
            strategy_id = new_strategy["id"]

    # Get current generation round (increment from last job)
    last_job = await fetch_one("""
        SELECT generation_round FROM strategy_generation_jobs
        WHERE client_id = $1
        ORDER BY created_at DESC
        LIMIT 1
    """, client_id)
    generation_round = (last_job["generation_round"] + 1) if last_job else 1

    # Create job
    job = await fetch_one("""
        INSERT INTO strategy_generation_jobs (client_id, submission_id, strategy_id, status, generation_round, job_type)
        VALUES ($1, $2, $3, 'pending', $4, 'initial')
        RETURNING id, status, generation_round, created_at
    """, client_id, submission_id, strategy_id, generation_round)

    logger.info(f"Created strategy generation job {job['id']} for client {client['name']} (round {generation_round})")

    return {
        "job_id": str(job["id"]),
        "client_id": str(client_id),
        "client_name": client["name"],
        "submission_id": str(submission_id) if submission_id else None,
        "strategy_id": str(strategy_id) if strategy_id else None,
        "status": job["status"],
        "generation_round": job["generation_round"],
        "created_at": job["created_at"].isoformat(),
        "message": "Job queued for processing by Claude Code worker"
    }


@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: UUID):
    """
    Get the status of a strategy generation job.
    """
    job = await fetch_one("""
        SELECT j.*, c.name as client_name
        FROM strategy_generation_jobs j
        JOIN clients c ON c.id = j.client_id
        WHERE j.id = $1
    """, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return StrategyJobResponse(
        job_id=job["id"],
        client_id=job["client_id"],
        client_name=job["client_name"],
        submission_id=job.get("submission_id"),
        status=job["status"],
        generation_round=job["generation_round"],
        error_message=job.get("error_message"),
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
    )


@router.get("/jobs/client/{client_id}")
async def get_client_jobs(client_id: UUID, limit: int = 10):
    """
    Get recent strategy generation jobs for a client.
    """
    jobs = await fetch_all("""
        SELECT id, submission_id, status, generation_round, error_message,
               created_at, started_at, completed_at
        FROM strategy_generation_jobs
        WHERE client_id = $1
        ORDER BY created_at DESC
        LIMIT $2
    """, client_id, limit)

    return {
        "client_id": str(client_id),
        "jobs": [
            {
                "job_id": str(j["id"]),
                "submission_id": str(j["submission_id"]) if j.get("submission_id") else None,
                "status": j["status"],
                "generation_round": j["generation_round"],
                "error_message": j.get("error_message"),
                "created_at": j["created_at"].isoformat() if j.get("created_at") else None,
                "started_at": j["started_at"].isoformat() if j.get("started_at") else None,
                "completed_at": j["completed_at"].isoformat() if j.get("completed_at") else None,
            }
            for j in (jobs or [])
        ],
        "total": len(jobs or [])
    }


# ============================================================================
# Strategy Suggestions
# ============================================================================

@router.get("/suggestions/{client_id}")
async def get_client_suggestions(
    client_id: UUID,
    status: Optional[str] = None,
    strategy_id: Optional[UUID] = None,
    sort: Optional[str] = None,  # score, created_at, status
    order: Optional[str] = "desc",  # asc, desc
    limit: int = 50
):
    """
    Get strategy suggestions for a client, optionally filtered and sorted.

    Args:
        client_id: The client UUID
        status: Filter by status (pending, approved, denied, revision_requested)
        strategy_id: Filter by strategy
        sort: Sort field (score, created_at, status)
        order: Sort order (asc, desc)
        limit: Maximum number to return
    """
    query = """
        SELECT s.*, j.generation_round as job_round
        FROM strategy_suggestions s
        JOIN strategy_generation_jobs j ON j.id = s.job_id
        WHERE s.client_id = $1
    """
    params = [client_id]
    param_num = 2

    if status:
        query += f" AND s.status = ${param_num}"
        params.append(status)
        param_num += 1

    if strategy_id:
        query += f" AND s.strategy_id = ${param_num}"
        params.append(strategy_id)
        param_num += 1

    # Handle sorting
    sort_field = "s.created_at"
    if sort == "score":
        sort_field = "s.score"
    elif sort == "status":
        sort_field = "s.status"
    elif sort == "created_at":
        sort_field = "s.created_at"

    sort_order = "DESC" if order != "asc" else "ASC"
    query += f" ORDER BY {sort_field} {sort_order} NULLS LAST"

    query += f" LIMIT ${param_num}"
    params.append(limit)

    suggestions = await fetch_all(query, *params)

    # Get counts (filtered by strategy_id if provided)
    count_query = """
        SELECT
            COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
            COUNT(*) FILTER (WHERE status = 'approved') as approved_count,
            COUNT(*) FILTER (WHERE status = 'denied') as denied_count,
            COUNT(*) FILTER (WHERE status = 'revision_requested') as revision_count,
            COUNT(*) as total
        FROM strategy_suggestions
        WHERE client_id = $1
    """
    count_params = [client_id]

    if strategy_id:
        count_query += " AND strategy_id = $2"
        count_params.append(strategy_id)

    counts = await fetch_one(count_query, *count_params)

    return ClientSuggestionsResponse(
        client_id=client_id,
        suggestions=[
            StrategySuggestionResponse(
                id=s["id"],
                job_id=s["job_id"],
                client_id=s["client_id"],
                strategy_id=s.get("strategy_id"),
                variant_number=s["variant_number"],
                subject_line=s["subject_line"],
                email_body=s["email_body"],
                edited_subject_line=s.get("edited_subject_line"),
                edited_email_body=s.get("edited_email_body"),
                score=s.get("score"),
                rationale=s.get("rationale"),
                used_variables=s.get("used_variables"),
                missing_variables=s.get("missing_variables"),
                campaign_type=s.get("campaign_type"),
                status=s["status"],
                human_comment=s.get("human_comment"),
                reviewed_by=s.get("reviewed_by"),
                reviewed_at=s.get("reviewed_at"),
                pushed_to_emailbison=s.get("pushed_to_emailbison", False),
                pushed_at=s.get("pushed_at"),
                original_suggestion_id=s.get("original_suggestion_id"),
                generation_round=s.get("generation_round", 1),
                created_at=s["created_at"],
            )
            for s in (suggestions or [])
        ],
        pending_count=counts["pending_count"] if counts else 0,
        approved_count=counts["approved_count"] if counts else 0,
        denied_count=counts["denied_count"] if counts else 0,
        revision_count=counts["revision_count"] if counts else 0,
        total=counts["total"] if counts else 0,
    )


@router.get("/suggestions/job/{job_id}")
async def get_job_suggestions(job_id: UUID):
    """
    Get all suggestions for a specific generation job.
    """
    suggestions = await fetch_all("""
        SELECT *
        FROM strategy_suggestions
        WHERE job_id = $1
        ORDER BY variant_number ASC
    """, job_id)

    return {
        "job_id": str(job_id),
        "suggestions": [
            {
                "id": str(s["id"]),
                "variant_number": s["variant_number"],
                "subject_line": s["subject_line"],
                "email_body": s["email_body"],
                "score": s.get("score"),
                "rationale": s.get("rationale"),
                "used_variables": s.get("used_variables"),
                "campaign_type": s.get("campaign_type"),
                "status": s["status"],
                "human_comment": s.get("human_comment"),
                "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
            }
            for s in (suggestions or [])
        ],
        "total": len(suggestions or [])
    }


@router.put("/suggestions/{suggestion_id}/edit")
async def edit_suggestion(suggestion_id: UUID, request: SuggestionEditRequest):
    """
    Edit a suggestion's content (subject line and email body).

    Edits are stored separately from the original AI-generated content,
    allowing users to customize while preserving the original.
    """
    # Verify suggestion exists
    suggestion = await fetch_one(
        "SELECT id, subject_line FROM strategy_suggestions WHERE id = $1",
        suggestion_id
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    # Update edited fields
    await execute("""
        UPDATE strategy_suggestions
        SET edited_subject_line = $1, edited_email_body = $2
        WHERE id = $3
    """, request.subject_line, request.email_body, suggestion_id)

    logger.info(f"Suggestion {suggestion_id} edited")

    return {
        "suggestion_id": str(suggestion_id),
        "edited_subject_line": request.subject_line,
        "edited_email_body": request.email_body,
        "message": "Suggestion edited successfully"
    }


@router.post("/suggestions/{suggestion_id}/review")
async def review_suggestion(suggestion_id: UUID, request: SuggestionReviewRequest):
    """
    Review a strategy suggestion - approve, deny, or request revision.

    Args:
        suggestion_id: The suggestion UUID
        request: Review action and optional comment
    """
    # Verify suggestion exists
    suggestion = await fetch_one(
        "SELECT id, subject_line FROM strategy_suggestions WHERE id = $1",
        suggestion_id
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    valid_actions = ['approve', 'deny', 'revision_requested']
    if request.action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be one of: {valid_actions}"
        )

    # Map action to status
    status_map = {
        'approve': 'approved',
        'deny': 'denied',
        'revision_requested': 'revision_requested'
    }
    new_status = status_map[request.action]

    # Update suggestion
    await execute("""
        UPDATE strategy_suggestions
        SET status = $1, human_comment = $2, reviewed_by = $3, reviewed_at = NOW()
        WHERE id = $4
    """, new_status, request.comment, request.reviewer, suggestion_id)

    logger.info(f"Suggestion {suggestion_id} reviewed: {new_status}")

    return {
        "suggestion_id": str(suggestion_id),
        "subject_line": suggestion["subject_line"],
        "status": new_status,
        "message": f"Suggestion {request.action}d successfully"
    }


@router.post("/suggestions/{suggestion_id}/revision")
async def request_revision(suggestion_id: UUID, request: RevisionRequestCreate):
    """
    Create a revision request for a suggestion AND auto-trigger a new generation job.

    This creates a revision request with the user's instruction and immediately
    queues a new job for the worker to process. The worker will generate a
    revised variant based on the original and the user's feedback.
    """
    # Get suggestion info including strategy_id
    suggestion = await fetch_one("""
        SELECT s.id, s.job_id, s.client_id, s.strategy_id
        FROM strategy_suggestions s
        WHERE s.id = $1
    """, suggestion_id)

    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    # Create revision request
    revision = await fetch_one("""
        INSERT INTO strategy_revision_requests (job_id, client_id, variant_id, instruction)
        VALUES ($1, $2, $3, $4)
        RETURNING id, created_at
    """, suggestion["job_id"], suggestion["client_id"], suggestion_id, request.instruction)

    # Update suggestion status
    await execute("""
        UPDATE strategy_suggestions
        SET status = 'revision_requested'
        WHERE id = $1
    """, suggestion_id)

    # Get current generation round
    last_job = await fetch_one("""
        SELECT generation_round FROM strategy_generation_jobs
        WHERE client_id = $1
        ORDER BY created_at DESC
        LIMIT 1
    """, suggestion["client_id"])
    generation_round = (last_job["generation_round"] + 1) if last_job else 1

    # AUTO-TRIGGER: Create new generation job for revision
    new_job = await fetch_one("""
        INSERT INTO strategy_generation_jobs
        (client_id, strategy_id, status, generation_round, revision_of, job_type)
        VALUES ($1, $2, 'pending', $3, $4, 'revision')
        RETURNING id, created_at
    """, suggestion["client_id"], suggestion.get("strategy_id"), generation_round, suggestion_id)

    logger.info(f"Auto-triggered revision job {new_job['id']} for suggestion {suggestion_id}")

    return {
        "revision_id": str(revision["id"]),
        "job_id": str(new_job["id"]),
        "client_id": str(suggestion["client_id"]),
        "variant_id": str(suggestion_id),
        "instruction": request.instruction,
        "status": "revision_queued",
        "message": "Revision request created and generation job queued"
    }


@router.get("/revisions/{client_id}")
async def get_client_revisions(client_id: UUID, processed: Optional[bool] = None):
    """
    Get revision requests for a client.
    """
    query = """
        SELECT r.*, s.subject_line
        FROM strategy_revision_requests r
        LEFT JOIN strategy_suggestions s ON s.id = r.variant_id
        WHERE r.client_id = $1
    """
    params = [client_id]

    if processed is not None:
        query += " AND r.processed = $2"
        params.append(processed)

    query += " ORDER BY r.created_at DESC"

    revisions = await fetch_all(query, *params)

    return {
        "client_id": str(client_id),
        "revisions": [
            {
                "id": str(r["id"]),
                "job_id": str(r["job_id"]),
                "variant_id": str(r["variant_id"]) if r.get("variant_id") else None,
                "subject_line": r.get("subject_line"),
                "instruction": r["instruction"],
                "processed": r["processed"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in (revisions or [])
        ],
        "total": len(revisions or [])
    }


# ============================================================================
# EmailBison Integration
# ============================================================================

@router.post("/suggestions/{suggestion_id}/push-to-emailbison")
async def push_to_emailbison(suggestion_id: UUID):
    """
    Push an approved suggestion to EmailBison to create a campaign draft.

    This endpoint:
    1. Validates the suggestion is approved and not already pushed
    2. Creates a campaign in EmailBison with the suggestion content
    3. Updates the suggestion status to 'sent'
    """
    # Get suggestion with client and workspace info
    suggestion = await fetch_one("""
        SELECT s.*, c.name as client_name, w.emailbison_workspace_id
        FROM strategy_suggestions s
        JOIN clients c ON c.id = s.client_id
        LEFT JOIN workspaces w ON w.id = c.workspace_id
        WHERE s.id = $1
    """, suggestion_id)

    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    if suggestion["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail="Only approved suggestions can be pushed to EmailBison"
        )

    if suggestion.get("pushed_to_emailbison"):
        raise HTTPException(
            status_code=400,
            detail="Suggestion has already been pushed to EmailBison"
        )

    # CRITICAL: Validate workspace has EmailBison mapping
    emailbison_workspace_id = suggestion.get("emailbison_workspace_id")
    if not emailbison_workspace_id:
        raise HTTPException(
            status_code=400,
            detail=f"Client '{suggestion['client_name']}' has no EmailBison workspace configured. "
                   "Please link this client's workspace to an EmailBison workspace first."
        )

    # Check EmailBison API configuration
    if not EMAILBISON_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="EmailBison API key not configured"
        )

    # Use edited version if available, otherwise original
    campaign_name = suggestion.get("edited_subject_line") or suggestion["subject_line"]

    # Create campaign in EmailBison with correct workspace context
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # CRITICAL: Switch to correct workspace first
            switch_response = await client.post(
                f"{EMAILBISON_API_URL}/api/workspaces/v1.1/switch-workspace",
                headers={
                    "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={"team_id": emailbison_workspace_id}
            )

            if switch_response.status_code != 200:
                logger.error(f"Failed to switch workspace {emailbison_workspace_id}: {switch_response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to switch to EmailBison workspace {emailbison_workspace_id}"
                )

            logger.info(f"Switched to EmailBison workspace {emailbison_workspace_id}")

            # Now create campaign in correct workspace context
            response = await client.post(
                f"{EMAILBISON_API_URL}/api/campaigns",
                headers={
                    "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "name": campaign_name,
                    "type": "outbound",
                },
            )

            if response.status_code not in (200, 201):
                logger.error(f"EmailBison API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"EmailBison API error: {response.status_code}"
                )

            campaign_data = response.json()
            campaign_id = campaign_data.get("data", {}).get("id") or campaign_data.get("id")

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to EmailBison: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to connect to EmailBison: {str(e)}"
        )

    # Update suggestion status to 'sent'
    await execute("""
        UPDATE strategy_suggestions
        SET status = 'sent', pushed_to_emailbison = TRUE, pushed_at = NOW()
        WHERE id = $1
    """, suggestion_id)

    logger.info(f"Pushed suggestion {suggestion_id} to EmailBison workspace {emailbison_workspace_id} as campaign {campaign_id}")

    return {
        "suggestion_id": str(suggestion_id),
        "client_id": str(suggestion["client_id"]),
        "client_name": suggestion["client_name"],
        "emailbison_workspace_id": emailbison_workspace_id,
        "emailbison_campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "status": "sent",
        "message": f"Campaign created in EmailBison workspace {emailbison_workspace_id}"
    }


# ============================================================================
# Campaign Sequences (4-Email Campaigns)
# ============================================================================

def _build_sequence_response(s: dict, job_round: int = 1) -> CampaignSequenceResponse:
    """Build a CampaignSequenceResponse from a database row."""
    # Parse sequence_data JSONB into email list
    sequence_data = s.get("sequence_data") or []
    emails = []
    for email in sequence_data:
        emails.append(SequenceEmail(
            position=email.get("position", 1),
            wait_days=email.get("wait_days", 0),
            subject_line=email.get("subject_line"),
            email_body=email.get("email_body", ""),
            edited_subject_line=email.get("edited_subject_line"),
            edited_email_body=email.get("edited_email_body"),
            thread_reply=email.get("thread_reply", False),
            strategy=email.get("strategy"),
            value_prop=email.get("value_prop"),
            word_count=email.get("word_count"),
        ))

    return CampaignSequenceResponse(
        id=s["id"],
        job_id=s["job_id"],
        client_id=s["client_id"],
        strategy_id=s.get("strategy_id"),
        campaign_name=s.get("subject_line") or "Untitled Campaign",
        campaign_type=s.get("campaign_type"),
        status=s["status"],
        score=s.get("score"),
        value_prop_rotation=s.get("value_prop_rotation"),
        emails=emails,
        used_variables=s.get("used_variables"),
        missing_variables=s.get("missing_variables"),
        rationale=s.get("rationale"),
        total_word_count=s.get("total_word_count"),
        human_comment=s.get("human_comment"),
        reviewed_by=s.get("reviewed_by"),
        reviewed_at=s.get("reviewed_at"),
        pushed_to_emailbison=s.get("pushed_to_emailbison", False),
        pushed_at=s.get("pushed_at"),
        generation_round=job_round,
        created_at=s["created_at"],
    )


@router.get("/sequences/{client_id}")
async def get_client_sequences(
    client_id: UUID,
    status: Optional[str] = None,
    strategy_id: Optional[UUID] = None,
    sort: Optional[str] = None,  # score, created_at, status
    order: Optional[str] = "desc",  # asc, desc
    limit: int = 50
):
    """
    Get all 4-email campaign sequences for a client.

    Only returns suggestions that are full sequences (is_sequence = TRUE).
    Each sequence includes all 4 emails with timing and threading info.
    """
    query = """
        SELECT s.*, j.generation_round as job_round
        FROM strategy_suggestions s
        JOIN strategy_generation_jobs j ON j.id = s.job_id
        WHERE s.client_id = $1 AND s.is_sequence = TRUE
    """
    params = [client_id]
    param_num = 2

    if status:
        query += f" AND s.status = ${param_num}"
        params.append(status)
        param_num += 1

    if strategy_id:
        query += f" AND s.strategy_id = ${param_num}"
        params.append(strategy_id)
        param_num += 1

    # Handle sorting
    sort_field = "s.created_at"
    if sort == "score":
        sort_field = "s.score"
    elif sort == "status":
        sort_field = "s.status"
    elif sort == "created_at":
        sort_field = "s.created_at"

    sort_order = "DESC" if order != "asc" else "ASC"
    query += f" ORDER BY {sort_field} {sort_order} NULLS LAST"

    query += f" LIMIT ${param_num}"
    params.append(limit)

    sequences = await fetch_all(query, *params)

    # Get counts (filtered by strategy_id if provided)
    count_query = """
        SELECT
            COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
            COUNT(*) FILTER (WHERE status = 'approved') as approved_count,
            COUNT(*) FILTER (WHERE status = 'denied') as denied_count,
            COUNT(*) FILTER (WHERE status = 'revision_requested') as revision_count,
            COUNT(*) as total
        FROM strategy_suggestions
        WHERE client_id = $1 AND is_sequence = TRUE
    """
    count_params = [client_id]

    if strategy_id:
        count_query += " AND strategy_id = $2"
        count_params.append(strategy_id)

    counts = await fetch_one(count_query, *count_params)

    return ClientSequencesResponse(
        client_id=client_id,
        sequences=[
            _build_sequence_response(s, s.get("job_round", 1))
            for s in (sequences or [])
        ],
        pending_count=counts["pending_count"] if counts else 0,
        approved_count=counts["approved_count"] if counts else 0,
        denied_count=counts["denied_count"] if counts else 0,
        revision_count=counts["revision_count"] if counts else 0,
        total=counts["total"] if counts else 0,
    )


@router.get("/sequences/{client_id}/{sequence_id}")
async def get_sequence_detail(client_id: UUID, sequence_id: UUID):
    """
    Get a single sequence by ID with full details.
    """
    sequence = await fetch_one("""
        SELECT s.*, j.generation_round as job_round
        FROM strategy_suggestions s
        JOIN strategy_generation_jobs j ON j.id = s.job_id
        WHERE s.id = $1 AND s.client_id = $2 AND s.is_sequence = TRUE
    """, sequence_id, client_id)

    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")

    return _build_sequence_response(sequence, sequence.get("job_round", 1))


@router.patch("/sequences/{sequence_id}")
async def update_sequence_status(sequence_id: UUID, request: SequenceReviewRequest):
    """
    Update a sequence's status - approve or deny the entire sequence.
    """
    sequence = await fetch_one(
        "SELECT id, subject_line FROM strategy_suggestions WHERE id = $1 AND is_sequence = TRUE",
        sequence_id
    )
    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")

    valid_actions = ['approve', 'deny']
    if request.action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be one of: {valid_actions}"
        )

    status_map = {'approve': 'approved', 'deny': 'denied'}
    new_status = status_map[request.action]

    await execute("""
        UPDATE strategy_suggestions
        SET status = $1, human_comment = $2, reviewed_by = $3, reviewed_at = NOW()
        WHERE id = $4
    """, new_status, request.comment, request.reviewer, sequence_id)

    logger.info(f"Sequence {sequence_id} reviewed: {new_status}")

    return {
        "sequence_id": str(sequence_id),
        "campaign_name": sequence["subject_line"],
        "status": new_status,
        "message": f"Sequence {request.action}d successfully"
    }


@router.patch("/sequences/{sequence_id}/emails/{position}")
async def edit_sequence_email(
    sequence_id: UUID,
    position: int,
    request: SequenceEmailEditRequest
):
    """
    Edit a specific email within a sequence.

    Position must be 1-4. Subject line can only be edited for positions 1 and 3
    (new thread emails). Edits are stored separately from original content.
    """
    if position < 1 or position > 4:
        raise HTTPException(status_code=400, detail="Position must be 1-4")

    # Get sequence
    sequence = await fetch_one(
        "SELECT id, sequence_data FROM strategy_suggestions WHERE id = $1 AND is_sequence = TRUE",
        sequence_id
    )
    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")

    sequence_data = sequence.get("sequence_data") or []

    # Find the email at the specified position
    email_found = False
    for email in sequence_data:
        if email.get("position") == position:
            email_found = True
            # Store edits
            email["edited_email_body"] = request.email_body
            if request.subject_line is not None:
                if position not in [1, 3]:
                    raise HTTPException(
                        status_code=400,
                        detail="Subject line can only be edited for Email 1 and 3 (new thread emails)"
                    )
                email["edited_subject_line"] = request.subject_line
            break

    if not email_found:
        raise HTTPException(status_code=404, detail=f"Email at position {position} not found")

    # Update sequence_data
    import json
    await execute("""
        UPDATE strategy_suggestions
        SET sequence_data = $1::jsonb
        WHERE id = $2
    """, json.dumps(sequence_data), sequence_id)

    logger.info(f"Sequence {sequence_id} email {position} edited")

    return {
        "sequence_id": str(sequence_id),
        "position": position,
        "edited_email_body": request.email_body,
        "edited_subject_line": request.subject_line,
        "message": f"Email {position} edited successfully"
    }


@router.post("/sequences/{sequence_id}/revision")
async def request_sequence_revision(sequence_id: UUID, request: SequenceRevisionRequest):
    """
    Request revision for a specific email or entire sequence.

    - email_position: 1-4 for specific email, 0 for whole sequence
    - scope: 'single' (just that email), 'subsequent' (that email and following),
             'all' (regenerate entire sequence)
    """
    # Get sequence info
    sequence = await fetch_one("""
        SELECT s.id, s.job_id, s.client_id, s.strategy_id
        FROM strategy_suggestions s
        WHERE s.id = $1 AND s.is_sequence = TRUE
    """, sequence_id)

    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")

    if request.email_position < 0 or request.email_position > 4:
        raise HTTPException(status_code=400, detail="email_position must be 0-4")

    # Create revision request with scope info
    revision_instruction = request.instruction
    if request.email_position > 0:
        revision_instruction = f"[Email {request.email_position}, scope: {request.scope}] {request.instruction}"

    revision = await fetch_one("""
        INSERT INTO strategy_revision_requests (job_id, client_id, variant_id, instruction)
        VALUES ($1, $2, $3, $4)
        RETURNING id, created_at
    """, sequence["job_id"], sequence["client_id"], sequence_id, revision_instruction)

    # Update sequence status
    await execute("""
        UPDATE strategy_suggestions
        SET status = 'revision_requested'
        WHERE id = $1
    """, sequence_id)

    # Get current generation round and create new job
    last_job = await fetch_one("""
        SELECT generation_round FROM strategy_generation_jobs
        WHERE client_id = $1
        ORDER BY created_at DESC
        LIMIT 1
    """, sequence["client_id"])
    generation_round = (last_job["generation_round"] + 1) if last_job else 1

    new_job = await fetch_one("""
        INSERT INTO strategy_generation_jobs
        (client_id, strategy_id, status, generation_round, revision_of, job_type)
        VALUES ($1, $2, 'pending', $3, $4, 'revision')
        RETURNING id, created_at
    """, sequence["client_id"], sequence.get("strategy_id"), generation_round, sequence_id)

    logger.info(f"Revision job {new_job['id']} created for sequence {sequence_id} (email {request.email_position}, scope {request.scope})")

    return {
        "revision_id": str(revision["id"]),
        "job_id": str(new_job["id"]),
        "sequence_id": str(sequence_id),
        "email_position": request.email_position,
        "scope": request.scope,
        "instruction": request.instruction,
        "status": "revision_queued",
        "message": "Revision request created and generation job queued"
    }


@router.post("/sequences/{sequence_id}/push-to-emailbison")
async def push_sequence_to_emailbison(sequence_id: UUID):
    """
    Push an approved 4-email sequence to EmailBison to create a complete campaign.

    This endpoint:
    1. Validates the sequence is approved and not already pushed
    2. Switches to the correct EmailBison workspace
    3. Creates a campaign with Email 1 subject as name
    4. Adds all 4 sequence steps with correct timing and threading
    5. Updates the sequence status to 'sent'
    """
    # Get sequence with client and workspace info
    sequence = await fetch_one("""
        SELECT s.*, c.name as client_name, w.emailbison_workspace_id
        FROM strategy_suggestions s
        JOIN clients c ON c.id = s.client_id
        LEFT JOIN workspaces w ON w.id = c.workspace_id
        WHERE s.id = $1 AND s.is_sequence = TRUE
    """, sequence_id)

    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")

    if sequence["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail="Only approved sequences can be pushed to EmailBison"
        )

    if sequence.get("pushed_to_emailbison"):
        raise HTTPException(
            status_code=400,
            detail="Sequence has already been pushed to EmailBison"
        )

    emailbison_workspace_id = sequence.get("emailbison_workspace_id")
    if not emailbison_workspace_id:
        raise HTTPException(
            status_code=400,
            detail=f"Client '{sequence['client_name']}' has no EmailBison workspace configured"
        )

    if not EMAILBISON_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="EmailBison API key not configured"
        )

    sequence_data = sequence.get("sequence_data") or []
    if len(sequence_data) != 4:
        raise HTTPException(
            status_code=400,
            detail=f"Sequence has {len(sequence_data)} emails, expected 4"
        )

    # Variable transformation: {{double_braces}} -> {SINGLE_BRACES}
    import re
    def transform_variables(text: str) -> str:
        if not text:
            return text
        # Map of variable names
        var_map = {
            "first_name": "FIRST_NAME",
            "company_name": "COMPANY_NAME",
            "role_title": "JOB_TITLE",
            "industry": "INDUSTRY",
        }
        result = text
        for old_var, new_var in var_map.items():
            result = re.sub(r"\{\{" + old_var + r"\}\}", "{" + new_var + "}", result, flags=re.IGNORECASE)
        # Handle any remaining {{var}} patterns
        result = re.sub(r"\{\{(\w+)\}\}", lambda m: "{" + m.group(1).upper() + "}", result)
        return result

    # Use edited version if available, otherwise original
    campaign_name = sequence.get("subject_line") or "Campaign"

    created_campaign_id = None
    steps_completed = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Switch workspace
            switch_response = await client.post(
                f"{EMAILBISON_API_URL}/api/workspaces/v1.1/switch-workspace",
                headers={
                    "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"team_id": emailbison_workspace_id}
            )

            if switch_response.status_code != 200:
                logger.error(f"Failed to switch workspace: {switch_response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to switch to EmailBison workspace"
                )
            steps_completed.append("workspace_switch")
            logger.info(f"Switched to EmailBison workspace {emailbison_workspace_id}")

            # Step 2: Create campaign
            campaign_response = await client.post(
                f"{EMAILBISON_API_URL}/api/campaigns",
                headers={
                    "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "name": campaign_name,
                    "type": "outbound",
                }
            )

            if campaign_response.status_code not in (200, 201):
                logger.error(f"Failed to create campaign: {campaign_response.text}")
                raise HTTPException(status_code=502, detail="Failed to create EmailBison campaign")

            campaign_data = campaign_response.json()
            created_campaign_id = campaign_data.get("data", {}).get("id") or campaign_data.get("id")
            steps_completed.append("campaign_create")
            logger.info(f"Created EmailBison campaign {created_campaign_id}")

            # Step 3: Add sequence steps (all 4 emails in one request)
            sequence_steps_payload = []
            for email in sorted(sequence_data, key=lambda x: x.get("position", 1)):
                position = email.get("position", 1)
                # Use edited versions if available, check multiple field names
                subject = (
                    email.get("edited_subject_line") or
                    email.get("subject_line") or
                    email.get("subjectLine") or
                    campaign_name  # Fallback to campaign name
                )
                body = (
                    email.get("edited_email_body") or
                    email.get("email_body") or
                    email.get("emailBody") or
                    ""
                )
                # wait_in_days must be at least 1 per EmailBison API
                wait_days = max(email.get("wait_days", 0), 1)

                logger.debug(f"Email {position}: subject='{subject[:50] if subject else 'EMPTY'}...', wait_days={wait_days}")

                sequence_steps_payload.append({
                    "email_subject": transform_variables(subject),
                    "email_body": transform_variables(body),
                    "order": position,
                    "wait_in_days": wait_days,
                    "thread_reply": email.get("thread_reply", False),
                    "variant": False,
                })

            step_response = await client.post(
                f"{EMAILBISON_API_URL}/api/campaigns/{created_campaign_id}/sequence-steps",
                headers={
                    "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "title": campaign_name,
                    "sequence_steps": sequence_steps_payload,
                }
            )

            if step_response.status_code not in (200, 201):
                logger.error(f"Failed to create sequence steps: {step_response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to create sequence steps"
                )
            logger.info(f"Created {len(sequence_steps_payload)} sequence steps for campaign {created_campaign_id}")

            steps_completed.append("sequence_steps")

            # Note: Sender email and leads attachment will be handled separately
            # in dedicated components. This endpoint only creates the campaign structure.

            # Step 4: Configure sending schedule (M-F 8am-5pm)
            try:
                schedule_response = await client.post(
                    f"{EMAILBISON_API_URL}/api/campaigns/{created_campaign_id}/schedule",
                    headers={
                        "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "monday": True,
                        "tuesday": True,
                        "wednesday": True,
                        "thursday": True,
                        "friday": True,
                        "saturday": False,
                        "sunday": False,
                        "start_time": "08:00",
                        "end_time": "17:00",
                        "timezone": "America/New_York",
                        "save_as_template": False
                    }
                )
                if schedule_response.status_code in (200, 201):
                    steps_completed.append("schedule_configured")
                    logger.info(f"Configured M-F 8am-5pm schedule for campaign {created_campaign_id}")
                else:
                    logger.warning(f"Failed to configure schedule: {schedule_response.text}")
            except Exception as e:
                logger.warning(f"Failed to configure schedule: {e}")

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to EmailBison: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to connect to EmailBison: {str(e)}"
        )

    # Update sequence status to 'sent'
    await execute("""
        UPDATE strategy_suggestions
        SET status = 'sent', pushed_to_emailbison = TRUE, pushed_at = NOW()
        WHERE id = $1
    """, sequence_id)

    logger.info(f"Pushed sequence {sequence_id} to EmailBison as campaign {created_campaign_id}")

    return {
        "sequence_id": str(sequence_id),
        "client_id": str(sequence["client_id"]),
        "client_name": sequence["client_name"],
        "emailbison_workspace_id": emailbison_workspace_id,
        "emailbison_campaign_id": created_campaign_id,
        "campaign_name": campaign_name,
        "emails_pushed": len(sequence_data),
        "schedule_configured": "schedule_configured" in steps_completed,
        "steps_completed": steps_completed,
        "status": "draft",
        "message": "4-email campaign created in EmailBison as draft",
        "next_steps": ["Assign sender emails", "Add leads list", "Review and activate"]
    }


# ============================================================================
# Database Migration - Remove Legacy Single-Variant Records
# ============================================================================

@router.get("/admin/migration/005-cleanup-legacy/preflight")
async def migration_005_preflight():
    """
    Pre-flight check for migration 005: Remove legacy single-variant records.
    Returns counts of records that would be affected WITHOUT making changes.
    """
    # Count legacy suggestions (is_sequence = FALSE or NULL)
    legacy_count = await fetch_one("""
        SELECT COUNT(*) as count FROM strategy_suggestions
        WHERE is_sequence = FALSE OR is_sequence IS NULL
    """)

    # Count sequence records (is_sequence = TRUE)
    sequence_count = await fetch_one("""
        SELECT COUNT(*) as count FROM strategy_suggestions
        WHERE is_sequence = TRUE
    """)

    # Count jobs that would become orphaned
    orphaned_jobs = await fetch_one("""
        SELECT COUNT(*) as count FROM strategy_generation_jobs
        WHERE id NOT IN (
            SELECT DISTINCT job_id FROM strategy_suggestions
            WHERE job_id IS NOT NULL AND is_sequence = TRUE
        )
    """)

    # Count revision requests that would become orphaned
    orphaned_revisions = await fetch_one("""
        SELECT COUNT(*) as count FROM strategy_revision_requests
        WHERE variant_id IS NOT NULL
        AND variant_id IN (
            SELECT id FROM strategy_suggestions
            WHERE is_sequence = FALSE OR is_sequence IS NULL
        )
    """)

    # Check current constraint status
    constraint_exists = await fetch_one("""
        SELECT COUNT(*) as count FROM information_schema.table_constraints
        WHERE constraint_name = 'chk_is_sequence_true'
        AND table_name = 'strategy_suggestions'
    """)

    return {
        "migration": "005-remove-legacy-single-variants",
        "status": "preflight",
        "will_delete": {
            "legacy_suggestions": legacy_count["count"] if legacy_count else 0,
            "orphaned_jobs": orphaned_jobs["count"] if orphaned_jobs else 0,
            "orphaned_revisions": orphaned_revisions["count"] if orphaned_revisions else 0,
        },
        "will_keep": {
            "sequence_suggestions": sequence_count["count"] if sequence_count else 0,
        },
        "constraint_already_exists": (constraint_exists["count"] if constraint_exists else 0) > 0,
        "safe_to_run": True,
        "message": "Use POST /admin/migration/005-cleanup-legacy/execute to run migration"
    }


@router.post("/admin/migration/005-cleanup-legacy/execute")
async def migration_005_execute(confirm: bool = False):
    """
    Execute migration 005: Remove legacy single-variant records.

    This migration:
    1. Deletes suggestions where is_sequence = FALSE or NULL
    2. Deletes orphaned revision requests
    3. Deletes orphaned jobs
    4. Sets is_sequence default to TRUE
    5. Adds NOT NULL constraint
    6. Adds CHECK constraint (is_sequence = TRUE)

    IRREVERSIBLE - deleted data cannot be recovered.
    """
    if not confirm:
        return {
            "status": "confirmation_required",
            "message": "Add ?confirm=true to execute this irreversible migration",
            "warning": "This will permanently delete legacy records"
        }

    results = {
        "migration": "005-remove-legacy-single-variants",
        "status": "executing",
        "steps": []
    }

    try:
        # Step 1: Delete revision requests pointing to legacy suggestions (FK constraint)
        revisions_deleted = await execute("""
            DELETE FROM strategy_revision_requests
            WHERE variant_id IN (
                SELECT id FROM strategy_suggestions
                WHERE is_sequence = FALSE OR is_sequence IS NULL
            )
        """)
        results["steps"].append({
            "step": 1,
            "action": "delete_legacy_revisions",
            "result": revisions_deleted
        })

        # Step 2: Nullify revision_of references in jobs pointing to legacy suggestions (FK constraint)
        jobs_updated = await execute("""
            UPDATE strategy_generation_jobs
            SET revision_of = NULL
            WHERE revision_of IN (
                SELECT id FROM strategy_suggestions
                WHERE is_sequence = FALSE OR is_sequence IS NULL
            )
        """)
        results["steps"].append({
            "step": 2,
            "action": "nullify_revision_of_references",
            "result": jobs_updated
        })

        # Step 3: Delete legacy suggestions (now safe - no FK references)
        legacy_deleted = await execute("""
            DELETE FROM strategy_suggestions
            WHERE is_sequence = FALSE OR is_sequence IS NULL
        """)
        results["steps"].append({
            "step": 3,
            "action": "delete_legacy_suggestions",
            "result": legacy_deleted
        })

        # Step 4: Delete any remaining orphaned revision requests
        orphan_revisions_deleted = await execute("""
            DELETE FROM strategy_revision_requests
            WHERE variant_id IS NOT NULL
            AND variant_id NOT IN (SELECT id FROM strategy_suggestions)
        """)
        results["steps"].append({
            "step": 4,
            "action": "delete_orphaned_revisions",
            "result": orphan_revisions_deleted
        })

        # Step 5: Delete orphaned jobs
        jobs_deleted = await execute("""
            DELETE FROM strategy_generation_jobs
            WHERE id NOT IN (
                SELECT DISTINCT job_id FROM strategy_suggestions
                WHERE job_id IS NOT NULL
            )
        """)
        results["steps"].append({
            "step": 5,
            "action": "delete_orphaned_jobs",
            "result": jobs_deleted
        })

        # Step 6: Set default value
        try:
            await execute("""
                ALTER TABLE strategy_suggestions
                ALTER COLUMN is_sequence SET DEFAULT TRUE
            """)
            results["steps"].append({
                "step": 6,
                "action": "set_default_true",
                "result": "success"
            })
        except Exception as e:
            results["steps"].append({
                "step": 6,
                "action": "set_default_true",
                "result": f"skipped: {str(e)}"
            })

        # Step 7: Update any remaining NULL values and add NOT NULL
        try:
            await execute("""
                UPDATE strategy_suggestions SET is_sequence = TRUE WHERE is_sequence IS NULL
            """)
            await execute("""
                ALTER TABLE strategy_suggestions
                ALTER COLUMN is_sequence SET NOT NULL
            """)
            results["steps"].append({
                "step": 7,
                "action": "add_not_null_constraint",
                "result": "success"
            })
        except Exception as e:
            results["steps"].append({
                "step": 7,
                "action": "add_not_null_constraint",
                "result": f"skipped: {str(e)}"
            })

        # Step 8: Add CHECK constraint
        try:
            await execute("""
                ALTER TABLE strategy_suggestions
                ADD CONSTRAINT chk_is_sequence_true CHECK (is_sequence = TRUE)
            """)
            results["steps"].append({
                "step": 8,
                "action": "add_check_constraint",
                "result": "success"
            })
        except Exception as e:
            results["steps"].append({
                "step": 8,
                "action": "add_check_constraint",
                "result": f"skipped (may already exist): {str(e)}"
            })

        # Verify final state
        final_count = await fetch_one("""
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE is_sequence = TRUE) as sequences,
                   COUNT(*) FILTER (WHERE is_sequence = FALSE) as legacy
            FROM strategy_suggestions
        """)

        results["status"] = "completed"
        results["final_state"] = {
            "total_suggestions": final_count["total"] if final_count else 0,
            "sequences": final_count["sequences"] if final_count else 0,
            "legacy": final_count["legacy"] if final_count else 0,
        }
        results["message"] = "Migration completed successfully"

    except Exception as e:
        results["status"] = "failed"
        results["error"] = str(e)
        logger.error(f"Migration 005 failed: {e}")

    return results
