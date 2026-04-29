---
title: "ADR-007: Drop `inventory_pool_status='warning'` + tighten Google kill thresholds"
created: 2026-04-29
updated: 2026-04-29
tags: [adr, status/accepted, kill-triggers, pool-management, v3-alignment]
status: accepted
---

# ADR-007: Drop `inventory_pool_status='warning'` + tighten Google kill thresholds

## Status

**Accepted** — Implemented 2026-04-29.

Migrations: 098 (one-time drain of existing warning rows).
Code: commits TBD.

## Context

The 2026-04-27 overhaul (ADR-006) inherited an `inventory_pool_status='warning'` intermediate state from earlier code. This state was set by `sync_accounts.upsert` whenever an inbox crossed `hard_bounces_24h ≥ 1 OR hard_bounces_7d ≥ 3` and acted as a soft-pause buffer:

- `set_tag_sync` untagged both `live` and `reserve` (active circuit breaker)
- The inbox sat untagged until either:
  - Bounces subsided (`auto-clear` branch restored pool from domain default), OR
  - A separate kill trigger fired (the warning state did not escalate to kill on its own)

**Three problems with this design:**

1. **Not in v3 spec.** The Health V3 specification (per [docs/features/v3-compliance-gap-analysis.md](../features/v3-compliance-gap-analysis.md) and [docs/features/hypertide-health-v3-impact.md](../features/hypertide-health-v3-impact.md)) defines only inbox states `live → dead` with kill-trigger transitions. There is no soft-pause intermediate. The `warning` state was a charm-specific addition not anchored in the design contract.

2. **Inboxes can sit in warning indefinitely.** Auto-clear requires `hb_24h < 1 AND hb_7d < 3`. The `_24h` counter resets nightly, but `_7d` decays only ~14% per day. An inbox that keeps bouncing without enough volume to trigger rate-based kill (which needs 100+ sends) can persist in warning for weeks. There was no escalation path.

3. **Misaligned with the small-fleet Google reality.** With 100% Google going forward (CEO directive 2026-04-27) and 3 inboxes per domain, ONE dead inbox = 33% domain capacity loss — already at v3's "replace domain" threshold (30%). A 1-bounce buffer before kill makes less sense for a fleet where every inbox is structurally significant. v3 spec says "kill fast, swap fast, diagnose after."

The 2026-04-28 fleet tag audit found 75 Gmail inboxes in warning state, all with `total_sends_*=0` (the very condition the now-fixed delta bug `bd4a25a` was hiding). They had bounced, hit warning, and stayed there because the floor was unsatisfiable. None were ever escalated.

A user question framed the decision: *"can you explain warning then if google inboxes based on kill triggers?"* — the answer was that warning's value-add over kill is small (1-bounce buffer + auto-recovery), and its downside (indefinite stuck-state) is real.

## Decision

**Drop `inventory_pool_status='warning'` fleet-wide. Replace with direct kill-queue queueing when bounce thresholds are met.**

### Pool state model — before vs after

**Before (4 states):**
- `'deployed'` — in active campaigns
- `'reserve'` — bench
- `'warning'` — soft-pause (active circuit breaker)
- `'quarantined'` — reserved for future severe use (never used in practice)
- `NULL` — unallocated

**After (3 states):**
- `'deployed'` — in active campaigns
- `'reserve'` — bench
- `NULL` — unallocated

(`'warning'` and `'quarantined'` are no longer set by code; existing rows are drained by migration 098. The string values remain reachable in stored historical rows for audit trail purposes.)

### Kill threshold model — ESP-aware

**Microsoft (legacy ride-to-death) — UNCHANGED:**

| Trigger | Threshold |
|---|---|
| `hard_blocked_24h` | ≥ 2 |
| `hard_unknown_24h` | ≥ 3 |
| `hard_bounces_24h` (combined fallback) | ≥ 2 |

Microsoft is being phased out. No point accelerating kills on a legacy population.

**Google — TIGHTENED:**

| Trigger | Threshold |
|---|---|
| `hard_blocked_24h` | ≥ **1** |
| `hard_unknown_24h` | ≥ **1** |
| `hard_bounces_24h` (combined fallback) | ≥ **1** |

All three become ≥ 1 for Google, with the **20-send floor still in effect** (a count trigger only fires when `total_sends_24h ≥ 20 OR total_sends_7d ≥ 20`). This protects against warmup-network bounce noise on low-volume inboxes.

