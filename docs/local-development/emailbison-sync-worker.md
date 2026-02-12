---
title: EmailBison Sync Worker
created: 2026-02-12
updated: 2026-02-12
tags: [worker, emailbison, sync, health]
---

# EmailBison Sync Worker

The EmailBison Sync Worker keeps the local database synchronized with EmailBison (the source of truth for inbox/campaign data).

## Purpose

- **Account Sync**: Keep `sender_accounts` table fresh with EmailBison data
- **Campaign Sync**: Sync campaign metrics and snapshots
- **Event Sync**: Track replies, bounces, and response messages
- **Health Checks**: Detect kill triggers and critical health issues
- **Kill Queue**: Process inbox deletion with 24hr tagging window
- **Retention**: Clean up old data based on retention policies

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     EMAILBISON SYNC WORKER                       │
├─────────────────────────────────────────────────────────────────┤
│  Main Loop (every 5 min):                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Events Sync (5 min) → Full Sync (1 hr) → Health (15 min)   ││
│  │       → Kill Queue (30 min) → Retention (daily)             ││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│  Modules:                                                        │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐│
│  │  Accounts   │ │  Campaigns  │ │   Events    │ │   Health    ││
│  │    Sync     │ │    Sync     │ │    Sync     │ │   Checks    ││
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘│
│  ┌─────────────┐ ┌─────────────┐                                │
│  │    Kill     │ │  Retention  │                                │
│  │  Processor  │ │   Manager   │                                │
│  └─────────────┘ └─────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

## Sync Intervals

| Operation | Interval | Description |
|-----------|----------|-------------|
| Events Sync | 5 min | Replies, bounces, response messages |
| Full Sync | 1 hour | Accounts, domains, campaign metrics |
| Health Checks | 15 min | Kill trigger detection, workspace health |
| Kill Queue | 30 min | Tag inboxes, process 24hr deletions |
| Retention | Daily | Clean up old audit logs, bounces |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | postgres | Database host |
| `POSTGRES_PORT` | 5432 | Database port |
| `POSTGRES_USER` | postgres | Database user |
| `POSTGRES_PASSWORD` | - | Database password |
| `POSTGRES_DB` | postgres | Database name |
| `EMAILBISON_API_KEY` | - | **Required** EmailBison API token |
| `EMAILBISON_API_URL` | https://spellcast.hirecharm.com/api | EmailBison API URL |
| `SYNC_INTERVAL_EVENTS` | 300 | Events sync interval (seconds) |
| `SYNC_INTERVAL_FULL` | 3600 | Full sync interval (seconds) |
| `SYNC_INTERVAL_HEALTH` | 900 | Health check interval (seconds) |
| `SYNC_INTERVAL_KILL` | 1800 | Kill queue interval (seconds) |
| `SLACK_WEBHOOK_URL` | - | Optional Slack alerts |
| `RETENTION_DAYS_AUDIT` | 90 | Days to keep audit logs |
| `RETENTION_DAYS_BOUNCES` | 90 | Days to keep bounce messages |

### Docker Compose Configuration

```yaml
emailbison-sync:
  build:
    context: .
    dockerfile: Dockerfile.emailbison-sync
  container_name: charm-emailbison-sync
  restart: unless-stopped
  environment:
    - POSTGRES_HOST=postgres
    - POSTGRES_PORT=5432
    - POSTGRES_USER=postgres
    - POSTGRES_PASSWORD=localdevpassword
    - POSTGRES_DB=postgres
    - EMAILBISON_API_KEY=${EMAILBISON_API_KEY:-}
    - EMAILBISON_API_URL=https://spellcast.hirecharm.com/api
    - SYNC_INTERVAL_EVENTS=300
    - SYNC_INTERVAL_FULL=3600
    - SYNC_INTERVAL_HEALTH=900
    - SYNC_INTERVAL_KILL=1800
  depends_on:
    postgres:
      condition: service_healthy
  networks:
    - charm-network
```

## Database Tables

The sync worker uses these tables:

| Table | Purpose |
|-------|---------|
| `sync_audit_log` | Tracks every sync operation |
| `response_messages` | Stores reply/bounce content |
| `kill_queue` | Tracks inboxes queued for deletion |
| `sync_status` | Last sync timestamps per workspace |

### Schema Migration

```bash
# Apply the sync audit schema
docker exec charm-postgres psql -U postgres -d postgres \
  -f /migrations/020_sync_audit_schema.sql
```

