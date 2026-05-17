"""
Task models — paperclip-pattern issues, Charm-renamed.
Backs the tasks + task_comments + task_documents + task_document_revisions tables
(migrations 114-115).
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
from datetime import datetime
from uuid import UUID


TaskStatus = Literal["backlog", "todo", "in_progress", "in_review", "done", "blocked"]
TaskPriority = Literal["low", "medium", "high", "urgent"]
TaskSource = Literal["operator", "agent", "inbound", "system"]
ActorType = Literal["operator", "agent", "system"]
DocumentFormat = Literal["markdown", "plain_text", "json"]


# ───────────────────────────────────────────────────────────────────────────────
# Comments
# ───────────────────────────────────────────────────────────────────────────────

class TaskCommentBase(BaseModel):
    body_markdown: str = Field(..., min_length=1, alias="bodyMarkdown")

    class Config:
        populate_by_name = True


class TaskCommentCreate(TaskCommentBase):
    """Operator (or system) posts a comment. Mentions parsed server-side."""
    actor_user_id: Optional[UUID] = Field(default=None, alias="actorUserId")
    actor_label: Optional[str] = Field(default=None, alias="actorLabel")

    class Config:
        populate_by_name = True


class TaskComment(TaskCommentBase):
    id: UUID
    task_id: UUID = Field(..., alias="taskId")
    actor_type: ActorType = Field(..., alias="actorType")
    actor_agent_id: Optional[UUID] = Field(default=None, alias="actorAgentId")
    actor_user_id: Optional[UUID] = Field(default=None, alias="actorUserId")
    actor_label: Optional[str] = Field(default=None, alias="actorLabel")
    actor_display: Optional[str] = Field(default=None, alias="actorDisplay")
    # Resolved when actor_type='agent' (joined agent.name) or actor_type='operator' (label or user lookup)
    mentioned_agent_ids: list[UUID] = Field(default_factory=list, alias="mentionedAgentIds")
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        populate_by_name = True


# ───────────────────────────────────────────────────────────────────────────────
# Documents
# ───────────────────────────────────────────────────────────────────────────────

class CitedContextItem(BaseModel):
    path: str
    commit_sha: Optional[str] = Field(default=None, alias="commitSha")
    relevance: Optional[str] = None

    class Config:
        populate_by_name = True


class TaskDocumentBase(BaseModel):
    doc_key: str = Field(..., min_length=1, max_length=64, alias="docKey")
    title: Optional[str] = None
    format: DocumentFormat = "markdown"
    body: str = ""
    cited_context: Optional[list[CitedContextItem]] = Field(default=None, alias="citedContext")

    class Config:
        populate_by_name = True


class TaskDocumentUpsert(TaskDocumentBase):
    """PUT payload — server inserts or appends a new revision."""
    change_summary: Optional[str] = Field(default=None, alias="changeSummary")
    actor_user_id: Optional[UUID] = Field(default=None, alias="actorUserId")

    class Config:
        populate_by_name = True


class TaskDocumentRevision(BaseModel):
    id: UUID
    revision_number: int = Field(..., alias="revisionNumber")
    body: str
    change_summary: Optional[str] = Field(default=None, alias="changeSummary")
    created_by_agent_id: Optional[UUID] = Field(default=None, alias="createdByAgentId")
    created_by_user_id: Optional[UUID] = Field(default=None, alias="createdByUserId")
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        populate_by_name = True


class TaskDocument(TaskDocumentBase):
    id: UUID
    task_id: UUID = Field(..., alias="taskId")
    latest_revision_number: int = Field(default=0, alias="latestRevisionNumber")
    created_by_agent_id: Optional[UUID] = Field(default=None, alias="createdByAgentId")
    created_by_user_id: Optional[UUID] = Field(default=None, alias="createdByUserId")
    updated_by_agent_id: Optional[UUID] = Field(default=None, alias="updatedByAgentId")
    updated_by_user_id: Optional[UUID] = Field(default=None, alias="updatedByUserId")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    class Config:
        populate_by_name = True


# ───────────────────────────────────────────────────────────────────────────────
# Tasks
# ───────────────────────────────────────────────────────────────────────────────

class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    workspace_id: Optional[UUID] = Field(default=None, alias="workspaceId")
    assignee_agent_id: Optional[UUID] = Field(default=None, alias="assigneeAgentId")
    parent_task_id: Optional[UUID] = Field(default=None, alias="parentTaskId")
    due_at: Optional[datetime] = Field(default=None, alias="dueAt")

    class Config:
        populate_by_name = True


class TaskCreate(TaskBase):
    source: TaskSource = "operator"
    inbound_origin: Optional[str] = Field(default=None, alias="inboundOrigin")
    created_by_user_id: Optional[UUID] = Field(default=None, alias="createdByUserId")
    created_by_label: Optional[str] = Field(default=None, alias="createdByLabel")

    class Config:
        populate_by_name = True


class TaskUpdate(BaseModel):
    """PATCH — all fields optional."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    workspace_id: Optional[UUID] = Field(default=None, alias="workspaceId")
    assignee_agent_id: Optional[UUID] = Field(default=None, alias="assigneeAgentId")
    parent_task_id: Optional[UUID] = Field(default=None, alias="parentTaskId")
    due_at: Optional[datetime] = Field(default=None, alias="dueAt")
    # Optional inline comment that posts alongside the update (paperclip pattern)
    comment: Optional[str] = None
    actor_user_id: Optional[UUID] = Field(default=None, alias="actorUserId")
    actor_label: Optional[str] = Field(default=None, alias="actorLabel")

    class Config:
        populate_by_name = True


class TaskCheckoutRequest(BaseModel):
    """Atomic claim. Agent or operator takes the task."""
    actor_user_id: Optional[UUID] = Field(default=None, alias="actorUserId")
    actor_agent_id: Optional[UUID] = Field(default=None, alias="actorAgentId")
    expected_statuses: list[TaskStatus] = Field(
        default_factory=lambda: ["backlog", "todo", "in_review", "blocked"],
        alias="expectedStatuses",
    )

    class Config:
        populate_by_name = True


class Task(TaskBase):
    id: UUID
    source: TaskSource = "operator"
    inbound_origin: Optional[str] = Field(default=None, alias="inboundOrigin")
    created_by_user_id: Optional[UUID] = Field(default=None, alias="createdByUserId")
    checkout_token: Optional[UUID] = Field(default=None, alias="checkoutToken")
    checkout_at: Optional[datetime] = Field(default=None, alias="checkoutAt")
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    closed_at: Optional[datetime] = Field(default=None, alias="closedAt")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    # Joined / convenience fields populated by route
    assignee_agent_name: Optional[str] = Field(default=None, alias="assigneeAgentName")
    workspace_name: Optional[str] = Field(default=None, alias="workspaceName")
    comment_count: int = Field(default=0, alias="commentCount")
    document_count: int = Field(default=0, alias="documentCount")

    class Config:
        populate_by_name = True


class TaskList(BaseModel):
    items: list[Task]
    total: int
    page: int = 1
    page_size: int = Field(default=50, alias="pageSize")

    class Config:
        populate_by_name = True


class TaskDetail(Task):
    """GET /tasks/{id} — task + comments + documents inline."""
    comments: list[TaskComment] = Field(default_factory=list)
    documents: list[TaskDocument] = Field(default_factory=list)
    children: list[Task] = Field(default_factory=list)
