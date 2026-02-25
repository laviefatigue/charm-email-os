---
title: EmailBison Sync Worker
created: 2026-02-12
updated: 2026-02-13
tags: [worker, emailbison, sync, health, database, kill-triggers, warmup]
---

# EmailBison Sync Worker

The EmailBison Sync Worker keeps the local database synchronized with EmailBison (the source of truth for inbox/campaign data).

## Purpose

- **Account Sync**: Keep `sender_accounts` table fresh with EmailBison data
- **Campaign Sync**: Sync campaign metrics and snapshots
- **Event Sync**: Track replies, bounces, and response messages
- **Warmup Sync**: Track warmup lifecycle, create snapshots, auto-enable warmup
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
│  │  → Kill Queue (30 min) → Warmup (30 min) → Retention (daily)││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│  Modules:                                                        │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐│
│  │  Accounts   │ │  Campaigns  │ │   Events    │ │   Warmup    ││
│  │    Sync     │ │    Sync     │ │    Sync     │ │    Sync     ││
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘│
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │   Health    │ │    Kill     │ │  Retention  │                │
│  │   Checks    │ │  Processor  │ │   Manager   │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

## Sync Intervals

| Operation | Interval | Description |
|-----------|----------|-------------|
| Events Sync | 5 min | Replies, bounces, response messages |
| Full Sync | 1 hour | Accounts, domains, campaign metrics |
| Health Checks | 15 min | Kill trigger detection, workspace health |
| Kill Queue | 30 min | Tag inboxes, process 24hr deletions |
| Warmup Sync | 30 min | Warmup stats, lifecycle tracking, auto-enable |
| Retention | Daily | Clean up old audit logs, bounces |
| Daily Counter Reset | Daily | Reset 24h bounce counters (prevents false positives) |

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
| `SYNC_INTERVAL_WARMUP` | 1800 | Warmup sync interval (seconds) |
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
    - SYNC_INTERVAL_WARMUP=1800
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
| `sender_warmup_snapshots` | Time-series warmup statistics |
| `warmup_check_runs` | Audit log of warmup sync runs |

### Warmup Tracking Columns

The `sender_accounts` table includes these warmup-related columns:

| Column | Type | Description |
|--------|------|-------------|
| `warmup_enabled` | boolean | Whether warmup is currently enabled in EmailBison |
| `warmup_started_at` | timestamp | When warmup was first detected as enabled (estimated: `first_seen_at + 7 days`) |
| `warmup_stopped_at` | timestamp | When warmup was detected as disabled |
| `sending_started_at` | timestamp | When inbox was first deployed to a campaign |

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

### Warmup Sync Module

Tracks warmup lifecycle and ensures connected inboxes stay in warmup (per user requirement: "We should always try to keep connected inboxes in warming").

**Key Functions:**

1. **Sync Warmup Stats**: Fetches warmup data from `/api/warmup/sender-emails` with date range
2. **Lifecycle Tracking**: Detects warmup start/stop transitions and sets timestamps
3. **Create Snapshots**: Stores time-series warmup metrics in `sender_warmup_snapshots`
4. **Auto-Enable Warmup**: Enables warmup for connected inboxes that don't have it

**Warmup Lifecycle:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ Connected inbox without warmup                                       │
│ → Auto-enable warmup via API                                        │
│ → Set warmup_started_at = first_seen_at + 7 days                    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Warmup Active (warmup_enabled = true)                               │
│ → Sync warmup stats every 30 min                                    │
│ → Create sender_warmup_snapshots                                    │
│ → Calculate warmup progress = days_warming / 30 * 100               │
└────────────────────────────┬────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
┌─────────────────────────┐    ┌─────────────────────────┐
│ Warmup Complete         │    │ Warmup Disabled         │
│ (30+ days, ready)       │    │ (bounces or manual)     │
│ → Ready for campaigns   │    │ → Set warmup_stopped_at │
│ → Set sending_started_at│    │ → Re-enable if fixed    │
│   when first deployed   │    │                         │
└─────────────────────────┘    └─────────────────────────┘
```

**7-Day Buffer Logic:**

When warmup is first detected as enabled, we estimate `warmup_started_at` as:

```
warmup_started_at = first_seen_at + 7 days (~5 business days)
```

This accounts for inbox setup time before warmup actually starts (domain verification, DKIM setup, etc.).

**API Endpoints Used:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/warmup/sender-emails` | GET | List inboxes with warmup stats |
| `/warmup/sender-emails/enable` | PATCH | Enable warmup for inboxes |
| `/warmup/sender-emails/disable` | PATCH | Disable warmup (24hr ramp-down) |

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

