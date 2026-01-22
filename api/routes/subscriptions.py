"""
Subscription routes - Client package and quota management
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
import logging

from database import fetch_all, fetch_one, execute
from models.subscription import (
    PackageTemplate,
    Subscription,
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionWithUsage,
    SubscriptionChange,
    ApplyTemplateRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Package Templates
# =============================================================================

@router.get("/templates", response_model=list[PackageTemplate])
async def list_package_templates(active_only: bool = Query(True)):
    """List available package templates"""
    query = """
        SELECT id, name,
               entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
               google_packages, google_domains_per_package, google_inboxes_per_domain,
               total_domains, total_inboxes,
               monthly_price, is_active, created_at
        FROM package_templates
        WHERE ($1 = false OR is_active = true)
        ORDER BY total_inboxes ASC
    """
    rows = await fetch_all(query, active_only)
    return [PackageTemplate(**row) for row in rows]


@router.get("/templates/{template_id}", response_model=PackageTemplate)
async def get_package_template(template_id: UUID):
    """Get a specific package template"""
    query = """
        SELECT id, name,
               entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
               google_packages, google_domains_per_package, google_inboxes_per_domain,
               total_domains, total_inboxes,
               monthly_price, is_active, created_at
        FROM package_templates
        WHERE id = $1
    """
    row = await fetch_one(query, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Package template not found")
    return PackageTemplate(**row)


# =============================================================================
# Client Subscriptions
# =============================================================================

@router.get("/client/{client_id}", response_model=Optional[SubscriptionWithUsage])
async def get_client_subscription(client_id: UUID):
    """Get active subscription for a client with current usage statistics"""
    # Get subscription
    sub_query = """
        SELECT
            s.id, s.client_id, s.package_template_id,
            pt.name as package_template_name,
            s.entra_packages, s.entra_domains_per_package, s.entra_inboxes_per_domain,
            s.google_packages, s.google_domains_per_package, s.google_inboxes_per_domain,
            s.spare_ratio, s.status, s.started_at, s.cancelled_at,
            s.notes, s.created_at, s.updated_at
        FROM client_subscriptions s
        LEFT JOIN package_templates pt ON s.package_template_id = pt.id
        WHERE s.client_id = $1 AND s.status = 'active'
        LIMIT 1
    """
    sub_row = await fetch_one(sub_query, client_id)

    if not sub_row:
        return None

    # Get workspace_id for this client
    client = await fetch_one("SELECT workspace_id FROM clients WHERE id = $1", client_id)
    workspace_id = client["workspace_id"] if client else None

    # Get current usage statistics
    usage = {
        "current_active_domains": 0,
        "current_active_inboxes": 0,
        "current_warming_inboxes": 0,
        "current_spare_inboxes": 0,
        "current_flagged_inboxes": 0,
    }

    if workspace_id:
        # Count domains by status
        domain_counts = await fetch_one("""
            SELECT
                COUNT(*) FILTER (WHERE approval_status IN ('active', 'legacy')) as active_domains,
                COUNT(*) FILTER (WHERE approval_status = 'warming') as warming_domains,
                COUNT(*) FILTER (WHERE approval_status = 'flagged') as flagged_domains
            FROM domains
            WHERE workspace_id = $1
        """, workspace_id)

        if domain_counts:
            usage["current_active_domains"] = domain_counts["active_domains"] or 0

        # Count inboxes by status (approximation based on domain status)
        # In practice, we'd query sender_accounts with health status
        inbox_counts = await fetch_one("""
            SELECT
                COUNT(*) FILTER (WHERE d.approval_status IN ('active', 'legacy')) as active_inboxes,
                COUNT(*) FILTER (WHERE d.approval_status = 'warming') as warming_inboxes,
                COUNT(*) FILTER (WHERE d.approval_status = 'flagged') as flagged_inboxes
            FROM sender_accounts sa
            JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
                AND sa.workspace_id = d.workspace_id
            WHERE sa.workspace_id = $1
        """, workspace_id)

        if inbox_counts:
            usage["current_active_inboxes"] = inbox_counts["active_inboxes"] or 0
            usage["current_warming_inboxes"] = inbox_counts["warming_inboxes"] or 0
            usage["current_flagged_inboxes"] = inbox_counts["flagged_inboxes"] or 0

    return SubscriptionWithUsage(**sub_row, **usage)


@router.post("/client/{client_id}", response_model=Subscription)
async def create_client_subscription(client_id: UUID, subscription: SubscriptionCreate):
    """Create a new subscription for a client"""
    # Verify client exists
    client = await fetch_one("SELECT id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Check for existing active subscription
    existing = await fetch_one(
        "SELECT id FROM client_subscriptions WHERE client_id = $1 AND status = 'active'",
        client_id
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Client already has an active subscription. Update or cancel the existing one first."
        )

    # If template specified, load its values
    template_name = None
    if subscription.package_template_id:
        template = await fetch_one(
            "SELECT name, entra_packages, google_packages FROM package_templates WHERE id = $1",
            subscription.package_template_id
        )
        if not template:
            raise HTTPException(status_code=404, detail="Package template not found")
        template_name = template["name"]
        # Use template values as defaults if not overridden
        if subscription.entra_packages == 6:  # default value
            subscription.entra_packages = template["entra_packages"]
        if subscription.google_packages == 5:  # default value
            subscription.google_packages = template["google_packages"]

    # Create subscription
    query = """
        INSERT INTO client_subscriptions (
            client_id, package_template_id,
            entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
            google_packages, google_domains_per_package, google_inboxes_per_domain,
            spare_ratio, notes
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id, client_id, package_template_id,
                  entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
                  google_packages, google_domains_per_package, google_inboxes_per_domain,
                  spare_ratio, status, started_at, cancelled_at,
                  notes, created_at, updated_at
    """
    row = await fetch_one(
        query,
        client_id,
        subscription.package_template_id,
        subscription.entra_packages,
        subscription.entra_domains_per_package,
        subscription.entra_inboxes_per_domain,
        subscription.google_packages,
        subscription.google_domains_per_package,
        subscription.google_inboxes_per_domain,
        subscription.spare_ratio,
        subscription.notes
    )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    # Record the creation in change history
    await execute("""
        INSERT INTO subscription_changes (
            subscription_id, change_type,
            new_entra_packages, new_google_packages,
            reason, changed_by
        )
        VALUES ($1, 'created', $2, $3, 'Initial subscription', 'system')
    """, row["id"], subscription.entra_packages, subscription.google_packages)

    logger.info(f"Created subscription for client {client_id}: {subscription.entra_packages} Entra, {subscription.google_packages} Google")

    return Subscription(**row, package_template_name=template_name)


@router.put("/client/{client_id}", response_model=Subscription)
async def update_client_subscription(client_id: UUID, update: SubscriptionUpdate):
    """Update a client's subscription"""
    # Get current subscription
    current = await fetch_one(
        "SELECT * FROM client_subscriptions WHERE client_id = $1 AND status = 'active'",
        client_id
    )
    if not current:
        raise HTTPException(status_code=404, detail="No active subscription found for this client")

    # Build SET clause
    set_parts = []
    params = []
    param_idx = 1

    fields = [
        ("entra_packages", update.entra_packages),
        ("entra_domains_per_package", update.entra_domains_per_package),
        ("entra_inboxes_per_domain", update.entra_inboxes_per_domain),
        ("google_packages", update.google_packages),
        ("google_domains_per_package", update.google_domains_per_package),
        ("google_inboxes_per_domain", update.google_inboxes_per_domain),
        ("spare_ratio", update.spare_ratio),
        ("notes", update.notes),
        ("status", update.status),
    ]

    for field_name, value in fields:
        if value is not None:
            set_parts.append(f"{field_name} = ${param_idx}")
            params.append(value)
            param_idx += 1

    if not set_parts:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Handle cancellation
    if update.status == "cancelled":
        set_parts.append("cancelled_at = NOW()")

    set_parts.append("updated_at = NOW()")

    # Execute update
    params.append(current["id"])
    query = f"""
        UPDATE client_subscriptions
        SET {', '.join(set_parts)}
        WHERE id = ${param_idx}
        RETURNING id, client_id, package_template_id,
                  entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
                  google_packages, google_domains_per_package, google_inboxes_per_domain,
                  spare_ratio, status, started_at, cancelled_at,
                  notes, created_at, updated_at
    """
    row = await fetch_one(query, *params)

    if not row:
        raise HTTPException(status_code=500, detail="Failed to update subscription")

    # Determine change type
    change_type = "modify"
    if update.status == "cancelled":
        change_type = "cancelled"
    elif update.entra_packages is not None or update.google_packages is not None:
        new_entra = update.entra_packages if update.entra_packages is not None else current["entra_packages"]
        new_google = update.google_packages if update.google_packages is not None else current["google_packages"]
        old_total = current["entra_packages"] + current["google_packages"]
        new_total = new_entra + new_google
        if new_total > old_total:
            change_type = "upgrade"
        elif new_total < old_total:
            change_type = "downgrade"

    # Record change
    await execute("""
        INSERT INTO subscription_changes (
            subscription_id, change_type,
            previous_entra_packages, previous_google_packages,
            new_entra_packages, new_google_packages,
            reason, changed_by
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    """,
        row["id"],
        change_type,
        current["entra_packages"],
        current["google_packages"],
        row["entra_packages"],
        row["google_packages"],
        update.change_reason,
        update.changed_by
    )

    logger.info(f"Updated subscription for client {client_id}: {change_type}")

    # Get template name if set
    template_name = None
    if row["package_template_id"]:
        template = await fetch_one(
            "SELECT name FROM package_templates WHERE id = $1",
            row["package_template_id"]
        )
        template_name = template["name"] if template else None

    return Subscription(**row, package_template_name=template_name)


@router.post("/client/{client_id}/apply-template", response_model=Subscription)
async def apply_template_to_subscription(client_id: UUID, request: ApplyTemplateRequest):
    """Apply a package template to a client's subscription"""
    # Get template
    template = await fetch_one("""
        SELECT id, name,
               entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
               google_packages, google_domains_per_package, google_inboxes_per_domain
        FROM package_templates
        WHERE id = $1 AND is_active = true
    """, request.package_template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Package template not found or inactive")

    # Get current subscription
    current = await fetch_one(
        "SELECT * FROM client_subscriptions WHERE client_id = $1 AND status = 'active'",
        client_id
    )

    if current:
        # Update existing subscription
        row = await fetch_one("""
            UPDATE client_subscriptions
            SET package_template_id = $1,
                entra_packages = $2, entra_domains_per_package = $3, entra_inboxes_per_domain = $4,
                google_packages = $5, google_domains_per_package = $6, google_inboxes_per_domain = $7,
                updated_at = NOW()
            WHERE id = $8
            RETURNING id, client_id, package_template_id,
                      entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
                      google_packages, google_domains_per_package, google_inboxes_per_domain,
                      spare_ratio, status, started_at, cancelled_at,
                      notes, created_at, updated_at
        """,
            template["id"],
            template["entra_packages"], template["entra_domains_per_package"], template["entra_inboxes_per_domain"],
            template["google_packages"], template["google_domains_per_package"], template["google_inboxes_per_domain"],
            current["id"]
        )

        # Determine change type
        old_total = current["entra_packages"] + current["google_packages"]
        new_total = template["entra_packages"] + template["google_packages"]
        change_type = "modify"
        if new_total > old_total:
            change_type = "upgrade"
        elif new_total < old_total:
            change_type = "downgrade"

        # Record change
        await execute("""
            INSERT INTO subscription_changes (
                subscription_id, change_type,
                previous_entra_packages, previous_google_packages,
                new_entra_packages, new_google_packages,
                reason, changed_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            row["id"],
            change_type,
            current["entra_packages"],
            current["google_packages"],
            template["entra_packages"],
            template["google_packages"],
            request.change_reason or f"Applied template: {template['name']}",
            request.changed_by
        )
    else:
        # Create new subscription from template
        row = await fetch_one("""
            INSERT INTO client_subscriptions (
                client_id, package_template_id,
                entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
                google_packages, google_domains_per_package, google_inboxes_per_domain
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, client_id, package_template_id,
                      entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
                      google_packages, google_domains_per_package, google_inboxes_per_domain,
                      spare_ratio, status, started_at, cancelled_at,
                      notes, created_at, updated_at
        """,
            client_id,
            template["id"],
            template["entra_packages"], template["entra_domains_per_package"], template["entra_inboxes_per_domain"],
            template["google_packages"], template["google_domains_per_package"], template["google_inboxes_per_domain"]
        )

        # Record creation
        await execute("""
            INSERT INTO subscription_changes (
                subscription_id, change_type,
                new_entra_packages, new_google_packages,
                reason, changed_by
            )
            VALUES ($1, 'created', $2, $3, $4, $5)
        """,
            row["id"],
            template["entra_packages"],
            template["google_packages"],
            request.change_reason or f"Created from template: {template['name']}",
            request.changed_by
        )

    logger.info(f"Applied template '{template['name']}' to client {client_id}")

    return Subscription(**row, package_template_name=template["name"])


@router.get("/client/{client_id}/history", response_model=list[SubscriptionChange])
async def get_subscription_history(client_id: UUID, limit: int = Query(20, ge=1, le=100)):
    """Get subscription change history for a client"""
    query = """
        SELECT sc.*
        FROM subscription_changes sc
        JOIN client_subscriptions s ON sc.subscription_id = s.id
        WHERE s.client_id = $1
        ORDER BY sc.created_at DESC
        LIMIT $2
    """
    rows = await fetch_all(query, client_id, limit)
    return [SubscriptionChange(**row) for row in rows]


# =============================================================================
# Bulk Operations / Utilities
# =============================================================================

@router.post("/backfill/starter-package")
async def backfill_starter_subscriptions():
    """
    Create Starter package subscriptions for all clients that don't have one.
    Useful for initial setup.
    """
    # Get Starter template
    template = await fetch_one("SELECT * FROM package_templates WHERE name = 'Starter'")
    if not template:
        raise HTTPException(status_code=500, detail="Starter template not found. Run migration first.")

    # Get clients without subscriptions
    clients_without = await fetch_all("""
        SELECT c.id, c.name
        FROM clients c
        LEFT JOIN client_subscriptions s ON c.id = s.client_id AND s.status = 'active'
        WHERE s.id IS NULL
    """)

    created = []
    for client in clients_without:
        result = await fetch_one("""
            INSERT INTO client_subscriptions (
                client_id, package_template_id,
                entra_packages, entra_domains_per_package, entra_inboxes_per_domain,
                google_packages, google_domains_per_package, google_inboxes_per_domain
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """,
            client["id"],
            template["id"],
            template["entra_packages"], template["entra_domains_per_package"], template["entra_inboxes_per_domain"],
            template["google_packages"], template["google_domains_per_package"], template["google_inboxes_per_domain"]
        )

        if result:
            # Record creation
            await execute("""
                INSERT INTO subscription_changes (
                    subscription_id, change_type,
                    new_entra_packages, new_google_packages,
                    reason, changed_by
                )
                VALUES ($1, 'created', $2, $3, 'Backfill - Starter package', 'system')
            """, result["id"], template["entra_packages"], template["google_packages"])

            created.append({"client_id": str(client["id"]), "client_name": client["name"]})

    return {
        "message": f"Backfill complete",
        "template_used": "Starter",
        "created_count": len(created),
        "created_subscriptions": created
    }
