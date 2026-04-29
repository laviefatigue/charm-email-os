---
title: EmailBison API — Deep Dive (for EOD Reapply)
status: reference
created: 2026-04-29
source: https://spellcast.hirecharm.com/api/reference.openapi
---

# EmailBison API — Deep Dive (for EOD Reapply)

This is the operator-and-builder reference for the EB endpoints relevant to the EOD reapply tool, distilled directly from the live OpenAPI spec at `https://spellcast.hirecharm.com/api/reference.openapi` (cached as `eb-openapi.json`, ~620KB).

It's organized for two reads: **what the tool uses today** (sections 1–4), and **what we don't use yet but should know about** for v2 scope and operator improvisation (sections 5–7).

---

## 1. Authentication & headers

- **Scheme**: HTTP Bearer (`Authorization: Bearer <token>`).
- **Token format**: Laravel Sanctum, `{id}|{plain_text}` (e.g. `39|RYHi6oE6o0fVuEPEDSUe6dN7tCFJwvJ6cAytBKxq69deeeee`).
- **Workspace scoping**: tokens are created per-workspace via super-admin endpoint `POST /api/workspaces/v1.1/{team_id}/api-tokens`. Every request made with such a token is implicitly scoped to that workspace; **no `switch-workspace` call needed or possible**. Each token has an `abilities` array — `["*"]` means full access.
- **Stored at**: `workspace_api_keys.key_token` (plaintext column). Joined to `workspaces` via `workspace_id`. Schema:
  ```sql
  SELECT w.id, w.workspace_name, w.emailbison_workspace_id, k.key_token
  FROM workspaces w
  JOIN workspace_api_keys k ON k.workspace_id = w.id AND k.is_active = TRUE
  WHERE w.workspace_name = $1 AND w.is_active = TRUE
  ```
- **Required headers**: `Authorization`, `Accept: application/json`. For mutations: `Content-Type: application/json`.
- **Response wrapping**: most endpoints return `{"data": <object|array>}`. Some (`/attach-sender-emails`, `/remove-sender-emails`) return bare `{"success": bool, "message": str}`. Our client unwraps `data` automatically.
- **Example types from spec**: schemas often declare response bodies as `text/plain` with a JSON-string example (especially older endpoints). In practice, EB returns `application/json`. Don't trust the `text/plain` content-type in the spec.

---

## 2. The 8 endpoints the tool uses

### 2.1. `GET /api/campaigns/{id}` — fetch campaign

Returns the full campaign object with current `status`. Used to short-circuit if the campaign isn't in an actively-sending state.

**Response shape (unwrapped):**
```json
{
  "id": 1, "uuid": "9h8ef374-...", "name": "John Doe Campaign",
  "type": "outbound",
  "status": "Active",
  "emails_sent": 7, "opened": 2, "unique_opens": 1, "replied": 2,
  "unique_replies": 1, "bounced": 1, "unsubscribed": 2, "interested": 3,
  "total_leads_contacted": 7, "total_leads": 10,
  "max_emails_per_day": 7, "max_new_leads_per_day": 2,
  "plain_text": true, "open_tracking": false,
  "sequence_prioritization": "new_leads",
  "can_unsubscribe": true, "unsubscribe_text": "Unsubscribe here",
  "created_at": "2025-04-14T16:59:21.000000Z",
  "updated_at": "2025-05-18T12:53:32.000000Z",
  "tags": [{"id": 1, "name": "VIP", "default": false}]
}
```

**Status enum** (from `POST /api/campaigns` query schema):
```
draft, launching, active, stopped, completed, paused, failed, queued, archived, "pending deletion", deleted
```

⚠️ **Discrepancy I hit and the orchestrator currently does not handle**:
- The query-param enum is **lowercase** (`active`, `paused`).
- Response body returns **capitalized** strings (`"Active"`, `"Paused"`, `"Launching"`).
- Our orchestrator lowercases before comparison — correct.
- Our `_ACTIVE_STATUSES = {"active", "queued", "sending"}` — **but `"sending"` is NOT in the enum**. Real values to consider as "actively running":
  - `active` — operating
  - `queued` — scheduled to send
  - `launching` — preparing to send (we currently SKIP this; should reconsider)
- `paused`, `stopped`, `archived`, `completed`, `failed`, `draft` — not active.
- L5 should observe what `Sending` (if it exists) returns; if not, drop from our set.

