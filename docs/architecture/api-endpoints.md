---
title: API Endpoints
created: 2026-01-16
updated: 2026-01-16
tags: [architecture, api, endpoints]
---

# API Endpoints

REST API documentation for Charm Email OS (FastAPI).

## Base URL

| Environment | URL |
|-------------|-----|
| Production | `http://ccssgc4gowsog04wck400o0w.31.97.142.123.sslip.io` |
| Local | `http://localhost:8000` |

## Client Routes

`/api/clients`

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| GET | `/api/clients` | List clients with pagination | Query: `page`, `page_size`, `search`, `onboarding_complete` |
| POST | `/api/clients` | Create new client | `{ name, workspace_id?, logo_url?, onboarding_data? }` |
| GET | `/api/clients/{id}` | Get single client | - |
| PUT | `/api/clients/{id}` | Update client | `{ name?, workspace_id?, logo_url?, onboarding_complete?, onboarding_data? }` |
| DELETE | `/api/clients/{id}` | Delete client | - |
| POST | `/api/clients/{id}/link-workspace` | Link to OwnRBL workspace | `{ workspace_id }` |
| POST | `/api/clients/{id}/onboard` | Complete onboarding | `{ onboarding_data }` |
| POST | `/api/clients/backfill/from-workspaces` | Create clients for all workspaces | - |

### Response: Client

```json
{
  "id": "uuid",
  "name": "Checkout Components",
  "workspace_id": "uuid",
  "workspace_name": "checkout-components",
  "logo_url": "https://...",
  "onboarding_complete": true,
  "onboarding_data": {},
  "inbox_count": 12,
  "domain_count": 3,
  "campaign_count": 2,
  "created_at": "2026-01-15T...",
  "updated_at": "2026-01-15T..."
}
```

## Onboarding Routes

`/api/onboarding`

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| GET | `/api/onboarding/clients/{client_id}/submissions` | Get all submissions for client | - |
| GET | `/api/onboarding/submissions/{submission_id}` | Get single submission | - |
| PUT | `/api/onboarding/submissions/{submission_id}` | Update submission fields | `{ field: value, ... }` |
| GET | `/api/onboarding/clients/{client_id}/contact-names` | Get names for inbox generation | - |

### Response: Onboarding Submission

```json
{
  "id": "uuid",
  "client_id": "uuid",
  "company_name": "Checkout Components",
  "website": "checkoutcomponents.com",
  "contact_name": "John Smith",
  "contact_email": "john@checkoutcomponents.com",
  "employee_count": "11-50",
  "funding_stage": "Series A",
  "hq_location": "New York",
  "core_product": "E-commerce checkout optimization",
  "target_customer": "DTC brands, Shopify stores",
  "acv": "$5,000-$20,000",
  "sales_cycle_length": "2-4 weeks",
  "signals": ["pricing page visits", "competitor mentions"],
  "job_titles": ["Head of E-commerce", "CTO"],
  "outbound_tools": ["Apollo", "Instantly"],
  "crm": "HubSpot",
  "customer_voice": "We need faster checkout...",
  "roi_results": "4.7x increase in conversion",
  "tone_style": "Conversational",
  "primary_gtm_objective": "Book demos",
  "success_metrics": ["Meetings booked", "Pipeline generated"],
  "success_definition": "10 demos/month",
  "segments": [...],
  "personas": [...],
  "submission_status": "complete",
  "submitted_at": "2026-01-15T...",
  "created_at": "2026-01-15T..."
}
```

## Domain Sourcing Routes

`/api/domain-sourcing`

### Generation Endpoints

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| POST | `/api/domain-sourcing/generate` | AI-powered domain generation | `{ client_name, industry, brand_keywords, ... }` |
| POST | `/api/domain-sourcing/generate-fallback` | Pattern-based generation (no AI) | Same as above |
| POST | `/api/domain-sourcing/generate-for-client/{client_id}` | Generate using client onboarding data | `{ count, preferred_tlds, ai_provider, ai_model }` |

### Candidate Management

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| GET | `/api/domain-sourcing/can-generate/{client_id}` | Check if generation available | - |
| GET | `/api/domain-sourcing/pending-candidates/{client_id}` | Get pending candidates for review | Query: `count` |
| POST | `/api/domain-sourcing/approve/{domain_id}` | Approve domain candidate | - |
| POST | `/api/domain-sourcing/deny/{domain_id}` | Deny domain candidate | - |
| GET | `/api/domain-sourcing/approved/{client_id}` | Get approved domains ready for purchase | - |

### Search & Purchase

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| GET | `/api/domain-sourcing/registrars` | Get configured registrars | - |
| POST | `/api/domain-sourcing/search` | Search registrar availability/pricing | `{ candidates, target_price, max_price }` |
| POST | `/api/domain-sourcing/purchase` | Purchase approved domains | `{ client_id, approved_domains, nameservers }` |

### Job Management (Claude Code Worker)

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| POST | `/api/domain-sourcing/jobs/create/{client_id}` | Create generation job | Query: `count` |
| GET | `/api/domain-sourcing/jobs/status/{job_id}` | Get job status | - |
| GET | `/api/domain-sourcing/jobs/client/{client_id}` | Get client's recent jobs | Query: `limit` |

