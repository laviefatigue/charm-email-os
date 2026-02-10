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
    submission_id: Optional[UUID] = None  # Link to onboarding submission


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
    submission_id: Optional[UUID] = None
    submission_created_at: Optional[datetime] = None  # When the linked submission was created
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


# ============================================================================
# Sequence Models (4-Email Campaign Sequences)
# ============================================================================

class SequenceEmail(BaseModel):
    """A single email within a 4-email sequence."""
    position: int  # 1, 2, 3, or 4
    wait_days: int
    subject_line: Optional[str] = None  # null for threaded emails
    email_body: str
    edited_subject_line: Optional[str] = None  # user edits
    edited_email_body: Optional[str] = None
    thread_reply: bool = False
    strategy: Optional[str] = None  # custom_signal, creative_ideas, etc.
    value_prop: Optional[str] = None  # save_time, save_money, make_money
    word_count: Optional[int] = None


class CampaignSequenceResponse(BaseModel):
    """A complete 4-email campaign sequence."""
    id: UUID
    job_id: UUID
    client_id: UUID
    strategy_id: Optional[UUID] = None
    campaign_name: str  # Email 1 subject
    campaign_type: Optional[str] = None  # custom_signal, creative_ideas, whole_offer, fallback
    status: str
    score: Optional[int] = None
    value_prop_rotation: Optional[List[str]] = None
    emails: List[SequenceEmail]
    spintaxed_emails: Optional[List[SequenceEmail]] = None  # Populated after spintax processing
    used_variables: Optional[List[str]] = None
    missing_variables: Optional[List[str]] = None
    rationale: Optional[str] = None
    total_word_count: Optional[int] = None
    human_comment: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    pushed_to_emailbison: bool = False
    pushed_at: Optional[datetime] = None
    generation_round: int = 1
    created_at: datetime


class ClientSequencesResponse(BaseModel):
    """Response containing all sequences for a client."""
    client_id: UUID
    sequences: List[CampaignSequenceResponse]
    pending_count: int
    approved_count: int
    denied_count: int
    revision_count: int
    total: int


class SequenceReviewRequest(BaseModel):
    """Request to review a sequence - approve, deny, or request revision."""
    action: str  # 'approve', 'deny'
    comment: Optional[str] = None
    reviewer: Optional[str] = None


class SequenceEmailEditRequest(BaseModel):
    """Request to edit a specific email in a sequence."""
    subject_line: Optional[str] = None  # Only for position 1 and 3
    email_body: str


class SequenceRevisionRequest(BaseModel):
    """Request revision for specific email or entire sequence."""
    email_position: int  # 1-4 for specific email, 0 for whole sequence
    instruction: str
    scope: str = "single"  # 'single', 'subsequent', 'all'


# ============================================================================
# Spintax Processing Models
# ============================================================================

class SpintaxJobResponse(BaseModel):
    """Response for a spintax processing job."""
    job_id: UUID
    sequence_id: UUID
    client_id: UUID
    status: str  # pending, processing, completed, failed
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ============================================================================
# Campaign Document Models (Stablekernel Format)
# ============================================================================

class TargetICP(BaseModel):
    """Target ICP definition."""
    role: str
    company_type: str
    company_size: str


class PainPoint(BaseModel):
    """Categorized pain point for ICP."""
    category: str
    label: str
    points: List[str]


class Objection(BaseModel):
    """Objection with preemption strategy."""
    objection: str
    preemption: str


class ICPMapping(BaseModel):
    """Complete ICP and objection mapping."""
    target_icp: TargetICP
    pain_points: List[PainPoint]
    objections: List[Objection]


class VariableDefinition(BaseModel):
    """Variable definition with optional source."""
    name: str
    description: str
    source: Optional[str] = None  # For high-signal variables


class VariableSchema(BaseModel):
    """Complete variable schema for campaign."""
    core: List[VariableDefinition]
    high_signal: List[VariableDefinition]
    ai_generated: List[VariableDefinition]


class SequenceSummaryStep(BaseModel):
    """Timeline step in sequence summary."""
    day: str  # "Day 0", "Day 3-4"
    title: str
    description: str


class QADimension(BaseModel):
    """Single QA scoring dimension."""
    name: str
    score: str  # "24/25"
    notes: str


class QAScoring(BaseModel):
    """Complete QA scoring for lead variant."""
    overall_score: int
    verdict: str  # "Ship it", "One more pass", "Start over"
    dimensions: List[QADimension]


class StrategyCallout(BaseModel):
    """Strategic callout (recommendation, warning, info)."""
    type: Literal["recommendation", "warning", "info"]
    text: str


class DataEnrichment(BaseModel):
    """Data enrichment source for a variable."""
    variable: str
    source: str


class StrategyNotes(BaseModel):
    """Strategy notes section."""
    callouts: List[StrategyCallout]
    data_enrichment: List[DataEnrichment]
    ab_testing: List[str]


class EmailVariant(BaseModel):
    """Single email variant within a position."""
    id: Optional[UUID] = None
    variant_number: int
    variant_name: Optional[str] = None
    is_recommended: bool = False
    subject_line: Optional[str] = None  # null for threaded
    email_body: str
    wait_days: int = 0
    thread_reply: bool = False
    word_count: Optional[int] = None
    them_us_ratio: Optional[str] = None
    score: Optional[int] = None
    angle: Optional[str] = None
    strategy: Optional[str] = None
    value_prop: Optional[str] = None
    edited_subject_line: Optional[str] = None
    edited_email_body: Optional[str] = None


class SubjectOption(BaseModel):
    """Subject line option with rationale."""
    subject_line: str
    rationale: str


class EmailPosition(BaseModel):
    """Email position with multiple variants."""
    position: int  # 1, 2, 3, or 4
    title: str  # "Email 1: Custom Signal — Day 0"
    variants: List[EmailVariant]
    subject_options: Optional[List[SubjectOption]] = None


class CampaignDocumentResponse(BaseModel):
    """Complete campaign document in stablekernel format."""
    id: UUID
    job_id: UUID
    client_id: UUID
    strategy_id: Optional[UUID] = None
    document_name: str
    document_version: int = 1
    vertical: Optional[str] = None
    objective: Optional[str] = None
    icp_mapping: Optional[ICPMapping] = None
    variable_schema: Optional[VariableSchema] = None
    email_positions: List[EmailPosition]
    sequence_summary: Optional[List[SequenceSummaryStep]] = None
    qa_scoring: Optional[QAScoring] = None
    strategy_notes: Optional[StrategyNotes] = None
    status: str = "draft"
    human_comment: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ClientDocumentsResponse(BaseModel):
    """Response containing all campaign documents for a client."""
    client_id: UUID
    documents: List[CampaignDocumentResponse]
    total: int


class DocumentVariantEditRequest(BaseModel):
    """Request to edit a specific variant in a document."""
    subject_line: Optional[str] = None
    email_body: str


class DocumentReviewRequest(BaseModel):
    """Request to review a campaign document."""
    action: Literal["approve", "deny", "revision_requested"]
    comment: Optional[str] = None
    reviewer: Optional[str] = None


class SelectVariantRequest(BaseModel):
    """Request to select a variant as recommended for a position."""
    position: int
    variant_number: int
