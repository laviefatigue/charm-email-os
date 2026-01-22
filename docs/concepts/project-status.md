---
title: Project Status
created: 2026-01-22
updated: 2026-01-22
tags: [status, project]
---

# Project Status

Current implementation progress for Charm Email OS infrastructure management.

## Completed Phases

### Phase 1-3: Domain Generation & Purchasing
- AI-powered domain name generation
- Dual-provider pricing (Porkbun/Dynadot)
- Domain purchase workflow with approval gates

### Phase 4: Data Backfill
- Migrated 303 domains to `purchased` status
- Aligned existing data with new workflow

### Phase 5: Dynadot Integration
- Fixed Dynadot balance/API issues
- Successfully purchased `growthwithcharm.com`

### Phase 6A: Post-Purchase Inbox Setup UI
**Completed 2026-01-22**

| File | Change |
|------|--------|
| `lib/types.ts` | Added `provisioning`, `legacy` statuses, `OnboardingPersona` |
| `app/clients/[clientId]/inboxes/page.tsx` | Tab filtering, "Domains Ready for Setup" section, 5-column pipeline |
| `components/purchasing/DomainsNeedingSetupTable.tsx` | NEW - Domain selection with checkboxes |
| `components/purchasing/InboxPurchaseWizard.tsx` | Complete redesign for usability |
| `components/ui/radio-group.tsx` | NEW - Radix UI radio group component |
| `api/routes/inbox_purchasing.py` | Updates domain status to `active` after provisioning |
| `api/routes/domains.py` | Migration endpoint for legacy domains |
| `api/models/domain.py` | Added all status values to Pydantic model |

**Key Changes in 6A:**
- Wizard redesigned to be domain-centric (not abstract inbox counts)
- Provider selection: Entra, Google, or Mixed
- Real-time order preview with costs
- Pre-selection from DomainsNeedingSetupTable
- Legacy status for pre-existing infrastructure

## Pending Phases

### Phase 6B: Subscription Management
**Status: Planned**

- Client subscription records with quotas
- Usage tracking vs. quota
- Upgrade/modify flows
- Package template database

See [[package-templates]] for planned schema.

### Phase 6C: Health Monitoring
**Status: Planned**

- Prefect flow for daily health checks
- EmailBison MCP integration
- Alert system for problem inboxes
- Alert UI with actionable info

### Phase 6D: Capacity Planning
**Status: Planned**

- Capacity dashboard showing inventory breakdown
- Replacement queue with approval workflow
- Spare capacity tracking
- Auto-replacement pipeline

## Current Focus

**Wizard Usability Improvements** - Just deployed (2026-01-22)

The InboxPurchaseWizard was redesigned to:
1. Start with domain selection instead of abstract counts
2. Show provider options with clear specifications
3. Calculate orders automatically from selected domains
4. Display real-time cost and inbox projections

## Next Steps

1. Test wizard with actual HyperTide provisioning
2. Implement Phase 6B (subscription management) or
3. Implement Phase 6C (health monitoring)

User should decide which phase to prioritize.

## Deployment Info

| Component | Location |
|-----------|----------|
| Frontend | Coolify `charm-frontend` |
| API | Coolify `charm-api` |
| Source | `laviefatigue/charm-email-os` |
| Branch | `master` |

Latest deployment: 2026-01-22 (wizard redesign)

## Related

- [[infrastructure-hub]] - Infrastructure documentation
- [[domain-lifecycle]] - Status flow
- [[inbox-provisioning]] - Wizard details
- [[adr-003-wizard-redesign]] - Design decisions
