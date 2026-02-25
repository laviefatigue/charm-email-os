#!/usr/bin/env python3
"""
EmailBison Daily Sync Worker

Modular sync system for keeping local database fresh with EmailBison data.
Features:
- Account & domain synchronization (hourly)
- Campaign metrics snapshots (hourly)
- Event & response message sync (every 5 min)
- Health checks and kill trigger detection (every 15 min)
- Kill queue processing with 24hr tagging (every 30 min)
- Data retention cleanup (daily)

Usage:
    python emailbison_sync_worker.py           # Run continuous polling
    python emailbison_sync_worker.py --once    # Run single pass and exit
"""
import argparse
import asyncio
import os
import signal
import sys
from datetime import datetime, timedelta, time as dtime
from typing import Optional
import asyncpg

from sync_modules import (
    EmailBisonClient,
    AuditLogger,
    SlackAlerter,
    AccountSyncModule,
    CampaignSyncModule,
    EventSyncModule,
    WarmupSyncModule,
    HealthCheckModule,
    KillProcessor,
    RetentionManager,
    OAuthSyncModule,
    DailySnapshotModule,
)

# Configuration from environment
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5433))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'localdevpassword')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'postgres')

# Sync intervals (seconds)
POLL_INTERVAL_EVENTS = int(os.getenv('SYNC_INTERVAL_EVENTS', 300))      # 5 min
POLL_INTERVAL_FULL = int(os.getenv('SYNC_INTERVAL_FULL', 3600))         # 1 hour
POLL_INTERVAL_HEALTH = int(os.getenv('SYNC_INTERVAL_HEALTH', 900))      # 15 min
POLL_INTERVAL_KILL = int(os.getenv('SYNC_INTERVAL_KILL', 1800))         # 30 min
POLL_INTERVAL_WARMUP = int(os.getenv('SYNC_INTERVAL_WARMUP', 1800))     # 30 min (warmup tracking)
POLL_INTERVAL_OAUTH_QUEUE = int(os.getenv('SYNC_INTERVAL_OAUTH_QUEUE', 300))  # 5 min (queue processing)
POLL_INTERVAL_OAUTH_VERIFY = int(os.getenv('SYNC_INTERVAL_OAUTH_VERIFY', 30 * 24 * 3600))  # 30 days (verification)

# Slack webhook for alerts
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')


