"""
Daily reconciliation audit for the 2026-04-27 tagging-kill overhaul.

Runs once per day, scans the fleet for the three failure modes that
caused the overhaul, and posts a Slack summary if any are present.

Detected anomalies
──────────────────
1. Likely dual-tag inboxes
     graduated reserve-pool inboxes that may still carry an orphan
     `live` tag in EmailBison from the pre-overhaul graduation bug.
     The set_tag_sync reconciling untag should drain these to zero
     within a sync cycle of deployment; this audit verifies the drain.

2. Warmup disabled silently
     active live inboxes whose `warmup_enabled` flipped to FALSE while
     they were in active sending. Migration 094's trigger records the
     flip in `warmup_disabled_at`; this audit alerts on inboxes that
     have been silently un-warmed for over 24h.

2b. Kill queue stuck pending
     kill_queue rows that have been in `pending` status for over 2h.
     The kill_processor runs every 15 min so this should normally be 0.
     Replaces the pre-ADR-007 `pool_warning` metric — that flagged
     inboxes in the indefinite warning soft-pause state, which no longer
     exists. Stuck-pending kills are the new "watch this" signal.

2c. Flagged but alive in DB
     kill_queue rows with status='flagged' for inboxes that still have
     `inbox_state='live'` and `killed_at IS NULL`. This is the legacy
     bug class that motivated migration 099 — it occurs when the OLD
     kill_processor (pre-overhaul) tagged in EB but failed to update
     the DB. The current code path is DB-first inside a single try
     block, so this should be 0 in steady state. Migration 099 narrows
     the dedup index so existing flagged-but-alive rows no longer
     block legit new kills, but having any drift here means something
     reverted an inbox after kill_processor marked it dead. Investigate.

2d. Stuck active + null pool
     inboxes with `lifecycle='active'` AND `pool=NULL` AND on a
     non-burned/cancelled domain. Should be 0 — graduations land in
     reserve or deployed, kills land in dead, and the sync_accounts
     self-heal branch (added post-mig-098 bug) defaults active+NULL
     to 'reserve' on next upsert. Drift here means the self-heal
     missed a path or someone manually set NULL on an active inbox
     without a real reason. Surfaces inboxes in operational limbo
     (alive but not deployable, not killable until 20-send floor met).

3. Orphan `is_active=FALSE` graduated inboxes
     inboxes with `inbox_state='live'`, `is_active=FALSE`, and a real
     `emailbison_account_id`. These are invisible to all sync paths
     (every fetch query filters by `is_active=TRUE`) but EB may still
     be sending through them. Phase 0 measured 2,807 of these; the
     daily count surfaces drift.

4. Stuck-in-incubation past 14 BD
     inboxes still `inventory_lifecycle_status='incubating'` after the
     14 business-day graduation window has elapsed (per migration 094's
     `warmup_enabled_since`). Should be zero post-deploy; non-zero
     suggests `lifecycle_tag_sync` isn't running or graduation SQL is
     filtering them out incorrectly.

5. Incubating inboxes assigned to active EB campaigns
     bypass guard for the Stable Kernel ODSC pattern (2026-04-28),
     where ops assigned incubating inboxes to a real campaign before
     the 14 BD graduation window completed. These will be sending
     production volume from un-warmed reputations. Surfaces only
     while still `incubating` — promoted/dead/graduated inboxes drop
     out automatically once the bypass is reconciled.

6. Burned-domain inboxes still assigned to active EB campaigns
     reputation risk: domains marked `pool_status='burned'` (or
     `cancelled`) shouldn't be sending. Per Rule C7 we don't
     auto-kill connected inboxes, but we should flag them so the
     team removes them from EB campaigns. Until an auto-cleanup
     function is built (TODO: see plan doc), this audit + manual
     EB cleanup is the loop closure.

Output
──────
A single Slack message with section blocks per anomaly. If all counts
are zero we send a confirmation only on the first run of each week
(reduces noise).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

import asyncpg

from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter

logger = logging.getLogger(__name__)


class OverhaulAuditModule:
    """
    Daily audit pass for the post-2026-04-27 tagging-kill model.

    Read-only — never mutates state. The intent is to surface drift,
    not to fix it. Fixes belong in the regular sync paths or in
    targeted scripts (scripts/fix_dual_tags.py, scripts/backfill_pool_status.py).
    """

    def __init__(
        self,
        db: asyncpg.Pool,
        audit_logger: AuditLogger,
        alerter: SlackAlerter | None = None,
    ):
        self.db = db
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()

    async def run(self) -> SyncResult:
        audit = await self.audit_logger.start_audit(
            sync_type='overhaul_audit',
            metadata={'scope': 'fleet'}
        )
        try:
            metrics = await self._collect_metrics()
            metrics['has_anomalies'] = (
                metrics['dual_tag_candidates'] > 0
                or metrics['warmup_disabled_active_24h'] > 0
                or metrics['orphan_inactive_live_count'] > 0
                or metrics['stuck_incubation_14bd'] > 0
                or metrics['incubating_in_campaigns'] > 0
                or metrics['burned_inboxes_in_campaigns'] > 0
                or metrics['kill_queue_pending_over_2h'] > 0
                or metrics['flagged_but_alive_count'] > 0
                or metrics['stuck_active_null_pool'] > 0
            )

            if metrics['has_anomalies'] and self.alerter:
                await self._post_alert(metrics)

            print(
                f"[OverhaulAudit] dual_tag={metrics['dual_tag_candidates']} "
                f"warmup_off={metrics['warmup_disabled_active_24h']} "
                f"orphans={metrics['orphan_inactive_live_count']} "
                f"stuck_incubation={metrics['stuck_incubation_14bd']} "
                f"incubating_in_campaigns={metrics['incubating_in_campaigns']} "
                f"burned_in_campaigns={metrics['burned_inboxes_in_campaigns']} "
                f"kill_pending_2h={metrics['kill_queue_pending_over_2h']} "
                f"flagged_alive={metrics['flagged_but_alive_count']} "
                f"stuck_active_null={metrics['stuck_active_null_pool']}"
            )
            return await audit.complete(metadata=metrics)
        except Exception as e:
            return await audit.fail(e)

    async def _collect_metrics(self) -> Dict[str, int]:
        # 1. Dual-tag candidates: graduated reserve inboxes whose history
        # likely accrued a 'live' EB tag at graduation (the pre-overhaul
        # bug pattern). post-deploy this should trend to zero.
        dual_tag = await self.db.fetchval("""
            SELECT COUNT(*)
            FROM sender_accounts sa
            JOIN domains d ON sa.domain_id = d.id
            WHERE sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.inventory_lifecycle_status = 'active'
              AND sa.inventory_pool_status = 'reserve'
              AND d.pool_status = 'reserve'
        """) or 0

        # 2. Warmup disabled silently — active live inboxes whose
        # warmup_enabled flipped FALSE more than 24h ago. Migration 094's
        # trigger maintains warmup_disabled_at.
        warmup_off = await self.db.fetchval("""
            SELECT COUNT(*)
            FROM sender_accounts
            WHERE is_active = TRUE
              AND inbox_state = 'live'
              AND warmup_enabled IS NOT TRUE
              AND warmup_disabled_at IS NOT NULL
              AND warmup_disabled_at < NOW() - INTERVAL '24 hours'
        """) or 0

        # 3. Orphan inactive: inboxes our sync can't see but that EB may
        # still be sending through. is_active=FALSE excludes them from
        # every is_active=TRUE filter in the sync paths.
        orphan_inactive = await self.db.fetchval("""
            SELECT COUNT(*)
            FROM sender_accounts
            WHERE is_active = FALSE
              AND inbox_state = 'live'
              AND emailbison_account_id IS NOT NULL
        """) or 0

        # 4. Stuck-in-incubation past 14 BD — should be zero post-deploy.
        # The lifecycle_tag_sync graduation runs hourly so this lagging
        # signal flags graduation-path issues if it ever ticks up.
        stuck = await self.db.fetchval("""
            SELECT COUNT(*)
            FROM sender_accounts
            WHERE is_active = TRUE
              AND inbox_state = 'live'
              AND inventory_lifecycle_status = 'incubating'
              AND warmup_enabled = TRUE
              AND warmup_enabled_since IS NOT NULL
              AND (
                  SELECT COUNT(*)
                  FROM generate_series(
                      warmup_enabled_since::date,
                      CURRENT_DATE - INTERVAL '1 day',
                      INTERVAL '1 day'
                  ) AS d
                  WHERE EXTRACT(DOW FROM d) NOT IN (0, 6)
              ) >= 14
        """) or 0

        # 5. Incubating-in-campaigns — Stable Kernel ODSC bypass guard.
        # An incubating inbox should never be assigned to a real campaign;
        # if one is, ops bypassed the warmup gate. Once graduated (or
        # removed from campaigns) the row drops out of this count.
        incubating_in_campaigns = await self.db.fetchval("""
            SELECT COUNT(DISTINCT sa.id)
            FROM sender_accounts sa
            JOIN campaign_inboxes ci
              ON ci.sender_account_id = sa.id
             AND ci.is_active = TRUE
            WHERE sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.inventory_lifecycle_status = 'incubating'
        """) or 0

        # 6. Burned-domain inboxes still in active campaigns — reputation
        # risk. Per Rule C7 we don't auto-kill connected inboxes, but
        # burned-domain inboxes shouldn't be sending. Surfaces the gap
        # between domain pool state and campaign membership.
        # TODO(auto-cleanup): Build a function that calls EB to remove
        # burned-domain inboxes from active campaigns. The audit catches
        # the state but team currently fixes manually.
        burned_in_campaigns = await self.db.fetchval("""
            SELECT COUNT(DISTINCT sa.id)
            FROM sender_accounts sa
            JOIN domains d ON d.id = sa.domain_id
            JOIN campaign_inboxes ci
              ON ci.sender_account_id = sa.id
             AND ci.is_active = TRUE
            WHERE sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND d.pool_status IN ('burned', 'cancelled')
        """) or 0

        # 7. Kill queue stuck pending — replaces the pre-ADR-007 pool_warning
        # metric. kill_processor runs every 15 min, so a pending kill older
        # than 2h indicates the queue isn't draining (worker stuck, EB API
        # auth broken, workspace API key invalid, etc).
        kill_queue_stuck = await self.db.fetchval("""
            SELECT COUNT(*)
            FROM kill_queue
            WHERE status = 'pending'
              AND created_at < NOW() - INTERVAL '2 hours'
        """) or 0

        # 8. Flagged-but-alive — kill_queue rows with status='flagged' that
        # SHOULD imply the inbox is dead in DB (current kill_processor is
        # DB-first inside a single try block). This metric surfaces drift
        # if anything reverts an inbox post-kill, OR catches legacy partial
        # kills that pre-overhaul code left behind. Migration 099 prevents
        # this state from blocking new kills, but the metric still warns
        # because the underlying drift is meaningful.
        flagged_but_alive = await self.db.fetchval("""
            SELECT COUNT(*)
            FROM kill_queue kq
            JOIN sender_accounts sa ON sa.id = kq.inbox_id
            WHERE kq.status = 'flagged'
              AND sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.killed_at IS NULL
        """) or 0

        # 9. Stuck active + NULL pool — operational limbo: lifecycle says
        # graduated (active) but no pool tag, on a non-burned/cancelled
        # domain. Inbox can't be in campaigns (no live tag), can't be
        # killed (no signal threshold met), can't auto-recover (warning
        # path was removed by ADR-007). This was the bug class introduced
        # by migration 098's "restore from domain default" branch on
        # unassigned-pool domains. Self-healed by sync_accounts upsert
        # (post 2026-04-29-late) — this metric should converge to 0
        # within one sync_accounts cycle.
        stuck_active_null = await self.db.fetchval("""
            SELECT COUNT(*)
            FROM sender_accounts sa
            JOIN domains d ON d.id = sa.domain_id
            WHERE sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.inventory_lifecycle_status = 'active'
              AND sa.inventory_pool_status IS NULL
              AND sa.killed_at IS NULL
              AND (d.pool_status IS NULL OR d.pool_status NOT IN ('burned', 'cancelled'))
        """) or 0

        return {
            'dual_tag_candidates': int(dual_tag),
            'warmup_disabled_active_24h': int(warmup_off),
            'orphan_inactive_live_count': int(orphan_inactive),
            'stuck_incubation_14bd': int(stuck),
            'incubating_in_campaigns': int(incubating_in_campaigns),
            'burned_inboxes_in_campaigns': int(burned_in_campaigns),
            'kill_queue_pending_over_2h': int(kill_queue_stuck),
            'flagged_but_alive_count': int(flagged_but_alive),
            'stuck_active_null_pool': int(stuck_active_null),
        }

    async def _post_alert(self, metrics: Dict[str, int]) -> None:
        lines = []
        if metrics['dual_tag_candidates']:
            lines.append(
                f"• *Likely dual-tag inboxes:* {metrics['dual_tag_candidates']} "
                f"(graduated reserve, may still carry orphan `live` tag in EB). "
                f"Run `scripts/fix_dual_tags.py` if non-zero after a sync cycle."
            )
        if metrics['warmup_disabled_active_24h']:
            lines.append(
                f"• *Warmup disabled silently:* {metrics['warmup_disabled_active_24h']} "
                f"active live inboxes have `warmup_enabled=FALSE` for 24h+. "
                f"These will not graduate; investigate why warmup was disabled."
            )
        if metrics['orphan_inactive_live_count']:
            lines.append(
                f"• *Orphan inboxes:* {metrics['orphan_inactive_live_count']} "
                f"have `is_active=FALSE` but `inbox_state='live'`. Sync paths "
                f"can't see them; EB may still be sending through them."
            )
        if metrics['stuck_incubation_14bd']:
            lines.append(
                f"• *Stuck-in-incubation past 14 BD:* {metrics['stuck_incubation_14bd']}. "
                f"Should be zero post-deploy — lifecycle_tag_sync may not be running."
            )
        if metrics['incubating_in_campaigns']:
            lines.append(
                f"• *Incubating inboxes in active campaigns:* {metrics['incubating_in_campaigns']}. "
                f"Bypass guard — un-warmed inboxes are sending production volume. "
                f"Either graduate (if warmup window is complete) or remove from campaigns."
            )
        if metrics['burned_inboxes_in_campaigns']:
            lines.append(
                f"• *Burned-domain inboxes in active campaigns:* {metrics['burned_inboxes_in_campaigns']}. "
                f"Reputation risk — these domains are flagged but their inboxes are still in EB campaigns. "
                f"Team must remove from campaigns manually until auto-cleanup is built."
            )
        if metrics['kill_queue_pending_over_2h']:
            lines.append(
                f"• *Kill queue stuck:* {metrics['kill_queue_pending_over_2h']} kill_queue rows pending >2h. "
                f"kill_processor runs every 15 min — investigate worker health, "
                f"workspace API key validity, EB API errors."
            )
        if metrics['flagged_but_alive_count']:
            lines.append(
                f"• *Flagged-but-alive:* {metrics['flagged_but_alive_count']} kill_queue rows with status='flagged' "
                f"but inbox_state='live' AND killed_at IS NULL. Should be 0 (kill_processor is DB-first). "
                f"Drift here means an inbox got resurrected post-kill, or a legacy partial-kill row exists."
            )
        if metrics['stuck_active_null_pool']:
            lines.append(
                f"• *Stuck active + NULL pool:* {metrics['stuck_active_null_pool']} inboxes with "
                f"lifecycle='active' AND pool=NULL on healthy domains. Operational limbo — alive but "
                f"not deployable. sync_accounts self-heals to 'reserve' on next upsert; if this stays "
                f"non-zero across cycles the self-heal branch is missing a path."
            )

        # SlackAlerter.context expects a string; serialize the metrics dict.
        context = ", ".join(f"{k}={v}" for k, v in metrics.items() if k != 'has_anomalies')

        try:
            await self.alerter.send_alert(
                level="warning",
                title="Daily overhaul audit — anomalies detected",
                message="\n".join(lines),
                context=context,
            )
        except Exception as e:
            logger.warning("[OverhaulAudit] Slack alert failed: %s", e)
