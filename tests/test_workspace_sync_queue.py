"""
Tests for WorkspaceSyncQueue — concurrent per-workspace job queue.

Static unit tests: all DB interactions are mocked with AsyncMock.
These tests validate business logic, not DB schema.

Test coverage:
  1. schedule_overdue_syncs — excludes keyless workspaces
  2. schedule_overdue_syncs — idempotent (skips already-pending jobs)
  3. _claim_batch — returns jobs at correct priority threshold
  4. process_priority_batch — only claims priority >= PRIORITY_FORCE jobs
  5. request_force_refresh — inserts all 5 sync types at priority=10
  6. request_force_refresh — skips already-running jobs
  7. _execute_jobs — error isolation: one failure does not block siblings
  8. _dispatch — routes accounts → AccountSyncModule
  9. _dispatch — routes campaigns → CampaignSyncModule + post-hook
  10. _dispatch — routes events → EventSyncModule
  11. _dispatch — routes warmup → WarmupSyncModule
  12. _dispatch — routes engagement → EngagementSyncModule
  13. _dispatch — raises ValueError for unknown sync_type
  14. log_missing_keys — returns count and logs warning for keyless workspaces
  15. log_missing_keys — returns 0 and logs info when all workspaces have keys
  16. prune_old_jobs — calls DELETE and returns count
  17. get_workspace_sync_status — returns correct shape
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4, UUID

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(**kwargs):
    """Create a dict-like asyncpg Record mock."""
    rec = MagicMock()
    rec.__getitem__ = lambda self, key: kwargs[key]
    rec.get = lambda key, default=None: kwargs.get(key, default)
    for k, v in kwargs.items():
        setattr(rec, k, v)
    return rec


def _make_queue(concurrency=3):
    """
    Create a WorkspaceSyncQueue with fully mocked DB, audit_logger, and alerter.
    """
    from sync_modules.workspace_sync_queue import WorkspaceSyncQueue

    db = MagicMock()
    db.execute = AsyncMock(return_value="INSERT 0 1")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.fetchval = AsyncMock(return_value=None)

    audit_logger = MagicMock()
    audit_logger.update_sync_status = AsyncMock()

    alerter = MagicMock()
    alerter.alert_sync_failure = AsyncMock()

    queue = WorkspaceSyncQueue(
        db=db,
        audit_logger=audit_logger,
        alerter=alerter,
        concurrency=concurrency,
    )
    return queue, db, audit_logger, alerter


# ---------------------------------------------------------------------------
# Schedule tests
# ---------------------------------------------------------------------------

class TestScheduleOverdueSyncs:
    @pytest.mark.asyncio
    async def test_schedule_calls_execute_for_each_sync_type(self):
        """schedule_overdue_syncs() issues one INSERT per sync type."""
        queue, db, _, _ = _make_queue()
        # Simulate INSERT returning 1 row each time
        db.execute = AsyncMock(return_value="INSERT 0 1")

        count = await queue.schedule_overdue_syncs()

        # 5 sync types → 5 INSERT calls
        assert db.execute.call_count == 5

    @pytest.mark.asyncio
    async def test_schedule_passes_workspace_key_join_condition(self):
        """SQL must JOIN workspace_api_keys to exclude keyless workspaces."""
        queue, db, _, _ = _make_queue()
        db.execute = AsyncMock(return_value="INSERT 0 0")

        await queue.schedule_overdue_syncs()

        # Every execute call must contain the workspace_api_keys join
        for c in db.execute.call_args_list:
            sql = c[0][0]
            assert 'workspace_api_keys' in sql, (
                "schedule_overdue_syncs() SQL must filter by workspace_api_keys "
                "to exclude workspaces without a scoped API key"
            )

    @pytest.mark.asyncio
    async def test_schedule_returns_total_inserted_count(self):
        """Return value should sum across all sync types."""
        queue, db, _, _ = _make_queue()
        # Simulate 2 rows inserted per sync type
        db.execute = AsyncMock(return_value="INSERT 0 2")

        count = await queue.schedule_overdue_syncs()

        # 5 types × 2 rows = 10
        assert count == 10

    @pytest.mark.asyncio
    async def test_schedule_uses_custom_intervals(self):
        """Custom intervals must be passed to the SQL as parameters."""
        queue, db, _, _ = _make_queue()
        db.execute = AsyncMock(return_value="INSERT 0 0")

        custom = {'accounts': 999, 'campaigns': 888, 'events': 111,
                  'warmup': 222, 'engagement': 333}
        await queue.schedule_overdue_syncs(custom)

        # sync_type is inlined as a literal in the SQL f-string; only
        # (priority, interval) are passed as positional args.
        for c in db.execute.call_args_list:
            sql  = c[0][0]      # f-string SQL
            # args: (PRIORITY_NORMAL, interval_seconds)
            interval = c[0][2]  # positional index 2 = interval
            # Extract the inlined sync_type from the SQL literal
            import re
            m = re.search(r"'(\w+)'", sql)
            assert m, "Could not find inlined sync_type in SQL"
            sync_type = m.group(1)
            assert interval == custom[sync_type], (
                f"Expected interval {custom[sync_type]} for {sync_type}, got {interval}"
            )


# ---------------------------------------------------------------------------
# Claim batch tests
# ---------------------------------------------------------------------------

class TestClaimBatch:
    @pytest.mark.asyncio
    async def test_claim_batch_uses_skip_locked_sql(self):
        """_claim_batch() must use FOR UPDATE SKIP LOCKED."""
        queue, db, _, _ = _make_queue()
        db.fetch = AsyncMock(return_value=[])

        await queue._claim_batch(min_priority=0)

        sql = db.fetch.call_args[0][0]
        assert 'SKIP LOCKED' in sql, "_claim_batch() must use FOR UPDATE SKIP LOCKED"

    @pytest.mark.asyncio
    async def test_claim_batch_passes_concurrency_limit(self):
        """_claim_batch() LIMIT must equal self.concurrency."""
        queue, db, _, _ = _make_queue(concurrency=4)
        db.fetch = AsyncMock(return_value=[])

        await queue._claim_batch(min_priority=0)

        args = db.fetch.call_args[0]
        # Args: (sql, min_priority, concurrency)
        assert args[2] == 4

    @pytest.mark.asyncio
    async def test_claim_batch_priority_filter(self):
        """_claim_batch(min_priority=10) passes 10 as priority threshold."""
        queue, db, _, _ = _make_queue()
        db.fetch = AsyncMock(return_value=[])

        await queue._claim_batch(min_priority=10)

        args = db.fetch.call_args[0]
        assert args[1] == 10

    @pytest.mark.asyncio
    async def test_process_priority_batch_uses_force_priority(self):
        """process_priority_batch() should claim only priority >= 10 jobs."""
        queue, db, _, _ = _make_queue()
        db.fetch = AsyncMock(return_value=[])

        await queue.process_priority_batch()

        args = db.fetch.call_args[0]
        # min_priority arg should be PRIORITY_FORCE (10)
        assert args[1] == 10

    @pytest.mark.asyncio
    async def test_process_pending_batch_uses_zero_priority(self):
        """process_pending_batch() claims all pending jobs (priority >= 0)."""
        queue, db, _, _ = _make_queue()
        db.fetch = AsyncMock(return_value=[])

        await queue.process_pending_batch()

        args = db.fetch.call_args[0]
        assert args[1] == 0


# ---------------------------------------------------------------------------
# Force-refresh tests
# ---------------------------------------------------------------------------

class TestRequestForceRefresh:
    @pytest.mark.asyncio
    async def test_force_refresh_queues_all_sync_types(self):
        """request_force_refresh() inserts all 5 sync types."""
        queue, db, _, _ = _make_queue()
        workspace_id = uuid4()

        # No running jobs
        db.fetchval = AsyncMock(return_value=None)
        # Each INSERT succeeds with 1 row
        db.execute = AsyncMock(return_value="INSERT 0 1")

        result = await queue.request_force_refresh(workspace_id)

        assert set(result['queued']) == {'accounts', 'campaigns', 'events', 'warmup', 'engagement'}
        assert result['already_running'] == []
        assert result['workspace_id'] == str(workspace_id)

    @pytest.mark.asyncio
    async def test_force_refresh_inserts_at_priority_10(self):
        """Force-refresh jobs must be inserted with priority=10 (PRIORITY_FORCE)."""
        queue, db, _, _ = _make_queue()
        workspace_id = uuid4()
        db.fetchval = AsyncMock(return_value=None)
        db.execute = AsyncMock(return_value="INSERT 0 1")

        await queue.request_force_refresh(workspace_id)

        # Every INSERT call should pass priority=10
        for c in db.execute.call_args_list:
            args = c[0]  # (sql, workspace_id, sync_type, priority, ...)
            # priority is the 4th positional arg (index 3)
            assert args[3] == 10, (
                f"Force-refresh must use priority=10, got {args[3]}"
            )

    @pytest.mark.asyncio
    async def test_force_refresh_skips_running_sync_types(self):
        """Types with a running job must appear in already_running, not queued."""
        queue, db, _, _ = _make_queue()
        workspace_id = uuid4()

        # Simulate 'accounts' is currently running (fetchval returns a UUID)
        running_job_id = uuid4()

        async def fetchval_side(sql, *args):
            # Second positional arg is sync_type
            if len(args) >= 2 and args[1] == 'accounts':
                return running_job_id
            return None

        db.fetchval = AsyncMock(side_effect=fetchval_side)
        db.execute = AsyncMock(return_value="INSERT 0 1")

        result = await queue.request_force_refresh(workspace_id)

        assert 'accounts' in result['already_running']
        assert 'accounts' not in result['queued']
        # Other 4 types should be queued
        assert len(result['queued']) == 4

    @pytest.mark.asyncio
    async def test_force_refresh_sets_is_force_refresh_true(self):
        """INSERT must set is_force_refresh=TRUE."""
        queue, db, _, _ = _make_queue()
        workspace_id = uuid4()
        db.fetchval = AsyncMock(return_value=None)
        db.execute = AsyncMock(return_value="INSERT 0 1")

        await queue.request_force_refresh(workspace_id)

        for c in db.execute.call_args_list:
            sql = c[0][0]
            assert 'is_force_refresh' in sql, (
                "request_force_refresh() INSERT must set is_force_refresh"
            )


# ---------------------------------------------------------------------------
# Error isolation tests
# ---------------------------------------------------------------------------

class TestErrorIsolation:
    @pytest.mark.asyncio
    async def test_execute_jobs_isolates_failures(self):
        """
        One job raising an exception must not prevent other jobs from completing.

        asyncio.gather(return_exceptions=True) ensures sibling jobs are not
        cancelled when one fails.
        """
        queue, db, audit_logger, alerter = _make_queue(concurrency=3)

        ws_id_a = uuid4()
        ws_id_b = uuid4()
        ws_id_c = uuid4()

        # Build fake job records
        jobs = [
            _make_record(id=uuid4(), workspace_id=ws_id_a, sync_type='events',
                         is_force_refresh=False, queued_at=datetime.now(timezone.utc)),
            _make_record(id=uuid4(), workspace_id=ws_id_b, sync_type='events',
                         is_force_refresh=False, queued_at=datetime.now(timezone.utc)),
            _make_record(id=uuid4(), workspace_id=ws_id_c, sync_type='events',
                         is_force_refresh=False, queued_at=datetime.now(timezone.utc)),
        ]

        call_order = []

        async def run_job_side(job, semaphore):
            ws_id = job['workspace_id']
            call_order.append(str(ws_id))
            if ws_id == ws_id_b:
                # Simulate workspace B failing
                raise RuntimeError("EB API timeout for workspace B")
            from sync_modules.audit_logger import SyncResult
            result = MagicMock(spec=SyncResult)
            result.records_processed = 5
            result.status = 'complete'
            return result

        with patch.object(queue, '_run_job', side_effect=run_job_side):
            with patch.object(queue, '_mark_job_failed', new_callable=AsyncMock):
                results = await queue._execute_jobs(jobs)

        # All three jobs must have been attempted
        assert len(call_order) == 3, "All 3 jobs must be attempted despite one failure"
        # Two successes should be in results
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_execute_jobs_marks_failed_job_in_db(self):
        """
        Exceptions in _run_job must call _mark_job_failed so the job doesn't
        stay as 'running' indefinitely.
        """
        queue, db, _, _ = _make_queue()

        job_id = uuid4()
        job = _make_record(
            id=job_id, workspace_id=uuid4(), sync_type='accounts',
            is_force_refresh=False, queued_at=datetime.now(timezone.utc),
        )

        async def run_job_raise(j, sem):
            raise RuntimeError("Simulated failure")

        with patch.object(queue, '_run_job', side_effect=run_job_raise):
            mark_failed = AsyncMock()
            with patch.object(queue, '_mark_job_failed', mark_failed):
                await queue._execute_jobs([job])

        mark_failed.assert_called_once()
        assert mark_failed.call_args[0][0] == job_id


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------

class TestDispatch:
    """Verify _dispatch routes sync_type to the correct module."""

    def _dispatch_test(self, sync_type: str, module_class: str, method: str):
        """
        Helper: patch the target module class, call _dispatch, verify call.
        """
        async def run():
            queue, db, audit_logger, alerter = _make_queue()
            workspace_id = uuid4()
            workspace_name = "Test Workspace"
            client = MagicMock()

            mock_result = MagicMock()
            mock_result.records_processed = 3
            mock_result.status = 'complete'
            mock_result.duration_seconds = 1.0

            mock_instance = MagicMock()
            setattr(mock_instance, method, AsyncMock(return_value=mock_result))

            # Also mock post-hook methods that exist on some modules
            mock_instance.sync_all_domains = AsyncMock()
            mock_instance.sync_campaign_inbox_assignments = AsyncMock()

            target_path = f'sync_modules.workspace_sync_queue.{module_class}'
            with patch(target_path, return_value=mock_instance) as MockClass:
                result = await queue._dispatch(
                    sync_type=sync_type,
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    client=client,
                )

            # Verify correct module was instantiated with db and client
            MockClass.assert_called_once()
            init_kwargs = MockClass.call_args[1]
            assert init_kwargs['db'] is db
            assert init_kwargs['client'] is client

            # Verify correct method was called
            dispatch_method = getattr(mock_instance, method)
            dispatch_method.assert_called_once()

            return result

        return asyncio.run(run())

    def test_dispatch_accounts(self):
        self._dispatch_test('accounts', 'AccountSyncModule', 'sync_workspace')

    def test_dispatch_campaigns(self):
        self._dispatch_test('campaigns', 'CampaignSyncModule', 'sync_workspace')

    def test_dispatch_events(self):
        self._dispatch_test('events', 'EventSyncModule', 'sync_workspace')

    def test_dispatch_warmup(self):
        self._dispatch_test('warmup', 'WarmupSyncModule', 'sync_workspace_warmup')

    def test_dispatch_engagement(self):
        self._dispatch_test('engagement', 'EngagementSyncModule', 'sync_workspace')

    @pytest.mark.asyncio
    async def test_dispatch_campaigns_calls_post_hook(self):
        """campaigns dispatch must call sync_campaign_inbox_assignments(workspace_id)."""
        queue, db, audit_logger, alerter = _make_queue()
        workspace_id = uuid4()

        mock_result = MagicMock()
        mock_result.records_processed = 2
        mock_result.status = 'complete'

        mock_instance = MagicMock()
        mock_instance.sync_workspace = AsyncMock(return_value=mock_result)
        mock_instance.sync_campaign_inbox_assignments = AsyncMock()

        with patch('sync_modules.workspace_sync_queue.CampaignSyncModule',
                   return_value=mock_instance):
            await queue._dispatch(
                sync_type='campaigns',
                workspace_id=workspace_id,
                workspace_name="Test",
                client=MagicMock(),
            )

        mock_instance.sync_campaign_inbox_assignments.assert_called_once_with(workspace_id)

    @pytest.mark.asyncio
    async def test_dispatch_accounts_calls_sync_all_domains(self):
        """accounts dispatch must call sync_all_domains() post-hook."""
        queue, db, _, _ = _make_queue()

        mock_result = MagicMock()
        mock_result.records_processed = 5
        mock_result.status = 'complete'

        mock_instance = MagicMock()
        mock_instance.sync_workspace = AsyncMock(return_value=mock_result)
        mock_instance.sync_all_domains = AsyncMock()

        with patch('sync_modules.workspace_sync_queue.AccountSyncModule',
                   return_value=mock_instance):
            await queue._dispatch(
                sync_type='accounts',
                workspace_id=uuid4(),
                workspace_name="Test",
                client=MagicMock(),
            )

        mock_instance.sync_all_domains.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_unknown_type_raises_valueerror(self):
        """_dispatch with unknown sync_type must raise ValueError."""
        queue, _, _, _ = _make_queue()

        with pytest.raises(ValueError, match="Unknown sync_type"):
            await queue._dispatch(
                sync_type='unknown_type',
                workspace_id=uuid4(),
                workspace_name="Test",
                client=MagicMock(),
            )


# ---------------------------------------------------------------------------
# log_missing_keys tests
# ---------------------------------------------------------------------------

class TestLogMissingKeys:
    @pytest.mark.asyncio
    async def test_log_missing_keys_returns_zero_when_all_have_keys(self):
        queue, db, _, _ = _make_queue()
        db.fetch = AsyncMock(return_value=[])  # No missing workspaces

        count = await queue.log_missing_keys()

        assert count == 0

    @pytest.mark.asyncio
    async def test_log_missing_keys_returns_count_of_missing(self):
        queue, db, _, _ = _make_queue()

        # Simulate 3 workspaces without API keys
        missing_rows = [
            _make_record(workspace_name="Sammy", emailbison_workspace_id=8),
            _make_record(workspace_name="SPUI", emailbison_workspace_id=9),
            _make_record(workspace_name="Stable Kernel", emailbison_workspace_id=6),
        ]
        db.fetch = AsyncMock(return_value=missing_rows)

        count = await queue.log_missing_keys()

        assert count == 3

    @pytest.mark.asyncio
    async def test_log_missing_keys_queries_active_workspaces(self):
        """Only active workspaces with emailbison_workspace_id should be checked."""
        queue, db, _, _ = _make_queue()
        db.fetch = AsyncMock(return_value=[])

        await queue.log_missing_keys()

        sql = db.fetch.call_args[0][0]
        assert 'is_active = TRUE' in sql
        assert 'emailbison_workspace_id IS NOT NULL' in sql


# ---------------------------------------------------------------------------
# prune_old_jobs tests
# ---------------------------------------------------------------------------

class TestPruneOldJobs:
    @pytest.mark.asyncio
    async def test_prune_default_30_days(self):
        queue, db, _, _ = _make_queue()
        db.execute = AsyncMock(return_value="DELETE 5")

        count = await queue.prune_old_jobs()

        assert count == 5
        sql = db.execute.call_args[0][0]
        assert 'DELETE' in sql
        assert 'completed_at' in sql

    @pytest.mark.asyncio
    async def test_prune_custom_days(self):
        queue, db, _, _ = _make_queue()
        db.execute = AsyncMock(return_value="DELETE 3")

        count = await queue.prune_old_jobs(days=7)

        args = db.execute.call_args[0]
        # days is passed as parameter (index 1)
        assert args[1] == 7

    @pytest.mark.asyncio
    async def test_prune_only_terminal_statuses(self):
        """DELETE must only target complete/failed jobs, not pending/running."""
        queue, db, _, _ = _make_queue()
        db.execute = AsyncMock(return_value="DELETE 0")

        await queue.prune_old_jobs()

        sql = db.execute.call_args[0][0]
        assert "'complete'" in sql or 'complete' in sql
        assert "'failed'" in sql or 'failed' in sql


# ---------------------------------------------------------------------------
# get_workspace_sync_status tests
# ---------------------------------------------------------------------------

class TestGetWorkspaceSyncStatus:
    @pytest.mark.asyncio
    async def test_returns_expected_shape(self):
        """get_workspace_sync_status must return all required keys."""
        queue, db, _, _ = _make_queue()
        workspace_id = uuid4()

        # Simulate sync_status rows
        ts = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        sync_rows = [
            _make_record(sync_type='accounts', last_successful_sync=ts),
            _make_record(sync_type='events', last_successful_sync=ts),
        ]

        # Simulate no active queue jobs
        queue_rows = []

        call_count = [0]

        async def fetch_side(sql, *args):
            call_count[0] += 1
            if 'sync_status' in sql:
                return sync_rows
            return queue_rows

        db.fetch = AsyncMock(side_effect=fetch_side)
        db.fetchval = AsyncMock(return_value=True)  # has_api_key = True

        result = await queue.get_workspace_sync_status(workspace_id)

        assert 'workspace_id' in result
        assert 'has_api_key' in result
        assert 'last_sync' in result
        assert 'pending_jobs' in result

    @pytest.mark.asyncio
    async def test_returns_none_for_never_synced_types(self):
        """Sync types never synced must appear as None in last_sync."""
        queue, db, _, _ = _make_queue()
        workspace_id = uuid4()

        # Only accounts has a sync row
        ts = datetime(2026, 4, 10, tzinfo=timezone.utc)
        db.fetch = AsyncMock(side_effect=lambda sql, *args: (
            [_make_record(sync_type='accounts', last_successful_sync=ts)]
            if 'sync_status' in sql else []
        ))
        db.fetchval = AsyncMock(return_value=True)

        result = await queue.get_workspace_sync_status(workspace_id)

        last_sync = result['last_sync']
        assert last_sync['accounts'] is not None
        assert last_sync['events'] is None
        assert last_sync['campaigns'] is None
        assert last_sync['warmup'] is None
        assert last_sync['engagement'] is None

    @pytest.mark.asyncio
    async def test_reports_has_api_key_false(self):
        """Workspace with no key must have has_api_key=False in response."""
        queue, db, _, _ = _make_queue()
        db.fetch = AsyncMock(return_value=[])
        db.fetchval = AsyncMock(return_value=False)

        result = await queue.get_workspace_sync_status(uuid4())

        assert result['has_api_key'] is False


# ---------------------------------------------------------------------------
# Concurrency contract tests
# ---------------------------------------------------------------------------

class TestConcurrencyContract:
    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_jobs(self):
        """
        asyncio.Semaphore(concurrency) must prevent more than `concurrency`
        jobs from running simultaneously.
        """
        concurrency = 2
        queue, db, audit_logger, alerter = _make_queue(concurrency=concurrency)

        active = [0]
        max_active = [0]

        async def fake_run_job(job, semaphore):
            async with semaphore:
                active[0] += 1
                if active[0] > max_active[0]:
                    max_active[0] = active[0]
                await asyncio.sleep(0.01)  # Simulate work
                active[0] -= 1
            from sync_modules.audit_logger import SyncResult
            r = MagicMock(spec=SyncResult)
            r.records_processed = 1
            r.status = 'complete'
            return r

        # Create 4 fake jobs
        jobs = [
            _make_record(
                id=uuid4(), workspace_id=uuid4(), sync_type='events',
                is_force_refresh=False, queued_at=datetime.now(timezone.utc),
            )
            for _ in range(4)
        ]

        with patch.object(queue, '_run_job', side_effect=fake_run_job):
            await queue._execute_jobs(jobs)

        # max_active should never exceed concurrency
        assert max_active[0] <= concurrency, (
            f"Expected max {concurrency} concurrent jobs, saw {max_active[0]}"
        )
