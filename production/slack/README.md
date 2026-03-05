# Slack Integration

## Daily Inbox Audit

Automated daily notifications sent to `#inbox-audit` channel.

### Schedule
- **Time**: 6:00 AM Pacific (7 AM PDT during daylight saving)
- **Method**: Coolify Scheduled Task (cron)
- **Cron**: `0 14 * * *` (2 PM UTC)

### Coolify Configuration

The daily audit is triggered via a **Coolify Scheduled Task**, not application code.

**Location**: Coolify → emailbison-sync → Scheduled Tasks

| Setting | Value |
|---------|-------|
| Task Name | Daily Inbox Audit |
| Command | `curl -X POST https://api.wizardgrimoire.cloud/api/slack/trigger-audit` |
| Frequency | `0 14 * * *` |
| Container | emailbison-sync |

**Why Coolify scheduled tasks instead of code?**
- Decoupled from application restarts (no lost state)
- No 5-minute timing window fragility
- Visible in Coolify UI with run history
- Easy to modify schedule without code deploy

### Notification Contents

| Section | Description |
|---------|-------------|
| Kill Triggers (24h) | Count of inboxes killed by each trigger type |
| Top Workspaces | Workspaces with most kills |
| Disconnected Inboxes | New disconnections + total count |
| Dead Domains | Domains pending subscription cancellation |

### CSV Download Buttons

| Button | Endpoint | Contents |
|--------|----------|----------|
| Kill Triggers CSV | `/api/health/export/kill-triggers` | All killed inboxes with trigger details |
| Disconnected CSV | `/api/health/export/disconnected` | Live inboxes that are disconnected |
| Dead Domains CSV | `/api/health/export/dead-domains` | Domains with no live inboxes |

CSVs are generated on-demand when clicked (fresh data).

### Action Buttons

| Button | Action |
|--------|--------|
| Confirmed - All Correct | Marks audit as reviewed, no issues |
| Issues Found | Opens thread for documenting problems |

### Manual Trigger

```bash
curl -X POST https://api.wizardgrimoire.cloud/api/slack/trigger-audit
```

Response:
```json
{"success": true, "audit_id": "4", "total_kills": 0, "total_disconnected": 4413}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SLACK_AUDIT_WEBHOOK_URL` | Webhook URL for #inbox-audit channel |
| `PUBLIC_API_URL` | Base URL for CSV download links |

## Key Files

| File | Purpose |
|------|---------|
| [sync_modules/slack_audit.py](../../sync_modules/slack_audit.py) | Audit message builder |
| [api/routes/slack_webhooks.py](../../api/routes/slack_webhooks.py) | Button handlers, manual trigger |
| [api/routes/health.py](../../api/routes/health.py) | CSV export endpoints |

## Database Tables

| Table | Purpose |
|-------|---------|
| `inbox_audits` | Audit records with status (pending/confirmed/issues) |
| `inbox_audit_corrections` | Logged corrections for incorrectly flagged inboxes |

## Troubleshooting

### No audit at 6 AM
1. Check Coolify scheduled task exists and is enabled:
   - Coolify → emailbison-sync → Scheduled Tasks → "Daily Inbox Audit"
   - Verify cron is `0 14 * * *`
2. Check scheduled task run history in Coolify UI
3. Verify `SLACK_AUDIT_WEBHOOK_URL` is set in charm-api environment
4. Test manually: `curl -X POST https://api.wizardgrimoire.cloud/api/slack/trigger-audit`

### CSV download fails
1. Verify `PUBLIC_API_URL` points to accessible API
2. Check API is responding: `curl https://api.wizardgrimoire.cloud/health`

### Buttons not working
- Slack buttons use `PUBLIC_API_URL` for links
- Ensure URL is publicly accessible (via Cloudflare tunnel)
