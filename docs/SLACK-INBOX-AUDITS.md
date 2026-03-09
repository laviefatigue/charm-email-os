# Slack Inbox Audits Setup

## Overview

Slack notifications for inbox health audits sent **twice daily** (6 AM and 1 PM Pacific) with interactive buttons for team review.

## Flow

```
┌─────────────────────────────────────────────────────────────┐
│  📋 Daily Inbox Audit - March 2, 2026                       │
│                                                             │
│  Kill Triggers (last 24h): 47 inboxes                       │
│  • hard_bounces_24h: 23                                     │
│  • spam_complaint: 15                                       │
│  • fresh_inbox_bounce: 9                                    │
│                                                             │
│  Top Workspaces:                                            │
│  • EventPanda: 20                                           │
│  • Charm: 15                                                │
│  • Sammy: 12                                                │
│                                                             │
│  Disconnected: 12 new (1,855 total)                         │
│                                                             │
│  [📥 Kill Triggers CSV]  [📥 Disconnected CSV]              │
│                                                             │
│  [✅ Confirmed - All Correct]  [⚠️ Issues Found]            │
└─────────────────────────────────────────────────────────────┘
```

## Slack App Setup

### 1. Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name: `Charm Inbox Audits`
4. Workspace: Select your workspace

### 2. Configure Incoming Webhook

1. Go to **Incoming Webhooks** in sidebar
2. Enable "Activate Incoming Webhooks"
3. Click "Add New Webhook to Workspace"
4. Select `#inbox-audits` channel
5. Copy the Webhook URL

### 3. Configure Interactive Components

1. Go to **Interactivity & Shortcuts** in sidebar
2. Enable "Interactivity"
3. Set Request URL:
   ```
   https://your-api-domain.com/api/slack/interactions
   ```
4. Save Changes

### 4. Bot Token (for modals)

1. Go to **OAuth & Permissions** in sidebar
2. Under "Bot Token Scopes", add:
   - `chat:write`
   - `files:read` (for corrections upload)
3. Install app to workspace
4. Copy "Bot User OAuth Token"

### 5. Signing Secret

1. Go to **Basic Information** in sidebar
2. Under "App Credentials", copy "Signing Secret"

## Environment Variables

Add to your deployment:

```bash
# Slack Audit Configuration
SLACK_AUDIT_WEBHOOK_URL=https://hooks.slack.com/services/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
SLACK_SIGNING_SECRET=140a65354f13e535a249b94a1eeeae08

# API URLs
PUBLIC_API_URL=http://nckgggwww8sggg0kc4wo00o8.187.77.19.81.sslip.io
```

### Slack App Details
- **App ID:** A0AHXEBSAH1
- **Created:** March 2, 2026
- **Channel:** #inbox-audits

## Database Setup

Run the migration:

```bash
psql -U charm -d postgres -f migrations/063_inbox_audit_tables.sql
```

Tables created:
- `inbox_audits` - Audit records
- `inbox_audit_corrections` - Corrections submitted
- `inbox_audit_history` - Audit trail

## API Endpoints

### Trigger Audit (Manual)

```bash
POST /api/slack/trigger-audit
```

### List Audits

```bash
GET /api/slack/audits?limit=10
```

### Get Audit Details

```bash
GET /api/slack/audits/{audit_id}
```

### Submit Corrections

```bash
POST /api/slack/corrections/{audit_id}
Content-Type: multipart/form-data

file=@corrections.csv
```

CSV format:
```csv
email_address,correction_type,reason
user@domain.com,wrong_kill,Inbox was working fine
other@domain.com,false_positive,No actual bounces
```

### Get Corrections

```bash
GET /api/slack/corrections/{audit_id}
```

### Resolve Correction

```bash
POST /api/slack/corrections/{audit_id}/{correction_id}/resolve
Content-Type: application/x-www-form-urlencoded

resolved_by=username&resolution_notes=Fixed
```

## Scheduled Audits

Audits run automatically via `emailbison_sync_worker.py`:

```python
# Runs at 6 AM and 1 PM Pacific (within 5-minute window)
audit_hours = [6, 13]  # 6 AM and 1 PM
if now_pacific.hour in audit_hours and now_pacific.minute < 5:
    if not already_ran_this_hour:
        await send_daily_audit()
```

| Time (Pacific) | Purpose |
|----------------|---------|
| 6:00 AM | Morning check before sending ramps up |
| 1:00 PM | Afternoon check for issues from morning sends |

Manual trigger:

```bash
curl -X POST https://api.wizardgrimoire.cloud/api/slack/trigger-audit
```

## Testing

1. Trigger a test audit:
   ```bash
   curl -X POST http://localhost:8000/api/slack/trigger-audit
   ```

2. Check `#inbox-audits` channel for message

3. Click buttons to test interactions

## Correction Workflow

1. Team downloads CSV from audit message
2. Reviews in Google Sheets
3. If issues found:
   - Click "Issues Found" button
   - Add `correction_type` column to CSV
   - Upload via corrections endpoint
4. Corrections appear in audit history
5. Resolve corrections as they're addressed
