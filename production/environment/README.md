# Environment Variables Reference

## Production Environment

All production environment variables are managed in Coolify UI, not in files.

## Variables by Service

### charm-api

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |
| `CORS_ORIGINS` | Allowed CORS origins | `https://app.wizardgrimoire.cloud,https://dashboard.wizardgrimoire.cloud` |
| `FRONTEND_URL` | Frontend URL for redirects | `https://app.wizardgrimoire.cloud` |
| `EMAILBISON_API_KEY` | EmailBison API key | `eb_...` |
| `HYPERTIDE_API_KEY` | HyperTide API key | (secret) |
| `DYNADOT_API_KEY` | Dynadot API key | (secret) |
| `PORKBUN_API_KEY` | Porkbun API key | (secret) |
| `PORKBUN_SECRET_KEY` | Porkbun secret key | (secret) |

### charm-frontend

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | API endpoint | `https://api.wizardgrimoire.cloud` |

**Note**: `NEXT_PUBLIC_*` variables are baked in at build time. Changes require full redeploy.

### executive-dashboard

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | API endpoint | `https://api.wizardgrimoire.cloud` |

### Workers (emailbison-sync, hypertide-worker, etc.)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `EMAILBISON_API_KEY` | EmailBison API key |
| `HYPERTIDE_API_KEY` | HyperTide API key |
| Various API keys | Per-worker requirements |

## EmailBison Workspace API Keys

Workspace-scoped EB API tokens are stored in the **`workspace_api_keys` database table** (migration 089) — not in Coolify env vars.

| Variable | Service | Purpose |
|----------|---------|---------|
| `EMAILBISON_API_KEY` | emailbison-sync | Admin-level key used for workspace discovery and tagging modules |

The per-workspace scoped keys in `workspace_api_keys` are used by the concurrent sync queue (migration 091). All 10 active workspaces are provisioned. Keys are context-bound — no `switch_workspace()` calls needed. New workspaces discovered by the daily workspace discovery task are auto-provisioned.

To check key status:
```sql
SELECT w.workspace_name, w.emailbison_workspace_id::text as eb_id,
       (wak.id IS NOT NULL) as has_key
FROM workspaces w
LEFT JOIN workspace_api_keys wak ON wak.workspace_id = w.id AND wak.is_active = TRUE
WHERE w.is_active = TRUE ORDER BY w.workspace_name;
```

### emailbison-sync — New Env Vars (added 2026-04-13)

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_WORKSPACE_CONCURRENCY` | `3` | Workspaces processed in parallel by the queue |
| `SYNC_INTERVAL_PRIORITY` | `30` | Seconds between priority-queue polls (force-refresh latency) |

## Local Development

For local development, use these files in project root:
- `.env` - Default environment
- `.env.local` - Local overrides (gitignored)
- `.env.production` - Production reference (gitignored)

## Secrets Management

| Secret Type | Storage |
|-------------|---------|
| API keys | Coolify environment variables |
| Database credentials | Coolify environment variables |
| Cloudflare tokens | MCP config (~/.mcp.json) |
| Service tokens | Cloudflare dashboard |

## Updating Production Variables

1. Go to https://coolify.wizardgrimoire.cloud
2. Authenticate with Google
3. Select application
4. Click "Environment Variables"
5. Add/update variable
6. Click "Save"
7. **Important**: Redeploy application

### Build-time Variable Changes

For `NEXT_PUBLIC_*` variables:
1. Update in Coolify
2. Trigger full rebuild (not just restart)
3. This rebuilds the Next.js application with new values

### Runtime Variable Changes

For other variables:
1. Update in Coolify
2. Restart application (faster than rebuild)

## Verification

After updating variables, verify:

```bash
# Check API health
curl https://api.wizardgrimoire.cloud/health

# Check frontend is calling correct API
# Open browser dev tools > Network tab
# Look for requests to api.wizardgrimoire.cloud
```
