"""
Lead models - New table for full lead management
"""

from pydantic import BaseModel, EmailStr
from typing import Optional, Literal, Any
from datetime import datetime
from uuid import UUID


LeadStatus = Literal["queued", "contacted", "replied", "bounced", "unsubscribed", "suppressed"]
LeadSource = Literal["manual_upload", "csv_upload", "script_pull", "enrichment", "manual_entry", "emailbison_sync"]


class LeadBase(BaseModel):
    """Base lead fields"""
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    company_domain: Optional[str] = None


class LeadCreate(LeadBase):
    """Create a single lead"""
    campaign_id: UUID
    linkedin_url: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    custom_fields: Optional[dict[str, Any]] = None
    source: LeadSource = "manual_entry"


class LeadUpdate(BaseModel):
    """Update lead fields"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    custom_fields: Optional[dict[str, Any]] = None
    status: Optional[LeadStatus] = None


class LeadBulkCreate(BaseModel):
    """Bulk create leads from CSV upload"""
    campaign_id: UUID
    leads: list[LeadBase]
    source: LeadSource = "csv_upload"
    # CSV column mappings
    column_mapping: Optional[dict[str, str]] = None


class Lead(LeadBase):
    """Full lead model"""
    id: UUID
    campaign_id: UUID

    # Extended fields
    linkedin_url: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    custom_fields: Optional[dict[str, Any]] = None

    # Status tracking
    status: LeadStatus = "queued"
    source: LeadSource = "manual_upload"
    contacted_at: Optional[datetime] = None
    enriched_at: Optional[datetime] = None

    # Suppression tracking
    suppression_status: Optional[str] = None
    suppressed_at: Optional[datetime] = None
    suppressed_by_domain: Optional[str] = None

    # Original data
    raw_data: Optional[dict[str, Any]] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeadList(BaseModel):
    """List of leads with pagination"""
    items: list[Lead]
    total: int
    page: int = 1
    page_size: int = 50

    # Status counts
    queued_count: int = 0
    contacted_count: int = 0
    replied_count: int = 0
    bounced_count: int = 0
    unsubscribed_count: int = 0
    suppressed_count: int = 0


class LeadStatusUpdate(BaseModel):
    """Update lead status"""
    status: LeadStatus
    contacted_at: Optional[datetime] = None


class LeadBulkUploadResult(BaseModel):
    """Result of bulk lead upload"""
    total_uploaded: int
    successful: int
    failed: int
    duplicates_skipped: int
    errors: Optional[list[dict]] = None
