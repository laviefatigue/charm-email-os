"""
Pydantic models for Strategy Generation API.
"""
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class StrategyJobCreate(BaseModel):
    """Request to create a strategy generation job."""
    submission_id: Optional[UUID] = None


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
    variant_number: int
    subject_line: str
    email_body: str
    score: Optional[int] = None
    rationale: Optional[str] = None
    used_variables: Optional[List[str]] = None
    missing_variables: Optional[List[str]] = None
    campaign_type: Optional[str] = None
    status: str
    human_comment: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
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
