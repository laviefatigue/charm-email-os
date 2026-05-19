# Sync Engine

## What Exists Today

The sync engine is the autonomous backbone of Charm OS. It runs as a single persistent process (`emailbison_sync_worker.py`) with modular sync tasks on staggered intervals.

### Database Tables (Written by Sync)
- **`sender_accounts`** — Inbox records, health scores, bounce counters, warmup state
- **`domains`** — Domain health scores, fulfillment status
- **`emailbison_campaigns`** — Campaign mirrors from EmailBison
- **`campaign_snapshots`** — Hourly campaign metrics snapshots
- **`campaign_inboxes`** — Campaign-to-inbox assignments
- **`campaign_events`** — Event records (opens, replies, bounces)
- **`response_messages`** — Full message content (replies, bounces, spam)
- **`inbox_health_snapshots`** — Historical health data
- **`inbox_engagement_snapshots`** — Daily engagement counters
- **`sender_warmup_snapshots`** — Warmup progress tracking
- **`daily_volume_snapshots`** — End-of-day snapshot of **cumulative** campaign sends + inbox capacity per workspace. Consumers must diff consecutive days for a daily figure. Warmup volume NOT captured here. Full contract: [docs/architecture/daily-volume-semantics.md](../architecture/daily-volume-semantics.md).
- **`sync_audit_log`** — Sync run history and metrics
- **`sync_status`** — Last successful sync per type per workspace

### Workers
- **`emailbison_sync_worker.py`** — Main orchestrator daemon

### Key Files
- `emailbison_sync_worker.py` — Orchestrator (schedules + runs all modules)
- `sync_modules/sync_accounts.py` — Account/inbox sync
- `sync_modules/sync_campaigns.py` — Campaign sync
- `sync_modules/sync_events.py` — Reply/bounce/spam event sync
- `sync_modules/sync_engagement.py` — Engagement metrics sync
- `sync_modules/sync_warmup.py` — Warmup status sync
- `sync_modules/health_checks.py` — Kill trigger detection
- `sync_modules/kill_processor.py` — Kill execution
- `sync_modules/lifecycle_tag_sync.py` — Incubating/active tagging
- `sync_modules/set_tag_sync.py` — Live/Reserve allocation tagging
- `sync_modules/daily_snapshot.py` — Daily volume + warmup snapshots
- `sync_modules/emailbison_client.py` — Shared EmailBison API client
- `sync_modules/slack_audit.py` — Slack audit notifications

## Sync Schedule

| Interval | Module | What It Does |
|----------|--------|-------------|
| **5 min** | sync_events | Pull replies, bounces, spam from EmailBison |
| **15 min** | health_checks | Evaluate kill triggers for all live inboxes |
| **30 min** | kill_processor | Execute pending kills, tag, promote backups |
| **30 min** | sync_warmup | Track warmup progress, auto-enable warmup |
| **30 min** | lifecycle_tag_sync | Graduate inboxes (incubating → active) |
| **30 min** | set_tag_sync | Manage Live/Reserve domain allocation tags |
| **1 hour** | sync_accounts | Full inbox sync from EmailBison |
| **1 hour** | sync_campaigns | Campaign + assignment sync |
| **Daily** | sync_engagement | Daily engagement snapshots |
| **Daily** | daily_snapshot | Cumulative-as-of-EOD volume snapshots + warmup snapshots (consumers diff for daily) |
| **Daily** | counter_reset | Reset 24h bounce counters to zero |
| **Daily** | workspace_discovery | Auto-discover new EmailBison workspaces |
| **Daily** | slack_audit | Send audit summary to Slack (6 AM + 1 PM PT) |
| **Daily** | retention_cleanup | Purge old sync_audit_log entries |

## How Records Are Created

### Account Sync (Hourly)
```
For each active workspace:
  ├─ Switch EmailBison context to workspace
  ├─ GET all sender accounts (paginated)
  ├─ For each account:
  │   ├─ UPSERT: sender_accounts (ON CONFLICT email_address)
  │   │   ├─ Health score (calculated: connection, bounce rate, spam, replies, daily limit)
  │   │   ├─ Bounce counters (hard_bounces_24h, hard_blocked_24h, etc.)
  │   │   ├─ Warmup state (enabled, score, started_at)
  │   │   ├─ Connection status (Connected, Not connected)
  │   │   ├─ inventory_lifecycle_status (incubating if warmup < 21d, else active)
  │   │   └─ total_sends_7d (delta tracking for rate-based triggers)
  │   │
  │   └─ UPSERT: domains (derived from email domain, globally unique)
  │       └─ Domain health = average of inbox health scores
  │
  └─ INSERT: sync_audit_log (records_processed, created, updated, failed)
```

