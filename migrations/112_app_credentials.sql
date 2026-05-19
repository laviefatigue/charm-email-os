-- Migration 112: Application-level credentials registry.
--
-- Stores shared credentials (GitHub App PEMs, OAuth refresh tokens, etc.)
-- used by charm-email-os services to talk to external systems on behalf
-- of HireCharm (the agency). Distinct from workspace_api_keys (migration
-- 089) which holds per-CLIENT credentials.
--
-- First consumer: the Charm Onboarder GitHub App PEM, seeded post-migration
-- via a one-time INSERT from a trusted host. Used by every service that
-- creates / reads / commits to HireCharm/client-* repos (the
-- client-repo-reconciler worker, the charm-email-os Context/Assets API
-- routes, the future meeting-sync worker).
--
-- Security model — mirrors workspace_api_keys exactly:
--   - value is stored plaintext (no application-layer encryption)
--   - Access controlled at the API layer: only api/services/credentials.py
--     reads the value column, and that helper is only called by
--     trusted server-side code (workers + API routes)
--   - Column excluded from any SELECT *
--   - No list endpoint exposes value
--
-- Rotation:
--   - UPDATE app_credentials SET value = '<new>', last_rotated_at = NOW()
--     WHERE name = '<name>';
--   - In-process token caches (~55 min TTL on installation tokens)
--     expire naturally; no worker restart needed.
--
-- Idempotent: re-running the migration is a no-op.
--
-- See docs/dayai/SPEC_app_credentials.md for full design context.

BEGIN;

CREATE TABLE IF NOT EXISTS app_credentials (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Stable name used as a lookup key by api/services/credentials.py.
    -- Convention: snake_case, descriptive. Examples:
    --   'charm_onboarder_github_app_pem'
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
CREATE INDEX IF NOT EXISTS idx_app_credentials_name_active
    ON app_credentials (name) WHERE is_active = TRUE;

COMMENT ON TABLE app_credentials IS
    'Shared application-level credentials (GitHub App PEMs, OAuth tokens). '
    'Plaintext storage; access-controlled at the application layer. Per-client '
    'credentials belong in workspace_api_keys, not here.';

COMMENT ON COLUMN app_credentials.value IS
    'Plaintext secret value. NEVER expose in list endpoints, dumps, or logs.';

COMMENT ON COLUMN app_credentials.name IS
    'Stable lookup key. snake_case convention. e.g. charm_onboarder_github_app_pem.';

COMMIT;
