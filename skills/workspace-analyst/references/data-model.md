# Data Model — what to query, what each table means

The Charm DB is your substrate. This file is the orientation map. Read it before your first query in a session.

## Access

- Admin SQL endpoint: `POST https://api.wizardgrimoire.cloud/api/admin/run-sql?key={ADMIN_KEY}&sql={SQL}`
- Returns `{"result": [...rows]}` for SELECT, `{"result": "OK"}` for non-SELECT statements
- SQL must be a single statement. `WITH` clauses sometimes get rejected — use inline subqueries
- Cast enum types to `text` before using string filters: `kill_trigger::text`, `pool_status::text`
- Pages of >5k rows are slow; paginate or aggregate server-side

## Core tables

### `workspaces`
The top-level tenant. One row per client workspace.

| Column | Notes |
|---|---|
| `id` | UUID — primary key, used everywhere as `workspace_id` |
| `workspace_name` | Display name (e.g., "Selery") |
| `emailbison_workspace_id` | The integer EB workspace ID (e.g., "22") |
| `client_id` | FK → `clients` |
| `is_active` | Filter to active workspaces for fleet-wide rollups |
| `sender_account_count`, `domain_count` | **Denormalized** — may drift. Verify with COUNT if precision matters |
| `last_sync_at` | **Stale denorm** — does not reliably update. Trust `sender_accounts.updated_at` MAX instead |
| `provider` | `emailbison` or `instantly` — inbox-infrastructure platform for this workspace |
| `automation_enabled`, `eod_reapply_enabled` | Daemon control flags |
| `package_id` | FK → packages — what tier this workspace runs |
| `forwarding_domain_pattern` | If set, forwarding domains follow this pattern |

> The legacy `manages_via_hypertide` column was DROPPED in migration 133 (2026-05-19). HT-tracking is now per-client via `client_hypertide_subscriptions` (any chs row whose `client_id = w.client_id` → the workspace is HT-tracked). See [[hypertide-data-model-and-change-tracking]].

### `sender_accounts`
One row per sender inbox. The most-queried table.

| Column | Notes |
|---|---|
| `id`, `workspace_id`, `domain_id` | Keys |
| `email_address` | The sender address |
| `esp` | **`microsoft` or `gmail`** — always group by this for bounce/complaint analysis |
| `status` | Connection status — `Connected` or various disconnected states |
| `inbox_state`, `inventory_pool_status`, `inventory_lifecycle_status` | Pool state (live / reserve / killed / etc.) — see [DOMAIN-INBOX-STATUS-DEFINITIONS.md](../../../docs/core/DOMAIN-INBOX-STATUS-DEFINITIONS.md) |
| `killed_at`, `kill_trigger`, `kill_reason` | Kill metadata. `kill_trigger` is an enum — cast to text for grouping |
| `hard_bounces_24h`, `hard_bounces_7d`, `bounces_all_time` | **Counters populated from `response_messages`** (per [migration 053](../../../migrations/053_fix_warmup_bounce_pollution.sql)). Warmup bounces excluded. |
| `hard_blocked_24h`, `hard_unknown_24h` | Sub-categorized 24h counters |
| `bounce_rate_7d` | Per-inbox 7d rate — often near zero for individual inboxes; aggregate at workspace/domain level instead |
| `complaints_lifetime` | Spam complaint counter — drives 78% of kills historically |
| `warmup_spam_count`, `last_placement_spam` | Warmup-side spam signals |
| `warmup_started_at`, `warmup_score`, `warmup_enabled` | Warmup lifecycle |
| `health_score` | 0–100 composite |
| `disconnected_at` | If set, when the last disconnect happened |
| `emails_sent_all_time` | Lifetime send count |
| `daily_limit` | Configured cap |
| `updated_at` | **MAX of this is the true workspace sync recency** |

### `domains`
One row per sending domain.

