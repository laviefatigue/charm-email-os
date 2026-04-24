"""
OAuth2 refresh-token flow for Day.AI.

Day.AI's OAuth endpoint is POST /api/oauth (form-encoded). Access tokens expire
(typically 1 hour). This module caches an access token in memory and refreshes
it ~60s before expiry.

Refresh token itself is long-lived and comes from the OAuth setup wizard (the
TypeScript SDK's `yarn oauth:setup` flow — done once, credentials committed to
env vars).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class DayAIAuthError(Exception):
    """Raised when OAuth refresh fails (bad creds, revoked refresh token, etc.)."""


@dataclass(frozen=True)
class DayAICredentials:
    """Static OAuth credentials. Load from env vars via from_env()."""

    base_url: str
    client_id: str
    client_secret: str
    refresh_token: str
    workspace_id: str | None = None

    @classmethod
    def from_env(cls) -> "DayAICredentials":
        """Load from standard env vars. Raises if any required var is missing."""
        import os

        missing = [
            k
            for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")
            if not os.getenv(k)
        ]
        if missing:
            raise DayAIAuthError(
                f"Missing required Day.AI OAuth env vars: {', '.join(missing)}. "
                "Run yarn oauth:setup in the Day.AI SDK to obtain them, "
                "then set on the Coolify application."
            )
        return cls(
            base_url=os.getenv("DAY_AI_BASE_URL", "https://day.ai"),
            client_id=os.environ["CLIENT_ID"],
            client_secret=os.environ["CLIENT_SECRET"],
            refresh_token=os.environ["REFRESH_TOKEN"],
            workspace_id=os.getenv("WORKSPACE_ID") or None,
        )


class AccessTokenCache:
    """
    In-memory access-token cache with auto-refresh on expiry.

    Thread-safety: use ONE instance per DayAIClient. This module assumes a
    single-process asyncio worker; cross-process sharing would need external
    storage (Redis/DB) which the watcher doesn't need.
    """

    # Refresh when the cached token has <= this many seconds of life left.
    _REFRESH_BUFFER_SECONDS = 60

    def __init__(self, creds: DayAICredentials, http: httpx.AsyncClient):
        self._creds = creds
        self._http = http
        self._access_token: str | None = None
        self._expires_at: float = 0.0  # unix seconds
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        """Return a valid access token, refreshing if needed."""
        async with self._lock:
            now = time.time()
            if self._access_token and self._expires_at > now + self._REFRESH_BUFFER_SECONDS:
                return self._access_token
            return await self._refresh_locked()

    async def invalidate(self) -> None:
        """Force a refresh on next get() (call after a 401 response)."""
        async with self._lock:
            self._access_token = None
            self._expires_at = 0.0

    async def _refresh_locked(self) -> str:
        """Caller must hold self._lock."""
        logger.info("refreshing Day.AI access token")
        payload = {
            "grant_type": "refresh_token",
            "client_id": self._creds.client_id,
            "client_secret": self._creds.client_secret,
            "refresh_token": self._creds.refresh_token,
        }
        resp = await self._http.post(
            f"{self._creds.base_url}/api/oauth",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise DayAIAuthError(
                f"Day.AI token refresh failed: HTTP {resp.status_code} — {resp.text[:500]}"
            )
        body = resp.json()
        if "access_token" not in body or "expires_in" not in body:
            raise DayAIAuthError(
                f"Day.AI token response missing expected fields: {list(body.keys())}"
            )
        self._access_token = body["access_token"]
        self._expires_at = time.time() + int(body["expires_in"])
        logger.info(
            "access token refreshed; expires in %d seconds", int(body["expires_in"])
        )
        return self._access_token
