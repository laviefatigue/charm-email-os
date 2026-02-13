---
title: Purchase Worker Coolify Deployment (Deprecated)
created: 2026-01-29
updated: 2026-02-11
tags: [deployment, purchase, coolify, docker, deprecated]
---

# Purchase Worker Coolify Deployment (DEPRECATED)

> **⚠️ DEPRECATED**: Coolify deployments are no longer active. Workers now run locally via Docker. See [[../local-development/workers]] for the current localhost-first setup.

---

*Legacy documentation below - for reference only*

Deploying the purchase worker to production via Coolify self-hosted PaaS.

## Prerequisites

- Coolify dashboard access: `https://panel.laviefatigue.com`
- Purchase worker Coolify application UUID: `xo4o4wcco0scgs8gskggw00k`
- GitHub repository pushed to `master` branch

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Coolify (panel.laviefatigue.com)                             │
│  VPS: 31.97.142.123                                          │
│                                                              │
│  ┌────────────────────────────────────────────────────┐      │
│  │ charm-api (ccssgc4gowsog04wck400o0w)               │      │
│  │ FastAPI → POST /api/inbox-purchasing/smart-order    │      │
│  │ Creates: inbox_purchase_jobs (status=pending)       │      │
│  └────────────────────────┬───────────────────────────┘      │
│                           │                                   │
│               PostgreSQL (31.97.142.123:5432)                 │
│                           │                                   │
│  ┌────────────────────────▼───────────────────────────┐      │
│  │ charm-purchase-worker (xo4o4wcco0scgs8gskggw00k)   │      │
│  │ Polls DB → Spawns hypertide_playwright.py           │      │
│  │ Direct Playwright automation (no LLM dependency)    │      │
│  └────────────────────────────────────────────────────┘      │
│                                                              │
│  ┌────────────────────────────────────────────────────┐      │
│  │ charm-frontend (jskswosswg80cg8wwk8g8kww)          │      │
│  │ Next.js → Polls /status/{job_id} for progress      │      │
│  └────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

## Deployment Steps

### 1. Push Code to GitHub

The purchase worker code is in the main `charm-email-os` repository. Push all changes to `master`:

```bash
cd D:\Work\charm-email-os
git add purchase_worker.py hypertide_playwright.py \
       Dockerfile.purchase-worker docker-compose.purchase-worker.yml \
       requirements-purchase-worker.txt
git commit -m "Purchase worker: <description>"
git push origin master
```

### 2. Create Application in Coolify (First Time Only)

If the purchase worker application doesn't exist yet in Coolify:

1. Go to Coolify dashboard → Project → **Add New Resource**
2. Select **Docker Compose** deployment type
3. Point to `docker-compose.purchase-worker.yml` in the repo
4. Set the Dockerfile path to `Dockerfile.purchase-worker`
5. Note the UUID assigned (currently `xo4o4wcco0scgs8gskggw00k`)

### 3. Configure Environment Variables in Coolify

Navigate to the purchase worker application in Coolify → **Settings** → **Environment Variables**.

Add these variables:

#### Database Connection

| Variable | Value |
|----------|-------|
| `POSTGRES_HOST` | `31.97.142.123` |
| `POSTGRES_PORT` | `5432` |
| `POSTGRES_DB` | `postgres` |
| `POSTGRES_USER` | `postgres` |
| `POSTGRES_PASSWORD` | *(database password)* |

#### Worker Configuration

| Variable | Value |
|----------|-------|
| `POLL_INTERVAL` | `10` |
| `JOB_TIMEOUT` | `1800` |
| `JOB_COOLDOWN` | `30` |
| `ALERT_WEBHOOK_URL` | *(Discord/Slack webhook, optional)* |

#### Credentials (Injected via ENV)

| Variable | Value | Notes |
|----------|-------|-------|
| `HYPERTIDE_EMAIL` | `chris@hirecharm.com` | Hypertide login |
| `HYPERTIDE_PASSWORD` | *(secret)* | Hypertide login |
| `BISON_USERNAME` | `elliott@hirecharm.com` | EmailBison login |
| `BISON_PASSWORD` | *(secret)* | EmailBison login |
| `BISON_URL` | `https://spellcast.hirecharm.com` | EmailBison instance |
| `EMAILBISON_API_KEY` | `17\|MJ4B2ye...` | Workspace fetch API key |

### 4. Deploy

**Via Coolify Dashboard:**
Coolify → Application → click **Deploy**

**Via Coolify MCP:**
```python
mcp__coolify__trigger_deployment(
    application_uuid="xo4o4wcco0scgs8gskggw00k",
    confirm=True
)
```

### 5. Pinned Commit SHA

