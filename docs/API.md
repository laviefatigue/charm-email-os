# Charm Email OS API Documentation

## Overview

The Charm Email OS API is a FastAPI-based REST API that manages email infrastructure, clients, domains, inboxes, and campaigns.

**Base URL**: `http://localhost:8000/api` (development) or your production URL

**Authentication**: Currently no authentication required (use Cloudflare Access for production)

---

## API Endpoints by Category

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Basic health check (root level) |
| GET | `/api/health/detailed` | Detailed health with database status |
| GET | `/api/health/database` | Database connection status |

---

### Clients (`/api/clients`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/clients` | List all clients with pagination |
| POST | `/api/clients` | Create a new client (auto-creates workspace) |
| GET | `/api/clients/{client_id}` | Get client by ID |
| PUT | `/api/clients/{client_id}` | Update client |
| DELETE | `/api/clients/{client_id}` | Delete client |
| POST | `/api/clients/{client_id}/link-workspace` | Link client to existing workspace |
| POST | `/api/clients/{client_id}/create-workspace` | Create new workspace for client |
| POST | `/api/clients/{client_id}/onboard` | Complete client onboarding |

**Sender Names:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/clients/{client_id}/sender-names` | Get pre-generated sender names |
| POST | `/api/clients/{client_id}/set-sender-name` | Set base sender name (replaces all) |
| POST | `/api/clients/{client_id}/add-sender-name` | Add sender name (appends) |
| DELETE | `/api/clients/{client_id}/sender-names/{index}` | Delete sender name by index |
| GET | `/api/clients/{client_id}/sender-name-config` | Get full sender name configuration |
| GET | `/api/clients/{client_id}/sender-names-for-provisioning` | Get names formatted for HyperTide |

---

### Workspaces (`/api/workspaces`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/workspaces` | List all workspaces |
| GET | `/api/workspaces/summary` | Get workspace summary list |
| GET | `/api/workspaces/{workspace_id}` | Get workspace by ID |
| GET | `/api/workspaces/{workspace_id}/stats` | Get workspace statistics |

---

### Domains (`/api/domains`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/domains` | List domains (supports filtering) |
| GET | `/api/domains/{domain_id}` | Get domain by ID |
| PUT | `/api/domains/{domain_id}` | Update domain |

---

### Inboxes (`/api/inboxes`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/inboxes` | List inboxes (sender accounts) |
| GET | `/api/inboxes/{inbox_id}` | Get inbox by ID |
| PUT | `/api/inboxes/{inbox_id}` | Update inbox |

---

### Campaigns (`/api/campaigns`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/campaigns` | List campaigns |
| GET | `/api/campaigns/{campaign_id}` | Get campaign by ID |

---

### Domain Sourcing (`/api/domain-sourcing`)

**Registrar Status:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/domain-sourcing/registrar-status` | Get Dynadot/Porkbun connection status and balances |

**Pricing:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/domain-sourcing/check-domain/{domain}` | Check single domain availability |
| POST | `/api/domain-sourcing/bulk-check` | Check multiple domain prices |

**Purchasing:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/domain-sourcing/purchase/{domain_id}` | Purchase single domain |
| POST | `/api/domain-sourcing/purchase-domains` | Bulk purchase domains |

**Example - Registrar Status Response:**
```json
{
  "dynadot": {
    "configured": true,
    "connected": true,
    "balance": "156.78",
    "error": null
  },
  "porkbun": {
    "configured": true,
    "connected": true,
    "balance": "243.50",
    "error": null
  }
}
```

**Example - Insufficient Funds (HTTP 402):**
```json
{
  "detail": "Insufficient dynadot balance. Need $12.99, have $5.00."
}
```

---

### Infrastructure (`/api/infrastructure`)

**Waterfall Views:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/infrastructure/waterfall/client/{client_id}` | Get infrastructure waterfall for client |
| GET | `/api/infrastructure/waterfall/workspace/{workspace_id}` | Get infrastructure waterfall for workspace |

**Domain Generation:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/infrastructure/generate-domains/simple` | Generate domain suggestions |

**Bulk Operations:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/infrastructure/bulk-price-check` | Two-phase price check (Dynadot then Porkbun) |
| POST | `/api/infrastructure/bulk-purchase` | Create bulk purchase job |

**HyperTide Orders:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/infrastructure/hypertide-order` | Create HyperTide order job |
| POST | `/api/infrastructure/hypertide-order/test` | Validate order without charging |

**DNS Verification:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/infrastructure/verify-dns/{domain_id}` | Verify DNS configuration |
| POST | `/api/infrastructure/fix-dns/{domain_id}` | Fix DNS issues |

**Example - HyperTide Test Order Request:**
```json
{
  "client_id": "uuid-here",
  "workspace_id": "uuid-here",
  "provider": "entra",
  "domain_ids": ["domain-uuid-1", "domain-uuid-2"],
  "dry_run": true
}
```

