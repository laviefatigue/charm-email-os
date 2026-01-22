---
title: Infrastructure Management Hub
created: 2026-01-22
updated: 2026-01-22
tags: [hub, infrastructure]
---

# Infrastructure Management

Central hub for cold email infrastructure documentation.

## Overview

The infrastructure system manages the complete lifecycle of email sending infrastructure:
1. **Domain Generation** - AI-powered domain name suggestions
2. **Domain Purchasing** - Dual-provider (Porkbun/Dynadot) purchase flow
3. **Inbox Provisioning** - HyperTide automation for inbox creation
4. **Health Monitoring** - OwnRBL blacklist checks and EmailBison metrics
5. **Capacity Planning** - Subscription packages and spare management

## Core Concepts

- [[domain-lifecycle]] - Status transitions from generation to active
- [[inbox-provisioning]] - HyperTide integration and automation
- [[package-templates]] - Starter/Growth package definitions
- [[provider-selection]] - Entra vs Google inbox providers

## Data Model

### Domain Status Flow
```
pending → approved → purchased → provisioning → active
                ↓
            rejected
```

### Key Entities
- **Domain** - `domains` table in OwnRBL
- **Inbox** - `sender_accounts` table in OwnRBL
- **Client** - `clients` table with `workspace_id` link

## UI Components

### Current Inventory Tab
Shows domains with active inboxes:
- Status: `active`, `legacy`, `warming`, `flagged`, `dead`
- Domain tree view with expandable inbox lists
- Health indicators per inbox

### Purchase New Tab
Shows domain pipeline:
- **Domain Candidates** - Pending approval, pricing, purchase actions
- **Domains Ready for Setup** - Purchased, awaiting inbox provisioning
- **Pipeline Summary** - Counts by status

## Key Files

| Component | File |
|-----------|------|
| Inboxes Page | `app/clients/[clientId]/inboxes/page.tsx` |
| Purchase Wizard | `components/purchasing/InboxPurchaseWizard.tsx` |
| Domain Candidates | `components/purchasing/DomainCandidatesTable.tsx` |
| Setup Table | `components/purchasing/DomainsNeedingSetupTable.tsx` |
| Domain Tree | `components/inboxes/DomainInboxTree.tsx` |

## Related

- [[project-status]] - Current implementation phase
- [[adr-003-wizard-redesign]] - Recent wizard improvements
- [[hypertide]] - Inbox provisioning service
