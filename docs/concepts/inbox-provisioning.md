---
title: Inbox Provisioning
created: 2026-01-22
updated: 2026-02-04
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
| Inboxes per domain | 50 |
| Domains per order | 2 |
| Inboxes per order | 100 |
| Cost per order | $50/month |

### Google Workspace

| Metric | Value |
|--------|-------|
| Inboxes per domain | 3 |
| Domains per order | 5 |
| Inboxes per order | 15 |
| Cost per order | $50/month |

## Frontend Purchase Flow

### Domain Selection (Setup Inboxes Table)

The **Setup Inboxes** table (`DomainsNeedingSetupTable`) shows purchased domains ready for provisioning:

- Domains must be **30+ days old** before provisioning (age validation)
- Young domains show remaining days with amber badge
- **Admin override**: Clicking a young domain's checkbox opens a "Domain Age Warning" dialog allowing force-selection
- Force-selected domains show amber checkboxes instead of green
- Locked domains (already in an active job) show "Queued" badge and disabled checkboxes

### InboxProvisionModal

The modal (`components/purchasing/InboxProvisionModal.tsx`) handles the purchase confirmation and progress tracking. It replaced the earlier multi-step wizard with a streamlined single-confirmation flow.

**Preview Phase** — shows before confirmation:

| Field | Source |
|-------|--------|
| Provider | Auto-detected from domain configuration (Entra or Google) |
| Domains | Count of selected domains |
| Orders | Calculated from `ceil(domains / domains_per_order)` |
| Total Inboxes | `orders × inboxes_per_order` |
| Monthly Cost | `orders × $50` |
| Sender Name | Auto-configured from onboarding data |
| Prefixes | Generated from name list |
| Forwarding Domain | Client's forwarding domain |

**Progress Phase** — shows after "Confirm Purchase":

- Polls `GET /api/inbox-purchasing/status/{job_id}` every 3 seconds
- Shows progress bar with `orders_completed / orders_total`
- Displays `current_step` from the worker

**Checkout Handoff** — on `awaiting_checkout` status:

- Shows "Payment Required" amber card
- Displays "Open Stripe Checkout" button linking to captured `checkout_url`
- User completes payment manually on Stripe
- After payment, calls `POST /api/inbox-purchasing/confirm-checkout` to finalize

**Terminal States:**

- `completed` → Success toast, domains marked active
- `failed` → Error display with retry option

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

## Checkout and Post-Provisioning

### Checkout Flow

The purchase worker automates everything up to payment, then hands off to the user:

1. Worker reaches Stripe checkout → captures URL → sets `awaiting_checkout`
2. Frontend shows "Payment Required" card with Stripe link
3. User completes payment on Stripe
4. User clicks "Confirm & Finalize" in the modal
5. API calls `POST /api/inbox-purchasing/confirm-checkout` → sets `completed`

### After Completion

1. Domain status updated from `purchased` → `active`
2. Inbox records created in `sender_accounts` table
3. Inboxes uploaded to EmailBison workspace
4. Domains appear in Current Inventory tab
5. Domain locks released (`purchase_job_id` → NULL)

## Job Management (Jobs Tab)

The **Jobs tab** (`PurchaseJobsTable.tsx`) displays purchase job history with:

| Column | Description |
|--------|-------------|
| Status | `pending`, `processing`, `executing`, `awaiting_checkout`, `completed`, `failed`, `cancelled` |
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
| Login failed | Hypertide credentials expired or changed | Update `HYPERTIDE_EMAIL`/`HYPERTIDE_PASSWORD` ENV in Coolify |
| Workspace not found | Bison workspace name mismatch | Verify `bison_workspace_name` in job matches EmailBison |
| Browser crash | Chromium OOM or Xvfb issue | Restart worker container, check `shm_size` |
| Job timeout | Automation exceeded `JOB_TIMEOUT` | Check Hypertide UI changes, review step screenshots |
| Domain DNS not ready | Nameservers not propagated | Wait 24-48 hours, retry |
| Lock conflict (409) | Domain already locked to another job | Cancel the existing job first |

## Related

- [[infrastructure-hub]] - Parent hub
- [[domain-lifecycle]] - Domain status flow
- [[package-templates]] - Starter/Growth packages
- [[hypertide]] - Automation service details
- [[../architecture/purchase-worker]] - Purchase worker architecture (Playwright automation)
- [[../deployment/purchase-worker-coolify]] - Coolify deployment guide
- [[adr-003-wizard-redesign]] - Recent UX improvements
