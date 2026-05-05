"""
Event listener — Tier 1 of the event-driven architecture.

Plan: docs/plans/event-driven-architecture.md

What this does
──────────────
Maintains a long-lived asyncpg connection in LISTEN mode. When the DB
emits a pg_notify (from triggers in migration 108), the listener fetches
the corresponding event_log row and dispatches it to the registered
handler.

Two-stage tracking
──────────────────
For every event:
  1. Trigger writes event_log (status='emitted') — guaranteed by transaction
  2. Listener receives notification, claims the row (status='processing')
  3. Handler runs
  4. On success: status='completed', handler_completed_at=NOW()
  5. On failure: status='failed', error_message populated, retry_after set

Watchdog (separate task) catches rows stuck in 'processing' too long
and either re-emits or escalates.

Per-workspace partitioning
──────────────────────────
The listener itself is workspace-agnostic — it dispatches events based
on event_type only. Tier 1 handlers do DB-only work (no EB API). They
NEVER touch EB directly. Instead, they enqueue tag_op_* events into
event_log with workspace_id set, and the Tier 2 batch worker
(set_tag_sync refactor, separate module) drains the queue per workspace
with workspace-scoped EB clients.

Feature flag
────────────
EVENT_DRIVEN_ENABLED env var gates the listener. Default false. The
listener task is spawned only when true. Polling continues unchanged
either way until Gate 6 of the plan.

Reconnect + catch-up
────────────────────
On listener startup or reconnect:
  1. Drain rows WHERE status = 'emitted' (events fired while listener
     was offline). Process them in emitted_at order.
  2. Then enter LISTEN loop for real-time events.

This makes events durable (no notification can be lost as long as the
trigger committed) and gives us the path to drop polling entirely
(Gate 6) once we trust the system.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Awaitable, Callable, Dict, Optional
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


# Feature flag — listener is a no-op unless this is true
EVENT_DRIVEN_ENABLED = os.getenv('EVENT_DRIVEN_ENABLED', 'false').lower() in ('true', '1', 'yes')

# How long an event can be in 'processing' before the watchdog calls it orphaned
ORPHAN_THRESHOLD_SECONDS = int(os.getenv('EVENT_ORPHAN_THRESHOLD_SECONDS', 300))  # 5 min default

# How often the watchdog runs
WATCHDOG_INTERVAL_SECONDS = int(os.getenv('EVENT_WATCHDOG_INTERVAL_SECONDS', 300))  # 5 min default

# Max retries before a failed event is given up
MAX_RETRIES = int(os.getenv('EVENT_MAX_RETRIES', 3))


# Handler signature: receives the full event_log row dict, returns nothing.
# Handler is responsible for marking the event completed/failed via emitter helpers.
EventHandler = Callable[[Dict], Awaitable[None]]


class EventListener:
    """LISTEN/NOTIFY consumer for the event-driven architecture.

    Usage:
        listener = EventListener(db_dsn=DSN)
        listener.register('kill_queued', kill_queued_handler)
        listener.register('inbox_died',  inbox_died_handler)
        # ...
        await listener.run()  # loops forever
    """

    def __init__(self, db_dsn: str):
        self.db_dsn = db_dsn
        self.handlers: Dict[str, EventHandler] = {}
        self._conn: Optional[asyncpg.Connection] = None
        self._stop = asyncio.Event()

    def register(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event_type. Channel matches event_type."""
        if event_type in self.handlers:
            raise ValueError(f"Handler already registered for {event_type}")
        self.handlers[event_type] = handler

    async def stop(self) -> None:
        """Signal the listener loop to exit."""
        self._stop.set()

    async def run(self) -> None:
        """Main loop. Reconnect-resilient."""
        if not EVENT_DRIVEN_ENABLED:
            logger.info("EventListener: EVENT_DRIVEN_ENABLED=false, listener is a no-op")
            return

        if not self.handlers:
            logger.warning("EventListener: no handlers registered, exiting")
            return

        logger.info(
            "EventListener: starting with handlers for: %s",
            sorted(self.handlers.keys()),
        )

        while not self._stop.is_set():
            try:
                await self._run_session()
            except Exception as exc:
                logger.exception("EventListener: session crashed, reconnecting in 5s: %s", exc)
                await asyncio.sleep(5)

        logger.info("EventListener: stopped")

    async def _run_session(self) -> None:
        """One LISTEN session. Returns on connection loss; outer loop reconnects."""
        self._conn = await asyncpg.connect(self.db_dsn)
        try:
            # Subscribe to every channel we have a handler for.
            for event_type in self.handlers:
                await self._conn.add_listener(event_type, self._on_notify)

            # Catch-up: drain any events that fired while we were offline.
            await self._drain_pending()

            # Wait until stop signal. Notifications arrive via _on_notify callback.
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=None)
            except asyncio.TimeoutError:
                pass

        finally:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None

    async def _drain_pending(self) -> None:
        """Process events that fired while listener was offline.

        Runs on session start (catch-up) and is the safety net that
        makes events durable. Even if a notification was missed,
        the event_log row exists with status='emitted' and we'll
        find it here.
        """
        rows = await self._conn.fetch("""
            SELECT id, event_type, entity_type, entity_id, payload,
                   emitted_at, workspace_id
            FROM event_log
            WHERE status = 'emitted'
            ORDER BY emitted_at
            LIMIT 1000
        """)

        if not rows:
            return

        logger.info("EventListener: catch-up found %d unprocessed events", len(rows))

        for row in rows:
            await self._dispatch(dict(row))

    def _on_notify(self, conn, pid, channel, payload) -> None:
        """asyncpg add_listener callback. payload is the event_id string.

        Schedules dispatch as a separate task so the LISTEN connection
        keeps consuming the next notification immediately.
        """
        try:
            event_id = UUID(payload)
        except ValueError:
            logger.warning("EventListener: invalid payload on %s: %r", channel, payload)
            return

        asyncio.create_task(self._fetch_and_dispatch(channel, event_id))

    async def _fetch_and_dispatch(self, channel: str, event_id: UUID) -> None:
        """Fetch the event_log row by id and dispatch."""
        if self._conn is None:
            return  # reconnecting

        try:
            row = await self._conn.fetchrow("""
                SELECT id, event_type, entity_type, entity_id, payload,
                       emitted_at, workspace_id, status
                FROM event_log
                WHERE id = $1
            """, event_id)
        except Exception as exc:
            logger.warning("EventListener: could not fetch event %s: %s", event_id, exc)
            return

        if not row:
            logger.warning("EventListener: notify for missing event %s on %s", event_id, channel)
            return

        await self._dispatch(dict(row))

    async def _dispatch(self, event: Dict) -> None:
        """Run the handler for an event, with status tracking.

        Idempotent: if the event is already 'processing' or 'completed',
        bail out. Multi-listener safe via SELECT FOR UPDATE SKIP LOCKED.
        """
        event_id = event['id']
        event_type = event['event_type']

        handler = self.handlers.get(event_type)
        if not handler:
            logger.debug("EventListener: no handler for %s (event %s)", event_type, event_id)
            return

        # Claim the event atomically. If another worker grabbed it first,
        # this update affects 0 rows and we bail.
        claimed = await self._claim(event_id)
        if not claimed:
            return

        try:
            await handler(event)
            await self._mark_completed(event_id)
        except Exception as exc:
            logger.exception("EventListener: handler %s raised on event %s", event_type, event_id)
            await self._mark_failed(event_id, str(exc))

    async def _claim(self, event_id: UUID) -> bool:
        """Try to claim event for processing. Returns True if we got it."""
        result = await self._conn.execute("""
            UPDATE event_log
            SET status = 'processing', handler_started_at = NOW()
            WHERE id = $1 AND status = 'emitted'
        """, event_id)
        return result.endswith(' 1')

    async def _mark_completed(self, event_id: UUID) -> None:
        await self._conn.execute("""
            UPDATE event_log
            SET status = 'completed', handler_completed_at = NOW()
            WHERE id = $1
        """, event_id)

    async def _mark_failed(self, event_id: UUID, error: str) -> None:
        # Exponential backoff: 1m, 2m, 4m
        await self._conn.execute("""
            UPDATE event_log
            SET status = 'failed',
                error_message = $2,
                retry_count = retry_count + 1,
                retry_after = NOW() + (INTERVAL '1 minute' * POWER(2, retry_count))
            WHERE id = $1
        """, event_id, error[:1000])  # cap error message size


