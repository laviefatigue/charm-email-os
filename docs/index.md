---
title: Charm Email OS Documentation
created: 2026-01-22
updated: 2026-01-22
tags: [hub, index]
---

# Charm Email OS

Cold email infrastructure management platform for managing domains, inboxes, and campaigns.

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
