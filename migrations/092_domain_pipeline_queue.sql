-- Migration 092: Domain Purchase Pipeline
--
-- Implements a multi-stage, queue-driven pipeline for purchasing domains at
-- Dynadot, flipping nameservers to DNSimple, and provisioning inboxes through
-- the Hypertide API (with per-workspace Bison targeting).
--
-- Problem this solves:
--   The old purchase pipeline (deleted in this branch: purchase_worker.py,
--   hypertide_playwright.py, domain_generator_worker.py) was a tangle of
--   Playwright browser automation, MCP-per-worker processes, and polling
--   daemons reading from bespoke tables. There was no clean seam between
--   "decide what to buy" and "execute the buy reliably", and failure modes
--   could produce runaway purchases on retry.
--
-- New model:
--   Decision layer lives outside the pipeline (Claude Code, future frontend,
--   other agents). Execution is a queue-driven worker that consumes a purchase
--   order and advances it through 5 stages, with two explicit money gates:
--
--     Gate 1: enqueue_domain_purchase() — workspace readiness + spend-cap check
--       │
--       ▼
--     Stage A: dynadot_register  — register domain, set NS to DNSimple
--     Stage B: ns_verify          — confirm NS propagated
--     Stage C: hypertide_order    — POST /orders (BYOD, unpaid, recordId stored)
--       │
--       ▼
--     Gate 2: approve_hypertide_charge() — per-workspace auto_charge flag or
--                                          explicit human/MCP approval
--       │
--       ▼
--     Stage D: hypertide_charge   — POST /payments/charge with recordIds
--     Stage E: hypertide_verify   — poll /orders/active until Done + Paid
--
-- Design notes:
--   - Job grain = one Hypertide order (2 Entra or 5 Google domains). Mirrors
--     vendor's grain, preserves Hypertide's $50/mo order-level pricing, and
--     keeps the /orders and /payments/charge calls atomic per row.
--   - Per-domain state lives in domain_pipeline_items with its own status
--     enum, so partial-success states (1 of 2 domains registered) are visible.
--   - Partial UNIQUE index on items.domain_name WHERE status NOT IN
--     ('dead','failed') is the idempotency guard: the enqueue endpoint cannot
--     create a second live attempt for the same domain.
--   - FOR UPDATE SKIP LOCKED in the consumer (future worker) prevents
--     double-claiming across horizontally-scaled worker instances.
--   - Money safety is split between DB constraints (CHECK, UNIQUE), the
--     enqueue-time guardrails in api/services/purchase_guardrails.py, and
--     the two-step Hypertide payment API. No single layer carries all the
--     weight.
--
-- Related tables:
--   workspaces          (00_public_schema.sql)    — FK target
--   clients             (00_public_schema.sql)    — FK target
--   domains             (00_public_schema.sql)    — linked post-provisioning
--   workspace_api_keys  (089)                     — per-workspace Bison token
--   sync_audit_log      (020)                     — reused for per-stage audit


-- ═══════════════════════════════════════════════════════════════════════════
-- workspace_purchase_config — per-workspace premap
-- ═══════════════════════════════════════════════════════════════════════════
-- Every workspace that will ever purchase must have a row here. The enqueue
-- readiness check fails loudly if the row is missing or incomplete.
--
-- NOT stored here (by design):
--   - Bison username/password/URL — shared org-level creds, from env vars
--     BISON_STANDARD_USERNAME / BISON_STANDARD_PASSWORD / BISON_URL
--   - Bison API key — already in workspace_api_keys (scoped per workspace)
--   - Workspace name — already on workspaces.workspace_name

