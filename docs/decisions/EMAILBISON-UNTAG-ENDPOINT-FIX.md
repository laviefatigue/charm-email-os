# EmailBison Untag Endpoint Bug — Root Cause & Fix

**Date:** 2026-03-11
**Status:** Fix Pending
**Severity:** High — causes incorrect tag state in EmailBison

## Problem

Inboxes in EmailBison are appearing with BOTH `live` and `reserve` tags simultaneously. Only one should ever be present.

Screenshot evidence: startselery.com inboxes in EmailBison showing both tags applied.

## Root Cause

`emailbison_client.py` `untag_inbox()` uses the **wrong HTTP method and endpoint** to remove tags:

```python
# WRONG — this endpoint does not exist
await self._request('DELETE', '/tags/attach-to-sender-emails', ...)

# CORRECT — EmailBison API for removing tags
await self._request('POST', '/tags/remove-from-sender-emails', ...)
```

The DELETE request to `/tags/attach-to-sender-emails` returns an error, which is silently caught (`except: pass`) in `set_tag_sync.py` line 436-440. The old tag remains, and the new tag gets added on line 443, resulting in dual tags.

The same bug exists in the one-off script `scripts/apply_selery_sets.py` `bulk_untag()` function (lines 237-247), which also accepts 404 as success (`r.status_code in (200, 204, 404)`).

## EmailBison Tag API (Correct Reference)

| Operation | Method | Endpoint | Body |
|-----------|--------|----------|------|
| Add tags | `POST` | `/tags/attach-to-sender-emails` | `{"tag_ids": [...], "sender_email_ids": [...]}` |
| Remove tags | `POST` | `/tags/remove-from-sender-emails` | `{"tag_ids": [...], "sender_email_ids": [...]}` |

**Both operations use POST.** The attach endpoint does NOT support DELETE.

## Files to Fix

1. **`sync_modules/emailbison_client.py`** (line 303-305)
   - Change: `'DELETE'` → `'POST'`, `'/tags/attach-to-sender-emails'` → `'/tags/remove-from-sender-emails'`

2. **`scripts/apply_selery_sets.py`** (line 241-245)
   - Change: `"DELETE"` → `"POST"`, path → `"/tags/remove-from-sender-emails"`
   - Remove 404 from accepted status codes

## Remediation Required

After fixing the code, a remediation script must:
1. Query all workspaces for inboxes that have BOTH `live` and `reserve` tags
2. For each dual-tagged inbox, determine the correct tag from domain `pool_status`
3. Remove the incorrect tag using the CORRECT endpoint (`POST /tags/remove-from-sender-emails`)
4. Verify each inbox has exactly one tag after cleanup

## Prevention

- Unit test added to verify `untag_inbox()` calls the correct endpoint
- Silent error handling in `set_tag_sync.py` should log failures rather than swallowing them
- The `bulk_untag()` function should NOT accept 404 as a success code

## Lessons Learned

1. **Never accept 404 as success for mutation operations** — a 404 means the endpoint doesn't exist or the resource wasn't found, not that the operation succeeded
2. **Silent `except: pass` on API calls hides critical failures** — at minimum, log the error
3. **EmailBison uses POST for both attach and remove** — don't assume REST conventions (DELETE for removal)
