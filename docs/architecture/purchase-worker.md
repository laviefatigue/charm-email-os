---
title: Purchase Worker Architecture
created: 2026-01-29
updated: 2026-01-29
tags: [architecture, purchase, worker, mcp, browser-automation, hypertide]
---

# Purchase Worker Architecture

How the purchase worker automates Hypertide inbox provisioning using Claude Code, Playwright browser automation, and MCP tools.

## Overview

Hypertide (app2.hypertide.io) has **no API** for purchasing email inboxes. The purchase worker solves this by using Claude Code as an autonomous browser operator: it reads job data from the database, navigates the Hypertide web UI with Playwright, fills forms, selects workspaces, and completes orders — all without human intervention.

### Why Browser Automation?

| Approach | Feasibility |
|----------|-------------|
| REST API | None exists |
| Direct DB access | No access to Hypertide internals |
| Manual human clicks | Does not scale, error-prone |
| **Claude Code + Playwright** | **Autonomous, auditable, resilient** |

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                                   │
│  POST /api/inbox-purchasing/smart-order { client_id, domain_ids, ...}       │
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
              Frontend polls GET /api/inbox-purchasing/status/{job_id}
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
│  - Polls DB for pending jobs                                                │
│  - Loads skill from .claude/skills/execute-purchase.md                       │
│  - Builds prompt with skill + job parameters                                │
│  - Spawns: claude -p <prompt> --dangerously-skip-permissions                │
│  - Timeout: 600s (configurable via JOB_TIMEOUT)                             │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ subprocess.run()
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Claude Code CLI                                        │
│  Reads embedded skill instructions (14 steps)                               │
│  Executes steps sequentially using MCP tools                                │
│  Max turns: 225 (production), (step * 15) + 15 (testing)                    │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ MCP Protocol (stdio)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               MCP Server (purchase_mcp/server.py)                            │
│                                                                             │
│  Browser Tools (Playwright):     Database Tools (psycopg2):                 │
│  - navigate(url)                 - get_purchase_job(job_id)                  │
│  - click(selector)               - update_job_status(job_id, status)        │
│  - fill(selector, value)         - log_step(job_id, step_name, notes)       │
│  - wait_for_text(text)           - complete_job(job_id, order_id)           │
│  - screenshot()                  - fail_job(job_id, error, step)            │
│  - get_page_text()                                                          │
│  - scroll_down(pixels)                                                      │
│  - select_dropdown(...)                                                     │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ Playwright (headed Chromium on Xvfb)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Hypertide Web UI (app2.hypertide.io)                      │
│                    EmailBison API (spellcast.hirecharm.com)                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `purchase_worker.py` | Main daemon — polls DB, spawns Claude Code subprocess |
| `purchase_mcp/server.py` | MCP server — browser automation + database tools |
| `purchase_mcp_config.json` | MCP server launch configuration (Docker) |
| `purchase_mcp_config_local.json` | MCP server launch configuration (Windows) |
| `.claude/skills/execute-purchase.md` | 14-step skill instructions embedded in prompt |
| `Dockerfile.purchase-worker` | Docker image (Debian + Claude Code + Playwright + Xvfb) |
| `docker-compose.purchase-worker.yml` | Production deployment (Coolify) |
| `docker-compose.purchase-test.yml` | Local testing (Docker Desktop) |
| `tests/insert_test_purchase_job.py` | Test job inserter + status/reset utilities |

## Credential Management

Global credentials are stored as **ENV variables** on the worker container, not in the database. The MCP server's `get_purchase_job()` handler merges ENV credentials into the response dict, so Claude Code receives a unified data shape regardless of source.

### What Goes Where

| Data | Storage | Reason |
|------|---------|--------|
| Hypertide email/password | ENV (`HYPERTIDE_EMAIL`, `HYPERTIDE_PASSWORD`) | Same account for all jobs |
| Bison username/password | ENV (`BISON_USERNAME`, `BISON_PASSWORD`) | Same account for all jobs |
| Bison URL | ENV (`BISON_URL`) | Always `https://spellcast.hirecharm.com` |
| EmailBison API key | ENV (`EMAILBISON_API_KEY`) | Same key for workspace fetch |
| Stripe card info | ENV (`STRIPE_CARD_*`) | Same payment method |
| Workspace name | Database (`bison_workspace_name`) | Different per client |
| Domain names | Database (`domain_names`) | Different per job |
| Provider type | Database (`provider_type`) | `entra` or `google` per job |
| Company name | Database (`company_name`) | Different per client |
| Sender names | Database (`sender_names`) | Different per job |