CREATE TABLE IF NOT EXISTS workspace_purchase_config (
    workspace_id    UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,

    -- Budget (all in cents = USD * 100)
    purchase_cap_cents  INTEGER NOT NULL DEFAULT 0
        CHECK (purchase_cap_cents >= 0),
    spent_cents         INTEGER NOT NULL DEFAULT 0
        CHECK (spent_cents >= 0),

    -- Gate 2 policy: if TRUE the worker auto-advances past awaiting_charge.
    -- Default FALSE — human must approve each Hypertide charge via the
    -- approve_hypertide_charge endpoint. Flip to TRUE only for trusted,
    -- high-volume workspaces after establishing pipeline confidence.
    auto_charge_hypertide   BOOLEAN NOT NULL DEFAULT FALSE,

    -- Hypertide order defaults (overridable per-order at enqueue time)
    default_forwarding_domain  TEXT,
    default_warmup_setup       JSONB NOT NULL DEFAULT
        '{"enabled":true,"settings":{"warmup_limit":5,"warmup_reply_rate":100,"warmup_increment":1}}'::jsonb,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE workspace_purchase_config IS
    'Per-workspace purchase settings: budget caps, Gate 2 auto-charge policy, '
    'Hypertide payload defaults. Credentials NOT stored here.';

COMMENT ON COLUMN workspace_purchase_config.purchase_cap_cents IS
    'Hard ceiling for total outstanding + spent purchase cost. Enforced at '
    'enqueue time AND re-checked at claim time in the worker.';

COMMENT ON COLUMN workspace_purchase_config.auto_charge_hypertide IS
    'Gate 2 policy. FALSE (default) requires explicit approve_hypertide_charge '
    'call. TRUE auto-advances from awaiting_charge to hypertide_charge stage.';


-- ═══════════════════════════════════════════════════════════════════════════
-- domain_pipeline_queue — the parent job (one per Hypertide order)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS domain_pipeline_queue (
    id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ── TRACKING (required, premapped at enqueue) ─────────────────────────
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
        -- ON DELETE RESTRICT: losing a workspace with open jobs is a bug.
    client_id     UUID REFERENCES clients(id) ON DELETE SET NULL,
    requested_by  TEXT NOT NULL,
        -- Identifier of the caller (e.g. 'claude-code:elliott@...', 'agent:bot').

    -- ── HYPERTIDE ORDER INPUTS (required, premapped at enqueue) ───────────
    plan VARCHAR(16) NOT NULL
        CHECK (plan IN ('entra', 'google')),
    forwarding_domain  TEXT NOT NULL,
        -- Overrides workspace_purchase_config.default_forwarding_domain if set.
    selected_tool  VARCHAR(16) NOT NULL DEFAULT 'bison'
        CHECK (selected_tool IN ('bison', 'smartlead', 'instantly', 'other')),
        -- Hypertide's selected_tool field. Drives tool_credentials shape.
    users  JSONB NOT NULL,
        -- [{first_name, last_name}, ...]
    warmup_setup  JSONB NOT NULL,
        -- Full warmup_setup payload passed to Hypertide. Resolved at enqueue
        -- from workspace default + per-order override.
    profile_picture_link  TEXT,
        -- google plan only

    -- ── BUDGET ENVELOPE (required, premapped at enqueue) ──────────────────
    -- These are per-ORDER maximums, used by Stage A (Dynadot) and Stage D
    -- (Hypertide charge) to refuse to proceed if actual costs exceed them.
    max_dynadot_cost_cents  INTEGER NOT NULL
        CHECK (max_dynadot_cost_cents >= 0),
        -- Per-domain ceiling. Each domain_pipeline_items row that exceeds
        -- this during Dynadot lookup fails the item, not the whole order.
    max_hypertide_one_time  INTEGER NOT NULL DEFAULT 0
        CHECK (max_hypertide_one_time >= 0),
        -- Zero for BYOD (our default). Non-zero only for purchase_domain_for_me.
    max_hypertide_monthly   INTEGER NOT NULL DEFAULT 5000
        CHECK (max_hypertide_monthly >= 0),
        -- Hypertide's documented $50/mo per order.

    -- ── STATE MACHINE ─────────────────────────────────────────────────────
    stage  VARCHAR(32) NOT NULL DEFAULT 'dynadot_register'
        CHECK (stage IN (
            'dynadot_register',   -- Stage A: register + NS flip at Dynadot
            'ns_verify',          -- Stage B: confirm NS propagated (DNSimple)
            'hypertide_order',    -- Stage C: POST /orders, store recordIds
            'awaiting_charge',    -- Gate 2 hold: waiting for approval
            'hypertide_charge',   -- Stage D: POST /payments/charge
            'hypertide_verify',   -- Stage E: poll /orders/active
            'complete'            -- terminal success
        )),
    status  VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'complete', 'failed', 'dead')),
        -- pending  → claimable by worker
        -- running  → currently in a handler
        -- complete → terminal success (stage='complete')
        -- failed   → current stage failed; scheduler may re-queue
        -- dead     → terminal failure; requires human intervention
    priority  INTEGER NOT NULL DEFAULT 0,
        -- Consumer sort: higher = processed first.
    attempts  INTEGER NOT NULL DEFAULT 0,
        -- Incremented on each claim. max_attempts enforced in worker.
    not_before  TIMESTAMPTZ,
        -- Scheduled retry gate. If set, the worker MUST NOT claim this job
        -- until NOW() >= not_before. Used by handlers that need backoff
        -- (e.g. ns_verify waiting for DNS propagation, transient-error retry).
        -- NULL = claimable immediately (the common case).

    -- ── HYPERTIDE RESULTS (derived) ───────────────────────────────────────
    hypertide_subscription_id  TEXT,
        -- Returned by POST /payments/charge. Needed for subscription cancel.

    -- ── LIFECYCLE ─────────────────────────────────────────────────────────
    queued_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at          TIMESTAMPTZ,
    charge_approved_at  TIMESTAMPTZ,
    charge_approved_by  TEXT,
    completed_at        TIMESTAMPTZ,
    error_message       TEXT,

    -- ── WORKER SCRATCHPAD ─────────────────────────────────────────────────
    runtime_state  JSONB NOT NULL DEFAULT '{}'::jsonb
        -- Small, opaque to DB. Per-stage retry counts, last poll timestamps,
        -- NS propagation check history. Do NOT duplicate columns here.
);

