---
title: File Locations Reference
created: 2026-02-10
updated: 2026-02-10
tags: [reference, files, structure]
---

# File Locations Reference

Complete reference for where all code, configuration, and documentation lives in Charm Email OS.

## Project Root

```
D:\Work\charm-email-os\
```

## Directory Structure

```
D:\Work\charm-email-os\
│
├── 📁 api/                          # FastAPI Backend
│   ├── Dockerfile                   # API container definition
│   ├── main.py                      # FastAPI app entry point
│   ├── database.py                  # Database connection & utilities
│   ├── requirements.txt             # Python dependencies
│   ├── 📁 routes/                   # API endpoints
│   │   ├── clients.py               # /api/clients/*
│   │   ├── strategy.py              # /api/strategy/*
│   │   ├── domains.py               # /api/domains/*
│   │   ├── domain_sourcing.py       # /api/domain-sourcing/*
│   │   ├── inbox_purchasing.py      # /api/purchasing/*
│   │   └── onboarding.py            # /api/onboarding/*
│   └── 📁 models/                   # Pydantic data models
│       ├── strategy.py              # Strategy-related models
│       ├── client.py                # Client models
│       └── domain.py                # Domain models
│
├── 📁 charm-email-os/               # Next.js Frontend
│   ├── Dockerfile                   # Frontend container definition
│   ├── package.json                 # Node dependencies
│   ├── next.config.ts               # Next.js configuration
│   ├── tailwind.config.ts           # Tailwind CSS config
│   ├── 📁 app/                      # Next.js App Router
│   │   ├── layout.tsx               # Root layout
│   │   ├── page.tsx                 # Home page
│   │   └── 📁 clients/              # Client pages
│   │       └── 📁 [clientId]/       # Dynamic client routes
│   │           ├── page.tsx         # Client overview
│   │           ├── 📁 strategy/     # Strategy page
│   │           │   └── page.tsx     # /clients/[id]/strategy
│   │           └── 📁 inboxes/      # Inboxes page
│   │               └── page.tsx     # /clients/[id]/inboxes
│   ├── 📁 components/               # React Components
│   │   ├── 📁 strategy/             # Strategy components
│   │   │   ├── CampaignSequences.tsx
│   │   │   ├── UnifiedCycleView.tsx
│   │   │   ├── CycleNavigator.tsx
│   │   │   ├── CampaignDocumentView.tsx
│   │   │   └── ComprehensiveOnboarding.tsx
│   │   ├── 📁 purchasing/           # Inbox purchasing
│   │   │   ├── InboxPurchaseWizard.tsx
│   │   │   └── DomainsNeedingSetupTable.tsx
│   │   └── 📁 ui/                   # shadcn/ui components
│   │       ├── button.tsx
│   │       ├── card.tsx
│   │       └── ...
│   ├── 📁 lib/                      # Utilities
│   │   ├── api.ts                   # API client functions
│   │   ├── types.ts                 # TypeScript types
│   │   └── utils.ts                 # Helper functions
│   └── 📁 public/                   # Static assets
│
├── 📁 workers/                      # AI Worker Scripts
│   ├── strategy_worker.py           # Strategy generation daemon
│   ├── domain_generator_worker.py   # Domain generation daemon
│   ├── spintax_worker.py            # Spintax processing daemon
│   └── purchase_worker.py           # Inbox purchasing daemon
│
├── 📁 strategy_mcp/                 # Strategy MCP Server
│   ├── server.py                    # MCP server implementation
│   └── requirements.txt             # Python dependencies
│
├── 📁 docker/                       # Docker Initialization
│   └── 📁 init/                     # Database init scripts
│       ├── 01-schema.sql            # Schema creation
│       └── 02-seed.sql              # Test data seeding
│
├── 📁 migrations/                   # Database Migrations
│   ├── 001_initial.sql
│   ├── 002_domains.sql
│   ├── ...
│   ├── 013_batch_campaign_generation.sql
│   └── 017_unified_cycle_schema.sql
│
├── 📁 docs/                         # Documentation (Foam)
│   ├── index.md                     # Main documentation hub
│   ├── 📁 local-development/        # Local dev docs (this section)
│   ├── 📁 architecture/             # System architecture
│   ├── 📁 deployment/               # Deployment guides
│   ├── 📁 infrastructure/           # Infrastructure docs
│   ├── 📁 features/                 # Feature documentation
│   └── 📁 database/                 # Database documentation
│
├── 📁 .claude/                      # Claude Code Configuration
│   └── 📁 skills/                   # Custom skills
│       └── generate-strategy.md     # Strategy generation skill
│
├── 📁 scripts/                      # Utility Scripts
│   ├── test_strategy_generation.py  # Local testing script
│   └── validate_output.py           # Output validation
│
├── 📁 test-output/                  # Local Test Output
│   └── 📁 jobs/                     # Generated test jobs
│
├── 📁 Hypertide/                    # Hypertide Integration
│   ├── CLAUDE.md                    # Hypertide-specific instructions
│   └── 📁 automation/               # Prefect flows
│
│── docker-compose.local.yml         # Local development stack
├── docker-compose.yml               # Production reference
├── docker-compose.strategy-worker.yml
├── docker-compose.domain-worker.yml
├── docker-compose.spintax-worker.yml
├── Dockerfile.strategy-worker
├── Dockerfile.domain-worker
├── Dockerfile.spintax-worker
├── Dockerfile.purchase-worker
├── .env.local                       # Local environment template
└── CLAUDE.md                        # Project-wide Claude instructions
```

