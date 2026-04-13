# Coolify Services

## Running Applications

| Service | Type | Purpose | Public URL |
|---------|------|---------|------------|
| charm-api | FastAPI | Main API | api.wizardgrimoire.cloud |
| charm-frontend | Next.js | User interface | app.wizardgrimoire.cloud |
| executive-dashboard | Next.js | Admin dashboard | dashboard.wizardgrimoire.cloud |
| emailbison-sync | Worker | Syncs data from EmailBison | N/A (background) |
| hypertide-worker | Worker | Domain provisioning | N/A (background) |
| price-checker | Worker | Domain price checks | N/A (background) |
| domain-worker | Worker | Domain management | N/A (background) |

## Service Details

### charm-api
- **Framework**: FastAPI (Python)
- **Port**: 8000 (internal)
- **Health Check**: `/health`
- **Database**: PostgreSQL

Key Environment Variables:
```
DATABASE_URL=postgresql://...
CORS_ORIGINS=https://app.wizardgrimoire.cloud,https://dashboard.wizardgrimoire.cloud
FRONTEND_URL=https://app.wizardgrimoire.cloud
```

### charm-frontend
- **Framework**: Next.js
- **Port**: 3000 (internal)
- **Build**: Static export

Key Environment Variables:
```
NEXT_PUBLIC_API_URL=https://api.wizardgrimoire.cloud
```

### executive-dashboard
- **Framework**: Next.js
- **Port**: 3000 (internal)
- **Build**: Static export

### emailbison-sync
- **Type**: Background worker
- **Schedule**: Continuous poll loop (30s priority tick, 5-min events, 1-hr accounts/campaigns, 30-min warmup, 24-hr engagement)
- **Purpose**: Pull inbox data from EmailBison API, manage inbox lifecycle tags, process kill triggers

#### Sync Architecture (deployed 2026-04-13)

**Concurrent workspace queue** — replaces the old sequential `switch_workspace()` model.

Old model: one shared client → `switch_workspace(A)` → sync A → `switch_workspace(B)` → sync B → ...  
New model: each workspace has a scoped EB API token → jobs claimed from `workspace_sync_queue` → up to 3 workspaces processed in parallel via `asyncio.gather`.

Key components:
- `workspace_sync_queue` table — persistent job queue with `FOR UPDATE SKIP LOCKED` for safe concurrent consumers
- `sync_status` table — tracks `last_successful_sync` per `(workspace_id, sync_type)`; used to determine which workspaces are overdue
- Priority queue — normal scheduler jobs use `priority=0`; force-refresh from client dashboard uses `priority=10` (picked up within ~30s)
- Post-hooks — `sync_all_domains()` runs after accounts sync; `sync_campaign_inbox_assignments()` runs after campaigns sync

Force-refresh API (for client dashboard):
- `POST /api/sync/workspaces/{id}/refresh` — enqueues all 5 sync types at priority=10
- `GET /api/sync/workspaces/{id}/status` — returns last sync times + pending/running queue state

Key env vars (set on emailbison-sync service):
```
SYNC_WORKSPACE_CONCURRENCY=3   # workspaces processed in parallel
SYNC_INTERVAL_PRIORITY=30      # seconds between priority-queue checks
```

#### Tagging & Kill Processing (as of 2026-04-13)
- `ENABLE_LIFECYCLE_TAGGING=true` — lifecycle tags (`live`, `reserve`, `incubating`, `flagged_*`) synced to EB
- `ENABLE_KILL_PROCESSING=false` — kill queue processing still paused pending 24h monitoring
- **Tag system**: Tags are domain-level — all inboxes on a domain share the same pool tag. Burned domains have all tags removed.
- **ESP-aware burns**: Google domains burn from 1 spam complaint, Entra domains require 3+ spam kills or >5% hard bounce rate. Circuit breakers prevent cascading burns.

#### Workspace API Keys
Each active workspace has a scoped EB API token stored in the `workspace_api_keys` DB table (migration 089). Keys are context-bound — no `switch_workspace()` calls needed. All 10 active workspaces are provisioned. New workspaces discovered via daily workspace discovery task are auto-provisioned.

### hypertide-worker
- **Type**: Background worker
- **Purpose**: Process domain purchase requests
- **Flow**: Check prices → Buy cheapest → Provision inboxes

### price-checker
- **Type**: Background worker
- **Purpose**: Check domain prices from Dynadot/Porkbun
- **Rate Limits**: Porkbun = 1 request/10 seconds

### domain-worker
- **Type**: Background worker
- **Purpose**: Domain lifecycle management

## Health Checks

```bash
# API health
curl https://api.wizardgrimoire.cloud/health

# Check all via Coolify MCP
# Use /coolify-status skill
```

## Logs

```bash
# Via Coolify MCP
# Use /coolify-logs skill

# Via Coolify UI
# Go to application > Logs tab
```

## Deployment Workflow (IMPORTANT)

### Auto Deploy is DISABLED

All 7 apps have **Auto Deploy OFF** (disabled 2026-03-04). This prevents unnecessary builds when pushing to GitHub.

**Reason**: All apps share the same monorepo (`laviefatigue/charm-email-os`). With auto-deploy enabled, pushing ANY change triggered ALL 7 apps to rebuild, overloading the VPS.

### Manual Deployment Required

After pushing code changes to GitHub:

1. **Identify which apps changed** based on your commit
2. **Deploy ONLY those apps** using Coolify MCP
3. **Wait for build to complete** before testing or triggering audits

### Deploying via Coolify MCP

```
# Deploy specific app by UUID
mcp__coolify__deploy uuid="<app-uuid>" confirm=true

# Example: Deploy charm-api
mcp__coolify__deploy uuid="nckgggwww8sggg0kc4wo00o8" confirm=true
```

### App UUIDs Reference

| App | UUID | Deploy When |
|-----|------|-------------|
| charm-api | `nckgggwww8sggg0kc4wo00o8` | `/api/**` changes |
| charm-frontend | `qw88skgwgwgk8g44c0g4wgks` | `/charm-email-os/**` changes |
| domain-worker | `u4oo8o0wocsgss8o4cs4g4oc` | `domain_worker.py` changes |
| emailbison-sync | `l4g44o00s4cccg804osswgcc` | `emailbison_sync_worker.py` or `/sync_modules/**` changes |
| executive-dashboard | `gkkgsscwck0o80gwkcsogcow` | `/executive-dashboard/**` changes |
| hypertide-worker | `e0go4ocg8cggw08kowocok4g` | `hypertide_worker.py` changes |
| price-checker | `rcckg8k84os8c400kwk4ck04` | `price_checker_worker.py` changes |

### Deployment Timing

- **Build time**: 1-5 minutes depending on app complexity
- **Frontend apps** (Next.js): ~3-5 minutes (includes npm install + build)
- **Workers** (Python): ~1-2 minutes (docker build only)
- **Always wait** for deployment to complete before testing endpoints

### After Environment Variable Changes
- Runtime vars: Restart only (no rebuild needed)
- Build-time vars (NEXT_PUBLIC_*): Full redeploy required

## Docker Cleanup

- **Automatic**: Daily at midnight UTC
- **Manual**: Coolify UI > Server > Docker Cleanup > Trigger Manual Cleanup
- **Cleans**: Stopped containers, unused images, build cache
