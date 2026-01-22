---
title: Inbox Provisioning
created: 2026-01-22
updated: 2026-01-22
tags: [concept, inbox, infrastructure, hypertide]
---

# Inbox Provisioning

The process of creating email inboxes on purchased domains via HyperTide automation.

## Overview

After domains are purchased, they need inboxes (email accounts) created. This is done through HyperTide, which:
1. Uses browser automation (Playwright) to interact with email provider UIs
2. Creates Microsoft Entra or Google Workspace accounts
3. Uploads inboxes to EmailBison for campaign management

## Provider Specifications

### Microsoft Entra

| Metric | Value |
|--------|-------|
| Inboxes per domain | 52 |
| Domains per order | 2 |
| Inboxes per order | 104 |
| Cost per order | $50/month |

### Google Workspace

| Metric | Value |
|--------|-------|
| Inboxes per domain | 3 |
| Domains per order | 5 |
| Inboxes per order | 15 |
| Cost per order | $50/month |

## InboxPurchaseWizard

The frontend wizard (`components/purchasing/InboxPurchaseWizard.tsx`) guides users through inbox setup.

### Wizard Steps

1. **Domains** - Select purchased domains to provision
   - Pre-selects domains from DomainsNeedingSetupTable
   - Choose provider: Entra (recommended), Google, or Mixed
   - Real-time order preview with costs

2. **Names** - Configure inbox account names
   - Load from onboarding personas (if available)
   - Generate random names
   - Add custom names manually
   - Format: `first.last@domain.com`

3. **Review** - Confirm configuration
   - Shows domains, orders, inboxes, cost
   - Provider breakdown

4. **Execute** - Run HyperTide automation
   - Progress tracking
   - Order-by-order completion
   - Error handling

### Key Props

```typescript
interface InboxPurchaseWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clientId: string;
  clientName: string;
  forwardingDomain: string;
  domains: Domain[];              // Purchased domains available
  selectedDomainIds?: string[];   // Pre-selected from setup table
  onboardingData?: OnboardingData;
  onComplete?: (totalInboxes: number) => void;
}
```

## Provider Selection Logic

```typescript
// Entra-only: all domains use Entra
if (providerType === 'entra') {
  entraDomains = domainCount;
}

// Google-only: all domains use Google
else if (providerType === 'google') {
  googleDomains = domainCount;
}

// Mixed: 70% Entra, 30% Google
else {
  entraDomains = Math.floor(domainCount * 0.7);
  googleDomains = domainCount - entraDomains;
}
```

## Order Calculation

Orders are calculated to use complete HyperTide packages:

```typescript
// Entra: ceil(domains / 2) orders
const entraOrders = Math.ceil(entraDomains / ENTRA_DOMAINS_PER_ORDER);

// Google: ceil(domains / 5) orders
const googleOrders = Math.ceil(googleDomains / GOOGLE_DOMAINS_PER_ORDER);

// May need additional domains to fill orders
const extraDomainsNeeded =
  (entraOrders * 2 + googleOrders * 5) - selectedDomainCount;
```

## API Endpoints

### Calculate Orders
```
POST /api/v1/inbox-purchasing/calculate
```
Returns order breakdown based on inbox targets.

### Generate Names
```
POST /api/v1/inbox-purchasing/generate-names
```
Returns random first/last name combinations.

### Execute Purchase
```
POST /api/v1/inbox-purchasing/execute
```
Starts HyperTide automation job.

### Check Status
```
GET /api/v1/inbox-purchasing/status/{job_id}
```
Returns job progress and results.

## Post-Provisioning

After successful provisioning:
1. Domain status updated from `purchased` → `active`
2. Inbox records created in `sender_accounts` table
3. Inboxes uploaded to EmailBison workspace
4. Domains appear in Current Inventory tab

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| HyperTide not available | Module import failed | Check Hypertide/automation installation |
| Browser access required | No display for Playwright | Run in headless mode or configure display |
| Payment failed | Stripe issue | Check saved payment method |
| Domain DNS not ready | Nameservers not propagated | Wait 24-48 hours, retry |

## Related

- [[infrastructure-hub]] - Parent hub
- [[domain-lifecycle]] - Domain status flow
- [[package-templates]] - Starter/Growth packages
- [[hypertide]] - Automation service details
- [[adr-003-wizard-redesign]] - Recent UX improvements
