#!/usr/bin/env python3
"""
Test A-Set/B-Set Logic with Live Accounts

Traces through all inbox states to verify correct behavior.

Usage:
    python scripts/test_set_logic.py
    python scripts/test_set_logic.py --workspace Charm
"""
import asyncio
import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5433))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'localdevpassword')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'postgres')


async def test_inbox_states(db: asyncpg.Pool, workspace_name: Optional[str] = None):
    """Analyze all inbox states and what would happen to each."""

    workspace_filter = "AND w.workspace_name = $1" if workspace_name else ""
    params = [workspace_name] if workspace_name else []

    # Get all live inboxes with their current states
    query = f"""
    SELECT
        sa.email_address,
        sa.inbox_state,
        sa.status,
        sa.inventory_lifecycle_status,
        sa.inventory_pool_status,
        sa.warmup_started_at,
        sa.health_score,
        d.domain_name,
        w.workspace_name,
        COALESCE(d.infrastructure_type,
            CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END
        ) as provider,
        -- Age calculation
        CASE
            WHEN sa.warmup_started_at IS NOT NULL
            THEN EXTRACT(DAY FROM NOW() - sa.warmup_started_at)::INTEGER
            ELSE NULL
        END as warmup_days,
        -- Is graduated?
        CASE
            WHEN sa.inventory_lifecycle_status = 'active' THEN TRUE
            WHEN sa.warmup_started_at IS NOT NULL
                AND sa.warmup_started_at <= NOW() - INTERVAL '14 days' THEN TRUE
            ELSE FALSE
        END as is_graduated,
        -- Can be tagged? (connected + graduated)
        CASE
            WHEN sa.status = 'Connected'
                AND (
                    sa.inventory_lifecycle_status = 'active'
                    OR (sa.warmup_started_at IS NOT NULL
                        AND sa.warmup_started_at <= NOW() - INTERVAL '14 days')
                )
            THEN TRUE
            ELSE FALSE
        END as can_be_tagged,
        -- Current set
        CASE sa.inventory_pool_status
            WHEN 'deployed' THEN 'A-Set'
            WHEN 'reserve' THEN 'B-Set'
            ELSE 'Untagged'
        END as current_set
    FROM sender_accounts sa
    JOIN domains d ON sa.domain_id = d.id
    JOIN workspaces w ON sa.workspace_id = w.id
    WHERE sa.is_active = TRUE
    AND sa.inbox_state = 'live'
    {workspace_filter}
    ORDER BY w.workspace_name, d.domain_name, sa.email_address
    """

    inboxes = await db.fetch(query, *params)

    print("\n" + "="*120)
    print("LIVE INBOX STATE ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if workspace_name:
        print(f"Workspace: {workspace_name}")
    print("="*120)

    # Group by state
    states = {
        'connected_graduated_tagged': [],
        'connected_graduated_untagged': [],
        'connected_incubating': [],
        'disconnected_any': [],
    }

    for inbox in inboxes:
        email = inbox['email_address']
        status = inbox['status']
        is_graduated = inbox['is_graduated']
        current_set = inbox['current_set']

        if status == 'Connected':
            if is_graduated:
                if current_set != 'Untagged':
                    states['connected_graduated_tagged'].append(inbox)
                else:
                    states['connected_graduated_untagged'].append(inbox)
            else:
                states['connected_incubating'].append(inbox)
        else:
            states['disconnected_any'].append(inbox)

    # Report each category
    print(f"\n{'='*60}")
    print("CONNECTED + GRADUATED + TAGGED (Already in A/B Set)")
    print(f"{'='*60}")
    print(f"Count: {len(states['connected_graduated_tagged'])}")
    if states['connected_graduated_tagged'][:5]:
        print(f"\n{'Email':<40} {'Provider':<8} {'Set':<8} {'Days':>6}")
        print(f"{'-'*40} {'-'*8} {'-'*8} {'-'*6}")
        for i in states['connected_graduated_tagged'][:5]:
            print(f"{i['email_address'][:40]:<40} {i['provider']:<8} {i['current_set']:<8} {i['warmup_days'] or 0:>6}")
        if len(states['connected_graduated_tagged']) > 5:
            print(f"... and {len(states['connected_graduated_tagged']) - 5} more")
    print("\n>>> ACTION: Skip (already tagged correctly)")

    print(f"\n{'='*60}")
    print("CONNECTED + GRADUATED + UNTAGGED (Need A/B Set assignment)")
    print(f"{'='*60}")
    print(f"Count: {len(states['connected_graduated_untagged'])}")
    if states['connected_graduated_untagged'][:10]:
        print(f"\n{'Email':<40} {'Provider':<8} {'Days':>6} {'Health':>7}")
        print(f"{'-'*40} {'-'*8} {'-'*6} {'-'*7}")
        for i in states['connected_graduated_untagged'][:10]:
            print(f"{i['email_address'][:40]:<40} {i['provider']:<8} {i['warmup_days'] or 0:>6} {i['health_score'] or 0:>7.1f}")
        if len(states['connected_graduated_untagged']) > 10:
            print(f"... and {len(states['connected_graduated_untagged']) - 10} more")
    print("\n>>> ACTION: Tag as A-Set (80%) or B-Set (20%) based on rank")

    print(f"\n{'='*60}")
    print("CONNECTED + INCUBATING (Still warming, < 14 days)")
    print(f"{'='*60}")
    print(f"Count: {len(states['connected_incubating'])}")
    if states['connected_incubating'][:5]:
        print(f"\n{'Email':<40} {'Provider':<8} {'Days':>6} {'Status':<12}")
        print(f"{'-'*40} {'-'*8} {'-'*6} {'-'*12}")
        for i in states['connected_incubating'][:5]:
            print(f"{i['email_address'][:40]:<40} {i['provider']:<8} {i['warmup_days'] or 0:>6} {i['inventory_lifecycle_status'] or 'NULL':<12}")
        if len(states['connected_incubating']) > 5:
            print(f"... and {len(states['connected_incubating']) - 5} more")
    print("\n>>> ACTION: Skip (wait for graduation at 14 days)")

    print(f"\n{'='*60}")
    print("DISCONNECTED (Cannot tag - not ready)")
    print(f"{'='*60}")
    print(f"Count: {len(states['disconnected_any'])}")
    if states['disconnected_any'][:5]:
        print(f"\n{'Email':<40} {'Provider':<8} {'Status':<15} {'Current Set':<10}")
        print(f"{'-'*40} {'-'*8} {'-'*15} {'-'*10}")
        for i in states['disconnected_any'][:5]:
            print(f"{i['email_address'][:40]:<40} {i['provider']:<8} {i['status']:<15} {i['current_set']:<10}")
        if len(states['disconnected_any']) > 5:
            print(f"... and {len(states['disconnected_any']) - 5} more")
    print("\n>>> ACTION: Skip (cannot tag disconnected inboxes)")

    # Summary
    print(f"\n{'='*120}")
    print("SUMMARY")
    print(f"{'='*120}")

    total = len(inboxes)
    print(f"\nTotal live inboxes: {total}")
    print(f"  Connected + Graduated + Tagged:   {len(states['connected_graduated_tagged']):>5} ({len(states['connected_graduated_tagged'])/total*100:.1f}%) - No action")
    print(f"  Connected + Graduated + Untagged: {len(states['connected_graduated_untagged']):>5} ({len(states['connected_graduated_untagged'])/total*100:.1f}%) - Will be tagged")
    print(f"  Connected + Incubating:           {len(states['connected_incubating']):>5} ({len(states['connected_incubating'])/total*100:.1f}%) - Waiting")
    print(f"  Disconnected:                     {len(states['disconnected_any']):>5} ({len(states['disconnected_any'])/total*100:.1f}%) - Cannot tag")

    # Breakdown by provider for untagged
    if states['connected_graduated_untagged']:
        print(f"\n--- Untagged breakdown by provider ---")
        entra_untagged = [i for i in states['connected_graduated_untagged'] if i['provider'] == 'entra']
        google_untagged = [i for i in states['connected_graduated_untagged'] if i['provider'] == 'google']

        print(f"  Entra:  {len(entra_untagged)} will be tagged (80% A-Set, 20% B-Set)")
        print(f"  Google: {len(google_untagged)} will be tagged (80% A-Set, 20% B-Set)")


async def test_domain_distribution(db: asyncpg.Pool, workspace_name: Optional[str] = None):
    """Show per-domain distribution and what would happen."""

    workspace_filter = "AND w.workspace_name = $1" if workspace_name else ""
    params = [workspace_name] if workspace_name else []

    query = f"""
    WITH domain_stats AS (
        SELECT
            d.domain_name,
            w.workspace_name,
            COALESCE(d.infrastructure_type,
                CASE WHEN EXISTS (SELECT 1 FROM sender_accounts sa2 WHERE sa2.domain_id = d.id AND sa2.esp = 'microsoft') THEN 'entra'
                     WHEN EXISTS (SELECT 1 FROM sender_accounts sa2 WHERE sa2.domain_id = d.id AND sa2.esp = 'gmail') THEN 'google'
                     ELSE 'unknown' END
            ) as provider,
            COALESCE(d.expected_inbox_count, CASE WHEN d.infrastructure_type = 'google' THEN 3 ELSE 50 END) as expected,

            -- Connected graduated counts
            COUNT(*) FILTER (
                WHERE sa.inbox_state = 'live'
                AND sa.status = 'Connected'
                AND (sa.inventory_lifecycle_status = 'active'
                     OR (sa.warmup_started_at <= NOW() - INTERVAL '14 days'))
            ) as graduated_connected,

            -- Current set distribution
            COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'deployed') as current_a_set,
            COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve') as current_b_set,
            COUNT(*) FILTER (
                WHERE sa.inventory_pool_status IS NULL
                AND sa.inbox_state = 'live'
                AND sa.status = 'Connected'
                AND (sa.inventory_lifecycle_status = 'active'
                     OR (sa.warmup_started_at <= NOW() - INTERVAL '14 days'))
            ) as untagged

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
        FLOOR(graduated_connected * 0.80)::INTEGER as target_a_set,
        CEIL(graduated_connected * 0.20)::INTEGER as target_b_set
    FROM domain_stats
    ORDER BY workspace_name, provider, domain_name
    """

    domains = await db.fetch(query, *params)

    print(f"\n{'='*120}")
    print("PER-DOMAIN A-SET/B-SET DISTRIBUTION")
    print(f"{'='*120}")

    print(f"\n{'Domain':<35} {'Type':<8} {'Grad':>6} {'A-Set':>7} {'B-Set':>7} {'Untag':>7} {'Tgt-A':>7} {'Tgt-B':>7} {'Action':<15}")
    print(f"{'-'*35} {'-'*8} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*15}")

    for d in domains:
        grad = d['graduated_connected']
        curr_a = d['current_a_set']
        curr_b = d['current_b_set']
        untag = d['untagged']
        tgt_a = d['target_a_set']
        tgt_b = d['target_b_set']

        if untag > 0:
            action = f"Tag {untag}"
        elif curr_a != tgt_a or curr_b != tgt_b:
            action = "Rebalance"
        else:
            action = "OK"

        print(f"{d['domain_name'][:35]:<35} {d['provider']:<8} {grad:>6} {curr_a:>7} {curr_b:>7} {untag:>7} {tgt_a:>7} {tgt_b:>7} {action:<15}")


async def main():
    parser = argparse.ArgumentParser(description='Test A-Set/B-Set logic with live accounts')
    parser.add_argument('--workspace', '-w', help='Filter by workspace name')
    args = parser.parse_args()

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
        await test_inbox_states(db, args.workspace)
        await test_domain_distribution(db, args.workspace)
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
