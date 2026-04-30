---
title: Inbox Audit Overhaul — Requirements Catalog (DEFERRED)
created: 2026-04-30
updated: 2026-04-30
status: DEFERRED — capture-only, no execution this sprint
purpose: Single doc collecting all audit-related requirements surfaced
         during the 2026-04-29 + 2026-04-30 sessions, for later scoping
---

# Inbox Audit Overhaul

> **Status: DEFERRED.** User explicitly deferred this work to focus on
> state-machine reliability first. This doc is a capture-only catalog of
> requirements as they surface during related work, so the eventual
> overhaul has clear scope.

## Context

The current `inbox_audits` Slack-driven workflow has been running since
2026-02-18, producing a daily report at 6 AM and 1 PM Pacific. As of
2026-04-30, **all 72 audit records are `status='pending'`** — nobody has
clicked "Confirmed" or "Issues Found" once. The human-in-the-loop
workflow is dead. The audit is fire-and-forget noise.

The work below addresses both the schema/data gaps AND the operational
discipline needed for the audit to drive action.

## Requirements catalog

Each row links back to where it surfaced.

### Schema gaps (data the audit doesn't currently capture)

| # | Requirement | Surfaced | Why it matters |
|:-:|-------------|----------|----------------|
| S-1 | Per-workspace audit, not fleet-aggregated | 2026-04-30 session §"Schema-level criticism" | Today's `inbox_audits` has no `workspace_id`. Cannot answer "is Sammy specifically in trouble?" without re-running queries against live data. |
| S-2 | Snapshot the inbox set, not just count | 2026-04-30 session §"Schema-level criticism" | Today the audit captures `total_kills=380` for 2026-04-29 but no record of WHICH 380. Investigation after the fact is impossible. |
| S-3 | Connected-status of dead inboxes for subscription-cancel signal | **2026-04-30 (this addition)** | An inbox killed by reputation but still showing Connected in EB has working OAuth. The DOMAIN it lives on still costs money. We need a per-domain rollup: "all inboxes on this domain are dead → subscription can be cancelled" vs "some dead, some alive → keep paying." Drives operator decisions on Hypertide cancellation. |

### Integrity sections (new audit categories)

| # | Requirement | Surfaced | Why it matters |
|:-:|-------------|----------|----------------|
| I-1 | Cross-workspace pollution count + foreign+live subset | 2026-04-29 audit | Foreign inboxes that hold pool tags = cross-tenant leak risk |
| I-2 | Stuck-in-incubation past 14 BD | 2026-04-30 SKMR investigation | The 6 SKMR rows that stuck for 22 days were invisible until manual investigation |
| I-3 | Workspace-orphan rows (last_synced > 7 days) | 2026-04-30 silent-failure findings | A row stops being synced when EB workspace moved. Today, no signal. |
| I-4 | lifecycle_tag_sync stale per workspace (not running) | 2026-04-30 Sammy investigation | Sammy's lifecycle was "running but processing 0" — looked broken until investigated |
| I-5 | Pool-eligibility lockout state (post-firewall) | 2026-04-30 firewall plan | When firewall ships, audit needs `quarantined_inbox_count` metric |
| I-6 | Promotion blocked by connection (silent capacity loss) | 2026-04-30 connection-state plan | Reserves stuck because they're disconnected. Needs surface. |
| I-7 | Cap-exceeded warnings (live count > target) | 2026-04-30 connection-state plan | Inventory overshoot signal |
| I-8 | Pool-tag drift (DB pool ≠ EB tag) | 2026-04-30 Spout investigation | The 10 Spout rows were caught manually; needs automated surface |
| I-9 | Domain subscription-cancel candidates | **2026-04-30 (this addition)** | Per-domain rollup: all inboxes dead → cancel candidate. Needs operator confirmation, never auto-cancel. Drives §S-3. |

### Operational discipline

