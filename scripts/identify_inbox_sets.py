#!/usr/bin/env python3
"""
Identify A-Set (Live) vs B-Set (Reserve) Inbox Distribution

Analyzes current inbox distribution per domain and calculates:
- Current state: How inboxes are currently distributed
- Target state: How they should be distributed (80/20 for both Entra and Google)
- Actions needed: Which inboxes to tag as live vs bset

Detects existing tag naming conventions:
- Standard: 'live' / 'bset'
- Legacy: 'A Set' / 'B Set' (Searchatlas, older workspaces)

Usage:
    python scripts/identify_inbox_sets.py
    python scripts/identify_inbox_sets.py --workspace Charm
    python scripts/identify_inbox_sets.py --output csv
    python scripts/identify_inbox_sets.py --show-tags  # Show tag config per workspace
"""
import asyncio
import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import asyncpg

# Database connection
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5433))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'localdevpassword')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'postgres')

# Set configuration (both 80/20 - replace infrastructure for infrastructure)
ENTRA_LIVE_PCT = 0.80  # 80% live, 20% reserve
GOOGLE_LIVE_PCT = 0.80  # 80% live, 20% reserve (domain-level swap when bad)
INCUBATION_DAYS = 14


async def get_domain_breakdown(db: asyncpg.Pool, workspace_name: Optional[str] = None):
    """Get inbox breakdown by domain with A-set/B-set calculations."""

    workspace_filter = "AND w.workspace_name = $1" if workspace_name else ""
    params = [workspace_name] if workspace_name else []

    query = f"""
    WITH domain_stats AS (
        SELECT
            d.id as domain_id,
            d.domain_name,
            w.workspace_name,
            COALESCE(d.infrastructure_type,
                CASE
                    WHEN EXISTS (SELECT 1 FROM sender_accounts sa2 WHERE sa2.domain_id = d.id AND sa2.esp = 'microsoft') THEN 'entra'
                    WHEN EXISTS (SELECT 1 FROM sender_accounts sa2 WHERE sa2.domain_id = d.id AND sa2.esp = 'gmail') THEN 'google'
                    ELSE 'unknown'
                END
            ) as provider,
            COALESCE(d.expected_inbox_count,
                CASE
                    WHEN d.infrastructure_type = 'google' THEN 3
                    ELSE 50
                END
            ) as expected_inbox_count,

            -- Inbox counts by state
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as connected,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status != 'Connected') as disconnected,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,

            -- Lifecycle status
            COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'incubating') as incubating,
            COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'active') as graduated,

            -- Current pool status
            COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'deployed') as deployed,
            COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve') as reserve,

            -- Warmup age analysis (for graduation eligibility)
            COUNT(*) FILTER (
                WHERE sa.inbox_state = 'live'
                AND sa.warmup_started_at IS NOT NULL
                AND sa.warmup_started_at <= NOW() - INTERVAL '{INCUBATION_DAYS} days'
            ) as mature_inboxes,
            COUNT(*) FILTER (
                WHERE sa.inbox_state = 'live'
                AND (sa.warmup_started_at IS NULL OR sa.warmup_started_at > NOW() - INTERVAL '{INCUBATION_DAYS} days')
            ) as immature_inboxes

        FROM domains d
        JOIN workspaces w ON d.workspace_id = w.id
        LEFT JOIN sender_accounts sa ON sa.domain_id = d.id AND sa.is_active = TRUE
        WHERE d.is_active = TRUE
        {workspace_filter}
        GROUP BY d.id, d.domain_name, w.workspace_name, d.infrastructure_type, d.expected_inbox_count
        HAVING COUNT(*) FILTER (WHERE sa.inbox_state = 'live') > 0
    )
    SELECT
        *,
        -- Target A-set (live) count based on provider
        CASE
            WHEN provider = 'entra' THEN FLOOR(expected_inbox_count * {ENTRA_LIVE_PCT})::INTEGER
            WHEN provider = 'google' THEN expected_inbox_count
            ELSE live_inboxes
        END as target_a_set,

        -- Target B-set (reserve) count based on provider
        CASE
            WHEN provider = 'entra' THEN CEIL(expected_inbox_count * {1 - ENTRA_LIVE_PCT})::INTEGER
            WHEN provider = 'google' THEN 0
            ELSE 0
        END as target_b_set

    FROM domain_stats
    ORDER BY provider, live_inboxes DESC
    """

    return await db.fetch(query, *params)