### 2.2. `GET /api/campaigns/{id}/schedule` — view schedule

This is what we built `evaluate_window` around. Returns the campaign's M-F send pattern, hours, timezone.

**Response (unwrapped):**
```json
{
  "id": 1,
  "type": "Generated",
  "monday": true, "tuesday": true, "wednesday": true,
  "thursday": true, "friday": true,
  "saturday": false, "sunday": false,
  "start_time": "08:00",
  "end_time": "17:00",
  "timezone": "America/New_York",
  "created_at": "...",
  "updated_at": "..."
}
```

- `start_time` / `end_time`: documented as `HH:MM`. Our parser also accepts `HH:MM:SS` defensively.
- `timezone`: IANA name. Spec example uses `America/New_York`, `Australia/Sydney` is implied.
- `type`: `"Generated"` (ad-hoc) or implies `"Template"` (saved template). Not used by us.

### 2.3. `PATCH /api/campaigns/{id}/pause` — pause campaign

**Response (unwrapped):**
```json
{
  "id": 1, "name": "...", "status": "Paused",
  ...everything else from get_campaign...,
  "tags": [...]
}
```

⚠️ **Operator note**: spec returns `text/plain` content-type but JSON body. Status field is `"Paused"` (capitalized).

### 2.4. `PATCH /api/campaigns/{id}/resume` — resume campaign

**Response (unwrapped):**
```json
{
  "id": 1, "status": "Queued", ...
}
```

⚠️ **Resume returns status `"Queued"`, not `"Active"`** in the spec example. Operationally this means: after resume, the campaign is in the EB scheduler queue, will become `Active` on next send tick. Our verification doesn't check post-resume status (we only verify the sender-set), so this isn't a problem — but it's worth knowing.

### 2.5. `GET /api/campaigns/{id}/sender-emails` — list attached senders

**Response (unwrapped):**
```json
[
  {
    "id": 1, "name": "John Doe", "email": "john@doe.com",
    "imap_server": "...", "imap_port": 110,
    "smtp_server": "...", "smtp_port": 112,
    "daily_limit": 5, "type": "Inbox",
    "status": "Connected",
    "emails_sent_count": 100, "total_replied_count": 10, ...
    "tags": [{"id": 1, "name": "Google", "default": true}]
  },
  ...
]
```

⚠️ **No pagination metadata in the spec.** Spec defines no `page`, `per_page`, `meta.last_page`. Our existing internal `EmailBisonClient.get_sender_accounts()` *does* paginate `/api/sender-emails` with `page` + `per_page`, so the convention exists in practice. For `/api/campaigns/{id}/sender-emails`, we treat it as a single-shot list. If a campaign ever has > 100 senders this becomes an L5-unknown.

The per-sender object includes a useful `status` field — `Connected | Not connected | Disconnected | etc.` — that we don't currently use, but could (see §6.2).

### 2.6. `GET /api/sender-emails?tag_ids[0]=N` — list senders by tag

This is the workspace-scoped paginated query. The target set comes from here.

**Query parameters (verified in spec):**
| Param | Type | Notes |
|---|---|---|
| `search` | string | text search, optional |
| `tag_ids` | int[] | indexed array `tag_ids[0]=5&tag_ids[1]=6` |
| `excluded_tag_ids` | int[] | inverse filter |
| `without_tags` | bool | only untagged senders |
| `status` | enum | `connected, not_connected, pending_move, pending_deletion` |

⚠️ **Pagination**: not formally documented in the spec for this endpoint. Existing repo code (`sync_modules/emailbison_client.py`) uses `page` + `per_page=100` and looks for `meta.last_page` in the response. **Our client matches that convention** (`tag_ids[0]=N&page=1&per_page=100`) and has a 1000-page safety limit.

⚠️ **Note**: spec example response is a bare list (no `meta`), but real API responses likely have `meta` because pagination is needed. L5 step 2 confirms.

### 2.7. `POST /api/campaigns/{id}/attach-sender-emails`

**Request:**
```json
{ "sender_email_ids": [1, 2, 3] }
```

**Response:**
```json
{ "success": true, "message": "Sender emails successfully added to Campaign One." }
```

⚠️ **Spec types `sender_email_ids` items as `string`** (`items: { type: string }`), but the example shows integers `[1, 2, 3]`. Our client sends integers. L5 step 5 must confirm integers work — the spec is almost certainly wrong, not the practice.

