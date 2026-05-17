"""
Task routes — paperclip-pattern issues, Charm-renamed.
CRUD + checkout + comments + documents.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID, uuid4
import re
import logging

from database import fetch_all, fetch_one, execute
from models.task import (
    Task,
    TaskCreate,
    TaskUpdate,
    TaskList,
    TaskDetail,
    TaskCheckoutRequest,
    TaskComment,
    TaskCommentCreate,
    TaskDocument,
    TaskDocumentUpsert,
    TaskDocumentRevision,
    ActorType,
)

router = APIRouter()
logger = logging.getLogger(__name__)


MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]+)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_mentions(body: str) -> list[UUID]:
    """Extract @Mentions and resolve to agent UUIDs (case-insensitive)."""
    names = list({m.group(1) for m in MENTION_RE.finditer(body)})
    if not names:
        return []
    rows = await fetch_all(
        "SELECT id FROM agents WHERE LOWER(name) = ANY($1::text[])",
        [n.lower() for n in names],
    )
    return [r["id"] for r in rows]


def _row_to_task(row: dict) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        description=row.get("description"),
        status=row["status"],
        priority=row["priority"],
        workspace_id=row.get("workspace_id"),
        assignee_agent_id=row.get("assignee_agent_id"),
        parent_task_id=row.get("parent_task_id"),
        due_at=row.get("due_at"),
        source=row["source"],
        inbound_origin=row.get("inbound_origin"),
        created_by_user_id=row.get("created_by_user_id"),
        checkout_token=row.get("checkout_token"),
        checkout_at=row.get("checkout_at"),
        started_at=row.get("started_at"),
        closed_at=row.get("closed_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        assignee_agent_name=row.get("assignee_agent_name"),
        workspace_name=row.get("workspace_name"),
        comment_count=int(row.get("comment_count") or 0),
        document_count=int(row.get("document_count") or 0),
    )


_TASK_LIST_SELECT = """
SELECT t.id, t.title, t.description, t.status, t.priority,
       t.workspace_id, t.assignee_agent_id, t.parent_task_id, t.due_at,
       t.source, t.inbound_origin, t.created_by_user_id,
       t.checkout_token, t.checkout_at, t.started_at, t.closed_at,
       t.created_at, t.updated_at,
       a.name AS assignee_agent_name,
       w.workspace_name AS workspace_name,
       (SELECT COUNT(*) FROM task_comments WHERE task_id = t.id) AS comment_count,
       (SELECT COUNT(*) FROM task_documents WHERE task_id = t.id) AS document_count
