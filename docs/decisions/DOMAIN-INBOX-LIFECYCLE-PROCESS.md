# Domain & Inbox Lifecycle — Business Process Document

**Date:** 2026-03-12
**Status:** Reference — defines how the system SHOULD work
**Purpose:** Canonical process definition for domain lifecycle, inbox lifecycle, pool assignment, and tagging

---

## 1. System of Record

Our **PostgreSQL database** is the system of record for:
- Domain lifecycle (generated → purchased → ready → deployed)
- Pool allocation (live/reserve assignment at domain level)
- Inbox status tracking (lifecycle stage, pool assignment, kill state)

**EmailBison** is the operational platform where infrastructure is deployed. It has:
- No concept of domains (only individual sender accounts/inboxes)
- No concept of pool allocation (only tags we apply)
- Tags that our team uses to filter inboxes for campaign assignment

**HyperTide** is the vendor that provisions inbox infrastructure on domains we own.

---

## 2. Domain Lifecycle

### 2.1 Stages

```
generated → ready → [HyperTide order] → deployed → pool assigned (live/reserve)
                                              ↓
                                         [kill trigger]
                                              ↓
                                           burned
```

| Stage | DB Column | Value | Meaning |
|-------|-----------|-------|---------|
| Generated | `approval_status` | `available` | Domain name created, price-checked at registrar |
| Purchased | `approval_status` | `purchased` | Bought at registrar, nameservers being configured |
| Ready | `approval_status` | `active` | Nameservers pointed to HyperTide, ready for inbox setup |
| Legacy | `approval_status` | `legacy` | Pre-existing domain, discovered from EmailBison sync |
| Deployed | (inferred) | inboxes exist | Inboxes detected in EmailBison for this domain |

**Note:** `approval_status = 'active'` means the domain is ready/deployed. There is no separate "deployed" value in `approval_status` — deployment is inferred from the presence of inboxes linked to that domain.

### 2.2 Legacy vs Sourced Domains

- **Legacy domains** (`approval_status = 'legacy'`): Purchased through HyperTide historically. HyperTide sourced the domain AND set up inboxes. We discovered these domains by matching inbox email addresses during EmailBison sync.
- **Sourced domains** (`approval_status = 'available' → 'purchased' → 'active'`): We generate domain names, price-check at Porkbun/Dynadot, purchase, configure nameservers, then submit to HyperTide for inbox setup only (no domain markup).

### 2.3 Domain-Level Columns

| Column | Purpose | Values |
|--------|---------|--------|
| `approval_status` | Purchase lifecycle | available, purchased, active, legacy |
| `pool_status` | Live/Reserve allocation | unassigned, live, reserve, burned |
| `domain_state` | Health/capacity state | live, flagged, dead |

These are **three independent dimensions**: purchase stage, pool allocation, and health.

---

## 3. Pool Allocation (Domain Level)

### 3.1 Core Principle

**All inboxes on a domain share the same pool assignment.** This is because:
- Domain-killing triggers (spam_complaint with 2+ cross-inbox pattern) compromise ALL inboxes on the domain
- If we mixed live and reserve inboxes on the same domain, a domain kill would burn our reserves too
- When we need to swap out a burned domain, we swap the ENTIRE domain (all ~50 inboxes for Entra)

### 3.2 Pool Values

| Domain `pool_status` | Meaning | Target % |
|-----------------------|---------|----------|
| `live` | A-Set — deployed to active campaigns | ~80% |
| `reserve` | B-Set — warmed backup, promoted when live burns | ~20% |
| `burned` | Compromised by confirmed domain-level trigger (2+ spam complaints cross-inbox pattern), permanently retired | N/A |
| `unassigned` | New domain, not yet allocated to a pool | N/A |

### 3.3 Pool Assignment Only Applies to Deployed Domains

A domain should only receive a pool_status of `live` or `reserve` AFTER:
1. It has been purchased and set up (`approval_status = 'active'` or `'legacy'`)
2. Inboxes have been detected in EmailBison
3. Those inboxes have completed incubation (21-day warmup)