-- ── Primary consumer index ───────────────────────────────────────────────
-- Covers the worker's claim query:
--   SELECT * FROM domain_pipeline_queue
--   WHERE status = 'pending' AND stage = $1
--     AND (not_before IS NULL OR NOW() >= not_before)
--   ORDER BY priority DESC, queued_at ASC
--   FOR UPDATE SKIP LOCKED
-- The not_before condition is not in the index WHERE clause because it's
-- a NOW()-dependent check; PostgreSQL still uses the index for the other
-- filters and applies the time comparison on each matching row.
CREATE INDEX IF NOT EXISTS idx_domain_pipeline_claim
    ON domain_pipeline_queue (stage, priority DESC, queued_at ASC)
    WHERE status = 'pending';

-- ── Open-work lookup (for funding forecast + dashboards) ─────────────────
CREATE INDEX IF NOT EXISTS idx_domain_pipeline_ws_open
    ON domain_pipeline_queue (workspace_id, stage)
    WHERE status IN ('pending', 'running');

-- ── Cleanup index ────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_domain_pipeline_completed
    ON domain_pipeline_queue (completed_at)
    WHERE status IN ('complete', 'failed', 'dead');

COMMENT ON TABLE domain_pipeline_queue IS
    'Purchase order queue. One row = one Hypertide order = 2 Entra or 5 '
    'Google domains. Advances through stages A-E with two money gates.';

COMMENT ON COLUMN domain_pipeline_queue.stage IS
    'Current pipeline stage. A:dynadot_register → B:ns_verify → '
    'C:hypertide_order → awaiting_charge (Gate 2) → D:hypertide_charge → '
    'E:hypertide_verify → complete.';

COMMENT ON COLUMN domain_pipeline_queue.status IS
    'Lifecycle: pending → running → (complete | failed | dead). '
    'failed = retry candidate; dead = human intervention required.';

COMMENT ON COLUMN domain_pipeline_queue.runtime_state IS
    'Opaque worker scratchpad: per-stage retry counts, last poll timestamps, '
    'NS propagation history. Do NOT move to dedicated columns — this is '
    'churny state, not queryable data.';


-- ═══════════════════════════════════════════════════════════════════════════
-- domain_pipeline_items — per-domain children (2-5 per order)
-- ═══════════════════════════════════════════════════════════════════════════
-- Each domain in the order has its own lifecycle because partial success
-- is real: 1-of-2 Dynadot registrations can fail, 1-of-5 NS verifications
-- can time out, etc. The order's aggregate status is a function of its
-- items; the worker makes all-or-nothing decisions (e.g. don't charge
-- Hypertide if any item is in 'failed') but the per-item record remains
-- so operators can diagnose and surgically retry.

CREATE TABLE IF NOT EXISTS domain_pipeline_items (
    id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id  UUID NOT NULL REFERENCES domain_pipeline_queue(id) ON DELETE CASCADE,

    domain_name  TEXT NOT NULL,
    tld          TEXT NOT NULL,

    -- Per-item lifecycle (independent of order's stage)
    status  VARCHAR(24) NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',         -- not yet touched by worker
            'registered',      -- Dynadot register succeeded
            'ns_flipped',      -- Dynadot NS set to DNSimple list
            'ns_verified',     -- dig NS <domain> returned DNSimple
            'hypertide_added', -- included in Hypertide order, recordId stored
            'paid',            -- Hypertide charge succeeded
            'provisioned',     -- /orders/active shows Done+Paid, linked to domains table
            'failed',          -- transient failure, may retry
            'dead'             -- terminal failure
        )),

    -- Dynadot results
    dynadot_order_id       TEXT,
    dynadot_cost_cents     INTEGER CHECK (dynadot_cost_cents IS NULL OR dynadot_cost_cents >= 0),
    dynadot_registered_at  TIMESTAMPTZ,
    ns_flipped_at          TIMESTAMPTZ,
    ns_verified_at         TIMESTAMPTZ,

    -- Hypertide results
    hypertide_record_id        TEXT,
    hypertide_status           VARCHAR(16),
        -- "To do" / "Done" as returned by Hypertide
    hypertide_payment_status   VARCHAR(16),
        -- "Unpaid" / "Paid"

    -- Link to main domain inventory once fully provisioned
    domain_id  UUID REFERENCES domains(id) ON DELETE SET NULL,

    error_message  TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Idempotency guard ────────────────────────────────────────────────────
