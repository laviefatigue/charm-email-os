-- Migration 097: Workspace package tiers + admin override + pause flag
--
-- Why this exists
-- ───────────────
-- Per-workspace capacity is a contract: a 50k Google package = 10 orders live
-- + 2 orders reserve = 180 Google inboxes total. Without this, the system
-- only reactively replaces dead inboxes; new workspaces sit cold-start with
-- 0 live, and existing workspaces never know whether they're at contracted
-- capacity. The package + threshold model turns "react on kill" into
-- "maintain target capacity proactively."
--
-- What's added:
--   workspace_packages — reference table, seeded with 50k_google and 100k_google
--   workspaces.package_id              — FK to the assigned tier
--   workspaces.target_live_count_override — admin override; CAN ONLY LOWER package target
--   workspaces.pause_pool_transitions  — boolean kill-switch for the orchestrator's
--                                         threshold-maintenance phase per workspace
--   workspaces.package_assigned_at     — when the package was assigned (audit)
--   trigger enforces override <= package.target_live_count
--   view workspace_effective_targets  — resolves package defaults + override
--
-- What is NOT added:
--   No new queue/transaction table. Pool transitions (graduate, promote, kill,
--   burn, manual override) all continue to write rows to inbox_rotation_history
--   as they happen. The cycle-based orchestrator is the worker; failed cycles
--   auto-retry the next cycle.

-- ──────────────────────────────────────────────────────────────────────────
-- 1. Reference table for capacity tiers
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workspace_packages (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                     TEXT UNIQUE NOT NULL,
    display_name             TEXT NOT NULL,
    target_monthly_sends     INTEGER NOT NULL,
    target_live_count        INTEGER NOT NULL,
    target_reserve_count     INTEGER NOT NULL,
    inboxes_per_order        INTEGER NOT NULL DEFAULT 15,
    orders_live              INTEGER NOT NULL,
    orders_reserve           INTEGER NOT NULL,
    daily_limit_per_inbox    INTEGER NOT NULL DEFAULT 20,
    description              TEXT,
    is_active                BOOLEAN NOT NULL DEFAULT TRUE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Math invariants — orders × per-order = inbox count
    CONSTRAINT package_live_math
        CHECK (target_live_count = orders_live * inboxes_per_order),
    CONSTRAINT package_reserve_math
        CHECK (target_reserve_count = orders_reserve * inboxes_per_order),
    -- Sanity bounds
    CONSTRAINT package_positive_values CHECK (
        target_monthly_sends    > 0 AND
        target_live_count       > 0 AND
        target_reserve_count    >= 0 AND
        inboxes_per_order       > 0 AND
        orders_live             > 0 AND
        orders_reserve          >= 0 AND
        daily_limit_per_inbox   > 0
    )
);

COMMENT ON TABLE workspace_packages IS
    'Capacity tier reference. Each workspace is assigned exactly one package, '
    'which sets the target_live_count and target_reserve_count maintained by '
    'the orchestrator. Admin can override target_live_count downward via '
    'workspaces.target_live_count_override.';

INSERT INTO workspace_packages (
    name, display_name, target_monthly_sends,
    target_live_count, target_reserve_count,
    inboxes_per_order, orders_live, orders_reserve,
    daily_limit_per_inbox, description
) VALUES
    ('50k_google',  'Google 50k/month',  50000,
     150, 30, 15, 10, 2, 20,
     'Standard Google tier: 10 orders live + 2 orders reserve = 180 inboxes.'),
    ('100k_google', 'Google 100k/month', 100000,
     300, 60, 15, 20, 4, 20,
     'Doubled Google tier: 20 orders live + 4 orders reserve = 360 inboxes.')
ON CONFLICT (name) DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────
-- 2. Per-workspace assignment columns
-- ──────────────────────────────────────────────────────────────────────────
ALTER TABLE workspaces
    ADD COLUMN IF NOT EXISTS package_id                UUID REFERENCES workspace_packages(id),
    ADD COLUMN IF NOT EXISTS target_live_count_override INTEGER,
    ADD COLUMN IF NOT EXISTS pause_pool_transitions    BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS package_assigned_at       TIMESTAMPTZ;

