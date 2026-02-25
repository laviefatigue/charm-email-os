---
title: Environment Variables Reference
created: 2026-02-10
updated: 2026-02-13
tags: [environment, config, reference, emailbison, slack, dynadot, porkbun, registrars]
---

# Environment Variables Reference

Complete reference for all environment variables used in Charm Email OS.

## Local Development

### Database (PostgreSQL)

| Variable | Local Value | Description |
|----------|-------------|-------------|
| `POSTGRES_HOST` | `postgres` (Docker) / `localhost` | Database host |
| `POSTGRES_PORT` | `5432` (internal) / `5433` (external) | Database port |
| `POSTGRES_DB` | `postgres` | Database name |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `localdevpassword` | Database password |
| `POSTGRES_SCHEMA` | `public` | Default schema |

### API (FastAPI)

| Variable | Local Value | Description |
|----------|-------------|-------------|
| `API_TITLE` | `Charm Email OS API (LOCAL)` | API title in Swagger |
| `API_VERSION` | `1.0.0-local` | API version |
| `DEBUG` | `true` | Enable debug mode |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |

### Frontend (Next.js)

| Variable | Local Value | Description |
|----------|-------------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API URL for frontend |
| `NODE_ENV` | `development` / `production` | Node environment |

### Workers

| Variable | Default | Description |
|----------|---------|-------------|
| `POLL_INTERVAL` | `5` | Seconds between job polls |
| `CLAUDE_ACCOUNT` | `ClaudeCodeMax` | Claude subscription account |
| `OAUTH_CHECK_INTERVAL` | `3600` | Seconds between OAuth checks |
| `ALERT_WEBHOOK_URL` | (empty) | Webhook for alerts |

### EmailBison Sync

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAILBISON_API_KEY` | **Required** | EmailBison API token (format: `17\|xxx...`) |
| `EMAILBISON_API_URL` | `https://spellcast.hirecharm.com/api` | EmailBison API URL |
| `SYNC_INTERVAL_EVENTS` | `300` | Events sync interval (seconds) |
| `SYNC_INTERVAL_FULL` | `3600` | Full account sync interval (seconds) |
| `SYNC_INTERVAL_HEALTH` | `900` | Health check interval (seconds) |
| `SYNC_INTERVAL_KILL` | `1800` | Kill queue processing interval (seconds) |
| `SYNC_INTERVAL_WARMUP` | `1800` | Warmup sync interval (seconds) |

> **Important**: The `EMAILBISON_API_KEY` must be set in `.env.local` for the sync worker to function. Without it, health scores will be NULL and infrastructure health data will be incomplete.

### Slack Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACK_ORDERS_WEBHOOK_URL` | **Required for Slack orders** | Webhook for inbox provisioning orders (#hypertide-orders) |
| `SLACK_WEBHOOK_URL` | (empty) | Webhook for sync alerts |

### Domain Registrar APIs

| Variable | Default | Description |
|----------|---------|-------------|
| `DYNADOT_API_KEY` | **Required** | Dynadot API key for domain purchasing |
| `PORKBUN_API_KEY` | **Required** | Porkbun API key (format: `pk1_xxx`) |
| `PORKBUN_API_SECRET` | **Required** | Porkbun API secret (format: `sk1_xxx`) |

> **Important**: Both registrar credentials are required for dual-provider pricing. The system checks both providers and automatically selects the cheapest.
>
> Get credentials from:
> - **Dynadot**: https://www.dynadot.com/community/developers
> - **Porkbun**: https://porkbun.com/account/api

### Optional Services

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (empty) | Anthropic API key (alternative to OAuth) |

## Production Environment

### Database

| Variable | Source | Description |
|----------|--------|-------------|
| `POSTGRES_HOST` | Coolify secret | OwnRBL database host |
| `POSTGRES_PORT` | Coolify secret | Usually 5432 |
| `POSTGRES_DB` | Coolify secret | Database name |
| `POSTGRES_USER` | Coolify secret | Database user |
| `POSTGRES_PASSWORD` | Coolify secret | Database password |

### API

