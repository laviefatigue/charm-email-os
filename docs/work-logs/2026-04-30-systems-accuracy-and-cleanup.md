---
title: 2026-04-30 — Systems Accuracy, Connection State Machine, and Decomposition Planning
date: 2026-04-30
status: in-progress
---

# Session Log — 2026-04-30

## Context

Started the day intending to "fix Sammy" (suspected dead lifecycle_tag_sync). Cascaded through five interconnected discoveries that reshape the immediate roadmap:

1. The cross-workspace pollution audit (from 2026-04-29) needed a prevention firewall — domain pattern matching against `clients.domain_pattern`.
2. Sammy's lifecycle_tag_sync was NOT dead — it was running every 30 min processing 0 records (because Sammy has no incubating inboxes; the actual issue was the 22 SPUI live zombies + 5 SKMR reserve foreign).
3. Charm's EB UI showed 127 inboxes with `flagged_disconnected_timeout` tag while currently `Connected` and sending — the system marked them dead 6 weeks ago, they reconnected, no resurrection path exists.
4. Fleet-wide: ~1,200 zombies across 10 workspaces, mostly the same pattern — operational disconnect was wrongly treated as terminal reputation kill.
5. The system has been silently inaccurate for months. We do not have proven accuracy of the data flowing through the state machine. **Automated actions on system outputs require accuracy validation first.**

## Decisions locked in

### D-1. Connection ≠ Kill
Connection status (`status`, `disconnected_at`) is monitoring telemetry. Kill state (`inbox_state='dead'`) is reputation-driven only. They never share authority over a row. The 21-day-disconnect-equals-dead rule is REMOVED.

Plan: [docs/plans/connection-state-machine.md](../plans/connection-state-machine.md)

### D-2. No automated EB removal — ever
The system tags inboxes in EB and categorizes them in our DB. EB removal is operator-only, manual. Hypertide subscription cancellation is operator-only. **No script will ever delete from EB.**

Locked in §0 and §7 of the connection-state-machine plan.

### D-3. Observation before automation
Before any automated action ships that depends on system data being correct, accuracy validation gates must pass:

| Gate | Threshold |
|------|-----------|
| Connection-status mirror (DB ↔ EB) | ≥99% |
| Disconnect timestamp coverage | ≥95% |
| Membership consistency | ≥98% |
| Pool-tag drift | ≤1% |

Audit script: [scripts/audit_system_accuracy.py](../../scripts/audit_system_accuracy.py)

### D-4. Cross-workspace pollution firewall — keyword-based, single field per client
Each client gets one `clients.domain_pattern` value — comma-separated keywords. Match logic is substring containment against the email's domain. Charm exception: multi-keyword (`charm,growthgroupusa,alldealsgroup,globaloutreachclub,urosaf-bio`).

Plan: [docs/plans/cross-workspace-integrity-firewall.md](../plans/cross-workspace-integrity-firewall.md)

### D-5. EmailBison-sync decomposition — start with incubation-watcher, then decide
Modularize emailbison-sync into focused services. Six total, but ship one first (incubation-watcher) and validate the pattern before committing the rest.

Plan: [docs/plans/emailbison-sync-decomposition.md](../plans/emailbison-sync-decomposition.md)

## Code changes today

### sync_modules/lifecycle_tag_sync.py — silent-failure patch (committed earlier)
Wrapped `tag_inbox` in try/except for the graduation path. EB 404 (workspace orphan) → log `[ORPHAN]`, skip via `continue`, audit error with explicit reason. Other errors re-raise (transient retry).

### sync_modules/health_checks.py — Phase 1 (this session)
- Removed `disconnected_timeout` from `KILL_THRESHOLDS` dict (preserved enum value for historical entries)
- Removed the trigger detection block at lines 509-521
- Replaced both with deprecation comments pointing to the connection-state-machine plan

Pure deletion. Stops new zombies from being created. Does not touch existing zombie rows.

## Audit deliverables (read-only, this session)

### scripts/audit_system_accuracy.py
Read-only fleet audit comparing DB to EB across four dimensions (connection status, disconnect timestamp, membership, pool tag). Outputs JSON snapshot to `docs/audits/2026-04-30-system-accuracy-snapshot.json`. Exit code 0 if all gates pass, 1 if any fail.

Run: `py scripts/audit_system_accuracy.py [--workspace <name>]`

### scripts/generate_zombie_review_csv.py
Read-only zombie review CSV per workspace. Captures EB current state, reputation history, system heuristic for "looks safe to restore." `operator_decision` and `operator_notes` columns left blank for operator fill-in.

Run: `py scripts/generate_zombie_review_csv.py --workspace Charm`

### Outputs
| File | Purpose |
|------|---------|
| `docs/audits/2026-04-30-system-accuracy-snapshot.json` | Per-workspace accuracy gates with sample mismatches |
| `docs/audits/2026-04-30-zombie-review-charm.csv` | Operator review queue for Charm's 127 zombies |
| (additional CSVs as `--workspace all` or per-workspace runs) | One per workspace |

