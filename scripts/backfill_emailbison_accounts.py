#!/usr/bin/env python3
"""
Backfill sender_accounts from EmailBison (source of truth).

This script fetches all sender accounts from EmailBison and upserts them
into the local database, deriving domains and linking appropriately.

Usage:
    python scripts/backfill_emailbison_accounts.py [--dry-run] [--workspace NAME]

Requirements:
    - EMAILBISON_API_KEY environment variable
    - asyncpg: pip install asyncpg
    - httpx: pip install httpx
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from typing import Optional

try:
    import httpx
    import asyncpg
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install httpx asyncpg")
    sys.exit(1)


# ============================================================================
# Configuration
# ============================================================================

EMAILBISON_API = "https://spellcast.hirecharm.com"
EMAILBISON_API_KEY = os.environ.get("EMAILBISON_API_KEY", "")

# Local database
DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_PORT = int(os.environ.get("POSTGRES_PORT", "5433"))
DB_USER = os.environ.get("POSTGRES_USER", "postgres")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "localdevpassword")
DB_NAME = os.environ.get("POSTGRES_DB", "postgres")

# ESP type mapping (EmailBison provider -> local esp_type enum)
ESP_MAP = {
    "Google": "gmail",
    "google": "gmail",
    "Microsoft": "microsoft",
    "microsoft": "microsoft",
    "Yahoo": "other",
    "yahoo": "other",
}


# ============================================================================
# EmailBison API Functions
# ============================================================================

async def get_workspaces(client: httpx.AsyncClient) -> list[dict]:
    """Fetch all workspaces from EmailBison."""
    response = await client.get(f"{EMAILBISON_API}/api/workspaces/v1.1")
    response.raise_for_status()
    data = response.json()
    return data.get("data", [])


async def switch_workspace(client: httpx.AsyncClient, workspace_id: int) -> bool:
    """Switch to a specific workspace context."""
    response = await client.post(
        f"{EMAILBISON_API}/api/workspaces/v1.1/switch-workspace",
        json={"team_id": workspace_id}
    )
    return response.status_code == 200


async def fetch_workspace_accounts(client: httpx.AsyncClient, workspace_id: int) -> list[dict]:
    """Fetch all sender accounts from an EmailBison workspace (handles pagination)."""
    # Switch to workspace first
    if not await switch_workspace(client, workspace_id):
        print(f"    [ERROR] Failed to switch to workspace {workspace_id}")
        return []

    accounts = []
    page = 1

    while True:
        response = await client.get(
            f"{EMAILBISON_API}/api/sender-emails",
            params={"page": page, "per_page": 100}
        )

        if response.status_code != 200:
            print(f"    [ERROR] API returned {response.status_code}")
            break

        data = response.json()
        page_accounts = data.get("data", [])

        if not page_accounts:
            break

        accounts.extend(page_accounts)

        # Check pagination
        meta = data.get("meta", {})
        last_page = meta.get("last_page", 1)
        if page >= last_page:
            break
        page += 1

    return accounts


# ============================================================================
# Data Transformation
# ============================================================================

def infer_inbox_state(account: dict) -> str:
    """Determine inbox_state from EmailBison account data."""
    status = account.get("connection_status", account.get("status", ""))
    if status.lower() in ("not connected", "disconnected", "inactive"):
        return "dead"
    return "live"


def infer_esp(account: dict) -> str:
    """Map EmailBison provider to local esp_type."""
    provider = account.get("provider", account.get("esp_type", ""))
    return ESP_MAP.get(provider, "other")


def extract_domain(email: str) -> Optional[str]:
    """Extract domain from email address."""
    if "@" in email:
        return email.split("@")[1].lower()
    return None


def transform_account(account: dict, local_workspace_id: str) -> dict:
    """Transform EmailBison account to local sender_accounts format."""
    email = account.get("email", "")

    return {
        "workspace_id": local_workspace_id,
        "email_address": email.lower(),
        "emailbison_account_id": str(account.get("id", "")),
        "display_name": account.get("name", account.get("first_name", "")),
        "status": account.get("connection_status", account.get("status", "Unknown")),
        "health_score": account.get("health_score"),
        "esp": infer_esp(account),
        "inbox_state": infer_inbox_state(account),
        "bounce_rate_7d": account.get("bounce_rate", 0) or 0,
        "is_active": infer_inbox_state(account) == "live",
    }


# ============================================================================
# Database Operations
# ============================================================================

async def get_workspace_mapping(db: asyncpg.Connection) -> dict[str, str]:
    """Get mapping of EmailBison workspace ID -> local workspace UUID."""
    rows = await db.fetch("""
        SELECT id, workspace_name, emailbison_workspace_id
        FROM workspaces
        WHERE emailbison_workspace_id IS NOT NULL AND is_active = TRUE
    """)

    mapping = {}
    for row in rows:
        eb_id = row["emailbison_workspace_id"]
        if eb_id:
            mapping[str(eb_id)] = str(row["id"])

    return mapping


async def upsert_sender_account(db: asyncpg.Connection, data: dict, dry_run: bool = False) -> str:
    """Insert or update a sender_account. Returns 'inserted', 'updated', or 'skipped'."""
    if not data.get("email_address"):
        return "skipped"

    if dry_run:
        return "dry_run"

    # Check if exists
    existing = await db.fetchval("""
        SELECT id FROM sender_accounts
        WHERE workspace_id = $1 AND email_address = $2
    """, data["workspace_id"], data["email_address"])

    if existing:
        # Update
        await db.execute("""
            UPDATE sender_accounts SET
                emailbison_account_id = $1,
                status = $2,
                health_score = $3,
                esp = $4,
                inbox_state = $5,
                bounce_rate_7d = $6,
                is_active = $7,
                last_seen_at = NOW(),
                last_synced_at = NOW(),
                updated_at = NOW()
            WHERE workspace_id = $8 AND email_address = $9
        """,
            data["emailbison_account_id"],
            data["status"],
            data["health_score"],
            data["esp"],
            data["inbox_state"],
            data["bounce_rate_7d"],
            data["is_active"],
            data["workspace_id"],
            data["email_address"]
        )
        return "updated"
    else:
        # Insert
        await db.execute("""
            INSERT INTO sender_accounts (
                workspace_id, email_address, emailbison_account_id, display_name,
                status, health_score, esp, inbox_state, bounce_rate_7d, is_active,
                first_seen_at, last_seen_at, last_synced_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW(), NOW())
        """,
            data["workspace_id"],
            data["email_address"],
            data["emailbison_account_id"],
            data["display_name"],
            data["status"],
            data["health_score"],
            data["esp"],
            data["inbox_state"],
            data["bounce_rate_7d"],
            data["is_active"]
        )
        return "inserted"


async def create_missing_domains(db: asyncpg.Connection, dry_run: bool = False) -> int:
    """Create domain records for any sender_accounts without matching domains."""
    if dry_run:
        count = await db.fetchval("""
            SELECT COUNT(DISTINCT (sa.workspace_id, SPLIT_PART(sa.email_address, '@', 2)))
            FROM sender_accounts sa
            WHERE NOT EXISTS (
                SELECT 1 FROM domains d
                WHERE d.workspace_id = sa.workspace_id
                AND d.domain_name = SPLIT_PART(sa.email_address, '@', 2)
            )
        """)
        return count or 0

    result = await db.execute("""
        INSERT INTO domains (workspace_id, domain_name, approval_status)
        SELECT DISTINCT
            sa.workspace_id,
            SPLIT_PART(sa.email_address, '@', 2),
            'legacy'
        FROM sender_accounts sa
        WHERE NOT EXISTS (
            SELECT 1 FROM domains d
            WHERE d.workspace_id = sa.workspace_id
            AND d.domain_name = SPLIT_PART(sa.email_address, '@', 2)
        )
        ON CONFLICT DO NOTHING
    """)

    # Parse "INSERT 0 N" to get count
    if result:
        parts = result.split()
        if len(parts) >= 3:
            return int(parts[2])
    return 0


async def link_domains_to_accounts(db: asyncpg.Connection, dry_run: bool = False) -> int:
    """Link sender_accounts to their domains via domain_id."""
    if dry_run:
        count = await db.fetchval("""
            SELECT COUNT(*)
            FROM sender_accounts sa
            JOIN domains d ON sa.workspace_id = d.workspace_id
                AND SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
            WHERE sa.domain_id IS NULL
        """)
        return count or 0

    result = await db.execute("""
        UPDATE sender_accounts sa
        SET domain_id = d.id
        FROM domains d
        WHERE sa.workspace_id = d.workspace_id
        AND SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
        AND sa.domain_id IS NULL
    """)

    # Parse "UPDATE N" to get count
    if result:
        parts = result.split()
        if len(parts) >= 2:
            return int(parts[1])
    return 0


# ============================================================================
# Main
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Backfill sender_accounts from EmailBison")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--workspace", help="Sync specific workspace only (by name)")
    parser.add_argument("--skip-domains", action="store_true", help="Skip domain creation/linking")
    args = parser.parse_args()

    # Validate API key
    if not EMAILBISON_API_KEY:
        print("[ERROR] EMAILBISON_API_KEY environment variable not set")
        print("  Set it with: export EMAILBISON_API_KEY=your_key_here")
        sys.exit(1)

    print("=" * 60)
    print("EmailBison -> Local Database Backfill")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Target: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print()

    # Connect to database
    print("Connecting to database...")
    db = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

    # Get initial counts
    initial_count = await db.fetchval("SELECT COUNT(*) FROM sender_accounts")
    print(f"Current sender_accounts: {initial_count}")
    print()

    # Get workspace mapping
    print("Loading workspace mapping...")
    workspace_mapping = await get_workspace_mapping(db)
    print(f"Found {len(workspace_mapping)} workspaces with EmailBison IDs")
    print()

    # Create HTTP client
    headers = {
        "Authorization": f"Bearer {EMAILBISON_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    stats = {
        "workspaces_processed": 0,
        "accounts_fetched": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }

    async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
        # Get EmailBison workspaces
        print("Fetching EmailBison workspaces...")
        eb_workspaces = await get_workspaces(client)
        print(f"Found {len(eb_workspaces)} workspaces in EmailBison")
        print()

        # Process each workspace
        for eb_ws in eb_workspaces:
            eb_id = str(eb_ws.get("id"))
            eb_name = eb_ws.get("name", "Unknown")

            # Filter by workspace name if specified
            if args.workspace and eb_name.lower() != args.workspace.lower():
                continue

            # Check if we have a local mapping
            if eb_id not in workspace_mapping:
                print(f"[SKIP] {eb_name} (ID: {eb_id}) - no local workspace mapping")
                continue

            local_ws_id = workspace_mapping[eb_id]
            print(f"[SYNC] {eb_name} (EmailBison ID: {eb_id})")

            # Fetch accounts from EmailBison
            accounts = await fetch_workspace_accounts(client, int(eb_id))
            print(f"       Found {len(accounts)} accounts in EmailBison")
            stats["accounts_fetched"] += len(accounts)

            # Process each account
            for account in accounts:
                try:
                    data = transform_account(account, local_ws_id)
                    result = await upsert_sender_account(db, data, dry_run=args.dry_run)

                    if result == "inserted":
                        stats["inserted"] += 1
                    elif result == "updated":
                        stats["updated"] += 1
                    elif result == "skipped":
                        stats["skipped"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    print(f"       [ERROR] {account.get('email')}: {e}")

            stats["workspaces_processed"] += 1
            print(f"       Processed: +{stats['inserted']} inserted, ~{stats['updated']} updated")

    print()

    # Domain operations
    if not args.skip_domains:
        print("Creating missing domains...")
        domains_created = await create_missing_domains(db, dry_run=args.dry_run)
        print(f"  {'Would create' if args.dry_run else 'Created'} {domains_created} domains")

        print("Linking accounts to domains...")
        links_created = await link_domains_to_accounts(db, dry_run=args.dry_run)
        print(f"  {'Would link' if args.dry_run else 'Linked'} {links_created} accounts")

    print()

    # Final counts
    final_count = await db.fetchval("SELECT COUNT(*) FROM sender_accounts")

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Workspaces processed: {stats['workspaces_processed']}")
    print(f"Accounts fetched:     {stats['accounts_fetched']}")
    print(f"Inserted:             {stats['inserted']}")
    print(f"Updated:              {stats['updated']}")
    print(f"Skipped:              {stats['skipped']}")
    print(f"Errors:               {stats['errors']}")
    print()
    print(f"sender_accounts: {initial_count} -> {final_count} ({'+' if final_count >= initial_count else ''}{final_count - initial_count})")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
