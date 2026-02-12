---
title: Charm Email OS Documentation
created: 2026-01-22
updated: 2026-02-10
tags: [hub, index]
---

# Charm Email OS

Cold email infrastructure management platform for managing domains, inboxes, and campaigns.

## Getting Started

**Start Here** - If you're a Claude agent or developer new to this codebase:

| Document | Purpose |
|----------|---------|
| [[local-development/index]] | **Local development hub** - Start here! |
| [[local-development/development-workflow]] | Local → production workflow |
| [[local-development/file-locations]] | Where all code and configs live |
| [[local-development/architecture]] | System architecture and components |

### Quick Start

```bash
cd D:\Work\charm-email-os
docker compose -f docker-compose.local.yml up -d
# Frontend: http://localhost:3000
# API: http://localhost:8000
```

## Local Development

- [[local-development/index]] - **Start here** - Complete local dev hub
- [[local-development/development-workflow]] - Local → production workflow
- [[local-development/file-locations]] - Where everything lives
- [[local-development/architecture]] - System architecture
- [[local-development/database-reference]] - Database schema and queries
- [[local-development/workers]] - AI workers (strategy, domain, spintax)
- [[local-development/troubleshooting]] - Common issues and solutions

## Architecture

- [[architecture-overview]] - System design and components
- [[tech-stack]] - Technologies used

## Infrastructure Management

- [[infrastructure-hub]] - Main hub for infrastructure docs
- [[domain-lifecycle]] - Domain status flow and management
- [[inbox-provisioning]] - HyperTide inbox setup process
- [[package-templates]] - Client subscription packages

## Guides

- [[guide-domain-purchase]] - How to purchase domains
- [[guide-inbox-setup]] - Setting up inboxes via HyperTide wizard

## Architecture Decisions

- [[adr-001-domain-status-lifecycle]] - Domain status model
- [[adr-002-legacy-status]] - Handling pre-existing infrastructure
- [[adr-003-wizard-redesign]] - InboxPurchaseWizard UX improvements

## Components

### Frontend (Next.js)
- `app/clients/[clientId]/inboxes/page.tsx` - Infrastructure management page
- `components/purchasing/InboxPurchaseWizard.tsx` - Inbox setup wizard
- `components/purchasing/DomainsNeedingSetupTable.tsx` - Domain selection table
- `components/purchasing/DomainCandidatesTable.tsx` - Domain approval table

### Backend (FastAPI)
- `api/routes/domains.py` - Domain management endpoints
- `api/routes/inbox_purchasing.py` - HyperTide automation integration
- `api/routes/domain_sourcing.py` - Domain generation

### External Services
- [[hypertide]] - Inbox provisioning service
- [[emailbison]] - Email campaign management
- [[ownrbl]] - Domain health monitoring

## Project Status

See [[project-status]] for current phase and progress.
