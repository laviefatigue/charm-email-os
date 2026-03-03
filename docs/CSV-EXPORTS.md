# CSV Exports for Team Review

## Overview

Three CSV export endpoints for manual team review of inbox health. All exports are structured for direct Google Sheets import with workspace → domain sorting.

## Endpoints

### 1. Kill Triggers Export

**URL:** `/api/health/export/kill-triggers`

**Purpose:** Review inboxes caught by automated kill triggers to verify the system is working correctly.

**Production URL:**
```
http://nckgggwww8sggg0kc4wo00o8.187.77.19.81.sslip.io/api/health/export/kill-triggers
```

**Columns:**

| Column | Description |
|--------|-------------|
| workspace_name | Workspace name (first column for grouping) |
| emailbison_workspace_id | EmailBison workspace ID |
| domain_name | Domain (second-level grouping) |
| email_address | The inbox email |
| kill_trigger | Trigger type: `hard_bounces_24h`, `spam_complaint`, `fresh_inbox_bounce`, `disconnected_21d` |
| killed_at | ISO timestamp when killed |
| days_active | Days from warmup start to kill |
| inbox_state | Current state (`dead`) |
| connection_status | `Connected` or `Not connected` |
| warmup_started_at | When warmup began |
| hard_bounces_24h | Hard bounces in last 24h |
| hard_blocked_24h | Hard blocked in last 24h |
| hard_unknown_24h | Unknown errors in last 24h |
| complaints_lifetime | Total spam complaints |
| trigger_value | Actual value that triggered kill |
| trigger_threshold | Threshold that was exceeded |

**Kill Trigger Types:**
- `hard_bounces_24h` - 2+ hard bounces in 24 hours
- `spam_complaint` - 1+ spam complaint
- `fresh_inbox_bounce` - Bounce within first 3 days of warmup
- `disconnected_21d` - Disconnected for 21+ days

---

### 2. Disconnected Inboxes Export

**URL:** `/api/health/export/disconnected`

**Purpose:** Review and manage disconnected inboxes that need attention.

**Production URL:**
```
http://nckgggwww8sggg0kc4wo00o8.187.77.19.81.sslip.io/api/health/export/disconnected
```

**Columns:**

| Column | Description |
|--------|-------------|
| workspace_name | Workspace name (first column for grouping) |
| emailbison_workspace_id | EmailBison workspace ID |
| domain_name | Domain (second-level grouping) |
| email_address | The inbox email |
| connection_status | Status (typically `Not connected`) |
| inbox_state | Should be `live` (dead inboxes filtered out) |
| warmup_enabled | `True` or `False` |
| warmup_started_at | When warmup began |
| esp | Email provider: `gmail`, `microsoft` |
| daily_limit | Current daily send limit |
| total_sends_7d | Sends in last 7 days |
| hard_bounces_24h | Hard bounces in last 24h |
| last_synced_at | Last sync timestamp |
| created_at | When inbox was created |

---

### 3. Dead Domains Export

**URL:** `/api/health/export/dead-domains`

**Purpose:** Identify domains where ALL inboxes have been removed from EmailBison, alerting the team to cancel HyperTide subscriptions.

**Production URL:**
```
http://nckgggwww8sggg0kc4wo00o8.187.77.19.81.sslip.io/api/health/export/dead-domains
```

**Columns:**

| Column | Description |
|--------|-------------|
| workspace_name | Workspace name (first column for grouping) |
| emailbison_workspace_id | EmailBison workspace ID |
| domain_name | The dead domain |
| provider | `entra` or `google` (for cancellation reference) |
| purchased_at | When domain was purchased |
| total_inboxes | How many inboxes existed on this domain |
| inboxes_in_emailbison | Should be 0 (all gone) |
| inboxes_gone | Count of removed inboxes |
| status | Always `CANCEL` |

**Key Concepts:**

This export identifies **dead domains** - domains where every inbox has been completely removed from EmailBison (not just killed or disabled in our system).

| Inbox State | Definition | In Dead Domains? |
|-------------|------------|------------------|
| Killed (`inbox_state=dead`) | Disabled in our system, still exists in EmailBison | No |
| Removed (`is_active=FALSE`) | Completely deleted from EmailBison | Yes |
| Live (`inbox_state=live`) | Active inbox | No |

**How Removal is Detected:**

The EmailBison sync worker (`sync_modules/sync_accounts.py`) marks inboxes as `is_active=FALSE` when they are no longer found in the EmailBison API. A domain is "dead" when:
- It has at least one inbox in our database (`total_inboxes > 0`)
- Zero of those inboxes are still active in EmailBison (`inboxes_in_emailbison = 0`)

**Action Required:**

When domains appear in this export, cancel the corresponding HyperTide subscription:
1. Note the `provider` column (entra or google)
2. Cancel subscription in the appropriate provider dashboard
3. Domain can be marked as cancelled in the system

---

## Google Sheets Import

1. Download CSV from endpoint
2. Google Sheets → File → Import → Upload
3. Select "Replace current sheet" or "Insert new sheet"
4. Separator: Comma
5. Data is pre-sorted by workspace → domain → inbox

## Filtering in Google Sheets

**By Workspace:**
- Data → Create Filter
- Click filter on `workspace_name` column
- Select workspaces to view

**By Kill Trigger Type:**
- Filter `kill_trigger` column
- Select specific trigger types

**By Domain:**
- Filter `domain_name` column

## Slack Audit Message

Daily audit messages are sent to Slack with download buttons for each CSV:

```
📋 Daily Inbox Audit - March 2, 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kill Triggers (last 24h): X inboxes
  🚫 hard_bounces_24h: X
  🚨 spam_complaint: X
  ...

Top Workspaces:
  • Workspace A: X
  • Workspace B: X

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔌 Disconnected Inboxes: X new (Y total)
🪦 Dead Domains (Cancel Subscriptions): Z domains
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Kill Triggers CSV] [Disconnected CSV] [Dead Domains CSV]
```

The dead domains count alerts the team when HyperTide subscriptions need cancellation.

## API Implementation

All endpoints are in `api/routes/health.py`:
- `export_kill_triggers()` - Lines ~2338
- `export_disconnected()` - Lines ~2436
- `export_dead_domains()` - Lines ~2544

Query filters:
- **Kill triggers:** `WHERE sa.kill_trigger IS NOT NULL AND w.is_active = TRUE`
- **Disconnected:** `WHERE sa.status != 'Connected' AND sa.inbox_state = 'live' AND w.is_active = TRUE`
- **Dead domains:** Domain-level rollup where `inboxes_in_emailbison = 0` (all inboxes have `is_active = FALSE`)

Slack integration is in `api/routes/slack_webhooks.py`:
- Dead domains count query and download button added to daily audit message
