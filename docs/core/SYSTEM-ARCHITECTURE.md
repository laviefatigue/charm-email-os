# Charm Email OS - Core System Architecture

**Document ID:** CORE-ARCH-001
**Created:** 2026-02-26
**Status:** Authoritative Reference

---

## Executive Summary

Charm Email OS is an **email infrastructure management system** that:
1. Purchases domains from registrars (Dynadot/Porkbun)
2. Orders inbox provisioning from HyperTide (vendor)
3. Syncs performance data from EmailBison (source of truth)
4. Applies health analysis and rotation decisions locally

**Critical Understanding:** We do NOT control inbox creation. We only control domain acquisition and rotation decisions.

---

## Control Boundaries

### What We Control

| Component | Control Level | Actions |
|-----------|--------------|---------|
| **Domain Purchase** | Full | Generate, price, purchase, DNS configuration |
| **HyperTide Orders** | Initiate Only | Request orders via Slack → they execute |
| **Rotation Decisions** | Full | Decide when to replace domains |
| **Health Analysis** | Full | Apply kill triggers, track metrics |
| **Campaign Assignment** | Partial | Tag/exclude bad inboxes in EmailBison |

### What We Do NOT Control

| Component | Owner | Our Role |
|-----------|-------|----------|
| **Inbox Creation** | HyperTide | Order and wait |
| **Inbox OAuth Setup** | HyperTide | Zero visibility |
| **EmailBison Data** | EmailBison | Read-only extraction |
| **Individual Inbox Replacement** | Not Possible | Must replace entire domain |
| **Warmup Mechanics** | EmailBison | Enable/disable only |

---

## The HyperTide Constraint

**CRITICAL: HyperTide does NOT support individual inbox replacement.**

When inboxes go bad, we must replace the **entire domain**, not individual inboxes.

### What HyperTide Provides

| Provider | Inboxes/Domain | Domains/Order | Inboxes/Order | Cost |
|----------|---------------|---------------|---------------|------|
| Microsoft Entra | 50 | 2 | 100 | $50/mo |
| Google Workspace | 3 | 5 | 15 | $50/mo |

### HyperTide Limitations

1. **Cannot add individual inboxes** to a domain
2. **Cannot remove individual inboxes** from a domain
3. **Cannot swap individual inboxes** when they go bad
4. Applies to BOTH HyperTide domains AND customer-supplied domains (BYO)

### What We CAN Do

1. **Replace entire domains** within an order (via HyperTide Bulk interface)
2. **Redistribute sending volume** across remaining active inboxes
3. **Safely send 3-4 emails per inbox per day** (increased from typical 2/day)

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 1: DOMAIN ACQUISITION                           │
│                              (We Control)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   AI Domain Generation → Price Check (Dynadot/Porkbun) → Purchase           │
│         ↓                        ↓                           ↓              │
│   domains table          cached_price, available      purchased_at          │
│   status: pending        porkbun_price, dynadot_price status: purchased     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 2: INBOX PROVISIONING                           │
│                         (HyperTide Controls)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Slack Order → HyperTide Team → Microsoft/Google Setup → EmailBison Upload │
│       ↓                ↓                    ↓                    ↓          │
│   We initiate    They execute         OAuth setup         Inboxes appear    │
│   and wait       (black box)          (invisible)         in workspace      │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  WE HAVE ZERO VISIBILITY INTO THIS PHASE                            │   │
│   │  Order completion = inboxes appearing in EmailBison                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 3: DATA EXTRACTION                              │
│                      (EmailBison = Source of Truth)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   EmailBison API                    Sync Worker                Our Database │
│   ─────────────                    ───────────                ────────────  │
│                                                                              │
│   GET /sender-emails        →      sync_accounts.py     →   sender_accounts │
│   (inboxes, status,                                         (extracted +    │
│    warmup, daily_limit)                                      calculated)    │
│                                                                              │
│   GET /campaigns            →      sync_campaigns.py    →   emailbison_     │
│   GET /campaigns/{id}                                        campaigns      │
│   (metrics, leads)                                                          │
│                                                                              │
│   GET /campaigns/{id}/      →      sync_events.py       →   response_       │
│       replies                                                messages       │
│   (inbox, bounced folders)                                                  │
│                                                                              │
│   GET /warmup/sender-emails →      sync_warmup.py       →   sender_warmup_  │
│   (warmup statistics)                                        snapshots      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 4: LOCAL ANALYSIS                               │
│                            (We Control)                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Health Checks          Kill Processor           Rotation Decision         │
│   ─────────────          ──────────────           ─────────────────         │
│                                                                              │
│   Bounce counting   →    Tag in EmailBison   →    Domain replacement        │
│   Kill triggers          Mark dead locally        (manual via HyperTide)    │
│   Domain health          Promote backups                                    │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  ALL ANALYSIS IS LOCAL                                              │   │
│   │  EmailBison API does NOT return: health_score, bounce_reason,       │   │
│   │  kill triggers, spam complaint detection                            │   │
│   │  We calculate these from raw data                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## EmailBison API - Complete Reference