## Plans authored

| Plan | Status | Lines |
|------|--------|------:|
| [cross-workspace-integrity-firewall.md](../plans/cross-workspace-integrity-firewall.md) | PROPOSED — pending operator decisions §12 | ~600 |
| [emailbison-sync-decomposition.md](../plans/emailbison-sync-decomposition.md) | PROPOSED — minimum-viable scope (incubation-watcher first) recommended | ~600 |
| [connection-state-machine.md](../plans/connection-state-machine.md) | PROPOSED — Phase 1 patched today, rest gated on accuracy | ~400 |

All three plans cross-reference each other. Each has explicit critical-pushback sections (§5 in firewall, §14 in decomposition, §12 in connection state).

## What's gated on what

```
Phase 1 (disconnected_timeout removed)
    ├── ships today, no gates
    │
    └── stops new zombies. Existing zombies untouched.

Accuracy validation gates (4 thresholds)
    ├── must pass before:
    │     - Phase 3+4 of connection-state plan (auto EB tag application,
    │       drop connection filter from promotion)
    │     - Phase 6 of firewall plan (auto-quarantine backfill writes)
    │     - Phase 1 of decomposition (validate baseline data flows)
    │
    └── operator-driven zombie restoration is independent of these gates
        — manual per-row decision based on the CSV preview.

Zombie restoration (~1,200 fleet-wide)
    ├── operator-only, manual SQL per row, smallest workspaces first
    ├── Spout 641 BLOCKED — needs root-cause investigation first
    └── Charm 154 is the natural pilot (visible in operator's EB UI today)

Decomposition (apps/incubation-watcher first)
    ├── starts AFTER:
    │     - Sammy patch validated in production for ≥7 days
    │     - Accuracy audit shows lifecycle data is reliable
    │
    └── then 1.5 days dev + 7 days shadow validation per service
```

## Open issues — explicit non-goals for today

These were considered and explicitly deferred:

| Item | Why deferred |
|------|--------------|
| `inbox_audits` overhaul (per-workspace, integrity sections) | User confirmed: audit is "dressing", priority is the underlying state machine |
| Hypertide upstream provisioning bug investigation | Not blocking; firewall handles consequences regardless |
| Auto-decommission at 20-day disconnect | Operator-only per D-2 |
| Drop connection filter from pool promotion | Unsafe pre-accuracy-validation |
| Bulk zombie restoration script | Unsafe pre-accuracy-validation |
| ADR-008 step 2 (collapse pool + lifecycle into single column) | Next sprint, post-firewall |

## Critical assessment of today's work

Three honest concerns about what shipped:

1. **The Phase 1 patch removes a kill trigger that was firing on REAL data**. Some inboxes that hit the 21-day threshold may have actually been abandoned (employee left, project ended). With the trigger gone, those inboxes stay alive in DB indefinitely. The notification ladder (Phase 2, not yet built) is supposed to surface them; until that ships, abandoned inboxes are tracked only via existing Slack alerts in `slack_audit.py` (24h/48h disconnect threshold). That's adequate but not ideal.

2. **The accuracy audit is a snapshot, not continuous**. Running it once today gives us a baseline. Drift between audits is invisible. A continuous audit (hourly? daily?) is needed to catch regression. Not in scope today.

3. **Three plan docs total ~1,600 lines for work that hasn't shipped**. Risk of plan-paralysis. The mitigation: each plan has an explicit "minimum viable scope" — for connection-state it's Phase 1 only (already shipped); for decomposition it's incubation-watcher only; for firewall it's the schema + populate + manual operator backfill. The full plans are aspirational; the MVPs are concrete.

## SPUI and Spout investigation (added end-of-session)

### SPUI — minor sync timing gap, mostly cosmetic residue

| Symptom | Detail | Severity |
|---------|--------|----------|
| 22 EB-only senders not in DB | Recent IDs 9866-9875+ (consecutive — single Hypertide batch) | Sync timing — accounts ran 21× in last 24h, last at 18:26 UTC. Likely caught up after audit ran. Verify by re-running audit. |
| 104 DB-only on `tryspui.com` | All `is_active=FALSE`, mostly state=live but inactive | Historical — `tryspui.com` is a retired domain. EB-side already cleaned by operator. DB rows are residue. Cosmetic only. |

**No urgent action.** Re-running the accuracy audit should show fewer EB-only senders as sync catches up.

### Spout — two distinct issues

#### Issue A: 287 DB-only rows (historical kill batch, NOT a current bug)

286 dead rows on retired domains (`usespoutwater`, `choosespoutwater`, `mistspoutwater`, etc.) — single 5-day kill event 2026-02-14 → 2026-02-18. Distribution:

| kill_trigger | Count |
|--------------|------:|
| `fresh_inbox_unknown` | 105 |
| `fresh_inbox_blocked` | 87 |
| `spam_complaint` | 59 |
| `hard_bounces_24h` | 35 |