## Operations

### Start the Worker

```bash
# Start with docker compose
docker compose -f docker-compose.local.yml up -d emailbison-sync

# Check status
docker logs -f charm-emailbison-sync
```

### Run Single Pass

```bash
# Run once and exit (useful for testing)
docker exec charm-emailbison-sync python emailbison_sync_worker.py --once
```

### Monitor Logs

```bash
# Follow logs
docker logs -f charm-emailbison-sync

# Show last 50 lines
docker logs charm-emailbison-sync --tail 50
```

## Module Details

### Account Sync Module

Syncs sender accounts from all EmailBison workspaces:

- Creates missing accounts in local DB
- Updates health scores, bounce rates, status
- Marks stale accounts as inactive
- Links accounts to domains

### Campaign Sync Module

Syncs campaign data and metrics:

- Creates/updates `emailbison_campaigns`
- Creates metric snapshots in `campaign_snapshots`
- Tracks send counts, bounces, replies

### Event Sync Module

Syncs replies and bounces with full message content:

- Fetches from inbox/bounced folders
- Classifies bounces (hard_unknown, hard_blocked, soft_full, soft_temp)
- Stores full message body in `response_messages`

### Health Check Module

Detects kill triggers and health issues:

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Hard bounces (24h) | >= 2 | Queue for kill |
| Hard bounce rate (7d) | > 0.5% | Queue for kill |
| Total bounce rate (7d) | > 5% | Queue for kill |
| Fresh inbox hard bounce | 1 (if <14 days old) | Queue for kill |

### Kill Processor

Implements 24-hour kill queue:

1. **Pending** → Tag inbox in EmailBison with `delete_queue_YYYYMMDD`
2. **Tagged** → Wait 24 hours
3. **Delete** → Remove from EmailBison after 24 hours
4. **Update** → Mark `sender_accounts.inbox_state = 'dead'`

### Retention Manager

Cleans up old data:

| Data | Retention | Notes |
|------|-----------|-------|
| Response messages (non-bounce) | Indefinite | Keep for copy analysis |
| Bounce messages | 90 days | No long-term value |
| Audit logs | 90 days | Configurable |
| Kill queue (completed) | 90 days | Cleanup completed entries |

## Slack Alerts

When configured, sends alerts for:

- **Error**: Sync module failures
- **Warning**: Kill triggers fired
- **Critical**: Workspace health dropped to critical

Alert format:
```
🔔 Inbox Kill Trigger Fired

Inbox `user@domain.com` has been queued for deletion

• Trigger: hard_bounces_24h
• Value: 3
• Status: Tagged for 24h queue
```

## Troubleshooting

### "Illegal header value" Error

The API key is missing or invalid:

```bash
# Check if API key is set
docker exec charm-emailbison-sync printenv | grep EMAILBISON

# Verify it's in .env.local
cat .env.local | grep EMAILBISON_API_KEY
```

### Campaign Sync Failures

Check workspace context switching:

```bash
# Verify workspaces have emailbison_workspace_id
docker exec charm-postgres psql -U postgres -d postgres -c \
  "SELECT workspace_name, emailbison_workspace_id FROM workspaces;"
```

### Health Check Not Running

Verify the health check interval hasn't elapsed:

```bash
docker logs charm-emailbison-sync --tail 100 | grep "Health checks"
```

## Files

| File | Purpose |
|------|---------|
| `emailbison_sync_worker.py` | Main orchestrator |
| `Dockerfile.emailbison-sync` | Container definition |
| `requirements-sync.txt` | Python dependencies |
| `sync_modules/__init__.py` | Module exports |
| `sync_modules/emailbison_client.py` | API client |
| `sync_modules/sync_accounts.py` | Account sync |
| `sync_modules/sync_campaigns.py` | Campaign sync |
| `sync_modules/sync_events.py` | Event sync |
| `sync_modules/health_checks.py` | Health evaluation |
| `sync_modules/kill_processor.py` | Kill queue processing |
| `sync_modules/retention.py` | Data retention |
| `sync_modules/audit_logger.py` | Audit logging |
| `sync_modules/slack_alerter.py` | Slack notifications |

## Related

- [[quick-start]] - Complete Local Setup
- [[workers]] - All Workers Reference
- [[environment-variables]] - All Environment Variables
- [[../database/migrations]] - Database Migrations
