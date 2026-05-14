"""EOD reapply daemon — event-driven scheduler for campaign sender reapply.

Long-lived process. Startup crash-recovery scan, then two cooperating
coroutines:

  - `recover_orphaned_jobs` (startup, once): any job left in 'flagged'
    state is a crash victim — the previous daemon instance claimed it and
    died before finalizing. The orchestrator pauses before mutating, so
    the campaign may be left paused. The scan checks each orphan's EB
    status and resumes it if paused. Runs before the loops so recovery
    completes before new work begins.

  - `enqueuer_loop`: every `enqueue_interval_seconds` (default 1h),
    walks `eod_reapply_enabled=TRUE` workspaces, fetches each active
    campaign's schedule from EB, computes `trigger_at` in the campaign's
    own IANA timezone, and INSERTs a job row for today's
    `run_local_date` with `ON CONFLICT DO NOTHING`. Idempotent.

  - `worker_loop`: blocks on `MIN(scheduled_for) WHERE status='pending'`,
    sleeps until that moment (or up to `idle_seconds` if no work),
    then atomically claims the job via SELECT FOR UPDATE SKIP LOCKED,
    emits the past-tense audit row in `event_log`
    (`event_type='campaign_reapply_due'`), runs `reapply_campaign(...)`,
    and finalizes both rows. LISTENs on `campaign_reapply_enqueued`
    to be woken when the enqueuer inserts an earlier-`scheduled_for`
    row mid-sleep.

Two independent axes of control:
  - WHICH workspaces participate: `workspaces.eod_reapply_enabled`
    (per-workspace DB flag, default FALSE — frontend-toggleable).
  - APPLY vs DRY-RUN: `DaemonConfig.dry_run_only` (daemon-wide deploy
    setting, set from the CLI's `--apply` flag). Dry-run computes and
    logs the diff but makes no EB mutations.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg

from .db import (
    claim_due_job,
    emit_event_log_due,
    enqueue_job,
    fetch_next_scheduled_at,
    fetch_orphaned_jobs,
    finalize_job,
    list_active_campaigns,
    list_enabled_workspaces,
    mark_job_recovered,
    sweep_stuck_event_log,
)
from .eb_client import EBClient, EmailBisonAPIError
from .reapply import ReapplyStatus, reapply_campaign

# EB campaign statuses that mean "paused by us, needs resume". The orchestrator
# pauses before mutating; a crash mid-reapply leaves the campaign here.
_PAUSED_STATUSES = {"paused"}

logger = logging.getLogger("eod_reapply.daemon")

# Default sleep ceiling when no jobs are pending. The daemon also wakes
# on LISTEN/NOTIFY, so this is a worst-case wake interval — not a hot loop.
_DEFAULT_IDLE_SECONDS = 3600

# Enqueue cadence. 1h is conservative — schedules don't change often,
# and the daemon already handles late-arriving job inserts via NOTIFY.
_DEFAULT_ENQUEUE_INTERVAL_SECONDS = 3600

# Channel name for NOTIFY when a new pending job is inserted. Daemon
# LISTENs; enqueuer issues `pg_notify(...)` so the worker re-evaluates
# its next-wake immediately rather than waiting out the idle sleep.
NOTIFY_CHANNEL_ENQUEUED = "campaign_reapply_enqueued"


# ============================================================================
# Config
# ============================================================================

@dataclass(frozen=True)
class DaemonConfig:
    database_url: str
    eb_base_url: str
    dry_run_only: bool = True
    buffer_minutes: int = 60          # window evaluator buffer (end_time + buffer = trigger)
    enqueue_interval_seconds: int = _DEFAULT_ENQUEUE_INTERVAL_SECONDS
    idle_seconds: int = _DEFAULT_IDLE_SECONDS
    # Per-call orchestrator tuning. Same defaults as the CLI's `reapply` command.
    min_target_size: int = 1
    max_removal_pct: float = 50.0
    verify_settle_attempts: int = 4
    verify_settle_seconds: float = 5.0
    # Test hook — when set, the daemon uses this for "now" so tests can
    # advance virtual time without monkeypatching datetime.now.
    now_fn: Any = field(default=None)  # Callable[[], datetime] | None


# ============================================================================
# Enqueuer
# ============================================================================

@dataclass(frozen=True)
class _ScheduleSummary:
    """Subset of EB's GET /api/campaigns/{id}/schedule we need."""
    timezone: str
    end_time: time
    weekday_active: tuple[bool, bool, bool, bool, bool, bool, bool]  # mon..sun


