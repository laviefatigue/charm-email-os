-- Migration 136: Shared application-level secrets registry.
--
-- Stores shared credentials (GitHub App PEMs, OAuth refresh tokens,
-- webhook signing secrets, etc.) used by charm-email-os services to
-- talk to external systems on behalf of HireCharm (the agency).
-- Distinct from workspace_api_keys (migration 089) which holds
-- per-CLIENT credentials.
--
-- Aligns with the `secrets` table referenced in
-- docs/architecture/client-context-sync.md §Security Model.
--
-- First consumer: the Charm Onboarder GitHub App PEM, seeded
-- post-migration via a one-time INSERT from a trusted host. Used by:
--   - client-repo-reconciler worker (per-client repo creation)
--   - context-sync worker (the canonical client-context-sync spec)
--   - charm-email-os context-query API routes
--   - future meeting-sync worker, etc.
--
-- Security model — mirrors workspace_api_keys exactly:
--   - value is stored plaintext (no application-layer encryption)
--   - Access controlled at the API layer: only api/services/credentials.py
--     reads the value column, and that helper is only called by
--     trusted server-side code (workers + API routes)
--   - Column excluded from any SELECT *
--   - No list endpoint exposes value
--
-- The client-context-sync spec's §Security Model describes
-- application-layer encryption as a future improvement; this v1
-- matches the existing workspace_api_keys plaintext-with-app-layer-
-- controls pattern. Envelope encryption is a defense-in-depth
-- follow-on, not blocking.
--
-- Rotation:
--   - UPDATE secrets SET value = '<new>', last_rotated_at = NOW()
--     WHERE name = '<name>';
--   - In-process token caches (~55 min TTL on installation tokens)
--     expire naturally; no worker restart needed.
--
-- Idempotent: re-running the migration is a no-op.
--
-- See docs/dayai/SPEC_secrets.md for full design context.
-- See docs/architecture/client-context-sync.md §Security Model for
-- the canonical naming + the three secret types this table holds
-- (github_app_private_key, github_webhook_secret, OAuth tokens).

BEGIN;

CREATE TABLE IF NOT EXISTS secrets (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Stable name used as a lookup key by api/services/credentials.py.
    -- Convention: snake_case, descriptive. Per client-context-sync.md:
    --   'github_app_private_key'
    --   'github_webhook_secret'
    --   'dayai_oauth_refresh_token'  (future)
    name            TEXT        NOT NULL UNIQUE,

    -- The raw secret value. For PEMs: full BEGIN/END envelope preserved.
    -- For OAuth refresh tokens: the bare token string.
    -- NEVER expose in list endpoints, dumps, or logs.
    value           TEXT        NOT NULL,

    -- Free-text description for operators. Useful when rotating: who
    -- generated it, where the originating credential lives, what
    -- breaks if revoked.
    description     TEXT,

    -- Soft-disable without deleting (kept for audit). Active lookups
    -- only return is_active=TRUE rows.
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,

    -- Set to NOW() on every rotation. Set on INSERT to creation time.
    last_rotated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Bumped by api/services/credentials.py:get_credential on each read.
    -- Provides a cheap audit signal: "is anything actually using this?"
    last_used_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Partial index: get_credential filters by name AND is_active.
CREATE INDEX IF NOT EXISTS idx_secrets_name_active
    ON secrets (name) WHERE is_active = TRUE;

COMMENT ON TABLE secrets IS
    'Shared application-level secrets (GitHub App PEMs, OAuth tokens, '
    'webhook signing secrets). Plaintext storage; access-controlled '
    'at the application layer. Per-client credentials belong in '
    'workspace_api_keys, not here. Canonical reference: '
    'docs/architecture/client-context-sync.md §Security Model.';

COMMENT ON COLUMN secrets.value IS
    'Plaintext secret value. NEVER expose in list endpoints, dumps, or logs.';

COMMENT ON COLUMN secrets.name IS
    'Stable lookup key. snake_case convention. e.g. github_app_private_key, github_webhook_secret.';

COMMIT;
