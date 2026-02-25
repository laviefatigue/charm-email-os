#!/usr/bin/env python3
"""
Validate sender_accounts and domains match EmailBison source of truth.
"""
import asyncio
import os
import asyncpg
import httpx

EMAILBISON_API_KEY = os.environ.get("EMAILBISON_API_KEY", "")
BASE_URL = "https://spellcast.hirecharm.com"


async def validate():
    db = await asyncpg.connect(
        host="postgres", port=5432, user="postgres",
        password="localdevpassword", database="postgres"
    )

    # Get workspace mapping
    workspaces = await db.fetch("""
        SELECT id, workspace_name, emailbison_workspace_id
        FROM workspaces
        WHERE emailbison_workspace_id IS NOT NULL AND is_active = TRUE
        ORDER BY workspace_name
    """)

    client = httpx.Client(timeout=60.0, headers={
        "Authorization": f"Bearer {EMAILBISON_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    })

    print("=" * 80)
    print("CROSS-VALIDATION: Local DB vs EmailBison Sender Accounts")
    print("=" * 80)
    print(f"{'Workspace':<25} {'Local':>8} {'EmailBison':>12} {'Match':>8}")
    print("-" * 60)

    mismatches = []

    for ws in workspaces:
        ws_name = ws["workspace_name"]
        eb_id = ws["emailbison_workspace_id"]
        local_id = str(ws["id"])

        # Get local count
        local_count = await db.fetchval(
            "SELECT COUNT(*) FROM sender_accounts WHERE workspace_id = $1", local_id
        )

        # Get EmailBison count
        try:
            client.post(f"{BASE_URL}/api/workspaces/v1.1/switch-workspace", json={"team_id": int(eb_id)})

            eb_count = 0
            page = 1
            while True:
                resp = client.get(f"{BASE_URL}/api/sender-emails", params={"page": page, "per_page": 100})
                data = resp.json()
                accounts = data.get("data", [])
                if not accounts:
                    break
                eb_count += len(accounts)
                meta = data.get("meta", {})
                if page >= meta.get("last_page", 1):
                    break
                page += 1

            match = "✓" if local_count == eb_count else "✗"
            if local_count != eb_count:
                mismatches.append((ws_name, local_count, eb_count, eb_id))

            print(f"{ws_name:<25} {local_count:>8} {eb_count:>12} {match:>8}")
        except Exception as e:
            print(f"{ws_name:<25} {local_count:>8} {'ERROR':>12} {'?':>8}")

    print("-" * 60)

    if mismatches:
        print(f"\n⚠️  {len(mismatches)} workspace(s) have count mismatches:")
        for ws_name, local, eb, eb_id in mismatches:
            diff = eb - local
            print(f"   {ws_name}: Local={local}, EmailBison={eb} (diff: {'+' if diff > 0 else ''}{diff})")
    else:
        print("\n✓ All sender_accounts match!")

    # Now validate domains - check if all sender email domains exist
    print("\n" + "=" * 80)
    print("DOMAIN VALIDATION: Check domain coverage")
    print("=" * 80)

    # Find sender_accounts with missing domain linkage
    missing_domain_link = await db.fetchval("""
        SELECT COUNT(*) FROM sender_accounts WHERE domain_id IS NULL
    """)
    print(f"Sender accounts without domain_id link: {missing_domain_link}")

    # Find domains that don't match any sender_account email domain
    orphan_domains = await db.fetch("""
        SELECT d.domain_name, w.workspace_name
        FROM domains d
        JOIN workspaces w ON d.workspace_id = w.id
        WHERE NOT EXISTS (
            SELECT 1 FROM sender_accounts sa
            WHERE sa.workspace_id = d.workspace_id
            AND SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
        )
        LIMIT 20
    """)

    if orphan_domains:
        print(f"\nDomains with no matching sender_accounts ({len(orphan_domains)} shown, may be more):")
        for row in orphan_domains:
            print(f"   {row['domain_name']} ({row['workspace_name']})")

    # Find sender_accounts with email domains not in domains table
    missing_domains = await db.fetch("""
        SELECT DISTINCT SPLIT_PART(sa.email_address, '@', 2) as domain, w.workspace_name, COUNT(*) as count
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        WHERE NOT EXISTS (
            SELECT 1 FROM domains d
            WHERE d.workspace_id = sa.workspace_id
            AND d.domain_name = SPLIT_PART(sa.email_address, '@', 2)
        )
        GROUP BY SPLIT_PART(sa.email_address, '@', 2), w.workspace_name
        ORDER BY count DESC
        LIMIT 20
    """)

    if missing_domains:
        print(f"\nEmail domains not in domains table ({len(missing_domains)} shown):")
        for row in missing_domains:
            print(f"   {row['domain']} ({row['workspace_name']}) - {row['count']} accounts")
    else:
        print("\n✓ All email domains have corresponding domain records!")

    client.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(validate())