**Pre-deployment domains** stay `pool_status = 'unassigned'`.

---

## 4. Inbox Lifecycle

### 4.1 How Inboxes Enter the System

1. HyperTide provisions inboxes on our domain
2. Inboxes appear in EmailBison (our sequencing platform)
3. Our `sync_accounts` worker detects them during hourly sync
4. We match the inbox email domain to our domains table
5. INSERT into `sender_accounts` with initial values

### 4.2 Lifecycle Stages

```
[detected in EB] → incubating (21 days warmup) → active (graduated) → dead (killed)
```

| Stage | `inventory_lifecycle_status` | Duration | What's Happening |
|-------|----------------------------|----------|-----------------|
| Incubating | `incubating` | ~21 days | Warmup in progress. NOT ready for campaigns. |
| Active | `active` | Until killed | Graduated. Ready for campaign assignment. |
| Dead | `dead` | Permanent | Kill trigger fired. Removed from campaigns. |

**Graduation is automatic:** After 21 days from `warmup_started_at`, `lifecycle_tag_sync` transitions the inbox to `active` and updates EB tags.

### 4.3 Inbox Pool Status

This is WHERE the graduated inbox is deployed:

| `inventory_pool_status` | Meaning | When Set |
|------------------------|---------|----------|
| `NULL` | Not yet assigned — incubating or dead | Initial insert; kill |
| `reserve` | B-Set — graduated, warming, ready to promote | After 21-day warmup graduation |
| `deployed` | A-Set — in active campaigns, sending | When domain pool_status = 'live' and set_tag_sync runs |
| `warning` | Cooldown — has bounce issues | When hard_bounces_24h >= 1 or hard_bounces_7d >= 3 |
| `quarantined` | Domain compromised — do NOT promote | When confirmed domain-level trigger fires |

---

## 5. The Promotion Flow

### 5.1 Normal Flow: Incubating → Reserve → Deployed

This is the happy path for every inbox:

```
Day 0:   Inbox detected in EB
         → inventory_lifecycle_status = 'incubating'
         → inventory_pool_status = NULL
         → EB tag: 'incubating'

Day 21:  Warmup complete, graduation
         → inventory_lifecycle_status = 'active'
         → inventory_pool_status = 'reserve' (ALWAYS starts in reserve)
         → EB tag: remove 'incubating', add 'live'

Day 21+: set_tag_sync evaluates domain pool_status
         IF domain.pool_status = 'live':
           → inventory_pool_status = 'deployed'
           → EB tag: add 'live' set tag (a_set_tag_name)
         IF domain.pool_status = 'reserve':
           → inventory_pool_status = 'reserve' (stays)
           → EB tag: add 'reserve' set tag (b_set_tag_name)
```

**Key insight:** Every inbox graduates to `reserve` first, THEN gets promoted to `deployed` based on domain allocation. We never skip reserve — it's the staging area.

### 5.2 Domain Burn & Promotion

When a confirmed domain-level trigger fires, the domain is burned and a reserve promoted:

**Conditional burns** — spam complaints (`spam_complaint`):
```
1. Inbox killed with spam_complaint trigger
2. Kill processor counts dead inboxes on same domain with spam_complaint
3. If 2+ inboxes → cross-inbox pattern confirmed → domain burn (same as above)
4. If 1 inbox → inbox-level only, domain safe, normal B-Set inbox promotion
```

> **Why conditional?** 1 spam complaint on 1 of 50 inboxes is statistically an inbox-level event (bad list segment, user error). 2+ complaints across different inboxes indicates the domain itself is being recognized as spam by recipients — that's domain-level compromise.

### 5.3 Inbox-Level Kill (Non-Domain)

When an inbox-level trigger fires (hard_bounces_24h, hard_blocked_24h, disconnected_timeout):

