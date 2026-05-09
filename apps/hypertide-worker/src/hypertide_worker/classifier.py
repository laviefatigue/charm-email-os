"""Decision-tree classification for HT records.

Single source of truth for:
  - Is this record currently being billed by HT?
  - What's its high-level state?
  - What action (if any) does it imply?

Rules captured here mirror the catalog in docs/integrations/hypertide-api.md
"Cancellation state signals". Test coverage in tests/test_classifier.py
should exercise every branch.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class HTState(str, Enum):
    """High-level state of a Hypertide record."""

    LIVE = "live"                          # Done, no cancellation
    IN_FLIGHT = "in_flight"                # Todo / In progress
    SCHEDULED_CANCEL = "scheduled_cancel"  # full_subscription or partial_product
    CANCELLED = "cancelled"                # cancellationType in (cancelled, executed)
    DRIFT = "drift"                        # NPC + Stripe active (cancellationType=unknown)
    NPC_NONE = "npc_none"                  # NPC + no cancel signal (vendor anomaly)
    OTHER = "other"                        # unexpected combinations


CANCELLED_TYPES = {"cancelled", "executed"}
SCHEDULED_TYPES = {"full_subscription", "partial_product", "partial", "cancelling"}


@dataclass(frozen=True)
class Classification:
    state: HTState
    is_subscribed: bool                    # is HT still billing right now?
    is_to_be_cancelled: bool               # has a cancel been queued?
    rationale: str


def classify(ht_record: dict[str, Any], revert_record: dict[str, Any] | None) -> Classification:
    """
    Apply the decision tree to a single HT order + (optional) verify-revert
    record. Returns a Classification dataclass that downstream consumers can
    branch on.

    Inputs:
      ht_record    — dict from /orders/active (status, paymentStatus, etc.)
      revert_record — dict from verify-revert for the same recordId, or None
                      if not yet fetched. None means we treat as no cancel
                      info (state inferred from status alone).
    """
    status = (ht_record.get("status") or "").strip()
    cancellation_type = (revert_record or {}).get("cancellationType") or "none"
    current_status = (revert_record or {}).get("currentStatus") or ""
    to_be_cancelled = bool((revert_record or {}).get("toBeCancelled", False))

    is_subscribed = cancellation_type not in CANCELLED_TYPES

    # Cancelled (terminal) — wins regardless of status field.
    if cancellation_type in CANCELLED_TYPES:
        return Classification(
            state=HTState.CANCELLED,
            is_subscribed=False,
            is_to_be_cancelled=False,
            rationale=f"cancellationType={cancellation_type}",
        )

    # Scheduled cancel — still subscribed but flagged.
    if cancellation_type in SCHEDULED_TYPES:
        return Classification(
            state=HTState.SCHEDULED_CANCEL,
            is_subscribed=True,
            is_to_be_cancelled=True,
            rationale=f"cancellationType={cancellation_type}, currentStatus={current_status!r}",
        )

    # Drift — HT thinks NPC, Stripe says active.
    if cancellation_type == "unknown":
        return Classification(
            state=HTState.DRIFT,
            is_subscribed=True,
            is_to_be_cancelled=False,
            rationale=(
                f"cancellationType=unknown (HT says NPC, Stripe says {current_status!r}); "
                "vendor data inconsistency"
            ),
        )

    # NPC + cancellationType=none — undocumented vendor state.
    if status == "NPC" and cancellation_type == "none":
        return Classification(
            state=HTState.NPC_NONE,
            is_subscribed=False,            # treat as not billing — Stripe link is gone
            is_to_be_cancelled=False,
            rationale="status=NPC + cancellationType=none (vendor post-cancellation residue)",
        )

    # Live (Done) — fully active.
    if status == "Done":
        return Classification(
            state=HTState.LIVE,
            is_subscribed=True,
            is_to_be_cancelled=to_be_cancelled,
            rationale="status=Done, cancellationType=none",
        )

    # In-flight (Todo / In progress) — order being provisioned.
    if status in ("Todo", "In progress"):
        return Classification(
            state=HTState.IN_FLIGHT,
            is_subscribed=True,
            is_to_be_cancelled=False,
            rationale=f"status={status!r}",
        )

    # Catch-all.
    return Classification(
        state=HTState.OTHER,
        is_subscribed=is_subscribed,
        is_to_be_cancelled=to_be_cancelled,
        rationale=(
            f"Unexpected status={status!r}, cancellationType={cancellation_type!r}, "
            f"currentStatus={current_status!r}"
        ),
    )


def expected_inbox_count(payment_status: str | None) -> int | None:
    """
    Map HT payment_status to expected inbox count.

    Empirical observations from production fleet (2026-05-06):
      - 'Paid'       → 52 (Microsoft Entra plan)
      - 'Google'     → 3  (Google Workspace plan, 5-domain bundles)
      - 'Google-Solo'→ 3  (Google Solo plan)

    See docs/integrations/hypertide-api.md "Undocumented enum values".
    """
    if not payment_status:
        return None
    p = payment_status.strip()
    if p == "Paid":
        return 52
    if p in ("Google", "Google-Solo"):
        return 3
    return None
