# Charm Email OS - Deployment Guide

## Overview

This guide covers deploying Charm Email OS to Coolify or any Docker-compatible environment.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Production Stack                        │
├─────────────────────────────────────────────────────────────┤
│  charm-frontend (3000)    │  executive-dashboard (3006)    │
│  Next.js 16               │  Next.js 16                    │
├─────────────────────────────────────────────────────────────┤
│                    charm-api (8000)                         │
│                    FastAPI / Python 3.11                    │
├─────────────────────────────────────────────────────────────┤
│                  emailbison-sync (worker)                   │
│                  Background sync service                    │
├─────────────────────────────────────────────────────────────┤
│                   PostgreSQL 15                             │
│                   (Coolify-managed or external)             │
└─────────────────────────────────────────────────────────────┘
```

---

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `POSTGRES_HOST` | PostgreSQL host | `postgres` or IP address |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_DB` | Database name | `postgres` |
| `POSTGRES_USER` | Database user | `postgres` |
| `POSTGRES_PASSWORD` | Database password | (secure password) |
| `EMAILBISON_API_KEY` | EmailBison API key | `eb_xxx...` |
| `EMAILBISON_API_URL` | EmailBison API URL | `https://spellcast.hirecharm.com` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DYNADOT_API_KEY` | Dynadot API key | (empty) |
| `PORKBUN_API_KEY` | Porkbun API key | (empty) |
| `PORKBUN_API_SECRET` | Porkbun API secret | (empty) |
| `NEXT_PUBLIC_API_URL` | API URL for frontend | `http://localhost:8000` |
| `FRONTEND_URL` | Frontend URL for CORS | `http://localhost:3000` |
| `DEBUG` | Enable debug mode | `false` |
| `API_PORT` | API server port | `8000` |
| `FRONTEND_PORT` | Frontend port | `3000` |
| `EXEC_DASHBOARD_PORT` | Dashboard port | `3006` |

### Sync Worker Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNC_INTERVAL_EVENTS` | Event sync interval (seconds) | `300` |
| `SYNC_INTERVAL_FULL` | Full sync interval (seconds) | `3600` |
| `SYNC_INTERVAL_HEALTH` | Health check interval (seconds) | `900` |

---

## Docker Compose Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Production deployment (3 services) |
| `docker-compose.local.yml` | Local development (10+ services) |
| `docker-compose.strategy-worker.yml` | Strategy AI worker |
| `docker-compose.domain-worker.yml` | Domain generation worker |

---

## Coolify Deployment

### Step 1: Create PostgreSQL Database

1. In Coolify dashboard, create new PostgreSQL 15 database
2. Note the connection details:
   - Host: (auto-assigned)
   - Port: 5432
   - Database: `charm_email_os`
   - User: `charm`
   - Password: (auto-generated)

### Step 2: Import Data

```bash
# Export from source database
pg_dump -h <source-host> -U postgres -d postgres \
  --no-owner --no-acl -F c -f backup.dump

# Import to Coolify PostgreSQL
pg_restore -h <coolify-host> -U charm -d charm_email_os \
  --no-owner --no-acl backup.dump
```

### Step 3: Deploy Applications

For each application:

1. **Source**: Connect to GitHub repository
2. **Docker Compose**: Use `docker-compose.yml`
3. **Environment Variables**: Configure in Coolify dashboard

#### charm-api

- Build Path: `api/`
- Dockerfile: `api/Dockerfile`
- Port: 8000
- Health Check: `GET /health`

#### charm-frontend

- Build Path: `charm-email-os/`
- Dockerfile: `charm-email-os/Dockerfile`
- Port: 3000
- Build Arg: `NEXT_PUBLIC_API_URL=https://<api-url>`

#### executive-dashboard

- Build Path: `executive-dashboard/`
- Dockerfile: `executive-dashboard/Dockerfile`
- Port: 3006
- Build Arg: `NEXT_PUBLIC_API_URL=https://<api-url>`

#### emailbison-sync

- Dockerfile: `Dockerfile.emailbison-sync`
- No exposed port (background worker)

### Step 4: Configure Environment

In Coolify dashboard, set environment variables for each application:

```env
# Database
POSTGRES_HOST=<coolify-postgres-host>
POSTGRES_PORT=5432
POSTGRES_DB=charm_email_os
POSTGRES_USER=charm
POSTGRES_PASSWORD=<password>

# EmailBison
EMAILBISON_API_KEY=<your-key>
EMAILBISON_API_URL=https://spellcast.hirecharm.com

# Registrars (for domain purchases)
DYNADOT_API_KEY=<your-key>
PORKBUN_API_KEY=<your-key>
PORKBUN_API_SECRET=<your-secret>

# URLs (update after deployment)
NEXT_PUBLIC_API_URL=https://<api-domain>
FRONTEND_URL=https://<frontend-domain>
```

### Step 5: Verify Deployment

1. **API Health**: `GET /health` should return `{"status": "healthy"}`
2. **Registrar Status**: `GET /api/domain-sourcing/registrar-status`
3. **Sync Worker**: Check logs for sync activity

---

## Local Development

```bash
# Start all services
docker compose -f docker-compose.local.yml up -d

# View logs
docker compose -f docker-compose.local.yml logs -f charm-api

# Rebuild after changes
docker compose -f docker-compose.local.yml up -d --build

# Stop all services
docker compose -f docker-compose.local.yml down
```

---

## Post-Deployment

### Custom Domain

1. Configure custom domain in Coolify
2. Update `NEXT_PUBLIC_API_URL` environment variable
3. Update `FRONTEND_URL` for CORS
4. Redeploy frontend with new build args

### Cloudflare Access

1. Log into Cloudflare Zero Trust
2. Create Access Application
3. Configure authentication (Email OTP, SSO, etc.)
4. Create Access Policy with allowed emails

---

## Troubleshooting

### Database Connection Issues

```bash
# Test connection
docker exec <container> psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1"
```

### API Not Starting

Check logs for database connection errors:
```bash
docker logs charm-api --tail 50
```

### Sync Worker Not Running

```bash
# Check sync worker logs
docker logs charm-emailbison-sync --tail 100
```

### Missing Registrar Keys

If `GET /api/domain-sourcing/registrar-status` returns "not configured":
- Verify `DYNADOT_API_KEY` is set in environment
- Verify `PORKBUN_API_KEY` and `PORKBUN_API_SECRET` are set
- Restart the API container

---

## Excluded Components

The following are NOT deployed in standard production:

- `strategy-worker` - AI strategy generation (separate deployment)
- `domain-worker` - AI domain generation (separate deployment)
- `hypertide-worker` - Browser automation (manual operation)
- `price-checker` - Background price checker (optional)