## Key Files by Purpose

### Docker Configuration

| File | Purpose |
|------|---------|
| `docker-compose.local.yml` | **Main local development stack** |
| `docker-compose.yml` | Production reference (Coolify uses this) |
| `docker-compose.strategy-worker.yml` | Strategy worker standalone |
| `docker-compose.domain-worker.yml` | Domain worker standalone |
| `docker-compose.spintax-worker.yml` | Spintax worker standalone |
| `api/Dockerfile` | FastAPI container |
| `charm-email-os/Dockerfile` | Next.js container |
| `Dockerfile.strategy-worker` | Strategy worker container |
| `Dockerfile.domain-worker` | Domain worker container |
| `Dockerfile.spintax-worker` | Spintax worker container |
| `Dockerfile.purchase-worker` | Purchase worker container |

### Database

| File | Purpose |
|------|---------|
| `docker/init/01-schema.sql` | Complete schema for local DB |
| `docker/init/02-seed.sql` | Test data for local development |
| `migrations/*.sql` | Individual migration files |
| `api/database.py` | Database connection code |

### API Endpoints

| File | Endpoints |
|------|-----------|
| `api/routes/strategy.py` | `/api/strategy/*` |
| `api/routes/clients.py` | `/api/clients/*` |
| `api/routes/domains.py` | `/api/domains/*` |
| `api/routes/domain_sourcing.py` | `/api/domain-sourcing/*` |
| `api/routes/inbox_purchasing.py` | `/api/purchasing/*` |
| `api/routes/onboarding.py` | `/api/onboarding/*` |

### Frontend Pages

| File | URL Route |
|------|-----------|
| `charm-email-os/app/page.tsx` | `/` |
| `charm-email-os/app/clients/[clientId]/page.tsx` | `/clients/[id]` |
| `charm-email-os/app/clients/[clientId]/strategy/page.tsx` | `/clients/[id]/strategy` |
| `charm-email-os/app/clients/[clientId]/inboxes/page.tsx` | `/clients/[id]/inboxes` |

### Key Components

| Component | File |
|-----------|------|
| Strategy page content | `components/strategy/CampaignSequences.tsx` |
| Unified cycle view | `components/strategy/UnifiedCycleView.tsx` |
| Cycle navigator | `components/strategy/CycleNavigator.tsx` |
| Campaign document | `components/strategy/CampaignDocumentView.tsx` |
| Onboarding form | `components/strategy/ComprehensiveOnboarding.tsx` |
| Inbox wizard | `components/purchasing/InboxPurchaseWizard.tsx` |

### AI Workers

| Worker | Main File | Dockerfile |
|--------|-----------|------------|
| Strategy | `workers/strategy_worker.py` | `Dockerfile.strategy-worker` |
| Domain | `workers/domain_generator_worker.py` | `Dockerfile.domain-worker` |
| Spintax | `workers/spintax_worker.py` | `Dockerfile.spintax-worker` |
| Purchase | `workers/purchase_worker.py` | `Dockerfile.purchase-worker` |

### MCP Servers

| Server | Directory |
|--------|-----------|
| Strategy MCP | `strategy_mcp/` |

### Claude Code Configuration

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project-wide instructions |
| `.claude/skills/generate-strategy.md` | Strategy generation skill |
| `Hypertide/CLAUDE.md` | Hypertide-specific instructions |

## Production Equivalents

| Local File | Production Location |
|------------|---------------------|
| `docker-compose.local.yml` | Coolify container configs |
| `docker/init/01-schema.sql` | OwnRBL database (31.97.142.123) |
| `docker/init/02-seed.sql` | Production has real data |
| `.env.local` | Coolify environment variables |

## Related

- [[index]] - Local development hub
- [[development-workflow]] - Development workflow
- [[architecture]] - System architecture