def _parse_eb_time(s: str) -> time:
    parts = s.strip().split(":")
    if len(parts) == 2:
        return time(int(parts[0]), int(parts[1]))
    if len(parts) == 3:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError(f"unrecognized time format: {s!r}")


def _build_schedule_summary(data: dict[str, Any]) -> _ScheduleSummary:
    required = (
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "end_time", "timezone",
    )
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"schedule response missing fields: {missing}")
    return _ScheduleSummary(
        timezone=data["timezone"],
        end_time=_parse_eb_time(data["end_time"]),
        weekday_active=(
            bool(data["monday"]),
            bool(data["tuesday"]),
            bool(data["wednesday"]),
            bool(data["thursday"]),
            bool(data["friday"]),
            bool(data["saturday"]),
            bool(data["sunday"]),
        ),
    )


def compute_trigger_at(
    *,
    schedule: _ScheduleSummary,
    now_utc: datetime,
    buffer_minutes: int,
) -> tuple[datetime, date, str] | None:
    """Compute the next `trigger_at` in UTC, plus the `run_local_date`
    and `run_local_tz` we'll persist on the job row.

    Returns None if today is not a sending day in the campaign's tz AND
    no future sending day within the next 7 days. (Realistically: if no
    day-of-week is enabled, this campaign will never fire — caller skips.)
    """
    tz = ZoneInfo(schedule.timezone)
    now_local = now_utc.astimezone(tz)

    # Walk today + 6 days looking for the next sending day whose
    # `end_time + buffer` is still in the future. The 6-day search keeps
    # us correct across weekends when end_time has already passed.
    for offset in range(0, 8):
        candidate_local_date = now_local.date() + timedelta(days=offset)
        weekday = candidate_local_date.weekday()  # 0=Mon..6=Sun
        if not schedule.weekday_active[weekday]:
            continue
        end_local = datetime.combine(candidate_local_date, schedule.end_time, tzinfo=tz)
        trigger_local = end_local + timedelta(minutes=buffer_minutes)
        if trigger_local <= now_local:
            continue
        trigger_utc = trigger_local.astimezone(UTC)
        return trigger_utc, candidate_local_date, schedule.timezone

    return None


async def enqueue_for_workspace(
    *,
    conn: asyncpg.Connection,
    eb: EBClient,
    workspace_id: UUID,
    workspace_name: str,
    buffer_minutes: int,
    now_utc: datetime,
) -> int:
    """Walk every active campaign for the workspace and ensure a pending
    job row exists for its next trigger. Returns the count of newly
    inserted rows (existing rows are no-ops via ON CONFLICT).
    """
    campaigns = await list_active_campaigns(conn, workspace_id)
    inserted = 0
    for c in campaigns:
        try:
            sched_raw = await eb.get_campaign_schedule(int(c.emailbison_campaign_id))
            schedule = _build_schedule_summary(sched_raw)
        except (EmailBisonAPIError, ValueError, KeyError) as e:
            logger.warning(
                "enqueue: skipped campaign eb_id=%s in workspace=%s — schedule fetch/parse failed: %s",
                c.emailbison_campaign_id, workspace_name, e,
            )
            continue

        trig = compute_trigger_at(
            schedule=schedule,
            now_utc=now_utc,
            buffer_minutes=buffer_minutes,
        )
        if trig is None:
            logger.info(
                "enqueue: campaign eb_id=%s in workspace=%s has no sending day in the next 7d; skipping",
                c.emailbison_campaign_id, workspace_name,
            )
            continue

        scheduled_for, run_local_date, run_local_tz = trig
        new_id = await enqueue_job(
            conn,
            workspace_id=workspace_id,
            campaign_id=c.campaign_id,
            scheduled_for=scheduled_for,
            run_local_date=run_local_date,
            run_local_tz=run_local_tz,
        )
        if new_id is not None:
            inserted += 1
            logger.info(
                "enqueue: workspace=%s campaign_eb_id=%s job_id=%s scheduled_for=%s "
                "run_local_date=%s tz=%s",
                workspace_name, c.emailbison_campaign_id, new_id,
                scheduled_for.isoformat(), run_local_date.isoformat(), run_local_tz,
            )

    return inserted