| Column | Notes |
|---|---|
| `id`, `workspace_id`, `domain_name` | Keys |
| `provider` | Often `unknown` — registrar info incomplete |
| `pool_status` | Enum: `live`, `burned`, `reserve`, `cancelled`, `unassigned` |
| `domain_state` | Enum: `live`, `flagged`, `dead` |
| `domain_age_days` | Days since registration |
| `registration_date`, `purchased_at` | Provenance |
| `spf_configured`, `dkim_configured`, `dmarc_configured`, `mx_configured` | Auth flags. All four = full auth. Often `false` on unprovisioned inventory |
| `dns_records_configured` | Composite flag |
| `infrastructure_type`, `infrastructure_set_at` | M365 / Google Workspace / etc. — often null |
| `live_inbox_count`, `dead_inbox_count`, `quarantined_inbox_count` | Per-domain rollups |
| `domain_sends_7d`, `domain_bounces_7d`, `domain_bounce_rate_7d` | **STALE denorm — do not trust without verification.** Compute from `response_messages` instead |
| `domain_sends_all_time`, `domain_bounces_all_time` | Lifetime — more reliable but lags |
| `domain_complaint_count`, `domain_complaints_7d` | Complaint counters |
| `burn_velocity_30d`, `projected_days_to_critical` | Forecasting columns |
| `killed_at`, `kill_reason`, `burn_trigger` | Domain-level kill metadata |
| `hypertide_record_id`, `hypertide_subscription_id`, `hypertide_status` | Hypertide-managed lifecycle |
| `legitimacy_score`, `rationale` | Pre-purchase grading |

### `response_messages`
Event log of every message received by a sender inbox. **The authoritative bounce source.**

| Column | Notes |
|---|---|
| `id`, `workspace_id`, `campaign_id`, `sender_account_id` | Keys |
| `folder` | `inbox` (replies) or `bounced` (bounces). Filter to `bounced` for bounce analysis |
| `from_email`, `from_name` | Who sent the message (usually `mailer-daemon@...` or `postmaster@...` for bounces) |
| `to_inbox_email` | Our sending inbox that received the bounce |
| `subject` | Often `Undeliverable: ...` or `Delivery Status Notification (Failure)` |
| `body_preview`, `body_full` | The NDR body — contains intended recipient + reason text. Parse for recipient extraction |
| `bounce_type` | **`hard_unknown`, `hard_blocked`, `soft_temp`, `soft_full`, `unknown`** — the most useful categorization |
| `bounce_reason` | The SMTP code + reason text (e.g., `550 5.1.1 \| mailbox not found`) |
| `received_at` | Use for time-series binning |
| `is_interested`, `is_automated`, `sentiment` | Reply-classification fields (use when folder=`inbox`) |

### `emailbison_campaigns`
One row per EB campaign. Mid-grain — useful for per-campaign attribution.

| Column | Notes |
|---|---|
| `id`, `workspace_id`, `emailbison_campaign_id`, `campaign_name` | Keys |
| `campaign_status` | `active`, `paused`, `completed`, `draft` |
| `campaign_state` | Internal lifecycle enum |
| `total_leads`, `total_leads_contacted`, `emails_sent` | Volume |
| `bounces`, `bounce_rate` | Per-campaign bounce summary (synced from EB) |
| `complaints` | **Often 0 due to sync gap** — use `sender_accounts.complaints_lifetime` for ground truth |
| `inboxes_burned`, `domains_affected`, `inboxes_burned_7d`, `domains_burned_7d` | Burn attribution |
| `copy_age_days` | How old the copy is — stale copy correlates with engagement decline |
| `killed_at`, `kill_reason`, `quarantined_at` | Campaign-level kill state |

### `campaign_events`
Per-event log within campaigns (sends, opens, replies, bounces at event grain).

| Column | Notes |
|---|---|
| `event_type` | `sent`, `opened`, `replied`, `bounced`, etc. |
| `emailbison_lead_id`, `lead_email`, `lead_name`, `lead_company` | Recipient info |
| `event_data` | JSONB blob with EB-side detail |
| `event_timestamp` | For time-series |

Use this when you need to attribute bounces to specific leads or trace a campaign's send timeline.