Implements trigger-specific tagging (no deletion):

1. **Pending** → Tag inbox in EmailBison with `flagged_{trigger_type}`
2. **Flagged** → Mark `sender_accounts.inbox_state = 'dead'`

**Tag Examples**:
- `flagged_fresh_inbox_bounce` - Inbox <14 days with any bounce
- `flagged_spam_complaint` - Spam complaint received
- `flagged_hard_blocked_24h` - Spam/policy rejection
- `flagged_hard_unknown_24h` - Bad email addresses

> **Note**: Inboxes are NOT deleted from EmailBison. They remain tagged for visibility into WHY each inbox was flagged. Tags are created on-demand using `get_or_create_tag()`.

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

Inbox `user@domain.com` has been flagged

• Trigger: hard_bounces_24h
• Value: 3
• Tag: flagged_hard_bounces_24h
• Status: Flagged (excluded from campaigns)
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

## Daily Volume Snapshots

The `daily_volume_snapshots` table stores historical sending volume per workspace for client dashboard charts.

### How It Works

Volume data comes from **EmailBison campaign stats**, not sender account deltas:

```
EmailBison API                Our Database
───────────────               ────────────
Campaigns → Stats             daily_volume_snapshots
    │          │                    │
    │    POST /campaigns/{id}/stats │
    │    { start_date, end_date }   │
    │          │                    │
    └──────────┴── emails_sent ────►│
               per day              │
```

Campaign-level stats are preserved even after sender accounts are killed/deleted.

### Backfill Script

To backfill historical data from EmailBison:

```bash
# Backfill last 90 days for all active workspaces
python scripts/backfill_daily_volume.py --days 90

# Backfill specific date range
python scripts/backfill_daily_volume.py --start-date 2025-11-01 --end-date 2026-02-22

# Backfill single workspace
python scripts/backfill_daily_volume.py --workspace-id b9abd34a-f16a-4b92-bda0-5af10f8c44bd --days 30
```

**Initial Backfill (2026-02-23)**: 54,716 emails across 7 workspaces, covering Nov 25, 2025 - Feb 22, 2026.

### Daily Snapshot Worker

The sync worker creates daily snapshots at 00:05 UTC via `run_daily_snapshot()`:

1. Queries current capacity metrics (live/incubating/dead inboxes, daily_limit sum)
2. Calls `snapshot_daily_volume()` SQL function
3. Logs results to `sync_audit_log`

## Files

| File | Purpose |
|------|---------|
| `emailbison_sync_worker.py` | Main orchestrator |
| `scripts/backfill_daily_volume.py` | Historical data backfill from EmailBison API |
| `sync_modules/daily_snapshot.py` | Daily snapshot worker module |
| `Dockerfile.emailbison-sync` | Container definition |
| `requirements-sync.txt` | Python dependencies |
| `sync_modules/__init__.py` | Module exports |
| `sync_modules/emailbison_client.py` | API client (includes warmup endpoints) |
| `sync_modules/sync_accounts.py` | Account sync (tracks warmup_enabled) |
| `sync_modules/sync_campaigns.py` | Campaign sync |
| `sync_modules/sync_events.py` | Event sync |
| `sync_modules/sync_warmup.py` | Warmup lifecycle tracking and auto-enable |
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
