# Pool Assignment & Tagging System — Definitive Reference

**Date:** 2026-03-12
**Status:** Active
**Supersedes:** Previous ad-hoc pool status logic in sync_accounts.py

---

## 1. Purpose

Our system manages email infrastructure inventory across domains and inboxes. The primary goals:

1. **Tag inboxes correctly** in EmailBison so our team knows which inboxes to assign to active campaigns
2. **Track pool allocation** in our database as system of record
3. **Surface kill signals** so the team can extract burned infrastructure from campaigns
4. **Promote reserves** when live infrastructure burns

We do NOT manage campaign assignment — the team does that in EmailBison using our tags as their guide.

---

## 2. Key Entities

### Our Database (System of Record)
- Tracks domain lifecycle, pool allocation, inbox status, kill triggers
- Source of truth for what's live, what's reserve, what's burned

### EmailBison (Operational Platform)
- Where inboxes are deployed and campaigns run
- No concept of domains — only individual sender accounts
- Tags are the interface between our system and the team's workflow
- Team filters by tags to decide which inboxes go into campaigns

### HyperTide (Vendor)
- Provisions inbox infrastructure on our domains
- Each domain gets ~50 inboxes (Entra) or ~3 inboxes (Google)
- Separate infrastructure per domain — domain reputation is isolated

---

## 3. Domain Lifecycle

```
generated → purchased → ready → [inboxes appear in EB] → deployed
```

| Stage | `approval_status` | What's Happening |
|-------|-------------------|-----------------|
| Generated | `available` | Domain name created, price-checked at registrar |
| Purchased | `purchased` | Bought, nameservers being configured for HyperTide |
| Ready | `active` | NS pointed to HyperTide, ready for inbox provisioning |
| Legacy | `legacy` | Pre-existing domain discovered from EB sync |
| Deployed | `active` + inboxes exist | Inboxes detected in EmailBison |

Deployment is inferred from inbox presence, not a separate status value.

---

## 4. Pool Allocation (Domain Level)

**Core rule:** All inboxes on a domain share the same pool. Domain-level allocation.

| `pool_status` | Meaning | Target | EB Tag on Inboxes |
|---------------|---------|--------|-------------------|
| `live` | A-Set — team assigns these to campaigns | ~80% | `live` (a_set_tag_name) |
| `reserve` | B-Set — warming only, promoted when live burns | ~20% | `reserve` (b_set_tag_name) |
| `burned` | Compromised by confirmed domain-level trigger (complaint rate >1.0%), permanently retired | N/A | Kill trigger tags remain |
| `unassigned` | Not yet allocated (pre-deployment) | N/A | None |

### When Pool Gets Assigned
Only after:
1. Domain is purchased/ready (`approval_status` = `active` or `legacy`)
2. Inboxes detected in EmailBison
3. Inboxes have completed 21-day warmup incubation

Pre-deployment domains stay `unassigned`.

### 80/20 Split
- ~80% of deployed domains allocated to `live`
- ~20% allocated to `reserve`
- Maintains sending capacity while ensuring backup availability

---

## 5. Inbox Lifecycle

### 5.1 Lifecycle Stages (Maturity)

| `inventory_lifecycle_status` | Meaning | Duration |
|------------------------------|---------|----------|
| `incubating` | Warming up, NOT ready for campaigns | ~21 days |
| `active` | Graduated, ready for campaign assignment | Until killed |
| `dead` | Kill trigger fired, removed permanently | Permanent |

Graduation is **automatic** — after 21 days from `warmup_started_at`, `lifecycle_tag_sync` transitions to `active`.

### 5.2 Pool Status (Deployment)

| `inventory_pool_status` | Meaning | How Set |
|------------------------|---------|---------|
| `NULL` | Incubating or dead — not in any pool | sync_accounts on insert; kill_processor on death |
| `reserve` | Graduated, in reserve pool | Graduation (21-day warmup complete) |
| `deployed` | On a live domain, tagged for campaigns | set_tag_sync when domain.pool_status = 'live' |
| `warning` | Temporary cooldown due to bounces | sync_accounts when bounce thresholds hit |

