---
title: Database Schema
created: 2026-01-16
updated: 2026-03-05
tags: [database, schema, postgresql, health, warmup, metrics, daily-volume, audit, users]
---

# Database Schema

Complete schema documentation for Charm Email OS.

## Core Tables

### clients

Basic client account information.

```sql
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    workspace_id UUID REFERENCES workspaces(id),
    logo_url TEXT,
    onboarding_complete BOOLEAN DEFAULT FALSE,
    onboarding_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_clients_workspace ON clients(workspace_id);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(255) | Client/company name |
| workspace_id | UUID | Link to OwnRBL workspace |
| logo_url | TEXT | Logo image URL |
| onboarding_complete | BOOLEAN | Whether onboarding finished |
| onboarding_data | JSONB | Legacy onboarding data |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Last update time |

### workspaces

OwnRBL workspace data (read-only, managed externally).

```sql
CREATE TABLE workspaces (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(255) | Workspace name |
| slug | VARCHAR(255) | URL-safe identifier |
| created_at | TIMESTAMP | Record creation time |

### domains

Email domains for sending.

```sql
CREATE TABLE domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    domain_name VARCHAR(255) NOT NULL,
    notes TEXT,
    rationale TEXT,
    legitimacy_score FLOAT,
    approval_status VARCHAR(20) DEFAULT 'pending',
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_domains_workspace ON domains(workspace_id);
CREATE INDEX idx_domains_status ON domains(approval_status);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| workspace_id | UUID | Owning workspace |
| domain_name | VARCHAR(255) | Domain name (e.g., `mail.example.com`) |
| notes | TEXT | Additional notes |
| rationale | TEXT | AI-generated reasoning |
| legitimacy_score | FLOAT | 0-1 score from AI |
| approval_status | VARCHAR(20) | `pending`, `approved`, `denied` |
| reviewed_at | TIMESTAMP | When reviewed |
| domain_state | VARCHAR(50) | Lifecycle status (see [[../concepts/domain-lifecycle]]) |
| purchased_at | TIMESTAMP | When domain was purchased from registrar |
| selected_provider | VARCHAR(50) | Registrar used: `porkbun`, `dynadot` |
| nameserver_status | VARCHAR(50) | NS propagation status |
| infrastructure_type | VARCHAR(50) | `entra`, `google`, or NULL |
| purchase_job_id | UUID | FK to `inbox_purchase_jobs.id` — locks domain to a purchase job |
| purchase_job_status | VARCHAR(50) | Lock status: `pending`, `processing`, `executing`, or NULL |
| created_at | TIMESTAMP | Record creation time |

#### Fulfillment Tracking (Migration 060)

| Column | Type | Description |
|--------|------|-------------|
| expected_inbox_count | INTEGER | Expected inboxes from HyperTide (50 Entra, 3 Google) |
| max_inboxes_seen | INTEGER | Peak inbox count ever observed |
| fulfillment_status | VARCHAR(20) | `pending`, `under_delivered`, `fulfilled`, `over_delivered` |

#### Error History (Migration 062)

| Column | Type | Description |
|--------|------|-------------|
| burn_breakdown | JSONB | Counts by kill trigger type (e.g., `{"spam_complaint": 1}`) |
| inboxes_with_complaints | INTEGER | Count of inboxes with spam complaints |
| inboxes_with_blocks | INTEGER | Count of inboxes with hard blocks |

### sender_accounts

Email inbox/sending accounts with health monitoring and metrics.

```sql
CREATE TABLE sender_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    domain_id UUID REFERENCES domains(id),
    email_address VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    emailbison_account_id VARCHAR(50),
    status VARCHAR(50),
    esp VARCHAR(50),

    -- Health & State (see [[../features/health-monitoring]])
    inbox_state VARCHAR(20) DEFAULT 'live',
    health_score INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE,

    -- Bounce Tracking (differentiated - see ADR-005)
    hard_bounces_24h INTEGER DEFAULT 0,
    hard_blocked_24h INTEGER DEFAULT 0,
    hard_unknown_24h INTEGER DEFAULT 0,
    hard_bounces_7d INTEGER DEFAULT 0,
    bounce_rate_7d DECIMAL,
    complaints_lifetime INTEGER DEFAULT 0,

    -- All-Time Metrics (from EmailBison UI)
    emails_sent_all_time INTEGER DEFAULT 0,
    replies_all_time INTEGER DEFAULT 0,
    bounces_all_time INTEGER DEFAULT 0,
    daily_limit INTEGER DEFAULT 0,

    -- Warmup Lifecycle
    warmup_enabled BOOLEAN DEFAULT FALSE,
    warmup_started_at TIMESTAMP WITH TIME ZONE,
    warmup_stopped_at TIMESTAMP WITH TIME ZONE,
    sending_started_at TIMESTAMP WITH TIME ZONE,

    -- Inventory Management
    inventory_pool_status VARCHAR(20) DEFAULT 'reserve',
    inventory_lifecycle_status VARCHAR(20) DEFAULT 'incubating',
    pool_tier VARCHAR(20) DEFAULT 'primary',

    -- Timestamps
    first_seen_at TIMESTAMP WITH TIME ZONE,
    last_seen_at TIMESTAMP WITH TIME ZONE,
    last_synced_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sender_accounts_workspace ON sender_accounts(workspace_id);
CREATE INDEX idx_sender_accounts_domain ON sender_accounts(domain_id);
CREATE INDEX idx_sender_accounts_warmup ON sender_accounts(warmup_enabled, warmup_started_at) WHERE is_active = TRUE;
CREATE INDEX idx_sender_accounts_metrics ON sender_accounts(emails_sent_all_time, bounces_all_time) WHERE is_active = TRUE;
```

#### Core Columns

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| workspace_id | UUID | Owning workspace |
| domain_id | UUID | Associated domain |
| email_address | VARCHAR(255) | Full email address (globally unique) |
| display_name | VARCHAR(255) | Sender display name |
| emailbison_account_id | VARCHAR(50) | EmailBison API ID |
| status | VARCHAR(50) | `Connected`, `Not connected`, etc. |
| esp | VARCHAR(50) | `gmail`, `microsoft`, `other` |

#### Health & State Columns

| Column | Type | Description |
|--------|------|-------------|
| inbox_state | VARCHAR(20) | `live` or `dead` |
| health_score | INTEGER | 0-100 calculated score |
| is_active | BOOLEAN | Whether account is actively synced |
| complaints_lifetime | INTEGER | Total spam complaints (1 = death trigger) |

#### Bounce Tracking Columns

| Column | Type | Description |
|--------|------|-------------|
| hard_bounces_24h | INTEGER | Combined hard bounces in 24h |
| hard_blocked_24h | INTEGER | Spam/policy rejections (550 5.7.x) |
| hard_unknown_24h | INTEGER | Bad addresses (550 5.1.x) |
| hard_bounces_7d | INTEGER | Hard bounces in 7 days |
| bounce_rate_7d | DECIMAL | 7-day bounce rate from EmailBison |

#### All-Time Metrics (from EmailBison UI)

| Column | Type | Description |
|--------|------|-------------|
| emails_sent_all_time | INTEGER | Total emails sent (all time) |
| replies_all_time | INTEGER | Total replies received (all time) |
| bounces_all_time | INTEGER | Total bounces (all time) |
| daily_limit | INTEGER | Daily sending limit |

#### Warmup Lifecycle Columns

| Column | Type | Description |
|--------|------|-------------|
| warmup_enabled | BOOLEAN | Whether warmup is active in EmailBison |
| warmup_started_at | TIMESTAMP | When warmup was first detected (estimated: first_seen_at + 7d) |
| warmup_stopped_at | TIMESTAMP | When warmup was disabled |
| sending_started_at | TIMESTAMP | When inbox was first deployed to campaign |

#### Inventory Management Columns

| Column | Type | Description |
|--------|------|-------------|
| inventory_pool_status | VARCHAR(20) | `deployed`, `warning`, `reserve` |
| inventory_lifecycle_status | VARCHAR(20) | `active`, `incubating`, `dead` |
| pool_tier | VARCHAR(20) | `primary`, `hot_backup`, `warming` |

## Onboarding Tables

### client_onboarding_submissions

Comprehensive onboarding form data (7 sections).

```sql
CREATE TABLE client_onboarding_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),

    -- Section 1: Foundation
    company_name VARCHAR(255),
    website VARCHAR(255),
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),

    -- Section 2: Offering
    core_product TEXT,
    target_customer TEXT,
    acv VARCHAR(100),
    sales_cycle_length VARCHAR(100),

    -- Section 3: Market Signals
    signals JSONB,  -- Array of signal objects

    -- Section 4: Audience
    job_titles JSONB,  -- Array of target titles

    -- Section 5: Process
    outbound_tools TEXT,
    crm VARCHAR(100),

    -- Section 6: Messaging
    customer_voice TEXT,
    roi_results TEXT,
    tone_style VARCHAR(100),

    -- Section 7: Goals
    primary_gtm_objective TEXT,
    success_metrics TEXT,
    success_definition TEXT,

    -- Metadata
    status VARCHAR(50) DEFAULT 'draft',
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_submissions_client ON client_onboarding_submissions(client_id);
CREATE INDEX idx_submissions_active ON client_onboarding_submissions(is_active);
```

### client_segments

Customer segments (nested under submissions).

```sql
CREATE TABLE client_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID REFERENCES client_onboarding_submissions(id),
    segment_name VARCHAR(255) NOT NULL,
    revenue_percentage INTEGER,
    unique_characteristics TEXT,
    pain_points TEXT,
    buying_triggers TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_segments_submission ON client_segments(submission_id);
