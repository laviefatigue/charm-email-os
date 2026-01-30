---
title: Inbox Provisioning
created: 2026-01-22
updated: 2026-01-30
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

## Domain Locking

When a purchase job is created, selected domains are **locked** to prevent concurrent job conflicts:

- `purchase_job_id` → set to the job's UUID
- `purchase_job_status` → set to `pending`

### Lock Lifecycle

```
Domain selected for job → purchase_job_id = job_id, purchase_job_status = 'pending'
                       ↓
        Job completes/fails/is cancelled
                       ↓
        Domain unlocked → purchase_job_id = NULL, purchase_job_status = NULL
```

### UI Indicators

Locked domains show:
- **Amber "Queued" badge** in the Setup Inboxes table
- **Disabled checkboxes** (cannot be selected for another job)
- **Summary text** showing count of locked domains

### Lock Conflict Detection

The smart-order endpoint checks for lock conflicts before creating a job. If any requested domain is already locked to another active job, the request is rejected with a 409 Conflict response.

## API Endpoints

### Calculate Orders
```
POST /api/inbox-purchasing/calculate
```
Returns order breakdown based on inbox targets.

### Generate Names
```
POST /api/inbox-purchasing/generate-names
```
Returns random first/last name combinations.

### Execute Purchase (Smart Order)
```
POST /api/inbox-purchasing/smart-order
```
Creates a purchase job with optimal order calculation. Locks selected domains.

### Check Status
```
GET /api/inbox-purchasing/jobs/{job_id}
```
Returns job progress and results.

### List Jobs
```
GET /api/inbox-purchasing/jobs
```
Returns job history with filtering by `client_id` and `status`.

### Retry Failed Job
```
POST /api/inbox-purchasing/jobs/{job_id}/retry
```
Retries a failed job by resetting its status to `pending`.

### Cancel Job
```
DELETE /api/inbox-purchasing/jobs/{job_id}
```
Cancels a pending or failed job and releases domain locks. Cannot cancel jobs with status `executing` (active HyperTide automation).

## Post-Provisioning

After successful provisioning:
1. Domain status updated from `purchased` → `active`
2. Inbox records created in `sender_accounts` table
3. Inboxes uploaded to EmailBison workspace
4. Domains appear in Current Inventory tab

## Job Management (Jobs Tab)

The **Jobs tab** (`PurchaseJobsTable.tsx`) displays purchase job history with:

| Column | Description |
|--------|-------------|
| Status | `pending`, `processing`, `executing`, `completed`, `failed`, `cancelled` |
| Provider | `entra`, `google`, `mixed`, or `unknown` |
| Domains | Count of domains in the job |
| Inboxes | Total inboxes created (with email icon for completed) |
| Created | Job creation timestamp |
| Duration | Time from start to completion |
| Actions | Cancel (trash icon) and Retry (refresh icon) buttons |

### Cancel Button

- Appears on `failed` and `pending` jobs (red trash icon)
- Calls `DELETE /api/inbox-purchasing/jobs/{job_id}`
- Releases domain locks (`purchase_job_id` and `purchase_job_status` set to NULL)
- Cannot cancel `executing` jobs (active HyperTide automation)

### Retry Button

- Appears on `failed` jobs (refresh icon)
- Calls `POST /api/inbox-purchasing/jobs/{job_id}/retry`
- Resets job status to `pending` for the worker to pick up again

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| HyperTide not available | Module import failed | Check Hypertide/automation installation |
| Browser access required | No display for Playwright | Run in headless mode or configure display |
| Payment failed | Stripe issue | Check saved payment method |
| Domain DNS not ready | Nameservers not propagated | Wait 24-48 hours, retry |
| Lock conflict (409) | Domain already locked to another job | Cancel the existing job first |

## Related

- [[infrastructure-hub]] - Parent hub
- [[domain-lifecycle]] - Domain status flow
- [[package-templates]] - Starter/Growth packages
- [[hypertide]] - Automation service details
- [[adr-003-wizard-redesign]] - Recent UX improvements
