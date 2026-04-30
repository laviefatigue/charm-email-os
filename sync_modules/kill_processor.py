"""
Kill Queue Processor

Processes inboxes flagged for removal from active use:
1. Tag inbox in EmailBison with trigger-specific tag (e.g., "flagged_fresh_inbox_blocked")
2. Mark inbox as 'dead' locally so it won't be used in new campaigns

Tag Format: flagged_{trigger_type}
Examples:
  - flagged_fresh_inbox_blocked
  - flagged_fresh_inbox_unknown
  - flagged_spam_complaint
  - flagged_hard_bounces_24h
  - flagged_hard_blocked_24h

NOTE: This processor does NOT delete inboxes from EmailBison.
Inboxes remain in the workspace but are tagged with the specific
trigger reason, allowing visibility into WHY each inbox was flagged.
"""
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, SyncResult
from .pool_promotion import pick_promotion_candidates, promote_inbox_to_deployed
from .slack_alerter import SlackAlerter


# =============================================================================
# TRIGGER SEVERITY CLASSIFICATION
# =============================================================================
# Domain-killing triggers indicate the DOMAIN is compromised, not just the
# inbox. When these fire, the entire domain is burned and a reserve domain
# is promoted (or a cross-domain reserve inbox under the per-inbox model).
#
# INSTANT domain-level: only dynamic `provider_block_*` triggers qualify.
# Static set used to be DOMAIN_KILLING_TRIGGERS but was removed when the
# 2026-03-18 audit found that hard_blocked bounces were being misclassified
# as provider blocks. is_domain_killing_trigger() below checks the prefix.

# CONDITIONAL domain burns — rate / count evaluated, ESP-aware decision in
# kill_processor._promote_backup_inbox(). Spam complaints trigger this path:
#   Google: any complaint = instant burn (3-inbox math, 1 = 33% domain hit)
#   Microsoft/Entra: ≥3 complaints AND rate ≥ burn threshold = burn
# Workspace circuit breaker: 3+ domains with spam kills in 24h = fleet-wide
# list quality event, domains enter monitoring instead of burning.
CONDITIONAL_DOMAIN_TRIGGERS = {
    'spam_complaint',
}

# Rate thresholds for domain burn decisions (aligned with Google Postmaster)
# Use Decimal to prevent asyncpg type inference errors on prepared statement reuse
from decimal import Decimal as _Decimal
DOMAIN_COMPLAINT_RATE_HEALTHY = _Decimal('0.001')    # < 0.1% = domain is fine
DOMAIN_COMPLAINT_RATE_FLAGGED = _Decimal('0.003')    # 0.1-0.3% = flagged, monitor
DOMAIN_COMPLAINT_RATE_BURN = _Decimal('0.01')        # > 1.0% sustained = burn immediately
MONITORING_WINDOW_DAYS = 7               # Observation window duration
CIRCUIT_BREAKER_DOMAINS_24H = 3          # Domains hit in 24h to trip workspace breaker
UNHEALTHY_MIN_COUNT = 2                  # Min unhealthy before 30% safety net applies

# ESP-aware domain burn thresholds (Option A)
# Google domains have ~3 inboxes each — 1 spam kill = 33%, a strong signal.
# Microsoft/Entra domains have ~52 inboxes — 1 spam kill = 1.9%, noise.
# Use absolute complaint counts instead of rates to avoid denominator distortion.
ESP_BURN_MIN_COMPLAINTS = {
    'google': 1,   # Any spam complaint = domain burn (1/3 = 33% rate)
    'entra': 3,    # Require pattern: 3+ spam kills before domain burn
}
ESP_BURN_MIN_COMPLAINTS_DEFAULT = 1  # Unknown ESP: conservative, treat like Google

# Inbox-killing triggers indicate inbox-level or list-level issues.
# Safe to promote B-Set inboxes from the same domain.
INBOX_KILLING_TRIGGERS = {
    # fresh_inbox_blocked and fresh_inbox_unknown removed (2026-03-18) —
    # redundant with hard_blocked_24h and hard_unknown_24h (identical thresholds).
    'hard_bounces_24h',      # Transient or list quality issue
    'hard_blocked_24h',      # Could escalate, but start as inbox-level
    'hard_unknown_24h',      # Bad addresses in list
    'hard_bounce_rate_7d',   # Sustained issue, likely list quality
    'bounce_rate_all_7d',    # General bounce rate
    'disconnected_timeout',  # OAuth issue, not reputation
}


def is_domain_killing_trigger(trigger_type: str) -> bool:
    """Check if a trigger type is an INSTANT domain kill (provider blocks)."""
    if not trigger_type:
        return False
    return trigger_type.startswith('provider_block_')


def is_conditional_domain_trigger(trigger_type: str) -> bool:
    """Check if a trigger requires cross-inbox confirmation before domain burn."""
    return trigger_type in CONDITIONAL_DOMAIN_TRIGGERS


