-- Migration 089: Workspace API Keys
--
-- Stores workspace-scoped EmailBison API keys for client-facing dashboards.
--
-- Security model:
--   - key_token is stored as plaintext in this table (no application-layer encryption)
--   - Access is controlled at the API layer: no list endpoint returns key_token;
--     only a dedicated GET /api/admin/workspaces/{id}/api-key endpoint exposes it
--   - The column is excluded from all views
--   - This table is NOT included in any SELECT * queries
--
-- Lifecycle:
--   - Key is generated automatically when a workspace is discovered or created
--   - ON CONFLICT (workspace_id) DO UPDATE allows re-keying if a key is rotated
--   - is_active=FALSE marks revoked keys (kept for audit trail)

CREATE TABLE IF NOT EXISTS workspace_api_keys (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID        NOT NULL UNIQUE REFERENCES workspaces(id) ON DELETE CASCADE,
    emailbison_workspace_id INTEGER     NOT NULL,
    key_name                TEXT        NOT NULL,
    -- Raw token from EmailBison API (Laravel Sanctum plain_text_token format).
    -- Never expose this column in list queries or workspace GET responses.
    key_token               TEXT        NOT NULL,
    is_active               BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_api_keys_workspace_id
    ON workspace_api_keys (workspace_id);

CREATE INDEX IF NOT EXISTS idx_workspace_api_keys_eb_workspace_id
    ON workspace_api_keys (emailbison_workspace_id);

COMMENT ON TABLE workspace_api_keys IS
    'Workspace-scoped EmailBison API keys for client dashboards. key_token is sensitive — never expose in list endpoints.';

COMMENT ON COLUMN workspace_api_keys.key_token IS
    'Plaintext EmailBison workspace API token. Access-controlled at application layer only.';
