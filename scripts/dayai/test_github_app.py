#!/usr/bin/env python3
"""
Smoke test for api/services/github_app.py.

Mints a Charm Onboarder installation token from the PEM stored in
the `secrets` table, then hits a known repo (HireCharm/client-sammy)
to confirm the token works.

Run from a host with charm-email-os DB access AFTER the PEM seed
INSERT has been performed. See PR body / SPEC_secrets.md §2.

Requires PyJWT installed (`pip install PyJWT[crypto]`). Not yet in
api/requirements.txt — added when this module's first consumer ships.

Usage:
    POSTGRES_HOST=...
    POSTGRES_PORT=5432
    POSTGRES_USER=charm
    POSTGRES_PASSWORD=...
    POSTGRES_DB=postgres
    python scripts/dayai/test_github_app.py

Expected output:
    PEM length: 1700 chars
    Minted token: ghs_******** (expires at <unix-ts>)
    GET /repos/HireCharm/client-sammy -> 200
    Repo: HireCharm/client-sammy
    Default branch: main
    SMOKE TEST PASSED
"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg

# Make the api package importable when run from repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api.services.github_app import gh_client, mint_installation_token  # noqa: E402


async def main() -> int:
    pool = await asyncpg.create_pool(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ.get("POSTGRES_USER", "charm"),
        password=os.environ["POSTGRES_PASSWORD"],
        database=os.environ.get("POSTGRES_DB", "postgres"),
        min_size=1,
        max_size=2,
    )
    try:
        # 1. Confirm we can read the PEM (via the credentials helper inside mint).
        tok = await mint_installation_token(pool)
        print(f"Minted token: {tok.token[:10]}******** (expires at {tok.expires_at:.0f})")

        # 2. Confirm the token actually authenticates against GitHub.
        async with await gh_client(pool) as gh:
            resp = await gh.get("/repos/HireCharm/client-sammy")
            print(f"GET /repos/HireCharm/client-sammy -> {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            print(f"Repo: {data['full_name']}")
            print(f"Default branch: {data['default_branch']}")

        # 3. Cache check — a second mint within the window should NOT re-mint.
        tok2 = await mint_installation_token(pool)
        assert tok2.token == tok.token, "Token cache failed — got a different token on second call"
        print("Token cache OK (second call returned cached token)")

        print("SMOKE TEST PASSED")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