class KillProcessor:
    """
    Processes the kill queue by tagging and flagging bad inboxes.

    Inboxes are tagged in EmailBison with trigger-specific tags
    (e.g., flagged_fresh_inbox_blocked) and marked as 'dead' locally.
    This provides visibility into WHY each inbox was flagged while
    preventing them from being used in new campaigns.

    Inboxes are NOT deleted from EmailBison - they remain in the
    workspace but are tagged and excluded from campaign assignment.
    """

    def __init__(
        self,
        db: asyncpg.Pool,
        client: EmailBisonClient,
        audit_logger: AuditLogger,
        alerter: SlackAlerter = None
    ):
        self.db = db
        self.client = client
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()

    # =========================================================================
    # RATE-BASED DOMAIN BURN HELPERS
    # =========================================================================

    async def _check_workspace_circuit_breaker(self, workspace_id, trigger_type: str) -> bool:
        """
        Check if multiple domains in this workspace are being hit by spam complaints
        in a short window — indicates a fleet-wide list quality event, not individual
        domain degradation.

        All live inboxes are shared across all campaigns (no campaign-to-inbox isolation),
        so we can't attribute complaints to individual campaigns. Instead we detect the
        workspace-level pattern: 3+ domains with spam kills in 24h = bad list segment.

        Returns True if circuit breaker tripped (do NOT burn domain).
        """
        domains_hit_24h = await self.db.fetchval("""
            SELECT COUNT(DISTINCT domain_id)
            FROM sender_accounts
            WHERE workspace_id = $1
              AND kill_trigger = 'spam_complaint'
              AND killed_at >= NOW() - INTERVAL '24 hours'
        """, workspace_id)

        if domains_hit_24h >= CIRCUIT_BREAKER_DOMAINS_24H:
            print(f"    [CIRCUIT BREAKER] {domains_hit_24h} domains with spam kills in 24h "
                  f"— fleet-wide list quality event, blocking domain burns")

            if self.alerter:
                try:
                    await self.alerter.send_alert(
                        level="warning",
                        title=f"Circuit Breaker: {domains_hit_24h} domains hit in 24h",
                        message=(
                            f"*{domains_hit_24h} domains* in this workspace have spam complaint "
                            f"kills in the last 24 hours.\n"
                            f"This indicates a fleet-wide list quality event, not individual "
                            f"domain reputation damage.\n"
                            f"*Action:* Domains entering monitoring (not burning). "
                            f"Review recent campaign lists for toxic segments."
                        ),
                        context={"workspace_id": str(workspace_id), "domains_hit": domains_hit_24h}
                    )
                except Exception as e:
                    print(f"    [WARNING] Failed to send circuit breaker alert: {e}")

            return True

        return False

    async def _get_domain_complaint_rate(self, domain_id) -> float:
        """Get the pre-calculated domain complaint rate (7-day window)."""
        rate = await self.db.fetchval("""
            SELECT COALESCE(domain_complaint_rate_7d, 0)
            FROM domains WHERE id = $1
        """, domain_id)
        return float(rate or 0)

    async def _enter_domain_monitoring(self, domain_id, domain_name: str,
                                        trigger_type: str, reason: str):
        """
        Put a domain into monitoring state with a 7-day observation window.
        After the window, health_checks.py evaluates whether to burn or recover.
        """
        # Capture old state BEFORE update for audit logging
        old_state = await self.db.fetchval(
            "SELECT domain_state::text FROM domains WHERE id = $1", domain_id
        )

        # Only enter monitoring if not already monitoring
        if old_state == 'monitoring':
            return

        await self.db.execute("""
            UPDATE domains
            SET domain_state = 'monitoring'::domain_state,
                monitoring_started_at = NOW(),
                monitoring_reason = $2,
                updated_at = NOW()
            WHERE id = $1
        """, domain_id, reason)

        # Log to domain_rotation_events with correct old_status
        try:
            await self.db.execute("""
                INSERT INTO domain_rotation_events (
                    domain_id, workspace_id, event_type,
                    trigger_type, old_status, new_status, notes
                )
                SELECT $1, workspace_id, 'monitoring_started', $2,
                       $4, 'monitoring', $3
                FROM domains WHERE id = $1
            """, domain_id, trigger_type, reason, old_state or 'unknown')
        except Exception as e:
            print(f"    [WARNING] Could not log monitoring event: {e}")

        print(f"    [MONITORING] {domain_name}: {reason}")

        if self.alerter:
            try:
                await self.alerter.send_alert(
                    level="info",
                    title=f"Domain Monitoring: {domain_name}",
                    message=(
                        f"*Trigger:* `{trigger_type}`\n"
                        f"*Reason:* {reason}\n"
                        f"*Action:* 7-day observation window started. "
                        f"Domain will be evaluated after window expires."
                    ),
                    context={"domain": domain_name, "trigger": trigger_type}
                )
            except Exception as e:
                print(f"    [WARNING] Failed to send monitoring alert: {e}")

    async def process_workspace_queue(
        self,
        workspace_id: UUID,
        workspace_name: str,
    ) -> SyncResult:
        """
        Process the kill queue for a single workspace.

        Called by WorkspaceWriteOrchestrator with a workspace-scoped EmailBison
        client (migration 089) — no switch_workspace() needed because the API
        token carries workspace context. This enables concurrent kill
        processing across workspaces without context-race issues.

        This is the only public entry point for kill processing. The legacy
        `process_queue()` cross-workspace fan-out was removed during the
        2026-04-27 overhaul along with the global super-admin client path.
        """
        audit = await self.audit_logger.start_audit(
            sync_type='kill_queue',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name, 'scope': 'process_workspace'}
        )

        try:
            tagged_count = await self._tag_pending_items_for_workspace(audit, workspace_id)
            if tagged_count > 0:
                print(f"[KillProcessor:{workspace_name}] Flagged inactive: {tagged_count}")
            return await audit.complete(metadata={'tagged_count': tagged_count})
        except Exception as e:
            return await audit.fail(e)

    async def _tag_pending_items_for_workspace(self, audit, workspace_id: UUID) -> int:
        """
        Tag pending kill queue items in EmailBison with trigger-specific tags.

        Each inbox is tagged with its specific trigger reason:
          flagged_spam_complaint, flagged_hard_bounces_24h,
          flagged_hard_blocked_24h, etc.

        This provides visibility into WHY each inbox was flagged. Inboxes
        are NOT deleted from EmailBison — they remain but are tagged.

        Scoped to a single workspace; the caller (process_workspace_queue)
        is responsible for binding the right workspace-scoped EB client.
        """
        pending = await self.db.fetch("""
            SELECT
                kq.id,
                kq.inbox_id,
                kq.workspace_id,
                kq.trigger_type,
                kq.trigger_value,
                kq.trigger_threshold,
                kq.status as queue_status,
                sa.email_address,
                sa.emailbison_account_id,
                sa.domain_id,
                w.emailbison_workspace_id,
                w.workspace_name,
                d.domain_name
            FROM kill_queue kq
            JOIN sender_accounts sa ON kq.inbox_id = sa.id
            JOIN workspaces w ON kq.workspace_id = w.id
            LEFT JOIN domains d ON sa.domain_id = d.id
            WHERE kq.status IN ('pending', 'eb_pending')
            AND kq.workspace_id = $1
            AND sa.emailbison_account_id IS NOT NULL
            AND w.emailbison_workspace_id IS NOT NULL
            AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
        """, workspace_id)

        if not pending:
            return 0

        tagged_count = 0

        # Single-workspace operation under the orchestrator. The cross-workspace
        # grouping that used to live here was removed with the legacy
        # process_queue() entry point: every inbox in `pending` shares the
        # same workspace and the EB client is already scoped to it.
        items = list(pending)

        try:
            # Cache tags within this workspace to avoid redundant API calls.
            tag_cache: Dict[str, int] = {}

            # Tag each inbox with its specific trigger tag.
            # Order of operations: DB first, EB second.
            # If DB succeeds but EB fails, inbox is correctly dead in DB
            # and kill_queue gets 'eb_pending' status for retry next cycle.
            for item in items:
                audit.increment_processed()
                trigger_type = item['trigger_type']
                tag_name = f"flagged_{trigger_type}"
                is_eb_retry = item.get('queue_status') == 'eb_pending'
                eb_account_id = int(item['emailbison_account_id'])

                # ── STEP 1: DB operations (skip if retrying EB only) ──
                if not is_eb_retry:
                    try:
                        # Mark kill_queue as flagged
                        await self.db.execute("""
                            UPDATE kill_queue
                            SET
                                status = 'flagged',
                                tagged_at = NOW(),
                                tag_name = $2,
                                updated_at = NOW()
                            WHERE id = $1
                        """, item['id'], tag_name)

                        # Mark inbox as dead — cannot be used in new campaigns
                        await self.db.execute("""
                            UPDATE sender_accounts
                            SET
                                inbox_state = 'dead',
                                killed_at = NOW(),
                                kill_trigger = $2::kill_trigger_type,
                                inventory_lifecycle_status = 'dead',
                                inventory_pool_status = NULL,
                                updated_at = NOW()
                            WHERE id = $1
                        """, item['inbox_id'], trigger_type)

                        # Update domain metrics and promote backup
                        await self._update_domain_on_inbox_death(item['inbox_id'])

                        await self._update_campaign_burn_counters(
                            inbox_id=item['inbox_id'],
                            workspace_id=item['workspace_id'],
                            trigger_type=trigger_type,
                            trigger_value=item.get('trigger_value'),
                            trigger_threshold=item.get('trigger_threshold'),
                            inbox_email=item['email_address'],
                            domain_id=item.get('domain_id'),
                            domain_name=item.get('domain_name')
                        )

                        if item.get('domain_id'):
                            await self._recalculate_domain_metrics(item['domain_id'])
                            await self._recalculate_domain_velocity(item['domain_id'])

                    except Exception as db_err:
                        # DB failed — do NOT touch EB, mark as failed
                        audit.add_error(
                            record_id=item['email_address'],
                            error=f"DB update failed: {db_err}",
                            details={'inbox_id': str(item['inbox_id']), 'tag': tag_name}
                        )
                        try:
                            await self.db.execute("""
                                UPDATE kill_queue
                                SET status = 'failed', error_message = $2, updated_at = NOW()
                                WHERE id = $1
                            """, item['id'], str(db_err)[:500])
                        except Exception:
                            pass
                        continue

                    # Promote backup inbox — isolated from the DB step so that
                    # EB errors here don't abort the kill or mark it failed.
                    try:
                        await self._promote_backup_inbox(
                            item['inbox_id'],
                            item['workspace_id'],
                            trigger_type=trigger_type
                        )
                    except Exception as promo_err:
                        # Promotion failure is non-fatal — inbox is already dead in DB.
                        # Log it but continue so the EB tagging step still runs.
                        print(f"    [WARN] Backup promotion failed for {item['email_address']}: {promo_err}")

                # ── STEP 2: EB operations (tag flagged_*, remove pool tags) ──
                try:
                    # Get or create the trigger-specific tag (cached per workspace)
                    if trigger_type not in tag_cache:
                        tag = await self.client.get_or_create_tag(tag_name)
                        tag_id = tag.get('id')
                        if tag_id:
                            tag_cache[trigger_type] = tag_id
                        else:
                            audit.add_error(
                                record_id=item['email_address'],
                                error=f"Failed to create tag: {tag_name}"
                            )
                            # DB is already updated; mark eb_pending for retry
                            await self.db.execute("""
                                UPDATE kill_queue
                                SET status = 'eb_pending', error_message = 'Tag creation failed', updated_at = NOW()
                                WHERE id = $1
                            """, item['id'])
                            continue
                    else:
                        tag_id = tag_cache[trigger_type]

                    # Tag in EmailBison with trigger-specific tag
                    await self.client.tag_inbox(
                        account_id=eb_account_id,
                        tag_id=tag_id
                    )

                    # Pool tags are now standardized to 'live' / 'reserve'
                    # (no more legacy A-Set/B-Set custom names per workspace —
                    # set_tag_sync._resolve_tag_names enforces this).
                    # Strip both pool tags from the dead inbox so it cannot
                    # be re-included in a campaign reapply by tag filter.
                    #
                    # Error handling discipline (2026-04-30 fix — see
                    # docs/work-logs/2026-04-30-systems-accuracy-and-cleanup.md
                    # SPUI/Spout investigation §): a bare `except: pass` here
                    # conflated two distinct outcomes —
                    #   (1) HTTP 404: tag was not present — intended state, fine
                    #       to swallow. The "Tag may not be present" goal IS this
                    #       case.
                    #   (2) HTTP 5xx / network / other: transient EB failure —
                    #       silently swallowing this leaves the pool tag still
                    #       applied in EB while DB is already dead+pool=NULL.
                    #       Result: zombie pool tags in EB on dead inboxes, e.g.
                    #       Spout has 10 such rows where 'live'/'reserve' tag
                    #       remained on inboxes killed in March alongside their
                    #       flagged_* tag.
                    # Re-raise non-404 errors so the outer except marks the kill
                    # row eb_pending for retry next cycle.
                    for pool_tag_name in ('live', 'reserve'):
                        pool_tag_id = tag_cache.get(pool_tag_name)
                        if not pool_tag_id:
                            pool_tag = await self.client.get_or_create_tag(pool_tag_name)
                            pool_tag_id = pool_tag.get('id')
                            if pool_tag_id:
                                tag_cache[pool_tag_name] = pool_tag_id

                        if pool_tag_id:
                            try:
                                await self.client.untag_inbox(
                                    account_id=eb_account_id,
                                    tag_id=pool_tag_id,
                                )
                            except EmailBisonAPIError as untag_err:
                                if getattr(untag_err, 'status_code', None) == 404:
                                    pass  # Tag was not present — intended outcome.
                                else:
                                    # Transient or unexpected — surface to outer
                                    # except for retry, do not silently produce
                                    # a zombie pool tag.
                                    raise

                    # EB succeeded — finalize status
                    if is_eb_retry:
                        await self.db.execute("""
                            UPDATE kill_queue
                            SET status = 'flagged', updated_at = NOW()
                            WHERE id = $1
                        """, item['id'])

                    tagged_count += 1
                    audit.increment_updated()

                    print(f"    [FLAGGED] {item['email_address']} - tag: {tag_name}")

                except (EmailBisonAPIError, Exception) as eb_err:
                    # EB failed but DB is already correct (inbox is dead in DB).
                    # Mark for retry next cycle — only EB operations will be retried.
                    audit.add_error(
                        record_id=item['email_address'],
                        error=f"EB tagging failed (DB updated): {eb_err}",
                        details={'inbox_id': str(item['inbox_id']), 'tag': tag_name}
                    )
                    try:
                        await self.db.execute("""
                            UPDATE kill_queue
                            SET status = 'eb_pending', error_message = $2, updated_at = NOW()
                            WHERE id = $1
                        """, item['id'], str(eb_err)[:500])
                    except Exception:
                        pass
                    print(f"    [EB_PENDING] {item['email_address']} - DB updated, EB retry next cycle")

        except Exception as e:
            audit.add_error(
                record_id="workspace_kill_pass",
                error=f"Workspace kill pass error: {e}",
            )

        return tagged_count

    async def cancel_kill(self, inbox_id: UUID, reason: str = None) -> bool:
        """
        Cancel a pending/flagged kill (manual override).

        Removes the tag from EmailBison and marks the inbox as live again.

        Returns:
            True if cancelled, False if not found or already processed
        """
        result = await self.db.fetchrow("""
            UPDATE kill_queue
            SET
                status = 'cancelled',
                error_message = $2,
                updated_at = NOW()
            WHERE inbox_id = $1
            AND status IN ('pending', 'flagged')
            RETURNING id, tag_name, inbox_id
        """, inbox_id, reason or 'Manual cancellation')

        if result and result['tag_name']:
            # Try to remove the tag from EmailBison
            try:
                inbox = await self.db.fetchrow("""
                    SELECT
                        sa.emailbison_account_id,
                        w.emailbison_workspace_id
                    FROM sender_accounts sa
                    JOIN workspaces w ON sa.workspace_id = w.id
                    WHERE sa.id = $1
                """, inbox_id)

                if inbox and inbox['emailbison_account_id']:
                    await self.client.switch_workspace(int(inbox['emailbison_workspace_id']))

                    # Find tag ID
                    tags = await self.client.list_tags()
                    tag = next((t for t in tags if t.get('name') == result['tag_name']), None)

                    if tag:
                        await self.client.untag_inbox(
                            account_id=int(inbox['emailbison_account_id']),
                            tag_id=tag['id']
                        )

            except Exception as e:
                print(f"[KillProcessor] Warning: Failed to remove tag: {e}")

        return result is not None

    async def get_queue_summary(self) -> Dict:
        """Get summary of kill queue status."""
        stats = await self.db.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'flagged') as flagged,
                COUNT(*) FILTER (WHERE status = 'tagged') as tagged_legacy,
                COUNT(*) FILTER (WHERE status = 'deleted') as deleted_legacy,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
            FROM kill_queue
        """)

        return {
            'pending': stats['pending'] or 0,
            'flagged': stats['flagged'] or 0,
            'tagged_legacy': stats['tagged_legacy'] or 0,  # Old records before code change
            'deleted_legacy': stats['deleted_legacy'] or 0,  # Old records before code change
            'failed': stats['failed'] or 0,
            'cancelled': stats['cancelled'] or 0
        }

    async def get_flagged_by_trigger(self, workspace_id: UUID = None) -> Dict:
        """
        Get breakdown of flagged inboxes by trigger type.

        Useful for understanding WHY inboxes are being flagged
        and identifying patterns (e.g., too many fresh_inbox_bounce).

        Args:
            workspace_id: Optional workspace filter

        Returns:
            Dict with trigger type counts and tag names
        """
        if workspace_id:
            rows = await self.db.fetch("""
                SELECT
                    kq.trigger_type,
                    kq.tag_name,
                    COUNT(*) as count
                FROM kill_queue kq
                WHERE kq.status = 'flagged'
                AND kq.workspace_id = $1
                GROUP BY kq.trigger_type, kq.tag_name
                ORDER BY count DESC
            """, workspace_id)
        else:
            rows = await self.db.fetch("""
                SELECT
                    kq.trigger_type,
                    kq.tag_name,
                    COUNT(*) as count
                FROM kill_queue kq
                WHERE kq.status = 'flagged'
                GROUP BY kq.trigger_type, kq.tag_name
                ORDER BY count DESC
            """)

        by_trigger = {}
        total = 0
        for row in rows:
            trigger = row['trigger_type']
            count = row['count']
            by_trigger[trigger] = {
                'count': count,
                'tag_name': row['tag_name'] or f"flagged_{trigger}"
            }
            total += count

        return {
            'total_flagged': total,
            'by_trigger': by_trigger
        }

    async def get_workspace_health_summary(self, workspace_id: UUID) -> Dict:
        """
        Get inbox health summary for a workspace.

        Returns counts of live vs flagged inboxes, broken down by trigger.
        Useful for determining available inboxes for campaign assignment.
        """
        stats = await self.db.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_count,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_count,
                COUNT(*) as total_count
            FROM sender_accounts sa
            LEFT JOIN domains d ON sa.domain_id = d.id
            WHERE sa.workspace_id = $1
            AND sa.is_active = TRUE
            AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
        """, workspace_id)

        # Get breakdown of dead inboxes by kill trigger
        trigger_breakdown = await self.db.fetch("""
            SELECT
                sa.kill_trigger,
                COUNT(*) as count
            FROM sender_accounts sa
            LEFT JOIN domains d ON sa.domain_id = d.id
            WHERE sa.workspace_id = $1
            AND sa.inbox_state = 'dead'
            AND sa.kill_trigger IS NOT NULL
            AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
            GROUP BY sa.kill_trigger
            ORDER BY count DESC
        """, workspace_id)

        by_trigger = {row['kill_trigger']: row['count'] for row in trigger_breakdown}

        return {
            'live_inboxes': stats['live_count'] or 0,
            'flagged_inboxes': stats['dead_count'] or 0,
            'total_inboxes': stats['total_count'] or 0,
            'available_for_campaigns': stats['live_count'] or 0,
            'flagged_by_trigger': by_trigger
        }

    # =========================================================================
    # V3 COMPLIANCE: Domain and Campaign State Management
    # =========================================================================

    async def _update_domain_on_inbox_death(self, inbox_id: UUID):
        """
        Update domain state when inbox dies.

        Rate-based domain state transitions:
        - Domain in 'monitoring' → don't override (handled by health_checks evaluate_monitoring_domains)
        - Complaint rate >1.0% → 'dead'
        - Small-domain capacity safety net: total ≤ 5 AND dead ≥ 2 → 'dead'
          (Google's 3-inbox/domain math: losing 2 of 3 = unrecoverable, retire whole.)
        - >30% unhealthy (min 2 inboxes) → 'dead' (legacy size-aware safety net for larger domains)
        - Complaint rate >0.3% → 'flagged'
        - 1 reputation kill → 'flagged'
        - Otherwise → 'live'

        NOTE: We only update local state. Domain remains in EmailBison.
        Human operators decide actual action based on tags.
        """
        # Get the domain for this inbox
        domain = await self.db.fetchrow("""
            SELECT
                sa.domain_id,
                d.domain_name,
                d.domain_state,
                d.workspace_id
            FROM sender_accounts sa
            JOIN domains d ON sa.domain_id = d.id
            WHERE sa.id = $1 AND sa.domain_id IS NOT NULL
        """, inbox_id)

        if not domain:
            return

        domain_id = domain['domain_id']

        # Recalculate complaint rate for this domain
        await self.db.execute(
            "SELECT recalculate_domain_complaint_rate($1)", domain_id
        )

        # Calculate domain health metrics
        metrics = await self.db.fetchrow("""
            SELECT
                COUNT(*) as total_inboxes,
                COUNT(*) FILTER (WHERE inbox_state = 'live') as live_count,
                COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_count,
                COUNT(*) FILTER (WHERE health_score < 60) as unhealthy_count,
                COUNT(*) FILTER (WHERE inbox_state = 'dead' AND (
                    kill_trigger IN ('spam_complaint', 'hard_blocked_24h')
                    OR kill_trigger::text LIKE 'provider_block_%'
                )) as reputation_dead
            FROM sender_accounts
            WHERE domain_id = $1 AND is_active = TRUE
        """, domain_id)

        total = metrics['total_inboxes'] or 0
        dead_count = metrics['dead_count'] or 0
        unhealthy_count = metrics['unhealthy_count'] or 0
        reputation_dead = metrics['reputation_dead'] or 0

        # Calculate unhealthy percentage
        unhealthy_pct = (unhealthy_count / total * 100) if total > 0 else 0

        # Get complaint rate
        complaint_rate = await self._get_domain_complaint_rate(domain_id)

        # Rate-based + trigger-aware domain state
        current_state = domain['domain_state']
        new_state = current_state

        if current_state == 'monitoring':
            new_state = 'monitoring'  # Don't override — handled by evaluate_monitoring_domains
        elif complaint_rate >= DOMAIN_COMPLAINT_RATE_BURN:
            new_state = 'dead'       # >1% complaint rate = dead
        elif total > 0 and total <= 5 and dead_count >= 2:
            # 2-kill capacity safety net for small (Google) domains.
            # On a 3-inbox Google domain, losing 2 means the third can't sustain
            # the domain's reputation alone — retire it and let kill_processor
            # cross-domain promote a reserve to maintain workspace capacity.
            new_state = 'dead'
        elif unhealthy_pct > 30 and (total >= 10 or unhealthy_count >= UNHEALTHY_MIN_COUNT):
            new_state = 'dead'       # Legacy size-aware unhealthy% rule (Microsoft 52-inbox domains)
        elif complaint_rate >= DOMAIN_COMPLAINT_RATE_FLAGGED:
            new_state = 'flagged'    # 0.3-1.0% complaint rate
        elif reputation_dead >= 1:
            new_state = 'flagged'    # One reputation signal (non-spam, e.g. hard_blocked_24h)
        else:
            new_state = 'live'       # List/operational kills don't affect domain state

        # Update domain metrics and state
        live_count = int(metrics['live_count'] or 0)
        health_pct = _Decimal(str(round(live_count / total * 100, 2))) if total > 0 else _Decimal('0')

        await self.db.execute("""
            UPDATE domains
            SET
                dead_inbox_count = $2,
                live_inbox_count = $3,
                health_percentage = $4,
                domain_state = $5::domain_state,
                updated_at = NOW()
            WHERE id = $1
        """, domain_id, int(dead_count), live_count, health_pct, new_state)

        # Log state transition
        if new_state != current_state:
            print(f"    [DOMAIN STATE] {domain['domain_name']}: {current_state} -> {new_state} "
                  f"(dead={dead_count}, unhealthy={unhealthy_pct:.1f}%, "
                  f"complaint_rate={complaint_rate*100:.3f}%)")

    async def _update_campaign_burn_counters(
        self,
        inbox_id: UUID,
        workspace_id: UUID,
        trigger_type: str,
        trigger_value: Optional[float] = None,
        trigger_threshold: Optional[float] = None,
        inbox_email: str = None,
        domain_id: UUID = None,
        domain_name: str = None
    ):
        """
        V3 Section 11: Update campaign burn counters when inbox dies.

        Increments:
        - inboxes_burned (lifetime total)
        - inboxes_burned_7d (rolling 7-day count)
        - domains_affected (unique domains)
        - domains_burned_7d (rolling 7-day)

        Also:
        - Inserts burn event into campaign_burn_events for granular analysis
        - Checks quarantine triggers (2+ burns = quarantine)

        NOTE: Quarantine = local flag for review. No auto-removal from inboxes.
        """
        # Get campaigns this inbox was assigned to
        campaigns = await self.db.fetch("""
            SELECT DISTINCT
                ci.campaign_id,
                ec.campaign_name,
                ec.inboxes_burned_7d,
                ec.domains_burned_7d,
                ec.campaign_state,
                sa.domain_id
            FROM campaign_inboxes ci
            JOIN emailbison_campaigns ec ON ci.campaign_id = ec.id
            JOIN sender_accounts sa ON ci.sender_account_id = sa.id
            WHERE ci.sender_account_id = $1
            AND ci.is_active = TRUE
        """, inbox_id)

        for campaign in campaigns:
            campaign_id = campaign['campaign_id']
            camp_domain_id = campaign['domain_id'] or domain_id

            # Insert burn event for granular tracking
            # ON CONFLICT handles edge case where inbox already has a burn event for this campaign
            await self.db.execute("""
                INSERT INTO campaign_burn_events (
                    workspace_id,
                    campaign_id,
                    inbox_id,
                    domain_id,
                    kill_trigger_type,
                    trigger_value,
                    trigger_threshold,
                    campaign_name,
                    inbox_email,
                    domain_name,
                    burned_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                ON CONFLICT (campaign_id, inbox_id) DO NOTHING
            """,
                workspace_id,
                campaign_id,
                inbox_id,
                camp_domain_id,
                trigger_type,
                trigger_value,
                trigger_threshold,
                campaign['campaign_name'],
                inbox_email,
                domain_name
            )

            # Increment burn counters
            await self.db.execute("""
                UPDATE emailbison_campaigns
                SET
                    inboxes_burned = COALESCE(inboxes_burned, 0) + 1,
                    inboxes_burned_7d = COALESCE(inboxes_burned_7d, 0) + 1,
                    updated_at = NOW()
                WHERE id = $1
            """, campaign_id)

            # Check if this is a new domain being burned
            existing_domain_burn = await self.db.fetchval("""
                SELECT COUNT(DISTINCT sa.domain_id)
                FROM campaign_inboxes ci
                JOIN sender_accounts sa ON ci.sender_account_id = sa.id
                WHERE ci.campaign_id = $1
                AND sa.inbox_state = 'dead'
                AND sa.domain_id != $2
            """, campaign_id, domain_id)

            if existing_domain_burn == 0:
                # First domain burned - increment domain counters
                await self.db.execute("""
                    UPDATE emailbison_campaigns
                    SET
                        domains_affected = COALESCE(domains_affected, 0) + 1,
                        domains_burned_7d = COALESCE(domains_burned_7d, 0) + 1,
                        updated_at = NOW()
                    WHERE id = $1
                """, campaign_id)

            # Get updated counts for quarantine check
            updated = await self.db.fetchrow("""
                SELECT
                    inboxes_burned_7d,
                    domains_burned_7d,
                    campaign_state
                FROM emailbison_campaigns
                WHERE id = $1
            """, campaign_id)

            # V3 Quarantine triggers (local flag only - no auto-removal from inboxes)
            should_quarantine = False
            quarantine_reason = None

            if updated['inboxes_burned_7d'] >= 2:
                should_quarantine = True
                quarantine_reason = f"Burned {updated['inboxes_burned_7d']} inboxes in 7 days"

            if updated['domains_burned_7d'] >= 2:
                should_quarantine = True
                quarantine_reason = f"Burned inboxes across {updated['domains_burned_7d']} domains in 7 days"

            # Apply quarantine if triggered and not already quarantined
            if should_quarantine and updated['campaign_state'] == 'live':
                await self.db.execute("""
                    UPDATE emailbison_campaigns
                    SET
                        campaign_state = 'quarantined',
                        quarantined_at = NOW(),
                        quarantine_reason = $2,
                        updated_at = NOW()
                    WHERE id = $1
                """, campaign_id, quarantine_reason)

                print(f"    [CAMPAIGN QUARANTINE] {campaign['campaign_name']}: {quarantine_reason}")

    async def _promote_backup_inbox(
        self,
        killed_inbox_id: UUID,
        workspace_id: UUID,
        trigger_type: str = None
    ):
        """
        Promote a reserve inbox to live when a deployed inbox is killed.

        Cross-domain (post-2026-04-27 overhaul):
            domain mixing is approved for promotion. We pull the longest-
            sitting healthy reserve inbox from anywhere in the workspace,
            not just the same domain. Source domain stays in its pool;
            only the promoted inbox transitions to `inventory_pool_status='live'`.
            set_tag_sync's per-inbox authority then propagates the EB tags.

        Trigger severity:
            provider_block_*  → instant domain burn, no promotion (domain compromised)
            spam_complaint    → ESP-aware burn (Google instant, others rate-gated),
                                with workspace circuit breaker for fleet-wide events
            inbox-level kills → promote a workspace reserve

        Capacity goal: maintain enough live inboxes to honor the 50k sends/month
        commitment. Without cross-domain promotion, killing the third inbox of a
        3-inbox Google domain leaves it short-handed for weeks.
        """
        # Get the killed inbox's domain and pool status
        killed_inbox = await self.db.fetchrow("""
            SELECT
                sa.id, sa.email_address, sa.domain_id, sa.esp,
                sa.inventory_pool_status,
                sa.kill_trigger,
                d.domain_name,
                w.emailbison_workspace_id,
                w.a_set_tag_name, w.b_set_tag_name
            FROM sender_accounts sa
            JOIN domains d ON sa.domain_id = d.id
            JOIN workspaces w ON sa.workspace_id = w.id
            WHERE sa.id = $1
        """, killed_inbox_id)

        if not killed_inbox or not killed_inbox['domain_id']:
            return

        # CEO directive: Microsoft Entra is legacy ride-to-death. Don't
        # consume a Google reserve to fill a Microsoft kill — the legacy
        # fleet bleeds out without replacement, and reserve runway must
        # stay aligned with the Google sending pool.
        if killed_inbox.get('esp') == 'microsoft':
            print(f"    [SKIP PROMOTE] {killed_inbox['email_address']} (microsoft, ride-to-death)")
            return

        domain_id = killed_inbox['domain_id']
        domain_name = killed_inbox['domain_name']
        killed_pool = killed_inbox['inventory_pool_status']
        eb_workspace_id = killed_inbox['emailbison_workspace_id']

        # Get trigger type from parameter or from the inbox record
        effective_trigger = trigger_type or killed_inbox.get('kill_trigger')

        # ==========================================
        # TRIGGER SEVERITY CHECK
        # ==========================================
        # Provider blocks = instant domain burn (unambiguously domain-level)
        if is_domain_killing_trigger(effective_trigger):
            await self._handle_domain_killing_trigger(
                domain_id=domain_id,
                domain_name=domain_name,
                workspace_id=workspace_id,
                trigger_type=effective_trigger,
                killed_inbox_email=killed_inbox['email_address']
            )
            return  # Skip normal promotion - domain is compromised

        # Conditional domain triggers (spam_complaint) = rate-based evaluation
        # with workspace circuit breaker and observation window.
        if is_conditional_domain_trigger(effective_trigger):
            # Step 1: Workspace circuit breaker — check BEFORE domain burn
            # If 3+ domains in this workspace have spam kills in 24h, it's a
            # fleet-wide list quality event, not individual domain degradation.
            circuit_breaker_tripped = await self._check_workspace_circuit_breaker(
                workspace_id, effective_trigger
            )
            if circuit_breaker_tripped:
                await self._enter_domain_monitoring(
                    domain_id, domain_name, effective_trigger,
                    reason="Workspace circuit breaker — fleet-wide list quality event"
                )
                # Still promote B-Set inbox for the killed inbox (domain not burned)
                # Fall through to normal promotion logic below

            else:
                # Step 2: Recalculate domain complaint rate
                await self.db.execute(
                    "SELECT recalculate_domain_complaint_rate($1)", domain_id
                )

                # Fetch rate AND complaint count + ESP type for ESP-aware decision
                domain_stats = await self.db.fetchrow("""
                    SELECT
                        COALESCE(domain_complaint_rate_7d, 0) as complaint_rate,
                        COALESCE(domain_complaints_7d, 0) as complaints_7d,
                        infrastructure_type
                    FROM domains WHERE id = $1
                """, domain_id)
                complaint_rate = float(domain_stats['complaint_rate'] or 0)
                complaints_7d = int(domain_stats['complaints_7d'] or 0)
                esp_type = domain_stats['infrastructure_type']  # 'google', 'entra', or None

                # Step 3: ESP-aware burn decision
                #
                # Google (3 inboxes/domain): INSTANT BURN on any spam complaint.
                #   1 of 3 inboxes complained = 33% of domain compromised. CEO
                #   directive 2026-04-27: do not gate by send-volume rate; the
                #   domain is gone. Workspace circuit breaker (above) still
                #   protects against bad-list-segment events.
                #
                # Microsoft/Entra (52 inboxes/domain, legacy ride-to-death):
                #   1 spam kill = 1.9% — noise. Require ≥3 spam kills AND the
                #   complaint rate to cross the burn threshold before burning.
                #   Microsoft fleet does not have reserve runway, so burning a
                #   52-inbox domain on a single complaint would be reckless.
                min_complaints = ESP_BURN_MIN_COMPLAINTS.get(
                    esp_type, ESP_BURN_MIN_COMPLAINTS_DEFAULT
                )
                is_google = esp_type == 'google'

                # Google: instant burn on any complaint (no rate gate).
                if is_google and complaints_7d >= min_complaints:
                    print(f"    [DOMAIN KILL] {domain_name} (google): "
                          f"{complaints_7d} spam complaint(s) — instant burn "
                          f"(rate {complaint_rate*100:.3f}% recorded for audit)")
                    await self._handle_domain_killing_trigger(
                        domain_id=domain_id,
                        domain_name=domain_name,
                        workspace_id=workspace_id,
                        trigger_type=effective_trigger,
                        killed_inbox_email=killed_inbox['email_address']
                    )
                    return  # Domain compromised

                # Non-Google: existing rate-gated path.
                if complaints_7d >= min_complaints and complaint_rate >= DOMAIN_COMPLAINT_RATE_BURN:
                    print(f"    [DOMAIN KILL] {domain_name} ({esp_type or 'unknown'}): "
                          f"{complaints_7d} spam kills, rate {complaint_rate*100:.3f}% "
                          f"(min {min_complaints} for {esp_type or 'default'}) — burning domain")
                    await self._handle_domain_killing_trigger(
                        domain_id=domain_id,
                        domain_name=domain_name,
                        workspace_id=workspace_id,
                        trigger_type=effective_trigger,
                        killed_inbox_email=killed_inbox['email_address']
                    )
                    return  # Domain compromised

                elif complaints_7d >= min_complaints and complaint_rate >= DOMAIN_COMPLAINT_RATE_FLAGGED:
                    # Meets ESP threshold but rate in monitoring range (0.3-1.0%)
                    await self._enter_domain_monitoring(
                        domain_id, domain_name, effective_trigger,
                        reason=f"{esp_type or 'unknown'}: {complaints_7d} spam kills, "
                               f"rate {complaint_rate*100:.3f}% — monitoring "
                               f"{MONITORING_WINDOW_DAYS} days"
                    )
                    # Fall through to normal promotion logic below

                elif complaint_rate >= DOMAIN_COMPLAINT_RATE_BURN and complaints_7d < min_complaints:
                    # Rate exceeds burn threshold but complaint count below ESP minimum.
                    # This happens for Entra domains with 1-2 spam kills (1.9-3.8% rate).
                    # Enter monitoring instead of burning — wait for pattern confirmation.
                    await self._enter_domain_monitoring(
                        domain_id, domain_name, effective_trigger,
                        reason=f"{esp_type or 'unknown'}: rate {complaint_rate*100:.3f}% "
                               f"exceeds burn threshold but only {complaints_7d}/{min_complaints} "
                               f"spam kills — monitoring for pattern"
                    )
                    # Fall through to normal promotion logic below

                else:
                    # Below thresholds. Inbox kill was sufficient. Domain is fine.
                    print(f"    [INBOX KILL] {domain_name} ({esp_type or 'unknown'}): "
                          f"{complaints_7d} spam kills, rate {complaint_rate*100:.3f}% "
                          f"— inbox-level only, domain safe")

        # Only promote if the killed inbox was deployed (live).
        # Reserve and warning inboxes don't get replaced — we just lose
        # one bench position; allocation will refill on next graduation.
        if killed_pool != 'live':
            return

        # ==========================================
        # INBOX-LEVEL TRIGGER: PROMOTE BENCH (CROSS-DOMAIN)
        # ==========================================
        # Post-2026-04-27 overhaul: domain mixing is approved for promotion.
        # When a live inbox dies we pull the oldest reserve from anywhere in
        # the workspace, not just the same domain. This protects sending
        # capacity (CEO commitment: 50k sends/month) — without cross-domain
        # promotion, killing the third inbox on a 3-inbox Google domain
        # leaves the live pool short with no replacement on hand.
        #
        # The promoted inbox's `inventory_pool_status` becomes 'live';
        # its source domain's `pool_status` stays 'reserve'. set_tag_sync
        # reads the per-inbox status as authority on the next cycle and
        # tags 'live' on the promoted inbox while keeping its siblings on
        # the source domain as 'reserve'.

        # Pick the oldest healthy reserve inbox via the shared domain-aware
        # selector. Same selector used by orchestrator's threshold maintenance,
        # so kill-driven and proactive promotions follow identical ordering:
        # finish a tapped reserve domain before opening a new one.
        candidates = await pick_promotion_candidates(self.db, workspace_id, n=1)
        candidate = candidates[0] if candidates else None

        if candidate:
            # Promote in DB + write inbox_rotation_history row in one transaction.
            # set_tag_sync's verified write loop applies the EB tags on the
            # next cycle (reads inventory_pool_status as authority).
            #
            # We also issue an immediate EB tag adjustment here because the
            # kill is happening NOW and the campaign filter may pick from
            # `live`-tagged inboxes within seconds. Tag-first then untag, so
            # if untag fails the inbox briefly has both tags (self-heals)
            # rather than briefly having no pool tag (campaigns can't pick).
            await promote_inbox_to_deployed(
                db=self.db,
                inbox_id=candidate['id'],
                workspace_id=workspace_id,
                reason=(
                    f"kill_replacement: replacing {killed_inbox['email_address']} "
                    f"(killed by {effective_trigger}) from "
                    f"domain={killed_inbox['domain_name']}; "
                    f"source domain={candidate['domain_name']} "
                    f"(deployed={candidate['deployed_count']}, "
                    f"reserve={candidate['reserve_count']})"
                ),
                triggered_by='kill_processor',
                rotation_type='promote',
                metadata={
                    'killed_inbox_id': str(killed_inbox_id),
                    'killed_inbox_email': killed_inbox['email_address'],
                    'kill_trigger': effective_trigger,
                    'killed_domain': killed_inbox['domain_name'],
                    'source_domain': candidate['domain_name'],
                },
            )

            # Apply EB tag immediately so campaigns can route to the promoted
            # inbox without waiting for the next set_tag_sync cycle.
            if candidate.get('id') and eb_workspace_id:
                try:
                    a_tag_name = killed_inbox.get('a_set_tag_name') or 'live'
                    b_tag_name = killed_inbox.get('b_set_tag_name') or 'reserve'
                    a_tag = await self.client.get_or_create_tag(a_tag_name)
                    b_tag = await self.client.get_or_create_tag(b_tag_name)
                    a_tag_id = a_tag.get('id')
                    b_tag_id = b_tag.get('id')

                    # Look up EB account id for the candidate (the selector
                    # doesn't return it because it's used by both kill and
                    # orchestrator paths; only kill needs immediate EB tag).
                    eb_account_id = await self.db.fetchval("""
                        SELECT emailbison_account_id::int
                        FROM sender_accounts WHERE id = $1
                    """, candidate['id'])

                    if eb_account_id and a_tag_id:
                        # TAG-FIRST: add live tag. If this fails, inbox keeps
                        # its prior 'reserve' tag (valid state, no orphan).
                        await self.client.tag_inbox(eb_account_id, a_tag_id)
                        # UNTAG-SECOND: remove reserve. If this fails, inbox
                        # briefly has both tags (self-heals next set_tag_sync).
                        if b_tag_id:
                            try:
                                await self.client.untag_inbox(eb_account_id, b_tag_id)
                            except EmailBisonAPIError:
                                pass

                    print(f"    [PROMOTE] {candidate['email_address']}: reserve → deployed (replacing killed inbox)")
                except EmailBisonAPIError as e:
                    print(f"    [WARN] Failed to apply EB tag during promotion (DB updated; next sync will reconcile): {e}")
        else:
            # No reserve available - check if this is critical
            domain_a_set_count = await self.db.fetchval("""
                SELECT COUNT(*)
                FROM sender_accounts
                WHERE domain_id = $1
                AND inbox_state = 'live'
                AND status = 'Connected'
                AND inventory_pool_status = 'live'
            """, domain_id)

            if domain_a_set_count == 0:
                print(f"    [WARNING] No reserve available and live exhausted for {killed_inbox.get('domain_name', domain_id)}")
                # Domain may need rotation - the waterfall view will flag this

    async def _handle_domain_killing_trigger(
        self,
        domain_id: UUID,
        domain_name: str,
        workspace_id: UUID,
        trigger_type: str,
        killed_inbox_email: str
    ):
        """
        Handle confirmed domain-level triggers.

        Called for:
        - Provider blocks (provider_block_*): instant — unambiguously domain-level
        - Spam complaints: only after cross-inbox check confirms 2+ inboxes affected

        Actions:
        1. Mark the ENTIRE A-Set domain as 'burned'
        2. Promote a B-Set DOMAIN to A-Set (not individual inboxes)
        3. Log rotation event and alert
        """
        print(f"    [DOMAIN KILL] {domain_name}: {trigger_type} on {killed_inbox_email}")
        print(f"    [DOMAIN KILL] Burning domain and promoting B-Set domain")

        # 1. Check if domain is currently live (A-Set)
        current_pool = await self.db.fetchval("""
            SELECT pool_status FROM domains WHERE id = $1
        """, domain_id)

        # 2. Burn the domain and promote reserve domain (using SQL function)
        # Both live AND reserve domains can be burned. Reserve domains with
        # high complaint rates must not be immune — and must not be promoted.
        promoted_domain = None
        if current_pool in ('live', 'reserve'):
            try:
                result = await self.db.fetchrow("""
                    SELECT * FROM burn_domain_and_promote($1, $2)
                """, domain_id, trigger_type)

                if result:
                    action = result.get('action', '')
                    if result['promoted_domain_name']:
                        promoted_domain = result['promoted_domain_name']
                        print(f"    [DOMAIN KILL] Promoted reserve domain: {promoted_domain}")
                    elif action == 'no_reserve':
                        print(f"    [DOMAIN KILL] WARNING: No healthy reserve domain available to promote!")
                    elif action == 'burned_reserve':
                        print(f"    [DOMAIN KILL] Burned reserve domain {domain_name} (no promotion needed)")
            except Exception as e:
                # Function may not exist yet - fall back to manual update
                print(f"    [DOMAIN KILL] burn_domain_and_promote not available: {e}")
                await self.db.execute("""
                    UPDATE domains
                    SET
                        pool_status = 'burned',
                        burned_at = NOW(),
                        burn_trigger = $2,
                        updated_at = NOW()
                    WHERE id = $1
                    AND pool_status IN ('live', 'reserve')
                """, domain_id, trigger_type)

        # 3. Update domain state (legacy compatibility)
        await self.db.execute("""
            UPDATE domains
            SET
                domain_state = CASE
                    WHEN domain_state = 'live' THEN 'flagged'::domain_state
                    ELSE domain_state
                END,
                updated_at = NOW()
            WHERE id = $1
        """, domain_id)

        # 2. Count remaining live inboxes that will be affected
        remaining = await self.db.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE inventory_pool_status = 'live') as a_set_count,
                COUNT(*) FILTER (WHERE inventory_pool_status = 'reserve') as b_set_count,
                COUNT(*) as total_live
            FROM sender_accounts
            WHERE domain_id = $1
            AND inbox_state = 'live'
        """, domain_id)

        a_set_remaining = remaining['a_set_count'] or 0
        b_set_remaining = remaining['b_set_count'] or 0
        total_remaining = remaining['total_live'] or 0

        # 3. Log the domain burn event
        await self.db.execute("""
            INSERT INTO inbox_rotation_history (
                workspace_id, rotation_type,
                reason, triggered_by,
                metadata
            ) VALUES (
                $1,
                'domain_burn',
                $2,
                'kill_trigger',
                $3::jsonb
            )
        """,
            workspace_id,
            f"Domain {domain_name} burned due to {trigger_type} on {killed_inbox_email}",
            f'{{"domain_id": "{domain_id}", "domain_name": "{domain_name}", '
            f'"trigger_type": "{trigger_type}", "killed_inbox": "{killed_inbox_email}", '
            f'"a_set_remaining": {a_set_remaining}, "b_set_on_domain": {b_set_remaining}}}'
        )

        # 4. Insert domain rotation event for tracking
        try:
            await self.db.execute("""
                INSERT INTO domain_rotation_events (
                    domain_id,
                    workspace_id,
                    event_type,
                    trigger_type,
                    trigger_inbox_email,
                    old_status,
                    new_status,
                    a_set_remaining,
                    b_set_quarantined,
                    notes
                ) VALUES ($1, $2, 'domain_burn', $3, $4, 'live', 'burned', $5, $6, $7)
            """,
                domain_id,
                workspace_id,
                trigger_type,
                killed_inbox_email,
                a_set_remaining,
                b_set_remaining,
                f"Domain-killing trigger {trigger_type} fired. Domain burned, reserve auto-promotes."
            )
        except Exception as e:
            # Table may not exist yet - log but don't fail
            print(f"    [WARNING] Could not log domain_rotation_event: {e}")

        print(f"    [DOMAIN KILL] A-Set: {a_set_remaining}, B-Set: {b_set_remaining} on burned domain")
        print(f"    [DOMAIN KILL] Domain {domain_name} burned")

        # 5. Check for promoted reserve domain (now live)
        promoted_info = await self.db.fetchrow("""
            SELECT domain_name
            FROM domains
            WHERE workspace_id = $1
            AND pool_status = 'live'
            AND promoted_at IS NOT NULL
            AND promoted_at >= NOW() - INTERVAL '1 minute'
            ORDER BY promoted_at DESC
            LIMIT 1
        """, workspace_id)
        promoted_domain = promoted_info['domain_name'] if promoted_info else None

        # 6. Get reserve runway for workspace
        reserve_runway = await self.db.fetchrow("""
            SELECT COUNT(*) as reserve_count
            FROM domains
            WHERE workspace_id = $1
            AND pool_status = 'reserve'
            AND is_active = TRUE
        """, workspace_id)
        reserves_remaining = reserve_runway['reserve_count'] if reserve_runway else 0

        # 7. Send Slack alert with investigation context
        if self.alerter:
            try:
                if promoted_domain:
                    action_text = f"Reserve domain `{promoted_domain}` promoted to live."
                    next_steps = "Monitor promoted domain. Review campaign lists for this workspace."
                else:
                    action_text = "Domain burned. *No reserve domain available to promote!*"
                    next_steps = "URGENT: Order replacement domains via HyperTide."

                await self.alerter.send_alert(
                    level="critical",
                    title=f"Domain Burned: {domain_name}",
                    message=(
                        f"*Trigger:* `{trigger_type}` on `{killed_inbox_email}`\n"
                        f"*Action:* {action_text}\n"
                        f"*Burned domain:* {domain_name} ({total_remaining} inboxes)\n"
                        f"*Reserve runway:* {reserves_remaining} reserve domains remaining\n"
                        f"*Next Steps:* {next_steps}"
                    ),
                    context={
                        "domain": domain_name,
                        "trigger": trigger_type,
                        "killed_inbox": killed_inbox_email,
                        "promoted_domain": promoted_domain,
                        "reserves_remaining": reserves_remaining
                    }
                )
            except Exception as e:
                print(f"    [WARNING] Failed to send Slack alert: {e}")

    async def decay_burn_counters(self):
        """
        Decay 7-day burn counters (run daily).

        Simple approach: reduce by ~14% daily to approximate 7-day rolling window.
        Same decay logic as health_checks.py uses for bounce counters.
        """
        await self.db.execute("""
            UPDATE emailbison_campaigns
            SET
                inboxes_burned_7d = GREATEST(0, (COALESCE(inboxes_burned_7d, 0) * 0.86)::INTEGER),
                domains_burned_7d = GREATEST(0, (COALESCE(domains_burned_7d, 0) * 0.86)::INTEGER),
                updated_at = NOW()
            WHERE inboxes_burned_7d > 0 OR domains_burned_7d > 0
        """)
        print("[KillProcessor] Decayed 7d burn counters")

    async def _recalculate_domain_metrics(self, domain_id: UUID):
        """
        Recalculate aggregate metrics for a domain after an inbox death.

        Calls the database function created in migration 037 which calculates:
        - domain_bounce_rate_7d (aggregate of all inbox bounce rates)
        - domain_sends_7d / domain_bounces_7d (totals)
        - inboxes_with_complaints / inboxes_with_blocks (cross-inbox detection)
        - burn_breakdown (JSONB with trigger type counts)
        """
        try:
            await self.db.execute(
                "SELECT recalculate_domain_metrics($1)",
                domain_id
            )
        except Exception as e:
            # Don't fail the kill process if metrics calc fails
            print(f"    [WARNING] Failed to recalculate domain metrics: {e}")

    async def _recalculate_domain_velocity(self, domain_id: UUID):
        """
        Recalculate burn velocity and projected days-to-critical for a domain.

        Called after each inbox kill to update:
        - burn_velocity_30d (kills in last 30 days)
        - projected_days_to_critical (days until 50% capacity)

        Uses database function created in migration 084.
        """
        try:
            await self.db.execute(
                "SELECT recalculate_domain_velocity($1)",
                domain_id
            )
        except Exception as e:
            # Don't fail the kill process if velocity calc fails
            print(f"    [WARNING] Failed to recalculate domain velocity: {e}")

    async def get_burn_breakdown_by_campaign(self, campaign_id: UUID) -> Dict:
        """
        Get breakdown of burns by trigger type for a campaign.

        Returns:
            Dict with trigger types and counts, e.g.:
            {"spam_complaint": 3, "hard_blocked_24h": 2, "fresh_inbox_bounce": 1}
        """
        rows = await self.db.fetch("""
            SELECT
                kill_trigger_type,
                COUNT(*) as count
            FROM campaign_burn_events
            WHERE campaign_id = $1
            GROUP BY kill_trigger_type
            ORDER BY count DESC
        """, campaign_id)

        return {row['kill_trigger_type']: row['count'] for row in rows}

    async def get_burn_breakdown_by_domain(self, domain_id: UUID) -> Dict:
        """
        Get breakdown of burns by trigger type for a domain.

        Returns:
            Dict with trigger types and counts
        """
        rows = await self.db.fetch("""
            SELECT
                kill_trigger_type,
                COUNT(*) as count
            FROM campaign_burn_events
            WHERE domain_id = $1
            GROUP BY kill_trigger_type
            ORDER BY count DESC
        """, domain_id)

        return {row['kill_trigger_type']: row['count'] for row in rows}
