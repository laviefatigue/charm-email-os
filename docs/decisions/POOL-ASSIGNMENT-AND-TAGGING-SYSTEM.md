# Pool Assignment & Tagging System — Definitive Reference

**Date:** 2026-03-12 (initial), updated 2026-04-28 for the post-overhaul model
**Status:** Active
**Supersedes:** Previous ad-hoc pool status logic in sync_accounts.py
**See also:** [[2026-04-27-tagging-kill-overhaul-plan]] for the full design + handoff doc, [[../adr/adr-006-tagging-kill-overhaul-2026-04-27]] for the architectural decision record.

> **2026-04-29 ADR-007 — DROP `warning` STATE:**
> - `inventory_pool_status='warning'` is REMOVED from the state model. Pool is now `deployed` / `reserve` / `NULL` only.
> - Google kill thresholds tightened to 1/1/1 (Microsoft kept at 2/3/2 — legacy ride-to-death).
> - Migration 098 drains existing warning rows. See [[../adr/adr-007-drop-warning-state-2026-04-29]] for the architectural decision record.
>
> **2026-04-27 OVERHAUL — KEY CHANGES TO THIS DOC:**
> 1. **Per-inbox pool authority** replaced domain-level. `sender_accounts.inventory_pool_status` is the SOLE authority for set tag reconciliation. `domain.pool_status` is now a default for new graduations + a scope marker for burn events — it does not drive per-inbox tagging cycle-to-cycle.
> 2. **Cross-domain promotion is now allowed** for kill-driven and threshold-driven promotion. The "all inboxes on a domain share the same pool" invariant from §4 below is no longer absolute — a reserve-pool domain may have one inbox promoted to deployed (cross-domain mixing) when filling a kill.
> 3. **Graduation timer is 14 business days** (not 21 calendar) — uses `warmup_enabled_since` (migration 094) for continuous-enabled tracking.
> 4. **Google graduates to `reserve`**, not directly to `live`. Microsoft (legacy Entra) graduates to `deployed` per ride-to-death pin.
> 5. **`live` (lifecycle) tag is no longer used.** Lifecycle phases use `incubating` only; the `live` tag in EB is now exclusively a pool tag.
> 6. **Workspace-scoped API keys** (migration 089) replace the global `switch_workspace()` model — tag writes are concurrent across workspaces.
>
> Sections 4 and 5 below are marked with **(POST-OVERHAUL)** updates inline.

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

## 4. Pool Allocation (POST-OVERHAUL)

> **Pre-overhaul "domain-level allocation" rule no longer applies.** The 80/20 domain split is still useful as a domain-level *default* when allocating new graduations, but it does not constrain per-inbox tagging — see §5.2 below for the new authority model.

### 4.1 Domain-level pool_status (default + burn scope)

`domains.pool_status` retains two roles post-overhaul:

| `pool_status` | Meaning | Role |
|---|---|---|
| `live` | Default destination for graduations on this domain | Default-only — per-inbox `inventory_pool_status` overrides cycle-to-cycle. |
| `reserve` | Default destination for graduations on this domain | Default-only — same as above. |
| `burned` | Domain compromised (complaint rate > 1.0%), permanently retired | Triggers domain-burn handler — sets all inboxes on this domain to `inventory_pool_status = NULL`. |
| `cancelled` | Domain not renewed, going away | Same effect as burned for tag/pool clearance. |
| `unassigned` | Not yet allocated (pre-deployment) | No tag effect. |

### 4.2 Per-inbox `inventory_pool_status` is the authority

The cycle-to-cycle tag decision is made per-inbox from `sender_accounts.inventory_pool_status`. See §5.2 for full mapping.

This enables:
- **Cross-domain promotion** — kill_processor promotes the oldest reserve inbox to fill a kill, regardless of source domain. The promoted inbox gets `inventory_pool_status='live'` while its source domain stays `pool_status='reserve'`. set_tag_sync respects the per-inbox value.
- **Threshold-driven promotion** — when a workspace has a `package_id`, the orchestrator promotes reserve inboxes to fill the package's live target. Domain-aware ordering (partially-tapped domains finished before opening new ones).
- **Active circuit breaker** — `inventory_pool_status='warning'` (set by sync_accounts on bounce signal) untags both `live` and `reserve` from EB without modifying the domain.

### 4.3 When pool gets assigned

| Path | When | Resulting `inventory_pool_status` |
|---|---|---|
| Graduation (Google) — domain `pool_status='live'` | After 14 BD warmup at `lifecycle_tag_sync` | `'reserve'` (post-overhaul: Google always graduates to reserve regardless of domain default) |
| Graduation (Google) — domain `pool_status='reserve'` | Same | `'reserve'` |
| Graduation (Microsoft) | Same | `'live'` (legacy Entra goes straight to live; never reserve) |
| Cross-domain promotion (kill_processor) | On each kill — picks oldest reserve, workspace-scoped | `'live'` |
| Threshold-driven promotion (orchestrator) | Per workspace, only when `workspaces.package_id IS NOT NULL` | `'live'` |
| Bounce signal | sync_accounts upsert when `hb_24h ≥ 1 OR hb_7d ≥ 3` | `'warning'` (auto-clears when bounces subside) |
| Kill | kill_processor on kill_queue drain | `NULL` |
| Domain burn | Burn handler: all inboxes on domain | `NULL` |

