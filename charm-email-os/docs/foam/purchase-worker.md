# Purchase Worker

Autonomous browser automation system for purchasing email inboxes on Hypertide (app2.hypertide.io), which has no API.

## How It Works

The purchase worker is a Docker container that polls the database for pending purchase jobs, then spawns **Claude Code** as a subprocess. Claude Code uses embedded skill instructions (14 steps) to navigate the Hypertide web UI via **Playwright browser automation**, filling forms, selecting workspaces, and completing orders without human intervention.

```
Frontend → API (creates job) → Database → Worker (polls) → Claude Code → MCP Server → Playwright → Hypertide
```

### Key Design Decisions

- **Claude Code as browser operator** — Hypertide has no API; browser automation is the only integration path
- **MCP tools for everything** — Browser actions (navigate, click, fill) and database operations (log_step, complete_job) are exposed as MCP tools
- **Credentials from ENV, not DB** — Global credentials (Hypertide login, Bison login, API key, Stripe card) are ENV vars on the container; only job-specific data (workspace, domains) lives in the database
- **Full audit trail** — Every step is logged with a screenshot to `purchase_job_steps` for debugging and compliance

## Connection to the System

### Frontend → API → Worker

The frontend triggers a purchase via `POST /api/inbox-purchasing/smart-order`, which creates a job row in `inbox_purchase_jobs` with `status='pending'` and `worker_mode='worker'`. The worker picks up jobs by polling this table every 10 seconds.

The frontend then polls `GET /api/inbox-purchasing/status/{job_id}` to display progress to the user. The three components (frontend, API, worker) communicate entirely through the shared PostgreSQL database — no direct connections between them.

### Worker → EmailBison

During Step 7 of the purchase flow, Claude uses the EmailBison API key (`EMAILBISON_API_KEY` ENV var) to fetch available workspaces from `spellcast.hirecharm.com`, then selects the exact workspace name stored in the job record (`bison_workspace_name`). This workspace isolation prevents inboxes from being assigned to the wrong client.

### Worker → Hypertide

The Playwright browser (headed Chromium on Xvfb virtual display) navigates Hypertide's multi-step order wizard:
1. Login → Dashboard
2. Place New Order → Provider selection → Domain entry → Configuration
3. Bison workspace selection → Warmup/Outbound settings → Sender names
4. Order review → Checkout → Confirmation

### After Purchase Completes

When a purchase succeeds, the MCP server's `complete_job()` tool updates the `domains` table:
```sql
UPDATE domains SET infrastructure_type = 'entra' (or 'google'), infrastructure_set_at = NOW()
WHERE id = ANY(domain_ids)
```

This marks domains as provisioned, enabling the downstream inbox provisioning pipeline.

## Deployment

The worker runs as a Docker container on Coolify (`xo4o4wcco0scgs8gskggw00k`). Global credentials are configured as ENV vars in the Coolify dashboard. See the full deployment guide in `docs/deployment/purchase-worker-coolify.md`.

### Key Files

| File | Purpose |
|------|---------|
| `purchase_worker.py` | Daemon: polls DB, spawns Claude Code |
| `purchase_mcp/server.py` | MCP server: browser + DB tools |
| `.claude/skills/execute-purchase.md` | 14-step skill for Claude |
| `Dockerfile.purchase-worker` | Container image |
| `docker-compose.purchase-worker.yml` | Coolify production compose |
| `docker-compose.purchase-test.yml` | Local testing compose |

## Safety

- **Login guard**: Server blocks re-navigation to signin after login completes
- **Step dedup**: Database-level prevention of duplicate audit entries
- **Workspace safety**: Job fails immediately if exact workspace name not found
- **Navigation rate limiting**: 3-second cooldown between page navigations
- **Max turns**: 225 tool calls hard cap prevents runaway execution
- **Job timeout**: 600s default, configurable via `JOB_TIMEOUT` ENV

## Related

- [[architecture]] - System architecture overview
- [[system-integration]] - How Charm OS, Lead Refinery, and EmailBison connect
- [[infrastructure]] - Email infrastructure (domains, inboxes)
- [[strategy-ai-container]] - Strategy worker (same Claude Code worker pattern)

---
Tags: #architecture #purchase #worker #automation #hypertide #browser
