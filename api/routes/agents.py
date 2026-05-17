"""
Agent routes — paperclip-pattern analyst agents.
Admin owns config; AEs read the roster + assign tasks (via tasks.py routes).
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
import logging

from database import fetch_all, fetch_one, execute
from models.agent import (
    Agent,
    AgentCreate,
    AgentUpdate,
    AgentList,
    AgentSkill,
    AgentSkillSummary,
    HeartbeatPolicy,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_skills_for_agent(agent_id: UUID) -> list[AgentSkillSummary]:
    rows = await fetch_all(
        """
        SELECT s.slug, s.name, s.description
        FROM agent_skills s
        JOIN agent_skill_mappings m ON m.skill_slug = s.slug
        WHERE m.agent_id = $1 AND s.is_active = TRUE
        ORDER BY s.name
        """,
        agent_id,
    )
    return [AgentSkillSummary(**dict(r)) for r in rows]


async def _pending_task_count(agent_id: UUID) -> int:
    row = await fetch_one(
        """
        SELECT COUNT(*) AS cnt
        FROM tasks
        WHERE assignee_agent_id = $1
          AND status NOT IN ('done', 'blocked')
        """,
        agent_id,
    )
    return int(row["cnt"]) if row else 0


def _agent_row_to_model(row: dict, skills: list[AgentSkillSummary], pending: int) -> Agent:
    hp_raw = row.get("heartbeat_policy") or {}
    return Agent(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        title=row["title"],
        description=row.get("description"),
        capabilities=row.get("capabilities"),
        adapter_type=row["adapter_type"],
        adapter_config=row.get("adapter_config") or {},
        budget_monthly_cents=row["budget_monthly_cents"],
        spent_monthly_cents=row["spent_monthly_cents"],
        status=row["status"],
        heartbeat_policy=HeartbeatPolicy(
            enabled=hp_raw.get("enabled", False),
            interval_sec=hp_raw.get("intervalSec", hp_raw.get("interval_sec", 300)),
            wake_on_assignment=hp_raw.get(
                "wakeOnAssignment", hp_raw.get("wake_on_assignment", True)
            ),
            cooldown_sec=hp_raw.get("cooldownSec", hp_raw.get("cooldown_sec", 60)),
        ),
        last_run_at=row.get("last_run_at"),
        last_error=row.get("last_error"),
        is_active=row["is_active"],
        skills=skills,
        pending_task_count=pending,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Skills (global library)
# ---------------------------------------------------------------------------

@router.get("/skills", response_model=list[AgentSkill])
async def list_skills(active_only: bool = Query(True)):
    """Global skill library."""
    where = "WHERE is_active = TRUE" if active_only else ""
    rows = await fetch_all(
        f"""
        SELECT slug, name, description, body_markdown, version, is_active,
               created_at, updated_at
        FROM agent_skills
        {where}
        ORDER BY name
        """
    )
    return [AgentSkill(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@router.get("", response_model=AgentList)
async def list_agents(role: Optional[str] = None, active_only: bool = Query(True)):
    """List agents (with attached skills + pending task count)."""
    conditions: list[str] = []
    params: list = []
    if active_only:
        conditions.append("is_active = TRUE")
    if role:
        conditions.append(f"role = ${len(params) + 1}")
        params.append(role)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = await fetch_all(
        f"""
        SELECT id, name, role, title, description, capabilities,
               adapter_type, adapter_config, budget_monthly_cents,
               spent_monthly_cents, status, heartbeat_policy,
               last_run_at, last_error, is_active, created_at, updated_at
        FROM agents
        {where}
        ORDER BY role, name
        """,
        *params,
    )

    agents: list[Agent] = []
    for r in rows:
        row = dict(r)
        skills = await _load_skills_for_agent(row["id"])
        pending = await _pending_task_count(row["id"])
        agents.append(_agent_row_to_model(row, skills, pending))

    return AgentList(items=agents, total=len(agents))


@router.get("/{agent_id}", response_model=Agent)
async def get_agent(agent_id: UUID):
    row = await fetch_one(
        """
        SELECT id, name, role, title, description, capabilities,
               adapter_type, adapter_config, budget_monthly_cents,
               spent_monthly_cents, status, heartbeat_policy,
               last_run_at, last_error, is_active, created_at, updated_at
        FROM agents
        WHERE id = $1
        """,
        agent_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    row = dict(row)
    skills = await _load_skills_for_agent(agent_id)
    pending = await _pending_task_count(agent_id)
    return _agent_row_to_model(row, skills, pending)


@router.patch("/{agent_id}", response_model=Agent)
async def update_agent(agent_id: UUID, body: AgentUpdate):
    """Admin-only — update agent config + skill mappings."""
    existing = await fetch_one("SELECT id FROM agents WHERE id = $1", agent_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Agent not found")

    set_parts: list[str] = []
    params: list = []

    def add(col: str, value):
        params.append(value)
        set_parts.append(f"{col} = ${len(params)}")

    if body.title is not None:
        add("title", body.title)
    if body.description is not None:
        add("description", body.description)
    if body.capabilities is not None:
        add("capabilities", body.capabilities)
    if body.adapter_type is not None:
        add("adapter_type", body.adapter_type)
    if body.adapter_config is not None:
        add("adapter_config", body.adapter_config)
    if body.budget_monthly_cents is not None:
        add("budget_monthly_cents", body.budget_monthly_cents)
    if body.heartbeat_policy is not None:
        add("heartbeat_policy", body.heartbeat_policy.model_dump(by_alias=True))
    if body.status is not None:
        add("status", body.status)
    if body.is_active is not None:
        add("is_active", body.is_active)

    if set_parts:
        params.append(agent_id)
        await execute(
            f"UPDATE agents SET {', '.join(set_parts)} WHERE id = ${len(params)}",
            *params,
        )

    # Replace skill mappings if provided
    if body.skill_slugs is not None:
        await execute("DELETE FROM agent_skill_mappings WHERE agent_id = $1", agent_id)
        for slug in body.skill_slugs:
            await execute(
                """
                INSERT INTO agent_skill_mappings (agent_id, skill_slug)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                agent_id,
                slug,
            )

    # Log to operator_actions
    await execute(
        """
        INSERT INTO operator_actions (action, entity_type, entity_id, details)
        VALUES ('agent.update', 'agent', $1, $2)
        """,
        agent_id,
        body.model_dump(by_alias=True, exclude_none=True),
    )

    return await get_agent(agent_id)