-- Prevents two simultaneous live attempts for the same domain_name. A dead
-- or failed attempt can be followed by a new live one — the worker marks
-- truly-terminal items as 'dead' specifically so a retry can re-enqueue.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pipeline_items_live_domain
    ON domain_pipeline_items (domain_name)
    WHERE status NOT IN ('dead', 'failed');

-- ── Lookup by parent order ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_pipeline_items_order
    ON domain_pipeline_items (order_id);

-- ── Lookup by linked domain (operator debugging) ─────────────────────────
CREATE INDEX IF NOT EXISTS idx_pipeline_items_domain_id
    ON domain_pipeline_items (domain_id)
    WHERE domain_id IS NOT NULL;

COMMENT ON TABLE domain_pipeline_items IS
    'Per-domain child rows. One order row in domain_pipeline_queue fans out '
    'into 2-5 item rows here (Entra=2, Google=5 per Hypertide playbook).';

COMMENT ON COLUMN domain_pipeline_items.status IS
    'Per-item lifecycle independent of the parent order stage. Worker '
    'updates this as each sub-step succeeds for each domain.';


-- ═══════════════════════════════════════════════════════════════════════════
-- v_pipeline_funding_forecast — "what will it cost to drain the queue?"
-- ═══════════════════════════════════════════════════════════════════════════
-- Per-workspace open-job cost projection. Used by:
--   (1) enqueue guardrail: refuse new orders if balance insufficient
--   (2) Slack alerter: warn when workspace is underfunded
--   (3) future dashboard: "$X needed for Y pending orders"

-- Aggregate per order first (so we count each order once, not once per item),
-- then roll up to workspace. Using SUM(DISTINCT ...) directly on the joined
-- set would collapse equal values across different orders — wrong.
CREATE OR REPLACE VIEW v_pipeline_funding_forecast AS
WITH order_forecast AS (
    SELECT
        q.id               AS order_id,
        q.workspace_id,
        q.status,
        q.stage,
        q.max_dynadot_cost_cents,
        q.max_hypertide_one_time,
        q.max_hypertide_monthly,
        COUNT(i.id) FILTER (WHERE i.status = 'pending') AS pending_item_count
    FROM domain_pipeline_queue q
    LEFT JOIN domain_pipeline_items i ON i.order_id = q.id
    GROUP BY q.id
)
SELECT
    workspace_id,
    COUNT(*) FILTER (WHERE status IN ('pending', 'running')) AS open_orders,
    COALESCE(SUM(pending_item_count) FILTER (
        WHERE status IN ('pending', 'running')
    ), 0) AS pending_dynadot_items,
    -- Per-item Dynadot spend: items still to be registered × per-order max cost
    COALESCE(SUM(max_dynadot_cost_cents * pending_item_count) FILTER (
        WHERE status IN ('pending', 'running')
    ), 0) AS projected_dynadot_cents,
    -- Per-order Hypertide one-time: only if payment not yet charged
    COALESCE(SUM(max_hypertide_one_time) FILTER (
        WHERE status IN ('pending', 'running')
          AND stage IN ('dynadot_register', 'ns_verify', 'hypertide_order',
                        'awaiting_charge', 'hypertide_charge')
    ), 0) AS projected_hypertide_one_time_cents,
    -- Per-order Hypertide monthly commitment (same condition)
    COALESCE(SUM(max_hypertide_monthly) FILTER (
        WHERE status IN ('pending', 'running')
          AND stage IN ('dynadot_register', 'ns_verify', 'hypertide_order',
                        'awaiting_charge', 'hypertide_charge')
    ), 0) AS projected_hypertide_monthly_cents
FROM order_forecast
GROUP BY workspace_id;

COMMENT ON VIEW v_pipeline_funding_forecast IS
    'Worst-case drain cost per workspace. Sums per-order max costs for '
    'pending+running orders. Used by enqueue guardrail and funding dashboard.';
