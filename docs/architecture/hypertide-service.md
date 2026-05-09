---
title: Hypertide Service — Architecture & Phased Plan
created: 2026-05-07
updated: 2026-05-07
status: planning
tags: [architecture, hypertide, integration, plan, service]
---

# Hypertide Service — Architecture & Phased Plan

> **Canonical plan document** for building the Hypertide micro-service inside Charm OS. Captures the architectural shift, bounded responsibilities, schema design, and phased delivery.
>
> Related:
> - API reference: [[hypertide-api]] — the canonical doc for what HT actually returns
> - Reconciliation runbook (Phase 1 deliverable): [[hypertide-reconciliation]]
> - Domain pipeline (legacy purchase flow): [[domain-purchase-pipeline]]

## TL;DR

We are building a bounded service around the Hypertide API to make HT the **source of truth for which domains exist, who's billing for them, and what workspace they belong to**. Today our `domains` table learns about new infrastructure *reactively* by parsing inbox emails after EmailBison sees them. Tomorrow it learns *proactively* from HT order metadata, and EmailBison's role flips from discovery to verification.

**Phase 1 (this PR — ~2-3 days):** read-only data collection. Pull HT records, match to existing DB rows by domain name, populate `hypertide_*` columns. Where no DB row exists for an HT record in an in-scope workspace, insert a new domain row with HT metadata. No writes to HT, no cancellation, no purchase flow.

**Phase 2+ (deferred):** event-driven cancellation via web UI + job queue, then order placement.

## Why this exists

### The problem with today's flow

Today's domain knowledge is inbox-driven:

```
HT order placed → MS provisions tenant → mailboxes created →
emails arrive → emailbison-sync detects new inbox →
parse domain from `email_address.split('@')[1]` →
INSERT INTO domains → guess workspace from where inboxes land
```

Three structural problems:

1. **Reactive discovery** — we only learn about infrastructure *after* mail flows. A 24-48 hour provisioning lag = 24-48 hours of operational blindness.
2. **No "expected but missing" signal** — if HT provisioned 52 inboxes for a domain but only 47 show up in EB, we have no way to detect the gap. We don't know what to expect.
3. **Workspace assignment is inferential** — based on inbox landing pattern. Brittle when HT splits one client's domains across multiple subscriptions, or when an org operates across multiple workspaces (e.g. Stable Kernel + Stable Kernel Market Research).

### The paradigm shift

```
═══════════ TODAY (inbox-driven discovery) ═════════════════════════
   HT order placed → MS provisions → EB sync detects new inbox
                                              │
                                              ▼
                  parse domain from email → INSERT INTO domains
                                              │
                                              ▼
                  guess workspace from inbox landing pattern

   Domain knowledge AFTER mail flows. No SLA on provisioning.

═══════════ PROPOSED (HT-first knowledge) ═══════════════════════════
   We POST /orders → HT returns recordId, subscriptionId
                                              │
                                              ▼
                  INSERT INTO domains with hypertide_record_id,
                  workspace_id, expected_inbox_count, deadline
                                              │
                                              ▼
   HT provisions → mailboxes arrive → EB sync VERIFIES match
                                              │
                                              ▼
                  diff(expected, actual) → "missing inboxes" alert

   Domain knowledge precedes inbox arrival. SLA enforceable.
```

## Bounded responsibilities of `hypertide-service`

| Responsibility | Scope | Money risk | Phase |
|---|---|---|---|
| **HT ↔ DB sync (collection)** | Pull `/orders/active`, `verify-revert`, populate `domains.hypertide_*`, alert on drift | None | **1** |
| **Workspace + legacy flagging** | `workspaces.manages_via_hypertide`, `domains.is_legacy` for non-HT records | None | **1** |
| **Provisioning verification** | Compare `domains.expected_inbox_count` to live `sender_accounts` count, alert on overdue (24-48h SLA) | None | 2 |
| **Cancellation orchestration** | Per-domain or per-subscription cancellation requests via web UI → job queue | **HIGH** | 2 |
| **Order assembly** | Validate bundling rules (entra=2 / google=5), submit unpaid orders | — | 3 |
| **Charge gating** | Hold orders in `awaiting_charge`, require explicit operator approval | **HIGH** | 3 |
| **Audit/health surface** | Endpoints/dashboard exposing drift, pending orders, scheduled cancels | None | 1+ |

