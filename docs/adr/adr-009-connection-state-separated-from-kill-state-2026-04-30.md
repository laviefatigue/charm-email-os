---
title: "ADR-009: Connection State Separated from Kill State"
created: 2026-04-30
status: accepted
supersedes-rules-from: ADR-006 (kill triggers section, partial — disconnected_timeout removed)
related:
  - docs/plans/connection-state-machine.md
  - docs/work-logs/2026-04-30-systems-accuracy-and-cleanup.md
  - docs/audits/2026-04-30-system-accuracy-snapshot.json
---

# ADR-009: Connection State Separated from Kill State

## Context

The kill-triggers system (introduced in [[adr-006-tagging-kill-overhaul-2026-04-27]] and refined in [[adr-007-drop-warning-state-2026-04-29]]) treated all kill conditions equally — once a row hit `inbox_state='dead'`, it was treated as terminal regardless of which trigger fired.

One of the kill triggers, `disconnected_timeout`, fired when an inbox had been disconnected for 21+ calendar days. The intent was: "if nobody reconnected the OAuth in three weeks, treat the inbox as abandoned."

In practice, the rule produced approximately **1,200 fleet-wide zombie rows** — sender_accounts marked `inbox_state='dead'` with `kill_trigger='disconnected_timeout'` whose actual EmailBison inboxes were currently `Connected` and actively sending. Inboxes were reconnecting after the 21-day window (clerical error, manual OAuth refresh, etc.), but no code path resurrected the dead state. The DB diverged from EB.

Direct evidence (2026-04-30 audit):

| Workspace | dead_with_disconnect_trigger AND status='Connected' |
|-----------|----------------------------------------------------:|
| Spout | 641 |
| Charm | 127 |
| Hello Hero | 124 |
| Selery | 84 |
| Sammy | 83 |
| Search Atlas | 44 |
| Barrena | 39 |
| Linkgraph | 20 |
| SPUI | 13 |
| Stable Kernel | 6 |
| **Fleet total** | **~1,181** |

These were not minor cases. Spout's zombie ratio was 98% of its dead pool. Charm's screenshot in EB UI showed 127 senders bearing the `flagged_disconnected_timeout` tag while sending 100+ emails each.

The root design flaw was conflating two different concerns into one state field:

1. **Quality** — is this inbox reputation-damaged? (terminal)
2. **Connection** — is this inbox's OAuth currently working? (operational, reversible)

Both fed the same `inbox_state='dead'` outcome. There was no semantic room for "dead reputation, fine connection" vs "alive reputation, bad connection."

## Decision

**Connection status and kill state are two completely independent tracks. They never share authority over `inbox_state`.**

### Authority boundaries

| Track | Field(s) | Authority | What can change `inbox_state` |
|-------|----------|-----------|-------------------------------|
| Quality state | `inbox_state` (live/dead), `inventory_pool_status`, `inventory_lifecycle_status` | Reputation kill triggers only (spam, hard bounces, hard blocked, hard unknown, fresh-inbox bounce) | YES |
| Connection state | `status` (Connected/Not connected), `disconnected_at` | EB sync (operational telemetry only) | NO |

### Removed kill trigger

`disconnected_timeout` is no longer a kill trigger. Removed from `KILL_THRESHOLDS` in [sync_modules/health_checks.py](../../sync_modules/health_checks.py) on 2026-04-30. The enum value is preserved in the DB type for historical entries; no new code path writes it.

### Replacement: connection notification ladder

Time-disconnected drives notifications, not kills:

| Time | Action | EB tag |
|:----:|--------|--------|
| 0–24h | None (EB auto-reconnect window) | none |
| 24h | Slack notification | `disconnected_24h` |
| 3 days | Reach out to Hypertide | `disconnected_3d` |
| 7 days | Re-escalation | `disconnected_7d` |
| 20 days | Operator review queue | `disconnected_20d` |

On reconnect, all `disconnected_*` tags are removed. Implementation phases in [[../plans/connection-state-machine]] §9.

### Pool eligibility — connection-blind

Pool promotion (reserve → live) no longer filters on `status = 'Connected'`. A reserve inbox eligible by reputation can promote even if currently disconnected; EB simply won't deliver through it until OAuth reconnects. This makes pool state reflect intended state, not transient operational state. Implementation deferred to Phase 4 of the plan, gated on accuracy validation.

### Hard rule: no automated EB-side removal

The system writes EB **tags**, never **removes** EB **senders**. EB-side cleanup of inboxes is operator-only. Hypertide subscription cancellation is operator-only. The 20-day disconnect tag is a flag for operator review, never an automated destructive action.

