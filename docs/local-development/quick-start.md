---
title: Quick Start - Complete Local Setup
created: 2026-02-12
updated: 2026-02-12
tags: [quickstart, local, docker, setup]
---

# Quick Start - Complete Local Setup

This guide will get you from zero to a fully running Charm Email OS in under 15 minutes.

## Prerequisites

- **Docker Desktop** - Running and configured
- **Git** - For cloning the repository
- **Claude Code credentials** - For strategy generation (optional)

## Step 1: Clone the Repositories

```bash
# Clone the main repository
cd D:\Work
git clone https://github.com/hirecharm/charm-email-os.git

# Clone the onboarding form (sibling directory)
git clone https://github.com/hirecharm/hirecharm-onboarding.git
```

## Step 2: Configure Environment

Copy the example environment file and customize:

```bash
cd charm-email-os
cp .env.example .env.local
```

Edit `.env.local` with your values:

```bash
# Database (defaults work for local)
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=localdevpassword

# EmailBison API (for sync worker)
EMAILBISON_API_KEY=your_api_key_here
EMAILBISON_API_URL=https://spellcast.hirecharm.com

# Optional: Slack alerts
SLACK_WEBHOOK_URL=
```

## Step 3: Start Core Services

```bash
# Start all services
docker compose -f docker-compose.local.yml up -d

# Verify services are healthy
docker compose -f docker-compose.local.yml ps
```

Expected output:
```
NAME                  STATUS
charm-postgres        running (healthy)
charm-api             running (healthy)
charm-frontend        running (healthy)
charm-onboarding      running (healthy)
charm-emailbison-sync running (healthy)
charm-strategy-worker running (healthy)
```

## Step 4: Access the Application

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:3000 | Main application |
| API | http://localhost:8000 | Backend API |
| API Docs | http://localhost:8000/docs | Swagger documentation |
| Onboarding | http://localhost:3004 | Client submission form |
| Database | localhost:5433 | PostgreSQL (postgres/localdevpassword) |

**Test Client URL**: http://localhost:3000/clients/4bd07dc0-059a-448b-b6f4-3275d0c104a9

## Step 5: Strategy Worker Authentication (First Time Only)

The strategy worker requires Claude Code authentication:

```bash
# Option A: Mount existing credentials (recommended)
# If you have ~/.claude configured, it's auto-mounted

# Option B: Authenticate inside container
docker exec -it charm-strategy-worker bash
claude /login
# Follow the browser OAuth flow
exit
```

Verify authentication:
```bash
docker logs charm-strategy-worker --tail 20
# Should show: "OAuth token is valid ✓"
```

## Step 6: Test the Full Flow

### Create an Onboarding Submission

```bash
curl -X POST http://localhost:3004/onboarding/submit \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "4bd07dc0-059a-448b-b6f4-3275d0c104a9",
    "company_name": "Charm",
    "website": "https://hirecharm.com",
    "core_product": "AI-powered outbound email platform",
    "target_customer": "B2B SaaS companies with SDR teams"
  }'
```

### Trigger Strategy Generation

```bash
# Create a cycle
curl -X POST "http://localhost:8000/api/strategy/cycles/4bd07dc0-059a-448b-b6f4-3275d0c104a9" \
  -H "Content-Type: application/json" \
  -d '{}'

# The response includes the cycle_id, use it to generate:
curl -X POST "http://localhost:8000/api/strategy/cycles/{cycle_id}/generate" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Monitor Generation Progress

```bash
# Check phases status
curl "http://localhost:8000/api/strategy/jobs/{job_id}/phases"

# Watch worker logs
docker logs -f charm-strategy-worker
```

## Service Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    CHARM EMAIL OS LOCAL STACK                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  Frontend   │    │    API      │    │ Onboarding  │         │
│  │  :3000      │───▶│   :8000     │◀───│   :3004     │         │
│  │  Next.js    │    │  FastAPI    │    │  FastAPI    │         │
│  └─────────────┘    └──────┬──────┘    └─────────────┘         │
│                            │                                    │
│                            ▼                                    │
│                    ┌─────────────┐                              │
│                    │  PostgreSQL │                              │
│                    │   :5433     │                              │
│                    └──────┬──────┘                              │
│                            │                                    │
│            ┌───────────────┼───────────────┐                   │
│            ▼               ▼               ▼                   │
│     ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│     │  Strategy   │ │  EmailBison │ │   Other     │           │
│     │   Worker    │ │    Sync     │ │  Workers    │           │
│     │  (Claude)   │ │   Worker    │ │  (Future)   │           │
│     └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Stopping and Cleaning Up

```bash
# Stop all services
docker compose -f docker-compose.local.yml down

# Stop and remove volumes (fresh start)
docker compose -f docker-compose.local.yml down -v

# Remove built images
docker compose -f docker-compose.local.yml down --rmi local
```

## Troubleshooting

### Service not starting

```bash
# Check logs for the failing service
docker logs <container-name>

# Rebuild a specific service
docker compose -f docker-compose.local.yml up -d --build <service-name>
```

### Database connection issues

```bash
# Verify PostgreSQL is healthy
docker exec charm-postgres pg_isready

# Connect directly
docker exec -it charm-postgres psql -U postgres -d postgres
```

### Strategy worker authentication failed

```bash
# Re-authenticate
docker exec -it charm-strategy-worker claude /login
```

## Related Documentation

- [[index]] - Local Development Hub
- [[workers]] - AI Workers Reference
- [[emailbison-sync-worker]] - EmailBison Sync Worker
- [[strategy-worker-setup]] - Strategy Worker Setup
- [[environment-variables]] - All Environment Variables