⚠️ **Response does NOT echo which IDs were actually attached**. We must verify by re-fetching `GET /api/campaigns/{id}/sender-emails` — our orchestrator does. Hard set-equality check.

⚠️ **No `skip_webhooks` option** here (compare with `/api/tags/attach-to-sender-emails` which does have it). Every reapply will fire whatever campaign-level webhooks are configured. Mention to ops.

### 2.8. `DELETE /api/campaigns/{id}/remove-sender-emails`

**Request body** (DELETE with body — non-standard but supported by EB and httpx):
```json
{ "sender_email_ids": [4, 5] }
```

**Response:**
```json
{ "success": true, "message": "Sender emails sent for deletion. This may take a moment." }
```

⚠️ **"This may take a moment"** message hints at **eventual consistency**. The remove call returns 200 immediately, but the senders may not be detached from the campaign until a background job processes. Our verify-by-refetch will fail in this case.

**Mitigation in v1**: if verify fails (set != target), we still resume and return `FAILED_POST_RESUME` (exit 2). Operator inspects.

**Mitigation for v2**: add a configurable verify-poll-with-timeout (e.g. retry the verify fetch every 2s for up to 15s before giving up).

⚠️ **Spec description says "remove sender emails from a draft or paused campaign"** — confirming pause is mandatory before remove.

### 2.9. `GET /api/tags` — resolve `live` tag id

Used once per run to map `"live"` → numeric id.

**Response (unwrapped):**
```json
[
  {"id": 1, "name": "Important", "default": false, "created_at": "...", "updated_at": "..."},
  {"id": 2, "name": "Interested", "default": true, ...}
]
```

⚠️ **`default: true`** identifies system/built-in tags (like `Interested`). Custom tags like `live`, `reserve`, `incubating` have `default: false`. Don't delete tags with `default: true`.

⚠️ **Tag names are workspace-scoped**: `live` in the Charm workspace is a different numeric id than `live` in the Sammy workspace. Our `resolve_tag_id` is exact-name match, case-sensitive. If a workspace has `Live` (capitalized), we won't find it. L5 step 2 must confirm the casing convention in production.

---

## 3. Response wrapping conventions

| Endpoint family | Wrapper | Example |
|---|---|---|
| Most endpoints | `{"data": <object/array>}` | `GET /api/campaigns/{id}` |
| Bulk operations | bare `{"success": bool, "message": str}` | `POST /attach-sender-emails`, `DELETE /remove-sender-emails` |
| Status-changing PATCHes | `{"data": <full campaign>}` | `PATCH /pause`, `PATCH /resume` |
| List endpoints (paginated) | `{"data": [...], "meta": {"last_page": N, "current_page": M, ...}}` | `GET /api/campaigns?page=N` |

Our `EBClient._unwrap()` normalizes the first three. Pagination is handled per-endpoint where needed.

---

## 4. Error response shape

⚠️ **Not formally documented in the spec.** Observed patterns:

- `400/422` (validation): typically `{"error": "validation message", "errors": {...}}`
- `401`: probably `{"message": "Unauthenticated."}` — Laravel default
- `403`: `{"error": "forbidden"}` — varies
- `404`: `{"data": {"success": false, "message": "...", "record_not_found": null}}` (we saw this at root probes)
- `5xx`: HTML body in some cases, JSON in others

Our `EmailBisonAPIError` captures `status_code`, `message`, and `response_body` (parsed JSON if possible, else raw text). The orchestrator only branches on `status_code`, never on body content — robust to error-shape drift.

---

## 5. Endpoints we don't use yet but should know about

### 5.1. `GET /api/campaigns/sending-schedules` — workspace-wide live forecast

```bash
GET /api/campaigns/sending-schedules
Body: { "day": "today" | "tomorrow" | "day_after_tomorrow" }
```

Returns every campaign in the workspace that will send on that day, with `emails_being_sent` counts. Useful for:
- Confirming a campaign actually has emails queued before we reapply (sanity check)
- Batch reapply discovery for v2 — instead of polling per-campaign, get the set of campaigns scheduled to send today and reapply each

⚠️ Quirk: `status` in this response is **numeric (0, 1, 2, ...)** not the string enum. Don't cross-reference with the string status values. The numeric mapping isn't documented.

### 5.2. `GET /api/campaigns/{id}/sending-schedule` — single-campaign live forecast

Same shape as above but for one campaign. Useful sanity check before our reapply: "is this campaign actually going to send anything tomorrow? if not, no point reapplying."

