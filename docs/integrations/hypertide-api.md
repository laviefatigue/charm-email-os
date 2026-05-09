---
title: Hypertide Standalone API Reference
created: 2026-05-06
updated: 2026-05-06
source: Vendor guide "Hypertide Standalone API — Complete Reference Guide" v1.0 + empirical observations 2026-05-06
status: canonical
tags: [integration, hypertide, api, reference, vendor]
---

# Hypertide Standalone API Reference

> **Canonical source of truth** for the documented API surface. Everything we previously inferred from the Postman collection at [hypertide_api/Hypertide API.postman_collection.json](../../hypertide_api/Hypertide%20API.postman_collection.json) and from prior memory snapshots is **superseded** — fields, endpoints, and shapes here win in any conflict.
>
> **Empirical findings** (live data observations 2026-05-06 that contradict or extend the vendor guide) are captured in [Empirical observations](#empirical-observations) below. The vendor guide is sole source for *intent*; live behavior wins for *what to actually expect from the API*.
>
> Related:
> - **Service architecture & roadmap**: [[hypertide-service]] — bounded responsibilities, phased plan, schema design
> - Pipeline architecture: [[domain-purchase-pipeline]]
> - Operations: [[domain-pipeline-runbook]]
> - **Reconciliation runbook** (Phase 1 deliverable): [[hypertide-reconciliation]] — workflow for HT ↔ DB drift audits and cleanup
> - Warmup playbook (separate doc, not API): [hypertide_api/Hypertide Latest and Greatest Recommendation.md](../../hypertide_api/Hypertide%20Latest%20and%20Greatest%20Recommendation.md)

## Conventions

- **Production base URL:** `https://backend.hypertide.io/api/v1` (verified 2026-05-06 via `/health`). The public marketing/app domains (`hypertide.io`, `app.hypertide.io`, `app2.hypertide.io`) all serve the SPA and do **not** route to the API — `/api/v1/*` on those hostnames returns the SPA's `index.html` with `Content-Type: text/html`, which is misleading. Always use `backend.hypertide.io`.
- **Env convention:** `HYPERTIDE_API_URL` (set in Coolify per-worker; not currently a default in code — `api/services/hypertide_client.py` ships with `localhost:5000` as DEFAULT_BASE_URL, dev only). The async client at `hypertide_api/client.py` already hardcodes the correct production URL.
- **Auth:** `x-api-key: <key>` header on every endpoint *except* `/health`. Header name is lowercase per the vendor guide; case-insensitive in practice.
- **Every response includes a `requestId`** (e.g. `req_1712345678_abc123xyz`) — log it on every call for support.
- **Per-API-key permissions.** A key only works for endpoints whose permission it carries (see [Permissions](#permissions)). Missing permission ⇒ HTTP 403 `PERMISSION_DENIED`.
- **Per-API-key rate limits.** See [Rate Limits](#rate-limits). Exceeded ⇒ HTTP 429 with `retryAfter` in seconds.

## Auth errors

| HTTP | Code | When |
|---|---|---|
| 401 | `API_KEY_REQUIRED` | No key sent |
| 401 | `INVALID_API_KEY` | Key not found / inactive |
| 403 | `PERMISSION_DENIED` | Key valid but lacks required permission for endpoint |

## Dry run mode

Any endpoint accepts dry run via header `x-dry-run: true` *or* query param `?dryRun=true`.

Dry run **validates** required fields, domain count/format, user count, tool credential structure, warmup/sending settings format. Dry run **skips** external API calls (Smartlead/Instantly verification, registrar availability checks), DB writes, payments.

Response: `{ success: true, message: "...", requestId: "..." }`.

## Permissions

| Endpoint | Permission |
|---|---|
| `POST /orders` | `orders:create` |
| `GET /orders/active` | `orders:read` |
| `GET /orders/pending` | `orders:read` |
| `POST /orders/reupload` | `orders:update` |
| `POST /payments/charge` | `payments:charge` |
| `POST /subscriptions/cancel` | `subscriptions:cancel` |
| `POST /subscriptions/verify-revert` | `subscriptions:cancel` |
| `POST /subscriptions/revert-cancellation` | `subscriptions:cancel` |
| `POST /domains/update-forwarding` | `domains:update` |
| `POST /users/update-username` | `users:update` |
| `POST /domains/generate-user-credentials-csv` | `domains:read` |
| `GET /domains/:domain/dns-records` | `domains:read` |
| `POST /domains/:domain/dns-records` | `domains:update` |
| `PUT /domains/:domain/dns-records/:id` | `domains:update` |
| `DELETE /domains/:domain/dns-records/:id` | `domains:update` |

For our **read-only reconciliation use case**, the minimum is `orders:read`. Add `subscriptions:cancel` only if you want to call `verify-revert` (which is itself read-only, despite the permission name).

## Rate limits

Per-API-key, per-minute:

| Endpoint | Limit |
|---|---|
| `POST /orders` | 30/min |
| `GET /orders/active` | 60/min |
| `GET /orders/pending` | 60/min |
| `POST /orders/reupload` | 30/min |
| `POST /payments/charge` | 20/min |
| `POST /subscriptions/*` | 20–30/min |
| `POST /domains/*` | 30/min |
| `GET /domains/*` | 60/min |
| `POST /users/update-username` | 30/min |

429 response: `{ "error": "Too many requests", "retryAfter": <seconds> }`.

## Common response shape

Success:
```json
{ "success": true, "message": "...", "requestId": "req_...", ...payload }
```

Error:
```json
{ "success": false, "error": "ERROR_CODE", "message": "...", "details": { ... }, "requestId": "req_..." }
```

---

# Endpoints

## Health Check

`GET /api/v1/health` — no auth.

Response 200:
```json
{ "success": true, "message": "Standalone API is running", "version": "1.0.0", "timestamp": "..." }
```

## Create Order

`POST /api/v1/orders` — auth `orders:create`.

Creates a new email infrastructure order.
- `entra` plan: 2 Azure/Microsoft 365 domains per call, 52 mailboxes/domain split across users.
- `google` plan: 5 Google Workspace domains per call, 3 mailboxes/domain (1 user replicated).

### Required fields

| Field | Values |
|---|---|
| `plan` | `entra` \| `google` |
| `domain_option` | `purchase_domain_for_me` \| `i_have_my_own_domains` |
| `domains[]` | entra: exactly 2; google: exactly 5; no case-insensitive duplicates |
| `forwarding_domain` | non-empty |
| `client_name` | non-empty |
| `selected_tool` | `smartlead` \| `instantly` \| `bison` \| `plusvibe` \| `other` |
| `users[]` | google: exactly 1; entra: 1+ but ≤ 52; each `{first_name, last_name}` |

### Domain rules

**`i_have_my_own_domains`:**
- Max 35 chars per domain.
- No hyphens in the name part (`my-domain.com` is invalid).
- Letters, numbers, dots only.

**`purchase_domain_for_me`:**
- TLDs: `.com`, `.net`, `.org`, `.info`, `.biz` only.
- Live availability + pricing check via registrar API.

### `tool_credentials` (conditional — required unless `selected_tool == "other"`)

**Smartlead:**
```json
{
  "api_key": "sl_api_...",
  "username": "you@email.com",
  "password": "yourpassword",
  "oauth_link": "https://login.microsoftonline.com/..."
}
```
- `oauth_link` REQUIRED for `entra`, NOT for `google`. Must start with `https://login.microsoftonline.com`.
- Live-verified against Smartlead API before order creation.

**Instantly:**
```json
{
  "username": "you@email.com",
  "password": "yourpassword",
  "api_key": "inst_api_...",
  "workspace": "workspace-name",
  "workspace_id": "ws_123"
}
```
- `workspace_id` optional; `workspace` (name) required and **not auto-fetched**.
- Live-verified.

**Bison:**
```json
{
  "api_key": "bison_key",
  "username": "you@email.com",
  "password": "yourpassword",
  "bison_url": "https://...",
  "workspace": "workspace-name",
  "app_id": "123456789012-abc.apps.googleusercontent.com"
}
```
- `bison_url`: HTTPS only, no localhost/private IPs.
- `app_id`: required only for `google` plan; must be Google OAuth client ID format.
- **Not** live-verified; format validated + sanitized.

**Plusvibe:**
```json
{
  "api_key": "pv_key",
  "username": "you@email.com",
  "password": "yourpassword",
  "workspace": "workspace-name"
}
```
- Not live-verified; format validated + sanitized.

**Other:** `tool_credentials` not required (ignored if sent).

### Optional fields

- `profile_picture_link` — google plan only; URL, applied to all 3 Google accounts.

**`warmup_setup`:**
```json
{
  "disabled": false,
  "settings": { ...tool-specific... },
  "tags": ["tag1", "tag2"]
}
```
- Smartlead: `max_warmup_emails_per_day`, `ramp_up_value`, `warmup_reply_rate`, `warmup_tag_identifier`.
- Instantly: `warmup_limit`, `warmup_reply_rate`, `warmup_increment`.
- Bison: `warmup_limit` only.
- Plusvibe: `warmup_limit`, `warmup_reply_rate`, `warmup_increment`.

**`sending_settings`:**
- Smartlead: `time_to_wait_in_minutes`, `max_email_per_day`.
- Instantly: `daily_limit`, `sending_gap` (minutes).
- Bison: `daily_limit` only.
- Plusvibe: `daily_limit` only.

### Inbox distribution

Entra (52 inboxes): split evenly across `users[]`. 1 user → 52, 2 → 26 each, 4 → 13 each, 13 → 4 each. Cannot exceed 52 users.

Google (3 inboxes): exactly 1 user, gets all 3 accounts.

### Success (200)
```json
{
  "success": true,
  "message": "Orders submitted successfully.",
  "data": {
    "orderCount": 2,
    "orders": [
      { "id": "recXXXXXXXXXXXXXX", "domain": "example1.com" },
      { "id": "recYYYYYYYYYYYYYY", "domain": "example2.com" }
    ],
    "nameservers": {
      "message": "Please update your domain nameservers to the following:",
      "ns": [
        "ns1.dnsimple.com",
        "ns2.dnsimple-edge.net",
        "ns3.dnsimple.com",
        "ns4.dnsimple-edge.org"
      ]
    }
  },
  "requestId": "req_..."
}
```
`nameservers` is returned **only** for `i_have_my_own_domains`.

### Errors

- 400 `VALIDATION_FAILED` — `details` is an array of `{field, reason}`.
- 400 `DOMAINS_ALREADY_PAID` — `details.paidDomains[]`, `details.suggestion`.
- 400 `ENTRA_LIMIT_EXCEEDED` — invited users limited to 5 Entra orders.

## Get Active Orders

`GET /api/v1/orders/active` — auth `orders:read`. No body.

Returns all PAID orders for your account.

```json
{
  "success": true,
  "count": 5,
  "orders": [
    {
      "id": "recXXXXXXXXXXXXXX",
      "domain": "example.com",
      "status": "Done",
      "paymentStatus": "Paid",
      "subscriptionId": "sub_1234567890",
      "forwardingDomain": "forward.example.com",
      "sendingTool": "Smartlead.ai",
      "organizationName": "Acme Corp",
      "productId": "prod_XXXXXXXXXX",
      "createdAt": "2024-01-01"
    }
  ],
  "requestId": "req_..."
}
```

Field meanings:
- `id` — Airtable record ID, used in reupload / charge / cancel / username APIs. Stored as `domain_pipeline_items.hypertide_record_id` in our DB.
- `subscriptionId` — Stripe subscription ID, used in cancel/revert APIs. Stored as `domain_pipeline_queue.hypertide_subscription_id`.
- `productId` — Stripe product ID, used in partial cancellation.
- `status` — current processing state (e.g. `Done`, `In progress`, `Todo`).

## Get Pending Orders

`GET /api/v1/orders/pending` — auth `orders:read`. No body.

Returns all UNPAID orders for your account.

```json
{
  "success": true,
  "count": 3,
  "orders": [
    {
      "id": "recXXXXXXXXXXXXXX",
      "domain": "example.com",
      "status": "Todo",
      "paymentStatus": "Unpaid",
      "forwardingDomain": "...",
      "sendingTool": "Smartlead.ai",
      "organizationName": "Acme Corp",
      "createdAt": "2024-01-01"
    }
  ],
  "requestId": "req_..."
}
```

Use after `POST /orders` to retrieve the IDs to feed into `POST /payments/charge`.

## Reupload Order

`POST /api/v1/orders/reupload` — auth `orders:update`.

Re-triggers setup for completed orders (status must be `Done`).

```json
{ "recordIds": ["recXXX", "recYYY"] }
```

Validation: each record must exist, belong to your account, and have `status == "Done"`.

Response groups results into `success[]` / `failed[]`. Per-record failure codes:
- `INVALID_RECORD_ID`
- `UNAUTHORIZED_RECORD`
- `ORDER_NOT_COMPLETED`
- `PROCESSING_ERROR`

If **all** fail: HTTP 400 `REUPLOAD_FAILED`.

## Update Forwarding

`POST /api/v1/domains/update-forwarding` — auth `domains:update`.

```json
{
  "domains": ["example1.com", "example2.com"],
  "forwardingDomain": "newforward.com",
  "forwardingEmail": "user@newforward.com"
}
```
Provide `forwardingDomain` OR `forwardingEmail`, not both.

**Behavior by status:**
- Order in progress (not `Done`) → update is queued, applied when order completes.
- Order `Done` → applied immediately at the registrar.

Response splits by status:
```json
{
  "success": true,
  "queued": { "count": 1, "domains": ["example1.com"] },
  "updated": { "count": 2, "domains": ["example2.com", "example3.com"] },
  "failed": { "count": 0, "domains": [] }
}
```

Errors: 404 `DOMAINS_NOT_FOUND`, 403 `UNAUTHORIZED`.

## Update Username

`POST /api/v1/users/update-username` — auth `users:update`.

```json
{
  "domains": ["example1.com"],
  "users": [
    { "first_name": "Jane", "last_name": "Smith", "signature": "Jane Smith, Head of Growth" }
  ]
}
```

`signature` optional. Entra: 1+ users, redistributed across 52 inboxes/domain. Google: exactly 1 user.

Triggers the full pipeline: detects mailboxes to delete (old vs new names), queues new usernames, sets order status to `In progress`.

Response includes:
- `mailboxesToDelete.csv` — `OldEmail,NewEmail\nold1@...\n...`
- `usernamesToCreate` — map of old → new email.

## Generate User Credentials CSV

`POST /api/v1/domains/generate-user-credentials-csv` — auth `domains:read`.

```json
{ "domains": ["example1.com", "example2.com"] }
```

Response is `text/csv` with `Content-Disposition: attachment; filename=user-credentials.csv`.

Possible headers (depends on credential format):
- `Domain,Name,Email,Password`
- `Domain,First Name,Last Name,Email,Password`

Errors: 400 invalid input, 404 no credentials found, 500 generation failed.

## DNS Records

### List

`GET /api/v1/domains/:domain/dns-records` — auth `domains:read`.

```json
{
  "success": true,
  "records": [
    { "id": "12345", "type": "A", "name": "example.com", "content": "192.168.1.1", "ttl": 3600 }
  ]
}
```

### Add

`POST /api/v1/domains/:domain/dns-records` — auth `domains:update`.

```json
{ "type": "A|TXT|CNAME", "content": "...", "hostname": "mail", "ttl": 3600 }
```

**Restrictions:**
- Only `A`, `TXT`, `CNAME`. Others → 400 `INVALID_RECORD_TYPE`.
- DKIM records are **protected**: any record with `._domainkey`, `dkim`, `selector1`, or `selector2` in its hostname → 400 `DKIM_RECORD_PROTECTED`.

201 success: `{ success, message, record: {...} }`.

### Update

`PUT /api/v1/domains/:domain/dns-records/:recordId` — auth `domains:update`.

```json
{ "type": "...", "content": "...", "ttl": 3600 }
```
All fields optional. Same DKIM protection.

### Delete

`DELETE /api/v1/domains/:domain/dns-records/:recordId?type=A&hostname=mail` — auth `domains:update`.

Query params optional but recommended — `type` validates the record type, `hostname` lets DKIM protection block the call before deletion.

## Subscriptions — Cancel

`POST /api/v1/subscriptions/cancel` — auth `subscriptions:cancel`.

Two modes:

**Mode 1 — by product IDs:**
```json
{
  "subscriptionId": "sub_1234567890",
  "productIds": ["prod_abc", "prod_def"]
}
```
Get `productIds` from `GET /orders/active` (`productId` field).

**Mode 2 — partial product cancellation by domain records:**
```json
{
  "subscriptionId": "sub_1234567890",
  "isPartialProductCancellation": true,
  "domainRecordIds": ["recXXX"]
}
```
Get `domainRecordIds` from `GET /orders/active` (`id` field).

Errors: 400 missing fields; 403 unauthorized subscription.

## Subscriptions — Verify Revert (read-only)

`POST /api/v1/subscriptions/verify-revert` — auth `subscriptions:cancel`.

Read-only — checks if a *scheduled* cancellation is still revertible.

Body (one of):
```json
{ "subscriptionId": "sub_1234567890" }
```
or
```json
{ "recordIds": ["recXXX"] }
```

Response:
```json
{
  "success": true,
  "canRevert": true,
  "summary": { "total": 2, "revertible": 2, "nonRevertible": 0 },
  "records": [
    {
      "recordId": "recXXX",
      "domain": "example.com",
      "currentStatus": "cancelling",
      "revertible": true,
      "reason": "Cancellation is scheduled but not yet executed",
      "cancellationType": "full_subscription"
    }
  ]
}
```

**Revertible (still scheduled):**
- `cancelling` / `Cancelling`
- `to_be_cancelled_complete_subscription`
- `to_be_cancelled_date:<ISO>`
- `partial_product_cancellation_date:<ISO>`

**Non-revertible (already executed):**
- `cancelled` / `Cancelled`
- `product_cancelled_at_<date>`
- `partial_product_cancelled_at_<date>`

`cancellationType` values: `full_subscription`, `partial`, `partial_product`, `cancelled`, `executed`, `none`, `unknown`.

## Subscriptions — Revert Cancellation

`POST /api/v1/subscriptions/revert-cancellation` — auth `subscriptions:cancel`.

Reverts a scheduled (not yet executed) cancellation. **Always call `verify-revert` first.**

Body (one of):
```json
{ "subscriptionId": "sub_..." }
```
or
```json
{ "recordIds": ["recXXX"] }
```

Response groups into `succeeded[]` / `failed[]` / `skipped[]` (skipped = non-revertible, not an error). For full-subscription reverts, also includes `stripeResults`.

400 nothing to revert · 404 no records found.

## Charge Card

`POST /api/v1/payments/charge` — auth `payments:charge`.

Charges the saved Stripe payment method for unpaid records. Customer email is auto-detected from records.

```json
{
  "recordIds": ["recXXX", "recYYY"],
  "couponCode": "DISCOUNT20",
  "description": "Monthly order charge"
}
```

Auto-derived (don't send): customer email, order type (Azure/Google from user count), purchase-vs-BYOD.

Errors: `MISSING_RECORD_IDS`, `NO_RECORDS_FOUND`, `MISSING_EMAIL`, `INVALID_COUPON`, `RECORDS_ALREADY_PAID` (with `details.alreadyPaidRecords[]`), `NO_UNPAID_RECORDS`, 403 `UNAUTHORIZED_RECORDS`.

---

# Error code master list

| Code | HTTP | Meaning |
|---|---|---|
| `API_KEY_REQUIRED` | 401 | No key sent |
| `INVALID_API_KEY` | 401 | Key not found / inactive |
| `PERMISSION_DENIED` | 403 | Key lacks permission |
| `VALIDATION_FAILED` | 400 | Input errors (see `details[]`) |
| `DOMAINS_ALREADY_PAID` | 400 | Domain already has paid order |
| `ENTRA_LIMIT_EXCEEDED` | 400 | Invited users capped at 5 Entra orders |
| `INVALID_RECORD_ID` | 400 | Record not found |
| `UNAUTHORIZED_RECORD` | 403 | Record belongs to another account |
| `UNAUTHORIZED_RECORDS` | 403 | Records belong to another account |
| `ORDER_NOT_COMPLETED` | 400 | Reupload requires status = Done |
| `REUPLOAD_FAILED` | 400 | All reupload records failed |
| `DOMAINS_NOT_FOUND` | 404 | No matching domains |
| `MISSING_RECORD_IDS` | 400 | recordIds missing/empty |
| `NO_RECORDS_FOUND` | 400 | No records matched |
| `MISSING_EMAIL` | 400 | Client email not on records |
| `INVALID_COUPON` | 400 | Stripe coupon invalid/expired |
| `RECORDS_ALREADY_PAID` | 400 | Already paid |
| `NO_UNPAID_RECORDS` | 400 | None unpaid |
| `INVALID_RECORD_TYPE` | 400 | DNS type not A/TXT/CNAME |
| `DKIM_RECORD_PROTECTED` | 400 | DKIM cannot be modified via API |
| `ORDER_CREATION_FAILED` | 500 | Internal order creation error |

---

# Empirical observations

These are live-data findings (732 records pulled 2026-05-06) that **contradict or extend** the vendor guide. The vendor guide is sole source for documented intent; these are the contracts the API actually keeps.

## Undocumented enum values

The vendor guide §8 lists `paymentStatus ∈ {Paid, Unpaid}`. **Live data shows three additional values:**

| paymentStatus | meaning (inferred) | observed count of 732 |
|---|---|---:|
| `Paid` | Stripe USD billing (Microsoft Entra plan) | 221 |
| `Google` | Google Workspace billing channel | 449 |
| `Google-Solo` | Google Solo (3-inbox) plan, billed separately | 62 |
| `Unpaid` | as documented (orders awaiting charge) | 0 in `/active`, expected in `/pending` |

The vendor guide also lists `status ∈ {Done, In progress, Todo}`. **Live data adds:**

| status | meaning (inferred) | observed count |
|---|---|---:|
| `Done` | provisioned, active | 377 |
| `Todo` | order placed, not yet provisioned | 10 |
| `In progress` | provisioning underway | 5 |
| `NPC` | **undocumented** — "Non-Paying Customer". Records for cancelled subscriptions where Hypertide retains the row but the Stripe linkage may be removed. | 340 |

Cross-tab `(status, paymentStatus, cancellationType)` evidence on NPC records: **315/340 (93%) of NPC records have `cancellationType ∈ {cancelled, executed}`** — confirming NPC is the post-cancellation state. The remaining 22 NPC records have `cancellationType=unknown` with `currentStatus=active` (drift between Hypertide and Stripe — flagged for vendor follow-up).

## `/orders/active` returns more than "PAID" orders

The vendor guide §8 says "Returns all PAID orders belonging to your account." In practice the endpoint also returns:
- All `NPC` records (cancelled but retained for history)
- Records with `paymentStatus=Google`/`Google-Solo` (not the documented `Paid`)
- Records with `status=Todo` and `In progress` (not yet provisioned, but already paid for)

**To filter to "currently being billed":** use `verify-revert` per subscription and exclude records where `cancellationType IN ('cancelled', 'executed')`. The `/orders/active` list alone is **not** a "currently billing" filter.

## `verify-revert` returns extra fields not documented

The vendor guide shows `verify-revert` records with `recordId, domain, currentStatus, revertible, reason, cancellationType`. Live responses also include:

- `subscriptionId` — same value passed in
- `toBeCancelled` (boolean) — true if a cancellation is scheduled
- `clientEmail` — email of the customer of record (e.g. `chris@hirecharm.com`)

`clientEmail` is useful for joining HT records back to our `clients` table when domain-name match fails.

## Cancellation state signals — full catalog

This is the most operationally important section. The vendor guide §19 lists `cancellationType` enums and `currentStatus` formats, but it scatters them and doesn't map to the platform UI. Here's the consolidated picture.

### "Queued for cancellation" — three independent fields, all observable in `verify-revert`

| field | type | what it tells you | observed values |
|---|---|---|---|
| `toBeCancelled` | boolean | **Simplest "is queued?" filter.** Set to `true` when HT has accepted the cancel request and scheduled it. Maps directly to the platform UI's orange "To Be Cancelled" status pill. | `true`, `false` |
| `cancellationType` | enum | Categorizes the cancel scope. Non-terminal (queued) types: `full_subscription`, `partial`, `partial_product`, `cancelling`. Terminal (already executed): `cancelled`, `executed`. Other: `none`, `unknown`. | see distribution below |
| `currentStatus` | string | Most informative when populated. Some values carry an ISO timestamp embedded in the string. | see catalog below |
| `revertible` | boolean | `true` when the cancellation can still be reverted via `POST /subscriptions/revert-cancellation`. Becomes `false` once executed. | — |
| `reason` | string | Human-readable explanation, e.g. `"Full subscription cancellation is scheduled and can be reverted"`. | — |

### `currentStatus` — observed and documented patterns

**Observed in our 732-record fleet (2026-05-06):**

| pattern | example | meaning |
|---|---|---|
| `""` (empty) | — | no cancellation in flight; `cancellationType=none` |
| `to_be_cancelled_complete_subscription` | (no date) | full-sub cancel scheduled — **no execution timestamp** |
| `partial_product_cancellation_date:<ISO>` | `partial_product_cancellation_date:2026-05-05T18:13:15.000Z` | partial cancel scheduled with execution timestamp |
| `cancelled` | — | already cancelled in Stripe |
| `active` | — | Stripe active (drift case — appears with `cancellationType=unknown`) |
| `partial_product_cancelled_at_<date>` | `partial_product_cancelled_at_2025-12-23` | partial cancel already executed |

**Documented in vendor guide §19 but UNOBSERVED in our data:**

| pattern | meaning | implication |
|---|---|---|
| `cancelling` / `Cancelling` | actively being processed (between request and scheduled) | Either too transient to catch, or HT uses a different internal state name |
| `to_be_cancelled_date:<ISO>` | full-sub cancel scheduled with execution date | All our full-sub cancels use the dateless `to_be_cancelled_complete_subscription` form |
| `product_cancelled_at_<date>` | full product cancel already executed | We've only seen the `partial_product_cancelled_at_*` form |

### Platform UI ↔ API mapping (verified via screenshot 2026-05-06)

| platform status pill | API state |
|---|---|
| `Done` | `status: "Done"`, `toBeCancelled: false`, `cancellationType: "none"` |
| `In progress` | `status: "In progress"` |
| `Todo` | `status: "Todo"` |
| `To Be Cancelled` (orange pill) | `toBeCancelled: true` (regardless of underlying `status`) |
| `Cancelled` | `cancellationType: "cancelled"`, `currentStatus: "cancelled"` |

The platform UI uses `toBeCancelled` as a display *overlay* on top of the underlying `status` field — a record can show `status="Done"` in the API while the UI shows "To Be Cancelled" because the boolean flag is set. That's why a naive read of `/orders/active` `status` field misses ~30 cancellations in our fleet.

### "When was this cancellation scheduled?" — **NOT exposed**

Neither the API nor the platform UI tells you when a cancellation was *requested*. The platform's "Order Date" column is the original order placement, not the cancel timestamp. For full-sub cancels (`to_be_cancelled_complete_subscription`), `currentStatus` carries no timestamp at all. Partial-product cancels embed a timestamp in `currentStatus`, but that's the **execution** time, not the request time.

**Operational consequence:** if you cancel domains via UI/API today, you cannot subsequently distinguish "scheduled today" from "scheduled last week" by reading state. You need to track request time on your side (e.g. `sync_audit_log` on cancel-batch-apply) or compare snapshots over time.

### Anomaly: 3 records with `full_subscription` + `toBeCancelled=false`

Out of 18 records with `cancellationType=full_subscription`, **15 have `toBeCancelled=true` and 3 have `toBeCancelled=false`** despite identical `currentStatus="to_be_cancelled_complete_subscription"`. Same scheduled state, contradictory boolean. Worth flagging to the vendor; possibly a state-machine inconsistency where the flag wasn't toggled when the cancel was scheduled, or a leftover from a past-revert cycle.

### Practical filters

```
"is currently being billed by HT, regardless of cancel state"
  → cancellationType NOT IN ('cancelled', 'executed')
    (includes scheduled cancels — they're still billed until execution date)

"has a cancel queued that hasn't executed yet"
  → toBeCancelled = true                              -- simplest
  → OR cancellationType IN ('full_subscription','partial','partial_product','cancelling')
    (catches the 3 anomalous records the boolean missed)

"already terminally cancelled"
  → cancellationType IN ('cancelled', 'executed')
  → AND toBeCancelled = false
```

## Records-vs-subscription cardinality

In our 732-record sample, **202 unique `subscriptionId` values** ⇒ avg ~3.6 records per subscription. Distribution observed: 2-record subs (Microsoft 51-inbox plan, 2 domains × 1 sub) and 5-record subs (Google 3-inbox plan, 5 domains × 1 sub).

**This makes the choice of cancel mode (full-sub vs partial-product) load-bearing:** if you want to cancel one domain in a multi-domain sub, you must use `isPartialProductCancellation: true` with `domainRecordIds[]`. A naive full-sub cancel would orphan adjacent healthy domains.

## "Past / cancelled orders" lookup is not a list endpoint

There is no documented `/orders/cancelled` or `/orders/history` endpoint. Once a record's `cancellationType=cancelled` with `currentStatus=cancelled`, it stays in `/orders/active` indefinitely (we have records dating back ~1 year still appearing).

For "what did we cancel last quarter" queries, use `verify-revert` against known recordIds (we keep these in our DB); there's no way to enumerate cancellations vendor-side.

## Marketing-domain catch-all is a footgun

`hypertide.io` (and `app.hypertide.io`, `app2.hypertide.io`, `api.hypertide.io`) all 301-redirect or serve the SPA's `index.html` for `/api/v1/*` paths with **HTTP 200** and `Content-Type: text/html`. A naive curl returns 200 OK and looks like a working API. The actual API host is `backend.hypertide.io` — verify response is `application/json` with `success: true` before trusting any 200.

---

# Mapping to our database

Hypertide records can be mapped to two places in our schema:

**Domain-purchase pipeline tables** (migration 092 — currently empty in production):

| Hypertide field | `domain_pipeline_items` / `domain_pipeline_queue` column |
|---|---|
| `orders[].id` (rec*) | `domain_pipeline_items.hypertide_record_id` |
| `orders[].domain` | `domain_pipeline_items.domain_name` |
| `orders[].status` | `domain_pipeline_items.hypertide_status` |
| `orders[].paymentStatus` | `domain_pipeline_items.hypertide_payment_status` |
| `orders[].subscriptionId` (sub_*) | `domain_pipeline_queue.hypertide_subscription_id` |
| `orders[].productId` (prod_*) | not currently stored |

**Live `domains` table — the actual operational join target.** The pipeline tables are scoped to in-flight purchase orders; ongoing domains live in `public.domains`. **The only available join key is `domains.domain_name`** — there are no `hypertide_*` columns on `domains` today (a future migration is queued to add them; see [[hypertide-reconciliation]]).

| Hypertide field | `domains` column (current state) |
|---|---|
| `orders[].domain` | `domains.domain_name` (case-insensitive join) |
| `orders[].id` | not stored — must be re-fetched per reconcile |
| `orders[].subscriptionId` | not stored |
| `orders[].cancellationType` (from verify-revert) | not stored — must be re-computed per reconcile |

## Reconciliation strategy (read-only)

1. `GET /orders/active` + `GET /orders/pending` → full Hypertide truth.
2. `POST /subscriptions/verify-revert` per `subscriptionId` to enrich each record with `cancellationType` (the only reliable "is HT still billing right now" signal).
3. Join HT records to `domains` on `domain_name` (lowercased).
4. Per-domain decision matrix in [[hypertide-reconciliation]].

**Tooling:** see `scripts/hypertide_reconcile.py` for the read-only fetch+match. The full audit/apply workflow used in May 2026 lived in `d:/tmp/ht_match/` (per-workspace decision CSVs + `apply_unkill.py` + `cleanup_candidates.py`); promote to `scripts/` if it becomes recurring.
