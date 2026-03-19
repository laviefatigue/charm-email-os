# Kill Triggers Reference

Kill triggers determine when an inbox is marked as "dead" and removed from active sending.

## Trigger Types & Thresholds

| Trigger | Threshold | Type | Domain Burn? | Description |
|---------|-----------|------|--------------|-------------|
| `spam_complaint` | >= 1 | Reputation | Rate-based (see thresholds) | Spam complaint kills inbox. Domain burn evaluated by complaint rate against thresholds |
| `hard_blocked_24h` | >= 2 | Reputation | No | Spam/policy rejection in 24h |
| `hard_unknown_24h` | >= 3 | List Quality | No | Invalid recipient errors in 24h |
| `hard_bounces_24h` | >= 2 | Operational | No | Combined hard bounces in 24h |
| `disconnected_timeout` | 21 days | Operational | No | Disconnected for 21+ days |
| `hard_bounce_rate_7d` | > 2.0% | Operational | No | 7-day hard bounce rate (min 100 sends) |
| `bounce_rate_all_7d` | > 5% | Operational | No | 7-day total bounce rate (min 100 sends) |

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
1. `burn_domain_and_promote()` sets `pool_status = 'burned'` on the domain
2. ALL inboxes on that domain are condemned — even healthy ones
3. A reserve **domain** (with all its inboxes) is promoted to replace it
4. If no reserve domain exists → Slack alert: "URGENT: Order replacement domains via HyperTide"

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
| `migrations/076_domain_level_ab_sets.sql` | `burn_domain_and_promote()` SQL function |
| `api/routes/health.py` | Analysis endpoints |