async def enqueuer_loop(
    cfg: DaemonConfig,
    pool: asyncpg.Pool,
    stop_event: asyncio.Event,
) -> None:
    """Periodic enqueuer. Wakes every `enqueue_interval_seconds` (or when
    `stop_event` is set, exits immediately).
    """
    while not stop_event.is_set():
        now_utc = (cfg.now_fn() if cfg.now_fn is not None else datetime.now(UTC))
        try:
            async with pool.acquire() as conn:
                enabled = await list_enabled_workspaces(conn)
                total_inserted = 0
                for ws in enabled:
                    async with EBClient(base_url=cfg.eb_base_url, api_key=ws.api_key) as eb:
                        n = await enqueue_for_workspace(
                            conn=conn, eb=eb,
                            workspace_id=ws.workspace_id,
                            workspace_name=ws.workspace_name,
                            buffer_minutes=cfg.buffer_minutes,
                            now_utc=now_utc,
                        )
                        total_inserted += n
                if total_inserted > 0:
                    # Wake any worker that's idle past the new scheduled_for.
                    await conn.execute(f"NOTIFY {NOTIFY_CHANNEL_ENQUEUED}")
                logger.info(
                    "enqueue: pass complete. workspaces=%d new_jobs=%d",
                    len(enabled), total_inserted,
                )
        except Exception:
            # Don't let an enqueuer crash kill the daemon — log + back off.
            logger.exception("enqueue: pass failed; will retry next interval")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=cfg.enqueue_interval_seconds)
        except TimeoutError:
            continue
        # If we got here, stop_event was set — fall out of the loop.


# ============================================================================
# Worker
# ============================================================================

async def _run_one_job(
    cfg: DaemonConfig,
    conn: asyncpg.Connection,
    job: Any,
) -> None:
    """Execute a single claimed job.

    `apply` is `not cfg.dry_run_only`: in dry-run mode the orchestrator
    computes and logs the diff but makes no EB mutations; in apply-mode it
    runs the full pause/attach/remove/verify/resume sequence.
    """
    payload = {
        "campaign_id": str(job.campaign_id),
        "emailbison_campaign_id": job.emailbison_campaign_id,
        "scheduled_for": job.scheduled_for.isoformat(),
        "run_local_date": job.run_local_date.isoformat(),
        "run_local_tz": job.run_local_tz,
        "dry_run": cfg.dry_run_only,
    }
    event_log_id = await emit_event_log_due(
        conn,
        workspace_id=job.workspace_id,
        campaign_id=job.campaign_id,
        job_id=job.job_id,
        payload=payload,
    )

    job_status = "failed"
    event_log_status = "failed"
    error_message: str | None = None
    result_meta: dict[str, Any] | None = None

    try:
        async with EBClient(base_url=cfg.eb_base_url, api_key=job.api_key) as eb:
            now_utc = (cfg.now_fn() if cfg.now_fn is not None else datetime.now(UTC))
            result = await reapply_campaign(
                eb=eb,
                workspace_name=job.workspace_name,
                campaign_id=job.emailbison_campaign_id,
                live_tag_name="live",
                apply=(not cfg.dry_run_only),
                skip_time_check=True,          # daemon already gated on scheduled_for
                buffer_minutes=cfg.buffer_minutes,
                now_utc=now_utc,
                # Cross-day idempotency is the job table's UNIQUE
                # (campaign_id, run_local_date) — not the orchestrator's
                # internal time-gate, which the daemon bypasses anyway.
                last_run_local_date=None,
                min_target_size=cfg.min_target_size,
                max_removal_pct=cfg.max_removal_pct,
                verify_settle_attempts=cfg.verify_settle_attempts,
                verify_settle_seconds=cfg.verify_settle_seconds,
            )
        result_meta = {
            "status": result.status.value,
            "verify_passed": result.verify_passed,
            "target_set_size": len(result.target_set),
            "prior_set_size": len(result.prior_set),
            "to_attach_size": len(result.attached_ids),
            "to_remove_size": len(result.removed_ids),
            "to_attach_sample": result.attached_ids[:20],
            "to_remove_sample": result.removed_ids[:20],
            "is_dry_run": result.is_dry_run,
            "error_step": result.error_step,
            "operator_action_required": result.operator_action_required,
        }

        # Job-row status mapping. The granular orchestrator status lives in the
        # event_log row's metadata (result_meta above); the job row carries
        # only a coarse closed-out indicator.
        if result.status in (
            ReapplyStatus.SUCCEEDED,
            ReapplyStatus.SKIPPED_NO_DIFF,
            ReapplyStatus.SKIPPED_DRY_RUN,
        ):
            job_status = "completed"
            event_log_status = "completed"
        elif result.status in (
            ReapplyStatus.SKIPPED_EMPTY_LIVE,
            ReapplyStatus.SKIPPED_NOT_ACTIVE,
            ReapplyStatus.SKIPPED_TIME_GATE,
            ReapplyStatus.SKIPPED_OVERSIZED_REMOVAL,
        ):
            job_status = "skipped"
            event_log_status = "completed"
            error_message = result.error_message
        else:  # FAILED_*
            job_status = "failed"
            event_log_status = "failed"
            error_message = result.error_message
    except Exception as e:
        logger.exception("worker: job %s threw — will mark failed", job.job_id)
        error_message = f"{type(e).__name__}: {e}"
        result_meta = {"unhandled_exception": True}

    await finalize_job(
        conn,
        job_id=job.job_id,
        event_log_id=event_log_id,
        job_status=job_status,
        event_log_status=event_log_status,
        error_message=error_message,
        result_meta=result_meta,
    )
    logger.info(
        "worker: job_id=%s workspace=%s campaign_eb_id=%s outcome=%s",
        job.job_id, job.workspace_name, job.emailbison_campaign_id, job_status,
    )


