---
title: Purchase Worker Architecture
created: 2026-01-29
updated: 2026-02-04
tags: [architecture, purchase, worker, browser-automation, hypertide, playwright]
---

# Purchase Worker Architecture

How the purchase worker automates Hypertide inbox provisioning using deterministic Playwright browser automation.

## Overview

Hypertide (app2.hypertide.io) has **no API** for purchasing email inboxes. The purchase worker solves this with a deterministic Python script (`hypertide_playwright.py`) that reads job data from the database, launches a headed Chromium browser via Playwright, navigates the Hypertide web UI, fills forms, selects workspaces, and reaches the Stripe checkout — all without human intervention.

### Why Direct Playwright (Not Claude Code)?

The purchase worker originally used Claude Code + MCP for browser automation. In v2.0, this was replaced with a deterministic Playwright script:

| Approach | Trade-offs |
|----------|------------|
| REST API | None exists for Hypertide |
| Manual human clicks | Does not scale, error-prone |
| Claude Code + MCP (v1) | Worked but slow (~5 min/job), required OAuth, LLM inference overhead |
| **Direct Playwright script (v2)** | **Fast (~2 min/job), deterministic, no LLM dependency** |

### Architecture Change (v1 → v2)

```
v1: purchase_worker.py → subprocess: claude -p <prompt> --mcp-config ... → MCP server → Playwright
v2: purchase_worker.py → subprocess: python3 hypertide_playwright.py --job-id <ID> → Playwright directly
```

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                                   │
│  POST /api/inbox-purchasing/smart-order { client_id, domain_ids, ...}       │
│  Polls GET /api/inbox-purchasing/status/{job_id} every 3 seconds            │
│  Shows: InboxProvisionModal with progress, checkout card on completion      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         API (FastAPI)                                        │
│  api/routes/inbox_purchasing.py → execute_smart_order()                      │
│  INSERT INTO inbox_purchase_jobs (job-specific data only)                    │
│  Returns: { job_id, status: 'pending' }                                     │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  PostgreSQL (inbox_purchase_jobs)                            │
│  status='pending', worker_mode='worker'                                     │
│  Stores: domains, provider_type, company_name, workspace_name, sender_names │
│  Does NOT store: credentials (those come from ENV)                          │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ POLL (every 10s)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               Purchase Worker Daemon (purchase_worker.py)                    │
│  Docker container: charm-purchase-worker                                     │
│  - Polls DB for pending jobs (worker_mode='worker')                         │
│  - Spawns: python3 hypertide_playwright.py --job-id <UUID>                  │
│  - Passes DB credentials via environment                                    │
│  - Timeout: 1800s (configurable via JOB_TIMEOUT)                            │
│  - Guard pattern: checks if script already handled status transition        │
│  - Cooldown: 30s between jobs (JOB_COOLDOWN)                                │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ subprocess.run()
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│            Playwright Script (hypertide_playwright.py)                       │
│                                                                             │
│  Deterministic step-by-step browser automation:                             │
│  - Reads job from DB (psycopg2)                                             │
│  - Reads credentials from ENV                                               │
│  - Launches headed Chromium on Xvfb virtual display                         │
│  - Navigates Hypertide UI step by step                                      │
│  - Updates job status + logs steps to purchase_job_steps table              │
│  - Captures Stripe checkout URL → sets awaiting_checkout                    │
│  - On failure: calls fail_job() with error categorization                   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ Playwright (headed Chromium on Xvfb)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Hypertide Web UI (app2.hypertide.io)                      │
│                    EmailBison API (spellcast.hirecharm.com)                  │
│                    Stripe Checkout (checkout.stripe.com)                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `purchase_worker.py` | Main daemon — polls DB, spawns Playwright script subprocess |
| `hypertide_playwright.py` | Deterministic Playwright automation script |
| `Dockerfile.purchase-worker` | Docker image (Debian + Python + Playwright + Xvfb) |
| `docker-compose.purchase-worker.yml` | Production deployment (Coolify) |
| `requirements-purchase-worker.txt` | Python deps: psycopg2-binary, playwright, python-dotenv |
| `tests/insert_test_purchase_job.py` | Test job inserter + status/reset utilities |

## Credential Management

Global credentials are stored as **ENV variables** on the worker container, not in the database. The Playwright script reads credentials from `os.getenv()` at startup.

### What Goes Where

