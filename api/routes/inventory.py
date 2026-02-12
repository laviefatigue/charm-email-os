"""
Inventory management routes - Pool status, lifecycle tracking, and auto-kill
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

import logging

from database import fetch_all, fetch_one, execute
from models.inventory import (
    InventoryOverview, InventoryInboxItem, InventoryInboxListResponse,
    AutoKillConfig, AutoKillConfigResponse,
    KillAndReplaceRequest, KillAndReplaceResponse,
    ProcessAutoKillsResponse,
    InventoryAuditEvent, InventoryAuditLogResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ===== OVERVIEW =====

@router.get("/overview/{client_id}", response_model=InventoryOverview)
async def get_inventory_overview(client_id: UUID):
    """Get inventory overview with pool/lifecycle distribution for a client"""

    # Get client's workspace
    client = await fetch_one("""
        SELECT c.id, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Client has no workspace linked")

    # Get feature flag
    flag = await fetch_one("""
        SELECT flag_value, config
        FROM feature_flags
        WHERE flag_name = 'AUTO_KILL_ENABLED'
        AND (workspace_id = $1 OR workspace_id IS NULL)
        ORDER BY workspace_id NULLS LAST
        LIMIT 1
    """, workspace_id)

    auto_kill_enabled = flag["flag_value"] if flag else False

    # Get inventory counts using the view
    counts = await fetch_one("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE calculated_pool_status = 'deployed') as deployed,
            COUNT(*) FILTER (WHERE calculated_pool_status = 'warning') as warning,
            COUNT(*) FILTER (WHERE calculated_pool_status = 'reserve') as reserve,
            COUNT(*) FILTER (WHERE calculated_lifecycle_status = 'active') as active,
            COUNT(*) FILTER (WHERE calculated_lifecycle_status = 'incubating') as incubating,
            COUNT(*) FILTER (WHERE calculated_lifecycle_status = 'dead') as dead
        FROM v_inbox_inventory_status
        WHERE workspace_id = $1
    """, workspace_id)

    if not counts:
        counts = {"total": 0, "deployed": 0, "warning": 0, "reserve": 0, "active": 0, "incubating": 0, "dead": 0}

    # Calculate targets (85% deployed, 15% reserve)
    total_live = counts["deployed"] + counts["warning"] + counts["reserve"]
    deployed_target = int(total_live * 0.85) if total_live > 0 else 0
    reserve_target = int(total_live * 0.15) if total_live > 0 else 0

    # Calculate spare capacity (reserve minus warning = actually available)
    spare_capacity = max(0, counts["reserve"] - counts["warning"])
    spare_percentage = (spare_capacity / deployed_target * 100) if deployed_target > 0 else 0

    # Determine capacity status
    if spare_percentage >= 20:
        capacity_status = "healthy"
    elif spare_percentage >= 10:
        capacity_status = "warning"
    else:
        capacity_status = "critical"

    return InventoryOverview(
        workspace_id=workspace_id,
        deployed_count=counts["deployed"],
        deployed_target=deployed_target,
        warning_count=counts["warning"],
        reserve_count=counts["reserve"],
        reserve_target=reserve_target,
        active_count=counts["active"],
        incubating_count=counts["incubating"],
        dead_count=counts["dead"],
        total_inboxes=counts["total"],
        spare_capacity=spare_capacity,
        spare_percentage=round(spare_percentage, 1),
        capacity_status=capacity_status,
        auto_kill_enabled=auto_kill_enabled,
        last_updated=datetime.now(timezone.utc)
    )


# ===== INBOX LIST =====

@router.get("/inboxes/{client_id}", response_model=InventoryInboxListResponse)
async def get_inventory_inboxes(
    client_id: UUID,
    pool_status: Optional[str] = Query(None, description="Filter by pool status: deployed, warning, reserve"),
    lifecycle_status: Optional[str] = Query(None, description="Filter by lifecycle: active, incubating, dead"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get inboxes with inventory status, optionally filtered"""

    # Get client's workspace
    client = await fetch_one("""
        SELECT c.id, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Client has no workspace linked")

    # Build query with filters
    where_clauses = ["workspace_id = $1"]
    params = [workspace_id]
    param_idx = 2

    if pool_status:
        where_clauses.append(f"calculated_pool_status = ${param_idx}")
        params.append(pool_status)
        param_idx += 1

    if lifecycle_status:
        where_clauses.append(f"calculated_lifecycle_status = ${param_idx}")
        params.append(lifecycle_status)
        param_idx += 1

    where_sql = " AND ".join(where_clauses)

    # Get total count
    count_result = await fetch_one(f"""
        SELECT COUNT(*) as total
        FROM v_inbox_inventory_status
        WHERE {where_sql}
    """, *params)
    total = count_result["total"] if count_result else 0

    # Get inbox list with warning info
    rows = await fetch_all(f"""
        SELECT
            v.id, v.email_address, v.workspace_id,
            v.calculated_pool_status, v.calculated_lifecycle_status,
            v.age_days, v.health_score, v.hard_bounces_24h, v.hard_bounces_7d,
            v.domain_name, v.associated_campaign_ids,
            sa.warning_reason, sa.cooldown_ends_at
        FROM v_inbox_inventory_status v
        JOIN sender_accounts sa ON sa.id = v.id
        WHERE {where_sql}
        ORDER BY
            CASE v.calculated_pool_status
                WHEN 'warning' THEN 1
                WHEN 'deployed' THEN 2
                ELSE 3
            END,
            v.hard_bounces_24h DESC NULLS LAST,
            v.health_score ASC NULLS LAST
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """, *params, limit, offset)

    # Build response items
    items = []
    for row in rows:
        # Get campaign names if any
        campaigns = []
        if row["associated_campaign_ids"]:
            camp_rows = await fetch_all("""
                SELECT campaign_name FROM emailbison_campaigns
                WHERE id = ANY($1)
            """, row["associated_campaign_ids"])
            campaigns = [c["campaign_name"] for c in camp_rows if c["campaign_name"]]

        items.append(InventoryInboxItem(
            inbox_id=row["id"],
            email=row["email_address"],
            domain_name=row["domain_name"] or "",
            pool_status=row["calculated_pool_status"],
            lifecycle_status=row["calculated_lifecycle_status"],
            age_days=row["age_days"] or 0,
            health_score=row["health_score"],
            hard_bounces_24h=row["hard_bounces_24h"] or 0,
            hard_bounces_7d=row["hard_bounces_7d"] or 0,
            associated_campaigns=campaigns,
            warning_reason=row["warning_reason"],
            cooldown_ends_at=row["cooldown_ends_at"]
        ))

    filter_desc = None
    if pool_status and lifecycle_status:
        filter_desc = f"{pool_status} + {lifecycle_status}"
    elif pool_status:
        filter_desc = pool_status
    elif lifecycle_status:
        filter_desc = lifecycle_status

    return InventoryInboxListResponse(
        items=items,
        total=total,
        filtered_by=filter_desc
    )


# ===== AUTO-KILL CONFIGURATION =====

@router.get("/auto-kill/config/{client_id}", response_model=AutoKillConfig)
async def get_auto_kill_config(client_id: UUID):
    """Get auto-kill configuration for a client"""

    # Get client's workspace
    client = await fetch_one("""
        SELECT c.id, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]

    # Get feature flag
    flag = await fetch_one("""
        SELECT flag_value, config
        FROM feature_flags
        WHERE flag_name = 'AUTO_KILL_ENABLED'
        AND (workspace_id = $1 OR workspace_id IS NULL)
        ORDER BY workspace_id NULLS LAST
        LIMIT 1
    """, workspace_id)

    if flag:
        config = flag["config"] or {}
        return AutoKillConfig(
            enabled=flag["flag_value"],
            cooldown_hours=config.get("cooldown_hours", 48),
            auto_replace=config.get("auto_replace", True),
            notify_on_kill=config.get("notify_on_kill", True)
        )

    return AutoKillConfig(enabled=False)


@router.post("/auto-kill/config/{client_id}", response_model=AutoKillConfigResponse)
async def set_auto_kill_config(client_id: UUID, config: AutoKillConfig):
    """Enable or disable auto-kill for a client's workspace"""

    # Get client's workspace
    client = await fetch_one("""
        SELECT c.id, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Client has no workspace linked")

    # Upsert feature flag
    await execute("""
        INSERT INTO feature_flags (workspace_id, client_id, flag_name, flag_value, config, updated_at)
        VALUES ($1, NULL, 'AUTO_KILL_ENABLED', $2, $3, NOW())
        ON CONFLICT (workspace_id, client_id, flag_name)
        DO UPDATE SET flag_value = $2, config = $3, updated_at = NOW()
    """, workspace_id, config.enabled, {
        "cooldown_hours": config.cooldown_hours,
        "auto_replace": config.auto_replace,
        "notify_on_kill": config.notify_on_kill
    })

    return AutoKillConfigResponse(
        success=True,
        message=f"Auto-kill {'enabled' if config.enabled else 'disabled'} for workspace",
        config=config
    )


# ===== KILL AND REPLACE =====

@router.post("/kill-and-replace", response_model=KillAndReplaceResponse)
async def kill_and_replace_inbox(request: KillAndReplaceRequest):
    """Kill an inbox and optionally replace it in associated campaigns"""

    # Get inbox details with campaigns
    inbox = await fetch_one("""
        SELECT
            sa.id, sa.email_address, sa.workspace_id, sa.inbox_state,
            sa.inventory_pool_status, sa.inventory_lifecycle_status
        FROM sender_accounts sa
        WHERE sa.id = $1
    """, request.inbox_id)

    if not inbox:
        raise HTTPException(status_code=404, detail="Inbox not found")

    if inbox["inbox_state"] == "dead":
        raise HTTPException(status_code=400, detail="Inbox is already dead")

    # Get active campaign associations
    campaigns = await fetch_all("""
        SELECT ci.emailbison_campaign_id, ec.id as campaign_uuid, ec.campaign_name
        FROM campaign_inboxes ci
        LEFT JOIN emailbison_campaigns ec ON ec.emailbison_campaign_id = ci.emailbison_campaign_id
        WHERE ci.sender_account_id = $1 AND ci.is_active = TRUE
    """, request.inbox_id)

    campaign_names = [c["campaign_name"] for c in campaigns if c["campaign_name"]]
    campaign_ids = [c["emailbison_campaign_id"] for c in campaigns]
    campaign_uuids = [c["campaign_uuid"] for c in campaigns if c["campaign_uuid"]]

    # Kill the inbox
    await execute("""
        UPDATE sender_accounts
        SET inbox_state = 'dead',
            killed_at = NOW(),
            kill_reason = $2,
            inventory_pool_status = NULL,
            inventory_lifecycle_status = 'dead',
            updated_at = NOW()
        WHERE id = $1
    """, request.inbox_id, request.kill_reason)

    # Deactivate from campaigns
    await execute("""
        UPDATE campaign_inboxes
        SET is_active = FALSE, removed_at = NOW()
        WHERE sender_account_id = $1
    """, request.inbox_id)

    replacement_id = None
    replacement_email = None

    # Find and assign replacement if requested
    if request.auto_replace and campaign_ids:
        # Find best replacement from reserve pool (active lifecycle, highest health)
        replacement = await fetch_one("""
            SELECT id, email_address
            FROM v_inbox_inventory_status
            WHERE workspace_id = $1
            AND calculated_pool_status = 'reserve'
            AND calculated_lifecycle_status = 'active'
            AND id != $2
            ORDER BY health_score DESC NULLS LAST, age_days DESC
            LIMIT 1
        """, inbox["workspace_id"], request.inbox_id)

        if replacement:
            replacement_id = replacement["id"]
            replacement_email = replacement["email_address"]

            # Assign replacement to all affected campaigns
            for camp_id in campaign_ids:
                # Get sender ID for the replacement inbox
                sender = await fetch_one("""
                    SELECT emailbison_account_id FROM sender_accounts WHERE id = $1
                """, replacement_id)
                sender_id = int(sender["emailbison_account_id"]) if sender and sender["emailbison_account_id"] else 0

                await execute("""
                    INSERT INTO campaign_inboxes (
                        sender_account_id, emailbison_campaign_id, emailbison_sender_id,
                        assigned_at, is_active
                    ) VALUES ($1, $2, $3, NOW(), TRUE)
                    ON CONFLICT (emailbison_campaign_id, emailbison_sender_id) DO NOTHING
                """, replacement_id, camp_id, sender_id)

    # Log to audit
    await execute("""
        INSERT INTO inventory_audit_log (
            workspace_id, inbox_id, inbox_email, event_type,
            previous_pool_status, new_pool_status,
            previous_lifecycle_status, new_lifecycle_status,
            reason, triggered_by, related_campaign_ids,
            replacement_for_inbox_id, metadata
        ) VALUES ($1, $2, $3, 'manual_kill', $4, NULL, $5, 'dead', $6, 'manual', $7, $8, $9)
    """,
        inbox["workspace_id"],
        request.inbox_id,
        inbox["email_address"],
        inbox["inventory_pool_status"],
        inbox["inventory_lifecycle_status"],
        request.kill_reason,
        campaign_uuids,
        replacement_id,
        {"replacement_email": replacement_email} if replacement_email else {}
    )

    return KillAndReplaceResponse(
        killed_inbox_id=request.inbox_id,
        killed_inbox_email=inbox["email_address"],
        affected_campaigns=campaign_names,
        replacement_inbox_id=replacement_id,
        replacement_inbox_email=replacement_email,
        success=True,
        message=f"Killed {inbox['email_address']}" +
                (f", replaced with {replacement_email}" if replacement_email else
                 ", no replacement available" if request.auto_replace and campaign_ids else "")
    )


# ===== PROCESS AUTO-KILLS =====

@router.post("/process-auto-kills/{client_id}", response_model=ProcessAutoKillsResponse)
async def process_auto_kills(client_id: UUID, background_tasks: BackgroundTasks):
    """Process all pending instant kill triggers if auto-kill is enabled"""

    # Get client's workspace
    client = await fetch_one("""
        SELECT c.id, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Client has no workspace linked")

    # Check feature flag
    flag = await fetch_one("""
        SELECT flag_value, config
        FROM feature_flags
        WHERE flag_name = 'AUTO_KILL_ENABLED'
        AND (workspace_id = $1 OR workspace_id IS NULL)
        ORDER BY workspace_id NULLS LAST
        LIMIT 1
    """, workspace_id)

    if not flag or not flag["flag_value"]:
        return ProcessAutoKillsResponse(
            processed=0,
            message="Auto-kill is disabled for this workspace"
        )

    config = flag["config"] or {}
    auto_replace = config.get("auto_replace", True)

    # Get pending instant triggers (with 5 min buffer for manual review)
    triggers = await fetch_all("""
        SELECT *
        FROM kill_trigger_events
        WHERE workspace_id = $1
        AND action_taken = 'pending'
        AND severity = 'instant'
        AND detected_at <= NOW() - INTERVAL '5 minutes'
        ORDER BY detected_at ASC
        LIMIT 50
    """, workspace_id)

    processed = 0
    details = []

    for trigger in triggers:
        try:
            # Process kill and replace
            response = await kill_and_replace_inbox(
                KillAndReplaceRequest(
                    inbox_id=trigger["inbox_id"],
                    kill_reason=f"Auto-kill: {trigger['trigger_type']}",
                    auto_replace=auto_replace
                )
            )

            # Mark trigger as processed
            await execute("""
                UPDATE kill_trigger_events
                SET action_taken = 'killed',
                    resolved_at = NOW(),
                    resolved_by = 'system',
                    auto_killed = TRUE,
                    replacement_inbox_id = $2
                WHERE id = $1
            """, trigger["id"], response.replacement_inbox_id)

            processed += 1
            details.append({
                "inbox": trigger["inbox_email"],
                "trigger": trigger["trigger_type"],
                "replacement": response.replacement_inbox_email
            })

        except Exception as e:
            logger.error(f"Failed to auto-kill inbox {trigger['inbox_id']}: {e}")
            details.append({
                "inbox": trigger["inbox_email"],
                "trigger": trigger["trigger_type"],
                "error": str(e)
            })

    return ProcessAutoKillsResponse(
        processed=processed,
        message=f"Auto-killed {processed} inbox(es)",
        details=details
    )


# ===== AUDIT LOG =====

@router.get("/audit-log/{client_id}", response_model=InventoryAuditLogResponse)
async def get_inventory_audit_log(
    client_id: UUID,
    event_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """Get inventory audit log for a client"""

    # Get client's workspace
    client = await fetch_one("""
        SELECT c.id, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Client has no workspace linked")

    # Build query
    where_clauses = ["workspace_id = $1"]
    params = [workspace_id]
    param_idx = 2

    if event_type:
        where_clauses.append(f"event_type = ${param_idx}")
        params.append(event_type)
        param_idx += 1

    where_sql = " AND ".join(where_clauses)

    # Get total count
    count_result = await fetch_one(f"""
        SELECT COUNT(*) as total
        FROM inventory_audit_log
        WHERE {where_sql}
    """, *params)
    total = count_result["total"] if count_result else 0

    # Get audit events
    rows = await fetch_all(f"""
        SELECT *
        FROM inventory_audit_log
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """, *params, limit, offset)

    items = [
        InventoryAuditEvent(
            id=row["id"],
            workspace_id=row["workspace_id"],
            inbox_id=row["inbox_id"],
            inbox_email=row["inbox_email"],
            event_type=row["event_type"],
            previous_pool_status=row["previous_pool_status"],
            new_pool_status=row["new_pool_status"],
            previous_lifecycle_status=row["previous_lifecycle_status"],
            new_lifecycle_status=row["new_lifecycle_status"],
            reason=row["reason"],
            triggered_by=row["triggered_by"],
            related_campaign_ids=row["related_campaign_ids"],
            created_at=row["created_at"]
        )
        for row in rows
    ]

    return InventoryAuditLogResponse(items=items, total=total)
