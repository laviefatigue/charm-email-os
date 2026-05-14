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

    async def get_campaign_senders(
        self,
        campaign_id: int,
        *,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """GET /api/campaigns/{id}/sender-emails — currently attached senders.

        Paginated. Real production observation (verified against Sammy #63):
        a single campaign can have hundreds of attached senders (634 in 43 pages
        of 15 each). The OpenAPI spec doesn't document the pagination shape for
        this endpoint, but the real response is the same Laravel paginated
        wrapper as /api/sender-emails: {"data": [...], "meta": {"last_page": N,
        "current_page": M, "total": T, "per_page": P}}.

        Server may cap per_page (observed default ~15). Our request asks for 100
        but we still loop pages until last_page is reached.

        Pagination terminates when:
          - response is a bare list (single page, no meta)
          - meta.last_page is reached
          - meta.last_page is missing (defensive — assume single page)
          - safety limit reached → raises
        """
        all_attached: list[dict[str, Any]] = []
        # Captured from page 1's meta. If set, we'll verify len(all_attached) == expected_total
        # at the end to guard against silent mid-pagination truncation (the exact class of bug
        # that hid /api/campaigns/{id}/sender-emails pagination from us in the first place).
        expected_total: int | None = None
        # If the first page is a bare list (no meta), we have no way to validate count — but
        # we also know the endpoint isn't paginating, so a single page is the whole thing.
        is_paginated = False

        for page in range(1, _PAGINATION_SAFETY_LIMIT + 1):
            params: dict[str, Any] = {"page": page, "per_page": per_page}
            result = await self._request(
                "GET",
                f"/api/campaigns/{campaign_id}/sender-emails",
                params=params,
            )

            if result is None:
                # 204 / empty body. Acceptable on page 1 (truly empty campaign).
                # Acceptable on page > 1 ONLY if we already saw page N-1 (i.e. we're about
                # to break naturally). If we expected more pages and got 204, that's silent
                # truncation — fail loud.
                if page == 1:
                    break
                if expected_total is not None and len(all_attached) < expected_total:
                    raise EmailBisonAPIError(
                        0,
                        f"page {page} returned empty body but expected_total={expected_total} "
                        f"and only {len(all_attached)} collected; possible silent truncation",
                    )
                break

            if isinstance(result, list):
                # Bare list — no pagination metadata. Only valid on page 1.
                if page > 1:
                    raise EmailBisonAPIError(
                        0,
                        f"page {page} returned bare list but earlier pages were paginated; "
                        f"response shape changed mid-pagination",
                    )
                all_attached.extend(result)
                break

            if not isinstance(result, dict):
                raise EmailBisonAPIError(
                    0,
                    f"Unexpected campaign senders response shape on page {page}: {type(result).__name__}",
                    result,
                )

            data = result.get("data")
            if data is None:
                # data missing. Acceptable on page 1 with bare-list-shaped result; otherwise
                # silent truncation territory. If we already started paginating and lose data,
                # fail loud.
                if is_paginated:
                    raise EmailBisonAPIError(
                        0,
                        f"page {page} response has no 'data' field but earlier pages did; "
                        f"shape changed mid-pagination",
                    )
                # First page, _unwrap-fallback path — accept and finish
                unwrapped = self._unwrap(result)
                if isinstance(unwrapped, list):
                    all_attached.extend(unwrapped)
                break

            if not isinstance(data, list):
                raise EmailBisonAPIError(
                    0,
                    f"Expected list under 'data' from get_campaign_senders page {page}, got {type(data).__name__}",
                    data,
                )
            all_attached.extend(data)

            meta = result.get("meta") or {}
            last_page = meta.get("last_page")
            total = meta.get("total")

            if page == 1 and last_page is not None:
                is_paginated = True
                if total is not None:
                    expected_total = int(total)

            if last_page is None:
                # No pagination metadata: should only happen on a single-page response.
                # If we're already paginating (saw last_page on page 1), losing it mid-stream
                # is silent truncation.
                if is_paginated:
                    raise EmailBisonAPIError(
                        0,
                        f"page {page} response missing meta.last_page but earlier pages had it; "
                        f"shape changed mid-pagination",
                    )
                break
            if page >= int(last_page):
                break
        else:
            raise EmailBisonAPIError(
                0,
                f"Pagination safety limit ({_PAGINATION_SAFETY_LIMIT}) exceeded for campaign {campaign_id} senders",
            )

        # Final consistency check: if the server told us a total, verify we collected it all.
        # Mid-fetch concurrent changes are extremely rare for campaign sender lists; a mismatch
        # is far more likely to be a server bug or pagination-shape inconsistency than benign
        # drift. Fail loud rather than return wrong data.
        if expected_total is not None and len(all_attached) != expected_total:
            raise EmailBisonAPIError(
                0,
                f"pagination collected {len(all_attached)} senders but meta.total={expected_total} "
                f"on campaign {campaign_id}; data may be incomplete or inconsistent",
            )

        return all_attached

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

        Pagination contract (matches Laravel paginator shape on EB):
          {"data": [...], "meta": {"current_page", "last_page", "per_page", "total", ...}}
          We track meta.total from page 1 and verify len(collected) == total at the end.
          Mid-pagination shape changes (data missing, meta.last_page lost, response becomes
          a bare list) raise — silent truncation is the bug class that hid Sammy #63's 634
          attached senders behind a single 15-row page response.

        Pagination terminates when:
          - First response is a bare list (single page, no meta)
          - meta.last_page is reached
          - meta.last_page is missing AND we never started paginating (single-page response)
          - safety limit (_PAGINATION_SAFETY_LIMIT) reached → raises
        """
        all_senders: list[dict[str, Any]] = []
        expected_total: int | None = None
        is_paginated = False

        for page in range(1, _PAGINATION_SAFETY_LIMIT + 1):
            params: dict[str, Any] = {
                "tag_ids[0]": tag_id,
                "page": page,
                "per_page": per_page,
            }
            result = await self._request("GET", "/api/sender-emails", params=params)

            if result is None:
                if page == 1:
                    break
                if expected_total is not None and len(all_senders) < expected_total:
                    raise EmailBisonAPIError(
                        0,
                        f"page {page} returned empty body but expected_total={expected_total} "
                        f"and only {len(all_senders)} collected; possible silent truncation",
                    )
                break

            if isinstance(result, list):
                if page > 1:
                    raise EmailBisonAPIError(
                        0,
                        f"page {page} returned bare list but earlier pages were paginated; "
                        f"shape changed mid-pagination",
                    )
                all_senders.extend(result)
                break

            if not isinstance(result, dict):
                raise EmailBisonAPIError(
                    0,
                    f"Unexpected sender-emails response shape on page {page}: {type(result).__name__}",
                    result,
                )

            data = result.get("data", [])
            if not isinstance(data, list):
                raise EmailBisonAPIError(
                    0,
                    f"Expected list under 'data' on page {page}, got {type(data).__name__}",
                    data,
                )
            all_senders.extend(data)
            # Empty data array is a natural terminator — but only after we've recorded the meta
            # check below. So don't early-break here.

            meta = result.get("meta") or {}
            last_page = meta.get("last_page")
            total = meta.get("total")

            if page == 1 and last_page is not None:
                is_paginated = True
                if total is not None:
                    expected_total = int(total)

            if last_page is None:
                if is_paginated:
                    raise EmailBisonAPIError(
                        0,
                        f"page {page} response missing meta.last_page but earlier pages had it; "
                        f"shape changed mid-pagination",
                    )
                break
            if not data:
                # Empty data array on a paginated response — only valid if we've reached or
                # passed last_page. Otherwise it's silent truncation.
                if page < int(last_page):
                    raise EmailBisonAPIError(
                        0,
                        f"page {page} returned empty data but last_page={last_page}; "
                        f"possible silent truncation",
                    )
                break
            if page >= int(last_page):
                break
        else:
            raise EmailBisonAPIError(
                0,
                f"Pagination safety limit ({_PAGINATION_SAFETY_LIMIT}) exceeded for /api/sender-emails",
            )

        if expected_total is not None and len(all_senders) != expected_total:
            raise EmailBisonAPIError(
                0,
                f"pagination collected {len(all_senders)} senders but meta.total={expected_total} "
                f"for tag_id={tag_id}; data may be incomplete or inconsistent",
            )

        # Filter-honored guard. Observed 2026-05-13 against Charm workspace: the
        # shape `filters[tag_ids][]=<id>` is silently ignored by EB and returns
        # the entire workspace (437 senders) instead of just the tagged subset
        # (280). We use the correct shape `tag_ids[0]=<id>` above, but a future
        # API change or workspace permission quirk could re-introduce the bug.
        # Every honored response carries the tag in each row's `tags[]`. If any
        # returned sender lacks the requested tag, the filter wasn't applied —
        # fail loud instead of letting the orchestrator wipe a campaign.
        for s in all_senders:
            tags = s.get("tags") or []
            if not any(int(t.get("id", -1)) == tag_id for t in tags):
                raise EmailBisonAPIError(
                    0,
                    f"sender id={s.get('id')} returned by tag_ids[0]={tag_id} filter "
                    f"does not carry that tag (tags={[t.get('name') for t in tags]}); "
                    f"the tag filter was silently ignored by EB",
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
