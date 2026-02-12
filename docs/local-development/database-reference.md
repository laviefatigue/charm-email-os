---
title: Database Reference
created: 2026-02-10
updated: 2026-02-10
tags: [database, schema, reference, postgresql]
---

# Database Reference

Complete reference for the Charm Email OS database schema, tables, and local development data.

## Connection Details

### Local Development

```
Host:     localhost
Port:     5433
Database: postgres
User:     postgres
Password: localdevpassword
```

**Connect with psql**:
```bash
psql -h localhost -p 5433 -U postgres -d postgres
```

**Connect with GUI** (DBeaver, pgAdmin, etc.):
- Host: `localhost`
- Port: `5433`
- Database: `postgres`
- User: `postgres`
- Password: `localdevpassword`

### Production

```
Host:     31.97.142.123
Port:     5432
Database: postgres
User:     (from Coolify env vars)
Password: (from Coolify env vars)
```

## Core Tables

### workspaces

Container for client organizations.

```sql
CREATE TABLE workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### clients

Client records linked to workspaces.

```sql
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    workspace_id UUID REFERENCES workspaces(id),
    logo_url TEXT,
    onboarding_complete BOOLEAN DEFAULT FALSE,
    onboarding_data JSONB,
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    website VARCHAR(255),
    industry VARCHAR(100),
    domain_pattern VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Key Relationships**:
- `workspace_id` → `workspaces.id`

### client_onboarding_submissions

Client onboarding form data used for strategy generation.

```sql
CREATE TABLE client_onboarding_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    company_name VARCHAR(255),
    website VARCHAR(255),
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    core_product TEXT,
    target_customer TEXT,
    acv VARCHAR(100),
    sales_cycle_length VARCHAR(100),
    signals JSONB,
    job_titles JSONB,
    outbound_tools TEXT,
    crm VARCHAR(100),
    customer_voice TEXT,
    roi_results TEXT,
    tone_style VARCHAR(100),
    primary_gtm_objective TEXT,
    success_metrics TEXT,
    success_definition TEXT,
    pain_points_raw TEXT,
    competitive_landscape TEXT,
    ideal_customer_description TEXT,
    case_studies JSONB,
    objections JSONB,
    status VARCHAR(50) DEFAULT 'draft',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Key Fields**:
- `signals` - Buying signals as JSONB array
- `job_titles` - Target job titles as JSONB array
- `case_studies` - Customer success stories as JSONB array
- `objections` - Common objections and responses as JSONB array

## Strategy Tables

### strategies

Strategy definitions (container for campaigns).

```sql
CREATE TABLE strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### strategy_generation_jobs

Tracks AI generation job status.

```sql
CREATE TABLE strategy_generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    strategy_id UUID REFERENCES strategies(id),
    status VARCHAR(50) DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    strategy_considerations JSONB,  -- Onboarding inputs used
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Status Values**: `pending`, `processing`, `completed`, `failed`

### campaign_cycles

14-day campaign cycles (1 cycle = 4 campaigns).

```sql
CREATE TABLE campaign_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategies(id),
    cycle_number INTEGER NOT NULL,
    cycle_name VARCHAR(100),
    start_date DATE,
    end_date DATE,
    duration_days INTEGER DEFAULT 14,
    target_campaigns INTEGER,
    actual_campaigns INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'planned',
    notes TEXT,
    submission_id UUID REFERENCES client_onboarding_submissions(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(client_id, cycle_number)
);
```

**Status Values**: `planned`, `active`, `completed`

### strategy_suggestions

Generated campaign suggestions with versioning.

```sql
CREATE TABLE strategy_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
    client_id UUID NOT NULL REFERENCES clients(id),

    -- Campaign metadata
    suggestion_type VARCHAR(50),
    title VARCHAR(255),
    copy TEXT,

    -- Sequence data (from migration 004)
    sequence_data JSONB,
    value_prop_rotation JSONB,
    is_sequence BOOLEAN DEFAULT FALSE,
    total_word_count INTEGER,

    -- Versioning (from migration 013)
    cycle_id UUID REFERENCES campaign_cycles(id),
    campaign_version INTEGER DEFAULT 1,
    previous_version_id UUID REFERENCES strategy_suggestions(id),
    lineage_id UUID,

    -- Campaign differentiation
    campaign_angle VARCHAR(50),  -- custom_signal, persona_pain, case_study, risk_efficiency
    target_persona VARCHAR(255),
    target_segment VARCHAR(255),
    opener_pattern VARCHAR(50),  -- status_pressure, efficiency_leverage, risk_based, binary, redirect

    -- Performance tracking
    emailbison_campaign_id VARCHAR(100),
    performance_metrics JSONB,
    last_performance_sync TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW()
);
```

**Campaign Angles**:
- `custom_signal` - Research-led, based on specific signals
- `persona_pain` - Role-specific pain points
- `case_study` - Proof-led with customer success
- `risk_efficiency` - Savings and risk reduction

### campaign_documents

Stablekernel format documents with ICP mapping.

```sql
CREATE TABLE campaign_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    strategy_id UUID REFERENCES strategies(id),
    job_id UUID REFERENCES strategy_generation_jobs(id),

    document_name VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) DEFAULT 'stablekernel',

    -- ICP Mapping
    icp_mapping JSONB,  -- target_icp, pain_points, objections

    -- Variable schema
    variable_schema JSONB,  -- core, high_signal, ai_generated

    -- QA and notes
    qa_scoring JSONB,
    strategy_notes JSONB,

    -- Cycle link
    cycle_id UUID REFERENCES campaign_cycles(id),
    campaign_variables JSONB,

    status VARCHAR(50) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### document_email_variants

