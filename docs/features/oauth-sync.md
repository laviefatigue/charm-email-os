---
title: OAuth Configuration Sync
created: 2026-02-12
updated: 2026-02-12
tags: [feature, oauth, sync, emailbison, playwright]
---

# OAuth Configuration Sync

Automatic discovery and verification of Google OAuth Client IDs from EmailBison workspaces.

## Overview

The EmailBison API does **not** expose OAuth configuration (Google Client IDs). This information is only visible in the EmailBison UI at `/sender-email-connect/google/oauth`. The OAuth Sync module uses browser automation (Playwright) to scrape this configuration.

## Key Finding

All workspaces share the same Google Client ID at the platform level:
- **Client ID**: `575201020991-j9v3o8mu7cr34f7ngefpohauj497bu5i.apps.googleusercontent.com`
- **App Name**: `Charm`

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                        OAUTH SYNC FLOW                                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  1. Client Creation                                                   │
│     ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│     │   Create    │───▶│   Create    │───▶│   Queue     │            │
│     │   Client    │    │  Workspace  │    │ OAuth Sync  │            │
│     └─────────────┘    └─────────────┘    └─────────────┘            │
│                                                  │                    │
│  2. Worker Processing (every 5 min)              ▼                    │
│     ┌─────────────────────────────────────────────────────────┐      │
│     │  oauth_sync_queue                                        │      │
│     │  ┌──────────┬─────────────────┬─────────┬──────────┐    │      │
│     │  │ pending  │ emailbison_id   │ retries │ error    │    │      │
│     │  └──────────┴─────────────────┴─────────┴──────────┘    │      │
│     └─────────────────────────────────────────────────────────┘      │
│                                                  │                    │
│  3. Browser Automation                           ▼                    │
│     ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│     │   Login     │───▶│   Switch    │───▶│   Scrape    │            │
│     │   (once)    │    │  Workspace  │    │  Client ID  │            │
│     └─────────────┘    └─────────────┘    └─────────────┘            │
│                                                  │                    │
│  4. Store Result                                 ▼                    │
│     ┌─────────────────────────────────────────────────────────┐      │
│     │  oauth_configs                                           │      │
│     │  ┌──────────────┬────────────────────┬──────────────┐   │      │
│     │  │ workspace_id │ google_client_id   │ verified_at  │   │      │
│     │  └──────────────┴────────────────────┴──────────────┘   │      │
│     └─────────────────────────────────────────────────────────┘      │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

## Sync Intervals

| Operation | Interval | Description |
|-----------|----------|-------------|
| Queue Processing | 5 min | Process newly queued workspaces |
| Monthly Verification | 30 days | Re-verify all existing configs |

## Database Schema

### oauth_configs

Stores the scraped OAuth configuration per workspace.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | FK to workspaces |
| `google_client_id` | VARCHAR(255) | Google OAuth Client ID |
| `google_app_name` | VARCHAR(100) | OAuth app display name |
| `microsoft_client_id` | VARCHAR(255) | Future: Microsoft OAuth |
| `microsoft_app_name` | VARCHAR(100) | Future: Microsoft app name |
| `last_verified_at` | TIMESTAMPTZ | Last verification timestamp |
| `verification_status` | VARCHAR(20) | pending, verified, changed, error |
| `previous_google_client_id` | VARCHAR(255) | For change detection |
| `scraped_at` | TIMESTAMPTZ | Initial scrape timestamp |

### oauth_sync_queue

Queue for async OAuth discovery jobs.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | FK to workspaces |
| `emailbison_workspace_id` | INTEGER | EmailBison workspace ID |
| `status` | VARCHAR(20) | pending, processing, completed, failed |
| `retry_count` | INTEGER | Current retry attempt |
| `max_retries` | INTEGER | Max retries (default: 3) |
| `error_message` | TEXT | Last error message |

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EMAILBISON_API_URL` | Yes | EmailBison base URL |
| `EMAILBISON_BROWSER_EMAIL` | Yes | Login email for browser automation |
| `EMAILBISON_BROWSER_PASSWORD` | Yes | Login password for browser automation |
| `SYNC_INTERVAL_OAUTH_QUEUE` | No | Queue poll interval (default: 300s) |
| `SYNC_INTERVAL_OAUTH_VERIFY` | No | Verification interval (default: 30 days) |

### Docker Compose

```yaml
emailbison-sync:
  env_file:
    - .env.local  # Contains EMAILBISON_BROWSER_EMAIL and PASSWORD
  environment:
    - SYNC_INTERVAL_OAUTH_QUEUE=300
    - SYNC_INTERVAL_OAUTH_VERIFY=2592000
