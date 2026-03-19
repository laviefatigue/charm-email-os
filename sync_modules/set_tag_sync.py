"""
Set Tag Sync Module (A-Set / B-Set Management)

Manages A-Set and B-Set inbox tags in EmailBison.

DOMAIN-LEVEL ALLOCATION (Migration 076):
Entire DOMAINS are allocated to A-Set or B-Set, not individual inboxes.
- domain.pool_status = 'live'    → ALL inboxes tagged 'live' (A-Set)
- domain.pool_status = 'reserve' → ALL inboxes tagged 'reserve' (B-Set)
- domain.pool_status = 'burned'  → Skip (compromised)
- domain.pool_status = 'unassigned' → Skip (needs allocation first)

WHY DOMAIN-LEVEL?
When a domain-killing trigger (spam_complaint) fires, ALL inboxes on that
domain are compromised. Mixed A/B per domain means B-Set is useless.
With domain-level: B-Set domains are completely isolated, safe to promote.

STANDARD TAG NAMING:
- 'live'       = A-Set (deployed to campaigns, actively sending)
- 'reserve'    = B-Set (warmed reserve, ready to promote when A-Set burns)
- 'incubating' = Warming up (< 21 days), not yet graduated

Legacy tags ('A Set'/'B Set', 'bset') are detected but new workspaces use standard names.

This module runs AFTER lifecycle_tag_sync.py - it only acts on graduated inboxes.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


# Standard tag names (use these for new workspaces)
DEFAULT_A_SET_TAG = 'live'      # A-Set: deployed to campaigns
DEFAULT_B_SET_TAG = 'reserve'   # B-Set: warmed reserve, ready to promote

# Legacy tag names (some older workspaces use these - will migrate over time)
LEGACY_A_SET_TAGS = ['A Set', 'a set', 'a-set', 'aset']
LEGACY_B_SET_TAGS = ['B Set', 'b set', 'b-set', 'bset']  # 'bset' is legacy, use 'reserve'

# Legacy: inbox-level percentages (no longer used with domain-level allocation)
# Domain-level allocation: ALL inboxes follow domain.pool_status
# Kept for reference only - allocation now happens at domain level (50/50 domains)

INCUBATION_DAYS = 21


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

            if tagged_a > 0 or tagged_b > 0 or promoted > 0:
                print(f"  [{workspace_name}] A-Set: +{tagged_a}, B-Set: +{tagged_b}, Promoted: {promoted}")

            return await audit.complete(metadata={
                'domains_processed': len(domains),
                'tagged_a_set': tagged_a,
                'tagged_b_set': tagged_b,
                'promoted_to_a_set': promoted
            })

        except Exception as e:
            return await audit.fail(e)

    async def _resolve_tag_names(
        self,
        configured_a: Optional[str],
        configured_b: Optional[str]
    ) -> Tuple[str, str]:
        """
        Resolve tag names - use configured values or detect from existing tags.

        Detection priority:
        1. Use explicitly configured names
        2. Check for standard tags ('live'/'reserve')
        3. Check for legacy tags ('A Set'/'B Set', 'bset')
        4. Fall back to defaults ('live'/'reserve')

        Standard naming:
        - live = A-Set (deployed to campaigns)
        - reserve = B-Set (warmed reserve)
        - incubating = Still warming up
        """
        if configured_a and configured_b:
            return configured_a, configured_b

        # Try to detect existing tags
        try:
            existing_tags = await self.client.list_tags()
            tag_names_lower = {t.get('name', '').lower(): t.get('name') for t in existing_tags}

            # Prefer standard tags first
            if 'live' in tag_names_lower and 'reserve' in tag_names_lower:
                return 'live', 'reserve'

            # Check for 'live' with legacy 'bset' (migrate to 'reserve')
            if 'live' in tag_names_lower and 'bset' in tag_names_lower:
                print("    [MIGRATE] Found 'bset' tag, will create 'reserve' instead")
                return 'live', 'reserve'

            # Check for legacy 'A Set'/'B Set' tags
            for legacy_a in LEGACY_A_SET_TAGS:
                if legacy_a.lower() in tag_names_lower:
                    # Find matching B-Set tag
                    for legacy_b in LEGACY_B_SET_TAGS:
                        if legacy_b.lower() in tag_names_lower:
                            return tag_names_lower[legacy_a.lower()], tag_names_lower[legacy_b.lower()]
                    # A-Set found but no B-Set, use reserve
                    return tag_names_lower[legacy_a.lower()], 'reserve'

        except Exception:
            pass  # Fall back to defaults

        return DEFAULT_A_SET_TAG, DEFAULT_B_SET_TAG

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
        Sync A-Set/B-Set for a single domain.

        DOMAIN-LEVEL ALLOCATION (Migration 076):
        - Entire domains are A-Set or B-Set, not individual inboxes
        - If domain.pool_status = 'live': ALL inboxes tagged 'live' (A-Set)
        - If domain.pool_status = 'reserve': ALL inboxes tagged 'reserve' (B-Set)
        - If domain.pool_status = 'burned': Skip (compromised)
        - If domain.pool_status = 'unassigned'/NULL: Skip (needs allocation first)

        This prevents blast radius: when a domain burns, B-Set domains are isolated.
        """
        domain_id = domain['domain_id']
        domain_name = domain['domain_name']
        domain_pool_status = domain.get('pool_status')
        graduated_count = domain['graduated_inbox_count']

        result = {'tagged_a': 0, 'tagged_b': 0, 'promoted': 0}

        # Skip domains with no graduated inboxes
        if graduated_count == 0:
            return result

        # Burned domains: remove live/reserve tags from all inboxes (prevent campaign assignment)
        if domain_pool_status == 'burned':
            print(f"    [BURNED] {domain_name}: Removing live/reserve tags from burned domain inboxes")
            burned_inboxes = await self._get_all_graduated_inboxes(domain_id)
            for inbox in burned_inboxes:
                account_id = inbox.get('emailbison_account_id')
                if not account_id or inbox.get('status') != 'Connected':
                    continue
                try:
                    # Remove both A-Set and B-Set tags
                    if a_set_tag_id:
                        await self.client.untag_inbox(account_id, a_set_tag_id)
                    if b_set_tag_id:
                        await self.client.untag_inbox(account_id, b_set_tag_id)
                    result['tagged_a'] += 1  # Track cleanup count
                except Exception as e:
                    print(f"      [WARN] Failed to untag {inbox.get('email_address')}: {e}")
            # Update DB: clear pool status for burned domain inboxes
            await self.db.execute("""
                UPDATE sender_accounts
                SET inventory_pool_status = NULL, updated_at = NOW()
                WHERE domain_id = $1 AND is_active = TRUE
                  AND inbox_state = 'live'
                  AND inventory_pool_status IS NOT NULL
            """, domain_id)
            return result

        # Skip cancelled domains - HyperTide order cancelled, inboxes are orphaned
        if domain_pool_status == 'cancelled':
            return result

        # Skip unassigned domains - they need allocation first
        if domain_pool_status in (None, 'unassigned'):
            # Don't spam logs - this is expected for domains not yet allocated
            return result

        # DOMAIN-LEVEL ALLOCATION: All inboxes follow the domain's pool status
        # If domain is 'live' -> all inboxes are A-Set (deployed)
        # If domain is 'reserve' -> all inboxes are B-Set (reserve)
        if domain_pool_status == 'live':
            target_set = 'deployed'
            target_tag_id = a_set_tag_id
            other_tag_id = b_set_tag_id
            set_label = 'A-Set'
        elif domain_pool_status == 'reserve':
            target_set = 'reserve'
            target_tag_id = b_set_tag_id
            other_tag_id = a_set_tag_id
            set_label = 'B-Set'
        else:
            # Unknown status
            return result

        # Get ALL graduated inboxes and split by connection state.
        # Disconnected inboxes: DB-only update (no EB operations possible).
        # Connected inboxes: EB tagging FIRST, then DB update per-inbox on success.
        # This prevents the race condition where DB updates before EB, causing
        # next sync to skip retrying failed EB operations.
        all_inboxes = await self._get_all_graduated_inboxes(domain_id)

        if not all_inboxes:
            return result

        connected_inboxes = [
            inbox for inbox in all_inboxes
            if inbox['status'] == 'Connected' and inbox['emailbison_account_id']
        ]
        disconnected_inboxes = [
            inbox for inbox in all_inboxes
            if inbox['status'] != 'Connected' or not inbox['emailbison_account_id']
        ]

        # 1. Bulk-update DB for DISCONNECTED inboxes (no EB work needed)
        disconnected_mismatched = [
            inbox['id'] for inbox in disconnected_inboxes
            if inbox['inventory_pool_status'] != target_set
        ]
        if disconnected_mismatched:
            await self.db.execute("""
                UPDATE sender_accounts
                SET inventory_pool_status = $2, updated_at = NOW()
                WHERE id = ANY($1::uuid[])
            """, disconnected_mismatched, target_set)

        # 2. Tag CONNECTED inboxes in EB, then update DB per-inbox on success
        for inbox in connected_inboxes:
            audit.increment_processed()
            eb_account_id = int(inbox['emailbison_account_id'])
            current_pool = inbox['inventory_pool_status']

            # Skip if already in correct set (EB tag already correct)
            if current_pool == target_set:
                continue

            # Check if this is a promotion (reserve → deployed)
            is_promotion = current_pool == 'reserve' and target_set == 'deployed'

            try:
                # Remove old tag if present
                if current_pool in ('deployed', 'reserve'):
                    try:
                        await self.client.untag_inbox(eb_account_id, other_tag_id)
                    except EmailBisonAPIError as e:
                        print(f"    [WARN] Failed to remove tag {other_tag_id} from inbox {eb_account_id} ({inbox['email_address']}): {e}")

                # Add new tag
                await self.client.tag_inbox(eb_account_id, target_tag_id)

                # EB tagging succeeded — now update DB
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET inventory_pool_status = $2, updated_at = NOW()
                    WHERE id = $1
                """, inbox['id'], target_set)

                if target_set == 'deployed':
                    result['tagged_a'] += 1
                    if is_promotion:
                        result['promoted'] += 1
                        print(f"    [PROMOTE] {inbox['email_address']} → {set_label} (domain promotion)")
                    else:
                        print(f"    [TAG] {inbox['email_address']} → {set_label}")
                else:
                    result['tagged_b'] += 1
                    print(f"    [TAG] {inbox['email_address']} → {set_label}")

                audit.increment_updated()

            except EmailBisonAPIError as e:
                # EB tagging failed — DB NOT updated so next sync will retry
                audit.add_error(
                    record_id=inbox['email_address'],
                    error=f"Failed to tag: {e}"
                )

        return result

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
                health_score
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
                CASE WHEN inventory_pool_status = 'deployed' THEN 0 ELSE 1 END,
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
                COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'deployed' AND sa.status = 'Connected') as a_set_connected,
                COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'deployed' AND sa.status != 'Connected') as a_set_disconnected,
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
