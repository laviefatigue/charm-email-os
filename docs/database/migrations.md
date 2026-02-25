---
title: Database Migrations
created: 2026-01-16
updated: 2026-02-23
tags: [database, migrations, warmup, health, daily-volume]
---

# Database Migrations

Migration history for Charm Email OS.

## Migration Log

### Initial Schema (Pre-documentation)

Tables created before formal migration tracking:

| Table | Created |
|-------|---------|
| clients | Initial |
| workspaces | Initial (OwnRBL) |
| domains | Initial |
| sender_accounts | Initial |
| client_onboarding_submissions | Initial |
| client_segments | Initial |
| client_personas | Initial |
| domain_generation_jobs | Initial |

### Planned Migrations

#### Phase 1: Client Profile Columns

**Status**: Pending

Add dedicated columns to `clients` table for basic info:

```sql
-- Migration: 001_add_client_profile_columns.sql
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_name VARCHAR(255);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS website VARCHAR(255);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS industry VARCHAR(100);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS domain_pattern VARCHAR(255);
```

#### Phase 3: Strategy Generation Tables

**Status**: Pending

Create tables for AI strategy generation:

```sql
-- Migration: 002_create_strategy_tables.sql

-- Strategy generation jobs
CREATE TABLE strategy_generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    submission_id UUID REFERENCES client_onboarding_submissions(id),
    status VARCHAR(50) DEFAULT 'pending',
    generation_round INTEGER DEFAULT 1,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_strategy_jobs_status ON strategy_generation_jobs(status);
CREATE INDEX idx_strategy_jobs_client ON strategy_generation_jobs(client_id);

-- Strategy suggestions
CREATE TABLE strategy_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    variant_number INTEGER NOT NULL,
    subject_line TEXT NOT NULL,
    email_body TEXT NOT NULL,
    score INTEGER,
    rationale TEXT,
    used_variables JSONB,
    missing_variables JSONB,
    campaign_type VARCHAR(50),
    status VARCHAR(50) DEFAULT 'pending',
    human_comment TEXT,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP,
    generation_round INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_suggestions_job ON strategy_suggestions(job_id);
CREATE INDEX idx_suggestions_client ON strategy_suggestions(client_id);
CREATE INDEX idx_suggestions_status ON strategy_suggestions(status);

-- Revision requests
CREATE TABLE strategy_revision_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    variant_id UUID REFERENCES strategy_suggestions(id),
    instruction TEXT NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_revisions_job ON strategy_revision_requests(job_id);
```

### Recent Migrations (2026-02)

#### 018_health_rotation_schema.sql

**Status**: Applied

Adds health metrics and rotation tracking:

```sql
-- Health columns on sender_accounts
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS inbox_state VARCHAR(20) DEFAULT 'live';
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS hard_bounces_24h INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS hard_bounces_7d INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS health_score INTEGER DEFAULT 100;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS pool_tier VARCHAR(20) DEFAULT 'primary';

-- Kill trigger tracking
CREATE TABLE IF NOT EXISTS kill_trigger_events (...);
CREATE TABLE IF NOT EXISTS inbox_health_snapshots (...);
CREATE TABLE IF NOT EXISTS inbox_rotation_history (...);
```

#### 021_inventory_management_schema.sql

**Status**: Applied

Adds inventory pool status and feature flags:

```sql
-- Pool status tracking
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS inventory_pool_status VARCHAR(20) DEFAULT 'reserve';
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS inventory_lifecycle_status VARCHAR(20) DEFAULT 'incubating';

-- Feature flags table
CREATE TABLE IF NOT EXISTS feature_flags (...);

-- Inventory audit log
CREATE TABLE IF NOT EXISTS inventory_audit_log (...);
```

#### 026_warmup_tracking_schema.sql

**Status**: Applied (2026-02-13)

Adds warmup lifecycle tracking:

