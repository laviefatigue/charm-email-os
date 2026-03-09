# Slack Integration

## Inbox Audit Notifications

Automated notifications sent to `#inbox-audit` channel **twice daily**.

### Schedule
| Time (Pacific) | Purpose |
|----------------|---------|
| **6:00 AM** | Morning check before sending ramps up |
| **1:00 PM** | Afternoon check to catch issues from morning sends |

- **Method**: Sync worker scheduled check (not Coolify cron)
- **Implementation**: `emailbison_sync_worker.py` → `_should_run_slack_audit()`

### Implementation

The audit is triggered by the sync worker's poll loop, checking if current time falls within a 5-minute window at each scheduled hour.

```python
# In emailbison_sync_worker.py
audit_hours = [6, 13]  # 6 AM and 1 PM Pacific
if now_pacific.hour in audit_hours and now_pacific.minute < 5:
    # Run audit if not already run this hour
```

**Why sync worker instead of Coolify cron?**
- Integrated with sync cycle (data is fresh)
- No separate scheduled task to manage
- Automatic retry on next poll if missed

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
| Rotation CSV | `/api/health/export/rotation-summary` | Domains needing rotation |
| Capacity CSV | `/api/health/export/capacity-gaps` | Client capacity gaps |

CSVs are generated on-demand when clicked (fresh data).

**Sorting**: Most recent items appear first (kill triggers by `killed_at`, disconnected by `last_synced_at`).

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

### No audit at scheduled time
1. Check sync worker is running:
   - Coolify → emailbison-sync → Logs
   - Look for `[SlackAudit]` log entries
2. Verify `SLACK_AUDIT_WEBHOOK_URL` is set in emailbison-sync environment
3. Test manually: `curl -X POST https://api.wizardgrimoire.cloud/api/slack/trigger-audit`
4. Check worker didn't restart during the audit window (resets `last_slack_audit`)

### CSV download fails
1. Verify `PUBLIC_API_URL` points to accessible API
2. Check API is responding: `curl https://api.wizardgrimoire.cloud/health`

### Buttons not working
- Slack buttons use `PUBLIC_API_URL` for links
- Ensure URL is publicly accessible (via Cloudflare tunnel)