### 5.3. `GET /api/campaigns/schedule/available-timezones` — IANA whitelist

Returns the authoritative list of timezones EB accepts:
```json
[
  {"name": "(GMT-12:00) International Date Line West", "id": "Pacific/Kwajalein"},
  {"name": "(GMT-11:00) Midway Island", "id": "Pacific/Midway"},
  {"name": "(GMT-11:00) Samoa", "id": "Pacific/Apia"},
  ...
]
```

Use case: when the schedule update flow is added (v2 or fix for the hardcoded NY tz in `api/routes/strategy.py:1572`), validate against this list. Don't rely on Python's `zoneinfo` accepting a name and assume EB will too.

### 5.4. `POST /api/campaigns/{id}/schedule` — create schedule

Takes the same body shape we already write in `api/routes/strategy.py`. Returns `{"data": <schedule>}`. Note: returns `201` on create vs `200` on update.

### 5.5. `PUT /api/campaigns/{id}/schedule` — update schedule

Same body shape; `200` response. Use this to fix wrong timezone on existing campaigns (the Sammy/Australia hardcoded-NY bug).

### 5.6. `POST /api/campaigns/{id}/create-schedule-from-template`

```json
{ "schedule_id": 5 }
```

Apply a saved schedule template (created via `save_as_template: true` on the create-schedule call). Operationally useful: define one canonical "M-F 8am-5pm Sydney" template, apply it to all Sammy campaigns instead of copy-pasting fields.

### 5.7. `GET /api/sender-emails/{id}/campaigns` — reverse lookup

Returns the campaigns a single sender is attached to. Cross-cutting view useful for:
- Verifying our reapply diff is complete (every dead inbox should be removed from every campaign it was on)
- The existing `sync_campaigns.sync_campaign_inbox_assignments()` already uses this

### 5.8. `POST /api/tags/attach-to-sender-emails` — bulk inbox tagging

```json
{
  "tag_ids": [5],
  "sender_email_ids": [10, 11, 12],
  "skip_webhooks": false
}
```

⚠️ **Has `skip_webhooks` option** that the campaign-level attach/remove does NOT. Useful for `lifecycle_tag_sync` and `kill_processor` background work where you don't want to fire webhook noise.

### 5.9. `POST /api/tags/remove-from-sender-emails`

Counterpart to 5.8. Note: **this is the correct way to detach a tag**, NOT `DELETE /api/tags/attach-to-sender-emails` (which the codebase historically misused — see [docs/decisions/EMAILBISON-UNTAG-ENDPOINT-FIX.md](../../../docs/decisions/EMAILBISON-UNTAG-ENDPOINT-FIX.md)).

---

## 6. Concrete uses for our reapply tool

### 6.1. Pre-reapply: verify campaign has work to do

Before pausing, call `GET /api/campaigns/{id}/sending-schedule` with `day: today`. If `emails_being_sent == 0`, the reapply is a no-op for the day's send (the campaign is empty or paused already). We can either skip with a clean status or proceed for tomorrow.

```python
# v2 enhancement — not in v1
forecast = await eb._request("GET", f"/api/campaigns/{cid}/sending-schedule",
                              json={"day": "today"})
emails_today = forecast.get("data", {}).get("emails_being_sent", 0)
if emails_today == 0:
    # Skip with note in audit
    ...
```

Worth adding in v2; not v1.

### 6.2. Filter target set by sender connection status

The target set is "every sender with the `live` tag." But what if some `live` senders are `Disconnected`? Attaching them is technically valid but they won't send. For maximum safety, filter:

```bash
GET /api/sender-emails?tag_ids[0]=<live_id>&status=connected
```

