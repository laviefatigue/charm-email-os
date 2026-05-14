"""L2 tests for daemon scheduling + outcome-write logic.

Two layers:
  - Pure-function tests for compute_trigger_at + _build_schedule_summary
    (no I/O, deterministic on now_utc).
  - Integration-style test for _run_one_job with a fake EBClient + fake
    asyncpg connection, validating that:
      * event_log row is emitted with the right shape on claim
      * orchestrator is called with apply=False (PR 1 dry-run lock)
      * finalize_job is called with the mapped job/event statuses

Process-loop tests (enqueuer_loop / worker_loop) are deferred to PR 2
where the lifecycle is more interesting (apply-mode + crash recovery).
"""
from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any
from uuid import uuid4

import pytest

from eod_reapply.daemon import (
    DaemonConfig,
    _build_schedule_summary,
    _run_one_job,
    compute_trigger_at,
)
from eod_reapply.db import PendingJob
from eod_reapply.reapply import ReapplyStatus

# ============================================================================
# compute_trigger_at — pure timezone math
# ============================================================================

class TestComputeTriggerAt:
    def _sched(
        self,
        tz: str = "America/Los_Angeles",
        end: time = time(17, 0),
        weekday_active: tuple[bool, ...] = (True,) * 7,
    ) -> Any:
        # Use the same dataclass shape _build_schedule_summary produces.
        from eod_reapply.daemon import _ScheduleSummary
        return _ScheduleSummary(timezone=tz, end_time=end, weekday_active=weekday_active)

    def test_fires_today_when_before_trigger(self):
        # Mon 09:00 PT, end_time 17:00, buffer 60 → fires at 18:00 PT = 01:00 UTC Tue
        sched = self._sched()
        now_utc = datetime(2026, 5, 11, 16, 0, tzinfo=UTC)  # Mon 09:00 PT (DST)
        trig = compute_trigger_at(schedule=sched, now_utc=now_utc, buffer_minutes=60)
        assert trig is not None
        trigger_utc, run_local_date, tz = trig
        # 18:00 PT (DST = UTC-7) → 01:00 UTC the next day
        assert trigger_utc == datetime(2026, 5, 12, 1, 0, tzinfo=UTC)
        assert run_local_date.isoformat() == "2026-05-11"
        assert tz == "America/Los_Angeles"

    def test_skips_to_tomorrow_when_past_today_trigger(self):
        # Mon 19:00 PT, today's window is closed → fires Tue at 18:00 PT
        sched = self._sched()
        now_utc = datetime(2026, 5, 12, 2, 0, tzinfo=UTC)  # Mon 19:00 PT (DST)
        trig = compute_trigger_at(schedule=sched, now_utc=now_utc, buffer_minutes=60)
        assert trig is not None
        trigger_utc, run_local_date, _ = trig
        assert run_local_date.isoformat() == "2026-05-12"  # Tue local
        assert trigger_utc == datetime(2026, 5, 13, 1, 0, tzinfo=UTC)

    def test_skips_weekend_when_not_sending(self):
        # Fri 19:00 PT after end → Mon, with weekends OFF
        sched = self._sched(
            weekday_active=(True, True, True, True, True, False, False),
        )
        now_utc = datetime(2026, 5, 16, 2, 0, tzinfo=UTC)  # Fri 19:00 PT
        trig = compute_trigger_at(schedule=sched, now_utc=now_utc, buffer_minutes=60)
        assert trig is not None
        _, run_local_date, _ = trig
        # Skip Sat + Sun → Mon
        assert run_local_date.isoformat() == "2026-05-18"

    def test_no_sending_days_returns_none(self):
        sched = self._sched(weekday_active=(False,) * 7)
        now_utc = datetime(2026, 5, 11, 16, 0, tzinfo=UTC)
        assert compute_trigger_at(schedule=sched, now_utc=now_utc, buffer_minutes=60) is None

    def test_australia_sydney_dst(self):
        # Sammy's actual tz. End 17:00 AEST/AEDT.
        # 2026-05-11 = Mon in Sydney, end_time 17:00 = 07:00 UTC. With +60 buffer
        # → trigger at 18:00 AEST = 08:00 UTC. AEST is UTC+10 (no DST in May).
        sched = self._sched(tz="Australia/Sydney")
        now_utc = datetime(2026, 5, 11, 0, 0, tzinfo=UTC)  # Mon 10:00 AEST
        trig = compute_trigger_at(schedule=sched, now_utc=now_utc, buffer_minutes=60)
        assert trig is not None
        trigger_utc, run_local_date, _ = trig
        assert trigger_utc == datetime(2026, 5, 11, 8, 0, tzinfo=UTC)
        assert run_local_date.isoformat() == "2026-05-11"


