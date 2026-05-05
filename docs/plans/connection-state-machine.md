---
title: Connection State Machine — Tagging and Categorization, Never Removal
created: 2026-04-30
updated: 2026-05-05 (Phase 2 disconnect ladder folded into event-driven architecture)
status: Phase 1 SHIPPED; Phase 2 folded into event-driven (no separate implementation)
related:
  - docs/plans/cross-workspace-integrity-firewall.md (P1.A)
  - docs/plans/emailbison-sync-decomposition.md (P1.B/C/D)
  - docs/plans/event-driven-architecture.md (Phase 2 implementation vehicle)
non-goal:
  - Removing inboxes from EmailBison (operator handles all EB cleanup manually)
  - Cancelling Hypertide subscriptions (operator handles all Hypertide actions)
  - Auto-decommissioning (no automated destructive EB-side action, ever)
---

> **2026-05-05 fold-in note:** Phase 2 (the 24h / 3d / 7d / 20d disconnect notification ladder) is now scheduled as part of the event-driven architecture rollout — see [event-driven-architecture.md](event-driven-architecture.md) § "Connection state triggers (folds in Plan B Phase 2)". A `notify_disconnect_observed` trigger fires on connection-state transitions; a 1h-cadence ladder evaluator reads `event_log` to determine which rung to fire next. No separate notification system needed.

# Connection State Machine

## 0. The hard rule, locked in

> **Our system tags inboxes in EB and categorizes them in our DB. That is the entire scope.**
>
> **We never remove inboxes from EmailBison. We never cancel Hypertide subscriptions. EB-side cleanup is operator-driven, manual, separate.**

Every section below respects this. If a section proposes a destructive EB-side action, that's a bug in the section.

## 1. The core principle

Connection status and kill state are **two completely independent tracks**. They share a row in `sender_accounts` but never share authority over disposition.

| Track | What it represents | Sole authority | What can change `inbox_state` |
|-------|---------------------|----------------|-------------------------------|
| **Quality state** | Inbox reputation health | Reputation kill triggers (spam, bounces, blocks, fresh-bounce) | YES |
| **Connection state** | OAuth/IMAP currently working? | EB's `status` field + `disconnected_at` timestamp | NO — never |

A connection issue does not, cannot, and never should drive an inbox into `inbox_state='dead'`. The 1,200 fleet-wide zombies prove the failure of that conflation.

## 2. The notification ladder — connection state's only output

Connection status drives **notifications** and **EB tagging**. Both are non-destructive. No removals, no cancellations.

| Time disconnected | Action | EB tag | Slack? | Hypertide notify? |
|:-----------------:|--------|--------|:------:|:-----------------:|
| 0–24h | None | none | no | no |
| **24h** | First notification | `disconnected_24h` applied | YES | no |
| **3 days** | Reach out to Hypertide | `disconnected_24h` upgraded to `disconnected_3d` | YES | YES |
| **7 days** | Re-escalation | `disconnected_3d` upgraded to `disconnected_7d` | YES | YES |
| **20 days** | Operator review queue | `disconnected_20d` (= "review for cleanup decision") | YES | YES |

The 20-day tag is **a flag for operator review**, not an automated action. Operator decides whether to manually remove from EB workspace + cancel the Hypertide subscription. The system never does this autonomously.

**On reconnect (status returns to `Connected`)**: all `disconnected_*` tags removed from EB. Slack notifies "X reconnected." That's it.

## 3. The kill state machine — unchanged scope, smaller authority

Kill triggers stay reputation-only. List explicitly:

| Kill trigger | Why it kills | Reversible? |
|--------------|--------------|:-----------:|
| `spam_complaint` | Recipient marked spam → brand damage | NO |
| `hard_bounces_24h` | Hard-bounce rate exceeds threshold | NO |
| `hard_blocked_24h` | Provider blocked sending | NO |
| `hard_unknown_24h` | Hard rejects without clear reason | NO |
| `fresh_inbox_bounce` | New inbox bouncing — provisioning failure | NO |

