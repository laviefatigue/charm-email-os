# EmailBison Sync — Issues Found 2026-04-13

Three bugs identified during routine sync check. All three fixed and deployed.

---

## Issue 1 — Health checks silently failing for every workspace

**Severity:** High — health checks have been a no-op  
**Status:** Fixed and deployed

### What was happening

The sync worker runs health checks every 15 minutes to evaluate inbox and domain health and detect kill triggers. Every single workspace was failing with a silent database error that never appeared in the printed logs — only in the `sync_audit_log` table.

Error logged in `sync_audit_log.error_details`:
```
operator does not exist: kill_trigger_type ~~ unknown
HINT: No operator matches the given name and argument types. You might need to add explicit type casts.
```

### Root cause

The `kill_trigger` column in `sender_accounts` is a PostgreSQL **enum** type (`kill_trigger_type`). PostgreSQL enums do not support the `LIKE` (`~~`) operator. Two queries used:
```sql
OR kill_trigger LIKE 'provider_block_%'
```

### Affected files

- `sync_modules/health_checks.py` line 612 — domain health scoring query
- `sync_modules/kill_processor.py` line 751 — same count used in kill evaluation

### Fix

Added `::text` cast in both locations:
```sql
OR kill_trigger::text LIKE 'provider_block_%'
```

### Impact

Health checks were processing 0 triggers reported, but the internal logic never ran. Domain state updates, complaint rate checks, and burn threshold evaluations were all skipped for every cycle since the enum was introduced. No false positives created — the system was just not checking.

---

## Issue 2 — Lifecycle tag sync reporting FAILED every cycle

**Severity:** Medium — sync appeared broken but graduation was still working  
**Status:** Fixed and deployed

### What was happening

The lifecycle tag sync graduates inboxes from `incubating` → `live` in EmailBison by adding/removing tags. Every cycle, the sync logged `[FAILED]` even when graduation work completed successfully.

Console output:
```
[WARN] Failed to remove 'incubating' tag from inbox 3278 (rvollmer.r@dewspoutwater.com): HTTP 422
[WARN] Failed to remove 'incubating' tag from inbox 9060 (rvollmer.v@mistspoutwater.com): HTTP 422
Lifecycle Tags: 1 graduated to live, 0 new incubating, 0 dead removed [FAILED]
```

### Root cause

Two queries in `lifecycle_tag_sync.py` — `_graduate_mature_inboxes` and `_tag_new_warmup_inboxes` — both used:
```sql
WHERE workspace_id = $1
AND inbox_state = 'live'
```

They were **missing `AND is_active = TRUE`**. This caused them to pick up inboxes that had been deactivated on our side (`is_active = FALSE`) but still had `inbox_state = 'live'` as a stale value.

When the sync tried to add/remove EB tags for these inboxes, EB returned HTTP 422 (`The selected sender_email_ids.0 is invalid`) because those inbox IDs no longer exist in EB's system.

Stale inboxes involved:
- `rvollmer.r@dewspoutwater.com` — `is_active: false`, domain `dewspoutwater.com` (live pool)
- `rvollmer.v@mistspoutwater.com` — `is_active: false`, domain `mistspoutwater.com` (burned)

### Fix

Added `AND is_active = TRUE` to both queries in `sync_modules/lifecycle_tag_sync.py`.

### Impact

Lifecycle sync was functional — actual graduations were completing. The `[FAILED]` status was a false alarm caused by the stale inbox attempts. Fix eliminates the 422 errors and restores accurate sync status reporting.

---

## Issue 3 — Campaign 175 (Search Atlas) causing 404 log spam

**Severity:** Low — log noise, no functional impact  
**Status:** Fixed in DB

### What was happening

The events sync (runs every 5 minutes) was fetching replies/bounces/spam for campaign 175 ("Search Atlas Cycle 1: Campaign 1, SEMRush") and receiving HTTP 404 every time:

```
Error fetching inbox for campaign 175: HTTP 404: {"data":{"success":false,"message":"Record not found."}}
Error fetching bounced for campaign 175: HTTP 404: ...
Error fetching spam for campaign 175: HTTP 404: ...
```

### Root cause

Campaign 175 was **deleted from EmailBison directly** (via the EB UI or API) but our database still had it as `campaign_status = 'paused'`. The events sync queries campaigns where `campaign_status IN ('active', 'running', 'sending', 'paused')` — so it kept retrying every 5 minutes.