async def run_watchdog(db_pool: asyncpg.Pool) -> None:
    """Periodic task: catch events stuck in 'processing' and mark orphaned.

    Run in parallel with the main listener. Restarts orphaned events
    by flipping them back to 'emitted', so the next listener
    reconnect (or the next handler dispatch on its channel) picks
    them up.
    """
    if not EVENT_DRIVEN_ENABLED:
        return

    logger.info(
        "EventWatchdog: starting (orphan_threshold=%ds, interval=%ds)",
        ORPHAN_THRESHOLD_SECONDS, WATCHDOG_INTERVAL_SECONDS,
    )

    while True:
        try:
            async with db_pool.acquire() as conn:
                # Mark stalled processing events as orphaned.
                stalled = await conn.fetch(f"""
                    UPDATE event_log
                    SET status = 'orphaned',
                        error_message = COALESCE(
                            error_message,
                            'handler_started_at exceeded orphan threshold'
                        )
                    WHERE status = 'processing'
                      AND handler_started_at < NOW() - INTERVAL '{ORPHAN_THRESHOLD_SECONDS} seconds'
                    RETURNING id, event_type, handler_started_at
                """)

                if stalled:
                    logger.warning(
                        "EventWatchdog: marked %d events orphaned: %s",
                        len(stalled),
                        [r['event_type'] for r in stalled[:5]],
                    )

                # Re-emit failed events whose retry_after is in the past
                # and retry_count < MAX_RETRIES.
                retried = await conn.fetch(f"""
                    UPDATE event_log
                    SET status = 'emitted',
                        handler_started_at = NULL,
                        retry_after = NULL
                    WHERE status = 'failed'
                      AND retry_after IS NOT NULL
                      AND retry_after < NOW()
                      AND retry_count < {MAX_RETRIES}
                    RETURNING id, event_type, retry_count
                """)

                if retried:
                    logger.info(
                        "EventWatchdog: re-emitting %d failed events for retry",
                        len(retried),
                    )

        except Exception as exc:
            logger.exception("EventWatchdog: cycle failed: %s", exc)

        await asyncio.sleep(WATCHDOG_INTERVAL_SECONDS)
