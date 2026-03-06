"""
Set Tag Sync Module (A-Set / B-Set Management)

Manages A-Set and B-Set inbox tags in EmailBison:
- A-Set (live/deployed): Actively assigned to campaigns
- B-Set (reserve): Warmed and ready to promote when A-Set inboxes die

Key Functions:
1. Tag graduated inboxes to appropriate set based on domain capacity
2. Promote B-Set → A-Set when A-Set capacity drops below threshold
3. Respect existing tag naming conventions per workspace

Tag Naming Conventions (workspace-configurable):
- Standard: 'live' / 'bset'
- Legacy: 'A Set' / 'B Set' (Searchatlas, older workspaces)

Set Percentages:
- Entra: 80% A-Set, 20% B-Set (40/10 split on 50-inbox domain)
- Google: 100% A-Set, 0% B-Set (reserve at domain level instead)

This module runs AFTER lifecycle_tag_sync.py - it only acts on graduated inboxes.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


# Default tag names (can be overridden per workspace)
DEFAULT_A_SET_TAG = 'live'
DEFAULT_B_SET_TAG = 'bset'

# Legacy tag names (some workspaces use these)
LEGACY_A_SET_TAG = 'A Set'
LEGACY_B_SET_TAG = 'B Set'

# Set percentages by provider (both 80/20 - replace infrastructure for infrastructure)
ENTRA_A_SET_PCT = 0.80  # 80% A-Set, 20% B-Set reserve
GOOGLE_A_SET_PCT = 0.80  # 80% A-Set, 20% B-Set reserve (domain-level swap when bad)

INCUBATION_DAYS = 14


class SetTagSyncModule:
    """
    Manages A-Set and B-Set inbox tags in EmailBison.

    This module runs after lifecycle_tag_sync graduates inboxes from 'incubating'.
    It assigns graduated inboxes to either A-Set or B-Set based on:
    - Provider type (Entra 80/20, Google 100/0)
    - Current A-Set capacity
    - Priority ranking (oldest warmup, highest health)

    When A-Set capacity drops (inboxes die/disconnect), it promotes B-Set inboxes.
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
        2. Check if legacy tags ('A Set'/'B Set') exist
        3. Fall back to defaults ('live'/'bset')
        """
        if configured_a and configured_b:
            return configured_a, configured_b

        # Try to detect existing tags
        try:
            existing_tags = await self.client.list_tags()
            tag_names = {t.get('name', '').lower(): t.get('name') for t in existing_tags}

            # Check for legacy tags
            if 'a set' in tag_names:
                return tag_names['a set'], tag_names.get('b set', LEGACY_B_SET_TAG)

            # Check for standard tags
            if 'live' in tag_names and 'bset' in tag_names:
                return 'live', 'bset'

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
        """Get all domains with ACTUAL graduated inbox counts for a workspace."""
        return await self.db.fetch("""
            SELECT
                d.id as domain_id,
                d.domain_name,
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
                    AND COALESCE(sa.inventory_pool_status, 'reserve') != 'quarantined'
                    AND (
                        sa.inventory_lifecycle_status = 'active'
                        OR (sa.warmup_started_at IS NOT NULL AND sa.warmup_started_at <= NOW() - INTERVAL '14 days')
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

        Logic:
        1. Get graduated inboxes (14+ days warmup, still live)
        2. Get inboxes already in A-Set or B-Set
        3. Calculate target counts based on provider
        4. Tag untagged graduated inboxes to appropriate set
        5. Promote B-Set → A-Set if A-Set below capacity
        """
        domain_id = domain['domain_id']
        domain_name = domain['domain_name']
        provider = domain['provider']
        graduated_count = domain['graduated_inbox_count']

        result = {'tagged_a': 0, 'tagged_b': 0, 'promoted': 0}

        # Skip domains with no graduated inboxes
        if graduated_count == 0:
            return result

        # Check if domain is quarantined (domain-killing trigger fired)
        if await self._is_domain_quarantined(domain_id):
            print(f"    [SKIP] {domain_name}: Domain quarantined, skipping set sync")
            return result

        # Calculate targets from ACTUAL graduated count (not expected)
        a_set_pct = ENTRA_A_SET_PCT if provider == 'entra' else GOOGLE_A_SET_PCT
        target_a = int(graduated_count * a_set_pct)
        target_b = graduated_count - target_a

        # Get priority-ranked graduated inboxes
        inboxes = await self._get_graduated_inboxes(domain_id)

        if not inboxes:
            return result

        # Count current A-Set and B-Set connected inboxes
        current_a_connected = sum(
            1 for i in inboxes
            if i['inventory_pool_status'] == 'deployed' and i['status'] == 'Connected'
        )
        current_b = sum(1 for i in inboxes if i['inventory_pool_status'] == 'reserve')

        # Track which inboxes need tagging
        for rank, inbox in enumerate(inboxes):
            audit.increment_processed()
            eb_account_id = inbox['emailbison_account_id']

            if not eb_account_id:
                continue

            eb_account_id = int(eb_account_id)
            current_pool = inbox['inventory_pool_status']

            # Determine target set based on priority rank
            if rank < target_a:
                target_set = 'deployed'  # A-Set
                target_tag_id = a_set_tag_id
                other_tag_id = b_set_tag_id
            else:
                target_set = 'reserve'  # B-Set
                target_tag_id = b_set_tag_id
                other_tag_id = a_set_tag_id

            # Skip if already in correct set
            if current_pool == target_set:
                continue

            # Check if this is a promotion (B-Set → A-Set)
            is_promotion = current_pool == 'reserve' and target_set == 'deployed'

            try:
                # Remove old tag if present
                if current_pool in ('deployed', 'reserve'):
                    try:
                        await self.client.untag_inbox(eb_account_id, other_tag_id)
                    except EmailBisonAPIError:
                        pass

                # Add new tag
                await self.client.tag_inbox(eb_account_id, target_tag_id)

                # Update local database
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET
                        inventory_pool_status = $2,
                        updated_at = NOW()
                    WHERE id = $1
                """, inbox['id'], target_set)

                if target_set == 'deployed':
                    result['tagged_a'] += 1
                    if is_promotion:
                        result['promoted'] += 1
                        print(f"    [PROMOTE] {inbox['email_address']} B-Set → A-Set")
                    else:
                        print(f"    [TAG] {inbox['email_address']} → A-Set")
                else:
                    result['tagged_b'] += 1
                    print(f"    [TAG] {inbox['email_address']} → B-Set")

                audit.increment_updated()

            except EmailBisonAPIError as e:
                audit.add_error(
                    record_id=inbox['email_address'],
                    error=f"Failed to tag: {e}"
                )

        return result

    async def _get_graduated_inboxes(self, domain_id: UUID) -> List[Dict]:
        """
        Get graduated CONNECTED inboxes for a domain, priority-ranked for A-Set assignment.

        Only connected inboxes can be tagged - they're ready to send.

        Priority ranking:
        1. Already in A-Set (maintain stability)
        2. Oldest warmup (most mature)
        3. Highest health score

        Only includes:
        - Live inboxes (inbox_state = 'live')
        - Connected (status = 'Connected') - required for tagging
        - Graduated (inventory_lifecycle_status = 'active' OR 14+ days warmup)
        - NOT quarantined (quarantined inboxes must not be promoted)
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
            AND status = 'Connected'
            AND COALESCE(inventory_pool_status, 'reserve') != 'quarantined'
            AND (
                inventory_lifecycle_status = 'active'
                OR (
                    warmup_started_at IS NOT NULL
                    AND warmup_started_at <= NOW() - INTERVAL '14 days'
                )
            )
            ORDER BY
                -- Already in A-Set first (maintain stability)
                CASE WHEN inventory_pool_status = 'deployed' THEN 0 ELSE 1 END,
                -- Oldest warmup (most mature)
                warmup_started_at ASC NULLS LAST,
                -- Highest health
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
            GROUP BY
                COALESCE(d.infrastructure_type,
                    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END
                )
        """, workspace_id)

        return {row['provider']: dict(row) for row in stats}
