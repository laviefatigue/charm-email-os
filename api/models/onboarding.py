"""
Onboarding submission models.

Pydantic models for comprehensive onboarding form data stored in client_onboarding_submissions.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID


class ClientSegment(BaseModel):
    """Customer segment from onboarding."""
    id: Optional[UUID] = None
    segment_name: str
    revenue_percentage: int = Field(default=0, ge=0, le=100)
    unique_characteristics: Optional[str] = None
    pain_points: Optional[str] = None
    buying_triggers: Optional[str] = None


class ClientPersona(BaseModel):
    """Buyer persona from onboarding."""
    id: Optional[UUID] = None
    job_title: str
    primary_segment: Optional[str] = None
    seniority_level: Optional[str] = None
    pain_before_buying: Optional[str] = None
    aha_moment: Optional[str] = None
    objections: Optional[str] = None


class OnboardingSubmission(BaseModel):
    """Full onboarding submission from external form."""
    id: UUID
    client_id: Optional[UUID] = None

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

    # Section 3: Market Signals
    signals: list[str] = Field(default_factory=list)
    custom_signals: Optional[str] = None

    # Section 4: Audience
    job_titles: list[str] = Field(default_factory=list)
    segments: list[ClientSegment] = Field(default_factory=list)
    personas: list[ClientPersona] = Field(default_factory=list)

    # Section 5: Process
    outbound_tools: list[str] = Field(default_factory=list)
    crm: Optional[str] = None

    # Section 6: Messaging
    customer_voice: Optional[str] = None
    roi_results: Optional[str] = None
    tone_style: Optional[str] = None

    # Section 7: Goals
    primary_gtm_objective: Optional[str] = None
    success_metrics: list[str] = Field(default_factory=list)
    success_definition: Optional[str] = None

    # Metadata
    submission_status: str = Field(default="submitted")
    submitted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OnboardingSubmissionUpdate(BaseModel):
    """Update fields for onboarding submission."""
    # Section 1: Foundation
    company_name: Optional[str] = None
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

    # Section 3: Market Signals
    signals: Optional[list[str]] = None
    custom_signals: Optional[str] = None

    # Section 4: Audience
    job_titles: Optional[list[str]] = None

    # Section 5: Process
    outbound_tools: Optional[list[str]] = None
    crm: Optional[str] = None

    # Section 6: Messaging
    customer_voice: Optional[str] = None
    roi_results: Optional[str] = None
    tone_style: Optional[str] = None

    # Section 7: Goals
    primary_gtm_objective: Optional[str] = None
    success_metrics: Optional[list[str]] = None
    success_definition: Optional[str] = None


class OnboardingSubmissionList(BaseModel):
    """List of onboarding submissions for a client."""
    client_id: UUID
    submissions: list[OnboardingSubmission]
    total: int
