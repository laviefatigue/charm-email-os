"""
Provider Performance Analysis: Microsoft vs Google Inboxes
Critical analysis comparing Entra/Microsoft vs Google inbox performance
"""

import asyncio
import sys
sys.path.insert(0, '/home/claw/charm-email-os/api')

from database import fetch_all, fetch_one, create_pool, close_pool
import json


async def run_analysis():
    """Run comprehensive provider performance analysis"""

    await create_pool()

    print("=" * 80)
    print("PROVIDER PERFORMANCE ANALYSIS: MICROSOFT VS GOOGLE")
    print("=" * 80)
    print()

    # 1. Basic inbox distribution and burn rates
    print("1. INBOX DISTRIBUTION & BURN RATES")
    print("-" * 80)

    basic_stats = await fetch_all("""
        SELECT
            CASE
                WHEN email_address LIKE '%@outlook.%' OR email_address LIKE '%@hotmail.%'
                     OR email_address LIKE '%@live.%' THEN 'Microsoft'
                WHEN email_address LIKE '%@gmail.%' THEN 'Google'
                ELSE 'Other'
            END as provider_type,
            COUNT(*) as total_inboxes,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_inboxes,
            COUNT(*) FILTER (WHERE inbox_state = 'live') as live_inboxes,
            ROUND(100.0 * COUNT(*) FILTER (WHERE inbox_state = 'dead') / NULLIF(COUNT(*), 0), 2) as burn_rate_pct,
            COUNT(DISTINCT domain_id) as unique_domains,
            COUNT(DISTINCT workspace_id) as unique_workspaces
        FROM sender_accounts
        WHERE email_address LIKE '%@outlook.%'
           OR email_address LIKE '%@hotmail.%'
           OR email_address LIKE '%@live.%'
           OR email_address LIKE '%@gmail.%'
        GROUP BY provider_type
        ORDER BY total_inboxes DESC;
    """)

    for row in basic_stats:
        print(f"\n{row['provider_type']} Provider:")
        print(f"  Total Inboxes: {row['total_inboxes']:,}")
        print(f"  Live: {row['live_inboxes']:,}")
        print(f"  Dead: {row['dead_inboxes']:,}")
        print(f"  Burn Rate: {row['burn_rate_pct']}%")
        print(f"  Unique Domains: {row['unique_domains']}")
        print(f"  Unique Workspaces: {row['unique_workspaces']}")

    # 2. Kill trigger breakdown
    print("\n\n2. KILL TRIGGER BREAKDOWN")
    print("-" * 80)

    kill_triggers = await fetch_all("""
        SELECT
            CASE
                WHEN sa.email_address LIKE '%@outlook.%' OR sa.email_address LIKE '%@hotmail.%'
                     OR sa.email_address LIKE '%@live.%' THEN 'Microsoft'
                WHEN sa.email_address LIKE '%@gmail.%' THEN 'Google'
            END as provider_type,
            sa.kill_trigger,
            COUNT(*) as kill_count,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY
                CASE
                    WHEN sa.email_address LIKE '%@outlook.%' OR sa.email_address LIKE '%@hotmail.%'
                         OR sa.email_address LIKE '%@live.%' THEN 'Microsoft'
                    WHEN sa.email_address LIKE '%@gmail.%' THEN 'Google'
                END
            ), 2) as pct_of_provider_kills
        FROM sender_accounts sa
        WHERE sa.inbox_state = 'dead'
          AND sa.kill_trigger IS NOT NULL
          AND (sa.email_address LIKE '%@outlook.%'
               OR sa.email_address LIKE '%@hotmail.%'
               OR sa.email_address LIKE '%@live.%'
               OR sa.email_address LIKE '%@gmail.%')
        GROUP BY provider_type, sa.kill_trigger
        ORDER BY provider_type, kill_count DESC;
    """)

    current_provider = None
    for row in kill_triggers:
        if row['provider_type'] != current_provider:
            current_provider = row['provider_type']
            print(f"\n{current_provider}:")
        print(f"  {row['kill_trigger']}: {row['kill_count']} ({row['pct_of_provider_kills']}%)")

    # 3. Performance metrics by provider
    print("\n\n3. PERFORMANCE METRICS (7-DAY AVERAGES)")
    print("-" * 80)

    performance = await fetch_all("""
        SELECT
            CASE
                WHEN sa.email_address LIKE '%@outlook.%' OR sa.email_address LIKE '%@hotmail.%'
                     OR sa.email_address LIKE '%@live.%' THEN 'Microsoft'
                WHEN sa.email_address LIKE '%@gmail.%' THEN 'Google'
            END as provider_type,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
            ROUND(AVG(sa.bounce_rate_7d), 4) as avg_bounce_rate_7d,
            ROUND(AVG(sa.hard_bounces_7d), 2) as avg_hard_bounces_7d,
            ROUND(AVG(sa.hard_bounces_24h), 2) as avg_hard_bounces_24h,
            ROUND(AVG(sa.consecutive_hard_bounces), 2) as avg_consecutive_bounces,
            MAX(sa.bounce_rate_7d) as max_bounce_rate_7d,
            MIN(sa.bounce_rate_7d) FILTER (WHERE sa.bounce_rate_7d > 0) as min_bounce_rate_7d
        FROM sender_accounts sa
        WHERE (sa.email_address LIKE '%@outlook.%'
               OR sa.email_address LIKE '%@hotmail.%'
               OR sa.email_address LIKE '%@live.%'
               OR sa.email_address LIKE '%@gmail.%')
          AND sa.inbox_state = 'live'
        GROUP BY provider_type;
    """)

    for row in performance:
        print(f"\n{row['provider_type']} (Live Inboxes Only):")
        print(f"  Live Inboxes: {row['live_inboxes']:,}")
        print(f"  Avg 7-Day Bounce Rate: {row['avg_bounce_rate_7d'] or 0:.4f}")
        print(f"  Avg Hard Bounces (7d): {row['avg_hard_bounces_7d'] or 0:.2f}")
        print(f"  Avg Hard Bounces (24h): {row['avg_hard_bounces_24h'] or 0:.2f}")
        print(f"  Avg Consecutive Bounces: {row['avg_consecutive_bounces'] or 0:.2f}")
        print(f"  Max Bounce Rate (7d): {row['max_bounce_rate_7d'] or 0:.4f}")
        print(f"  Min Bounce Rate (7d): {row['min_bounce_rate_7d'] or 0:.4f}")

    # 4. Campaign performance by provider
    print("\n\n4. CAMPAIGN PERFORMANCE BY PROVIDER")
    print("-" * 80)

    campaign_perf = await fetch_all("""
        SELECT
            CASE
                WHEN sa.email_address LIKE '%@outlook.%' OR sa.email_address LIKE '%@hotmail.%'
                     OR sa.email_address LIKE '%@live.%' THEN 'Microsoft'
                WHEN sa.email_address LIKE '%@gmail.%' THEN 'Google'
            END as provider_type,
            COUNT(DISTINCT ci.campaign_id) as campaigns_with_provider,
            COUNT(DISTINCT ci.sender_account_id) as total_inbox_assignments,
            COUNT(DISTINCT CASE WHEN sa.inbox_state = 'dead' THEN sa.id END) as inboxes_killed_in_campaigns,
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN sa.inbox_state = 'dead' THEN sa.id END) /
                  NULLIF(COUNT(DISTINCT ci.sender_account_id), 0), 2) as kill_rate_in_campaigns
        FROM campaign_inboxes ci
        JOIN sender_accounts sa ON ci.sender_account_id = sa.id
        WHERE (sa.email_address LIKE '%@outlook.%'
               OR sa.email_address LIKE '%@hotmail.%'
               OR sa.email_address LIKE '%@live.%'
               OR sa.email_address LIKE '%@gmail.%')
        GROUP BY provider_type;
    """)

    for row in campaign_perf:
        print(f"\n{row['provider_type']}:")
        print(f"  Campaigns Using Provider: {row['campaigns_with_provider']}")
        print(f"  Total Inbox Assignments: {row['total_inbox_assignments']:,}")
        print(f"  Inboxes Killed: {row['inboxes_killed_in_campaigns']:,}")
        print(f"  Kill Rate in Campaigns: {row['kill_rate_in_campaigns']}%")

    # 5. Client-level analysis (controlling for client)
    print("\n\n5. PER-CLIENT COMPARISON (Controlling for Client Variable)")
    print("-" * 80)
    print("\nClients using BOTH providers:")

    dual_provider_clients = await fetch_all("""
        WITH provider_by_client AS (
            SELECT
                w.client_name,
                w.id as workspace_id,
                CASE
                    WHEN sa.email_address LIKE '%@outlook.%' OR sa.email_address LIKE '%@hotmail.%'
                         OR sa.email_address LIKE '%@live.%' THEN 'Microsoft'
                    WHEN sa.email_address LIKE '%@gmail.%' THEN 'Google'
                END as provider_type,
                COUNT(*) as inbox_count,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_count,
                ROUND(100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / NULLIF(COUNT(*), 0), 2) as burn_rate,
                ROUND(AVG(sa.bounce_rate_7d) FILTER (WHERE sa.inbox_state = 'live'), 4) as avg_bounce_rate
            FROM sender_accounts sa
            JOIN domains d ON sa.domain_id = d.id
            JOIN workspaces w ON d.workspace_id = w.id
            WHERE (sa.email_address LIKE '%@outlook.%'
                   OR sa.email_address LIKE '%@hotmail.%'
                   OR sa.email_address LIKE '%@live.%'
                   OR sa.email_address LIKE '%@gmail.%')
            GROUP BY w.client_name, w.id, provider_type
        ),
        dual_clients AS (
            SELECT
                client_name,
                COUNT(DISTINCT provider_type) as provider_count
            FROM provider_by_client
            GROUP BY client_name
            HAVING COUNT(DISTINCT provider_type) = 2
        )
        SELECT
            pbc.client_name,
            pbc.provider_type,
            pbc.inbox_count,
            pbc.dead_count,
            pbc.burn_rate,
            pbc.avg_bounce_rate
        FROM provider_by_client pbc
        JOIN dual_clients dc ON pbc.client_name = dc.client_name
        ORDER BY pbc.client_name, pbc.provider_type;
    """)

    current_client = None
    for row in dual_provider_clients:
        if row['client_name'] != current_client:
            current_client = row['client_name']
            print(f"\n{current_client}:")
        print(f"  {row['provider_type']}:")
        print(f"    Inboxes: {row['inbox_count']}, Dead: {row['dead_count']}, " +
              f"Burn Rate: {row['burn_rate']}%, Avg Bounce: {row['avg_bounce_rate'] or 0:.4f}")

    # 6. Domain-level infrastructure tracking
    print("\n\n6. INFRASTRUCTURE TYPE TRACKING (Domain-Level)")
    print("-" * 80)

    infra_stats = await fetch_all("""
        SELECT
            d.infrastructure_type,
            COUNT(DISTINCT d.id) as domain_count,
            COUNT(sa.id) as total_inboxes,
            COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,
            ROUND(100.0 * COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'dead') /
                  NULLIF(COUNT(sa.id), 0), 2) as burn_rate,
            ROUND(AVG(sa.bounce_rate_7d) FILTER (WHERE sa.inbox_state = 'live'), 4) as avg_bounce_rate
        FROM domains d
        LEFT JOIN sender_accounts sa ON sa.domain_id = d.id
        WHERE d.infrastructure_type IS NOT NULL
        GROUP BY d.infrastructure_type
        ORDER BY d.infrastructure_type;
    """)

    if infra_stats:
        for row in infra_stats:
            print(f"\n{row['infrastructure_type'].upper() if row['infrastructure_type'] else 'Unknown'}:")
            print(f"  Domains: {row['domain_count']}")
            print(f"  Total Inboxes: {row['total_inboxes']:,}")
            print(f"  Dead Inboxes: {row['dead_inboxes']:,}")
            print(f"  Burn Rate: {row['burn_rate']}%")
            print(f"  Avg Bounce Rate (live): {row['avg_bounce_rate'] or 0:.4f}")
    else:
        print("\nNo infrastructure type data available (column may not be populated yet)")

    # 7. Time-to-death analysis
    print("\n\n7. TIME-TO-DEATH ANALYSIS")
    print("-" * 80)

    ttd_stats = await fetch_all("""
        SELECT
            CASE
                WHEN sa.email_address LIKE '%@outlook.%' OR sa.email_address LIKE '%@hotmail.%'
                     OR sa.email_address LIKE '%@live.%' THEN 'Microsoft'
                WHEN sa.email_address LIKE '%@gmail.%' THEN 'Google'
            END as provider_type,
            COUNT(*) as killed_inboxes,
            ROUND(AVG(EXTRACT(EPOCH FROM (sa.killed_at - sa.created_at)) / 86400.0), 2) as avg_days_to_death,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (sa.killed_at - sa.created_at)) / 86400.0), 2) as median_days_to_death,
            ROUND(MIN(EXTRACT(EPOCH FROM (sa.killed_at - sa.created_at)) / 86400.0), 2) as min_days_to_death,
            ROUND(MAX(EXTRACT(EPOCH FROM (sa.killed_at - sa.created_at)) / 86400.0), 2) as max_days_to_death
        FROM sender_accounts sa
        WHERE sa.inbox_state = 'dead'
          AND sa.killed_at IS NOT NULL
          AND sa.created_at IS NOT NULL
          AND (sa.email_address LIKE '%@outlook.%'
               OR sa.email_address LIKE '%@hotmail.%'
               OR sa.email_address LIKE '%@live.%'
               OR sa.email_address LIKE '%@gmail.%')
        GROUP BY provider_type;
    """)

    for row in ttd_stats:
        print(f"\n{row['provider_type']}:")
        print(f"  Killed Inboxes: {row['killed_inboxes']:,}")
        print(f"  Avg Days to Death: {row['avg_days_to_death']} days")
        print(f"  Median Days to Death: {row['median_days_to_death']} days")
        print(f"  Min Days to Death: {row['min_days_to_death']} days")
        print(f"  Max Days to Death: {row['max_days_to_death']} days")

    # 8. Recent kills (last 30 days)
    print("\n\n8. RECENT PERFORMANCE (Last 30 Days)")
    print("-" * 80)

    recent_kills = await fetch_all("""
        SELECT
            CASE
                WHEN sa.email_address LIKE '%@outlook.%' OR sa.email_address LIKE '%@hotmail.%'
                     OR sa.email_address LIKE '%@live.%' THEN 'Microsoft'
                WHEN sa.email_address LIKE '%@gmail.%' THEN 'Google'
            END as provider_type,
            COUNT(*) as kills_last_30d,
            COUNT(*) FILTER (WHERE sa.killed_at >= NOW() - INTERVAL '7 days') as kills_last_7d,
            COUNT(*) FILTER (WHERE sa.killed_at >= NOW() - INTERVAL '1 day') as kills_last_24h
        FROM sender_accounts sa
        WHERE sa.inbox_state = 'dead'
          AND sa.killed_at >= NOW() - INTERVAL '30 days'
          AND (sa.email_address LIKE '%@outlook.%'
               OR sa.email_address LIKE '%@hotmail.%'
               OR sa.email_address LIKE '%@live.%'
               OR sa.email_address LIKE '%@gmail.%')
        GROUP BY provider_type;
    """)

    for row in recent_kills:
        print(f"\n{row['provider_type']}:")
        print(f"  Kills (30 days): {row['kills_last_30d']:,}")
        print(f"  Kills (7 days): {row['kills_last_7d']:,}")
        print(f"  Kills (24 hours): {row['kills_last_24h']:,}")

    print("\n\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

    await close_pool()


if __name__ == "__main__":
    asyncio.run(run_analysis())