### Endpoints We Use

| Endpoint | Method | Data Extracted | Sync Module |
|----------|--------|----------------|-------------|
| `/workspaces/v1.1` | GET | Workspace list | - |
| `/workspaces/v1.1/switch-workspace` | POST | Context switch | All |
| `/sender-emails` | GET | Inbox list (paginated) | sync_accounts |
| `/sender-emails/{id}` | GET | Single inbox details | sync_accounts |
| `/sender-emails/{id}/campaigns` | GET | Inbox → campaign mapping | sync_campaigns |
| `/campaigns` | GET | Campaign list (paginated) | sync_campaigns |
| `/campaigns/{id}` | GET | Campaign details + metrics | sync_campaigns |
| `/campaigns/{id}/replies` | GET | Replies/bounces by folder | sync_events |
| `/warmup/sender-emails` | GET | Warmup statistics | sync_warmup |
| `/warmup/sender-emails/enable` | PATCH | Enable warmup | sync_warmup |
| `/warmup/sender-emails/disable` | PATCH | Disable warmup | sync_warmup |
| `/tags` | GET | Tag list | kill_processor |
| `/tags` | POST | Create tag | kill_processor |
| `/tags/attach-to-sender-emails` | POST | Add tag to inbox | kill_processor |

### Sender Account Fields (from /sender-emails)

| EmailBison Field | Our Column | Notes |
|------------------|------------|-------|
| `id` | `emailbison_account_id` | External sync ID |
| `email` | `email_address` | Primary identifier |
| `status` | `status` | Connected, Not connected, Disabled |
| `provider` | `esp` | Mapped: Google→gmail, Microsoft→microsoft |
| `daily_limit` | `daily_limit` | Current send limit |
| `warmup_enabled` | `warmup_enabled` | Boolean |
| `emails_sent_count` | `emails_sent_all_time` | Cumulative |
| `total_replied_count` | `replies_all_time` | Cumulative |
| `bounced_count` | `bounces_all_time` | Cumulative |
| `bounce_rate` | `bounce_rate_7d` | From API (not reliable) |
| `warmup_score` | `warmup_score` | 0-100 (monitoring only) |
| `warmup_spam_count` | `warmup_spam_count` | Emails in spam during warmup |
| `warmup_bounces_received_count` | `warmup_bounces_received` | Warmup bounces (monitoring) |
| `warmup_bounces_caused_count` | `warmup_bounces_caused` | Warmup bounces caused |

### What EmailBison Does NOT Provide

| Missing Data | How We Handle It |
|--------------|------------------|
| `health_score` | Calculated locally from metrics |
| `bounce_reason` | Extracted from bounce message body via SMTP code parsing |
| `bounce_type` | Classified locally (hard_unknown, hard_blocked, soft_full, soft_temp) |
| `spam_complaint` | Detected from response text analysis + FBL patterns |
| `hard_bounces_24h` | Counted from response_messages with time filter |
| `total_sends_7d` | **NOT TRACKED** (gap in current implementation) |
| Campaign type (warmup vs user) | **NOT AVAILABLE** (critical gap) |

---

## Inbox Lifecycle

### Complete Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. ORDER PLACED                                                              │
│    Slack message → HyperTide #hypertide-orders channel                      │
│    Domain status: purchased → provisioning                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ (HyperTide executes - invisible to us)
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. INBOXES APPEAR IN EMAILBISON                                             │
│    Sync worker discovers via GET /sender-emails                             │
│    Domain status: provisioning → active                                      │
│    Inbox created in sender_accounts with:                                    │
│      - inbox_state: 'live'                                                   │
│      - status: 'Connected' (ideally) or 'Not connected'                     │
│      - warmup_enabled: depends on HyperTide config                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. WARMUP PERIOD (~30 days)                                                  │
│    EmailBison handles warmup sends automatically                            │
│    We track: warmup_started_at (first observation)                          │
│    We auto-enable warmup if inbox is Connected but warmup_enabled=false     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. ACTIVE SENDING                                                            │
│    Inbox assigned to campaigns in EmailBison                                 │
│    sending_started_at set when first deployed                               │
│    Performance tracked via campaign replies/bounces                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
              ┌─────────────────────┴─────────────────────┐
              ▼                                           ▼
