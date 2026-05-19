# Spec — `secrets` table + GitHub App helper (implementation companion)

> Implementation-side details for the `secrets` table referenced in
> [docs/architecture/client-context-sync.md](../architecture/client-context-sync.md)
> §Security Model. That doc is the **canonical architecture**; this
> doc covers the DB schema, the helper module shape, the rotation
> procedure, and the security trade-offs.
>
> Paired with [`CONCEPT_client_repo.md`](CONCEPT_client_repo.md) for
> the broader context-engine vision.

---

## 1. Scope

The canonical [client-context-sync.md](../architecture/client-context-sync.md)
spec calls for a `secrets` table holding shared application-level
credentials (GitHub App private key, webhook HMAC secret, future
OAuth tokens). This doc covers:

- The exact table shape that migration 136 ships
- The Python service modules consumers use (`credentials.py`, `github_app.py`)
- Rotation procedure
- Security trade-off (plaintext vs envelope encryption)

It does **not** re-cover what's in client-context-sync.md §Security Model:
- GitHub App registration steps
- The three secret types (`github_app_private_key`, `github_webhook_secret`, OAuth tokens)
- Webhook HMAC verification flow
- Per-workspace scoping at the API layer

Read that doc first if you need the full security picture.

---

## 2. Schema — `migrations/136_secrets.sql`

```sql
CREATE TABLE IF NOT EXISTS secrets (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL UNIQUE,
    value           TEXT        NOT NULL,
    description     TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    last_rotated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_secrets_name_active
    ON secrets (name) WHERE is_active = TRUE;
```

Plain mirror of the `workspace_api_keys` (089) security posture:
plaintext storage, access controlled at the app layer, no list endpoint
exposes `value`.

### Seed data (one-time, per environment)

After the migration applies, seed the Charm Onboarder PEM from a
trusted host with both DB access AND the PEM contents:

```sql
INSERT INTO secrets (name, value, description) VALUES (
    'github_app_private_key',
    $$<paste PEM body, BEGIN/END envelope preserved>$$,
    'Private key for the Charm Onboarder GitHub App (App ID 3480661, install 126503394 on HireCharm).'
);
```

Use PostgreSQL dollar-quoting (`$$ ... $$`) so the PEM's newlines and
special characters don't need escaping. Never commit the actual PEM
to git.

Other seeds (added when consumers ship):

```sql
INSERT INTO secrets (name, value, description) VALUES (
    'github_webhook_secret',
    $$<random 32-byte hex>$$,
    'HMAC secret for verifying GitHub App webhooks at /api/v1/webhooks/github/context-sync.'
);
```

---

## 3. Service module — `api/services/credentials.py`

Minimal wrapper around DB access + audit:

```python
async def get_credential(name: str, pool: asyncpg.Pool) -> str:
    """Return the active secret value by name. Raises CredentialNotFound."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE secrets
               SET last_used_at = NOW()
             WHERE name = $1 AND is_active = TRUE
            RETURNING value
            """,
            name,
        )
    if row is None:
        raise CredentialNotFound(...)
    return row["value"]
```

~20 lines, one function. No abstractions for "secret providers" — one
table, one function.

---

## 4. GitHub App helper — `api/services/github_app.py`

Uses `get_credential` to mint short-lived installation tokens. Cached
in-process for ~55 minutes (GitHub installation tokens expire after 60).

```python
CHARM_ONBOARDER_APP_ID = "3480661"
CHARM_ONBOARDER_INSTALL_ID = "126503394"
PEM_CREDENTIAL_NAME = "github_app_private_key"  # secrets.name

async def mint_installation_token(pool) -> GitHubAppToken: ...
async def gh_client(pool) -> httpx.AsyncClient: ...
```

Auth flow matches client-context-sync.md §Security Model "Auth flow
at request time" exactly:

1. Look up PEM via `get_credential('github_app_private_key', pool)`
2. Sign JWT with RS256: `{iat, exp: iat+540, iss: APP_ID}`, 10-min skew
3. `POST /app/installations/{INSTALL_ID}/access_tokens` → installation token
4. Cache for ~55 min in-process
5. Use as `Authorization: token <installation_token>` for subsequent calls

