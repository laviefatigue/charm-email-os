# Spec — `app_credentials` table + GitHub App helper

> Authoritative spec for how charm-email-os and its workers store + use
> shared application-level credentials. The first credential to land
> in this table is the **Charm Onboarder GitHub App PEM**, but the
> pattern generalizes (Day.AI OAuth refresh token can migrate here
> later).
>
> Paired with `SPEC_charm_os_repo_access.md` (the consumer-side pattern
> that uses this primitive) and `CONCEPT_client_repo.md` (the
> architectural framing).

---

## 1. Why DB-stored shared credentials

The current pattern for the Charm Onboarder PEM is "one file on the
admin's laptop." That's blocking:

- The `dayai-watcher` Coolify worker can't create repos because it
  doesn't have the PEM
- A future `client-repo-reconciler` worker needs it
- The `charm-email-os` backend needs it to render the Context + Assets
  frontend sections (Audience D in `CONCEPT_client_repo.md` §4)
- The `meeting-sync` worker will need it
- Future workers (EB report cron, value-change detector) will need it

Distributing the PEM as a Coolify env var on every worker means:
- N copies to rotate when the App is re-issued
- Drift risk between workers
- Each new service needs separate provisioning

**DB-stored solves all of this with a single primitive.** Any service
that connects to charm-email-os Postgres can mint a GitHub installation
token. No env-var sprawl, no per-worker secret wiring.

Precedent exists: `migrations/089_workspace_api_keys.sql` already stores
EmailBison Sanctum tokens in the DB with the security boundary at the
application layer.

---

## 2. Schema — `migrations/112_app_credentials.sql`

```sql
-- Migration 112: Application-level credentials registry
--
-- Stores shared credentials (GitHub App PEMs, OAuth refresh tokens,
-- etc.) used by charm-email-os services to talk to external systems
-- on behalf of HireCharm (the agency), as opposed to per-client
-- credentials which belong in workspace_api_keys.
--
-- Security model:
--   - value column is plaintext (same as workspace_api_keys.key_token)
--   - Access controlled at application layer: no list endpoint returns
--     the value column; only api/services/credentials.py:get_credential
--     reads it, and that helper is only called by trusted server-side
--     code (workers + API routes)
--   - The column is excluded from any SELECT * pattern
--   - SELECT permissions limited to the charm-api service role
--
-- Rotation:
--   - UPDATE value WHERE name = '<name>'; set last_rotated_at = NOW()
--   - In-process token caches (~55 min TTL) will expire on their own
--   - No worker restart needed

CREATE TABLE IF NOT EXISTS app_credentials (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL UNIQUE,
    -- The raw secret value. For PEMs: full BEGIN/END envelope preserved.
    -- For OAuth refresh tokens: the bare token string.
    -- Never expose in list endpoints or admin UIs.
    value           TEXT        NOT NULL,
    description     TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    last_rotated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_credentials_name
    ON app_credentials (name) WHERE is_active = TRUE;

COMMENT ON TABLE app_credentials IS
    'Shared application-level credentials (GitHub App PEMs, OAuth tokens). Plaintext storage; access-controlled at the application layer.';

COMMENT ON COLUMN app_credentials.value IS
    'Plaintext secret value. NEVER expose in list endpoints, dumps, or logs.';
```

### Seed data (one-time)

After the migration applies, seed the Charm Onboarder PEM:

```sql
-- Run once from a trusted host with the PEM contents available
INSERT INTO app_credentials (name, value, description)
VALUES (
    'charm_onboarder_github_app_pem',
    '<paste PEM contents including BEGIN/END envelope>',
    'Private key for the Charm Onboarder GitHub App (App ID 3480661, install 126503394 on HireCharm). Used to mint installation tokens for repo creation + commits.'
);
```

Operationally: copy-paste from the local file, never commit to git.

---

## 3. Service module — `api/services/credentials.py`

Minimal helper that wraps DB access + audit:

```python
"""Credentials access for charm-email-os services.

Single entry point for reading shared credentials from the
app_credentials table. Bumps last_used_at on each read for audit.

DO NOT bypass this module — direct SELECTs scatter access points and
make the next rotation/audit harder.
"""
from __future__ import annotations
import asyncpg


class CredentialNotFound(Exception):
    pass


async def get_credential(name: str, pool: asyncpg.Pool) -> str:
    """Return the active credential by name. Raises CredentialNotFound."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE app_credentials
               SET last_used_at = NOW()
             WHERE name = $1 AND is_active = TRUE
            RETURNING value
            """,
            name,
        )
    if row is None:
        raise CredentialNotFound(f"No active credential named {name!r}")
    return row["value"]
```

That's the whole surface area. ~20 lines. No abstractions for "secret
providers," no plugin pattern, no fallback chain. One table, one
function.

---

## 4. GitHub App helper — `api/services/github_app.py`

Thin layer that uses the credential helper to produce authed clients.

