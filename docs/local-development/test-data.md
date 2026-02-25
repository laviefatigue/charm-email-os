---
title: Test Data Reference
created: 2026-02-10
updated: 2026-02-10
tags: [test, data, seed, reference]
---

# Test Data Reference

Reference for all test data seeded in the local development environment.

## Seed Data Location

**File**: `D:\Work\charm-email-os\docker\init\02-seed.sql`

This script runs automatically when the PostgreSQL container starts for the first time.

## Primary Test Client: Charm

The main test client used for development and testing. The ID matches production for consistency.

| Field | Value |
|-------|-------|
| **ID** | `4bd07dc0-059a-448b-b6f4-3275d0c104a9` |
| Name | Charm |
| Website | https://hirecharm.com |
| Industry | Recruiting Technology |
| Contact Name | Elliott Saille |
| Contact Email | elliott@hirecharm.com |
| Onboarding Complete | true |

### Direct URLs

| Page | URL |
|------|-----|
| Client Overview | http://localhost:3000/clients/4bd07dc0-059a-448b-b6f4-3275d0c104a9 |
| Strategy Page | http://localhost:3000/clients/4bd07dc0-059a-448b-b6f4-3275d0c104a9/strategy |
| Inboxes Page | http://localhost:3000/clients/4bd07dc0-059a-448b-b6f4-3275d0c104a9/inboxes |

## Test Workspace

| Field | Value |
|-------|-------|
| **ID** | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| Name | Charm Test Workspace |
| Slug | charm-test |

## Onboarding Submission

Complete onboarding data for Charm client.

| Field | Value |
|-------|-------|
| **ID** | `550e8400-e29b-41d4-a716-446655440000` |
| Client ID | `4bd07dc0-059a-448b-b6f4-3275d0c104a9` |
| Company | Charm |
| Core Product | AI-powered recruiting automation platform |
| Target Customer | VP/Director of Talent Acquisition at mid-market tech |
| ACV | $50,000 - $150,000 |
| Sales Cycle | 30-60 days |
| Status | submitted |

### Signals

```json
[
  {"signal": "Job postings", "description": "Companies actively posting roles", "priority": "high"},
  {"signal": "Hiring surge", "description": "Company announced funding or expansion", "priority": "high"},
  {"signal": "New TA leader", "description": "Recently hired VP/Director of TA", "priority": "medium"}
]
```

### Job Titles

```json
[
  {"title": "VP of Talent Acquisition", "seniority": "VP"},
  {"title": "Director of Recruiting", "seniority": "Director"},
  {"title": "Head of People", "seniority": "Director"}
]
```

### Case Studies

```json
[
  {"company": "TechCorp", "result": "Reduced time-to-fill by 60%", "quote": "Charm transformed our recruiting process"},
  {"company": "StartupXYZ", "result": "Hired 50 engineers in 3 months", "quote": "We could not have scaled without Charm"}
]
```

### Objections

```json
[
  {"objection": "We already have an ATS", "response": "Charm integrates with your existing ATS"},
  {"objection": "Our recruiters prefer manual outreach", "response": "Charm handles repetitive tasks"}
]
```

## Sample Strategy

| Field | Value |
|-------|-------|
| **ID** | `660e8400-e29b-41d4-a716-446655440001` |
| Client ID | `4bd07dc0-059a-448b-b6f4-3275d0c104a9` |
| Name | Q1 2026 Outbound Campaign |
| Status | active |

## Sample Campaign Cycle

| Field | Value |
|-------|-------|
| **ID** | `770e8400-e29b-41d4-a716-446655440001` |
| Client ID | `4bd07dc0-059a-448b-b6f4-3275d0c104a9` |
| Cycle Number | 1 |
| Cycle Name | Initial Launch |
| Start Date | 2026-02-10 |
| End Date | 2026-02-24 |
| Duration | 14 days |
| Status | active |

## Sample Campaign Document

| Field | Value |
|-------|-------|
| **ID** | `aa0e8400-e29b-41d4-a716-446655440001` |
| Document Name | Charm VP TA - Custom Signal |
| Document Type | stablekernel |
| Status | active |

### ICP Mapping

```json
{
  "target_icp": {
    "role": "VP of Talent Acquisition",
    "company_type": "Mid-market SaaS",
    "company_size": "200-2000 employees"
  },
  "pain_points": [
    {"category": "Efficiency", "label": "Time-to-fill", "points": ["45+ days average", "Manual processes"]},
    {"category": "Quality", "label": "Candidate quality", "points": ["Low response rates", "Wrong fit hires"]}
  ],
  "objections": [
    {"objection": "We already have an ATS", "preemption": "Charm integrates with existing tools"}
  ]
}
```

### Variable Schema

```json
{
  "core": [
    {"name": "first_name", "description": "Contact first name"}
  ],
  "high_signal": [
    {"name": "core_vendor", "description": "Current ATS vendor", "source": "ZoomInfo"}
  ],
  "ai_generated": [
    {"name": "ai_opener", "description": "AI-personalized opener"}
  ]
}
```

## Sample Email Variants

| Position | Variant | Subject | Recommended |
|----------|---------|---------|-------------|
| 1 | 1 | Quick question about {{company}} hiring | true |
| 1 | 2 | {{first_name}}, noticed your TA team is growing | false |
| 2 | 1 | Following up on recruiting efficiency | true |
| 3 | 1 | One more thought on {{company}} | true |
| 4 | 1 | Resource: How TechCorp cut time-to-fill 60% | true |

## Additional Test Clients

| ID | Name | Onboarding Complete |
|----|------|---------------------|
| `11111111-1111-1111-1111-111111111111` | Acme Corp | false |
| `22222222-2222-2222-2222-222222222222` | TechFlow | false |

## Resetting Test Data

```bash
# Full reset (deletes all data, re-runs seed)
docker compose -f docker-compose.local.yml down -v
docker compose -f docker-compose.local.yml up -d

# Manually re-run seed script
docker exec -it charm-postgres psql -U postgres -d postgres -f /docker-entrypoint-initdb.d/02-seed.sql
```

## Creating Custom Test Data

### Add a new client

```sql
INSERT INTO clients (id, name, workspace_id, website, industry, onboarding_complete)
VALUES (
    gen_random_uuid(),
    'My Test Company',
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    'https://example.com',
    'Technology',
    false
);
```

### Create a test generation job

```sql
INSERT INTO strategy_generation_jobs (id, client_id, status)
VALUES (
    gen_random_uuid(),
    '4bd07dc0-059a-448b-b6f4-3275d0c104a9',
    'pending'
);
```

## Related

- [[database-reference]] - Full database schema
- [[development-workflow]] - Development process
- [[troubleshooting]] - Common issues
