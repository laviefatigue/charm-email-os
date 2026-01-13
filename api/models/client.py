"""
Client models - New table linking to OwnRBL workspaces
"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class OnboardingData(BaseModel):
    """Client onboarding data stored in JSONB"""
    contact_first_names: Optional[list[str]] = Field(default_factory=list, alias="contactFirstNames")
    primary_domain: Optional[str] = Field(None, alias="primaryDomain")
    industry: Optional[str] = None
    product: Optional[str] = None
    inboxes_needed: Optional[int] = Field(None, alias="inboxesNeeded")
    notes: Optional[str] = None

    class Config:
        populate_by_name = True


class ClientBase(BaseModel):
    """Base client fields"""
    name: str
    logo_url: Optional[str] = None


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