async def get_inbox_assignments(db: asyncpg.Pool, domain_id: str):
    """Get specific inbox assignments for a domain - which go to A-set vs B-set."""

    query = """
    SELECT
        id,
        email_address,
        status,
        inbox_state,
        inventory_lifecycle_status,
        inventory_pool_status,
        warmup_started_at,
        health_score,
        CASE
            WHEN warmup_started_at IS NOT NULL
            AND warmup_started_at <= NOW() - INTERVAL '14 days'
            THEN 'mature'
            ELSE 'immature'
        END as maturity,
        EXTRACT(DAY FROM NOW() - warmup_started_at)::INTEGER as warmup_days
    FROM sender_accounts
    WHERE domain_id = $1
    AND is_active = TRUE
    AND inbox_state = 'live'
    ORDER BY
        -- Priority: Connected first, then by warmup age (oldest first), then health
        CASE WHEN status = 'Connected' THEN 0 ELSE 1 END,
        warmup_started_at ASC NULLS LAST,
        health_score DESC NULLS LAST
    """

    return await db.fetch(query, domain_id)


async def print_summary(db: asyncpg.Pool, workspace_name: Optional[str] = None):
    """Print summary of A-set/B-set distribution."""

    domains = await get_domain_breakdown(db, workspace_name)

    if not domains:
        print(f"No domains found{f' for workspace {workspace_name}' if workspace_name else ''}")
        return

    print("\n" + "=" * 100)
    print(f"A-SET / B-SET DISTRIBUTION ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if workspace_name:
        print(f"Workspace: {workspace_name}")
    print("=" * 100)

    # Group by provider
    entra_domains = [d for d in domains if d['provider'] == 'entra']
    google_domains = [d for d in domains if d['provider'] == 'google']

    for provider, provider_domains in [('ENTRA', entra_domains), ('GOOGLE', google_domains)]:
        if not provider_domains:
            continue

        print(f"\n{'─' * 100}")
        print(f"{provider} DOMAINS ({len(provider_domains)} total)")
        print(f"{'─' * 100}")

        print(f"\n{'Domain':<35} {'Live':>6} {'Conn':>6} {'Grad':>6} {'A-Set':>7} {'B-Set':>7} {'Action':>15}")
        print(f"{'-'*35} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*15}")

        total_live = 0
        total_graduated = 0
        total_to_move = 0

        for d in provider_domains:
            live = d['live_inboxes']
            connected = d['connected']
            graduated = d['graduated']
            target_a = d['target_a_set']
            target_b = d['target_b_set']

            # How many graduated inboxes need to move to B-set
            current_in_a = min(graduated, target_a) if graduated > 0 else 0
            to_move_to_b = max(0, graduated - target_a) if provider == 'ENTRA' else 0

            action = ""
            if to_move_to_b > 0:
                action = f"Move {to_move_to_b} to B"
            elif graduated < target_a:
                action = f"Need {target_a - graduated} more"
            else:
                action = "OK"

            print(f"{d['domain_name']:<35} {live:>6} {connected:>6} {graduated:>6} {target_a:>7} {target_b:>7} {action:>15}")

            total_live += live
            total_graduated += graduated
            total_to_move += to_move_to_b

        print(f"{'-'*35} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*15}")
        print(f"{'TOTAL':<35} {total_live:>6} {'-':>6} {total_graduated:>6} {'-':>7} {'-':>7} {f'{total_to_move} to move':>15}")

    # Overall summary
    print(f"\n{'=' * 100}")
    print("SUMMARY")
    print(f"{'=' * 100}")

    total_entra_live = sum(d['live_inboxes'] for d in entra_domains)
    total_entra_grad = sum(d['graduated'] for d in entra_domains)
    total_google_live = sum(d['live_inboxes'] for d in google_domains)

    print(f"\nEntra:")
    print(f"  Total live inboxes: {total_entra_live}")
    print(f"  Graduated (eligible for sets): {total_entra_grad}")
    print(f"  Target A-Set (80%): {int(total_entra_grad * ENTRA_LIVE_PCT)}")
    print(f"  Target B-Set (20%): {int(total_entra_grad * (1 - ENTRA_LIVE_PCT))}")

    if google_domains:
        print(f"\nGoogle:")
        print(f"  Total live inboxes: {total_google_live}")
        print(f"  Target A-Set: {total_google_live} (100% - no inbox-level reserve)")
        print(f"  Reserve strategy: Domain-level (keep extra domains warmed)")


async def export_csv(db: asyncpg.Pool, workspace_name: Optional[str] = None):
    """Export detailed inbox-level assignments to CSV."""

    domains = await get_domain_breakdown(db, workspace_name)

    print("domain_name,email,provider,status,lifecycle,pool_status,warmup_days,health_score,target_set,action")

    for d in domains:
        provider = d['provider']
        target_a = d['target_a_set']

        live_pct = ENTRA_LIVE_PCT if provider == 'entra' else GOOGLE_LIVE_PCT

        inboxes = await get_inbox_assignments(db, d['domain_id'])

        for i, inbox in enumerate(inboxes):
            # Determine target set based on position in priority-sorted list
            if inbox['maturity'] == 'immature':
                target_set = 'incubating'
                action = 'wait'
            elif i < target_a:
                target_set = 'live'
                current = inbox['inventory_pool_status']
                action = 'ok' if current == 'deployed' else 'tag_live'
            else:
                target_set = 'bset'
                current = inbox['inventory_pool_status']
                action = 'ok' if current == 'reserve' else 'tag_bset'

            warmup_days = inbox['warmup_days'] or 0
            health = inbox['health_score'] or 0

            print(f"{d['domain_name']},{inbox['email_address']},{provider},{inbox['status']},"
                  f"{inbox['inventory_lifecycle_status']},{inbox['inventory_pool_status']},"
                  f"{warmup_days},{health},{target_set},{action}")


async def get_workspace_tag_config(db: asyncpg.Pool):
    """Get tag configuration per workspace."""
    return await db.fetch("""
        SELECT
            w.workspace_name,
            COALESCE(w.a_set_tag_name, 'live') as a_set_tag,
            COALESCE(w.b_set_tag_name, 'bset') as b_set_tag,
            COUNT(sa.id) FILTER (WHERE sa.inventory_pool_status = 'deployed') as current_a_set,
            COUNT(sa.id) FILTER (WHERE sa.inventory_pool_status = 'reserve') as current_b_set,
            COUNT(sa.id) FILTER (WHERE sa.inventory_lifecycle_status = 'active') as graduated,
            COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') as live_total
        FROM workspaces w
        LEFT JOIN sender_accounts sa ON sa.workspace_id = w.id AND sa.is_active = TRUE
        WHERE w.is_active = TRUE
        AND w.emailbison_workspace_id IS NOT NULL
        GROUP BY w.id, w.workspace_name, w.a_set_tag_name, w.b_set_tag_name
        ORDER BY w.workspace_name
    """)


async def print_tag_config(db: asyncpg.Pool):
    """Print workspace tag configuration."""
    configs = await get_workspace_tag_config(db)

    print("\n" + "=" * 90)
    print("WORKSPACE TAG CONFIGURATION")
    print("=" * 90)

    print(f"\n{'Workspace':<25} {'A-Set Tag':<15} {'B-Set Tag':<15} {'A-Set':>8} {'B-Set':>8} {'Grad':>8}")
    print(f"{'-'*25} {'-'*15} {'-'*15} {'-'*8} {'-'*8} {'-'*8}")

    for c in configs:
        print(f"{c['workspace_name']:<25} {c['a_set_tag']:<15} {c['b_set_tag']:<15} "
              f"{c['current_a_set'] or 0:>8} {c['current_b_set'] or 0:>8} {c['graduated'] or 0:>8}")

    print(f"\nNote: Workspaces using 'A Set'/'B Set' are legacy - will be preserved.")
    print(f"      New workspaces use 'live'/'bset' tags.")


async def main():
    parser = argparse.ArgumentParser(description='Identify A-Set and B-Set inbox distribution')
    parser.add_argument('--workspace', '-w', help='Filter by workspace name')
    parser.add_argument('--output', '-o', choices=['summary', 'csv', 'tags'], default='summary',
                       help='Output format (default: summary, tags=show tag config)')
    parser.add_argument('--show-tags', action='store_true',
                       help='Show tag configuration per workspace')
    args = parser.parse_args()

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

    try:
        if args.show_tags or args.output == 'tags':
            await print_tag_config(db)
        elif args.output == 'csv':
            await export_csv(db, args.workspace)
        else:
            await print_summary(db, args.workspace)
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
