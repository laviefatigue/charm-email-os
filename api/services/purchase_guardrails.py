"""
Purchase-pipeline guardrails.

Centralizes the "is this order safe to enqueue?" logic so that the enqueue
endpoint, the worker (at claim time), and any future orchestrator all enforce
the same invariants.

The five guardrails:
    1. Workspace readiness       — config, creds, and balance present
    2. Domain idempotency        — no two live attempts for the same domain
    3. Spend cap                 — projected drain cost ≤ available budget
    4. Price sanity              — quote not >5× the recent median
    5. Rate limit                — per-workspace enqueues/hour ceiling

Each guardrail returns structured errors that callers can surface as
actionable UI / Slack messages. None of them raise on a routine failure —
raises are reserved for config-missing or DB errors.

Money safety: readiness + spend-cap MUST be re-run by the worker at claim
time, not trusted from enqueue time. Caps drift; workspaces get paused;
budgets get burned. Claim-time re-check is the belt; enqueue-time is the
suspenders.
"""

import logging
import os
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from database import fetch_all, fetch_one

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════

# Per-workspace hourly enqueue ceiling. Insane-input guard — typical real
# usage is <10/hr even at scale.
DEFAULT_RATE_LIMIT_PER_HOUR = 50

# Price sanity: reject quotes > N × median of recent registrations.
PRICE_SANITY_MULTIPLIER = 5

# Absolute ceiling for a single domain registration cost. Normal .com pricing
# at Dynadot is ~$7–10; $12 is comfortably above that while rejecting typos
# (extra zero → $120) and premium domains that should never auto-buy.
PRICE_ABSOLUTE_CAP_CENTS = 1_200  # $12.00

# How many recent items to sample when computing the median for sanity.
PRICE_SAMPLE_SIZE = 100


# ═══════════════════════════════════════════════════════════════════════════
# Report models
# ═══════════════════════════════════════════════════════════════════════════

class GuardrailFinding(BaseModel):
    """
    Structured single-issue description. `code` is machine-readable for
    callers (MCP tool, frontend) to branch on; `field` points at the input
    or DB row the user can fix; `suggested_fix` is human-readable.
    """
    code: str
    severity: str  # "error" | "warning"
    field: Optional[str] = None
    message: str
    suggested_fix: Optional[str] = None


class ReadinessReport(BaseModel):
    ready: bool
    workspace_id: UUID
    workspace_name: Optional[str] = None
    errors: list[GuardrailFinding] = []
    warnings: list[GuardrailFinding] = []
    budget_cap_cents: int = 0
    budget_spent_cents: int = 0
    budget_reserved_cents: int = 0
    budget_available_cents: int = 0


class EnqueueValidation(BaseModel):
    ok: bool
    errors: list[GuardrailFinding] = []
    warnings: list[GuardrailFinding] = []


# ═══════════════════════════════════════════════════════════════════════════
# Guardrail 1: Workspace readiness
# ═══════════════════════════════════════════════════════════════════════════