### 4.4 80/20 split — informal guideline

The 80% live / 20% reserve split is a high-level capacity-planning heuristic, NOT enforced by code. The `workspace_packages` model (migration 097) replaces this with explicit per-package targets:

- `50k_google` package: 150 live (10 orders × 3 inboxes/domain × 5 domains/order) + 30 reserve (2 orders bench)
- `100k_google` package: 300 live + 60 reserve

`target_live_count_override` on `workspaces` can lower the package target for ramp-up; can never raise above package.

---

## 5. Inbox Lifecycle (POST-OVERHAUL)

### 5.1 Lifecycle Stages

| `inventory_lifecycle_status` | Meaning | Duration |
|------------------------------|---------|----------|
| `NULL` | Brand new, never classified | Briefly — sync_accounts upsert sets it on insert |
| `incubating` | Warming up, NOT ready for campaigns | **14 business days** of continuous `warmup_enabled=TRUE` |
| `active` | Graduated, ready for campaign assignment | Until killed |
| `dead` | Kill trigger fired, removed permanently | Permanent |

**Graduation is automatic** — `lifecycle_tag_sync._graduate_mature_inboxes` runs every 15 min per workspace and graduates inboxes whose `warmup_enabled_since` (migration 094) shows 14 business days of continuous warmup.

### 5.2 Pool Status (POST-ADR-007, 2026-04-29)

`inventory_pool_status` is now the SOLE authority for set_tag_sync's per-inbox tag decision. The mapping below is enforced by `set_tag_sync._pool_to_tag_targets`:

| `inventory_pool_status` | EB Tag State | How Set |
|---|---|---|
| `NULL` | Neither `live` nor `reserve` | sync_accounts on insert (new inbox), kill, domain burn, `mark_stale_accounts`, or migration 098 (former warning Google with no domain default) |
| `'reserve'` | `reserve` tag, not `live` | Graduation (Google), migration 098 restoring former warning Gmail on reserve-pool domains |
| `'live'` | `live` tag, not `reserve` | Graduation (Microsoft), cross-domain promotion (kill_processor), threshold-driven promotion (orchestrator), migration 098 restoring former warning MS (pin) or Gmail on live domains |

**Removed states (per ADR-007):**

| Former state | Removal reason |
|---|---|
| ~~`'warning'`~~ | Pre-overhaul soft-pause buffer; not in v3 spec; allowed indefinite stuck-state. Inboxes that hit bounce thresholds now queue for kill directly via health_checks. |
| ~~`'quarantined'`~~ | Reserved for future use but never operationalized. Same circuit-breaker behavior as warning; removed alongside it. |

### 5.3 Graduation Path (POST-OVERHAUL)

```
NULL (new sync) → 'incubating' → 'active' (graduated)
                                    │
                                    ├─ Google → 'reserve' (cross-domain promotion later via kill or threshold)
                                    └─ Microsoft → 'live' (legacy ride-to-death)
```

Post-graduation, the inbox stays at `lifecycle='active'` permanently until killed. `inventory_pool_status` may transition multiple times: reserve → deployed (promotion) → warning (bounces) → reserve (recovery) → NULL (kill). See §4.3 for transition triggers.

### 5.4 Microsoft pin

Microsoft Entra inboxes are special-cased in `set_tag_sync` per CEO Rule C2 ("legacy ride to death"):

- **Always tagged `live`** in EB regardless of `inventory_pool_status` (pin behavior).
- **Never tagged `reserve`** — reserve concept does not apply to MS.
- **Warning circuit breaker is overridden** — even MS inboxes with `pool='warning'` get the `live` tag because the pin runs first.
- Only `lifecycle='dead'` (kill trigger fired) removes the live tag.

This makes the MS fleet a constant-state population that's never re-tagged in normal operation. Audit metric `pool_warning_should_have_no_pool_tag` flags MS warning inboxes — these are by-design and should not be cleaned up.

---

## 6. Tags in EmailBison

### 6.1 What We Tag

| Tag | Applied When | Removed When | Team Action |
|-----|-------------|--------------|-------------|
| `incubating` | Inbox detected, warmup started | After 21 days | Do not assign to campaigns |
| ~~`live` (lifecycle)~~ | **REMOVED post-overhaul.** Lifecycle no longer uses a `live` tag — graduation goes straight to pool tag (`reserve` for Google, `live` for Microsoft via pin). | — | — |
| `live` (pool tag) | Per-inbox `inventory_pool_status='live'` (or Microsoft pin) | Pool flips to reserve/warning/NULL OR pool tag drained by warning circuit breaker | Assign to campaigns |
| `reserve` (pool tag) | Per-inbox `inventory_pool_status='reserve'` | Promoted to deployed (kill-driven or threshold-driven) | Do not assign — warming reserve |
| `flagged_{trigger}` | Kill trigger fires (health_checks → kill_queue) | Never removed | Extract from campaigns |

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
