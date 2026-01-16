"""
Client routes - CRUD for the new clients table
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
import json
import logging

from database import fetch_all, fetch_one, execute
from models.client import (
    Client, ClientCreate, ClientUpdate, ClientOnboard,
    ClientList, LinkWorkspaceRequest
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=ClientList)
async def list_clients(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    onboarding_complete: Optional[bool] = None
):
    """List all clients"""
    offset = (page - 1) * page_size

    # Build WHERE clause
    conditions = []
    params = []
    param_idx = 1

    if search:
        conditions.append(f"c.name ILIKE ${param_idx}")
        params.append(f"%{search}%")
        param_idx += 1

    if onboarding_complete is not None:
        conditions.append(f"c.onboarding_complete = ${param_idx}")
        params.append(onboarding_complete)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Get total count
    count_query = f"SELECT COUNT(*) as total FROM clients c {where_clause}"
    count_result = await fetch_one(count_query, *params)
    total = count_result["total"] if count_result else 0

    # Get clients with workspace info
    query = f"""
        SELECT
            c.id,
            c.name,
            c.workspace_id,
            w.workspace_name,
            c.logo_url,
            c.onboarding_complete,
            c.onboarding_data,
            c.contact_name,
            c.contact_email,
            c.website,
            c.industry,
            c.domain_pattern,
            c.created_at,
            c.updated_at,
            COALESCE(w.sender_account_count, 0) as inbox_count,
            COALESCE(
                (SELECT COUNT(*) FROM domains d WHERE d.workspace_id = c.workspace_id),
                0
            ) as domain_count,
            COALESCE(
                (SELECT COUNT(*) FROM emailbison_campaigns ec WHERE ec.workspace_id = c.workspace_id),
                0
            ) as campaign_count
        FROM clients c
        LEFT JOIN workspaces w ON c.workspace_id = w.id
        {where_clause}
        ORDER BY c.created_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([page_size, offset])

    rows = await fetch_all(query, *params)

    # Parse onboarding_data JSON string to dict for each row
    items = []
    for row in rows:
        row_dict = dict(row)
        if row_dict.get("onboarding_data") and isinstance(row_dict["onboarding_data"], str):
            row_dict["onboarding_data"] = json.loads(row_dict["onboarding_data"])
        items.append(Client(**row_dict))

    return ClientList(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("", response_model=Client)
async def create_client(client: ClientCreate):
    """Create a new client"""
    # Convert onboarding_data to JSON if provided
    onboarding_json = None
    if client.onboarding_data:
        onboarding_json = json.dumps(client.onboarding_data.model_dump(by_alias=True))

    query = """
        INSERT INTO clients (name, workspace_id, logo_url, onboarding_data,
                             contact_name, contact_email, website, industry, domain_pattern)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id, name, workspace_id, logo_url, onboarding_complete, onboarding_data,
                  contact_name, contact_email, website, industry, domain_pattern,
                  created_at, updated_at
    """
    row = await fetch_one(
        query,
        client.name,
        client.workspace_id,
        client.logo_url,
        onboarding_json,
        client.contact_name,
        client.contact_email,
        client.website,
        client.industry,
        client.domain_pattern
    )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create client")

    # Get workspace name if linked
    workspace_name = None
    if row["workspace_id"]:
        ws = await fetch_one("SELECT workspace_name FROM workspaces WHERE id = $1", row["workspace_id"])
        workspace_name = ws["workspace_name"] if ws else None

    return Client(
        **row,
        workspace_name=workspace_name,
        inbox_count=0,
        domain_count=0,
        campaign_count=0
    )


@router.get("/{client_id}", response_model=Client)
async def get_client(client_id: UUID):
    """Get a client by ID"""
    query = """
        SELECT
            c.id,
            c.name,
            c.workspace_id,
            w.workspace_name,
            c.logo_url,
            c.onboarding_complete,
            c.onboarding_data,
            c.contact_name,
            c.contact_email,
            c.website,
            c.industry,
            c.domain_pattern,
            c.created_at,
            c.updated_at,
            COALESCE(w.sender_account_count, 0) as inbox_count,
            COALESCE(
                (SELECT COUNT(*) FROM domains d WHERE d.workspace_id = c.workspace_id),
                0
            ) as domain_count,
            COALESCE(
                (SELECT COUNT(*) FROM emailbison_campaigns ec WHERE ec.workspace_id = c.workspace_id),
                0
            ) as campaign_count
        FROM clients c
        LEFT JOIN workspaces w ON c.workspace_id = w.id
        WHERE c.id = $1
    """
    row = await fetch_one(query, client_id)

    if not row:
        raise HTTPException(status_code=404, detail="Client not found")

    # Parse onboarding_data JSON string to dict
    row_dict = dict(row)
    if row_dict.get("onboarding_data") and isinstance(row_dict["onboarding_data"], str):
        row_dict["onboarding_data"] = json.loads(row_dict["onboarding_data"])

    return Client(**row_dict)


@router.put("/{client_id}", response_model=Client)
async def update_client(client_id: UUID, update: ClientUpdate):
    """Update a client"""
    # Build SET clause dynamically
    set_parts = []
    params = []
    param_idx = 1

    if update.name is not None:
        set_parts.append(f"name = ${param_idx}")
        params.append(update.name)
        param_idx += 1

    if update.workspace_id is not None:
        set_parts.append(f"workspace_id = ${param_idx}")
        params.append(update.workspace_id)
        param_idx += 1

    if update.logo_url is not None:
        set_parts.append(f"logo_url = ${param_idx}")
        params.append(update.logo_url)
        param_idx += 1

    if update.onboarding_complete is not None:
        set_parts.append(f"onboarding_complete = ${param_idx}")
        params.append(update.onboarding_complete)
        param_idx += 1

    if update.onboarding_data is not None:
        set_parts.append(f"onboarding_data = ${param_idx}")
        params.append(json.dumps(update.onboarding_data.model_dump(by_alias=True)))
        param_idx += 1

    # Profile fields
    if update.contact_name is not None:
        set_parts.append(f"contact_name = ${param_idx}")
        params.append(update.contact_name)
        param_idx += 1

    if update.contact_email is not None:
        set_parts.append(f"contact_email = ${param_idx}")
        params.append(update.contact_email)
        param_idx += 1

    if update.website is not None:
        set_parts.append(f"website = ${param_idx}")
        params.append(update.website)
        param_idx += 1

    if update.industry is not None:
        set_parts.append(f"industry = ${param_idx}")
        params.append(update.industry)
        param_idx += 1

    if update.domain_pattern is not None:
        set_parts.append(f"domain_pattern = ${param_idx}")
        params.append(update.domain_pattern)
        param_idx += 1

    if not set_parts:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Add updated_at
    set_parts.append("updated_at = NOW()")

    # Execute update
    params.append(client_id)
    query = f"""
        UPDATE clients
        SET {', '.join(set_parts)}
        WHERE id = ${param_idx}
        RETURNING id
    """
    result = await fetch_one(query, *params)

    if not result:
        raise HTTPException(status_code=404, detail="Client not found")

    # Return updated client
    return await get_client(client_id)


@router.delete("/{client_id}")
async def delete_client(client_id: UUID):
    """Delete a client"""
    result = await execute("DELETE FROM clients WHERE id = $1", client_id)

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Client not found")

    return {"message": "Client deleted successfully"}


@router.post("/{client_id}/link-workspace", response_model=Client)
async def link_workspace(client_id: UUID, request: LinkWorkspaceRequest):
    """Link a client to an OwnRBL workspace"""
    # Verify workspace exists
    workspace = await fetch_one("SELECT id FROM workspaces WHERE id = $1", request.workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Update client
    result = await fetch_one(
        "UPDATE clients SET workspace_id = $1, updated_at = NOW() WHERE id = $2 RETURNING id",
        request.workspace_id,
        client_id
    )

    if not result:
        raise HTTPException(status_code=404, detail="Client not found")

    return await get_client(client_id)


@router.post("/{client_id}/onboard", response_model=Client)
async def complete_onboarding(client_id: UUID, onboard: ClientOnboard):
    """Complete client onboarding"""
    # Update onboarding data and mark complete
    onboarding_json = json.dumps(onboard.onboarding_data.model_dump(by_alias=True))

    result = await fetch_one(
        """
        UPDATE clients
        SET onboarding_data = $1, onboarding_complete = true, updated_at = NOW()
        WHERE id = $2
        RETURNING id
        """,
        onboarding_json,
        client_id
    )

    if not result:
        raise HTTPException(status_code=404, detail="Client not found")

    return await get_client(client_id)


@router.post("/backfill/from-workspaces")
async def backfill_clients_from_workspaces():
    """
    Create client records for each workspace that doesn't have one.
    Each workspace should have exactly one corresponding client.
    """
    # Get all workspaces that don't have a client record
    query = """
        SELECT w.id, w.workspace_name
        FROM workspaces w
        LEFT JOIN clients c ON c.workspace_id = w.id
        WHERE c.id IS NULL
    """
    workspaces_without_clients = await fetch_all(query)

    created = []
    for workspace in workspaces_without_clients:
        # Create a client for this workspace
        result = await fetch_one(
            """
            INSERT INTO clients (name, workspace_id, onboarding_complete)
            VALUES ($1, $2, true)
            RETURNING id, name, workspace_id
            """,
            workspace["workspace_name"],
            workspace["id"]
        )
        if result:
            created.append(dict(result))

    # Also get count of existing clients that are already linked
    existing_count = await fetch_one(
        "SELECT COUNT(*) as count FROM clients WHERE workspace_id IS NOT NULL"
    )

    return {
        "message": f"Backfill complete",
        "created_count": len(created),
        "created_clients": created,
        "already_linked_count": existing_count["count"] if existing_count else 0
    }