## Consequences

### Positive

- The 1,200 zombies stop being created. Phase 1 (the `disconnected_timeout` removal) shipped 2026-04-30 in commit `94fd0fa`.
- DB state machine becomes coherent: `inbox_state='dead'` always means "reputation-damaged, terminal."
- Pool/lifecycle decisions become independent of operational connection state, reducing capacity loss from disconnected reserves not being eligible for promotion.
- Operator can read EB UI without confusion — connection tags are for monitoring, not for treating connected inboxes as dead.

### Negative

- An inbox truly abandoned (disconnected forever, never reconnected) stays in DB with `is_active=TRUE` indefinitely. Mitigation: the notification ladder surfaces these to operators at 24h/3d/7d/20d. Operator-driven manual cleanup, no automated decision.
- The ~1,200 existing zombies are not auto-restored by this ADR. Restoration is operator-driven, per-workspace, manual SQL based on the [generate_zombie_review_csv.py](../../scripts/generate_zombie_review_csv.py) review queue. See [[../plans/connection-state-machine]] §8.
- Disconnect duration is no longer reflected in `inbox_state`. Code that read `kill_trigger='disconnected_timeout'` for analytics needs to read `disconnected_at` directly instead.

### Neutral

- Existing rows with `kill_trigger='disconnected_timeout'` are unaffected by this ADR. They remain dead in DB until operator review explicitly restores them.

## Alternatives considered

### Alternative A — Add a `cancelled` state distinct from `dead`

Considered: introduce `inbox_state='cancelled'` to represent "subscription stopped, not reputation-damaged." Disconnect timeout would transition to `cancelled`, leaving `dead` for reputation only.

Rejected because: it adds schema complexity for a distinction the operator doesn't need at the inbox-state level. Operator's mental model is "this inbox is operationally usable" (driven by `status`) vs "this inbox is reputation-damaged" (driven by `inbox_state`). A third state adds cognitive overhead without buying clarity.

### Alternative B — Keep `disconnected_timeout` but add a resurrection path

Considered: leave the trigger in place, add code that detects "row marked dead by disconnected_timeout AND now Connected" and auto-resurrects.

Rejected because: it preserves the conflation. Resurrection logic that auto-restores based on the system's own data is exactly the failure mode that produced the zombies in the first place — the system was wrong, then trusted itself to recover. We don't have proven accuracy. Operator-driven restoration is safer.

### Alternative C — Auto-decommission at 20 days

Considered: at 20-day disconnect, automatically remove the inbox from EB workspace and notify Hypertide to cancel the subscription.

Rejected because: violates the "no automated EB-side removal" hard rule. Operator handles all EB cleanup. The 20-day tag is operator's signal to act, not the system's signal to act.

## Implementation status

- ✅ **Phase 1** (this ADR's primary action): `disconnected_timeout` removed from `KILL_THRESHOLDS`. Shipped 2026-04-30 commit `94fd0fa`.
- ⏳ **Phase 2** (notification ladder): planned, gated on accuracy validation.
- ⏳ **Phase 3** (EB connection tags): planned, gated on accuracy validation.
- ⏳ **Phase 4** (drop connection filter from promotion): planned, gated on accuracy validation.
- ⏳ **Phase 5** (zombie restoration): operator-driven, per-workspace, manual SQL based on CSV review.
- ⏳ **Phase 6** (EB tag cleanup for restored zombies): runs as part of Phase 5 operator-confirmed flow.

## Compliance check

The change is consistent with prior ADRs:

- **ADR-006** (tagging-kill overhaul): kill philosophy preserved. The five reputation triggers are unchanged; `disconnected_timeout` was always a separate concern that was wrongly bundled.
- **ADR-007** (drop warning state): connection state is monitoring telemetry; the warning intermediate is not reintroduced.
- **ADR-008** (proposed inbox_status collapse): the decision in ADR-008 to merge `inventory_pool_status` and `inventory_lifecycle_status` is unaffected. Connection state was never going to be in that merged column; this ADR clarifies why.

## References

- Plan doc: [[../plans/connection-state-machine]]
- Work log: [[../work-logs/2026-04-30-systems-accuracy-and-cleanup]]
- Audit snapshot: `docs/audits/2026-04-30-system-accuracy-snapshot.json`
- Code: commit `94fd0fa` on `plan/eod-campaign-reapply` — `sync_modules/health_checks.py`, `sync_modules/lifecycle_tag_sync.py`
