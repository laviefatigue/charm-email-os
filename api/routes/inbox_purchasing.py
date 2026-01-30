"""
Inbox Purchasing Routes - HyperTide automation integration.

Provides endpoints for:
- Calculating optimal order quantities
- Generating inbox names
- Executing purchases via HyperTide browser automation
- Tracking purchase job status
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
import logging
import sys
import uuid
import asyncio
import random
from pathlib import Path
from uuid import UUID

from database import fetch_one, fetch_all, execute
from datetime import datetime, timezone

# Add HyperTide automation to path
hypertide_path = Path(__file__).parent.parent.parent / "Hypertide" / "automation" / "src"
if str(hypertide_path) not in sys.path:
    sys.path.insert(0, str(hypertide_path))

from models.inbox_purchasing import (
    CalculateOrdersRequest,
    CalculateOrdersResponse,
    OrderBreakdownResponse,
    GenerateNamesRequest,
    GenerateNamesResponse,
    GeneratedInboxName,
    ExecutePurchaseRequest,
    PurchaseJobResponse,
    PurchaseStatusResponse,
    PurchaseCompleteResponse,
    OrderResultResponse,
    OrderStatus,
    InboxProviderType,
    # V2 models
    ExecutePurchaseV2Request,
    ExecutePurchaseV2Summary,
    OrderGroup,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# =============================================================================
# Database Job Storage Helpers
# =============================================================================


async def _create_job_in_db(
    job_id: str,
    client_id: UUID,
    workspace_id: Optional[UUID],
    provider_type: str,
    domain_ids: list[UUID],
    domain_names: list[str],
    breakdown: dict,
    request_data: dict,
    override_age_check: bool = False,
    custom_purchase: bool = False,
) -> str:
    """Create a job record in the database."""
    await execute(
        """
        INSERT INTO inbox_purchase_jobs (
            id, client_id, workspace_id, status, provider_type,
            domain_ids, domain_names, entra_orders, google_orders,
            orders_total, total_inboxes, monthly_cost,
            request_data, override_age_check, custom_purchase,
            created_at
        ) VALUES (
            $1, $2, $3, 'pending', $4,
            $5, $6, $7, $8,
            $9, $10, $11,
            $12, $13, $14,
            NOW()
        )
        """,
        UUID(job_id),
        client_id,
        workspace_id,
        provider_type,
        domain_ids,
        domain_names,
        breakdown.get("entra_orders", 0),
        breakdown.get("google_orders", 0),
        breakdown.get("total_orders", 0),
        breakdown.get("total_inboxes", 0),
        float(breakdown.get("total_orders", 0) * 50),
        request_data,
        override_age_check,
        custom_purchase,
    )
    return job_id


async def _check_domain_lock_conflicts(domain_ids: list) -> list[dict]:
    """Check if any domains are already locked by an active job. Read-only."""
    conflicts = []
    for did in domain_ids:
        row = await fetch_one(
            """SELECT d.id, d.domain_name, d.purchase_job_id, d.purchase_job_status
               FROM domains d WHERE d.id = $1""",
            did
        )
        if row and row.get("purchase_job_id") and row.get("purchase_job_status") not in ("completed", "cancelled", None):
            conflicts.append({
                "domain_id": str(row["id"]),
                "domain_name": row.get("domain_name", ""),
                "locked_by_job": str(row["purchase_job_id"]),
                "job_status": row.get("purchase_job_status"),
            })
    return conflicts


async def _lock_domains_for_job(job_id: str, domain_ids: list) -> None:
    """Lock domains for a purchase job. Job must already exist in inbox_purchase_jobs (FK constraint)."""
    await execute(
        "UPDATE domains SET purchase_job_id = $1, purchase_job_status = 'pending' WHERE id = ANY($2)",
        UUID(job_id), [UUID(str(d)) for d in domain_ids]
    )


async def _release_domain_locks(job_id: str) -> None:
    """Release all domain locks held by a job."""
    await execute(
        "UPDATE domains SET purchase_job_id = NULL, purchase_job_status = NULL WHERE purchase_job_id = $1",
        UUID(job_id)
    )


async def _transfer_domain_locks(old_job_id: str, new_job_id: str) -> None:
    """Transfer domain locks from an old job to a new one (used on retry)."""
    await execute(
        "UPDATE domains SET purchase_job_id = $1, purchase_job_status = 'pending' WHERE purchase_job_id = $2",
        UUID(new_job_id), UUID(old_job_id)
    )


async def _update_job_status(
    job_id: str,
    status: str,
    current_step: Optional[str] = None,
    orders_completed: Optional[int] = None,
    total_inboxes: Optional[int] = None,
    results: Optional[list] = None,
    errors: Optional[list[str]] = None,
) -> None:
    """Update job status in the database."""
    import json

    updates = ["status = $2"]
    params: list = [UUID(job_id), status]

    if current_step is not None:
        updates.append(f"current_step = ${len(params) + 1}")
        params.append(current_step)

    if orders_completed is not None:
        updates.append(f"orders_completed = ${len(params) + 1}")
        params.append(orders_completed)

    if total_inboxes is not None:
        updates.append(f"total_inboxes = ${len(params) + 1}")
        params.append(total_inboxes)

    if results is not None:
        updates.append(f"results = ${len(params) + 1}")
        params.append(json.dumps(results))

    if errors is not None:
        updates.append(f"errors = ${len(params) + 1}")
        params.append(errors)

    # Update timestamps based on status
    if status == "executing":
        updates.append("started_at = NOW()")
    if status in ("completed", "failed"):
        updates.append("completed_at = NOW()")

    await execute(
        f"UPDATE inbox_purchase_jobs SET {', '.join(updates)} WHERE id = $1",
        *params
    )

    # Sync purchase_job_status on locked domains
    await execute(
        "UPDATE domains SET purchase_job_status = $1 WHERE purchase_job_id = $2",
        status, UUID(job_id)
    )

    # On completion, release domain locks (domains now have infrastructure_type set)
    if status == "completed":
        await _release_domain_locks(job_id)


async def _get_job_from_db(job_id: str) -> Optional[dict]:
    """Fetch a job from the database."""
    import json

    job = await fetch_one(
        """
        SELECT id, client_id, workspace_id, status, current_step,
               provider_type, domain_ids, domain_names,
               entra_orders, google_orders, orders_completed, orders_total,
               total_inboxes, monthly_cost,
               created_at, started_at, completed_at,
               results, errors, request_data,
               override_age_check, custom_purchase
        FROM inbox_purchase_jobs
        WHERE id = $1
        """,
        UUID(job_id)
    )

    if not job:
        return None

    # Parse JSONB fields
    results = job.get("results")
    if results and isinstance(results, str):
        results = json.loads(results)

    request_data = job.get("request_data")
    if request_data and isinstance(request_data, str):
        request_data = json.loads(request_data)

    return {
        "job_id": str(job["id"]),
        "client_id": str(job["client_id"]),
        "workspace_id": str(job["workspace_id"]) if job.get("workspace_id") else None,
        "status": job["status"],
        "current_step": job.get("current_step"),
        "provider_type": job.get("provider_type"),
        "domain_ids": [str(d) for d in (job.get("domain_ids") or [])],
        "domain_names": job.get("domain_names") or [],
        "breakdown": {
            "entra_orders": job.get("entra_orders") or 0,
            "google_orders": job.get("google_orders") or 0,
            "total_orders": job.get("orders_total") or 0,
            "total_inboxes": job.get("total_inboxes") or 0,
        },
        "orders_completed": job.get("orders_completed") or 0,
        "orders_total": job.get("orders_total") or 0,
        "total_inboxes": job.get("total_inboxes") or 0,
        "monthly_cost": float(job.get("monthly_cost") or 0),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "created_at": job.get("created_at"),
        "results": results or [],
        "errors": job.get("errors") or [],
        "request_data": request_data,
        "override_age_check": job.get("override_age_check", False),
        "custom_purchase": job.get("custom_purchase", False),
    }


def _import_hypertide_modules():
    """Import HyperTide modules with error handling."""
    try:
        from hypertide_automation.models import (
            InboxTarget,
            InboxConfig,
            MixedOrderRequest,
            BisonCredentials,
            OrderType,
            DomainConfig,
            calculate_optimal_orders,
            create_order_bundle,
        )
        from hypertide_automation.purchase import (
            purchase_mixed_order,
            BundlePurchaseAutomation,
        )
        from hypertide_automation.client import HypertideClient

        return {
            "InboxTarget": InboxTarget,
            "InboxConfig": InboxConfig,
            "MixedOrderRequest": MixedOrderRequest,
            "BisonCredentials": BisonCredentials,
            "OrderType": OrderType,
            "DomainConfig": DomainConfig,
            "calculate_optimal_orders": calculate_optimal_orders,
            "create_order_bundle": create_order_bundle,
            "purchase_mixed_order": purchase_mixed_order,
            "BundlePurchaseAutomation": BundlePurchaseAutomation,
            "HypertideClient": HypertideClient,
        }
    except ImportError as e:
        logger.warning(f"HyperTide modules not available: {e}")
        return None


# Common first and last names for inbox generation
COMMON_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey",
    "Riley", "Quinn", "Avery", "Parker", "Cameron",
    "Drew", "Blake", "Jamie", "Reese", "Skyler",
    "Sage", "Rowan", "Emery", "Finley", "Phoenix",
]

COMMON_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones",
    "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Anderson", "Taylor", "Thomas", "Moore", "Jackson",
    "Martin", "Lee", "Thompson", "White", "Harris",
]


@router.post("/calculate", response_model=CalculateOrdersResponse)
async def calculate_orders(request: CalculateOrdersRequest):
    """
    Calculate optimal order quantities for inbox targets.

    Given target inbox counts for Entra and/or Google, calculates:
    - Number of orders needed for each provider
    - Actual inboxes that will be created (may exceed target due to package sizes)
    - Estimated monthly cost

    Hypertide order specifications:
    - Entra: 2 domains/order × 50 inboxes/domain = 100 inboxes/order
    - Google: 5 domains/order × 3 inboxes/domain = 15 inboxes/order
    """
    ht = _import_hypertide_modules()

    if ht:
        # Use HyperTide's calculation
        target = ht["InboxTarget"](
            entra_inboxes=request.inbox_target.entra_inboxes,
            google_inboxes=request.inbox_target.google_inboxes,
        )
        breakdown = ht["calculate_optimal_orders"](target)

        return CalculateOrdersResponse(
            client_id=request.client_id,
            requested_target=request.inbox_target,
            breakdown=OrderBreakdownResponse(
                entra_orders=breakdown.entra_orders,
                entra_domains=breakdown.entra_domains,
                entra_inboxes_actual=breakdown.entra_inboxes_actual,
                google_orders=breakdown.google_orders,
                google_domains=breakdown.google_domains,
                google_inboxes_actual=breakdown.google_inboxes_actual,
                total_orders=breakdown.entra_orders + breakdown.google_orders,
                total_inboxes=breakdown.total_inboxes,
                total_domains=breakdown.total_domains,
                total_monthly_capacity=breakdown.total_monthly_capacity,
                estimated_monthly_cost=breakdown.estimated_monthly_cost,
                has_entra=breakdown.has_entra,
                has_google=breakdown.has_google,
                is_mixed=breakdown.is_mixed,
            ),
            message=f"Calculated: {breakdown.entra_orders} Entra + {breakdown.google_orders} Google orders"
        )
    else:
        # Fallback calculation without HyperTide
        import math

        entra_target = request.inbox_target.entra_inboxes
        google_target = request.inbox_target.google_inboxes

        # Entra: 100 inboxes per order (2 domains × 50 inboxes)
        entra_orders = math.ceil(entra_target / 100) if entra_target > 0 else 0
        entra_domains = entra_orders * 2
        entra_inboxes = entra_orders * 100

        # Google: 15 inboxes per order (5 domains × 3 inboxes)
        google_orders = math.ceil(google_target / 15) if google_target > 0 else 0
        google_domains = google_orders * 5
        google_inboxes = google_orders * 15

        total_orders = entra_orders + google_orders
        total_capacity = total_orders * 5000
        estimated_cost = total_orders * 50.0

        return CalculateOrdersResponse(
            client_id=request.client_id,
            requested_target=request.inbox_target,
            breakdown=OrderBreakdownResponse(
                entra_orders=entra_orders,
                entra_domains=entra_domains,
                entra_inboxes_actual=entra_inboxes,
                google_orders=google_orders,
                google_domains=google_domains,
                google_inboxes_actual=google_inboxes,
                total_orders=total_orders,
                total_inboxes=entra_inboxes + google_inboxes,
                total_domains=entra_domains + google_domains,
                total_monthly_capacity=total_capacity,
                estimated_monthly_cost=estimated_cost,
                has_entra=entra_orders > 0,
                has_google=google_orders > 0,
                is_mixed=entra_orders > 0 and google_orders > 0,
            ),
            message=f"Calculated (fallback): {entra_orders} Entra + {google_orders} Google orders"
        )


@router.post("/generate-names", response_model=GenerateNamesResponse)
async def generate_inbox_names(request: GenerateNamesRequest):
    """
    Generate inbox names (first.last combinations).

    Returns randomized combinations of first and last names suitable for
    professional email addresses. You can provide custom name lists or
    use the built-in common names.
    """
    first_names = request.first_names or COMMON_FIRST_NAMES
    last_names = request.last_names or COMMON_LAST_NAMES

    # Generate unique combinations
    generated = []
    used_combos = set()

    attempts = 0
    max_attempts = request.count * 3  # Allow retries for uniqueness

    while len(generated) < request.count and attempts < max_attempts:
        first = random.choice(first_names)
        last = random.choice(last_names)
        combo = f"{first.lower()}.{last.lower()}"

        if combo not in used_combos:
            used_combos.add(combo)
            generated.append(GeneratedInboxName(
                first_name=first,
                last_name=last,
                email_prefix=combo,
            ))

        attempts += 1

    return GenerateNamesResponse(
        client_id=request.client_id,
        names=generated,
        count=len(generated),
    )


@router.post("/execute", response_model=PurchaseJobResponse)
async def execute_purchase(
    request: ExecutePurchaseRequest,
    background_tasks: BackgroundTasks
):
    """
    Execute inbox purchase via HyperTide automation.

    This starts a background task that:
    1. Logs into HyperTide (manual authentication required)
    2. Executes purchase flow for each order type (Entra/Google)
    3. Connects inboxes to EmailBison (if credentials provided)

    The purchase typically takes 2-5 minutes per order type.
    Use the /status/{job_id} endpoint to check progress.

    **Note**: HyperTide requires browser automation - the server running
    this API must have a display or run in headless mode.
    """
    ht = _import_hypertide_modules()
    if not ht:
        raise HTTPException(
            status_code=503,
            detail="HyperTide automation module not available"
        )

    # Create job ID
    job_id = str(uuid.uuid4())

    # Calculate order breakdown
    target = ht["InboxTarget"](
        entra_inboxes=request.inbox_target.entra_inboxes,
        google_inboxes=request.inbox_target.google_inboxes,
    )
    breakdown = ht["calculate_optimal_orders"](target)

    # Get client workspace
    client = await fetch_one(
        "SELECT workspace_id FROM clients WHERE id = $1",
        request.client_id
    )
    workspace_id = client.get("workspace_id") if client else None

    # Build domain names list
    domain_names = []
    for d in (request.entra_domains or []):
        domain_names.append(d.domain_name)
    for d in (request.google_domains or []):
        domain_names.append(d.domain_name)

    # Store job in database
    await _create_job_in_db(
        job_id=job_id,
        client_id=request.client_id,
        workspace_id=workspace_id,
        provider_type="mixed" if breakdown.is_mixed else ("entra" if breakdown.has_entra else "google"),
        domain_ids=[],  # V1 doesn't track domain IDs
        domain_names=domain_names,
        breakdown={
            "entra_orders": breakdown.entra_orders,
            "google_orders": breakdown.google_orders,
            "total_orders": breakdown.entra_orders + breakdown.google_orders,
            "total_inboxes": breakdown.total_inboxes,
        },
        request_data=request.model_dump(mode="json"),
    )

    # Start background task
    background_tasks.add_task(
        _execute_purchase_task,
        job_id,
        request,
        ht,
    )

    total_orders = breakdown.entra_orders + breakdown.google_orders
    estimated_duration = total_orders * 120  # ~2 minutes per order

    return PurchaseJobResponse(
        job_id=job_id,
        client_id=request.client_id,
        status=OrderStatus.PENDING,
        message=f"Purchase job started. {total_orders} order(s) to process.",
        estimated_duration_seconds=estimated_duration,
    )


async def _execute_purchase_task(
    job_id: str,
    request: ExecutePurchaseRequest,
    ht: dict,
):
    """Background task to execute HyperTide purchase."""
    try:
        await _update_job_status(job_id, "executing", "Preparing order request")

        # Build inbox configs
        inbox_configs = [
            ht["InboxConfig"](
                first_name=name.first_name,
                last_name=name.last_name,
            )
            for name in request.inbox_names
        ]

        # Build domain configs
        entra_domain_configs = [
            ht["DomainConfig"](
                name=d.domain_name.split('.')[0],
                tld='.'.join(d.domain_name.split('.')[1:]) or 'com',
                use_hypertide_domain=True,
            )
            for d in request.entra_domains
        ]

        google_domain_configs = [
            ht["DomainConfig"](
                name=d.domain_name.split('.')[0],
                tld='.'.join(d.domain_name.split('.')[1:]) or 'com',
                use_hypertide_domain=True,
            )
            for d in request.google_domains
        ]

        # Build Bison credentials if provided
        bison_creds = None
        if request.bison_username and request.bison_password:
            bison_creds = ht["BisonCredentials"](
                username=request.bison_username,
                password=request.bison_password,
                workspace=request.bison_workspace or "Default",
                bison_url=request.bison_url,
            )

        # Build mixed order request
        await _update_job_status(job_id, "executing", "Creating HyperTide order request")

        mixed_request = ht["MixedOrderRequest"](
            client_name=request.client_name,
            forwarding_domain=request.forwarding_domain,
            inbox_target=ht["InboxTarget"](
                entra_inboxes=request.inbox_target.entra_inboxes,
                google_inboxes=request.inbox_target.google_inboxes,
            ),
            bison_credentials=bison_creds or ht["BisonCredentials"](
                username="placeholder@email.com",
                password="placeholder",
                workspace="Default",
            ),
            users=inbox_configs,
            entra_domains=entra_domain_configs,
            google_domains=google_domain_configs,
            use_saved_payment=request.use_saved_payment,
        )

        # Execute purchase
        await _update_job_status(job_id, "executing", "Executing HyperTide purchase automation")

        result = await ht["purchase_mixed_order"](mixed_request)

        # Process results
        await _update_job_status(job_id, "executing", "Processing results")

        order_results = []
        for order_result in result.order_results:
            order_results.append({
                "success": order_result.success,
                "order_type": order_result.order_type.value,
                "quantity": order_result.quantity,
                "inboxes_created": order_result.total_inboxes,
                "domains_created": order_result.domains_created,
                "order_id": order_result.order_id,
                "error": order_result.error_message,
            })

        if result.success:
            await _update_job_status(job_id, "executing", "Saving inboxes to database")

            # Save inboxes to database
            try:
                client = await fetch_one(
                    "SELECT workspace_id FROM clients WHERE id = $1",
                    request.client_id
                )
                if client and client["workspace_id"]:
                    workspace_id = client["workspace_id"]
                    created_count = 0

                    for order_result in result.order_results:
                        if order_result.success:
                            # Get the domains from this order result
                            domains = order_result.domains_created or []
                            inboxes = request.inbox_names

                            # Create inbox records for each domain and name combination
                            for domain in domains:
                                for name in inboxes[:order_result.total_inboxes // len(domains) if domains else 0]:
                                    email = f"{name.first_name.lower()}.{name.last_name.lower()}@{domain}"

                                    # Check if exists
                                    existing = await fetch_one(
                                        "SELECT id FROM sender_accounts WHERE workspace_id = $1 AND email_address = $2",
                                        workspace_id, email
                                    )

                                    if not existing:
                                        await execute(
                                            "INSERT INTO sender_accounts (workspace_id, email_address, inbox_state) VALUES ($1, $2, 'live')",
                                            workspace_id, email
                                        )
                                        created_count += 1

                    logger.info(f"Created {created_count} inbox records in database")

                    # Update domain status to 'active' for provisioned domains
                    domains_provisioned = []
                    for order_result in result.order_results:
                        if order_result.success and order_result.domains_created:
                            domains_provisioned.extend(order_result.domains_created)

                    if domains_provisioned:
                        # Update status of provisioned domains from 'purchased' to 'active'
                        await execute(
                            """
                            UPDATE domains
                            SET approval_status = 'active', updated_at = NOW()
                            WHERE workspace_id = $1
                            AND domain_name = ANY($2)
                            AND approval_status IN ('purchased', 'provisioning')
                            """,
                            workspace_id,
                            domains_provisioned
                        )
                        logger.info(f"Updated {len(domains_provisioned)} domain(s) to 'active' status")
            except Exception as db_error:
                logger.error(f"Failed to save inboxes to database: {db_error}")

            # Mark job as completed
            await _update_job_status(
                job_id, "completed", "Purchase completed successfully",
                orders_completed=len([r for r in order_results if r["success"]]),
                total_inboxes=result.total_inboxes,
                results=order_results,
            )
        else:
            # Mark job as failed
            await _update_job_status(
                job_id, "failed", "Purchase completed with errors",
                orders_completed=len([r for r in order_results if r["success"]]),
                results=order_results,
                errors=result.errors,
            )

    except Exception as e:
        logger.error(f"Purchase task failed: {e}")
        await _update_job_status(
            job_id, "failed", f"Failed: {str(e)}",
            errors=[str(e)],
        )


@router.get("/status/{job_id}", response_model=PurchaseStatusResponse)
async def get_purchase_status(job_id: str):
    """
    Get status of a purchase job.

    Poll this endpoint to track progress of a purchase initiated via /execute.
    """
    job = await _get_job_from_db(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Purchase job not found")

    # Convert results to response format
    results = None
    if job.get("results"):
        results = [
            OrderResultResponse(
                success=r["success"],
                order_type=r["order_type"],
                quantity=r.get("quantity", 1),
                inboxes_created=r.get("inboxes_created", 0),
                domains_created=r.get("domains_created", []),
                order_id=r.get("order_id"),
                error=r.get("error"),
            )
            for r in job["results"]
        ]

    breakdown = job.get("breakdown", {})

    return PurchaseStatusResponse(
        job_id=job_id,
        client_id=uuid.UUID(job["client_id"]),
        status=job["status"],
        current_step=job.get("current_step"),
        orders_completed=job.get("orders_completed", 0),
        orders_total=breakdown.get("total_orders", 0),
        results=results,
        total_inboxes=job.get("total_inboxes", 0),
        total_monthly_capacity=job.get("total_inboxes", 0) * 50,
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        errors=job.get("errors", []),
    )


@router.delete("/jobs/{job_id}")
async def cancel_purchase_job(job_id: str):
    """
    Cancel or clean up a purchase job.

    Note: Cannot cancel in-progress HyperTide automation.
    This marks the job as cancelled but does not delete it from history.
    """
    job = await _get_job_from_db(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Purchase job not found")

    if job["status"] == "executing":
        return {
            "message": "Cannot cancel in-progress purchase. HyperTide automation must complete.",
            "status": job["status"],
        }

    # Release domain locks and mark as cancelled (preserve history)
    await _release_domain_locks(job_id)
    await _update_job_status(job_id, "cancelled", "Cancelled by user")
    return {"message": "Purchase job cancelled", "job_id": job_id}


@router.get("/jobs")
async def list_purchase_jobs(
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    List purchase jobs from database, optionally filtered by client or status.
    """
    conditions = []
    params: list = []

    if client_id:
        conditions.append(f"client_id = ${len(params) + 1}")
        params.append(UUID(client_id))

    if status:
        conditions.append(f"status = ${len(params) + 1}")
        params.append(status)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    jobs = await fetch_all(
        f"""
        SELECT id, client_id, status, current_step, provider_type,
               domain_names, entra_orders, google_orders, orders_completed, orders_total,
               total_inboxes, monthly_cost,
               created_at, started_at, completed_at, errors
        FROM inbox_purchase_jobs
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset
    )

    total_result = await fetch_one(
        f"SELECT COUNT(*) as count FROM inbox_purchase_jobs {where_clause}",
        *params
    )

    return {
        "jobs": [
            {
                "job_id": str(j["id"]),
                "client_id": str(j["client_id"]),
                "status": j["status"],
                "current_step": j.get("current_step"),
                "provider_type": j.get("provider_type"),
                "domain_names": j.get("domain_names") or [],
                "entra_orders": j.get("entra_orders", 0),
                "google_orders": j.get("google_orders", 0),
                "orders_completed": j.get("orders_completed", 0),
                "orders_total": j.get("orders_total", 0),
                "total_inboxes": j.get("total_inboxes", 0),
                "monthly_cost": float(j.get("monthly_cost", 0) or 0),
                "created_at": j.get("created_at").isoformat() if j.get("created_at") else None,
                "started_at": j.get("started_at").isoformat() if j.get("started_at") else None,
                "completed_at": j.get("completed_at").isoformat() if j.get("completed_at") else None,
                "errors": j.get("errors") or [],
            }
            for j in jobs
        ],
        "total": total_result["count"] if total_result else 0,
    }


@router.post("/jobs/{job_id}/retry")
async def retry_failed_job(job_id: str, background_tasks: BackgroundTasks):
    """
    Retry a failed purchase job using stored request data.

    Creates a new job with the same parameters and marks the old job as superseded.
    """
    import json

    job = await _get_job_from_db(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] not in ("failed",):
        raise HTTPException(
            status_code=400,
            detail=f"Can only retry failed jobs. Current status: {job['status']}"
        )

    if not job.get("request_data"):
        raise HTTPException(
            status_code=400,
            detail="Job has no stored request data for retry"
        )

    # Release domain locks from old job before marking superseded
    # (the new job will re-acquire locks via execute_smart_order)
    await _release_domain_locks(job_id)

    # Mark old job as superseded
    await _update_job_status(job_id, "superseded", "Superseded by retry")

    # Create and execute new job with the same request
    request_data = job["request_data"]

    # Determine which type of request this was and re-execute
    if "order_groups" in request_data:
        # V2 request
        new_request = ExecutePurchaseV2Request(**request_data)
        return await execute_purchase_v2(new_request, background_tasks)
    elif "domain_ids" in request_data:
        # Smart order request
        new_request = SmartOrderRequest(**request_data)
        return await execute_smart_order(new_request, background_tasks)
    else:
        # V1 request
        new_request = ExecutePurchaseRequest(**request_data)
        return await execute_purchase(new_request, background_tasks)


# =============================================================================
# V2 Endpoints - Enhanced Flow with Domain Grouping
# =============================================================================

def _convert_prefixes_to_inbox_configs(
    prefixes: list[str],
    first_name: str,
    last_name: str,
    limit: int
) -> list[dict]:
    """
    Convert Charm prefixes to Hypertide InboxConfig format.

    Prefixes like "chris.booth" → InboxConfig(first_name="chris", last_name="booth")
    Prefixes like "chris" → InboxConfig(first_name="chris", last_name=<original_last_name>)

    Args:
        prefixes: List of email prefixes
        first_name: Original first name (fallback for single-part prefixes)
        last_name: Original last name (fallback for single-part prefixes)
        limit: Max configs to return (10 for Entra, 3 for Google - Hypertide max 10)
    """
    configs = []
    for prefix in prefixes[:limit]:
        if '.' in prefix:
            parts = prefix.split('.', 1)
            configs.append({
                "first_name": parts[0],
                "last_name": parts[1] if len(parts) > 1 else last_name,
            })
        else:
            # Single name prefix like "chris" or "booth"
            configs.append({
                "first_name": prefix,
                "last_name": last_name,
            })
    return configs


@router.post("/execute-v2/preview", response_model=ExecutePurchaseV2Summary)
async def preview_purchase_v2(request: ExecutePurchaseV2Request):
    """
    Preview a V2 purchase without executing.

    Validates order groups and returns a summary of what would be purchased.
    Use this to show users the breakdown before they confirm.
    """
    import json

    # Validate each order group
    errors = []
    for i, group in enumerate(request.order_groups):
        is_valid, msg = group.validate_domain_count()
        if not is_valid:
            errors.append(f"Order group {i + 1}: {msg}")

    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Get client's sender names
    client = await fetch_one(
        "SELECT id, name, onboarding_data FROM clients WHERE id = $1",
        request.client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    onboarding_data = client.get("onboarding_data")
    if isinstance(onboarding_data, str):
        onboarding_data = json.loads(onboarding_data)

    # Calculate totals
    entra_orders = sum(1 for g in request.order_groups if g.order_type == InboxProviderType.ENTRA)
    google_orders = sum(1 for g in request.order_groups if g.order_type == InboxProviderType.GOOGLE)

    # Hypertide constraints:
    # - Entra: 2 domains × 50 inboxes = 100 inboxes per order
    # - Google: 5 domains × 3 inboxes = 15 inboxes per order
    entra_inboxes = entra_orders * 100  # 2 domains × 50 inboxes
    google_inboxes = google_orders * 15   # 5 domains × 3 inboxes
    total_inboxes = entra_inboxes + google_inboxes

    total_domains = sum(len(g.domain_ids) for g in request.order_groups)

    # Fetch domain names for breakdown
    domain_breakdown = []
    for group in request.order_groups:
        domain_rows = await fetch_all(
            "SELECT id, domain_name FROM domains WHERE id = ANY($1)",
            list(group.domain_ids)
        )
        domain_names = [d["domain_name"] for d in domain_rows]

        inboxes_per_order = 100 if group.order_type == InboxProviderType.ENTRA else 15
        domain_breakdown.append({
            "order_type": group.order_type.value,
            "domains": domain_names,
            "sender_name_id": group.sender_name_id,
            "inboxes": inboxes_per_order,
        })

    return ExecutePurchaseV2Summary(
        total_orders=entra_orders + google_orders,
        entra_orders=entra_orders,
        google_orders=google_orders,
        total_domains=total_domains,
        total_inboxes=total_inboxes,
        entra_inboxes=entra_inboxes,
        google_inboxes=google_inboxes,
        estimated_monthly_cost=(entra_orders + google_orders) * 50.0,
        domain_breakdown=domain_breakdown,
    )


@router.post("/execute-v2", response_model=PurchaseJobResponse)
async def execute_purchase_v2(
    request: ExecutePurchaseV2Request,
    background_tasks: BackgroundTasks
):
    """
    Execute inbox purchase with domain grouping (V2).

    This enforces Hypertide's fixed domain requirements:
    - Each Entra order must have exactly 2 domains → 100 inboxes
    - Each Google order must have exactly 5 domains → 15 inboxes

    The flow:
    1. Validates order groups (domain counts)
    2. Fetches sender name prefixes for each group
    3. Converts prefixes to InboxConfigs (50 for Entra, 3 for Google)
    4. Executes Hypertide automation for each order
    5. Marks domains with infrastructure_type after provisioning
    """
    import json

    ht = _import_hypertide_modules()
    if not ht:
        raise HTTPException(
            status_code=503,
            detail="HyperTide automation module not available"
        )

    # Validate each order group
    errors = []
    for i, group in enumerate(request.order_groups):
        is_valid, msg = group.validate_domain_count()
        if not is_valid:
            errors.append(f"Order group {i + 1}: {msg}")

    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Get client info and sender names
    client = await fetch_one(
        "SELECT id, name, workspace_id, onboarding_data FROM clients WHERE id = $1",
        request.client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if not client.get("workspace_id"):
        raise HTTPException(status_code=400, detail="Client has no workspace linked")

    onboarding_data = client.get("onboarding_data")
    if isinstance(onboarding_data, str):
        onboarding_data = json.loads(onboarding_data)

    # Get sender name prefixes
    base_names = onboarding_data.get("baseSenderNames", []) if onboarding_data else []
    pre_generated = onboarding_data.get("preGeneratedSenderNames", []) if onboarding_data else []

    if not base_names or not pre_generated:
        raise HTTPException(
            status_code=400,
            detail="Client has no sender names configured. Set sender names first."
        )

    # Fetch all domain details
    all_domain_ids = []
    for group in request.order_groups:
        all_domain_ids.extend(group.domain_ids)

    domain_rows = await fetch_all(
        """
        SELECT id, domain_name, registration_date, purchased_at
        FROM domains
        WHERE id = ANY($1)
        """,
        all_domain_ids
    )
    domains_by_id = {d["id"]: d for d in domain_rows}

    # Validate domain age unless override
    if not request.override_age_check:
        young_domains = []
        for domain in domain_rows:
            reg_date = domain.get("registration_date") or domain.get("purchased_at")
            if reg_date:
                age_days = (datetime.now(timezone.utc) - reg_date.replace(tzinfo=timezone.utc)).days
                if age_days < 30:
                    young_domains.append(f"{domain['domain_name']} ({age_days} days)")

        if young_domains:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Some domains are younger than 30 days",
                    "young_domains": young_domains,
                    "hint": "Set override_age_check=true to proceed anyway"
                }
            )

    # Create job ID
    job_id = str(uuid.uuid4())

    # Calculate totals
    entra_orders = sum(1 for g in request.order_groups if g.order_type == InboxProviderType.ENTRA)
    google_orders = sum(1 for g in request.order_groups if g.order_type == InboxProviderType.GOOGLE)
    total_inboxes = (entra_orders * 100) + (google_orders * 15)

    # Get domain names for storage
    domain_names = [d["domain_name"] for d in domain_rows]

    # Determine provider type
    provider_type = "mixed" if entra_orders > 0 and google_orders > 0 else ("entra" if entra_orders > 0 else "google")

    # Store job in database
    await _create_job_in_db(
        job_id=job_id,
        client_id=request.client_id,
        workspace_id=client["workspace_id"],
        provider_type=provider_type,
        domain_ids=all_domain_ids,
        domain_names=domain_names,
        breakdown={
            "entra_orders": entra_orders,
            "google_orders": google_orders,
            "total_orders": entra_orders + google_orders,
            "total_inboxes": total_inboxes,
        },
        request_data=request.model_dump(mode="json"),
        override_age_check=request.override_age_check,
    )

    # Start background task - pass necessary data directly instead of storing in-memory
    background_tasks.add_task(
        _execute_purchase_v2_task,
        job_id,
        request,
        ht,
        {str(k): v for k, v in domains_by_id.items()},
        base_names,
        pre_generated,
        str(client["workspace_id"]),
    )

    total_orders = entra_orders + google_orders
    estimated_duration = total_orders * 120  # ~2 minutes per order

    return PurchaseJobResponse(
        job_id=job_id,
        client_id=request.client_id,
        status=OrderStatus.PENDING,
        message=f"Purchase job started. {total_orders} order(s) to process. {total_inboxes} inboxes expected.",
        estimated_duration_seconds=estimated_duration,
    )


async def _execute_purchase_v2_task(
    job_id: str,
    request: ExecutePurchaseV2Request,
    ht: dict,
    domains_by_id: dict,
    base_names: list,
    pre_generated: list,
    workspace_id_str: str,
):
    """Background task to execute V2 HyperTide purchase with domain grouping."""
    try:
        await _update_job_status(job_id, "executing", "Preparing order requests")

        # Process each order group
        all_results = []
        total_groups = len(request.order_groups)

        for group_idx, group in enumerate(request.order_groups):
            await _update_job_status(job_id, "executing", f"Processing order group {group_idx + 1}/{total_groups}")

            # Get domain names for this group
            domain_names = [
                domains_by_id[str(domain_id)]["domain_name"]
                for domain_id in group.domain_ids
            ]

            # Get prefixes for this sender name
            prefixes = [p.get("emailPrefix") for p in pre_generated if p.get("emailPrefix")]

            # Determine limit based on order type
            # Hypertide accepts max 10 InboxConfigs per order
            # Hypertide internally creates 50 inboxes/domain (Entra) or 3/domain (Google)
            limit = 10 if group.order_type == InboxProviderType.ENTRA else 3

            # Get base name for fallback
            first_name = base_names[0].get("firstName", "Unknown") if base_names else "Unknown"
            last_name = base_names[0].get("lastName", "User") if base_names else "User"

            # Convert prefixes to InboxConfigs
            inbox_configs = _convert_prefixes_to_inbox_configs(
                prefixes, first_name, last_name, limit
            )

            # Build Hypertide InboxConfig objects
            ht_inbox_configs = [
                ht["InboxConfig"](
                    first_name=cfg["first_name"],
                    last_name=cfg["last_name"],
                )
                for cfg in inbox_configs
            ]

            # Build domain configs
            domain_configs = [
                ht["DomainConfig"](
                    name=dn.split('.')[0],
                    tld='.'.join(dn.split('.')[1:]) or 'com',
                    use_hypertide_domain=False,  # We're providing our own domains
                )
                for dn in domain_names
            ]

            # Build Bison credentials if provided
            bison_creds = None
            if request.bison_username and request.bison_password:
                bison_creds = ht["BisonCredentials"](
                    username=request.bison_username,
                    password=request.bison_password,
                    workspace=request.bison_workspace or "Default",
                    bison_url=request.bison_url,
                )

            # Calculate inboxes for this order
            inboxes_per_domain = 50 if group.order_type == InboxProviderType.ENTRA else 3
            expected_inboxes = len(domain_names) * inboxes_per_domain

            await _update_job_status(job_id, "executing", f"Executing Hypertide order for {len(domain_names)} {group.order_type.value} domains")

            try:
                # Create order bundle for this group
                order_type = ht["OrderType"].HYPERTIDE_ENTRA if group.order_type == InboxProviderType.ENTRA else ht["OrderType"].HYPERTIDE_GOOGLE

                # Build request for this specific order
                inbox_target = ht["InboxTarget"](
                    entra_inboxes=expected_inboxes if group.order_type == InboxProviderType.ENTRA else 0,
                    google_inboxes=expected_inboxes if group.order_type == InboxProviderType.GOOGLE else 0,
                )

                mixed_request = ht["MixedOrderRequest"](
                    client_name=request.client_name,
                    forwarding_domain=request.forwarding_domain,
                    inbox_target=inbox_target,
                    bison_credentials=bison_creds or ht["BisonCredentials"](
                        username="placeholder@email.com",
                        password="placeholder",
                        workspace="Default",
                    ),
                    users=ht_inbox_configs,
                    entra_domains=domain_configs if group.order_type == InboxProviderType.ENTRA else [],
                    google_domains=domain_configs if group.order_type == InboxProviderType.GOOGLE else [],
                    use_saved_payment=request.use_saved_payment,
                )

                # Execute purchase
                result = await ht["purchase_mixed_order"](mixed_request)

                # Record result
                for order_result in result.order_results:
                    all_results.append({
                        "success": order_result.success,
                        "order_type": group.order_type.value,
                        "quantity": 1,
                        "inboxes_created": order_result.total_inboxes,
                        "domains_created": domain_names,
                        "domain_ids": [str(d) for d in group.domain_ids],
                        "order_id": order_result.order_id,
                        "error": order_result.error_message,
                    })

            except Exception as order_error:
                logger.error(f"Order group {group_idx + 1} failed: {order_error}")
                all_results.append({
                    "success": False,
                    "order_type": group.order_type.value,
                    "quantity": 1,
                    "inboxes_created": 0,
                    "domains_created": domain_names,
                    "domain_ids": [str(d) for d in group.domain_ids],
                    "error": str(order_error),
                })

        await _update_job_status(job_id, "executing", "Updating database records")

        # Update domain infrastructure types
        workspace_id = UUID(workspace_id_str)
        for result in all_results:
            if result["success"]:
                infra_type = result["order_type"]
                domain_ids_to_update = [UUID(d) for d in result["domain_ids"]]

                # Mark domains with infrastructure type
                await execute(
                    """
                    UPDATE domains
                    SET infrastructure_type = $1,
                        infrastructure_set_at = NOW(),
                        approval_status = 'active',
                        updated_at = NOW()
                    WHERE id = ANY($2)
                    """,
                    infra_type,
                    domain_ids_to_update
                )
                logger.info(f"Marked {len(domain_ids_to_update)} domains as {infra_type}")

        # Calculate final totals
        successful_results = [r for r in all_results if r["success"]]
        total_inboxes = sum(r["inboxes_created"] for r in successful_results)
        orders_completed = len(successful_results)

        if all(r["success"] for r in all_results):
            await _update_job_status(
                job_id, "completed", "Purchase completed successfully",
                orders_completed=orders_completed,
                total_inboxes=total_inboxes,
                results=all_results,
            )
        elif any(r["success"] for r in all_results):
            await _update_job_status(
                job_id, "completed", "Purchase completed with some errors",
                orders_completed=orders_completed,
                total_inboxes=total_inboxes,
                results=all_results,
                errors=[r["error"] for r in all_results if r.get("error")],
            )
        else:
            await _update_job_status(
                job_id, "failed", "Purchase failed",
                orders_completed=0,
                results=all_results,
                errors=[r["error"] for r in all_results if r.get("error")],
            )

    except Exception as e:
        logger.error(f"Purchase V2 task failed: {e}")
        await _update_job_status(
            job_id, "failed", f"Failed: {str(e)}",
            errors=[str(e)],
        )


# =============================================================================
# Smart Order Endpoints - One-Click Provisioning
# =============================================================================

class SmartOrderRequest(BaseModel):
    """Request for smart order - auto-configures everything from database."""
    client_id: UUID
    domain_ids: list[UUID]
    provider_type: str = Field(default="entra", description="'entra' or 'google'")
    override_age_check: bool = Field(default=False, description="Allow domains younger than 30 days")
    custom_purchase: bool = Field(default=False, description="Bypass package limits, only validate domain count")
    use_worker: bool = Field(default=True, description="Use AI worker container instead of in-process Playwright")


class SmartOrderPreview(BaseModel):
    """Preview of what would be ordered - for confirmation modal."""
    # Client info (auto-populated from database)
    client_id: UUID
    client_name: str
    forwarding_domain: Optional[str]
    emailbison_workspace_id: Optional[int]

    # Sender name info
    sender_name: dict  # {firstName, lastName, prefixCount}

    # Order calculation
    provider_type: str
    domains: list[str]
    order_count: int
    inbox_count: int
    monthly_cost: float

    # Package validation
    package_usage: dict  # {used, available, withinLimit}

    # Validation
    is_valid: bool
    validation_errors: list[str] = Field(default_factory=list)


@router.get("/smart-order/preview")
async def preview_smart_order(
    client_id: UUID,
    domain_ids: str,  # Comma-separated UUIDs
    provider_type: str = "entra",
    custom_purchase: bool = False  # If True, bypasses package validation
):
    """
    Preview a smart order without executing.

    Returns all the data needed for the confirmation modal:
    - Client info (auto-populated from database)
    - Sender name info
    - Order calculation (domains, inboxes, cost)
    - Package validation (subscription limits)

    If custom_purchase=True, skips subscription validation and only validates
    domain count (2 for Entra, 5 for Google).
    """
    import json

    # Parse domain IDs
    domain_id_list = [UUID(d.strip()) for d in domain_ids.split(",") if d.strip()]

    if not domain_id_list:
        raise HTTPException(status_code=400, detail="No domain IDs provided")

    # Fetch client with workspace
    client = await fetch_one(
        """
        SELECT c.id, c.name, c.onboarding_data, c.workspace_id,
               w.emailbison_workspace_id
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

    # Get forwarding domain
    forwarding_domain = onboarding_data.get("primaryDomain") if onboarding_data else None

    # Get sender name info
    base_names = onboarding_data.get("baseSenderNames", []) if onboarding_data else []
    pre_generated = onboarding_data.get("preGeneratedSenderNames", []) if onboarding_data else []

    sender_name = {
        "firstName": base_names[0].get("firstName", "Unknown") if base_names else "Unknown",
        "lastName": base_names[0].get("lastName", "User") if base_names else "User",
        "prefixCount": len(pre_generated),
    }

    # Fetch domain names
    domain_rows = await fetch_all(
        "SELECT id, domain_name FROM domains WHERE id = ANY($1)",
        domain_id_list
    )
    domain_names = [d["domain_name"] for d in domain_rows]

    # Validate domain count
    validation_errors = []
    domain_count = len(domain_id_list)

    if provider_type == "entra":
        required = 2
        if domain_count % required != 0:
            validation_errors.append(f"Entra requires {required} domains per order. You have {domain_count} domains.")
        order_count = domain_count // required
        inbox_count = order_count * 100  # 2 domains × 50 inboxes
    else:
        required = 5
        if domain_count % required != 0:
            validation_errors.append(f"Google requires {required} domains per order. You have {domain_count} domains.")
        order_count = domain_count // required
        inbox_count = order_count * 15  # 5 domains × 3 inboxes

    monthly_cost = order_count * 50.0

    # Check subscription limits (skip if custom_purchase)
    if custom_purchase:
        # Custom purchase mode: bypass package validation, only domain count matters
        available = 0
        used = 0
        within_limit = True  # Always allow for custom purchases
    else:
        subscription = await fetch_one(
            """
            SELECT entra_packages, google_packages
            FROM client_subscriptions
            WHERE client_id = $1 AND status = 'active'
            """,
            client_id
        )

        # Count already provisioned domains
        provisioned = await fetch_one(
            """
            SELECT
                COUNT(*) FILTER (WHERE infrastructure_type = 'entra') as entra_count,
                COUNT(*) FILTER (WHERE infrastructure_type = 'google') as google_count
            FROM domains
            WHERE workspace_id = $1 AND infrastructure_type IS NOT NULL
            """,
            client.get("workspace_id")
        )

        # Calculate package usage
        if subscription:
            if provider_type == "entra":
                available = subscription.get("entra_packages", 0)
                # Each Entra order uses 2 domains, so current usage is domains / 2
                used = (provisioned.get("entra_count", 0) or 0) // 2
                within_limit = (used + order_count) <= available
            else:
                available = subscription.get("google_packages", 0)
                used = (provisioned.get("google_count", 0) or 0) // 5
                within_limit = (used + order_count) <= available

            if not within_limit:
                validation_errors.append(f"Exceeds package limit. Used: {used}, Available: {available}, Requested: {order_count}")
        else:
            available = 0
            used = 0
            within_limit = False
            validation_errors.append("No active subscription found for this client")

    # Check sender name availability
    if not pre_generated:
        validation_errors.append("No sender names configured. Set up sender names first.")

    return SmartOrderPreview(
        client_id=client_id,
        client_name=client.get("name", "Unknown"),
        forwarding_domain=forwarding_domain,
        emailbison_workspace_id=client.get("emailbison_workspace_id"),
        sender_name=sender_name,
        provider_type=provider_type,
        domains=domain_names,
        order_count=order_count,
        inbox_count=inbox_count,
        monthly_cost=monthly_cost,
        package_usage={
            "used": used,
            "available": available,
            "withinLimit": within_limit,
        },
        is_valid=len(validation_errors) == 0,
        validation_errors=validation_errors,
    )


@router.post("/smart-order")
async def execute_smart_order(
    request: SmartOrderRequest,
    background_tasks: BackgroundTasks
):
    """
    Execute a smart order - auto-configures everything from database.

    This is the simplified one-click provisioning flow:
    1. Fetches all needed data from database (client, sender names, workspace)
    2. Validates domain count and subscription limits
    3. Builds Hypertide order request automatically
    4. Executes via Hypertide automation
    5. Updates domains with infrastructure_type on success
    """
    import json

    # First, get the preview to validate
    preview = await preview_smart_order(
        client_id=request.client_id,
        domain_ids=",".join(str(d) for d in request.domain_ids),
        provider_type=request.provider_type,
        custom_purchase=request.custom_purchase
    )

    if not preview.is_valid:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Validation failed",
                "errors": preview.validation_errors
            }
        )

    # Fetch full client data
    client = await fetch_one(
        """
        SELECT c.id, c.name, c.onboarding_data, c.workspace_id,
               w.emailbison_workspace_id, w.workspace_name
        FROM clients c
        LEFT JOIN workspaces w ON c.workspace_id = w.id
        WHERE c.id = $1
        """,
        request.client_id
    )

    onboarding_data = client.get("onboarding_data")
    if isinstance(onboarding_data, str):
        onboarding_data = json.loads(onboarding_data)

    # --- Worker Mode: Create self-contained job for AI purchase worker ---
    # Global credentials (Hypertide login, Bison login, API key, Stripe) come from
    # ENV vars on the worker container — injected by MCP server's get_purchase_job().
    # Only job-specific data is stored in the DB row.
    if request.use_worker:
        # Resolve domain names
        domain_names = []
        for did in request.domain_ids:
            domain = await fetch_one("SELECT domain_name FROM domains WHERE id = $1", did)
            if domain:
                domain_names.append(domain["domain_name"])

        # Resolve sender names from onboarding data
        pre_generated = onboarding_data.get("preGeneratedSenderNames", []) if onboarding_data else []
        sender_names_json = pre_generated[:10] if pre_generated else []

        # Calculate order count
        domains_per_order = 2 if request.provider_type == "entra" else 5
        order_count = len(request.domain_ids) // domains_per_order

        # Check for domain lock conflicts before creating the job (read-only check)
        lock_conflicts = await _check_domain_lock_conflicts(request.domain_ids)
        if lock_conflicts:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Some domains are locked by existing purchase jobs",
                    "locked_domains": lock_conflicts,
                }
            )

        # Create worker job FIRST (must exist before locking domains due to FK constraint)
        job_id = str(uuid.uuid4())
        await execute(
            """
            INSERT INTO inbox_purchase_jobs (
                id, client_id, workspace_id, status, provider_type,
                domain_ids, domain_names, orders_total, order_count,
                override_age_check, custom_purchase,
                worker_mode, company_name, forwarding_domain,
                bison_workspace_name,
                sender_names, use_saved_payment,
                created_at
            ) VALUES (
                $1, $2, $3, 'pending', $4,
                $5, $6, $7, $8,
                $9, $10,
                'worker', $11, $12,
                $13,
                $14, TRUE,
                NOW()
            )
            """,
            UUID(job_id),
            request.client_id,
            client.get("workspace_id"),
            request.provider_type,
            request.domain_ids,
            domain_names,
            order_count,
            order_count,
            request.override_age_check,
            request.custom_purchase,
            client.get("name", "Unknown"),
            onboarding_data.get("primaryDomain", "") if onboarding_data else "",
            client.get("workspace_name") or "Charm",
            json.dumps(sender_names_json),
        )

        # Lock domains for this job (FK constraint satisfied — job now exists)
        await _lock_domains_for_job(job_id, request.domain_ids)

        return PurchaseJobResponse(
            job_id=job_id,
            client_id=request.client_id,
            status=OrderStatus.PENDING,
            message=f"Purchase job queued for AI worker. {order_count} order(s), {len(domain_names)} domains.",
            estimated_duration_seconds=order_count * 180,
        )

    # --- Existing V2 Path (in-process Playwright) ---

    # Build order groups
    base_names = onboarding_data.get("baseSenderNames", [])
    pre_generated = onboarding_data.get("preGeneratedSenderNames", [])

    # Calculate order groups
    domain_ids = request.domain_ids
    if request.provider_type == "entra":
        domains_per_order = 2
    else:
        domains_per_order = 5

    order_groups = []
    for i in range(0, len(domain_ids), domains_per_order):
        group_domains = domain_ids[i:i + domains_per_order]
        if len(group_domains) == domains_per_order:
            order_groups.append(OrderGroup(
                order_type=InboxProviderType(request.provider_type),
                domain_ids=group_domains,
                domain_names=[],  # Will be populated by execute-v2
                sender_name_id="name-0",  # Use primary sender name
            ))

    # Build V2 request
    v2_request = ExecutePurchaseV2Request(
        client_id=request.client_id,
        client_name=client.get("name", "Unknown"),
        forwarding_domain=onboarding_data.get("primaryDomain", ""),
        order_groups=order_groups,
        override_age_check=request.override_age_check,
        bison_workspace=str(client.get("emailbison_workspace_id", "")),
        use_saved_payment=True,
    )

    # Use existing V2 execute endpoint logic
    return await execute_purchase_v2(v2_request, background_tasks)