COMMENT ON COLUMN workspaces.package_id IS
    'Assigned capacity tier. NULL = no proactive promotion (cycle-based reactive only).';
COMMENT ON COLUMN workspaces.target_live_count_override IS
    'Admin-set override of package.target_live_count. NULL = use package default. '
    'Trigger enforces 0 <= override <= package.target_live_count. Lowering the override '
    'does NOT actively demote already-deployed inboxes — it only governs new promotions, '
    'so attrition naturally brings the live count down to the new target.';
COMMENT ON COLUMN workspaces.pause_pool_transitions IS
    'When TRUE, orchestrator skips the threshold-maintenance phase for this workspace. '
    'Lifecycle and kill paths still run; only proactive promotion is paused.';

-- ──────────────────────────────────────────────────────────────────────────
-- 3. Trigger: validate override <= package target at write time
-- ──────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION validate_target_live_override() RETURNS TRIGGER AS $$
DECLARE pkg_target INTEGER;
BEGIN
    -- NULL override means "use package default" — always allowed.
    IF NEW.target_live_count_override IS NULL THEN
        RETURN NEW;
    END IF;

    -- Override requires a package to be assigned (otherwise what's the ceiling?)
    IF NEW.package_id IS NULL THEN
        RAISE EXCEPTION
            'target_live_count_override requires a package_id (workspace %)',
            NEW.id;
    END IF;

    IF NEW.target_live_count_override < 0 THEN
        RAISE EXCEPTION
            'target_live_count_override cannot be negative (got %)',
            NEW.target_live_count_override;
    END IF;

    -- Override is a CEILING constraint — admin can only LOWER from package default.
    -- Raising above package target makes no sense — the package is the contract.
    SELECT target_live_count INTO pkg_target
    FROM workspace_packages WHERE id = NEW.package_id;

    IF pkg_target IS NULL THEN
        RAISE EXCEPTION
            'package_id % does not exist', NEW.package_id;
    END IF;

    IF NEW.target_live_count_override > pkg_target THEN
        RAISE EXCEPTION
            'target_live_count_override (%) cannot exceed package target_live_count (%)',
            NEW.target_live_count_override, pkg_target;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validate_target_live_override ON workspaces;
CREATE TRIGGER trg_validate_target_live_override
    BEFORE INSERT OR UPDATE OF target_live_count_override, package_id ON workspaces
    FOR EACH ROW
    EXECUTE FUNCTION validate_target_live_override();

-- ──────────────────────────────────────────────────────────────────────────
-- 4. Resolved-targets view — single source for the orchestrator to read
-- ──────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW workspace_effective_targets AS
SELECT
    w.id                                            AS workspace_id,
    w.workspace_name,
    p.id                                            AS package_id,
    p.name                                          AS package_name,
    p.target_monthly_sends,
    p.target_live_count                             AS package_live_target,
    p.target_reserve_count                          AS package_reserve_minimum,
    w.target_live_count_override,
    COALESCE(w.target_live_count_override,
             p.target_live_count)                   AS effective_live_target,
    p.target_reserve_count                          AS effective_reserve_minimum,
    w.pause_pool_transitions,
    w.package_assigned_at
FROM workspaces w
LEFT JOIN workspace_packages p ON p.id = w.package_id
WHERE w.is_active = TRUE;

COMMENT ON VIEW workspace_effective_targets IS
    'Resolved capacity targets per workspace. effective_live_target = override if set, '
    'else package default. NULL package_id = no proactive promotion (orchestrator '
    'short-circuits the threshold-maintenance phase for this workspace).';

-- ──────────────────────────────────────────────────────────────────────────
-- 5. Index supporting the orchestrator's effective-targets lookup
-- ──────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_workspaces_package_id
    ON workspaces (package_id)
    WHERE package_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_workspaces_pause_pool_transitions
    ON workspaces (id)
    WHERE pause_pool_transitions = TRUE;
