#!/usr/bin/env python3
"""
Backfill Domain Sets (Live/Reserve Allocation)

Targeted backfill for domain-level A-Set/B-Set allocation.
Uses capacity-based logic: only create reserve if surplus exists.

Usage:
    # Dry run - see what would change
    python scripts/backfill_domain_sets.py --workspace Selery --dry-run

    # Apply changes
    python scripts/backfill_domain_sets.py --workspace Selery --apply

    # All workspaces
    python scripts/backfill_domain_sets.py --all --dry-run

Run in production:
    docker exec emailbison-sync python scripts/backfill_domain_sets.py --workspace Selery --dry-run
"""
import asyncio
import argparse
import os
import sys
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from uuid import UUID

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

# Try to import EmailBison client
try:
    from sync_modules.emailbison_client import EmailBisonClient
    HAS_EMAILBISON = True
except ImportError:
    HAS_EMAILBISON = False
    print("[WARN] EmailBisonClient not available - will only update local DB")

# Database connection
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'localdevpassword')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'postgres')

# Standard tag names
LIVE_TAG = 'live'
RESERVE_TAG = 'reserve'


@dataclass
class DomainHealth:
    """Domain health data for allocation decisions."""
    domain_id: str
    domain_name: str
    workspace_id: str
    provider: str  # 'entra' or 'google'
    inbox_count: int
    connected_count: int
    avg_health_score: float
    avg_bounce_rate: float
    high_bounce_count: int
    has_spam_complaints: bool
    has_hard_blocks: bool
    current_pool_status: Optional[str]


@dataclass
class WorkspaceCapacity:
    """Workspace capacity from v_client_capacity."""
    workspace_id: str
    workspace_name: str
    client_name: str
    entra_target: int
    entra_live: int
    entra_reserve: int
    google_target: int
    google_live: int
    google_reserve: int
    spare_ratio: float


def score_domain_health(domain: DomainHealth) -> float:
    """
    Calculate domain health score.
    HIGHER = healthier = RESERVE candidate
    LOWER = degraded = LIVE (expendable)
    """
    score = 100.0

    if domain.has_spam_complaints:
        score -= 200
    if domain.has_hard_blocks:
        score -= 100

    score -= domain.avg_bounce_rate * 500
    score += (domain.avg_health_score - 80) * 2

    high_bounce_pct = domain.high_bounce_count / max(domain.inbox_count, 1)
    score -= high_bounce_pct * 50

    if domain.inbox_count >= 50:
        score += 10
    elif domain.inbox_count >= 3:
        score += 5

    return round(score, 2)


def calculate_reserve_capacity(capacity: WorkspaceCapacity) -> Dict[str, int]:
    """Calculate how many inboxes can be reserved per provider."""
    entra_surplus = capacity.entra_live - capacity.entra_target
    google_surplus = capacity.google_live - capacity.google_target

    entra_ideal = int(capacity.entra_target * capacity.spare_ratio)
    google_ideal = int(capacity.google_target * capacity.spare_ratio)

    return {
        'entra': min(entra_ideal, max(0, entra_surplus)),
        'google': min(google_ideal, max(0, google_surplus)),
        'entra_surplus': entra_surplus,
        'google_surplus': google_surplus,
    }


async def get_workspace_capacity(db: asyncpg.Pool, workspace_name: str) -> Optional[WorkspaceCapacity]:
    """Get capacity data from v_client_capacity."""
    row = await db.fetchrow("""
        SELECT
            cc.workspace_id,
            w.workspace_name,
            cc.client_name,
            COALESCE(cc.entra_inboxes_target, 0) as entra_target,
            COALESCE(cc.entra_inboxes_live, 0) as entra_live,
            COALESCE(cc.entra_inboxes_reserve, 0) as entra_reserve,
            COALESCE(cc.google_inboxes_target, 0) as google_target,
            COALESCE(cc.google_inboxes_live, 0) as google_live,
            COALESCE(cc.google_inboxes_reserve, 0) as google_reserve,
            COALESCE(cc.target_buffer_ratio, 0.15) as spare_ratio
        FROM v_client_capacity cc
        JOIN workspaces w ON cc.workspace_id = w.id
        WHERE w.workspace_name = $1
    """, workspace_name)

    if not row:
        return None

    return WorkspaceCapacity(
        workspace_id=str(row['workspace_id']),
        workspace_name=row['workspace_name'],
        client_name=row['client_name'],
        entra_target=row['entra_target'],
        entra_live=row['entra_live'],
        entra_reserve=row['entra_reserve'],
        google_target=row['google_target'],
        google_live=row['google_live'],
        google_reserve=row['google_reserve'],
        spare_ratio=float(row['spare_ratio']),
    )


