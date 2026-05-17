"""
Project routes — long-term initiatives that contain tasks.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
import logging

from database import fetch_all, fetch_one, execute
from models.project import (
    Project,
    ProjectCreate,
    ProjectUpdate,
    ProjectList,
    ProjectProgress,
)

router = APIRouter()
logger = logging.getLogger(__name__)


_PROJECT_SELECT = """
SELECT p.id, p.workspace_id, p.name, p.description, p.status, p.priority,
       p.color, p.owner_agent_id, p.owner_user_id,
       p.start_at, p.target_end_at, p.actual_end_at,
       p.created_by_user_id, p.created_at, p.updated_at,
       w.workspace_name AS workspace_name,
       a.name AS owner_agent_name,
       pp.total_tasks, pp.done_tasks, pp.in_progress_tasks,
       pp.in_review_tasks, pp.blocked_tasks, pp.overdue_tasks,
       pp.percent_done, pp.earliest_task_start, pp.latest_task_end
FROM projects p
LEFT JOIN workspaces w ON w.id = p.workspace_id
LEFT JOIN agents a ON a.id = p.owner_agent_id
LEFT JOIN project_progress pp ON pp.project_id = p.id
"""


def _row_to_project(row: dict) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        description=row.get("description"),
        status=row["status"],
        priority=row["priority"],
        color=row.get("color"),
        workspace_id=row.get("workspace_id"),
        owner_agent_id=row.get("owner_agent_id"),
        owner_user_id=row.get("owner_user_id"),
        start_at=row.get("start_at"),
        target_end_at=row.get("target_end_at"),
        actual_end_at=row.get("actual_end_at"),
        created_by_user_id=row.get("created_by_user_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        workspace_name=row.get("workspace_name"),
        owner_agent_name=row.get("owner_agent_name"),
        progress=ProjectProgress(
            total_tasks=int(row.get("total_tasks") or 0),
            done_tasks=int(row.get("done_tasks") or 0),
            in_progress_tasks=int(row.get("in_progress_tasks") or 0),
            in_review_tasks=int(row.get("in_review_tasks") or 0),
            blocked_tasks=int(row.get("blocked_tasks") or 0),
            overdue_tasks=int(row.get("overdue_tasks") or 0),
            percent_done=float(row.get("percent_done") or 0),
            earliest_task_start=row.get("earliest_task_start"),
            latest_task_end=row.get("latest_task_end"),
        ),
    )


async def _log_action(
    action: str,
    entity_type: str,
    entity_id: Optional[UUID],
    workspace_id: Optional[UUID],
    actor_user_id: Optional[UUID],
    actor_label: Optional[str],
    details: dict,
):
    await execute(
        """
        INSERT INTO operator_actions
            (actor_user_id, actor_label, action, entity_type, entity_id, workspace_id, details)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        actor_user_id,
        actor_label,
        action,
        entity_type,
        entity_id,
        workspace_id,
        details,
    )


@router.get("", response_model=ProjectList)
async def list_projects(
    workspace_id: Optional[UUID] = Query(default=None),
    status: Optional[str] = None,
    include_closed: bool = Query(default=True),
):
    conditions: list[str] = []
    params: list = []

    def add(clause: str, value):
        params.append(value)
        conditions.append(clause.replace("?", f"${len(params)}"))

    if workspace_id:
        add("p.workspace_id = ?", workspace_id)
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            add("p.status = ?", statuses[0])
        else:
            params.append(statuses)
            conditions.append(f"p.status = ANY(${len(params)}::text[])")
    elif not include_closed:
        conditions.append("p.status NOT IN ('done', 'cancelled')")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = await fetch_all(
        f"""
        {_PROJECT_SELECT}
        {where}
        ORDER BY
            CASE p.status
                WHEN 'active' THEN 0
                WHEN 'planning' THEN 1
                WHEN 'paused' THEN 2
                WHEN 'done' THEN 3
                WHEN 'cancelled' THEN 4
            END,
            p.priority DESC,
            p.target_end_at NULLS LAST,
            p.created_at DESC
        """,
        *params,
    )
    items = [_row_to_project(dict(r)) for r in rows]
    return ProjectList(items=items, total=len(items))


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: UUID):
    row = await fetch_one(_PROJECT_SELECT + " WHERE p.id = $1", project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return _row_to_project(dict(row))


@router.post("", response_model=Project, status_code=201)
async def create_project(body: ProjectCreate):
    row = await fetch_one(
        """
        INSERT INTO projects
            (name, description, status, priority, color,
             workspace_id, owner_agent_id, owner_user_id,
             start_at, target_end_at, created_by_user_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING id
        """,
        body.name,
        body.description,
        body.status,
        body.priority,
        body.color,
        body.workspace_id,
        body.owner_agent_id,
        body.owner_user_id,
        body.start_at,
        body.target_end_at,
        body.created_by_user_id,
    )
    new_id = row["id"]
    await _log_action(
        action="project.create",
        entity_type="project",
        entity_id=new_id,
        workspace_id=body.workspace_id,
        actor_user_id=body.created_by_user_id,
        actor_label=body.created_by_label,
        details={"name": body.name, "status": body.status, "priority": body.priority},
    )
    full = await fetch_one(_PROJECT_SELECT + " WHERE p.id = $1", new_id)
    return _row_to_project(dict(full))


@router.patch("/{project_id}", response_model=Project)
async def update_project(project_id: UUID, body: ProjectUpdate):
    existing = await fetch_one(
        "SELECT id, workspace_id, status FROM projects WHERE id = $1",
        project_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    set_parts: list[str] = []
    params: list = []

    def add(col: str, value):
        params.append(value)
        set_parts.append(f"{col} = ${len(params)}")

    if body.name is not None:
        add("name", body.name)
    if body.description is not None:
        add("description", body.description)
    if body.status is not None:
        add("status", body.status)
    if body.priority is not None:
        add("priority", body.priority)
    if body.color is not None:
        add("color", body.color)
    if body.workspace_id is not None:
        add("workspace_id", body.workspace_id)
    if body.owner_agent_id is not None:
        add("owner_agent_id", body.owner_agent_id)
    if body.owner_user_id is not None:
        add("owner_user_id", body.owner_user_id)
    if body.start_at is not None:
        add("start_at", body.start_at)
    if body.target_end_at is not None:
        add("target_end_at", body.target_end_at)

    if set_parts:
        params.append(project_id)
        await execute(
            f"UPDATE projects SET {', '.join(set_parts)} WHERE id = ${len(params)}",
            *params,
        )

    await _log_action(
        action="project.update",
        entity_type="project",
        entity_id=project_id,
        workspace_id=existing.get("workspace_id"),
        actor_user_id=body.actor_user_id,
        actor_label=body.actor_label,
        details=body.model_dump(by_alias=True, exclude_none=True, exclude={"actor_user_id", "actor_label"}),
    )

    return await get_project(project_id)