```

| Column | Type | Description |
|--------|------|-------------|
| segment_name | VARCHAR(255) | Name of segment |
| revenue_percentage | INTEGER | 0-100 percentage of revenue |
| unique_characteristics | TEXT | What makes them unique |
| pain_points | TEXT | Their problems |
| buying_triggers | TEXT | What triggers purchase |

### client_personas

Buyer personas (nested under submissions).

```sql
CREATE TABLE client_personas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID REFERENCES client_onboarding_submissions(id),
    job_title VARCHAR(255) NOT NULL,
    primary_segment VARCHAR(255),
    seniority_level VARCHAR(100),
    pain_before_buying TEXT,
    aha_moment TEXT,
    objections TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_personas_submission ON client_personas(submission_id);
```

| Column | Type | Description |
|--------|------|-------------|
| job_title | VARCHAR(255) | Target job title |
| primary_segment | VARCHAR(255) | Which segment they belong to |
| seniority_level | VARCHAR(100) | C-Level, VP, Director, Manager, Individual |
| pain_before_buying | TEXT | Pain they experienced |
| aha_moment | TEXT | When they "got it" |
| objections | TEXT | Common objections |

## Purchase Job Tables

### inbox_purchase_jobs

Queue for inbox provisioning purchase jobs executed by the purchase worker.

```sql
CREATE TABLE inbox_purchase_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    workspace_id UUID REFERENCES workspaces(id),
    status VARCHAR(50) DEFAULT 'pending',
    current_step TEXT,
    provider_type VARCHAR(50),
    domain_ids UUID[],
    domain_names TEXT[],
    entra_orders INTEGER DEFAULT 0,
    google_orders INTEGER DEFAULT 0,
    orders_total INTEGER DEFAULT 0,
    orders_completed INTEGER DEFAULT 0,
    total_inboxes INTEGER DEFAULT 0,
    monthly_cost NUMERIC,
    request_data JSONB,
    results JSONB,
    errors JSONB,
    override_age_check BOOLEAN DEFAULT FALSE,
    custom_purchase BOOLEAN DEFAULT FALSE,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_purchase_jobs_status ON inbox_purchase_jobs(status);
