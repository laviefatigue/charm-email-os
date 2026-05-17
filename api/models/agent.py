"""
Agent models — paperclip-pattern analyst agents.
Backs the agents + agent_skills + agent_skill_mappings tables (migrations 112-113).
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
from datetime import datetime
from uuid import UUID


AgentRole = Literal["data_analyst", "researcher", "day_ai_reviewer", "github_admin", "general"]
AgentStatus = Literal["active", "idle", "running", "error", "paused", "terminated"]
AdapterType = Literal["claude_local", "process", "http"]


class HeartbeatPolicy(BaseModel):
    """Per-agent scheduling config."""
    enabled: bool = False
    interval_sec: int = Field(default=300, alias="intervalSec")
    wake_on_assignment: bool = Field(default=True, alias="wakeOnAssignment")
    cooldown_sec: int = Field(default=60, alias="cooldownSec")

    class Config:
        populate_by_name = True


class AgentSkill(BaseModel):
    """One row from the global skill library."""
    slug: str
    name: str
    description: str
    body_markdown: str = Field(default="", alias="bodyMarkdown")
    version: str = "1.0.0"
    is_active: bool = Field(default=True, alias="isActive")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    class Config:
        populate_by_name = True


class AgentSkillSummary(BaseModel):
    """Compact skill summary for inclusion in agent responses (no body)."""
    slug: str
    name: str
    description: str

    class Config:
        populate_by_name = True


class AgentBase(BaseModel):
    """Shared fields between create / update / read."""
    name: str = Field(..., min_length=1, max_length=64)
    role: AgentRole
    title: str
    description: Optional[str] = None
    capabilities: Optional[str] = None
    adapter_type: AdapterType = Field(default="claude_local", alias="adapterType")
    adapter_config: dict[str, Any] = Field(default_factory=dict, alias="adapterConfig")
    budget_monthly_cents: int = Field(default=5000, ge=0, alias="budgetMonthlyCents")
    heartbeat_policy: HeartbeatPolicy = Field(
        default_factory=HeartbeatPolicy, alias="heartbeatPolicy"
    )
    is_active: bool = Field(default=True, alias="isActive")

    class Config:
        populate_by_name = True


class AgentCreate(AgentBase):
    """Admin-only — create a new agent."""
    skill_slugs: list[str] = Field(default_factory=list, alias="skillSlugs")


class AgentUpdate(BaseModel):
    """Admin-only — patch existing agent. All fields optional."""
    title: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[str] = None
    adapter_type: Optional[AdapterType] = Field(default=None, alias="adapterType")
    adapter_config: Optional[dict[str, Any]] = Field(default=None, alias="adapterConfig")
    budget_monthly_cents: Optional[int] = Field(default=None, ge=0, alias="budgetMonthlyCents")
    heartbeat_policy: Optional[HeartbeatPolicy] = Field(default=None, alias="heartbeatPolicy")
    status: Optional[AgentStatus] = None
    is_active: Optional[bool] = Field(default=None, alias="isActive")
    skill_slugs: Optional[list[str]] = Field(default=None, alias="skillSlugs")

    class Config:
        populate_by_name = True


class Agent(AgentBase):
    """Full agent — what API GET returns."""
    id: UUID
    status: AgentStatus = "active"
    spent_monthly_cents: int = Field(default=0, alias="spentMonthlyCents")
    last_run_at: Optional[datetime] = Field(default=None, alias="lastRunAt")
    last_error: Optional[str] = Field(default=None, alias="lastError")
    skills: list[AgentSkillSummary] = Field(default_factory=list)
    pending_task_count: int = Field(default=0, alias="pendingTaskCount")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    class Config:
        populate_by_name = True


class AgentList(BaseModel):
    items: list[Agent]
    total: int