| # | Requirement | Surfaced | Why it matters |
|:-:|-------------|----------|----------------|
| O-1 | SLA on corrections workflow | 2026-04-30 session §"Schema-level criticism" | If `status='pending'` for >24h, escalate. If >7d, page. Currently no SLA — 72 audits, all pending, zero ever reviewed. |
| O-2 | Audit must surface specific actionable lists, not just counts | 2026-04-30 throughout | "Disconnect count = 1,079" is unactionable. "These 5 inboxes need EB cleanup" is. |
| O-3 | Per-workspace Slack channel routing (optional) | open question | Some operators want per-client channels; others one combined. |
| O-4 | Audit must enforce, not just report | 2026-04-30 session §"Critical synthesis" | When audit fires N consecutive cycles with same finding, escalate to halt-action (e.g., block reapply for that workspace) until acknowledged. |

## Subscription cancellation signal — new section detail

Per the user's 2026-04-30 directive: **the audit should report on Connected status of dead inboxes to drive Hypertide subscription cancellation decisions for domains.**

The shape:

```
Per-domain audit row:
  domain_name
  total_inboxes
  dead_inboxes (count)
  alive_connected (count)
  alive_disconnected (count)
  dead_connected (count)        ← informational; OAuth works but inbox dead
  dead_not_connected (count)    ← truly inactive
  subscription_cancel_eligible? boolean
    = (dead_inboxes == total_inboxes)  AND (no inbox returns to alive in last N days)
```

Operator workflow when the signal fires:
1. Audit lists "domains where 100% of inboxes are dead, none alive in last 14 days"
2. Operator reviews each row
3. Operator decides: cancel the Hypertide subscription manually
4. Operator removes from EB workspace manually
5. NEVER auto-cancellation per ADR-009 hard rule

Why this matters operationally: a domain we've stopped using is still costing
us a Hypertide subscription. Without this signal, dead domains accumulate
and cost compounds. With it, operator has a weekly review queue.

Importantly, the signal differentiates:
- **All-dead, none-connected** → strong cancel signal
- **All-dead, some still Connected** → still strong, just OAuth works (but
  no value since reputation-damaged)
- **Mixed dead/alive** → keep the subscription (alive inboxes still useful)

Both "all-dead-Connected" and "all-dead-Not-connected" are equivalent for
cancellation purposes per ADR-009 (kill is terminal regardless of connection
state). But operator wants the connection breakdown for context — "did
the inbox die and OAuth got revoked together (clean abandonment)?" or "did
reputation die but OAuth still works (operator decided to stop using)?"

## Out of scope (explicitly NOT this overhaul)

- Auto-cancellation of subscriptions or removal from EB → ADR-009 hard rule
- Replacing the existing daily Slack flow → augmenting, not replacing
- Building per-workspace Slack channel infrastructure → operator config

## Implementation phasing (when work picks up)

| Phase | Work | Effort estimate |
|-------|------|----------------|
| 1 | Schema migration: add `workspace_id` + `inbox_id_set JSONB` columns to `inbox_audits` | 1 day + migration |
| 2 | Per-workspace audit query rewrite | 1 day |
| 3 | Add integrity sections (I-1 through I-9) | 2 days |
| 4 | Subscription-cancel domain rollup section | 1 day |
| 5 | Slack message restructure (per-workspace, with action lists) | 1 day |
| 6 | SLA enforcement on corrections (escalation at 24h, page at 7d) | 1 day |
| Total | | ~7 days |

Sequencing: this should NOT ship until the firewall (Plan A) is in place,
because integrity sections I-5/I-6 depend on the `is_quarantined` column.

## When to pick this up

After:
1. Firewall (Plan A) ships
2. Connection state machine Phases 2-4 ship (notification ladder, EB tags)
3. apps/incubation-watcher cutover validated

The audit overhaul is the integrative observability layer that makes all
the above legible. It's worth doing but only after the underlying
state-machine work is stable. Building it earlier means refactoring it
when the state machine changes shape.

## Cross-references

- Master tracker: [INBOX-INTEGRITY-PROGRAM.md](INBOX-INTEGRITY-PROGRAM.md) §3.7
- Critical analysis of current audit: [docs/work-logs/2026-04-30-systems-accuracy-and-cleanup.md](../work-logs/2026-04-30-systems-accuracy-and-cleanup.md) §"Critical review of the existing inbox audit"
- Existing audit code: [sync_modules/slack_audit.py](../../sync_modules/slack_audit.py)
- Existing audit schema: migration 063
- ADR-009 (no auto-removal): [adr-009-...md](../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md)