FROM tasks t
LEFT JOIN agents a ON a.id = t.assignee_agent_id
LEFT JOIN workspaces w ON w.id = t.workspace_id
"""


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


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.post("", response_model=Task, status_code=201)
async def create_task(body: TaskCreate):
    row = await fetch_one(
        """
        INSERT INTO tasks
            (title, description, status, priority, workspace_id,
             assignee_agent_id, parent_task_id, source, inbound_origin,
             created_by_user_id, due_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING id
        """,
        body.title,
        body.description,
        body.status,
        body.priority,
        body.workspace_id,
        body.assignee_agent_id,
        body.parent_task_id,
        body.source,
        body.inbound_origin,
        body.created_by_user_id,
        body.due_at,
    )
    new_id = row["id"]

    await _log_action(
        action="task.create",
        entity_type="task",
        entity_id=new_id,
        workspace_id=body.workspace_id,
        actor_user_id=body.created_by_user_id,
        actor_label=body.created_by_label,
        details={
            "title": body.title,
            "assignee_agent_id": str(body.assignee_agent_id) if body.assignee_agent_id else None,
            "priority": body.priority,
            "source": body.source,
        },
    )

    full = await fetch_one(_TASK_LIST_SELECT + " WHERE t.id = $1", new_id)
    return _row_to_task(dict(full))


@router.get("", response_model=TaskList)
async def list_tasks(
    status: Optional[str] = None,
    assignee_agent_id: Optional[UUID] = Query(default=None),
    workspace_id: Optional[UUID] = Query(default=None),
    parent_task_id: Optional[UUID] = Query(default=None),
    include_closed: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    conditions: list[str] = []
    params: list = []

    def add(clause: str, value):
        params.append(value)
        conditions.append(clause.replace("?", f"${len(params)}"))

    if status:
        # Support comma-separated multi-status filter
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            add("t.status = ?", statuses[0])
        else:
            params.append(statuses)
            conditions.append(f"t.status = ANY(${len(params)}::text[])")
    elif not include_closed:
        conditions.append("t.status NOT IN ('done', 'blocked')")

    if assignee_agent_id:
        add("t.assignee_agent_id = ?", assignee_agent_id)
    if workspace_id:
        add("t.workspace_id = ?", workspace_id)
    if parent_task_id:
        add("t.parent_task_id = ?", parent_task_id)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Count
    cnt_row = await fetch_one(f"SELECT COUNT(*) AS cnt FROM tasks t {where}", *params)
    total = int(cnt_row["cnt"]) if cnt_row else 0

    offset = (page - 1) * page_size
    params_with_paging = params + [page_size, offset]
    rows = await fetch_all(
        f"""
        {_TASK_LIST_SELECT}
        {where}
        ORDER BY
            CASE t.priority
                WHEN 'urgent' THEN 0
                WHEN 'high'   THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low'    THEN 3
            END,
            t.updated_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params_with_paging,
    )

    items = [_row_to_task(dict(r)) for r in rows]
    return TaskList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task(task_id: UUID):
    row = await fetch_one(_TASK_LIST_SELECT + " WHERE t.id = $1", task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    task = _row_to_task(dict(row))

    # Comments
    comment_rows = await fetch_all(
        """
        SELECT c.id, c.task_id, c.actor_type, c.actor_agent_id, c.actor_user_id,
               c.actor_label, c.body_markdown, c.mentioned_agent_ids, c.created_at,
               a.name AS actor_agent_name
        FROM task_comments c
        LEFT JOIN agents a ON a.id = c.actor_agent_id
        WHERE c.task_id = $1
        ORDER BY c.created_at ASC
        """,
        task_id,
    )
    comments: list[TaskComment] = []
    for r in comment_rows:
        d = dict(r)
        actor_display = d.get("actor_agent_name") or d.get("actor_label") or "operator"
        comments.append(
            TaskComment(
                id=d["id"],
                task_id=d["task_id"],
                actor_type=d["actor_type"],
                actor_agent_id=d.get("actor_agent_id"),
                actor_user_id=d.get("actor_user_id"),
                actor_label=d.get("actor_label"),
                actor_display=actor_display,
                body_markdown=d["body_markdown"],
                mentioned_agent_ids=d.get("mentioned_agent_ids") or [],
                created_at=d["created_at"],
            )
        )

    # Documents
    doc_rows = await fetch_all(
        """
        SELECT id, task_id, doc_key, title, format, body, latest_revision_number,
               created_by_agent_id, created_by_user_id,
               updated_by_agent_id, updated_by_user_id,
               cited_context, created_at, updated_at
        FROM task_documents
        WHERE task_id = $1
        ORDER BY updated_at DESC
        """,
        task_id,
    )
    documents = [TaskDocument(**dict(r)) for r in doc_rows]

    # Children
    child_rows = await fetch_all(
        _TASK_LIST_SELECT + " WHERE t.parent_task_id = $1 ORDER BY t.created_at",
        task_id,
    )
    children = [_row_to_task(dict(r)) for r in child_rows]

    return TaskDetail(
        **task.model_dump(by_alias=False),
        comments=comments,
        documents=documents,
        children=children,
    )


@router.patch("/{task_id}", response_model=Task)
async def update_task(task_id: UUID, body: TaskUpdate):
    existing = await fetch_one(
        "SELECT id, workspace_id, status, assignee_agent_id FROM tasks WHERE id = $1",
        task_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    set_parts: list[str] = []
    params: list = []

    def add(col: str, value):
        params.append(value)
        set_parts.append(f"{col} = ${len(params)}")

    if body.title is not None:
        add("title", body.title)
    if body.description is not None:
        add("description", body.description)
    if body.status is not None:
        add("status", body.status)
    if body.priority is not None:
        add("priority", body.priority)
    if body.workspace_id is not None:
        add("workspace_id", body.workspace_id)
    if body.assignee_agent_id is not None:
        add("assignee_agent_id", body.assignee_agent_id)
    if body.parent_task_id is not None:
        add("parent_task_id", body.parent_task_id)
    if body.due_at is not None:
        add("due_at", body.due_at)

    if set_parts:
        params.append(task_id)
        await execute(
            f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = ${len(params)}",
            *params,
        )

    # Optional inline comment
    if body.comment:
        mentions = await _resolve_mentions(body.comment)
        await execute(
            """
            INSERT INTO task_comments
                (task_id, actor_type, actor_user_id, actor_label,
                 body_markdown, mentioned_agent_ids)
            VALUES ($1, 'operator', $2, $3, $4, $5)
            """,
            task_id,
            body.actor_user_id,
            body.actor_label,
            body.comment,
            mentions,
        )

    # Log mutation
    changed_fields = body.model_dump(by_alias=True, exclude_none=True)
    changed_fields.pop("comment", None)
    if changed_fields:
        action = "task.status_change" if body.status else (
            "task.assign" if body.assignee_agent_id else "task.update"
        )
        await _log_action(
            action=action,
            entity_type="task",
            entity_id=task_id,
            workspace_id=existing["workspace_id"],
            actor_user_id=body.actor_user_id,
            actor_label=body.actor_label,
            details=changed_fields,
        )

    full = await fetch_one(_TASK_LIST_SELECT + " WHERE t.id = $1", task_id)
    return _row_to_task(dict(full))


@router.post("/{task_id}/checkout", response_model=Task)
async def checkout_task(task_id: UUID, body: TaskCheckoutRequest):
    """Atomic claim. 409 if owned by someone else."""
    current = await fetch_one(
        "SELECT checkout_token, status, assignee_agent_id FROM tasks WHERE id = $1",
        task_id,
    )
    if not current:
        raise HTTPException(status_code=404, detail="Task not found")
    if current["status"] not in body.expected_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Task status '{current['status']}' not in expected {body.expected_statuses}",
        )
    if current["checkout_token"] is not None:
        # Idempotent re-claim by the same agent is fine; otherwise 409
        if (
            body.actor_agent_id
            and current["assignee_agent_id"] == body.actor_agent_id
        ):
            pass
        else:
            raise HTTPException(status_code=409, detail="Task already checked out")

    token = uuid4()
    await execute(
        """
        UPDATE tasks
        SET checkout_token = $1,
            checkout_at = NOW(),
            status = 'in_progress',
            assignee_agent_id = COALESCE($2, assignee_agent_id)
        WHERE id = $3
        """,
        token,
        body.actor_agent_id,
        task_id,
    )

    await _log_action(
        action="task.checkout",
        entity_type="task",
        entity_id=task_id,
        workspace_id=None,
        actor_user_id=body.actor_user_id,
        actor_label=None,
        details={
            "actor_agent_id": str(body.actor_agent_id) if body.actor_agent_id else None,
            "token": str(token),
        },
    )

    full = await fetch_one(_TASK_LIST_SELECT + " WHERE t.id = $1", task_id)
    return _row_to_task(dict(full))


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@router.post("/{task_id}/comments", response_model=TaskComment, status_code=201)
async def post_comment(task_id: UUID, body: TaskCommentCreate):
    task_row = await fetch_one("SELECT workspace_id FROM tasks WHERE id = $1", task_id)
    if not task_row:
        raise HTTPException(status_code=404, detail="Task not found")

    mentions = await _resolve_mentions(body.body_markdown)
    row = await fetch_one(
        """
        INSERT INTO task_comments
            (task_id, actor_type, actor_user_id, actor_label,
             body_markdown, mentioned_agent_ids)
        VALUES ($1, 'operator', $2, $3, $4, $5)
        RETURNING id, task_id, actor_type, actor_user_id, actor_label,
                  body_markdown, mentioned_agent_ids, created_at
        """,
        task_id,
        body.actor_user_id,
        body.actor_label,
        body.body_markdown,
        mentions,
    )

    await _log_action(
        action="task.comment",
        entity_type="comment",
        entity_id=row["id"],
        workspace_id=task_row["workspace_id"],
        actor_user_id=body.actor_user_id,
        actor_label=body.actor_label,
        details={"task_id": str(task_id), "mentions": [str(m) for m in mentions]},
    )

    d = dict(row)
    return TaskComment(
        id=d["id"],
        task_id=d["task_id"],
        actor_type=d["actor_type"],
        actor_user_id=d.get("actor_user_id"),
        actor_label=d.get("actor_label"),
        actor_display=d.get("actor_label") or "operator",
        body_markdown=d["body_markdown"],
        mentioned_agent_ids=d.get("mentioned_agent_ids") or [],
        created_at=d["created_at"],
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.put("/{task_id}/documents/{doc_key}", response_model=TaskDocument)
async def upsert_document(task_id: UUID, doc_key: str, body: TaskDocumentUpsert):
    """Insert or update a keyed document; appends a revision."""
    task_row = await fetch_one("SELECT workspace_id FROM tasks WHERE id = $1", task_id)
    if not task_row:
        raise HTTPException(status_code=404, detail="Task not found")

    existing = await fetch_one(
        "SELECT id, latest_revision_number FROM task_documents WHERE task_id = $1 AND doc_key = $2",
        task_id,
        doc_key,
    )

    cited = (
        [c.model_dump(by_alias=True) for c in body.cited_context]
        if body.cited_context
        else None
    )

    if existing:
        doc_id = existing["id"]
        next_rev = (existing["latest_revision_number"] or 0) + 1
        await execute(
            """
            UPDATE task_documents
            SET title = COALESCE($1, title),
                format = $2,
                body = $3,
                latest_revision_number = $4,
                updated_by_user_id = $5,
                cited_context = $6
            WHERE id = $7
            """,
            body.title,
            body.format,
            body.body,
            next_rev,
            body.actor_user_id,
            cited,
            doc_id,
        )
    else:
        next_rev = 1
        new_row = await fetch_one(
            """
            INSERT INTO task_documents
                (task_id, doc_key, title, format, body, latest_revision_number,
                 created_by_user_id, updated_by_user_id, cited_context)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $7, $8)
            RETURNING id
            """,
            task_id,
            doc_key,
            body.title,
            body.format,
            body.body,
            next_rev,
            body.actor_user_id,
            cited,
        )
        doc_id = new_row["id"]

    # Append revision
    await execute(
        """
        INSERT INTO task_document_revisions
            (document_id, revision_number, body, created_by_user_id, change_summary)
        VALUES ($1, $2, $3, $4, $5)
        """,
        doc_id,
        next_rev,
        body.body,
        body.actor_user_id,
        body.change_summary,
    )

    await _log_action(
        action="document.update",
        entity_type="document",
        entity_id=doc_id,
        workspace_id=task_row["workspace_id"],
        actor_user_id=body.actor_user_id,
        actor_label=None,
        details={"task_id": str(task_id), "doc_key": doc_key, "revision": next_rev},
    )

    doc_row = await fetch_one(
        """
        SELECT id, task_id, doc_key, title, format, body, latest_revision_number,
               created_by_agent_id, created_by_user_id,
               updated_by_agent_id, updated_by_user_id,
               cited_context, created_at, updated_at
        FROM task_documents WHERE id = $1
        """,
        doc_id,
    )
    return TaskDocument(**dict(doc_row))


@router.get("/{task_id}/documents/{doc_key}/revisions", response_model=list[TaskDocumentRevision])
async def list_document_revisions(task_id: UUID, doc_key: str):
    doc = await fetch_one(
        "SELECT id FROM task_documents WHERE task_id = $1 AND doc_key = $2",
        task_id,
        doc_key,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    rows = await fetch_all(
        """
        SELECT id, revision_number, body, change_summary,
               created_by_agent_id, created_by_user_id, created_at
        FROM task_document_revisions
        WHERE document_id = $1
        ORDER BY revision_number DESC
        """,
        doc["id"],
    )
    return [TaskDocumentRevision(**dict(r)) for r in rows]
