"""
JSON-RPC 2.0 wrapper for Day.AI's MCP endpoint.

Day.AI exposes its CRM via Model Context Protocol over HTTP at /api/mcp.
All calls are JSON-RPC 2.0 POSTs:

    { "jsonrpc": "2.0", "id": <num>, "method": <str>, "params": <obj> }

Key methods:
    initialize          — handshake (required before tools/call)
    tools/list          — introspection (debug use)
    tools/call          — invoke a tool by name with args

Tool call returns { content: [{ type: "text", text: "<json-encoded result>" }] }.
The `text` field is a string that must be json.loads()'d to get the real payload.

This module is read-only by contract — see dayai/__init__.py docstring.
"""
from __future__ import annotations

import itertools
import json
import logging
from typing import Any

import httpx

from .auth import AccessTokenCache, DayAIAuthError

logger = logging.getLogger(__name__)


# Read-only tool allowlist. Enforced at the Python boundary to make accidental
# write calls fail fast. Adding a tool here requires explicit security review.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "search_objects",
        "get_meeting_recording_context",
        "read_crm_schema",
        "keyword_search",
        "whoami",
    }
)


class DayAIMCPError(Exception):
    """Raised when an MCP call fails (HTTP error, JSON-RPC error, or tool error)."""


class MCPClient:
    """
    Thin JSON-RPC 2.0 client for Day.AI's /api/mcp endpoint.

    Performs lazy initialize() on first tool call. Handles token refresh on 401
    by invalidating the cache and retrying once.
    """

    _JSONRPC_VERSION = "2.0"
    _PROTOCOL_VERSION = "2025-06-18"

    def __init__(
        self,
        base_url: str,
        token_cache: AccessTokenCache,
        http: httpx.AsyncClient,
        client_info: dict[str, str] | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._token_cache = token_cache
        self._http = http
        self._client_info = client_info or {
            "name": "charm-email-os dayai worker",
            "version": "0.1.0",
        }
        self._initialized = False
        self._id_counter = itertools.count(1)

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Invoke an MCP tool by name. Returns the parsed JSON payload from the
        tool's text response.

        Raises:
            DayAIMCPError: on any failure (HTTP, JSON-RPC, or tool error).
            ValueError: if `name` is not in ALLOWED_TOOLS.
        """
        if name not in ALLOWED_TOOLS:
            raise ValueError(
                f"Tool {name!r} is not in the read-only allowlist. "
                f"Allowed: {sorted(ALLOWED_TOOLS)}. Security policy prohibits "
                "adding mutation tools without explicit review."
            )

        if not self._initialized:
            await self._initialize()

        result = await self._request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )
        # Tool result shape: { content: [{ type: "text", text: "<json>" }] }
        content = result.get("content", [])
        if not content:
            raise DayAIMCPError(f"Tool {name} returned no content")
        text = content[0].get("text")
        if text is None:
            raise DayAIMCPError(f"Tool {name} content[0] missing 'text' field")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise DayAIMCPError(
                f"Tool {name} returned non-JSON text: {e} — first 200 chars: {text[:200]!r}"
            ) from e

    async def _initialize(self) -> None:
        """MCP handshake. Idempotent per-instance."""
        await self._request(
            "initialize",
            {
                "protocolVersion": self._PROTOCOL_VERSION,
                "clientInfo": self._client_info,
                "capabilities": {"tools": {}, "resources": {}},
            },
        )
        self._initialized = True
        logger.info("MCP initialized against %s", self._base_url)

    async def _request(self, method: str, params: Any) -> dict[str, Any]:
        """
        Send a JSON-RPC 2.0 request. Retries once on 401 (token expired).

        Returns the `result` field of a successful JSON-RPC response.
        Raises DayAIMCPError on HTTP error, JSON-RPC error, or missing result.
        """
        payload = {
            "jsonrpc": self._JSONRPC_VERSION,
            "id": next(self._id_counter),
            "method": method,
            "params": params,
        }

        for attempt in (1, 2):  # retry-once semantic on 401
            access_token = await self._token_cache.get()
            resp = await self._http.post(
                f"{self._base_url}/api/mcp",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
            if resp.status_code == 401 and attempt == 1:
                logger.warning("MCP returned 401; invalidating token and retrying")
                await self._token_cache.invalidate()
                continue
            if resp.status_code != 200:
                raise DayAIMCPError(
                    f"MCP {method} HTTP {resp.status_code}: {resp.text[:500]}"
                )
            body = resp.json()
            if body.get("jsonrpc") != "2.0":
                raise DayAIMCPError(
                    f"MCP response is not JSON-RPC 2.0: got {body.get('jsonrpc')!r}"
                )
            if "error" in body:
                err = body["error"]
                raise DayAIMCPError(
                    f"JSON-RPC error {err.get('code')}: {err.get('message')} "
                    f"(data={err.get('data')!r})"
                )
            if "result" not in body:
                raise DayAIMCPError(f"MCP response missing 'result' field: {body}")
            return body["result"]

        # Should be unreachable
        raise DayAIMCPError("MCP request failed after retry")
