#!/usr/bin/env python3
"""
Backfill 90 days of engagement snapshots from EmailBison.

One-time script. Populates inbox_engagement_snapshots table with historical
daily event data (opens, replies, interested, sent, bounced, unsubscribed)
per inbox.

Usage:
    python scripts/backfill_engagement_90d.py

Requires:
    - Database connection (POSTGRES_* env vars)
    - EmailBison API access (EMAILBISON_* env vars)
    - Migration 086 applied (inbox_engagement_snapshots table exists)
"""
import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
from sync_modules import EmailBisonClient, AuditLogger, SlackAlerter, EngagementSyncModule


POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5433))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'charm')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'charm_email_os')

DAYS_BACK = int(os.getenv('BACKFILL_DAYS', 90))


async def main():
    print(f"[{datetime.now()}] Engagement backfill: {DAYS_BACK} days")
    print(f"  Database: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")

    # Connect to database
    db = await asyncpg.create_pool(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
        min_size=1,
        max_size=3
    )

    try:
        # Get active workspaces
        workspaces = await db.fetch("""
            SELECT w.id, w.workspace_name, w.emailbison_workspace_id,
                   c.name as client_name
            FROM workspaces w
            LEFT JOIN clients c ON w.id = c.workspace_id
            WHERE w.emailbison_workspace_id IS NOT NULL
            AND w.is_active = TRUE
            ORDER BY c.name
        """)

        print(f"  Workspaces: {len(workspaces)}")

        total_snapshots = 0

        async with EmailBisonClient() as client:
            audit_logger = AuditLogger(db)
            engagement = EngagementSyncModule(
                db=db, client=client,
                audit_logger=audit_logger
            )

            for ws in workspaces:
                client_name = ws['client_name'] or ws['workspace_name']
                print(f"\n--- {client_name} ---")

                count = await engagement.backfill_workspace(
                    workspace_id=ws['id'],
                    workspace_name=client_name,
                    eb_workspace_id=ws['emailbison_workspace_id'],
                    days_back=DAYS_BACK
                )
                total_snapshots += count

        print(f"\n[{datetime.now()}] Backfill complete: {total_snapshots} total snapshots")

        # Verify
        snapshot_count = await db.fetchval(
            "SELECT COUNT(*) FROM inbox_engagement_snapshots"
        )
        print(f"  Total snapshots in table: {snapshot_count}")

        # Check ESP performance view
        esp_data = await db.fetch("SELECT * FROM v_esp_performance")
        if esp_data:
            print(f"\n  ESP Performance:")
            for row in esp_data:
                print(f"    {row.get('provider', '?')}: "
                      f"sent={row.get('total_sent', 0)}, "
                      f"opens={row.get('unique_opens', 0)}, "
                      f"replies={row.get('unique_replies', 0)}, "
                      f"interested={row.get('interested_leads', 0)}, "
                      f"open_rate={row.get('open_rate_pct', 0)}%, "
                      f"reply_rate={row.get('reply_rate_pct', 0)}%")

    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
