"""
Day.AI integration layer for charm-email-os.

Shared Python client + typed objects for building automations against Day.AI.
First consumer: dayai_watcher_worker.py (closed-won detector). Future consumers
will live alongside and import from this package.

Public API:
    from dayai import DayAIClient, OpportunitySnapshot, DayAIAuthError

Architecture:
    auth.py    — OAuth2 refresh (POST /api/oauth, refresh_token grant)
    mcp.py     — JSON-RPC 2.0 MCP wrapper (POST /api/mcp)
    client.py  — High-level DayAIClient with typed convenience methods
    objects.py — Typed snapshots: OpportunitySnapshot, etc.

Read-only by policy: this package MUST NOT call create/update/delete MCP tools.
Enforced by SECURITY_FOLLOWUPS §2.3 (code-level binding). Only read tools:
    search_objects, get_meeting_recording_context, read_crm_schema
"""

from .auth import DayAIAuthError, DayAICredentials
from .client import DayAIClient
from .objects import OpportunitySnapshot, normalize_opportunity

__all__ = [
    "DayAIClient",
    "DayAICredentials",
    "DayAIAuthError",
    "OpportunitySnapshot",
    "normalize_opportunity",
]
