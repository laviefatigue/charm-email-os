# Kill Triggers Reference

Kill triggers determine when an inbox is marked as "dead" and removed from active sending.

> **2026-05-04 — Rate-based rewrite (ADR-010).** All count-based 24h triggers and 7d windowed rate triggers were replaced by a single ESP-agnostic lifetime-rate rule. Numerator computed on demand from `response_messages` (no rolling counter). See [docs/concepts/kill-triggers.md](concepts/kill-triggers.md) for the full reference.

## Trigger Types & Thresholds (current)

| Trigger | Threshold | Type | Domain Burn? | Description |
|---------|-----------|------|--------------|-------------|
| `spam_complaint` | `complaints_lifetime ≥ 1` | Reputation | Rate-based (see below) | Phrase-matched spam complaint in lead reply. Inbox kill instant; domain burn evaluated by complaint rate. |
| `hard_bounce_rate_lifetime` | `hard_bounces / emails_sent_all_time > 5%` (≥ 20 sends) | Reputation + List Quality | No (inbox-level only) | Lifetime hard-bounce rate exceeds Postmaster "high" threshold. ESP-agnostic. |

## Removed Triggers (kept in enum for historical rows only)

These were the rules pre-2026-05-04. They are no longer evaluated; new kills do not emit them. Historical `kill_queue` and `sender_accounts.kill_trigger` rows still classify under these values.

| Trigger | Old Threshold | Reason for removal |
|---------|---------------|--------------------|
| `hard_blocked_24h` | ≥ 1 (Gmail) / ≥ 2 (MS) | Counter inflation — `GREATEST(stale, fresh)` reconciliation produced false positives. 2026-04-14 Barrena mass-kill triggered the rewrite. |
| `hard_unknown_24h` | ≥ 1 (Gmail) / ≥ 3 (MS) | Same |
| `hard_bounces_24h` | ≥ 1 (Gmail) / ≥ 2 (MS) | Same |
| `hard_bounce_rate_7d` | > 2.0% (min 100 sends) | Replaced by lifetime rate (more stable, no window math). |
| `bounce_rate_all_7d` | > 5% (incl. soft) | Removed — soft bounces are not reputation signals. |
| `disconnected_timeout` | ≥ 21 days disconnected | Removed by ADR-009 — connection state is monitoring-only. |
| `fresh_inbox_blocked`, `fresh_inbox_unknown` | (removed 2026-03-18) | Were duplicates of `hard_blocked_24h` / `hard_unknown_24h`. |

307 inboxes killed by the count-based rules but healthy under the new rate rule were resurrected on 2026-05-04 via `scripts/resurrect_false_positive_kills.py`.

## Domain Burn Classification

The kill processor uses rate-based classification to decide domain-level action after an inbox kill:

**Rate-based domain evaluation** (`spam_complaint`):
- Domain complaint rate = spam-killed inboxes / total inboxes on domain
- **< 0.3%** complaint rate = domain safe (inbox kill only, promote B-Set inbox)
- **0.3% - 1.0%** complaint rate = `monitoring` state, 7-day observation window. If rate stays below 1.0% after 7 days, domain returns to `flagged`. If rate exceeds 1.0%, domain burns.
- **> 1.0%** complaint rate = immediate domain burn

**Workspace circuit breaker:**
- 3+ domains in the same workspace with spam kills in 24h = fleet-wide list quality event
- Affected domains enter `monitoring` instead of burning, even if rate exceeds 1.0%
- Prevents cascade burns from a bad list hitting multiple domains simultaneously

**Capacity safety net:** > 30% unhealthy inboxes AND (domain has 10+ inboxes OR 2+ unhealthy) = `dead`

**Inbox-level only** (all other triggers):
- Indicate individual inbox or list quality issues
- B-Set inboxes from the same domain CAN be promoted
- Domain continues operating with reduced capacity

> **History**: Prior to 2026-03-18, `spam_complaint` was an instant domain burn. Changed to require 2+ cross-inbox pattern on 2026-03-18. Updated to rate-based thresholds on 2026-03-19 for proportional response across different domain sizes.

## Domain Burn = Total Loss

**A domain burn condemns ALL inboxes on that domain.** The reserve pool operates at the **domain level**, not the inbox level. You cannot split inboxes from the same domain and selectively keep some.

When a domain burns:
1. `burn_domain_and_promote()` sets `pool_status = 'burned'` on the domain AND writes the verdict — `qualifies_for_cancellation_at = NOW()` + `qualifies_for_cancellation_reason = <trigger_type>` — atomically with the burn (per migration 125 / DECISION 6 of [[hypertide-data-model-and-change-tracking]]). The Hypertide change tracker reads this verdict to label HT cancellations as `justified` (we burned it first) vs `unjustified` (HT/operator acted out-of-band).
2. ALL inboxes on that domain are condemned — even healthy ones
3. A reserve **domain** (with all its inboxes) is promoted to replace it
4. If no reserve domain exists → Slack alert: "URGENT: Order replacement domains via HyperTide"

