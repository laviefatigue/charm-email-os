#!/usr/bin/env python3
"""
Backfill A-Set/B-Set Tags from EmailBison

This script syncs EXISTING tags from EmailBison to our local database,
ensuring we don't re-tag inboxes that already have set assignments.

Steps:
1. For each workspace, detect tag naming convention ('A Set'/'B Set' vs 'live'/'bset')
2. Query EmailBison for inboxes with existing set tags
3. Update local inventory_pool_status to match
4. Report which inboxes are already tagged vs need tagging

After running this, the regular set_tag_sync will only tag untagged graduated inboxes.

Usage:
    python scripts/backfill_set_tags.py
    python scripts/backfill_set_tags.py --workspace Searchatlas
    python scripts/backfill_set_tags.py --dry-run
"""
import asyncio
import argparse
import os
import sys
from datetime import datetime
from typing import Optional, Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

from sync_modules.emailbison_client import EmailBisonClient

# Database connection
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5433))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'localdevpassword')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'postgres')

# Possible tag names for A-Set and B-Set
A_SET_TAG_NAMES = ['A Set', 'live', 'a set', 'a-set', 'aset']
B_SET_TAG_NAMES = ['B Set', 'bset', 'b set', 'b-set', 'reserve']


async def get_workspaces(db: asyncpg.Pool, workspace_name: Optional[str] = None) -> List[Dict]:
    """Get workspaces with EmailBison integration."""
    query = """
        SELECT id, workspace_name, emailbison_workspace_id,
               a_set_tag_name, b_set_tag_name
        FROM workspaces
        WHERE emailbison_workspace_id IS NOT NULL
        AND is_active = TRUE
    """
    if workspace_name:
        query += " AND workspace_name = $1"
        return await db.fetch(query, workspace_name)
    return await db.fetch(query)


