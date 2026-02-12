---
title: Development Workflow - Local to Production
created: 2026-02-10
updated: 2026-02-10
tags: [workflow, development, deployment, git]
---

# Development Workflow: Local to Production

This document describes the complete workflow for making changes to Charm Email OS, from local development through production deployment.

## Principle: Local First

**All changes start locally, then deploy to production.**

This ensures:
1. Changes are tested before affecting real users
2. Database migrations are validated locally first
3. Integration points are verified
4. Rollback is simple (don't push)

## Step 1: Set Up Local Environment

### First Time Setup

```bash
# Clone the repository
git clone <repo-url> D:\Work\charm-email-os
cd D:\Work\charm-email-os

# Start all services
docker compose -f docker-compose.local.yml up -d

# Wait for services to be healthy
docker compose -f docker-compose.local.yml ps

# Verify everything is running
curl http://localhost:8000/health
```

### Subsequent Sessions

```bash
cd D:\Work\charm-email-os

# Start services
docker compose -f docker-compose.local.yml up -d

# Check status
docker compose -f docker-compose.local.yml ps
```

## Step 2: Choose Development Mode

### Option A: Full Docker (Recommended for Integration Testing)

All services run in Docker containers.

```bash
# Start everything
docker compose -f docker-compose.local.yml up -d

# Rebuild after code changes
docker compose -f docker-compose.local.yml up -d --build
```

**Pros**: Matches production exactly
**Cons**: Slower iteration, no hot reload

### Option B: Hybrid (Recommended for Active Development)

Database in Docker, frontend/API run locally with hot reload.

```bash
# Start only database
docker compose -f docker-compose.local.yml up -d postgres

# Run API locally (in one terminal)
cd api
pip install -r requirements.txt
POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_PASSWORD=localdevpassword uvicorn main:app --reload

# Run frontend locally (in another terminal)
cd charm-email-os
npm install
npm run dev
```

**Pros**: Fast iteration with hot reload
**Cons**: Slight env differences from production

### Option C: Frontend Only (UI Development)

Frontend runs locally, API points to production.

```bash
cd charm-email-os

# Edit .env.local
echo "NEXT_PUBLIC_API_URL=https://api.laviefatigue.com" > .env.local

# Run frontend
npm run dev
```

**Pros**: Real data, fast iteration
**Cons**: Can't test API changes

## Step 3: Make Changes

### Frontend Changes (Next.js)

Location: `D:\Work\charm-email-os\charm-email-os\`

```
charm-email-os/
├── app/                    # Next.js App Router pages
│   ├── clients/            # Client pages
│   │   └── [clientId]/     # Dynamic client routes
│   │       ├── strategy/   # Strategy page
│   │       └── inboxes/    # Inboxes page
│   └── layout.tsx          # Root layout
├── components/             # React components
│   ├── strategy/           # Strategy-related components
│   ├── purchasing/         # Inbox purchasing components
│   └── ui/                 # shadcn/ui components
├── lib/                    # Utilities
│   ├── api.ts              # API client
│   └── types.ts            # TypeScript types
└── public/                 # Static assets
```

### API Changes (FastAPI)

Location: `D:\Work\charm-email-os\api\`

```
api/
├── main.py                 # FastAPI app entry point
├── routes/                 # API endpoints
│   ├── strategy.py         # /api/strategy/*
│   ├── clients.py          # /api/clients/*
│   ├── domains.py          # /api/domains/*
│   └── inbox_purchasing.py # /api/purchasing/*
├── models/                 # Pydantic models
│   ├── strategy.py         # Strategy models
│   └── client.py           # Client models
├── database.py             # Database connection
└── Dockerfile              # Container definition
```

### Database Changes

Location: `D:\Work\charm-email-os\migrations\`

```bash
# Create new migration
touch migrations/018_your_change.sql

# Apply to local database
psql -h localhost -p 5433 -U postgres -d postgres -f migrations/018_your_change.sql

# Update docker init schema for new local environments
# Edit: docker/init/01-schema.sql
```

### Worker Changes

Location: `D:\Work\charm-email-os\workers\`

```
workers/
├── strategy_worker.py       # Strategy generation daemon
├── domain_generator_worker.py # Domain generation daemon
├── spintax_worker.py        # Spintax processing daemon
└── purchase_worker.py       # Inbox purchasing daemon
```

## Step 4: Test Locally

### Verify Frontend

1. Open http://localhost:3000
2. Navigate to Charm client: http://localhost:3000/clients/4bd07dc0-059a-448b-b6f4-3275d0c104a9
3. Test your changes

### Verify API

1. Open Swagger UI: http://localhost:8000/docs
2. Test relevant endpoints
3. Check database for expected changes

### Verify Database Migrations

```bash
# Connect to local database
psql -h localhost -p 5433 -U postgres -d postgres

# Check tables exist
\dt

# Verify columns
\d+ your_table_name
```

### Run Tests (if applicable)

```bash
# Frontend tests
cd charm-email-os
npm test

# API tests
cd api
pytest
```

## Step 5: Commit and Push

```bash
# Stage changes
git add .

# Review what's staged
git status
git diff --staged

# Commit with descriptive message
git commit -m "feat: Add campaign regeneration to unified view

- Add RegenerationModal component
- Add regeneration endpoint to strategy routes
- Update CampaignSequences to show regenerate button

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Push to remote
git push origin main
```

## Step 6: Production Deployment

### Automatic Deployments

These services auto-deploy on push to `main`:

| Service | Coolify UUID | Trigger |
|---------|--------------|---------|
| charm-api | `ccssgc4gowsog04wck400o0w` | Push to main |
| charm-frontend | `jskswosswg80cg8wwk8g8kww` | Push to main |

### Manual Worker Deployments

Workers do NOT auto-deploy. When worker code changes:

```bash
# Via Coolify MCP (from Claude Code)
# Use the coolify MCP tool to trigger deployment
```

**Worker UUIDs:**

| Worker | UUID |
|--------|------|
| strategy-worker | `qwgc8ws0wwk0wgg4s48ssg0w` |
| domain-worker | `ew8cw0o00ksws8gg4gggws4k` |
| spintax-worker | `roccs4g0gwkcs8ws8k8kgog4` |
| purchase-worker | `xo4o4wcco0scgs8gskggw00k` |
| price-checker | `ewskcsk0s0gw0kgc08kkoccg` |

### Database Migrations (Production)

**CAUTION**: Production migrations affect real data.

```bash
# Connect to production database
psql -h 31.97.142.123 -p 5432 -U <user> -d <database>

# Run migration
\i migrations/018_your_change.sql

# Verify
\dt
```

## Step 7: Verify Production

1. Check Coolify dashboard for deployment status
2. Verify frontend at https://app.laviefatigue.com
3. Verify API at https://api.laviefatigue.com/health
4. Test the specific feature you changed

## Rollback Procedures

### Frontend/API Rollback

```bash
# Revert the commit locally
git revert HEAD

# Push the revert
git push origin main

# Coolify will auto-deploy the reverted version
```

### Database Rollback

Write a reverse migration or restore from backup. Document rollback SQL in your migration file.

### Worker Rollback

Workers are pinned to specific commits. No auto-deploy means you can redeploy the previous working version from Coolify.

## Quick Reference

| Task | Command |
|------|---------|
| Start local stack | `docker compose -f docker-compose.local.yml up -d` |
| Stop local stack | `docker compose -f docker-compose.local.yml down` |
| View logs | `docker compose -f docker-compose.local.yml logs -f` |
| Rebuild containers | `docker compose -f docker-compose.local.yml up -d --build` |
| Reset database | `docker compose -f docker-compose.local.yml down -v` |
| Connect to local DB | `psql -h localhost -p 5433 -U postgres` |

## Related

- [[index]] - Local development hub
- [[file-locations]] - Where everything lives
- [[../infrastructure/coolify]] - Production deployment details
- [[troubleshooting]] - Common issues and solutions
