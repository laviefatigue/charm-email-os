"""
Project models — long-term initiatives that contain tasks.
Backs the projects table + project_progress view (migration 117).
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


ProjectStatus = Literal["planning", "active", "paused", "done", "cancelled"]
ProjectPriority = Literal["low", "medium", "high", "urgent"]


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: ProjectStatus = "planning"
    priority: ProjectPriority = "medium"
    color: Optional[str] = None
    workspace_id: Optional[UUID] = Field(default=None, alias="workspaceId")
    owner_agent_id: Optional[UUID] = Field(default=None, alias="ownerAgentId")
    owner_user_id: Optional[UUID] = Field(default=None, alias="ownerUserId")
    start_at: Optional[datetime] = Field(default=None, alias="startAt")
    target_end_at: Optional[datetime] = Field(default=None, alias="targetEndAt")

    class Config:
        populate_by_name = True


class ProjectCreate(ProjectBase):
    created_by_user_id: Optional[UUID] = Field(default=None, alias="createdByUserId")
    created_by_label: Optional[str] = Field(default=None, alias="createdByLabel")

    class Config:
        populate_by_name = True


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    priority: Optional[ProjectPriority] = None
    color: Optional[str] = None
    workspace_id: Optional[UUID] = Field(default=None, alias="workspaceId")
    owner_agent_id: Optional[UUID] = Field(default=None, alias="ownerAgentId")
    owner_user_id: Optional[UUID] = Field(default=None, alias="ownerUserId")
    start_at: Optional[datetime] = Field(default=None, alias="startAt")
    target_end_at: Optional[datetime] = Field(default=None, alias="targetEndAt")
    actor_user_id: Optional[UUID] = Field(default=None, alias="actorUserId")
    actor_label: Optional[str] = Field(default=None, alias="actorLabel")

    class Config:
        populate_by_name = True


class ProjectProgress(BaseModel):
    """Rollup from the project_progress view."""
    total_tasks: int = Field(default=0, alias="totalTasks")
    done_tasks: int = Field(default=0, alias="doneTasks")
    in_progress_tasks: int = Field(default=0, alias="inProgressTasks")
    in_review_tasks: int = Field(default=0, alias="inReviewTasks")
    blocked_tasks: int = Field(default=0, alias="blockedTasks")
    overdue_tasks: int = Field(default=0, alias="overdueTasks")
    percent_done: float = Field(default=0, alias="percentDone")
    earliest_task_start: Optional[datetime] = Field(default=None, alias="earliestTaskStart")
    latest_task_end: Optional[datetime] = Field(default=None, alias="latestTaskEnd")

    class Config:
        populate_by_name = True


class Project(ProjectBase):
    id: UUID
    actual_end_at: Optional[datetime] = Field(default=None, alias="actualEndAt")
    created_by_user_id: Optional[UUID] = Field(default=None, alias="createdByUserId")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    # Joined / convenience
    workspace_name: Optional[str] = Field(default=None, alias="workspaceName")
    owner_agent_name: Optional[str] = Field(default=None, alias="ownerAgentName")
    progress: ProjectProgress = Field(default_factory=ProjectProgress)

    class Config:
        populate_by_name = True


class ProjectList(BaseModel):
    items: list[Project]
    total: int
