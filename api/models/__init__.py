"""
Pydantic models for Charm Email OS API
"""

from .workspace import Workspace, WorkspaceList
from .client import Client, ClientCreate, ClientUpdate, ClientOnboard, ClientList
from .domain import Domain, DomainCreate, DomainList, DomainHealth
from .inbox import Inbox, InboxCreate, InboxList, InboxHealth
from .campaign import Campaign, CampaignCreate, CampaignList, CampaignMetrics
from .lead import Lead, LeadCreate, LeadUpdate, LeadBulkCreate, LeadList
from .health import HealthOverview, InboxHealthMetrics, DomainHealthMetrics, Alert

__all__ = [
    # Workspace
    "Workspace", "WorkspaceList",
    # Client
    "Client", "ClientCreate", "ClientUpdate", "ClientOnboard", "ClientList",
    # Domain
    "Domain", "DomainCreate", "DomainList", "DomainHealth",
    # Inbox
    "Inbox", "InboxCreate", "InboxList", "InboxHealth",
    # Campaign
    "Campaign", "CampaignCreate", "CampaignList", "CampaignMetrics",
    # Lead
    "Lead", "LeadCreate", "LeadUpdate", "LeadBulkCreate", "LeadList",
    # Health
    "HealthOverview", "InboxHealthMetrics", "DomainHealthMetrics", "Alert",
]
