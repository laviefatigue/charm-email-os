---
title: "ADR-008 (PROPOSED): Collapse inventory_lifecycle_status + inventory_pool_status into a single `inbox_status` column"
created: 2026-04-29
updated: 2026-04-29
tags: [adr, status/proposed, schema, simplification, planning]
status: proposed
---

# ADR-008 (PROPOSED): Collapse `inventory_lifecycle_status` + `inventory_pool_status` into a single `inbox_status` column

## Status

**PROPOSED — pending planned execution next week (target ~2026-05-05/06).**

This ADR captures the model as discussed during the 2026-04-29 session-3 architecture review. Implementation deferred to a dedicated sprint to avoid compounding bugs from the recent ADR-006 + ADR-007 + mig 099 stack of changes still settling.

## Context

The 2026-04-29 fleet audit caught 3 inboxes (Stable Kernel ODSC: `david@evolvestablekernel.com`, `david@inferstablekernel.com`, `david@tunestablekernel.com`) stuck in `lifecycle='active' + pool=NULL` operational limbo:

- Migration 098's "restore from domain default" branch had a hole: when domain pool was `unassigned`, the CASE fell through to NULL.
- ADR-007 had removed the `'warning'` auto-recovery path, so once at NULL, no path home.
- Sub-floor sends → no kill could fire either.

Result: the inbox was alive in DB, no pool tag in EB, no kill, no auto-promotion. Indefinite limbo until a manual UPDATE.

User raised two structural questions in response:

1. **Why two columns** (`inventory_lifecycle_status` + `inventory_pool_status`) when they encode overlapping facts?
2. **Why two value vocabularies** (`'live'` for domain pool vs `'deployed'` for inbox pool) when they mean the same thing?

The follow-up answer to "what's the value of the dual encoding": **historical drift**, not architectural justification. Both columns evolved over time — domain-level pool came first (when pool was a domain-only concept), per-inbox `inventory_pool_status` came later (when cross-domain promotion required per-inbox authority), and `inventory_lifecycle_status` was always there as a maturity tracker. The two-column model encodes orthogonal-in-theory facts (graduation status + pool membership) but in practice nearly every state is one of 4 combinations:

| `lifecycle` | `pool` | What it means |
|---|---|---|
| `incubating` | NULL | Warming up |
| `active` | `reserve` | Graduated, on bench |
| `active` | `deployed` | Graduated, sending |
| `dead` | NULL | Killed |

Plus one operational-limbo case (the bug class):
| `active` | NULL | Stuck (rare/buggy) |

If we make the linear-lifecycle assumption that "active without a pool is undefined and shouldn't exist," the dual-column encoding is providing zero information that a single column couldn't. Worse, it allows mismatched states (the limbo bug above).

## Decision

Collapse `inventory_lifecycle_status` and `inventory_pool_status` into a single `inbox_status` column with 4 values:

```
inbox_status:  incubating → reserve ⇄ live → dead
                          ↑ ↓
                       (promote/demote by kill-driven OR threshold-driven path)
```

### Status definitions

| Value | Meaning | Set when |
|---|---|---|
| `incubating` | Warming up; not yet ready for campaigns | New inbox synced from EB; warmup_enabled=TRUE; warmup_enabled_since not yet 14 BD elapsed |
| `reserve` | Graduated; on the bench, available for promotion | (a) Graduation completes 14 BD warmup, OR (b) promoted live inbox demoted (e.g., bounce signals subside on a non-deployed inbox), OR (c) self-heal from active-but-NULL operational state |
| `live` | Graduated; deployed in active EB campaigns | (a) Graduation for Microsoft (legacy ride-to-death pin), OR (b) cross-domain promotion (kill_processor on a kill, picks next reserve), OR (c) threshold-driven promotion (orchestrator fills package live target) |
| `dead` | Cannot send. Terminal. | (a) Kill trigger fired (reputation damage — spam_complaint, hard_blocked, hard_unknown, hard_bounces, rate triggers), OR (b) Domain burned (entire domain reputation-toxic, all inboxes dead-cascade), OR (c) Disconnected for 21+ days (`disconnected_timeout` — assume Hypertide-cancelled, clerically lingering) |

### Refined definition of `dead` (per user direction 2026-04-29)

> "Dead inbox status indicates to us that we can no longer send. The team will independently cancel with Hypertide on a per-domain basis."

`dead` is the operational state — "we can't use this inbox" — regardless of cause. Three causes, one terminal state:

1. **Kill trigger** — we explicitly killed it (reputation reasons, ESP-aware thresholds per ADR-007)
2. **Domain burn** — the inbox's domain is `pool_status='burned'`. The whole domain is reputation-toxic; all its inboxes cascade to dead.
3. **Disconnected timeout** — EB has shown it disconnected for 21+ days; we assume Hypertide cancelled the inbox at the upstream provider. Clerically the EB row may still exist but operationally the inbox is gone.

This is a refinement of CEO Rule C7 ("Connected inboxes can't be auto-classified as dead"):

> Connected ≠ dead **unless** a structural reason exists (kill trigger, domain burn, or 21+ day disconnect).

The "domain burn cascades to inbox dead" branch is the new behavior that ADR-007 didn't include. Previously, ~1,019 burned-domain Connected inboxes sat at `lifecycle=active + pool=NULL` and the team manually removed them from EB campaigns. Under ADR-008, they'd all flip to `inbox_status='dead'` automatically. **This is a deliberate behavior change — see Migration section.**

### Connection status remains separate (continuous binary EB-derived signal)

`sender_accounts.status` (EB-derived, values `Connected` / `Not connected`) and `disconnected_at` timestamp remain unchanged. They track:

- "Is EB authenticated to the inbox right now?"
- "How long has it been disconnected?"

These are independent of `inbox_status`. Connection state is a CONDITION that may TRIGGER a transition (via the `disconnected_timeout` kill trigger), but it doesn't define the inbox_status itself.

User clarification:

> "Connection status represents we are still paying for that inbox. So connection should be a binary true/false continuous check. We want to know when inboxes have been disconnected for an extended period of time. Since EmailBison auto-checks and will retry, we need to know if that disconnect stays longer than 24h. If it exceeds 20 days, we can assume we are no longer paying for it."

The 24h threshold is operational visibility (Slack alert / dashboard signal) — not status-changing. The 21-day threshold (existing `KILL_THRESHOLD_DISCONNECTED_DAYS`) IS status-changing — fires `disconnected_timeout` kill trigger → `inbox_status='dead'`.

### Hypertide flow stays operational, separate from inbox_status

> "EmailBison is just the sequencer so we will manually audit what needs to happen."

Hypertide is the upstream provider where inboxes are physically provisioned. EmailBison is the sequencer/sender. Our system tracks the EmailBison-side state.