| Data | Storage | Reason |
|------|---------|--------|
| Hypertide email/password | ENV (`HYPERTIDE_EMAIL`, `HYPERTIDE_PASSWORD`) | Same account for all jobs |
| Bison username/password | ENV (`BISON_USERNAME`, `BISON_PASSWORD`) | Same account for all jobs |
| Bison URL | ENV (`BISON_URL`) | Always `https://spellcast.hirecharm.com` |
| EmailBison API key | ENV (`EMAILBISON_API_KEY`) | Same key for workspace fetch |
| Workspace name | Database (`bison_workspace_name`) | Different per client |
| Domain names | Database (`domain_names`) | Different per job |
| Provider type | Database (`provider_type`) | `entra` or `google` per job |
| Company name | Database (`company_name`) | Different per client |
| Sender names | Database (`sender_names`) | Different per job |

## Purchase Flow Steps

The `hypertide_playwright.py` script executes these steps sequentially:

| Step | Name | What Happens |
|------|------|-------------|
| 1 | Load Job Data | Read job from DB via psycopg2, merge ENV credentials |
| 2 | Login to Hypertide | Navigate to signin, fill email/password, verify dashboard |
| 3 | Start New Order | Click "Place New Order" |
| 4 | Select Provider | Click Entra or Google option |
| 5 | Select Domains (BYOD) | Enter each domain name in the form |
| 6 | Basic Configuration | Fill forwarding domain and company name |
| 7 | **Bison Config (Critical)** | Select Bison tool, fill credentials, fetch workspaces via API key, select exact workspace |
| 8 | Warmup Settings | Accept defaults |
| 9 | Outbound Settings | Accept defaults |
| 10 | User Configuration | Add sender names (firstName/lastName) |
| 11 | Review Order | Verify domain count, provider, pricing |
| 12 | **Checkout Handoff** | Capture Stripe checkout URL, set job to `awaiting_checkout` |

### Step 7 Detail: Bison Workspace Selection

This is the most critical step — incorrect workspace selection causes cross-contamination of inboxes between clients.

```
Hypertide Form: "Step 2) Connect Your Email Automation Tool"
    │
    ├─ Select "Bison" radio button
    ├─ Fill Username (bison_username from ENV)
    ├─ Fill Password (bison_password from ENV)
    ├─ Fill Bison URL (bison_url = https://spellcast.hirecharm.com)
    │
    ├─ Click Workspace dropdown → Opens modal
    │   ├─ "Bison URL" field (pre-filled)
    │   ├─ "API Key (Global)" field → Fill with bison_api_key from ENV
    │   ├─ Click "Fetch Workspaces"
    │   ├─ Wait for workspace list to populate
    │   └─ Select EXACT bison_workspace_name from DB
    │
    └─ Click "Move on without saving"
```

**Safety:** If the exact workspace name is NOT found in the dropdown, the job fails immediately to prevent cross-contamination.

### Step 12: Checkout Handoff

Instead of completing payment automatically, the script captures the Stripe checkout URL and hands off to the user:

```python
# Script captures checkout URL from Stripe redirect
checkout_url = page.url  # e.g., https://checkout.stripe.com/c/pay/cs_live_...

# Updates job in DB
UPDATE inbox_purchase_jobs
SET status = 'awaiting_checkout',
    checkout_url = $1,
    current_step = 'awaiting_manual_checkout'
WHERE id = $2
```

The frontend displays a "Payment Required" card with an "Open Stripe Checkout" button.

## Job Status Lifecycle

```
pending → processing → executing → awaiting_checkout → completed
                                 ↘ failed
```

| Status | Set By | Meaning |
|--------|--------|---------|
| `pending` | API | Job created, waiting for worker |
| `processing` | Worker | Worker picked up job, spawning script |
| `executing` | Script | Playwright is actively automating |
| `awaiting_checkout` | Script | Stripe URL captured, waiting for manual payment |
| `completed` | API | Payment confirmed via confirm-checkout endpoint |
| `failed` | Script/Worker | Error occurred, see `error_type` and `errors` |

## Domain Locking

When a purchase job is created via `POST /api/inbox-purchasing/smart-order`, selected domains are locked to prevent concurrent job conflicts:

```sql
UPDATE domains
SET purchase_job_id = $1, purchase_job_status = 'pending'
WHERE id = ANY($2)
```

### Lock Release

Locks are released by `_release_domain_locks()`:

| Trigger | What Happens |
|---------|-------------|
| Job **cancelled** | `DELETE /jobs/{job_id}` → domains unlocked |
| Job **completed** | `confirm-checkout` → domains unlocked, status → active |
| Job **failed** | Script's `fail_job()` releases locks; on retry, domains remain locked |

## Safety and Rate Limiting

