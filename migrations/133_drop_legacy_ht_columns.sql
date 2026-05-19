-- Migration 133: drop workspaces.manages_via_hypertide
--
-- Step 10a of docs/plans/hypertide-data-model-and-change-tracking.md.
--
-- The per-workspace HT-tracked flag is replaced by "client has at least one
-- client_hypertide_subscriptions row" — chs is per-client, more correct since
-- HT bills at the client/subscription level. All readers migrated:
--   - apps/hypertide-worker/audit.py (scope query)
--   - apps/hypertide-worker/backfill.py (existing-domains + workspace-catalog)
--   - apps/hypertide-worker/cli.py (inspect-domain + mark-legacy)
--   - api/routes/reports.py (drift report scope)
--
-- Pre-flight verification 2026-05-18:
--   - Old vs new audit-scope query: identical 673 domains
--   - No production code references the column outside the worker + reports
--     migrated above (HANDOFF.md text was also updated)
--
-- Step 10b (NOT in this migration): drop clients.workspace_id.
-- Deferred because there are 6 remaining call sites needing migration:
--   - api/database.py _backfill_charm_purchase_record: 5 SQL reads of c.workspace_id
--   - api/routes/clients.py:278 + api/models/client.py: Pydantic field + creation flow
-- These need the workspaces.client_id 1:many model surfaced in the api layer.
-- Tracked as follow-up.
--
-- Safe to re-run: DROP COLUMN IF EXISTS.
-- domains.is_legacy is KEPT per Concern C (its semantic "acquired outside
-- the HT pipeline" still applies; only its old F&F-detection misuse went away).

BEGIN;

-- The v_operational_workspaces view was defined with SELECT w.* in migration
-- 132, which pins its column list to whatever workspaces has at view creation
-- time — including manages_via_hypertide. Dropping the column would require
-- CASCADE (which also rebuilds v_operational_domains). Cleaner approach:
-- redefine the views first without referencing the column, then drop.

DROP VIEW IF EXISTS v_operational_domains;
DROP VIEW IF EXISTS v_operational_workspaces;

ALTER TABLE workspaces
    DROP COLUMN IF EXISTS manages_via_hypertide;

CREATE VIEW v_operational_workspaces AS
    SELECT w.* FROM workspaces w
    JOIN v_operational_clients c ON c.id = w.client_id
    WHERE w.is_active = TRUE;

CREATE VIEW v_operational_domains AS
    SELECT d.* FROM domains d
    JOIN v_operational_workspaces w ON w.id = d.workspace_id;

COMMENT ON VIEW v_operational_workspaces IS
    'Workspaces under operational clients (client_status NOT IN (friends_and_family, inactive)) '
    'AND workspace.is_active = TRUE. Replaces the de-facto operational filter pattern '
    'across sync_modules (FROM workspaces WHERE is_active = TRUE) with a single source of truth. '
    'Admin/CRUD routes that need to show disabled workspaces should read from the workspaces base table.';

COMMENT ON VIEW v_operational_domains IS
    'Domains under operational workspaces only. Joins through both views so F&F filtering is transitive.';

COMMIT;
