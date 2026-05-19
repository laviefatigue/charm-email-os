"""Detect HT subscription lifecycle changes between audit passes.

Step 9 of docs/plans/hypertide-data-model-and-change-tracking.md (DECISION 4).

After chs_sync.ensure_chs_rows has touched last_seen_at for every sub appearing
in the current /orders/active pass, this module:

  1. Finds chs rows whose last_seen_at predates this_audit_started_at — those
     subs didn't appear in the current pass (HT cancellation or HT API anomaly).
  2. For each, checks whether a 'cancelled' event already exists in
     hypertide_status_events since their last sighting. If yes, skip
     (already-tracked absence — no duplicate event). If no, insert a new
     'cancelled' event with a verdict joining domains.qualifies_for_cancellation_*.
  3. Detects reappearances: chs rows that have a recent 'cancelled' event but
     last_seen_at > that event's event_at — emit a 'reappeared' event.

Verdict logic (DECISION 6 join):
  - 'justified'  — any domain for this sub's client has
                   qualifies_for_cancellation_at within the last 90 days
  - 'unjustified' — no recent kill-trigger verdict on any client domain
  - 'pending'    — no domains yet linked to the client (Instantly-only client
                   whose extraction hasn't landed; can't evaluate)

The verdict-recency window (90d) is intentional. Burns from > 90d ago shouldn't
justify a brand-new cancellation event — operational rules and rule-state shift
over months (ADR-010 was 2026-05-04). A fresh burn within the prior quarter is
strong evidence; ancient burns are not.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


VERDICT_RECENCY_DAYS = 90


@dataclass
class ChangeDetectorResult:
    """Per-run counters. One entry per subscription state transition emitted."""

    candidates_examined: int = 0          # chs rows not touched this pass
    cancelled_events_written: int = 0
    reappeared_events_written: int = 0
    organization_renamed_events_written: int = 0
    skipped_already_tracked: int = 0      # cancellation already logged for this absence cycle
    verdict_justified: int = 0
    verdict_unjustified: int = 0
    verdict_pending: int = 0
    cancelled_examples: list[dict[str, Any]] = field(default_factory=list)
    unjustified_examples: list[dict[str, Any]] = field(default_factory=list)


def classify_verdict(verdict_rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """
    Pure decision: given rows of domains.qualifies_for_cancellation_*
    (already filtered to recent + this client), return (verdict, reasons).

    No DB; trivially testable.
    """
    if not verdict_rows:
        return "pending", []
    has_burn = [r for r in verdict_rows if r.get("qualifies_for_cancellation_at") is not None]
    if not has_burn:
        return "unjustified", []
    reasons = sorted({
        r["qualifies_for_cancellation_reason"]
        for r in has_burn
        if r.get("qualifies_for_cancellation_reason")
    })
    return "justified", reasons


async def detect_status_changes(
    conn: asyncpg.Connection,
    *,
    this_audit_started_at: datetime,
    active_sub_ids: set[str],
    apply: bool = False,
) -> ChangeDetectorResult:
    """
    Worker-side entrypoint. Call AFTER chs_sync has touched last_seen_at for
    every sub in active_sub_ids.

    Detection windows the caller is responsible for:
      this_audit_started_at — UTC timestamp marking the start of this audit
                              pass. Any chs.last_seen_at older than this is
                              a candidate for cancellation.

    active_sub_ids        — the set of sub_ids appearing in current
                              /orders/active. Used for the reappearance
                              detection branch (chs already in events as
                              cancelled, but now back in active).

    apply=False is read-only — populates counters, no writes.
    """
    result = ChangeDetectorResult()
    recency_floor = this_audit_started_at - timedelta(days=VERDICT_RECENCY_DAYS)

    # --- Branch 1: cancellations (chs absent from this pass) ---------------
    # Candidates are chs rows whose last_seen_at didn't get bumped this pass.
    # The first time a sub disappears we INSERT; subsequent absences are
    # skipped by the "no prior cancelled event since last_seen" guard below.
    candidates = await conn.fetch(
        """
        SELECT chs.subscription_id, chs.client_id, chs.last_seen_at,
               chs.organization_name, c.client_status, c.name AS client_name
        FROM client_hypertide_subscriptions chs
        JOIN clients c ON c.id = chs.client_id
        WHERE chs.last_seen_at < $1
        """,
        this_audit_started_at,
    )
    result.candidates_examined = len(candidates)

    for cand in candidates:
        sub_id = cand["subscription_id"]
        # Idempotency guard: if we already logged a 'cancelled' event for this
        # sub since chs.last_seen_at, this absence is already tracked — skip.
        existing = await conn.fetchrow(
            """
            SELECT 1 FROM hypertide_status_events
            WHERE subscription_id = $1
              AND event_type = 'cancelled'
              AND event_at > $2
            LIMIT 1
            """,
            sub_id,
            cand["last_seen_at"],
        )
        if existing:
            result.skipped_already_tracked += 1
            continue

        # Verdict join — domains for this sub's client whose verdict was
        # written within the recency window.
        verdict_rows_raw = await conn.fetch(
            """
            SELECT d.qualifies_for_cancellation_at, d.qualifies_for_cancellation_reason
            FROM domains d
            JOIN workspaces w ON w.id = d.workspace_id
            WHERE w.client_id = $1
              AND d.qualifies_for_cancellation_at IS NOT NULL
              AND d.qualifies_for_cancellation_at >= $2
            """,
            cand["client_id"],
            recency_floor,
        )
        verdict_rows = [dict(r) for r in verdict_rows_raw]
        verdict, reasons = classify_verdict(verdict_rows)
        if verdict == "justified":
            result.verdict_justified += 1
        elif verdict == "unjustified":
            result.verdict_unjustified += 1
        else:
            result.verdict_pending += 1

        # Count of in-scope domains for the affected client (helps operator
        # gauge blast radius without joining domains separately).
        affected = await conn.fetchval(
            """
            SELECT COUNT(*) FROM domains d
            JOIN workspaces w ON w.id = d.workspace_id
            WHERE w.client_id = $1 AND d.is_active = TRUE
            """,
            cand["client_id"],
        )

        ex = {
            "sub_id": sub_id,
            "client_name": cand["client_name"],
            "client_status": cand["client_status"],
            "verdict": verdict,
            "affected_domains": affected,
        }
        result.cancelled_examples.append(ex)
        if verdict == "unjustified":
            result.unjustified_examples.append(ex)
        result.cancelled_events_written += 1

        if apply:
            await conn.execute(
                """
                INSERT INTO hypertide_status_events
                    (subscription_id, client_id, event_type, event_at, detected_at,
                     prior_last_seen_at, verdict, verdict_reasons, affected_domain_count, notes)
                VALUES
                    ($1, $2, 'cancelled', NOW(), NOW(), $3, $4, $5, $6, $7)
                """,
                sub_id,
                cand["client_id"],
                cand["last_seen_at"],
                verdict,
                reasons,
                affected,
                f"detected by hypertide-worker audit at {this_audit_started_at.isoformat()}",
            )

    # --- Branch 2: reappearances (chs back in active after a 'cancelled' event) --
    # A sub that appears in current /orders/active AND has a 'cancelled' event
    # whose event_at predates the (now-bumped) last_seen_at is reappearing.
    # Idempotency: only emit if there's no 'reappeared' event AFTER the most
    # recent 'cancelled' event.
    if active_sub_ids:
        reappear_candidates = await conn.fetch(
            """
            SELECT chs.subscription_id, chs.client_id, chs.last_seen_at
            FROM client_hypertide_subscriptions chs
            WHERE chs.subscription_id = ANY($1::text[])
              AND EXISTS (
                  SELECT 1 FROM hypertide_status_events e
                  WHERE e.subscription_id = chs.subscription_id
                    AND e.event_type = 'cancelled'
                    AND e.event_at < chs.last_seen_at
              )
              AND NOT EXISTS (
                  SELECT 1 FROM hypertide_status_events e2
                  WHERE e2.subscription_id = chs.subscription_id
                    AND e2.event_type = 'reappeared'
                    AND e2.event_at >= (
                        SELECT MAX(e3.event_at) FROM hypertide_status_events e3
                        WHERE e3.subscription_id = chs.subscription_id
                          AND e3.event_type = 'cancelled'
                    )
              )
            """,
            list(active_sub_ids),
        )
        for ra in reappear_candidates:
            result.reappeared_events_written += 1
            if apply:
                await conn.execute(
                    """
                    INSERT INTO hypertide_status_events
                        (subscription_id, client_id, event_type, event_at, detected_at,
                         prior_last_seen_at, notes)
                    VALUES
                        ($1, $2, 'reappeared', NOW(), NOW(), $3, $4)
                    """,
                    ra["subscription_id"],
                    ra["client_id"],
                    ra["last_seen_at"],
                    f"sub returned to /orders/active; detected at {this_audit_started_at.isoformat()}",
                )

    if apply and (result.cancelled_events_written or result.reappeared_events_written):
        logger.info(
            "change_detector: wrote %d cancelled (%d justified, %d unjustified, %d pending) + %d reappeared",
            result.cancelled_events_written,
            result.verdict_justified,
            result.verdict_unjustified,
            result.verdict_pending,
            result.reappeared_events_written,
        )

    return result