| Protection | Implementation | Purpose |
|------------|---------------|---------|
| Workspace guard | Script fails if workspace name not found | Prevent cross-contamination |
| Login dedup | `_login_completed` flag | Prevent double login |
| Slow motion | `slow_mo=100` on Playwright browser | Pace all browser actions |
| Navigation waits | `wait_for_load_state('networkidle')` | Reliable page transitions |
| Step logging | Each step logged to `purchase_job_steps` with screenshot | Full audit trail |
| Job timeout | 1800s default (configurable via `JOB_TIMEOUT`) | Hard time limit |
| Stale job recovery | `cleanup_stale_jobs()` on worker startup | Recover from crashes |
| Guard pattern | Worker checks if script already set final status before double-failing | Prevent status clobbering |

## Audit Trail

Every job execution produces a full audit trail in the `purchase_job_steps` table:

| Column | Type | Description |
|--------|------|-------------|
| `job_id` | UUID | FK to inbox_purchase_jobs |
| `step_name` | TEXT | e.g. `login_page`, `bison_config`, `checkout_handoff` |
| `screenshot_base64` | TEXT | Auto-captured screenshot at each step |
| `notes` | TEXT | Human-readable description of what happened |
| `created_at` | TIMESTAMP | When the step was recorded |

## Docker Container Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  charm-purchase-worker Container (Debian bookworm-slim)          │
│                                                                 │
│  User: worker (non-root)                                        │
│                                                                 │
│  ┌───────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │ Xvfb :99      │  │ purchase_      │  │ hypertide_       │   │
│  │ Virtual display│  │ worker.py      │  │ playwright.py    │   │
│  │ 1280x900x24   │  │ (main daemon)  │  │ (subprocess)     │   │
│  └───────────────┘  └───────┬────────┘  └────────┬─────────┘   │
│                              │                     │            │
│                              │ spawns              │ Playwright  │
│                              └─────────────────────┘            │
│                                        │                        │
│                              ┌─────────▼──────────┐            │
│                              │ Chromium (headed)   │            │
│                              │ via Playwright      │            │
│                              └─────────────────────┘            │
│                                                                 │
│  No volumes needed (no Claude OAuth)                            │
│  ENV: HYPERTIDE_*, BISON_*, EMAILBISON_*, POSTGRES_*            │
│  shm_size: 256m (Chromium shared memory)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Why Headed Chromium?

Hypertide is a React SPA. Headless Chromium fails to render some dynamic content. The solution is headed Chromium on a virtual display (Xvfb), configured with `DISPLAY=:99`.

## Testing

### Test Modes

```bash
# Insert a test job
python tests/insert_test_purchase_job.py

# Run single job, stop after step 4 (provider selection)
docker exec charm-purchase-worker \
    python3 /app/purchase_worker.py --single-job <JOB_ID> --stop-after-step 4

# Run single job, stop after step 7 (Bison workspace selection)
docker exec charm-purchase-worker \
    python3 /app/purchase_worker.py --single-job <JOB_ID> --stop-after-step 7

# Check job status and audit trail
python tests/insert_test_purchase_job.py --status <JOB_ID>

# Reset job for re-testing
python tests/insert_test_purchase_job.py --reset <JOB_ID>
```

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `POSTGRES_HOST` | Yes | - | Database host |
| `POSTGRES_PORT` | No | `5432` | Database port |
| `POSTGRES_DB` | No | `postgres` | Database name |
| `POSTGRES_USER` | Yes | - | Database user |
| `POSTGRES_PASSWORD` | Yes | - | Database password |
| `POLL_INTERVAL` | No | `10` | Seconds between DB polls |
| `JOB_TIMEOUT` | No | `1800` | Max seconds per job |
| `JOB_COOLDOWN` | No | `30` | Seconds between jobs |
| `HYPERTIDE_EMAIL` | Yes | - | Hypertide login email |
| `HYPERTIDE_PASSWORD` | Yes | - | Hypertide login password |
| `BISON_USERNAME` | Yes | - | EmailBison login email |
| `BISON_PASSWORD` | Yes | - | EmailBison login password |
| `BISON_URL` | No | `https://spellcast.hirecharm.com` | EmailBison instance URL |
| `EMAILBISON_API_KEY` | Yes | - | API key for workspace fetch |
| `ALERT_WEBHOOK_URL` | No | - | Discord/Slack webhook for alerts |

## Related

- [[claude-code-worker]] - Domain and strategy worker architecture (still uses Claude Code)
- [[../deployment/purchase-worker-coolify]] - Coolify deployment guide
- [[../concepts/inbox-provisioning]] - Inbox provisioning concepts
- [[data-flow]] - System data flow
