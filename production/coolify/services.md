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
| incubation-watcher | App (PROPOSED — not yet deployed) | Per-workspace incubation graduation, extracted from emailbison-sync's lifecycle_tag_sync. v1 operator-invoked CLI; v2 daemon. | N/A |
| eod-reapply | CLI / on-demand | EOD campaign sender-tag reapply (operator-invoked) | N/A (no service) |

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

#### Tagging & Kill Processing (as of 2026-04-30)
- `ENABLE_LIFECYCLE_TAGGING=true` — lifecycle tags (`live`, `reserve`, `incubating`, `flagged_*`) synced to EB
- `ENABLE_KILL_PROCESSING=true` — kill queue processing active (since 2026-04-13 stabilization)
- **Tag system**: Tags are per-inbox per ADR-006 — `inventory_pool_status` is the per-inbox authority. Cross-domain promotion allowed within a workspace.
- **ESP-aware burns**: Google domains burn from 1 spam complaint (small-fleet). Microsoft Entra requires rate-based threshold or 3+ kill-equivalents.

#### Connection State (as of 2026-04-30 — ADR-009)
Connection state and kill state are independent tracks. Disconnect duration drives notifications, not kills.

- `disconnected_timeout` REMOVED as kill trigger. Connection-only conditions never produce `inbox_state='dead'`.
- Notification ladder (planned, Phase 2 of [docs/plans/connection-state-machine.md](../../docs/plans/connection-state-machine.md)): 24h → 3d → 7d → 20d Slack alerts + EB tags.
- The system NEVER auto-removes inboxes from EB or auto-cancels Hypertide subscriptions. Operator handles all destructive cleanup.
- ~1,200 fleet-wide rows currently flagged `kill_trigger='disconnected_timeout'` while EB-side Connected — operator-driven restoration via [scripts/generate_zombie_review_csv.py](../../scripts/generate_zombie_review_csv.py).

#### Silent-Failure Hardening (as of 2026-04-30)
- `lifecycle_tag_sync._graduate_mature_inboxes` now detects EB 404 from `tag_inbox` and skips with `[ORPHAN]` log + audit error rather than retrying forever. The DB row falls out via `sync_accounts.mark_stale_accounts` on its next cycle.

#### Accuracy Audits (READ-ONLY, on-demand)
- [scripts/audit_system_accuracy.py](../../scripts/audit_system_accuracy.py) — fleet DB↔EB drift gate (CONN ≥99%, DISC ≥95%, MEMBERSHIP ≥98%, POOL DRIFT ≤1%). Exit code 1 if any workspace fails. Output: `docs/audits/<date>-system-accuracy-snapshot.json`.
- [scripts/generate_zombie_review_csv.py](../../scripts/generate_zombie_review_csv.py) — per-workspace operator review CSV for the disconnected_timeout zombies. `operator_decision` column blank for fill-in.

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

### eod-reapply
- **Type**: CLI / on-demand container
- **Purpose**: Reapply a campaign's `live`-tagged sender set as its EmailBison sender attachment. Closes the loop that `kill_processor` leaves open: dead inboxes lose the `live` tag in EB but stay attached to active campaigns until something reconciles them.
- **Status**: v1 — operator-invoked, not a continuous service. v2 (the scheduler) is documented in [docs/plans/eod-campaign-reapply.md](../../docs/plans/eod-campaign-reapply.md).
- **Source**: [apps/eod-reapply/](../../apps/eod-reapply/) — see README + STAGING-RUNBOOK.

#### Subcommands
- `eod-reapply check --workspace <name> [--campaign-id N]` — read-only pre-flight (DB + EB auth + campaign + tag + expected diff). Never mutates. Run before any `--apply`.
- `eod-reapply reapply --workspace <name> --campaign-id N [--apply]` — pause → diff → attach → remove → verify → resume. Default dry-run; `--apply` is opt-in.

#### Deployment patterns

**Pattern A — sleeping container, exec on demand** (recommended for v1):
- Build context: `apps/eod-reapply/`
- Dockerfile: `apps/eod-reapply/Dockerfile`
- Service type: "Dockerfile" (not docker-compose)
- Override CMD: `sleep infinity` so the container stays up
- Env vars (set in Coolify UI from secrets): `DATABASE_URL`, `EMAILBISON_API_URL`
- No public URL, no health check
- Restart policy: `unless-stopped`
- Operator runs commands via `coolify exec <service> eod-reapply check --workspace Sammy`

**Pattern B — Run as needed** (no continuous resource use):
- Build the image and push to a registry, OR build on the operator's host
- Operator runs `docker run --rm -e DATABASE_URL=... <image> reapply ...` from a host with prod DB access (e.g. a jumphost or one of the existing worker containers via exec)

#### Exit codes (load-bearing for any future scheduler)
| Code | Subcommand | Meaning |
|---|---|---|
| 0 | both | Success / clean no-op |
| 1 | check | At least one warning |
| 1 | reapply | Dry-run completed and would have made changes |
| 2 | both | Failure but no campaign mutation occurred (or check has FAILs) |
| 3 | reapply | **CRITICAL** — campaign may be left paused. Operator must verify and resume. |

#### Required env vars
```
DATABASE_URL=postgresql://...                          # same DB as charm-api / emailbison-sync
EMAILBISON_API_URL=https://spellcast.hirecharm.com/api # same as emailbison-sync
```

#### Reads (no writes in v1)
- `workspaces` — workspace name → id
- `workspace_api_keys` — workspace-scoped Sanctum token
- `campaign_inboxes` — only via existing operational queries (not by this app)
- `sender_accounts.inventory_pool_status` — only via existing operational queries

v1 owns no tables. Operational metrics (daily live-set shrinkage etc.) are answered by SQL against existing tables — see app README "Tracking & operational metrics" section.

#### Pre-staging gate
**Not yet promoted past L4** (mocked + e2e tests). L5 (real-EB staging) is documented in [apps/eod-reapply/STAGING-RUNBOOK.md](../../apps/eod-reapply/STAGING-RUNBOOK.md) and is the mandatory gate before any production workspace touches the tool.

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
