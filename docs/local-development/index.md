---
title: Local Development Hub
created: 2026-02-10
updated: 2026-02-10
tags: [hub, local, development, docker]
---

# Local Development Hub

This hub documents the complete local development environment for Charm Email OS. Use this as your starting point when working on any feature or fix.

## Quick Start

```bash
# Navigate to project root
cd D:\Work\charm-email-os

# Start all services
docker compose -f docker-compose.local.yml up -d

# Verify services are running
docker ps
```

**Access Points:**
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Database: localhost:5433 (postgres/localdevpassword)

## Development Workflow

**CRITICAL**: All changes start locally, then deploy to production.

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEVELOPMENT WORKFLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. LOCAL DEVELOPMENT                                            │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │  docker-compose.local.yml                               │ │
│     │  - Test changes against local PostgreSQL                │ │
│     │  - Use seed data or connect to production DB for data   │ │
│     │  - Hot reload for frontend/API development              │ │
│     └─────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  2. VERIFY & COMMIT                                              │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │  git add && git commit && git push                      │ │
│     │  - Run tests locally before pushing                     │ │
│     │  - Verify database migrations work                      │ │
│     └─────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  3. PRODUCTION DEPLOYMENT (Coolify)                              │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │  Auto-deploy: charm-api, charm-frontend                 │ │
│     │  Manual deploy: All workers (via Coolify MCP)           │ │
│     │  Dashboard: https://panel.laviefatigue.com              │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

See [[development-workflow]] for detailed workflow instructions.

## Documentation Index

### Core Documentation

| Document | Purpose |
|----------|---------|
| [[architecture]] | System architecture and component relationships |
| [[development-workflow]] | Step-by-step local → production workflow |
| [[file-locations]] | Where all code, configs, and docker files live |
| [[database-reference]] | Schema, tables, seed data, and migrations |
| [[workers]] | AI workers (strategy, domain, spintax, purchase) |

### Guides

| Document | Purpose |
|----------|---------|
| [[frontend-development]] | Hot reload, component development, testing |
| [[api-development]] | FastAPI routes, endpoints, testing |
| [[worker-development]] | Claude Code workers, MCP tools, testing |
| [[database-operations]] | Migrations, queries, troubleshooting |

### Reference

| Document | Purpose |
|----------|---------|
| [[docker-compose-reference]] | All docker-compose files and their purpose |
| [[environment-variables]] | All env vars across local and production |
| [[test-data]] | Seed data, test client IDs, sample data |
| [[troubleshooting]] | Common issues and solutions |

## Key Directories

```
D:\Work\charm-email-os\
├── api/                    # FastAPI backend
│   ├── Dockerfile         # API container
│   ├── main.py            # Entry point
│   ├── routes/            # API endpoints
│   └── models/            # Pydantic models
├── charm-email-os/         # Next.js frontend
│   ├── Dockerfile         # Frontend container
│   ├── app/               # Next.js app router
│   ├── components/        # React components
│   └── lib/               # API clients, utilities
├── docker/                 # Docker initialization
│   └── init/              # Database init scripts
│       ├── 01-schema.sql  # Schema creation
│       └── 02-seed.sql    # Test data
├── migrations/             # Database migrations
├── workers/                # AI worker scripts
├── strategy_mcp/           # Strategy MCP server
├── docs/                   # This documentation
└── docker-compose*.yml     # Various compose configs
```

See [[file-locations]] for complete file reference.

## Test Client: Charm

The local environment uses the Charm client for testing. This ID matches production for consistency:

| Entity | ID |
|--------|-----|
| **Client ID** | `4bd07dc0-059a-448b-b6f4-3275d0c104a9` |
| Workspace ID | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| Onboarding Submission | `550e8400-e29b-41d4-a716-446655440000` |

**Direct URL**: http://localhost:3000/clients/4bd07dc0-059a-448b-b6f4-3275d0c104a9

## Production Reference

| Service | URL | Deployment |
|---------|-----|------------|
| Frontend | https://app.laviefatigue.com | Auto-deploy on push |
| API | https://api.laviefatigue.com | Auto-deploy on push |
| Coolify Dashboard | https://panel.laviefatigue.com | Manual access |
| Database | OwnRBL (31.97.142.123) | Managed |

See [[../infrastructure/coolify]] for production deployment details.

## Related

- [[../index]] - Main documentation hub
- [[../deployment/index]] - Deployment documentation
- [[../architecture/index]] - System architecture
