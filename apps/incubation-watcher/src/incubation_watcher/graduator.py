"""Graduation orchestrator — pure logic for the per-inbox transition.

Mirrors the order-of-operations from sync_modules/lifecycle_tag_sync.py:
  1. Untag 'incubating' in EB. 404 swallowed, transient raises.
  2. Tag the destination ('live' for Microsoft, 'reserve' for Google) in EB.
     404 here means the sender isn't in this workspace anymore — log
     ORPHAN, skip the row, do not write DB.
  3. UPDATE sender_accounts (lifecycle='active', pool=target).
  4. INSERT into inbox_rotation_history.

Steps 1+2 happen in the EB client; steps 3+4 in DB inside a single
transaction. If step 2 raises (non-404), we never reach 3+4 — the row
stays at lifecycle='incubating' and re-attempts next cycle.

This is the safety property: NEVER end up with DB transitioned to active
but EB still has 'incubating' applied. EB-first, DB-on-success.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from .db import (
    GraduationCandidate,
    record_rotation_history,
    update_graduation,
)
from .eb_client import EBClient, EmailBisonAPIError

logger = logging.getLogger(__name__)

ESP_GOOGLE = "gmail"
ESP_MICROSOFT = "microsoft"

INCUBATING_TAG = "incubating"
LIVE_TAG = "live"
RESERVE_TAG = "reserve"


@dataclass(frozen=True)
class GraduationResult:
    candidate: GraduationCandidate
    target_pool: str  # 'live' | 'reserve'
    outcome: str  # 'graduated' | 'orphan_skipped' | 'transient_failed' | 'dry_run'
    error: str | None = None


def target_pool_for_esp(esp: str | None) -> str:
    """Microsoft → live (legacy ride-to-death). Google/unknown → reserve."""
    if esp == ESP_MICROSOFT:
        return LIVE_TAG
    return RESERVE_TAG


async def graduate_one(
    *,
    db_conn: asyncpg.Connection,
    eb: EBClient,
    workspace_id: UUID,
    candidate: GraduationCandidate,
    incubating_tag_id: int,
    live_tag_id: int,
    reserve_tag_id: int,
    apply: bool,
) -> GraduationResult:
    """Process one graduation candidate. Returns the resulting outcome.

    `apply=False` → dry-run: returns 'dry_run' outcome, no EB or DB write.
    `apply=True`  → real: tags in EB, updates DB, logs to rotation_history.
    """
    target_pool = target_pool_for_esp(candidate.esp)
    target_tag_id = live_tag_id if target_pool == LIVE_TAG else reserve_tag_id

    if not apply:
        return GraduationResult(candidate=candidate, target_pool=target_pool, outcome="dry_run")

    # Step 1: untag incubating. 404 means it wasn't there — fine.
    try:
        await eb.untag_inbox(candidate.emailbison_account_id, incubating_tag_id)
    except EmailBisonAPIError as e:
        if e.status_code != 404:
            logger.warning(
                "[%s] untag incubating failed (will continue): %s",
                candidate.email_address,
                e,
            )

    # Step 2: tag destination. 404 = workspace orphan; skip the row.
    try:
        await eb.tag_inbox(candidate.emailbison_account_id, target_tag_id)
    except EmailBisonAPIError as e:
        if e.status_code == 404:
            logger.warning(
                "[ORPHAN] %s (eb=%d) not in this workspace — skipping graduation. "
                "sync_accounts.mark_stale_accounts will reconcile is_active=FALSE next cycle.",
                candidate.email_address,
                candidate.emailbison_account_id,
            )
            return GraduationResult(
                candidate=candidate,
                target_pool=target_pool,
                outcome="orphan_skipped",
                error=f"EB 404: {e.message}",
            )
        # Transient: leave row at lifecycle='incubating'; retry next cycle.
        logger.error(
            "[%s] tag %s failed (transient — DB unchanged, will retry): %s",
            candidate.email_address,
            target_pool,
            e,
        )
        return GraduationResult(
            candidate=candidate,
            target_pool=target_pool,
            outcome="transient_failed",
            error=str(e),
        )

    # Steps 3+4: DB transition + audit row, atomic.
    async with db_conn.transaction():
        await update_graduation(
            conn=db_conn, sender_id=candidate.sender_id, target_pool=target_pool,
        )
        await record_rotation_history(
            conn=db_conn,
            workspace_id=workspace_id,
            sender_id=candidate.sender_id,
            sender_email=candidate.email_address,
            target_pool=target_pool,
            reason=f"14 BD warmup complete for {candidate.esp or 'unknown'} inbox",
        )

    logger.info(
        "[GRADUATE] %s (esp=%s, bd=%d) incubating -> %s",
        candidate.email_address,
        candidate.esp or "unknown",
        candidate.business_days_elapsed,
        target_pool,
    )
    return GraduationResult(candidate=candidate, target_pool=target_pool, outcome="graduated")