async def check_workspace_readiness(workspace_id: UUID) -> ReadinessReport:
    """
    Validate that a workspace is configured to accept purchase orders.

    Checks:
        - workspaces row exists and is_active
        - workspace_purchase_config row exists
        - purchase_cap_cents > spent_cents (budget remaining)
        - workspace_api_keys row exists (Bison API key for Hypertide payload)
        - Env vars: BISON_STANDARD_USERNAME, BISON_STANDARD_PASSWORD,
                    DYNADOT_API_KEY, HYPERTIDE_API_KEY, HYPERTIDE_API_URL

    Returns a ReadinessReport with ready=True only if there are zero errors.
    Warnings are non-blocking (e.g. "domain aging recommendation: wait N days").
    """
    errors: list[GuardrailFinding] = []
    warnings: list[GuardrailFinding] = []

    ws = await fetch_one(
        """
        SELECT w.id, w.workspace_name, w.is_active, w.emailbison_workspace_id
        FROM workspaces w
        WHERE w.id = $1
        """,
        workspace_id,
    )
    if not ws:
        errors.append(GuardrailFinding(
            code="WORKSPACE_NOT_FOUND",
            severity="error",
            field="workspace_id",
            message=f"No workspace with id {workspace_id}",
            suggested_fix="Check the workspace_id; create the workspace first if new.",
        ))
        return ReadinessReport(ready=False, workspace_id=workspace_id, errors=errors)

    if not ws["is_active"]:
        errors.append(GuardrailFinding(
            code="WORKSPACE_INACTIVE",
            severity="error",
            field="workspaces.is_active",
            message=f"Workspace '{ws['workspace_name']}' is paused.",
            suggested_fix="Reactivate the workspace before purchasing.",
        ))

    # Budget config
    cfg = await fetch_one(
        """
        SELECT purchase_cap_cents, spent_cents, auto_charge_hypertide,
               default_forwarding_domain, default_warmup_setup
        FROM workspace_purchase_config
        WHERE workspace_id = $1
        """,
        workspace_id,
    )
    cap_cents = 0
    spent_cents = 0
    if not cfg:
        errors.append(GuardrailFinding(
            code="PURCHASE_CONFIG_MISSING",
            severity="error",
            field="workspace_purchase_config",
            message="No purchase config row for this workspace.",
            suggested_fix=(
                "Insert a row into workspace_purchase_config with a "
                "purchase_cap_cents value >0."
            ),
        ))
    else:
        cap_cents = cfg["purchase_cap_cents"]
        spent_cents = cfg["spent_cents"]
        if cap_cents <= 0:
            errors.append(GuardrailFinding(
                code="NO_BUDGET",
                severity="error",
                field="workspace_purchase_config.purchase_cap_cents",
                message="Workspace has no purchase budget configured.",
                suggested_fix="Set purchase_cap_cents > 0.",
            ))

    # Bison API key per workspace (for Hypertide's tool_credentials.api_key)
    key_row = await fetch_one(
        "SELECT api_key FROM workspace_api_keys WHERE workspace_id = $1",
        workspace_id,
    )
    if not key_row or not key_row.get("api_key"):
        errors.append(GuardrailFinding(
            code="BISON_API_KEY_MISSING",
            severity="error",
            field="workspace_api_keys.api_key",
            message="No EmailBison API key on file for this workspace.",
            suggested_fix="Run workspace discovery to populate workspace_api_keys.",
        ))

    # Org-level env vars
    for var_name, description in [
        ("BISON_STANDARD_USERNAME", "Bison account username for Hypertide order payload"),
        ("BISON_STANDARD_PASSWORD", "Bison account password for Hypertide order payload"),
        ("DYNADOT_API_KEY", "Dynadot API key for domain registration"),
        ("HYPERTIDE_API_KEY", "Hypertide X-API-Key header value"),
        ("HYPERTIDE_API_URL", "Hypertide API base URL"),
    ]:
        if not os.getenv(var_name):
            errors.append(GuardrailFinding(
                code=f"ENV_{var_name}_MISSING",
                severity="error",
                field=f"env.{var_name}",
                message=f"Environment variable {var_name} is not set.",
                suggested_fix=f"Set {var_name} on the charm-api / worker deployment. ({description})",
            ))

    # Reserved = sum of max costs for all open orders on this workspace
    reserved_row = await fetch_one(
        """
        SELECT
            COALESCE(projected_dynadot_cents, 0)
            + COALESCE(projected_hypertide_one_time_cents, 0) AS reserved_cents
        FROM v_pipeline_funding_forecast
        WHERE workspace_id = $1
        """,
        workspace_id,
    )
    reserved_cents = int(reserved_row["reserved_cents"]) if reserved_row else 0
    available_cents = max(0, cap_cents - spent_cents - reserved_cents)

    return ReadinessReport(
        ready=len(errors) == 0,
        workspace_id=workspace_id,
        workspace_name=ws["workspace_name"],
        errors=errors,
        warnings=warnings,
        budget_cap_cents=cap_cents,
        budget_spent_cents=spent_cents,
        budget_reserved_cents=reserved_cents,
        budget_available_cents=available_cents,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Guardrail 2: Domain idempotency
# ═══════════════════════════════════════════════════════════════════════════

async def check_domain_idempotency(domain_names: list[str]) -> list[GuardrailFinding]:
    """
    Return a finding per domain that already has a live pipeline attempt.

    The DB's partial UNIQUE index on domain_pipeline_items enforces this at
    insert time, but we check here first so the enqueue endpoint can return
    a clean error instead of a constraint violation.
    """
    if not domain_names:
        return []

    rows = await fetch_all(
        """
        SELECT i.domain_name, i.status, q.id AS order_id, q.stage, q.workspace_id
        FROM domain_pipeline_items i
        JOIN domain_pipeline_queue q ON q.id = i.order_id
        WHERE i.domain_name = ANY($1::text[])
          AND i.status NOT IN ('dead', 'failed')
        """,
        domain_names,
    )

    findings = []
    for row in rows:
        findings.append(GuardrailFinding(
            code="DOMAIN_ALREADY_IN_PIPELINE",
            severity="error",
            field=f"domains.{row['domain_name']}",
            message=(
                f"Domain '{row['domain_name']}' already has a live purchase "
                f"attempt (order {row['order_id']}, stage={row['stage']}, "
                f"item_status={row['status']})."
            ),
            suggested_fix=(
                "Cancel the existing order first, or wait for it to complete. "
                "If the existing attempt is stuck, mark it 'dead' via admin."
            ),
        ))
    return findings


# ═══════════════════════════════════════════════════════════════════════════
# Guardrail 3: Spend cap (pre-flight)
# ═══════════════════════════════════════════════════════════════════════════

async def check_spend_cap(
    workspace_id: UUID,
    projected_cost_cents: int,
    readiness: Optional[ReadinessReport] = None,
) -> Optional[GuardrailFinding]:
    """
    Would this additional spend push the workspace over its cap?

    Call this at enqueue time with the worst-case projected cost for the
    new order (max_dynadot_cost_cents × domain_count + max_hypertide_one_time
    + max_hypertide_monthly).

    Returns None if within cap, or a GuardrailFinding otherwise.
    """
    if readiness is None:
        readiness = await check_workspace_readiness(workspace_id)

    if projected_cost_cents <= readiness.budget_available_cents:
        return None

    deficit_cents = projected_cost_cents - readiness.budget_available_cents
    return GuardrailFinding(
        code="INSUFFICIENT_BUDGET",
        severity="error",
        field="workspace_purchase_config.purchase_cap_cents",
        message=(
            f"Order requires {projected_cost_cents} cents but workspace has "
            f"only {readiness.budget_available_cents} cents available "
            f"(cap={readiness.budget_cap_cents}, "
            f"spent={readiness.budget_spent_cents}, "
            f"reserved={readiness.budget_reserved_cents})."
        ),
        suggested_fix=(
            f"Top up workspace_purchase_config.purchase_cap_cents by at least "
            f"{deficit_cents} cents (~${deficit_cents / 100:.2f}), or wait for "
            f"open orders to complete."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Guardrail 4: Price sanity
# ═══════════════════════════════════════════════════════════════════════════

async def check_price_sanity(max_dynadot_cost_cents: int) -> Optional[GuardrailFinding]:
    """
    Is the per-domain max price reasonable? Catches typos (extra zero) and
    accidental selection of premium domains.
    """
    if max_dynadot_cost_cents > PRICE_ABSOLUTE_CAP_CENTS:
        return GuardrailFinding(
            code="PRICE_ABSOLUTE_CAP",
            severity="error",
            field="max_dynadot_cost_cents",
            message=(
                f"max_dynadot_cost_cents={max_dynadot_cost_cents} exceeds "
                f"absolute cap of {PRICE_ABSOLUTE_CAP_CENTS} "
                f"(${PRICE_ABSOLUTE_CAP_CENTS / 100:.2f})."
            ),
            suggested_fix="Lower the per-domain cost ceiling, or split premium buys to manual flow.",
        )

    if max_dynadot_cost_cents <= 0:
        return GuardrailFinding(
            code="PRICE_NON_POSITIVE",
            severity="error",
            field="max_dynadot_cost_cents",
            message="max_dynadot_cost_cents must be >0.",
        )

    # Median-based sanity
    median_row = await fetch_one(
        """
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY dynadot_cost_cents) AS median
        FROM (
            SELECT dynadot_cost_cents
            FROM domain_pipeline_items
            WHERE dynadot_cost_cents IS NOT NULL
            ORDER BY dynadot_registered_at DESC NULLS LAST
            LIMIT $1
        ) recent
        """,
        PRICE_SAMPLE_SIZE,
    )
    median = median_row["median"] if median_row and median_row.get("median") else None
    if median is None:
        # No history yet — absolute cap is the only guard.
        return None

    threshold = int(Decimal(str(median)) * PRICE_SANITY_MULTIPLIER)
    if max_dynadot_cost_cents > threshold:
        return GuardrailFinding(
            code="PRICE_SANITY_OUTLIER",
            severity="warning",
            field="max_dynadot_cost_cents",
            message=(
                f"max_dynadot_cost_cents={max_dynadot_cost_cents} is "
                f"{PRICE_SANITY_MULTIPLIER}×+ the recent median of "
                f"{int(median)}. Typo or premium domain?"
            ),
            suggested_fix="Confirm this is intentional before enqueuing.",
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Guardrail 5: Rate limit
# ═══════════════════════════════════════════════════════════════════════════

async def check_rate_limit(
    workspace_id: UUID,
    limit_per_hour: int = DEFAULT_RATE_LIMIT_PER_HOUR,
) -> Optional[GuardrailFinding]:
    """
    Cap enqueues per workspace per rolling hour. Catches runaway scripts.
    """
    row = await fetch_one(
        """
        SELECT COUNT(*) AS n
        FROM domain_pipeline_queue
        WHERE workspace_id = $1
          AND queued_at > NOW() - INTERVAL '1 hour'
        """,
        workspace_id,
    )
    count = int(row["n"]) if row else 0
    if count >= limit_per_hour:
        return GuardrailFinding(
            code="RATE_LIMIT_EXCEEDED",
            severity="error",
            field="workspace_id",
            message=(
                f"Workspace has enqueued {count} orders in the past hour "
                f"(limit: {limit_per_hour})."
            ),
            suggested_fix="Wait, or raise the limit if legitimate batch load.",
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Master validator — one call, all five checks
# ═══════════════════════════════════════════════════════════════════════════

async def validate_enqueue(
    workspace_id: UUID,
    domain_names: list[str],
    max_dynadot_cost_cents: int,
    max_hypertide_one_time: int,
    max_hypertide_monthly: int,
) -> EnqueueValidation:
    """
    Run all five guardrails for a prospective order. Returns an
    EnqueueValidation with ok=True only if every error-severity check passes.
    """
    errors: list[GuardrailFinding] = []
    warnings: list[GuardrailFinding] = []

    # 1. Workspace readiness
    readiness = await check_workspace_readiness(workspace_id)
    errors.extend(readiness.errors)
    warnings.extend(readiness.warnings)

    # 2. Domain idempotency
    errors.extend(await check_domain_idempotency(domain_names))

    # 3. Spend cap (worst-case projection)
    projected = (
        max_dynadot_cost_cents * len(domain_names)
        + max_hypertide_one_time
        + max_hypertide_monthly
    )
    cap_finding = await check_spend_cap(workspace_id, projected, readiness)
    if cap_finding:
        errors.append(cap_finding)

    # 4. Price sanity
    price_finding = await check_price_sanity(max_dynadot_cost_cents)
    if price_finding:
        if price_finding.severity == "error":
            errors.append(price_finding)
        else:
            warnings.append(price_finding)

    # 5. Rate limit
    rate_finding = await check_rate_limit(workspace_id)
    if rate_finding:
        errors.append(rate_finding)

    return EnqueueValidation(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