If the application has `git_commit_sha` pinned, update it to the latest commit. Use the **full 40-character SHA** (Coolify's shallow clone cannot resolve short SHAs):

```python
mcp__coolify__update_application(
    application_uuid="xo4o4wcco0scgs8gskggw00k",
    git_commit_sha="<full-40-char-sha>",
    confirm=True
)
```

## Connecting to Frontend and Backend

### Frontend Connection

The frontend triggers purchases via the API. The connection chain:

```
Frontend (charm-frontend)
    │
    ├─ User selects domains in "Setup Inboxes" table
    ├─ InboxProvisionModal shows preview (provider, orders, cost)
    │
    ├─ POST /api/inbox-purchasing/smart-order
    │   Body: { client_id, domain_ids, provider_type, override_age_check }
    │
    ├─ Receives: { job_id, status: 'pending' }
    │
    ├─ Polls: GET /api/inbox-purchasing/status/{job_id}
    │   Every 3 seconds until status is terminal
    │   Shows: current_step, progress bar, order count
    │
    ├─ On 'awaiting_checkout':
    │   Shows "Payment Required" card with "Open Stripe Checkout" button
    │
    └─ On 'completed' or 'failed':
       Shows final status with toast notification
```

The frontend does NOT communicate directly with the purchase worker. It only talks to the API, which writes to the database. The worker picks up jobs from the same database.

### Database Connection

All three components (API, worker, frontend polling) connect to the same PostgreSQL database:

| Component | Connection |
|-----------|-----------|
| charm-api | `POSTGRES_HOST` ENV var in Coolify settings |
| charm-purchase-worker | `POSTGRES_HOST` ENV var in Coolify settings |
| charm-frontend | Reads via API (no direct DB connection) |

**Critical:** The API and worker MUST point to the same database for job handoff to work.

## Monitoring

### Check Worker Status

```bash
# View logs (Coolify dashboard)
# Application → Logs tab

# Via Coolify MCP
mcp__coolify__get_application_logs(
    application_uuid="xo4o4wcco0scgs8gskggw00k"
)

# Via SSH
ssh root@31.97.142.123
docker logs -f $(docker ps -q --filter "name=purchase-worker")
```

### Health Check

The container has a built-in health check:
```yaml
healthcheck:
  test: ["CMD", "pgrep", "-f", "python3.*purchase_worker.py"]
  interval: 30s
  timeout: 10s
  start_period: 10s
  retries: 3
```

### What Good Logs Look Like

```
INFO - Purchase Worker starting...
INFO - Database: 31.97.142.123:5432/postgres
INFO - Poll interval: 10 seconds
INFO - Job timeout: 1800 seconds
INFO - Playwright script: /app/hypertide_playwright.py
INFO - Purchase tables ready
INFO - No stale jobs found
INFO - Worker ready - polling for purchase jobs...
INFO - Processing job <UUID> for <Company> (entra, N domains)
INFO - Spawning Playwright script for job <UUID>...
INFO - Job <UUID> completed (exit 0)
INFO - Job cooldown: waiting 30s before next poll...
```

### Check Job Status

```bash
# From local machine (with DB access)
python tests/insert_test_purchase_job.py --status <JOB_ID>

# From the VPS
docker exec <container_id> python3 -c "
import psycopg2, os, json
conn = psycopg2.connect(host=os.environ['POSTGRES_HOST'], port=5432,
    database='postgres', user='postgres', password=os.environ['POSTGRES_PASSWORD'])
cur = conn.cursor()
cur.execute(\"SELECT status, current_step, errors FROM inbox_purchase_jobs ORDER BY created_at DESC LIMIT 5\")
for row in cur.fetchall():
    print(f'{row[0]:12} | {row[1] or \"-\":20} | {row[2] or \"-\"}')
conn.close()
"
```

## Troubleshooting

### Worker Not Processing Jobs

1. **Container running?** Check Coolify dashboard or `docker ps`
2. **Pending jobs exist?** Query `inbox_purchase_jobs WHERE status='pending' AND worker_mode='worker'`
3. **ENV vars set?** Check: `docker exec <id> env | grep HYPERTIDE`
4. **Stale jobs blocking?** Worker logs will show "Cleaned up N stale job(s)" on restart

### Job Stuck in Processing

```sql
-- Check how long it's been processing
SELECT id, status, started_at, NOW() - started_at as duration
FROM inbox_purchase_jobs
WHERE status = 'processing';

-- If stuck > JOB_TIMEOUT, restart the worker container.
-- cleanup_stale_jobs() will recover them automatically.

-- Manual reset to pending for retry:
UPDATE inbox_purchase_jobs
SET status = 'pending', current_step = NULL, started_at = NULL
WHERE id = '<job_id>';

-- Also clear audit steps for clean retry:
DELETE FROM purchase_job_steps WHERE job_id = '<job_id>';
```

### Login Failed

- Verify `HYPERTIDE_EMAIL` and `HYPERTIDE_PASSWORD` ENV vars are correct
- Check if Hypertide has changed their login flow (review screenshots in `purchase_job_steps`)
- Try logging in manually at `https://app2.hypertide.io/signin`

### Workspace Not Found

- Verify `bison_workspace_name` in the job matches an actual workspace in EmailBison
- Check `EMAILBISON_API_KEY` is valid
- Ensure `BISON_URL` is `https://spellcast.hirecharm.com`

### Credential ENV Vars Not Working

Verify inside the container:

```bash
docker exec <id> env | grep -E 'HYPERTIDE|BISON|EMAILBISON'
```

If values are empty, check that they're configured in Coolify's Environment Variables section for this application.

## Updating Credentials

When credentials change (new password, etc.):

1. Update the ENV variable in Coolify → Application → Environment Variables
2. Redeploy the application (Coolify rebuilds the container with new ENV)
3. No code changes needed — the script reads ENV at runtime

## Related

- [[../architecture/purchase-worker]] - Purchase worker architecture
- [[../architecture/claude-code-worker]] - Worker pattern overview
- [[../concepts/inbox-provisioning]] - Inbox provisioning concepts
- [[../infrastructure/coolify]] - Coolify platform
- [[index]] - Deployment overview