# ============================================================================
# _build_schedule_summary
# ============================================================================

class TestScheduleSummary:
    def test_typical_response_parses(self):
        data = {
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True, "saturday": False, "sunday": False,
            "start_time": "08:00", "end_time": "17:00",
            "timezone": "America/Los_Angeles",
        }
        s = _build_schedule_summary(data)
        assert s.timezone == "America/Los_Angeles"
        assert s.end_time == time(17, 0)
        assert s.weekday_active == (True, True, True, True, True, False, False)

    def test_seconds_in_end_time_handled(self):
        data = {
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True, "saturday": False, "sunday": False,
            "end_time": "17:30:45", "timezone": "UTC",
        }
        s = _build_schedule_summary(data)
        assert s.end_time == time(17, 30, 45)

    def test_missing_field_raises(self):
        data = {"monday": True}
        with pytest.raises(ValueError, match="missing fields"):
            _build_schedule_summary(data)


# ============================================================================
# _run_one_job — integration with fakes
# ============================================================================

class FakeConn:
    """Captures the calls _run_one_job makes against asyncpg.Connection.

    Implements only the surface emit_event_log_due + finalize_job use:
      - fetchval (for INSERT ... RETURNING id)
      - execute (for the two UPDATEs in finalize_job)
      - transaction context manager
    """

    def __init__(self) -> None:
        self.event_log_id = uuid4()
        self.fetchval_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.fetchval_calls.append((sql, args))
        # emit_event_log_due is the only fetchval caller in this path
        return self.event_log_id

    async def execute(self, sql: str, *args: Any) -> None:
        self.execute_calls.append((sql, args))

    def transaction(self) -> Any:
        conn = self

        class _Txn:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, *_exc: Any) -> bool:
                _ = conn
                return False

        return _Txn()


class FakeReapplyResult:
    """Bare-minimum ReapplyResult shape the daemon reads."""

    def __init__(self, status: ReapplyStatus, *, is_dry_run: bool = True) -> None:
        self.status = status
        self.verify_passed = True if status == ReapplyStatus.SUCCEEDED else None
        self.target_set: list[int] = [1, 2, 3]
        self.prior_set: list[int] = [1, 2]
        self.attached_ids: list[int] = [3]
        self.removed_ids: list[int] = []
        self.is_dry_run = is_dry_run
        self.error_step: str | None = None
        self.error_message: str | None = None
        self.operator_action_required = (status == ReapplyStatus.FAILED_LEFT_PAUSED)


def _make_job(eb_campaign_id: int = 271) -> PendingJob:
    return PendingJob(
        job_id=uuid4(),
        workspace_id=uuid4(),
        workspace_name="Charm",
        api_key="test-key",
        campaign_id=uuid4(),
        emailbison_campaign_id=eb_campaign_id,
        scheduled_for=datetime(2026, 5, 12, 1, 0, tzinfo=UTC),
        run_local_date=datetime(2026, 5, 11).date(),
        run_local_tz="America/Los_Angeles",
    )


@pytest.fixture
def cfg() -> DaemonConfig:
    return DaemonConfig(
        database_url="postgresql://fake/test",
        eb_base_url="https://eb.example.com",
        dry_run_only=True,
        now_fn=lambda: datetime(2026, 5, 12, 1, 5, tzinfo=UTC),
    )


