"""Full-fleet HT<->DB audit. Read-only by default; --apply persists changes.

The audit:
  1. Pulls /orders/active (732+ records).
  2. Walks unique subscriptionIds, calls verify-revert in sequence (rate-limited).
  3. Joins HT records to DB domains by domain_name (case-insensitive).
  4. Categorizes each pair into a decision_code.
  5. If apply=True: UPDATEs hypertide_* columns on matched DB rows.

Returns a structured AuditResult that the CLI / tests can assert on.

Note: backfill (initial INSERT of new rows) is a separate module — see
backfill.py. This audit only updates existing rows; it does not create.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import asyncpg

from .classifier import Classification, classify, expected_inbox_count
from .ht_client import HypertideClient

logger = logging.getLogger(__name__)


@dataclass
class AuditResult:
    ht_active_count: int = 0
    ht_pending_count: int = 0
    db_in_scope_count: int = 0
    matched: int = 0
    db_only: int = 0                       # rows in our DB with no HT match (potential is_legacy)
    ht_only: int = 0                       # HT records with no DB row (need INSERT via backfill)
    drift_to_be_cancelled: int = 0
    drift_cancelled_db_alive: int = 0      # HT cancelled, DB row not killed_at — concerning
    drift_ht_cancelled_inboxes_connected: int = 0   # HT cancelled BUT EB shows ≥1 connected inbox
    drift_ht_cancelled_still_sending: int = 0       # subset: any inbox with sends_24h > 0
    by_workspace: dict[str, dict[str, int]] = field(default_factory=dict)
    drift_examples: list[dict[str, Any]] = field(default_factory=list)   # representative rows
    rows_updated: int = 0
    skipped_workspaces: list[str] = field(default_factory=list)


async def run_audit(
    conn: asyncpg.Connection,
    ht: HypertideClient,
    *,
    apply: bool = False,
) -> AuditResult:
    """
    Full-fleet audit. Idempotent — re-runs are safe and overwrite hypertide_*
    columns with the latest snapshot.

    apply=False: read-only. Computes diff, updates AuditResult, no DB writes.
    apply=True:  UPDATE matched DB rows; INSERT into sync_audit_log.
    """
    result = AuditResult()
    sync_started_at = datetime.now(timezone.utc)

    # --- 1. Pull HT side ---
    logger.info("Fetching HT /orders/active...")
    active = await ht.get_active_orders()
    pending = await ht.get_pending_orders()
    result.ht_active_count = len(active)
    result.ht_pending_count = len(pending)
    logger.info("HT: %d active, %d pending", len(active), len(pending))

    sub_ids = sorted({o["subscriptionId"] for o in active if o.get("subscriptionId")})
    logger.info("Verify-revert across %d subscriptions...", len(sub_ids))
    revert_records = await ht.verify_revert_per_subscription(sub_ids)
    revert_by_id = {r["recordId"]: r for r in revert_records}

    # --- 2. Pull in-scope DB rows ---
    db_rows = await conn.fetch(
        """
        SELECT d.id, d.domain_name, d.workspace_id, w.workspace_name,
               d.killed_at, d.hypertide_record_id, d.hypertide_to_be_cancelled,
               d.is_legacy
        FROM domains d
        LEFT JOIN workspaces w ON w.id = d.workspace_id
        WHERE w.manages_via_hypertide = TRUE OR w.id IS NULL
        """
    )
    result.db_in_scope_count = len(db_rows)
    db_by_domain: dict[str, asyncpg.Record] = {
        r["domain_name"].lower(): r for r in db_rows
    }

    # --- 3. Classify each HT record ---
    matched_records: list[tuple[asyncpg.Record, dict[str, Any], Classification]] = []
    ht_only_records: list[dict[str, Any]] = []
    for ht_rec in active:
        domain_lc = (ht_rec.get("domain") or "").lower()
        db_row = db_by_domain.get(domain_lc)
        rev = revert_by_id.get(ht_rec["id"])
        cls = classify(ht_rec, rev)
        if db_row is None:
            ht_only_records.append({"ht": ht_rec, "rev": rev, "cls": cls})
        else:
            matched_records.append((db_row, ht_rec, cls))

    result.matched = len(matched_records)
    result.ht_only = len(ht_only_records)

    # --- 4. Per-workspace tallies + drift counts ---
    for db_row, ht_rec, cls in matched_records:
        ws = db_row["workspace_name"] or "<no-workspace>"
        slot = result.by_workspace.setdefault(ws, {})
        slot[cls.state.value] = slot.get(cls.state.value, 0) + 1
        if cls.is_to_be_cancelled:
            result.drift_to_be_cancelled += 1
        if cls.state.value == "cancelled" and db_row["killed_at"] is None:
            result.drift_cancelled_db_alive += 1

    # DB-only (rows we have, no HT record) — these become is_legacy candidates.
    seen_ids = {r[0]["id"] for r in matched_records}
    db_only_rows = [r for r in db_rows if r["id"] not in seen_ids]
    result.db_only = len(db_only_rows)

    # --- 4b. HT-cancelled-but-EB-connected drift detection ---
    # When HT terminates a subscription, the Microsoft/Google tenants behind
    # the inboxes don't disappear instantly — EmailBison's status stays
    # "Connected" until the next provider-side reaper runs. During that gap
    # we're using infrastructure we're no longer paying for, which is fine
    # short-term but the inboxes ARE sending mail through dead tenants. If a
    # campaign reaches a lead during this window and they bounce/complain,
    # the trail leads back to us with no live HT order to support it.
    cancelled_domain_ids = [
        db_row["id"] for (db_row, _ht, cls) in matched_records
        if not cls.is_subscribed
    ]
    if cancelled_domain_ids:
        drift_rows = await conn.fetch(
            """
            SELECT d.id, d.domain_name, w.workspace_name,
                   COUNT(*) AS total_inboxes,
                   COUNT(*) FILTER (WHERE sa.status = 'Connected') AS connected,
                   COUNT(*) FILTER (WHERE sa.status = 'Connected'
                                    AND sa.total_sends_24h > 0) AS still_sending,
                   COALESCE(SUM(sa.total_sends_24h)
                            FILTER (WHERE sa.status = 'Connected'), 0) AS sends_24h_total
            FROM domains d
            LEFT JOIN workspaces w ON w.id = d.workspace_id
            LEFT JOIN sender_accounts sa ON sa.domain_id = d.id
            WHERE d.id = ANY($1::uuid[])
            GROUP BY d.id, d.domain_name, w.workspace_name
            HAVING COUNT(*) FILTER (WHERE sa.status = 'Connected') > 0
            """,
            cancelled_domain_ids,
        )
        result.drift_ht_cancelled_inboxes_connected = len(drift_rows)
        result.drift_ht_cancelled_still_sending = sum(
            1 for r in drift_rows if r["still_sending"] > 0
        )
        # Keep top 20 most-sending examples for operator visibility
        sorted_drift = sorted(
            drift_rows, key=lambda r: r["sends_24h_total"], reverse=True
        )
        for r in sorted_drift[:20]:
            result.drift_examples.append({
                "type": "HT_CANCELLED_INBOXES_CONNECTED",
                "domain": r["domain_name"],
                "workspace": r["workspace_name"],
                "connected_inboxes": r["connected"],
                "still_sending_inboxes": r["still_sending"],
                "total_sends_24h": r["sends_24h_total"],
            })

    # --- 5. Apply phase ---
    if apply:
        result.rows_updated = await _apply_updates(conn, matched_records, sync_started_at)
        await _record_audit_run(conn, result, sync_started_at)

    return result


async def _apply_updates(
    conn: asyncpg.Connection,
    matched: list[tuple[asyncpg.Record, dict[str, Any], Classification]],
    synced_at: datetime,
) -> int:
    """
    UPDATE hypertide_* columns on matched DB rows. Single transaction.
    """
    if not matched:
        return 0

    updates = []
    for db_row, ht_rec, cls in matched:
        rev = ht_rec.get("_revert", {})  # populated by classify path? — fetch directly
        updates.append(
            (
                ht_rec["id"],
                ht_rec.get("subscriptionId"),
                ht_rec.get("productId"),
                ht_rec.get("status"),
                ht_rec.get("paymentStatus"),
                ht_rec.get("sendingTool"),
                # cancellation_type comes from classify input; rebuild from cls.rationale or pass-through.
                # For simplicity, re-derive from cls.state.
                _cancellation_type_from_classification(cls),
                cls.is_to_be_cancelled,
                synced_at,
                synced_at,
                expected_inbox_count(ht_rec.get("paymentStatus")),
                db_row["id"],
            )
        )

    async with conn.transaction():
        await conn.executemany(
            """
            UPDATE domains SET
              hypertide_record_id        = $1,
              hypertide_subscription_id  = $2,
              hypertide_product_id       = $3,
              hypertide_status           = $4,
              hypertide_payment_status   = $5,
              hypertide_sending_tool     = $6,
              hypertide_cancellation_type = $7,
              hypertide_to_be_cancelled  = $8,
              hypertide_last_synced_at   = $9,
              hypertide_last_seen_at     = $10,
              expected_inbox_count       = COALESCE(expected_inbox_count, $11)
            WHERE id = $12
            """,
            updates,
        )
    return len(updates)


def _cancellation_type_from_classification(cls: Classification) -> str:
    """Reverse-derive a stored cancellation_type from the classification result.

    We could plumb the original cancellationType through the audit instead,
    but the state taxonomy carries the same information at the granularity we need.
    """
    if cls.state.value == "cancelled":
        return "cancelled"
    if cls.state.value == "scheduled_cancel":
        return "full_subscription"  # simplification: distinct partial_product not surfaced here
    if cls.state.value == "drift":
        return "unknown"
    return "none"


async def _record_audit_run(
    conn: asyncpg.Connection,
    result: AuditResult,
    started_at: datetime,
) -> None:
    """Append a row to sync_audit_log summarizing this run."""
    await conn.execute(
        """
        INSERT INTO sync_audit_log
            (id, sync_type, started_at, completed_at, status,
             records_processed, records_updated, metadata)
        VALUES
            (gen_random_uuid(), 'hypertide_audit', $1, NOW(), 'completed',
             $2, $3, $4::jsonb)
        """,
        started_at,
        result.matched,
        result.rows_updated,
        _to_metadata_json(result),
    )


def _to_metadata_json(result: AuditResult) -> str:
    """Serialize summary into the metadata JSONB field."""
    import json
    return json.dumps(
        {
            "ht_active_count": result.ht_active_count,
            "ht_pending_count": result.ht_pending_count,
            "db_in_scope_count": result.db_in_scope_count,
            "matched": result.matched,
            "db_only": result.db_only,
            "ht_only": result.ht_only,
            "drift_to_be_cancelled": result.drift_to_be_cancelled,
            "drift_cancelled_db_alive": result.drift_cancelled_db_alive,
            "drift_ht_cancelled_inboxes_connected": result.drift_ht_cancelled_inboxes_connected,
            "drift_ht_cancelled_still_sending": result.drift_ht_cancelled_still_sending,
            "drift_examples": result.drift_examples,
            "by_workspace": result.by_workspace,
        }
    )
