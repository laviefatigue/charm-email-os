"""
High-level Day.AI client. The entry point for all charm-email-os automations.

Usage:
    async with DayAIClient.from_env() as client:
        opps = await client.list_opportunities_in_stages(["stage-uuid"])
        for opp in opps:
            ... # opp is an OpportunitySnapshot

One client instance is expected per worker process. The underlying httpx
connection pool + access-token cache live for the lifetime of the client.

Read-only by contract — see module docstrings in dayai/__init__.py and
dayai/mcp.py. Mutation is enforced to fail at the MCP layer.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .auth import AccessTokenCache, DayAICredentials
from .mcp import MCPClient
from .objects import OpportunitySnapshot, normalize_opportunity

logger = logging.getLogger(__name__)


class DayAIClient:
    """
    High-level async client for Day.AI.

    Construct via `DayAIClient.from_env()` to load credentials from standard
    env vars, or pass `DayAICredentials` directly for testing.
    """

    # Max pages to fetch in a paginated search. 50 pages × ~100/page = 5000
    # opps — well beyond any realistic pipeline. A larger stage should surface
    # as a warning, not silently truncate.
    _MAX_PAGES = 50

    def __init__(self, creds: DayAICredentials, http: httpx.AsyncClient | None = None):
        self._creds = creds
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        self._token_cache = AccessTokenCache(creds, self._http)
        self._mcp = MCPClient(creds.base_url, self._token_cache, self._http)

    @classmethod
    def from_env(cls) -> "DayAIClient":
        return cls(DayAICredentials.from_env())

    async def __aenter__(self) -> "DayAIClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # ---- typed convenience methods --------------------------------------------------

    async def list_opportunities_in_stages(
        self, stage_ids: list[str]
    ) -> list[OpportunitySnapshot]:
        """
        Return all opportunities currently in any of the given stage IDs.

        Paginates automatically. Day.AI's search_objects filter operators don't
        include `in`, so we use `eq` for single-stage and an OR list of `eq`
        for multi-stage — mirrors the Node watcher's behavior.
        """
        if not stage_ids:
            logger.warning("list_opportunities_in_stages called with empty stage_ids")
            return []

        if len(stage_ids) == 1:
            where_clause: dict[str, Any] = {
                "propertyId": "stageId",
                "operator": "eq",
                "value": stage_ids[0],
            }
        else:
            where_clause = {
                "or": [
                    {"propertyId": "stageId", "operator": "eq", "value": sid}
                    for sid in stage_ids
                ]
            }

        all_opps: list[OpportunitySnapshot] = []
        offset = 0
        for page_num in range(self._MAX_PAGES):
            parsed = await self._mcp.call_tool(
                "search_objects",
                {
                    "queries": [
                        {"objectType": "native_opportunity", "where": where_clause}
                    ],
                    "propertiesToReturn": "*",
                    "includeRelationships": True,
                    "offset": offset,
                },
            )

            # Response shape:
            # { offset, totalRecords, hasMore, nextOffset,
            #   native_opportunity: { results: [...] } }
            bucket = parsed.get("native_opportunity") or {}
            page_results = bucket.get("results") or []

            for raw in page_results:
                if not isinstance(raw, dict):
                    logger.warning("skipping non-dict opportunity result: %r", type(raw))
                    continue
                all_opps.append(normalize_opportunity(raw))

            logger.debug(
                "opportunities page fetched page=%d offset=%d got=%d total=%s has_more=%s",
                page_num,
                offset,
                len(page_results),
                parsed.get("totalRecords"),
                parsed.get("hasMore"),
            )

            if not parsed.get("hasMore") or not page_results:
                break
            next_offset = parsed.get("nextOffset")
            if next_offset is None:
                break
            offset = int(next_offset)
        else:
            logger.warning(
                "list_opportunities_in_stages hit MAX_PAGES=%d — possible truncation",
                self._MAX_PAGES,
            )

        logger.info(
            "fetched %d opportunities across %d stage(s)", len(all_opps), len(stage_ids)
        )
        return all_opps

    async def whoami(self) -> dict[str, Any]:
        """Diagnostic: returns the authenticated workspace/user identity."""
        return await self._mcp.call_tool("whoami", {})

    # ---- escape hatch for ad-hoc tool calls (still allowlist-enforced) --------------

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Call any read-only MCP tool by name. ValueError if `name` is not in
        dayai.mcp.ALLOWED_TOOLS.

        Prefer typed methods above. Use this for exploratory work or tools we
        haven't wrapped yet (read_crm_schema, get_meeting_recording_context, etc.).
        """
        return await self._mcp.call_tool(name, arguments)