```sql
-- Warmup status columns
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS warmup_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS warmup_started_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS warmup_stopped_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS sending_started_at TIMESTAMP WITH TIME ZONE;

-- Index for warmup queries
CREATE INDEX IF NOT EXISTS idx_sender_accounts_warmup
ON sender_accounts (warmup_enabled, warmup_started_at)
WHERE is_active = TRUE;

-- Time-series warmup statistics
CREATE TABLE IF NOT EXISTS sender_warmup_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_account_id UUID NOT NULL REFERENCES sender_accounts(id) ON DELETE CASCADE,
    snapshot_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    warmup_enabled BOOLEAN DEFAULT FALSE,
    warmup_score INTEGER,
    warmup_emails_sent INTEGER DEFAULT 0,
    warmup_replies_received INTEGER DEFAULT 0,
    warmup_bounces_received_count INTEGER DEFAULT 0,
    ...
);

-- Audit log for warmup sync runs
CREATE TABLE IF NOT EXISTS warmup_check_runs (...);
```

**Note**: Backfill is deferred to sync worker. The `warmup_started_at` is set as `first_seen_at + 7 days` when warmup is first detected.

#### 028_sender_account_metrics.sql

**Status**: Applied (2026-02-13)

Adds all-time sending metrics to match EmailBison UI:

```sql
-- All-time metrics (from EmailBison API)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS emails_sent_all_time INTEGER DEFAULT 0;

ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS replies_all_time INTEGER DEFAULT 0;

ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS bounces_all_time INTEGER DEFAULT 0;

ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS daily_limit INTEGER DEFAULT 0;

-- Index for metrics queries
CREATE INDEX IF NOT EXISTS idx_sender_accounts_metrics
ON sender_accounts (emails_sent_all_time, bounces_all_time)
WHERE is_active = TRUE;
```

**Note**: These columns match the "Emails Sent (All Time)", "Replied", and "Bounced" columns visible in EmailBison UI. Rate-based kill triggers are NOT implemented since absolute count thresholds (24h/7d bounces) catch the same problems.

#### 029_inventory_segmentation_fix.sql

**Status**: Applied (2026-02-13)

Fixes pool status calculation to properly distinguish Reserve vs Incubating:

```sql
-- Updated v_inbox_inventory_status view with corrected pool status logic
CREATE OR REPLACE VIEW v_inbox_inventory_status AS
SELECT
    sa.id, sa.email_address, sa.workspace_id, sa.inbox_state,
    sa.warmup_enabled, sa.warmup_started_at,

    -- Pool status calculation:
    -- deployed = in active campaigns
    -- warning = has bounces (1+ in 24h OR 3+ in 7d)
    -- reserve = 14+ days AND warmup enabled (deployment-ready)
    -- incubating = under 14 days OR warmup not enabled (still warming)
    CASE
        WHEN sa.inbox_state = 'dead' THEN NULL
        WHEN COALESCE(sa.hard_bounces_24h, 0) >= 1
             OR COALESCE(sa.hard_bounces_7d, 0) >= 3 THEN 'warning'
        WHEN EXISTS (
            SELECT 1 FROM campaign_inboxes ci
            WHERE ci.sender_account_id = sa.id AND ci.is_active = TRUE
        ) THEN 'deployed'
        WHEN sa.created_at <= NOW() - INTERVAL '14 days'
             AND COALESCE(sa.warmup_enabled, TRUE) = TRUE THEN 'reserve'
        ELSE 'incubating'
    END as calculated_pool_status,
    ...
FROM sender_accounts sa
LEFT JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name;

-- Update existing pool status values
UPDATE sender_accounts SET inventory_pool_status = CASE
    WHEN inbox_state = 'dead' THEN NULL
    WHEN COALESCE(hard_bounces_24h, 0) >= 1 OR COALESCE(hard_bounces_7d, 0) >= 3 THEN 'warning'
    WHEN EXISTS (SELECT 1 FROM campaign_inboxes ci WHERE ci.sender_account_id = id AND ci.is_active) THEN 'deployed'
    WHEN created_at <= NOW() - INTERVAL '14 days' AND COALESCE(warmup_enabled, TRUE) = TRUE THEN 'reserve'
    ELSE 'incubating'
END WHERE inbox_state = 'live';
```

