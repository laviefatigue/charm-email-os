---
title: System Architecture
created: 2026-02-10
updated: 2026-02-10
tags: [architecture, components, system]
---

# System Architecture

Charm Email OS is a cold email infrastructure management platform with the following components.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CHARM EMAIL OS                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                           FRONTEND (Next.js)                                 │ │
│  │                                                                              │ │
│  │   /clients           /clients/[id]/strategy     /clients/[id]/inboxes       │ │
│  │   Client List        Strategy Generation        Inbox Management            │ │
│  │                                                                              │ │
│  │   Components:                                                                │ │
│  │   - CampaignSequences     - InboxPurchaseWizard                             │ │
│  │   - UnifiedCycleView      - DomainsNeedingSetupTable                        │ │
│  │   - ComprehensiveOnboarding                                                 │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                           │
│                                      ▼ HTTP                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                            API (FastAPI)                                     │ │
│  │                                                                              │ │
│  │   /api/clients        /api/strategy         /api/purchasing                 │ │
│  │   Client CRUD         Strategy Gen Jobs     Inbox Provisioning              │ │
│  │                                                                              │ │
│  │   /api/domains        /api/onboarding                                       │ │
│  │   Domain Management   Client Onboarding                                     │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                           │
│                                      ▼ SQL                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                         DATABASE (PostgreSQL)                                │ │
│  │                                                                              │ │
│  │   clients              strategies            campaign_cycles                 │ │
│  │   domains              strategy_suggestions  campaign_documents              │ │
│  │   sender_accounts      strategy_generation_jobs                              │ │
│  │   client_onboarding_submissions                                              │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                      ▲                                           │
│                                      │ Poll                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                          AI WORKERS (Claude Code)                            │ │
│  │                                                                              │ │
│  │   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │ │
│  │   │  Strategy   │ │   Domain    │ │   Spintax   │ │  Purchase   │          │ │
│  │   │   Worker    │ │   Worker    │ │   Worker    │ │   Worker    │          │ │
│  │   │             │ │             │ │             │ │             │          │ │
│  │   │ Generates   │ │ Generates   │ │ Processes   │ │ Automates   │          │ │
│  │   │ campaigns   │ │ domains     │ │ spintax     │ │ HyperTide   │          │ │
│  │   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │ │
│  │                          │                                                   │ │
│  │                          ▼ MCP                                               │ │
│  │                   ┌─────────────┐                                           │ │
│  │                   │ Strategy    │                                           │ │
│  │                   │ MCP Server  │                                           │ │
│  │                   │             │                                           │ │
│  │                   │ save_doc,   │                                           │ │
│  │                   │ get_context │                                           │ │
│  │                   └─────────────┘                                           │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼ External
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL SERVICES                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │  HyperTide  │ │ EmailBison  │ │   Porkbun   │ │   Dynadot   │               │
│  │             │ │             │ │             │ │             │               │
│  │ Inbox       │ │ Campaign    │ │ Domain      │ │ Domain      │               │
│  │ Provisioning│ │ Management  │ │ Purchasing  │ │ Purchasing  │               │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### Frontend (Next.js)

**Technology**: Next.js 14+ with App Router, React, TypeScript, Tailwind CSS, shadcn/ui

**Purpose**: User interface for managing clients, viewing strategies, and provisioning inboxes.

**Key Pages**:
| Route | Purpose |
|-------|---------|
| `/` | Dashboard / Client list |
| `/clients/[id]` | Client overview |
| `/clients/[id]/strategy` | Strategy generation and viewing |
| `/clients/[id]/inboxes` | Inbox provisioning |

**Key Components**:
- `CampaignSequences.tsx` - Main strategy view container
- `UnifiedCycleView.tsx` - Displays cycle with 4 campaigns
- `ComprehensiveOnboarding.tsx` - Client onboarding form
- `InboxPurchaseWizard.tsx` - Inbox provisioning wizard

### API (FastAPI)

**Technology**: Python 3.11+, FastAPI, asyncpg, Pydantic

**Purpose**: REST API for all CRUD operations, connects frontend to database.

**Key Routes**:
| Route | Purpose |
|-------|---------|
| `/api/clients` | Client CRUD |
| `/api/strategy` | Strategy generation jobs |
| `/api/domains` | Domain management |
| `/api/purchasing` | Inbox provisioning |
| `/api/onboarding` | Client onboarding submissions |

**Swagger UI**: http://localhost:8000/docs

### Database (PostgreSQL)

**Technology**: PostgreSQL 15

**Purpose**: Persistent storage for all application data.

