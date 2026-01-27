"""
Client routes - CRUD for the new clients table
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
import json
import logging
import httpx
import os

from database import fetch_all, fetch_one, execute
from models.client import (
    Client, ClientCreate, ClientUpdate, ClientOnboard,
    ClientList, LinkWorkspaceRequest, SenderName, SenderNamePreferences,
    BaseName, SenderNameVariation, GenerateVariationsRequest, SaveSenderNamesRequest,
    SetBaseNameRequest
)
from data.sender_names import (
    FIRST_NAMES_POOL, LAST_NAMES_POOL,
    generate_email_prefix as _generate_email_prefix,
    generate_random_names as _generate_random_names,
)
from data.client_name_strategies import get_strategy, get_founder_name
from data.name_variations import (
    generate_variations,
    generate_all_prefixes,
    get_available_patterns,
    get_patterns_for_provider,
    PATTERN_TEMPLATES_52,
    TIER_1_PATTERNS,
    ALL_PATTERNS_RANKED,
)
import random

router = APIRouter()
logger = logging.getLogger(__name__)

# EmailBison API configuration
EMAILBISON_API_URL = os.getenv("EMAILBISON_API_URL", "https://spellcast.hirecharm.com")
EMAILBISON_API_KEY = os.getenv("EMAILBISON_API_KEY", "")


async def create_emailbison_workspace(workspace_name: str) -> Optional[int]:
    """
    Create a new workspace in EmailBison and return its ID.

    Args:
        workspace_name: Name for the new workspace

    Returns:
        EmailBison workspace ID if successful, None otherwise
    """
    if not EMAILBISON_API_KEY:
        logger.warning("EMAILBISON_API_KEY not configured, skipping workspace creation")
        return None

    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                f"{EMAILBISON_API_URL}/api/workspaces",
                headers={
                    "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"name": workspace_name},
                timeout=30.0
            )

            if response.status_code in (200, 201):
                data = response.json()
                eb_workspace_id = data.get("data", {}).get("id")
                logger.info(f"Created EmailBison workspace '{workspace_name}' with ID {eb_workspace_id}")
                return eb_workspace_id
            else:
                logger.error(f"Failed to create EmailBison workspace: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        logger.error(f"Error creating EmailBison workspace: {e}")
        return None


async def create_local_workspace(workspace_name: str, emailbison_workspace_id: int) -> Optional[UUID]:
    """
    Create a workspace record in the local database.

    Args:
        workspace_name: Name for the workspace
        emailbison_workspace_id: EmailBison workspace ID

    Returns:
        Local workspace UUID if successful, None otherwise
    """
    try:
        # Note: instance_id is required. We copy it from an existing workspace
        # since all workspaces belong to the same OwnRBL instance.
        result = await fetch_one("""
            INSERT INTO workspaces (instance_id, workspace_name, emailbison_workspace_id, automation_enabled)
            SELECT instance_id, $1, $2, true FROM workspaces LIMIT 1
            RETURNING id
        """, workspace_name, emailbison_workspace_id)

        if result:
            logger.info(f"Created local workspace '{workspace_name}' with ID {result['id']}")
            return result["id"]
        return None

    except Exception as e:
        logger.error(f"Error creating local workspace: {e}")
        return None


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
    """
    Create a new client.

    If workspace_id is not provided, automatically creates:
    1. A new workspace in EmailBison with the client's name
    2. A corresponding workspace record in the local database
    3. Links the client to this workspace
    """
    # Convert onboarding_data to JSON if provided
    onboarding_json = None
    if client.onboarding_data:
        onboarding_json = json.dumps(client.onboarding_data.model_dump(by_alias=True))

    # Auto-create workspace if not provided
    workspace_id = client.workspace_id
    workspace_name = None

    if not workspace_id:
        logger.info(f"Auto-creating workspace for client '{client.name}'")

        # 1. Create workspace in EmailBison
        eb_workspace_id = await create_emailbison_workspace(client.name)

        if eb_workspace_id:
            # 2. Create local workspace record
            workspace_id = await create_local_workspace(client.name, eb_workspace_id)

            if workspace_id:
                workspace_name = client.name
                logger.info(f"Auto-created workspace '{client.name}' (local: {workspace_id}, EmailBison: {eb_workspace_id})")
            else:
                logger.warning(f"Failed to create local workspace for '{client.name}', client will be created without workspace")
        else:
            logger.warning(f"Failed to create EmailBison workspace for '{client.name}', client will be created without workspace")

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
        workspace_id,
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

    # Get workspace name if linked (in case workspace_id was provided)
    if row["workspace_id"] and not workspace_name:
        ws = await fetch_one("SELECT workspace_name FROM workspaces WHERE id = $1", row["workspace_id"])
        workspace_name = ws["workspace_name"] if ws else None

    return Client(
        **row,
        workspace_name=workspace_name,
        inbox_count=0,
        domain_count=0,
        campaign_count=0
    )


# ============================================
# Static Routes (MUST be before /{client_id} routes)
# ============================================

@router.get("/name-patterns")
async def get_name_patterns(provider: Optional[str] = None):
    """
    Get available name variation patterns.

    Args:
        provider: Optional filter by provider ("entra" or "google")

    Returns list of patterns with descriptions, examples, and tier info.
    Used by the frontend to populate pattern checkboxes.

    Provider-specific behavior:
    - entra: Returns all 52 patterns (full domain coverage)
    - google: Returns top 10 patterns (tier 1 only)
    """
    patterns = get_available_patterns(provider=provider)

    return {
        "patterns": patterns,
        "total_count": len(patterns),
        "default_patterns": get_patterns_for_provider(provider or "google", 10),
        "provider": provider,
        "provider_limits": {
            "entra": 52,
            "google": 10,
        },
    }


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


@router.post("/{client_id}/create-workspace", response_model=Client)
async def create_workspace_for_client(client_id: UUID):
    """
    Create a new workspace for an existing client.

    This endpoint:
    1. Creates a workspace in EmailBison with the client's name
    2. Creates a corresponding local workspace record
    3. Links the client to the new workspace

    Use this for clients that were created without a workspace.
    """
    # Get client
    client = await fetch_one("SELECT id, name, workspace_id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client already has a workspace")

    client_name = client["name"]

    # 1. Create workspace in EmailBison
    eb_workspace_id = await create_emailbison_workspace(client_name)
    if not eb_workspace_id:
        raise HTTPException(
            status_code=500,
            detail="Failed to create workspace in EmailBison. Check API key configuration."
        )

    # 2. Create local workspace record
    workspace_id = await create_local_workspace(client_name, eb_workspace_id)
    if not workspace_id:
        raise HTTPException(
            status_code=500,
            detail=f"Created EmailBison workspace (ID: {eb_workspace_id}) but failed to create local record"
        )

    # 3. Link client to workspace
    await execute(
        "UPDATE clients SET workspace_id = $1, updated_at = NOW() WHERE id = $2",
        workspace_id,
        client_id
    )

    logger.info(f"Created and linked workspace '{client_name}' for client {client_id} (local: {workspace_id}, EmailBison: {eb_workspace_id})")

    return await get_client(client_id)


@router.post("/{client_id}/link-workspace", response_model=Client)
async def link_workspace(client_id: UUID, request: LinkWorkspaceRequest):
    """Link a client to an existing OwnRBL workspace"""
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


class ImportWorkspaceRequest(BaseModel):
    """Request to import an existing EmailBison workspace"""
    emailbison_workspace_id: int
    workspace_name: Optional[str] = None


@router.post("/{client_id}/import-workspace", response_model=Client)
async def import_emailbison_workspace(client_id: UUID, request: ImportWorkspaceRequest):
    """
    Import an existing EmailBison workspace and link it to the client.

    Use this when an EmailBison workspace was created externally or when
    recovering from a partial workspace creation.
    """
    # Verify client exists and has no workspace
    client = await fetch_one("SELECT id, name, workspace_id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client already has a workspace")

    # Check if this EmailBison workspace is already imported
    # Note: emailbison_workspace_id is stored as VARCHAR in the database
    eb_workspace_id_str = str(request.emailbison_workspace_id)
    existing = await fetch_one(
        "SELECT id, workspace_name FROM workspaces WHERE emailbison_workspace_id = $1",
        eb_workspace_id_str
    )

    if existing:
        workspace_id = existing["id"]
        logger.info(f"Using existing local workspace for EmailBison ID {request.emailbison_workspace_id}")
    else:
        # Create local workspace record
        # Note: instance_id is required. We copy it from an existing workspace.
        workspace_name = request.workspace_name or client["name"]
        result = await fetch_one("""
            INSERT INTO workspaces (instance_id, workspace_name, emailbison_workspace_id, automation_enabled)
            SELECT instance_id, $1, $2, true FROM workspaces LIMIT 1
            RETURNING id
        """, workspace_name, eb_workspace_id_str)

        if not result:
            raise HTTPException(status_code=500, detail="Failed to create local workspace record")

        workspace_id = result["id"]
        logger.info(f"Created local workspace '{workspace_name}' for EmailBison ID {request.emailbison_workspace_id}")

    # Link client to workspace
    await execute(
        "UPDATE clients SET workspace_id = $1, updated_at = NOW() WHERE id = $2",
        workspace_id,
        client_id
    )

    logger.info(f"Linked client {client_id} to workspace {workspace_id}")

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


# Use expanded name pools from data module (50+ names each)
FIRST_NAMES = FIRST_NAMES_POOL
LAST_NAMES = LAST_NAMES_POOL


def generate_email_prefix(first_name: str, last_name: str) -> str:
    """Generate email prefix from name (e.g., 'John Smith' -> 'john.smith')"""
    return f"{first_name.lower()}.{last_name.lower()}"


def generate_random_sender_names(count: int = 10) -> list[dict]:
    """Generate random sender names for inbox provisioning"""
    names = []
    used_prefixes = set()
    target_count = min(count, 10)  # Hypertide max is 10

    while len(names) < target_count:
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        email_prefix = generate_email_prefix(first_name, last_name)

        if email_prefix not in used_prefixes:
            used_prefixes.add(email_prefix)
            names.append({
                "firstName": first_name,
                "lastName": last_name,
                "emailPrefix": email_prefix,
                "source": "generated",
            })

    return names


def personas_to_sender_names(personas: list[dict], max_count: int = 10) -> list[dict]:
    """Convert onboarding personas to sender names"""
    names = []
    used_prefixes = set()

    for persona in personas:
        if len(names) >= max_count:
            break

        # Extract first name from persona
        first_name = persona.get("firstName") or persona.get("first_name")
        if not first_name and persona.get("name"):
            parts = persona["name"].split(" ")
            first_name = parts[0]
        if not first_name and persona.get("jobTitle") or persona.get("job_title"):
            # Use random name if only job title provided
            first_name = random.choice(FIRST_NAMES)

        if not first_name:
            continue

        # Get or generate last name
        last_name = persona.get("lastName") or persona.get("last_name")
        if not last_name and persona.get("name"):
            parts = persona["name"].split(" ")
            last_name = parts[-1] if len(parts) > 1 else None
        if not last_name:
            last_name = random.choice(LAST_NAMES)

        email_prefix = generate_email_prefix(first_name, last_name)

        if email_prefix not in used_prefixes:
            used_prefixes.add(email_prefix)
            names.append({
                "firstName": first_name,
                "lastName": last_name,
                "emailPrefix": email_prefix,
                "source": "persona",
            })

    return names


class GenerateSenderNamesRequest(BaseModel):
    """Request to generate sender names"""
    count: int = 10
    use_personas: bool = True
    use_client_strategy: bool = True  # Apply client-specific strategy (founder name, etc.)
    custom_names: Optional[list[SenderName]] = None


class GenerateSenderNamesResponse(BaseModel):
    """Response with generated sender names"""
    names: list[dict]
    total_count: int
    from_founder: int = 0
    from_personas: int
    from_custom: int
    from_generated: int
    strategy_applied: Optional[str] = None


@router.post("/{client_id}/generate-sender-names", response_model=GenerateSenderNamesResponse)
async def generate_sender_names(client_id: UUID, request: GenerateSenderNamesRequest):
    """
    Generate sender names for a client and save to their onboarding data.

    Names are generated based on:
    1. Client strategy (founder name first, if configured)
    2. Custom names if provided
    3. Personas from onboarding data (if use_personas=true)
    4. Random generation to fill remaining slots (from 50+ name pool)

    Hypertide allows max 10 names per order, and names are reused across domains.
    """
    # Get client with onboarding data
    client = await fetch_one(
        "SELECT id, name, onboarding_data FROM clients WHERE id = $1",
        client_id
    )

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    target_count = min(request.count, 10)  # Hypertide max
    names = []
    used_prefixes = set()
    from_founder = 0
    from_personas = 0
    from_custom = 0
    from_generated = 0
    strategy_applied = None

    def add_name(name: dict) -> bool:
        nonlocal from_founder, from_personas, from_custom, from_generated
        prefix = name.get("emailPrefix")
        if prefix not in used_prefixes and len(names) < target_count:
            used_prefixes.add(prefix)
            names.append(name)
            source = name.get("source", "generated")
            if source == "founder":
                from_founder += 1
            elif source == "persona":
                from_personas += 1
            elif source == "custom":
                from_custom += 1
            else:
                from_generated += 1
            return True
        return False

    # 0. Apply client strategy (founder name first)
    if request.use_client_strategy:
        client_name = client.get("name", "")
        strategy = get_strategy(client_name=client_name)
        if strategy.get("include_founder"):
            founder = get_founder_name(strategy)
            if founder:
                add_name(founder)
                strategy_applied = client_name.lower() if client_name else None
                logger.info(f"Applied founder name for client '{client_name}': {founder['emailPrefix']}")

    # 1. Use custom names if provided
    if request.custom_names:
        for custom in request.custom_names:
            add_name({
                "firstName": custom.first_name,
                "lastName": custom.last_name,
                "emailPrefix": custom.email_prefix,
                "source": "custom",
            })

    # 2. Use personas if enabled
    if request.use_personas:
        onboarding_data = client.get("onboarding_data")
        if onboarding_data:
            if isinstance(onboarding_data, str):
                onboarding_data = json.loads(onboarding_data)

            personas = onboarding_data.get("personas", [])
            if personas:
                persona_names = personas_to_sender_names(personas, target_count)
                for name in persona_names:
                    add_name(name)

    # 3. Fill remaining with random names (using expanded 50+ name pool)
    if len(names) < target_count:
        random_names = generate_random_sender_names(target_count - len(names))
        for name in random_names:
            add_name(name)

    # Save to client's onboarding_data
    onboarding_data = client.get("onboarding_data")
    if isinstance(onboarding_data, str):
        onboarding_data = json.loads(onboarding_data)
    elif onboarding_data is None:
        onboarding_data = {}

    onboarding_data["preGeneratedSenderNames"] = names
    onboarding_data["senderNamePreferences"] = {
        "usePersonas": request.use_personas,
        "nameCount": target_count,
    }
    if request.custom_names:
        onboarding_data["senderNamePreferences"]["customNames"] = [
            {
                "firstName": n.first_name,
                "lastName": n.last_name,
                "emailPrefix": n.email_prefix,
                "source": "custom",
            }
            for n in request.custom_names
        ]

    await execute(
        """
        UPDATE clients
        SET onboarding_data = $1, updated_at = NOW()
        WHERE id = $2
        """,
        json.dumps(onboarding_data),
        client_id
    )

    logger.info(f"Generated {len(names)} sender names for client {client_id} "
                f"(founder: {from_founder}, personas: {from_personas}, custom: {from_custom}, generated: {from_generated})")

    return GenerateSenderNamesResponse(
        names=names,
        total_count=len(names),
        from_founder=from_founder,
        from_personas=from_personas,
        from_custom=from_custom,
        from_generated=from_generated,
        strategy_applied=strategy_applied,
    )


@router.get("/{client_id}/sender-names")
async def get_sender_names(client_id: UUID):
    """
    Get the pre-generated sender names for a client.

    Returns the names from onboarding_data.preGeneratedSenderNames.
    """
    client = await fetch_one(
        "SELECT id, onboarding_data FROM clients WHERE id = $1",
        client_id
    )

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    onboarding_data = client.get("onboarding_data")
    if isinstance(onboarding_data, str):
        onboarding_data = json.loads(onboarding_data)

    names = []
    preferences = None

    if onboarding_data:
        names = onboarding_data.get("preGeneratedSenderNames", [])
        preferences = onboarding_data.get("senderNamePreferences")

    return {
        "names": names,
        "count": len(names),
        "preferences": preferences,
    }


# ============================================
# Name Variation Endpoints (Phase 6A.5)
# ============================================

@router.post("/{client_id}/generate-name-variations")
async def generate_name_variations(client_id: UUID, request: GenerateVariationsRequest):
    """
    Generate email prefix variations from base names.

    Base names are the real identities (1-2 names like "Chris Booth").
    Variations are different email prefix formats generated from those names.

    Provider-specific behavior:
    - entra (Microsoft): Up to 52 variations using all pattern tiers
    - google: Up to 10 variations using tier 1 patterns only

    Example for base name "Chris Booth" with provider="entra":
    - chris.booth (firstname.lastname)
    - chris (firstname)
    - c.booth (f.lastname)
    - chrisbooth (firstnamelastname)
    - ... up to 52 variations
    """
    # Verify client exists
    client = await fetch_one("SELECT id, name FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Convert Pydantic models to dicts for the variation generator
    base_names_dicts = [
        {
            "firstName": bn.first_name,
            "lastName": bn.last_name,
            "isFounder": bn.is_founder,
        }
        for bn in request.base_names
    ]

    # Generate variations with provider-aware patterns
    variations = generate_variations(
        base_names=base_names_dicts,
        patterns=request.patterns,
        count=request.count,
        provider=request.provider,
    )

    # Determine which patterns were used
    patterns_used = request.patterns if request.patterns else get_patterns_for_provider(request.provider, request.count)

    logger.info(f"Generated {len(variations)} name variations for client {client_id} (provider: {request.provider})")

    return {
        "variations": variations,
        "count": len(variations),
        "patterns_used": patterns_used,
        "base_names": base_names_dicts,
        "provider": request.provider,
        "max_for_provider": 52 if request.provider == "entra" else 10,
    }


@router.put("/{client_id}/sender-names")
async def save_sender_names(client_id: UUID, request: SaveSenderNamesRequest):
    """
    Save sender names (base names + variations) to client profile.

    This saves:
    - baseSenderNames: The original names (1-2 identities)
    - variationPatterns: Which patterns were used to generate variations
    - preGeneratedSenderNames: The generated variations ready for Hypertide

    These are stored in onboarding_data JSONB column.
    """
    # Get client
    client = await fetch_one(
        "SELECT id, onboarding_data FROM clients WHERE id = $1",
        client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Parse existing onboarding data
    onboarding_data = client.get("onboarding_data")
    if isinstance(onboarding_data, str):
        onboarding_data = json.loads(onboarding_data)
    elif onboarding_data is None:
        onboarding_data = {}

    # Convert base names to serializable dicts
    base_names_data = [
        {
            "firstName": bn.first_name,
            "lastName": bn.last_name,
            "isFounder": bn.is_founder,
        }
        for bn in request.base_names
    ]

    # Convert variations to SenderName format for compatibility with existing code
    pre_generated_names = [
        {
            "firstName": v.first_name,
            "lastName": v.last_name,
            "emailPrefix": v.email_prefix,
            "source": "founder" if v.is_founder else "generated",
        }
        for v in request.variations
    ]

    # Update onboarding data
    onboarding_data["baseSenderNames"] = base_names_data
    onboarding_data["variationPatterns"] = request.patterns
    onboarding_data["preGeneratedSenderNames"] = pre_generated_names
    onboarding_data["senderNamePreferences"] = {
        "usePersonas": False,  # Not using personas when using variations
        "nameCount": len(request.variations),
        "provider": request.provider,
    }

    # Save to database
    await execute(
        """
        UPDATE clients
        SET onboarding_data = $1, updated_at = NOW()
        WHERE id = $2
        """,
        json.dumps(onboarding_data),
        client_id
    )

    logger.info(f"Saved {len(request.variations)} sender name variations for client {client_id}")

    # Return updated client
    return await get_client(client_id)


@router.get("/{client_id}/sender-name-config")
async def get_sender_name_config(client_id: UUID):
    """
    Get the full sender name configuration for a client.

    Returns:
    - baseNames: The original names (seeds)
    - patterns: Which variation patterns are enabled
    - variations: Generated variations
    - hasConfig: Whether names have been configured
    """
    client = await fetch_one(
        "SELECT id, onboarding_data FROM clients WHERE id = $1",
        client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    onboarding_data = client.get("onboarding_data")
    if isinstance(onboarding_data, str):
        onboarding_data = json.loads(onboarding_data)

    base_names = []
    patterns = ["firstname.lastname", "f.lastname", "firstnamelastname", "firstname.l", "flastname"]
    variations = []
    has_config = False

    if onboarding_data:
        base_names = onboarding_data.get("baseSenderNames", [])
        patterns = onboarding_data.get("variationPatterns", patterns)
        variations = onboarding_data.get("preGeneratedSenderNames", [])
        has_config = bool(base_names)

    # Get provider from preferences if set
    preferences = onboarding_data.get("senderNamePreferences", {}) if onboarding_data else {}
    provider = preferences.get("provider", "google")

    return {
        "baseNames": base_names,
        "patterns": patterns,
        "variations": variations,
        "hasConfig": has_config,
        "provider": provider,
        "availablePatterns": get_available_patterns(provider=provider),
        "providerLimits": {
            "entra": 52,
            "google": 10,
        },
    }


@router.get("/{client_id}/sender-names-for-provisioning")
async def get_sender_names_for_provisioning(client_id: UUID):
    """
    Get sender names formatted for inbox provisioning.

    Returns sender names with full prefix lists and metadata needed for
    the Hypertide order flow. Each sender name includes:
    - Base name (first/last)
    - All prefixes generated for that name
    - Counts for Entra (50 usable) and Google (3 usable)

    Also returns:
    - forwardingDomain: Client's primary domain for Hypertide configuration
    - emailbisonWorkspaceId: Workspace ID for inbox upload

    These prefixes become InboxConfigs sent to Hypertide:
    - Entra: Uses top 50 prefixes (out of 52 generated)
    - Google: Uses top 3 prefixes (out of 10 generated)
    """
    # Fetch client with workspace join to get EmailBison ID
    client = await fetch_one(
        """
        SELECT c.id, c.name, c.onboarding_data, c.workspace_id,
               w.emailbison_workspace_id, w.workspace_name
        FROM clients c
        LEFT JOIN workspaces w ON c.workspace_id = w.id
        WHERE c.id = $1
        """,
        client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    onboarding_data = client.get("onboarding_data")
    if isinstance(onboarding_data, str):
        onboarding_data = json.loads(onboarding_data)

    sender_names = []

    if onboarding_data:
        base_names = onboarding_data.get("baseSenderNames", [])
        pre_generated = onboarding_data.get("preGeneratedSenderNames", [])
        provider = onboarding_data.get("senderNamePreferences", {}).get("provider", "entra")

        # Group prefixes by base name
        # For now, we assume one base name = one set of prefixes
        for i, base_name in enumerate(base_names):
            first_name = base_name.get("firstName", "")
            last_name = base_name.get("lastName", "")
            is_founder = base_name.get("isFounder", i == 0)

            # Get all prefixes for this base name
            prefixes = [p.get("emailPrefix") for p in pre_generated if p.get("emailPrefix")]

            # Calculate usable counts for each provider
            # Hypertide constraints:
            # - Entra: 50 inboxes per domain (use top 50 prefixes)
            # - Google: 3 inboxes per domain (use top 3 prefixes)
            entra_prefixes = prefixes[:50]  # Top 50 for Entra
            google_prefixes = prefixes[:3]   # Top 3 for Google

            sender_names.append({
                "id": f"name-{i}",
                "firstName": first_name,
                "lastName": last_name,
                "isFounder": is_founder,
                "prefixes": prefixes,
                "totalPrefixCount": len(prefixes),
                "entraPrefixCount": len(entra_prefixes),
                "googlePrefixCount": len(google_prefixes),
                "entraPrefixes": entra_prefixes,
                "googlePrefixes": google_prefixes,
                "provider": provider,
                "createdAt": base_name.get("createdAt"),
            })

    # Extract forwarding domain from onboarding data
    forwarding_domain = None
    if onboarding_data:
        forwarding_domain = onboarding_data.get("primaryDomain")

    return {
        "clientId": str(client_id),
        "clientName": client.get("name"),
        "forwardingDomain": forwarding_domain,
        "emailbisonWorkspaceId": client.get("emailbison_workspace_id"),
        "workspaceId": str(client.get("workspace_id")) if client.get("workspace_id") else None,
        "senderNames": sender_names,
        "totalNames": len(sender_names),
        "hypertideConstraints": {
            "entra": {
                "domainsPerOrder": 2,
                "inboxesPerDomain": 50,
                "inboxesPerOrder": 100,
            },
            "google": {
                "domainsPerOrder": 5,
                "inboxesPerDomain": 3,
                "inboxesPerOrder": 15,
            }
        }
    }


@router.post("/{client_id}/set-sender-name")
async def set_sender_name(client_id: UUID, request: SetBaseNameRequest):
    """
    Simplified endpoint: Set base sender name and auto-generate all prefixes.

    Just provide first/last name and provider. The system automatically generates
    all email prefixes using the 52-pattern template system (for Entra) or
    top 10 patterns (for Google).

    No manual pattern selection or approval needed.

    Example:
        POST /clients/{id}/set-sender-name
        {
            "firstName": "Chris",
            "lastName": "Booth",
            "provider": "entra"
        }

    This will auto-generate 52 email prefixes like:
        chris.booth, chris, c.booth, chrisbooth, chris.b, ...
    """
    # Verify client exists
    client = await fetch_one(
        "SELECT id, onboarding_data FROM clients WHERE id = $1",
        client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Parse existing onboarding data
    onboarding_data = client.get("onboarding_data")
    if isinstance(onboarding_data, str):
        onboarding_data = json.loads(onboarding_data)
    elif onboarding_data is None:
        onboarding_data = {}

    # Generate all prefixes for this name
    prefixes = generate_all_prefixes(
        request.first_name,
        request.last_name,
        request.provider
    )

    # Build base name data
    base_name_data = {
        "firstName": request.first_name,
        "lastName": request.last_name,
        "isFounder": request.is_founder,
    }

    # Build pre-generated sender names from prefixes
    pre_generated_names = [
        {
            "firstName": request.first_name,
            "lastName": request.last_name,
            "emailPrefix": prefix,
            "source": "generated",
        }
        for prefix in prefixes
    ]

    # Get patterns used
    patterns_used = get_patterns_for_provider(request.provider)

    # Update onboarding data
    onboarding_data["baseSenderNames"] = [base_name_data]
    onboarding_data["variationPatterns"] = patterns_used
    onboarding_data["preGeneratedSenderNames"] = pre_generated_names
    onboarding_data["senderNamePreferences"] = {
        "usePersonas": False,
        "nameCount": len(prefixes),
        "provider": request.provider,
    }

    # Save to database
    await execute(
        """
        UPDATE clients
        SET onboarding_data = $1, updated_at = NOW()
        WHERE id = $2
        """,
        json.dumps(onboarding_data),
        client_id
    )

    logger.info(f"Set sender name for client {client_id}: {request.first_name} {request.last_name} ({request.provider}, {len(prefixes)} prefixes)")

    return {
        "success": True,
        "baseName": base_name_data,
        "prefixCount": len(prefixes),
        "prefixes": prefixes,
        "provider": request.provider,
        "patterns": patterns_used,
    }


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
