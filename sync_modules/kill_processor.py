"""
Kill Queue Processor

Processes inboxes flagged for removal from active use:
1. Tag inbox in EmailBison with trigger-specific tag (e.g., "flagged_fresh_inbox_bounce")
2. Mark inbox as 'dead' locally so it won't be used in new campaigns

Tag Format: flagged_{trigger_type}
Examples:
  - flagged_fresh_inbox_bounce
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
from .slack_alerter import SlackAlerter


class KillProcessor:
    """
    Processes the kill queue by tagging and flagging bad inboxes.

    Inboxes are tagged in EmailBison with trigger-specific tags
    (e.g., flagged_fresh_inbox_bounce) and marked as 'dead' locally.
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

    async def process_queue(self) -> SyncResult:
        """
        Process the kill queue:
        1. Tag pending items in EmailBison
        2. Mark inboxes as 'dead' locally (no deletion from EmailBison)
        """
        audit = await self.audit_logger.start_audit(
            sync_type='kill_queue',
            metadata={'scope': 'process_all'}
        )

        try:
            # Tag pending items and mark as dead locally
            # NOTE: We do NOT delete from EmailBison - inboxes stay but are flagged
            tagged_count = await self.tag_pending_items(audit)

            print(f"[KillProcessor] Flagged inactive: {tagged_count}")

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def tag_pending_items(self, audit) -> int:
        """
        Tag pending kill queue items in EmailBison with trigger-specific tags.

        Each inbox is tagged with its specific trigger reason:
          - flagged_fresh_inbox_bounce
          - flagged_spam_complaint
          - flagged_hard_bounces_24h
          - flagged_hard_blocked_24h
          - etc.

        This provides visibility into WHY each inbox was flagged.
        Inboxes are NOT deleted from EmailBison - they remain but are tagged.
        """
        pending = await self.db.fetch("""
            SELECT
                kq.id,
                kq.inbox_id,
                kq.workspace_id,
                kq.trigger_type,
                kq.trigger_value,
                kq.trigger_threshold,
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
            WHERE kq.status = 'pending'
            AND sa.emailbison_account_id IS NOT NULL
            AND w.emailbison_workspace_id IS NOT NULL
        """)

        if not pending:
            return 0

        tagged_count = 0

        # Group by workspace for efficiency
        by_workspace = {}
        for item in pending:
            ws_id = item['emailbison_workspace_id']
            if ws_id not in by_workspace:
                by_workspace[ws_id] = []
            by_workspace[ws_id].append(item)

        for ws_id, items in by_workspace.items():
            try:
                # Switch to workspace
                await self.client.switch_workspace(int(ws_id))

                # Cache tags per workspace to avoid redundant API calls
                tag_cache = {}  # {trigger_type: tag_id}

                # Tag each inbox with its specific trigger tag
                for item in items:
                    audit.increment_processed()
                    trigger_type = item['trigger_type']

                    # Build trigger-specific tag name: flagged_{trigger_type}
                    tag_name = f"flagged_{trigger_type}"

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
                                continue
                        else:
                            tag_id = tag_cache[trigger_type]

                        # Tag in EmailBison with trigger-specific tag
                        await self.client.tag_inbox(
                            account_id=int(item['emailbison_account_id']),
                            tag_id=tag_id
                        )

                        # Remove A-Set tag (live or 'A Set' depending on workspace)
                        # This ensures the team can't accidentally assign dead inboxes
                        # Get workspace tag config
                        ws_tags = await self.db.fetchrow("""
                            SELECT a_set_tag_name FROM workspaces WHERE id = $1
                        """, item['workspace_id'])
                        a_set_tag_name = (ws_tags.get('a_set_tag_name') if ws_tags else None) or 'live'

                        a_set_tag_id = tag_cache.get(a_set_tag_name)
                        if not a_set_tag_id:
                            a_set_tag = await self.client.get_or_create_tag(a_set_tag_name)
                            a_set_tag_id = a_set_tag.get('id')
                            if a_set_tag_id:
                                tag_cache[a_set_tag_name] = a_set_tag_id

                        if a_set_tag_id:
                            try:
                                await self.client.untag_inbox(
                                    account_id=int(item['emailbison_account_id']),
                                    tag_id=a_set_tag_id
                                )
                            except EmailBisonAPIError:
                                pass  # May not have the tag - that's fine

                        # Also try to remove legacy 'live' if using different tag name
                        if a_set_tag_name != 'live':
                            try:
                                live_tag = await self.client.get_or_create_tag('live')
                                if live_tag.get('id'):
                                    await self.client.untag_inbox(
                                        account_id=int(item['emailbison_account_id']),
                                        tag_id=live_tag['id']
                                    )
                            except EmailBisonAPIError:
                                pass

                        # Update queue status to 'flagged' (final state - no deletion)
                        await self.db.execute("""
                            UPDATE kill_queue
                            SET
                                status = 'flagged',
                                tagged_at = NOW(),
                                tag_name = $2,
                                updated_at = NOW()
                            WHERE id = $1
                        """, item['id'], tag_name)

                        # Mark inbox as dead locally - cannot be used in new campaigns
                        # Also update inventory status columns for capacity tracking
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

                        # V3: Update domain dead_inbox_count and check state transitions
                        await self._update_domain_on_inbox_death(item['inbox_id'])

                        # V3: Update campaign burn counters + insert burn events
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

                        # V3: Recalculate domain aggregate metrics
                        if item.get('domain_id'):
                            await self._recalculate_domain_metrics(item['domain_id'])

                        # V3: Promote backup inbox to fill the gap
                        await self._promote_backup_inbox(item['inbox_id'], item['workspace_id'])

                        tagged_count += 1
                        audit.increment_updated()

                        print(f"    [FLAGGED] {item['email_address']} - tag: {tag_name}")

                    except EmailBisonAPIError as e:
                        audit.add_error(
                            record_id=item['email_address'],
                            error=f"Failed to tag: {e}",
                            details={'inbox_id': str(item['inbox_id']), 'tag': tag_name}
                        )

                        # Mark as failed
                        await self.db.execute("""
                            UPDATE kill_queue
                            SET status = 'failed', error_message = $2, updated_at = NOW()
                            WHERE id = $1
                        """, item['id'], str(e))

            except Exception as e:
                audit.add_error(
                    record_id=f"workspace_{ws_id}",
                    error=f"Workspace error: {e}"
                )

        return tagged_count

    # NOTE: delete_ready_items() has been removed.
    # Inboxes are now only flagged, not deleted from EmailBison.
    # The 'flagged' status is the final state in the kill queue workflow.

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
                COUNT(*) FILTER (WHERE inbox_state = 'live') as live_count,
                COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_count,
                COUNT(*) as total_count
            FROM sender_accounts
            WHERE workspace_id = $1
            AND is_active = TRUE
        """, workspace_id)

        # Get breakdown of dead inboxes by kill trigger
        trigger_breakdown = await self.db.fetch("""
            SELECT
                kill_trigger,
                COUNT(*) as count
            FROM sender_accounts
            WHERE workspace_id = $1
            AND inbox_state = 'dead'
            AND kill_trigger IS NOT NULL
            GROUP BY kill_trigger
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
        V3 Section 5: Update domain state when inbox dies.

        Domain State Transitions (tag-only, no deletion):
        - 1 dead inbox = 'flagged' (accelerate backup warming)
        - 2+ dead inboxes = 'dead' (tag entire domain for review)
        - >30% inboxes unhealthy = 'dead' (tag for review)

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

        # Calculate domain health metrics
        metrics = await self.db.fetchrow("""
            SELECT
                COUNT(*) as total_inboxes,
                COUNT(*) FILTER (WHERE inbox_state = 'live') as live_count,
                COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_count,
                COUNT(*) FILTER (WHERE health_score < 60) as unhealthy_count
            FROM sender_accounts
            WHERE domain_id = $1 AND is_active = TRUE
        """, domain_id)

        total = metrics['total_inboxes'] or 0
        dead_count = metrics['dead_count'] or 0
        unhealthy_count = metrics['unhealthy_count'] or 0

        # Calculate unhealthy percentage
        unhealthy_pct = (unhealthy_count / total * 100) if total > 0 else 0

        # Determine new domain state per V3 spec
        current_state = domain['domain_state']
        new_state = current_state

        if dead_count >= 2 or unhealthy_pct > 30:
            new_state = 'dead'
        elif dead_count >= 1:
            new_state = 'flagged'

        # Update domain metrics and state
        await self.db.execute("""
            UPDATE domains
            SET
                dead_inbox_count = $2,
                live_inbox_count = $3,
                health_percentage = CASE
                    WHEN $4 > 0 THEN (($3::DECIMAL / $4) * 100)
                    ELSE 0
                END,
                domain_state = $5::domain_state,
                updated_at = NOW()
            WHERE id = $1
        """, domain_id, dead_count, metrics['live_count'] or 0, total, new_state)

        # Log state transition
        if new_state != current_state:
            print(f"    [DOMAIN STATE] {domain['domain_name']}: {current_state} -> {new_state} "
                  f"(dead={dead_count}, unhealthy={unhealthy_pct:.1f}%)")

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

    async def _promote_backup_inbox(self, killed_inbox_id: UUID, workspace_id: UUID):
        """
        V3 Section 6: Promote B-Set inbox when A-Set inbox is killed.

        A-Set/B-Set System:
        - A-Set (deployed): Actively assigned to campaigns
        - B-Set (reserve): Warmed and ready to promote when A-Set dies

        When an A-Set inbox is killed:
        1. Find best connected B-Set inbox from same domain
        2. Promote to A-Set (update tag in EmailBison + local DB)
        3. Log rotation history

        NOTE: Also handles legacy pool_tier for backwards compatibility.
        """
        # Get the killed inbox's domain and pool status
        killed_inbox = await self.db.fetchrow("""
            SELECT
                sa.id, sa.email_address, sa.domain_id,
                sa.inventory_pool_status, sa.pool_tier,
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

        domain_id = killed_inbox['domain_id']
        killed_pool = killed_inbox['inventory_pool_status']
        eb_workspace_id = killed_inbox['emailbison_workspace_id']

        # Only promote if the killed inbox was in A-Set (deployed)
        if killed_pool != 'deployed':
            # Also handle legacy pool_tier for backwards compatibility
            killed_tier = killed_inbox['pool_tier'] or 'primary'
            if killed_tier not in ('primary', 'hot_backup'):
                return
            # Legacy path - continue below

        # ==========================================
        # NEW A-SET / B-SET PROMOTION LOGIC
        # ==========================================

        # Find best B-Set inbox to promote (connected, oldest warmup, highest health)
        candidate = await self.db.fetchrow("""
            SELECT id, email_address, emailbison_account_id
            FROM sender_accounts
            WHERE domain_id = $1
            AND workspace_id = $2
            AND inbox_state = 'live'
            AND status = 'Connected'
            AND inventory_pool_status = 'reserve'
            AND inventory_lifecycle_status = 'active'
            ORDER BY
                warmup_started_at ASC NULLS LAST,
                health_score DESC NULLS LAST
            LIMIT 1
        """, domain_id, workspace_id)

        if candidate and candidate['emailbison_account_id'] and eb_workspace_id:
            try:
                # Switch to workspace in EmailBison
                await self.client.switch_workspace(int(eb_workspace_id))

                # Get tag names (use workspace config or defaults)
                a_tag_name = killed_inbox.get('a_set_tag_name') or 'live'
                b_tag_name = killed_inbox.get('b_set_tag_name') or 'bset'

                # Get tag IDs
                a_tag = await self.client.get_or_create_tag(a_tag_name)
                b_tag = await self.client.get_or_create_tag(b_tag_name)
                a_tag_id = a_tag.get('id')
                b_tag_id = b_tag.get('id')

                eb_account_id = int(candidate['emailbison_account_id'])

                # Remove B-Set tag
                if b_tag_id:
                    try:
                        await self.client.untag_inbox(eb_account_id, b_tag_id)
                    except EmailBisonAPIError:
                        pass  # May not have tag

                # Add A-Set tag
                if a_tag_id:
                    await self.client.tag_inbox(eb_account_id, a_tag_id)

                # Update local database
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET
                        inventory_pool_status = 'deployed',
                        pool_tier = 'primary',
                        updated_at = NOW()
                    WHERE id = $1
                """, candidate['id'])

                # Log rotation history
                await self.db.execute("""
                    INSERT INTO inbox_rotation_history (
                        workspace_id, rotation_type,
                        source_inbox_id, source_inbox_email, source_pool,
                        target_inbox_id, target_inbox_email, target_pool,
                        reason, triggered_by
                    ) VALUES ($1, 'promote', $2, $3, 'dead', $4, $5, 'deployed', $6, 'kill_trigger')
                """,
                    workspace_id,
                    killed_inbox_id, killed_inbox['email_address'],
                    candidate['id'], candidate['email_address'],
                    f"B-Set promoted to A-Set after {killed_inbox['email_address']} killed"
                )

                print(f"    [PROMOTE] {candidate['email_address']}: B-Set → A-Set (replacing killed inbox)")

            except EmailBisonAPIError as e:
                print(f"    [ERROR] Failed to promote B-Set inbox: {e}")
        else:
            # No B-Set available - check if this is critical
            domain_a_set_count = await self.db.fetchval("""
                SELECT COUNT(*)
                FROM sender_accounts
                WHERE domain_id = $1
                AND inbox_state = 'live'
                AND status = 'Connected'
                AND inventory_pool_status = 'deployed'
            """, domain_id)

            if domain_a_set_count == 0:
                print(f"    [WARNING] No B-Set available and A-Set exhausted for {killed_inbox.get('domain_name', domain_id)}")
                # Domain may need rotation - the waterfall view will flag this

        # ==========================================
        # LEGACY POOL_TIER HANDLING (backwards compat)
        # ==========================================
        killed_tier = killed_inbox['pool_tier'] or 'primary'

        if killed_tier == 'primary' and not candidate:
            # Legacy path: promote hot_backup to primary
            backup = await self.db.fetchrow("""
                SELECT id, email_address
                FROM sender_accounts
                WHERE domain_id = $1
                AND workspace_id = $2
                AND pool_tier = 'hot_backup'
                AND inbox_state = 'live'
                ORDER BY health_score DESC, first_seen_at ASC
                LIMIT 1
            """, domain_id, workspace_id)

            if backup:
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET pool_tier = 'primary', updated_at = NOW()
                    WHERE id = $1
                """, backup['id'])

                await self.db.execute("""
                    INSERT INTO inbox_rotation_history (
                        workspace_id, rotation_type,
                        source_inbox_id, source_inbox_email, source_pool,
                        target_inbox_id, target_inbox_email, target_pool,
                        reason, triggered_by
                    ) VALUES ($1, 'promote', $2, $3, 'dead', $4, $5, 'primary', $6, 'kill_trigger')
                """,
                    workspace_id,
                    killed_inbox_id, killed_inbox['email_address'],
                    backup['id'], backup['email_address'],
                    f"Legacy: Promoted from hot_backup after {killed_inbox['email_address']} killed"
                )

                print(f"    [PROMOTE] {backup['email_address']}: hot_backup -> primary (legacy)")
                await self._promote_warming_to_hot_backup(domain_id, workspace_id)

        elif killed_tier == 'hot_backup':
            await self._promote_warming_to_hot_backup(domain_id, workspace_id)

    async def _promote_warming_to_hot_backup(self, domain_id: UUID, workspace_id: UUID):
        """Promote a warming inbox to hot_backup tier."""
        warming = await self.db.fetchrow("""
            SELECT id, email_address
            FROM sender_accounts
            WHERE domain_id = $1
            AND workspace_id = $2
            AND pool_tier = 'warming'
            AND inbox_state = 'live'
            AND warmup_enabled = TRUE
            ORDER BY first_seen_at ASC
            LIMIT 1
        """, domain_id, workspace_id)

        if warming:
            await self.db.execute("""
                UPDATE sender_accounts
                SET pool_tier = 'hot_backup', updated_at = NOW()
                WHERE id = $1
            """, warming['id'])

            await self.db.execute("""
                INSERT INTO inbox_rotation_history (
                    workspace_id, rotation_type,
                    target_inbox_id, target_inbox_email, target_pool,
                    reason, triggered_by
                ) VALUES ($1, 'promote', $2, $3, 'hot_backup', 'Promoted from warming to fill backup gap', 'kill_trigger')
            """, workspace_id, warming['id'], warming['email_address'])

            print(f"    [PROMOTE] {warming['email_address']}: warming -> hot_backup")
        else:
            # No warming inbox available - log warning
            print(f"    [WARNING] No warming inbox available to promote to hot_backup for domain {domain_id}")

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