**Revert path** (operator resurrects a falsely-burned domain): also NULL `qualifies_for_cancellation_at` + `_reason`. A NULL verdict reads correctly through the change tracker as "no, we did not justify this cancellation." Not wired automatically; operator-driven via [scripts/resurrect_false_positive_kills.py](../scripts/resurrect_false_positive_kills.py) or manual UPDATE.

**Blast radius by ESP** (set by vendor HyperTide, not configurable):

| ESP | Inboxes/Domain | Inboxes Lost per Burn | Daily Capacity Lost |
|-----|---------------|----------------------|---------------------|
| Gmail | ~3 | ~3 | ~60 sends/day |
| Microsoft | ~50 | ~50 | ~100 sends/day |

A Microsoft domain burn destroys ~50 inboxes even if only 2-3 triggered the kill. The remaining healthy inboxes are collateral damage. This is a structural concentration risk inherent to the Microsoft infrastructure shape provided by HyperTide.

## Trigger-Aware Domain State

`domain_state` is computed from **domain complaint rate** — list-quality and operational kills do not change domain state:

| Rule | Resulting State |
|------|----------------|
| Complaint rate > 1.0% | `dead` (immediate burn) |
| Complaint rate 0.3% - 1.0% | `monitoring` (7-day observation window) |
| Complaint rate 0.1% - 0.3% | `flagged` |
| Complaint rate < 0.1% | `live` |
| > 30% unhealthy AND (10+ inboxes OR 2+ unhealthy) | `dead` (capacity safety net) |
| Workspace circuit breaker (3+ domains with spam kills in 24h) | `monitoring` (overrides burn) |

Domain state values: `live`, `flagged`, `monitoring`, `dead`

**Note**: `domain_state` and `pool_status = 'burned'` are separate concepts. A domain can be `domain_state = 'dead'` from the capacity safety net but not burned. A domain in `monitoring` is under observation and may recover or burn after the 7-day window.

## ESP Kill Profiles

Gmail and Microsoft have fundamentally different risk profiles under the same trigger definitions:

| Metric | Gmail | Microsoft |
|--------|-------|-----------|
| **Inboxes per domain** | ~3 (HyperTide) | ~50 (HyperTide) |
| **Daily limit per inbox** | 20 | 2 |
| **Inbox kill rate** | Higher (more volume per inbox → triggers hit faster) | Lower (less volume → triggers hit slower) |
| **Domain burn rate** | Lower (kills spread across many domains) | Higher (kills concentrate on fewer domains) |
| **Blast radius per burn** | Low (~3 inboxes, ~60 sends/day) | Catastrophic (~50 inboxes, ~100 sends/day) |
| **Rate trigger activation** | ~5 days (100 sends at 20/day) | ~50 days (100 sends at 2/day) |

**Detection gap**: At 2 sends/day, a Microsoft inbox cannot trigger `hard_unknown_24h >= 3` (max 2 bounces from 2 sends). Rate triggers take ~50 days to activate. This means problematic Microsoft inboxes are detected slower than Gmail inboxes.

## Incubation Period

The **21-day incubation period** starts at `warmup_started_at`. During this period, inboxes are tagged `incubating` in the lifecycle system. Standard kill triggers apply — there are no special incubation-only triggers.

## Kill Processing Flow

1. **Health check** runs every 15 minutes (`sync_modules/health_checks.py`)
2. Evaluates each inbox against all thresholds
3. Triggered inboxes added to `kill_queue` table
4. **Kill processor** runs every 30 minutes (`sync_modules/kill_processor.py`)
5. Processes queue: marks inbox dead, tags in EmailBison, evaluates domain burn, handles reserve domain promotion, sends Slack alerts

## Related Files

| File | Purpose |
|------|---------|
| `sync_modules/health_checks.py` | Threshold definitions, `evaluate_inbox_health()`, domain state |
| `sync_modules/kill_processor.py` | Queue processing, domain burn decision, reserve promotion |
| `sync_modules/sync_events.py` | Bounce classification from EmailBison responses |
| `migrations/076_domain_level_ab_sets.sql` | `burn_domain_and_promote()` original SQL function |
| `migrations/088_fix_domain_burn_functions.sql` | Reserve-burn handling + no-reserve action codes |
| `migrations/125_burn_writes_qualifies_for_cancellation.sql` | Adds `qualifies_for_cancellation_at` + `_reason` writes to the burn UPDATE (DECISION 6) |
| `apps/hypertide-worker/src/hypertide_worker/change_detector.py` | Reads the verdict columns when labeling HT cancellation events |
| `api/routes/health.py` | Analysis endpoints |
