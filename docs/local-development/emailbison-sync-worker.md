---
title: EmailBison Sync Worker
created: 2026-02-12
updated: 2026-02-12
tags: [worker, emailbison, sync, health, database, kill-triggers]
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
| `KILL_THRESHOLD_SPAM` | 1 | Spam complaints to trigger kill (v3: 1 = death) |
| `KILL_THRESHOLD_HARD_BLOCKED_24H` | 1 | Spam/policy rejections in 24h (reputation damage) |
| `KILL_THRESHOLD_HARD_UNKNOWN_24H` | 3 | Bad addresses in 24h (list quality issue) |
| `KILL_THRESHOLD_HARD_BOUNCES_24H` | 2 | Combined hard bounces fallback threshold |
| `KILL_THRESHOLD_HARD_BOUNCE_RATE` | 0.005 | Hard bounce rate threshold (0.5%) |
| `KILL_THRESHOLD_TOTAL_BOUNCE_RATE` | 0.05 | Total bounce rate threshold (5%) |
| `KILL_THRESHOLD_MIN_SENDS` | 50 | Min sends before rate triggers apply |
| `KILL_THRESHOLD_FRESH_INBOX_DAYS` | 14 | Days before inbox is "not fresh" |

### Docker Compose Configuration

```yaml
emailbison-sync:
  build:
    context: .
    dockerfile: Dockerfile.emailbison-sync
  container_name: charm-emailbison-sync
  restart: unless-stopped
  env_file:
    - .env.local  # EMAILBISON_API_KEY loaded from here
  environment:
    - POSTGRES_HOST=postgres
    - POSTGRES_PORT=5432
    - POSTGRES_USER=postgres
    - POSTGRES_PASSWORD=localdevpassword
    - POSTGRES_DB=postgres
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

> **Note**: The `EMAILBISON_API_KEY` is loaded from `.env.local` via `env_file`. This ensures the API key persists across container restarts without needing to set it in the shell environment.

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
- **Calculates health scores locally** (EmailBison API doesn't return health_score)
- Updates bounce rates, status, warmup progress
- Marks stale accounts as inactive
- Links accounts to domains

#### Health Score Calculation

The sync worker calculates health scores using this formula:

```
Health Score (0-100) = Connection (40) + Bounces (20) + Spam (20) + Replies (10) + Limits (10)

Connection (40 points):
- Connected: 40
- Not connected: 0
- Other: 20

Bounce Rate (20 points):
- <2%: 20
- <5%: 15
- <10%: 10
- >=10%: 0

Spam Rate (20 points):
- <1%: 20
- <3%: 15
- <5%: 10
- >=5%: 0

Reply Rate (10 points):
- >10%: 10
- >5%: 7
- >2%: 5
- <=2%: 3

Daily Limit (10 points):
- Warmup enabled: 10
- Has daily limit: 7
- No limit: 5
```

Health ranges:
- **Healthy**: 80-100
- **Good**: 60-80
- **Warning**: 40-60
- **Critical**: 0-40

### Campaign Sync Module

Syncs campaign data and metrics:

- Creates/updates `emailbison_campaigns`
- Creates metric snapshots in `campaign_snapshots`
- Tracks send counts, bounces, replies

### Event Sync Module

Syncs replies, bounces, and spam complaints with full message content:

- Fetches from inbox/bounced folders
- Classifies bounces (hard_unknown, hard_blocked, soft_full, soft_temp)
- **Detects spam complaints** from lead response text and FBL patterns in bounces
- Increments `complaints_lifetime` when spam complaint detected
- Stores full message body in `response_messages`

#### Spam Complaint Detection

Spam complaints are detected through analyzing response content:

1. **Inbox response text analysis**: When a lead replies to our email, we scan the response body for phrases indicating they marked us as spam:
   - "marked as spam", "reported as spam", "flagged as spam"
   - "moved to spam", "sent to spam", "goes to spam"
   - "marked as junk", "reported as junk", "moved to junk" (Outlook)
   - "reported to google", "reported to microsoft", etc.
   - "filing a spam complaint", "spam complaint"

2. **FBL patterns in bounces**: Bounce messages containing Feedback Loop indicators:
   - `feedback-type:`, `abuse report`, `marked as spam`, `reported as junk`
   - ARF (Abuse Reporting Format) headers
   - Microsoft Junk Mail Reporting headers (X-HMXMROriginalRecipient)
   - Google FBL headers (Feedback-ID)

3. **SMTP codes**: Bounce codes like 550 5.7.51 (user reported spam) combined with complaint keywords

**Note**: We do NOT fetch from a separate "spam" API folder. Spam detection is based on analyzing the TEXT of lead responses in the inbox folder.

#### Bounce Reason & SMTP Code Extraction

When a lead's inbox bounces our email, EmailBison returns the bounce message in the `bounced` folder. The API does **NOT** provide a separate `bounce_reason` field - instead, the SMTP error codes and reason text are embedded in the message body.

**How we extract bounce information:**

1. **Fetch bounce messages** from `/campaigns/{id}/replies?folder=bounced`
2. **Parse message body** (`text_body` or `html_body`) for SMTP codes and keywords
3. **Extract SMTP codes** using regex: `[45]\d{2}\s*[45]\.\d+\.\d+`
4. **Classify bounce type** based on code + keywords

**SMTP Code Reference:**

| Code | Extended | Meaning | Classification |
|------|----------|---------|----------------|
| 550 | 5.1.1 | User unknown / mailbox doesn't exist | `hard_unknown` |
| 550 | 5.1.0 | Address rejected | `hard_unknown` |
| 550 | 5.7.1 | Policy rejection (spam/block) | `hard_blocked` |
| 550 | 5.7.51 | User reported as spam (Microsoft) | `hard_blocked` + spam complaint |
| 552 | 5.2.2 | Mailbox full | `soft_full` |
| 452 | 4.2.2 | Mailbox full (temporary) | `soft_full` |
| 421 | 4.7.0 | Temporary failure | `soft_temp` |

**Example bounce message parsing:**

```
Subject: "Undeliverable: Re: GTM motion stuck?"
Body: "Your message to john@example.com couldn't be delivered.
       john wasn't found at example.com.
       Unknown To address"

Extracted:
- bounce_reason: "user unknown | not found"
- bounce_type: "hard_unknown"
```

**Important**: The `bounce_reason` field stored in `response_messages` is populated by our `extract_bounce_reason()` function, not by the EmailBison API.

### Health Check Module

Detects kill triggers and health issues:

| Trigger | Threshold | Action |
|---------|-----------|--------|
| **Spam complaint** | >= 1 | Queue for kill (v3: 1 = death) |
| **Hard blocked (24h)** | >= 1 | Queue for kill (reputation damage) |
| Hard unknown (24h) | >= 3 | Queue for kill (list quality) |
| Hard bounces combined (24h) | >= 2 | Queue for kill (fallback) |
| Hard bounce rate (7d) | > 0.5% | Queue for kill |
| Total bounce rate (7d) | > 5% | Queue for kill |
| Fresh inbox hard bounce | 1 (if <14 days old) | Queue for kill |

See [[../concepts/kill-triggers]] for detailed documentation on kill trigger evaluation.

### Kill Processor

Implements 24-hour kill queue:

1. **Pending** → Tag inbox in EmailBison with `delete_queue`
2. **Tagged** → Wait 24 hours
3. **Delete** → Remove from EmailBison after 24 hours
4. **Update** → Mark `sender_accounts.inbox_state = 'dead'`

> **Note**: The `delete_queue` tag must exist in each workspace. When provisioning new workspaces, create this tag to prevent 422 errors during kill processing.

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