async def get_workspace_domains(db: asyncpg.Pool, workspace_id: str) -> List[DomainHealth]:
    """Get all domains with health metrics for a workspace."""
    # Note: pool_status column may not exist yet (migration 076 pending)
    rows = await db.fetch("""
        WITH domain_metrics AS (
            SELECT
                d.id as domain_id,
                d.domain_name,
                d.workspace_id,
                NULL as pool_status,
                CASE
                    WHEN sa.esp = 'microsoft' THEN 'entra'
                    WHEN sa.esp = 'gmail' THEN 'google'
                    ELSE 'unknown'
                END as provider,
                COUNT(sa.id) as inbox_count,
                COUNT(sa.id) FILTER (WHERE sa.status = 'Connected') as connected_count,
                AVG(sa.health_score) as avg_health_score,
                AVG(COALESCE(sa.bounce_rate_7d, 0)) as avg_bounce_rate,
                COUNT(sa.id) FILTER (WHERE COALESCE(sa.bounce_rate_7d, 0) > 0.02) as high_bounce_count,
                COUNT(sa.id) FILTER (WHERE sa.kill_trigger::text = 'spam_complaint') > 0 as has_spam_complaints,
                COUNT(sa.id) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block%%') > 0 as has_hard_blocks
            FROM domains d
            JOIN sender_accounts sa ON sa.domain_id = d.id
            WHERE d.workspace_id = $1::uuid
              AND d.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.is_active = TRUE
            GROUP BY d.id, d.domain_name, d.workspace_id, sa.esp
        )
        SELECT * FROM domain_metrics
        WHERE inbox_count > 0
        ORDER BY provider, avg_health_score DESC
    """, workspace_id)

    return [
        DomainHealth(
            domain_id=str(row['domain_id']),
            domain_name=row['domain_name'],
            workspace_id=str(row['workspace_id']),
            provider=row['provider'],
            inbox_count=row['inbox_count'],
            connected_count=row['connected_count'],
            avg_health_score=float(row['avg_health_score'] or 0),
            avg_bounce_rate=float(row['avg_bounce_rate'] or 0),
            high_bounce_count=row['high_bounce_count'],
            has_spam_complaints=row['has_spam_complaints'],
            has_hard_blocks=row['has_hard_blocks'],
            current_pool_status=row['pool_status'],
        )
        for row in rows
    ]


def allocate_domains(
    domains: List[DomainHealth],
    reserve_capacity: Dict[str, int]
) -> Tuple[List[DomainHealth], List[DomainHealth]]:
    """
    Allocate domains to live/reserve pools.
    Returns (reserve_domains, live_domains)
    """
    # Separate by provider
    entra = [d for d in domains if d.provider == 'entra']
    google = [d for d in domains if d.provider == 'google']

    # Sort by health (highest = healthiest = reserve candidates)
    entra.sort(key=lambda d: score_domain_health(d), reverse=True)
    google.sort(key=lambda d: score_domain_health(d), reverse=True)

    def select_reserve(domains: List[DomainHealth], target_inboxes: int) -> Tuple[List, List]:
        """Select domains for reserve until we hit target inbox count."""
        reserve = []
        live = []
        reserve_inbox_count = 0

        for d in domains:
            if reserve_inbox_count < target_inboxes:
                reserve.append(d)
                reserve_inbox_count += d.inbox_count
            else:
                live.append(d)

        return reserve, live

    entra_reserve, entra_live = select_reserve(entra, reserve_capacity['entra'])
    google_reserve, google_live = select_reserve(google, reserve_capacity['google'])

    return (entra_reserve + google_reserve, entra_live + google_live)