What `hypertide-service` does **NOT** own:
- Inbox-level health (lives with EB sync — its job)
- Domain rotation / burn decisions (current rotation logic — its job)
- Lead-list quality (separate concern — campaign system)
- DNS records (HT API exposes them; we don't operate at that layer)

## Data flow — Phase 1 (collection only)

```
┌────────────────────────────────────────────────────────────────┐
│  Daily cron @ apps/hypertide-worker                            │
│                                                                │
│  1. GET /orders/active            → 732+ records              │
│  2. POST /subscriptions/verify-revert per unique sub          │
│     (~200 calls, takes ~10 min, well under rate limit)        │
│  3. Classifier:                                                │
│       • for each HT record → find domain by name              │
│       • update domain.hypertide_*                              │
│       • if no domain row → INSERT (in-scope workspaces only)  │
│       • if no matching workspace inferable → flag for review  │
│  4. Mark domains in non-HT-managed workspaces as is_legacy   │
│     (Estrada, Neon, EventPanda, etc.)                         │
│  5. Write summary row to sync_audit_log                       │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  Postgres                                                      │
│   workspaces (+ manages_via_hypertide, occupancy_only)        │
│   domains (+ hypertide_*, is_legacy, expected_inbox_count)    │
│   sync_audit_log (run history with drift counts)              │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (consumed by, not yet wired in P1)
┌────────────────────────────────────────────────────────────────┐
│  Future: emailbison-sync verifies, charm-frontend dashboards   │
└────────────────────────────────────────────────────────────────┘
```

## Polling vs. event-driven — the design call

**Decision: minimal polling + event-sourced verification on our actions, not blanket polling.**

Reasoning: HT state is mostly stable. Variation only happens when:
- **WE act**: we cancel or place an order → we know to expect a state change
- **Vendor side acts**: scheduled cancels execute on their date, support staff cleans up records, new orders provision

Naive 5-minute polling would burn API quota on identical responses 99% of the time. The right pattern:

| trigger | frequency | scope |
|---|---|---|
| **Our action** (cancel, place order — Phase 2+) | one-shot, with retry schedule (5min, 1h, 24h) | only the record we touched |
| **Daily light audit** | 1×/day | only records with `cancellation_type IN (full_subscription, partial_product)` — scheduled events that fire on a future date |
| **Weekly full audit** | 1×/week | full `/orders/active` + all `verify-revert` |
| **Provisioning watchdog** (Phase 2) | 1×/hour | only records with `expected_inbox_count > current_inbox_count` AND age < 48h |

**Net for steady state:** ~0 calls/day during quiet periods, 1 cheap cron daily, 1 expensive cron weekly. Drift hidden no longer than 24h.

The job queue (Phase 2 schema) carries this naturally: jobs have `scheduled_for` timestamps, workers claim `WHERE scheduled_for <= NOW() FOR UPDATE SKIP LOCKED`. No external bus or queue infrastructure.

## Workspace ↔ HT-org mapping — the design call

**Decision: don't try to derive workspace from HT metadata. We control the mapping, not Hypertide.**

The Stable Kernel case forced this:
- Stable Kernel + Stable Kernel Market Research = two DB workspaces
- Both share **one Hypertide organization** (HT thinks it's one customer)
- HT's `organizationName` is a free-text field with values like `"Stable Kernel"`, `"stable kernel"`, `"Stable Kernel Network HT"`, `"Stable Kernel Market Research"` (4 strings observed for what HT calls one client)
- Therefore: any logic that maps `organizationName` → `workspace_id` is wrong by construction

The right architecture:

1. **At order-creation time (Phase 3):** we tell HT one `client_name` (it only takes one), but **internally we record per-domain `workspace_id`**. The HT field is informational; our DB is canonical.

2. **At reconciliation time (Phase 1):** we match by `domain_name` (case-insensitive). For domains that match, we attach the existing `domains.workspace_id`. For unmatched, see workflow below.

3. **For ambiguous/unmatched HT records:** mark as `pending_workspace_assignment`, surface in operator review queue.

## Legacy & exempt classification

Two separate flags:

```sql
ALTER TABLE workspaces
  ADD COLUMN manages_via_hypertide BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN occupancy_only BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE domains
  ADD COLUMN is_legacy BOOLEAN NOT NULL DEFAULT FALSE;
```

- `workspaces.manages_via_hypertide = FALSE` → entire workspace skipped by every HT process. Set on Estrada, Neon, EventPanda (friend-occupancy workspaces with no HT footprint).
- `workspaces.occupancy_only = TRUE` → optional companion flag for "we host this workspace but they're not a billed client" — useful for filters/reports.
- `domains.is_legacy = TRUE` → domain in an HT-managed workspace, but we can't match it to any HT record. Pre-HT manual provisioning, or out-of-band-acquired domains.

These flags are **idempotent and durable**. The reconciliation worker reads them but never auto-changes them — operators flip them deliberately.

## Schema design

### Migration 110 — workspace + domain HT state

```sql
-- Workspace classification
ALTER TABLE workspaces
  ADD COLUMN manages_via_hypertide BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN occupancy_only BOOLEAN NOT NULL DEFAULT FALSE;

-- Domain HT state (Phase 1 reads, future phases write)
ALTER TABLE domains
  ADD COLUMN is_legacy BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN hypertide_record_id        TEXT,
  ADD COLUMN hypertide_subscription_id  TEXT,
  ADD COLUMN hypertide_product_id       TEXT,
  ADD COLUMN hypertide_status           VARCHAR(16),
  ADD COLUMN hypertide_payment_status   VARCHAR(16),
  ADD COLUMN hypertide_sending_tool     VARCHAR(20),
  ADD COLUMN hypertide_cancellation_type VARCHAR(24),
  ADD COLUMN hypertide_to_be_cancelled  BOOLEAN DEFAULT FALSE,
  ADD COLUMN hypertide_last_synced_at   TIMESTAMPTZ,
  ADD COLUMN hypertide_last_seen_at     TIMESTAMPTZ,
  ADD COLUMN expected_inbox_count       INTEGER;

CREATE UNIQUE INDEX domains_hypertide_record_id_uniq
  ON domains(hypertide_record_id) WHERE hypertide_record_id IS NOT NULL;
```

Field semantics:
- `hypertide_last_synced_at` — timestamp of last successful reconcile pass. Used for staleness checks.
- `hypertide_last_seen_at` — timestamp of last reconcile pass where this `hypertide_record_id` appeared in `/orders/active`. If this stops advancing while the row exists, HT has purged the record vendor-side — flag for review (don't auto-delete).
- `expected_inbox_count` — populated from HT plan (52 for entra, 3 for google). Used by Phase 2 provisioning watchdog.

### Migration 111 — hypertide_jobs (Phase 2)

Deferred to Phase 2. Job queue is not needed for read-only collection.

```sql
-- Phase 2 — DO NOT INCLUDE IN PHASE 1
-- CREATE TABLE hypertide_jobs (
--   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--   job_type VARCHAR(32) NOT NULL,
--   status VARCHAR(20) NOT NULL DEFAULT 'created',
--   workspace_id UUID REFERENCES workspaces(id),
--   payload JSONB,
--   result JSONB,
--   parent_job_id UUID REFERENCES hypertide_jobs(id),
--   scheduled_for TIMESTAMPTZ DEFAULT NOW(),
--   requested_by VARCHAR(255),
--   approved_by VARCHAR(255),
--   approved_at TIMESTAMPTZ,
--   started_at TIMESTAMPTZ,
--   completed_at TIMESTAMPTZ,
--   error_message TEXT,
--   created_at TIMESTAMPTZ DEFAULT NOW(),
--   CHECK (status IN ('created','pending_confirmation','approved',
--                     'running','completed','failed','cancelled'))
-- );
```

## Phased delivery

### Phase 1 — Data collection only (~2-3 days, this PR)

**Goal:** Hypertide records are mirrored into `domains` table. Drift is observable. No HT writes.

**Deliverables:**

1. **Migration 110** (workspace + domain state)
2. **`hypertide_api/classifier.py`** — single source of truth for decision logic (lifted from `d:/tmp/`, no curl, env-var secrets)
3. **`apps/hypertide-worker/`** — new Coolify app, replaces existing `hypertide-worker`
   - `pyproject.toml`, `Dockerfile`, `README.md`, `HANDOFF.md`
   - `src/hypertide_worker/audit.py` — workspace-level reconcile (matches d:/tmp/workspace_audit.py)
   - `src/hypertide_worker/jobs/audit_drift.py` — single job processor (Phase 1 only needs this one)
   - `src/hypertide_worker/cli.py` — `audit`, `backfill`, `mark-legacy` commands
   - `src/hypertide_worker/worker.py` — main loop (Phase 1: cron-mode only)
   - `tests/` — classifier coverage + audit fixture tests
4. **One-time backfill script** — populates `hypertide_*` columns for existing 642 domains by matching on domain_name + HT `/orders/active` data
5. **Workspace flag setup** — set `manages_via_hypertide=FALSE` on Estrada, Neon, EventPanda, Test Workspace, Deprecate
6. **Daily cron in Coolify** — runs `audit_drift` job, emits summary to `sync_audit_log`
7. **Runbook** — [[hypertide-reconciliation]] documenting the workflow

**Acceptance criteria:**
- 100% of in-scope domains (those in `manages_via_hypertide=TRUE` workspaces) either have `hypertide_record_id` populated OR `is_legacy=TRUE`
- Daily audit job runs successfully for 7 consecutive days without errors
- Drift count visible in audit_log; alerts NOT yet wired (Phase 2)
- All `d:/tmp/` scripts archived; functionality replicated in `apps/hypertide-worker/cli.py`
- Tests: classifier 100% branch coverage; audit job has integration test against fixture HT response

**Out of scope (Phase 1):**
- Web UI / charm-frontend changes
- HTTP routes in charm-api
- Job queue (`hypertide_jobs`)
- Cancellation flows
- Order placement
- Provisioning watchdog
- Slack alerts
- EB sync code changes

### Phase 2 — Cancellation via web UI + job queue (~1 week, deferred)

- Migration 095 (`hypertide_jobs`)
- Worker process picks up `cancel_domain` jobs
- HTTP endpoints in `charm-api`: `POST /api/hypertide/cancellations`, `POST /api/hypertide/cancellations/{id}/approve`
- Cancellation web UI on `charm-frontend` (redesigned, not a port of d:/tmp/cleanup_viewer.html)
- `verify_subscription` follow-up job pattern (5 min / 1 h / 24 h after our action)
- Slack notification when jobs land in `pending_confirmation` (visibility, not approval)
- Provisioning watchdog (`provisioning_check` job)

### Phase 3 — Order placement (~1 week, deferred)

- Order creation flow in web UI (operator confirms in UI before HT call)
- Two-step charge gating (per-workspace `auto_charge` flag)
- `expected_inbox_count` populated at order time
- Two-step payment safety: orders created unpaid, charge requires explicit approval

### Phase 4 — EB sync rework (~1 week, deferred)

- Audit existing EB sync code for domain-creation paths
- Convert to verify-only with alerts (no auto-INSERT)
- Dry-run mode for production cutover
- Deprecate the old discovery path

## Phase 1 — `apps/hypertide-worker/` package layout

```
apps/hypertide-worker/
├── Dockerfile
├── HANDOFF.md
├── README.md
├── pyproject.toml                  # asyncpg, httpx, click, pytest, respx, ruff, mypy
├── src/
│   └── hypertide_worker/
│       ├── __init__.py
│       ├── config.py               # env vars: HYPERTIDE_API_KEY, HYPERTIDE_API_URL, DATABASE_URL
│       ├── db.py                   # asyncpg connection helper
│       ├── ht_client.py            # thin wrapper around hypertide_api.client.HypertideAPIClient
│       ├── audit.py                # workspace audit logic (returns dataclasses, not CSVs)
│       ├── backfill.py             # one-time backfill from HT into domains
│       ├── classifier.py           # decision tree (re-exports hypertide_api.classifier)
│       ├── jobs/
│       │   ├── __init__.py
│       │   └── audit_drift.py      # only job in Phase 1
│       ├── worker.py               # main loop (Phase 1: cron entrypoint, not continuous claim)
│       └── cli.py                  # `audit`, `backfill`, `mark-legacy`, `inspect-domain`
└── tests/
    ├── conftest.py                 # respx fixtures, fake DB
    ├── test_classifier.py          # 100% branch coverage on decision tree
    ├── test_audit.py               # full pipeline integration test with mocked HT
    └── test_backfill.py            # backfill idempotency, ambiguous-match handling
```

## Phase 1 — backfill workflow

The one-time backfill is the most operationally consequential part of Phase 1. Specification:

```
INPUT:  fresh /orders/active + verify-revert sweep (732 records as of 2026-05-06)
        existing 642 domains rows

FOR EACH ws IN workspaces:
  IF ws.manages_via_hypertide = FALSE:           CONTINUE  (skip Estrada/Neon/EventPanda)

  FOR EACH ht_rec IN /orders/active WHERE matched-or-mappable to this ws:
    db_row = SELECT * FROM domains WHERE LOWER(domain_name) = LOWER(ht_rec.domain)

    IF db_row exists:
      UPDATE db_row SET
        hypertide_record_id        = ht_rec.id,
        hypertide_subscription_id  = ht_rec.subscriptionId,
        hypertide_product_id       = ht_rec.productId,
        hypertide_status           = ht_rec.status,
        hypertide_payment_status   = ht_rec.paymentStatus,
        hypertide_sending_tool     = ht_rec.sendingTool,
        hypertide_cancellation_type = verify_revert.cancellationType,
        hypertide_to_be_cancelled  = verify_revert.toBeCancelled,
        hypertide_last_synced_at   = NOW(),
        hypertide_last_seen_at     = NOW(),
        expected_inbox_count       = (52 IF entra ELSE 3)

    ELSE (no DB row):
      INSERT INTO domains (
        domain_name, workspace_id, hypertide_*,
        expected_inbox_count, is_active=TRUE, ...
      )

FOR EACH db_row IN domains WHERE workspace.manages_via_hypertide = TRUE:
  IF hypertide_record_id IS NULL after backfill:
    UPDATE db_row SET is_legacy = TRUE

EMIT summary:
  matched: N
  inserted: N
  legacy_flagged: N
  ambiguous_workspace: N (operator review needed)
```

### Workspace assignment for new INSERTs

When inserting a new domain row from an HT record without a DB match, we need a workspace_id. The order of preference:

1. **Domain name pattern match** — if the domain ends with a workspace's known suffix (e.g., `*.spoutwater.com` → Spout, `*.searchatlas.com` → Search Atlas), assign automatically.
2. **HT `forwardingDomain` heuristic** — if `forwardingDomain` matches a known client domain (e.g., `forwardingDomain=stablekernel.com` → Stable Kernel or Stable Kernel Market Research), narrow to those workspaces.
3. **Operator review** — if neither rule resolves, leave `workspace_id = NULL` and flag for operator assignment via CLI command (`hypertide-worker assign-workspace <domain>`).

We do **not** trust HT's `organizationName` field for routing. It's recorded as `metadata.ht_organization` for debugging only.

### Idempotency

The backfill must be safely re-runnable. Properties:

- `UPDATE` paths use `hypertide_last_synced_at = NOW()` regardless of what changed
- `INSERT` paths check `WHERE NOT EXISTS (SELECT 1 FROM domains WHERE LOWER(domain_name) = LOWER($1))` first
- `is_legacy` flag is only set, never unset (operators reverse manually if needed)

## Decisions log

| date | decision | rationale |
|---|---|---|
| 2026-05-07 | Service lives in expanded existing `hypertide-worker` Coolify app | Single app, fewer moving parts, replaces outdated logic |
| 2026-05-07 | HTTP routes in `charm-api` (`/api/hypertide/*`), not separate API service | Auth, workspace context, DB connection already there |
| 2026-05-07 | Frontend in `charm-email-os` (Next.js), with explicit redesign | Existing UI infrastructure; redesign needs design pass |
| 2026-05-07 | Single worker, serial processing | Cancel/order are low-volume, money-safe; concurrency adds risk for no benefit |
| 2026-05-07 | Daily light audit + weekly full audit, no 5-min polling | HT state is mostly stable; blanket polling burns quota |
| 2026-05-07 | Workspace ↔ HT-org mapping is OUR canonical state, not derived from HT | Stable Kernel case proves HT `organizationName` cannot be a join key |
| 2026-05-07 | Phase 1 = collection only (no HT writes) | De-risks the merge; purchasing requires careful planning |
| 2026-05-07 | Web UI for cancel/order is event-driven (UI → DB job → worker) | No Slack-driven approvals; operator confirms in UI |
| 2026-05-07 | New domain rows can be INSERTed at backfill time when in scope | HT becomes proactive source of truth; legacy domains flagged separately |

## Investigation findings (2026-05-07)

The architecture-doc questions were investigated against the production DB. Resolutions captured here so the next reader doesn't re-investigate.

### ✅ Q1 — `inbox_purchase_jobs` state: EMPTY (0 rows)

```
SELECT status, worker_mode, COUNT(*), MIN(created_at), MAX(created_at)
FROM inbox_purchase_jobs;     → 0 rows
```

**Implication:** old `hypertide-worker` has nothing to drain. **Decommissioning is safe with no migration needed.** Cutover plan: deploy new `apps/hypertide-worker/`, verify it claims the new `hypertide_jobs` table (Phase 2) or runs scheduled audits (Phase 1), stop old worker, delete its Coolify app.

### ✅ Q2 — Coolify cutover: confirmed simple replacement

Since `inbox_purchase_jobs` is empty, no drain step. Default approach:
1. Build & deploy new `apps/hypertide-worker/` Coolify app under same name
2. Verify daily audit cron runs successfully for 24h
3. Delete old `hypertide_api/worker.py` from repo
4. (Optional) rename old Coolify app to `hypertide-worker-legacy` if you want a safety rollback window

### ✅ Q3 — EB sync's domain-creation path: located, idempotent, coexists safely

**Found at:** [sync_modules/sync_accounts.py:651-680](../../sync_modules/sync_accounts.py#L651-L680)

```python
# sync_all_domains() — creates domains by parsing email addresses
INSERT INTO domains (workspace_id, domain_name, approval_status, domain_source, ...)
SELECT DISTINCT ON (SPLIT_PART(sa.email_address, '@', 2))
    sa.workspace_id, SPLIT_PART(sa.email_address, '@', 2), 'legacy', 'legacy', ...
FROM sender_accounts sa
WHERE NOT EXISTS (SELECT 1 FROM domains d WHERE d.domain_name = ...)
```

Properties:
- **Idempotent** — `NOT EXISTS` check on `domain_name` (which has a global unique constraint per [migration 092](../../migrations/092_domain_pipeline_queue.sql) commentary)
- **Sets `domain_source='legacy'`** for inferred domains
- **Workspace assignment**: takes `workspace_id` from the first sender_account that mentioned the domain (`first_seen_at ASC`)

**Implication for Phase 1:** EB's path and our HT-INSERT path can coexist. Whoever runs first inserts the row. If HT-INSERT runs first (preferred — Phase 1 backfill happens before next EB sync cycle), EB's `NOT EXISTS` skips. If EB's path runs first (a new domain not in HT yet), our subsequent HT match adds metadata via UPDATE on existing row.

**Other domain-INSERT paths discovered (orthogonal to Phase 1, document for Phase 4 cleanup):**
- [api/routes/clients.py:1958-1967](../../api/routes/clients.py#L1958) — duplicates EB's parse-from-email logic, used by manual import flow
- [api/routes/infrastructure.py:1917](../../api/routes/infrastructure.py#L1917) — domain create from infrastructure setup
- [api/routes/domains.py:434](../../api/routes/domains.py#L434) — direct create endpoint
- [api/routes/domain_sourcing.py:426](../../api/routes/domain_sourcing.py#L426) — domain registration tracking

These don't interfere with Phase 1 (still protected by `domain_name` unique constraint), but Phase 4 audit should catalog them.

### ⚠️ Q4 — 24-48h provisioning SLA: cannot empirically validate today

Investigation: queried `domains.created_at` vs first `sender_accounts.created_at` for last 60 days of new domains. Result: **first inbox `created_at` precedes domain `created_at` by ~2 minutes** for every recent domain. That confirms the inbox-driven discovery pattern (`domain` rows are created from inbox emails) but means we have no "order-placed → first-inbox-arrived" measurement on file.

HT API's `created_at` field is **date-precision only** (`"2026-04-07"`), not timestamped — too coarse for SLA validation.

**Implication:** the 24-48h window is operational lore, not data-validated. Phase 2 provisioning watchdog will be the first time we measure this empirically. Set initial deadline to 48h, observe first 30 days of data, calibrate.

### Resolved: `domain_source` discriminator value

Existing values on `domains.domain_source`:
- `'legacy'` (522 rows) — discovered via EB inbox parsing
- `'generated'` (150 rows: 84 pending + 59 available + 7 purchased status) — purchase pipeline candidates

**Phase 1 convention:**
- New rows from HT-INSERT: `domain_source='hypertide'` (new enum value)
- Existing rows we match to HT records: **leave `domain_source` unchanged** (don't rewrite history). Just populate `hypertide_*` columns. Eventually a normalization pass can promote `legacy → hypertide` for matched rows, but that's not Phase 1.

### Open question — frontend redesign (Phase 3)

Not investigatable via code. Needs a UX/design doc before Phase 3 implementation starts. The d:/tmp/`cleanup_viewer.html` was a 30-min dev tool — production version warrants intentional design. **Recommend a separate `docs/design/hypertide-frontend.md` planning doc before Phase 3 work begins.**

## Future considerations (Phase 5+)

Things explicitly out of scope today but worth flagging for later:

- **Webhook integration with HT.** Vendor doesn't currently expose webhooks. If they add them, our event-driven model fits naturally — the cron-based daily audit becomes a fallback, not the primary signal.
- **Multi-vendor abstraction.** If we ever onboard a second inbox-infrastructure vendor (alternative to Hypertide), the `domains.hypertide_*` columns prefix should generalize to a `provider` discriminator. Not worth pre-engineering until we have a second vendor.
- **HT API version migration.** Vendor said the API is v1.0. When v2 lands, we'll want a single migration point — `hypertide_api/client.py` is already the right boundary.
- **Cost reporting dashboard.** Once `hypertide_payment_status` is populated, we can compute per-workspace monthly HT spend. Useful for client billing transparency.

---

*This is a planning document. Implementation tracking lives in PRs. Operational runbook (once Phase 1 ships) at [[hypertide-reconciliation]].*