### Event Sync (Every 5 min)
```
For each workspace with active campaigns:
  ├─ For each campaign:
  │   ├─ GET replies from inbox folder
  │   ├─ GET bounces from bounced folder
  │   ├─ GET spam from spam folder
  │   │
  │   ├─ For each message:
  │   │   ├─ INSERT: response_messages (content, classification, bounce_type)
  │   │   ├─ INSERT: campaign_events (linked to response)
  │   │   └─ UPDATE: sender_accounts bounce counters
  │   │       ├─ hard_blocked_24h (550 5.7.x codes)
  │   │       ├─ hard_unknown_24h (550 5.1.1 codes)
  │   │       ├─ hard_bounces_24h (combined)
  │   │       ├─ soft_bounces_7d (4xx codes)
  │   │       └─ complaints_lifetime (spam complaints — triggers instant kill)
  │   │
  │   └─ Bounce type classification:
  │       ├─ hard_blocked = 550 5.7.x (spam/policy rejection)
  │       ├─ hard_unknown = 550 5.1.1 (bad email address)
  │       ├─ soft_full = 452 4.2.2 (mailbox full)
  │       └─ soft_temp = 421 4.7.0 (transient, retry later)
```

### Campaign Sync (Hourly)
```
For each workspace:
  ├─ GET all campaigns from EmailBison
  ├─ UPSERT: emailbison_campaigns
  ├─ INSERT: campaign_snapshots (hourly metrics)
  │
  ├─ For each inbox in workspace:
  │   ├─ GET campaign assignments for inbox
  │   ├─ UPSERT: campaign_inboxes
  │   └─ UPDATE: sender_accounts.sending_started_at = NOW()
  │       (set on FIRST campaign assignment — critical for fresh_inbox_bounce calculation)
```

### Engagement Sync (Daily)
```
For each workspace:
  ├─ For each inbox:
  │   ├─ GET daily event stats (opens, replies, interested, sent, bounced)
  │   ├─ INSERT: inbox_engagement_snapshots
  │   └─ UPDATE: sender_accounts (opens_7d, replies_7d, etc. from 7-day rollup)
  │
  └─ Domain engagement rollup (averages from inboxes)
```

## What's Automated vs Manual

| Component | Automated | Manual |
|-----------|-----------|--------|
| Account sync | Yes (hourly) | — |
| Campaign sync | Yes (hourly) | — |
| Event sync | Yes (5 min) | — |
| Engagement sync | Yes (daily) | — |
| Warmup sync | Yes (30 min) | — |
| Health checks | Yes (15 min) | — |
| Kill processing | Yes (30 min) | — |
| Lifecycle tagging | Yes (30 min) | — |
| Set allocation | Yes (30 min) | — |
| Daily snapshots | Yes (daily) | — |
| Workspace discovery | Yes (daily) | — |
| Counter reset | Yes (daily midnight) | — |
| Slack audit | Yes (6 AM + 1 PM PT) | — |

**The sync engine is 100% autonomous.** Nothing requires manual triggering.

## What's Working in Production
- All sync modules running on Coolify (`emailbison-sync` app)
- Last warmup sync: moments ago (verified in production query)
- Last campaign sync: within the hour
- 31,920 engagement snapshots collected
- Kill triggers actively processing (205 kills in last 7 days)
- 9 active workspaces being synced

## What's Dead Code or Half-Built
- `sync_modules/__init__.py` — imports engagement module but engagement is relatively new (migration 086)
- `emailbison_client.py` — shared client class, well-used
- Counter reset relies on midnight timing — if sync worker restarts mid-cycle, counters may not reset on schedule

## What Needs to Change

### For Headless Engine
1. **This is already headless.** The sync engine doesn't need a UI. It runs autonomously and writes to the database.

2. **Add API endpoints for sync control:**
   - `POST /api/sync/trigger/{module}` — Force-run a specific sync module on demand
   - `GET /api/sync/status` — Current sync state (last run times, errors)
   - This allows an AI agent to trigger a sync check after provisioning new inboxes

3. **Faster inbox discovery after provisioning:** When a HyperTide order completes, trigger an immediate account sync for that workspace instead of waiting up to 60 minutes.

4. **Health check webhooks/callbacks:** Instead of just writing to the DB, health checks could notify external systems (Day.ai, Slack, webhook URL) when critical events happen (inbox killed, domain burned, capacity drops below threshold).

## Downstream Connection
The sync engine feeds data to **health and kill triggers** — see [health-and-kill-triggers.md](health-and-kill-triggers.md) — and **tagging and allocation** — see [tagging-and-allocation.md](tagging-and-allocation.md).