### 5.3 The Promotion Path

Every inbox follows this path:

```
NULL (incubating) → reserve (graduated) → deployed (domain is live)
```

**Inboxes always graduate to `reserve` first.** Promotion to `deployed` is driven by domain `pool_status`, not inbox-level logic. If the domain is `live`, its graduated inboxes are `deployed`. If the domain is `reserve`, they stay `reserve`.

---

## 6. Tags in EmailBison

### 6.1 What We Tag

| Tag | Applied When | Removed When | Team Action |
|-----|-------------|--------------|-------------|
| `incubating` | Inbox detected, warmup started | After 21 days | Do not assign to campaigns |
| `live` (lifecycle) | 21-day warmup complete | Inbox killed | Eligible for campaigns |
| `live` (pool/set) | Domain pool_status = 'live' | Domain burned or demoted | Assign to campaigns |
| `reserve` (pool/set) | Domain pool_status = 'reserve' | Domain promoted to live | Do not assign — warming reserve |
| `flagged_{trigger}` | Kill trigger fires | Never removed | Extract from campaigns |

### 6.2 Team Workflow

The team operates entirely in EmailBison:
1. Filter inboxes by `live` tag → these are graduated AND on live domains
2. Assign to active campaigns
3. When they see `flagged_*` tags → extract those inboxes from campaigns
4. When reserve inboxes get re-tagged to `live` (after promotion) → assign to campaigns
5. We manage the tagging; they manage the campaigns

### 6.3 Tag Name Configuration

Each workspace stores its tag names:
- `a_set_tag_name` (default: `live`) — applied to inboxes on live domains
- `b_set_tag_name` (default: `reserve`) — applied to inboxes on reserve domains

All workspaces are now standardized to `live`/`reserve`.

---

## 7. Kill Triggers and Domain Health

### 7.1 Two Levels of Kill Triggers

**Rate-based domain burns** (spam complaints — evaluated by complaint rate, not count):
- `spam_complaint` — inbox killed instantly; domain state determined by complaint rate thresholds

Rate thresholds:
- <0.1% complaint rate → `live` (domain healthy)
- 0.3%+ complaint rate → `monitoring` (elevated risk, under observation)
- >1.0% complaint rate → domain burned + oldest reserve promoted

**Workspace circuit breaker:** If 3+ domains hit monitoring/burn thresholds within 24 hours, this indicates a fleet-wide campaign event (bad list, provider crackdown), not domain-specific problems. The system flags all affected domains as `monitoring` instead of burning, and raises a Slack alert for investigation.

**Inbox-killing triggers** (individual inbox only — never burn domain):
- `hard_bounces_24h`, `hard_blocked_24h`, `hard_unknown_24h`
- `hard_bounce_rate_7d`, `bounce_rate_all_7d`, `disconnected_timeout`

When fired:
1. Single inbox → `inbox_state = 'dead'`, `inventory_pool_status = NULL`
2. Domain health recalculated (dead_inbox_count, health_percentage)
3. Other inboxes on same domain continue operating
4. Domain capacity decreases but doesn't burn

### 7.2 Domain Degradation

When multiple inbox-level kills accumulate on a domain:
- Domain goes from 50 → 40 → 30 live inboxes
- `domain_state` transitions: `live` → `flagged` → `monitoring` → `dead`
- The `monitoring` state is an intermediate observation period for domains with elevated complaint rates (0.3%+) that haven't yet crossed the burn threshold (>1.0%)
- The system doesn't auto-burn on degradation — only when complaint rate exceeds 1.0% (and the workspace circuit breaker hasn't triggered)

The team and our reporting surface this: "This domain has lost 40% of its inboxes, consider extracting."

### 7.3 Reserve Runway

