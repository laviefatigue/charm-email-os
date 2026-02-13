#!/usr/bin/env python3
"""Find and fix misassigned accounts (accounts in wrong workspace)."""
import asyncio
import os
import asyncpg
import httpx

EMAILBISON_API_KEY = os.environ.get("EMAILBISON_API_KEY", "")
BASE_URL = "https://spellcast.hirecharm.com"


async def analyze():
    db = await asyncpg.connect(
        host="postgres", port=5432, user="postgres",
        password="localdevpassword", database="postgres"
    )

    client = httpx.Client(timeout=60.0, headers={
        "Authorization": f"Bearer {EMAILBISON_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    })

    # Get all workspaces and their EmailBison IDs
    workspaces = await db.fetch("""
        SELECT id, workspace_name, emailbison_workspace_id
        FROM workspaces
        WHERE emailbison_workspace_id IS NOT NULL AND is_active = TRUE
    """)

    ws_map = {str(ws["id"]): ws["workspace_name"] for ws in workspaces}
    eb_id_map = {str(ws["emailbison_workspace_id"]): str(ws["id"]) for ws in workspaces}

    # Build complete EmailBison email -> workspace mapping
    print("Building EmailBison email->workspace mapping...")
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

        print(f"  {ws_name}: {len([e for e, w in eb_email_to_ws.items() if w['ws_id'] == ws_id])} accounts")

    print(f"\nTotal EmailBison accounts: {len(eb_email_to_ws)}")

    # Now check local accounts
    print("\n" + "=" * 70)
    print("MISASSIGNMENT ANALYSIS")
    print("=" * 70)

    local_accounts = await db.fetch("""
        SELECT sa.id, sa.email_address, sa.workspace_id, w.workspace_name
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
    """)

    misassigned = []
    not_in_eb = []
    correct = 0

    for acc in local_accounts:
        email = acc["email_address"].lower()
        local_ws_id = str(acc["workspace_id"])
        local_ws_name = acc["workspace_name"]

        if email in eb_email_to_ws:
            eb_info = eb_email_to_ws[email]
            if eb_info["ws_id"] != local_ws_id:
                misassigned.append({
                    "email": email,
                    "account_id": str(acc["id"]),
                    "local_ws": local_ws_name,
                    "correct_ws": eb_info["ws_name"],
                    "correct_ws_id": eb_info["ws_id"]
                })
            else:
                correct += 1
        else:
            not_in_eb.append({
                "email": email,
                "local_ws": local_ws_name
            })

    print(f"\nCorrectly assigned: {correct}")
    print(f"Misassigned (wrong workspace): {len(misassigned)}")
    print(f"Not in EmailBison (deleted?): {len(not_in_eb)}")

    # Show misassignment details
    if misassigned:
        print(f"\n{'='*70}")
        print("MISASSIGNED ACCOUNTS (sample)")
        print("=" * 70)

        # Group by local workspace
        by_ws = {}
        for m in misassigned:
            key = m["local_ws"]
            if key not in by_ws:
                by_ws[key] = []
            by_ws[key].append(m)

        for ws_name, accounts in sorted(by_ws.items(), key=lambda x: -len(x[1])):
            print(f"\n{ws_name}: {len(accounts)} misassigned")
            for acc in accounts[:3]:
                print(f"   {acc['email']} -> should be in {acc['correct_ws']}")

    client.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(analyze())
