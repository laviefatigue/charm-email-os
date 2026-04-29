"""
Lifecycle Tag Sync Module

Manages inbox lifecycle tags in EmailBison to control campaign assignment.

Graduation model (post-2026-04-27 overhaul)
───────────────────────────────────────────
Reserve is the bench: graduation lands inboxes there, and kill_processor
promotes from reserve to live to maintain sending capacity. Campaigns are
reapplied by filtering on the 'live' tag, which naturally drains stale
campaign_inboxes entries when reapply runs.

ESP-aware graduation:
- Google: graduate to RESERVE (tag 'reserve', inventory_pool_status='reserve').
  Cross-domain promotion to live happens via kill_processor when a live
  inbox dies.
- Microsoft Entra (legacy): graduate directly to LIVE (tag 'live',
  inventory_pool_status='live'). No reserve concept for Entra — the
  legacy fleet rides to death.

Tag transitions handled here:
1. warmup_started_at set, < 14 BD                → add 'incubating' tag
2. 14 BD warmup complete, esp='microsoft'        → remove 'incubating', add 'live'
3. 14 BD warmup complete, esp='gmail' (Google)   → remove 'incubating', add 'reserve'
4. inbox_state='dead'                            → remove 'live' (safety net for kill_processor)

Phase 3 will replace the calendar-day INCUBATION_DAYS check with a
business-day calculation. This module currently still uses 21 calendar days.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


# Tag names used for lifecycle management
INCUBATING_TAG = 'incubating'
LIVE_TAG = 'live'        # A-Set: deployed, sending campaigns (Microsoft direct, Google after promotion)
RESERVE_TAG = 'reserve'  # B-Set: warmed bench, awaiting promotion (Google graduations)

# Graduation window: 14 BUSINESS days (Mon-Fri), measured from warmup_started_at.
# Holiday awareness is intentionally not included for v1 — the SQL uses
# EXTRACT(DOW FROM d) NOT IN (0,6) so weekends are excluded but federal /
# bank holidays still count as business days. This was acceptable for v1
# because the kill triggers downstream re-evaluate on real send activity, so
# a one-day-too-early graduation does not mean an immediate problem.
INCUBATION_BUSINESS_DAYS = 14

# Calendar-day fallback constant kept for legacy callers (e.g. dashboards).
# All graduation logic in this module uses INCUBATION_BUSINESS_DAYS.
INCUBATION_DAYS = 21

# ESP identifier used by sender_accounts.esp for Google Workspace inboxes.
# Code that branches "Microsoft = legacy live, Google = reserve graduation"
# must use this constant — historic data uses 'gmail' rather than 'google'.
ESP_GOOGLE = 'gmail'
ESP_MICROSOFT = 'microsoft'


class LifecycleTagSyncModule:
    """
    Manages inbox lifecycle tags in EmailBison.

    This module ensures EmailBison tags reflect the local database state:
    - Inboxes in incubation (< 21 days warmup) have 'incubating' tag
    - Graduated inboxes (21+ days warmup) have 'live' tag
    - Dead inboxes have neither (kill_processor handles flagged_* tags)

    The team uses these tags to control which inboxes can be assigned to campaigns.
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

    async def sync_all_workspaces(self) -> List[SyncResult]:
        """
        Sync lifecycle tags for all active workspaces.

        Returns:
            List of SyncResult for each workspace processed
        """
        results = []

        workspaces = await self.db.fetch("""
            SELECT id, workspace_name, emailbison_workspace_id
            FROM workspaces
            WHERE emailbison_workspace_id IS NOT NULL
            AND is_active = TRUE
        """)

        print(f"[LifecycleTagSync] Processing {len(workspaces)} workspaces")

        for ws in workspaces:
            try:
                result = await self.sync_workspace_tags(
                    workspace_id=ws['id'],
                    workspace_name=ws['workspace_name'],
                    emailbison_workspace_id=int(ws['emailbison_workspace_id'])
                )
                results.append(result)

                # Add delay between workspaces to avoid rate limiting
                await self.client.inter_batch_delay(1.0)

            except Exception as e:
                print(f"[LifecycleTagSync] Error syncing {ws['workspace_name']}: {e}")

        return results

    async def sync_workspace_tags(
        self,
        workspace_id: UUID,
        workspace_name: str,
        emailbison_workspace_id: int
    ) -> SyncResult:
        """
        Sync lifecycle tags for a single workspace.

        Handles:
        1. Graduate inboxes from 'incubating' to 'live' (21+ days warmup)
        2. Tag new warmup inboxes with 'incubating'
        3. Remove 'live' tag from dead inboxes (consistency check)

        Args:
            workspace_id: Our workspace UUID
            workspace_name: Workspace name for logging
            emailbison_workspace_id: EmailBison workspace ID

        Returns:
            SyncResult with counts of tags added/removed
        """
        audit = await self.audit_logger.start_audit(
            sync_type='lifecycle_tags',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Switch to workspace context (no-op for workspace-scoped clients).
            if not await self.client.switch_workspace(emailbison_workspace_id):
                return await audit.fail(Exception(f"Failed to switch to workspace {workspace_name}"))

            # Get or create the three lifecycle tags. 'reserve' is needed because
            # Google graduations now land in reserve rather than live.
            incubating_tag = await self.client.get_or_create_tag(INCUBATING_TAG)
            live_tag = await self.client.get_or_create_tag(LIVE_TAG)
            reserve_tag = await self.client.get_or_create_tag(RESERVE_TAG)

            incubating_tag_id = incubating_tag.get('id')
            live_tag_id = live_tag.get('id')
            reserve_tag_id = reserve_tag.get('id')

            if not incubating_tag_id or not live_tag_id or not reserve_tag_id:
                return await audit.fail(Exception("Failed to get/create lifecycle tags"))

            # 1. Graduate mature inboxes (ESP-aware: Google→reserve, Microsoft→live)
            graduated = await self._graduate_mature_inboxes(
                workspace_id=workspace_id,
                incubating_tag_id=incubating_tag_id,
                live_tag_id=live_tag_id,
                reserve_tag_id=reserve_tag_id,
                audit=audit
            )

            # 2. Tag new warmup inboxes with 'incubating'
            new_incubating = await self._tag_new_warmup_inboxes(
                workspace_id=workspace_id,
                incubating_tag_id=incubating_tag_id,
                audit=audit
            )

            # 3. Remove 'live' tag from dead inboxes (consistency safety net)
            cleaned = await self._remove_live_from_dead(
                workspace_id=workspace_id,
                live_tag_id=live_tag_id,
                audit=audit
            )

            # 4. Untag 'incubating' from inboxes that are now lifecycle='active'.
            # Catches the orphan-tag pattern where:
            #   - Graduation untag failed silently (try/except on line 292)
            #   - Clerical-bypass UPDATE set lifecycle='active' without untagging
            # Scoped to recent activity to limit per-cycle EB calls.
            untag_orphan = await self._untag_incubating_from_active(
                workspace_id=workspace_id,
                incubating_tag_id=incubating_tag_id,
                audit=audit
            )

            if graduated > 0 or new_incubating > 0 or cleaned > 0 or untag_orphan > 0:
                print(f"  [{workspace_name}] Graduated: {graduated}, New incubating: {new_incubating}, Cleaned: {cleaned}, Untag orphan incubating: {untag_orphan}")

            return await audit.complete(metadata={
                'graduated': graduated,
                'new_incubating': new_incubating,
                'live_removed_dead': cleaned,
                'untag_orphan_incubating': untag_orphan,
            })

        except Exception as e:
            return await audit.fail(e)

    async def _graduate_mature_inboxes(
        self,
        workspace_id: UUID,
        incubating_tag_id: int,
        live_tag_id: int,
        reserve_tag_id: int,
        audit
    ) -> int:
        """
        Graduate inboxes that have completed warmup.

        ESP-aware destination (post-overhaul):
        - Microsoft Entra inboxes  → live (inventory_pool_status='live')
          Legacy fleet rides to death; reserve concept does not apply.
        - Google / unknown ESP     → reserve (inventory_pool_status='reserve')
          Bench position; kill_processor promotes to live when capacity drops.

        Eligibility:
        - inbox_state = 'live'
        - is_active = TRUE
        - warmup_started_at >= INCUBATION_BUSINESS_DAYS business days ago
          (Mon-Fri only; holiday awareness deferred to v2)
        - warmup_enabled = TRUE  (current state; historical pause is invisible)
        - inventory_lifecycle_status = 'incubating'
        - emailbison_account_id IS NOT NULL

        Order of operations matters: we tag in EmailBison FIRST, and only update
        the DB on success. If tagging fails the inbox stays incubating in DB
        and the next cycle retries — preventing a desync where DB shows
        'active' but EB still has the 'incubating' tag.

        Returns:
            Number of inboxes graduated.
        """
        # Eligibility uses BUSINESS days (Mon-Fri) since warmup_enabled_since
        # — the timestamp of the most recent FALSE/NULL → TRUE transition of
        # warmup_enabled. This is maintained by the trigger added in migration
        # 094 and gives us a continuous-enabled requirement: a paused-then-
        # resumed warmup resets the clock, which matches the operational
        # intent ("warmed for 14 business days without interruption").
        ready_to_graduate = await self.db.fetch("""
            SELECT
                id,
                email_address,
                emailbison_account_id,
                warmup_started_at,
                warmup_enabled_since,
                esp
            FROM sender_accounts
            WHERE workspace_id = $1
            AND inbox_state = 'live'
            AND is_active = TRUE
            AND warmup_enabled = TRUE
            AND warmup_enabled_since IS NOT NULL
            AND inventory_lifecycle_status = 'incubating'
            AND emailbison_account_id IS NOT NULL
            AND (
                SELECT COUNT(*)
                FROM generate_series(
                    warmup_enabled_since::date,
                    CURRENT_DATE - INTERVAL '1 day',
                    INTERVAL '1 day'
                ) AS d
                WHERE EXTRACT(DOW FROM d) NOT IN (0, 6)
            ) >= $2
        """, workspace_id, INCUBATION_BUSINESS_DAYS)

        graduated_count = 0

        for inbox in ready_to_graduate:
            audit.increment_processed()
            eb_account_id = int(inbox['emailbison_account_id'])
            esp = inbox.get('esp')

            # Microsoft → deployed (live tag, permanent).
            # Google / unknown → reserve (bench, awaits promotion).
            if esp == ESP_MICROSOFT:
                target_tag_id = live_tag_id
                target_pool_status = 'live'
                target_tag_label = 'live'
            else:
                target_tag_id = reserve_tag_id
                target_pool_status = 'reserve'
                target_tag_label = 'reserve'

            try:
                # Remove 'incubating' tag (best-effort; absence is fine).
                try:
                    await self.client.untag_inbox(eb_account_id, incubating_tag_id)
                except EmailBisonAPIError as e:
                    print(f"    [WARN] Failed to remove 'incubating' tag from inbox {eb_account_id} ({inbox['email_address']}): {e}")

                # Add destination tag (live for Microsoft, reserve for Google).
                await self.client.tag_inbox(eb_account_id, target_tag_id)

                # EB succeeded — update DB to match. inventory_pool_status is the
                # authority for set_tag_sync going forward (post-overhaul model).
                # The graduation is logged to inbox_rotation_history so the
                # transition from incubating → reserve/deployed has an audit
                # row alongside other pool transitions.
                async with self.db.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute("""
                            UPDATE sender_accounts
                            SET
                                inventory_lifecycle_status = 'active',
                                inventory_pool_status = $2,
                                updated_at = NOW()
                            WHERE id = $1
                        """, inbox['id'], target_pool_status)

                        await conn.execute("""
                            INSERT INTO inbox_rotation_history (
                                workspace_id, rotation_type,
                                target_inbox_id, target_inbox_email,
                                source_pool, target_pool,
                                reason, triggered_by,
                                success, executed_at
                            ) VALUES (
                                $1, 'graduate',
                                $2, $3,
                                NULL, $4,
                                $5, 'lifecycle_tag_sync',
                                TRUE, NOW()
                            )
                        """,
                            workspace_id,
                            inbox['id'], inbox['email_address'],
                            target_pool_status,
                            f"14 BD warmup complete for {esp or 'unknown'} inbox",
                        )

                graduated_count += 1
                audit.increment_updated()

                print(f"    [GRADUATE] {inbox['email_address']} ({esp or 'unknown'}) - incubating -> {target_tag_label}")

            except EmailBisonAPIError as e:
                audit.add_error(
                    record_id=inbox['email_address'],
                    error=f"Failed to graduate: {e}"
                )

        return graduated_count

    async def _tag_new_warmup_inboxes(
        self,
        workspace_id: UUID,
        incubating_tag_id: int,
        audit
    ) -> int:
        """
        Tag new warmup inboxes with 'incubating'.

        Finds inboxes that:
        - Have warmup_started_at set (recently started warming)
        - Are live
        - Have warmup_started_at < 21 days ago
        - Are not yet graduated (inventory_lifecycle_status IS NULL OR 'incubating')

        IMPORTANT: This must NOT match 'active' (graduated) or 'dead' (killed)
        inboxes. The pre-overhaul filter `!= 'incubating'` matched 'active'
        and re-tagged graduated inboxes back to 'incubating', reverting the
        graduation (commit 7e79c0e fixed that). However, NULL-only was too
        narrow: sync_accounts.upsert independently sets lifecycle='incubating'
        for new inboxes via its calendar-day CASE without ever calling EB to
        tag them. Result: 266 fleet-wide inboxes (Charm 251, SKMR 14, Spout 1)
        had lifecycle='incubating' in DB but NO 'incubating' tag in EB —
        invisible to this function. Caught by 2026-04-28 fleet tag audit.

        Including 'incubating' here lets the function self-heal that orphan
        state. The DB UPDATE is conditional (only fires for NULL → 'incubating')
        so already-incubating rows don't bump updated_at unnecessarily.

        Returns:
            Number of inboxes tagged
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=INCUBATION_DAYS)

        # Find newly warming inboxes that need 'incubating' tag
        new_warmup = await self.db.fetch("""
            SELECT
                id,
                email_address,
                emailbison_account_id,
                warmup_started_at,
                inventory_lifecycle_status
            FROM sender_accounts
            WHERE workspace_id = $1
            AND inbox_state = 'live'
            AND is_active = TRUE
            AND warmup_started_at IS NOT NULL
            AND warmup_started_at > $2
            AND emailbison_account_id IS NOT NULL
            AND (inventory_lifecycle_status IS NULL
                 OR inventory_lifecycle_status = 'incubating')
        """, workspace_id, cutoff)

        tagged_count = 0

        for inbox in new_warmup:
            audit.increment_processed()
            eb_account_id = int(inbox['emailbison_account_id'])

            try:
                # Add 'incubating' tag (idempotent in EB — re-tagging a
                # tagged inbox is a no-op).
                await self.client.tag_inbox(eb_account_id, incubating_tag_id)

                # Conditional UPDATE: only fires when DB lifecycle is NULL
                # (truly new inbox). For inboxes already at 'incubating'
                # (the self-heal case), the WHERE doesn't match and no
                # UPDATE happens — avoids bumping updated_at uselessly
                # and triggering downstream domain_health updates.
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET
                        inventory_lifecycle_status = 'incubating',
                        updated_at = NOW()
                    WHERE id = $1
                      AND inventory_lifecycle_status IS NULL
                """, inbox['id'])

                tagged_count += 1
                audit.increment_updated()

                # Different log line for self-heal vs. brand-new tag.
                if inbox['inventory_lifecycle_status'] == 'incubating':
                    print(f"    [TAG SELF-HEAL] {inbox['email_address']} - re-applied missing 'incubating' tag")
                else:
                    print(f"    [TAG] {inbox['email_address']} - added 'incubating' tag")

            except EmailBisonAPIError as e:
                audit.add_error(
                    record_id=inbox['email_address'],
                    error=f"Failed to tag: {e}"
                )

        return tagged_count

    async def _untag_incubating_from_active(
        self,
        workspace_id: UUID,
        incubating_tag_id: int,
        audit
    ) -> int:
        """
        Remove 'incubating' tag from inboxes that are now lifecycle='active'.

        Catches the orphan-tag pattern where the EB 'incubating' tag persists
        after an inbox transitions out of incubating:
          - Graduation untag failed silently (best-effort try/except in
            _graduate_mature_inboxes line 292).
          - Clerical-bypass UPDATE (admin SQL setting lifecycle='active'
            for inboxes that were pushed into campaigns prematurely, e.g.
            the Stable Kernel ODSC pattern of 2026-04-28) doesn't go
            through the graduation untag path.

        Scope is limited to inboxes that recently became 'active' (per
        inbox_rotation_history within the last 24h) to bound the per-cycle
        EB call count. Pre-existing orphans older than that need a one-shot
        cleanup script (scripts/cleanup_orphan_incubating_tags.py).

        Returns:
            Number of tags removed (idempotent — repeated runs return 0).
        """
        # Recent transitions to 'active' via either graduation or threshold/
        # promote. Clerical bypasses that don't write a history row would
        # need to do so to be picked up here — that's the rule going forward.
        candidates = await self.db.fetch("""
            SELECT DISTINCT
                sa.id,
                sa.email_address,
                sa.emailbison_account_id
            FROM sender_accounts sa
            JOIN inbox_rotation_history irh ON irh.target_inbox_id = sa.id
            WHERE sa.workspace_id = $1
              AND sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.inventory_lifecycle_status = 'active'
              AND sa.emailbison_account_id IS NOT NULL
              AND irh.executed_at > NOW() - INTERVAL '24 hours'
              AND irh.rotation_type IN ('graduate', 'promote', 'threshold_promotion', 'clerical_bypass')
        """, workspace_id)

        if not candidates:
            return 0

        untagged_count = 0
        for inbox in candidates:
            eb_account_id = int(inbox['emailbison_account_id'])
            try:
                await self.client.untag_inbox(eb_account_id, incubating_tag_id)
                untagged_count += 1
            except EmailBisonAPIError as e:
                # 404/not-tagged is the steady state — already cleaned. Only
                # log if the error looks unexpected.
                msg = str(e)
                if '404' not in msg and 'not found' not in msg.lower():
                    print(f"    [WARN] untag 'incubating' on active inbox {inbox['email_address']} failed: {e}")

        return untagged_count

    async def _remove_live_from_dead(
        self,
        workspace_id: UUID,
        live_tag_id: int,
        audit
    ) -> int:
        """
        Remove 'live' tag from dead inboxes (consistency check).

        This catches any edge cases where an inbox was killed but still has
        the 'live' tag. The kill_processor should handle this, but this
        provides a safety net.

        Returns:
            Number of tags removed
        """
        # Find dead inboxes that might still have 'live' tag.
        # Safety net: catches partial kill_processor failures where inbox_state
        # was set to 'dead' but inventory_lifecycle_status wasn't updated.
        dead_with_live = await self.db.fetch("""
            SELECT
                id,
                email_address,
                emailbison_account_id
            FROM sender_accounts
            WHERE workspace_id = $1
            AND inbox_state = 'dead'
            AND emailbison_account_id IS NOT NULL
            AND inventory_lifecycle_status != 'dead'
        """, workspace_id)

        cleaned_count = 0

        for inbox in dead_with_live:
            audit.increment_processed()
            eb_account_id = int(inbox['emailbison_account_id'])

            try:
                # Try to remove 'live' tag
                await self.client.untag_inbox(eb_account_id, live_tag_id)

                # Update local status
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET
                        inventory_lifecycle_status = 'dead',
                        updated_at = NOW()
                    WHERE id = $1
                """, inbox['id'])

                cleaned_count += 1
                audit.increment_updated()

                print(f"    [CLEAN] {inbox['email_address']} - removed 'live' tag (dead inbox)")

            except EmailBisonAPIError:
                # Tag may not exist, that's fine
                pass

        return cleaned_count

    async def get_lifecycle_summary(self, workspace_id: UUID) -> Dict:
        """
        Get summary of lifecycle tag states for a workspace.

        Returns:
            Dict with counts of inboxes in each lifecycle state
        """
        stats = await self.db.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE inbox_state = 'live' AND (warmup_started_at IS NULL OR warmup_started_at > NOW() - INTERVAL '21 days')) as incubating,
                COUNT(*) FILTER (WHERE inbox_state = 'live' AND warmup_started_at IS NOT NULL AND warmup_started_at <= NOW() - INTERVAL '21 days') as live,
                COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead,
                COUNT(*) as total
            FROM sender_accounts
            WHERE workspace_id = $1
            AND is_active = TRUE
        """, workspace_id)

        return {
            'incubating': stats['incubating'] or 0,
            'live': stats['live'] or 0,
            'dead': stats['dead'] or 0,
            'total': stats['total'] or 0
        }