**Spam complaint — UNCHANGED for both ESPs:**
- `complaints_lifetime ≥ 1` triggers kill, no floor (single complaint is signal regardless of volume).

**Rate-based — UNCHANGED for both ESPs:**
- `hard_bounce_rate_7d > 2.0%` with `min 100 sends`
- `bounce_rate_all_7d > 5.0%` with `min 100 sends`

**Disconnected timeout — UNCHANGED:**
- 21 days disconnected → kill

### Code locus

The ESP-aware lookup is implemented in `sync_modules/health_checks.py`:

```python
def get_count_threshold(esp: Optional[str], trigger: str) -> int:
    if esp == 'gmail':
        return GOOGLE_KILL_THRESHOLD_*[trigger]   # 1/1/1
    return KILL_THRESHOLD_*[trigger]               # 2/3/2 (MS + unknown ESP)
```

Each count-based trigger evaluation in `evaluate_inbox_health` calls this function with the inbox's ESP. All three Google thresholds are configurable via env vars (`GOOGLE_KILL_THRESHOLD_HARD_BLOCKED_24H`, etc.) for emergency rollback.

## Consequences

### Positive

- **State model simplification.** Pool has 3 states instead of 5 (counting NULL and the dead `quarantined`). Easier to reason about, audit, and visualize.
- **No more indefinite warning purgatory.** Inboxes either send or get killed. No stuck-state.
- **v3 spec alignment.** Charm Email OS now matches the Health V3 specification's state model.
- **Faster reputation protection on Google.** A single hard bounce on a 3-inbox domain (33% capacity loss) triggers immediate response rather than soft-pausing into ambiguity.
- **Audit metric simplification.** `pool_warning_should_have_no_pool_tag` (which had 224 by-design Microsoft pin violations + 13 disconnected-Gmail genuine violations and was therefore mostly noise) is replaced by `kill_queue_pending_over_2h` — a cleaner watch signal for queue health.

### Negative

- **More Google kills.** Tightened thresholds will produce more kill-queue activity on Google. The 20-send floor protects against warmup noise, but well-volume inboxes with a single bad-recipient bounce now die.
- **No more soft-recovery for transient blips.** Pre-overhaul, an inbox that hit one hard bounce could recover if the next 24h had no bounces (auto-clear from warning back to deployed). Post-ADR-007, that one bounce is enough — kill is permanent.
- **Microsoft legacy keeps the gap.** MS thresholds remain at 2/3/2. Operationally fine (legacy fleet, no new orders) but creates a known divergence between ESPs that future maintainers must remember.

### Mitigations for the negatives

- **20-send floor preserved.** Bounces on low-volume inboxes (warmup phase, slow campaigns) don't trigger kills. The floor handles the noise case.
- **Rate-based gates unchanged.** Rate triggers still need 100 sends minimum. They catch sustained problems, not single events.
- **`disconnected_timeout` unchanged at 21 days.** Connection loss isn't accelerated — operational mishaps don't kill quickly.
- **Migration 098 staged.** Existing warning rows are evaluated against the new threshold + 20-send floor. As of 2026-04-29 pre-state, 0 of 75 Gmail warning inboxes have ≥ 20 sends, so 0 will be killed by the migration itself. Future bounces will route through the new path.

## Rollout

1. Migration 098 applied to production via admin SQL endpoint with pre-state snapshot at `scripts/backfill_snapshots/2026-04-29_warning_drop_pre_state.json` (299 rows: 75 gmail + 224 microsoft).
2. Code deploy via Coolify after migration applies.
3. First post-deploy cycle: monitor kill_queue depth — expected near-zero new kills initially since `total_sends_24h` is just starting to populate (post-`bd4a25a` delta fix). As fleet send activity accumulates, kill rate normalizes.
4. Re-run [scripts/audit_tags_fleet.py](../../scripts/audit_tags_fleet.py): expect 0 `pool_warning_should_have_no_pool_tag` violations (replaced by `legacy_pool_state_warning_after_migration_098` if any drift exists).
5. 7-day watch: track Google kill rate vs Microsoft kill rate. Expectation: Google kills 2-3x more frequently than Microsoft (consistent with tighter thresholds).

## Tests

`tests/test_warning_drop.py` — 14 tests:

