"""
Workspace-scoped EmailBison API client — minimal subset for EOD reapply.

Only implements the 8 endpoints needed by the orchestrator. Self-contained so
this app has no import-time dependency on charm-email-os/sync_modules.

The api_key is the per-workspace Sanctum token from `workspace_api_keys`. The
token bakes the workspace context — no switch_workspace() calls anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

# Pagination safety: we should never see anywhere near this many pages, but
# never loop forever on a malformed `meta.last_page`.
_PAGINATION_SAFETY_LIMIT = 1000


class EmailBisonAPIError(Exception):
    """Raised on any non-2xx response or transport error.

    `status_code=0` means the request never produced an HTTP response
    (timeout, connection refused, etc.).
    """

    def __init__(self, status_code: int, message: str, response_body: Any = None):
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"EB API {status_code}: {message}")


@dataclass(frozen=True)
class _Endpoint:
    method: str
    path: str


class EBClient:
    """Async context-managed client. Construct with workspace API key; reuse for
    one operator run. Every request carries `Authorization: Bearer <api_key>`.
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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if self._client is None:
            raise RuntimeError("EBClient must be used as an async context manager")
        url = f"{self.base_url}{path}"
        try:
            resp = await self._client.request(method, url, params=params, json=json)
        except httpx.TimeoutException as e:
            raise EmailBisonAPIError(0, f"Timeout calling {method} {path}: {e}") from e
        except httpx.RequestError as e:
            raise EmailBisonAPIError(0, f"Network error calling {method} {path}: {e}") from e

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise EmailBisonAPIError(
                resp.status_code,
                f"{method} {path} returned {resp.status_code}",
                body,
            )

        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        """EB wraps successful responses as `{"data": ...}` for most endpoints
        but returns bare arrays for some. Normalize to inner content."""
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    # ========================================================================
    # Campaigns
    # ========================================================================

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        """GET /api/campaigns/{id} — full campaign incl. status."""
        result = await self._request("GET", f"/api/campaigns/{campaign_id}")
        return self._unwrap(result) or {}

    async def get_campaign_schedule(self, campaign_id: int) -> dict[str, Any]:
        """GET /api/campaigns/{id}/schedule — read-only, never write."""
        result = await self._request("GET", f"/api/campaigns/{campaign_id}/schedule")
        return self._unwrap(result) or {}

    async def pause_campaign(self, campaign_id: int) -> dict[str, Any]:
        """PATCH /api/campaigns/{id}/pause."""
        result = await self._request("PATCH", f"/api/campaigns/{campaign_id}/pause")
        return self._unwrap(result) or {}

    async def resume_campaign(self, campaign_id: int) -> dict[str, Any]:
        """PATCH /api/campaigns/{id}/resume."""
        result = await self._request("PATCH", f"/api/campaigns/{campaign_id}/resume")
        return self._unwrap(result) or {}

    async def get_campaign_senders(self, campaign_id: int) -> list[dict[str, Any]]:
        """GET /api/campaigns/{id}/sender-emails — currently attached senders."""
        result = await self._request("GET", f"/api/campaigns/{campaign_id}/sender-emails")
        unwrapped = self._unwrap(result)
        if unwrapped is None:
            return []
        if not isinstance(unwrapped, list):
            raise EmailBisonAPIError(
                0,
                f"Expected list from get_campaign_senders, got {type(unwrapped).__name__}",
                unwrapped,
            )
        return unwrapped

    async def attach_senders(self, campaign_id: int, sender_email_ids: list[int]) -> dict[str, Any]:
        """POST /api/campaigns/{id}/attach-sender-emails."""
        if not sender_email_ids:
            raise ValueError("sender_email_ids must not be empty")
        result = await self._request(
            "POST",
            f"/api/campaigns/{campaign_id}/attach-sender-emails",
            json={"sender_email_ids": sender_email_ids},
        )
        return result or {}

    async def remove_senders(self, campaign_id: int, sender_email_ids: list[int]) -> dict[str, Any]:
        """DELETE /api/campaigns/{id}/remove-sender-emails."""
        if not sender_email_ids:
            raise ValueError("sender_email_ids must not be empty")
        result = await self._request(
            "DELETE",
            f"/api/campaigns/{campaign_id}/remove-sender-emails",
            json={"sender_email_ids": sender_email_ids},
        )
        return result or {}

    # ========================================================================
    # Sender emails (workspace-scoped, tag-filtered)
    # ========================================================================

    async def list_senders_with_tag(
        self,
        tag_id: int,
        *,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """GET /api/sender-emails?tag_ids[0]={tag_id} — paginated.

        Returns the full list of senders that have the given tag. The orchestrator
        uses this to compute the target attachment set (the 'live' tag).

        Pagination terminates when:
          - response is a bare list (single page)
          - meta.last_page is reached
          - meta.last_page is missing (defensive — assume single page)
          - empty data array
          - safety limit (_PAGINATION_SAFETY_LIMIT) reached → raises
        """
        all_senders: list[dict[str, Any]] = []
        for page in range(1, _PAGINATION_SAFETY_LIMIT + 1):
            params: dict[str, Any] = {
                "tag_ids[0]": tag_id,
                "page": page,
                "per_page": per_page,
            }
            result = await self._request("GET", "/api/sender-emails", params=params)

            if isinstance(result, list):
                # Bare-list response — no pagination metadata available.
                all_senders.extend(result)
                break

            if not isinstance(result, dict):
                raise EmailBisonAPIError(
                    0,
                    f"Unexpected sender-emails response shape: {type(result).__name__}",
                    result,
                )

            data = result.get("data", [])
            if not data:
                break
            all_senders.extend(data)

            meta = result.get("meta") or {}
            last_page = meta.get("last_page")
            if last_page is None:
                # Defensive: no pagination metadata, stop after one page rather than risk a loop.
                break
            if page >= int(last_page):
                break
        else:
            raise EmailBisonAPIError(
                0,
                f"Pagination safety limit ({_PAGINATION_SAFETY_LIMIT}) exceeded for /api/sender-emails",
            )

        return all_senders

    # ========================================================================
    # Tags
    # ========================================================================

    async def get_workspace_tags(self) -> list[dict[str, Any]]:
        """GET /api/tags — list all tags for the current workspace.

        Used to resolve the 'live' tag id once per run.
        """
        result = await self._request("GET", "/api/tags")
        unwrapped = self._unwrap(result)
        if unwrapped is None:
            return []
        if not isinstance(unwrapped, list):
            raise EmailBisonAPIError(
                0,
                f"Expected list from get_workspace_tags, got {type(unwrapped).__name__}",
                unwrapped,
            )
        return unwrapped

    async def resolve_tag_id(self, tag_name: str) -> int | None:
        """Convenience: find the numeric id of a tag by exact-match name.
        Returns None if not found.
        """
        tags = await self.get_workspace_tags()
        for t in tags:
            if t.get("name") == tag_name and "id" in t:
                return int(t["id"])
        return None
