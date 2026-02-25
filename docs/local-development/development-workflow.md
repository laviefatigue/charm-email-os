---
title: Development Workflow
created: 2026-02-10
updated: 2026-02-11
tags: [workflow, development, localhost]
---

# Development Workflow

This document describes the complete workflow for making changes to Charm Email OS.

> **Localhost-First**: All development and testing happens locally via Docker. Coolify/VPS deployments are deprecated.

## Principle: Everything Local

**All development, testing, and running happens on localhost.**

This ensures:
1. Full control over the environment
2. Database migrations are validated locally
3. Integration points are verified
4. No dependency on external infrastructure

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

## Step 6: Restart Services

After making changes, rebuild and restart:

```bash
# Rebuild containers with latest code
docker compose -f docker-compose.local.yml up -d --build

# View logs to verify
docker compose -f docker-compose.local.yml logs -f
```

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
- [[docker-compose-reference]] - Docker compose configuration
- [[troubleshooting]] - Common issues and solutions
