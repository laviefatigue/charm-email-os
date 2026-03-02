# CSV Exports for Team Review

## Overview

Two CSV export endpoints for manual team review of inbox health. Both exports are structured for direct Google Sheets import with workspace → domain → inbox sorting.

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

## Slack Message Format (Future)

For Slack notifications, format as:

```
📊 *Daily Inbox Health Report*

*Kill Triggers (last 24h):*
• Charm: 5 inboxes killed
  - 3 hard_bounces_24h
  - 2 spam_complaint

• EventPanda: 12 inboxes killed
  - 10 fresh_inbox_bounce
  - 2 hard_bounces_24h

*Disconnected Inboxes:*
• Charm: 158 disconnected
• Sammy: 580 disconnected

📎 Full reports: [Kill Triggers](url) | [Disconnected](url)
```

## API Implementation

Both endpoints are in `api/routes/health.py`:
- `export_kill_triggers()` - Lines 2338-2433
- `export_disconnected()` - Lines 2436-2539

Query filters:
- Kill triggers: `WHERE sa.kill_trigger IS NOT NULL AND w.is_active = TRUE`
- Disconnected: `WHERE sa.status != 'Connected' AND sa.inbox_state = 'live' AND w.is_active = TRUE`