Email variants for each position in a campaign.

```sql
CREATE TABLE document_email_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES campaign_documents(id),

    position INTEGER NOT NULL,  -- 1, 2, 3, 4
    variant_number INTEGER NOT NULL,  -- 1, 2, 3

    subject_line TEXT,
    email_body TEXT,
    word_count INTEGER,
    is_recommended BOOLEAN DEFAULT FALSE,

    -- Notes
    variant_notes TEXT,
    focus VARCHAR(255),

    created_at TIMESTAMP DEFAULT NOW()
);
```

## Domain Tables

### domains

Domain records with purchasing status.

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
    domain_state VARCHAR(50),

    -- Pricing
    cached_price DECIMAL(10,2),
    price_checked_at TIMESTAMP,
    purchased_at TIMESTAMP,
    porkbun_price DECIMAL(10,2),
    porkbun_available BOOLEAN,
    dynadot_price DECIMAL(10,2),
    dynadot_available BOOLEAN,
    selected_provider VARCHAR(20),
    job_id UUID,

    -- Nameservers
    nameservers_updated_at TIMESTAMP,
    nameserver_status VARCHAR(20) DEFAULT 'pending',
    nameserver_verified_at TIMESTAMP,
    current_nameservers TEXT[],

    -- Infrastructure
    infrastructure_type VARCHAR(20),
    infrastructure_set_at TIMESTAMP,

    -- Purchase job
    purchase_job_id UUID,
    purchase_job_status TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);
```

### sender_accounts

Email sender accounts linked to domains.

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
```

## Test Data (Seed)

### Charm Client

The main test client, with ID matching production:

| Field | Value |
|-------|-------|
| **ID** | `4bd07dc0-059a-448b-b6f4-3275d0c104a9` |
| Name | Charm |
| Website | https://hirecharm.com |
| Industry | Recruiting Technology |
| Contact | Elliott Saille |
| Email | elliott@hirecharm.com |

### Sample Onboarding Submission

| Field | Sample Value |
|-------|--------------|
| **ID** | `550e8400-e29b-41d4-a716-446655440000` |
| Core Product | AI-powered recruiting automation platform |
| Target Customer | VP/Director of Talent Acquisition at mid-market tech |
| ACV | $50,000 - $150,000 |
| Sales Cycle | 30-60 days |
| Signals | Job postings, Hiring surge, New TA leader |

## Common Queries

### Get client with onboarding

```sql
SELECT c.*, o.*
FROM clients c
LEFT JOIN client_onboarding_submissions o ON o.client_id = c.id AND o.is_active = true
WHERE c.id = '4bd07dc0-059a-448b-b6f4-3275d0c104a9';
```

### Get active campaigns for client

```sql
SELECT cc.*, cd.*
FROM campaign_cycles cc
LEFT JOIN campaign_documents cd ON cd.cycle_id = cc.id
WHERE cc.client_id = '4bd07dc0-059a-448b-b6f4-3275d0c104a9'
  AND cc.status = 'active'
ORDER BY cc.cycle_number;
```

### Get pending generation jobs

```sql
SELECT *
FROM strategy_generation_jobs
WHERE status = 'pending'
ORDER BY created_at;
```

## Migrations

Migrations are in `D:\Work\charm-email-os\migrations\`:

| Migration | Purpose |
|-----------|---------|
| `001_initial.sql` | Base tables |
| `004_sequences.sql` | Added sequence_data, value_prop_rotation |
| `013_batch_campaign_generation.sql` | Added cycle tracking, versioning |
| `016_onboarding.sql` | Comprehensive onboarding fields |
| `017_unified_cycle_schema.sql` | Cycle strategy config, campaign variables |

## Related

- [[architecture]] - System architecture
- [[file-locations]] - Where schema files live
- [[../database/schema]] - Full schema documentation
