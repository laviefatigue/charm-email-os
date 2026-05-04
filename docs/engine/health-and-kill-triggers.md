# Health Monitoring & Kill Triggers

> **2026-05-04 — RATE-BASED REWRITE.** All count-based 24h rules removed.
> Single ESP-agnostic lifetime-rate rule replaces them. See [[../concepts/kill-triggers]]
> for the full concept doc and [[../adr/adr-010-lifetime-rate-kill-rule-2026-05-04]]
> for the decision record.

## What Exists Today (post-rewrite)

### Database Tables
- **`kill_trigger_events`** — Historical record of every kill trigger detection
- **`kill_queue`** — Pending kills awaiting processing
- **`domain_rotation_events`** — Domain state transitions (healthy → monitoring → burned)
- **`campaign_burn_events`** — Which campaigns lost inboxes to kills
- **`inbox_removal_events`** — Inbox removal tracking
- **`bounce_counter_resets`** — Daily counter reset audit trail (legacy `_24h` columns only)

### Kill Trigger Thresholds (Production — post-2026-05-04)

| Trigger | Threshold | Severity | Action |
|---------|-----------|----------|--------|
| `spam_complaint` | `complaints_lifetime ≥ 1` | Conditional domain-killing | Inbox kill instant; domain rate-evaluated |
| `hard_bounce_rate_lifetime` | `emails_sent_all_time ≥ 20 AND hard_bounces_lifetime / emails_sent_all_time > 5%` | Inbox-killing | Inbox kill |

That's it. Two rules. ESP-agnostic. No counts. No windows.

**Numerator**: `hard_bounces_lifetime` is computed on demand per inbox from `response_messages.bounce_type IN ('hard_blocked','hard_unknown')`. No stored counter, no decay, no reset job.

**Denominator**: `emails_sent_all_time` is synced from EB `sender.emails_sent_count`.

### Removed (kept in enum for historical rows only)

- `hard_blocked_24h`, `hard_unknown_24h`, `hard_bounces_24h` — count-based 24h rules. Replaced by lifetime rate.
- `hard_bounce_rate_7d`, `bounce_rate_all_7d` — windowed rates. Replaced by lifetime rate.
- `disconnected_timeout` — connection state. Removed by ADR-009 (notification ladder owns it now).
- `provider_block_*` — was misclassifying recipient rejections. Removed 2026-03-18.
- `fresh_inbox_blocked`, `fresh_inbox_unknown` — duplicates of hard_blocked/hard_unknown. Removed 2026-03-18.

### Kill Trigger Severity
- **Conditionally domain-killing** (`spam_complaint`): rate-evaluated by `kill_processor`. Workspace circuit breaker for fleet-wide list events.
- **Inbox-killing** (`hard_bounce_rate_lifetime`): individual inbox only.

### Key Files
- `sync_modules/health_checks.py` — Kill rule (`evaluate_lifetime_rule` pure function + `evaluate_inbox_health` integration). Runs every 15 min.
- `sync_modules/kill_processor.py` — Kill execution. Runs every 30 min.
- `scripts/validate_new_kill_rule.py` — Read-only fleet audit against the rule.
- `scripts/resurrect_false_positive_kills.py` — One-shot revival tool.

## How Records Are Created

### Health Check Flow (every 15 min)
```
For each active workspace:
  ├─ Query ALL live inboxes (inbox_state = 'live')
  │   SELECT ... emails_sent_all_time, complaints_lifetime,
  │          (subquery) hard_bounces_lifetime
  │   FROM sender_accounts ...
  │
  ├─ For each inbox, evaluate rule:
  │   1. complaints_lifetime ≥ 1     → trigger 'spam_complaint'
  │   2. emails_sent_all_time < 20   → SKIP (insufficient data)
  │   3. rate > 5%                   → trigger 'hard_bounce_rate_lifetime'
  │
  ├─ If trigger fires:
  │   ├─ INSERT: kill_queue (inbox_id, trigger_type, value, threshold, status='pending')
  │   ├─ INSERT: kill_trigger_events (historical record)
  │   └─ Dedup: ON CONFLICT (inbox_id) WHERE status = 'pending'
  │
  └─ When KILL_RULE_DRY_RUN=true: log decisions instead of queueing
```