**Key Tables**:
| Table | Purpose |
|-------|---------|
| `clients` | Client records |
| `client_onboarding_submissions` | Onboarding form data |
| `strategies` | Strategy definitions |
| `strategy_generation_jobs` | AI generation job tracking |
| `strategy_suggestions` | Generated campaign suggestions |
| `campaign_cycles` | 14-day campaign cycles |
| `campaign_documents` | Stablekernel documents with emails |
| `document_email_variants` | Email variants per position |
| `domains` | Domain records |
| `sender_accounts` | Email accounts |

### AI Workers

**Technology**: Python, Claude Code CLI, MCP

**Purpose**: Background daemons that poll for jobs and execute AI-powered tasks.

**Workers**:

| Worker | Purpose | Poll Target |
|--------|---------|-------------|
| **Strategy Worker** | Generate 4-campaign strategies | `strategy_generation_jobs` where status='pending' |
| **Domain Worker** | Generate domain suggestions | `domain_generation_jobs` |
| **Spintax Worker** | Process spintax in emails | `spintax_jobs` |
| **Purchase Worker** | Automate HyperTide purchases | `purchase_jobs` |

**Worker Architecture**:
```
┌─────────────────────────────────────────────────────┐
│                    WORKER DAEMON                     │
├─────────────────────────────────────────────────────┤
│                                                      │
│   1. Poll database for pending jobs                 │
│                  │                                   │
│                  ▼                                   │
│   2. Claim job (set status = 'processing')          │
│                  │                                   │
│                  ▼                                   │
│   3. Launch Claude Code with MCP server             │
│      ┌────────────────────────────────────┐         │
│      │ claude -p "Generate strategy..."  │          │
│      │        --mcp strategy_mcp         │          │
│      └────────────────────────────────────┘         │
│                  │                                   │
│                  ▼                                   │
│   4. Claude uses MCP tools to:                      │
│      - Read context (get_client_context)            │
│      - Save output (save_campaign_document)         │
│                  │                                   │
│                  ▼                                   │
│   5. Update job status (completed/failed)           │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Strategy MCP Server

**Technology**: FastMCP, Python

**Purpose**: Provides tools for Claude Code to interact with the database during strategy generation.

**Tools**:
| Tool | Purpose |
|------|---------|
| `get_client_context` | Retrieve client and onboarding data |
| `get_job_context` | Get generation job details |
| `save_campaign_document` | Save generated stablekernel document |
| `update_job_status` | Mark job complete/failed |

## Data Flow: Strategy Generation

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Frontend │────▶│   API    │────▶│ Database │◀────│  Worker  │────▶│ Claude   │
│          │     │          │     │          │     │          │     │ Code     │
└──────────┘     └──────────┘     └──────────┘     └──────────┘     └──────────┘
     │                │                │                │                │
     │ 1. Click       │                │                │                │
     │ "Generate"     │                │                │                │
     │───────────────▶│                │                │                │
     │                │ 2. POST        │                │                │
     │                │ /api/strategy/ │                │                │
     │                │ generate       │                │                │
     │                │───────────────▶│                │                │
     │                │                │ 3. INSERT job  │                │
     │                │                │ status=pending │                │
     │                │                │◀───────────────│                │
     │                │                │                │ 4. Poll finds  │
     │                │                │                │ pending job    │
     │                │                │                │───────────────▶│
     │                │                │                │                │ 5. Generate
     │                │                │                │                │ via skill
     │                │                │ 6. MCP tools   │                │
     │                │                │ save documents │◀───────────────│
     │                │                │◀───────────────│                │
     │                │                │                │ 7. Update      │
     │                │                │ 8. job status  │ job complete   │
     │                │                │ = completed    │◀───────────────│
     │ 9. Frontend    │                │                │                │
     │ polls/receives │◀───────────────│                │                │
     │ result         │                │                │                │
     │◀───────────────│                │                │                │
```

## Local vs Production

| Aspect | Local | Production |
|--------|-------|------------|
| **Frontend** | Docker or `npm run dev` | Coolify (auto-deploy) |
| **API** | Docker or `uvicorn` | Coolify (auto-deploy) |
| **Database** | Local PostgreSQL (:5433) | OwnRBL (31.97.142.123) |
| **Workers** | Optional (uncomment in compose) | Always running (Coolify) |
| **Data** | Seed data | Real client data |
| **URL** | localhost:3000 | app.laviefatigue.com |

## Related

- [[file-locations]] - Where code lives
- [[development-workflow]] - Development process
- [[workers]] - Worker documentation
- [[../database/schema]] - Database schema details