CREATE INDEX idx_purchase_jobs_client ON inbox_purchase_jobs(client_id);
```

| Status | Description |
|--------|-------------|
| pending | Waiting for worker to pick up |
| processing | Worker is preparing the job |
| executing | HyperTide automation running |
| completed | Successfully finished |
| failed | Error occurred |
| cancelled | Cancelled by user, domain locks released |

### purchase_job_steps

Audit trail for each step of a purchase job execution.

```sql
CREATE TABLE purchase_job_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES inbox_purchase_jobs(id),
    step_name TEXT NOT NULL,
    screenshot_base64 TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(job_id, step_name)
);

CREATE INDEX idx_job_steps_job ON purchase_job_steps(job_id);
```

## Generation Job Tables

### domain_generation_jobs

Queue for domain generation tasks.

```sql
CREATE TABLE domain_generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    count INTEGER DEFAULT 10,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_domain_jobs_status ON domain_generation_jobs(status);
CREATE INDEX idx_domain_jobs_client ON domain_generation_jobs(client_id);
```

| Status | Description |
|--------|-------------|
| pending | Waiting to be picked up |
| processing | Worker is running |
| completed | Successfully finished |
| failed | Error occurred |

### strategy_generation_jobs (NEW)

Queue for AI strategy generation tasks.

```sql
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
```

| Status | Description |
|--------|-------------|
| pending | Waiting to be picked up |
| processing | Claude Code is running |
| review | Variants ready for human review |
| completed | All variants reviewed |
| failed | Error occurred |

### strategy_suggestions (NEW)

Individual campaign variants for review.

```sql
CREATE TABLE strategy_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
    client_id UUID NOT NULL REFERENCES clients(id),

    -- Email content
    variant_number INTEGER NOT NULL,
    subject_line TEXT NOT NULL,
    email_body TEXT NOT NULL,

    -- Metadata from skill
    score INTEGER,
    rationale TEXT,
    used_variables JSONB,
    missing_variables JSONB,
    campaign_type VARCHAR(50),

    -- Review status
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
```

| Column | Type | Description |
|--------|------|-------------|
| variant_number | INTEGER | 1, 2, or 3 |
| subject_line | TEXT | Email subject |
| email_body | TEXT | Email content |
| score | INTEGER | 0-100 from QA scoring |
| rationale | TEXT | Why this variant works |
| campaign_type | VARCHAR(50) | `custom_signal`, `creative_ideas`, `whole_offer` |
| status | VARCHAR(50) | `pending`, `approved`, `denied`, `revision_requested` |

### strategy_revision_requests (NEW)

Human feedback for regeneration.

```sql
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
CREATE INDEX idx_revisions_processed ON strategy_revision_requests(processed);
```

## Metrics Tables

### daily_volume_snapshots

Historical sending volume per workspace for client dashboard charts.

```sql
CREATE TABLE daily_volume_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    snapshot_date DATE NOT NULL,

    -- Volume metrics (from EmailBison campaign stats)
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

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(workspace_id, snapshot_date)
);