**Key Changes**:
- **Reserve** now requires BOTH: 14+ days old AND `warmup_enabled = TRUE`
- **Incubating** is the fallback for everything else (under 14 days OR warmup not enabled)
- Aligns with business logic: Reserve = deployment-ready inboxes only

### Health & Capacity Tracking (2026-02)

#### 032_domain_source_tracking.sql

**Status**: Applied (2026-02-22)

Tracks domain source (legacy vs HyperTide-generated):

```sql
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_source VARCHAR(20) DEFAULT 'legacy';
-- Values: 'legacy', 'hypertide_entra', 'hypertide_google'
```

#### 033_backfill_killed_at.sql

**Status**: Applied (2026-02-22)

Backfills `killed_at` timestamp for 5528 dead inboxes based on `tagged_at`.

#### 034_bounce_counter_reset.sql

**Status**: Applied (2026-02-22)

Adds function to reset 24h bounce counters daily:

```sql
CREATE OR REPLACE FUNCTION reset_24h_bounce_counters()
RETURNS INTEGER AS $$
-- Resets hard_bounces_24h, hard_blocked_24h, hard_unknown_24h to 0
$$;
```

#### 035_performance_indexes.sql

**Status**: Applied (2026-02-22)

Adds performance indexes for domain lookups:

```sql
CREATE INDEX IF NOT EXISTS idx_sender_accounts_domain_split
ON sender_accounts (SPLIT_PART(email_address, '@', 2));
```

#### 036_campaign_burn_events.sql

**Status**: Applied (2026-02-22)

Granular campaign burn tracking:

```sql
CREATE TABLE campaign_burn_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id VARCHAR(100) NOT NULL,
    workspace_id UUID REFERENCES workspaces(id),
    sender_account_id UUID REFERENCES sender_accounts(id),
    trigger_type VARCHAR(50) NOT NULL,
    -- spam_complaint, hard_blocked, hard_unknown, hard_bounces, bounce_rate, fresh_inbox
    burned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ...
);

-- Views for analysis
CREATE VIEW campaign_burn_summary AS ...
CREATE VIEW domain_burn_summary AS ...
CREATE VIEW recent_burn_summary AS ...
```

#### 037_domain_aggregate_metrics.sql

**Status**: Applied (2026-02-22)

Domain-wide health aggregation:

```sql
ALTER TABLE domains ADD COLUMN IF NOT EXISTS total_inboxes INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS live_inboxes INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS dead_inboxes INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_bounce_rate_7d NUMERIC(5,2);
ALTER TABLE domains ADD COLUMN IF NOT EXISTS inboxes_with_complaints INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS inboxes_with_blocks INTEGER DEFAULT 0;

-- Function to recalculate metrics
CREATE OR REPLACE FUNCTION recalculate_domain_metrics(p_domain_id UUID) ...

-- Alert view
CREATE VIEW domain_health_alerts AS ...
```

#### 038_domain_capacity_views.sql

**Status**: Applied (2026-02-23)

HyperTide capacity tracking views (database-only, no automation changes):

```sql
-- Per-domain capacity vs HyperTide expected
CREATE VIEW v_domain_capacity AS
SELECT
    domain_id, domain_name, provider_type,
    live_inboxes, dead_inboxes,
    current_daily_capacity, expected_daily_capacity,
    capacity_utilization_pct, viability_status
FROM ...

-- Workspace rollup by provider
CREATE VIEW v_workspace_capacity_summary AS ...

-- Domains below 70% utilization
CREATE VIEW v_domains_at_risk AS ...

-- Validation: daily_limit vs expected
CREATE VIEW v_capacity_validation AS ...
```

