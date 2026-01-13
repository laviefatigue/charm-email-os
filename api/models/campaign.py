"""
Campaign models - Maps to OwnRBL emailbison_campaigns table
"""

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


CampaignStatus = Literal["draft", "active", "paused", "completed", "archived"]


class CampaignBase(BaseModel):
    """Base campaign fields"""
    campaign_name: str
    industry: Optional[str] = None
    segment: Optional[str] = None
    angle: Optional[str] = None


class CampaignCreate(CampaignBase):
    """Create a new campaign (from idea)"""
    workspace_id: UUID
    idea_id: Optional[str] = None  # Reference to frontend campaign idea


class Campaign(BaseModel):
    """Full campaign model from OwnRBL emailbison_campaigns"""
    id: UUID
    workspace_id: UUID
    emailbison_campaign_id: Optional[int] = None  # External sync ID

    # Identity
    campaign_name: str
    industry: Optional[str] = None
    segment: Optional[str] = None
    angle: Optional[str] = None

    # Status
    campaign_status: CampaignStatus = "draft"

    # Lead counts
    total_leads: int = 0
    total_leads_contacted: int = 0
    leads_capacity: int = 0

    # Metrics from snapshots
    emails_sent: int = 0
    unique_opens: int = 0
    unique_replies: int = 0
    bounced: int = 0
    unsubscribed: int = 0
    spam_complaints: int = 0

    # Computed rates
    reply_rate: Optional[float] = None
    open_rate: Optional[float] = None
    bounce_rate: Optional[float] = None
    completion_percentage: Optional[float] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_snapshot_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CampaignList(BaseModel):
    """List of campaigns with pagination"""
    items: list[Campaign]
    total: int
    page: int = 1
    page_size: int = 50

    # Aggregates
    active_count: int = 0
    paused_count: int = 0
    completed_count: int = 0


class CampaignMetrics(BaseModel):
    """Detailed campaign metrics"""
    campaign_id: UUID
    campaign_name: str

    # Volume
    emails_sent: int = 0
    total_leads: int = 0
    leads_contacted: int = 0

    # Engagement
    unique_opens: int = 0
    unique_replies: int = 0
    interested_replies: int = 0
    automated_replies: int = 0

    # Deliverability
    bounced: int = 0
    unsubscribed: int = 0
    spam_complaints: int = 0

    # Rates
    reply_rate: float = 0.0
    open_rate: float = 0.0
    bounce_rate: float = 0.0
    interested_rate: float = 0.0

    # Timeline
    days_active: int = 0
    daily_send_rate: float = 0.0

    # Snapshot history
    snapshots: Optional[list[dict]] = None


class CampaignStatusUpdate(BaseModel):
    """Update campaign status"""
    status: CampaignStatus
