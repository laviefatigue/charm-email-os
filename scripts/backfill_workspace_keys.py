#!/usr/bin/env python3
"""
Backfill workspace_api_keys for existing workspaces.

This is a one-time script. Run after migration 089 is deployed.
Fill in the KEYS dict below with values from Coolify → charm-api env vars.

Usage:
    py scripts/backfill_workspace_keys.py [--dry-run]
"""
import sys
import asyncio
import asyncpg
import os

# ─────────────────────────────────────────────────────────────────────────────
# FILL THESE IN before running.
# eb_workspace_id → workspace-scoped EB API token
# Keys were generated via _tmp_create_key.py and are stored in Coolify.
# ─────────────────────────────────────────────────────────────────────────────
KEYS = {
    4:  ("Hello Hero",    "PASTE_KEY_HERE"),
    13: ("Spout",         "PASTE_KEY_HERE"),
    22: ("Selery",        "PASTE_KEY_HERE"),
    24: ("Search Atlas",  "PASTE_KEY_HERE"),
    25: ("Linkgraph",     "PASTE_KEY_HERE"),
}


async def main(dry_run: bool = False):
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    # Validate no placeholders remain
    missing = [name for (_, (name, token)) in KEYS.items() if token == "PASTE_KEY_HERE"]
    if missing:
        print(f"ERROR: Fill in KEYS dict before running. Missing: {missing}")
        sys.exit(1)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Resolve workspace_id from emailbison_workspace_id
        rows = await conn.fetch(
            "SELECT id, emailbison_workspace_id, workspace_name FROM workspaces "
            "WHERE emailbison_workspace_id = ANY($1::text[])",
            [str(k) for k in KEYS.keys()]
        )

        matched = {int(row["emailbison_workspace_id"]): row for row in rows}
        print(f"Found {len(matched)}/{len(KEYS)} workspaces in DB")

        inserted = 0
        for eb_id, (ws_name, token) in KEYS.items():
            row = matched.get(eb_id)
            if not row:
                print(f"  SKIP: EB workspace {eb_id} ({ws_name}) not found in DB")
                continue

            workspace_id = row["id"]
            key_name = f"{ws_name} dashboard key"

            if dry_run:
                print(f"  DRY RUN: would insert key for {ws_name} (workspace_id={workspace_id})")
                continue

            await conn.execute("""
                INSERT INTO workspace_api_keys
                    (workspace_id, emailbison_workspace_id, key_name, key_token)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (workspace_id) DO UPDATE SET
                    key_token = EXCLUDED.key_token,
                    key_name = EXCLUDED.key_name,
                    updated_at = NOW(),
                    is_active = TRUE
            """, workspace_id, eb_id, key_name, token)

            print(f"  OK: {ws_name} (EB {eb_id}) → key stored")
            inserted += 1

        if not dry_run:
            print(f"\nDone: {inserted} keys stored in workspace_api_keys")
        else:
            print(f"\nDry run complete. Re-run without --dry-run to apply.")

    finally:
        await conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run))
