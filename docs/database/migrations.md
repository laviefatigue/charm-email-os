---
title: Database Migrations
created: 2026-01-16
updated: 2026-01-16
tags: [database, migrations]
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
