-- Phase 6B: Subscription Management
-- Client subscriptions tracking quotas and package configurations

-- Package templates table (reference data)
CREATE TABLE IF NOT EXISTS package_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,

    -- Entra configuration
    entra_packages INTEGER NOT NULL DEFAULT 6,
    entra_domains_per_package INTEGER DEFAULT 2,
    entra_inboxes_per_domain INTEGER DEFAULT 52,

    -- Google configuration
    google_packages INTEGER NOT NULL DEFAULT 5,
    google_domains_per_package INTEGER DEFAULT 5,
    google_inboxes_per_domain INTEGER DEFAULT 3,

    -- Calculated totals (stored for quick reference)
    total_domains INTEGER GENERATED ALWAYS AS (
        (entra_packages * entra_domains_per_package) +
        (google_packages * google_domains_per_package)
    ) STORED,
    total_inboxes INTEGER GENERATED ALWAYS AS (
        (entra_packages * entra_domains_per_package * entra_inboxes_per_domain) +
        (google_packages * google_domains_per_package * google_inboxes_per_domain)
    ) STORED,

    monthly_price DECIMAL(10,2),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Seed initial packages based on Infra - Domains x Inboxes.csv
INSERT INTO package_templates (name, entra_packages, google_packages, monthly_price)
VALUES
    ('Starter', 6, 5, NULL),   -- 37 domains, 699 inboxes
    ('Growth', 12, 10, NULL)   -- 74 domains, 1398 inboxes
ON CONFLICT (name) DO NOTHING;

-- Client subscriptions table
CREATE TABLE IF NOT EXISTS client_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Package reference (optional - can use template or custom)
    package_template_id UUID REFERENCES package_templates(id),

    -- Package configuration (can override template or be fully custom)
    -- Entra
    entra_packages INTEGER NOT NULL DEFAULT 6,
    entra_domains_per_package INTEGER DEFAULT 2,
    entra_inboxes_per_domain INTEGER DEFAULT 52,

    -- Google
    google_packages INTEGER NOT NULL DEFAULT 5,
    google_domains_per_package INTEGER DEFAULT 5,
    google_inboxes_per_domain INTEGER DEFAULT 3,

    -- Spare/buffer configuration
    spare_ratio DECIMAL(3,2) DEFAULT 0.15,  -- 15% spare capacity target

    -- Status
    status VARCHAR(20) DEFAULT 'active',  -- active, paused, cancelled
    started_at TIMESTAMP DEFAULT NOW(),
    cancelled_at TIMESTAMP,

    -- Tracking
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- One active subscription per client
    CONSTRAINT unique_active_subscription UNIQUE (client_id, status)
);

-- Indexes for subscriptions
CREATE INDEX IF NOT EXISTS idx_subscriptions_client ON client_subscriptions(client_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON client_subscriptions(status);

-- Subscription history for upgrades/downgrades
CREATE TABLE IF NOT EXISTS subscription_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID NOT NULL REFERENCES client_subscriptions(id) ON DELETE CASCADE,
    change_type VARCHAR(20) NOT NULL,  -- 'created', 'upgrade', 'downgrade', 'modify', 'cancelled'

    -- Previous values (null for 'created')
    previous_entra_packages INTEGER,
    previous_google_packages INTEGER,

    -- New values
    new_entra_packages INTEGER,
    new_google_packages INTEGER,

    reason TEXT,
    changed_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscription_changes_subscription ON subscription_changes(subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscription_changes_created ON subscription_changes(created_at);