### Fix

Updated in DB (no code change needed):
```sql
UPDATE emailbison_campaigns
SET campaign_status = 'archived', campaign_state = 'dead'
WHERE emailbison_campaign_id = '175'
```

`archived` is excluded from the events sync's active-campaign filter. Campaign data is preserved in our DB — nothing was deleted.

### Impact

Pure log noise. No data was lost, no sync was broken. Events sync will no longer query this campaign.

---

---

## Issue 4 — Engagement sync crashing on every workspace every 30s

**Severity:** High — no engagement data captured since concurrent queue was deployed  
**Status:** Fixed and deployed (`848c8d8`)

### What was happening

Every engagement sync was failing immediately with:
```
object NoneType can't be used in 'await' expression
```

Because `last_successful_sync` was being stamped even on failures (see Issue 5), the flood of failures silently stopped — but engagement data stopped being captured entirely.

### Root cause

`AuditContext.increment_processed()`, `increment_created()`, `increment_updated()`, and `add_error()` are synchronous methods. `sync_engagement.py` called them with `await`, returning `None` from each call. `await None` raises the NoneType error immediately on the first inbox.

The other sync modules call these methods correctly without `await` — only engagement had this bug.

### Fix

Removed `await` from 5 calls in `sync_modules/sync_engagement.py`.

---

## Issue 5 — sync_status updated on failures, masking crashes and blocking retries

**Severity:** High — silent failure mode across all sync types  
**Status:** Fixed and deployed (`de2e108`)

### What was happening

`WorkspaceSyncQueue._run_job()` called `audit_logger.update_sync_status()` unconditionally after every job — success or failure. This stamped `last_successful_sync` even when the sync crashed, so:
- The scheduler treated the workspace as "recently synced" and didn't re-queue it
- Failed syncs waited a full interval (up to 24h for engagement) before being retried
- The engagement flood from Issue 4 stopped naturally, but engagement data silently stopped too

### Fix

Added `if result.status != 'failed':` guard around `update_sync_status()` in `workspace_sync_queue.py`. Also cleared all stale engagement `sync_status` records via DB so syncs ran immediately post-fix.

---

## Issue 6 — kill_processor marking kills as failed when backup promotion hits EB error

**Severity:** Medium — 182 kill queue items incorrectly failed; kills were completing in DB but not in EB  
**Status:** Fixed and deployed (`be189f8`)

### What was happening

`_promote_backup_inbox()` makes EB API calls but was nested inside the DB step's `try/except` block. When it raised an EB error (HTTP 422 from stale workspace context), the DB exception handler caught it and:
- Marked the kill_queue item as `failed`
- Set `tag_name = NULL` (the kill_queue UPDATE that sets tag_name was rolled back at app level)
- Skipped the EB tagging step entirely

Result: 182 items in `failed` state — 170 with inbox already dead in DB but no EB flagging tag applied.

### Fix

Moved `_promote_backup_inbox()` into its own isolated `try/except` after the DB step closes. Promotion failures now log a warning but the kill continues to the EB tagging step. The 170 dead-in-DB items were reset to `eb_pending` for retry; 12 stale duplicates were deleted.

---

## Summary

| # | Issue | Root Cause | Fixed |
|---|-------|------------|-------|
| 1 | Health checks failing for all workspaces | `kill_trigger` enum used with `LIKE` without `::text` cast | Code fix, deployed |
| 2 | Lifecycle tag sync showing FAILED | Missing `is_active = TRUE` on graduation queries | Code fix, deployed |
| 3 | Campaign 175 — 404 on every events poll | Campaign deleted from EB, not marked in our DB | DB update |
| 4 | Engagement sync crashing every workspace every 30s | `await` on sync AuditContext methods (non-async) | Code fix, deployed |
| 5 | sync_status stamped on failures — masked crashes, blocked retries | `update_sync_status()` called unconditionally in queue dispatcher | Code fix, deployed |
| 6 | Kill processor marking kills failed on backup promotion EB error | `_promote_backup_inbox()` inside DB step try block | Code fix, deployed |

Commits: `faebccb` (health checks), `7a0c2a2` (lifecycle tags), `848c8d8` (engagement), `de2e108` (sync_status), `be189f8` (kill_processor)
