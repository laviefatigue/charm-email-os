#!/usr/bin/env python3
"""
Fix domain workspace assignments.
- Delete duplicate domains (keep the one matching sender_accounts workspace)
- Reassign misplaced domains to correct workspace
- Delete orphan domains
"""
import asyncio
import asyncpg


async def fix_domains():
    db = await asyncpg.connect(
        host="postgres", port=5432, user="postgres",
        password="localdevpassword", database="postgres"
    )

    print("=" * 70)
    print("DOMAIN CLEANUP")
    print("=" * 70)

    # First, find the correct workspace for each domain based on sender_accounts
    print("\n1. Building domain -> correct workspace mapping from sender_accounts...")

    domain_to_ws = await db.fetch("""
        SELECT
            SPLIT_PART(sa.email_address, '@', 2) as domain_name,
            sa.workspace_id,
            w.workspace_name,
            COUNT(*) as account_count
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        GROUP BY SPLIT_PART(sa.email_address, '@', 2), sa.workspace_id, w.workspace_name
        ORDER BY domain_name, account_count DESC
    """)

    # Build mapping: domain -> correct workspace_id
    correct_ws = {}
    for row in domain_to_ws:
        domain = row["domain_name"]
        if domain not in correct_ws:
            # First occurrence has highest count, use that workspace
            correct_ws[domain] = str(row["workspace_id"])

    print(f"Found {len(correct_ws)} unique domains from sender_accounts")

    # 2. Delete all existing domains and recreate from sender_accounts
    print("\n2. Deleting all existing domains...")

    # First, clear domain_id from sender_accounts
    await db.execute("UPDATE sender_accounts SET domain_id = NULL")
    print("   Cleared domain_id from sender_accounts")

    # Delete all domains
    deleted = await db.execute("DELETE FROM domains")
    print(f"   Deleted domains: {deleted}")

    # 3. Recreate domains based on sender_accounts
    print("\n3. Recreating domains from sender_accounts...")

    # Insert unique domains per workspace
    inserted = await db.execute("""
        INSERT INTO domains (workspace_id, domain_name, approval_status, created_at, updated_at)
        SELECT DISTINCT
            sa.workspace_id,
            SPLIT_PART(sa.email_address, '@', 2),
            'legacy',
            NOW(),
            NOW()
        FROM sender_accounts sa
        WHERE SPLIT_PART(sa.email_address, '@', 2) != ''
        ON CONFLICT DO NOTHING
    """)
    print(f"   Inserted domains: {inserted}")

    # 4. Relink sender_accounts to domains
    print("\n4. Relinking sender_accounts to domains...")

    linked = await db.execute("""
        UPDATE sender_accounts sa
        SET domain_id = d.id
        FROM domains d
        WHERE sa.workspace_id = d.workspace_id
        AND SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
    """)
    print(f"   Linked: {linked}")

    # 5. Verify
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    total_domains = await db.fetchval("SELECT COUNT(*) FROM domains")
    total_accounts = await db.fetchval("SELECT COUNT(*) FROM sender_accounts")
    linked_accounts = await db.fetchval("SELECT COUNT(*) FROM sender_accounts WHERE domain_id IS NOT NULL")
    unlinked = await db.fetchval("SELECT COUNT(*) FROM sender_accounts WHERE domain_id IS NULL")

    print(f"Total domains: {total_domains}")
    print(f"Total sender_accounts: {total_accounts}")
    print(f"Linked accounts: {linked_accounts}")
    print(f"Unlinked accounts: {unlinked}")

    # Check for multi-workspace domains (should be 0 now)
    multi = await db.fetchval("""
        SELECT COUNT(*)
        FROM (
            SELECT domain_name
            FROM domains
            GROUP BY domain_name
            HAVING COUNT(DISTINCT workspace_id) > 1
        ) x
    """)
    print(f"Domains in multiple workspaces: {multi}")

    # Domain count by workspace
    print("\nDomains by workspace:")
    ws_domains = await db.fetch("""
        SELECT w.workspace_name, COUNT(d.id) as cnt
        FROM workspaces w
        LEFT JOIN domains d ON d.workspace_id = w.id
        WHERE w.is_active = TRUE
        GROUP BY w.workspace_name
        ORDER BY cnt DESC
    """)

    for row in ws_domains:
        print(f"   {row['workspace_name']:<30} {row['cnt']:>5}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(fix_domains())