async def apply_allocation(
    db: asyncpg.Pool,
    eb_client,
    workspace_id: str,
    reserve_domains: List[DomainHealth],
    live_domains: List[DomainHealth],
    dry_run: bool = True
) -> Dict:
    """Apply the allocation to database and EmailBison."""
    result = {
        'domains_to_reserve': len(reserve_domains),
        'domains_to_live': len(live_domains),
        'inboxes_tagged_reserve': 0,
        'inboxes_tagged_live': 0,
        'errors': [],
    }

    if dry_run:
        return result

    # Get or create tags in EmailBison
    live_tag_id = None
    reserve_tag_id = None

    if eb_client:
        try:
            live_tag = await eb_client.get_or_create_tag(LIVE_TAG)
            reserve_tag = await eb_client.get_or_create_tag(RESERVE_TAG)
            live_tag_id = live_tag.get('id')
            reserve_tag_id = reserve_tag.get('id')
        except Exception as e:
            result['errors'].append(f"Failed to get/create tags: {e}")

    # Process reserve domains
    for domain in reserve_domains:
        try:
            # Update inbox pool_status (this column exists)
            await db.execute("""
                UPDATE sender_accounts
                SET inventory_pool_status = 'reserve', updated_at = NOW()
                WHERE domain_id = $1::uuid
                  AND inbox_state = 'live'
                  AND is_active = TRUE
            """, domain.domain_id)

            # Try to update domain pool_status (may not exist yet - migration 076)
            try:
                await db.execute("""
                    UPDATE domains
                    SET pool_status = 'reserve', updated_at = NOW()
                    WHERE id = $1::uuid
                """, domain.domain_id)
            except Exception:
                pass  # Column doesn't exist yet

            result['inboxes_tagged_reserve'] += domain.inbox_count

            # Tag in EmailBison
            if eb_client and reserve_tag_id:
                inboxes = await db.fetch("""
                    SELECT emailbison_account_id
                    FROM sender_accounts
                    WHERE domain_id = $1::uuid
                      AND inbox_state = 'live'
                      AND emailbison_account_id IS NOT NULL
                """, domain.domain_id)

                for inbox in inboxes:
                    try:
                        eb_id = int(inbox['emailbison_account_id'])
                        # Remove live tag if present
                        if live_tag_id:
                            try:
                                await eb_client.untag_inbox(eb_id, live_tag_id)
                            except:
                                pass
                        # Add reserve tag
                        await eb_client.tag_inbox(eb_id, reserve_tag_id)
                    except Exception as e:
                        result['errors'].append(f"Tag inbox {eb_id}: {e}")

        except Exception as e:
            result['errors'].append(f"Reserve {domain.domain_name}: {e}")

    # Process live domains
    for domain in live_domains:
        try:
            # Update inbox pool_status (this column exists)
            await db.execute("""
                UPDATE sender_accounts
                SET inventory_pool_status = 'deployed', updated_at = NOW()
                WHERE domain_id = $1::uuid
                  AND inbox_state = 'live'
                  AND is_active = TRUE
            """, domain.domain_id)

            # Try to update domain pool_status (may not exist yet - migration 076)
            try:
                await db.execute("""
                    UPDATE domains
                    SET pool_status = 'live', updated_at = NOW()
                    WHERE id = $1::uuid
                """, domain.domain_id)
            except Exception:
                pass  # Column doesn't exist yet

            result['inboxes_tagged_live'] += domain.inbox_count

            # Tag in EmailBison
            if eb_client and live_tag_id:
                inboxes = await db.fetch("""
                    SELECT emailbison_account_id
                    FROM sender_accounts
                    WHERE domain_id = $1::uuid
                      AND inbox_state = 'live'
                      AND emailbison_account_id IS NOT NULL
                """, domain.domain_id)

                for inbox in inboxes:
                    try:
                        eb_id = int(inbox['emailbison_account_id'])
                        # Remove reserve tag if present
                        if reserve_tag_id:
                            try:
                                await eb_client.untag_inbox(eb_id, reserve_tag_id)
                            except:
                                pass
                        # Add live tag
                        await eb_client.tag_inbox(eb_id, live_tag_id)
                    except Exception as e:
                        result['errors'].append(f"Tag inbox {eb_id}: {e}")

        except Exception as e:
            result['errors'].append(f"Live {domain.domain_name}: {e}")

    return result


