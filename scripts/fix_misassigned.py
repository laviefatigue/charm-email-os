#!/usr/bin/env python3
"""Fix misassigned accounts by moving them to correct workspaces."""
import asyncio
import os
import asyncpg
import httpx

EMAILBISON_API_KEY = os.environ.get("EMAILBISON_API_KEY", "")
BASE_URL = "https://spellcast.hirecharm.com"


async def fix():
    db = await asyncpg.connect(
        host="postgres", port=5432, user="postgres",
        password="localdevpassword", database="postgres"
    )

    client = httpx.Client(timeout=60.0, headers={
        "Authorization": f"Bearer {EMAILBISON_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    })

    # Get all workspaces
    workspaces = await db.fetch("""
        SELECT id, workspace_name, emailbison_workspace_id
        FROM workspaces
        WHERE emailbison_workspace_id IS NOT NULL AND is_active = TRUE
    """)

    # Build EmailBison email -> correct workspace mapping
    print("Building EmailBison mapping...")
    eb_email_to_ws = {}

    for ws in workspaces:
        eb_id = ws["emailbison_workspace_id"]
        ws_id = str(ws["id"])
        ws_name = ws["workspace_name"]

        client.post(f"{BASE_URL}/api/workspaces/v1.1/switch-workspace", json={"team_id": int(eb_id)})

        page = 1
        while True:
            resp = client.get(f"{BASE_URL}/api/sender-emails", params={"page": page, "per_page": 100})
            data = resp.json()
            accounts = data.get("data", [])
            if not accounts:
                break
            for acc in accounts:
                email = acc.get("email", "").lower()
                eb_email_to_ws[email] = {
                    "ws_id": ws_id,
                    "ws_name": ws_name,
                    "eb_account_id": str(acc.get("id", "")),
                    "eb_workspace_id": str(eb_id)
                }
            meta = data.get("meta", {})
            if page >= meta.get("last_page", 1):
                break
            page += 1

    print(f"Loaded {len(eb_email_to_ws)} EmailBison accounts")

    # Find and fix misassigned
    local_accounts = await db.fetch("""
        SELECT sa.id, sa.email_address, sa.workspace_id, sa.domain_id
        FROM sender_accounts sa
    """)

    fixed = 0
    errors = 0

    for acc in local_accounts:
        email = acc["email_address"].lower()
        local_ws_id = str(acc["workspace_id"])

        if email in eb_email_to_ws:
            eb_info = eb_email_to_ws[email]
            if eb_info["ws_id"] != local_ws_id:
                # Update workspace_id
                try:
                    await db.execute("""
                        UPDATE sender_accounts
                        SET workspace_id = $1, domain_id = NULL, updated_at = NOW()
                        WHERE id = $2
                    """, eb_info["ws_id"], acc["id"])
                    fixed += 1
                except Exception as e:
                    print(f"Error fixing {email}: {e}")
                    errors += 1

    print(f"\nFixed {fixed} misassigned accounts")
    print(f"Errors: {errors}")

    # Now relink domains
    print("\nRelinking domains...")
    linked = await db.execute("""
        UPDATE sender_accounts sa
        SET domain_id = d.id
        FROM domains d
        WHERE sa.workspace_id = d.workspace_id
        AND SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
        AND sa.domain_id IS NULL
    """)
    print(f"Domain links updated: {linked}")

    client.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(fix())