| Variable | Production Value | Description |
|----------|------------------|-------------|
| `API_TITLE` | `Charm Email OS API` | API title |
| `API_VERSION` | `1.0.0` | API version |
| `DEBUG` | `false` | Disable debug |
| `CORS_ORIGINS` | `["https://app.laviefatigue.com"]` | Production frontend |

### Frontend

| Variable | Production Value | Description |
|----------|------------------|-------------|
| `NEXT_PUBLIC_API_URL` | `https://api.laviefatigue.com` | Production API |
| `NODE_ENV` | `production` | Production mode |

### Purchase Worker (Additional)

| Variable | Source | Description |
|----------|--------|-------------|
| `HYPERTIDE_EMAIL` | Coolify secret | HyperTide login |
| `HYPERTIDE_PASSWORD` | Coolify secret | HyperTide password |
| `BISON_USERNAME` | Coolify secret | EmailBison login |
| `BISON_PASSWORD` | Coolify secret | EmailBison password |
| `BISON_URL` | Coolify secret | EmailBison URL |
| `STRIPE_CARD_NUMBER` | Coolify secret | Payment card |
| `STRIPE_CARD_EXP` | Coolify secret | Card expiry |
| `STRIPE_CARD_CVC` | Coolify secret | Card CVC |
| `STRIPE_CARD_ZIP` | Coolify secret | Billing ZIP |
| `JOB_TIMEOUT` | `1800` | Job timeout in seconds |

## .env.local Template

Create `.env.local` in project root for local development:

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=localdevpassword

# API
DEBUG=true
CORS_ORIGINS=["http://localhost:3000"]

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000

# Workers (optional)
POLL_INTERVAL=5
CLAUDE_ACCOUNT=ClaudeCodeMax

# EmailBison Sync (REQUIRED for health monitoring)
EMAILBISON_API_KEY=17|YOUR_TOKEN_HERE
EMAILBISON_API_URL=https://spellcast.hirecharm.com

# Domain Registrar APIs (REQUIRED for domain purchasing)
DYNADOT_API_KEY=your_dynadot_api_key
PORKBUN_API_KEY=pk1_xxx
PORKBUN_API_SECRET=sk1_xxx

# Slack Integration (REQUIRED for inbox provisioning)
SLACK_ORDERS_WEBHOOK_URL=https://hooks.slack.com/services/xxx/xxx/xxx

# Optional Services
SLACK_WEBHOOK_URL=
```

> **Note**: Get your EmailBison API key from the EmailBison dashboard under Settings > API.
>
> **Note**: The `SLACK_ORDERS_WEBHOOK_URL` webhook should point to your #hypertide-orders channel. Without it, inbox provisioning orders will fail.
>
> **Note**: Domain registrar credentials are required for domain purchasing. Both providers are checked for pricing - the system auto-selects the cheapest.

## Variable Usage by Service

### In docker-compose.local.yml

```yaml
services:
  charm-api:
    environment:
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_PASSWORD=localdevpassword
```

### In Python (FastAPI)

```python
import os

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
```

### In Next.js

```typescript
// Client-side (must be prefixed with NEXT_PUBLIC_)
const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// Server-side only
const secret = process.env.API_SECRET;
```

## Local vs Production Comparison

| Variable | Local | Production |
|----------|-------|------------|
| `POSTGRES_HOST` | `postgres` / `localhost` | OwnRBL IP |
| `POSTGRES_PORT` | `5433` (external) | `5432` |
| `POSTGRES_PASSWORD` | `localdevpassword` | Secret |
| `DEBUG` | `true` | `false` |
| `CORS_ORIGINS` | `localhost:3000` | `app.laviefatigue.com` |
| `NEXT_PUBLIC_API_URL` | `localhost:8000` | `api.laviefatigue.com` |

## Security Notes

1. **Never commit secrets** - Use `.env.local` (gitignored) for local secrets
2. **Use Coolify secrets** - Production secrets are managed in Coolify UI
3. **Local passwords are intentionally weak** - `localdevpassword` is fine for local dev
4. **API keys are optional locally** - Most features work without external service keys

## Related

- [[docker-compose-reference]] - Compose files
- [[development-workflow]] - Development process
- [[../infrastructure/coolify]] - Production environment
