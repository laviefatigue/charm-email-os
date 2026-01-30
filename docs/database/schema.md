---
title: Database Schema
created: 2026-01-16
updated: 2026-01-30
tags: [database, schema, postgresql]
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

### sender_accounts

Email inbox/sending accounts.

```sql
CREATE TABLE sender_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    domain_id UUID REFERENCES domains(id),
    email VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    status VARCHAR(50),
    provider VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sender_accounts_workspace ON sender_accounts(workspace_id);
CREATE INDEX idx_sender_accounts_domain ON sender_accounts(domain_id);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| workspace_id | UUID | Owning workspace |
| domain_id | UUID | Associated domain |
| email | VARCHAR(255) | Full email address |
| first_name | VARCHAR(100) | Sender first name |
| last_name | VARCHAR(100) | Sender last name |
| status | VARCHAR(50) | `active`, `suspended`, `warming` |
| provider | VARCHAR(50) | `entra`, `google` |
| created_at | TIMESTAMP | Record creation time |

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

## Related

- [[../infrastructure/supabase]] - Database hosting details
- [[../architecture/data-flow]] - How data flows through system
- [[migrations]] - Migration history
