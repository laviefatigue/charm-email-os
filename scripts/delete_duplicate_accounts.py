#!/usr/bin/env python3
"""Delete duplicate accounts that exist in wrong workspaces."""
import asyncio
import os
import asyncpg
import httpx

EMAILBISON_API_KEY = os.environ.get("EMAILBISON_API_KEY", "")
BASE_URL = "https://spellcast.hirecharm.com"


async def delete_duplicates():
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
    eb_email_to_ws_id = {}

    for ws in workspaces:
        eb_id = ws["emailbison_workspace_id"]
        ws_id = str(ws["id"])

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
                eb_email_to_ws_id[email] = ws_id
            meta = data.get("meta", {})
            if page >= meta.get("last_page", 1):
                break
            page += 1

    print(f"Loaded {len(eb_email_to_ws_id)} EmailBison accounts")

    # Find duplicate accounts in wrong workspaces
    local_accounts = await db.fetch("""
        SELECT sa.id, sa.email_address, sa.workspace_id, w.workspace_name
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
    """)

    to_delete = []

    for acc in local_accounts:
        email = acc["email_address"].lower()
        local_ws_id = str(acc["workspace_id"])

        if email in eb_email_to_ws_id:
            correct_ws_id = eb_email_to_ws_id[email]
            if correct_ws_id != local_ws_id:
                # This account is in the wrong workspace - mark for deletion
                to_delete.append({
                    "id": acc["id"],
                    "email": email,
                    "wrong_ws": acc["workspace_name"]
                })

    print(f"\nFound {len(to_delete)} duplicate accounts in wrong workspaces")

    if to_delete:
        print("\nDeleting duplicates...")

        # Delete in batches
        ids_to_delete = [d["id"] for d in to_delete]

        result = await db.execute("""
            DELETE FROM sender_accounts
            WHERE id = ANY($1::uuid[])
        """, ids_to_delete)

        print(f"Deleted: {result}")

    # Verify final state
    print("\n" + "=" * 70)
    print("FINAL VERIFICATION")
    print("=" * 70)

    final_count = await db.fetchval("SELECT COUNT(*) FROM sender_accounts")
    print(f"Total sender_accounts: {final_count}")

    # Quick workspace count check
    ws_counts = await db.fetch("""
        SELECT w.workspace_name, COUNT(sa.id) as cnt
        FROM workspaces w
        LEFT JOIN sender_accounts sa ON sa.workspace_id = w.id
        WHERE w.is_active = TRUE
        GROUP BY w.workspace_name
        ORDER BY cnt DESC
    """)

    print(f"\n{'Workspace':<30} {'Accounts':>10}")
    print("-" * 42)
    for row in ws_counts:
        print(f"{row['workspace_name']:<30} {row['cnt']:>10}")

    client.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(delete_duplicates())
