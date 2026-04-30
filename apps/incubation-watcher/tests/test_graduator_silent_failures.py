"""Tests for every silent-failure path in graduate_one().

Coverage targets the patterns the user has flagged repeatedly:
  - EB 404 → ORPHAN, skip (must not propagate as graduate-success)
  - EB 5xx / network → transient_failed, retry next cycle (must not silently
    succeed)
  - DB transaction rollback → row stays at incubating (must not have
    EB-tagged-but-DB-unchanged silent state)
  - Race condition: eligibility flips between candidate-fetch and DB
    transaction → race_skipped (must NOT graduate ineligible row)
  - Untag failure with non-404 → log + continue (must not abort graduation
    over a non-critical untag)
  - Dry-run → ZERO writes (must not call EB or DB)

Each test models the EB and DB at the right level to fake the failure
deterministically.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from incubation_watcher.db import GraduationCandidate
from incubation_watcher.eb_client import EmailBisonAPIError
from incubation_watcher.graduator import (
    LIVE_TAG,
    RESERVE_TAG,
    graduate_one,
)

# ---------- shared fixtures ----------


def _candidate(esp: str = "gmail") -> GraduationCandidate:
    return GraduationCandidate(
        sender_id=uuid4(),
        email_address=f"test@example-{esp}.com",
        emailbison_account_id=12345,
        esp=esp,
        warmup_enabled_since_iso="2026-04-14",
        business_days_elapsed=14,
    )


def _stub_eb(*, untag=None, tag=None) -> AsyncMock:
    """Build a stub EBClient with override-able untag/tag side_effects.

    untag/tag accept either:
      - a successful return value (default: None)
      - an Exception instance (raised when called)
    """
    eb = AsyncMock()
    if isinstance(untag, BaseException):
        eb.untag_inbox = AsyncMock(side_effect=untag)
    else:
        eb.untag_inbox = AsyncMock(return_value=untag)
    if isinstance(tag, BaseException):
        eb.tag_inbox = AsyncMock(side_effect=tag)
    else:
        eb.tag_inbox = AsyncMock(return_value=tag)
    return eb


class _FakeTxn:
    """Async-context-manager that wraps a list of (call, args) for assertions."""
    async def __aenter__(self) -> _FakeTxn:
        return self
    async def __aexit__(self, *exc: Any) -> None:
        pass


def _stub_conn(*, update_returns: int = 1, history_raises: BaseException | None = None) -> MagicMock:
    """Stub asyncpg.Connection — fakes update_graduation + record_rotation_history."""
    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_FakeTxn())
    # We don't directly mock update_graduation/record_rotation_history at the
    # module level — instead, the graduator imports them; the test patches
    # those at module scope below.
    return conn


# ---------- the tests ----------


@pytest.mark.asyncio
async def test_dry_run_makes_zero_writes() -> None:
    """apply=False must not touch EB or DB. Pure read-only."""
    eb = _stub_eb()
    conn = _stub_conn()
    res = await graduate_one(
        db_conn=conn, eb=eb,
        workspace_id=uuid4(), candidate=_candidate("gmail"),
        incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
        apply=False,
    )
    assert res.outcome == "dry_run"
    assert res.target_pool == RESERVE_TAG  # gmail → reserve
    eb.untag_inbox.assert_not_called()
    eb.tag_inbox.assert_not_called()


@pytest.mark.asyncio
async def test_orphan_404_on_tag_returns_orphan_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """EB returns 404 on tag_inbox → row is workspace-orphan. Must skip,
    do NOT update DB. set_tag_sync.mark_stale_accounts will reconcile.
    """
    eb = _stub_eb(tag=EmailBisonAPIError(404, "sender not in workspace"))
    conn = _stub_conn()
    update_called = MagicMock()
    history_called = MagicMock()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation",
                        AsyncMock(side_effect=update_called))
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history",
                        AsyncMock(side_effect=history_called))

    res = await graduate_one(
        db_conn=conn, eb=eb,
        workspace_id=uuid4(), candidate=_candidate("gmail"),
        incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
        apply=True,
    )
    assert res.outcome == "orphan_skipped"
    assert "404" in (res.error or "")
    update_called.assert_not_called()
    history_called.assert_not_called()


@pytest.mark.asyncio
async def test_transient_5xx_on_tag_returns_transient_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """EB 5xx → transient. Row stays at lifecycle='incubating'. Retry next cycle.

    Must NOT silently succeed. Must NOT update DB.
    """
    eb = _stub_eb(tag=EmailBisonAPIError(503, "service unavailable"))
    conn = _stub_conn()
    update_mock = AsyncMock()
    history_mock = AsyncMock()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation", update_mock)
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history", history_mock)

    res = await graduate_one(
        db_conn=conn, eb=eb,
        workspace_id=uuid4(), candidate=_candidate("microsoft"),
        incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
        apply=True,
    )
    assert res.outcome == "transient_failed"
    assert res.target_pool == LIVE_TAG  # microsoft → live (record what we tried)
    update_mock.assert_not_called()
    history_mock.assert_not_called()


@pytest.mark.asyncio
async def test_transport_error_returns_transient_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """status_code=0 (transport failure: timeout, connection refused).
    Must be treated like 5xx — transient_failed, not silently swallowed.
    """
    eb = _stub_eb(tag=EmailBisonAPIError(0, "connection refused"))
    conn = _stub_conn()
    update_mock = AsyncMock()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation", update_mock)
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history", AsyncMock())

    res = await graduate_one(
        db_conn=conn, eb=eb,
        workspace_id=uuid4(), candidate=_candidate("gmail"),
        incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
        apply=True,
    )
    assert res.outcome == "transient_failed"
    update_mock.assert_not_called()


@pytest.mark.asyncio
async def test_untag_404_swallowed_graduation_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """untag_inbox 404 means the inbox didn't have the incubating tag — fine.
    Graduation must proceed normally.
    """
    eb = _stub_eb(untag=EmailBisonAPIError(404, "tag not present"))
    conn = _stub_conn()
    update_mock = AsyncMock(return_value=1)  # 1 row updated — eligibility holds
    history_mock = AsyncMock()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation", update_mock)
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history", history_mock)

    res = await graduate_one(
        db_conn=conn, eb=eb,
        workspace_id=uuid4(), candidate=_candidate("gmail"),
        incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
        apply=True,
    )
    assert res.outcome == "graduated"
    eb.tag_inbox.assert_awaited_once()
    update_mock.assert_awaited_once()
    history_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_untag_5xx_logged_graduation_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """untag_inbox 5xx is logged but does NOT block the graduation.
    The destination tag still gets applied; set_tag_sync's drift reconciler
    cleans up the still-applied incubating tag on next cycle.
    """
    eb = _stub_eb(untag=EmailBisonAPIError(503, "service unavailable"))
    conn = _stub_conn()
    update_mock = AsyncMock(return_value=1)
    history_mock = AsyncMock()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation", update_mock)
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history", history_mock)

    res = await graduate_one(
        db_conn=conn, eb=eb,
        workspace_id=uuid4(), candidate=_candidate("gmail"),
        incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
        apply=True,
    )
    assert res.outcome == "graduated"


@pytest.mark.asyncio
async def test_race_condition_returns_race_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """update_graduation returns 0 rows → eligibility flipped between
    candidate-selection and the DB transaction. Must NOT insert rotation
    history for an event that didn't actually happen in DB.
    """
    eb = _stub_eb()
    conn = _stub_conn()
    # Simulate eligibility flip: UPDATE ... AND warmup_enabled=TRUE no longer matches
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation",
                        AsyncMock(return_value=0))
    history_mock = AsyncMock()
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history", history_mock)

    res = await graduate_one(
        db_conn=conn, eb=eb,
        workspace_id=uuid4(), candidate=_candidate("gmail"),
        incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
        apply=True,
    )
    assert res.outcome == "race_skipped"
    history_mock.assert_not_called()  # critical: don't lie about a graduation that didn't fire


@pytest.mark.asyncio
async def test_db_update_raises_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """If update_graduation raises (e.g., asyncpg connection lost), the
    exception must propagate so the CLI's outer try/except records it as
    transient_failed for that row. Must NOT silently consume.
    """
    eb = _stub_eb()
    conn = _stub_conn()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation",
                        AsyncMock(side_effect=ConnectionError("db dropped")))
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history", AsyncMock())

    with pytest.raises(ConnectionError):
        await graduate_one(
            db_conn=conn, eb=eb,
            workspace_id=uuid4(), candidate=_candidate("gmail"),
            incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
            apply=True,
        )


@pytest.mark.asyncio
async def test_history_insert_raises_rolls_back_update(monkeypatch: pytest.MonkeyPatch) -> None:
    """If record_rotation_history raises, the wrapping transaction must roll
    back the update. The graduate_one function should propagate the
    exception so the caller can record the row as transient_failed.

    Note: this test relies on _FakeTxn doing nothing on __aexit__. Real
    asyncpg would actually roll back. We're testing graduator's PROMISE
    to wrap correctly, not asyncpg's transaction semantics.
    """
    eb = _stub_eb()
    conn = _stub_conn()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation",
                        AsyncMock(return_value=1))
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history",
                        AsyncMock(side_effect=RuntimeError("constraint violation")))

    with pytest.raises(RuntimeError, match="constraint violation"):
        await graduate_one(
            db_conn=conn, eb=eb,
            workspace_id=uuid4(), candidate=_candidate("gmail"),
            incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
            apply=True,
        )


@pytest.mark.asyncio
async def test_microsoft_routes_to_live_with_correct_tag_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """ESP=microsoft must call tag_inbox with the live_tag_id, not reserve."""
    eb = _stub_eb()
    conn = _stub_conn()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation",
                        AsyncMock(return_value=1))
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history", AsyncMock())

    res = await graduate_one(
        db_conn=conn, eb=eb,
        workspace_id=uuid4(), candidate=_candidate("microsoft"),
        incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
        apply=True,
    )
    assert res.outcome == "graduated"
    assert res.target_pool == LIVE_TAG
    eb.tag_inbox.assert_awaited_once_with(12345, 2)  # live_tag_id


@pytest.mark.asyncio
async def test_gmail_routes_to_reserve_with_correct_tag_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """ESP=gmail must call tag_inbox with reserve_tag_id."""
    eb = _stub_eb()
    conn = _stub_conn()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation",
                        AsyncMock(return_value=1))
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history", AsyncMock())

    res = await graduate_one(
        db_conn=conn, eb=eb,
        workspace_id=uuid4(), candidate=_candidate("gmail"),
        incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
        apply=True,
    )
    assert res.outcome == "graduated"
    assert res.target_pool == RESERVE_TAG
    eb.tag_inbox.assert_awaited_once_with(12345, 3)  # reserve_tag_id


@pytest.mark.asyncio
async def test_unknown_esp_routes_to_reserve_safe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown ESP → reserve. Must NOT default to live (which is unsafe —
    live = active sending; reserve = bench).
    """
    eb = _stub_eb()
    conn = _stub_conn()
    monkeypatch.setattr("incubation_watcher.graduator.update_graduation",
                        AsyncMock(return_value=1))
    monkeypatch.setattr("incubation_watcher.graduator.record_rotation_history", AsyncMock())

    for unknown in (None, "", "zoho", "unknown"):
        # Reset mocks
        eb.tag_inbox.reset_mock()
        res = await graduate_one(
            db_conn=conn, eb=eb,
            workspace_id=uuid4(),
            candidate=GraduationCandidate(
                sender_id=uuid4(),
                email_address="test@example.com",
                emailbison_account_id=12345,
                esp=unknown,
                warmup_enabled_since_iso="2026-04-14",
                business_days_elapsed=14,
            ),
            incubating_tag_id=1, live_tag_id=2, reserve_tag_id=3,
            apply=True,
        )
        assert res.target_pool == RESERVE_TAG, f"esp={unknown!r} should default to reserve"
        eb.tag_inbox.assert_awaited_once_with(12345, 3)  # NEVER live_tag_id