**Example - HyperTide Test Order Response:**
```json
{
  "is_valid": true,
  "validation_errors": [],
  "order_preview": {
    "plan": "entra",
    "domains": ["domain1.com", "domain2.com"],
    "domain_option": "i_have_my_own_domains",
    "forwarding_domain": "hirecharm.com",
    "client_name": "Charm",
    "selected_tool": "bison",
    "tool_credentials": {...},
    "users": [{"first_name": "Chris", "last_name": "Booth"}],
    "warmup_setup": {"enabled": true, "settings": {...}}
  },
  "hypertide_response": null
}
```

---

### Inbox Purchasing (`/api/inbox-purchasing`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/inbox-purchasing/execute` | Execute HyperTide purchase |
| GET | `/api/inbox-purchasing/status/{job_id}` | Get purchase job status |
| POST | `/api/inbox-purchasing/calculate` | Calculate optimal order quantities |
| DELETE | `/api/inbox-purchasing/jobs/{job_id}` | Cancel purchase job |

---

### Subscriptions (`/api/subscriptions`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/subscriptions/templates` | List package templates |
| GET | `/api/subscriptions/client/{client_id}` | Get client subscription |
| POST | `/api/subscriptions/client/{client_id}` | Create subscription |
| PUT | `/api/subscriptions/client/{client_id}` | Update subscription |
| POST | `/api/subscriptions/client/{client_id}/apply-template` | Apply package template |

---

### Inventory (`/api/inventory`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/inventory/summary` | Get inventory summary |
| GET | `/api/inventory/domains` | List domains in inventory |

---

### Health Analysis (`/api/health/analysis`)

Endpoints for analyzing inbox health, kill triggers, and domain performance.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health/analysis/kill-trigger-by-esp` | Kill trigger breakdown by ESP (Google/Microsoft) |
| GET | `/api/health/analysis/kill-trigger-lifecycle` | Kill triggers by lifecycle stage |
| GET | `/api/health/analysis/domain-capacity-impact` | Domain lifespan and capacity loss analysis |
| GET | `/api/health/analysis/domain-bounce-rollup` | Domains with bounces (filterable by workspace) |
| GET | `/api/health/analysis/spam-complaint-timing` | When spam complaints occur in inbox lifecycle |
| GET | `/api/health/workspace-sync-diagnosis` | Diagnose sync issues for a workspace |

**Common Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | Filter to specific workspace (recommended) |

**Example - Domain Bounce Rollup:**
```
GET /api/health/analysis/domain-bounce-rollup?workspace_id=3fabfb3c-80d1-4991-8834-70cfbe0c97b9
```

**Response:**
```json
{
  "workspace_id": "3fabfb3c-80d1-4991-8834-70cfbe0c97b9",
  "summary": {
    "domains_with_bounces": 36,
    "total_bounces_24h": 281,
    "inboxes_with_bounces_24h": 176
  },
  "domains": [
    {
      "domain": "enableselery.com",
      "esp": "microsoft",
      "total_inboxes": 52,
      "inboxes_with_bounces_24h": 16,
      "total_bounces_24h": 18,
      "inboxes_with_bounces_alltime": 16,
      "total_bounces_alltime": 18,
      "dead_inboxes": 0,
      "live_connected": 52
    }
  ]
}
```

**Example - Kill Trigger by ESP:**
```
GET /api/health/analysis/kill-trigger-by-esp
```

**Response:**
```json
{
  "esp_summary": [
    {"provider": "microsoft", "total_inboxes": 3936, "dead_count": 914, "kill_rate_pct": 23.2},
    {"provider": "google", "total_inboxes": 537, "dead_count": 216, "kill_rate_pct": 40.2}
  ],
  "triggers_by_esp": [
    {"provider": "microsoft", "trigger_type": "fresh_inbox_bounce", "count": 659},
    {"provider": "microsoft", "trigger_type": "spam_complaint", "count": 185},
    {"provider": "google", "trigger_type": "hard_bounces_24h", "count": 127},
    {"provider": "google", "trigger_type": "spam_complaint", "count": 20}
  ]
}
```

---

## Error Responses

All endpoints return standard HTTP status codes:

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (invalid input) |
| 402 | Payment Required (insufficient funds) |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |

**Standard Error Format:**
```json
{
  "detail": "Error message here"
}
```

---

## Rate Limits

- **Porkbun API**: 1 request per 10 seconds (enforced by registrar)
- **Dynadot API**: No rate limit documented
- **EmailBison API**: Standard REST limits

---

## Environment Variables

See [DEPLOYMENT.md](./DEPLOYMENT.md) for full environment variable reference.

Key variables:
- `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `EMAILBISON_API_KEY`, `EMAILBISON_API_URL`
- `DYNADOT_API_KEY`
- `PORKBUN_API_KEY`, `PORKBUN_API_SECRET`
