"""
Client models - New table linking to OwnRBL workspaces
"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
from datetime import datetime
from uuid import UUID


class SenderName(BaseModel):
    """A sender name for inbox provisioning"""
    first_name: str = Field(..., alias="firstName")
    last_name: str = Field(..., alias="lastName")
    email_prefix: str = Field(..., alias="emailPrefix")
    source: Literal["persona", "custom", "generated"] = "generated"

    class Config:
        populate_by_name = True


class SenderNamePreferences(BaseModel):
    """Configuration for sender name generation"""
    use_personas: bool = Field(True, alias="usePersonas")
    custom_names: Optional[list[SenderName]] = Field(None, alias="customNames")
    name_count: int = Field(10, alias="nameCount")

    class Config:
        populate_by_name = True


class OnboardingPersona(BaseModel):
    """A persona from client onboarding data"""
    name: Optional[str] = None
    first_name: Optional[str] = Field(None, alias="firstName")
    last_name: Optional[str] = Field(None, alias="lastName")
    job_title: Optional[str] = Field(None, alias="jobTitle")
    primary_segment: Optional[str] = Field(None, alias="primarySegment")
    seniority_level: Optional[str] = Field(None, alias="seniorityLevel")

    class Config:
        populate_by_name = True


class OnboardingData(BaseModel):
    """Client onboarding data stored in JSONB"""
    contact_first_names: Optional[list[str]] = Field(default_factory=list, alias="contactFirstNames")
    primary_domain: Optional[str] = Field(None, alias="primaryDomain")
    industry: Optional[str] = None
    product: Optional[str] = None
    inboxes_needed: Optional[int] = Field(None, alias="inboxesNeeded")
    notes: Optional[str] = None
    # Sender name configuration
    personas: Optional[list[OnboardingPersona]] = None
    sender_name_preferences: Optional[SenderNamePreferences] = Field(None, alias="senderNamePreferences")
    pre_generated_sender_names: Optional[list[SenderName]] = Field(None, alias="preGeneratedSenderNames")

    class Config:
        populate_by_name = True


class ClientBase(BaseModel):
    """Base client fields"""
    name: str
    logo_url: Optional[str] = None
    # Profile fields
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    domain_pattern: Optional[str] = None


class ClientCreate(ClientBase):
    """Create a new client"""
    workspace_id: Optional[UUID] = None
    onboarding_data: Optional[OnboardingData] = None


class ClientUpdate(BaseModel):
    """Update client fields"""
    name: Optional[str] = None
    workspace_id: Optional[UUID] = None
    logo_url: Optional[str] = None
    onboarding_complete: Optional[bool] = None
    onboarding_data: Optional[OnboardingData] = None
    # Profile fields
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    domain_pattern: Optional[str] = None


class ClientOnboard(BaseModel):
    """Complete client onboarding"""
    onboarding_data: OnboardingData


class Client(ClientBase):
    """Full client model with all fields"""
    id: UUID
    workspace_id: Optional[UUID] = None
    workspace_name: Optional[str] = None  # Joined from workspaces table
    onboarding_complete: bool = False
    onboarding_data: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    # Computed fields from linked workspace
    inbox_count: int = 0
    domain_count: int = 0
    campaign_count: int = 0

    class Config:
        from_attributes = True


class ClientList(BaseModel):
    """List of clients with pagination"""
    items: list[Client]
    total: int
    page: int = 1
    page_size: int = 50


class LinkWorkspaceRequest(BaseModel):
    """Request to link a client to a workspace"""
    workspace_id: UUID