async def detect_existing_tags(client: EmailBisonClient) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Detect existing A-Set and B-Set tags in the current workspace.

    Returns:
        Tuple of (a_set_tag, b_set_tag) dicts or None if not found
    """
    try:
        tags = await client.list_tags()
    except Exception as e:
        print(f"    Error listing tags: {e}")
        return None, None

    a_set_tag = None
    b_set_tag = None

    for tag in tags:
        tag_name = tag.get('name', '').lower()

        # Check for A-Set variants
        if tag_name in [t.lower() for t in A_SET_TAG_NAMES]:
            a_set_tag = tag

        # Check for B-Set variants
        if tag_name in [t.lower() for t in B_SET_TAG_NAMES]:
            b_set_tag = tag

    return a_set_tag, b_set_tag


async def get_tagged_inboxes(client: EmailBisonClient, tag_id: int) -> List[Dict]:
    """Get all inboxes with a specific tag from EmailBison."""
    try:
        # Use the leads endpoint with tag filter
        response = await client.api_request(
            'GET',
            '/api/v1/lead',
            params={'tagIds': str(tag_id), 'limit': 1000}
        )
        return response.get('items', [])
    except Exception as e:
        print(f"    Error fetching tagged inboxes: {e}")
        return []


async def backfill_workspace(
    db: asyncpg.Pool,
    client: EmailBisonClient,
    workspace: Dict,
    dry_run: bool = False
) -> Dict:
    """
    Backfill set tags for a single workspace.

    Returns:
        Dict with counts of actions taken
    """
    workspace_id = workspace['id']
    workspace_name = workspace['workspace_name']
    eb_workspace_id = int(workspace['emailbison_workspace_id'])

    result = {
        'workspace': workspace_name,
        'a_set_found': 0,
        'b_set_found': 0,
        'a_set_updated': 0,
        'b_set_updated': 0,
        'already_correct': 0,
        'not_in_db': 0,
        'tag_names': {}
    }

    print(f"\n{'='*60}")
    print(f"Workspace: {workspace_name}")
    print(f"{'='*60}")

    # Switch to workspace
    if not await client.switch_workspace(eb_workspace_id):
        print(f"  ERROR: Failed to switch to workspace")
        return result

    # Detect existing tags
    a_set_tag, b_set_tag = await detect_existing_tags(client)

    if not a_set_tag and not b_set_tag:
        print(f"  No A-Set or B-Set tags found in EmailBison")
        return result

    if a_set_tag:
        result['tag_names']['a_set'] = a_set_tag['name']
        print(f"  A-Set tag: '{a_set_tag['name']}' (ID: {a_set_tag['id']})")

    if b_set_tag:
        result['tag_names']['b_set'] = b_set_tag['name']
        print(f"  B-Set tag: '{b_set_tag['name']}' (ID: {b_set_tag['id']})")

    # Get our local inboxes for this workspace
    local_inboxes = await db.fetch("""
        SELECT id, email_address, emailbison_account_id, inventory_pool_status
        FROM sender_accounts
        WHERE workspace_id = $1
        AND emailbison_account_id IS NOT NULL
        AND is_active = TRUE
    """, workspace_id)

    # Build lookup by EmailBison account ID
    eb_to_local = {
        str(inbox['emailbison_account_id']): inbox
        for inbox in local_inboxes
    }

    print(f"  Local inboxes with EmailBison ID: {len(local_inboxes)}")

    # Process A-Set tagged inboxes
    if a_set_tag:
        print(f"\n  Fetching A-Set tagged inboxes...")
        a_set_inboxes = await get_tagged_inboxes(client, a_set_tag['id'])
        result['a_set_found'] = len(a_set_inboxes)
        print(f"  Found {len(a_set_inboxes)} inboxes with A-Set tag")

        for inbox in a_set_inboxes:
            eb_id = str(inbox.get('id'))
            email = inbox.get('email', 'unknown')

            if eb_id not in eb_to_local:
                result['not_in_db'] += 1
                continue

            local = eb_to_local[eb_id]
            current_pool = local['inventory_pool_status']

            if current_pool == 'deployed':
                result['already_correct'] += 1
                continue

            # Update to deployed (A-Set)
            if not dry_run:
                await db.execute("""
                    UPDATE sender_accounts
                    SET inventory_pool_status = 'deployed',
                        updated_at = NOW()
                    WHERE id = $1
                """, local['id'])

            result['a_set_updated'] += 1
            print(f"    [A-SET] {email}: {current_pool or 'NULL'} -> deployed")

    # Process B-Set tagged inboxes
    if b_set_tag:
        print(f"\n  Fetching B-Set tagged inboxes...")
        b_set_inboxes = await get_tagged_inboxes(client, b_set_tag['id'])
        result['b_set_found'] = len(b_set_inboxes)
        print(f"  Found {len(b_set_inboxes)} inboxes with B-Set tag")

        for inbox in b_set_inboxes:
            eb_id = str(inbox.get('id'))
            email = inbox.get('email', 'unknown')

            if eb_id not in eb_to_local:
                result['not_in_db'] += 1
                continue

            local = eb_to_local[eb_id]
            current_pool = local['inventory_pool_status']

            if current_pool == 'reserve':
                result['already_correct'] += 1
                continue

            # Update to reserve (B-Set)
            if not dry_run:
                await db.execute("""
                    UPDATE sender_accounts
                    SET inventory_pool_status = 'reserve',
                        updated_at = NOW()
                    WHERE id = $1
                """, local['id'])

            result['b_set_updated'] += 1
            print(f"    [B-SET] {email}: {current_pool or 'NULL'} -> reserve")

    # Save tag names to workspace config
    if not dry_run and (a_set_tag or b_set_tag):
        await db.execute("""
            UPDATE workspaces
            SET a_set_tag_name = COALESCE($2, a_set_tag_name),
                b_set_tag_name = COALESCE($3, b_set_tag_name),
                updated_at = NOW()
            WHERE id = $1
        """, workspace_id,
            a_set_tag['name'] if a_set_tag else None,
            b_set_tag['name'] if b_set_tag else None
        )

    return result


async def main():
    parser = argparse.ArgumentParser(
        description='Backfill A-Set/B-Set tags from EmailBison to local database'
    )
    parser.add_argument('--workspace', '-w', help='Process only this workspace')
    parser.add_argument('--dry-run', '-n', action='store_true',
                       help='Show what would be done without making changes')
    args = parser.parse_args()

    if args.dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***\n")

    # Connect to database
    db = await asyncpg.create_pool(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
        min_size=1,
        max_size=5
    )

    results = []

    try:
        workspaces = await get_workspaces(db, args.workspace)

        if not workspaces:
            print(f"No workspaces found{f' matching {args.workspace}' if args.workspace else ''}")
            return

        print(f"\nBackfilling set tags for {len(workspaces)} workspace(s)")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        async with EmailBisonClient() as client:
            for ws in workspaces:
                result = await backfill_workspace(db, client, ws, args.dry_run)
                results.append(result)

                # Delay between workspaces
                await asyncio.sleep(1.0)

        # Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)

        total_a_updated = sum(r['a_set_updated'] for r in results)
        total_b_updated = sum(r['b_set_updated'] for r in results)
        total_correct = sum(r['already_correct'] for r in results)

        print(f"\nWorkspaces processed: {len(results)}")
        print(f"A-Set tags synced: {total_a_updated}")
        print(f"B-Set tags synced: {total_b_updated}")
        print(f"Already correct: {total_correct}")

        if args.dry_run:
            print("\n*** DRY RUN - No changes were made ***")
            print("Run without --dry-run to apply changes")
        else:
            print("\nBackfill complete. Run set_tag_sync to tag remaining inboxes.")

    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