┌─────────────────────────┐                 ┌─────────────────────────┐
│ 5a. HEALTHY OPERATION   │                 │ 5b. KILL TRIGGER FIRED  │
│     Continue sending    │                 │     hard_bounces_24h≥2  │
│     Monitor metrics     │                 │     spam_complaint≥1    │
│                         │                 │     etc.                │
└─────────────────────────┘                 └─────────────────────────┘
                                                         │
                                                         ▼
                                            ┌─────────────────────────┐
                                            │ 6. INBOX FLAGGED        │
                                            │    Tag in EmailBison:   │
                                            │    flagged_{trigger}    │
                                            │    inbox_state: 'dead'  │
                                            │    killed_at: NOW()     │
                                            └─────────────────────────┘
                                                         │
                                                         ▼
                                            ┌─────────────────────────┐
                                            │ 7. DOMAIN EVALUATION    │
                                            │    30%+ inboxes dead?   │
                                            │    RBL listing?         │
                                            │    Cannot maintain vol? │
                                            │         ↓               │
                                            │    REPLACE DOMAIN       │
                                            │    (via HyperTide Bulk) │
                                            └─────────────────────────┘
```

### Key States

| State | Column | Values | Meaning |
|-------|--------|--------|---------|
| **Connection** | `status` | Connected, Not connected, Disabled | EmailBison OAuth connection |
| **Kill Status** | `inbox_state` | live, dead | Has inbox been killed for bad behavior? |
| **Lifecycle** | `inventory_lifecycle_status` | incubating, active, dead | Age-based lifecycle |
| **Pool** | `inventory_pool_status` | deployed, warning, reserve, incubating | Operational readiness |

**Important Distinction:**
- `status='Not connected'` + `inbox_state='live'` = Needs reconnection, not killed
- `status='Disabled'` → `inbox_state='dead'` = Explicitly disabled in EmailBison

---

## Rotation Strategy

### Domain-Based Rotation (NOT Inbox-Based)

Since we cannot replace individual inboxes, rotation is at the **domain level**:

#### Tier 1: Volume Redistribution (Stay on Domain)

**Conditions:**
- Inbox deaths < 30% of domain
- Domain NOT on RBL
- Can maintain required volume at 3-4 emails/inbox/day

**Action:** Ice bad inboxes, redistribute volume across remaining healthy inboxes

#### Tier 2: Domain Replacement (Full Swap)

**Trigger (ANY of):**
- Inbox deaths ≥ 30% of domain
- Domain appears on RBL
- Cannot maintain required volume
- Domain-level bounce rate > 10%

**Action:** Replace entire domain via HyperTide Bulk interface

### Capacity Calculation

```
Per-Domain Capacity:
- Conservative: Active Inboxes × 3 emails/day
- Aggressive: Active Inboxes × 4 emails/day (short-term only)

Reserve Buffer: 20-30% above required volume
```

---

## Data Integrity Status

### Verified Working

| Component | Status | Notes |
|-----------|--------|-------|
| Inbox discovery from EmailBison | ✅ | Properly syncs new inboxes |
| Connection status tracking | ✅ | Fixed in migration 051-052 |
| Warmup observation tracking | ✅ | Fixed in migration 043-044 |
| Kill trigger tagging | ✅ | Tags inboxes without deletion |
| Bounce type classification | ✅ | SMTP code parsing works |

### Known Gaps

| Issue | Severity | Impact |
|-------|----------|--------|
| `total_sends_7d` never populated | **CRITICAL** | Rate-based kill triggers never fire |
| Warmup vs campaign bounces mixed | **HIGH** | May kill inboxes for warmup bounces |
| Spam folder not synced | **HIGH** | Missing spam complaints |
| Daily snapshot overcounting | **MEDIUM** | Inflated volume charts |
| Bounce counter duplication risk | **MEDIUM** | Premature kills possible |

See [DATA-INTEGRITY-AUDIT.md](./DATA-INTEGRITY-AUDIT.md) for detailed analysis.

---

## Related Documents

- [DATA-INTEGRITY-AUDIT.md](./DATA-INTEGRITY-AUDIT.md) - Detailed integrity analysis
- [../infrastructure/hypertide-rotation-policy.md](../infrastructure/hypertide-rotation-policy.md) - Rotation policy
- [../concepts/domain-lifecycle.md](../concepts/domain-lifecycle.md) - Domain states
- [../concepts/inbox-provisioning.md](../concepts/inbox-provisioning.md) - Provisioning flow
- [../local-development/emailbison-sync-worker.md](../local-development/emailbison-sync-worker.md) - Sync worker details

---

**Document Version:** 1.0
**Last Updated:** 2026-02-26
**Author:** System Audit
