# HyperTide Order Flow

## Overview

HyperTide orders are now **fully automated** via REST API. When you create an order from the Infrastructure page, the system:

1. Creates an `inbox_purchase_job` with `worker_mode='api'`
2. Worker picks up the job and calls HyperTide REST API directly
3. Inboxes are created automatically (no manual steps)
4. Slack notifications sent at each stage

## Order Specifications

| Plan | Domains/Order | Inboxes/Domain | Inboxes/Order | Cost |
|------|---------------|----------------|---------------|------|
| **Entra** | 2 | 50 | 100 | $50/mo |
| **Google** | 5 | 3 | 15 | $50/mo |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │     │   Charm API     │     │ Hypertide Worker│
│  (Next.js)      │────▶│   (FastAPI)     │────▶│   (Python)      │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌─────────────────┐              │
                        │  Slack Webhook  │◀─────────────┤
                        │  (Notifications)│              │
                        └─────────────────┘              │
                                                         ▼
                                                ┌─────────────────┐
                                                │  Hypertide API  │
                                                │  (REST API)     │
                                                └─────────────────┘
```

## Flow Details

### 1. Order Creation (Frontend → API)

```
POST /api/infrastructure/hypertide-order
{
  "client_id": "uuid",
  "workspace_id": "uuid",
  "provider": "entra" | "google",
  "domain_ids": ["uuid", ...],
  "order_count": 1
}
```

Creates `inbox_purchase_job` with:
- `status = 'pending'`
- `worker_mode = 'api'` (automated REST API flow)
- `domain_names` array for the order

### 2. Worker Processing

The `hypertide_worker.py` polls for pending jobs:

```python
# Priority order:
1. Domain purchase jobs (Porkbun/Dynadot)
2. Inbox purchase jobs - API mode (automated)
3. Inbox purchase jobs - Worker mode (Slack spec)
```

For API mode jobs:
1. **Validates inputs** - checks Bison credentials
2. **Sends "Initiated" notification** - blue Slack message
3. **Calls Hypertide API** - `POST /orders`
4. **Updates job status** - completed/failed
5. **Sends result notification** - green/red Slack message

### 3. Hypertide API Call

```json
POST https://backend.hypertide.io/api/v1/orders
Headers: X-API-Key: {HYPERTIDE_API_KEY}

{
  "plan": "entra",
  "domains": ["domain1.com", "domain2.com"],
  "domain_option": "i_have_my_own_domains",
  "forwarding_domain": "company.com",
  "client_name": "Company Name",
  "selected_tool": "bison",
  "tool_credentials": {
    "bison_url": "https://spellcast.hirecharm.com",
    "username": "...",
    "password": "...",
    "workspace": "..."
  },
  "users": [{"first_name": "John", "last_name": "Doe"}],
  "warmup_setup": {
    "enabled": true,
    "settings": {
      "warmup_limit": 5,
      "warmup_reply_rate": 100,
      "warmup_increment": 1
    }
  }
}
```

## Slack Notifications

| Stage | Message | Color |
|-------|---------|-------|
| Order Initiated | 🚀 HyperTide Order Initiated | 🔵 Blue |
| Order Complete | ✅ HyperTide Order Complete | 🟢 Green |
| Order Failed | ❌ HyperTide Order Failed | 🔴 Red |

Each notification includes:
- Client name
- Provider type (Entra/Google)
- Domain count
- Expected inboxes
- Estimated cost
- Job ID

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HYPERTIDE_API_KEY` | **Yes** | Hypertide REST API key |
| `EMAILBISON_USERNAME` | **Yes** | Default Bison login email |
| `EMAILBISON_PASSWORD` | **Yes** | Default Bison password |
| `EMAILBISON_API_URL` | No | Bison URL (default: spellcast.hirecharm.com) |
| `SLACK_ORDERS_WEBHOOK_URL` | No | Slack webhook for notifications |

## Files

| File | Purpose |
|------|---------|
| `hypertide_worker.py` | Main worker - processes all job types |
| `hypertide_api/client.py` | Low-level Hypertide REST API client |
| `hypertide_api/models.py` | Pydantic models for orders |
| `hypertide_api/service.py` | Business logic + duplicate detection |
| `api/routes/infrastructure.py` | API endpoints for order creation |

## Error Handling

| Error Type | Cause | Action |
|------------|-------|--------|
| `AUTHENTICATION` | Invalid API key | Check `HYPERTIDE_API_KEY` |
| `DOMAIN_CONFLICT` | Domain already exists | Manual review |
| `VALIDATION` | Invalid request data | Check domain format |
| `PAYMENT_REQUIRED` | Payment method issue | Check Stripe in Hypertide |

Failed orders:
- Marked `status='failed'` in database
- Red Slack notification sent
- Manual retry required

## Testing

### Validation Only (No Charge)
```bash
curl -X POST http://localhost:8000/api/infrastructure/hypertide-order/test \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "...",
    "workspace_id": "...",
    "provider": "entra",
    "domain_ids": ["...", "..."],
    "dry_run": true
  }'
```

### Full Order (Will Charge)
Trigger via frontend Infrastructure page or:
```bash
curl -X POST http://localhost:8000/api/infrastructure/hypertide-order \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "...",
    "workspace_id": "...",
    "provider": "entra",
    "domain_ids": ["...", "..."],
    "order_count": 1
  }'
```

## Monitoring

```bash
# Watch worker logs
docker logs charm-hypertide-worker -f

# Check pending jobs
docker exec charm-postgres psql -U postgres -d postgres -c "
  SELECT id, status, worker_mode, provider_type, created_at
  FROM inbox_purchase_jobs
  WHERE status IN ('pending', 'executing')
  ORDER BY created_at DESC;
"
```
