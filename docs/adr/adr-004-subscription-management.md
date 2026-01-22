---
title: "ADR-004: Subscription Management System"
created: 2026-01-22
updated: 2026-01-22
tags: [adr, status/accepted, infrastructure, subscription]
status: accepted
---

# ADR-004: Subscription Management System

## Status

Accepted (2026-01-22)

## Context

The infrastructure system needed a way to track client packages and quotas:

1. **No Quota Visibility** - Couldn't determine if a client was within their package limits
2. **Manual Tracking** - Package sizes tracked in spreadsheets, not in the system
3. **No Change History** - No audit trail for subscription upgrades/downgrades
4. **Wizard Disconnect** - InboxPurchaseWizard couldn't reference client quotas

## Decision

Implement a subscription management system with:

### Database Schema

1. **package_templates** - Pre-defined packages (Starter, Growth)
   - Entra/Google order counts and specifications
   - Auto-computed total domains/inboxes

2. **client_subscriptions** - Client's active subscription
   - Links to package template (optional for custom configs)
   - Override capability for all settings
   - Spare capacity configuration

3. **subscription_changes** - Audit trail
   - Change type (created, upgrade, downgrade, modify, cancelled)
   - Previous/new values
   - Reason and changed_by tracking

### Package Templates

Based on actual HyperTide specifications:

| Package | Entra Orders | Google Orders | Total Domains | Total Inboxes |
|---------|--------------|---------------|---------------|---------------|
| Starter | 6 | 5 | 37 | 699 |
| Growth | 12 | 10 | 74 | 1,398 |

### API Endpoints

- `GET /subscriptions/templates` - List available packages
- `GET /subscriptions/client/{id}` - Get subscription with usage stats
- `POST /subscriptions/client/{id}` - Create subscription
- `PUT /subscriptions/client/{id}` - Update subscription
- `POST /subscriptions/client/{id}/apply-template` - Apply a template
- `GET /subscriptions/client/{id}/history` - Change history

### Frontend Components

1. **SubscriptionCard** - Display subscription with:
   - Domain/inbox quotas with progress bars
   - Provider breakdown (Entra vs Google)
   - Current inventory status
   - Spare capacity indicator

2. **SubscriptionEditModal** - Create/edit subscriptions:
   - Template selection
   - Custom configuration option
   - Spare ratio slider
   - Live preview of totals

## Consequences

### Positive

- **Quota Visibility** - Clear view of usage vs. limits
- **Package Standardization** - Templates ensure consistent offerings
- **Audit Trail** - Full history of subscription changes
- **Wizard Integration** - Wizard can check quotas before provisioning
- **Spare Capacity** - Configurable buffer for replacements

### Negative

- **Migration Needed** - Existing clients need subscriptions created
- **Extra Tables** - Three new tables in database

### Neutral

- **Backfill Endpoint** - `/subscriptions/backfill/starter-package` creates Starter for all clients
- **Flexible Override** - Can use templates or fully custom configurations

## Related

- [[package-templates]] - Package definitions
- [[inbox-provisioning]] - Wizard documentation
- [[adr-003-wizard-redesign]] - Wizard redesign
- [[project-status]] - Phase completion tracking
