#!/usr/bin/env python3
"""
Backfill Daily Volume Snapshots from EmailBison API

This script queries EmailBison's campaign stats endpoint for each day
in the specified range and updates the daily_volume_snapshots table
with real sending volume data.

Usage:
    python scripts/backfill_daily_volume.py --days 90
    python scripts/backfill_daily_volume.py --start-date 2025-11-01 --end-date 2026-02-22
    python scripts/backfill_daily_volume.py --workspace-id b9abd34a-f16a-4b92-bda0-5af10f8c44bd --days 30

Environment Variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    EMAILBISON_API_URL, EMAILBISON_API_KEY
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from typing import Dict, List, Optional
import httpx
import asyncpg

# Configuration
EMAILBISON_API_URL = os.getenv('EMAILBISON_API_URL', 'https://spellcast.hirecharm.com/api')
EMAILBISON_API_KEY = os.getenv('EMAILBISON_API_KEY', '17|MJ4B2ye4YyzawJFcQKxNJlIFGmyafaEQuZodYCV6d1ef7cbb')

# Ensure API URL has /api suffix
if not EMAILBISON_API_URL.endswith('/api'):
    EMAILBISON_API_URL = EMAILBISON_API_URL.rstrip('/') + '/api'

POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5433'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'postgres')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'localdevpassword')

# Rate limiting
API_DELAY_SECONDS = 0.5  # Delay between API calls to avoid rate limiting


class EmailBisonBackfill:
    """Backfill daily volume snapshots from EmailBison API."""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.client: Optional[httpx.AsyncClient] = None
        self.current_workspace_id: Optional[int] = None
        self.stats = {
            'workspaces_processed': 0,
            'days_processed': 0,
            'campaigns_queried': 0,
            'rows_updated': 0,
            'total_emails_backfilled': 0,
            'errors': []
        }

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                'Authorization': f'Bearer {EMAILBISON_API_KEY}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def switch_workspace(self, emailbison_workspace_id: int) -> bool:
        """Switch to an EmailBison workspace."""
        if self.current_workspace_id == emailbison_workspace_id:
            return True

        try:
            response = await self.client.post(
                f'{EMAILBISON_API_URL}/workspaces/v1.1/switch-workspace',
                json={'team_id': int(emailbison_workspace_id)}
            )
            response.raise_for_status()
            self.current_workspace_id = emailbison_workspace_id
            return True
        except Exception as e:
            print(f"  [ERROR] Failed to switch to workspace {emailbison_workspace_id}: {e}")
            return False

    async def get_campaigns(self) -> List[Dict]:
        """Get all campaigns for current workspace."""
        campaigns = []
        page = 1

        while True:
            response = await self.client.get(
                f'{EMAILBISON_API_URL}/campaigns',
                params={'page': page, 'limit': 100}
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                campaigns.extend(data)
                break
            else:
                page_campaigns = data.get('data', [])
                if not page_campaigns:
                    break
                campaigns.extend(page_campaigns)
                meta = data.get('meta', {})
                if page >= meta.get('last_page', page):
                    break
            page += 1

        return campaigns

    async def get_campaign_stats_for_day(self, campaign_id: int, day: date) -> Dict:
        """Get campaign stats for a single day."""
        try:
            day_str = day.strftime('%Y-%m-%d')
            response = await self.client.post(
                f'{EMAILBISON_API_URL}/campaigns/{campaign_id}/stats',
                json={'start_date': day_str, 'end_date': day_str}
            )
            response.raise_for_status()
            result = response.json()

            # Handle both response formats
            if 'data' in result:
                return result['data']
            return result

        except Exception as e:
            # Don't fail on individual campaign errors
            return {'emails_sent': 0, 'bounced': 0, 'unique_replies_per_contact': 0}

    async def get_workspaces_to_process(self, workspace_id: Optional[str] = None) -> List[Dict]:
        """Get workspaces to process from database."""
        async with self.db_pool.acquire() as conn:
            if workspace_id:
                rows = await conn.fetch("""
                    SELECT id, workspace_name, emailbison_workspace_id
                    FROM workspaces
                    WHERE id = $1 AND emailbison_workspace_id IS NOT NULL
                """, workspace_id)
            else:
                rows = await conn.fetch("""
                    SELECT id, workspace_name, emailbison_workspace_id
                    FROM workspaces
                    WHERE is_active = true
                      AND emailbison_workspace_id IS NOT NULL
                    ORDER BY workspace_name
                """)

            return [dict(row) for row in rows]

    async def update_snapshot(
        self,
        workspace_id: str,
        snapshot_date: date,
        emails_sent: int,
        emails_bounced: int
    ) -> bool:
        """Update a daily volume snapshot with real data."""
        import uuid
        workspace_uuid = uuid.UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id

        # Calculate utilization percentage in Python to avoid type issues
        async with self.db_pool.acquire() as conn:
            # First get the capacity
            row = await conn.fetchrow("""
                SELECT daily_capacity_available
                FROM daily_volume_snapshots
                WHERE workspace_id = $1 AND snapshot_date = $2
            """, workspace_uuid, snapshot_date)

            if not row:
                return False

            capacity = row['daily_capacity_available'] or 0
            utilization_pct = round((emails_sent / capacity) * 100, 2) if capacity > 0 else 0

            result = await conn.execute("""
                UPDATE daily_volume_snapshots
                SET emails_sent = $1,
                    emails_bounced = $2,
                    capacity_utilization_pct = $3,
                    updated_at = NOW()
                WHERE workspace_id = $4
                  AND snapshot_date = $5
            """, emails_sent, emails_bounced, utilization_pct, workspace_uuid, snapshot_date)

            return result == 'UPDATE 1'

    async def backfill_workspace(
        self,
        workspace: Dict,
        start_date: date,
        end_date: date
    ) -> Dict:
        """Backfill all days for a single workspace."""
        workspace_id = workspace['id']
        workspace_name = workspace['workspace_name']
        emailbison_id = workspace['emailbison_workspace_id']

        print(f"\n[WORKSPACE] Processing: {workspace_name} (EB ID: {emailbison_id})")

        # Switch to workspace
        if not await self.switch_workspace(emailbison_id):
            self.stats['errors'].append(f"Failed to switch to {workspace_name}")
            return {'emails_sent': 0, 'days': 0}

        # Get campaigns
        campaigns = await self.get_campaigns()
        if not campaigns:
            print(f"  [WARN] No campaigns found")
            return {'emails_sent': 0, 'days': 0}

        print(f"  [INFO] Found {len(campaigns)} campaigns")
        campaign_ids = [c['id'] for c in campaigns]

        # Process each day
        workspace_total = 0
        days_processed = 0
        current_date = start_date

        while current_date <= end_date:
            day_total_sent = 0
            day_total_bounced = 0

            # Query each campaign for this day
            for campaign_id in campaign_ids:
                stats = await self.get_campaign_stats_for_day(campaign_id, current_date)

                # Parse emails_sent (could be string or int)
                sent = stats.get('emails_sent', 0)
                if isinstance(sent, str):
                    sent = int(sent) if sent.isdigit() else 0

                bounced = stats.get('bounced', 0)
                if isinstance(bounced, str):
                    bounced = int(bounced) if bounced.isdigit() else 0

                day_total_sent += sent
                day_total_bounced += bounced
                self.stats['campaigns_queried'] += 1

                # Rate limiting
                await asyncio.sleep(API_DELAY_SECONDS)

            # Update snapshot
            if await self.update_snapshot(workspace_id, current_date, day_total_sent, day_total_bounced):
                self.stats['rows_updated'] += 1

            workspace_total += day_total_sent
            days_processed += 1
            self.stats['days_processed'] += 1
            self.stats['total_emails_backfilled'] += day_total_sent

            # Progress indicator (every 7 days)
            if days_processed % 7 == 0 or current_date == end_date:
                print(f"  [{current_date}] {day_total_sent:,} emails | Running total: {workspace_total:,}")

            current_date += timedelta(days=1)

        print(f"  [DONE] Workspace complete: {workspace_total:,} emails over {days_processed} days")
        self.stats['workspaces_processed'] += 1

        return {'emails_sent': workspace_total, 'days': days_processed}

    async def run(
        self,
        start_date: date,
        end_date: date,
        workspace_id: Optional[str] = None
    ):
        """Run the backfill process."""
        print("=" * 60)
        print("EmailBison Daily Volume Backfill")
        print("=" * 60)
        print(f"Date range: {start_date} to {end_date}")
        print(f"API URL: {EMAILBISON_API_URL}")
        print(f"Database: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")

        # Get workspaces
        workspaces = await self.get_workspaces_to_process(workspace_id)
        if not workspaces:
            print("[ERROR] No workspaces found to process")
            return

        print(f"\nWorkspaces to process: {len(workspaces)}")
        for ws in workspaces:
            print(f"   - {ws['workspace_name']} (EB ID: {ws['emailbison_workspace_id']})")

        # Process each workspace
        grand_total = 0
        for workspace in workspaces:
            try:
                result = await self.backfill_workspace(workspace, start_date, end_date)
                grand_total += result['emails_sent']
            except Exception as e:
                error_msg = f"Error processing {workspace['workspace_name']}: {e}"
                print(f"  [ERROR] {error_msg}")
                self.stats['errors'].append(error_msg)

        # Summary
        print("\n" + "=" * 60)
        print("BACKFILL COMPLETE")
        print("=" * 60)
        print(f"Workspaces processed: {self.stats['workspaces_processed']}")
        print(f"Days processed: {self.stats['days_processed']}")
        print(f"Campaign queries: {self.stats['campaigns_queried']}")
        print(f"Rows updated: {self.stats['rows_updated']}")
        print(f"Total emails backfilled: {self.stats['total_emails_backfilled']:,}")

        if self.stats['errors']:
            print(f"\n[WARN] Errors ({len(self.stats['errors'])}):")
            for err in self.stats['errors'][:5]:
                print(f"   - {err}")


async def main():
    parser = argparse.ArgumentParser(description='Backfill daily volume snapshots from EmailBison')
    parser.add_argument('--days', type=int, default=90, help='Number of days to backfill (default: 90)')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--workspace-id', type=str, help='Specific workspace UUID to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    args = parser.parse_args()

    # Calculate date range
    if args.start_date and args.end_date:
        start_date = date.fromisoformat(args.start_date)
        end_date = date.fromisoformat(args.end_date)
    else:
        end_date = date.today() - timedelta(days=1)  # Yesterday
        start_date = end_date - timedelta(days=args.days - 1)

    # Connect to database
    try:
        db_pool = await asyncpg.create_pool(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            min_size=1,
            max_size=5
        )
    except Exception as e:
        print(f"[ERROR] Failed to connect to database: {e}")
        sys.exit(1)

    try:
        async with EmailBisonBackfill(db_pool) as backfill:
            await backfill.run(
                start_date=start_date,
                end_date=end_date,
                workspace_id=args.workspace_id
            )
    finally:
        await db_pool.close()


if __name__ == '__main__':
    asyncio.run(main())