When live domains burn, reserves get promoted. This depletes the reserve pool:
- 10 reserve domains → 1 burns, promote → 9 reserve domains
- If reserves run out → critical alert: "No reserve domains available, order replacements"
- Tracked via `v_domain_runway` view: `reserve_count`, `monthly_burn_rate`, `runway_months`

---

## 8. What's NOT in Scope (Future Considerations)

### Quarantine → Reframed as Kill Trigger Intelligence (Deferred)

The codebase has `quarantined` as a valid `inventory_pool_status` value. Originally designed to pause reserve promotion after domain kills, pending manual review.

**Current decision: Do not use quarantine as a blocking mechanism.** The system should keep promoting reserves automatically. Instead, quarantine is reframed as **reporting and alerting** — surface the kill trigger intelligence so the team can investigate and act in EmailBison.

**What the Slack notification should surface on domain-killing triggers:**
- Which inbox triggered the kill (email address, domain)
- Which workspace and campaign the inbox was running in
- The kill trigger type (spam_complaint)
- Which reserve domain was auto-promoted to replace it
- Reserve runway remaining (how many reserves left)

This gives the team the context to decide: "Was this a bad list? Should we pause campaigns in this workspace?" They control campaigns in EmailBison — they're the human checkpoint, not the database.

**If we need quarantine as a blocking mechanism later, three options exist:**

#### Option A: Manual Release (Admin Action)
API endpoint `POST /api/admin/domains/{id}/release-quarantine`:
- Team reviews the burn, confirms domain-specific root cause
- Clicks release, inboxes return to `reserve`, promotion re-enabled
- **Pro:** Explicit human decision. **Con:** Requires active monitoring; forgotten quarantines block reserves indefinitely.

#### Option B: Time-Based Auto-Release
Quarantine expires after 24-48 hours using existing `cooldown_ends_at` column:
- If no second burn in that window, reserve is safe to promote
- `set_tag_sync` checks: if `quarantined` AND `cooldown_ends_at < NOW()`, release
- **Pro:** No manual action needed; schema already supports it. **Con:** Arbitrary timer; slow campaign cycles might not trigger a second burn within the window.

#### Option C: Signal-Based Auto-Release
Quarantine releases when the promoted domain proves healthy:
- Promoted domain sends for N days with no kill triggers → root cause was domain-specific
- System auto-releases quarantine on remaining reserves
- **Pro:** Evidence-based decision. **Con:** Most complex to implement; requires tracking burn→quarantine→promotion relationships.

**Recommendation when ready:** Start with Option B (time-based, minimal code, schema ready), then graduate to Option C if burn pattern data justifies the complexity.

### Automated Campaign Management (Deferred)
We tag inboxes; the team manages campaigns. Future consideration: auto-assign promoted inboxes to campaigns that lost capacity from burned domains.

### Warning Cooldown Management (Deferred)
Schema has `warning_started_at`, `cooldown_ends_at`, `warning_reason` columns but no active code uses them. Currently `warning` is set/cleared purely by bounce counter state during sync. A proper cooldown system with timed recovery is a future enhancement.

---

## 9. Current Implementation Gaps

These are gaps between the business process defined above and what the code currently does:

### GAP 1: sync_accounts.py Overwrites Pool Status (CRITICAL)

**File:** `sync_modules/sync_accounts.py` lines 377-386

**Problem:** The hourly sync UPSERT recalculates `inventory_pool_status` from scratch. It only knows `NULL`, `warning`, and `reserve` — it never outputs `deployed`. Every inbox that `set_tag_sync` correctly set to `deployed` gets overwritten back to `reserve` on the next hourly sync.

**Required fix:** Preserve existing `deployed` and `reserve` values. Only override for:
- Dead/killed → `NULL`
- Bounce thresholds → `warning`
- New graduation (NULL → reserve)

### GAP 2: Warning Has No Recovery to Previous Pool (MODERATE)