### Merge Logic (server.py)

```python
# After building result dict from DB row:
env_credentials = {
    "hypertide_email": os.getenv("HYPERTIDE_EMAIL", ""),
    "hypertide_password": os.getenv("HYPERTIDE_PASSWORD", ""),
    "bison_username": os.getenv("BISON_USERNAME", ""),
    "bison_password": os.getenv("BISON_PASSWORD", ""),
    "bison_url": os.getenv("BISON_URL", "https://spellcast.hirecharm.com"),
    "bison_api_key": os.getenv("EMAILBISON_API_KEY", ""),
}
for key, env_value in env_credentials.items():
    if env_value:  # ENV set -> use it; else keep DB value (backwards compat)
        result[key] = env_value
```

### Backwards Compatibility

| Scenario | Behavior |
|----------|----------|
| Old DB row WITH credentials + ENV set | ENV wins (override) |
| Old DB row WITH credentials + ENV not set | DB value used (fallback) |
| New DB row WITHOUT credentials + ENV set | ENV provides credentials |
| New DB row WITHOUT credentials + ENV not set | Empty credentials, job fails at login |

## 14-Step Purchase Flow

The skill file (`.claude/skills/execute-purchase.md`) defines these steps:

| Step | Name | What Happens |
|------|------|-------------|
| 1 | Load Job Data | `get_purchase_job(job_id)` fetches all parameters |
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
| 12 | Checkout / Payment | Select saved payment or enter card |
| 13 | Capture Confirmation | Extract order ID, take screenshot |
| 14 | Complete Job | `complete_job(job_id, order_id)` updates DB |

### Step 7 Detail: Bison Workspace Selection

This is the most critical step — incorrect workspace selection causes cross-contamination of inboxes between clients.

```
Hypertide Form: "Step 2) Connect Your Email Automation Tool"
    │
    ├─ Select "Bison" radio button
    ├─ Fill Username (bison_username)
    ├─ Fill Password (bison_password)
    ├─ Fill Bison URL (bison_url = https://spellcast.hirecharm.com)
    │
    ├─ Click Workspace dropdown → Opens modal
    │   ├─ "Bison URL" field (pre-filled)
    │   ├─ "API Key (Global)" field → Fill with bison_api_key
    │   ├─ Click "Fetch Workspaces"
    │   ├─ Wait for workspace list to populate
    │   └─ Select EXACT bison_workspace_name
    │
    └─ Click "Move on without saving"
```

**Safety:** If the exact workspace name is NOT found in the dropdown, the job fails immediately to prevent cross-contamination.

## Safety and Rate Limiting

### Server-Side Enforcement

| Protection | Implementation | Purpose |
|------------|---------------|---------|
| Login guard | `_login_completed` flag; navigate handler blocks signin URLs after login | Prevent double login |
| Step dedup | DB query before INSERT into `purchase_job_steps` | Prevent duplicate audit entries |
| Navigation dedup | Skip navigate() if already on the same URL | Reduce unnecessary page loads |
| Navigation rate limit | 3-second cooldown between navigate() calls | Prevent hammering Hypertide |
| Slow motion | `slow_mo=100` on Playwright browser | Pace all browser actions |
| Post-click tracking | Detect URL change after click, wait for domcontentloaded | Reliable page transitions |
| Max turns | 225 (production), `(step * 15) + 15` (testing) | Prevent runaway execution |
| Job timeout | 600s default (configurable via `JOB_TIMEOUT`) | Hard time limit |

### Skill-Level Safety Rules

1. Only use data from the job record — never invent values
2. Log every step exactly once via `log_step`
3. If workspace name not found: fail immediately
4. If unexpected content: fail with screenshot
5. If payment fails: fail, never retry payment
6. Never navigate away from Hypertide
7. Login once and only once
8. Execute steps in strict sequential order

## Audit Trail

Every job execution produces a full audit trail in the `purchase_job_steps` table:

| Column | Type | Description |
|--------|------|-------------|
| `job_id` | UUID | FK to inbox_purchase_jobs |
| `step_name` | TEXT | e.g. `login_page`, `bison_config`, `confirmation` |
| `screenshot_base64` | TEXT | Auto-captured screenshot at each step |
| `notes` | TEXT | Human-readable description of what happened |
| `created_at` | TIMESTAMP | When the step was recorded |

