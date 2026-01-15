"""
Inbox Purchasing Routes - HyperTide automation integration.

Provides endpoints for:
- Calculating optimal order quantities
- Generating inbox names
- Executing purchases via HyperTide browser automation
- Tracking purchase job status
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
import logging
import sys
import uuid
import asyncio
import random
from pathlib import Path
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
)

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory job storage (in production, use Redis or database)
_purchase_jobs: dict[str, dict] = {}


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

    # Store job info
    _purchase_jobs[job_id] = {
        "job_id": job_id,
        "client_id": str(request.client_id),
        "status": OrderStatus.PENDING,
        "request": request.model_dump(),
        "breakdown": {
            "entra_orders": breakdown.entra_orders,
            "google_orders": breakdown.google_orders,
            "total_orders": breakdown.entra_orders + breakdown.google_orders,
            "total_inboxes": breakdown.total_inboxes,
        },
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "results": [],
        "errors": [],
        "current_step": "Initializing",
    }

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
    job = _purchase_jobs.get(job_id)
    if not job:
        return

    try:
        job["status"] = OrderStatus.EXECUTING
        job["current_step"] = "Preparing order request"

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
        job["current_step"] = "Creating HyperTide order request"

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
        job["current_step"] = "Executing HyperTide purchase automation"

        result = await ht["purchase_mixed_order"](mixed_request)

        # Process results
        job["current_step"] = "Processing results"

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

        job["results"] = order_results
        job["total_inboxes"] = result.total_inboxes
        job["total_monthly_capacity"] = result.total_monthly_capacity

        if result.success:
            job["status"] = OrderStatus.COMPLETED
            job["current_step"] = "Purchase completed successfully"
        else:
            job["status"] = OrderStatus.FAILED
            job["errors"] = result.errors
            job["current_step"] = "Purchase completed with errors"

        job["completed_at"] = datetime.now(timezone.utc)

    except Exception as e:
        logger.error(f"Purchase task failed: {e}")
        job["status"] = OrderStatus.FAILED
        job["errors"].append(str(e))
        job["current_step"] = f"Failed: {str(e)}"
        job["completed_at"] = datetime.now(timezone.utc)


@router.get("/status/{job_id}", response_model=PurchaseStatusResponse)
async def get_purchase_status(job_id: str):
    """
    Get status of a purchase job.

    Poll this endpoint to track progress of a purchase initiated via /execute.
    """
    job = _purchase_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Purchase job not found")

    # Convert results to response format
    results = None
    if job.get("results"):
        results = [
            OrderResultResponse(
                success=r["success"],
                order_type=r["order_type"],
                quantity=r["quantity"],
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
        orders_completed=len([r for r in job.get("results", []) if r.get("success")]),
        orders_total=breakdown.get("total_orders", 0),
        results=results,
        total_inboxes=job.get("total_inboxes", 0),
        total_monthly_capacity=job.get("total_monthly_capacity", 0),
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        errors=job.get("errors", []),
    )


@router.delete("/jobs/{job_id}")
async def cancel_purchase_job(job_id: str):
    """
    Cancel or clean up a purchase job.

    Note: Cannot cancel in-progress HyperTide automation.
    This only removes the job from tracking.
    """
    if job_id not in _purchase_jobs:
        raise HTTPException(status_code=404, detail="Purchase job not found")

    job = _purchase_jobs[job_id]

    if job["status"] == OrderStatus.EXECUTING:
        return {
            "message": "Cannot cancel in-progress purchase. HyperTide automation must complete.",
            "status": job["status"],
        }

    del _purchase_jobs[job_id]
    return {"message": "Purchase job removed", "job_id": job_id}


@router.get("/jobs")
async def list_purchase_jobs(
    client_id: Optional[str] = None,
    status: Optional[OrderStatus] = None,
):
    """
    List purchase jobs, optionally filtered by client or status.
    """
    jobs = list(_purchase_jobs.values())

    if client_id:
        jobs = [j for j in jobs if j["client_id"] == client_id]

    if status:
        jobs = [j for j in jobs if j["status"] == status]

    return {
        "jobs": [
            {
                "job_id": j["job_id"],
                "client_id": j["client_id"],
                "status": j["status"],
                "current_step": j.get("current_step"),
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
            }
            for j in jobs
        ],
        "total": len(jobs),
    }
