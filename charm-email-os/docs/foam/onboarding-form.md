---
title: Client Onboarding Form
created: 2026-01-13
updated: 2026-01-13
tags: [guide, clients, onboarding, database]
---

# Client Onboarding Form

External web form for comprehensive client data collection at **https://onboard.laviefatigue.com**.

## Overview

The onboarding form captures detailed client information needed for [[campaign-ideas|campaign generation]]. Unlike the in-app [[clients|client wizard]], this form collects deep context about the client's business, market, and messaging.

## Form URL

- **Production**: https://onboard.laviefatigue.com
- **Repository**: `laviefatigue/hirecharm-onboarding`
- **Deployment**: Coolify (`hirecharm-onboarding-test`)

## Form Sections

| Section | Purpose | Key Fields |
|---------|---------|------------|
| 1. Foundation | Company basics | company_name, website, contact_name, employee_count, funding_stage |
| 2. Offering | Product/service | core_product, target_customer, acv, sales_cycle_length |
| 3. Market Signals | Buying triggers | signals[], custom_signals |
| 4. Audience | ICPs & personas | segments[], personas[], job_titles[] |
| 5. Process | Current tools | outbound_tools[], crm |
| 6. Messaging | Voice & proof | customer_voice, roi_results, tone_style |
| 7. Goals | GTM objectives | primary_gtm_objective, success_metrics[], success_definition |
| 8. Review | Submission | Confirm and submit |

## Database Schema

Data is stored across three tables in the OwnRBL PostgreSQL database:

### client_onboarding_submissions

Main submission data linked to [[clients]]:

```sql
client_onboarding_submissions
├── id (UUID)
├── client_id → clients.id
├── company_name, website, contact_name, contact_email
├── employee_count, funding_stage, hq_location
├── core_product, target_customer, acv, sales_cycle_length
├── signals[] (text array)
├── job_titles[] (text array)
├── outbound_tools[]
├── customer_voice, roi_results, tone_style
├── primary_gtm_objective, success_metrics[]
├── submission_status ('draft'|'submitted'|'processing'|'completed')
└── submitted_at, created_at, updated_at
```

### client_segments

Customer segments (1:N with submissions):

```sql
client_segments
├── id (UUID)
├── submission_id → client_onboarding_submissions.id
├── segment_name
├── revenue_percentage (0-100)
├── unique_characteristics
├── pain_points
└── buying_triggers
```

### client_personas

Buyer personas (1:N with submissions):

```sql
client_personas
├── id (UUID)
├── submission_id → client_onboarding_submissions.id
├── job_title
├── primary_segment
├── seniority_level
├── pain_before_buying
├── aha_moment
└── objections
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/onboarding/submit` | POST | Submit form |
| `/onboarding/{id}` | GET | Retrieve submission |

### Submit Payload Example

```json
{
  "company_name": "Acme Corp",
  "website": "https://acme.com",
  "contact_name": "Jane Smith",
  "contact_email": "jane@acme.com",
  "employee_count": "51-200",
  "funding_stage": "series-a",
  "core_product": "Enterprise CRM platform",
  "target_customer": "Mid-market SaaS companies",
  "acv": "50k-100k",
  "sales_cycle_length": "3-6months",
  "signals": ["funding", "leadership_change", "job_postings"],
  "job_titles": ["CTO", "VP Engineering"],
  "tone_style": "professional",
  "segments": [
    {"name": "Enterprise", "revenue_pct": 60, "unique_characteristics": "Fortune 500"}
  ],
  "personas": [
    {"job_title": "CTO", "primary_segment": "Enterprise", "pain_before_buying": "Legacy systems"}
  ]
}
```

### Response

```json
{
  "success": true,
  "submission_id": "1d0a919a-6f67-488b-9d9d-99bf4291953b",
  "message": "Onboarding form submitted successfully"
}
```

## Campaign Idea Generator Integration

The onboarding data feeds directly into [[campaign-ideas|campaign generation]]:

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Onboarding Form │────▶│    Supabase DB   │────▶│ Campaign Generator│
│    Submission    │     │                  │     │    (AI/LLM)       │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### Campaign Context View

Query `vw_campaign_generation_context` for aggregated client context:

```sql
SELECT * FROM vw_campaign_generation_context
WHERE client_id = 'your-client-uuid';
```

Returns:
- Company info (name, product, target customer)
- ICP segments as JSONB array
- Buyer personas as JSONB array
- Messaging context (tone, voice, proof points)
- Success criteria

## Client Lifecycle

```
1. Sales closes deal
   ↓
2. Client record created in Charm Email OS
   ↓
3. Send onboarding form link (onboard.laviefatigue.com?client_id=xxx)
   ↓
4. Client completes 8-section form
   ↓
5. Submission saved to database
   ↓
6. Campaign generator uses context
   ↓
7. AI generates targeted campaign ideas
```

## Constraints

- **One active submission per client**: Unique constraint prevents duplicates
- Previous submission must be `archived` or `completed` before resubmitting
- `company_name` or `client_id` required for submission

## Environment Variables

The API requires these environment variables (set in Coolify):

| Variable | Description |
|----------|-------------|
| `POSTGRES_HOST` | Database host |
| `POSTGRES_PORT` | Database port (5432) |
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |

## Related

- [[clients]] - Client entity and in-app wizard
- [[campaign-ideas]] - AI-generated campaign ideas
- [[data-models]] - Core data structures
- [[infrastructure]] - Domain and inbox setup

---
Tags: #guide #clients #onboarding #database #api
