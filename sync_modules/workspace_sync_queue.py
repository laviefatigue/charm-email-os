"""
Workspace Sync Queue

Concurrent, workspace-scoped job queue for EmailBison data sync.

Architecture overview
─────────────────────
Old model (sequential):
    One shared EmailBisonClient  →  switch_workspace(A)  →  sync A
                                 →  switch_workspace(B)  →  sync B
                                 →  ...
    Total wall time = sum(all workspace sync times)

New model (concurrent):
    Each workspace gets its own EmailBisonClient(api_key=<workspace_scoped_key>).
    Workspace-scoped tokens are context-bound — no switch_workspace() needed.
    Jobs are processed in batches of `concurrency` (default 3) via asyncio.gather.
    Total wall time ≈ max(single workspace sync time) × ⌈N_workspaces / concurrency⌉

Job lifecycle
─────────────
    schedule_overdue_syncs()  →  INSERT pending jobs (ON CONFLICT DO NOTHING)
    process_pending_batch()   →  FOR UPDATE SKIP LOCKED to claim N jobs
                              →  asyncio.gather(*[_run_job(j) for j in claimed])
    _run_job()                →  load workspace key → build client → dispatch → mark result
    On complete:              →  UPDATE status='complete', update sync_status
    On failure:               →  UPDATE status='failed', log error_message

Retry strategy
──────────────
Failed jobs are NOT explicitly retried. The scheduler re-queues any workspace
where sync_status.last_successful_sync is older than the interval, so a failed
workspace naturally re-enters the queue on the next scheduler tick.

Force-refresh
─────────────
POST /api/sync/workspaces/{id}/refresh enqueues all sync types with priority=10.
A dedicated 30-second poll loop in the worker picks up priority > 5 jobs first,
giving force-refresh a ~30s max latency vs the normal 5-minute events cycle.

Key invariants
──────────────
- UNIQUE INDEX on (workspace_id, sync_type) WHERE status='pending' prevents
  duplicate pending jobs.  insert must use ON CONFLICT DO NOTHING.
- FOR UPDATE SKIP LOCKED ensures safe concurrent consumers (future horizontal
  scaling without double-processing).
- Workspaces with no entry in workspace_api_keys are silently excluded from
  scheduling.  log_missing_keys() surfaces these at worker startup.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import asyncpg

from .audit_logger import AuditLogger, SyncResult
from .emailbison_client import EmailBisonClient
from .slack_alerter import SlackAlerter
from .sync_accounts import AccountSyncModule
from .sync_campaigns import CampaignSyncModule
from .sync_engagement import EngagementSyncModule
from .sync_events import EventSyncModule
from .sync_warmup import WarmupSyncModule

logger = logging.getLogger(__name__)

# All sync types handled by this queue.
# These map 1:1 to the data-pull modules that read FROM EmailBison INTO our DB.
# Tagging modules (lifecycle_tag_sync, set_tag_sync, kill_processor) are NOT
# in this queue — they write FROM our DB TO EmailBison and run on their own schedule.
SYNC_TYPES: Tuple[str, ...] = ('accounts', 'campaigns', 'events', 'warmup', 'engagement')

# Sync intervals (seconds) — must match values in emailbison_sync_worker.py
# These are defaults; the actual values are passed in from the worker.
DEFAULT_INTERVALS: Dict[str, int] = {
    'events':     300,    # 5 min  — most critical, picks up bounces + spam
    'accounts':   3600,   # 1 hour
    'campaigns':  3600,   # 1 hour
    'warmup':     1800,   # 30 min
    'engagement': 86400,  # 24 hr
}

# Priority levels for the queue consumer.
PRIORITY_NORMAL: int = 0   # Scheduler-inserted jobs
PRIORITY_FORCE: int = 10   # Force-refresh from client dashboard


class WorkspaceSyncQueue:
    """
    Manages the workspace_sync_queue table.

    Responsibilities:
    - Schedule: determine which workspaces are overdue and insert pending jobs
    - Execute:  claim batches of pending jobs and run them concurrently
    - Expose:   status endpoint data for the force-refresh API
    - Warn:     log workspaces that are missing API keys at startup

    Args:
        db:           asyncpg connection pool (shared with the rest of the worker)
        audit_logger: audit logger instance (shared)
        alerter:      Slack alerter instance (shared)
        concurrency:  max workspace jobs to run simultaneously (default 3)
    """

    def __init__(
        self,
        db: asyncpg.Pool,
        audit_logger: AuditLogger,
        alerter: Optional[SlackAlerter] = None,
        concurrency: int = 3,
    ):
        self.db = db
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()
        self.concurrency = concurrency

    # =========================================================================
    # SCHEDULING
    # =========================================================================

    async def schedule_overdue_syncs(
        self,
        intervals: Optional[Dict[str, int]] = None,
    ) -> int:
        """
        Insert pending jobs for every (workspace, sync_type) pair that is overdue.

        A workspace+type is overdue when:
          - It has never successfully synced (no row in sync_status), OR
          - sync_status.last_successful_sync < NOW() - interval

        Only workspaces with an active entry in workspace_api_keys are scheduled.
        Workspaces without a key are skipped silently (they were logged at startup
        by log_missing_keys()).

        The partial unique index on (workspace_id, sync_type) WHERE status='pending'
        makes the INSERT idempotent: if a job is already pending, ON CONFLICT DO
        NOTHING leaves it untouched.

        Args:
            intervals: sync type → seconds.  Defaults to DEFAULT_INTERVALS.

        Returns:
            Number of new pending jobs inserted.
        """
        ivs = intervals or DEFAULT_INTERVALS

        # Build per-type interval conditions.
        # We use a VALUES literal so a single query handles all types at once.
        # Each row: (sync_type, interval_seconds)
        type_intervals = [(t, ivs.get(t, DEFAULT_INTERVALS.get(t, 3600))) for t in SYNC_TYPES]

        rows_inserted = 0
        for sync_type, interval_seconds in type_intervals:
            # sync_type is always one of SYNC_TYPES (hardcoded tuple) — safe to inline
            # as a SQL literal. Using a $N parameter for it causes asyncpg type-inference
            # conflicts because the same param appears against both VARCHAR(20) and
            # VARCHAR(50) columns (sync_status vs workspace_sync_queue).
            result = await self.db.execute(f"""
                INSERT INTO workspace_sync_queue (workspace_id, sync_type, priority)
                SELECT w.id, '{sync_type}', $1
                FROM workspaces w
                -- Only workspaces with an active workspace-scoped API key
                JOIN workspace_api_keys wak
                    ON wak.workspace_id = w.id
                    AND wak.is_active = TRUE
                -- Only active workspaces with an EmailBison workspace ID
                WHERE w.is_active = TRUE
                  AND w.emailbison_workspace_id IS NOT NULL
                  -- Check last successful sync time
                  AND NOT EXISTS (
                      SELECT 1 FROM sync_status ss
                      WHERE ss.workspace_id = w.id
                        AND ss.sync_type = '{sync_type}'
                        AND ss.last_successful_sync >= NOW() - ($2 * INTERVAL '1 second')
                  )
                  -- Skip if already pending (partial unique index covers this,
                  -- but being explicit avoids unnecessary conflict escalation)
                  AND NOT EXISTS (
                      SELECT 1 FROM workspace_sync_queue q
                      WHERE q.workspace_id = w.id
                        AND q.sync_type = '{sync_type}'
                        AND q.status = 'pending'
                  )
            """, PRIORITY_NORMAL, interval_seconds)

            # asyncpg returns "INSERT 0 N" — extract the count
            try:
                rows_inserted += int(result.split()[-1])
            except (IndexError, ValueError):
                pass

        if rows_inserted > 0:
            logger.debug("[SyncQueue] Scheduled %d overdue sync jobs", rows_inserted)

        return rows_inserted

    # =========================================================================
    # BATCH PROCESSING
    # =========================================================================

    async def process_pending_batch(self) -> List[SyncResult]:
        """
        Claim up to `self.concurrency` pending jobs and execute them concurrently.

        Job claiming uses FOR UPDATE SKIP LOCKED so this method is safe to call
        from multiple worker instances simultaneously (future horizontal scaling).

        Each job runs in its own task, isolated from sibling failures:
          asyncio.gather(*tasks, return_exceptions=True)

        Returns:
            List of SyncResult objects (one per executed job).
            Exceptions from individual jobs are captured as failed SyncResults,
            not raised.
        """
        jobs = await self._claim_batch(min_priority=0)
        if not jobs:
            return []

        return await self._execute_jobs(jobs)

    async def process_priority_batch(self) -> List[SyncResult]:
        """
        Claim and execute only high-priority (force-refresh) jobs.

        Called on a short 30-second poll interval so force-refresh requests
        from the client dashboard are picked up quickly without waiting for the
        main 5-minute events cycle.

        Returns:
            List of SyncResult objects (empty if no priority jobs pending).
        """
        jobs = await self._claim_batch(min_priority=PRIORITY_FORCE)
        if not jobs:
            return []

        return await self._execute_jobs(jobs)

    async def _claim_batch(self, min_priority: int = 0) -> List[asyncpg.Record]:
        """
        Atomically claim up to `self.concurrency` pending jobs from the queue.

        Uses FOR UPDATE SKIP LOCKED:
        - SKIP LOCKED: rows locked by another consumer are skipped, not waited on.
          This enables safe concurrent consumers without deadlocks.
        - FOR UPDATE: the UPDATE that changes status='running' is atomic with
          the SELECT, preventing double-claiming.

        Args:
            min_priority: Only claim jobs with priority >= this value.
                          0 = all pending jobs.
                          PRIORITY_FORCE (10) = force-refresh only.

        Returns:
            List of claimed job records (may be empty).
        """
        return await self.db.fetch("""
            UPDATE workspace_sync_queue
            SET status = 'running', started_at = NOW()
            WHERE id IN (
                SELECT id FROM workspace_sync_queue
                WHERE status = 'pending'
                  AND priority >= $1
                ORDER BY priority DESC, queued_at ASC
                LIMIT $2
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, workspace_id, sync_type, is_force_refresh, queued_at
        """, min_priority, self.concurrency)

    async def _execute_jobs(self, jobs: List[asyncpg.Record]) -> List[SyncResult]:
        """
        Run a list of claimed jobs concurrently, respecting the semaphore.

        Each job:
        1. Loads the workspace API key from workspace_api_keys
        2. Opens a workspace-scoped EmailBisonClient (no switch_workspace needed)
        3. Dispatches to the correct sync module
        4. Marks the job complete or failed in the queue

        return_exceptions=True ensures one failure never prevents others from running.
        """
        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [self._run_job(job, semaphore) for job in jobs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        sync_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                job = jobs[i]
                logger.error(
                    "[SyncQueue] Unhandled exception for job %s (%s / %s): %s",
                    job['id'], job['workspace_id'], job['sync_type'], result,
                    exc_info=result,
                )
                # Mark the job failed in DB (best-effort)
                try:
                    await self._mark_job_failed(job['id'], str(result))
                except Exception:
                    pass
            elif result is not None:
                sync_results.append(result)

        return sync_results

    async def _run_job(
        self,
        job: asyncpg.Record,
        semaphore: asyncio.Semaphore,
    ) -> Optional[SyncResult]:
        """
        Execute a single sync job within the semaphore.

        Loads the workspace API key, builds a workspace-scoped client,
        dispatches to the correct sync module, and records the outcome.

        The workspace-scoped API key means NO switch_workspace() call is needed.
        The EB API authenticates the request AND sets the workspace context from
        the token itself.  This is what enables safe concurrency: two workspaces
        can make API calls simultaneously without interfering with each other's
        context.

        Args:
            job:       Claimed job record from workspace_sync_queue.
            semaphore: Concurrency limiter shared across jobs in the batch.

        Returns:
            SyncResult on success or failure, or None if workspace key is missing.
        """
        async with semaphore:
            workspace_id: UUID = job['workspace_id']
            sync_type: str = job['sync_type']
            job_id: UUID = job['id']

            # Load workspace name and API key together
            ws_row = await self.db.fetchrow("""
                SELECT w.workspace_name, wak.key_token
                FROM workspaces w
                JOIN workspace_api_keys wak ON wak.workspace_id = w.id
                WHERE w.id = $1
                  AND wak.is_active = TRUE
            """, workspace_id)

            if not ws_row or not ws_row['key_token']:
                # No key — workspace was deactivated or key revoked since scheduling.
                # Mark the job as failed with a clear message; it will be rescheduled
                # only if the workspace gets a key and the interval expires.
                msg = f"No active API key for workspace {workspace_id}"
                logger.warning("[SyncQueue] %s — skipping job %s (%s)", msg, job_id, sync_type)
                await self._mark_job_failed(job_id, msg)
                return None

            workspace_name: str = ws_row['workspace_name']
            ws_api_key: str = ws_row['key_token']

            try:
                async with EmailBisonClient(api_key=ws_api_key) as client:
                    result = await self._dispatch(
                        sync_type=sync_type,
                        workspace_id=workspace_id,
                        workspace_name=workspace_name,
                        client=client,
                    )

                await self._mark_job_complete(job_id, result.records_processed)

                # Update sync_status only on success/partial so failed jobs are
                # rescheduled on the next scheduler tick instead of being silently
                # skipped for a full interval.
                if result.status != 'failed':
                    await self.audit_logger.update_sync_status(
                        sync_type=sync_type,
                        workspace_id=workspace_id,
                        record_count=result.records_processed,
                    )

                logger.debug(
                    "[SyncQueue] %s / %s — %d records in %.1fs [%s]",
                    workspace_name, sync_type,
                    result.records_processed, result.duration_seconds,
                    result.status,
                )
                return result

            except Exception as e:
                logger.error(
                    "[SyncQueue] %s / %s failed: %s",
                    workspace_name, sync_type, e,
                    exc_info=True,
                )
                await self._mark_job_failed(job_id, str(e))

                if self.alerter:
                    await self.alerter.alert_sync_failure(
                        module=sync_type,
                        error=str(e),
                        workspace=workspace_name,
                    )
                return None

    # =========================================================================
    # DISPATCH
    # =========================================================================

    async def _dispatch(
        self,
        sync_type: str,
        workspace_id: UUID,
        workspace_name: str,
        client: EmailBisonClient,
    ) -> SyncResult:
        """
        Route a sync job to the correct module.

        Each module receives:
        - db: shared connection pool
        - client: workspace-scoped EmailBisonClient — NO switch_workspace() needed
        - audit_logger / alerter: shared infrastructure

        Post-sync hooks (sync_all_domains, sync_campaign_inbox_assignments)
        are called here so each module's sync_workspace() stays single-purpose.

        Args:
            sync_type:       One of SYNC_TYPES.
            workspace_id:    Internal workspace UUID.
            workspace_name:  Human-readable name for logging.
            client:          Pre-configured workspace-scoped API client.

        Returns:
            SyncResult from the sync module.

        Raises:
            ValueError: Unknown sync_type (programming error — never raised in prod).
        """
        if sync_type == 'accounts':
            module = AccountSyncModule(
                db=self.db, client=client,
                audit_logger=self.audit_logger, alerter=self.alerter,
            )
            result = await module.sync_workspace(workspace_id, workspace_name)
            # sync_all_domains() is a pure SQL operation (no API calls).
            # It creates missing domain rows from sender_accounts email addresses
            # and updates health scores.  Called after every accounts sync so
            # domain metadata stays fresh.
            try:
                await module.sync_all_domains()
            except Exception as e:
                logger.warning("[SyncQueue] sync_all_domains post-hook failed: %s", e)
            return result

        elif sync_type == 'campaigns':
            module = CampaignSyncModule(
                db=self.db, client=client,
                audit_logger=self.audit_logger, alerter=self.alerter,
            )
            result = await module.sync_workspace(workspace_id, workspace_name)
            # sync_campaign_inbox_assignments() maps EB campaign↔inbox pairings
            # into campaign_inboxes and sets sending_started_at.  Scoped to this
            # workspace, so it only queries the inboxes we just synced.
            try:
                await module.sync_campaign_inbox_assignments(workspace_id)
            except Exception as e:
                logger.warning(
                    "[SyncQueue] sync_campaign_inbox_assignments post-hook failed: %s", e
                )
            return result

        elif sync_type == 'events':
            module = EventSyncModule(
                db=self.db, client=client,
                audit_logger=self.audit_logger, alerter=self.alerter,
            )
            return await module.sync_workspace(workspace_id, workspace_name)

        elif sync_type == 'warmup':
            module = WarmupSyncModule(
                db=self.db, client=client,
                audit_logger=self.audit_logger, alerter=self.alerter,
            )
            # sync_workspace_warmup() now calls auto_enable_warmup_for_connected()
            # internally after syncing warmup stats, so no post-hook needed here.
            return await module.sync_workspace_warmup(workspace_id, workspace_name)

        elif sync_type == 'engagement':
            module = EngagementSyncModule(
                db=self.db, client=client,
                audit_logger=self.audit_logger, alerter=self.alerter,
            )
            return await module.sync_workspace(workspace_id, workspace_name)

        else:
            raise ValueError(f"Unknown sync_type: {sync_type!r}. "
                             f"Valid types: {SYNC_TYPES}")

    # =========================================================================
    # FORCE-REFRESH (client dashboard API)
    # =========================================================================

    async def request_force_refresh(self, workspace_id: UUID) -> Dict:
        """
        Enqueue all sync types for a workspace at high priority.

        Called by POST /api/sync/workspaces/{workspace_id}/refresh.
        The priority poll loop (30-second interval) will pick these up within
        ~30 seconds regardless of where the normal sync schedule is.

        Only queues sync types that are NOT already running for this workspace.
        Already-running jobs continue to completion; a new pending job will be
        queued after they finish.

        Args:
            workspace_id: Internal workspace UUID.

        Returns:
            Dict with 'queued' (list of types enqueued) and 'already_running'
            (types that had an active job and were skipped).
        """
        queued = []
        already_running = []

        for sync_type in SYNC_TYPES:
            # Check for in-flight job (do not queue duplicate while running)
            running = await self.db.fetchval("""
                SELECT id FROM workspace_sync_queue
                WHERE workspace_id = $1
                  AND sync_type = $2
                  AND status = 'running'
                LIMIT 1
            """, workspace_id, sync_type)

            if running:
                already_running.append(sync_type)
                continue

            # Insert high-priority job (pending unique index handles duplicates)
            result = await self.db.execute("""
                INSERT INTO workspace_sync_queue
                    (workspace_id, sync_type, priority, is_force_refresh)
                VALUES ($1, $2, $3, TRUE)
                ON CONFLICT DO NOTHING
            """, workspace_id, sync_type, PRIORITY_FORCE)

            try:
                if int(result.split()[-1]) > 0:
                    queued.append(sync_type)
            except (IndexError, ValueError):
                queued.append(sync_type)

        logger.info(
            "[SyncQueue] Force-refresh for %s: queued=%s already_running=%s",
            workspace_id, queued, already_running,
        )

        return {
            'workspace_id': str(workspace_id),
            'queued': queued,
            'already_running': already_running,
        }

    # =========================================================================
    # STATUS (API endpoint data)
    # =========================================================================

    async def get_workspace_sync_status(self, workspace_id: UUID) -> Dict:
        """
        Return sync freshness and queue state for a single workspace.

        Used by GET /api/sync/workspaces/{workspace_id}/status.

        Returns a dict with:
        - last_sync_times:    {sync_type: ISO timestamp or null} from sync_status
        - pending_jobs:       list of pending/running jobs
        - has_api_key:        whether workspace has a valid workspace-scoped key
        """
        # Last successful sync per type
        sync_rows = await self.db.fetch("""
            SELECT sync_type, last_successful_sync
            FROM sync_status
            WHERE workspace_id = $1
        """, workspace_id)
        last_sync = {
            row['sync_type']: row['last_successful_sync'].isoformat()
            if row['last_successful_sync'] else None
            for row in sync_rows
        }
        # Fill in None for types with no entry
        for t in SYNC_TYPES:
            last_sync.setdefault(t, None)

        # Active / pending queue jobs
        queue_rows = await self.db.fetch("""
            SELECT sync_type, status, priority, is_force_refresh, queued_at, started_at
            FROM workspace_sync_queue
            WHERE workspace_id = $1
              AND status IN ('pending', 'running')
            ORDER BY priority DESC, queued_at ASC
        """, workspace_id)
        pending_jobs = [
            {
                'sync_type':       row['sync_type'],
                'status':          row['status'],
                'priority':        row['priority'],
                'is_force_refresh': row['is_force_refresh'],
                'queued_at':       row['queued_at'].isoformat(),
                'started_at':      row['started_at'].isoformat() if row['started_at'] else None,
            }
            for row in queue_rows
        ]

        # API key presence
        has_key = await self.db.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM workspace_api_keys
                WHERE workspace_id = $1 AND is_active = TRUE
            )
        """, workspace_id)

        return {
            'workspace_id':  str(workspace_id),
            'has_api_key':   bool(has_key),
            'last_sync':     last_sync,
            'pending_jobs':  pending_jobs,
        }

    # =========================================================================
    # STARTUP DIAGNOSTICS
    # =========================================================================

    async def log_missing_keys(self) -> int:
        """
        Log active workspaces that have no entry in workspace_api_keys.

        Called once at worker startup.  These workspaces will be silently
        excluded from all scheduling until a key is generated.

        To generate missing keys, run:
            python scripts/backfill_workspace_keys.py

        Or the workspace discovery daily task will auto-generate keys for
        any newly discovered workspaces.

        Returns:
            Number of workspaces missing a key.
        """
        missing = await self.db.fetch("""
            SELECT w.workspace_name, w.emailbison_workspace_id
            FROM workspaces w
            WHERE w.is_active = TRUE
              AND w.emailbison_workspace_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM workspace_api_keys wak
                  WHERE wak.workspace_id = w.id
                    AND wak.is_active = TRUE
              )
            ORDER BY w.workspace_name
        """)

        if missing:
            names = [r['workspace_name'] for r in missing]
            logger.warning(
                "[SyncQueue] %d workspace(s) have no API key and will be excluded "
                "from sync scheduling: %s — run scripts/backfill_workspace_keys.py "
                "to generate keys.",
                len(missing), ', '.join(names),
            )
        else:
            logger.info("[SyncQueue] All active workspaces have API keys. Ready.")

        return len(missing)

    # =========================================================================
    # QUEUE MAINTENANCE
    # =========================================================================

    async def prune_old_jobs(self, days: int = 30) -> int:
        """
        Delete completed/failed jobs older than `days` days.

        Called by the retention manager as part of the daily cleanup pass.
        Keeps the table small so the consumer index stays efficient.

        Args:
            days: Retention window in days.  Jobs completed before this are deleted.

        Returns:
            Number of rows deleted.
        """
        result = await self.db.execute("""
            DELETE FROM workspace_sync_queue
            WHERE status IN ('complete', 'failed')
              AND completed_at < NOW() - ($1 * INTERVAL '1 day')
        """, days)

        try:
            deleted = int(result.split()[-1])
        except (IndexError, ValueError):
            deleted = 0

        if deleted > 0:
            logger.info("[SyncQueue] Pruned %d old sync jobs (>%d days)", deleted, days)

        return deleted

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    async def _mark_job_complete(self, job_id: UUID, records_synced: int):
        """Update a claimed job to 'complete'."""
        await self.db.execute("""
            UPDATE workspace_sync_queue
            SET status = 'complete',
                completed_at = NOW(),
                records_synced = $2
            WHERE id = $1
        """, job_id, records_synced)

    async def _mark_job_failed(self, job_id: UUID, error_message: str):
        """Update a claimed job to 'failed' with the error message."""
        await self.db.execute("""
            UPDATE workspace_sync_queue
            SET status = 'failed',
                completed_at = NOW(),
                error_message = $2
            WHERE id = $1
        """, job_id, error_message[:2000])  # truncate to fit TEXT column sanely