**Problem:** When bounces clear, the sync_accounts CASE statement falls through to `reserve` — not back to `deployed`. An inbox on a live domain goes: `deployed` → `warning` → `reserve` → (waits for set_tag_sync) → `deployed`. There's a window where the DB shows `reserve` for an inbox that should be `deployed`.

**Required fix:** When clearing warning, restore the previous pool status based on domain `pool_status` rather than defaulting to `reserve`.

### GAP 3: set_tag_sync Only Updates Connected Inboxes in DB (MODERATE)

**File:** `sync_modules/set_tag_sync.py` line 507

**Problem:** `_get_graduated_inboxes()` filters to `status = 'Connected'` for both EB API calls AND DB updates. Disconnected inboxes on a live domain never get `deployed` in DB.

**Required fix:** Update `inventory_pool_status` in DB for ALL graduated inboxes on the domain. Only call the EB tag API for Connected ones (API requires connection). The DB should reflect the domain's pool regardless of connection state.

### GAP 4: Replace Blocking Quarantine with Kill Trigger Alerting (MODERATE)

**File:** `sync_modules/kill_processor.py` lines 1043-1047

**Problem:** On domain-level triggers, `kill_processor` sets B-Set inboxes to `inventory_pool_status = 'quarantined'`, which blocks auto-promotion. No un-quarantine path exists, so reserves get permanently stuck.

**Required fix:** Remove the quarantine step from the domain-kill flow. Instead:
1. Mark domain `pool_status = 'burned'`
2. Kill the affected inboxes (they're on the burned domain)
3. Auto-promote oldest reserve domain → `pool_status = 'live'`
4. `set_tag_sync` tags the promoted domain's inboxes
5. **Enhance the Slack alert** to surface: triggering inbox, campaign, workspace, kill trigger type, promoted domain name, reserve runway remaining

The `quarantined` value stays in the CHECK constraint for future use but is not actively set. See Section 8 for future quarantine options if blocking behavior is needed later.

---

## 10. Execution Order (How Sync Modules Interact)

Understanding the timing prevents conflicts:

```
Every 5 min:   Events sync (campaign events, replies)
Every 30 min:  Warmup sync → Lifecycle tag sync → Set tag sync
Every 60 min:  Full sync (sync_accounts — inbox data from EB)
Every 30 min:  Kill queue processing
```

**Critical interaction:**
1. `sync_accounts` (hourly) syncs inbox data from EB → MUST preserve pool status
2. `lifecycle_tag_sync` (30 min) graduates incubating → active, tags in EB
3. `set_tag_sync` (30 min) assigns pool based on domain → tags in EB, updates DB
4. `kill_processor` (30 min) processes kill triggers → sets inbox dead, domain burned

The fix for GAP 1 ensures step 1 doesn't undo step 3's work.

---

## 11. Database Column Reference

### Domain-Level (Three Independent Dimensions)

| Column | Dimension | Values | Purpose |
|--------|-----------|--------|---------|
| `approval_status` | Purchase lifecycle | available, purchased, active, legacy | Where in purchase flow |
| `pool_status` | Pool allocation | unassigned, live, reserve, burned | A-Set vs B-Set |
| `domain_state` | Health/capacity | live, flagged, monitoring, dead | Inbox capacity assessment |

### Inbox-Level (Two Independent Dimensions)

| Column | Dimension | Values | Purpose |
|--------|-----------|--------|---------|
| `inventory_lifecycle_status` | Maturity | incubating, active, dead | Warmup stage |
| `inventory_pool_status` | Deployment | NULL, reserve, deployed, warning | Pool assignment |

### Mapping: Domain Pool → Inbox Pool → EB Tag

| Domain `pool_status` | Inbox `inventory_pool_status` | EB Tag |
|-----------------------|-------------------------------|--------|
| `live` | `deployed` | `live` (a_set_tag_name) |
| `reserve` | `reserve` | `reserve` (b_set_tag_name) |
| `burned` | `NULL` (dead) | `flagged_{trigger}` |
| `unassigned` | `NULL` (incubating) | `incubating` or none |
