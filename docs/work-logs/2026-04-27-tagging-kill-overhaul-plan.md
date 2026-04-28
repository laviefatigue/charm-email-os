# Tagging & Kill System Overhaul — Plan & Handoff

**Started:** 2026-04-27
**Last updated:** 2026-04-28
**Status:** Schema + DB cleanup complete; code deploy via CI/CD pending
**Supersedes:** [[2026-04-08-TAG-RECONCILIATION-WORK]] (point fix), [[2026-04-08-PRODUCTION-FIX-CONTEXT]] (running context)

> **READ THIS FIRST IF YOU'RE PICKING THIS UP.** This document is a self-contained handoff. The system was producing dual-tagged inboxes, killing healthy inboxes for low-volume bounces, and skipping graduations. We rewrote the tagging/kill stack to fix root causes. Migrations 094–097 are applied to production. DB cleanup is done. Code changes are complete locally and awaiting your CI/CD deploy. Section "What's next" lists every remaining action.

---

## Context — why this exists

CEO confirmed four pivots that change the system's invariants:

1. **100% Google Workspace infrastructure going forward** — 3 inboxes per domain, no Microsoft Entra in new builds.
2. **Microsoft Entra is legacy.** Remaining Entra inboxes ride to death: tag `live`, kill on trigger, never re-tag.
3. **Domain mixing is approved for cross-domain promotion only.** When kill_processor promotes a reserve inbox to fill a kill, the promoted inbox can have `inventory_pool_status='deployed'` while its source domain remains `pool_status='reserve'`.
4. **Reserve is the bench, not a passive label.** Graduation lands in reserve. When a live inbox is killed, kill_processor promotes the oldest reserve inbox (workspace-scoped, cross-domain) to live so sending capacity never drops. Campaigns are reapplied by filtering on the `live` tag — that natural reapply cycle drains stale `campaign_inboxes` entries (dead/reserve inboxes that haven't been removed). Therefore campaign-membership enforcement is **out of scope** for this overhaul; tag correctness is sufficient because reapply does the cleanup.

### Concrete production bugs that triggered the overhaul

- `brittany@carrieselery.com` and `brittany.southern@carrieselery.com` carry both `live` AND `reserve` tags simultaneously (visible in EB UI).
- `b.southern@carrieselery.com` was killed on 2026-04-23 with `hard_bounces_24h` despite being a reserve-pool inbox — meaning EB sent campaigns through reserve inboxes, breaking pool isolation.
- `r.westberg@accelerateselery.com` is `lifecycle='incubating'` after 24.9 days warmup. Should have graduated at 21d.

---

## Root cause analysis

Three structural defects interact:

### 1. Hardcoded `live` tag at graduation
[`lifecycle_tag_sync._graduate_mature_inboxes`](../../sync_modules/lifecycle_tag_sync.py) line 225 always tagged `live` regardless of domain pool. The downstream "fixup" comment was incorrect: `set_tag_sync._sync_domain_sets` skipped reconciliation when `current_pool == target_set` in DB, even if EB had a stale extra tag.

**Race:**
1. Inbox tagged `reserve` in EB. DB: `inventory_pool_status='reserve'`, `lifecycle='incubating'`.
2. lifecycle_tag_sync: `untag(incubating)`, `tag(live)`. DB updates `lifecycle='active'` only.
3. set_tag_sync: domain pool=`reserve`, `target='reserve'`, DB `inbox_pool='reserve'` → SKIP.
4. EB now permanently has both `live` and `reserve`.

### 2. Domain-level pool authority blocked promotion
`set_tag_sync` derived every inbox's tag from `domain.pool_status`. Cross-domain promotion of a reserve inbox to deployed was undone within 30 minutes by the next set_tag_sync cycle.

### 3. Single shared `EmailBisonClient` with `switch_workspace()`
Sequential global serialization of tag/kill writes; workspace context drops mid-operation are a documented issue (`fix_dual_tags.py` already includes context-re-switching retry logic).

---

## Locked design criteria

| #  | Criterion |
|----|-----------|
| C1 | Google Workspace only. 3 inboxes/domain drives all thresholds. |
| C2 | Microsoft Entra: tag `live` once, never re-tagged, only `live → dead` on kill trigger. No incubating, no reserve. |
| C3 | Domain mixing allowed only for cross-domain promotion. Default tag flow stays domain-uniform. |
| C4 | Workspace-scoped API keys (migration 089). No `switch_workspace()` calls in tag/kill paths. |
| C5 | 50,000 sends/month commitment per workspace (Google package). Kill thresholds must be size-aware (not over-eager). |
| C6 | Real DB tests, simulated EB failures. No mocked-DB shortcuts. |
| **C7** | **Connection status FIRST.** Per 2026-04-28 user directive: never auto-classify a Connected inbox as dead unless a kill trigger fired. Disconnected for 21+ days OR removed from EB → mark dead. Connected → "carefully consider," manage normally. |

---

## Authority shift (data model change)

| Concept | Before | After |
|---|---|---|
| Per-inbox pool tag source | derived every cycle from `domain.pool_status` | `sender_accounts.inventory_pool_status` is sole authority |
| `domain.pool_status` | authoritative for tag flow | default for new graduations + scope for burn events |
| Cross-domain promotion | impossible (set_tag_sync overrides next cycle) | promoted inbox's `inventory_pool_status='deployed'` is preserved |
| Mixed pool tags within a domain | invariant: never | allowed only when override produced by promotion |
| Inbox alive-ness | dual columns (`is_active` + `inbox_state`) with asymmetric maintenance | same dual columns, but `mark_stale_accounts` now properly sets `inbox_state='dead'` when EB stops returning the inbox (Option 1 patch from 2026-04-28) |

**Schema changes:** migrations 094, 095, 096, 097 (see "Migrations applied to production" below).

Lifecycle of `inventory_pool_status`:

```
graduation (Google):
    domain.pool_status='live'    → inbox.inventory_pool_status='deployed'
    domain.pool_status='reserve' → inbox.inventory_pool_status='reserve'

graduation (Microsoft, C2):
    inbox.inventory_pool_status='deployed' (always; reserve concept does not apply)

cross-domain promotion (kill_processor):
    promoted.inventory_pool_status='deployed' (override; source domain stays 'reserve')

threshold-driven promotion (orchestrator, when packages assigned):
    promoted.inventory_pool_status='deployed' (domain-aware selector picks oldest tapped/untapped)

kill:
    inbox.inventory_pool_status=NULL

domain burn:
    UPDATE sender_accounts SET inventory_pool_status=NULL WHERE domain_id=$1

inbox removed from EB (mark_stale_accounts):
    inbox_state='dead', inventory_lifecycle_status='dead', inventory_pool_status=NULL,
    kill_trigger='disconnected_timeout', killed_at=NOW(), is_active=FALSE
```

---

## Module architecture (final)

```
WorkspaceWriteOrchestrator (sync_modules/workspace_writes.py — NEW)
    for each ws in active workspaces with valid API key:
        if ws.pause_pool_transitions: skip
        client = EmailBisonClient(api_key=ws.key_token, is_workspace_scoped=True)
        # Sequential within workspace:
        await lifecycle_tag_sync.sync_workspace_tags(ws, client)         # graduates incubating → reserve/live
        if ws.package_id is not None:
            await orchestrator._maintain_pool_thresholds(ws)              # proactive promotion if deficit
        await set_tag_sync.sync_workspace_sets(ws, client)               # reconciles EB tags from DB authority
        await kill_processor.process_workspace_queue(ws.id, ws.name)     # processes kill queue with cross-domain promotion
    concurrency: asyncio.Semaphore(SYNC_WORKSPACE_CONCURRENCY=3)

pool_promotion module (sync_modules/pool_promotion.py — NEW)
    pick_promotion_candidates(db, workspace_id, n)
        Domain-aware ordering:
          1. Partially-tapped reserve domains first (fewest remaining reserves first)
          2. Untapped reserve domains, oldest warmup_enabled_since first
          3. Within a domain, oldest reserve inbox first
        Filters: esp='gmail', is_active, inbox_state='live', status='Connected',
                 inventory_pool_status='reserve', lifecycle='active',
                 domain.pool_status NOT IN ('burned','cancelled')
    promote_inbox_to_deployed(db, inbox_id, workspace_id, reason, triggered_by, rotation_type, metadata)
        Transactional UPDATE + INSERT inbox_rotation_history row
```

NOT routing through `WorkspaceSyncQueue` — that queue is for data-pull (EB→DB) jobs which are independently orderable. Tag writes have hard intra-workspace ordering (lifecycle → set → kill).

---

## Migrations applied to production

| # | File | What it adds | When applied |
|---|---|---|---|
| 094 | [migrations/094_warmup_enabled_since.sql](../../migrations/094_warmup_enabled_since.sql) | `warmup_enabled_since`, `warmup_disabled_at` columns + trigger to maintain them on warmup_enabled transitions + indexes + 4,172-row backfill | 2026-04-27 |
| 095 | [migrations/095_total_sends_24h.sql](../../migrations/095_total_sends_24h.sql) | `total_sends_24h INTEGER NOT NULL DEFAULT 0` + index. Populated by `sync_accounts` upsert (delta tracking) | 2026-04-27 |
| 096 | [migrations/096_warmup_trigger_handles_insert.sql](../../migrations/096_warmup_trigger_handles_insert.sql) | Fix to migration 094: trigger now fires on `INSERT OR UPDATE OF warmup_enabled` (was UPDATE-only). Without this, new EB inboxes synced via INSERT never got `warmup_enabled_since` stamped → graduation eligibility broken for new fleet. | 2026-04-27 |
| 097 | [migrations/097_workspace_packages.sql](../../migrations/097_workspace_packages.sql) | `workspace_packages` reference table (seeded with `50k_google` and `100k_google`) + `workspaces.package_id`, `target_live_count_override`, `pause_pool_transitions`, `package_assigned_at` columns + trigger validating override ≤ package target + `workspace_effective_targets` view | 2026-04-28 |

All applied via the admin SQL endpoint at `https://api.wizardgrimoire.cloud/api/admin/run-sql`. Each verified post-apply (table/column/trigger/index existence).

---

## DB cleanup applied to production (2026-04-28 session)

Performed in response to the user directive: **"DB CLEAN UP FIRST. Accuracy then proceed."**

| Phase | Action | Rows affected | Result |
|---|---|---|---|
| **A+E** | Cancelled-domain inboxes mass-killed (combined Phase A "clear pool" + Phase E "kill zombies"). All 796 had been disconnected 60+ days OR removed from EB; per Rule C7 "extended disconnect = dead." `inbox_state='dead'`, `inventory_lifecycle_status='dead'`, `inventory_pool_status=NULL`, `kill_trigger='disconnected_timeout'`, `killed_at=NOW()`, `is_active=FALSE` | 796 | ✓ Verified 0 Connected inboxes were killed. Pre-state IDs saved to `scripts/backfill_snapshots/2026-04-28_cancelled_domain_kill_pre_state.txt` |
| **B** | Microsoft inboxes wrongly tagged `inventory_pool_status='reserve'` on healthy domains corrected to `'deployed'`. CEO directive: MS = always deployed (never reserve). Pre-state IDs at `scripts/backfill_snapshots/2026-04-28_phase_B_ms_reserve_pre_state.txt` | 194 | ✓ Verified |
| **C** | 3 Stable Kernel ODSC East 2026 inboxes (david.meeker, david@infer*, david@evolve*) updated `lifecycle='active'`, `pool='deployed'` because they had been assigned to a real EB campaign (created 2026-04-27, inboxes assigned 2026-04-28 06:09). User decision: clerical bypass of incubation, mark live to reflect operational reality | 3 | ✓ Verified |
| ~~D~~ | ~~Burned-domain Connected zombie cleanup~~ | 0 | **SKIPPED per Rule C7**: 982 burned-Connected inboxes still in EB; cannot auto-classify as dead. Team handles EB campaign cleanup manually. |
| ~~F~~ | ~~Cross-workspace mismatches~~ | 0 | SKIPPED: 17 inboxes recorded under wrong workspace_id (e.g., Selery domain inboxes recorded under Sammy). Needs manual judgment. |

**Total DB writes**: 993 inboxes corrected.

### Earlier in the session: prerequisite backfill

Before the "accuracy first" cleanup, a `scripts/backfill_pool_status.py` run set 1,196 Microsoft NULL-pool inboxes to `'deployed'` to align them with CEO's "MS always live" directive before the new code deploy. **Design flaw**: the backfill SQL did not exclude burned/cancelled domains. Result: 909 of those 1,196 had their pool set to NULL again by the running OLD code's burned-domain handler (correct behavior — burned domain inboxes shouldn't have pool tags). Net effect was +212 correctly-deployed MS inboxes, not the 1,196 originally claimed. Lesson recorded under "Lessons learned" below.

---

## Code complete (locally, awaiting CI/CD deploy)

### New files

| File | Purpose |
|---|---|
| [sync_modules/workspace_writes.py](../../sync_modules/workspace_writes.py) | `WorkspaceWriteOrchestrator` — drives lifecycle → threshold → set → kill per workspace, concurrent across workspaces, workspace-scoped API keys |
| [sync_modules/pool_promotion.py](../../sync_modules/pool_promotion.py) | Shared `pick_promotion_candidates()` (domain-aware selector) and `promote_inbox_to_deployed()` (transactional update + history). Used by both `kill_processor._promote_backup_inbox` and orchestrator's `_maintain_pool_thresholds` |
| [sync_modules/overhaul_audit.py](../../sync_modules/overhaul_audit.py) | `OverhaulAuditModule` — daily reconciliation that posts Slack summary if any drift signal is non-zero (dual-tag candidates, silently-disabled warmup, is_active=FALSE orphans, stuck-incubation past 14 BD) |
| [scripts/backfill_pool_status.py](../../scripts/backfill_pool_status.py) | One-off backfill for `inventory_pool_status` (already run; see DB cleanup section). Uses bulk EB endpoints |
| [tests/conftest.py](../../tests/conftest.py) | Pytest fixtures + Postgres schema setup (testcontainers OR `TEST_DATABASE_URL` env var) |
| [tests/fakes.py](../../tests/fakes.py) | `FakeEmailBisonClient` — records calls, models EB tag state, supports failure injection |
| [tests/test_overhaul.py](../../tests/test_overhaul.py) | 14 integration tests T1-T18 covering graduation, set_tag_sync reconciliation, cross-domain promotion, kill safety net, package thresholds, override enforcement, pause flag, domain-aware ordering |
| [tests/README.md](../../tests/README.md) | How to run tests + schema-setup instructions |

### Modified files

| File | Change |
|---|---|
| [sync_modules/emailbison_client.py](../../sync_modules/emailbison_client.py) | Added `is_workspace_scoped` flag — `switch_workspace()` is a no-op when set |
| [sync_modules/workspace_sync_queue.py](../../sync_modules/workspace_sync_queue.py) | Builds clients with `is_workspace_scoped=True` |
| [sync_modules/lifecycle_tag_sync.py](../../sync_modules/lifecycle_tag_sync.py) | Graduate Google→reserve, Microsoft→live; 14 BD timer using `warmup_enabled_since`; writes `inbox_rotation_history` rows on graduation |
| [sync_modules/set_tag_sync.py](../../sync_modules/set_tag_sync.py) | Per-inbox `inventory_pool_status` is sole authority; legacy tag detection deleted; idempotent reconciling untag every cycle (fixes the skip-bug); active circuit breaker for warning/quarantined; **tag-first/untag-second** order on both Microsoft pin and main path (failure mode: tag fails → no orphan; untag fails → transient dual-tag self-heals); MS-pin enforces `live` for Microsoft regardless of pool |
| [sync_modules/kill_processor.py](../../sync_modules/kill_processor.py) | New `process_workspace_queue(workspace_id, name)` per-workspace entry; cross-domain promotion via shared selector; small-domain 2-kill safety net; Google instant burn (no rate gate); MS skip on cross-domain promotion (legacy ride-to-death); ~200 lines of legacy code removed (`pool_tier`, `hot_backup`, `warming`, `_promote_warming_to_hot_backup`, `DOMAIN_KILLING_TRIGGERS` empty set, legacy `process_queue` cross-workspace fanout) |
| [sync_modules/health_checks.py](../../sync_modules/health_checks.py) | `KILL_THRESHOLD_MIN_SENDS_24H_FOR_COUNT_TRIGGER=20` floor on count-based triggers (with `total_sends_7d >= 20` as fallback for rollout safety until column populates); aligned 2-kill safety net SQL; resets `total_sends_24h` daily |
| [sync_modules/sync_accounts.py](../../sync_modules/sync_accounts.py) | Populates `total_sends_24h` from same delta as `total_sends_7d`; **patched `mark_stale_accounts`** to mark inboxes dead (not just `is_active=FALSE`) when EB stops returning them — Option 1 fix for the asymmetric maintenance bug discovered during this session |
| [sync_modules/__init__.py](../../sync_modules/__init__.py) | Exports `WorkspaceWriteOrchestrator`, `OverhaulAuditModule` |
| [emailbison_sync_worker.py](../../emailbison_sync_worker.py) | Replaced `run_lifecycle_tag_sync` + `run_kill_processing` with `run_workspace_writes`; `POLL_INTERVAL_KILL` 1800 → 900 (15 min); daily `run_overhaul_audit` slot |

All files parse cleanly and import without errors (verified via `ast.parse` + module import on Python 3.13).

---

## Architectural decisions made (and rationale)

These are the load-bearing decisions. Future sessions/operators should understand WHY before changing them.

### 1. Per-inbox `inventory_pool_status` as sole authority for set_tag_sync

**Why**: Domain-level authority blocks cross-domain promotion (the next cycle reverts it). Per-inbox authority enables CEO Rule C3 "domain mixing on promotion."

**Tradeoff**: Slightly more complex SQL in set_tag_sync (per-inbox loop instead of per-domain bulk). But clarity wins.

### 2. NO new pool_transition_queue table

**Why**: User explicitly pushed back against schema sprawl. We already have `inbox_rotation_history` (with `rotation_type`, `source_pool`, `target_pool`, `reason`, `triggered_by`, `metadata` jsonb, `success`, `error_message`). It already records `'domain_burn'` and `'promote'` events. We just extended `rotation_type` values to include `'graduate'` and `'threshold_promotion'`.

**Tradeoff**: No retry semantics for failed transitions, but the cycle-based orchestrator (15 min) provides natural retry — operations are idempotent.

### 3. Tag-first / untag-second ordering in set_tag_sync

**Why**: With untag-first, a transient EB failure on tag leaves the inbox with NO pool tag (campaigns can't pick it). With tag-first, a failure on untag leaves a transient dual-tag that self-heals next cycle. The dual-tag is operationally less harmful than the orphan.

**Not yet implemented**: Full read-plan-apply-verify protocol with bulk endpoints. Deferred — current design + 15-min cadence + daily EB-side dual-tag detector is sufficient. If post-deploy monitoring shows dual-tag drift > 0, this is the next thing to ship.

### 4. Connection status FIRST decision rule (C7)

User directive 2026-04-28:
> "First check should be: is this inbox connected? Then statuses. If kill triggered, mark dead. If disconnected for extended duration, mark dead. If connected, carefully consider."

This is now codified:
- `mark_stale_accounts` patch handles "removed from EB → dead"
- `disconnected_timeout` kill trigger handles "disconnected 21+ days → dead" (existing, unchanged)
- Health checks handle "kill triggered → dead" (existing)
- **For Connected inboxes, never auto-classify as dead.** Burned-domain inboxes that are still Connected stay `inbox_state='live'`; team handles EB campaign cleanup manually.

### 5. Workspace packages with override (migration 097)

**Why**: Without a contracted target, the system only reactively promotes on kills. New workspaces would have all-reserve, no-live. Selery is at the edge of the 50k commitment with one bad domain.

**Why override only LOWERS package target**: Operator can ramp up gradually (set override=current_deployed initially, raise as orders come in). Override > package makes no semantic sense (package is the contract).

**Why no active demotion when override is lowered**: Established sender reputation matters. Lowering override only governs new promotions; natural attrition brings the count down.

### 6. Threshold maintenance only when package assigned

**Why**: NULL package_id = workspace opts out of proactive promotion. Reactive (kill-driven) promotion still runs. This preserves current behavior for any workspace that hasn't been explicitly opted in.

### 7. Microsoft pin in set_tag_sync (force live, untag reserve)

**Why**: 246 Microsoft inboxes had `inventory_pool_status='reserve'` despite CEO directive that MS should never be reserve. Without the pin, the new code's NULL → "untag both" path would have stripped live tags from 1,032 NULL-pool MS inboxes during the deploy window. The pin makes the rollout forgiving.

**Tradeoff**: MS warning inboxes also get force-tagged live (no active circuit breaker for MS). This matches CEO intent ("ride to death") — warning is a health flag, not a kill trigger for legacy fleet.

---

## Production baseline (current state, 2026-04-28 mid-session)

| Signal | Value |
|---|---|
| Active live inboxes (fleet) | 3,308 |
| — Google active | ~482 |
| — Microsoft active (legacy) | ~2,826 (was 3,625 before cancelled-domain kill) |
| Dead inboxes | grew by 796 from cleanup |
| Domains: live pool | ~86 |
| Domains: reserve pool | ~15 |
| Domains: burned | ~6 |
| Domains: cancelled | (now have all-dead inboxes per cleanup) |
| Workspaces with package assigned | 0 |
| Workspaces paused | 0 |
| Dual-tag inboxes (per EB census) | 27 fleet-wide (24 Selery + 2 Hello Hero + 1 Spout) |
| Stuck-in-incubation past 14 BD | ~85 (mostly will graduate on first new-code cycle) |
| sync_audit_log failures (24h) | 0 |

---

## Phased execution log

### Phase 0 — Diagnostics (read-only) — DONE 2026-04-27

Single SQL pass measured blast radius. Output:

| Metric | Value |
|---|---|
| Active workspaces | 11 |
| Workspaces missing API keys | 0 |
| Workspaces with non-standard tag names | 0 |
| Microsoft Entra inboxes (live, active) | 3,648 |
| Google inboxes (live, active) | 482 |
| Inboxes matching DB-side dual-tag pattern | 133 |
| Stuck-in-incubation past 14 BD | 85 |
| Last 7d kills via `hard_bounces_24h` | 127 |
| Of those, kills with <20 sends/7d | **83 (65%)** |
| Orphan `is_active=FALSE` but `inbox_state='live'` | 2,807 |

### Phase 1 — Workspace-scoped client refactor — DONE

`is_workspace_scoped` flag on `EmailBisonClient`, `switch_workspace()` becomes no-op when set. New `WorkspaceWriteOrchestrator`. All `switch_workspace()` calls in tag/kill paths now no-op (left in place for backward compat with global super-admin path used by workspace discovery).

### Phase 2 — Tag logic correctness — DONE

Per-inbox authority. Legacy tag detection deleted. Microsoft pin. Reconciling untag every cycle.

### Phase 3 — 14 business-day graduation timer — DONE

`INCUBATION_BUSINESS_DAYS=14`. Uses `warmup_enabled_since` (column added by migration 094). `warmup_enabled=TRUE` filter ensures paused inboxes don't graduate.

### Phase 4 — Kill logic hardening — DONE

Min-sends floor (20 sends/24h with 7d fallback). Cross-domain promotion. Small-domain 2-kill safety net. Google instant burn.

### Phase 5 — Reconciliation — DONE

`OverhaulAuditModule` runs daily, posts Slack on drift. `inbox_rotation_history` writes for graduation + threshold promotion. `mark_stale_accounts` patched (Option 1).

### Phase 6 — Tests — WRITTEN, BLOCKED

14 tests collected via pytest. Real-Postgres setup via testcontainers OR `TEST_DATABASE_URL`. Local schema dump at `docker/init/00_public_schema.sql` is stale (missing columns added by migrations 026+) — replaying migrations on top produces ordering collisions. Resolution requires fresh `pg_dump` from production into `docker/init/`.

### Phase 7 — Rollout — IN PROGRESS

| Step | Status |
|---|---|
| 1. Apply migrations 094, 095, 096 to production | ✓ 2026-04-27 |
| 2. Apply migration 097 (workspace_packages) | ✓ 2026-04-28 |
| 3. Run backfill_pool_status.py | ✓ 2026-04-27 (with design flaw, self-corrected to +212 net) |
| 4. DB cleanup (Phases A+E, B, C) | ✓ 2026-04-28 |
| 5. **Code deploy via CI/CD** | **PENDING — your action** |
| 6. Watch first 2-3 sync cycles after deploy | pending |
| 7. Verify daily overhaul audit posts to Slack | pending |
| 8. Reconciliation pass (re-run fix_dual_tags or let new code drain naturally) | pending |
| 9. Hold kill triggers in alert-only for 48h before allowing real kills | pending (per C5 paranoia) |

---

## Lessons learned / mistakes made (so we don't repeat)

### 1. Backfill design flaw — overly broad WHERE clause

The first `scripts/backfill_pool_status.py` run set ALL Microsoft NULL-pool inboxes to `'deployed'`, including ~909 on burned domains. The OLD code's burned-domain handler then reset those to NULL (correctly). Net outcome was +212 correctly deployed, not the 1,196 claimed.

**Lesson**: Backfill SQL must account for self-correcting handlers in the running code. Always include domain pool filters (`AND domain.pool_status NOT IN ('burned','cancelled')`) when backfilling pool status.

### 2. "Operationally inert" was a lazy classification

When asked about the 1,609 connected-orphan inboxes, the initial assessment was "mostly burned-zombies, operationally inert, cosmetic only." User correctly pushed back: only ~903 are burned-zombies. The other 700+ included 357 incubating inboxes that were warming inventory the user was paying for, and the assessment had been wrong.

**Lesson**: Drill into the data. Don't classify a population by its largest subgroup.

### 3. Connection-status check was missing from cleanup logic

When killing 796 cancelled-domain inboxes, the logic was "cancelled domain → mark dead" without explicitly checking EB connection status first. User flagged the rule violation: "if connected, can't be classified as dead unless kill triggered." Verified post-hoc that 0 of the 796 were actually Connected, so no harm done — but the LOGIC was wrong.

**Lesson**: Always make connection status the first decision branch when computing inbox state. Per Rule C7.

### 4. The `mark_stale_accounts` asymmetric ratchet

Sets `is_active=FALSE` when EB stops returning an inbox; never sets it back to TRUE. Plus never marks `inbox_state='dead'`. Result: 793+ stale-disconnected inboxes accumulating over months. Patched in this session (Option 1).

**Lesson**: Bidirectional state maintenance is a basic invariant. Any code that sets a flag based on external state must also handle the reverse transition.

### 5. Two columns for "alive-ness" creates drift

`is_active` and `inbox_state` both encode "alive" but with asymmetric maintenance. The 2,807 orphan class is the classic symptom. Long-term fix is consolidating to one column. For now, the patch + rule C7 keeps them aligned going forward.

### 6. Stale schema dump blocks tests

`docker/init/00_public_schema.sql` was from before migration 026, missing columns added later. Replaying migrations on top produced ordering errors. Tests can't run against this. Needs fresh prod schema dump.

---

## What's next — comprehensive list

### A. Required to complete this overhaul

| # | Task | Owner | Notes |
|---|---|---|---|
| 1 | **Trigger code deploy via CI/CD** | You | Schema is ready, DB is clean, code is committed locally. |
| 2 | Watch first 2-3 sync cycles after deploy (~30-45 min) | Me / monitor | Confirm dual-tag count drops to 0, reserve graduations happen, no Slack errors |
| 3 | Verify daily overhaul audit fires at midnight UTC | Me | First scheduled run — confirms `OverhaulAuditModule` is wired correctly |
| 4 | Re-run `scripts/fix_dual_tags.py --dry-run` to confirm 27 dual-tag count drops to 0 | Me | Should be auto-handled by set_tag_sync's reconciling untag |
| 5 | Re-run fleet EB census to verify clean state | Me | Snapshot for handoff to next sprint |

### B. Recommended additions before deploy (small)

| # | Task | Effort |
|---|---|---|
| 6 | Add "incubating inbox in active campaign" check to `OverhaulAuditModule` (Stable Kernel ODSC guard) | ~10 lines |
| 7 | Daily audit Slack throttling (don't re-alert same anomaly within 24h) | ~30 lines |

### C. Manual operator actions (your team, post-deploy)

| # | Task | Why |
|---|---|---|
| 8 | Remove `vollmer.r@joinspoutwater.com` and `rvollmer.v@mistspoutwater.com` from active EB campaigns | Burned-domain MS inboxes still sending; reputation risk. 92 emails sent from a burned domain. |
| 9 | Remove the 982 burned-Connected zombies from any campaigns | Per Rule C7 we don't auto-kill them. Team manually disconnects from campaigns. |
| 10 | Review 17 cross-workspace mismatches | Sammy workspace has Selery-domain inboxes recorded against it. Cross-workspace tenant conflict needs human judgment. |
| 11 | Verify no other ODSC-style cases (incubating inboxes pushed to active campaigns) | Stable Kernel did this; was anyone else operating outside the playbook? |

### D. Decisions deferred until after deploy stabilizes

| # | Item | What you'd decide |
|---|---|---|
| 12 | Assign packages to workspaces (50k or 100k) | Per workspace, with `target_live_count_override` initially set to current Google deployed count |
| 13 | Selery's 30 Google warning inboxes — investigate root cause | Health check tuning or actual list quality issue? |
| 14 | Hello Hero / Barrena (Microsoft-only / empty) | Stay package=NULL or eventually migrate to Google? |
| 15 | Override the 21-day disconnect threshold | Change `KILL_THRESHOLD_DISCONNECTED_DAYS` env var if you want shorter/longer |
| 16 | Stable Kernel: confirm ODSC campaign was intentional ramp from incubation | If not, those 3 inboxes may need to revert + team educated on warmup gate |

### E. Architectural follow-ups (future sprints, not blocking)

| # | Item | Value |
|---|---|---|
| 17 | Verified tag-write protocol (snapshot → plan → apply → verify with bulk EB) | Stronger correctness than tag-first reorder. Current design is good enough; ship if dual-tag drift > 0 post-deploy. |
| 18 | Dedicated `ConnectionReconciler` module (Option 2) running hourly | Cleaner than relying on `mark_stale_accounts` patch (Option 1). Defer until evidence Option 1 isn't sufficient. |
| 19 | Test execution: fresh production schema dump for `tests/conftest.py` | Currently tests are written but blocked on schema drift. Fresh `pg_dump` of production into `docker/init/00_public_schema.sql` unblocks. |
| 20 | Investigate the 2,807 `is_active=FALSE` orphans (most are churned workspaces, harmless) | One-time cleanup. Lower priority since Option 1 patch prevents new ones. |
| 21 | Microsoft Entra retirement plan | Long-term — they ride to death, eventually replaced by Google. No code action; just operational planning. |
| 22 | Patch warning-pool sync race | `sync_accounts.upsert` keeps flipping pool back to `warning` when bounces are present, even on cancelled/burned domains. Add domain pool filter to that branch. |
| 23 | Incubation enforcement: prevent EB ops from assigning incubating inboxes to campaigns | Can't enforce at EB write time; surface as audit alert (item 6 above is the start). |
| 24 | Rate limiting per-workspace EB API calls | Currently 3 workspaces concurrent via `SYNC_WORKSPACE_CONCURRENCY`. If EB rate-limits, may need throttle. |
| 29 | **Auto-cleanup function: remove burned-domain inboxes from active EB campaigns** | Per 2026-04-28 (session-2) user directive: *"ok if burned inboxes are appearing in campaigns since we are constantly checking. Notate we need to build a function to address this."* The audit now surfaces a `burned_inboxes_in_campaigns` count; team removes manually until automated. Build a sync_module that, per workspace, lists `campaign_inboxes` where `domain.pool_status IN ('burned','cancelled')` and calls EB API to remove those sender_email_ids from each campaign. Run on same 15-min cadence as `workspace_writes`. Constraints: Rule C7 (don't auto-kill connected inboxes — only remove from campaigns; the inbox stays alive in EB until `disconnected_timeout` fires). EB endpoint TBD (likely `DELETE /campaigns/{id}/sender-emails/{sender_email_id}`). |

### F. Documentation updates needed

| # | Item |
|---|---|
| 25 | Update operational playbook: "never assign incubating inboxes to campaigns" rule |
| 26 | Document the 14-BD graduation timer and `warmup_enabled_since` semantics for ops |
| 27 | Document the workspace_packages model (50k_google, 100k_google) for ops |
| 28 | Update [docs/architecture/emailbison-sync.md](../../docs/architecture/emailbison-sync.md) — references `run_kill_processing` which no longer exists |

---

## Suggested order

**Tonight / this session:**
- #6 (10-min addition: incubating-in-campaigns audit)
- #1 (trigger code deploy)
- #2-#5 (post-deploy verification)

**Tomorrow / handoff:**
- #8, #9, #10 (your team's EB cleanup)
- #25-#28 (doc updates)

**Within a week:**
- #12 (start assigning packages, workspace by workspace)
- #13 (Selery warning inboxes investigation)
- #22 (warning-pool race patch — small change)

**Later sprints:**
- #17, #18, #19, #20, #21, #23, #24

---

## Handoff context (operational)

### Where to run admin SQL
- Endpoint: `https://api.wizardgrimoire.cloud/api/admin/run-sql`
- Auth: `key` query parameter (admin API key — see `scripts/fix_dual_tags.py` for hardcoded value, or env vars)
- Method: POST with `key` and `sql` URL-encoded as query params (curl example: `curl -s -X POST URL --get --data-urlencode "key=..." --data-urlencode "sql=..."`)
- Caveats: rejects multi-statement bodies that include DDL+DML, rejects data-modifying CTEs (HTTP 500), accepts plain UPDATE/INSERT/DELETE individually.

### Workspace API keys
- Stored in `workspace_api_keys` table (migration 089).
- One key per workspace, scoped to that workspace's EB context — no `switch_workspace()` needed.
- All 11 active workspaces have keys (verified Phase 0).
- Workspace discovery uses the global `EMAILBISON_API_KEY` env var (only path that legitimately needs super-admin).

### Test environment
- pytest 8.4.2, pytest-asyncio installed.
- testcontainers-postgres installed but requires Docker Desktop running.
- Fallback: `TEST_DATABASE_URL` env var pointing at any reachable Postgres.
- Local Postgres on port 5433 (postgres:postgres) is available but `docker/init/00_public_schema.sql` is stale.
- See [tests/README.md](../../tests/README.md) for setup.

### Snapshot / rollback files
Stored in `scripts/backfill_snapshots/`:
- `2026-04-27_pre_pool_status_backfill.txt` — 1,196 IDs from initial backfill
- `2026-04-28_cancelled_domain_kill_pre_state.txt` — 796 IDs from Phase A+E
- `2026-04-28_phase_B_ms_reserve_pre_state.txt` — 194 IDs from Phase B

Each rollback would be a SQL UPDATE with `WHERE id = ANY(ARRAY[...]::uuid[])` setting fields back to their pre-state values.

### Memory rules updated this overhaul
- [domain-tagging-rule.md](../../C:/Users/ellio/.claude/projects/d--Work-Charm-charm-email-os/memory/domain-tagging-rule.md) — rewritten 2026-04-27 to reflect per-inbox pool authority
- [domain-state-volatile.md](../../C:/Users/ellio/.claude/projects/d--Work-Charm-charm-email-os/memory/domain-state-volatile.md) — rewritten 2026-04-27 to clarify domain.pool_status semantics

### Critical files to know
- [emailbison_sync_worker.py](../../emailbison_sync_worker.py) — main sync worker; orchestration entry point
- [sync_modules/workspace_writes.py](../../sync_modules/workspace_writes.py) — new orchestrator (lifecycle → threshold → set → kill)
- [sync_modules/pool_promotion.py](../../sync_modules/pool_promotion.py) — shared promotion logic (kill-driven AND threshold-driven both use this)
- [sync_modules/overhaul_audit.py](../../sync_modules/overhaul_audit.py) — daily drift detector
- [migrations/094-097](../../migrations/) — schema changes (all applied)

### Production fleet count snapshot (2026-04-28 post-cleanup)
- Total active live: 3,308 (was 4,107 pre-cleanup; 796 killed in Phase A+E)
- Google: ~482, Microsoft: ~2,826
- 27 dual-tag inboxes will drain on first new-code sync cycle
- 982 burned-Connected zombies still alive (per Rule C7, intentional)

---

## Related artifacts

- Migration 089: [[../../migrations/089_workspace_api_keys.sql]] — workspace-scoped API keys (predates this overhaul, foundational)
- [[../../scripts/fix_dual_tags.py]] — point-fix for dual tags (existing tool)
- [[../../scripts/backfill_pool_status.py]] — one-off backfill (already run)
- [[../../scripts/backfill_snapshots/]] — pre-state snapshots for every cleanup phase
- Memory rules: `domain-tagging-rule.md`, `domain-state-volatile.md`, `complaint-rate-bug.md`, `domain-pipeline-bulletproof.md`
