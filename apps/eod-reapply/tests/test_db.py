"""Tests for db.fetch_workspace_context.

Mocks asyncpg.Connection — verifies SQL query shape and result mapping.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from eod_reapply.db import WorkspaceContext, fetch_workspace_context


class FakeConn:
    """Minimal asyncpg.Connection stand-in: records fetchrow calls, returns scripted row."""

    def __init__(self, row=None):
        self._row = row
        self.fetchrow_calls: list[tuple] = []

    async def fetchrow(self, query: str, *args):
        self.fetchrow_calls.append((query, args))
        return self._row


class TestFetchWorkspaceContext:
    async def test_returns_context_when_row_found(self):
        ws_id = uuid4()
        conn = FakeConn(row={
            "workspace_id": ws_id,
            "workspace_name": "Charm",
            "emailbison_workspace_id": "42",
            "api_key": "test-key-deadbeef",
        })
        result = await fetch_workspace_context(conn, "Charm")
        assert result is not None
        assert isinstance(result, WorkspaceContext)
        assert result.workspace_id == ws_id
        assert result.workspace_name == "Charm"
        assert result.emailbison_workspace_id == "42"
        assert result.api_key == "test-key-deadbeef"

    async def test_returns_none_when_row_missing(self):
        conn = FakeConn(row=None)
        result = await fetch_workspace_context(conn, "DOES_NOT_EXIST")
        assert result is None

    async def test_query_filters_by_workspace_name(self):
        conn = FakeConn(row=None)
        await fetch_workspace_context(conn, "Sammy")
        assert len(conn.fetchrow_calls) == 1
        query, args = conn.fetchrow_calls[0]
        assert args == ("Sammy",)
        # Query must filter on the active+API-key+active-workspace conditions
        assert "is_active = TRUE" in query
        assert "workspace_name = $1" in query
        assert "JOIN workspace_api_keys" in query

    async def test_query_uses_key_token_column(self):
        # Critical: must read from key_token, not api_key or api_key_encrypted
        conn = FakeConn(row=None)
        await fetch_workspace_context(conn, "Charm")
        query = conn.fetchrow_calls[0][0]
        assert "k.key_token" in query
        # Should NOT use the wrong column name
        assert "api_key_encrypted" not in query

    async def test_emailbison_workspace_id_can_be_null(self):
        conn = FakeConn(row={
            "workspace_id": uuid4(),
            "workspace_name": "TestWS",
            "emailbison_workspace_id": None,
            "api_key": "x",
        })
        result = await fetch_workspace_context(conn, "TestWS")
        assert result is not None
        assert result.emailbison_workspace_id is None
