"""Thin wrapper around Hypertide REST API. Async httpx, no curl, no globals.

Surface kept minimal for Phase 1 (read-only):
  - get_active_orders()
  - get_pending_orders()
  - verify_revert(subscription_id)
  - verify_revert_records(record_ids)

Phase 2+ adds: cancel_subscription, revert_cancellation, create_order, charge_card.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx


class HypertideAPIError(RuntimeError):
    """Raised when HT returns an error or unexpected response shape."""

    def __init__(self, message: str, *, status: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class HypertideClient:
    """Read-only client for Phase 1. Connection-per-instance, closes with `async with`."""

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> HypertideClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "x-api-key": self._api_key,
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("HypertideClient must be used inside `async with`")
        return self._client

    async def _get(self, path: str) -> dict[str, Any]:
        r = await self._request_with_retry("GET", path)
        return _parse_or_raise(r)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = await self._request_with_retry("POST", path, json=payload)
        return _parse_or_raise(r)

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> httpx.Response:
        """Retry transient network errors only — never on HTTP status codes.

        Observed 2026-05-14/15: the HT API occasionally hits httpx.ReadTimeout
        for individual GET calls. Without retry, a single transient timeout
        fails the entire audit cycle, and the 24h freshness loop means stale
        data for a full day. 3 attempts with exponential backoff covers
        normal flakiness while not masking real outages.

        Only retries on connection / read / write / pool / protocol errors.
        HTTP 4xx/5xx responses are returned for `_parse_or_raise` to handle —
        retrying a 401/403 would just burn API budget on the same auth
        failure; 5xx is HT-side and probably won't resolve in seconds.
        """
        retriable = (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
            httpx.ConnectError,
        )
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                if method == "GET":
                    return await self.client.get(path)
                if method == "POST":
                    return await self.client.post(path, json=json)
                raise ValueError(f"unsupported method {method!r}")
            except retriable as exc:
                last_exc = exc
                if attempt >= max_attempts:
                    break
                # 1s, 2s, 4s — total ~7s worst-case before giving up
                await asyncio.sleep(2 ** (attempt - 1))
        # All retries exhausted — re-raise the last transient error
        assert last_exc is not None
        raise last_exc

    async def get_active_orders(self) -> list[dict[str, Any]]:
        body = await self._get("/orders/active")
        return body.get("orders", []) or []

    async def get_pending_orders(self) -> list[dict[str, Any]]:
        body = await self._get("/orders/pending")
        return body.get("orders", []) or []

    async def verify_revert_subscription(self, subscription_id: str) -> list[dict[str, Any]]:
        body = await self._post(
            "/subscriptions/verify-revert",
            {"subscriptionId": subscription_id},
        )
        return body.get("records", []) or []

    async def verify_revert_records(self, record_ids: list[str]) -> list[dict[str, Any]]:
        """Batch verify-revert by recordIds. The API accepts a list; we pass it directly."""
        body = await self._post(
            "/subscriptions/verify-revert",
            {"recordIds": record_ids},
        )
        return body.get("records", []) or []

    async def verify_revert_per_subscription(
        self,
        subscription_ids: list[str],
        *,
        sleep_between: float = 2.5,
    ) -> list[dict[str, Any]]:
        """
        Iterate verify-revert across many subscriptions, respecting rate limits.

        HT documents 20-30/min for /subscriptions/*. Default 2.5s sleep = 24/min,
        well inside the floor.
        """
        out: list[dict[str, Any]] = []
        for sub in subscription_ids:
            recs = await self.verify_revert_subscription(sub)
            out.extend(recs)
            if sleep_between > 0:
                await asyncio.sleep(sleep_between)
        return out


def _parse_or_raise(response: httpx.Response) -> dict[str, Any]:
    """
    Validate HT responses and raise on shape/status problems. Two known
    footguns:
    1. Wrong hostname returns 200 OK with text/html (SPA index.html). Caller
       might think it's a successful API call — check Content-Type.
    2. HT errors come as JSON with success=false; raise on those too.
    """
    ctype = response.headers.get("content-type", "")
    if "application/json" not in ctype:
        raise HypertideAPIError(
            f"Hypertide returned non-JSON ({ctype!r}). Wrong hostname? "
            f"Expected backend.hypertide.io. Status={response.status_code}",
            status=response.status_code,
        )
    try:
        body = response.json()
    except ValueError as e:
        raise HypertideAPIError(
            f"Invalid JSON from Hypertide: {e}", status=response.status_code
        ) from e
    if response.status_code >= 400:
        raise HypertideAPIError(
            f"HTTP {response.status_code}: {body.get('error')} {body.get('message','')}",
            status=response.status_code,
            body=body,
        )
    if not body.get("success", False) and "orders" not in body and "records" not in body:
        # /health is the only success-true endpoint without orders/records;
        # everything else with success=false is an error.
        raise HypertideAPIError(
            f"Hypertide returned success=false: {body}",
            status=response.status_code,
            body=body,
        )
    assert isinstance(body, dict)
    return body