**Removed from kill triggers**: `disconnected_timeout`. Disconnect alone never kills. (Implementation: drop from `KILL_THRESHOLDS`, remove the detection block in [health_checks.py:509-521](sync_modules/health_checks.py#L509-L521).)

A row already in `inbox_state='dead'` because of any of the 5 reputation triggers stays dead, regardless of connection state. Reputation kills don't reverse just because OAuth came back.

## 4. The DB categorization model

Two independent columns drive everything:

```
sender_accounts:
    inbox_state           — 'live' or 'dead'  (quality)
    status                — 'Connected' or 'Not connected'  (operational)
    disconnected_at       — timestamp of last disconnect, or NULL
    kill_trigger          — reputation reason if state='dead', or NULL
    inventory_pool_status — 'live' / 'reserve' / NULL  (quality-driven)
    inventory_lifecycle_status — 'incubating' / 'active' / 'dead'  (quality-driven)
```

Critical: `status='Not connected'` does NOT imply `inbox_state='dead'`. The two are recorded independently. A row can be:

- `inbox_state='live'`, `status='Connected'` → healthy, ready to send
- `inbox_state='live'`, `status='Not connected'` → healthy reputation, needs OAuth — still in pool, EB just won't deliver until reconnect
- `inbox_state='dead'`, `status='Connected'` → reputation-killed, but OAuth fine — should NOT happen by accident, only if a reputation trigger fired while connected
- `inbox_state='dead'`, `status='Not connected'` → reputation-killed AND disconnected — common terminal state

The third case is fine — reputation kill happened, the row is dead, doesn't matter that OAuth still works. We don't restore a dead reputation just because connection holds.

## 5. The pool eligibility rule — connection-blind

[pool_promotion.py:88](sync_modules/pool_promotion.py#L88) currently filters on `status = 'Connected'`. **That filter goes away.**

Promotion to live is driven purely by quality (lifecycle = active, pool = reserve, healthy reputation). If the promoted inbox happens to be currently disconnected, EB will fail to deliver through it until OAuth reconnects — that's EB's problem, not ours. The notification ladder handles ops awareness.

This makes the pool reflect **intended state**, not **transient operational state**. Operationally cleaner.

## 6. The EB tagging strategy

Tags applied by our system to mirror DB state. Operator sees this in EB UI.

### Quality tags (driven by `inventory_pool_status`)
- `live` — inbox is in the live pool
- `reserve` — inbox is in the reserve pool
- `incubating` — inbox is in incubation (lifecycle='incubating')
- `flagged_<trigger>` — inbox was killed by reputation trigger (e.g. `flagged_spam_complaint`, `flagged_hard_bounces_24h`)

### Connection tags (NEW — driven by `status` and `disconnected_at`)
- `disconnected_24h` — disconnected ≥ 24h
- `disconnected_3d` — disconnected ≥ 3 days
- `disconnected_7d` — disconnected ≥ 7 days
- `disconnected_20d` — disconnected ≥ 20 days, **operator review for EB cleanup**

These are escalating: at each milestone, the prior tag is replaced. Reconnect removes whichever is current. They surface "needs attention" in the EB UI without any system-driven destructive action.

### Removed
- **`flagged_disconnected_timeout`** is deprecated. It conflated "this is killed" with "this is operationally stale." Existing zombies wearing this tag are part of the §8 restoration.

## 7. What this DOES NOT do — explicit non-goals

| Action | Position |
|--------|----------|
| Auto-remove inbox from EB workspace | **NEVER** — operator only |
| Auto-cancel Hypertide subscription | **NEVER** — operator only |
| Auto-decommission after 20 days | **NEVER** — operator decides per-inbox |
| Resurrect a reputation kill on reconnect | **NEVER** — reputation kills are terminal |
| Mark `inbox_state='dead'` based on connection alone | **NEVER** — connection doesn't drive quality state |

The system's authority is: **tagging and categorizing**. Anything destructive is operator territory.

## 8. The 1,200 zombie restoration

The fleet has ~1,200 rows where `inbox_state='dead'` AND `kill_trigger='disconnected_timeout'`. They were killed under the wrong rule. Restoration is per-row, with reputation re-validation.

### Per-row decision tree

For each zombie row:

```
1. Does the row have ANY non-disconnected_timeout kill_trigger in its history?
   (Check inbox_rotation_history, kill_queue, audit logs for prior reputation events.)
   
   YES → keep killed. Reputation reason exists; row is correctly dead.
        (kill_trigger should not be 'disconnected_timeout' in this case — fix it
        by setting kill_trigger to the reputation reason that actually applied.)
   
   NO → continue to step 2.

2. Does the row have current reputation indicators of damage?
   - hard_bounces_24h above threshold?
   - spam_complaints in last 30 days?
   - provider_block tags in EB currently?
   
   YES → mark with the actual reputation kill_trigger; keep killed.
   
   NO → continue to step 3 (eligible for restoration).

3. Restoration:
   - inbox_state = 'live'
   - kill_trigger = NULL
   - kill_reason = NULL
   - killed_at = NULL
   - inventory_lifecycle_status = derive from warmup state (active if past 14 BD,
     else incubating)
   - inventory_pool_status = derive from prior pool history (default reserve for Google,
     live for Microsoft)
   - is_active = TRUE
   - EB tag cleanup: remove `flagged_disconnected_timeout` from EB
   - EB tag apply: based on resulting inventory_pool_status, apply correct tag
     (handled by set_tag_sync next cycle)

4. Parallel: based on current connection status, apply the right disconnect tag:
   - status='Connected' AND disconnected_at IS NULL → no disconnect tag
   - status='Not connected' AND disconnected_at within milestone → apply
     `disconnected_24h` / `_3d` / `_7d` / `_20d` accordingly
```

### Per-workspace gating

The 1,200 are not uniform. Spout has 641 (98% of its dead pool). Hello Hero has 124 (98%). These suspiciously high ratios suggest a fleet-wide OAuth wipe + bulk reconnect pattern. **Operator review per workspace before bulk restoration**, especially Spout — a single-event mass reconnect needs to be confirmed legitimate before we restore that many at once.

Workspace-by-workspace order, smallest to largest:
1. Stable Kernel (6) — proof of concept
2. SPUI (13) — small, simple
3. Linkgraph (20)
4. Barrena (39)
5. Search Atlas (44)
6. Sammy (83)
7. Selery (84)
8. Hello Hero (124)
9. Charm (154) — the screenshot you showed
10. Spout (641) — last, highest scrutiny

After each workspace's restore, monitor for 24h before moving to next. If anything looks wrong, halt and investigate.

## 9. Implementation phases

### Phase 1 — stop new zombies (today)
- Remove `disconnected_timeout` from `KILL_THRESHOLDS` in [health_checks.py:129](sync_modules/health_checks.py#L129)
- Remove the trigger detection block at [health_checks.py:509-521](sync_modules/health_checks.py#L509-L521)
- Add a `# DEPRECATED — see docs/plans/connection-state-machine.md` comment at the trigger value if it still exists in any enum
- ~15 line patch

### Phase 2 — notification ladder
- New module: `sync_modules/connection_monitor.py` (or extend `slack_audit.py`)
- Cron-style: every 30 min, scan rows where `status='Not connected' AND disconnected_at IS NOT NULL`
- For each row, compute time-since-disconnect; emit Slack message at milestone boundaries (24h / 3d / 7d / 20d)
- Idempotent: track last-notified milestone in a small `connection_notifications` table or `sender_accounts.last_disconnect_notification_at` column to avoid spamming the same row across cycles

### Phase 3 — connection tags in EB
- Extend `set_tag_sync.py` with a connection-tag pass: read row's `disconnected_at`, compute current milestone, ensure the right `disconnected_*` tag is applied (and prior milestones removed)
- On reconnect, all `disconnected_*` tags removed
- Idempotent

### Phase 4 — pool promotion connection-blind
- Drop `AND sa.status = 'Connected'` from [pool_promotion.py:88](sync_modules/pool_promotion.py#L88) and [:108](sync_modules/pool_promotion.py#L108) and [:228](sync_modules/pool_promotion.py#L228)
- Tests need updating; regression test that disconnected reserves are now eligible for promotion

### Phase 5 — zombie restoration (per-workspace)
- Script: `scripts/restore_disconnected_timeout_zombies.py`
- Inputs: workspace name, dry-run flag
- Per-row decision tree from §8
- Captures pre-state JSON for every row before changes
- Reports: count restored, count kept-killed (with reputation reason), count skipped (audit follow-up)

### Phase 6 — EB tag cleanup for restored zombies
- Strips `flagged_disconnected_timeout` from EB for every row restored in Phase 5
- Workspace-scoped, idempotent
- Runs as part of Phase 5 script, gated by per-row `EB_WRITE_ENABLED` flag (default false until operator confirms)

### Phases 1-3 ship as code; Phase 5+6 are operator-driven scripts run per workspace

## 10. Decisions still needed

| # | Decision | Default if unanswered |
|---|----------|----------------------|
| D-1 | Do we need a `connection_notifications` tracking table, or just stamp `last_disconnect_notification_at` on `sender_accounts`? | Column on sender_accounts (simpler, no new schema) |
| D-2 | Is the milestone schedule **24h / 3d / 7d / 20d** correct, or do you want different thresholds? | As stated |
| D-3 | EB connection tags: 4 escalating tags (`disconnected_24h` etc) vs 1 single tag (`disconnected_long`)? | 4 escalating tags — operator gets visual signal of duration without checking timestamps |
| D-4 | Hypertide notification at 3d and 7d — do we have a Hypertide notification API endpoint, or is this a manual Slack-to-them workflow? | Manual Slack message linking to disconnect-list initially. API integration later if Hypertide exposes one. |
| D-5 | Phase 5 zombie restoration: operator runs per-workspace manually, or scheduled batch? | Operator-driven, manual, per workspace, with dry-run preview |
| D-6 | Spout's 641 zombies: do we need to investigate the root cause (mass OAuth wipe?) before restoring? | YES — block Phase 5 for Spout until cause is understood |

## 11. The model in one sentence

**Connection status drives notifications and visual EB tags. Quality state (live/dead) is driven only by reputation kills. They never share authority over a row, and we never automatically remove anything from EmailBison or Hypertide.**

## 12. Critical pushback I'd make on this plan

Three things I want to flag honestly:

### 12.1 The notification ladder is only useful if someone reads it

The existing `inbox_audits` Slack channel has 72 unreviewed audits in 72 days. Adding more Slack messages without an SLA is just adding noise. **Recommendation**: tie the 20-day tag specifically to a workflow that requires action — either an operator dashboard view, or a weekly "decommission review" message that lists all 20-day-tagged inboxes for explicit operator-confirm/decline.

Without that, the 20-day tag is just colorful documentation.

### 12.2 Restoration of 1,200 inboxes is a non-trivial fleet-state change

We're talking about restoring ~25-30% of total fleet capacity in some workspaces. This will increase send volume, possibly trigger fresh-inbox-bounce thresholds, and generally perturb the system. **Recommendation**: per-workspace restoration with a 24-72h observation window between workspaces. Don't bulk-restore.

### 12.3 The Spout 641 anomaly needs investigation BEFORE restoration

98% zombie ratio on Spout's dead pool is not normal. Possible causes:
- Mass OAuth provider-key rotation (single event)
- A bulk delete-and-readd by Hypertide (subscription churn)
- A buggy sync that wrongly marked them disconnected (false positive avalanche)

If it's (3), restoration without fixing the underlying bug means the zombies come back. **Recommendation**: investigate before action. If we can't trace the cause within a few days, treat Spout's 641 as a separate manual-review batch, not standard restoration.

## 13. What this plan covers vs related plans

| Concern | This plan | Other plan |
|---------|:---------:|:----------:|
| Connection state machine + notifications | ✓ | — |
| `disconnected_timeout` removed as kill trigger | ✓ | — |
| Zombie restoration (1,200 fleet-wide) | ✓ | — |
| Pool promotion connection-blind | ✓ | — |
| Cross-workspace pollution prevention | — | [cross-workspace-integrity-firewall.md](cross-workspace-integrity-firewall.md) |
| Service decomposition (apps/* extraction) | — | [emailbison-sync-decomposition.md](emailbison-sync-decomposition.md) |
| Inbox-audit overhaul (per-workspace, integrity sections) | — | (deferred — separate plan) |

Sequencing: Phase 1 of this plan ships immediately (today, alongside the Sammy hot-fix). Phases 2-4 wire up the new model. Phase 5+6 (the actual zombie cleanup) wait for operator-driven per-workspace execution.