| # | Scenario | Expectation |
|---|---|---|
| W1 | Google + hb_24h=1 + 25 sends | kill_queue created |
| W2 | Google + hb_24h=1 + 10 sends_24h, 15 sends_7d | NO kill (floor) |
| W3 | Microsoft + hb_24h=1 + 25 sends | NO kill (MS threshold = 2) |
| W4 | Microsoft + hb_24h=2 + 25 sends | kill_queue created |
| W5 | Google + hb_7d=5, sends_7d=50 | NO kill (rate gate needs 100 sends) |
| W6 | Google + hard_blocked=1 + sends | kill_queue with `hard_blocked_24h` (priority over fallback) |
| W7 | sync_accounts upsert | Pool stays in {deployed, reserve, NULL}; never 'warning' |
| W8 | set_tag_sync NULL pool | Untags both `live` and `reserve` |
| W9 | Migration 098 idempotent | Re-applying produces no additional changes |
| W10 | Migration 098 on MS warning inbox | Restored to `deployed` (pin) |
| R1 | spam_complaint=1 + 0 sends | kill (no floor on spam) |
| R2 | disconnected 22 days | kill via `disconnected_timeout` |
| R3 | hb_rate_7d=2.5% + 200 sends | kill via `hard_bounce_rate_7d` |
| R4 | MS pin: NULL pool inbox | Tagged `live` (pin overrides NULL) |

## Followup (2026-04-29 same day): kill_queue dedup index relaxed (migration 099)

After deploying ADR-007, an investigation into "why aren't certain inboxes with current bounce signals being killed" surfaced a related structural issue: the partial unique index `idx_kill_queue_inbox_pending` was `WHERE status IN ('pending', 'flagged')`. That assumed `flagged` always means the inbox is dead — but pre-overhaul kill_processor (EB-tag-first ordering) sometimes succeeded on EB tagging while failing the DB death-state update. Result: 76 inboxes (47 MS + 29 Gmail) had `kill_queue.status='flagged'` from March 2026 with `inbox_state='live'`, blocking new spam_complaint or hard_bounces kills from queueing via the partial unique index.

**Decision**: narrow the index to `WHERE status = 'pending'` only. Migration 099 ships alongside ADR-007.

**Why safe**:
- The current kill_processor (post-overhaul) is DB-first inside a single try block (kill_processor.py:336-360 — sets `kill_queue.status='flagged'` AND `inbox_state='dead'` together). Steady-state never produces flagged-but-alive.
- Properly-dead inboxes (`inbox_state='dead'`) are filtered out of `health_checks.check_workspace_health` (line 330: `WHERE inbox_state = 'live'`). They cannot be re-queued, so the index doesn't need to "protect" them.
- Only the buggy/legacy "flagged but alive" case is unblocked. If signals fire, health_checks queues a new pending row, kill_processor processes it normally — self-heals the bad state.

**New audit metric**: `flagged_but_alive_count` in `OverhaulAuditModule`. Counts kill_queue rows with `status='flagged'` for inboxes with `inbox_state='live' AND killed_at IS NULL`. Should be 0 in steady state. Non-zero alerts on Slack.

**Affected files**:
- `migrations/099_relax_kill_queue_dedup.sql` (NEW)
- `sync_modules/health_checks.py` — `queue_for_kill` ON CONFLICT clause matches new index
- `sync_modules/overhaul_audit.py` — new `flagged_but_alive_count` metric
- `tests/test_warning_drop.py` — W11 verifies flagged+alive can re-queue

**Pre-state cleanup** (ran 2026-04-29 ~15:35 UTC, before the migration): 76 stale provider_block_* flagged rows cancelled via admin SQL. Pre-state snapshot at `scripts/backfill_snapshots/2026-04-29_provider_block_cleanup_pre_state.json`. 41 of those 76 inboxes had current bounce signals and re-trigger kills under ADR-007 thresholds on the next health_checks cycle.

## Related

- [[adr-006-tagging-kill-overhaul-2026-04-27]] — overhaul that introduced the per-inbox pool authority model
- [[../decisions/POOL-ASSIGNMENT-AND-TAGGING-SYSTEM]] — pool assignment reference
- [[../concepts/kill-triggers]] — kill triggers concept doc
- [[../features/v3-compliance-gap-analysis]] — V3 spec compliance audit
- [[../features/hypertide-health-v3-impact]] — Hypertide constraints + small-fleet Google logic
