# Charm Email OS - Data Dictionary

**Last Updated:** 2026-02-24
**Database:** PostgreSQL (charm-postgres:5432)
**Total Tables:** 91
**Total Enum Types:** 6

---

## Table of Contents

1. [Core Tables](#core-tables)
   - [sender_accounts](#sender_accounts)
   - [domains](#domains)
   - [emailbison_campaigns](#emailbison_campaigns)
   - [workspaces](#workspaces)
   - [kill_queue](#kill_queue)
2. [Enum Types](#enum-types)
3. [Common Pitfalls](#common-pitfalls)
4. [Field Naming Conventions](#field-naming-conventions)

---

## Core Tables

### sender_accounts

**Purpose:** The primary inbox tracking table. Each row represents a single email sending account (inbox) synced from EmailBison API.

**Row Count:** ~6,978 inboxes
**Primary Key:** `id` (UUID)
**Foreign Keys:** `workspace_id` → workspaces, `domain_id` → domains

#### Critical Fields

| Field | Type | Nullable | Default | Description | Business Rules |
|-------|------|----------|---------|-------------|----------------|
| **id** | uuid | NOT NULL | gen_random_uuid() | Primary key | - |
| **workspace_id** | uuid | NOT NULL | - | Client/workspace this inbox belongs to | FK to workspaces.id |
| **email_address** | varchar(255) | NOT NULL | - | Full email address (user@domain.com) | Unique constraint |
| **emailbison_account_id** | text | NULL | - | EmailBison API account ID | Used for API sync, can be NULL for legacy |
| **esp** | esp_type | NULL | 'other' | Email service provider type | **GROUND TRUTH** for infrastructure - gmail, microsoft, yahoo, other |
| **inbox_state** | inbox_state | NULL | 'live' | Current inbox state | live = active, dead = disconnected (NOT the same as burned!) |
| **kill_trigger** | kill_trigger_type | NULL | NULL | **Kill trigger that caused death** | **NULL = healthy disconnection**, NOT NULL = performance-based burn |
| **kill_reason** | text | NULL | NULL | Human-readable kill explanation | Set when kill_trigger fires |
| **killed_at** | timestamptz | NULL | NULL | When inbox was killed | Set when moved to dead state with kill_trigger |
| **disconnected_at** | timestamptz | NULL | NULL | When inbox disconnected from EmailBison | Set when status changes to "Not connected" |

#### State and Health Fields

| Field | Type | Default | Description | Critical Notes |
|-------|------|---------|-------------|----------------|
| **status** | varchar(50) | NULL | EmailBison connection status | "Connected", "Not connected", etc. - from EmailBison API |
| **health_score** | integer | NULL | EmailBison health score | 0-100, if available from API |
| **is_active** | boolean | true | Whether account is considered active | Used for filtering in queries |
| **first_seen_at** | timestamptz | now() | First time synced from EmailBison | Immutable after creation |
| **last_seen_at** | timestamptz | now() | Most recent sync where account present | Updated on every sync |
| **created_at** | timestamptz | now() | Record creation timestamp | Standard audit field |
| **updated_at** | timestamptz | now() | Record last modification | Updated by trigger on every change |

#### Role and Infrastructure

| Field | Type | Default | Description | Business Rules |
|-------|------|---------|-------------|----------------|
| **role** | inbox_role | 'primary' | Inbox role in domain portfolio | primary = active sending, hot_backup = warmed backup, warming = in warmup |
| **pool_tier** | varchar(20) | 'primary' | Rotation pool tier | primary (active), hot_backup (warmed), warming (warmup), retired (dead/rotated) |
| **inventory_pool_status** | varchar(20) | 'reserve' | Pool status | deployed (in campaigns), warning (needs cooldown), reserve (ready pool) |
| **inventory_lifecycle_status** | varchar(20) | 'incubating' | Lifecycle stage | active (mature), incubating (warmup), dead (killed) |

#### Kill Trigger Counters (24-Hour Rolling Windows)

| Field | Type | Default | Description | Threshold | Reset |
|-------|------|---------|-------------|-----------|-------|
| **hard_bounces_24h** | integer | 0 | **Combined hard bounces in 24h** | ≥2 triggers kill | Daily at midnight |
| **hard_blocked_24h** | integer | 0 | **Spam/policy rejections (550 5.7.x)** | ≥1 triggers kill | Daily at midnight |
| **hard_unknown_24h** | integer | 0 | **Bad addresses (550 5.1.1)** | ≥3 triggers kill | Daily at midnight |
| **consecutive_hard_bounces** | integer | 0 | Back-to-back hard bounces | ≥2 triggers kill | On any successful send |
| **complaints_lifetime** | integer | 0 | **Total spam complaints EVER** | ≥1 triggers INSTANT DEATH | Never resets |

**CRITICAL:** These are evaluated in priority order (see health_checks.py). `hard_blocked_24h` is highest priority (reputation damage), then `hard_unknown_24h` (list quality), then combined `hard_bounces_24h` as fallback.

#### 7-Day Metrics

| Field | Type | Default | Description | Used For |
|-------|------|---------|-------------|----------|
| **hard_bounces_7d** | integer | 0 | Hard bounces in last 7 days | Trend analysis, rate calculations |
| **soft_bounces_7d** | integer | 0 | Soft bounces in last 7 days | Not used for kills, monitoring only |
| **total_sends_7d** | integer | 0 | Total emails sent in 7 days | Denominator for bounce rate |
| **hard_bounce_rate_7d** | numeric(5,4) | NULL | Hard bounce rate % | >0.5% triggers kill (min 50 sends) |
| **total_bounce_rate_7d** | numeric(5,4) | NULL | Total bounce rate % | >5% triggers kill |

#### All-Time Metrics (Ground Truth)

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| **emails_sent_all_time** | integer | 0 | Total emails sent (lifetime) | EmailBison API `emails_sent_count` field |
| **replies_all_time** | integer | 0 | Total replies received | EmailBison API `total_replied_count` field |
| **bounces_all_time** | integer | 0 | Total bounces | EmailBison API `bounced_count` field |
| **daily_limit** | integer | 0 | Daily sending limit | EmailBison API `daily_limit` field |

**CRITICAL FOR ANALYSIS:** Use `emails_sent_all_time` for volume-adjusted metrics (e.g., burns per million emails).

#### Warmup Tracking

| Field | Type | Default | Description | Notes |
|-------|------|---------|-------------|-------|
| **warmup_enabled** | boolean | false | Whether warmup currently enabled | From EmailBison API |
| **warmup_started_at** | timestamptz | NULL | When warmup first detected | Tracked locally, not from API |
| **warmup_stopped_at** | timestamptz | NULL | When warmup disabled | Tracked locally |
| **inbox_age_days** | integer | NULL | Days since first seen | Calculated field |

#### Placement Testing (Future)

| Field | Type | Default | Description | Status |
|-------|------|---------|-------------|--------|
| **last_placement_test_at** | timestamptz | NULL | Last placement test timestamp | Not actively used yet |
| **last_placement_primary** | numeric(5,2) | NULL | % inbox placement | Not actively used yet |
| **last_placement_spam** | numeric(5,2) | NULL | % spam folder | Not actively used yet |
| **last_placement_other** | numeric(5,2) | NULL | % other (missing, etc.) | Not actively used yet |
| **consecutive_placement_failures** | integer | 0 | Placement test failures | Not actively used yet |

#### Retest Queue (Confirming Triggers)

| Field | Type | Default | Description | Process |
|-------|------|---------|-------------|---------|
| **flagged_for_retest** | boolean | false | Confirming trigger fired, needs 48h retest | Set by health_checks.py |
| **retest_scheduled_at** | timestamptz | NULL | When retest scheduled | +48h from flag |
| **retest_trigger** | kill_trigger_type | NULL | Which trigger needs confirmation | placement_failure, spam_folder_rate, degrading_trend |

#### Removal/Tagging System

| Field | Type | Default | Description | Process |
|-------|------|---------|-------------|---------|
| **removal_tagged** | boolean | false | Tagged for removal by warmup cleanup | System of record for tag state |
| **tagged_at** | timestamptz | NULL | When tagged for removal | Set by warmup cleanup flow |
| **removal_tag** | text | NULL | Kill trigger tag value | bounce_24h, bounce_7d, rbl_critical, warmup_failed, manual |
| **removal_tagged_at** | timestamptz | NULL | When tagged (duplicate?) | Consider consolidating with tagged_at |

#### Warning/Cooldown System

| Field | Type | Default | Description | Used For |
|-------|------|---------|-------------|----------|
| **warning_started_at** | timestamptz | NULL | When inbox entered warning status | Inventory management |
| **warning_reason** | text | NULL | Why inbox in warning | Inventory management |
| **cooldown_ends_at** | timestamptz | NULL | When cooldown ends, can return to reserve | Inventory management |

#### Metadata

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **display_name** | varchar(255) | NULL | Friendly display name |
| **notes** | text | NULL | Free-form admin notes |
| **domain_id** | uuid | NULL | FK to domains table |
| **last_check_run_id** | uuid | NULL | Most recent health check run |
| **last_synced_at** | timestamp | NULL | Last sync timestamp (no timezone) |

#### Provider-Specific Reputation (Unused)

| Field | Type | Default | Description | Status |
|-------|------|---------|-------------|--------|
| **gmail_reputation** | varchar(20) | NULL | Gmail Postmaster reputation | Not implemented |
| **microsoft_snds_status** | varchar(20) | NULL | Microsoft SNDS status | Not implemented |

---

### domains

**Purpose:** Domain health tracking and lifecycle management. Each row represents a sending domain (e.g., example.com) with associated sender accounts.

**Row Count:** ~509 domains
**Primary Key:** `id` (UUID)
**Foreign Keys:** `workspace_id` → workspaces, `purchase_job_id` → inbox_purchase_jobs

#### Critical Fields

| Field | Type | Default | Description | Business Rules |
|-------|------|---------|-------------|----------------|
| **id** | uuid | NOT NULL | Primary key | - |
| **workspace_id** | uuid | NOT NULL | Client workspace | FK to workspaces.id |
| **domain_name** | varchar(255) | NOT NULL | Domain (example.com) | Unique constraint |
| **domain_state** | domain_state | 'live' | Current state | live/flagged/dead |
| **sender_account_count** | integer | 0 | Number of inboxes on domain | Avg ~3 per domain |
| **is_active** | boolean | true | Whether domain is active | - |

#### Domain Health State Machine

| Field | Type | Default | Description | Transition Rules |
|-------|------|---------|-------------|------------------|
| **domain_state** | domain_state | 'live' | Current state | live → flagged (1 dead inbox) → dead (2+ dead inboxes) |
| **dead_inbox_count** | integer | 0 | Count of dead inboxes | 1 = flagged, 2+ = dead domain |
| **live_inbox_count** | integer | 0 | Count of live inboxes | Updated by triggers |
| **health_percentage** | numeric(5,2) | 100.00 | % of healthy inboxes | >15% unhealthy = investigation needed |
| **killed_at** | timestamptz | NULL | When domain marked dead | Set when state → dead |
| **kill_reason** | text | NULL | Why domain killed | e.g., "2+ inboxes burned" |

#### RBL Health Tracking

| Field | Type | Default | Description | Updated By |
|-------|------|---------|-------------|-----------|
| **latest_health_score** | numeric(5,2) | NULL | Most recent RBL score (0-100) | Denormalized from domain_check_summary |
| **latest_blacklist_count** | integer | NULL | Number of blacklists hit | From latest check |
| **latest_whitelist_count** | integer | NULL | Number of whitelists | From latest check |
| **is_clean** | boolean | NULL | TRUE if no blacklists | Quick filter for RBL issues |
| **last_checked_at** | timestamptz | NULL | Last RBL check | Updated by RBL checker |
| **next_check_at** | timestamptz | NULL | Next scheduled check | Used by scheduler |

#### Bounce and Complaint Tracking

| Field | Type | Default | Description | Window |
|-------|------|---------|-------------|--------|
| **domain_sends_7d** | integer | 0 | Total sends across all inboxes | 7-day rolling |
| **domain_bounces_7d** | integer | 0 | Total bounces across all inboxes | 7-day rolling |
| **domain_bounce_rate_7d** | numeric(5,4) | NULL | Domain-level bounce rate | Calculated |
| **domain_complaint_count** | integer | 0 | Total complaints | Lifetime |
| **inboxes_with_complaints** | integer | 0 | Count of inboxes with ≥1 complaint | Cross-inbox pattern detection |
| **inboxes_with_blocks** | integer | 0 | Count of inboxes with blocks | Cross-inbox pattern detection |

#### Burn Analysis

| Field | Type | Default | Description | Structure |
|-------|------|---------|-------------|-----------|
| **burn_breakdown** | jsonb | {} | Breakdown of kills by trigger type | `{"fresh_inbox_bounce": 5, "hard_bounces_24h": 2}` |
| **metrics_calculated_at** | timestamptz | NULL | When metrics last calculated | For cache invalidation |

#### Lifecycle Management

| Field | Type | Default | Description | Stages |
|-------|------|---------|-------------|--------|
| **lifecycle_stage** | varchar(20) | NULL | Current lifecycle stage | warming/ramping/establishing/peak/monitoring/rotation |
| **rotation_due_at** | timestamptz | NULL | Scheduled rotation date | Alert at 180d, force at 240d |
| **domain_age_days** | integer | NULL | Days since first seen | Calculated |
| **first_seen_at** | timestamptz | now() | First sync timestamp | Immutable |

#### Domain Purchase/Provisioning (Legacy)

| Field | Type | Default | Description | Status |
|-------|------|---------|-------------|--------|
| **approval_status** | varchar(20) | 'pending' | AI generation approval | Legacy - most domains from Hypertide |
| **reviewed_at** | timestamp | NULL | When reviewed | Legacy |
| **rationale** | text | NULL | Generation rationale | Legacy |
| **legitimacy_score** | double precision | NULL | AI legitimacy score | Legacy |
| **porkbun_price** | numeric(10,2) | NULL | Porkbun domain price | Legacy |
| **porkbun_available** | boolean | NULL | Available at Porkbun | Legacy |
| **dynadot_price** | numeric(10,2) | NULL | Dynadot domain price | Legacy |
| **dynadot_available** | boolean | NULL | Available at Dynadot | Legacy |
| **selected_provider** | varchar(20) | NULL | Selected registrar | Legacy |
| **purchased_at** | timestamp | NULL | Purchase timestamp | Legacy |
| **registration_date** | timestamptz | NULL | Domain registration date | Legacy |
| **job_id** | uuid | NULL | Associated job ID | Legacy |
| **purchase_job_id** | uuid | NULL | Purchase job reference | Legacy FK |
| **purchase_job_status** | text | NULL | Job status | Legacy |
| **cached_price** | numeric(10,2) | NULL | Cached price check | Legacy |
| **price_checked_at** | timestamp | NULL | Price check timestamp | Legacy |
| **last_price_check** | timestamptz | NULL | Last continuous check | Legacy |

#### Nameserver Configuration (Legacy)

| Field | Type | Default | Description | Status |
|-------|------|---------|-------------|--------|
| **nameservers_updated_at** | timestamp | NULL | When nameservers set | Legacy |
| **nameserver_status** | varchar(20) | 'pending' | NS update status | Legacy |
| **nameserver_verified_at** | timestamp | NULL | When NS verified | Legacy |
| **current_nameservers** | text[] | NULL | Array of current NS | Legacy |
| **available_for_setup_at** | timestamptz | NULL | When ready for setup | Legacy |

#### Infrastructure Classification

| Field | Type | Default | Description | **CRITICAL NOTE** |
|-------|------|---------|-------------|-------------------|
| **infrastructure_type** | varchar(20) | NULL | Infrastructure type | **ALWAYS NULL - DO NOT USE** |
| **infrastructure_set_at** | timestamp | NULL | When type set | **ALWAYS NULL - DO NOT USE** |
| **provider** | varchar(100) | 'unknown' | Provider name | Not reliable |

**CRITICAL:** Do NOT use `infrastructure_type` field - it is always NULL. Use `sender_accounts.esp` field for infrastructure classification.

#### Domain Source

| Field | Type | Default | Description | Values |
|-------|------|---------|-------------|--------|
| **domain_source** | varchar(20) | 'legacy' | Origin of domain | generated (AI), purchased (system), legacy (pre-1/22/26) |

#### Metadata

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **notes** | text | NULL | Free-form admin notes |
| **created_at** | timestamptz | now() | Record creation |
| **updated_at** | timestamptz | now() | Last modification |

---

### emailbison_campaigns

**Purpose:** Campaign metadata synced from EmailBison API. Each row represents an email outreach campaign with associated inboxes.

**Row Count:** ~113 campaigns
**Primary Key:** `id` (UUID)
**Foreign Keys:** `workspace_id` → workspaces

#### Critical Fields

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| **id** | uuid | NOT NULL | Internal primary key | Generated |
| **workspace_id** | uuid | NOT NULL | Client workspace | FK to workspaces.id |
| **emailbison_campaign_id** | text | NOT NULL | EmailBison API campaign ID | Unique, from API |
| **campaign_name** | text | NOT NULL | Campaign display name | From API |
| **campaign_status** | text | NULL | Status from EmailBison | "active", "paused", "completed" |
| **campaign_type** | text | NULL | Campaign type | From API |

#### Campaign State

| Field | Type | Default | Description | States |
|-------|------|---------|-------------|--------|
| **campaign_state** | campaign_state | 'live' | Internal campaign state | live/quarantined/dead |
| **is_active** | boolean | true | Whether campaign active | Filter flag |
| **paused_at** | timestamptz | NULL | When campaign paused | From API or manual |
| **completed_at** | timestamptz | NULL | When campaign completed | From API |
| **quarantined_at** | timestamptz | NULL | When quarantined | Internal action |
| **quarantine_reason** | text | NULL | Why quarantined | e.g., "High burn rate" |
| **killed_at** | timestamptz | NULL | When killed | Terminal state |
| **kill_reason** | text | NULL | Why killed | e.g., "Multiple domain burns" |

#### Lead/Contact Metrics

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| **total_leads** | integer | 0 | Total leads in campaign | From API |
| **total_leads_contacted** | integer | 0 | Leads contacted | From API |
| **completion_percentage** | numeric(5,2) | NULL | % complete | From API |

#### Sending Metrics

| Field | Type | Default | Description | Updated By |
|-------|------|---------|-------------|-----------|
| **emails_sent** | integer | 0 | Emails sent (from API) | sync_campaigns.py |
| **total_sends** | integer | 0 | Total sends (calculated) | Internal calculation |
| **bounces** | integer | 0 | Total bounces | Aggregated from events |
| **bounce_rate** | numeric(5,4) | 0 | Bounce rate | Calculated |
| **complaints** | integer | 0 | Spam complaints | Aggregated from events |

#### Burn Tracking

| Field | Type | Default | Description | Window |
|-------|------|---------|-------------|--------|
| **inboxes_burned** | integer | 0 | Total inboxes burned (lifetime) | Calculated from campaign_inboxes |
| **domains_affected** | integer | 0 | Unique domains with burns | Calculated |
| **inboxes_burned_7d** | integer | 0 | Inboxes burned in last 7 days | Rolling window |
| **domains_burned_7d** | integer | 0 | Domains burned in last 7 days | Rolling window |

#### Copy/Content Tracking

| Field | Type | Default | Description | Purpose |
|-------|------|---------|-------------|---------|
| **copy_created_at** | timestamptz | NULL | When campaign copy created | Content age tracking |
| **copy_version** | integer | 1 | Copy version number | Track iterations |
| **copy_age_days** | integer | NULL | Days since copy created | Calculated field |

#### Snapshot Tracking

| Field | Type | Default | Description | Process |
|-------|------|---------|-------------|---------|
| **last_snapshot_at** | timestamptz | NULL | Last snapshot taken | Updated by snapshot worker |
| **completed_snapshot_taken** | boolean | false | Whether completion snapshot taken | One-time flag |

#### Timestamps

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **first_seen_at** | timestamptz | now() | First sync from EmailBison |
| **last_seen_at** | timestamptz | now() | Most recent sync |
| **created_at** | timestamptz | now() | Record creation |
| **updated_at** | timestamptz | now() | Last modification (trigger) |

#### Metadata

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **notes** | text | NULL | Admin notes |

---

### workspaces

**Purpose:** Client workspace container. Each row represents a client account with associated sender accounts, domains, and campaigns.

**Row Count:** ~30 workspaces
**Primary Key:** `id` (UUID)
**Foreign Keys:** `instance_id` → emailbison_instances

#### Fields

| Field | Type | Default | Description | Notes |
|-------|------|---------|-------------|-------|
| **id** | uuid | NOT NULL | Primary key | - |
| **instance_id** | uuid | NOT NULL | EmailBison instance ID | FK to emailbison_instances.id |
| **workspace_name** | varchar(255) | NOT NULL | Client name | e.g., "Charm", "SPUI", "Sammy" |
| **emailbison_workspace_id** | text | NULL | EmailBison API workspace ID | Used for syncing |
| **is_active** | boolean | true | Whether workspace active | Filter flag |
| **automation_enabled** | boolean | true | Feature flag for automations | When FALSE, sync skips workspace |
| **sender_account_count** | integer | 0 | Count of sender accounts | Denormalized counter |
| **domain_count** | integer | 0 | Count of domains | Denormalized counter |
| **last_sync_at** | timestamptz | NULL | Last successful sync | Updated by sync workers |
| **created_at** | timestamptz | now() | Record creation | - |
| **updated_at** | timestamptz | now() | Last modification | Updated by trigger |
| **notes** | text | NULL | Admin notes | Free-form text |

---

### kill_queue

**Purpose:** 24-hour waiting queue for inboxes that triggered kill conditions. Implements the "tag → wait 24h → delete" flow.

**Row Count:** ~3 rows (active queue)
**Primary Key:** `id` (UUID)
**Foreign Keys:** `inbox_id` → sender_accounts, `workspace_id` → workspaces

#### Fields

| Field | Type | Default | Description | Process |
|-------|------|---------|-------------|---------|
| **id** | uuid | NOT NULL | Primary key | - |
| **inbox_id** | uuid | NOT NULL | Inbox being queued for kill | FK to sender_accounts.id |
| **workspace_id** | uuid | NOT NULL | Workspace | FK to workspaces.id |
| **trigger_type** | varchar(50) | NOT NULL | Which kill trigger fired | e.g., "hard_bounces_24h" |
| **trigger_value** | numeric(10,4) | NULL | Actual value that triggered | e.g., 2 bounces |
| **trigger_threshold** | numeric(10,4) | NULL | Threshold that was exceeded | e.g., 2 |
| **status** | varchar(20) | 'pending' | Queue status | pending → tagged → deleted/cancelled/failed |
| **queued_at** | timestamp | now() | When added to queue | Entry timestamp |
| **tagged_at** | timestamp | NULL | When EmailBison tag applied | After successful API call |
| **tag_name** | varchar(100) | NULL | EmailBison tag name | e.g., "remove_bounce_24h" |
| **scheduled_delete_at** | timestamp | NULL | When deletion scheduled | tagged_at + 24 hours |
| **deleted_at** | timestamp | NULL | When actually deleted | Completion timestamp |
| **error_message** | text | NULL | Error if failed | For debugging |
| **created_at** | timestamp | now() | Record creation | - |
| **updated_at** | timestamp | now() | Last modification | - |

#### Status Flow

```
pending → tagged → deleted (normal flow)
       ↘ cancelled (manual override)
       ↘ failed (error in tagging/deletion)
```

---

## Enum Types

### kill_trigger_type

**Purpose:** Categorizes the reason an inbox was killed. Used in `sender_accounts.kill_trigger` and `kill_queue.trigger_type`.

**Values:**

| Value | Description | Threshold | Priority | Status |
|-------|-------------|-----------|----------|--------|
| **spam_complaint** | Spam complaint from recipient | ≥1 | Highest | ACTIVE |
| **hard_blocked_24h** | Spam/policy rejection (550 5.7.x) | ≥1 | Highest | ACTIVE |
| **hard_unknown_24h** | Bad email addresses (550 5.1.1) | ≥3 | High | ACTIVE |
| **hard_bounces_24h** | Combined hard bounces in 24h | ≥2 | Medium (fallback) | ACTIVE |
| **fresh_inbox_bounce** | Bounce on inbox <14 days old | ≥1 | Medium | ACTIVE |
| **consecutive_hard_bounces** | Back-to-back hard bounces | ≥2 | Medium | DEFINED (not firing) |
| **hard_bounce_rate_7d** | Hard bounce rate >0.5% (min 50 sends) | >0.5% | Medium | DEFINED (not firing) |
| **bounce_rate_all_7d** | Total bounce rate >5% | >5% | Medium | DEFINED (not firing) |
| **provider_block** | ESP blocked the account | Any | Highest | DEFINED (not firing) |
| **placement_failure** | <85% inbox placement | <85% | Confirming | DEFINED (not firing) |
| **spam_folder_rate** | >5% spam placement | >5% | Confirming | DEFINED (not firing) |
| **degrading_trend** | 3 consecutive days declining | 3 days | Confirming | DEFINED (not firing) |

**Critical Notes:**
- Only 4 of 12 triggers are actively firing in production
- Evaluation order matters (see health_checks.py priority)
- "Confirming" triggers require 48h retest before actual kill

### esp_type

**Purpose:** Email service provider classification. Used in `sender_accounts.esp`.

**Values:**

| Value | Description | Notes |
|-------|-------------|-------|
| **gmail** | Google Workspace / Gmail | Ground truth from EmailBison tags |
| **microsoft** | Microsoft Entra / Outlook | Ground truth from EmailBison tags |
| **yahoo** | Yahoo Mail | Ground truth from EmailBison tags |
| **other** | Unknown or other provider | Default value |

**Critical:** This is the ONLY reliable source for infrastructure type. Do NOT use `domains.infrastructure_type` (always NULL).

### inbox_state

**Purpose:** Current operational state of an inbox. Used in `sender_accounts.inbox_state`.

**Values:**

| Value | Description | When Set |
|-------|-------------|----------|
| **live** | Inbox is active and connected | Default state, inbox operational |
| **dead** | Inbox is disconnected | When status = "Not connected" OR kill trigger fires |

**CRITICAL DISTINCTION:**
- `inbox_state = 'dead'` means "disconnected from EmailBison"
- `kill_trigger IS NOT NULL` means "burned due to performance issue"
- `inbox_state = 'dead' AND kill_trigger IS NULL` means "healthy disconnection" (supplier change, rotation, cancellation)

### domain_state

**Purpose:** Domain health state machine. Used in `domains.domain_state`.

**Values:**

| Value | Description | Transition Rule |
|-------|-------------|-----------------|
| **live** | Domain is healthy | Default state |
| **flagged** | Domain has 1 dead inbox | When dead_inbox_count = 1 |
| **dead** | Domain has 2+ dead inboxes | When dead_inbox_count ≥ 2 |

**State Machine:**
```
live (0 dead inboxes)
  ↓ (1 dead inbox)
flagged (1 dead inbox)
  ↓ (2+ dead inboxes)
dead (2+ dead inboxes, terminal state)
```

### campaign_state

**Purpose:** Campaign operational state. Used in `emailbison_campaigns.campaign_state`.

**Values:**

| Value | Description | When Set |
|-------|-------------|----------|
| **live** | Campaign is running normally | Default state |
| **quarantined** | Campaign flagged for review | High burn rate or suspicious activity |
| **dead** | Campaign terminated | Multiple domain burns or manual kill |

### inbox_role

**Purpose:** Inbox role in domain portfolio rotation strategy. Used in `sender_accounts.role`.

**Values:**

| Value | Description | Notes |
|-------|-------------|-------|
| **primary** | Active sending inbox | Currently deployed to campaigns |
| **hot_backup** | Warmed backup ready to deploy | Kept warm for quick rotation |
| **warming** | Inbox in warmup phase | Not yet ready for production |

---

## Common Pitfalls

### 1. Burn Rate Definition

**WRONG:**
```sql
-- This counts ALL disconnected inboxes, including healthy ones
SELECT COUNT(*) FILTER (WHERE inbox_state = 'dead') / COUNT(*) as burn_rate
FROM sender_accounts;
```

**CORRECT:**
```sql
-- This counts only performance-based burns
SELECT COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) / COUNT(*) as burn_rate
FROM sender_accounts;
```

**Explanation:** `inbox_state = 'dead'` includes:
- Burned inboxes (kill_trigger IS NOT NULL) - 9-33% of dead inboxes
- Healthy disconnections (kill_trigger IS NULL) - 67-91% of dead inboxes
  - Subscription cancellations
  - Supplier (Hypertide) provisioning changes
  - Manual deactivation
  - Domain rotation

### 2. Infrastructure Classification

**WRONG:**
```sql
-- This field is ALWAYS NULL
SELECT domain_name, infrastructure_type
FROM domains
WHERE infrastructure_type = 'microsoft';  -- Returns nothing
```

**CORRECT:**
```sql
-- Use sender_accounts.esp field
SELECT d.domain_name, sa.esp, COUNT(*)
FROM domains d
JOIN sender_accounts sa ON sa.domain_id = d.id
WHERE sa.esp = 'microsoft'
GROUP BY d.domain_name, sa.esp;
```

**Explanation:** `domains.infrastructure_type` was never populated. EmailBison API tags are the ground truth, stored in `sender_accounts.esp`.

### 3. Dual-Provider Comparison

**WRONG:**
```sql
-- Compares different clients with different qualities
SELECT esp,
       COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned
FROM sender_accounts
WHERE esp IN ('microsoft', 'gmail')
GROUP BY esp;
```

**CORRECT:**
```sql
-- Only compare within clients that have BOTH provider types
WITH dual_provider_workspaces AS (
    SELECT workspace_id
    FROM sender_accounts
    WHERE esp IN ('microsoft', 'gmail')
    GROUP BY workspace_id
    HAVING COUNT(DISTINCT esp) = 2
)
SELECT esp,
       COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned
FROM sender_accounts
WHERE workspace_id IN (SELECT workspace_id FROM dual_provider_workspaces)
  AND esp IN ('microsoft', 'gmail')
GROUP BY esp;
```

**Explanation:** Comparing across different clients introduces client quality bias. Must control for workspace variable.

### 4. Volume-Adjusted Metrics

**WRONG:**
```sql
-- Raw burn rate ignores that some inboxes send 10x more volume
SELECT esp, COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned
FROM sender_accounts
GROUP BY esp;
```

**CORRECT:**
```sql
-- Burns per million emails accounts for volume differences
SELECT
    esp,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
    ROUND(1000000.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) /
          NULLIF(SUM(emails_sent_all_time), 0), 2) as burns_per_million_emails
FROM sender_accounts
WHERE esp IN ('microsoft', 'gmail')
GROUP BY esp;
```

**Explanation:** Google inboxes send 2.2x more volume per inbox than Microsoft. Must normalize by volume.

### 5. Active Senders vs All Inboxes

**WRONG:**
```sql
-- Includes inboxes that never sent (avg = 0 sends)
SELECT AVG(emails_sent_all_time) as avg_volume
FROM sender_accounts;
```

**CORRECT:**
```sql
-- Only include inboxes that actually sent emails
SELECT AVG(emails_sent_all_time) as avg_volume
FROM sender_accounts
WHERE emails_sent_all_time > 0;
```

**Explanation:** Many inboxes are provisioned but never used. Filter to `emails_sent_all_time > 0` for meaningful averages.

### 6. 24-Hour Counter Reset Logic

**WRONG:**
```sql
-- Assumes counters are cumulative
SELECT hard_bounces_24h
FROM sender_accounts
ORDER BY hard_bounces_24h DESC;  -- Max value is 2-3, not cumulative
```

**CORRECT:**
```sql
-- Understand that counters reset daily
-- hard_bounces_24h is a ROLLING 24h count, reset at midnight
-- To see all-time bounces, use bounces_all_time
SELECT email_address, bounces_all_time as lifetime_bounces
FROM sender_accounts
ORDER BY bounces_all_time DESC;
```

**Explanation:** `hard_bounces_24h`, `hard_blocked_24h`, `hard_unknown_24h` are rolling 24h counters that reset at midnight to prevent accumulation.

### 7. Unused Kill Triggers

**WRONG:**
```sql
-- Assuming all 12 triggers are active
SELECT kill_trigger, COUNT(*)
FROM sender_accounts
WHERE kill_trigger IS NOT NULL
GROUP BY kill_trigger;
-- Returns only 4 values, not 12
```

**CORRECT:**
```sql
-- Only these 4 triggers are actually firing:
-- fresh_inbox_bounce (67.71%)
-- hard_bounces_24h (17.42%)
-- spam_complaint (14.68%)
-- hard_blocked_24h (0.19%)

SELECT kill_trigger, COUNT(*) as count,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct
FROM sender_accounts
WHERE kill_trigger IS NOT NULL
GROUP BY kill_trigger
ORDER BY count DESC;
```

**Explanation:** 8 of 12 defined triggers never fire. May indicate implementation gaps or thresholds too high.

---

## Field Naming Conventions

### Timestamp Suffixes

| Suffix | Timezone | Example | Usage |
|--------|----------|---------|-------|
| `_at` | WITH timezone (timestamptz) | `created_at`, `killed_at`, `first_seen_at` | Standard timestamps |
| `_at` | WITHOUT timezone (timestamp) | `queued_at` (kill_queue) | Legacy fields (inconsistent) |

**Recommendation:** All new timestamp fields should use `timestamptz` for proper timezone handling.

### Boolean Prefixes

| Prefix | Meaning | Example |
|--------|---------|---------|
| `is_` | State flag | `is_active`, `is_clean` |
| (no prefix) | Feature flag | `automation_enabled`, `warmup_enabled` |
| (no prefix) | Completion flag | `removal_tagged`, `completed_snapshot_taken` |

### Counter Suffixes

| Suffix | Meaning | Example |
|--------|---------|---------|
| `_count` | Absolute count | `sender_account_count`, `dead_inbox_count` |
| `_24h` | Rolling 24h window | `hard_bounces_24h`, `hard_blocked_24h` |
| `_7d` | Rolling 7d window | `hard_bounces_7d`, `total_sends_7d` |
| `_all_time` | Lifetime total | `emails_sent_all_time`, `replies_all_time` |

### Rate/Percentage Fields

| Suffix | Range | Precision | Example |
|--------|-------|-----------|---------|
| `_rate` | 0-1 decimal | numeric(5,4) | `bounce_rate` (0.0523 = 5.23%) |
| `_rate_pct` | 0-100 | numeric(5,2) | Not used, prefer `_rate` |
| `_percentage` | 0-100 | numeric(5,2) | `completion_percentage`, `health_percentage` |

### ID Suffixes

| Suffix | Meaning | Example |
|--------|---------|---------|
| `_id` | Internal UUID FK | `workspace_id`, `domain_id`, `inbox_id` |
| `_account_id` | External API ID | `emailbison_account_id` |
| `_campaign_id` | External API ID | `emailbison_campaign_id` |
| `_workspace_id` | External API ID | `emailbison_workspace_id` |

---

## Quick Reference: Key Queries

### Burn Rate (Correct Definition)
```sql
SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
    COUNT(*) FILTER (WHERE kill_trigger IS NULL AND inbox_state = 'dead') as healthy_disconnected,
    COUNT(*) FILTER (WHERE inbox_state = 'live') as still_live,
    ROUND(100.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) / COUNT(*), 2) as burn_rate_pct
FROM sender_accounts;
```

### Infrastructure Performance (Microsoft vs Google)
```sql
WITH dual_provider_workspaces AS (
    SELECT workspace_id
    FROM sender_accounts
    WHERE esp IN ('microsoft', 'gmail')
    GROUP BY workspace_id
    HAVING COUNT(DISTINCT esp) = 2
)
SELECT
    sa.esp,
    COUNT(sa.id) as total_inboxes,
    COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) as burned,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) / COUNT(sa.id), 2) as burn_rate,
    ROUND(1000000.0 * COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) /
          NULLIF(SUM(sa.emails_sent_all_time), 0), 2) as burns_per_million_emails
FROM sender_accounts sa
JOIN dual_provider_workspaces dpw ON sa.workspace_id = dpw.workspace_id
WHERE sa.esp IN ('microsoft', 'gmail')
GROUP BY sa.esp;
```

### Kill Trigger Distribution
```sql
SELECT
    kill_trigger,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct_of_burns,
    ROUND(AVG(emails_sent_all_time), 0) as avg_emails_before_kill
FROM sender_accounts
WHERE kill_trigger IS NOT NULL
GROUP BY kill_trigger
ORDER BY count DESC;
```

---

## See Also

- [DATABASE-GUIDE.md](./DATABASE-GUIDE.md) - Master navigation guide with data flow and architecture
- [QUERY-COOKBOOK.md](./QUERY-COOKBOOK.md) - 20 ready-to-use query templates
- [ADR-005](./adr/adr-005-differentiated-bounce-thresholds.md) - Kill trigger threshold documentation
- [health-monitoring.md](./features/health-monitoring.md) - Health check system documentation

---

**Last Updated:** 2026-02-24
**Maintainer:** Charm Email OS Team
**Version:** 1.0
