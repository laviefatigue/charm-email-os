"""
Domain Purchase Pipeline routes.

HTTP surface for the queue-driven domain acquisition pipeline. The MCP server
and the frontend both call these endpoints — there is no separate business
logic in either surface.

Flow:
    1. Caller checks workspace readiness → GET  /workspaces/{id}/readiness
    2. (Optional) price-check candidates   → POST /check-availability
                                             POST /check-bulk
    3. Enqueue purchase order              → POST /enqueue    (Gate 1)
    4. Poll status                         → GET  /jobs/{id}
                                             GET  /jobs
    5. Approve Hypertide charge            → POST /jobs/{id}/approve-charge
                                                             (Gate 2)
    6. Cancel if needed                    → POST /jobs/{id}/cancel

All endpoints require X-User-Email header (via get_current_user dependency).
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from database import execute, fetch_all, fetch_one
from deps.user import CurrentUser, get_current_user
from services.dynadot_client import DynadotClient, DynadotError
from services.purchase_guardrails import (
    EnqueueValidation,
    ReadinessReport,
    validate_enqueue,
    check_workspace_readiness,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# Request / response models
# ═══════════════════════════════════════════════════════════════════════════

class InboxUserIn(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=64)
    last_name: str = Field(..., min_length=1, max_length=64)


class EnqueuePurchaseRequest(BaseModel):
    workspace_id: UUID
    client_id: Optional[UUID] = None

    plan: str = Field(..., pattern="^(entra|google)$")
    domains: list[str] = Field(..., min_length=1, max_length=5)
    forwarding_domain: Optional[str] = Field(
        None,
        description="Overrides workspace_purchase_config.default_forwarding_domain.",
    )
    users: list[InboxUserIn] = Field(..., min_length=1)
    warmup_setup: Optional[dict] = Field(
        None,
        description="Overrides workspace_purchase_config.default_warmup_setup.",
    )
    profile_picture_link: Optional[str] = None

    # Budget envelope (per-domain Dynadot cap is $12.00 — see PRICE_ABSOLUTE_CAP_CENTS
    # in services/purchase_guardrails.py; keep these in sync)
    max_dynadot_cost_cents: int = Field(..., gt=0, le=1_200)
    max_hypertide_one_time: int = Field(0, ge=0)
    max_hypertide_monthly: int = Field(5_000, ge=0)

    priority: int = Field(0, ge=0, le=10)

    @field_validator("domains")
    @classmethod
    def domains_unique_and_clean(cls, v: list[str]) -> list[str]:
        cleaned = [d.strip().lower() for d in v]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("domains must be unique")
        for d in cleaned:
            if "." not in d or " " in d:
                raise ValueError(f"invalid domain: {d}")
        return cleaned


class EnqueueResponse(BaseModel):
    ok: bool
    order_id: Optional[UUID] = None
    projected_total_cost_cents: Optional[int] = None
    warnings: list[dict] = []
    errors: list[dict] = []


class JobItem(BaseModel):
    id: UUID
    domain_name: str
    tld: str
    status: str
    dynadot_cost_cents: Optional[int] = None
    dynadot_registered_at: Optional[str] = None
    ns_verified_at: Optional[str] = None
    hypertide_record_id: Optional[str] = None
    hypertide_status: Optional[str] = None
    hypertide_payment_status: Optional[str] = None
    error_message: Optional[str] = None


class JobDetail(BaseModel):
    id: UUID
    workspace_id: UUID
    client_id: Optional[UUID] = None
    requested_by: str
    plan: str
    forwarding_domain: str
    selected_tool: str
    stage: str
    status: str
    attempts: int
    hypertide_subscription_id: Optional[str] = None
    queued_at: Optional[str] = None
    claimed_at: Optional[str] = None
    charge_approved_at: Optional[str] = None
    charge_approved_by: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    items: list[JobItem] = []


class JobSummary(BaseModel):
    id: UUID
    workspace_id: UUID
    client_id: Optional[UUID] = None
    plan: str
    stage: str
    status: str
    item_count: int
    queued_at: Optional[str] = None
    completed_at: Optional[str] = None


class AvailabilityRequest(BaseModel):
    domain: str


class AvailabilityResponse(BaseModel):
    domain: str
    available: bool
    price_cents: Optional[int] = None
    premium: bool = False
    error: Optional[str] = None


class BulkAvailabilityRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1, max_length=50)


class BulkAvailabilityResponse(BaseModel):
    results: list[AvailabilityResponse]


class FundingForecastResponse(BaseModel):
    workspace_id: UUID
    open_orders: int
    pending_dynadot_items: int
    projected_dynadot_cents: int
    projected_hypertide_one_time_cents: int
    projected_hypertide_monthly_cents: int
    projected_total_cents: int


# ═══════════════════════════════════════════════════════════════════════════
# Readiness
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/workspaces/{workspace_id}/readiness",
    response_model=ReadinessReport,
    summary="Check if a workspace can accept purchase orders",
)
async def readiness_endpoint(
    workspace_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> ReadinessReport:
    return await check_workspace_readiness(workspace_id)


# ═══════════════════════════════════════════════════════════════════════════
# Funding forecast
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/workspaces/{workspace_id}/funding-forecast",
    response_model=FundingForecastResponse,
    summary="Projected worst-case cost to drain pending orders for a workspace",
)
async def funding_forecast_endpoint(
    workspace_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> FundingForecastResponse:
    row = await fetch_one(
        """
        SELECT workspace_id,
               COALESCE(open_orders, 0) AS open_orders,
               COALESCE(pending_dynadot_items, 0) AS pending_dynadot_items,
               COALESCE(projected_dynadot_cents, 0) AS projected_dynadot_cents,
               COALESCE(projected_hypertide_one_time_cents, 0) AS projected_hypertide_one_time_cents,
               COALESCE(projected_hypertide_monthly_cents, 0) AS projected_hypertide_monthly_cents
        FROM v_pipeline_funding_forecast
        WHERE workspace_id = $1
        """,
        workspace_id,
    )
    if not row:
        return FundingForecastResponse(
            workspace_id=workspace_id,
            open_orders=0,
            pending_dynadot_items=0,
            projected_dynadot_cents=0,
            projected_hypertide_one_time_cents=0,
            projected_hypertide_monthly_cents=0,
            projected_total_cents=0,
        )
    total = (
        int(row["projected_dynadot_cents"])
        + int(row["projected_hypertide_one_time_cents"])
        + int(row["projected_hypertide_monthly_cents"])
    )
    return FundingForecastResponse(
        workspace_id=workspace_id,
        open_orders=int(row["open_orders"]),
        pending_dynadot_items=int(row["pending_dynadot_items"]),
        projected_dynadot_cents=int(row["projected_dynadot_cents"]),
        projected_hypertide_one_time_cents=int(row["projected_hypertide_one_time_cents"]),
        projected_hypertide_monthly_cents=int(row["projected_hypertide_monthly_cents"]),
        projected_total_cents=total,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Availability checks (Dynadot proxy, sync)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/check-availability",
    response_model=AvailabilityResponse,
    summary="Check one domain's Dynadot availability + price",
)
async def check_availability_endpoint(
    payload: AvailabilityRequest,
    user: CurrentUser = Depends(get_current_user),
) -> AvailabilityResponse:
    try:
        async with DynadotClient() as dd:
            result = await dd.check_availability(payload.domain)
    except DynadotError as e:
        raise HTTPException(status_code=502, detail=f"Dynadot error: {e}")
    return AvailabilityResponse(**result.model_dump())


@router.post(
    "/check-bulk",
    response_model=BulkAvailabilityResponse,
    summary="Check availability + price for up to 50 domains in parallel",
)
async def check_bulk_endpoint(
    payload: BulkAvailabilityRequest,
    user: CurrentUser = Depends(get_current_user),
) -> BulkAvailabilityResponse:
    import asyncio
    try:
        async with DynadotClient() as dd:
            results = await asyncio.gather(
                *[dd.check_availability(d) for d in payload.domains],
                return_exceptions=True,
            )
    except DynadotError as e:
        raise HTTPException(status_code=502, detail=f"Dynadot error: {e}")

    out = []
    for domain, r in zip(payload.domains, results):
        if isinstance(r, Exception):
            out.append(AvailabilityResponse(domain=domain, available=False, error=str(r)))
        else:
            out.append(AvailabilityResponse(**r.model_dump()))
    return BulkAvailabilityResponse(results=out)


# ═══════════════════════════════════════════════════════════════════════════
# Enqueue (Gate 1)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/enqueue",
    response_model=EnqueueResponse,
    summary="Create a purchase order (Gate 1). Worker claims it for execution.",
)
async def enqueue_endpoint(
    payload: EnqueuePurchaseRequest,
    user: CurrentUser = Depends(get_current_user),
) -> EnqueueResponse:
    # Validate
    validation = await validate_enqueue(
        workspace_id=payload.workspace_id,
        domain_names=payload.domains,
        max_dynadot_cost_cents=payload.max_dynadot_cost_cents,
        max_hypertide_one_time=payload.max_hypertide_one_time,
        max_hypertide_monthly=payload.max_hypertide_monthly,
    )
    if not validation.ok:
        return EnqueueResponse(
            ok=False,
            errors=[f.model_dump() for f in validation.errors],
            warnings=[f.model_dump() for f in validation.warnings],
        )

    # Resolve forwarding_domain and warmup_setup with workspace fallbacks
    cfg = await fetch_one(
        """
        SELECT default_forwarding_domain, default_warmup_setup
        FROM workspace_purchase_config
        WHERE workspace_id = $1
        """,
        payload.workspace_id,
    )
    forwarding_domain = payload.forwarding_domain or (cfg and cfg["default_forwarding_domain"])
    if not forwarding_domain:
        return EnqueueResponse(
            ok=False,
            errors=[{
                "code": "NO_FORWARDING_DOMAIN",
                "severity": "error",
                "field": "forwarding_domain",
                "message": (
                    "No forwarding_domain provided and workspace has no "
                    "default_forwarding_domain configured."
                ),
                "suggested_fix": (
                    "Pass forwarding_domain in the request OR set "
                    "workspace_purchase_config.default_forwarding_domain."
                ),
            }],
        )

    warmup_setup = payload.warmup_setup or (cfg and cfg["default_warmup_setup"]) or {
        "enabled": True,
        "settings": {"warmup_limit": 5, "warmup_reply_rate": 100, "warmup_increment": 1},
    }

    requested_by = user.email or "unknown"
    users_json = json.dumps([u.model_dump() for u in payload.users])
    warmup_json = json.dumps(warmup_setup) if not isinstance(warmup_setup, str) else warmup_setup

    # Insert order + items in one transaction
    from database import get_connection
    async with get_connection() as conn:
        async with conn.transaction():
            order_row = await conn.fetchrow(
                """
                INSERT INTO domain_pipeline_queue (
                    workspace_id, client_id, requested_by,
                    plan, forwarding_domain, selected_tool,
                    users, warmup_setup, profile_picture_link,
                    max_dynadot_cost_cents, max_hypertide_one_time, max_hypertide_monthly,
                    priority
                ) VALUES (
                    $1, $2, $3,
                    $4, $5, 'bison',
                    $6::jsonb, $7::jsonb, $8,
                    $9, $10, $11,
                    $12
                )
                RETURNING id
                """,
                payload.workspace_id, payload.client_id, requested_by,
                payload.plan, forwarding_domain,
                users_json, warmup_json, payload.profile_picture_link,
                payload.max_dynadot_cost_cents, payload.max_hypertide_one_time, payload.max_hypertide_monthly,
                payload.priority,
            )
            order_id = order_row["id"]

            # Insert items. If any conflicts with the live-attempt unique
            # index, the whole transaction rolls back and we return an error.
            try:
                for domain in payload.domains:
                    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
                    await conn.execute(
                        """
                        INSERT INTO domain_pipeline_items (order_id, domain_name, tld)
                        VALUES ($1, $2, $3)
                        """,
                        order_id, domain, tld,
                    )
            except Exception as e:
                # asyncpg UniqueViolationError is a likely case — the guardrail
                # catches it at validation time but a race is possible.
                logger.warning(f"Item insert conflict for order {order_id}: {e}")
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Concurrent enqueue detected for one of the domains: {e}. "
                        "Retry with check-availability to confirm current state."
                    ),
                )

    projected = (
        payload.max_dynadot_cost_cents * len(payload.domains)
        + payload.max_hypertide_one_time
        + payload.max_hypertide_monthly
    )
    logger.info(
        f"Enqueued purchase order {order_id}: workspace={payload.workspace_id} "
        f"plan={payload.plan} domains={payload.domains} requested_by={requested_by}"
    )
    return EnqueueResponse(
        ok=True,
        order_id=order_id,
        projected_total_cost_cents=projected,
        warnings=[f.model_dump() for f in validation.warnings],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Job status
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/jobs",
    response_model=list[JobSummary],
    summary="List purchase orders with optional filters",
)
async def list_jobs_endpoint(
    workspace_id: Optional[UUID] = Query(None),
    client_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
) -> list[JobSummary]:
    conditions = []
    args: list = []
    if workspace_id is not None:
        args.append(workspace_id)
        conditions.append(f"q.workspace_id = ${len(args)}")
    if client_id is not None:
        args.append(client_id)
        conditions.append(f"q.client_id = ${len(args)}")
    if status is not None:
        args.append(status)
        conditions.append(f"q.status = ${len(args)}")
    if stage is not None:
        args.append(stage)
        conditions.append(f"q.stage = ${len(args)}")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    args.append(limit)
    limit_placeholder = f"${len(args)}"

    rows = await fetch_all(
        f"""
        SELECT q.id, q.workspace_id, q.client_id, q.plan, q.stage, q.status,
               q.queued_at, q.completed_at,
               COUNT(i.id) AS item_count
        FROM domain_pipeline_queue q
        LEFT JOIN domain_pipeline_items i ON i.order_id = q.id
        {where}
        GROUP BY q.id
        ORDER BY q.queued_at DESC
        LIMIT {limit_placeholder}
        """,
        *args,
    )
    return [
        JobSummary(
            id=r["id"],
            workspace_id=r["workspace_id"],
            client_id=r["client_id"],
            plan=r["plan"],
            stage=r["stage"],
            status=r["status"],
            item_count=int(r["item_count"]),
            queued_at=r["queued_at"].isoformat() if r["queued_at"] else None,
            completed_at=r["completed_at"].isoformat() if r["completed_at"] else None,
        )
        for r in rows
    ]


@router.get(
    "/jobs/{order_id}",
    response_model=JobDetail,
    summary="Get one purchase order with all its per-domain items",
)
async def get_job_endpoint(
    order_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> JobDetail:
    order = await fetch_one(
        """
        SELECT id, workspace_id, client_id, requested_by, plan,
               forwarding_domain, selected_tool, stage, status, attempts,
               hypertide_subscription_id,
               queued_at, claimed_at, charge_approved_at, charge_approved_by,
               completed_at, error_message
        FROM domain_pipeline_queue
        WHERE id = $1
        """,
        order_id,
    )
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    items = await fetch_all(
        """
        SELECT id, domain_name, tld, status,
               dynadot_cost_cents, dynadot_registered_at, ns_verified_at,
               hypertide_record_id, hypertide_status, hypertide_payment_status,
               error_message
        FROM domain_pipeline_items
        WHERE order_id = $1
        ORDER BY domain_name
        """,
        order_id,
    )
    return JobDetail(
        id=order["id"],
        workspace_id=order["workspace_id"],
        client_id=order["client_id"],
        requested_by=order["requested_by"],
        plan=order["plan"],
        forwarding_domain=order["forwarding_domain"],
        selected_tool=order["selected_tool"],
        stage=order["stage"],
        status=order["status"],
        attempts=int(order["attempts"]),
        hypertide_subscription_id=order["hypertide_subscription_id"],
        queued_at=order["queued_at"].isoformat() if order["queued_at"] else None,
        claimed_at=order["claimed_at"].isoformat() if order["claimed_at"] else None,
        charge_approved_at=order["charge_approved_at"].isoformat() if order["charge_approved_at"] else None,
        charge_approved_by=order["charge_approved_by"],
        completed_at=order["completed_at"].isoformat() if order["completed_at"] else None,
        error_message=order["error_message"],
        items=[
            JobItem(
                id=i["id"],
                domain_name=i["domain_name"],
                tld=i["tld"],
                status=i["status"],
                dynadot_cost_cents=i["dynadot_cost_cents"],
                dynadot_registered_at=i["dynadot_registered_at"].isoformat() if i["dynadot_registered_at"] else None,
                ns_verified_at=i["ns_verified_at"].isoformat() if i["ns_verified_at"] else None,
                hypertide_record_id=i["hypertide_record_id"],
                hypertide_status=i["hypertide_status"],
                hypertide_payment_status=i["hypertide_payment_status"],
                error_message=i["error_message"],
            )
            for i in items
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Gate 2 — approve Hypertide charge
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/jobs/{order_id}/approve-charge",
    summary="Approve Gate 2 charge. Worker will advance awaiting_charge → hypertide_charge.",
)
async def approve_charge_endpoint(
    order_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    order = await fetch_one(
        "SELECT stage, status FROM domain_pipeline_queue WHERE id = $1",
        order_id,
    )
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    if order["stage"] != "awaiting_charge":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Order is at stage '{order['stage']}', not 'awaiting_charge'. "
                "Gate 2 approval only valid for orders waiting at Hypertide payment step."
            ),
        )

    approver = user.email or "unknown"
    await execute(
        """
        UPDATE domain_pipeline_queue
        SET stage = 'hypertide_charge',
            status = 'pending',
            charge_approved_at = NOW(),
            charge_approved_by = $2
        WHERE id = $1
        """,
        order_id, approver,
    )
    logger.info(f"Gate 2 approved for order {order_id} by {approver}")
    return {"ok": True, "order_id": str(order_id), "approved_by": approver}


# ═══════════════════════════════════════════════════════════════════════════
# Cancel
# ═══════════════════════════════════════════════════════════════════════════

class CancelRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


@router.post(
    "/jobs/{order_id}/cancel",
    summary="Mark a purchase order as dead. Worker will skip it.",
)
async def cancel_endpoint(
    order_id: UUID,
    payload: CancelRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    order = await fetch_one(
        "SELECT stage, status FROM domain_pipeline_queue WHERE id = $1",
        order_id,
    )
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    if order["status"] in ("complete", "dead"):
        raise HTTPException(
            status_code=409,
            detail=f"Order already terminal (status={order['status']}).",
        )

    canceller = user.email or "unknown"
    # Items are marked dead too so the domain names become re-enqueueable.
    from database import get_connection
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE domain_pipeline_queue
                SET status = 'dead',
                    completed_at = NOW(),
                    error_message = $2
                WHERE id = $1
                """,
                order_id,
                f"Cancelled by {canceller}: {payload.reason}",
            )
            await conn.execute(
                """
                UPDATE domain_pipeline_items
                SET status = 'dead',
                    error_message = COALESCE(error_message, '') || $2,
                    updated_at = NOW()
                WHERE order_id = $1 AND status NOT IN ('provisioned')
                """,
                order_id,
                f" [order cancelled by {canceller}]",
            )
    logger.info(f"Order {order_id} cancelled by {canceller}: {payload.reason}")
    return {"ok": True, "order_id": str(order_id)}