**Consumer pattern:**

```python
from api.services.github_app import gh_client

async with await gh_client(pool) as gh:
    resp = await gh.get(f"/repos/HireCharm/client-{slug}/contents/client.md")
    resp.raise_for_status()
```

---

## 5. Security trade-off

Plaintext PEM in DB has the same exposure profile as the existing
`workspace_api_keys.key_token`. Threat model:

| Threat | Mitigation |
|---|---|
| SQL injection | All queries parameterized; reviewed on PR. |
| DB backup leak | Backups encrypted at rest (Coolify-managed); restricted distribution. |
| Compromised app server reads PEM | Same impact as compromised app server in any architecture — would have to be reasoned about regardless. |
| Insider with DB read | Limit `secrets` SELECT to a small set of service roles; log queries; rotate on suspicion. |
| Replicated DB read replica with weaker controls | Either exclude `secrets` from replication (pg_publication filter) or ensure replicas inherit primary's access controls. |

**Defense-in-depth follow-up (out of scope for first cut):** wrap
`value` with application-layer envelope encryption. A single master
key in a Coolify env var (one narrow secret) wraps + unwraps. DB read
alone wouldn't expose the PEM. Easy add later when an additional
sensitive secret type lands.

**What we explicitly accept:** the PEM is more sensitive than other
DB rows. If it leaks, attacker can read/write every `HireCharm/*`
repo. Treat the row with the same care as production DB backups.

---

## 6. Rotation procedure

When the GitHub App is re-keyed (annually, or on suspicion of leak):

1. In the GitHub App settings, generate a new private key. Download
   the new `.pem` file.
2. From a trusted host with DB access:
   ```sql
   UPDATE secrets
      SET value = '<new PEM contents>',
          last_rotated_at = NOW()
    WHERE name = 'github_app_private_key';
   ```
3. In-process token caches (~55 min TTL) expire naturally. No worker
   restart needed.
4. Revoke the old key in the GitHub App settings only after confirming
   the new key works (check one worker's logs for a successful token mint).

No deployment, no env-var update, no container restart.

Same procedure for `github_webhook_secret` (replace via UPDATE; new
webhooks will use the new secret on next inbound).

---

## 7. Future secrets that land here

Each can move on its own PR; no dependencies.

| Secret | Current location | Move when |
|---|---|---|
| `github_app_private_key` | (target) — seeded after migration 136 | This PR |
| `github_webhook_secret` | (target) — seeded when sync worker ships | client-context-sync.md Phase 1a |
| `dayai_oauth_refresh_token` | Coolify env var on `dayai-watcher` | When a second service needs Day.AI access |
| `dayai_oauth_client_secret` | Same | Same |

Per-client credentials (per-workspace EmailBison API keys) stay in
`workspace_api_keys` — that's per-client data, this table is per-app data.

---

## 8. What this unlocks

Once `secrets` + `github_app.py` ship:

- The canonical sync worker described in
  [client-context-sync.md §Sync Architecture](../architecture/client-context-sync.md)
  can mint tokens to clone repos
- The `client-repo-reconciler` worker (ROADMAP Tier 1.4) can be a
  Coolify-portable container with no PEM env var
- The webhook verifier at `/api/v1/webhooks/github/context-sync` can
  read the HMAC secret from the same table
- Rotation of either secret becomes a one-line SQL UPDATE
- New services added to charm-email-os get GitHub access for free

This is the keystone for both the **creation** side of the pipeline
(my reconciler work) and the **consumption** side (the canonical sync
worker that ingests repo content into `workspace_context_documents`).

---

## End

When implementing: migration 136 + the two service modules + the seed
INSERT, in that order. PyJWT gets added to `api/requirements.txt` in
the PR that ships the first consumer (sync worker or reconciler) so
master's dependency footprint stays minimal while this code is dormant.