### Response: Can Generate

```json
{
  "client_id": "uuid",
  "client_name": "Checkout Components",
  "can_generate": true,
  "generation_mode": "pattern_fallback",
  "has_onboarding": false,
  "existing_domain_count": 5,
  "domain_pattern": "checkoutcomponents.com",
  "message": "Ready to generate new domains matching pattern: checkoutcomponents.com"
}
```

## Domain Routes

`/api/domains`

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| GET | `/api/domains` | List domains | Query: `workspace_id`, `client_id`, `status`, `page`, `page_size` |
| GET | `/api/domains/{domain_id}` | Get single domain | - |
| GET | `/api/domains/{domain_id}/health` | Get domain health details | - |
| GET | `/api/domains/{domain_id}/inboxes` | Get inboxes for domain | Query: `page`, `page_size` |
| POST | `/api/domains/{domain_id}/approve` | Approve pending domain | - |
| POST | `/api/domains/generate` | Generate domain from onboarding | `{ client_id, primary_domain }` |

### Response: Domain

```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "client_id": "uuid",
  "domain_name": "mailcc.io",
  "status": "active",
  "health_state": "healthy",
  "latest_health_score": 95,
  "latest_blacklist_count": 0,
  "latest_whitelist_count": 2,
  "is_clean": true,
  "inbox_count": 4,
  "live_inbox_count": 4,
  "dead_inbox_count": 0,
  "blacklist_names": [],
  "last_checked_at": "2026-01-15T...",
  "created_at": "2026-01-15T..."
}
```

## Inbox Routes

`/api/inboxes`

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| GET | `/api/inboxes` | List inboxes | Query: `workspace_id`, `client_id`, `domain_id`, `status`, `inbox_state`, `page`, `page_size` |
| GET | `/api/inboxes/{inbox_id}` | Get single inbox | - |
| GET | `/api/inboxes/{inbox_id}/health` | Get inbox health details | - |
| POST | `/api/inboxes/{inbox_id}/kill` | Manually kill inbox | `{ kill_trigger }` |
| POST | `/api/inboxes/{inbox_id}/approve` | Approve pending inbox | - |
| POST | `/api/inboxes/generate` | Generate inboxes from names | `{ client_id, domain_id, first_names }` |

### Response: Inbox

```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "client_id": "uuid",
  "email_address": "john@mailcc.io",
  "display_name": "John Smith",
  "status": "active",
  "inbox_state": "live",
  "health_state": "healthy",
  "warmup_enabled": true,
  "warmup_score": 85,
  "hard_bounces_24h": 0,
  "hard_bounces_7d": 1,
  "total_sends_7d": 150,
  "bounce_rate_7d": 0.67,
  "domain_name": "mailcc.io",
  "health_score": 92,
  "created_at": "2026-01-15T..."
}
```

## Health Routes

`/api/health`

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| GET | `/api/health/overview/{client_id}` | Get health overview for client | - |
| GET | `/api/health/dashboard/{client_id}` | Get full health dashboard | - |
| GET | `/api/health/kill-stats/{workspace_id}` | Get kill trigger statistics | - |
| GET | `/api/health/alerts` | Get active health alerts | Query: `client_id`, `workspace_id`, `severity`, `limit` |

### Response: Health Overview

```json
{
  "client_id": "uuid",
  "client_name": "Checkout Components",
  "workspace_id": "uuid",
  "total_inboxes": 12,
  "healthy_inboxes": 10,
  "warning_inboxes": 1,
  "critical_inboxes": 1,
  "dead_inboxes": 0,
  "total_domains": 3,
  "clean_domains": 3,
  "flagged_domains": 0,
  "active_campaigns": 2,
  "total_emails_sent": 5420,
  "overall_reply_rate": 3.2,
  "overall_bounce_rate": 0.8,
  "critical_alerts": 1,
  "warning_alerts": 1,
  "last_updated": "2026-01-15T..."
}
```

## Strategy Routes (NEW - Phase 3)

`/api/strategy` - To be implemented

| Method | Path | Purpose | Request Body |
|--------|------|---------|--------------|
| POST | `/api/strategy/jobs` | Create strategy generation job | `{ client_id, submission_id? }` |
| GET | `/api/strategy/jobs/{job_id}` | Get job status | - |
| GET | `/api/strategy/jobs/client/{client_id}` | Get client's jobs | Query: `limit` |
| GET | `/api/strategy/suggestions/{client_id}` | Get suggestions for client | Query: `status`, `limit` |
| POST | `/api/strategy/suggestions/{suggestion_id}/approve` | Approve suggestion | - |
| POST | `/api/strategy/suggestions/{suggestion_id}/deny` | Deny suggestion | - |
| POST | `/api/strategy/suggestions/{suggestion_id}/revision` | Request revision | `{ instruction }` |

## Error Responses

All endpoints return standard error format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

| Status Code | Meaning |
|-------------|---------|
| 400 | Bad Request - Invalid input |
| 404 | Not Found - Resource doesn't exist |
| 500 | Internal Server Error |
| 503 | Service Unavailable - External dependency unavailable |

## Related

- [[../infrastructure/coolify]] - Deployment details
- [[data-flow]] - How data moves through system
- [[claude-code-worker]] - Worker integration for generation jobs
