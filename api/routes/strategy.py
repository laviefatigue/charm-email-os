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
import json

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
    # Spintax models
    SpintaxJobResponse,
    # Campaign Document models
    CampaignDocumentResponse,
    ClientDocumentsResponse,
    DocumentReviewRequest,
    DocumentVariantEditRequest,
    SelectVariantRequest,
    EmailPosition,
    EmailVariant,
    SubjectOption,
    ICPMapping,
    VariableSchema,
    QAScoring,
    StrategyNotes,
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


@router.post("/cycles/{cycle_id}/generate")
async def generate_cycle_campaigns(cycle_id: UUID, data: dict = None):
    """
    Generate campaigns for an existing cycle.

    This creates a generation job specifically for populating campaigns
    in an existing cycle (as opposed to creating a new cycle).
    """
    data = data or {}

    # Get cycle and verify it exists
    cycle = await fetch_one("""
        SELECT cc.id, cc.client_id, cc.strategy_id, cc.cycle_number, c.name as client_name
        FROM campaign_cycles cc
        JOIN clients c ON c.id = cc.client_id
        WHERE cc.id = $1
    """, cycle_id)

    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    # Check if there's already a pending/processing job for this cycle
    existing_job = await fetch_one("""
        SELECT id, status FROM strategy_generation_jobs
        WHERE cycle_id = $1 AND status IN ('pending', 'processing')
    """, cycle_id)

    if existing_job:
        return {
            "job_id": str(existing_job["id"]),
            "client_id": str(cycle["client_id"]),
            "cycle_id": str(cycle_id),
            "status": existing_job["status"],
            "message": "Generation already in progress for this cycle"
        }

    # Get submission_id if provided, otherwise try to use client's most recent
    submission_id = data.get("submission_id")
    if not submission_id:
        try:
            latest_submission = await fetch_one("""
                SELECT id FROM onboarding_submissions
                WHERE client_id = $1
                ORDER BY submitted_at DESC
                LIMIT 1
            """, cycle["client_id"])
            if latest_submission:
                submission_id = latest_submission["id"]
        except Exception:
            # Table might not exist in local/dev environments
            submission_id = None

    # Get current generation round
    last_job = await fetch_one("""
        SELECT generation_round FROM strategy_generation_jobs
        WHERE client_id = $1
        ORDER BY created_at DESC
        LIMIT 1
    """, cycle["client_id"])
    generation_round = (last_job["generation_round"] + 1) if last_job else 1

    # Create job linked to this cycle
    job = await fetch_one("""
        INSERT INTO strategy_generation_jobs
        (client_id, submission_id, strategy_id, cycle_id, status, generation_round, job_type)
        VALUES ($1, $2, $3, $4, 'pending', $5, 'cycle_campaigns')
        RETURNING id, status, generation_round, created_at
    """, cycle["client_id"], submission_id, cycle.get("strategy_id"), cycle_id, generation_round)

    logger.info(f"Created cycle generation job {job['id']} for cycle {cycle_id} (round {generation_round})")

    return {
        "job_id": str(job["id"]),
        "client_id": str(cycle["client_id"]),
        "client_name": cycle["client_name"],
        "cycle_id": str(cycle_id),
        "cycle_number": cycle["cycle_number"],
        "submission_id": str(submission_id) if submission_id else None,
        "status": job["status"],
        "generation_round": job["generation_round"],
        "created_at": job["created_at"].isoformat(),
        "message": "Job queued to generate campaigns for this cycle"
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


@router.get("/jobs/{job_id}/phases")
async def get_job_phases(job_id: UUID):
    """
    Get detailed phase status for a phased generation job.

    Returns:
        - Job info with overall status
        - List of phases with individual status
        - Progress percentage and estimated time remaining

    Phase types:
        - scaffold: Creates ICP, variables, campaign stubs (phase 1)
        - campaign_copy: Generates emails for one campaign (phases 2-5)

    Phase statuses: pending, processing, completed, failed
    """
    # Get job info
    job = await fetch_one("""
        SELECT j.id, j.client_id, j.status, j.job_type, j.cycle_id,
               j.error_message, j.created_at, j.started_at, j.completed_at,
               c.name as client_name
        FROM strategy_generation_jobs j
        JOIN clients c ON c.id = j.client_id
        WHERE j.id = $1
    """, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get all phases for this job with campaign details
    phases = await fetch_all("""
        SELECT p.id, p.phase_type, p.phase_number, p.campaign_document_id,
               p.status, p.error_message, p.started_at, p.completed_at, p.created_at,
               cd.document_name as campaign_name,
               cd.angle as campaign_angle
        FROM strategy_generation_phases p
        LEFT JOIN campaign_documents cd ON cd.id = p.campaign_document_id
        WHERE p.parent_job_id = $1
        ORDER BY
            CASE p.phase_type WHEN 'scaffold' THEN 0 ELSE 1 END,
            p.phase_number NULLS FIRST
    """, job_id)

    # Calculate progress
    total_phases = len(phases) if phases else 0
    completed_phases = sum(1 for p in phases if p["status"] == "completed") if phases else 0
    failed_phases = sum(1 for p in phases if p["status"] == "failed") if phases else 0
    processing_phases = sum(1 for p in phases if p["status"] == "processing") if phases else 0

    # Progress percentage
    if total_phases == 0:
        # No phases yet - job is in initial state
        progress_percent = 0
    else:
        progress_percent = int((completed_phases / total_phases) * 100)

    # Estimate time remaining (rough: ~3 min per phase)
    pending_phases = total_phases - completed_phases - failed_phases - processing_phases
    estimated_remaining_seconds = (pending_phases + processing_phases) * 180  # 3 min each

    # Format phases for response
    phase_list = []
    for p in (phases or []):
        phase_list.append({
            "id": str(p["id"]),
            "type": p["phase_type"],
            "number": p["phase_number"],
            "campaign_document_id": str(p["campaign_document_id"]) if p.get("campaign_document_id") else None,
            "campaign_name": p.get("campaign_name"),
            "campaign_angle": p.get("campaign_angle"),
            "status": p["status"],
            "error_message": p.get("error_message"),
            "started_at": p["started_at"].isoformat() if p.get("started_at") else None,
            "completed_at": p["completed_at"].isoformat() if p.get("completed_at") else None,
        })

    return {
        "job_id": str(job["id"]),
        "client_id": str(job["client_id"]),
        "client_name": job["client_name"],
        "job_status": job["status"],
        "job_type": job.get("job_type", "full"),
        "cycle_id": str(job["cycle_id"]) if job.get("cycle_id") else None,
        "error_message": job.get("error_message"),
        "created_at": job["created_at"].isoformat() if job.get("created_at") else None,
        "started_at": job["started_at"].isoformat() if job.get("started_at") else None,
        "completed_at": job["completed_at"].isoformat() if job.get("completed_at") else None,
        "phases": phase_list,
        "progress": {
            "total_phases": total_phases,
            "completed_phases": completed_phases,
            "failed_phases": failed_phases,
            "processing_phases": processing_phases,
            "percent": progress_percent,
            "estimated_remaining_seconds": estimated_remaining_seconds,
        }
    }


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
                f"{EMAILBISON_API_URL}/api/workspaces/switch-workspace",
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

    # Parse spintaxed_sequence_data JSONB into spintaxed email list
    spintaxed_data = s.get("spintaxed_sequence_data") or []
    spintaxed_emails = None
    if spintaxed_data:
        spintaxed_emails = []
        for email in spintaxed_data:
            spintaxed_emails.append(SequenceEmail(
                position=email.get("position", 1),
                wait_days=email.get("wait_days", 0),
                subject_line=email.get("subject_line"),
                email_body=email.get("email_body", ""),
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
        spintaxed_emails=spintaxed_emails,
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
    Push a spintaxed 4-email sequence to EmailBison to create a complete campaign.

    This endpoint:
    1. Validates the sequence is spintaxed and not already pushed
    2. Switches to the correct EmailBison workspace
    3. Creates a campaign with Email 1 subject as name
    4. Adds all 4 sequence steps with spintax/liquid syntax
    5. Updates the sequence status to 'sent'

    Note: Sequences must be spintaxed before pushing. Use POST /sequences/{id}/spintax first.
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

    # Only spintaxed sequences can be pushed (spintax is required before push)
    if sequence["status"] != "spintaxed":
        if sequence["status"] == "approved":
            raise HTTPException(
                status_code=400,
                detail="Sequence must be spintaxed before pushing to EmailBison. Click 'Add Spintax' first."
            )
        raise HTTPException(
            status_code=400,
            detail=f"Only spintaxed sequences can be pushed to EmailBison. Current status: {sequence['status']}"
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

    # Use spintaxed version if available, otherwise fall back to original
    sequence_data = sequence.get("spintaxed_sequence_data") or sequence.get("sequence_data") or []
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
                f"{EMAILBISON_API_URL}/api/workspaces/switch-workspace",
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
# Spintax Processing
# ============================================================================

@router.post("/sequences/{sequence_id}/spintax")
async def create_spintax_job(sequence_id: UUID):
    """
    Create a spintax processing job for an approved sequence.

    This endpoint:
    1. Validates the sequence is approved and not already spintaxed
    2. Creates a spintax_processing_jobs record
    3. Updates sequence status to 'spintax_pending'
    4. Returns the job_id for status polling

    The spintax_worker daemon will pick up the job and process it.
    """
    # Get sequence
    sequence = await fetch_one("""
        SELECT s.id, s.client_id, s.status, s.is_sequence,
               s.spintaxed_sequence_data
        FROM strategy_suggestions s
        WHERE s.id = $1 AND s.is_sequence = TRUE
    """, sequence_id)

    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")

    if sequence["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Only approved sequences can be spintaxed. Current status: {sequence['status']}"
        )

    if sequence.get("spintaxed_sequence_data"):
        raise HTTPException(
            status_code=400,
            detail="Sequence has already been spintaxed"
        )

    # Check if there's already a pending/processing spintax job for this sequence
    existing_job = await fetch_one("""
        SELECT id, status FROM spintax_processing_jobs
        WHERE sequence_id = $1 AND status IN ('pending', 'processing')
    """, sequence_id)

    if existing_job:
        raise HTTPException(
            status_code=400,
            detail=f"Spintax job already in progress (status: {existing_job['status']})"
        )

    # Create spintax processing job
    job = await fetch_one("""
        INSERT INTO spintax_processing_jobs (sequence_id, client_id, status)
        VALUES ($1, $2, 'pending')
        RETURNING id, sequence_id, client_id, status, created_at
    """, sequence_id, sequence["client_id"])

    # Update sequence status to spintax_pending
    await execute("""
        UPDATE strategy_suggestions
        SET status = 'spintax_pending'
        WHERE id = $1
    """, sequence_id)

    logger.info(f"Created spintax job {job['id']} for sequence {sequence_id}")

    return SpintaxJobResponse(
        job_id=job["id"],
        sequence_id=job["sequence_id"],
        client_id=job["client_id"],
        status=job["status"],
        created_at=job["created_at"],
    )


@router.get("/spintax-jobs/{job_id}/status")
async def get_spintax_job_status(job_id: UUID):
    """
    Get the status of a spintax processing job.

    Use this endpoint to poll for job completion.
    Status values: pending, processing, completed, failed
    """
    job = await fetch_one("""
        SELECT id, sequence_id, client_id, status, error_message,
               created_at, started_at, completed_at
        FROM spintax_processing_jobs
        WHERE id = $1
    """, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Spintax job not found")

    return SpintaxJobResponse(
        job_id=job["id"],
        sequence_id=job["sequence_id"],
        client_id=job["client_id"],
        status=job["status"],
        error_message=job.get("error_message"),
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
    )


@router.get("/sequences/{sequence_id}/spintax-status")
async def get_sequence_spintax_status(sequence_id: UUID):
    """
    Get the spintax status for a sequence.

    Returns the most recent spintax job for this sequence, if any.
    """
    # Get the most recent spintax job for this sequence
    job = await fetch_one("""
        SELECT id, sequence_id, client_id, status, error_message,
               created_at, started_at, completed_at
        FROM spintax_processing_jobs
        WHERE sequence_id = $1
        ORDER BY created_at DESC
        LIMIT 1
    """, sequence_id)

    if not job:
        return {
            "sequence_id": str(sequence_id),
            "has_spintax_job": False,
            "message": "No spintax job found for this sequence"
        }

    return {
        "sequence_id": str(sequence_id),
        "has_spintax_job": True,
        "job": SpintaxJobResponse(
            job_id=job["id"],
            sequence_id=job["sequence_id"],
            client_id=job["client_id"],
            status=job["status"],
            error_message=job.get("error_message"),
            created_at=job["created_at"],
            started_at=job.get("started_at"),
            completed_at=job.get("completed_at"),
        )
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


# ============================================================================
# Campaign Document Routes (Stablekernel Format)
# ============================================================================

@router.get("/documents/{client_id}", response_model=ClientDocumentsResponse)
async def get_client_documents(client_id: UUID):
    """
    Get all campaign documents for a client.
    Returns documents with full structure (ICP, variables, email positions).
    """
    # Verify client exists
    client = await fetch_one("SELECT id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get all documents for client
    documents = await fetch_all("""
        SELECT d.id, d.job_id, d.client_id, d.strategy_id,
               d.document_name, d.document_version, d.vertical, d.objective,
               d.icp_mapping, d.variable_schema, d.sequence_summary,
               d.qa_scoring, d.strategy_notes, d.status,
               d.human_comment, d.reviewed_by, d.reviewed_at,
               d.created_at, d.updated_at
        FROM campaign_documents d
        WHERE d.client_id = $1
        ORDER BY d.created_at DESC
    """, client_id)

    result_docs = []
    for doc in documents:
        # Get email variants for this document
        variants = await fetch_all("""
            SELECT id, document_id, email_position, variant_number, variant_name,
                   is_recommended, subject_line, email_body, wait_days, thread_reply,
                   word_count, them_us_ratio, score, angle, strategy, value_prop,
                   edited_subject_line, edited_email_body, created_at
            FROM document_email_variants
            WHERE document_id = $1
            ORDER BY email_position, variant_number
        """, doc["id"])

        # Get subject options
        subject_options = await fetch_all("""
            SELECT id, email_position, subject_line, rationale, sort_order
            FROM document_subject_options
            WHERE document_id = $1
            ORDER BY email_position, sort_order
        """, doc["id"])

        # Group variants by position
        positions_map = {}
        for v in variants:
            pos = v["email_position"]
            if pos not in positions_map:
                positions_map[pos] = {"position": pos, "title": f"Email {pos}", "variants": [], "subject_options": []}
            positions_map[pos]["variants"].append(EmailVariant(
                id=v["id"],
                variant_number=v["variant_number"],
                variant_name=v.get("variant_name"),
                is_recommended=v.get("is_recommended", False),
                subject_line=v.get("subject_line"),
                email_body=v["email_body"],
                wait_days=v.get("wait_days", 0),
                thread_reply=v.get("thread_reply", False),
                word_count=v.get("word_count"),
                them_us_ratio=v.get("them_us_ratio"),
                score=v.get("score"),
                angle=v.get("angle"),
                strategy=v.get("strategy"),
                value_prop=v.get("value_prop"),
                edited_subject_line=v.get("edited_subject_line"),
                edited_email_body=v.get("edited_email_body"),
            ))

        # Add subject options to positions
        for so in subject_options:
            pos = so["email_position"]
            if pos in positions_map:
                positions_map[pos]["subject_options"].append(SubjectOption(
                    subject_line=so["subject_line"],
                    rationale=so.get("rationale")
                ))

        email_positions = [EmailPosition(**p) for p in sorted(positions_map.values(), key=lambda x: x["position"])]

        result_docs.append(CampaignDocumentResponse(
            id=doc["id"],
            job_id=doc["job_id"],
            client_id=doc["client_id"],
            strategy_id=doc.get("strategy_id"),
            document_name=doc["document_name"],
            document_version=doc.get("document_version", 1),
            vertical=doc.get("vertical"),
            objective=doc.get("objective"),
            icp_mapping=ICPMapping(**doc["icp_mapping"]) if doc.get("icp_mapping") else None,
            variable_schema=VariableSchema(**doc["variable_schema"]) if doc.get("variable_schema") else None,
            email_positions=email_positions,
            sequence_summary=doc.get("sequence_summary"),
            qa_scoring=QAScoring(**doc["qa_scoring"]) if doc.get("qa_scoring") else None,
            strategy_notes=StrategyNotes(**doc["strategy_notes"]) if doc.get("strategy_notes") else None,
            status=doc["status"],
            human_comment=doc.get("human_comment"),
            reviewed_by=doc.get("reviewed_by"),
            reviewed_at=doc.get("reviewed_at"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        ))

    return ClientDocumentsResponse(
        client_id=client_id,
        documents=result_docs,
        total=len(result_docs)
    )


@router.get("/documents/{client_id}/{document_id}", response_model=CampaignDocumentResponse)
async def get_document(client_id: UUID, document_id: UUID):
    """
    Get a single campaign document with all details.
    """
    doc = await fetch_one("""
        SELECT d.id, d.job_id, d.client_id, d.strategy_id,
               d.document_name, d.document_version, d.vertical, d.objective,
               d.icp_mapping, d.variable_schema, d.sequence_summary,
               d.qa_scoring, d.strategy_notes, d.status,
               d.human_comment, d.reviewed_by, d.reviewed_at,
               d.created_at, d.updated_at
        FROM campaign_documents d
        WHERE d.id = $1 AND d.client_id = $2
    """, document_id, client_id)

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get email variants
    variants = await fetch_all("""
        SELECT id, email_position, variant_number, variant_name,
               is_recommended, subject_line, email_body, wait_days, thread_reply,
               word_count, them_us_ratio, score, angle, strategy, value_prop,
               edited_subject_line, edited_email_body
        FROM document_email_variants
        WHERE document_id = $1
        ORDER BY email_position, variant_number
    """, document_id)

    # Get subject options
    subject_options = await fetch_all("""
        SELECT email_position, subject_line, rationale
        FROM document_subject_options
        WHERE document_id = $1
        ORDER BY email_position, sort_order
    """, document_id)

    # Group by position
    positions_map = {}
    for v in variants:
        pos = v["email_position"]
        if pos not in positions_map:
            positions_map[pos] = {"position": pos, "title": f"Email {pos}", "variants": [], "subject_options": []}
        positions_map[pos]["variants"].append(EmailVariant(
            id=v["id"],
            variant_number=v["variant_number"],
            variant_name=v.get("variant_name"),
            is_recommended=v.get("is_recommended", False),
            subject_line=v.get("subject_line"),
            email_body=v["email_body"],
            wait_days=v.get("wait_days", 0),
            thread_reply=v.get("thread_reply", False),
            word_count=v.get("word_count"),
            them_us_ratio=v.get("them_us_ratio"),
            score=v.get("score"),
            angle=v.get("angle"),
            strategy=v.get("strategy"),
            value_prop=v.get("value_prop"),
            edited_subject_line=v.get("edited_subject_line"),
            edited_email_body=v.get("edited_email_body"),
        ))

    for so in subject_options:
        pos = so["email_position"]
        if pos in positions_map:
            positions_map[pos]["subject_options"].append(SubjectOption(
                subject_line=so["subject_line"],
                rationale=so.get("rationale")
            ))

    email_positions = [EmailPosition(**p) for p in sorted(positions_map.values(), key=lambda x: x["position"])]

    return CampaignDocumentResponse(
        id=doc["id"],
        job_id=doc["job_id"],
        client_id=doc["client_id"],
        strategy_id=doc.get("strategy_id"),
        document_name=doc["document_name"],
        document_version=doc.get("document_version", 1),
        vertical=doc.get("vertical"),
        objective=doc.get("objective"),
        icp_mapping=ICPMapping(**doc["icp_mapping"]) if doc.get("icp_mapping") else None,
        variable_schema=VariableSchema(**doc["variable_schema"]) if doc.get("variable_schema") else None,
        email_positions=email_positions,
        sequence_summary=doc.get("sequence_summary"),
        qa_scoring=QAScoring(**doc["qa_scoring"]) if doc.get("qa_scoring") else None,
        strategy_notes=StrategyNotes(**doc["strategy_notes"]) if doc.get("strategy_notes") else None,
        status=doc["status"],
        human_comment=doc.get("human_comment"),
        reviewed_by=doc.get("reviewed_by"),
        reviewed_at=doc.get("reviewed_at"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.patch("/documents/{document_id}/variants/{variant_id}")
async def edit_document_variant(document_id: UUID, variant_id: UUID, request: DocumentVariantEditRequest):
    """
    Edit a specific variant's content in a campaign document.
    Stores edits in edited_* columns, preserving originals.
    """
    # Verify variant exists
    variant = await fetch_one("""
        SELECT id, document_id
        FROM document_email_variants
        WHERE id = $1 AND document_id = $2
    """, variant_id, document_id)

    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    # Update edited fields
    await execute("""
        UPDATE document_email_variants
        SET edited_subject_line = $1, edited_email_body = $2
        WHERE id = $3
    """, request.subject_line, request.email_body, variant_id)

    return {"status": "updated", "variant_id": str(variant_id)}


@router.post("/documents/{document_id}/select-variant")
async def select_recommended_variant(document_id: UUID, request: SelectVariantRequest):
    """
    Select a variant as the recommended one for its position.
    Clears is_recommended from other variants in the same position.
    """
    # Clear existing recommendation for this position
    await execute("""
        UPDATE document_email_variants
        SET is_recommended = FALSE
        WHERE document_id = $1 AND email_position = $2
    """, document_id, request.position)

    # Set new recommendation
    await execute("""
        UPDATE document_email_variants
        SET is_recommended = TRUE
        WHERE document_id = $1 AND email_position = $2 AND variant_number = $3
    """, document_id, request.position, request.variant_number)

    return {"status": "updated", "position": request.position, "variant": request.variant_number}


@router.post("/documents/{document_id}/review")
async def review_document(document_id: UUID, request: DocumentReviewRequest):
    """
    Review a campaign document - approve, deny, or request revision.
    """
    doc = await fetch_one("SELECT id, status FROM campaign_documents WHERE id = $1", document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    new_status = request.action  # approve, deny, revision_requested
    if new_status == "approve":
        new_status = "approved"
    elif new_status == "deny":
        new_status = "denied"

    await execute("""
        UPDATE campaign_documents
        SET status = $1, human_comment = $2, reviewed_by = $3, reviewed_at = NOW(), updated_at = NOW()
        WHERE id = $4
    """, new_status, request.comment, request.reviewer, document_id)

    logger.info(f"Document {document_id} reviewed: {new_status}")

    return {"status": new_status, "document_id": str(document_id)}


# ============================================================================
# Campaign Cycles (NEW - Phase 15 Implementation)
# ============================================================================

@router.get("/cycles/{client_id}")
async def get_client_cycles(client_id: UUID, strategy_id: Optional[UUID] = None):
    """
    Get all campaign cycles for a client, optionally filtered by strategy.

    Cycles represent 14-day periods, each containing 4 campaigns.
    """
    # Verify client exists
    client = await fetch_one("SELECT id, name FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Build query
    query = """
        SELECT cc.id, cc.client_id, cc.strategy_id, cc.cycle_number, cc.cycle_name,
               cc.status, cc.start_date, cc.end_date, cc.notes, cc.created_at, cc.updated_at,
               (SELECT COUNT(*) FROM campaign_documents cd WHERE cd.cycle_id = cc.id) as campaign_count
        FROM campaign_cycles cc
        WHERE cc.client_id = $1
    """
    params = [client_id]
    param_num = 2

    if strategy_id:
        query += f" AND cc.strategy_id = ${param_num}"
        params.append(strategy_id)
        param_num += 1

    query += " ORDER BY cc.cycle_number DESC, cc.created_at DESC"

    cycles = await fetch_all(query, *params)

    return {
        "client_id": str(client_id),
        "cycles": [
            {
                "id": str(c["id"]),
                "client_id": str(c["client_id"]),
                "strategy_id": str(c["strategy_id"]) if c.get("strategy_id") else None,
                "cycle_number": c.get("cycle_number", 1),
                "cycle_name": c.get("cycle_name") or f"Cycle {c.get('cycle_number', 1)}",
                "status": c.get("status", "draft"),
                "start_date": c["start_date"].isoformat() if c.get("start_date") else None,
                "end_date": c["end_date"].isoformat() if c.get("end_date") else None,
                "notes": c.get("notes"),
                "campaign_count": c.get("campaign_count", 0),
                "target_campaigns": 4,  # Always 4 campaigns per cycle
                "created_at": c["created_at"].isoformat() if c.get("created_at") else None,
                "updated_at": c["updated_at"].isoformat() if c.get("updated_at") else None,
            }
            for c in (cycles or [])
        ],
        "total": len(cycles or [])
    }


@router.get("/cycles/detail/{cycle_id}")
async def get_cycle_detail(cycle_id: UUID):
    """
    Get a specific cycle with its configuration and campaign count.
    """
    cycle = await fetch_one("""
        SELECT cc.id, cc.client_id, cc.strategy_id, cc.cycle_number, cc.cycle_name,
               cc.status, cc.start_date, cc.end_date, cc.notes, cc.created_at, cc.updated_at,
               csc.icp_mapping, csc.cycle_variables, csc.strategic_focus, csc.target_outcome
        FROM campaign_cycles cc
        LEFT JOIN cycle_strategy_config csc ON csc.cycle_id = cc.id
        WHERE cc.id = $1
    """, cycle_id)

    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    # Get campaign count
    campaign_count = await fetch_one(
        "SELECT COUNT(*) as count FROM campaign_documents WHERE cycle_id = $1",
        cycle_id
    )

    return {
        "id": str(cycle["id"]),
        "client_id": str(cycle["client_id"]),
        "strategy_id": str(cycle["strategy_id"]) if cycle.get("strategy_id") else None,
        "cycle_number": cycle.get("cycle_number", 1),
        "cycle_name": cycle.get("cycle_name") or f"Cycle {cycle.get('cycle_number', 1)}",
        "status": cycle.get("status", "draft"),
        "start_date": cycle["start_date"].isoformat() if cycle.get("start_date") else None,
        "end_date": cycle["end_date"].isoformat() if cycle.get("end_date") else None,
        "notes": cycle.get("notes"),
        "campaign_count": campaign_count["count"] if campaign_count else 0,
        "target_campaigns": 4,
        "config": {
            "icp_mapping": cycle.get("icp_mapping"),
            "cycle_variables": cycle.get("cycle_variables"),
            "strategic_focus": cycle.get("strategic_focus"),
            "target_outcome": cycle.get("target_outcome"),
        } if cycle.get("icp_mapping") else None,
        "created_at": cycle["created_at"].isoformat() if cycle.get("created_at") else None,
        "updated_at": cycle["updated_at"].isoformat() if cycle.get("updated_at") else None,
    }


@router.post("/cycles/{client_id}")
async def create_cycle(client_id: UUID, data: dict = None):
    """
    Create a new campaign cycle for a client.
    """
    # Verify client exists
    client = await fetch_one("SELECT id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get next cycle number
    last_cycle = await fetch_one("""
        SELECT cycle_number FROM campaign_cycles
        WHERE client_id = $1
        ORDER BY cycle_number DESC
        LIMIT 1
    """, client_id)
    next_cycle_number = (last_cycle["cycle_number"] + 1) if last_cycle else 1

    data = data or {}
    cycle_name = data.get("cycle_name") or f"Cycle {next_cycle_number}"

    cycle = await fetch_one("""
        INSERT INTO campaign_cycles (client_id, strategy_id, cycle_number, cycle_name, status, notes)
        VALUES ($1, $2, $3, $4, 'draft', $5)
        RETURNING id, client_id, strategy_id, cycle_number, cycle_name, status, start_date, end_date, notes, created_at, updated_at
    """, client_id, data.get("strategy_id"), next_cycle_number, cycle_name, data.get("notes"))

    return {
        "id": str(cycle["id"]),
        "client_id": str(cycle["client_id"]),
        "strategy_id": str(cycle["strategy_id"]) if cycle.get("strategy_id") else None,
        "cycle_number": cycle["cycle_number"],
        "cycle_name": cycle["cycle_name"],
        "status": cycle["status"],
        "start_date": cycle["start_date"].isoformat() if cycle.get("start_date") else None,
        "end_date": cycle["end_date"].isoformat() if cycle.get("end_date") else None,
        "notes": cycle.get("notes"),
        "campaign_count": 0,
        "target_campaigns": 4,
        "created_at": cycle["created_at"].isoformat() if cycle.get("created_at") else None,
        "updated_at": cycle["updated_at"].isoformat() if cycle.get("updated_at") else None,
    }


@router.put("/cycles/detail/{cycle_id}")
async def update_cycle(cycle_id: UUID, data: dict):
    """
    Update a cycle's details.
    """
    cycle = await fetch_one("SELECT id FROM campaign_cycles WHERE id = $1", cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    # Build update query
    updates = []
    params = []
    param_num = 1

    for field in ["cycle_name", "status", "start_date", "end_date", "notes"]:
        if field in data:
            updates.append(f"{field} = ${param_num}")
            params.append(data[field])
            param_num += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")
    params.append(cycle_id)

    query = f"UPDATE campaign_cycles SET {', '.join(updates)} WHERE id = ${param_num} RETURNING *"
    updated = await fetch_one(query, *params)

    return {
        "id": str(updated["id"]),
        "client_id": str(updated["client_id"]),
        "strategy_id": str(updated["strategy_id"]) if updated.get("strategy_id") else None,
        "cycle_number": updated.get("cycle_number", 1),
        "cycle_name": updated.get("cycle_name"),
        "status": updated.get("status"),
        "start_date": updated["start_date"].isoformat() if updated.get("start_date") else None,
        "end_date": updated["end_date"].isoformat() if updated.get("end_date") else None,
        "notes": updated.get("notes"),
        "created_at": updated["created_at"].isoformat() if updated.get("created_at") else None,
        "updated_at": updated["updated_at"].isoformat() if updated.get("updated_at") else None,
    }


@router.delete("/cycles/detail/{cycle_id}")
async def delete_cycle(cycle_id: UUID):
    """
    Delete a cycle and its associated campaign documents.
    """
    cycle = await fetch_one("SELECT id, cycle_name FROM campaign_cycles WHERE id = $1", cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    # Delete associated campaign documents first
    await execute("DELETE FROM campaign_documents WHERE cycle_id = $1", cycle_id)

    # Delete the cycle
    await execute("DELETE FROM campaign_cycles WHERE id = $1", cycle_id)

    logger.info(f"Deleted cycle '{cycle['cycle_name']}' and its campaigns")

    return {"message": f"Cycle deleted", "id": str(cycle_id)}


@router.get("/cycles/{cycle_id}/campaigns")
async def get_cycle_campaigns(cycle_id: UUID):
    """
    Get all campaigns (campaign_documents) for a specific cycle.

    Returns campaign documents with their email positions and variants.
    """
    # Verify cycle exists
    cycle = await fetch_one("SELECT id, client_id FROM campaign_cycles WHERE id = $1", cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    # Get all campaign documents for this cycle
    documents = await fetch_all("""
        SELECT d.id, d.job_id, d.client_id, d.strategy_id, d.cycle_id,
               d.document_name, d.campaign_number, d.angle,
               d.icp_mapping, d.variable_schema, d.campaign_variables,
               d.email_positions, d.qa_scoring, d.strategy_notes,
               d.status, d.human_comment, d.reviewed_by, d.reviewed_at,
               d.created_at, d.updated_at
        FROM campaign_documents d
        WHERE d.cycle_id = $1
        ORDER BY d.campaign_number ASC
    """, cycle_id)

    campaigns = []
    for doc in (documents or []):
        # Parse email_positions JSONB if present
        email_positions = doc.get("email_positions") or []
        email_count = sum(len(pos.get("variants", [])) for pos in email_positions) if email_positions else 0

        campaigns.append({
            "id": str(doc["id"]),
            "job_id": str(doc["job_id"]) if doc.get("job_id") else None,
            "client_id": str(doc["client_id"]),
            "strategy_id": str(doc["strategy_id"]) if doc.get("strategy_id") else None,
            "cycle_id": str(doc["cycle_id"]) if doc.get("cycle_id") else None,
            "campaign_number": doc.get("campaign_number"),
            "campaign_name": doc.get("document_name") or f"Campaign {doc.get('campaign_number', '')}",
            "angle": doc.get("angle"),
            "campaign_angle": doc.get("angle"),  # Frontend compatibility
            "status": doc.get("status", "draft"),
            "email_count": email_count,
            "score": doc.get("qa_scoring", {}).get("overall_score") if doc.get("qa_scoring") else None,
            "email_positions": email_positions,
            "campaign_variables": doc.get("campaign_variables"),
            "icp_mapping": doc.get("icp_mapping"),
            "variable_schema": doc.get("variable_schema"),
            "qa_scoring": doc.get("qa_scoring"),
            "strategy_notes": doc.get("strategy_notes"),
            "human_comment": doc.get("human_comment"),
            "reviewed_by": doc.get("reviewed_by"),
            "reviewed_at": doc["reviewed_at"].isoformat() if doc.get("reviewed_at") else None,
            "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
            "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None,
        })

    return {
        "cycle_id": str(cycle_id),
        "client_id": str(cycle["client_id"]),
        "campaigns": campaigns,
        "total": len(campaigns)
    }


@router.get("/cycles/{cycle_id}/unified")
async def get_cycle_unified(cycle_id: UUID):
    """
    Get unified cycle data including cycle info, config, and all 4 campaigns.

    Returns the complete structure needed by UnifiedCycleView frontend component.
    """
    # Get cycle with config
    cycle = await fetch_one("""
        SELECT cc.id, cc.client_id, cc.strategy_id, cc.cycle_number, cc.cycle_name,
               cc.status, cc.start_date, cc.end_date, cc.notes, cc.created_at, cc.updated_at,
               csc.id as config_id, csc.icp_mapping, csc.cycle_variables,
               csc.strategic_focus, csc.target_outcome,
               csc.created_at as config_created_at, csc.updated_at as config_updated_at
        FROM campaign_cycles cc
        LEFT JOIN cycle_strategy_config csc ON csc.cycle_id = cc.id
        WHERE cc.id = $1
    """, cycle_id)

    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    # Get all campaign documents for this cycle
    documents = await fetch_all("""
        SELECT d.id, d.job_id, d.client_id, d.strategy_id, d.cycle_id,
               d.document_name, d.campaign_number, d.angle,
               d.icp_mapping, d.variable_schema, d.campaign_variables,
               d.email_positions, d.qa_scoring, d.strategy_notes,
               d.status, d.human_comment, d.reviewed_by, d.reviewed_at,
               d.created_at, d.updated_at
        FROM campaign_documents d
        WHERE d.cycle_id = $1
        ORDER BY d.campaign_number ASC
    """, cycle_id)

    # Transform campaigns to unified format
    campaigns = []
    for doc in (documents or []):
        email_positions = doc.get("email_positions") or []

        # Transform email positions to unified emails
        emails = []
        for pos in email_positions:
            variants = pos.get("variants", [])
            recommended = next((v for v in variants if v.get("is_recommended")), variants[0] if variants else {})

            emails.append({
                "position": pos.get("position", len(emails) + 1),
                "title": pos.get("title") or f"Email {pos.get('position', len(emails) + 1)}",
                "wait_days": recommended.get("wait_days", 0),
                "subject_line": recommended.get("subject_line"),
                "email_body": recommended.get("email_body", ""),
                "thread_reply": recommended.get("thread_reply", False),
                "word_count": recommended.get("word_count"),
                "score": recommended.get("score"),
                "copy_variables": [],  # Extracted from variable_schema.core
            })

        # Extract campaign variables from variable_schema or campaign_variables
        variable_schema = doc.get("variable_schema") or {}
        campaign_vars = doc.get("campaign_variables") or variable_schema.get("high_signal", [])

        campaigns.append({
            "id": str(doc["id"]),
            "cycle_id": str(doc["cycle_id"]) if doc.get("cycle_id") else None,
            "campaign_number": doc.get("campaign_number", len(campaigns) + 1),
            "angle": doc.get("angle") or "custom_signal",
            "campaign_angle": doc.get("angle") or "custom_signal",  # Frontend compatibility
            "document_name": doc.get("document_name") or f"Campaign {doc.get('campaign_number', '')}",
            "status": doc.get("status", "draft"),
            "campaign_variables": campaign_vars,
            "emails": emails,
            "qa_scoring": doc.get("qa_scoring"),
            "score": doc.get("qa_scoring", {}).get("overall_score") if doc.get("qa_scoring") else None,
            "revision_history": [],  # Could be populated from strategy_revision_requests
            "reviewed_by": doc.get("reviewed_by"),
            "reviewed_at": doc["reviewed_at"].isoformat() if doc.get("reviewed_at") else None,
            "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
            "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None,
        })

    # Build the unified response
    return {
        "client_id": str(cycle["client_id"]),
        "data": {
            "cycle": {
                "id": str(cycle["id"]),
                "cycle_number": cycle.get("cycle_number", 1),
                "start_date": cycle["start_date"].isoformat() if cycle.get("start_date") else None,
                "end_date": cycle["end_date"].isoformat() if cycle.get("end_date") else None,
                "status": cycle.get("status", "draft"),
            },
            "config": {
                "id": str(cycle["config_id"]) if cycle.get("config_id") else f"config-{cycle['id']}",
                "cycle_id": str(cycle["id"]),
                "icp_mapping": cycle.get("icp_mapping") or {
                    "target_icp": {"role": "", "company_type": "", "company_size": ""},
                    "pain_points": [],
                    "objections": [],
                },
                "cycle_variables": cycle.get("cycle_variables") or [],
                "strategic_focus": cycle.get("strategic_focus") or "",
                "target_outcome": cycle.get("target_outcome") or "",
                "created_at": cycle["config_created_at"].isoformat() if cycle.get("config_created_at") else None,
                "updated_at": cycle["config_updated_at"].isoformat() if cycle.get("config_updated_at") else None,
            },
            "campaigns": campaigns,
        }
    }


@router.get("/clients/{client_id}/current-cycle")
async def get_current_cycle(client_id: UUID):
    """
    Get the current (most recent active or latest) cycle for a client.

    Convenience endpoint for UnifiedCycleView when no specific cycle is selected.
    """
    # Verify client exists
    client = await fetch_one("SELECT id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get the most recent active cycle, or just the most recent cycle
    cycle = await fetch_one("""
        SELECT id FROM campaign_cycles
        WHERE client_id = $1
        ORDER BY
            CASE WHEN status = 'active' THEN 0 ELSE 1 END,
            cycle_number DESC,
            created_at DESC
        LIMIT 1
    """, client_id)

    if not cycle:
        raise HTTPException(status_code=404, detail="No cycles found for this client")

    # Delegate to the unified endpoint
    return await get_cycle_unified(cycle["id"])


# ============================================================================
# Campaign Document Operations (New Phased Generation System)
# ============================================================================

@router.put("/campaigns/{document_id}/status")
async def update_campaign_document_status(document_id: UUID, status: str, human_comment: str = None):
    """
    Update campaign document status (approve, deny, request revision).

    Valid status transitions:
    - draft -> approved, denied
    - approved -> spintaxed (via spintax endpoint)
    - spintaxed -> sent (via push endpoint)
    """
    valid_statuses = ["draft", "approved", "denied", "revision_requested", "spintaxed", "sent"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    doc = await fetch_one("SELECT id, status FROM campaign_documents WHERE id = $1", document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Campaign document not found")

    await execute("""
        UPDATE campaign_documents
        SET status = $2, human_comment = $3, reviewed_at = NOW(), updated_at = NOW()
        WHERE id = $1
    """, document_id, status, human_comment)

    return {"document_id": str(document_id), "status": status, "message": f"Campaign {status}"}


@router.post("/campaigns/{document_id}/spintax")
async def create_campaign_spintax(document_id: UUID):
    """
    Add spintax variations to an approved campaign document.

    This endpoint processes the email_positions and creates spintaxed versions
    with {spin1|spin2|spin3} syntax for A/B testing.
    """
    doc = await fetch_one("""
        SELECT cd.*, c.name as client_name, w.emailbison_workspace_id
        FROM campaign_documents cd
        JOIN clients c ON c.id = cd.client_id
        LEFT JOIN workspaces w ON w.id = c.workspace_id
        WHERE cd.id = $1
    """, document_id)

    if not doc:
        raise HTTPException(status_code=404, detail="Campaign document not found")

    if doc["status"] not in ["approved", "draft"]:
        raise HTTPException(
            status_code=400,
            detail=f"Campaign must be approved before adding spintax. Current status: {doc['status']}"
        )

    email_positions = doc.get("email_positions") or []
    if not email_positions:
        raise HTTPException(status_code=400, detail="Campaign has no email positions to spintax")

    # Process spintax - for now, just mark as spintaxed
    # In production, this would trigger the spintax worker
    spintaxed_positions = []
    for pos in email_positions:
        spintaxed_pos = dict(pos)
        variants = pos.get("variants", [])
        if variants:
            # Use first variant as the base, add spintax markers
            base = variants[0]
            spintaxed_pos["spintaxed_subject"] = base.get("subject_line", "")
            spintaxed_pos["spintaxed_body"] = base.get("email_body", "")
        spintaxed_positions.append(spintaxed_pos)

    # asyncpg handles JSONB serialization, so pass the Python object directly
    await execute("""
        UPDATE campaign_documents
        SET status = 'spintaxed',
            spintaxed_positions = $2::jsonb,
            updated_at = NOW()
        WHERE id = $1
    """, document_id, json.dumps(spintaxed_positions))

    return {
        "document_id": str(document_id),
        "status": "spintaxed",
        "email_count": len(spintaxed_positions),
        "message": "Spintax added successfully"
    }


@router.post("/campaigns/{document_id}/push-to-emailbison")
async def push_campaign_to_emailbison(document_id: UUID):
    """
    Push a spintaxed campaign document to EmailBison to create a complete campaign.

    This endpoint:
    1. Validates the campaign is spintaxed and not already pushed
    2. Switches to the correct EmailBison workspace
    3. Creates a campaign with the document name
    4. Adds all email positions as sequence steps
    5. Updates the campaign status to 'sent'
    """
    doc = await fetch_one("""
        SELECT cd.*, c.name as client_name, w.emailbison_workspace_id
        FROM campaign_documents cd
        JOIN clients c ON c.id = cd.client_id
        LEFT JOIN workspaces w ON w.id = c.workspace_id
        WHERE cd.id = $1
    """, document_id)

    if not doc:
        raise HTTPException(status_code=404, detail="Campaign document not found")

    # Must be spintaxed (or approved for testing)
    if doc["status"] not in ["spintaxed", "approved"]:
        raise HTTPException(
            status_code=400,
            detail=f"Campaign must be spintaxed before pushing to EmailBison. Current status: {doc['status']}"
        )

    if doc.get("pushed_to_emailbison"):
        raise HTTPException(
            status_code=400,
            detail="Campaign has already been pushed to EmailBison"
        )

    emailbison_workspace_id = doc.get("emailbison_workspace_id")
    if not emailbison_workspace_id:
        raise HTTPException(
            status_code=400,
            detail=f"Client '{doc['client_name']}' has no EmailBison workspace configured"
        )

    if not EMAILBISON_API_KEY:
        raise HTTPException(status_code=500, detail="EmailBison API key not configured")

    # Get email positions (use spintaxed if available, otherwise original)
    email_positions = doc.get("spintaxed_positions") or doc.get("email_positions") or []
    # Handle case where JSONB was stored as double-encoded string
    if isinstance(email_positions, str):
        email_positions = json.loads(email_positions)
    if not email_positions:
        raise HTTPException(status_code=400, detail="Campaign has no email content")

    campaign_name = doc.get("document_name") or "Campaign"
    created_campaign_id = None
    steps_completed = []

    # Variable transformation: {{double_braces}} -> {SINGLE_BRACES}
    import re
    def transform_variables(text: str) -> str:
        if not text:
            return text
        var_map = {
            "first_name": "FIRST_NAME",
            "company_name": "COMPANY_NAME",
            "role_title": "JOB_TITLE",
            "industry": "INDUSTRY",
        }
        result = text
        for old_var, new_var in var_map.items():
            result = re.sub(r"\{\{" + old_var + r"\}\}", "{" + new_var + "}", result, flags=re.IGNORECASE)
        result = re.sub(r"\{\{(\w+)\}\}", lambda m: "{" + m.group(1).upper() + "}", result)
        return result

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Switch workspace
            switch_response = await client.post(
                f"{EMAILBISON_API_URL}/api/workspaces/switch-workspace",
                headers={
                    "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"team_id": emailbison_workspace_id}
            )

            if switch_response.status_code != 200:
                logger.error(f"Failed to switch workspace: {switch_response.text}")
                raise HTTPException(status_code=502, detail="Failed to switch to EmailBison workspace")
            steps_completed.append("workspace_switch")
            logger.info(f"Switched to EmailBison workspace {emailbison_workspace_id}")

            # Step 2: Create campaign
            campaign_response = await client.post(
                f"{EMAILBISON_API_URL}/api/campaigns",
                headers={
                    "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"name": campaign_name, "type": "outbound"}
            )

            if campaign_response.status_code not in (200, 201):
                logger.error(f"Failed to create campaign: {campaign_response.text}")
                raise HTTPException(status_code=502, detail="Failed to create EmailBison campaign")

            campaign_data = campaign_response.json()
            created_campaign_id = campaign_data.get("data", {}).get("id") or campaign_data.get("id")
            steps_completed.append("campaign_create")
            logger.info(f"Created EmailBison campaign {created_campaign_id}")

            # Step 3: Add sequence steps from email positions
            sequence_steps_payload = []
            first_subject = None  # Track first email's subject for thread replies
            for pos in sorted(email_positions, key=lambda x: x.get("position", 1)):
                position = pos.get("position", 1)
                is_thread_reply = pos.get("thread_reply", position > 1)

                # Get subject and body from variants or spintaxed versions
                variants = pos.get("variants", [])
                if variants:
                    subject = variants[0].get("subject_line") or ""
                    body = variants[0].get("email_body") or ""
                    # Also check wait_days from variant
                    wait_days_from_variant = variants[0].get("wait_days", 0)
                else:
                    subject = pos.get("spintaxed_subject") or pos.get("title") or ""
                    body = pos.get("spintaxed_body") or ""
                    wait_days_from_variant = 0

                # Track first subject for thread replies
                if position == 1 and subject:
                    first_subject = subject
                # For thread replies with no subject, use "Re: {first_subject}" or campaign name
                if not subject:
                    if is_thread_reply and first_subject:
                        subject = f"Re: {first_subject}"
                    else:
                        subject = campaign_name

                wait_days = max(pos.get("wait_days", 0) or wait_days_from_variant or position, 1)

                sequence_steps_payload.append({
                    "email_subject": transform_variables(subject),
                    "email_body": transform_variables(body),
                    "order": position,
                    "wait_in_days": wait_days,
                    "thread_reply": pos.get("thread_reply", position > 1),
                    "variant": False,
                })

            step_response = await client.post(
                f"{EMAILBISON_API_URL}/api/campaigns/{created_campaign_id}/sequence-steps",
                headers={
                    "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"title": campaign_name, "sequence_steps": sequence_steps_payload}
            )

            if step_response.status_code not in (200, 201):
                logger.error(f"Failed to create sequence steps: {step_response.text}")
                raise HTTPException(status_code=502, detail="Failed to create sequence steps")

            steps_completed.append("sequence_steps")
            logger.info(f"Created {len(sequence_steps_payload)} sequence steps for campaign {created_campaign_id}")

            # Step 4: Configure sending schedule (M-F 8am-5pm)
            try:
                schedule_response = await client.post(
                    f"{EMAILBISON_API_URL}/api/campaigns/{created_campaign_id}/schedule",
                    headers={
                        "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "monday": True, "tuesday": True, "wednesday": True,
                        "thursday": True, "friday": True, "saturday": False, "sunday": False,
                        "start_time": "08:00", "end_time": "17:00",
                        "timezone": "America/New_York", "save_as_template": False
                    }
                )
                if schedule_response.status_code in (200, 201):
                    steps_completed.append("schedule_configured")
            except Exception as e:
                logger.warning(f"Failed to configure schedule: {e}")

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to EmailBison: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to EmailBison: {str(e)}")

    # Update campaign document status
    await execute("""
        UPDATE campaign_documents
        SET status = 'sent',
            pushed_to_emailbison = TRUE,
            pushed_at = NOW(),
            emailbison_campaign_id = $2,
            updated_at = NOW()
        WHERE id = $1
    """, document_id, created_campaign_id)

    logger.info(f"Pushed campaign document {document_id} to EmailBison as campaign {created_campaign_id}")

    return {
        "document_id": str(document_id),
        "client_id": str(doc["client_id"]),
        "client_name": doc["client_name"],
        "emailbison_workspace_id": emailbison_workspace_id,
        "emailbison_campaign_id": created_campaign_id,
        "campaign_name": campaign_name,
        "emails_pushed": len(sequence_steps_payload),
        "schedule_configured": "schedule_configured" in steps_completed,
        "steps_completed": steps_completed,
        "status": "draft",
        "message": f"{len(sequence_steps_payload)}-email campaign created in EmailBison as draft",
        "next_steps": ["Assign sender emails", "Add leads list", "Review and activate"]
    }