This gives us senders that are *both* `live`-tagged *and* currently `Connected`. **We don't do this in v1** because:
- The `live` tag is supposed to imply connection (it's removed by `kill_processor` on disconnect)
- Adding the filter masks bugs in lifecycle_tag_sync
- L1-L4 don't test this combination

For v2, consider an opt-in flag `--require-connected` that adds the status filter. Default off until lifecycle drift is observed.

### 6.3. Skip webhooks during heavy reapply

Not available on `/attach-sender-emails` — every reapply will fire campaign webhooks. If the workspace has a webhook for "campaign sender added", it gets N events per reapply. Document this for ops; consider asking EB to add `skip_webhooks` here too.

### 6.4. Schedule template normalization (v2 stretch)

If the reapply tool ever gets schedule-fixing capability:
1. `GET /api/campaigns/schedule/available-timezones` — validate input
2. `POST /api/campaigns/schedule/templates` (didn't dig in but exists) — define one template per region
3. `POST /api/campaigns/{id}/create-schedule-from-template` — apply

Cleaner than per-campaign field updates, and harder to mess up.

### 6.5. v2 scheduler discovery query

Instead of querying our local DB for active campaigns, the scheduler can:
```bash
GET /api/campaigns?status=active   # then status=queued, then status=launching
```

Returns the EB-side authoritative list. Cross-reference with our `emailbison_campaigns` table. Probably faster than per-campaign GET on every poll tick.

---

## 7. Open questions (answerable only via L5 staging)

1. **Pagination on `/api/campaigns/{id}/sender-emails`** — does it paginate, or always return all? If paginate, what's the convention?
2. **Pagination on `/api/sender-emails?tag_ids[]=N`** — does the response include `meta.last_page` despite the spec example omitting it?
3. **Eventual consistency on attach/remove** — is the verify-fetch reliable immediately, or do we need a poll-with-timeout?
4. **Idempotent attach** — does posting an already-attached `sender_email_id` silently dedup, error, or produce a duplicate?
5. **Idempotent remove** — does a remove call for a non-attached id silently no-op, error, or what?
6. **Pause synchronicity** — does `PATCH /pause` return 200 only after status flips, or is it eventually consistent?
7. **Campaign status `"Sending"`** — does this string appear in real responses, or is it always `"Active"`?
8. **`launching` status** — should we treat this as in our active set, or skip?
9. **`skip_webhooks` request-level missing on /attach-sender-emails** — confirm with EB whether the option simply isn't supported, or if undocumented support exists.
10. **Sender object `status` values** — spec lists `connected | not_connected | pending_move | pending_deletion` for the query filter, but the response example shows `"Connected"` capitalized. Are response values lowercase too, or capitalized?

Each of these is a row in [STAGING-RUNBOOK.md](../STAGING-RUNBOOK.md). Don't promote past L5 until each has a documented answer.

---

## Quick reference — curl recipes

All examples assume:
```bash
EB_KEY='<workspace api key from workspace_api_keys.key_token>'
EB='https://spellcast.hirecharm.com/api'
CID=42  # campaign id
```

```bash
# Get campaign
curl -H "Authorization: Bearer $EB_KEY" "$EB/campaigns/$CID"

# Get schedule
curl -H "Authorization: Bearer $EB_KEY" "$EB/campaigns/$CID/schedule"

# Pause
curl -X PATCH -H "Authorization: Bearer $EB_KEY" "$EB/campaigns/$CID/pause"

# Resume
curl -X PATCH -H "Authorization: Bearer $EB_KEY" "$EB/campaigns/$CID/resume"

# Current campaign senders
curl -H "Authorization: Bearer $EB_KEY" "$EB/campaigns/$CID/sender-emails"

# Senders with 'live' tag (assume tag_id=5)
curl -H "Authorization: Bearer $EB_KEY" \
  "$EB/sender-emails?tag_ids%5B0%5D=5&page=1&per_page=100"

# Senders with 'live' tag AND connected
curl -H "Authorization: Bearer $EB_KEY" \
  "$EB/sender-emails?tag_ids%5B0%5D=5&status=connected&page=1&per_page=100"

# Attach senders
curl -X POST -H "Authorization: Bearer $EB_KEY" -H "Content-Type: application/json" \
  -d '{"sender_email_ids":[10,11,12]}' \
  "$EB/campaigns/$CID/attach-sender-emails"

# Remove senders (DELETE with body)
curl -X DELETE -H "Authorization: Bearer $EB_KEY" -H "Content-Type: application/json" \
  -d '{"sender_email_ids":[99]}' \
  "$EB/campaigns/$CID/remove-sender-emails"

# Workspace tags
curl -H "Authorization: Bearer $EB_KEY" "$EB/tags"

# Today's sending forecast for one campaign
curl -X GET -H "Authorization: Bearer $EB_KEY" -H "Content-Type: application/json" \
  -d '{"day":"today"}' \
  "$EB/campaigns/$CID/sending-schedule"

# Available timezones (workspace-wide)
curl -H "Authorization: Bearer $EB_KEY" "$EB/campaigns/schedule/available-timezones"
```
