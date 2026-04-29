---
title: Inbox Provisioning
created: 2026-01-22
updated: 2026-04-28
tags: [concept, inbox, infrastructure, hypertide, slack]
---

# Inbox Provisioning

The process of creating email inboxes on purchased domains via HyperTide automation.

> **2026-04-27 OVERHAUL — provider mix changed.** Per CEO directive, all NEW orders are Google Workspace (3 inboxes/domain). Microsoft Entra is legacy ride-to-death — no new Entra orders. The provisioning flow described below still applies to both, but the queue should only see Google going forward. See [[package-templates]] for the post-overhaul package model (`50k_google`, `100k_google`).

## Overview

After domains are purchased, they need inboxes (email accounts) created. This is done through HyperTide, which:
1. Uses browser automation (Playwright) to interact with email provider UIs
2. Creates Microsoft Entra or Google Workspace accounts (Google only for new orders)
3. Uploads inboxes to EmailBison for campaign management

## Slack-First Workflow (Current)

Orders are now sent to Slack for **manual processing** by the HyperTide team, rather than automated browser automation. This provides better reliability and human oversight.

### Flow

1. User selects domains in "Setup Inboxes" table
2. User clicks "Setup Inboxes" button → opens `InboxProvisionModal`
3. User confirms order → API creates job with `manual_processing` status
4. Slack notification sent to `#hypertide-orders` channel
5. HyperTide team processes order manually
6. User clicks "Mark Complete" in Jobs tab when done

### Slack Message Format

The Slack message includes:

| Field | Example |
|-------|---------|
| Company | `Charm` |
| Forwarding | `growthwithcharm.com` |
| EmailBison Workspace | `Charm` (workspace name, not ID) |
| Provider | `Microsoft Entra` or `Google Workspace` |
| Domain List | `outboundwithcharm.com, growthwithcharm.com` |
| Orders | `1 order (2 domains, 100 inboxes)` |

**Google Orders**: Include additional instruction:
> Get Bison App ID: Visit https://spellcast.hirecharm.com/sender-email-connect and switch workspace to `Charm`

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

The modal (`components/purchasing/InboxProvisionModal.tsx`) handles the purchase confirmation. It sends orders to Slack for manual HyperTide processing.

**Preview Phase** — shows before confirmation:

| Field | Source |
|-------|--------|
| Provider | Selectable (Entra or Google) |
| Domains | Count of selected domains |
| Orders | Calculated from `ceil(domains / domains_per_order)` |
| Total Inboxes | `orders × inboxes_per_order` |
| Monthly Cost | `orders × $50` |
| Forwarding Domain | Client's forwarding domain |

**Custom Purchase Toggle**:
- **OFF (default)**: Validates against subscription package limits
- **ON**: Bypasses subscription limits, only validates HyperTide minimums (2 domains for Entra, 5 for Google)

**After "Send to Slack"**:
- Creates job with `manual_processing` status
- Sends Slack notification to `#hypertide-orders`
- Modal closes immediately with success toast
- Order tracked in Jobs tab

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
| Status | `pending`, `processing`, `executing`, `awaiting_checkout`, `completed`, `failed`, `cancelled`, `manual_processing` |
| Provider | `entra`, `google`, `mixed`, or `unknown` |
| Domains | Count of domains in the job |
| Inboxes | Total inboxes created (with email icon for completed) |
| Created | Job creation timestamp |
| Duration | Time from start to completion |
| Actions | Context-dependent buttons |

### Job Statuses

| Status | Description | Badge Color |
|--------|-------------|-------------|
| `manual_processing` | Sent to Slack, awaiting HyperTide | Purple |
| `pending` | Queued for automated processing | Gray |
| `executing` | Active automation running | Blue |
| `awaiting_checkout` | Needs manual payment | Amber |
| `completed` | Successfully finished | Green |
| `failed` | Error occurred | Red |
| `cancelled` | User cancelled | Gray |

### Actions by Status

**manual_processing**:
- **Copy** (clipboard icon) — Copy order details to clipboard
- **Delete** (red trash icon) — Cancel job and unlock domains
- **Mark Complete** (green checkmark) — Mark as manually completed

**failed / pending**:
- **Delete** (red trash icon) — Cancel job and unlock domains
- **Retry** (refresh icon) — Reset to pending status

**awaiting_checkout**:
- **Open Checkout** (credit card) — Open Stripe payment URL
- **Confirm** (green checkmark) — Confirm payment completed
- **Delete** (red trash icon) — Cancel and unlock domains

### Delete/Cancel Button

- Appears on `failed`, `pending`, and `manual_processing` jobs
- Calls `DELETE /api/inbox-purchasing/jobs/{job_id}`
- Releases domain locks (`purchase_job_id` set to NULL)
- Cannot cancel `executing` jobs (active HyperTide automation)

### Mark Complete Button

- Appears on `manual_processing` and `failed` jobs
- Opens confirmation dialog requiring checkbox acknowledgment
- Updates job status to `completed`
- Updates all associated domains to `active` status with appropriate infrastructure type

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| Lock conflict (409) | Domain already locked to another job | Cancel the existing job in Jobs tab first |
| NS not verified | Nameservers not pointing to Cloudflare | Run NS verification, wait for propagation |
| Slack notification failed | Webhook URL not configured | Check `SLACK_ORDERS_WEBHOOK_URL` in `.env.local` |
| Login failed | Hypertide credentials expired or changed | Update `HYPERTIDE_EMAIL`/`HYPERTIDE_PASSWORD` ENV in Coolify |
| Workspace not found | Bison workspace name mismatch | Verify `bison_workspace_name` in job matches EmailBison |

### Frontend Error Display

The `InboxProvisionModal` handles structured API errors:

```typescript
// Extracts detail.error and detail.locked_domains from API responses
if (errObj.detail && typeof errObj.detail === 'object') {
  const detail = errObj.detail;
  if (detail.error) message = detail.error;
  if (detail.locked_domains) {
    message += `: ${detail.locked_domains.map(d => d.domain_name).join(', ')}`;
  }
}
```

This ensures error messages like "Some domains are locked by existing purchase jobs: domain1.com, domain2.com" are displayed instead of `[object Object]`.

## Related

- [[infrastructure-hub]] - Parent hub
- [[domain-lifecycle]] - Domain status flow
- [[package-templates]] - Starter/Growth packages
- [[hypertide]] - Automation service details
- [[../architecture/purchase-worker]] - Purchase worker architecture (Playwright automation)
- [[../deployment/purchase-worker-coolify]] - Coolify deployment guide
- [[adr-003-wizard-redesign]] - Recent UX improvements