```
1. Single inbox killed: inbox_state = 'dead', inventory_pool_status = NULL
2. Domain health recalculated (trigger-aware):
   - Only reputation kills (spam_complaint, hard_blocked_24h) affect domain_state
   - List-quality kills (hard_unknown_24h, hard_bounces_24h) and operational kills (disconnected_timeout) do NOT change domain state
   - >30% unhealthy inboxes → domain_state = 'dead' (capacity safety net)
3. Domain pool_status stays 'live' — other inboxes continue sending
4. Capacity decreases but domain continues operating
```

**Domain degradation warning:** When multiple inbox kills reduce a domain from 50 → 30 → 20 inboxes, the domain is losing capacity. This is tracked via `domain_state` and health metrics, but the domain only gets `pool_status = 'burned'` on a confirmed domain-level trigger (2+ spam complaints across different inboxes).

---

## 6. Tags in EmailBison

### 6.1 Tag Types

Our system manages three categories of tags in EmailBison:

| Tag Category | Tag Names | Set By | Purpose |
|-------------|-----------|--------|---------|
| **Lifecycle** | `incubating`, `live` | lifecycle_tag_sync | Indicates warmup stage |
| **Pool/Set** | `live` (a_set), `reserve` (b_set) | set_tag_sync | Indicates deployment pool |
| **Kill flags** | `flagged_{trigger}` | kill_processor | Marks why inbox was killed |

### 6.2 How the Team Uses Tags

The team operates in EmailBison to assign inboxes to campaigns. They use tags to filter:

1. **Lifecycle filter:** Only assign inboxes tagged `live` (graduated, not incubating)
2. **Pool filter:** Only assign inboxes tagged `live` (A-Set/deployed pool)
3. **Avoid killed:** Never assign inboxes tagged `flagged_*`

The `reserve`-tagged inboxes are visible but not assigned — they're warmed and ready for when live domains burn.

### 6.3 Tag Naming Overlap

**Important:** The tag name `live` is used for BOTH lifecycle AND pool:
- Lifecycle `live` = "this inbox has graduated warmup" (set by lifecycle_tag_sync)
- Pool `live` = "this inbox is on an A-Set domain, deployed to campaigns" (set by set_tag_sync, configured via `a_set_tag_name`)

In practice these overlap: an inbox that's graduated AND on a live domain gets the `live` tag from both systems. But the distinction matters for reserve inboxes — they have lifecycle `live` (graduated) but pool `reserve` (not in campaigns).

---

## 7. What `warning` Means

`warning` is a **temporary inbox-level demotion** due to bounce activity:

| Condition | Result |
|-----------|--------|
| hard_bounces_24h >= 1 | inventory_pool_status → 'warning' |
| hard_bounces_7d >= 3 | inventory_pool_status → 'warning' |
| Bounces clear | Should return to previous pool (deployed or reserve) |

**Current problem:** The `warning` status has columns (`warning_started_at`, `cooldown_ends_at`, `warning_reason`) defined in the schema but **no active code uses them for clearing**. The only mechanism that sets `warning` is the `sync_accounts` UPSERT, which recalculates every hour. When bounces clear (counters reset daily), the inbox naturally moves out of `warning` on next sync.

**Warning does NOT exist at the domain level.** Domain health is tracked separately via `domain_state` (live/flagged/dead).

---

## 8. Summary: The Full Picture

```
DOMAIN LIFECYCLE:
  generated → purchased → ready (active) → deployed (inboxes in EB)
                                                ↓
POOL ALLOCATION (domain level):          live (80%) / reserve (20%)
                                                ↓
INBOX LIFECYCLE:                    incubating → active → dead
                                                ↓
INBOX POOL (follows domain):    NULL → reserve → deployed
                                         ↑           ↓
                                    (promotion)   (warning on bounces)
                                         ↑           ↓
                                    (bounces clear)  (back to pool)

EMAILBISON TAGS:
  Lifecycle: 'incubating' → 'live' (graduated)
  Pool:      'reserve' or 'live' (matches domain allocation)
  Kill:      'flagged_{trigger}' (permanent)

TEAM WORKFLOW:
  Filter EB by 'live' tag → assign to campaigns → system tracks performance
  If domain burns → system auto-promotes reserve → team sees new 'live' inboxes
```