Steps are deduplicated at the database level — if a step_name already exists for a job, the INSERT is rejected with a warning message telling Claude to continue forward.

## Docker Container Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  charm-purchase-worker Container (Debian bookworm-slim)          │
│                                                                 │
│  User: claude (non-root, required for --dangerously-skip-perms) │
│                                                                 │
│  ┌───────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │ Xvfb :99      │  │ purchase_      │  │ Claude Code CLI  │   │
│  │ Virtual display│  │ worker.py      │  │ (subprocess)     │   │
│  │ 1280x900x24   │  │ (main daemon)  │  │                  │   │
│  └───────────────┘  └───────┬────────┘  └────────┬─────────┘   │
│                              │                     │            │
│                              │ spawns              │ stdio      │
│                              └─────────────────────┘            │
│                                        │                        │
│                              ┌─────────▼──────────┐            │
│                              │ purchase_mcp/       │            │
│                              │ server.py           │            │
│                              │ (Playwright +       │            │
│                              │  psycopg2)          │            │
│                              └─────────────────────┘            │
│                                                                 │
│  Volume: /home/claude/.claude (Claude OAuth credentials)        │
│  ENV: HYPERTIDE_*, BISON_*, EMAILBISON_*, STRIPE_*, POSTGRES_* │
│  shm_size: 256m (Chromium shared memory)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Why Headed Chromium?

Hypertide is a React SPA. Headless Chromium fails to render some dynamic content. The solution is headed Chromium on a virtual display (Xvfb), configured with `DISPLAY=:99`.

## Testing

### Test Modes

```bash
# Insert a test job (no credentials in DB row)
python tests/insert_test_purchase_job.py

# Run single job, stop after step 2 (login only)
docker exec -e JOB_TIMEOUT=300 charm-purchase-worker-test \
    python3 /app/purchase_worker.py --single-job <JOB_ID> --stop-after-step 2

# Run single job, stop after step 7 (Bison workspace selection)
docker exec -e JOB_TIMEOUT=900 charm-purchase-worker-test \
    python3 /app/purchase_worker.py --single-job <JOB_ID> --stop-after-step 7

# Check job status and audit trail
python tests/insert_test_purchase_job.py --status <JOB_ID>

# Reset job for re-testing
python tests/insert_test_purchase_job.py --reset <JOB_ID>
```

### 4-Layer Testing Strategy

| Layer | Tests | Scope |
|-------|-------|-------|
| 1 | Windows browser + DB | Playwright connects, DB reads/writes work |
| 2 | Claude Code + MCP on Windows | MCP tools respond correctly to Claude |
| 3 | Docker container (isolated) | Full flow inside container, step-by-step |
| 4 | Production Coolify | Live deployment end-to-end |

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `POSTGRES_HOST` | Yes | - | Database host |
| `POSTGRES_PORT` | No | `5432` | Database port |
| `POSTGRES_DB` | No | `postgres` | Database name |
| `POSTGRES_USER` | Yes | - | Database user |
| `POSTGRES_PASSWORD` | Yes | - | Database password |
| `POLL_INTERVAL` | No | `10` | Seconds between DB polls |
| `JOB_TIMEOUT` | No | `600` | Max seconds per job |
| `CLAUDE_ACCOUNT` | No | - | Claude profile name |
| `HYPERTIDE_EMAIL` | Yes | - | Hypertide login email |
| `HYPERTIDE_PASSWORD` | Yes | - | Hypertide login password |
| `BISON_USERNAME` | Yes | - | EmailBison login email |
| `BISON_PASSWORD` | Yes | - | EmailBison login password |
| `BISON_URL` | No | `https://spellcast.hirecharm.com` | EmailBison instance URL |
| `EMAILBISON_API_KEY` | Yes | - | API key for workspace fetch |
| `STRIPE_CARD_NUMBER` | No | - | Card number for checkout |
| `STRIPE_CARD_EXP` | No | - | Card expiry (MM/YY) |
| `STRIPE_CARD_CVC` | No | - | Card CVC |
| `STRIPE_CARD_ZIP` | No | - | Card billing ZIP |
| `ALERT_WEBHOOK_URL` | No | - | Discord/Slack webhook for alerts |

## Related

- [[claude-code-worker]] - Domain and strategy worker architecture (same pattern)
- [[../deployment/purchase-worker-coolify]] - Coolify deployment guide
- [[../deployment/local-docker]] - Local Docker development
- [[../infrastructure/coolify]] - Coolify platform
- [[data-flow]] - System data flow
