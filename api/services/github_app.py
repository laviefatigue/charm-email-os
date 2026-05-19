"""
Charm Onboarder GitHub App authentication.

Mints short-lived installation tokens for the Charm Onboarder App from
the PEM stored in app_credentials (migration 112). Caches tokens
in-process for ~55 minutes (GitHub installation tokens expire after 60).

Every charm-email-os service that talks to HireCharm/* uses this
module — workers, API routes, scheduled jobs. Do not roll your own
JWT signing elsewhere.

Usage:

    from api.services.github_app import gh_client

    async with await gh_client(pool) as gh:
        resp = await gh.get("/repos/HireCharm/client-sammy/contents/client.md")
        resp.raise_for_status()
        ...

See docs/dayai/SPEC_app_credentials.md for the design.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import asyncpg
import httpx
import jwt  # PyJWT

from .credentials import get_credential

logger = logging.getLogger(__name__)

# Public-ish identifiers — not secrets, but kept here as single source of truth.
CHARM_ONBOARDER_APP_ID = "3480661"
CHARM_ONBOARDER_INSTALL_ID = "126503394"
PEM_CREDENTIAL_NAME = "charm_onboarder_github_app_pem"

# JWT lifetime constraints from GitHub:
#   - JWT used to mint installation tokens: max 10 min from iat
#   - Installation token: 60 min absolute
# We mint short JWTs (~9 min) and cache installation tokens for 55 min.
_JWT_LIFETIME_SECONDS = 9 * 60
_INSTALLATION_TOKEN_CACHE_SECONDS = 55 * 60

# In-process cache. Module-level is fine — a fresh worker process always
# starts with an empty cache, which forces a DB read for the PEM at boot.
_token_cache: tuple[str, float] | None = None  # (token, expires_at_epoch)


@dataclass
class GitHubAppToken:
    """Installation token plus expiry. Returned by mint_installation_token."""
    token: str
    expires_at: float  # unix epoch seconds


async def mint_installation_token(pool: asyncpg.Pool) -> GitHubAppToken:
    """
    Return a valid Charm Onboarder installation access token.

    Cached in-process. Subsequent calls within ~55 minutes return the
    cached token with no DB read and no GitHub round-trip. After
    expiry, the next call re-reads the PEM from app_credentials and
    re-mints.
    """
    global _token_cache
    now = time.time()

    if _token_cache is not None and _token_cache[1] - 60 > now:
        return GitHubAppToken(token=_token_cache[0], expires_at=_token_cache[1])

    pem = await get_credential(PEM_CREDENTIAL_NAME, pool)

    app_jwt = jwt.encode(
        {
            "iat": int(now) - 10,  # 10s skew tolerance
            "exp": int(now) + _JWT_LIFETIME_SECONDS,
            "iss": CHARM_ONBOARDER_APP_ID,
        },
        pem,
        algorithm="RS256",
    )

    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(
            f"https://api.github.com/app/installations/{CHARM_ONBOARDER_INSTALL_ID}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "charm-onboarder",
            },
        )
        resp.raise_for_status()
        body = resp.json()

    expires_at = now + _INSTALLATION_TOKEN_CACHE_SECONDS
    _token_cache = (body["token"], expires_at)
    logger.info(
        "Minted new Charm Onboarder installation token (expires_at=%s)",
        body.get("expires_at"),
    )
    return GitHubAppToken(token=body["token"], expires_at=expires_at)


async def gh_client(pool: asyncpg.Pool) -> httpx.AsyncClient:
    """
    Return an httpx.AsyncClient pre-configured with Charm Onboarder
    authentication, the standard Accept header, and API version.

    Caller closes (preferred: use as `async with await gh_client(pool):`).
    """
    tok = await mint_installation_token(pool)
    return httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"token {tok.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "charm-onboarder",
        },
        timeout=30.0,
    )
