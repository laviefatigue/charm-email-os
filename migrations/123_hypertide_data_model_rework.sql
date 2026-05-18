-- Migration 123: Hypertide data model rework — clients <-> workspaces 1:many,
--                client-level F&F tagging, subscription-as-identity binding,
--                plus the qualifies_for_cancellation_at verdict column for the
--                Phase 2 change tracker.
--
-- Plan: docs/plans/hypertide-data-model-and-change-tracking.md (DECISIONS 1-6)
--
-- This is the ADDITIVE phase. No columns are dropped. clients.workspace_id
-- stays in place so existing read paths keep working while code is migrated
-- to workspaces.client_id and the v_operational_* views. A follow-up
-- migration will drop clients.workspace_id (and workspaces.manages_via_hypertide)
-- once all reads are confirmed on the new model.
--
-- Safe to re-run: every ADD COLUMN / CREATE uses IF NOT EXISTS. The
-- workspaces.client_id backfill is idempotent (WHERE client_id IS NULL).
--
-- What this enables (but does not yet wire up):
--   - hypertide-worker can switch to subscription-keyed ingest (step 5)
--   - kill-trigger evaluator can write the verdict (step 8)
--   - Phase 2 change tracker can read it (step 9)

BEGIN;

-- =====================================================================
-- 1. clients: add client_status + primary_hypertide_organization_name
-- =====================================================================

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS client_status VARCHAR(24) NOT NULL DEFAULT 'client',
    ADD COLUMN IF NOT EXISTS primary_hypertide_organization_name TEXT;

COMMENT ON COLUMN clients.client_status IS
    'Operational classification: client | friends_and_family | prospect | inactive. '
    'Default ''client'' applies to existing rows on migration (they''re real clients '
    'today). The hypertide-worker explicitly INSERTs newly-discovered HT subscriptions '
    'with ''friends_and_family'' per DECISION 5 — asymmetric error cost (bad kill '
    'decisions are not recoverable; operator promotion is one UPDATE). Operational '
    'reads should go through v_operational_clients which auto-filters F&F.';

COMMENT ON COLUMN clients.primary_hypertide_organization_name IS
    'Human-readable HT organizationName for ops UI. NOT a unique key. HT exposes no '
    'stable organization identifier — organizationName is plural per real customer '
    '(Hello Hero has 5 variants, Charm 6, Stable Kernel 4 — verified 2026-05-13). '
    'For HT identity binding see client_hypertide_subscriptions.';


-- =====================================================================
-- 2. workspaces: client_id (1:many parent FK), provider, routing pattern
-- =====================================================================

ALTER TABLE workspaces
    ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id),
    ADD COLUMN IF NOT EXISTS provider VARCHAR(16) NOT NULL DEFAULT 'emailbison',
    ADD COLUMN IF NOT EXISTS forwarding_domain_pattern TEXT;

