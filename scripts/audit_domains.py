#!/usr/bin/env python3
"""Audit domain-to-workspace assignments using sender_account email domains as source of truth."""
import asyncio
import asyncpg


async def audit_domains():
    db = await asyncpg.connect(
        host="postgres", port=5432, user="postgres",
        password="localdevpassword", database="postgres"
    )

    print("=" * 70)
    print("DOMAIN ASSIGNMENT AUDIT")
    print("=" * 70)

    # Find domains that exist in multiple workspaces
    print("\n1. DOMAINS APPEARING IN MULTIPLE WORKSPACES:")
    print("-" * 70)

    multi_ws_domains = await db.fetch("""
        SELECT domain_name, array_agg(DISTINCT w.workspace_name) as workspaces, COUNT(DISTINCT w.id) as ws_count
        FROM domains d
        JOIN workspaces w ON d.workspace_id = w.id
        GROUP BY domain_name
        HAVING COUNT(DISTINCT w.id) > 1
        ORDER BY ws_count DESC, domain_name
    """)

    if multi_ws_domains:
        print(f"Found {len(multi_ws_domains)} domains in multiple workspaces:")
        for row in multi_ws_domains[:15]:
            print(f"   {row['domain_name']}: {row['workspaces']}")
    else:
        print("No domains appear in multiple workspaces.")

    # Find domains with mismatched workspace assignment
    # A domain should belong to the workspace where its sender_accounts are
    print("\n2. DOMAINS WITH SENDER ACCOUNTS IN DIFFERENT WORKSPACE:")
    print("-" * 70)

    mismatched = await db.fetch("""
        SELECT
            d.domain_name,
            w1.workspace_name as domain_workspace,
            w2.workspace_name as account_workspace,
            COUNT(*) as account_count
        FROM domains d
        JOIN workspaces w1 ON d.workspace_id = w1.id
        JOIN sender_accounts sa ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
        JOIN workspaces w2 ON sa.workspace_id = w2.id
        WHERE d.workspace_id != sa.workspace_id
        GROUP BY d.domain_name, w1.workspace_name, w2.workspace_name
        ORDER BY account_count DESC
        LIMIT 20
    """)

    if mismatched:
        print(f"{'Domain':<35} {'Domain WS':<20} {'Account WS':<20} {'Count':>6}")
        print("-" * 85)
        for row in mismatched:
            print(f"{row['domain_name']:<35} {row['domain_workspace']:<20} {row['account_workspace']:<20} {row['account_count']:>6}")
    else:
        print("All domains are correctly assigned to their sender_accounts' workspaces.")

    # Find orphan domains (domains with no sender_accounts)
    print("\n3. ORPHAN DOMAINS (no sender_accounts using this domain):")
    print("-" * 70)

    orphans = await db.fetch("""
        SELECT d.domain_name, w.workspace_name
        FROM domains d
        JOIN workspaces w ON d.workspace_id = w.id
        WHERE NOT EXISTS (
            SELECT 1 FROM sender_accounts sa
            WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
        )
        ORDER BY w.workspace_name, d.domain_name
    """)

    if orphans:
        print(f"Found {len(orphans)} orphan domains:")
        by_ws = {}
        for row in orphans:
            ws = row['workspace_name']
            if ws not in by_ws:
                by_ws[ws] = []
            by_ws[ws].append(row['domain_name'])

        for ws, domains in sorted(by_ws.items()):
            print(f"   {ws}: {len(domains)} domains")
            for d in domains[:3]:
                print(f"      - {d}")
            if len(domains) > 3:
                print(f"      ... and {len(domains) - 3} more")
    else:
        print("No orphan domains.")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_domains = await db.fetchval("SELECT COUNT(*) FROM domains")
    total_accounts = await db.fetchval("SELECT COUNT(*) FROM sender_accounts")
    linked_accounts = await db.fetchval("SELECT COUNT(*) FROM sender_accounts WHERE domain_id IS NOT NULL")

    print(f"Total domains: {total_domains}")
    print(f"Total sender_accounts: {total_accounts}")
    print(f"Accounts with domain_id linked: {linked_accounts} ({linked_accounts*100//total_accounts}%)")

    await db.close()


if __name__ == "__main__":
    asyncio.run(audit_domains())