```

### Required .env.local Variables

```bash
EMAILBISON_BROWSER_EMAIL=your-email@example.com
EMAILBISON_BROWSER_PASSWORD=your-password
```

## API Integration

OAuth sync is automatically triggered in three places:

### 1. Client Creation (POST /clients)

When a new client is created without a workspace_id, the system:
1. Creates an EmailBison workspace
2. Creates a local workspace record
3. **Queues OAuth sync** for the new workspace

### 2. Create Workspace for Client (POST /clients/{id}/create-workspace)

When creating a workspace for an existing client:
1. Creates EmailBison workspace
2. Creates local workspace
3. Links client to workspace
4. **Queues OAuth sync**

### 3. Import Workspace (POST /clients/{id}/import-workspace)

When importing an existing EmailBison workspace:
1. Creates local workspace record (if needed)
2. Links client to workspace
3. **Queues OAuth sync**

## Browser Automation

The `OAuthSyncModule` uses Playwright with Chromium:

```python
async def _scrape_oauth_config(self, emailbison_workspace_id: int) -> dict:
    """
    Navigate to OAuth settings page and extract Client ID.

    URL: /sender-email-connect/google/oauth
    Selector: input[value*=".apps.googleusercontent.com"]
    """
```

### Scraping Process

1. Launch headless Chromium browser
2. Login to EmailBison (once per session)
3. Switch to target workspace via API
4. Navigate to OAuth settings page
5. Extract Client ID from input field
6. Store in `oauth_configs` table

## Verification Process

Monthly verification detects configuration changes:

1. Fetch all workspaces with existing `oauth_configs`
2. Re-scrape each workspace's OAuth config
3. Compare with stored values
4. If changed:
   - Store previous value in `previous_google_client_id`
   - Update `verification_status` to 'changed'
   - Send Slack alert

## Files

| File | Purpose |
|------|---------|
| `sync_modules/sync_oauth.py` | OAuthSyncModule implementation |
| `migrations/023_oauth_configs_schema.sql` | Database schema |
| `api/routes/clients.py:queue_oauth_sync()` | Queue helper function |
| `Dockerfile.emailbison-sync` | Container with Playwright |
| `requirements-sync.txt` | Includes `playwright>=1.40.0` |

## Troubleshooting

### "Browser credentials not configured"

```bash
# Check environment variables
docker exec charm-emailbison-sync printenv | grep EMAILBISON_BROWSER

# Add to .env.local
echo "EMAILBISON_BROWSER_EMAIL=your-email" >> .env.local
echo "EMAILBISON_BROWSER_PASSWORD=your-password" >> .env.local

# Restart worker
docker compose -f docker-compose.local.yml restart emailbison-sync
```

### OAuth Scraping Fails

Check for login issues:

```bash
# View detailed logs
docker logs charm-emailbison-sync --tail 100 | grep -i oauth
```

Common issues:
- Invalid credentials
- Rate limiting (too many login attempts)
- UI changes (selectors may need updating)

### Queue Stuck in Processing

```sql
-- Check queue status
SELECT * FROM oauth_sync_queue WHERE status = 'processing';

-- Reset stuck items
UPDATE oauth_sync_queue
SET status = 'pending', started_at = NULL
WHERE status = 'processing'
AND started_at < NOW() - INTERVAL '10 minutes';
```

## Related

- [[../local-development/emailbison-sync-worker]] - Sync worker documentation
- [[health-monitoring]] - Health monitoring (similar pattern)
- [[../database/migrations]] - Database migrations