### Kill Processor Flow (every 30 min) — unchanged
```
Query kill_queue WHERE status = 'pending':
  │
  For each pending kill (per-workspace via workspace-scoped EB API key):
  │
  ├─ 1. TAG in EmailBison: Add 'flagged_{trigger_type}' tag to inbox
  │     - flagged_hard_bounce_rate_lifetime
  │     - flagged_spam_complaint
  │
  ├─ 2. MARK DEAD locally:
  │   └─ UPDATE sender_accounts:
  │       ├─ inbox_state = 'dead'
  │       ├─ killed_at = NOW()
  │       ├─ kill_trigger = trigger_type
  │       ├─ inventory_lifecycle_status = 'dead'
  │       └─ inventory_pool_status = NULL
  │
  ├─ 3. REMOVE LIVE TAG: Remove 'live' tag from inbox in EmailBison
  │
  ├─ 4. UPDATE DOMAIN METRICS:
  │   ├─ Increment domain dead_inbox_count
  │   ├─ Calculate domain complaint rate (for spam_complaint)
  │   ├─ If spam kills: rate-based domain burn evaluation
  │   └─ INSERT: domain_rotation_events (if domain transitions state)
  │
  ├─ 5. PROMOTE BACKUP (cross-domain via pool_promotion):
  │   └─ Find oldest reserve inbox workspace-wide, promote to live
  │
  └─ 6. UPDATE kill_queue.status = 'flagged'
```

### Domain Burn Logic (unchanged from 2026-04-27 overhaul)

Only `spam_complaint` produces a domain burn evaluation. Rate-based:
- < 0.3% complaint rate = safe, inbox-level only
- 0.3% – 1.0% = `monitoring` (7-day window, re-evaluated)
- > 1.0% = immediate burn

Workspace circuit breaker: 3+ domains with spam kills in 24h = fleet-wide list event, all affected domains enter `monitoring` instead of burning.

`hard_bounce_rate_lifetime` is **inbox-level only** — never burns the domain. Rationale: a single inbox crossing the lifetime rate threshold indicates list-quality or sender-config issue specific to that inbox, not domain-wide compromise.

## What's Automated vs Manual

| Step | Automated | Manual |
|------|-----------|--------|
| Kill trigger detection | Yes (15 min) | — |
| Kill execution | Yes (30 min) | — |
| EmailBison tagging | Yes (kill processor) | — |
| Backup promotion | Yes (kill processor, cross-domain) | — |
| Domain burn evaluation (spam_complaint only) | Yes (rate-based) | — |
| Circuit breaker | Yes (fleet-wide detection) | — |
| Counter reset (legacy `_24h` columns) | Yes (daily midnight) | — |
| **Override/cancel a kill** | — | DB UPDATE |
| **Resurrect a false positive** | `scripts/resurrect_false_positive_kills.py` | Operator-driven |

**Kill triggers are 100% autonomous.** Human review only for resurrection of past false positives.

## What's Working in Production

### Post-rewrite state (2026-05-04)

- 307 inboxes resurrected from prior count-rule false positives (35 Barrena + 272 fleet)
- 58 legitimate kills queued under new rule (currently in `KILL_RULE_DRY_RUN` mode pending operator confirmation):
  - 21 SKMR Mary Elzey (8–25% lifetime rate)
  - 23 Hello Hero Jessica Jordan (5–10% lifetime rate)
  - 14 scattered single-inbox cases across other workspaces
- Cumulative bounce rate per workspace verified clean post-revival

## What's Dead Code / Half-Built (cleanup queue)

- `aggregate_bounce_counts_from_events` — `GREATEST(stale, fresh)` reconciliation. No longer affects kill decisions but still maintains `_24h` / `_7d` columns. Delete after UI consumers migrate to lifetime fields.
- `reset_daily_counters` — zeros `_24h` columns at midnight. Same: legacy column maintenance only.
- `decay_weekly_counters` — 14% daily decay on `_7d` columns. Same.
- `_thresholds_for_esp` / `get_count_threshold` — ESP-aware count threshold dispatch. No longer called by `evaluate_inbox_health`. Delete in next pass.
- Pre-2026-05-04 count-trigger tests in `tests/test_warning_drop.py` — marked `@_OBSOLETE_COUNT_RULE` skip with deprecation note. Delete after one release cycle.
- **Migration runner stuck on 076** (`076_domain_level_ab_sets.sql`) — pre-existing failure on existing-data check constraint. Blocks 18 pending migrations. Migration 105 was applied directly via admin endpoint as workaround. Needs separate cleanup.

## What Needs to Change

### For Headless Engine
1. **Kill trigger API:**
   - `GET /api/health/kill-queue` — View pending kills
   - `POST /api/health/kill-queue/{id}/cancel` — Override a kill (with reason)
   - `GET /api/health/kill-stats` — Summary stats for AI consumption

2. **Domain replacement chain** when a domain burns: auto-trigger generation → purchase → HyperTide provision.

3. **Webhook/callback on kill events.** AI agent managing the fleet needs real-time awareness, not just polling.

4. **Configurable thresholds via API.** `KILL_MATURE_RATE` / `KILL_MIN_SENDS_LIFETIME` are env-tunable but global. Per-workspace tolerance levels would help (some clients run higher-bounce campaigns by design).

## Downstream Connection

Kill triggers interact with **tagging and allocation** — see [tagging-and-allocation.md](tagging-and-allocation.md) — for backup promotion and tag management. Domain burns should eventually trigger **domain generation** — see [domain-generation.md](domain-generation.md) — for automated replacement.
