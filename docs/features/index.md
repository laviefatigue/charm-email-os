---
title: Features
created: 2026-01-16
updated: 2026-02-12
tags: [hub, features]
---

# Features

Feature documentation for Charm Email OS.

## Current Features

- [[domain-generation]] - AI-powered domain name generation
- [[domain-purchasing]] - Registrar integration for domain availability and purchase
- [[ns-verification]] - Nameserver verification and DNS configuration
- [[sender-names]] - Base name seeds with variation generation for inboxes
- [[client-profile]] - Client profile management (Phase 1)
- [[strategy-generation]] - AI strategy generation (Phase 3)
- [[health-monitoring]] - Database-driven inbox/domain health monitoring with kill triggers
- [[oauth-sync]] - OAuth workspace synchronization
- [[hypertide-automation]] - Hypertide inbox provisioning integration

## Implementation Guides

- [[rbl-implementation-guide]] - DNS-based blacklist checking system
  - Production-ready code examples
  - Free self-hosted solution
  - Essential providers: Spamhaus, Barracuda, SpamCop

## System Integration & Compliance

- [[hypertide-health-v3-impact]] - How Hypertide constraints affect Health V3 system
  - 75% compatibility analysis
  - Kill triggers: No changes needed ✅
  - Capacity planning: Formula updates required ⚠️
- [[v3-compliance-gap-analysis]] - Health V3 compliance assessment

## Feature Status

| Feature | Status | Phase |
|---------|--------|-------|
| Domain Generation | Partial | - |
| Domain Purchasing (Porkbun) | **Working** | - |
| Domain Purchasing (Dynadot) | **Working** | - |
| NS Verification | **Working** | 6A |
| Sender Names (Variations) | **Working** | 6A.5 |
| Inbox Setup Wizard | **Working** | 6A |
| Health Monitoring | **Working** | - |
| Kill Trigger System | **Working** | - |
| Differentiated Bounces | **Working** | - |
| Client Profile | Planned | Phase 1 |
| Domain Generation Fix | Planned | Phase 2 |
| Strategy Generation | **Working** | Phase 3 |

## Health & Infrastructure

The health monitoring system includes:

- **Health Score Calculation** - Local calculation (not from EmailBison API)
- **Kill Trigger Detection** - Automated inbox termination thresholds
- **Differentiated Bounce Thresholds** - Different thresholds for spam blocks vs bad addresses
- **24-Hour Kill Queue** - Safety window before deletion

See [[../concepts/kill-triggers]] for detailed kill trigger documentation.

## Related

- [[../concepts/kill-triggers]] - Kill trigger system
- [[../architecture/index]] - System architecture
- [[../database/schema]] - Database schema
