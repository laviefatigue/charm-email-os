"""
Client models - New table linking to OwnRBL workspaces
"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
from datetime import datetime
from uuid import UUID


class BaseName(BaseModel):
    """A base/seed name for variation generation"""
    first_name: str = Field(..., alias="firstName")
    last_name: str = Field(..., alias="lastName")
    is_founder: bool = Field(False, alias="isFounder")

    class Config:
        populate_by_name = True


class SenderName(BaseModel):
    """A sender name for inbox provisioning"""
    first_name: str = Field(..., alias="firstName")
    last_name: str = Field(..., alias="lastName")
    email_prefix: str = Field(..., alias="emailPrefix")
    source: Literal["persona", "custom", "generated", "founder"] = "generated"

    class Config:
        populate_by_name = True


class SenderNameVariation(BaseModel):
    """A generated variation from a base name"""
    first_name: str = Field(..., alias="firstName")
    last_name: str = Field(..., alias="lastName")
    email_prefix: str = Field(..., alias="emailPrefix")
    base_name: str = Field(..., alias="baseName")
    pattern: str
    is_founder: bool = Field(False, alias="isFounder")

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
    # Variation-based name generation (Phase 6A.5)
    base_sender_names: Optional[list[BaseName]] = Field(None, alias="baseSenderNames")
    variation_patterns: Optional[list[str]] = Field(None, alias="variationPatterns")

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
    # Workspace sync control (updates workspace.is_active)
    sync_enabled: Optional[bool] = None


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
    sync_enabled: Optional[bool] = True  # Maps to workspace.is_active

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


class GenerateVariationsRequest(BaseModel):
    """Request to generate name variations from base names.

    Provider-specific behavior:
    - entra: Up to 52 variations using all pattern tiers
    - google: Up to 10 variations using tier 1 patterns only
    """
    base_names: list[BaseName] = Field(..., alias="baseNames")
    patterns: Optional[list[str]] = Field(
        default=None,  # Will use provider-specific defaults
        description="Pattern names to use. If not specified, uses provider-specific ranked patterns."
    )
    count: int = Field(10, ge=1, le=52, description="Number of variations to generate (max 52 for Entra, 10 for Google)")
    provider: Literal["entra", "google"] = Field("google", description="Infrastructure provider: 'entra' (Microsoft, 52 inboxes) or 'google' (10 inboxes)")

    class Config:
        populate_by_name = True


class SaveSenderNamesRequest(BaseModel):
    """Request to save sender names to client profile"""
    base_names: list[BaseName] = Field(..., alias="baseNames")
    variations: list[SenderNameVariation]
    patterns: list[str]
    provider: Literal["entra", "google"] = Field("google", description="Infrastructure provider used for generation")

    class Config:
        populate_by_name = True


class SetBaseNameRequest(BaseModel):
    """
    Simplified request to set base sender name.

    Just provide first/last name and provider - the 52 email prefixes
    are auto-generated using the pattern template system.
    """
    first_name: str = Field(..., alias="firstName")
    last_name: str = Field(..., alias="lastName")
    is_founder: bool = Field(True, alias="isFounder")
    provider: Literal["entra", "google"] = Field("entra", description="Infrastructure provider: 'entra' (52 prefixes) or 'google' (10 prefixes)")

    class Config:
        populate_by_name = True