**HyperTide Capacity Model**:
- Entra: 50 inboxes/domain × 2 emails/day = 100 emails/day expected
- Google: 3 inboxes/domain × 20 emails/day = 60 emails/day expected

#### 040_fix_inventory_status_consistency.sql

**Status**: Applied (2026-02-23)

Fixes stale `inventory_lifecycle_status` and `inventory_pool_status` values to ensure consistency with actual inbox state.

#### 041_daily_volume_snapshots.sql

**Status**: Applied (2026-02-23)

Daily sending volume tracking for client dashboard time-series charts:

```sql
CREATE TABLE daily_volume_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    snapshot_date DATE NOT NULL,

    -- Volume metrics (backfilled from EmailBison campaign stats)
    emails_sent INTEGER NOT NULL DEFAULT 0,
    emails_delivered INTEGER NOT NULL DEFAULT 0,
    emails_bounced INTEGER NOT NULL DEFAULT 0,
    emails_complained INTEGER NOT NULL DEFAULT 0,

    -- Capacity metrics (snapshot as of end of day)
    live_inboxes INTEGER NOT NULL DEFAULT 0,
    incubating_inboxes INTEGER NOT NULL DEFAULT 0,
    dead_inboxes INTEGER NOT NULL DEFAULT 0,
    daily_capacity_available INTEGER NOT NULL DEFAULT 0,

    -- Derived metrics
    capacity_utilization_pct DECIMAL(5,2),
    kills_that_day INTEGER NOT NULL DEFAULT 0,

    UNIQUE(workspace_id, snapshot_date)
);
```

**Initial Backfill**: 54,716 emails backfilled across 7 active workspaces using `scripts/backfill_daily_volume.py`. Data coverage: Nov 25, 2025 - Feb 22, 2026 (90 days).

| Workspace | Backfilled | Coverage |
|-----------|------------|----------|
| Spout | 29,692 | 39% of all-time |
| SPUI | 8,510 | 54% |
| EventPanda | 6,277 | 73% |
| Charm | 6,115 | 34% |
| Sammy | 2,058 | 2% (pre-Nov activity) |
| Stable Kernel | 1,282 | 13% |
| Hello Hero | 782 | 3% |

**Note**: Coverage percentages are relative to all-time totals in `sender_accounts.emails_sent_all_time`. Lower percentages indicate most sending occurred before the 90-day backfill window.

#### 039_client_capacity_views.sql

**Status**: Applied (2026-02-23)

Client-level capacity tracking against purchased packages:

```sql
-- Client packages vs actual with gap analysis
CREATE VIEW v_client_capacity AS
SELECT
    client_name,
    entra_packages, entra_domains_target, entra_domains_actual,
    entra_inbox_gap, entra_orders_needed,
    google_packages, google_domains_target, google_domains_actual,
    google_inbox_gap, google_orders_needed,
    entra_pipeline_buffer, google_pipeline_buffer
FROM ...

-- Actionable HyperTide order queue
CREATE VIEW v_hypertide_order_queue AS ...

-- Inbox flow through lifecycle stages
CREATE VIEW v_inbox_pipeline AS ...

-- Raw volume for ALL workspaces (no package required)
CREATE VIEW v_workspace_volume AS ...
```

**Key Fields**:
- Package targets from `client_subscriptions` table
- Gap analysis: target - actual active domains
- Pipeline buffer: incubating + reserve inboxes
- Works with or without subscription (informational, not restrictive)

## Running Migrations

### Via psql

```bash
psql "postgresql://postgres.lhnzdotfevttijwyfcib:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres" \
  -f migrations/001_add_client_profile_columns.sql
```

### Via Supabase Studio

1. Go to https://supabase.com/dashboard
2. Select project `lhnzdotfevttijwyfcib`
3. Navigate to SQL Editor
4. Paste and run migration SQL

## Related

- [[schema]] - Full database schema
- [[../infrastructure/supabase]] - Database hosting
