"""Asyncio cancellation tests for the reapply orchestrator.

The L3 invariant tests prove that on EmailBisonAPIError mid-flight, the
finally block's resume call still fires. But that's a synchronous-throw
case. asyncio cancellation (Ctrl-C, supervisor shutdown, parent task
cancel) is a different beast — the cancellation propagates through every
await point.

Python's contract: finally blocks DO run when a task is cancelled, but
each await inside the finally is itself cancellable. So if our
resume_campaign call is awaited inside finally and a CancelledError
is propagating, the resume call could itself be cancelled.

These tests prove:
  - When the orchestrator is cancelled mid-attach, the finally block runs.
  - The resume_campaign call is reached (and recorded by the fake).
  - CancelledError eventually propagates out of reapply_campaign (we don't
    swallow it — the caller still sees the cancellation).

Real production semantics (what the operator sees on Ctrl-C):
  Without asyncio.shield() in finally, a re-raised CancelledError after
  resume completes is the expected behavior. This test confirms resume
  RUNS — not that the CancelledError stays internal.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from eod_reapply.reapply import reapply_campaign

INSIDE_SYDNEY_WINDOW = datetime(2026, 1, 15, 7, 0, tzinfo=UTC)


class _CancellingFakeEB:
    """Fake EB client that triggers a cancellation when attach is called.

    The pattern: attach awaits a future that gets cancelled, simulating
    real-world conditions where the operator hits Ctrl-C while attach is
    in flight.
    """

    def __init__(self):
        self.calls: list[str] = []
        self._attach_started = asyncio.Event()
        self._cancellation_signal: asyncio.Event = asyncio.Event()

    async def __aenter__(self): return self
    async def __aexit__(self, *exc): pass

    async def get_campaign(self, cid):
        self.calls.append("get_campaign")
        return {"id": cid, "status": "Active"}

    async def get_campaign_schedule(self, cid):
        self.calls.append("get_campaign_schedule")
        return {
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True, "saturday": False, "sunday": False,
            "start_time": "08:00", "end_time": "17:00",
            "timezone": "Australia/Sydney",
        }

    async def resolve_tag_id(self, name):
        self.calls.append("resolve_tag_id")
        return 5

    async def list_senders_with_tag(self, tag_id, *, per_page=100):
        self.calls.append("list_senders_with_tag")
        return [{"id": 10}, {"id": 11}, {"id": 12}]

    async def get_campaign_senders(self, cid):
        self.calls.append("get_campaign_senders")
        # First call (prior): {11, 99} — diff: attach 10,12; remove 99
        # Second call won't happen (we cancel before verify)
        return [{"id": 11}, {"id": 99}]

    async def pause_campaign(self, cid):
        self.calls.append("pause_campaign")
        return {"id": cid, "status": "Paused"}

    async def attach_senders(self, cid, ids):
        self.calls.append("attach_senders")
        # Signal that attach is in flight, then block until cancelled
        self._attach_started.set()
        try:
            await self._cancellation_signal.wait()
        except asyncio.CancelledError:
            self.calls.append("attach_cancelled")
            raise
        return {"success": True}

    async def remove_senders(self, cid, ids):
        self.calls.append("remove_senders")
        return {"success": True}

    async def resume_campaign(self, cid):
        self.calls.append("resume_campaign")
        return {"id": cid, "status": "Queued"}


class TestCancellationDuringAttach:
    """The CRITICAL real-world test: operator Ctrl-Cs while attach is in flight.
    The finally clause must fire and resume must be called.
    """

    async def test_cancellation_during_attach_runs_finally(self):
        eb = _CancellingFakeEB()

        # Wrap the orchestrator in a task we can cancel
        task = asyncio.create_task(reapply_campaign(
            eb=eb,
            workspace_name="Charm",
            campaign_id=1,
            apply=True,
            skip_time_check=False,
            now_utc=INSIDE_SYDNEY_WINDOW,
        ))

        # Wait until attach is in flight
        await eb._attach_started.wait()
        assert "attach_senders" in eb.calls
        assert "resume_campaign" not in eb.calls  # finally hasn't run yet

        # Cancel the task — like Ctrl-C from operator
        task.cancel()

        # The task should have run its finally clause and propagated CancelledError
        with pytest.raises(asyncio.CancelledError):
            await task

        # CRITICAL ASSERTIONS:
        # 1. attach was cancelled (the await inside attach raised)
        assert "attach_cancelled" in eb.calls, (
            f"attach should have observed cancellation. calls={eb.calls}"
        )
        # 2. The resume_campaign call in finally STILL fired despite cancellation
        # Note: this is the load-bearing test — it proves Python's finally semantics
        # work as expected for our orchestrator.
        assert "resume_campaign" in eb.calls, (
            f"INVARIANT VIOLATED: finally block did not run resume_campaign on "
            f"cancellation. calls={eb.calls}"
        )
        # 3. Order: attach must have started before resume in finally
        attach_idx = eb.calls.index("attach_senders")
        resume_idx = eb.calls.index("resume_campaign")
        assert attach_idx < resume_idx
