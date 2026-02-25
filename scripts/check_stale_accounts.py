#!/usr/bin/env python3
"""Check for stale accounts (in local but deleted from EmailBison)."""
import asyncio
import os
import asyncpg
import httpx

EMAILBISON_API_KEY = os.environ.get("EMAILBISON_API_KEY", "")
BASE_URL = "https://spellcast.hirecharm.com"


async def check_stale_accounts():
    db = await asyncpg.connect(
        host="postgres", port=5432, user="postgres",
        password="localdevpassword", database="postgres"
    )

    client = httpx.Client(timeout=60.0, headers={
        "Authorization": f"Bearer {EMAILBISON_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    })

    # Workspaces with mismatches (local > EmailBison)
    mismatched = [
        ("Charm", 2),
        ("Checkout Components", 10),
        ("Estrada", 17),
        ("EventPanda", 12),
    ]

    total_stale = 0

    for ws_name, eb_id in mismatched:
        print("=" * 70)
        print(f"CHECKING: {ws_name}")
        print("=" * 70)

        # Get workspace
        ws = await db.fetchrow(
            "SELECT id, emailbison_workspace_id FROM workspaces WHERE workspace_name = $1",
            ws_name
        )

        if not ws:
            print(f"Workspace not found: {ws_name}")
            continue

        # Get local accounts
        local_rows = await db.fetch(
            "SELECT email_address FROM sender_accounts WHERE workspace_id = $1",
            str(ws["id"])
        )
        local_emails = set(row["email_address"].lower() for row in local_rows)

        # Get EmailBison accounts
        client.post(f"{BASE_URL}/api/workspaces/v1.1/switch-workspace", json={"team_id": eb_id})

        eb_emails = set()
        page = 1
        while True:
            resp = client.get(f"{BASE_URL}/api/sender-emails", params={"page": page, "per_page": 100})
            data = resp.json()
            accounts = data.get("data", [])
            if not accounts:
                break
            for acc in accounts:
                eb_emails.add(acc.get("email", "").lower())
            meta = data.get("meta", {})
            if page >= meta.get("last_page", 1):
                break
            page += 1

        # Find stale (local but not in EB)
        stale = local_emails - eb_emails
        missing = eb_emails - local_emails

        print(f"Local: {len(local_emails)}, EmailBison: {len(eb_emails)}")
        print(f"Stale (local only): {len(stale)}")
        print(f"Missing (EB only): {len(missing)}")

        if stale:
            total_stale += len(stale)
            print(f"\nSample stale accounts (first 5):")
            for email in list(stale)[:5]:
                print(f"   {email}")

        print()

    print("=" * 70)
    print(f"TOTAL STALE ACCOUNTS: {total_stale}")
    print("=" * 70)
    print("\nThese accounts were likely deleted from EmailBison but still exist locally.")
    print("Consider marking them as inactive or removing them.")

    client.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(check_stale_accounts())