class _FakeEB:
    """Minimal EBClient stand-in: async context manager, no real session."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeEB:
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False


class TestRunOneJob:
    async def test_dry_run_passes_apply_false(self, cfg, monkeypatch):
        """dry_run_only=True → orchestrator called with apply=False."""
        captured: dict[str, Any] = {}

        async def fake_reapply_campaign(**kwargs: Any) -> FakeReapplyResult:
            captured.update(kwargs)
            return FakeReapplyResult(ReapplyStatus.SKIPPED_NO_DIFF)

        monkeypatch.setattr("eod_reapply.daemon.reapply_campaign", fake_reapply_campaign)
        monkeypatch.setattr("eod_reapply.daemon.EBClient", _FakeEB)

        conn = FakeConn()
        await _run_one_job(cfg, conn, _make_job())  # type: ignore[arg-type]

        assert captured["apply"] is False
        assert captured["skip_time_check"] is True
        assert captured["campaign_id"] == 271

        # event_log emit + finalize_job execute calls
        assert len(conn.fetchval_calls) == 1  # emit_event_log_due
        # finalize_job does 2 UPDATEs in one transaction
        assert len(conn.execute_calls) == 2

    async def test_apply_mode_passes_apply_true(self, monkeypatch):
        """dry_run_only=False → orchestrator called with apply=True."""
        captured: dict[str, Any] = {}

        async def fake_reapply_campaign(**kwargs: Any) -> FakeReapplyResult:
            captured.update(kwargs)
            return FakeReapplyResult(ReapplyStatus.SUCCEEDED)

        monkeypatch.setattr("eod_reapply.daemon.reapply_campaign", fake_reapply_campaign)
        monkeypatch.setattr("eod_reapply.daemon.EBClient", _FakeEB)

        apply_cfg = DaemonConfig(
            database_url="postgresql://fake/test",
            eb_base_url="https://eb.example.com",
            dry_run_only=False,
            now_fn=lambda: datetime(2026, 5, 12, 1, 5, tzinfo=UTC),
        )
        conn = FakeConn()
        await _run_one_job(apply_cfg, conn, _make_job())  # type: ignore[arg-type]

        assert captured["apply"] is True
        assert captured["skip_time_check"] is True

    async def test_succeeded_maps_to_completed_job_status(self, cfg, monkeypatch):
        async def fake_reapply_campaign(**kwargs: Any) -> FakeReapplyResult:
            return FakeReapplyResult(ReapplyStatus.SUCCEEDED)
        monkeypatch.setattr("eod_reapply.daemon.reapply_campaign", fake_reapply_campaign)

        class FakeEB:
            def __init__(self, **_kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> FakeEB:
                return self

            async def __aexit__(self, *_exc: Any) -> bool:
                return False
        monkeypatch.setattr("eod_reapply.daemon.EBClient", FakeEB)

        conn = FakeConn()
        await _run_one_job(cfg, conn, _make_job())  # type: ignore[arg-type]

        # Check that finalize_job was called with job_status='completed' and event_log_status='completed'.
        # finalize_job's first UPDATE sets the job row; positional args [1]=job_status.
        job_update_sql, job_update_args = conn.execute_calls[0]
        assert "UPDATE campaign_reapply_jobs" in job_update_sql
        assert job_update_args[1] == "completed"

    async def test_failed_left_paused_maps_to_failed_job_status(self, cfg, monkeypatch):
        async def fake_reapply_campaign(**kwargs: Any) -> FakeReapplyResult:
            r = FakeReapplyResult(ReapplyStatus.FAILED_LEFT_PAUSED)
            r.error_message = "resume failed: connection reset"
            r.error_step = "resume"
            return r
        monkeypatch.setattr("eod_reapply.daemon.reapply_campaign", fake_reapply_campaign)

        class FakeEB:
            def __init__(self, **_kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> FakeEB:
                return self

            async def __aexit__(self, *_exc: Any) -> bool:
                return False
        monkeypatch.setattr("eod_reapply.daemon.EBClient", FakeEB)

        conn = FakeConn()
        await _run_one_job(cfg, conn, _make_job())  # type: ignore[arg-type]

        job_update_sql, job_update_args = conn.execute_calls[0]
        assert job_update_args[1] == "failed"
        assert "resume failed" in (job_update_args[3] or "")

    async def test_unhandled_exception_marks_failed(self, cfg, monkeypatch):
        async def fake_reapply_campaign(**kwargs: Any) -> FakeReapplyResult:
            raise RuntimeError("boom")
        monkeypatch.setattr("eod_reapply.daemon.reapply_campaign", fake_reapply_campaign)

        class FakeEB:
            def __init__(self, **_kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> FakeEB:
                return self

            async def __aexit__(self, *_exc: Any) -> bool:
                return False
        monkeypatch.setattr("eod_reapply.daemon.EBClient", FakeEB)

        conn = FakeConn()
        await _run_one_job(cfg, conn, _make_job())  # type: ignore[arg-type]

        job_update_sql, job_update_args = conn.execute_calls[0]
        assert job_update_args[1] == "failed"
        # Error message captured in finalize args[3]
        assert "RuntimeError: boom" in (job_update_args[3] or "")

    @pytest.mark.parametrize("skipped_status,expected_job_status", [
        (ReapplyStatus.SKIPPED_NO_DIFF, "completed"),
        (ReapplyStatus.SKIPPED_EMPTY_LIVE, "skipped"),
        (ReapplyStatus.SKIPPED_NOT_ACTIVE, "skipped"),
        (ReapplyStatus.SKIPPED_OVERSIZED_REMOVAL, "skipped"),
    ])
    async def test_skipped_statuses_map(self, cfg, monkeypatch, skipped_status, expected_job_status):
        async def fake_reapply_campaign(**kwargs: Any) -> FakeReapplyResult:
            return FakeReapplyResult(skipped_status)
        monkeypatch.setattr("eod_reapply.daemon.reapply_campaign", fake_reapply_campaign)

        class FakeEB:
            def __init__(self, **_kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> FakeEB:
                return self

            async def __aexit__(self, *_exc: Any) -> bool:
                return False
        monkeypatch.setattr("eod_reapply.daemon.EBClient", FakeEB)

        conn = FakeConn()
        await _run_one_job(cfg, conn, _make_job())  # type: ignore[arg-type]

        job_update_sql, job_update_args = conn.execute_calls[0]
        assert job_update_args[1] == expected_job_status


# ============================================================================
# recover_orphaned_jobs — startup crash recovery
# ============================================================================

class _FakePool:
    """Minimal asyncpg.Pool stand-in: acquire() yields a dummy conn.

    recover_orphaned_jobs only uses the conn to pass to db helpers, which
    the tests monkeypatch — so the conn object itself is never touched.
    """

    def acquire(self) -> Any:
        class _Acq:
            async def __aenter__(self) -> object:
                return object()

            async def __aexit__(self, *_exc: Any) -> bool:
                return False

        return _Acq()


class _RecoveryFakeEB:
    """EBClient stand-in for recovery tests. Scripts get_campaign status and
    records whether resume_campaign was called."""

    def __init__(self, *, status: str, resume_raises: bool = False) -> None:
        self._status = status
        self._resume_raises = resume_raises
        self.resumed: list[int] = []

    def __call__(self, **_kwargs: Any) -> _RecoveryFakeEB:
        # daemon does `EBClient(base_url=..., api_key=...)` — instance is callable
        # so the same object can stand in for the class.
        return self

    async def __aenter__(self) -> _RecoveryFakeEB:
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        return {"id": campaign_id, "status": self._status}

    async def resume_campaign(self, campaign_id: int) -> dict[str, Any]:
        if self._resume_raises:
            from eod_reapply.eb_client import EmailBisonAPIError
            raise EmailBisonAPIError(500, "resume failed in recovery")
        self.resumed.append(campaign_id)
        return {"id": campaign_id, "status": "queued"}


class TestRecoverOrphanedJobs:
    async def test_no_orphans_clean_startup(self, cfg, monkeypatch):
        async def fake_fetch(_conn: Any) -> list[Any]:
            return []

        async def fake_sweep(_conn: Any) -> int:
            return 0

        monkeypatch.setattr("eod_reapply.daemon.fetch_orphaned_jobs", fake_fetch)
        monkeypatch.setattr("eod_reapply.daemon.sweep_stuck_event_log", fake_sweep)

        from eod_reapply.daemon import recover_orphaned_jobs
        n = await recover_orphaned_jobs(cfg, _FakePool())  # type: ignore[arg-type]
        assert n == 0

    async def test_paused_campaign_is_resumed(self, cfg, monkeypatch):
        """The load-bearing case: a crash left the campaign paused → resume it."""
        job = _make_job(eb_campaign_id=555)
        marked: list[tuple[Any, str]] = []

        async def fake_fetch(_conn: Any) -> list[Any]:
            return [job]

        async def fake_sweep(_conn: Any) -> int:
            return 1

        async def fake_mark(_conn: Any, *, job_id: Any, note: str) -> None:
            marked.append((job_id, note))

        fake_eb = _RecoveryFakeEB(status="paused")

        monkeypatch.setattr("eod_reapply.daemon.fetch_orphaned_jobs", fake_fetch)
        monkeypatch.setattr("eod_reapply.daemon.sweep_stuck_event_log", fake_sweep)
        monkeypatch.setattr("eod_reapply.daemon.mark_job_recovered", fake_mark)
        monkeypatch.setattr("eod_reapply.daemon.EBClient", fake_eb)

        from eod_reapply.daemon import recover_orphaned_jobs
        n = await recover_orphaned_jobs(cfg, _FakePool())  # type: ignore[arg-type]

        assert n == 1
        assert fake_eb.resumed == [555]  # campaign was resumed
        assert len(marked) == 1
        assert marked[0][0] == job.job_id
        assert "LEFT PAUSED" in marked[0][1] and "resumed" in marked[0][1]

    async def test_non_paused_campaign_not_resumed(self, cfg, monkeypatch):
        """Crash victim whose campaign is NOT paused → no resume, still marked."""
        job = _make_job(eb_campaign_id=556)
        marked: list[tuple[Any, str]] = []

        async def fake_fetch(_conn: Any) -> list[Any]:
            return [job]

        async def fake_sweep(_conn: Any) -> int:
            return 0

        async def fake_mark(_conn: Any, *, job_id: Any, note: str) -> None:
            marked.append((job_id, note))

        fake_eb = _RecoveryFakeEB(status="active")

        monkeypatch.setattr("eod_reapply.daemon.fetch_orphaned_jobs", fake_fetch)
        monkeypatch.setattr("eod_reapply.daemon.sweep_stuck_event_log", fake_sweep)
        monkeypatch.setattr("eod_reapply.daemon.mark_job_recovered", fake_mark)
        monkeypatch.setattr("eod_reapply.daemon.EBClient", fake_eb)

        from eod_reapply.daemon import recover_orphaned_jobs
        n = await recover_orphaned_jobs(cfg, _FakePool())  # type: ignore[arg-type]

        assert n == 1
        assert fake_eb.resumed == []  # NOT resumed — wasn't paused
        assert "not paused" in marked[0][1]

    async def test_recovery_failure_still_marks_job(self, cfg, monkeypatch):
        """If the recovery attempt itself throws, the job is still marked
        failed with the error captured — recovery never silently drops a job."""
        job = _make_job(eb_campaign_id=557)
        marked: list[tuple[Any, str]] = []

        async def fake_fetch(_conn: Any) -> list[Any]:
            return [job]

        async def fake_sweep(_conn: Any) -> int:
            return 0

        async def fake_mark(_conn: Any, *, job_id: Any, note: str) -> None:
            marked.append((job_id, note))

        # Campaign is paused, but resume_campaign raises.
        fake_eb = _RecoveryFakeEB(status="paused", resume_raises=True)

        monkeypatch.setattr("eod_reapply.daemon.fetch_orphaned_jobs", fake_fetch)
        monkeypatch.setattr("eod_reapply.daemon.sweep_stuck_event_log", fake_sweep)
        monkeypatch.setattr("eod_reapply.daemon.mark_job_recovered", fake_mark)
        monkeypatch.setattr("eod_reapply.daemon.EBClient", fake_eb)

        from eod_reapply.daemon import recover_orphaned_jobs
        n = await recover_orphaned_jobs(cfg, _FakePool())  # type: ignore[arg-type]

        assert n == 1
        assert len(marked) == 1
        assert "recovery attempt failed" in marked[0][1]


# ============================================================================
# DaemonConfig sanity
# ============================================================================

class TestDaemonConfig:
    def test_defaults(self):
        cfg = DaemonConfig(database_url="x", eb_base_url="y")
        assert cfg.dry_run_only is True
        assert cfg.buffer_minutes == 60
        assert cfg.verify_settle_attempts == 4
        assert cfg.verify_settle_seconds == 5.0
        assert cfg.now_fn is None

    def test_immutable(self):
        from dataclasses import FrozenInstanceError
        cfg = DaemonConfig(database_url="x", eb_base_url="y")
        with pytest.raises(FrozenInstanceError):
            cfg.dry_run_only = False  # type: ignore[misc]