### `daily_volume_snapshots`
Per-workspace per-day rollup. Useful for trend visualization.

| Column | Notes |
|---|---|
| `workspace_id`, `snapshot_date` | Composite key |
| `emails_sent`, `emails_delivered`, `emails_bounced`, `emails_complained` | **Cumulative running totals**, not per-day. Compute deltas manually |
| `live_inboxes`, `incubating_inboxes`, `dead_inboxes` | Pool counts that day |
| `kills_that_day` | Per-day delta |
| `capacity_utilization_pct` | Often shows `999.99` (overflow value — ignore) |

### `kill_trigger_events`, `health_events`, `campaign_burn_events`
Event tables for forensic investigation. Use when you need a chain of causality.

| Table | Use |
|---|---|
| `kill_trigger_events` | Per-kill detail (what threshold tripped) |
| `health_events` | Severity-tagged events with root-cause classification |
| `campaign_burn_events` | Which campaign burned which inbox/domain when |

### `inbox_bounce_summary`
A view that summarizes per-inbox bounce activity. Convenient for "top bouncers" queries.

| Column |
|---|
| `sender_account_id`, `email_address`, `inbox_state` |
| `hard_bounces_24h`, `hard_bounces_7d`, `soft_bounces_7d`, `total_bounces_7d` |
| `last_bounce_at` |

## Key enum values (cast `::text` before filtering)

| Enum | Values |
|---|---|
| `pool_status` (domains) | `live`, `burned`, `reserve`, `cancelled`, `unassigned` |
| `domain_state` (domains) | `live`, `flagged`, `dead` |
| `kill_trigger` (sender_accounts) | `spam_complaint`, `hard_blocked_24h`, `hard_bounces_24h`, `hard_bounce_rate_lifetime`, plus others |
| `bounce_type` (response_messages) | `hard_unknown`, `hard_blocked`, `soft_temp`, `soft_full`, `unknown` |

## Stale denorm — always verify

| Column | Why stale | Use instead |
|---|---|---|
| `workspaces.last_sync_at` | Not updated by syncs | `MAX(sender_accounts.updated_at) WHERE workspace_id=X` |
| `workspaces.sender_account_count` | Drift | `COUNT(*) FROM sender_accounts WHERE workspace_id=X` |
| `workspaces.domain_count` | Drift | `COUNT(*) FROM domains WHERE workspace_id=X` |
| `domains.domain_sends_7d`, `domain_bounces_7d`, `domain_bounce_rate_7d` | Can be wildly off | Compute from `response_messages.received_at >= NOW() - INTERVAL '7 days'` |
| `emailbison_campaigns.complaints` | Sync gap, often 0 | Aggregate `sender_accounts.complaints_lifetime` filtered to campaign window |

When in doubt, the **event log is the truth** (`response_messages`, `campaign_events`, `kill_trigger_events`, `health_events`). Counters and rollup columns can drift.

## Joins you'll reuse

```sql
-- Inbox → domain
sender_accounts sa JOIN domains d ON d.id = sa.domain_id

-- Inbox → workspace name
sender_accounts sa JOIN workspaces w ON w.id = sa.workspace_id

-- Bounce event → inbox → domain
response_messages rm
  JOIN sender_accounts sa ON sa.id = rm.sender_account_id
  JOIN domains d ON d.id = sa.domain_id
WHERE rm.folder = 'bounced'

-- Campaign → workspace
emailbison_campaigns ec
WHERE ec.workspace_id = '{workspace_id}'

-- Kill events → inbox → workspace
kill_trigger_events kte
  JOIN sender_accounts sa ON sa.id = kte.inbox_id
WHERE sa.workspace_id = '{workspace_id}'
```

## Resolving a workspace by name

```sql
SELECT id, workspace_name, emailbison_workspace_id, client_id
FROM workspaces
WHERE LOWER(workspace_name) LIKE '%{name}%'
```

Use this first when the operator names a workspace by string; resolve to UUID before substituting into other queries.
