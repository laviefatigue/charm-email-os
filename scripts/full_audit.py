#!/usr/bin/env python3
"""Comprehensive database audit."""
import asyncio
import asyncpg


async def full_audit():
    db = await asyncpg.connect(
        host="localhost", port=5433, user="postgres",
        password="localdevpassword", database="postgres"
    )

    print("=" * 80)
    print("COMPREHENSIVE DATABASE AUDIT")
    print("=" * 80)

    # 1. Core table counts
    print("\n1. CORE TABLE COUNTS")
    print("-" * 60)

    tables = [
        "workspaces",
        "clients",
        "domains",
        "sender_accounts",
        "emailbison_campaigns",
        "campaign_snapshots",
        "campaign_events",
        "onboarding_submissions",
        "campaign_cycles",
        "campaign_documents",
        "strategy_generation_jobs",
    ]

    for table in tables:
        try:
            count = await db.fetchval(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table:<35} {count:>10}")
        except Exception as e:
            print(f"  {table:<35} ERROR: {str(e)[:30]}")

    # 2. Workspace health
    print("\n2. WORKSPACE INTEGRITY")
    print("-" * 60)

    active_ws = await db.fetchval("SELECT COUNT(*) FROM workspaces WHERE is_active = TRUE")
    ws_with_eb = await db.fetchval(
        "SELECT COUNT(*) FROM workspaces WHERE emailbison_workspace_id IS NOT NULL AND is_active = TRUE"
    )
    print(f"  Active workspaces: {active_ws}")
    print(f"  With EmailBison ID: {ws_with_eb}")

    # 3. Sender accounts integrity
    print("\n3. SENDER ACCOUNTS INTEGRITY")
    print("-" * 60)

    total_sa = await db.fetchval("SELECT COUNT(*) FROM sender_accounts")
    sa_with_domain = await db.fetchval("SELECT COUNT(*) FROM sender_accounts WHERE domain_id IS NOT NULL")
    sa_with_eb_id = await db.fetchval(
        "SELECT COUNT(*) FROM sender_accounts WHERE emailbison_account_id IS NOT NULL"
    )
    sa_orphaned = await db.fetchval(
        """SELECT COUNT(*) FROM sender_accounts
           WHERE workspace_id IS NULL
           OR NOT EXISTS (SELECT 1 FROM workspaces w WHERE w.id = sender_accounts.workspace_id)"""
    )

    print(f"  Total accounts: {total_sa}")
    pct = sa_with_domain * 100 // total_sa if total_sa else 0
    print(f"  With domain_id: {sa_with_domain} ({pct}%)")
    pct = sa_with_eb_id * 100 // total_sa if total_sa else 0
    print(f"  With emailbison_account_id: {sa_with_eb_id} ({pct}%)")
    print(f"  Orphaned (no valid workspace): {sa_orphaned}")

    # 4. Domain integrity
    print("\n4. DOMAIN INTEGRITY")
    print("-" * 60)

    total_domains = await db.fetchval("SELECT COUNT(*) FROM domains")
    domains_multi_ws = await db.fetchval(
        """SELECT COUNT(*) FROM (
            SELECT domain_name FROM domains
            GROUP BY domain_name HAVING COUNT(DISTINCT workspace_id) > 1
        ) x"""
    )
    domains_orphaned = await db.fetchval(
        """SELECT COUNT(*) FROM domains
           WHERE NOT EXISTS (
               SELECT 1 FROM sender_accounts sa
               WHERE SPLIT_PART(sa.email_address, '@', 2) = domains.domain_name
           )"""
    )

    print(f"  Total domains: {total_domains}")
    print(f"  In multiple workspaces: {domains_multi_ws}")
    print(f"  Orphaned (no accounts): {domains_orphaned}")

    # 5. Campaign data integrity
    print("\n5. CAMPAIGN DATA INTEGRITY")
    print("-" * 60)

    total_campaigns = await db.fetchval("SELECT COUNT(*) FROM emailbison_campaigns")
    campaigns_with_snapshots = await db.fetchval("SELECT COUNT(DISTINCT campaign_id) FROM campaign_snapshots")
    campaigns_with_events = await db.fetchval("SELECT COUNT(DISTINCT campaign_id) FROM campaign_events")
    total_snapshots = await db.fetchval("SELECT COUNT(*) FROM campaign_snapshots")
    total_events = await db.fetchval("SELECT COUNT(*) FROM campaign_events")

    print(f"  Total campaigns: {total_campaigns}")
    print(f"  Campaigns with snapshots: {campaigns_with_snapshots}")
    print(f"  Campaigns with events: {campaigns_with_events}")
    print(f"  Total snapshots: {total_snapshots}")
    print(f"  Total events: {total_events}")

    # 6. Client/Strategy data
    print("\n6. CLIENT & STRATEGY DATA")
    print("-" * 60)

    async def safe_count(query):
        try:
            return await db.fetchval(query)
        except Exception:
            return "N/A"

    total_clients = await safe_count("SELECT COUNT(*) FROM clients")
    clients_with_submissions = await safe_count("SELECT COUNT(DISTINCT client_id) FROM client_onboarding_submissions")
    total_submissions = await safe_count("SELECT COUNT(*) FROM client_onboarding_submissions")
    total_cycles = await safe_count("SELECT COUNT(*) FROM campaign_cycles")
    total_docs = await safe_count("SELECT COUNT(*) FROM campaign_documents")
    total_jobs = await safe_count("SELECT COUNT(*) FROM strategy_generation_jobs")

    print(f"  Total clients: {total_clients}")
    print(f"  Clients with submissions: {clients_with_submissions}")
    print(f"  Total submissions: {total_submissions}")
    print(f"  Campaign cycles: {total_cycles}")
    print(f"  Campaign documents: {total_docs}")
    print(f"  Strategy jobs: {total_jobs}")

    # 7. Foreign key integrity check
    print("\n7. FOREIGN KEY INTEGRITY")
    print("-" * 60)

    sa_bad_ws = await db.fetchval(
        """SELECT COUNT(*) FROM sender_accounts sa
           WHERE NOT EXISTS (SELECT 1 FROM workspaces w WHERE w.id = sa.workspace_id)"""
    )
    print(f"  sender_accounts with invalid workspace_id: {sa_bad_ws}")

    sa_bad_domain = await db.fetchval(
        """SELECT COUNT(*) FROM sender_accounts sa
           WHERE sa.domain_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM domains d WHERE d.id = sa.domain_id)"""
    )
    print(f"  sender_accounts with invalid domain_id: {sa_bad_domain}")

    d_bad_ws = await db.fetchval(
        """SELECT COUNT(*) FROM domains d
           WHERE NOT EXISTS (SELECT 1 FROM workspaces w WHERE w.id = d.workspace_id)"""
    )
    print(f"  domains with invalid workspace_id: {d_bad_ws}")

    snap_bad_campaign = await db.fetchval(
        """SELECT COUNT(*) FROM campaign_snapshots cs
           WHERE NOT EXISTS (SELECT 1 FROM emailbison_campaigns c WHERE c.id = cs.campaign_id)"""
    )
    print(f"  campaign_snapshots with invalid campaign_id: {snap_bad_campaign}")

    evt_bad_campaign = await db.fetchval(
        """SELECT COUNT(*) FROM campaign_events ce
           WHERE NOT EXISTS (SELECT 1 FROM emailbison_campaigns c WHERE c.id = ce.campaign_id)"""
    )
    print(f"  campaign_events with invalid campaign_id: {evt_bad_campaign}")

    # 8. Data freshness
    print("\n8. DATA FRESHNESS")
    print("-" * 60)

    latest_account_sync = await db.fetchval("SELECT MAX(last_synced_at) FROM sender_accounts")
    latest_snapshot = await db.fetchval("SELECT MAX(snapshot_timestamp) FROM campaign_snapshots")
    latest_event = await db.fetchval("SELECT MAX(created_at) FROM campaign_events")

    print(f"  Latest sender_account sync: {latest_account_sync}")
    print(f"  Latest campaign snapshot: {latest_snapshot}")
    print(f"  Latest campaign event: {latest_event}")

    # 9. Workspace breakdown
    print("\n9. DATA BY WORKSPACE")
    print("-" * 60)

    ws_breakdown = await db.fetch("""
        SELECT
            w.workspace_name,
            (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.workspace_id = w.id) as accounts,
            (SELECT COUNT(*) FROM domains d WHERE d.workspace_id = w.id) as domains,
            (SELECT COUNT(*) FROM emailbison_campaigns c WHERE c.workspace_id = w.id) as campaigns
        FROM workspaces w
        WHERE w.is_active = TRUE
        ORDER BY accounts DESC
    """)

    print(f"  {'Workspace':<25} {'Accounts':>10} {'Domains':>10} {'Campaigns':>10}")
    print("  " + "-" * 57)
    for row in ws_breakdown:
        print(f"  {row['workspace_name']:<25} {row['accounts']:>10} {row['domains']:>10} {row['campaigns']:>10}")

    # 10. Summary verdict
    print("\n" + "=" * 80)
    print("AUDIT SUMMARY")
    print("=" * 80)

    issues = []
    if sa_orphaned > 0:
        issues.append(f"{sa_orphaned} orphaned sender_accounts")
    if domains_multi_ws > 0:
        issues.append(f"{domains_multi_ws} domains in multiple workspaces")
    if domains_orphaned > 0:
        issues.append(f"{domains_orphaned} orphan domains")
    if sa_bad_ws > 0:
        issues.append(f"{sa_bad_ws} sender_accounts with invalid workspace FK")
    if sa_bad_domain > 0:
        issues.append(f"{sa_bad_domain} sender_accounts with invalid domain FK")
    if d_bad_ws > 0:
        issues.append(f"{d_bad_ws} domains with invalid workspace FK")
    if snap_bad_campaign > 0:
        issues.append(f"{snap_bad_campaign} snapshots with invalid campaign FK")
    if evt_bad_campaign > 0:
        issues.append(f"{evt_bad_campaign} events with invalid campaign FK")

    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("All integrity checks passed!")

    # Completeness check
    print("\nCOMPLETENESS:")
    if total_sa > 0 and sa_with_domain == total_sa:
        print("  Sender accounts: 100% linked to domains")
    else:
        print(f"  Sender accounts: {sa_with_domain}/{total_sa} linked to domains")

    if campaigns_with_snapshots == total_campaigns:
        print(f"  Campaigns: 100% have snapshots ({campaigns_with_snapshots}/{total_campaigns})")
    else:
        print(f"  Campaigns: {campaigns_with_snapshots}/{total_campaigns} have snapshots")

    await db.close()


if __name__ == "__main__":
    asyncio.run(full_audit())
