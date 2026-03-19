"""
Engagement Sync Module

Captures positive engagement signals per inbox from EmailBison's
campaign-events/stats endpoint and stores daily snapshots for
time-series analysis. Rolls up to domain level.

Endpoints used:
- GET /api/campaign-events/stats (per-inbox daily event counts)

Sync cadence:
- All-time counters: captured by sync_accounts.py hourly (zero extra API calls)
- Daily snapshots: captured once per day during low-traffic hours
- 7-day windowed metrics: derived from snapshot table after daily capture
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID

import asyncpg

from .audit_logger import AuditLogger, SyncResult
from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .slack_alerter import SlackAlerter


# Event label mapping from EB campaign-events/stats response
EVENT_LABEL_MAP = {
    'Replied': 'replies',
    'Total Opens': 'opens',
    'Unique Opens': 'unique_opens',
    'Sent': 'sent',
    'Bounced': 'bounced',
    'Unsubscribed': 'unsubscribed',
    'Interested': 'interested',
}


class EngagementSyncModule:
    """
    Syncs per-inbox engagement data from EmailBison and stores daily snapshots.

    Two modes:
    1. Daily snapshot: one API call per inbox for yesterday's data → inbox_engagement_snapshots
    2. 7-day window update: derive windowed metrics from snapshot table → sender_accounts
    """

    def __init__(
        self,
        db: asyncpg.Pool,
        client: EmailBisonClient,
        audit_logger: AuditLogger,
        alerter: SlackAlerter = None
    ):
        self.db = db
        self.client = client
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()

    async def sync_all_workspaces(self) -> List[SyncResult]:
        """Capture daily engagement snapshots for all workspaces."""
        workspaces = await self.db.fetch("""
            SELECT id, workspace_name, emailbison_workspace_id
            FROM workspaces
            WHERE emailbison_workspace_id IS NOT NULL
            AND is_active = TRUE
        """)

        results = []
        for ws in workspaces:
            result = await self.sync_workspace(
                workspace_id=ws['id'],
                workspace_name=ws['workspace_name'],
                eb_workspace_id=ws['emailbison_workspace_id']
            )
            results.append(result)
            await self.client.inter_batch_delay(1.0)

        return results

    async def sync_workspace(
        self,
        workspace_id: UUID,
        workspace_name: str,
        eb_workspace_id: int
    ) -> SyncResult:
        """
        Capture daily engagement snapshots for all connected inboxes in a workspace.

        For each inbox, calls /api/campaign-events/stats with yesterday's date range
        and stores the daily event counts in inbox_engagement_snapshots.
        Then updates 7-day windowed metrics on sender_accounts and rolls up to domains.
        """
        audit = await self.audit_logger.start_audit(
            sync_type='engagement',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Switch to workspace
            if not await self.client.switch_workspace(int(eb_workspace_id)):
                return await audit.fail(Exception(f"Failed to switch workspace {eb_workspace_id}"))

            # Get all connected inboxes with EB account IDs
            inboxes = await self.db.fetch("""
                SELECT id, emailbison_account_id, email_address
                FROM sender_accounts
                WHERE workspace_id = $1
                  AND emailbison_account_id IS NOT NULL
                  AND inbox_state = 'live'
                  AND status = 'Connected'
                  AND is_active = TRUE
            """, workspace_id)

            if not inboxes:
                return await audit.complete(metadata={'inboxes': 0})

            # Yesterday's date range for daily snapshot
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')

            print(f"  [Engagement] {workspace_name}: {len(inboxes)} inboxes, date={yesterday}")

            for inbox in inboxes:
                await audit.increment_processed()
                try:
                    eb_id = int(inbox['emailbison_account_id'])
                    stats = await self.client.get_campaign_event_stats(
                        start_date=yesterday,
                        end_date=yesterday,
                        sender_email_ids=[eb_id]
                    )

                    # Parse response into daily counts
                    day_data = self._parse_event_stats(stats, yesterday)

                    if day_data and any(v > 0 for v in day_data.values()):
                        # Upsert into snapshot table
                        await self.db.execute("""
                            INSERT INTO inbox_engagement_snapshots (
                                sender_account_id, workspace_id, snapshot_date,
                                opens, unique_opens, replies, interested,
                                sent, bounced, unsubscribed
                            ) VALUES ($1, $2, $3::date, $4, $5, $6, $7, $8, $9, $10)
                            ON CONFLICT (sender_account_id, snapshot_date) DO UPDATE SET
                                opens = EXCLUDED.opens,
                                unique_opens = EXCLUDED.unique_opens,
                                replies = EXCLUDED.replies,
                                interested = EXCLUDED.interested,
                                sent = EXCLUDED.sent,
                                bounced = EXCLUDED.bounced,
                                unsubscribed = EXCLUDED.unsubscribed
                        """,
                            inbox['id'], workspace_id, yesterday,
                            day_data.get('opens', 0),
                            day_data.get('unique_opens', 0),
                            day_data.get('replies', 0),
                            day_data.get('interested', 0),
                            day_data.get('sent', 0),
                            day_data.get('bounced', 0),
                            day_data.get('unsubscribed', 0)
                        )
                        await audit.increment_created()
                    else:
                        await audit.increment_updated()

                except EmailBisonAPIError as e:
                    await audit.add_error(
                        record_id=inbox['email_address'],
                        error=f"API error: {e}"
                    )
                except Exception as e:
                    await audit.add_error(
                        record_id=inbox['email_address'],
                        error=str(e)
                    )

            # Update 7-day windowed metrics from snapshot table
            await self._update_7d_metrics(workspace_id)

            # Rollup to domain level
            try:
                await self.db.execute(
                    "SELECT rollup_all_domain_engagement($1)", workspace_id
                )
            except Exception as e:
                print(f"  [Engagement] Domain rollup warning: {e}")

            return await audit.complete(metadata={
                'inboxes': len(inboxes),
                'date': yesterday
            })

        except Exception as e:
            return await audit.fail(e)

    def _parse_event_stats(self, stats: Dict, target_date: str) -> Dict:
        """
        Parse /api/campaign-events/stats response into a flat dict for one date.

        Response format:
        {"data": [
            {"label": "Replied", "dates": [["2026-03-15", 3], ...]},
            {"label": "Sent", "dates": [["2026-03-15", 50], ...]},
            ...
        ]}
        """
        result = {
            'opens': 0, 'unique_opens': 0, 'replies': 0,
            'interested': 0, 'sent': 0, 'bounced': 0, 'unsubscribed': 0,
        }

        if not stats or 'data' not in stats:
            return result

        for event_series in stats['data']:
            label = event_series.get('label', '')
            field_name = EVENT_LABEL_MAP.get(label)
            if not field_name:
                continue

            for date_entry in event_series.get('dates', []):
                if isinstance(date_entry, (list, tuple)) and len(date_entry) >= 2:
                    date_str, count = date_entry[0], date_entry[1]
                    if date_str == target_date:
                        result[field_name] = int(count or 0)

        return result

    async def _update_7d_metrics(self, workspace_id: UUID):
        """Derive 7-day windowed engagement metrics from snapshot table."""
        await self.db.execute("""
            UPDATE sender_accounts sa
            SET
                opens_7d = COALESCE(sub.opens, 0),
                unique_opens_7d = COALESCE(sub.unique_opens, 0),
                replies_7d = COALESCE(sub.replies, 0),
                interested_7d = COALESCE(sub.interested, 0),
                sent_7d = COALESCE(sub.sent, 0),
                unsubscribed_7d = COALESCE(sub.unsubscribed, 0),
                engagement_synced_at = NOW(),
                updated_at = NOW()
            FROM (
                SELECT
                    sender_account_id,
                    SUM(opens) AS opens,
                    SUM(unique_opens) AS unique_opens,
                    SUM(replies) AS replies,
                    SUM(interested) AS interested,
                    SUM(sent) AS sent,
                    SUM(unsubscribed) AS unsubscribed
                FROM inbox_engagement_snapshots
                WHERE workspace_id = $1
                  AND snapshot_date >= CURRENT_DATE - 7
                GROUP BY sender_account_id
            ) sub
            WHERE sa.id = sub.sender_account_id
        """, workspace_id)

    async def backfill_workspace(
        self,
        workspace_id: UUID,
        workspace_name: str,
        eb_workspace_id: int,
        days_back: int = 90
    ) -> int:
        """
        Backfill historical engagement snapshots for a workspace.
        Called by scripts/backfill_engagement_90d.py (one-time).

        Returns count of snapshots created.
        """
        if not await self.client.switch_workspace(int(eb_workspace_id)):
            print(f"  [Backfill] Failed to switch workspace {eb_workspace_id}")
            return 0

        inboxes = await self.db.fetch("""
            SELECT id, emailbison_account_id, email_address
            FROM sender_accounts
            WHERE workspace_id = $1
              AND emailbison_account_id IS NOT NULL
              AND is_active = TRUE
        """, workspace_id)

        if not inboxes:
            return 0

        start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%d')
        end_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
        total_created = 0

        print(f"  [Backfill] {workspace_name}: {len(inboxes)} inboxes, {start_date} to {end_date}")

        for i, inbox in enumerate(inboxes):
            try:
                eb_id = int(inbox['emailbison_account_id'])
                stats = await self.client.get_campaign_event_stats(
                    start_date=start_date,
                    end_date=end_date,
                    sender_email_ids=[eb_id]
                )

                # Parse all dates from response
                snapshots = self._parse_all_dates(stats)

                for date_str, day_data in snapshots.items():
                    if any(v > 0 for v in day_data.values()):
                        await self.db.execute("""
                            INSERT INTO inbox_engagement_snapshots (
                                sender_account_id, workspace_id, snapshot_date,
                                opens, unique_opens, replies, interested,
                                sent, bounced, unsubscribed
                            ) VALUES ($1, $2, $3::date, $4, $5, $6, $7, $8, $9, $10)
                            ON CONFLICT (sender_account_id, snapshot_date) DO UPDATE SET
                                opens = EXCLUDED.opens,
                                unique_opens = EXCLUDED.unique_opens,
                                replies = EXCLUDED.replies,
                                interested = EXCLUDED.interested,
                                sent = EXCLUDED.sent,
                                bounced = EXCLUDED.bounced,
                                unsubscribed = EXCLUDED.unsubscribed
                        """,
                            inbox['id'], workspace_id, date_str,
                            day_data.get('opens', 0),
                            day_data.get('unique_opens', 0),
                            day_data.get('replies', 0),
                            day_data.get('interested', 0),
                            day_data.get('sent', 0),
                            day_data.get('bounced', 0),
                            day_data.get('unsubscribed', 0)
                        )
                        total_created += 1

                if (i + 1) % 50 == 0:
                    print(f"    Progress: {i + 1}/{len(inboxes)} inboxes, {total_created} snapshots")

            except EmailBisonAPIError as e:
                print(f"    [WARN] {inbox['email_address']}: API error {e}")
            except Exception as e:
                print(f"    [WARN] {inbox['email_address']}: {e}")

        # Update 7d windowed metrics
        await self._update_7d_metrics(workspace_id)

        # Rollup to domains
        try:
            await self.db.execute(
                "SELECT rollup_all_domain_engagement($1)", workspace_id
            )
        except Exception as e:
            print(f"  [Backfill] Domain rollup warning: {e}")

        print(f"  [Backfill] {workspace_name}: {total_created} snapshots created")
        return total_created

    def _parse_all_dates(self, stats: Dict) -> Dict[str, Dict]:
        """
        Parse all dates from campaign-events/stats into {date: {field: count}} dict.

        Returns e.g.: {"2026-03-01": {"opens": 3, "replies": 1, ...}, ...}
        """
        result = {}

        if not stats or 'data' not in stats:
            return result

        for event_series in stats['data']:
            label = event_series.get('label', '')
            field_name = EVENT_LABEL_MAP.get(label)
            if not field_name:
                continue

            for date_entry in event_series.get('dates', []):
                if isinstance(date_entry, (list, tuple)) and len(date_entry) >= 2:
                    date_str, count = str(date_entry[0]), int(date_entry[1] or 0)
                    if date_str not in result:
                        result[date_str] = {
                            'opens': 0, 'unique_opens': 0, 'replies': 0,
                            'interested': 0, 'sent': 0, 'bounced': 0, 'unsubscribed': 0,
                        }
                    result[date_str][field_name] = count

        return result
