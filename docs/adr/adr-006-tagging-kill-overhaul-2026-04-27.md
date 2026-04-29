---
title: "ADR-006: Tagging & Kill System Overhaul (2026-04-27)"
created: 2026-04-28
updated: 2026-04-28
tags: [adr, status/accepted, sync, tagging, kill-triggers, pool-management, workspace-scoped]
status: accepted
---

# ADR-006: Tagging & Kill System Overhaul (2026-04-27)

## Status

**Accepted** — Implemented 2026-04-27 to 2026-04-28 (initial deploy `b4c5bda`, 7 follow-up commits through `7089acb` + `3d5f999`).

Supersedes the per-domain pool authority and serial admin-key tag write paths.

## Context

In April 2026, the tagging and kill system had three structural defects that produced visible production bugs:

1. **Dual tags in EmailBison.** `brittany@carrieselery.com` and `brittany.southern@carrieselery.com` carried both `live` AND `reserve` tags simultaneously, visible in the EB UI. Root cause: `lifecycle_tag_sync._graduate_mature_inboxes` hardcoded the `live` tag at graduation regardless of domain pool, and `set_tag_sync._sync_domain_sets` skipped per-cycle reconciliation when `current_pool == target_set` in DB even if EB had stale tags.

2. **Reserve inboxes pulled into campaigns.** `b.southern@carrieselery.com` was killed on 2026-04-23 with `hard_bounces_24h` despite being a reserve-pool inbox — meaning EB sent campaigns through reserve inboxes, breaking pool isolation.

3. **Stuck graduations.** `r.westberg@accelerateselery.com` was `lifecycle='incubating'` after 24.9 days warmup, well past the 21-day window. Investigation found the same revert bug class also affected dozens of other inboxes.

CEO directives at the start of the overhaul:

1. **100% Google Workspace going forward** — 3 inboxes per domain. No new Microsoft Entra orders.
2. **Microsoft Entra is legacy.** Existing Entra inboxes ride to death: tag `live` once, kill on trigger, never re-tag.
3. **Domain mixing is approved for cross-domain promotion only.** When kill_processor promotes a reserve inbox to fill a kill, the promoted inbox can have `inventory_pool_status='deployed'` while its source domain stays `pool_status='reserve'`.
4. **Reserve is the bench, not a passive label.** Graduation lands in reserve. Kills trigger workspace-scoped, cross-domain promotion.

A fifth directive emerged during execution:

5. **Connection status FIRST** — never auto-classify a Connected inbox as dead unless a kill trigger fired. Disconnected for 21+ days OR removed from EB → mark dead.

## Decision

We rewrote the tagging/kill stack with these load-bearing decisions:

### 1. Per-inbox `inventory_pool_status` is the sole authority for set tag reconciliation

`set_tag_sync` no longer derives an inbox's pool tag from `domain.pool_status` every cycle. Each inbox carries its own decision in `sender_accounts.inventory_pool_status`:

| `inventory_pool_status` | EB tags |
|---|---|
| `'deployed'` | `live` (and untag `reserve`) |
| `'reserve'` | `reserve` (and untag `live`) |
| `'warning'` | NEITHER (active circuit breaker) |
| `'quarantined'` | NEITHER (active circuit breaker) |
| `NULL` | NEITHER (unallocated, no pool) |

`domain.pool_status` retains two roles: (a) default for new graduations, (b) scope marker for burn events that NULL the pool of all inboxes on the domain.

**Why**: Domain-level authority blocks cross-domain promotion (the next set_tag_sync cycle reverts it). Per-inbox authority enables CEO Rule C3 "domain mixing on promotion."

**Tradeoff**: Slightly more complex SQL in set_tag_sync (per-inbox loop instead of per-domain bulk). Clarity wins.

### 2. Workspace-scoped EB API keys (migration 089) eliminate `switch_workspace()` races in the tag-write path

Pre-overhaul, all tag writes used the global `EMAILBISON_API_KEY` and called `switch_workspace(eb_workspace_id)` between workspaces. This:
- Forced sequential execution (two concurrent callers race over the workspace context)
- Was fragile (a crash mid-call left the client in the wrong workspace)
- Was slow (each switch was an extra round-trip)