These are LEGITIMATE reputation kills that fired correctly. Operator removed them from EB workspace. DB rows are residue. **Cosmetic only.**

#### Issue B: 10 pool-tag drift rows (NEW BUG SURFACED — kill_processor silent failure)

Pattern: DB says `inbox_state='dead', pool=NULL, kill_trigger=hard_blocked_24h|spam_complaint`. EB has the **pool tag still applied** (`live` or `reserve`) PLUS the `flagged_*` tag. Killed in March (Mar 1 / 13 / 18 / 26).

Sample:
```
reuben@trustspoutwater.com
  DB: dead, pool=NULL, kill_trigger=hard_blocked_24h, killed=2026-03-13
  EB tags: ['google', 'flagged_provider_block_gmail', 'live']    ← 'live' is the bug
```

**Root cause**: `kill_processor.py:444-459` strips pool tags but catches `EmailBisonAPIError` with bare `pass`:

```python
for pool_tag_name in ('live', 'reserve'):
    ...
    if pool_tag_id:
        try:
            await self.client.untag_inbox(account_id=eb_account_id, tag_id=pool_tag_id)
        except EmailBisonAPIError:
            pass  # Tag may not be present — that's the goal.
```

This conflates two outcomes:
- **404** — tag wasn't applied, untag returns "not found" — intended behavior, fine to swallow
- **5xx / transient** — EB had a hiccup, untag actually failed — should retry

Result: 10 rows where pool tag stayed applied because the strip failed transiently and was silently ignored. No retry path exists; `kill_queue.status` is set to `flagged` (success) regardless of pool-strip outcome.

**Same bug class as the Sammy `lifecycle_tag_sync` patch shipped earlier today** (commit `94fd0fa`). The fix is analogous — distinguish 404 from transient errors in the untag call, and either retry or surface as audit error.

#### Spout's 641 disconnected_timeout zombies (separate, not investigated this session)

Per accuracy audit, 641 rows where `inbox_state='dead' AND kill_trigger='disconnected_timeout' AND status='Connected'`. These are the zombie pattern that motivated the entire connection-state-machine plan today. Spout's ratio (98% of dead pool) is the highest in the fleet.

**Recommendation**: investigate WHY Spout had a fleet-wide disconnect-then-reconnect pattern (mass OAuth wipe? sync regression?) before any restoration. Block bulk operator restoration on Spout until cause is understood. Generate `scripts/generate_zombie_review_csv.py --workspace Spout` first, then root-cause from the killed_at distribution before any DB action.

## Documentation updated

Beyond the plan docs and work log written earlier this session:

| File | Change |
|------|--------|
| [docs/concepts/kill-triggers.md](../concepts/kill-triggers.md) | Added 2026-04-30 banner. Removed `disconnected_timeout` row from both ESP-trigger tables. Added "Removed kill triggers" section linking to the connection-state-machine plan. |
| [production/coolify/services.md](../../production/coolify/services.md) | Updated `emailbison-sync` service section: ENABLE_KILL_PROCESSING flipped to `true` (since 2026-04-13). Added Connection State section (ADR-009 reference). Added Silent-Failure Hardening section. Added Accuracy Audits section pointing to the new scripts. |
| [docs/adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md](../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md) | NEW — formalizes the connection ≠ kill decision. Lists alternatives considered, consequences, implementation status. |

## Next session

In priority order:

1. Ship Phase 1 patch (commit + deploy charm-api + emailbison-sync). Verify lifecycle_tag_sync no longer queues kills with trigger=disconnected_timeout.
2. Operator review of Charm zombie CSV — establishes the per-row decision pattern before any other workspace.
3. Investigate Spout's 641-zombie anomaly. Single-event vs trickle? Trace `killed_at` distribution.
4. Run the accuracy audit fleet-wide. Read the gate results. Decide if/when Phase 2-4 of connection-state-machine can ship.
5. Begin `apps/incubation-watcher/` extraction per decomposition plan. Pure structural move; existing `lifecycle_tag_sync` keeps running in `emailbison-sync` until shadow validation completes.

## Files modified or added this session

```
sync_modules/lifecycle_tag_sync.py      M  (orphan-skip on tag_inbox 404)
sync_modules/health_checks.py           M  (Phase 1: disconnected_timeout kill removed)

docs/plans/cross-workspace-integrity-firewall.md     A
docs/plans/emailbison-sync-decomposition.md          A
docs/plans/connection-state-machine.md               A

scripts/audit_system_accuracy.py                     A
scripts/generate_zombie_review_csv.py                A

docs/work-logs/2026-04-30-systems-accuracy-and-cleanup.md   A  (this file)

docs/audits/2026-04-30-system-accuracy-snapshot.json        A  (generated by audit script)
docs/audits/2026-04-30-zombie-review-charm.csv              A  (generated by zombie CSV script)
```

All commits pending — will be batched as a single coherent PR after audit scripts complete and produce their outputs.