CREATE INDEX idx_daily_volume_workspace_date ON daily_volume_snapshots(workspace_id, snapshot_date DESC);
CREATE INDEX idx_daily_volume_date ON daily_volume_snapshots(snapshot_date DESC);
```

| Column | Type | Description |
|--------|------|-------------|
| workspace_id | UUID | Workspace this snapshot belongs to |
| snapshot_date | DATE | Date of this snapshot |
| emails_sent | INTEGER | Total emails sent across all campaigns |
| emails_bounced | INTEGER | Total bounced emails |
| daily_capacity_available | INTEGER | SUM(daily_limit) for all live inboxes |
| capacity_utilization_pct | DECIMAL | (emails_sent / daily_capacity) * 100 |
| kills_that_day | INTEGER | Inboxes killed on this date |

**Data Source**: Backfilled from EmailBison API via `scripts/backfill_daily_volume.py`. Daily updates via sync worker's `run_daily_snapshot()`.

**Initial Backfill (2026-02-23)**: 54,716 emails across 7 workspaces, covering Nov 25, 2025 - Feb 22, 2026.

## User & Activity Tables

### users (Migration 064)

Authenticated users from Cloudflare Access Google OAuth (@hirecharm.com).

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_last_seen ON users(last_seen_at);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| email | VARCHAR(255) | Email from CF-Access-Authenticated-User-Email header |
| display_name | VARCHAR(255) | Derived from email (e.g., elliott@hirecharm.com → Elliott) |
| first_seen_at | TIMESTAMPTZ | First login timestamp |
| last_seen_at | TIMESTAMPTZ | Most recent API request |
| is_active | BOOLEAN | Active status |

### activity_log (Migration 064)

Audit trail of user actions for compliance and debugging.

```sql
CREATE TABLE activity_log (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    user_email VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    details JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_activity_log_user_email ON activity_log(user_email);
CREATE INDEX idx_activity_log_action ON activity_log(action);
CREATE INDEX idx_activity_log_resource ON activity_log(resource_type, resource_id);
CREATE INDEX idx_activity_log_created ON activity_log(created_at DESC);
```

| Column | Type | Description |
|--------|------|-------------|
| user_id | UUID | FK to users table |
| user_email | VARCHAR(255) | Denormalized for query performance |
| action | VARCHAR(100) | Action type: `domain_purchased`, `hypertide_order_created`, etc. |
| resource_type | VARCHAR(50) | `domain`, `inbox`, `client`, etc. |
| resource_id | VARCHAR(255) | UUID or identifier of affected resource |
| details | JSONB | Action-specific context (domain_name, price, etc.) |

## Sync & Health Tables

### sync_audit_log (Migration 020)

Tracks every sync operation for debugging and monitoring.

```sql
CREATE TABLE sync_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_type VARCHAR(50) NOT NULL,
    workspace_id UUID REFERENCES workspaces(id),
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'running',
    records_processed INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    error_message TEXT,
    error_details JSONB,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

| sync_type Values | Description |
|-----------------|-------------|
| accounts | Sender account sync from EmailBison |
| campaigns | Campaign sync from EmailBison |
| events | Bounce/reply event sync |
| health | Health check run |
| kill_queue | Kill queue processing |
| retention | Data retention cleanup |

### kill_queue (Migration 020)

Tracks inboxes queued for flagging with health monitoring.

```sql
CREATE TABLE kill_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id UUID NOT NULL REFERENCES sender_accounts(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    trigger_type VARCHAR(50) NOT NULL,
    trigger_value DECIMAL(10,4),
    trigger_threshold DECIMAL(10,4),
    queued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    tagged_at TIMESTAMP,
    tag_name VARCHAR(100),
    scheduled_delete_at TIMESTAMP,
    deleted_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

| Column | Type | Description |
|--------|------|-------------|
| inbox_id | UUID | FK to sender_accounts |
| trigger_type | VARCHAR(50) | Kill trigger: `spam_complaint`, `hard_blocked_24h`, `fresh_inbox_bounce`, etc. |
| trigger_value | DECIMAL | Actual value that triggered (e.g., bounce count) |
| trigger_threshold | DECIMAL | Threshold that was exceeded |
| tag_name | VARCHAR(100) | EmailBison tag applied (e.g., `flagged_hard_blocked_24h`) |
| status | VARCHAR(20) | `pending`, `tagged`, `deleted`, `cancelled`, `failed` |

#### Kill Trigger Priority Order

1. `spam_complaint` >= 1 (instant)
2. `provider_block_{esp}` >= 1 (instant, ESP-specific)
3. `hard_blocked_24h` >= 1 (instant)
4. `hard_unknown_24h` >= 3 (instant)
5. `hard_bounces_24h` >= 2 (fallback)
6. `hard_bounce_rate_7d` > 0.5% (min 20 sends)
7. `bounce_rate_all_7d` > 5% (min 20 sends)
8. `fresh_inbox_bounce` (any bounce on <14 day inbox)
9. `disconnected_timeout` (21+ days disconnected)

### response_messages (Migration 020)

Stores reply/bounce content for campaign analysis.

```sql
CREATE TABLE response_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_event_id UUID REFERENCES campaign_events(id),
    campaign_id UUID REFERENCES emailbison_campaigns(id),
    workspace_id UUID REFERENCES workspaces(id),
    folder VARCHAR(20) NOT NULL,
    from_email VARCHAR(255),
    to_inbox_email VARCHAR(255),
    sender_account_id UUID REFERENCES sender_accounts(id),
    subject TEXT,
    body_preview TEXT,
    body_full TEXT,
    received_at TIMESTAMP,
    is_interested BOOLEAN DEFAULT FALSE,
    is_automated BOOLEAN DEFAULT FALSE,
    sentiment VARCHAR(20),
    bounce_type VARCHAR(50),
    bounce_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

| bounce_type Values | Description |
|-------------------|-------------|
| hard_unknown | Bad email address (550 5.1.x) |
| hard_blocked | Reputation/policy rejection (550 5.7.x) |
| soft_full | Mailbox full |
| soft_temp | Temporary error |

## Inbox Audit Tables

### inbox_audits (Migration 063)

Daily inbox health audits sent to Slack for team review.

```sql
CREATE TABLE inbox_audits (
    id SERIAL PRIMARY KEY,
    audit_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMPTZ,
    notes TEXT,
    total_kills INTEGER,
    total_disconnected INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

| status Values | Description |
|--------------|-------------|
| pending | Awaiting review |
| confirmed | Reviewed and approved |
| issues_found | Problems identified |

### inbox_audit_corrections (Migration 063)

Corrections submitted when audit reveals incorrectly flagged inboxes.

```sql
CREATE TABLE inbox_audit_corrections (
    id SERIAL PRIMARY KEY,
    audit_id INTEGER NOT NULL REFERENCES inbox_audits(id),
    email_address VARCHAR(255) NOT NULL,
    correction_type VARCHAR(50) NOT NULL,
    reason TEXT,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by VARCHAR(255),
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

| correction_type Values | Description |
|-----------------------|-------------|
| wrong_kill | Inbox killed incorrectly |
| false_positive | Trigger was a false positive |
| should_restore | Inbox should be restored |
| other | Other correction needed |

## Database Views

### v_infrastructure_waterfall (Migration 062)

Infrastructure waterfall view with error-aware rotation recommendations. Primary view for the Infrastructure Waterfall UI.

**Key Columns:**

| Column | Type | Description |
|--------|------|-------------|
| domain_id | UUID | Domain primary key |
| domain_name | VARCHAR | Domain name |
| assigned_provider | VARCHAR | `entra` or `google` |
| detected_provider | VARCHAR | Provider detected from inbox ESP |

**Pricing Columns:**

| Column | Type | Description |
|--------|------|-------------|
| price_status | VARCHAR | `not_checked`, `stale`, `unavailable`, `valid` |
| porkbun_price | DECIMAL | Porkbun price in dollars |
| dynadot_price | DECIMAL | Dynadot price in dollars |
| selected_provider | VARCHAR | Chosen registrar |

**Inbox Count Columns:**

| Column | Type | Description |
|--------|------|-------------|
| live_inbox_count | INTEGER | Inboxes with `inbox_state != 'dead'` |
| dead_inbox_count | INTEGER | Inboxes with `inbox_state = 'dead'` |
| connected_inbox_count | INTEGER | Live + Connected (operational capacity) |
| disconnected_inbox_count | INTEGER | Live + Not connected |
| synced_inbox_count | INTEGER | Total inboxes from EmailBison |

**Fulfillment Columns:**

| Column | Type | Description |
|--------|------|-------------|
| expected_inbox_count | INTEGER | What HyperTide should deliver |
| max_inboxes_seen | INTEGER | Peak count ever observed |
| capacity_remaining_pct | DECIMAL | (connected / expected) * 100 |

**Error History Columns:**

| Column | Type | Description |
|--------|------|-------------|
| burn_breakdown | JSONB | Counts by kill trigger type |
| inboxes_with_complaints | INTEGER | Spam complaint count |
| inboxes_with_blocks | INTEGER | Hard block count |
| has_compromised_inboxes | BOOLEAN | TRUE if complaints or blocks exist |

**Rotation Columns:**

| Column | Type | Description |
|--------|------|-------------|
| rotation_recommendation | VARCHAR | `not_applicable`, `healthy`, `monitor`, `consider_rotate`, `rotate_now` |
| recommended_action | VARCHAR | `none`, `watch`, `reconnect`, `rotate` |

**Rotation Priority Logic:**
1. Spam complaints → `rotate_now` (domain is burned)
2. All disconnected → `rotate_now` (no capacity)
3. Multiple hard blocks (2+) → `consider_rotate`
4. Below capacity threshold → `consider_rotate`
5. Single hard block → `monitor`
6. Disconnected with clean history → `monitor` + `reconnect` action
7. No issues → `healthy`

## Related

- [[../infrastructure/supabase]] - Database hosting details
- [[../architecture/data-flow]] - How data flows through system
- [[migrations]] - Migration history
