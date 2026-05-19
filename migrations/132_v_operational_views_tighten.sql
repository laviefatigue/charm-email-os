-- Migration 127: tighten v_operational_workspaces semantic
--
-- Step 6 of docs/plans/hypertide-data-model-and-change-tracking.md.
--
-- v_operational_workspaces (created in migration 123) originally filtered only
-- on the parent client's client_status. Operationally though, workspaces also
-- have an is_active flag (operator-controlled "is this workspace in active
-- rotation"). Every existing sync_module already does
-- `FROM workspaces WHERE is_active = TRUE`. For the view to subsume that
-- pattern cleanly, it must ALSO filter on is_active = TRUE.
--
-- Same logic for v_operational_domains by transitive join.
--
-- Pre-flight: no production code uses these views yet (added 2026-05-18 in
-- migration 123, callers being migrated in this commit's batch work). Safe
-- to change the semantic.
--
-- Safe to re-run: CREATE OR REPLACE.

BEGIN;

CREATE OR REPLACE VIEW v_operational_workspaces AS
    SELECT w.* FROM workspaces w
    JOIN v_operational_clients c ON c.id = w.client_id
    WHERE w.is_active = TRUE;

-- v_operational_domains unchanged in body (it joins through the tightened
-- workspaces view, so it inherits the is_active filter transitively).
-- Re-declared here only for completeness of the migration's purpose.
CREATE OR REPLACE VIEW v_operational_domains AS
    SELECT d.* FROM domains d
    JOIN v_operational_workspaces w ON w.id = d.workspace_id;

COMMENT ON VIEW v_operational_workspaces IS
    'Workspaces under operational clients (client_status NOT IN (friends_and_family, inactive)) '
    'AND workspace.is_active = TRUE. Replaces the de-facto operational filter pattern '
    'across sync_modules (FROM workspaces WHERE is_active = TRUE) with a single source of truth. '
    'Admin/CRUD routes that need to show disabled workspaces should read from the workspaces base table.';

COMMIT;