class SyncOrchestrator:
    """Main orchestrator for EmailBison sync operations."""

    def __init__(self):
        self.db: Optional[asyncpg.Pool] = None
        self.client: Optional[EmailBisonClient] = None
        self.alerter: Optional[SlackAlerter] = None
        self.audit_logger: Optional[AuditLogger] = None
        self.running = True

        # Track last run times
        self.last_full_sync: Optional[datetime] = None
        self.last_health_check: Optional[datetime] = None
        self.last_kill_check: Optional[datetime] = None
        self.last_warmup_sync: Optional[datetime] = None
        self.last_retention_cleanup: Optional[datetime] = None
        self.last_daily_counter_reset: Optional[datetime] = None
        self.last_oauth_queue_check: Optional[datetime] = None
        self.last_oauth_verify: Optional[datetime] = None
        self.last_daily_snapshot: Optional[datetime] = None

    async def start(self, single_pass: bool = False):
        """Initialize connections and start the sync worker."""
        print(f"[{datetime.now()}] EmailBison Sync Worker starting...")
        print(f"  Database: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
        print(f"  Slack alerts: {'Enabled' if SLACK_WEBHOOK_URL else 'Disabled'}")
        print(f"  Intervals: events={POLL_INTERVAL_EVENTS}s, full={POLL_INTERVAL_FULL}s, health={POLL_INTERVAL_HEALTH}s, kill={POLL_INTERVAL_KILL}s, warmup={POLL_INTERVAL_WARMUP}s, oauth_queue={POLL_INTERVAL_OAUTH_QUEUE}s")

        try:
            # Initialize database connection pool
            self.db = await asyncpg.create_pool(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                database=POSTGRES_DB,
                min_size=2,
                max_size=10
            )
            print("  Database pool created")

            # Initialize shared services
            self.alerter = SlackAlerter(SLACK_WEBHOOK_URL)
            self.audit_logger = AuditLogger(self.db)

            # Test database connection
            async with self.db.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                print(f"  Connected to: {version[:50]}...")

            print(f"[{datetime.now()}] Worker initialized successfully")

            if single_pass:
                await self.run_single_pass()
            else:
                await self.poll_loop()

        except Exception as e:
            print(f"[FATAL] Worker startup failed: {e}")
            if self.alerter:
                await self.alerter.alert_sync_failure(
                    module='startup',
                    error=str(e)
                )
            raise

        finally:
            if self.db:
                await self.db.close()

    async def poll_loop(self):
        """Main polling loop with staggered sync schedules."""
        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_shutdown)

        print(f"[{datetime.now()}] Starting poll loop...")

        while self.running:
            try:
                now = datetime.now()

                # Events sync (highest priority, most frequent)
                await self.run_events_sync()

                # Full sync (accounts, campaigns) - hourly
                if self._should_run(self.last_full_sync, POLL_INTERVAL_FULL):
                    await self.run_full_sync()
                    self.last_full_sync = now

                # Health checks - every 15 min
                if self._should_run(self.last_health_check, POLL_INTERVAL_HEALTH):
                    await self.run_health_checks()
                    self.last_health_check = now

                # Kill queue processing - every 30 min
                if self._should_run(self.last_kill_check, POLL_INTERVAL_KILL):
                    await self.run_kill_processing()
                    self.last_kill_check = now

                # Warmup sync - every 30 min
                if self._should_run(self.last_warmup_sync, POLL_INTERVAL_WARMUP):
                    await self.run_warmup_sync()
                    self.last_warmup_sync = now

                # Daily retention cleanup (run at midnight)
                if self._should_run_daily(self.last_retention_cleanup):
                    await self.run_retention_cleanup()
                    self.last_retention_cleanup = now

                # Daily 24h counter reset (CRITICAL: prevents false positives)
                if self._should_run_daily(self.last_daily_counter_reset):
                    await self.run_daily_counter_reset()
                    self.last_daily_counter_reset = now

                # Daily volume snapshot (for client dashboard capacity chart)
                if self._should_run_daily(self.last_daily_snapshot):
                    await self.run_daily_snapshot()
                    self.last_daily_snapshot = now

                # OAuth queue processing - every 5 min (for new workspaces)
                if self._should_run(self.last_oauth_queue_check, POLL_INTERVAL_OAUTH_QUEUE):
                    await self.run_oauth_queue()
                    self.last_oauth_queue_check = now

                # OAuth monthly verification - every 30 days
                if self._should_run(self.last_oauth_verify, POLL_INTERVAL_OAUTH_VERIFY):
                    await self.run_oauth_verification()
                    self.last_oauth_verify = now

                # Sleep until next poll interval
                await asyncio.sleep(POLL_INTERVAL_EVENTS)

            except asyncio.CancelledError:
                print("[INFO] Poll loop cancelled")
                break
            except Exception as e:
                print(f"[ERROR] Poll loop error: {e}")
                await asyncio.sleep(60)  # Back off on errors

        print(f"[{datetime.now()}] Poll loop stopped")

    async def run_single_pass(self):
        """Run all sync operations once and exit."""
        print(f"[{datetime.now()}] Running single pass...")

        await self.run_full_sync()
        await self.run_events_sync()
        await self.run_warmup_sync()
        await self.run_health_checks()
        await self.run_kill_processing()

        print(f"[{datetime.now()}] Single pass complete")

    async def run_full_sync(self):
        """Run full account and campaign sync."""
        print(f"\n[{datetime.now()}] === FULL SYNC ===")

        async with EmailBisonClient() as client:
            # Sync accounts
            account_sync = AccountSyncModule(
                db=self.db,
                client=client,
                audit_logger=self.audit_logger,
                alerter=self.alerter
            )
            account_results = await account_sync.sync_all_workspaces()
            self._print_results('Accounts', account_results)

            # Sync campaigns
            campaign_sync = CampaignSyncModule(
                db=self.db,
                client=client,
                audit_logger=self.audit_logger,
                alerter=self.alerter
            )
            campaign_results = await campaign_sync.sync_all_workspaces()
            self._print_results('Campaigns', campaign_results)

    async def run_events_sync(self):
        """Run event/response message sync."""
        print(f"[{datetime.now()}] Events sync...")

        async with EmailBisonClient() as client:
            event_sync = EventSyncModule(
                db=self.db,
                client=client,
                audit_logger=self.audit_logger,
                alerter=self.alerter
            )
            result = await event_sync.sync_all_active_campaigns()

            if result.records_processed > 0 or not result.success:
                status = 'OK' if result.success else 'FAILED'
                print(f"  Events: {result.records_processed} campaigns, {result.records_updated} with new events [{status}]")

    async def run_health_checks(self):
        """Run health checks and kill trigger detection."""
        print(f"[{datetime.now()}] Health checks...")

        health_module = HealthCheckModule(
            db=self.db,
            audit_logger=self.audit_logger,
            alerter=self.alerter
        )
        result = await health_module.run_all_checks()

        status = 'OK' if result.success else 'FAILED'
        print(f"  Health: {result.records_processed} workspaces, {result.records_updated} with triggers [{status}]")

    async def run_kill_processing(self):
        """Process the kill queue (tag and flag inboxes as inactive - NO DELETION)."""
        print(f"[{datetime.now()}] Kill queue processing...")

        async with EmailBisonClient() as client:
            kill_processor = KillProcessor(
                db=self.db,
                client=client,
                audit_logger=self.audit_logger,
                alerter=self.alerter
            )
            result = await kill_processor.process_queue()

            if result.records_processed > 0:
                status = 'OK' if result.success else 'FAILED'
                print(f"  Kill Queue: {result.records_processed} processed [{status}]")

    async def run_warmup_sync(self):
        """Sync warmup status and auto-enable warmup for connected inboxes.

        Per user requirement: "We should always try to keep connected inboxes in warming."
        """
        print(f"[{datetime.now()}] Warmup sync...")

        async with EmailBisonClient() as client:
            warmup_sync = WarmupSyncModule(
                db=self.db,
                client=client,
                audit_logger=self.audit_logger,
                alerter=self.alerter
            )

            # Sync warmup stats from EmailBison
            results = await warmup_sync.sync_all_workspaces()
            self._print_results('Warmup', results)

            # Auto-enable warmup for connected inboxes without it
            workspaces = await self.db.fetch("""
                SELECT id, workspace_name
                FROM workspaces
                WHERE emailbison_workspace_id IS NOT NULL
                AND is_active = TRUE
            """)

            total_auto_enabled = 0
            for ws in workspaces:
                try:
                    enabled = await warmup_sync.auto_enable_warmup_for_connected(ws['id'])
                    total_auto_enabled += enabled
                except Exception as e:
                    print(f"  [WARN] Auto-enable warmup failed for {ws['workspace_name']}: {e}")

            if total_auto_enabled > 0:
                print(f"  Auto-enabled warmup for {total_auto_enabled} connected inboxes")

    async def run_retention_cleanup(self):
        """Run data retention cleanup."""
        print(f"[{datetime.now()}] Retention cleanup...")

        retention_manager = RetentionManager(
            db=self.db,
            audit_logger=self.audit_logger
        )
        result = await retention_manager.run_cleanup()

        if result.records_processed > 0:
            print(f"  Retention: {result.records_processed} records cleaned up")

    async def run_daily_counter_reset(self):
        """Reset 24h bounce counters at midnight.

        CRITICAL: This prevents false positives in kill triggers.
        Without this reset, hard_bounces_24h accumulates forever,
        causing legitimate inboxes to trigger the ≥2 threshold.
        """
        print(f"[{datetime.now()}] Daily counter reset...")

        health_module = HealthCheckModule(
            db=self.db,
            audit_logger=self.audit_logger,
            alerter=self.alerter
        )
        await health_module.reset_daily_counters()

        print(f"  24h counters reset for all active inboxes")

    async def run_daily_snapshot(self):
        """Create daily volume snapshots for client dashboard capacity chart.

        Captures yesterday's metrics:
        - Emails sent
        - Capacity available
        - Live/incubating/dead inbox counts
        - Capacity utilization percentage
        - Kill events for chart annotations
        """
        print(f"[{datetime.now()}] Daily volume snapshot...")

        async with EmailBisonClient() as client:
            snapshot_module = DailySnapshotModule(
                db=self.db,
                client=client,
                alerter=self.alerter,
                audit_logger=self.audit_logger
            )
            result = await snapshot_module.snapshot_all_workspaces()

            print(
                f"  Snapshot: {result['workspaces_processed']} workspaces | "
                f"Total capacity: {result['total_capacity']:,} | "
                f"Kills: {result['total_kills']}"
            )

    async def run_oauth_queue(self):
        """Process OAuth sync queue (newly created workspaces)."""
        oauth_module = OAuthSyncModule(
            db=self.db,
            audit_logger=self.audit_logger,
            alerter=self.alerter
        )
        results = await oauth_module.process_queue()

        if results:
            total_processed = sum(r.records_processed for r in results)
            failed_count = sum(1 for r in results if not r.success)
            if total_processed > 0:
                status = 'FAILED' if failed_count > 0 else 'OK'
                print(f"[{datetime.now()}] OAuth Queue: {len(results)} workspaces processed [{status}]")

    async def run_oauth_verification(self):
        """Run monthly OAuth config verification."""
        print(f"[{datetime.now()}] OAuth verification...")

        oauth_module = OAuthSyncModule(
            db=self.db,
            audit_logger=self.audit_logger,
            alerter=self.alerter
        )
        results = await oauth_module.verify_existing_configs()

        if results:
            total_verified = sum(r.records_processed for r in results)
            changes_detected = sum(1 for r in results if r.metadata and r.metadata.get('changed'))
            status = 'CHANGES DETECTED' if changes_detected > 0 else 'OK'
            print(f"  OAuth: {total_verified} configs verified [{status}]")

    def _should_run(self, last_run: Optional[datetime], interval: int) -> bool:
        """Check if enough time has passed since last run."""
        if last_run is None:
            return True
        return (datetime.now() - last_run).total_seconds() >= interval

    def _should_run_daily(self, last_run: Optional[datetime]) -> bool:
        """Check if we should run daily cleanup (around midnight)."""
        if last_run is None:
            return True
        now = datetime.now()
        # Run if last run was before today
        return last_run.date() < now.date()

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print(f"\n[{datetime.now()}] Received shutdown signal, stopping...")
        self.running = False

    def _print_results(self, module: str, results: list):
        """Print summary of sync results."""
        total_processed = sum(r.records_processed for r in results)
        total_created = sum(r.records_created for r in results)
        total_updated = sum(r.records_updated for r in results)
        total_failed = sum(r.records_failed for r in results)
        failed_count = sum(1 for r in results if not r.success)

        status = 'FAILED' if failed_count > 0 else 'OK'
        print(f"  {module}: {total_processed} processed, {total_created} created, {total_updated} updated, {total_failed} failed [{status}]")


async def main():
    parser = argparse.ArgumentParser(description='EmailBison Daily Sync Worker')
    parser.add_argument('--once', action='store_true', help='Run single pass and exit')
    args = parser.parse_args()

    orchestrator = SyncOrchestrator()
    await orchestrator.start(single_pass=args.once)


if __name__ == '__main__':
    asyncio.run(main())