async def worker_loop(
    cfg: DaemonConfig,
    pool: asyncpg.Pool,
    stop_event: asyncio.Event,
) -> None:
    """Block on next-wake; claim+run jobs as they come due."""
    # Dedicated connection for LISTEN — asyncpg requires LISTEN to live on
    # one connection, not a pool acquire transient.
    wake_event = asyncio.Event()

    def _on_notify(_conn: Any, _pid: int, _channel: str, _payload: str) -> None:
        wake_event.set()

    listen_conn = await pool.acquire()
    try:
        await listen_conn.add_listener(NOTIFY_CHANNEL_ENQUEUED, _on_notify)

        while not stop_event.is_set():
            # 1. Try to claim a due job. Loop until none are due.
            while not stop_event.is_set():
                now_utc = (cfg.now_fn() if cfg.now_fn is not None else datetime.now(UTC))
                async with pool.acquire() as conn:
                    job = await claim_due_job(conn, now_utc)
                if job is None:
                    break
                async with pool.acquire() as conn:
                    await _run_one_job(cfg, conn, job)

            # 2. Determine how long to sleep.
            async with pool.acquire() as conn:
                next_at = await fetch_next_scheduled_at(conn)
            now_utc = (cfg.now_fn() if cfg.now_fn is not None else datetime.now(UTC))
            sleep_seconds: float
            if next_at is None:
                sleep_seconds = float(cfg.idle_seconds)
            else:
                # next_at is timestamptz from asyncpg → ensure UTC for comparison
                if next_at.tzinfo is None:
                    next_at = next_at.replace(tzinfo=UTC)
                sleep_seconds = max(0.0, (next_at - now_utc).total_seconds())
                sleep_seconds = min(sleep_seconds, float(cfg.idle_seconds))

            # 3. Wait for either: stop signal, NOTIFY wake, or timeout.
            wake_event.clear()
            wakers = [
                asyncio.create_task(stop_event.wait()),
                asyncio.create_task(wake_event.wait()),
            ]
            try:
                done, pending = await asyncio.wait(
                    wakers,
                    timeout=sleep_seconds if sleep_seconds > 0 else None,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
            except Exception:
                logger.exception("worker: wait failed")
                await asyncio.sleep(1.0)
    finally:
        try:
            await listen_conn.remove_listener(NOTIFY_CHANNEL_ENQUEUED, _on_notify)
        except Exception:
            pass
        try:
            await pool.release(listen_conn)
        except Exception:
            pass


# ============================================================================
# Crash recovery
# ============================================================================

async def recover_orphaned_jobs(cfg: DaemonConfig, pool: asyncpg.Pool) -> int:
    """Startup crash-recovery scan.

    A job stuck in status='flagged' means the daemon claimed it and died
    before finalize_job ran — the campaign may be PAUSED mid-reapply
    (the orchestrator pauses before mutating). For each orphan:
      1. Fetch the campaign's current EB status.
      2. If paused → resume it (this is the load-bearing recovery — a
         paused campaign sends nothing until resumed).
      3. Mark the job 'failed' with a recovery note either way.

    Also sweeps any event_log rows stuck in 'processing' (the daemon is
    single-instance, so those are always crash victims).

    Returns the number of orphaned jobs handled. Runs before the enqueuer
    and worker loops start, so recovery completes before new work begins.
    """
    async with pool.acquire() as conn:
        orphans = await fetch_orphaned_jobs(conn)
        stuck_events = await sweep_stuck_event_log(conn)

    if stuck_events:
        logger.warning("recovery: swept %d stuck event_log row(s) to failed", stuck_events)

    if not orphans:
        if stuck_events == 0:
            logger.info("recovery: no orphaned jobs — clean startup")
        return 0

    logger.warning(
        "recovery: found %d orphaned job(s) (claimed but never finalized) — checking campaigns",
        len(orphans),
    )
    recovered = 0
    for job in orphans:
        note: str
        try:
            async with EBClient(base_url=cfg.eb_base_url, api_key=job.api_key) as eb:
                campaign = await eb.get_campaign(job.emailbison_campaign_id)
                status = (campaign.get("status") or "").lower()
                if status in _PAUSED_STATUSES:
                    await eb.resume_campaign(job.emailbison_campaign_id)
                    note = (
                        f"recovered on startup: campaign was LEFT PAUSED by a crash "
                        f"mid-reapply (eb status={status!r}); resumed"
                    )
                    logger.error(
                        "recovery: job_id=%s workspace=%s campaign_eb_id=%s was LEFT PAUSED — RESUMED",
                        job.job_id, job.workspace_name, job.emailbison_campaign_id,
                    )
                else:
                    note = (
                        f"recovered on startup: crash victim, campaign not paused "
                        f"(eb status={status!r}); no resume needed"
                    )
                    logger.warning(
                        "recovery: job_id=%s workspace=%s campaign_eb_id=%s crash victim, "
                        "campaign status=%s — no resume needed",
                        job.job_id, job.workspace_name, job.emailbison_campaign_id, status,
                    )
        except Exception as e:
            # Recovery itself failed — log loud and leave a breadcrumb. The
            # job is still marked failed; an operator can inspect via the note.
            note = f"recovery attempt failed: {type(e).__name__}: {e}"
            logger.exception(
                "recovery: job_id=%s campaign_eb_id=%s — recovery attempt itself failed; "
                "OPERATOR: verify campaign is not paused",
                job.job_id, job.emailbison_campaign_id,
            )

        async with pool.acquire() as conn:
            await mark_job_recovered(conn, job_id=job.job_id, note=note)
        recovered += 1

    logger.warning("recovery: handled %d orphaned job(s)", recovered)
    return recovered


# ============================================================================
# Entrypoint
# ============================================================================

async def run(cfg: DaemonConfig) -> None:
    """Bring up the daemon and run forever (until SIGINT/SIGTERM)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info("daemon: starting. config=%s", asdict(cfg))
    if not cfg.dry_run_only:
        logger.warning(
            "daemon: dry_run_only=FALSE — apply-mode is enabled. "
            "Ensure workspace flags are set as intended."
        )

    pool = await asyncpg.create_pool(cfg.database_url, min_size=2, max_size=6)
    assert pool is not None
    stop_event = asyncio.Event()

    # Crash recovery FIRST — before any new work. A previous daemon instance
    # may have died mid-reapply, leaving a campaign paused. Resume it before
    # the loops start so we never stack new work on top of a degraded state.
    try:
        await recover_orphaned_jobs(cfg, pool)
    except Exception:
        # Recovery is best-effort; a failure here must not block startup.
        # Individual job failures are already logged inside the function.
        logger.exception("daemon: crash-recovery scan failed; continuing startup")

    # SIGINT/SIGTERM → stop_event.set(). On Windows the signal API is
    # limited; we wrap in try/except so dev-laptop runs don't crash.
    try:
        loop = asyncio.get_running_loop()
        import signal

        def _stop() -> None:
            logger.info("daemon: stop signal received")
            stop_event.set()

        for sig_name in ("SIGINT", "SIGTERM"):
            try:
                loop.add_signal_handler(getattr(signal, sig_name), _stop)
            except (NotImplementedError, RuntimeError, AttributeError):
                pass
    except Exception:
        logger.warning("daemon: signal handler setup failed; relying on KeyboardInterrupt", exc_info=True)

    enqueuer_task = asyncio.create_task(enqueuer_loop(cfg, pool, stop_event))
    worker_task = asyncio.create_task(worker_loop(cfg, pool, stop_event))

    try:
        await stop_event.wait()
    finally:
        logger.info("daemon: shutting down")
        for t in (enqueuer_task, worker_task):
            t.cancel()
        for t in (enqueuer_task, worker_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("daemon: task raised during shutdown")
        await pool.close()
        logger.info("daemon: stopped")