Operational flow when an inbox transitions to `dead`:
1. `inbox_status='dead'` set (by trigger / burn cascade / disconnect timeout)
2. `set_tag_sync` removes pool tags in EB, optionally adds `flagged_*` tag
3. Auto-cleanup function (still TBD — currently item #29 in plan doc) removes the inbox from active EB campaigns
4. **Team independently audits** at Hypertide on a per-domain basis — decides whether to cancel the underlying provisioning
5. If team cancels at Hypertide → `domain.pool_status='cancelled'` records the audit trail (separate from inbox_status)

`domain.pool_status='cancelled'` and `inbox_status='dead'` track different facts:
- `inbox_status='dead'` — we won't send through this inbox
- `domain.pool_status='cancelled'` — we cancelled the Hypertide order for this domain (no longer paying)

A burned domain may have `domain.pool_status='burned'` AND eventually `'cancelled'` after team audit. All inboxes are `inbox_status='dead'` throughout.

### Domain-level `pool_status` — kept as-is, different scope

`domains.pool_status` continues to track domain lifecycle:

| Value | Meaning |
|---|---|
| `live` | Default destination for Google graduations on this domain |
| `reserve` | Default destination for Google graduations on this domain (bench) |
| `burned` | Reputation-killed; all inboxes cascade to `inbox_status='dead'` |
| `cancelled` | Hypertide order cancelled; clerical record of upstream cancellation |
| `unassigned` | Pre-allocation default (need to be assigned to live or reserve before graduations land cleanly) |

The user noted: "I can understand tracking at the domain level where it might matter to track that information like if a domain is fully deployed (all inboxes live) or in reserve."

That's the role of `domain.pool_status` going forward. It's NOT a per-inbox tag authority. Per-inbox state is `inbox_status`.

### EB tag mapping (no change to tag names)

```
inbox_status='incubating'     →  EB tag 'incubating', no pool tag
inbox_status='reserve'        →  EB tag 'reserve', no 'live'
inbox_status='live'           →  EB tag 'live', no 'reserve'
inbox_status='dead'           →  no pool tag, optional 'flagged_*' kill trigger tag
```

Plus the burn-domain gate in set_tag_sync (regardless of inbox_status):

```
if domain.pool_status IN ('burned', 'cancelled'):
    untag both 'live' and 'reserve'
elif inbox_status == 'live':
    tag 'live', untag 'reserve'
elif inbox_status == 'reserve':
    tag 'reserve', untag 'live'
elif inbox_status == 'incubating':
    tag 'incubating' (managed by lifecycle_tag_sync)
elif inbox_status == 'dead':
    untag 'live', untag 'reserve' (and ensure 'flagged_*' tag if not already)
```

The Microsoft pin (always tag 'live' regardless of pool) becomes simpler under ADR-008: Microsoft inboxes go from `incubating` → `live` directly at graduation. The pin is then redundant — `inbox_status='live'` IS the source of truth.

## Consequences

### Positive

- **One column, one source of truth.** Eliminates the lifecycle/pool mismatch bug class entirely. Migration 098's hole and the 3 ODSC stuck cases couldn't recur — there's no NULL pool to fall through to.
- **Dead is operationally meaningful.** "Can we send?" → check one column. No more cross-referencing 3 columns.
- **Burn cascade resolves automatically.** All burned-domain inboxes are `dead`. Auto-cleanup of `burned_inboxes_in_campaigns` (1,019 today) becomes "remove all dead inboxes from EB campaigns" — falls out of the model.
- **Audit metric simplification.** `flagged_but_alive_count`, `stuck_active_null_pool` — derivable from inbox_status checks.
- **Aligns with operator mental model.** Operators talk about "live inboxes" and "reserve inboxes" — column matches their language.
- **Aligns with EB tag names.** `live` (column) = `live` (EB tag). Less translation overhead.
- **Eliminates the `'live'` vs `'deployed'` value-name divergence.** Both column and EB tag use `live`.

### Negative

- **Substantial migration.** Touches every module that reads/writes lifecycle or pool status:
  - `set_tag_sync.py`, `lifecycle_tag_sync.py`, `kill_processor.py`, `sync_accounts.py`, `health_checks.py`, `overhaul_audit.py`, `pool_promotion.py`, `workspace_writes.py`, `daily_snapshot.py`
  - All audit queries and reporting views
  - All scripts that filter on these columns (~10 in `scripts/`)
  - All tests that set/read these columns
  - All docs (4-5 files reference the dual-column model)
- **Behavior change for burned-domain inboxes.** ~1,019 currently-Connected burned-domain inboxes flip from `lifecycle=active + pool=NULL` to `inbox_status='dead'` in one migration. Need:
  - Pre-state snapshot (rollback path)
  - Slack alert pre + post
  - Team awareness — they'll see new dead inboxes in their dashboard and may misinterpret as "system killed extra inboxes"
  - The auto-cleanup function (item #29) becomes more important — the dead inboxes need to be removed from EB campaigns
- **Loss of granularity in some queries.** With 2 columns we could ask "is this inbox graduated AND in reserve?" With 1 column, "graduated AND reserve" = `inbox_status='reserve'` (graduated is implied). Some legacy reporting may need rewriting.
- **Migration cost ~2 days focused work.** Higher than Option A but lower than the original ADR-006 overhaul.

### What does NOT change

- `inbox_state` column (`live` / `dead` from EB sync) — kept separate, EB-sourced
- `sender_accounts.status` (Connected / Not connected from EB) — kept separate, EB-sourced
- `disconnected_at` timestamp — kept separate
- `domains.pool_status` — kept separate (domain lifecycle scope, distinct concern)
- EB tag names (`live`, `reserve`, `incubating`, `flagged_*`) — unchanged
- Kill trigger thresholds (ADR-007 ESP-aware) — unchanged
- Workspace package model (mig 097) — unchanged
- Workspace-scoped API keys (mig 089) — unchanged

## Migration plan (high-level)

To be detailed and tested in the dedicated sprint. Sketch only:

### Phase 1 — Schema preparation

1. Add `inbox_status` column to `sender_accounts` (nullable initially)
2. Backfill: derive `inbox_status` from current `inventory_lifecycle_status` + `inventory_pool_status`:
   ```
   if inventory_lifecycle_status = 'incubating': inbox_status = 'incubating'
   elif inventory_lifecycle_status = 'dead': inbox_status = 'dead'
   elif inventory_lifecycle_status = 'active' AND inventory_pool_status = 'reserve': inbox_status = 'reserve'
   elif inventory_lifecycle_status = 'active' AND inventory_pool_status = 'deployed': inbox_status = 'live'
   elif inventory_lifecycle_status = 'active' AND inventory_pool_status IS NULL:
     # the limbo state — backfill to reserve (default for graduated inboxes)
     # (already self-healed by current sync_accounts code)
     inbox_status = 'reserve'
   ```
3. Apply burn cascade: for any inbox where `domain.pool_status IN ('burned', 'cancelled')` AND `inbox_status != 'dead'`, set `inbox_status='dead'` (with kill_trigger='domain_burn_cascade' for audit trail)
4. NOT NULL constraint after backfill verified

### Phase 2 — Code migration (parallel writes)

1. Update all writers to set BOTH old columns AND `inbox_status` for safety
2. Update all readers to read `inbox_status` exclusively
3. Run for ~24h to confirm consistency
4. Drift detection: continuous comparison of old vs new column values

### Phase 3 — Cleanup

1. Drop `inventory_lifecycle_status` and `inventory_pool_status` columns
2. Remove old write paths from code
3. Update all docs
4. Remove migration scripts

### Phase 4 — Auto-cleanup integration

The auto-cleanup function for `burned_inboxes_in_campaigns` (item #29 in plan doc) should be built as part of ADR-008 since the model unifies "should this inbox be in campaigns" → check `inbox_status`. After ADR-008 ships, the auto-cleanup is "for any inbox with `inbox_status='dead'`, remove from active EB campaigns."

## Open questions to resolve before implementing

1. **Burn cascade timing** — should domain-burn cascade happen synchronously (in the burn handler) or asynchronously (in a periodic job)? Sync is cleaner but slower for big domains.

2. **Re-graduation paths** — if an inbox somehow ends up `inbox_status='dead'` but signals show it's recoverable (e.g., a misclassified kill), what's the recovery path? Probably "manual SQL UPDATE → log to inbox_rotation_history with `rotation_type='recovered'`" — but we should think about this.

3. **`domain.pool_status` value rename?** Currently uses `'live'` for the "primary" pool. After ADR-008, inbox column also uses `'live'`. The domain column's `'live'` means "this domain is in the live pool" — different scope but same word. Keep aligned, or rename one for clarity?

4. **Migration window** — running on a Saturday morning UTC when send activity is lowest minimizes blast radius. Confirm timing.

5. **Rollback plan** — rollback from Phase 1+2 is manageable (just stop writing to new column, drop it, re-derive from old columns). Phase 3 (after old columns dropped) is one-way. Need to ensure Phase 3 only runs after Phase 2 is bulletproof.

6. **`flagged_*` tag preservation in EB** — when an inbox transitions to `dead`, the kill_processor adds `flagged_<trigger>` tag in EB. Under ADR-008, "domain burn cascade" needs a corresponding tag (e.g., `flagged_domain_burn`) so EB-side audit shows WHY each inbox is dead, not just that it is.

## Related

- [[adr-006-tagging-kill-overhaul-2026-04-27]] — introduced the per-inbox pool authority that ADR-008 collapses
- [[adr-007-drop-warning-state-2026-04-29]] — removed `warning` state; ADR-008 builds on this simplification
- [[../decisions/POOL-ASSIGNMENT-AND-TAGGING-SYSTEM]] — current pool/tag reference, will need rewriting post-ADR-008
- [[../core/DOMAIN-INBOX-STATUS-DEFINITIONS]] — current state model, will need rewriting post-ADR-008
- [[../work-logs/2026-04-27-tagging-kill-overhaul-plan]] — overhaul plan; ADR-008 listed as future architectural follow-up

## Author note

User direction (2026-04-29 session-3):

> "I want option A for the ease, but we should consider collapsing to a single column to reduce code noise. The db value status of an inbox should be only 1 column. Inbox first arrives in EmailBison workspace, inbox status = incubating and triggers warmup tracker. Warmup period complete, inbox status changes to reserve. When inbox is promoted to live, inbox status is live."

> "Connection should be a binary true/false continuous check. We want to know when inboxes have been disconnected for an extended period of time. Since EmailBison auto-checks and will retry, we need to know if that disconnect stays longer than 24h. If it exceeds 20 days, we can assume we are no longer paying for it."

> "Dead inbox status indicates to us that we can no longer send and the team will independently cancel with Hypertide on a per-domain basis. If they're left in EmailBison, but disconnected for longer than 20 days we can assume they were cancelled in Hypertide, but clerically we didn't remove."

User explicitly asked for critical pushback. Pushback summary:

- Scope is large; recommended phased execution next week, not inline with post-overhaul fixes still settling.
- Domain burn cascade is a behavior change from Rule C7's interpretation; needs care.
- Migration cost ~2 days; not a quick patch.

Path 1 chosen: Option A this session (cosmetic alignment), ADR-008 next week.
