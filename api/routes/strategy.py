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

from models.strategy import (
    StrategyJobCreate,
    StrategyJobResponse,
    StrategySuggestionResponse,
    SuggestionReviewRequest,
    RevisionRequestCreate,
    RevisionRequestResponse,
    ClientSuggestionsResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


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
        request: Optional request with submission_id

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
        INSERT INTO strategy_generation_jobs (client_id, submission_id, status, generation_round)
        VALUES ($1, $2, 'pending', $3)
        RETURNING id, status, generation_round, created_at
    """, client_id, submission_id, generation_round)

    logger.info(f"Created strategy generation job {job['id']} for client {client['name']} (round {generation_round})")

    return {
        "job_id": str(job["id"]),
        "client_id": str(client_id),
        "client_name": client["name"],
        "submission_id": str(submission_id) if submission_id else None,
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
    limit: int = 50
):
    """
    Get strategy suggestions for a client, optionally filtered by status.

    Args:
        client_id: The client UUID
        status: Filter by status (pending, approved, denied, revision_requested)
        limit: Maximum number to return
    """
    query = """
        SELECT s.*, j.generation_round as job_round
        FROM strategy_suggestions s
        JOIN strategy_generation_jobs j ON j.id = s.job_id
        WHERE s.client_id = $1
    """
    params = [client_id]

    if status:
        query += " AND s.status = $2"
        params.append(status)

    query += " ORDER BY s.created_at DESC LIMIT $" + str(len(params) + 1)
    params.append(limit)

    suggestions = await fetch_all(query, *params)

    # Get counts
    counts = await fetch_one("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
            COUNT(*) FILTER (WHERE status = 'approved') as approved_count,
            COUNT(*) FILTER (WHERE status = 'denied') as denied_count,
            COUNT(*) FILTER (WHERE status = 'revision_requested') as revision_count,
            COUNT(*) as total
        FROM strategy_suggestions
        WHERE client_id = $1
    """, client_id)

    return ClientSuggestionsResponse(
        client_id=client_id,
        suggestions=[
            StrategySuggestionResponse(
                id=s["id"],
                job_id=s["job_id"],
                client_id=s["client_id"],
                variant_number=s["variant_number"],
                subject_line=s["subject_line"],
                email_body=s["email_body"],
                score=s.get("score"),
                rationale=s.get("rationale"),
                used_variables=s.get("used_variables"),
                missing_variables=s.get("missing_variables"),
                campaign_type=s.get("campaign_type"),
                status=s["status"],
                human_comment=s.get("human_comment"),
                reviewed_by=s.get("reviewed_by"),
                reviewed_at=s.get("reviewed_at"),
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
    Create a revision request for a suggestion.

    This adds specific guidance for the next generation round.
    """
    # Get suggestion info
    suggestion = await fetch_one("""
        SELECT s.id, s.job_id, s.client_id
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

    return RevisionRequestResponse(
        id=revision["id"],
        job_id=suggestion["job_id"],
        client_id=suggestion["client_id"],
        variant_id=suggestion_id,
        instruction=request.instruction,
        processed=False,
        created_at=revision["created_at"],
    )


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
