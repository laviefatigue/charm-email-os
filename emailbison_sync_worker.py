#!/usr/bin/env python3
"""
EmailBison Sync Worker

Concurrent, workspace-scoped sync system that keeps the local database fresh
with EmailBison data.

Architecture:
    Data-pull syncs (EB → DB) are managed by WorkspaceSyncQueue — a persistent
    PostgreSQL job queue that enables concurrent per-workspace processing.  Each
    workspace has a scoped API key (workspace_api_keys, migration 089) so all 5
    data-pull modules run without switch_workspace() calls and can run in parallel.

    Poll loop sleeps for POLL_INTERVAL_PRIORITY (30s).  On each tick:
      1. run_priority_sync() — claim any force-refresh (priority=10) jobs
      2. run_data_sync()     — schedule overdue workspaces, process concurrent batch
      3. Other non-data tasks on their own intervals (health checks, tagging, etc.)

Features:
- Accounts & domains        — hourly, concurrent per workspace
- Campaigns & snapshots     — hourly, concurrent per workspace
- Events (replies/bounces)  — every 5 min, concurrent per workspace
- Warmup tracking           — every 30 min, concurrent per workspace
- Engagement snapshots      — daily, concurrent per workspace
- Force-refresh (client UI) — picked up within ~30s via priority queue
- Health checks & kill triggers — every 15 min
- Kill queue processing     — every 30 min
- Lifecycle + Set tagging   — every 30 min (writes EB → DB, sequential)
- Workspace discovery       — daily (auto-import new EB workspaces)
- Data retention cleanup    — daily

Usage:
    python emailbison_sync_worker.py           # Run continuous polling
    python emailbison_sync_worker.py --once    # Force-refresh all + single pass
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
    WorkspaceSyncQueue,
    WorkspaceWriteOrchestrator,
    HealthCheckModule,
    KillProcessor,
    RetentionManager,
    OAuthSyncModule,
    DailySnapshotModule,
    LifecycleTagSyncModule,
    SetTagSyncModule,
    OnboardingMonitorModule,
    OverhaulAuditModule,
)

# Configuration from environment
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5433))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'localdevpassword')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'postgres')

# Sync intervals (seconds) — used by WorkspaceSyncQueue.schedule_overdue_syncs()
POLL_INTERVAL_EVENTS = int(os.getenv('SYNC_INTERVAL_EVENTS', 300))          # 5 min  (events)
POLL_INTERVAL_FULL = int(os.getenv('SYNC_INTERVAL_FULL', 3600))             # 1 hour (accounts, campaigns)
POLL_INTERVAL_HEALTH = int(os.getenv('SYNC_INTERVAL_HEALTH', 900))          # 15 min
POLL_INTERVAL_KILL = int(os.getenv('SYNC_INTERVAL_KILL', 900))              # 15 min — drives workspace_writes (lifecycle + threshold + set_tags + kill)
POLL_INTERVAL_WARMUP = int(os.getenv('SYNC_INTERVAL_WARMUP', 1800))         # 30 min (warmup)
POLL_INTERVAL_ENGAGEMENT = int(os.getenv('SYNC_INTERVAL_ENGAGEMENT', 86400))  # 24 hours (daily snapshots)
POLL_INTERVAL_OAUTH_QUEUE = int(os.getenv('SYNC_INTERVAL_OAUTH_QUEUE', 300))  # 5 min  (queue processing)
POLL_INTERVAL_OAUTH_VERIFY = int(os.getenv('SYNC_INTERVAL_OAUTH_VERIFY', 30 * 24 * 3600))  # 30 days
POLL_INTERVAL_WORKSPACE_DISCOVERY = int(os.getenv('SYNC_INTERVAL_WORKSPACE_DISCOVERY', 300))  # 5 min

# Concurrent workspace processing — how many workspaces run in parallel per batch
SYNC_WORKSPACE_CONCURRENCY = int(os.getenv('SYNC_WORKSPACE_CONCURRENCY', '3'))

# How often to poll for force-refresh (priority) jobs from the client dashboard
# This is the main poll loop sleep interval — all other schedules are managed by
# the queue's last_successful_sync checks, not by timer loops here.
POLL_INTERVAL_PRIORITY = int(os.getenv('SYNC_INTERVAL_PRIORITY', '30'))     # 30s priority poll

# Slack webhook for alerts
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')

# Domain Engine V2 Local Development Flags
# Set these to 'false' in local .env to disable EmailBison writes
ENABLE_KILL_PROCESSING = os.getenv('ENABLE_KILL_PROCESSING', 'true').lower() == 'true'
ENABLE_LIFECYCLE_TAGGING = os.getenv('ENABLE_LIFECYCLE_TAGGING', 'true').lower() == 'true'


class SyncOrchestrator:
    """Main orchestrator for EmailBison sync operations."""

    def __init__(self):
        self.db: Optional[asyncpg.Pool] = None
        self.alerter: Optional[SlackAlerter] = None
        self.audit_logger: Optional[AuditLogger] = None
        self.sync_queue: Optional[WorkspaceSyncQueue] = None
        self.running = True

        # Track last run times for non-queue-managed tasks
        # Data-pull syncs (accounts/campaigns/events/warmup/engagement) are managed
        # entirely by WorkspaceSyncQueue.schedule_overdue_syncs() — no last_*_sync
        # trackers needed here for those types.
        self.last_health_check: Optional[datetime] = None
        # last_workspace_writes drives lifecycle + set + kill in one orchestrated
        # pass per workspace (replaces last_kill_check + last_lifecycle_tag_sync).
        self.last_workspace_writes: Optional[datetime] = None
        self.last_retention_cleanup: Optional[datetime] = None
        self.last_daily_counter_reset: Optional[datetime] = None
        self.last_oauth_queue_check: Optional[datetime] = None
        self.last_oauth_verify: Optional[datetime] = None
        self.last_daily_snapshot: Optional[datetime] = None
        self.last_slack_audit: Optional[datetime] = None
        self.last_workspace_discovery: Optional[datetime] = None
        self.last_onboarding_monitor: Optional[datetime] = None
        self.last_overhaul_audit: Optional[datetime] = None
        # Inbox Audit Overhaul (Plan: docs/plans/inbox-audit-overhaul.md) —
        # per-workspace structured audit. Runs daily; persists to inbox_audits
        # table with workspace_id + inbox_id_set + audit_data populated.
        self.last_inbox_audit: Optional[datetime] = None

    async def start(self, single_pass: bool = False):
        """Initialize connections and start the sync worker."""
        print(f"[{datetime.now()}] EmailBison Sync Worker starting...")
        print(f"  Database: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
        print(f"  Slack alerts: {'Enabled' if SLACK_WEBHOOK_URL else 'Disabled'}")
        print(f"  Kill processing: {'Enabled' if ENABLE_KILL_PROCESSING else 'DISABLED'}")
        print(f"  Lifecycle tagging: {'Enabled' if ENABLE_LIFECYCLE_TAGGING else 'DISABLED'}")
        print(f"  Intervals: events={POLL_INTERVAL_EVENTS}s, full={POLL_INTERVAL_FULL}s, health={POLL_INTERVAL_HEALTH}s, kill={POLL_INTERVAL_KILL}s, warmup={POLL_INTERVAL_WARMUP}s, oauth_queue={POLL_INTERVAL_OAUTH_QUEUE}s")
        print(f"  Workspace concurrency: {SYNC_WORKSPACE_CONCURRENCY} parallel | Priority poll: {POLL_INTERVAL_PRIORITY}s")

        try:
            # Initialize database connection pool
            # max_size=20 supports SYNC_WORKSPACE_CONCURRENCY=3 workspaces × 5 sync types
            # with headroom for health checks, tagging, and admin queries.
            self.db = await asyncpg.create_pool(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                database=POSTGRES_DB,
                min_size=2,
                max_size=20
            )
            print("  Database pool created")

            # Initialize shared services
            self.alerter = SlackAlerter(SLACK_WEBHOOK_URL)
            self.audit_logger = AuditLogger(self.db)

            # Initialize workspace sync queue — manages concurrent per-workspace data pulls
            self.sync_queue = WorkspaceSyncQueue(
                db=self.db,
                audit_logger=self.audit_logger,
                alerter=self.alerter,
                concurrency=SYNC_WORKSPACE_CONCURRENCY,
            )
            # Warn about workspaces that don't have API keys yet (cannot be synced)
            await self.sync_queue.log_missing_keys()

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

                # ── Data-pull syncs (EB → DB) — managed by WorkspaceSyncQueue ──────────
                # Priority jobs first: force-refresh requests from the client dashboard.
                # These use priority=10 and are picked up every 30s (POLL_INTERVAL_PRIORITY).
                await self.run_priority_sync()

                # Scheduled sync: enqueue any overdue workspaces, then process a concurrent
                # batch (up to SYNC_WORKSPACE_CONCURRENCY workspaces at once).
                # schedule_overdue_syncs() is idempotent — safe to call every 30s.
                await self.run_data_sync()
                # ─────────────────────────────────────────────────────────────────────────

                # Health checks - every 15 min
                if self._should_run(self.last_health_check, POLL_INTERVAL_HEALTH):
                    await self.run_health_checks()
                    self.last_health_check = now

                # Workspace writes — lifecycle + set + kill, concurrent per workspace,
                # workspace-scoped API keys (migration 089). Replaces the previous
                # serial run_lifecycle_tag_sync + run_kill_processing path.
                if self._should_run(self.last_workspace_writes, POLL_INTERVAL_KILL):
                    await self.run_workspace_writes()
                    self.last_workspace_writes = now

                # Daily retention cleanup (run at midnight)
                if self._should_run_daily(self.last_retention_cleanup):
                    try:
                        await self.run_retention_cleanup()
                    except Exception as e:
                        print(f"[ERROR] Retention cleanup failed: {e}")
                    self.last_retention_cleanup = now

                # Daily 24h counter reset (CRITICAL: prevents false positives)
                if self._should_run_daily(self.last_daily_counter_reset):
                    try:
                        await self.run_daily_counter_reset()
                    except Exception as e:
                        print(f"[ERROR] Daily counter reset failed: {e}")
                    self.last_daily_counter_reset = now

                # Daily volume snapshot (for client dashboard capacity chart)
                if self._should_run_daily(self.last_daily_snapshot):
                    try:
                        await self.run_daily_snapshot()
                    except Exception as e:
                        print(f"[ERROR] Daily snapshot failed: {e}")
                    self.last_daily_snapshot = now

                # Slack audit at 6 AM and 1 PM Pacific (send audit summary to #inbox-audits)
                if self._should_run_slack_audit(self.last_slack_audit):
                    try:
                        await self.run_slack_audit()
                    except Exception as e:
                        print(f"[ERROR] Slack audit failed: {e}")
                    self.last_slack_audit = now

                # Workspace discovery — check every 5 min for new EB workspaces
                if self._should_run(self.last_workspace_discovery, POLL_INTERVAL_WORKSPACE_DISCOVERY):
                    try:
                        await self.run_workspace_discovery()
                    except Exception as e:
                        print(f"[ERROR] Workspace discovery failed: {e}")
                    self.last_workspace_discovery = now

                # Daily onboarding form monitor
                if self._should_run_daily(self.last_onboarding_monitor):
                    try:
                        await self.run_onboarding_monitor()
                    except Exception as e:
                        print(f"[ERROR] Onboarding monitor failed: {e}")
                    self.last_onboarding_monitor = now

                # Daily overhaul audit — surfaces dual-tag drift, silently
                # disabled warmup, and is_active=FALSE orphans (CEO ask:
                # "daily checks with notifications", 2026-04-27 plan).
                if self._should_run_daily(self.last_overhaul_audit):
                    try:
                        await self.run_overhaul_audit()
                    except Exception as e:
                        print(f"[ERROR] Overhaul audit failed: {e}")
                    self.last_overhaul_audit = now

                # Daily inbox audit (per-workspace) — Inbox Audit Overhaul.
                # Phase 2/3 of docs/plans/inbox-audit-overhaul.md. Runs the
                # InboxAuditor against each active workspace, persists the
                # structured audit row with workspace_id + inbox_id_set +
                # audit_data populated. Phase 5 (Slack restructure) and
                # Phase 6 (SLA enforcement) read from this table.
                if self._should_run_daily(self.last_inbox_audit):
                    try:
                        await self.run_inbox_audit()
                    except Exception as e:
                        print(f"[ERROR] Inbox audit failed: {e}")
                    self.last_inbox_audit = now

                # OAuth queue processing - every 5 min (for new workspaces)
                if self._should_run(self.last_oauth_queue_check, POLL_INTERVAL_OAUTH_QUEUE):
                    try:
                        await self.run_oauth_queue()
                    except Exception as e:
                        print(f"[ERROR] OAuth queue failed: {e}")
                    self.last_oauth_queue_check = now

                # OAuth monthly verification - every 30 days
                if self._should_run(self.last_oauth_verify, POLL_INTERVAL_OAUTH_VERIFY):
                    try:
                        await self.run_oauth_verification()
                    except Exception as e:
                        print(f"[ERROR] OAuth verification failed: {e}")
                    self.last_oauth_verify = now

                # Sleep for priority poll interval (30s).
                # All sync schedules are driven by the queue's schedule_overdue_syncs()
                # logic, not by this sleep interval — so 30s is fine.
                await asyncio.sleep(POLL_INTERVAL_PRIORITY)

            except asyncio.CancelledError:
                print("[INFO] Poll loop cancelled")
                break
            except Exception as e:
                print(f"[ERROR] Poll loop error: {e}")
                await asyncio.sleep(60)  # Back off on errors

        print(f"[{datetime.now()}] Poll loop stopped")

    async def run_single_pass(self):
        """Run all sync operations once and exit."""
        print(f"[{datetime.now()}] Running single pass (force-refresh all workspaces)...")

        # Force-refresh enqueues all 5 sync types at priority=10 for every workspace.
        # This is the equivalent of the old run_full_sync + run_events_sync + run_warmup_sync
        # + run_engagement_sync, but concurrent instead of sequential.
        workspaces = await self.db.fetch("""
            SELECT w.id FROM workspaces w
            JOIN workspace_api_keys k ON k.workspace_id = w.id AND k.is_active = TRUE
            WHERE w.is_active = TRUE
        """)
        for ws in workspaces:
            await self.sync_queue.request_force_refresh(ws['id'])

        # Process until queue drains (multiple passes since batch size = concurrency)
        for _ in range(len(workspaces) * 2 + 1):
            await self.sync_queue.process_pending_batch()

        await self.run_health_checks()
        await self.run_workspace_writes()

        print(f"[{datetime.now()}] Single pass complete")

    async def run_data_sync(self):
        """
        Schedule overdue workspace syncs and process the next concurrent batch.

        Two-phase operation:
        1. schedule_overdue_syncs(): for each active workspace with a valid API key,
           insert pending jobs for any sync type whose last_successful_sync is older
           than its configured interval.  Uses ON CONFLICT DO NOTHING — safe to call
           every 30s (POLL_INTERVAL_PRIORITY).
        2. process_pending_batch(): claim up to SYNC_WORKSPACE_CONCURRENCY jobs via
           FOR UPDATE SKIP LOCKED and run them concurrently with asyncio.gather.

        Sync intervals per type:
          accounts   — POLL_INTERVAL_FULL       (1 hour)
          campaigns  — POLL_INTERVAL_FULL       (1 hour)
          events     — POLL_INTERVAL_EVENTS     (5 min)
          warmup     — POLL_INTERVAL_WARMUP     (30 min)
          engagement — POLL_INTERVAL_ENGAGEMENT (24 hours)
        """
        await self.sync_queue.schedule_overdue_syncs({
            'accounts':   POLL_INTERVAL_FULL,
            'campaigns':  POLL_INTERVAL_FULL,
            'events':     POLL_INTERVAL_EVENTS,
            'warmup':     POLL_INTERVAL_WARMUP,
            'engagement': POLL_INTERVAL_ENGAGEMENT,
        })
        await self.sync_queue.process_pending_batch()

    async def run_priority_sync(self):
        """
        Process force-refresh (priority=10) jobs without waiting for the normal batch.

        Called every POLL_INTERVAL_PRIORITY (30s) so client dashboard refresh
        requests are picked up within ~30s of submission.

        Force-refresh jobs are inserted by POST /api/sync/workspaces/{id}/refresh
        (via WorkspaceSyncQueue.request_force_refresh).
        """
        await self.sync_queue.process_priority_batch()

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

    async def run_workspace_writes(self):
        """
        Orchestrated DB→EB writes per workspace.

        Replaces the legacy run_lifecycle_tag_sync + run_kill_processing pair.
        Each workspace runs lifecycle → set tags → kill processing in order,
        through a workspace-scoped EmailBisonClient (migration 089) — no
        switch_workspace() calls, safe concurrency across workspaces.

        Honors the same feature flags as before:
        - ENABLE_LIFECYCLE_TAGGING gates lifecycle + set tagging
        - ENABLE_KILL_PROCESSING gates kill queue processing

        When both are disabled the orchestrator is skipped entirely.
        """
        if not ENABLE_LIFECYCLE_TAGGING and not ENABLE_KILL_PROCESSING:
            print(f"[{datetime.now()}] Workspace writes DISABLED (lifecycle + kill both off)")
            return

        if not ENABLE_LIFECYCLE_TAGGING:
            print(f"[{datetime.now()}] Lifecycle tagging DISABLED — kill processing only")
        if not ENABLE_KILL_PROCESSING:
            print(f"[{datetime.now()}] Kill processing DISABLED — tagging only")

        print(f"[{datetime.now()}] Workspace writes (lifecycle + set + kill, concurrent={SYNC_WORKSPACE_CONCURRENCY})...")

        orchestrator = WorkspaceWriteOrchestrator(
            db=self.db,
            audit_logger=self.audit_logger,
            alerter=self.alerter,
            concurrency=SYNC_WORKSPACE_CONCURRENCY,
            enable_lifecycle_tagging=ENABLE_LIFECYCLE_TAGGING,
            enable_kill_processing=ENABLE_KILL_PROCESSING,
        )
        results = await orchestrator.run()

        # Roll up per-phase metadata across workspaces for a one-line status print.
        graduated = sum(r.metadata.get('graduated', 0) for r in results if r.metadata)
        new_incubating = sum(r.metadata.get('new_incubating', 0) for r in results if r.metadata)
        dead_cleaned = sum(r.metadata.get('live_removed_dead', 0) for r in results if r.metadata)
        a_tagged = sum(r.metadata.get('tagged_a_set', 0) for r in results if r.metadata)
        b_tagged = sum(r.metadata.get('tagged_b_set', 0) for r in results if r.metadata)
        promoted = sum(r.metadata.get('promoted_to_a_set', 0) for r in results if r.metadata)
        kills_tagged = sum(r.metadata.get('tagged_count', 0) for r in results if r.metadata)
        failed = sum(1 for r in results if not r.success)

        status = 'FAILED' if failed > 0 else 'OK'
        print(
            f"  Writes: graduated={graduated}, new_incubating={new_incubating}, "
            f"dead_cleaned={dead_cleaned}, +A={a_tagged}, +B={b_tagged}, "
            f"promoted={promoted}, kills_flagged={kills_tagged} [{status}]"
        )

    async def run_inbox_audit(self):
        """Per-workspace structured inbox audit — Inbox Audit Overhaul Phase 2/3.

        Runs InboxAuditor.audit_workspace() against every active workspace,
        persists each as a row in inbox_audits with workspace_id, inbox_id_set,
        and audit_data JSONB populated. Idempotent per workspace+date.

        Plan: docs/plans/inbox-audit-overhaul.md
        Tracker: docs/plans/INBOX-INTEGRITY-PROGRAM.md §3.7
        """
        from sync_modules.inbox_auditor import InboxAuditor

        print(f"[{datetime.now()}] Inbox audit (per-workspace)...")

        # Pull all active workspaces.
        workspaces = await self.db.fetch(
            "SELECT id, workspace_name FROM workspaces WHERE is_active = TRUE ORDER BY workspace_name"
        )

        auditor = InboxAuditor(self.db)
        succeeded = 0
        failed = 0

        for ws in workspaces:
            try:
                result = await auditor.audit_workspace(ws['id'])
                audit_id = await auditor.persist(result)
                # Surface critical/warn findings to the worker log so they
                # appear in Coolify's container output. Phase 5 will route
                # the same data through Slack with per-workspace formatting.
                critical = sum(1 for s in result.sections if s.severity == 'critical' and s.count > 0)
                warn = sum(1 for s in result.sections if s.severity == 'warn' and s.count > 0)
                marker = '🔴' if critical else ('🟡' if warn else '🟢')
                print(
                    f"  {marker} [{ws['workspace_name']}] audit_id={audit_id} "
                    f"inboxes={len(result.inbox_id_set)} "
                    f"critical={critical} warn={warn}"
                )
                succeeded += 1
            except Exception as e:
                print(f"  [ERROR] [{ws['workspace_name']}] audit failed: {e!r}")
                failed += 1

        print(f"  Inbox audit: {succeeded} of {len(workspaces)} succeeded ({failed} failed)")

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
        await health_module.decay_weekly_counters()

        print(f"  24h counters reset, 7d counters decayed for all active inboxes")

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

    async def run_slack_audit(self):
        """Send daily inbox audit summary to Slack #inbox-audits channel.

        Includes:
        - Kill trigger summary (last 24h)
        - Disconnected inbox count
        - Download buttons for CSVs
        - Confirm/Issues buttons for team review
        """
        from sync_modules.slack_audit import send_daily_audit, SLACK_WEBHOOK_URL

        if not SLACK_WEBHOOK_URL:
            print(f"[{datetime.now()}] Slack audit skipped (SLACK_AUDIT_WEBHOOK_URL not configured)")
            return

        print(f"[{datetime.now()}] Sending daily Slack audit...")

        result = await send_daily_audit()

        if result.get("success"):
            stats = result.get("stats", {})
            print(
                f"  Audit sent: {stats.get('total_kills', 0)} kills | "
                f"{stats.get('new_disconnected', 0)} new disconnected | "
                f"audit_id={result.get('audit_id')}"
            )
        else:
            print(f"  Audit failed: {result.get('error')}")

    async def run_overhaul_audit(self):
        """Daily reconciliation audit for the 2026-04-27 tagging-kill model.

        Read-only — counts the three drift signals (dual-tag candidates,
        silently-disabled warmup, orphan is_active=FALSE inboxes) and
        posts a single Slack message if any are non-zero.
        """
        print(f"[{datetime.now()}] Overhaul audit (daily reconciliation)...")
        audit = OverhaulAuditModule(
            db=self.db,
            audit_logger=self.audit_logger,
            alerter=self.alerter,
        )
        await audit.run()

    async def run_onboarding_monitor(self):
        """Check for new onboarding form submissions and stale clients."""
        print(f"[{datetime.now()}] Onboarding form monitor...")
        try:
            monitor = OnboardingMonitorModule(
                db=self.db,
                alerter=self.alerter,
                audit_logger=self.audit_logger
            )
            results = await monitor.run()
            processed = results.get("submissions", {}).get("processed", 0)
            reminded = results.get("stale", {}).get("reminded", 0)
            errors = results.get("submissions", {}).get("errors", 0)
            print(f"  Onboarding: {processed} processed, {reminded} reminders, {errors} errors")
        except Exception as e:
            print(f"[ERROR] Onboarding monitor failed: {e}")
            if self.alerter:
                await self.alerter.send_alert(
                    level="error",
                    title="Onboarding Monitor Failed",
                    message=str(e)
                )

    async def _create_workspace_api_key(
        self,
        http_client,
        workspace_id,
        eb_workspace_id: int,
        workspace_name: str,
        api_url: str,
        api_key: str,
    ) -> str:
        """Generate a workspace-scoped EB API key and store it in workspace_api_keys.

        The key is for client-facing dashboards to query EmailBison data scoped
        to a single workspace. It is stored in a dedicated table and never returned
        in general workspace API responses.
        """
        key_name = f"{workspace_name} dashboard key"
        response = await http_client.post(
            f"{api_url}/api/workspaces/v1.1/{eb_workspace_id}/api-tokens",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={"name": key_name},
            timeout=30.0,
        )

        if response.status_code not in (200, 201):
            raise Exception(f"EB API returned {response.status_code}: {response.text[:200]}")

        resp = response.json()
        # EB API wraps response under "data" key; token is plain_text_token
        data = resp.get("data", resp)
        token = (
            data.get("plain_text_token")
            or data.get("token")
            or data.get("key")
        )
        if not token:
            raise Exception(f"EB API returned no token value: {list(data.keys())}")

        await self.db.execute("""
            INSERT INTO workspace_api_keys
                (workspace_id, emailbison_workspace_id, key_name, key_token)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (workspace_id) DO UPDATE SET
                key_token = EXCLUDED.key_token,
                key_name = EXCLUDED.key_name,
                updated_at = NOW(),
                is_active = TRUE
        """, workspace_id, eb_workspace_id, key_name, token)

        return token

    async def run_workspace_discovery(self):
        """Discover new EmailBison workspaces and create local records.

        When we get added to a new EmailBison workspace externally,
        this creates the corresponding local workspace + client records,
        queues OAuth sync, and immediately backfills all account/domain data.
        """
        import httpx

        EMAILBISON_API_URL = os.getenv('EMAILBISON_API_URL', 'https://spellcast.hirecharm.com')
        EMAILBISON_API_KEY = os.getenv('EMAILBISON_API_KEY', '')

        if not EMAILBISON_API_KEY:
            print(f"[{datetime.now()}] Workspace discovery skipped (EMAILBISON_API_KEY not configured)")
            return

        print(f"[{datetime.now()}] Workspace discovery...")

        try:
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                # Fetch all workspaces from EmailBison
                response = await http_client.get(
                    f"{EMAILBISON_API_URL}/api/workspaces/v1.1",
                    headers={
                        "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                        "Accept": "application/json",
                    },
                )

                if response.status_code != 200:
                    print(f"  Discovery failed: EmailBison API {response.status_code}")
                    return

                data = response.json()
                eb_workspaces = data if isinstance(data, list) else data.get('data', [])

                # Get existing local workspace EmailBison IDs
                existing_rows = await self.db.fetch(
                    "SELECT emailbison_workspace_id FROM workspaces WHERE emailbison_workspace_id IS NOT NULL"
                )
                existing_eb_ids = {str(row['emailbison_workspace_id']) for row in existing_rows}

                # Find new workspaces
                new_workspaces = [
                    ws for ws in eb_workspaces
                    if str(ws.get('id')) not in existing_eb_ids
                ]

                if not new_workspaces:
                    print(f"  No new workspaces found ({len(eb_workspaces)} total in EmailBison)")
                    return

                print(f"  Found {len(new_workspaces)} new workspaces to import")

                # Track newly created workspaces for immediate backfill
                created_workspaces = []

                for eb_workspace in new_workspaces:
                    eb_id = eb_workspace.get('id')
                    eb_name = eb_workspace.get('name', f'Workspace {eb_id}')

                    try:
                        # Create local workspace record
                        # Set is_active=TRUE so sync immediately picks up this workspace
                        # instance_id is required NOT NULL - use the shared instance
                        instance_id = await self.db.fetchval(
                            "SELECT instance_id FROM workspaces WHERE instance_id IS NOT NULL LIMIT 1"
                        )
                        workspace_row = await self.db.fetchrow("""
                            INSERT INTO workspaces (workspace_name, emailbison_workspace_id, instance_id, automation_enabled, is_active, a_set_tag_name, b_set_tag_name)
                            VALUES ($1, $2, $3, TRUE, TRUE, 'live', 'reserve')
                            RETURNING id
                        """, eb_name, str(eb_id), instance_id)

                        if not workspace_row:
                            continue

                        workspace_id = workspace_row['id']

                        # Create client record linked to workspace
                        await self.db.execute("""
                            INSERT INTO clients (name, workspace_id, onboarding_complete)
                            VALUES ($1, $2, FALSE)
                        """, eb_name, workspace_id)

                        # Queue OAuth config discovery
                        await self.db.execute("""
                            INSERT INTO oauth_sync_queue (workspace_id, emailbison_workspace_id)
                            VALUES ($1, $2)
                            ON CONFLICT (workspace_id) DO NOTHING
                        """, workspace_id, eb_id)

                        # Generate workspace-scoped API key for client dashboard access
                        try:
                            await self._create_workspace_api_key(
                                http_client=http_client,
                                workspace_id=workspace_id,
                                eb_workspace_id=eb_id,
                                workspace_name=eb_name,
                                api_url=EMAILBISON_API_URL,
                                api_key=EMAILBISON_API_KEY,
                            )
                            print(f"    API key generated for {eb_name}")
                        except Exception as key_err:
                            print(f"    WARNING: API key generation failed for {eb_name}: {key_err}")

                        created_workspaces.append({
                            'id': workspace_id,
                            'name': eb_name,
                            'eb_id': eb_id
                        })
                        print(f"    Created: {eb_name} (EmailBison ID: {eb_id})")

                        # Alert on new workspace
                        if self.alerter:
                            await self.alerter.send_alert(
                                level='info',
                                title=f'New Workspace Discovered: {eb_name}',
                                message=f"EmailBison ID: {eb_id}\nStarting immediate data backfill..."
                            )

                    except Exception as e:
                        print(f"    Error creating {eb_name}: {e}")

                # Immediate backfill: enqueue force-refresh for all new workspaces.
                # The workspace API key was just created in _create_workspace_api_key(),
                # so schedule_overdue_syncs() will see it on the next pass.  Submitting
                # force-refresh (priority=10) ensures the new workspace is processed within
                # POLL_INTERVAL_PRIORITY (30s) without waiting for the normal schedule.
                if created_workspaces:
                    print(f"  Queueing force-refresh for {len(created_workspaces)} new workspaces...")

                    for ws in created_workspaces:
                        try:
                            queued = await self.sync_queue.request_force_refresh(ws['id'])
                            print(f"    Sync queued for {ws['name']}: {queued}")
                        except Exception as e:
                            print(f"    Queue error for {ws['name']}: {e}")

                print(f"  Discovery complete: {len(created_workspaces)} workspaces created and backfilled")

        except Exception as e:
            print(f"  Workspace discovery error: {e}")

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

    def _should_run_slack_audit(self, last_run: Optional[datetime]) -> bool:
        """Check if we should run Slack audit (6 AM and 1 PM Pacific daily)."""
        from datetime import timezone
        from zoneinfo import ZoneInfo

        # Get current time in Pacific timezone
        pacific = ZoneInfo("America/Los_Angeles")
        now_pacific = datetime.now(pacific)

        # Run at 6 AM and 1 PM Pacific (within 5 min window)
        audit_hours = [6, 13]  # 6 AM and 1 PM
        if now_pacific.hour not in audit_hours or now_pacific.minute >= 5:
            return False

        # Check if already ran in this time slot
        if last_run is None:
            return True

        # Convert last_run to Pacific for comparison
        if last_run.tzinfo is None:
            last_run_pacific = last_run.replace(tzinfo=timezone.utc).astimezone(pacific)
        else:
            last_run_pacific = last_run.astimezone(pacific)

        # Don't run if we already ran in the same hour slot today
        if last_run_pacific.date() == now_pacific.date() and last_run_pacific.hour == now_pacific.hour:
            return False

        return True

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
