"""
Set Tag Sync Module — Per-Inbox Pool Authority

Manages the 'live' and 'reserve' pool tags in EmailBison so they reflect each
inbox's `inventory_pool_status`.

Authority model (post-2026-04-27 overhaul)
──────────────────────────────────────────
`sender_accounts.inventory_pool_status` is the SOLE authority for which pool
tag an inbox carries in EmailBison. `domains.pool_status` is no longer read
here — it stays as a domain-level concept for allocation/burn scope but does
not drive per-inbox tagging.

Per-inbox state → EB tag:

    inventory_pool_status     EB pool tag(s)
    ─────────────────────────────────────────
    'live'                live (and untag reserve)
    'reserve'                 reserve (and untag live)
    NULL                      NEITHER — unallocated, no pool

Note: pre-2026-04-29 the table also included 'warning' and 'quarantined'
intermediate states (active circuit breaker — untag both). Those were
removed per ADR-007 because v3 spec doesn't include a warning soft-pause:
inboxes that hit bounce thresholds queue for kill via health_checks
rather than entering an indefinite paused state. Existing 'warning'
rows are drained by migration 098.

Reconciliation discipline
─────────────────────────
Every cycle, set_tag_sync issues an untag of the OPPOSITE pool tag even when
the DB and EB already match — idempotent, no-cost if absent. This fixes the
historic skip-bug where an inbox with `inventory_pool_status='reserve'` and
target='reserve' was skipped, leaving an orphan 'live' tag in EB from a
previous graduation.

ESP differentiation
───────────────────
- Microsoft Entra inboxes are managed by lifecycle_tag_sync directly: they
  graduate to 'live' permanently and ride to death. set_tag_sync still
  enforces that 'live' is set and 'reserve' is absent for them — but never
  changes their pool status.
- Google inboxes graduate to 'reserve'. Cross-domain promotion to 'live'
  is performed by kill_processor and reflected here on the next cycle.

Standard tag names (only)
─────────────────────────
- 'live'       = deployed to campaigns
- 'reserve'    = warmed bench, awaits promotion
- 'incubating' = warming up (managed by lifecycle_tag_sync)

Legacy tag names ('A Set', 'B Set', 'bset') are no longer supported.
Workspaces with non-standard names raise an error at sync time. Phase 0
diagnostics (2026-04-27) confirmed all 11 active workspaces use 'live' and
'reserve' — there is nothing to migrate.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


# Required tag names — workspaces MUST use these.
REQUIRED_A_SET_TAG = 'live'      # deployed
REQUIRED_B_SET_TAG = 'reserve'   # bench

# Legacy compat exports (kept for any external imports; constants remain
# unused inside this module).
DEFAULT_A_SET_TAG = REQUIRED_A_SET_TAG
DEFAULT_B_SET_TAG = REQUIRED_B_SET_TAG

INCUBATION_DAYS = 21

# ESP markers (must match values stored in sender_accounts.esp).
ESP_MICROSOFT = 'microsoft'


class SetTagSyncModule:
    """
    Manages A-Set and B-Set inbox tags in EmailBison.

    DOMAIN-LEVEL ALLOCATION:
    This module tags inboxes based on their DOMAIN's pool_status:
    - Domain is 'live' → ALL inboxes tagged 'live' (A-Set, deployed)
    - Domain is 'reserve' → ALL inboxes tagged 'reserve' (B-Set, backup)

    This ensures blast radius isolation: when a domain burns (spam complaint),
    all inboxes on that domain are compromised. B-Set domains remain safe.

    Domain allocation (50/50 split) happens via:
    - Migration 076: allocate_domain_sets(workspace_id) function
    - API endpoint: /infrastructure/domain-sets/{workspace_id}/allocate
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
        Sync A-Set/B-Set tags for all active workspaces.

        Returns:
            List of SyncResult for each workspace processed
        """
        results = []

        workspaces = await self.db.fetch("""
            SELECT id, workspace_name, emailbison_workspace_id,
                   a_set_tag_name, b_set_tag_name
            FROM workspaces
            WHERE emailbison_workspace_id IS NOT NULL
            AND is_active = TRUE
        """)

        print(f"[SetTagSync] Processing {len(workspaces)} workspaces")

        for ws in workspaces:
            try:
                result = await self.sync_workspace_sets(
                    workspace_id=ws['id'],
                    workspace_name=ws['workspace_name'],
                    emailbison_workspace_id=int(ws['emailbison_workspace_id']),
                    a_set_tag_name=ws.get('a_set_tag_name'),
                    b_set_tag_name=ws.get('b_set_tag_name')
                )
                results.append(result)

                # Add delay between workspaces to avoid rate limiting
                await self.client.inter_batch_delay(1.0)

            except Exception as e:
                print(f"[SetTagSync] Error syncing {ws['workspace_name']}: {e}")

        return results

    async def sync_workspace_sets(
        self,
        workspace_id: UUID,
        workspace_name: str,
        emailbison_workspace_id: int,
        a_set_tag_name: Optional[str] = None,
        b_set_tag_name: Optional[str] = None
    ) -> SyncResult:
        """
        Sync A-Set/B-Set tags for a single workspace.

        Steps:
        1. Detect or use configured tag names (A Set/B Set vs live/bset)
        2. Get all domains with their set configuration
        3. For each domain:
           a. Get graduated inboxes (priority-ranked)
           b. Calculate target A-Set/B-Set counts
           c. Tag inboxes that need set assignment
           d. Promote B-Set → A-Set if A-Set below threshold

        Args:
            workspace_id: Our workspace UUID
            workspace_name: Workspace name for logging
            emailbison_workspace_id: EmailBison workspace ID
            a_set_tag_name: Custom A-Set tag name (or None to detect)
            b_set_tag_name: Custom B-Set tag name (or None to detect)

        Returns:
            SyncResult with counts
        """
        audit = await self.audit_logger.start_audit(
            sync_type='set_tags',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Switch to workspace context
            if not await self.client.switch_workspace(emailbison_workspace_id):
                return await audit.fail(Exception(f"Failed to switch to workspace {workspace_name}"))

            # Detect or use configured tag names
            a_tag_name, b_tag_name = await self._resolve_tag_names(
                a_set_tag_name, b_set_tag_name
            )

            print(f"  [{workspace_name}] Using tags: A-Set='{a_tag_name}', B-Set='{b_tag_name}'")

            # Get or create the tags
            a_set_tag = await self.client.get_or_create_tag(a_tag_name)
            b_set_tag = await self.client.get_or_create_tag(b_tag_name)

            a_set_tag_id = a_set_tag.get('id')
            b_set_tag_id = b_set_tag.get('id')

            if not a_set_tag_id or not b_set_tag_id:
                return await audit.fail(Exception("Failed to get/create set tags"))

            # Save tag names to workspace if not already set
            await self._save_workspace_tag_config(
                workspace_id, a_tag_name, b_tag_name
            )

            # Get domains in this workspace
            domains = await self._get_workspace_domains(workspace_id)

            tagged_a = 0
            tagged_b = 0
            promoted = 0
            cleared = 0

            for domain in domains:
                domain_result = await self._sync_domain_sets(
                    domain=domain,
                    a_set_tag_id=a_set_tag_id,
                    b_set_tag_id=b_set_tag_id,
                    audit=audit
                )
                tagged_a += domain_result['tagged_a']
                tagged_b += domain_result['tagged_b']
                promoted += domain_result['promoted']
                cleared += domain_result.get('cleared', 0)

            if tagged_a > 0 or tagged_b > 0 or promoted > 0 or cleared > 0:
                print(f"  [{workspace_name}] live: +{tagged_a}, reserve: +{tagged_b}, promoted: {promoted}, cleared: {cleared}")

            return await audit.complete(metadata={
                'domains_processed': len(domains),
                'tagged_a_set': tagged_a,
                'tagged_b_set': tagged_b,
                'promoted_to_a_set': promoted,
                'cleared_pool_tags': cleared,
            })

        except Exception as e:
            return await audit.fail(e)

    async def _resolve_tag_names(
        self,
        configured_a: Optional[str],
        configured_b: Optional[str]
    ) -> Tuple[str, str]:
        """
        Validate workspace tag config. Standard names ('live'/'reserve') are required.

        Phase 0 of the 2026-04-27 overhaul confirmed all active workspaces use
        the standard names. Legacy detection ('A Set'/'B Set'/'bset') was
        removed because it lets a misconfigured workspace silently mis-tag.

        Behavior:
        - If both configured values are 'live'/'reserve' → use them.
        - If unset (NULL) → use standards.
        - If anything else → raise: workspace must be migrated to standards
          before this sync can run safely.
        """
        a = configured_a or REQUIRED_A_SET_TAG
        b = configured_b or REQUIRED_B_SET_TAG

        if a != REQUIRED_A_SET_TAG or b != REQUIRED_B_SET_TAG:
            raise ValueError(
                f"Workspace tag config must be a_set='{REQUIRED_A_SET_TAG}' / "
                f"b_set='{REQUIRED_B_SET_TAG}' but got a_set='{a}' / b_set='{b}'. "
                f"Migrate the workspace to standard tag names before re-running."
            )

        return a, b

    async def _save_workspace_tag_config(
        self,
        workspace_id: UUID,
        a_tag_name: str,
        b_tag_name: str
    ):
        """Save detected/configured tag names to workspace for future reference."""
        await self.db.execute("""
            UPDATE workspaces
            SET
                a_set_tag_name = COALESCE(a_set_tag_name, $2),
                b_set_tag_name = COALESCE(b_set_tag_name, $3),
                updated_at = NOW()
            WHERE id = $1
        """, workspace_id, a_tag_name, b_tag_name)

    async def _is_domain_quarantined(self, domain_id: UUID) -> bool:
        """
        Check if a domain has been quarantined due to domain-killing triggers.

        A domain is quarantined if:
        1. It has inboxes with inventory_pool_status = 'quarantined'
        2. OR it has a recent domain_rotation_event of type 'quarantine'

        Quarantined domains should NOT have B-Set promoted - the domain is compromised.
        """
        result = await self.db.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE inventory_pool_status = 'quarantined') as quarantined_count,
                EXISTS (
                    SELECT 1 FROM domain_rotation_events dre
                    WHERE dre.domain_id = $1
                    AND dre.event_type = 'quarantine'
                    AND dre.created_at > NOW() - INTERVAL '30 days'
                ) as has_recent_quarantine_event
            FROM sender_accounts
            WHERE domain_id = $1
            AND inbox_state = 'live'
        """, domain_id)

        if not result:
            return False

        return (result['quarantined_count'] > 0) or result['has_recent_quarantine_event']

    async def _get_workspace_domains(self, workspace_id: UUID) -> List[Dict]:
        """Get all domains with pool status and graduated inbox counts for a workspace."""
        return await self.db.fetch("""
            SELECT
                d.id as domain_id,
                d.domain_name,
                d.pool_status,  -- Domain-level pool: 'live', 'reserve', 'burned', 'unassigned'
                COALESCE(d.infrastructure_type,
                    CASE
                        WHEN EXISTS (SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id AND sa.esp = 'microsoft') THEN 'entra'
                        WHEN EXISTS (SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id AND sa.esp = 'gmail') THEN 'google'
                        ELSE 'unknown'
                    END
                ) as provider,
                -- Count ACTUAL graduated connected inboxes (not expected_inbox_count)
                (
                    SELECT COUNT(*)
                    FROM sender_accounts sa
                    WHERE sa.domain_id = d.id
                    AND sa.is_active = TRUE
                    AND sa.inbox_state = 'live'
                    AND sa.status = 'Connected'
                    AND (
                        sa.inventory_lifecycle_status = 'active'
                        OR (sa.warmup_started_at IS NOT NULL AND sa.warmup_started_at <= NOW() - INTERVAL '21 days')
                    )
                ) as graduated_inbox_count
            FROM domains d
            WHERE d.workspace_id = $1
            AND d.is_active = TRUE
            AND EXISTS (
                SELECT 1 FROM sender_accounts sa
                WHERE sa.domain_id = d.id
                AND sa.inbox_state = 'live'
                AND sa.is_active = TRUE
            )
        """, workspace_id)

    async def _sync_domain_sets(
        self,
        domain: Dict,
        a_set_tag_id: int,
        b_set_tag_id: int,
        audit
    ) -> Dict:
        """
        Reconcile EB pool tags with each inbox's `inventory_pool_status`.

        Per-inbox authority (post-2026-04-27 overhaul, updated ADR-007 2026-04-29):
        - 'live'    → ensure 'live' tag, untag 'reserve'
        - 'reserve'     → ensure 'reserve' tag, untag 'live'
        - NULL          → untag both (unallocated; was also 'warning'/'quarantined' pre-ADR-007)

        Domain-scope actions still apply:
        - domain.pool_status = 'burned'    → clear all inbox pool tags + DB
        - domain.pool_status = 'cancelled' → skip (HyperTide order cancelled)

        Reconciliation discipline: every cycle issues an untag of the OPPOSITE
        pool tag even when DB and EB agree on target. This is idempotent (a
        no-op if absent) and is what fixes the 133 dual-tagged inboxes from
        the previous skip-bug, without requiring a separate cleanup pass.

        Microsoft Entra inboxes are NEVER re-pooled here — lifecycle_tag_sync
        sets them to 'live' permanently and they ride to death. We still
        emit the reconciling untag of 'reserve' on them in case a stale tag
        slipped in.
        """
        domain_id = domain['domain_id']
        domain_name = domain['domain_name']
        domain_pool_status = domain.get('pool_status')
        graduated_count = domain['graduated_inbox_count']

        result = {'tagged_a': 0, 'tagged_b': 0, 'promoted': 0, 'cleared': 0}

        # No graduated inboxes — nothing to reconcile.
        if graduated_count == 0:
            return result

        # Cancelled domains: HyperTide order cancelled, inboxes are orphaned.
        # We don't touch them — leave whatever EB has, they're not our concern.
        if domain_pool_status == 'cancelled':
            return result

        # Burned domains: domain-scope action, clear ALL pool tags from EB and DB.
        if domain_pool_status == 'burned':
            print(f"    [BURNED] {domain_name}: Clearing pool tags from burned-domain inboxes")
            burned_inboxes = await self._get_all_graduated_inboxes(domain_id)
            for inbox in burned_inboxes:
                account_id = inbox.get('emailbison_account_id')
                if not account_id or inbox.get('status') != 'Connected':
                    continue
                try:
                    await self.client.untag_inbox(account_id, a_set_tag_id)
                    await self.client.untag_inbox(account_id, b_set_tag_id)
                    result['cleared'] += 1
                except Exception as e:
                    print(f"      [WARN] Failed to untag {inbox.get('email_address')}: {e}")
            await self.db.execute("""
                UPDATE sender_accounts
                SET inventory_pool_status = NULL, updated_at = NOW()
                WHERE domain_id = $1 AND is_active = TRUE
                  AND inbox_state = 'live'
                  AND inventory_pool_status IS NOT NULL
            """, domain_id)
            return result

        # All other domain states (live, reserve, unassigned, NULL): iterate
        # by inbox and let per-inbox `inventory_pool_status` drive the decision.
        all_inboxes = await self._get_all_graduated_inboxes(domain_id)
        if not all_inboxes:
            return result

        for inbox in all_inboxes:
            audit.increment_processed()

            # Skip inboxes with no EB ID or not connected — we cannot tag them
            # in EB. The DB is already authoritative; nothing to reconcile.
            account_id = inbox.get('emailbison_account_id')
            if not account_id or inbox.get('status') != 'Connected':
                continue

            eb_account_id = int(account_id)
            current_pool = inbox.get('inventory_pool_status')
            esp = inbox.get('esp')

            # Microsoft Entra is permanent-live (CEO directive — legacy fleet
            # rides to death). Force live + strip reserve regardless of what
            # the per-inbox DB column happens to say. This makes the rollout
            # forgiving to the 1,032 Microsoft inboxes whose
            # inventory_pool_status was NULL pre-backfill — without this
            # branch the NULL → "untag both" path would strip live tags
            # from currently-sending Microsoft inboxes during the deploy
            # window before scripts/backfill_pool_status.py runs.
            if esp == ESP_MICROSOFT:
                # Microsoft pin: tag-first ensures we never strip the live tag
                # if the subsequent untag(reserve) fails.
                try:
                    await self.client.tag_inbox(eb_account_id, a_set_tag_id)
                    result['tagged_a'] += 1
                    audit.increment_updated()
                except EmailBisonAPIError as e:
                    audit.add_error(
                        record_id=inbox['email_address'],
                        error=f"MS live-tag enforcement failed: {e}",
                    )
                    continue  # don't proceed to untag if tag failed
                try:
                    await self.client.untag_inbox(eb_account_id, b_set_tag_id)
                except EmailBisonAPIError:
                    pass  # transient dual tag, heals next cycle
                continue

            # Decide target tag and which other tag to remove.
            target_tag_id, other_tag_id, target_label = self._pool_to_tag_targets(
                current_pool, a_set_tag_id, b_set_tag_id
            )

            # Reconciliation: ALWAYS converge to the desired tag set.
            # Order matters for failure-mode safety:
            #   - TAG TARGET FIRST. If the tag call fails, the inbox keeps its
            #     prior valid tag and we abort the per-inbox sequence — no
            #     orphan/stripped state is created.
            #   - UNTAG OPPOSITE SECOND. If this fails, the inbox briefly has
            #     both tags. The next cycle's reconciling untag clears it.
            # Untag-first would have the opposite (worse) failure mode: a
            # successful untag followed by a failed tag would leave the inbox
            # with no pool tag, causing campaigns to drop it from the live pool.
            try:
                if target_tag_id is None:
                    # No target — unallocated (NULL pool). Untag both. Order
                    # doesn't matter because we're not adding anything.
                    # Note: pre-2026-04-29 this branch also handled the
                    # 'warning' and 'quarantined' soft-pause states; those
                    # were removed per ADR-007 (no more circuit-breaker
                    # intermediate state — bounce thresholds queue kills).
                    try:
                        await self.client.untag_inbox(eb_account_id, a_set_tag_id)
                    except EmailBisonAPIError:
                        pass
                    try:
                        await self.client.untag_inbox(eb_account_id, b_set_tag_id)
                    except EmailBisonAPIError:
                        pass
                    continue

                # TAG TARGET FIRST.
                await self.client.tag_inbox(eb_account_id, target_tag_id)

                # UNTAG OPPOSITE SECOND. Failure here = transient dual tag,
                # self-heals on the next cycle (which is now 15 min, per the
                # POLL_INTERVAL_KILL bump in the orchestrator).
                try:
                    await self.client.untag_inbox(eb_account_id, other_tag_id)
                except EmailBisonAPIError as e:
                    msg = str(e)
                    if '404' not in msg and 'not found' not in msg.lower():
                        print(f"    [WARN] Untag opposite failed for {inbox['email_address']} (will retry next cycle): {e}")

                # Microsoft inboxes: DO NOT update inventory_pool_status from
                # set_tag_sync. lifecycle_tag_sync owns their pool lifetime.
                # Only count for visibility.
                if esp == ESP_MICROSOFT:
                    if target_label == 'live':
                        result['tagged_a'] += 1
                    audit.increment_updated()
                    continue

                # Google / unknown: DB already reflects per-inbox status because
                # promotion (kill_processor) and graduation (lifecycle_tag_sync)
                # both update inventory_pool_status. set_tag_sync just enforces
                # EB tags. No DB write needed here.
                if target_label == 'live':
                    result['tagged_a'] += 1
                else:
                    result['tagged_b'] += 1
                audit.increment_updated()

            except EmailBisonAPIError as e:
                # Tag/untag failed mid-write. DB authority is unaffected; the
                # next cycle will re-attempt because we always emit reconciling
                # untags whether or not DB matches.
                audit.add_error(
                    record_id=inbox['email_address'],
                    error=f"Tag reconciliation failed: {e}"
                )

        return result

    @staticmethod
    def _pool_to_tag_targets(
        pool_status: Optional[str],
        a_set_tag_id: int,
        b_set_tag_id: int,
    ) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        """
        Map an inbox's `inventory_pool_status` to (target_tag_id, opposite_tag_id, label).

        target_tag_id is None when no pool tag should be present (NULL or
        unknown). In that case opposite_tag_id is also None and the caller
        untags BOTH pool tags.

        Note: pre-2026-04-29 (ADR-007), 'warning' and 'quarantined' returned
        (None, None, None) too — they were intermediate active-circuit-breaker
        states. They are no longer set by sync_accounts; existing rows are
        drained by migration 098.

        Returns:
            (target_tag_id, opposite_tag_id, label):
                - 'live'    → (live, reserve, 'live')
                - 'reserve'     → (reserve, live, 'reserve')
                - else (NULL/unknown) → (None, None, None)
        """
        if pool_status == 'live':
            return a_set_tag_id, b_set_tag_id, 'live'
        if pool_status == 'reserve':
            return b_set_tag_id, a_set_tag_id, 'reserve'
        return None, None, None

    async def _get_all_graduated_inboxes(self, domain_id: UUID) -> List[Dict]:
        """
        Get ALL graduated inboxes for a domain (connected or not).

        Used for bulk DB pool status updates — the database should reflect
        domain allocation regardless of connection state. EB API tagging
        is filtered to Connected inboxes separately.

        Includes:
        - Live inboxes (inbox_state = 'live')
        - Graduated (inventory_lifecycle_status = 'active' OR 14+ days warmup)
        """
        return await self.db.fetch("""
            SELECT
                id,
                email_address,
                emailbison_account_id,
                status,
                inbox_state,
                inventory_pool_status,
                inventory_lifecycle_status,
                warmup_started_at,
                health_score,
                esp
            FROM sender_accounts
            WHERE domain_id = $1
            AND is_active = TRUE
            AND inbox_state = 'live'
            AND (
                inventory_lifecycle_status = 'active'
                OR (
                    warmup_started_at IS NOT NULL
                    AND warmup_started_at <= NOW() - INTERVAL '21 days'
                )
            )
            ORDER BY
                CASE WHEN inventory_pool_status = 'live' THEN 0 ELSE 1 END,
                warmup_started_at ASC NULLS LAST,
                health_score DESC NULLS LAST
        """, domain_id)

    # NOTE: B-Set -> A-Set promotion on kill is handled by kill_processor._promote_backup_inbox()
    # This module only handles periodic re-balancing of set assignments.

    async def get_set_distribution_summary(self, workspace_id: UUID) -> Dict:
        """
        Get summary of A-Set/B-Set distribution for a workspace.

        Returns:
            Dict with counts by provider and set status
        """
        stats = await self.db.fetch("""
            SELECT
                COALESCE(d.infrastructure_type,
                    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END
                ) as provider,
                COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'live' AND sa.status = 'Connected') as a_set_connected,
                COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'live' AND sa.status != 'Connected') as a_set_disconnected,
                COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve') as b_set,
                COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'incubating') as incubating,
                COUNT(*) as total
            FROM sender_accounts sa
            JOIN domains d ON sa.domain_id = d.id
            WHERE d.workspace_id = $1
            AND sa.is_active = TRUE
            AND sa.inbox_state = 'live'
            AND d.pool_status != 'cancelled'
            GROUP BY
                COALESCE(d.infrastructure_type,
                    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END
                )
        """, workspace_id)

        return {row['provider']: dict(row) for row in stats}
