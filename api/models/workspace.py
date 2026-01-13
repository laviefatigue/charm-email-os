"""
Workspace models - Read from OwnRBL workspaces table
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class Workspace(BaseModel):
    """OwnRBL workspace - read-only from database"""
    id: UUID
    workspace_name: str
    emailbison_workspace_id: Optional[int] = None
    sender_account_count: int = 0
    campaign_count: int = 0
    automation_enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkspaceList(BaseModel):
    """List of workspaces with pagination"""
    items: list[Workspace]
    total: int
    page: int = 1
    page_size: int = 50


class WorkspaceSummary(BaseModel):
    """Compact workspace summary for dropdowns"""
    id: UUID
    workspace_name: str
    sender_account_count: int = 0
    campaign_count: int = 0
