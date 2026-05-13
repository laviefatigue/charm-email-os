"""Backfill: align our DB to HT for the domains WE manage.

PARITY MODEL (2026-05-13 refinement):
  Our DB is the source of truth for which domains we manage. Hypertide
  has additional records for friends-and-family subscriptions outside our
  GTM work — those are vendor-side and we do not mirror them.

  Therefore backfill does NOT auto-INSERT HT-only records by default.
  Two operations only:

  1. UPDATE existing DB rows with HT state (handled by audit.py, not here)
  2. SET is_legacy=TRUE on in-scope DB rows that have no HT match
     (pre-HT or out-of-band acquired domains)

  Explicit onboarding of an HT-only workspace (e.g. if we ever want to
  bring "Ink'd" inboxes into our DB) is a separate, gated operation:
    hypertide-worker backfill --onboard-workspace 'Ink'd'

  Default `backfill` (no flag) only does the legacy flagging pass.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import asyncpg

from .classifier import classify, expected_inbox_count
from .ht_client import HypertideClient

logger = logging.getLogger(__name__)


@dataclass
class BackfillResult:
    inserted: int = 0
    is_legacy_flagged: int = 0
    workspace_assigned: int = 0
    workspace_unresolved: int = 0
    ht_only_friends_and_family: int = 0   # informational: HT records we deliberately ignore
    by_workspace: dict[str, int] = field(default_factory=dict)


async def run_backfill(
    conn: asyncpg.Connection,
    ht: HypertideClient,
    *,
    apply: bool = False,
    onboard_workspace: str | None = None,
) -> BackfillResult:
    """
    Backfill aligned to the parity model.

    Default behavior (no onboard_workspace):
      - SET is_legacy=TRUE on in-scope DB rows with no HT match
      - Count HT-only records as friends_and_family (informational only)

    With onboard_workspace='Ink\\'d' (or similar):
      - Additionally INSERT new domains rows for HT records whose inferred
        workspace matches that name, under the operator's explicit direction.
      - Use this for one-shot onboarding of an HT-managed workspace we want
        to start tracking in our DB.

    Idempotent: NOT EXISTS check on domain_name prevents duplicates. is_legacy
    flag is only set, never auto-cleared.
    """
    result = BackfillResult()
    now = datetime.now(timezone.utc)

    active = await ht.get_active_orders()
    sub_ids = sorted({o["subscriptionId"] for o in active if o.get("subscriptionId")})
    revert_records = await ht.verify_revert_per_subscription(sub_ids)
    revert_by_id = {r["recordId"]: r for r in revert_records}

    # Existing in-scope DB rows (workspace must be HT-managed).
    existing = await conn.fetch(
        """
        SELECT d.id, d.domain_name, d.workspace_id, d.hypertide_record_id, d.is_legacy
        FROM domains d
        JOIN workspaces w ON w.id = d.workspace_id
        WHERE w.manages_via_hypertide = TRUE
        """
    )
    existing_by_name: dict[str, asyncpg.Record] = {r["domain_name"].lower(): r for r in existing}

    # Workspace catalog for assignment heuristics.
    workspaces = await conn.fetch(
        """
        SELECT id, workspace_name FROM workspaces
        WHERE manages_via_hypertide = TRUE
        """
    )
    ws_by_name = {w["workspace_name"]: w["id"] for w in workspaces}

    # ----- Tally HT-only records (informational; only INSERT if explicit onboard) -----
    inserts: list[tuple[Any, ...]] = []
    for ht_rec in active:
        domain_lc = (ht_rec.get("domain") or "").lower()
        if domain_lc in existing_by_name:
            continue  # matched — audit.py handles UPDATE, not backfill
        rev = revert_by_id.get(ht_rec["id"])
        cls = classify(ht_rec, rev)
        if not cls.is_subscribed:
            # Don't onboard already-cancelled records — they'd land as is_legacy=true zombies
            result.ht_only_friends_and_family += 1
            continue

        if onboard_workspace is None:
            # Default: do not auto-INSERT. HT-only = friends-and-family, out of scope.
            result.ht_only_friends_and_family += 1
            continue

        # Explicit onboarding: only INSERT records that map to the named workspace
        ws_id = _infer_workspace_id(ht_rec, ws_by_name)
        if ws_id is None:
            result.workspace_unresolved += 1
            continue
        target_ws_name = next(
            (w["workspace_name"] for w in workspaces if w["id"] == ws_id), None
        )
        if target_ws_name != onboard_workspace:
            # In-scope HT record, but for a workspace we're not onboarding right now.
            continue
        result.workspace_assigned += 1
        result.by_workspace[target_ws_name] = result.by_workspace.get(target_ws_name, 0) + 1
        inserts.append(
            (
                ht_rec["domain"],
                ws_id,
                "purchased",                   # domain_source — CHECK ('generated','purchased','legacy')
                "active",                      # approval_status — matches existing post-activation convention
                _infer_infrastructure_type(ht_rec.get("paymentStatus")),
                True,                          # is_active
                ht_rec["id"],
                ht_rec.get("subscriptionId"),
                ht_rec.get("productId"),
                ht_rec.get("status"),
                ht_rec.get("paymentStatus"),
                ht_rec.get("sendingTool"),
                _ct_to_str(rev),
                cls.is_to_be_cancelled,
                now,
                now,
                expected_inbox_count(ht_rec.get("paymentStatus")),
            )
        )

    # ----- is_legacy flagging on DB-only rows (always runs, with or without onboarding) -----
    ht_record_domains = {(o.get("domain") or "").lower() for o in active}
    legacy_ids = [
        r["id"]
        for r in existing
        if r["domain_name"].lower() not in ht_record_domains
        and not r["is_legacy"]
    ]

    if apply:
        async with conn.transaction():
            if inserts:
                await conn.executemany(
                    """
                    INSERT INTO domains (
                        domain_name, workspace_id, domain_source, approval_status,
                        infrastructure_type, is_active,
                        hypertide_record_id, hypertide_subscription_id, hypertide_product_id,
                        hypertide_status, hypertide_payment_status, hypertide_sending_tool,
                        hypertide_cancellation_type, hypertide_to_be_cancelled,
                        hypertide_last_synced_at, hypertide_last_seen_at, expected_inbox_count
                    ) VALUES (
                        $1, $2, $3, $4,
                        $5, $6,
                        $7, $8, $9,
                        $10, $11, $12,
                        $13, $14,
                        $15, $16, $17
                    )
                    ON CONFLICT (domain_name) DO NOTHING
                    """,
                    inserts,
                )
            if legacy_ids:
                await conn.execute(
                    "UPDATE domains SET is_legacy = TRUE WHERE id = ANY($1::uuid[])",
                    legacy_ids,
                )

    result.inserted = len(inserts)
    result.is_legacy_flagged = len(legacy_ids)
    return result


def _infer_workspace_id(
    ht_rec: dict[str, Any],
    ws_by_name: dict[str, Any],
) -> Any:
    """
    Workspace assignment heuristic for explicit onboarding only.

    Priority:
      1. Domain-name suffix match: spoutwater→Spout, searchatlas→Search Atlas, etc.
      2. forwardingDomain heuristic: stablekernel.com → Stable Kernel*.
      3. Return None for operator review.

    NOTE on Stable Kernel: one HT organization maps to TWO DB workspaces
    (Stable Kernel + Stable Kernel Market Research). The forwarding-domain
    heuristic distinguishes them where possible, but the truly authoritative
    mapping happens at order-creation time when WE set workspace_id.

    Used only when --onboard-workspace is explicitly passed. Default backfill
    does not call this.
    """
    domain = (ht_rec.get("domain") or "").lower()
    fwd = (ht_rec.get("forwardingDomain") or "").lower()

    suffix_map = {
        "spoutwater": "Spout",
        "selery": "Selery",
        "searchatlas": "Search Atlas",
        "sammy": "Sammy",
        "linkgraph": "Linkgraph",
        "guardare": "Barrena",
        "hellohero": "Hello Hero",
        "spui": "SPUI",
        "rootaccess": "Root Access",
        "checkoutcomponents": "Checkout Components",
        "peaksave": "Peaksave",
        "inkdstores": "Ink'd",
        "charmgtm": "Charm",
        "hirecharm": "Charm",
    }
    for suffix, ws_name in suffix_map.items():
        if suffix in domain:
            return ws_by_name.get(ws_name)

    # Stable Kernel: one HT org, two DB workspaces. Forwarding-domain
    # heuristic narrows where possible.
    if "stablekernel.com/services/market-research" in fwd:
        return ws_by_name.get("Stable Kernel Market Research")
    if "stablekernel.com" in fwd:
        return ws_by_name.get("Stable Kernel")

    return None


def _ct_to_str(rev: dict[str, Any] | None) -> str | None:
    if rev is None:
        return None
    return rev.get("cancellationType") or "none"


def _infer_infrastructure_type(payment_status: str | None) -> str | None:
    """
    Map HT paymentStatus → domains.infrastructure_type (entra|google|NULL).

    Live CHECK constraint: infrastructure_type IS NULL OR IN ('entra','google').
    Setting this correctly avoids the legacy a/b-set view defaulting to 50
    for what is actually a 3-inbox Google domain.
    """
    if not payment_status:
        return None
    p = payment_status.strip()
    if p == "Paid":
        return "entra"
    if p in ("Google", "Google-Solo"):
        return "google"
    return None