-- Workspace provider must match what we sync from. emailbison is the only
-- platform we currently extract from; instantly is forward-looking
-- (OPEN #3 — Instantly extraction is a separate workstream).
ALTER TABLE workspaces
    DROP CONSTRAINT IF EXISTS workspaces_provider_check,
    ADD CONSTRAINT workspaces_provider_check
        CHECK (provider IN ('emailbison', 'instantly'));

COMMENT ON COLUMN workspaces.client_id IS
    'Parent client. 1:many — multiple workspaces can belong to one client. '
    'Canonical examples: Stable Kernel has 2 EB workspaces; Ink''d has 1 EB + 1 '
    'Instantly. Replaces the legacy clients.workspace_id 1:1 FK after the code '
    'migration is complete (follow-up migration drops clients.workspace_id).';

COMMENT ON COLUMN workspaces.provider IS
    'Inbox-infrastructure platform: emailbison | instantly. Used by the HT-record '
    'routing rule per RESOLVED #5 — when forwarding_domain_pattern is not '
    'specific enough, sendingTool from the HT record maps to provider here.';

COMMENT ON COLUMN workspaces.forwarding_domain_pattern IS
    'Optional disambiguator for routing HT domains to this specific workspace under '
    'a multi-workspace client. Matched against the HT record''s forwardingDomain '
    'field. Stable Kernel uses this to route market-research domains to a separate '
    'workspace (stablekernel.com/services/market-research vs plain stablekernel.com). '
    'NULL means no pattern — fall through to provider-based or operator-decided routing.';

CREATE INDEX IF NOT EXISTS workspaces_client_id_idx
    ON workspaces(client_id)
    WHERE client_id IS NOT NULL;


-- =====================================================================
-- 3. Backfill workspaces.client_id from the existing clients.workspace_id
--    Idempotent: only fills NULL client_id rows.
-- =====================================================================

UPDATE workspaces w
SET client_id = c.id
FROM clients c
WHERE c.workspace_id = w.id
  AND w.client_id IS NULL;


-- =====================================================================
-- 4. client_hypertide_subscriptions — HT identity binding (RESOLVED #1)
--
--    HT exposes no stable organization identifier. Stripe subscription_id IS
--    stable and IS what HT keys billing on (we verified this across the whole
--    /orders/active surface during Phase 1). This table maps each Stripe
--    subscription to a CharmOS client.
--
--    Populated by:
--      (a) operator seed step (one-shot, ~211 subs as of 2026-05-06)
--      (b) hypertide-worker on first sync of an unknown sub
--          (creates new clients row with client_status='friends_and_family',
--           inserts binding row pointing at it)
-- =====================================================================

CREATE TABLE IF NOT EXISTS client_hypertide_subscriptions (
    subscription_id   TEXT PRIMARY KEY,
    client_id         UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    organization_name TEXT,
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS chs_client_idx
    ON client_hypertide_subscriptions(client_id);

CREATE INDEX IF NOT EXISTS chs_last_seen_idx
    ON client_hypertide_subscriptions(last_seen_at);

COMMENT ON TABLE client_hypertide_subscriptions IS
    'Maps Stripe subscription_id (HT''s stable billing identifier) to CharmOS '
    'client. One subscription = one client; one client can have many. Populated '
    'by hypertide-worker (first-sync auto-creates client + binding) or operator '
    'seed. organization_name is the HT label at first/last sight, retained for '
    'ops UI; it is NOT a unique key.';


-- =====================================================================
-- 5. v_operational_* views — DEFAULT read API for operational code
--
--    Per Concern A: scattering WHERE client_status NOT IN (...) across every
--    read path is the failure mode this design exists to prevent. Operational
--    code reads these views by default. Reports and the change tracker that
--    need the full picture (including F&F) read base tables explicitly.
--
--    Inverts the failure mode: you have to opt INTO seeing F&F, not remember
--    to filter it out.
-- =====================================================================

CREATE OR REPLACE VIEW v_operational_clients AS
    SELECT * FROM clients
    WHERE client_status NOT IN ('friends_and_family', 'inactive');

CREATE OR REPLACE VIEW v_operational_workspaces AS
    SELECT w.* FROM workspaces w
    JOIN v_operational_clients c ON c.id = w.client_id;

CREATE OR REPLACE VIEW v_operational_domains AS
    SELECT d.* FROM domains d
    JOIN v_operational_workspaces w ON w.id = d.workspace_id;

COMMENT ON VIEW v_operational_clients IS
    'Default read API for operational CharmOS code (kill triggers, rotation, '
    'dashboards, health monitoring, GTM-scoped reports). Filters out '
    'friends_and_family and inactive clients automatically. Code that needs the '
    'full picture (financial reporting, drift detection, change tracker) reads '
    'the clients base table directly.';

COMMENT ON VIEW v_operational_workspaces IS
    'Workspaces under operational clients only. Same opt-in/opt-out convention '
    'as v_operational_clients.';

COMMENT ON VIEW v_operational_domains IS
    'Domains under operational workspaces only. Same opt-in/opt-out convention. '
    'Joins through both views so F&F filtering is transitive.';


-- =====================================================================
-- 6. domains: qualifies_for_cancellation_at + reason (DECISION 6)
--
--    The kill-trigger evaluator writes these columns at the moment a domain
--    crosses a burn threshold. The hypertide-worker change tracker reads them
--    at HT-transition-detection time to label cancellations as justified
--    (our rules said so) vs unjustified (HT or operator acted without our
--    recommendation).
--
--    Persisting at kill-time (not re-deriving at transition-time) is the only
--    honest answer — rules and rule-state evolve between kill fire-time and
--    HT execution time (ADR-010 was a real rule change). Re-derivation at
--    transition time would give wrong answers for old transitions.
-- =====================================================================

ALTER TABLE domains
    ADD COLUMN IF NOT EXISTS qualifies_for_cancellation_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS qualifies_for_cancellation_reason TEXT;

COMMENT ON COLUMN domains.qualifies_for_cancellation_at IS
    'Set by the kill-trigger evaluator (see docs/KILL-TRIGGERS.md) when this '
    'domain crossed a burn threshold. Persists "our system said this should be '
    'cancelled at time X" so the hypertide-worker change tracker can label HT '
    'cancellations as justified vs unjustified. Idempotent — re-firing on the '
    'same domain updates the timestamp. A revert (domain promoted back from dead) '
    'should set this to NULL along with the reason.';

COMMENT ON COLUMN domains.qualifies_for_cancellation_reason IS
    'Which kill-trigger rule fired (e.g. ''spam_complaint_rate_1.5pct'', '
    '''workspace_circuit_breaker''). Used by the change tracker as verdict '
    'evidence.';

CREATE INDEX IF NOT EXISTS domains_qualifies_for_cancellation_at_idx
    ON domains(qualifies_for_cancellation_at)
    WHERE qualifies_for_cancellation_at IS NOT NULL;


COMMIT;


-- =====================================================================
-- Follow-up (NOT in this migration):
--
-- After all operational reads have been migrated to v_operational_* views,
-- AND after the hypertide-worker has switched to subscription-keyed ingest
-- (writing client_hypertide_subscriptions rows for unknown subs), a future
-- migration should:
--
--   1. ALTER TABLE clients DROP COLUMN workspace_id;
--   2. ALTER TABLE workspaces DROP COLUMN manages_via_hypertide;
--
-- BOTH of those are blocked on code-side work and operator confirmation of
-- parity. They do NOT happen automatically. domains.is_legacy is KEPT (per
-- Concern C) with its original "acquired outside the HT pipeline" semantic.
-- =====================================================================