Post-overhaul, every workspace has a Sanctum-scoped token in `workspace_api_keys`. `EmailBisonClient(api_key=key, is_workspace_scoped=True)` is created per workspace; `switch_workspace()` is a no-op when the flag is set. Tag writes are now concurrent across workspaces (semaphore=`SYNC_WORKSPACE_CONCURRENCY=3`), sequential within each.

The global `EMAILBISON_API_KEY` is retained ONLY for workspace discovery (the legitimate cross-workspace path).

### 3. Tag-first / untag-second ordering on every set_tag_sync write

The per-inbox loop in `set_tag_sync` now:
1. Tags the target pool first (e.g., `live`).
2. Untags the opposite pool second (e.g., `reserve`).

**Failure-mode reasoning**: If untag-first, a transient tag failure leaves the inbox with NO pool tag (campaigns can't pick it up). With tag-first, a failure on untag leaves a transient dual-tag that self-heals on the next 15-min cycle. Dual tags are operationally less harmful than orphans.

### 4. Reconciling untag every cycle (idempotent)

`set_tag_sync` now issues an idempotent untag of the OPPOSITE pool tag on every cycle, even when DB and EB already match. This fixes the historic skip-bug where a stale tag in EB persisted because the per-cycle "did anything change?" check was too eager.

### 5. ESP-aware graduation paths

- **Google** graduates to `'reserve'` (cross-domain promotion fills `'deployed'` from there).
- **Microsoft** graduates directly to `'deployed'` (CEO Rule C2 — legacy ride-to-death).

Microsoft is also pinned in `set_tag_sync`: always tagged `live`, never tagged `reserve`, warning circuit breaker is overridden. This makes the MS fleet a constant-state population that's never re-tagged in normal operation.

### 6. 14 business-day graduation timer (`warmup_enabled_since`, migration 094)

`lifecycle_tag_sync._graduate_mature_inboxes` filters by `warmup_enabled = TRUE` AND 14 business days since `warmup_enabled_since`. The new column (added by migration 094 with a maintenance trigger) tracks continuous warmup-enabled state — a paused-then-resumed warmup resets the clock, matching operational intent.

Pre-overhaul timer was 21 calendar days. The shift to 14 BD is tighter (no weekends in the count) and continuous-tracking (no false graduations from disabled-then-re-enabled warmup).

### 7. Workspace packages with override (migration 097)

`workspaces.package_id` ties a workspace to a `workspace_packages` row (seeded with `50k_google` and `100k_google`). The orchestrator's `_maintain_pool_thresholds` reads the `workspace_effective_targets` view and proactively promotes reserve inboxes to fill the live deficit.

`target_live_count_override` allows operators to lower the package target during ramp-up (validated by trigger to never exceed package target). `pause_pool_transitions` is an emergency stop.

**Why**: Without a contracted target, the system only reactively promotes on kills. New workspaces would have all-reserve, no-live. Override only LOWERS because the package IS the contract.

### 8. NO new pool_transition_queue table

We extended `inbox_rotation_history` (existing, with `rotation_type`, `source_pool`, `target_pool`, `reason`, `triggered_by`, `metadata` jsonb) instead of adding a new table. New `rotation_type` values: `'graduate'`, `'threshold_promotion'`, `'clerical_bypass'`. Cycle-based 15-min orchestrator provides natural retry — operations are idempotent.

**User direction**: "Are we taking into account the database schema that's already in place and not creating a new table for work that could be on a single one? I don't want a sprawling db either."

### 9. Connection status FIRST decision rule (Rule C7)

User directive 2026-04-28:

> "First check should be: is this inbox connected? Then statuses. If kill triggered, mark dead. If disconnected for extended duration, mark dead. If connected, carefully consider."

Codified:
- `mark_stale_accounts` (Option 1 patch): handles "removed from EB → dead"
- `disconnected_timeout` kill trigger: handles "disconnected 21+ days → dead" (existing, unchanged)
- Health checks: handle "kill triggered → dead" (existing)
- For Connected inboxes: never auto-classify as dead. Burned-domain inboxes that are still Connected stay `inbox_state='live'`; team handles EB campaign cleanup manually.

### 10. 20-send floor on count-based kill triggers

`KILL_THRESHOLD_MIN_SENDS_24H_FOR_COUNT_TRIGGER=20`. Count-based triggers (`hard_bounces_24h`, `hard_blocked_24h`, `hard_unknown_24h`) only fire when the inbox has ≥20 sends in 24h.

Phase 0 audit found 65% of recent count-trigger kills were on inboxes with <20 sends — low-volume noise (1 bounce out of 2 sends = 50% bounce rate by raw count, but statistically meaningless). Falls back to `total_sends_7d ≥ 20` for rollout safety until the new `total_sends_24h` column (migration 095) populates.

## Architecture (post-overhaul)

```
WorkspaceWriteOrchestrator (sync_modules/workspace_writes.py)
    for each ws in active workspaces with valid API key:
        if ws.pause_pool_transitions: skip
        client = EmailBisonClient(api_key=ws.key_token, is_workspace_scoped=True)
        # Sequential within workspace:
        await lifecycle_tag_sync.sync_workspace_tags(ws, client)
            # graduate (incubating → reserve|live), tag new (NULL or 'incubating'),
            # untag dead, untag orphan incubating from active (24h history-driven)
        if ws.package_id is not None:
            await orchestrator._maintain_pool_thresholds(ws)
            # proactive cross-domain promotion if deficit
        await set_tag_sync.sync_workspace_sets(ws, client)
            # per-inbox reconciliation; tag-first/untag-second; MS pin; circuit breaker
        await kill_processor.process_workspace_queue(ws.id, ws.name)
            # process kill_queue rows; cross-domain promote; small-domain safety net
    concurrency: asyncio.Semaphore(SYNC_WORKSPACE_CONCURRENCY=3)

pool_promotion module (sync_modules/pool_promotion.py)
    pick_promotion_candidates(db, workspace_id, n)
        # Domain-aware ordering:
        #   1. Partially-tapped reserve domains first (fewest remaining reserves first)
        #   2. Untapped reserve domains, oldest warmup_enabled_since first
        #   3. Within a domain, oldest reserve inbox first
    promote_inbox_to_deployed(...)
        # Transactional UPDATE + INSERT inbox_rotation_history row

OverhaulAuditModule (sync_modules/overhaul_audit.py)
    Daily fleet drift detector. Surfaces dual-tag candidates,
    silently-disabled warmup, is_active=FALSE orphans, stuck-incubation
    past 14 BD, incubating-in-campaigns, burned-in-campaigns. Posts
    Slack alert when any anomaly is non-zero.
```

## Migrations

| # | File | What it adds |
|---|---|---|
| 094 | `094_warmup_enabled_since.sql` | `warmup_enabled_since`, `warmup_disabled_at` columns + trigger to maintain them on warmup_enabled transitions + indexes + 4,172-row backfill from `warmup_started_at` |
| 095 | `095_total_sends_24h.sql` | `total_sends_24h INTEGER NOT NULL DEFAULT 0` + index. Populated by `sync_accounts` upsert |
| 096 | `096_warmup_trigger_handles_insert.sql` | Fix to migration 094: trigger fires on `INSERT OR UPDATE OF warmup_enabled` (was UPDATE-only) |
| 097 | `097_workspace_packages.sql` | `workspace_packages` reference table + workspace columns (`package_id`, `target_live_count_override`, `pause_pool_transitions`, `package_assigned_at`) + validation trigger + `workspace_effective_targets` view |

## Consequences

### Positive

- **Zero dual-tag invariant violations** post-deploy (verified by `scripts/audit_tags_fleet.py`).
- **Cross-domain promotion works** — kills no longer drop sending capacity below contracted volume.
- **Concurrent tag writes** — total cycle time bounded by max(workspace) × ⌈N/3⌉ instead of sum(workspaces).
- **Connection-first decision rule** prevents accidental kills of Connected inboxes during cleanup operations.
- **Daily audit surfaces drift** with 6 metrics covering all known failure modes from the overhaul.

### Negative

- **More complex SQL in set_tag_sync** (per-inbox loop). Mitigated by tests + clear documentation.
- **Workspace API keys are now load-bearing** — losing one means a workspace can't sync. Auto-provisioned by workspace discovery so the failure mode is "new workspace stuck for 24h until discovery runs," not "indefinitely broken."
- **Microsoft pin is a special case** — set_tag_sync code has a per-ESP branch. Long-term plan: Microsoft retirement, eventually remove the pin.
- **Schema cost of migrations 094–097** — three new columns on `sender_accounts`, four new on `workspaces`, one new reference table, two new triggers. Acceptable for the operational benefit.

### Operational follow-ups (not part of the overhaul)

- Auto-cleanup function for `burned_inboxes_in_campaigns` (1,019 baseline at deploy; manual until automated).
- Cross-workspace data integrity sweep (Sammy has 664 EB-only inboxes from historical mis-routing).
- 21-day disconnected_timeout review for stale tags on disconnected Gmail warning inboxes.
- Microsoft retirement plan (long-term — operational, not architectural).

## Post-deploy fixes (session-2)

The post-deploy fleet audit caught five latent bugs that the overhaul didn't surface in code review. All fixed and redeployed within 24 hours:

| # | Commit | Bug | Caught by |
|---|---|---|---|
| 1 | `7e79c0e` | `lifecycle_tag_sync._tag_new_warmup_inboxes` reverting graduations same cycle (filter `!= 'incubating'` matched `'active'`) | `stuck_incubation_14bd=85` not draining despite 85 successful graduations in `inbox_rotation_history` |
| 2 | `9e1c43f` | `AuditContext.complete(metadata=)` not persisting metric counts to `sync_audit_log` row | Audit row showed only `{"scope":"fleet"}` start metadata |
| 3 | `45ed164` | `daily_snapshot.capacity_utilization_pct` overflowing `NUMERIC(5,2)` | 10 of 11 workspaces' `daily_snapshot` ran with `partial` status |
| 4 | `13523ca` | `sync_accounts` flipping pool to `'warning'` for burned/cancelled domain inboxes (race with set_tag_sync's NULL handler) | 1,031 burned-domain inboxes oscillating pool='warning' ↔ NULL |
| 5 | `c866929` | `sync_accounts` upsert reverting `lifecycle='active'` → `'incubating'` for recently-graduated inboxes (warmup_started_at < 21d) | `incubating_in_campaigns` jumped 1 → 11 within 30 min after Phase C-style UPDATE |
| 6 | `7089acb` | (a) `_tag_new_warmup_inboxes` filter too narrow (NULL-only) — missed 266 inboxes whose lifecycle was set to 'incubating' by sync_accounts but never tagged in EB. (b) Clerical-bypass UPDATE doesn't trigger EB untag of 'incubating' tag. | Fleet tag audit `incubating_lifecycle_missing_incubating_tag=266` and `active_lifecycle_still_has_incubating_tag=3` |

## Related artifacts

- [[../work-logs/2026-04-27-tagging-kill-overhaul-plan]] — Full plan, handoff context, phased execution log, lessons learned.
- [[../decisions/POOL-ASSIGNMENT-AND-TAGGING-SYSTEM]] — Pool assignment & tagging system reference (updated 2026-04-28 for post-overhaul).
- [[../architecture/emailbison-sync]] — EmailBison sync worker architecture (updated 2026-04-28).
- [[../concepts/kill-triggers]] — Kill triggers concept (updated 2026-04-28).
- [[../concepts/package-templates]] — Package templates (updated 2026-04-28 for `workspace_packages` model).
- `scripts/audit_tags_fleet.py` — Fleet-wide DB↔EB tag audit script.
- `scripts/backfill_pool_status.py` — One-off pool backfill (already run 2026-04-27).