async def backfill_workspace(
    db: asyncpg.Pool,
    eb_client,
    workspace_name: str,
    dry_run: bool = True
) -> Dict:
    """Run backfill for a single workspace."""
    print(f"\n{'='*70}")
    print(f"WORKSPACE: {workspace_name}")
    print(f"{'='*70}")

    # Get capacity data
    capacity = await get_workspace_capacity(db, workspace_name)
    if not capacity:
        print(f"  [SKIP] No capacity data found (no subscription?)")
        return {'skipped': True, 'reason': 'no_capacity_data'}

    print(f"\n## Capacity Analysis")
    print(f"   Client: {capacity.client_name}")
    print(f"   Spare Ratio: {capacity.spare_ratio*100:.0f}%")

    # Calculate reserve capacity
    reserve_cap = calculate_reserve_capacity(capacity)

    print(f"\n   ENTRA:")
    print(f"     Target: {capacity.entra_target} | Live: {capacity.entra_live}")
    print(f"     Surplus: {reserve_cap['entra_surplus']:+d}")
    print(f"     Reserve Capacity: {reserve_cap['entra']} inboxes")

    print(f"\n   GOOGLE:")
    print(f"     Target: {capacity.google_target} | Live: {capacity.google_live}")
    print(f"     Surplus: {reserve_cap['google_surplus']:+d}")
    print(f"     Reserve Capacity: {reserve_cap['google']} inboxes")

    # Check if any reserve possible
    if reserve_cap['entra'] == 0 and reserve_cap['google'] == 0:
        print(f"\n   [RESULT] No reserve capacity - ALL DOMAINS LIVE")
        print(f"   (At or below target threshold)")
        return {'skipped': True, 'reason': 'no_surplus'}

    # Get domains
    domains = await get_workspace_domains(db, capacity.workspace_id)
    if not domains:
        print(f"  [SKIP] No domains with live inboxes")
        return {'skipped': True, 'reason': 'no_domains'}

    print(f"\n## Domain Inventory")
    entra_domains = [d for d in domains if d.provider == 'entra']
    google_domains = [d for d in domains if d.provider == 'google']
    print(f"   Entra: {len(entra_domains)} domains, {sum(d.inbox_count for d in entra_domains)} inboxes")
    print(f"   Google: {len(google_domains)} domains, {sum(d.inbox_count for d in google_domains)} inboxes")

    # Allocate
    reserve_domains, live_domains = allocate_domains(domains, reserve_cap)

    print(f"\n## Allocation Plan")
    print(f"\n### RESERVE (Protected) - {len(reserve_domains)} domains")
    print(f"   {'Domain':<30} {'Provider':<8} {'Inboxes':>8} {'Health':>8} {'Score':>8}")
    print(f"   {'-'*70}")
    for d in reserve_domains:
        score = score_domain_health(d)
        print(f"   {d.domain_name:<30} {d.provider:<8} {d.inbox_count:>8} {d.avg_health_score:>8.1f} {score:>8.1f}")

    print(f"\n### LIVE (Expendable) - {len(live_domains)} domains")
    print(f"   {'Domain':<30} {'Provider':<8} {'Inboxes':>8} {'Health':>8} {'Score':>8}")
    print(f"   {'-'*70}")
    # Show worst 5
    live_sorted = sorted(live_domains, key=lambda d: score_domain_health(d))
    for d in live_sorted[:5]:
        score = score_domain_health(d)
        print(f"   {d.domain_name:<30} {d.provider:<8} {d.inbox_count:>8} {d.avg_health_score:>8.1f} {score:>8.1f}")
    if len(live_domains) > 5:
        print(f"   ... and {len(live_domains) - 5} more domains")

    # Apply or dry-run
    if dry_run:
        print(f"\n## DRY RUN - No changes made")
        print(f"   Would set {len(reserve_domains)} domains to RESERVE")
        print(f"   Would set {len(live_domains)} domains to LIVE")
        return {
            'dry_run': True,
            'reserve_domains': len(reserve_domains),
            'live_domains': len(live_domains),
            'reserve_inboxes': sum(d.inbox_count for d in reserve_domains),
            'live_inboxes': sum(d.inbox_count for d in live_domains),
        }

    # Apply changes
    print(f"\n## APPLYING CHANGES...")
    result = await apply_allocation(
        db, eb_client, capacity.workspace_id,
        reserve_domains, live_domains, dry_run=False
    )

    print(f"\n## Results")
    print(f"   Reserve: {result['inboxes_tagged_reserve']} inboxes tagged")
    print(f"   Live: {result['inboxes_tagged_live']} inboxes tagged")
    if result['errors']:
        print(f"   Errors: {len(result['errors'])}")
        for e in result['errors'][:5]:
            print(f"     - {e}")

    return result


async def main():
    parser = argparse.ArgumentParser(description='Backfill domain live/reserve sets')
    parser.add_argument('--workspace', '-w', help='Target workspace name')
    parser.add_argument('--all', action='store_true', help='Process all workspaces')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Show what would change')
    parser.add_argument('--apply', action='store_true', help='Apply changes')
    args = parser.parse_args()

    if not args.workspace and not args.all:
        parser.error("Must specify --workspace NAME or --all")

    if args.apply and args.dry_run:
        parser.error("Cannot use both --apply and --dry-run")

    dry_run = not args.apply

    if dry_run:
        print("\n" + "="*70)
        print("DRY RUN MODE - No changes will be made")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("APPLY MODE - Changes will be committed")
        print("="*70)

    # Connect to database
    db = await asyncpg.create_pool(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
        min_size=1,
        max_size=5
    )

    # Connect to EmailBison if available
    eb_client = None
    if HAS_EMAILBISON and not dry_run:
        eb_client = EmailBisonClient()
        await eb_client.__aenter__()

    try:
        if args.workspace:
            await backfill_workspace(db, eb_client, args.workspace, dry_run)
        elif args.all:
            # Get all workspaces with capacity data
            workspaces = await db.fetch("""
                SELECT DISTINCT w.workspace_name
                FROM v_client_capacity cc
                JOIN workspaces w ON cc.workspace_id = w.id
                WHERE cc.client_name IS NOT NULL
                ORDER BY w.workspace_name
            """)
            for ws in workspaces:
                await backfill_workspace(db, eb_client, ws['workspace_name'], dry_run)

    finally:
        if eb_client:
            await eb_client.__aexit__(None, None, None)
        await db.close()

    print("\n" + "="*70)
    print("COMPLETE")
    print("="*70)


if __name__ == '__main__':
    asyncio.run(main())
