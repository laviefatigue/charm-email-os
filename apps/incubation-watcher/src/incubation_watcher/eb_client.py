"""Workspace-scoped EmailBison API client — minimal subset for incubation graduation.

Only implements the endpoints needed to:
  - Resolve tag IDs (`/tags`)
  - Tag/untag senders (`/sender-emails/{id}/tags`)

The api_key is the per-workspace Sanctum token from `workspace_api_keys`. The
token bakes the workspace context — no switch_workspace() calls anywhere.

Mirrors apps/eod-reapply/src/eod_reapply/eb_client.py error handling:
  - `EmailBisonAPIError(status_code, message)` raised on any non-2xx
  - status_code=0 means transport error (timeout, connection refused)
  - 404 must be distinguishable so callers can swallow expected-absent cases
"""
from __future__ import annotations

from typing import Any

import httpx


class EmailBisonAPIError(Exception):
    """Raised on any non-2xx response or transport error."""

    def __init__(self, status_code: int, message: str, response_body: Any = None):
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"EB API {status_code}: {message}")


class EBClient:
    """Async context-managed client. Construct with workspace API key; reuse
    for one operator run. Every request carries `Authorization: Bearer <key>`.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not api_key:
            raise ValueError("api_key is required")
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> EBClient:
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers=self._headers,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("EBClient must be used as async context manager")
        return self._client

    async def list_tags(self) -> list[dict[str, Any]]:
        """List all tags in this workspace. Returns raw EB tag objects."""
        client = self._ensure_client()
        try:
            r = await client.get(f"{self.base_url}/tags")
        except httpx.TransportError as e:
            raise EmailBisonAPIError(0, f"transport: {e}") from e
        if r.status_code != 200:
            raise EmailBisonAPIError(r.status_code, "list_tags failed", _safe_json(r))
        body = r.json()
        return list(body.get("data", []))

    async def get_or_create_tag_id(self, name: str) -> int:
        """Return the tag_id for `name`, creating it if not present.

        Lookup is exact-match on tag name. Case-sensitive — EB does NOT
        normalize, so 'live' and 'Live' are distinct tags. Caller should
        only pass canonical lowercase names: 'incubating', 'live', 'reserve'.
        """
        existing = await self.list_tags()
        for t in existing:
            if t.get("name") == name:
                return int(t["id"])
        # Create
        client = self._ensure_client()
        try:
            r = await client.post(f"{self.base_url}/tags", json={"name": name})
        except httpx.TransportError as e:
            raise EmailBisonAPIError(0, f"transport: {e}") from e
        if r.status_code not in (200, 201):
            raise EmailBisonAPIError(r.status_code, f"create tag {name!r}", _safe_json(r))
        return int(r.json()["data"]["id"])

    async def tag_inbox(self, account_id: int, tag_id: int) -> None:
        """Apply a tag to a sender. Idempotent in EB — re-applying is fine."""
        client = self._ensure_client()
        try:
            r = await client.post(
                f"{self.base_url}/sender-emails/{account_id}/tags",
                json={"tag_id": tag_id},
            )
        except httpx.TransportError as e:
            raise EmailBisonAPIError(0, f"transport: {e}") from e
        if r.status_code not in (200, 201, 204):
            raise EmailBisonAPIError(r.status_code, f"tag_inbox {account_id} -> {tag_id}", _safe_json(r))

    async def untag_inbox(self, account_id: int, tag_id: int) -> None:
        """Remove a tag from a sender. 404 means tag wasn't present (caller's
        problem to interpret).
        """
        client = self._ensure_client()
        try:
            r = await client.delete(
                f"{self.base_url}/sender-emails/{account_id}/tags/{tag_id}",
            )
        except httpx.TransportError as e:
            raise EmailBisonAPIError(0, f"transport: {e}") from e
        if r.status_code not in (200, 204):
            raise EmailBisonAPIError(r.status_code, f"untag_inbox {account_id} -> {tag_id}", _safe_json(r))


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return r.text[:500]
