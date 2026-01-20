"""
Pydantic models for Strategy Generation API.
"""
from pydantic import BaseModel
from typing import Optional, List, Literal
from uuid import UUID
from datetime import datetime


# ============================================================================
# Strategy Models (NEW)
# ============================================================================

class StrategyCreate(BaseModel):
    """Request to create a new strategy."""
    name: str
    description: Optional[str] = None


class StrategyUpdate(BaseModel):
    """Request to update a strategy."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal['draft', 'active', 'paused', 'completed']] = None


class StrategyResponse(BaseModel):
    """Response for a strategy."""
    id: UUID
    client_id: UUID
    name: str
    description: Optional[str] = None
    status: str
    emailbison_campaign_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SuggestionEditRequest(BaseModel):
    """Request to edit a suggestion's content."""
    subject_line: str
    email_body: str


# ============================================================================
# Job Models
# ============================================================================

class StrategyJobCreate(BaseModel):
    """Request to create a strategy generation job."""
    submission_id: Optional[UUID] = None
    strategy_id: Optional[UUID] = None


class StrategyJobResponse(BaseModel):
    """Response for a strategy generation job."""
    job_id: UUID
    client_id: UUID
    client_name: str
    submission_id: Optional[UUID] = None
    status: str
    generation_round: int
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class StrategySuggestionResponse(BaseModel):
    """A single strategy suggestion/variant."""
    id: UUID
    job_id: UUID
    client_id: UUID
    strategy_id: Optional[UUID] = None
    variant_number: int
    subject_line: str
    email_body: str
    edited_subject_line: Optional[str] = None
    edited_email_body: Optional[str] = None
    score: Optional[int] = None
    rationale: Optional[str] = None
    used_variables: Optional[List[str]] = None
    missing_variables: Optional[List[str]] = None
    campaign_type: Optional[str] = None
    status: str
    human_comment: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    pushed_to_emailbison: bool = False
    pushed_at: Optional[datetime] = None
    original_suggestion_id: Optional[UUID] = None
    generation_round: int
    created_at: datetime


class SuggestionReviewRequest(BaseModel):
    """Request to review a suggestion."""
    action: str  # 'approve', 'deny', 'revision_requested'
    comment: Optional[str] = None
    reviewer: Optional[str] = None


class RevisionRequestCreate(BaseModel):
    """Request to create a revision request."""
    variant_id: Optional[UUID] = None
    instruction: str


class RevisionRequestResponse(BaseModel):
    """Response for a revision request."""
    id: UUID
    job_id: UUID
    client_id: UUID
    variant_id: Optional[UUID] = None
    instruction: str
    processed: bool
    created_at: datetime


class ClientSuggestionsResponse(BaseModel):
    """Response containing all suggestions for a client."""
    client_id: UUID
    suggestions: List[StrategySuggestionResponse]
    pending_count: int
    approved_count: int
    denied_count: int
    revision_count: int
    total: int