```python
"""Charm Onboarder GitHub App authentication.

Mints short-lived installation tokens from the PEM stored in
app_credentials. Caches tokens in-process for ~55 minutes (GitHub
installation tokens expire after 60).

Every charm-email-os service that talks to HireCharm/* uses this
module — workers, API routes, scheduled jobs. Do not roll your own
JWT signing elsewhere.
"""
from __future__ import annotations
import time
from dataclasses import dataclass

import httpx
import jwt  # PyJWT

from .credentials import get_credential

# GitHub App identifiers — public-ish; not secrets, but kept here for
# single-source-of-truth.
CHARM_ONBOARDER_APP_ID = "3480661"
CHARM_ONBOARDER_INSTALL_ID = "126503394"

_token_cache: tuple[str, float] | None = None  # (token, expires_at)


@dataclass
class GitHubAppToken:
    token: str
    expires_at: float  # unix epoch seconds


async def mint_installation_token(pool) -> GitHubAppToken:
    """Return a valid Charm Onboarder installation token.

    Cached in-process for ~55 minutes. Subsequent calls within the
    window return the cached token without DB or GitHub round-trips.
    """
    global _token_cache
    now = time.time()
    if _token_cache and _token_cache[1] - 60 > now:
        return GitHubAppToken(_token_cache[0], _token_cache[1])

    pem = await get_credential("charm_onboarder_github_app_pem", pool)
    app_jwt = jwt.encode(
        {"iat": int(now) - 10, "exp": int(now) + 540, "iss": CHARM_ONBOARDER_APP_ID},
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

    expires_at = now + 55 * 60  # cache for 55 min; tokens valid for 60
    _token_cache = (body["token"], expires_at)
    return GitHubAppToken(body["token"], expires_at)


async def gh_client(pool) -> httpx.AsyncClient:
    """Return an httpx.AsyncClient pre-configured with auth headers.

    Caller is responsible for closing (or using as async context).
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
```

Usage pattern across the codebase:

```python
from api.services.github_app import gh_client

async with await gh_client(pool) as gh:
    resp = await gh.get(f"/repos/HireCharm/client-{slug}/contents/client.md")
    ...
```

---

## 5. Security trade-off — discussed in writing

Plaintext PEM in DB is the same exposure profile as the existing
`workspace_api_keys.key_token`. The threat model:

| Threat | Mitigation |
|---|---|
| SQL injection in any API endpoint | All queries parameterized; review on PR. |
| DB backup leak | Backups encrypted at rest (Coolify-managed); restricted distribution. |
| Compromised app server reads PEM | Same impact as compromised app server in any other architecture — would have to be reasoned about regardless. |
| Insider with DB read access exfiltrates PEM | Limit `app_credentials` SELECT to a small set of service roles; log queries; rotate on suspicion. |
| Replicated DB read replica with weaker access controls | Either exclude `app_credentials` from replication (pg_publication filter) or ensure replicas inherit the same access controls as the primary. |

**Defense-in-depth follow-up (out of scope for first cut):** wrap value
with application-layer envelope encryption. A single master key in a
Coolify env var (one narrow secret, instead of N PEMs across N
workers) wraps + unwraps. Then DB read alone doesn't equal PEM
exposure. Easy add later; not needed to ship.

**What we explicitly accept:** the PEM is more sensitive than other
DB rows. If the PEM leaks, the attacker can read/write every
`HireCharm/*` repo. Treat the DB row with the same care given to
production database backups in general.

---

## 6. Rotation procedure

When the GitHub App is re-keyed (annually, or on suspicion of leak):

1. In the GitHub App settings, generate a new private key. Download
   the new `.pem` file.
2. From a trusted host with DB access:
   ```sql
   UPDATE app_credentials
      SET value = '<new PEM contents>',
          last_rotated_at = NOW()
    WHERE name = 'charm_onboarder_github_app_pem';
   ```
3. In-process token caches (~55 min TTL) expire naturally. No worker
   restart needed.
4. Revoke the old key in the GitHub App settings only after confirming
   the new key works (check one worker's logs for a successful token
   mint).

No deployment, no env-var update, no container restart.

---

## 7. Future credentials that migrate here

Each can move on its own PR; no dependencies between them.

| Credential | Current location | Move when |
|---|---|---|
| Day.AI OAuth refresh token | Coolify env var on `dayai-watcher` | When a second service needs Day.AI access |
| Day.AI OAuth client secret | Same | Same |
| (Potentially) Hypertide API key | TBD | When the Hypertide worker needs DB-coordinated access |

Per-client credentials (per-workspace EmailBison API keys) stay in
`workspace_api_keys` — that's per-client data, this table is per-app
data.

---

## 8. What this unlocks

Once `app_credentials` + `github_app.py` ship:

- The `client-repo-reconciler` worker (ROADMAP Tier 1.4) can be a
  Coolify-portable container with no PEM env var
- `charm-email-os` API routes (ROADMAP Tier 1.6, the Context + Assets
  pages — see `SPEC_charm_os_repo_access.md`) can read repos
- The future `meeting-sync` worker (ROADMAP Tier 1.5) reuses the same
  helper
- Rotation becomes a one-line SQL UPDATE
- New services added to charm-email-os get GitHub access for free

This is the keystone for the entire pipeline becoming Coolify-portable.

---

## End

When implementing: migration 112 + the two service modules + the seed
INSERT, in that order. No other migrations or code depend on this work
beyond the consumer-side spec at `SPEC_charm_os_repo_access.md`.
