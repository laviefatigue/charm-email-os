---
title: Zombie Resurrection — disconnected_timeout retired-trigger cleanup
created: 2026-05-04
updated: 2026-05-04
status: PLANNED — paused for review (bounce-history audit needed first)
purpose: Decide whether and how to resurrect inboxes that were killed by
         the disconnected_timeout trigger before it was retired in commit
         94fd0fa (2026-04-30). Includes the bounce-history audit needed
         to surface kills that would have fired but didn't because the
         inbox exited the kill_processor loop after disconnect-kill.
---

# Zombie Resurrection — Disconnected Timeout Cleanup

> **Status: PLANNED.** Discovery happened during the 2026-05-02
> audit_system_accuracy.py run. EB pool-tag drift cleanup completed
> 2026-05-02/03 (Spout + SPUI). Resurrection deferred pending
> bounce-history audit per user direction 2026-05-03.

## 1. Context — how we got here

Phase 1 of [connection-state-machine.md](connection-state-machine.md)
retired the `disconnected_timeout` kill trigger on 2026-04-30 in commit
`94fd0fa`. The trigger marked an inbox dead when its OAuth had been
disconnected for ≥21 days. The commit message itself called out the
problem:

> "the 21-day-disconnect-equals-dead rule produced ~1,200 fleet-wide
> zombies (rows marked dead in DB while currently Connected and
> sending in EB)."

The retirement stopped new kills under this rule, but **did not reverse
existing kills**. That decision was deferred. This doc captures the
deferred decision.

ADR-009 codified the principle: **connection state is monitoring-only,
not a kill signal.** A disconnect ≠ a dead inbox. An inbox can lose
OAuth and reconnect later, perfectly healthy.

## 2. Population (current snapshot 2026-05-03)

Discovered via `scripts/audit_system_accuracy.py` followed by direct
DB+EB cross-reference. See
`docs/audits/2026-05-03-disconnect-zombie-resurrection-candidates.json`
for the candidate-level data.

```
672 sender_accounts where:
    inbox_state = 'dead'
    kill_trigger = 'disconnected_timeout' (retired)
    is_active = TRUE

  ┌─ 241 resurrect-eligible (no other reason to keep dead, on healthy domain)
  │     Charm: 100, Sammy: 115, SPUI: 22, Hello Hero: 2, Spout: 2
  │     107 currently Connected in EB
  │     134 currently Not connected in EB
  │
  ├─ 373 on cancelled domains (Hypertide subscription gone — pointless to resurrect)
  ├─  58 on burned domains (domain itself shouldn't send — defer)
  └─   ... overlap and other secondary signals
```

In EB, 277 of these inboxes still carry the `flagged_disconnected_timeout`
tag. SPUI's 22 lost both pool-tag AND flag-tag in their kill cycle
(silent EB-API failures), so they're DB-only zombies.

## 3. Why a bounce-history audit is required FIRST

User-surfaced critical insight (2026-05-03):

> "We need to audit their bounce history as well. Since kill triggers
> could have run, but because we have the disconnect timeout, others
> didn't follow."

The `kill_trigger` column captures the **first** kill that fired. Once
an inbox is `inbox_state='dead'`, kill_processor stops evaluating it
(it only processes live inboxes). So:

- An inbox killed by `disconnected_timeout` at 2026-03-15
- That accumulated 5 hard bounces on 2026-03-20
- Would still have `kill_trigger='disconnected_timeout'` today
- Resurrecting it on the basis of "kill_trigger isn't a real signal"
  would put a genuinely-bad inbox back in rotation

We need to replay the active kill thresholds against current counters
before resurrecting anyone.

## 4. Active kill triggers (replay matrix)

From `sync_modules/health_checks.py` (Microsoft / Google differ):

| Trigger | Microsoft | Google | Source column |
|---------|-----------|--------|---------------|
| `spam_complaint` | ≥1 | ≥1 | `complaints_lifetime` (cumulative) |
| `consecutive_hard_bounces` | ≥2 | ≥2 | `consecutive_hard_bounces` (running) |
| `hard_bounces_24h` | ≥2 | ≥1 | `hard_bounces_24h` (rolling 24h) |
| `hard_blocked_24h` | ≥2 | ≥1 | `hard_blocked_24h` (rolling 24h) |
| `hard_unknown_24h` | ≥3 | ≥1 | `hard_unknown_24h` (rolling 24h) |
| `hard_bounce_rate_7d` | >2.0% (min 100 sends) | same | `hard_bounce_rate_7d` |
| `bounce_rate_all_7d` | >5.0% (min 100 sends) | same | `total_bounce_rate_7d` |

`disconnected_timeout` is intentionally absent — retired.

## 5. Audit phases

### Phase A — Threshold replay (read-only)

For each of the 241 candidates, evaluate the table above against current
column values. Bucket:

- **clean_resurrect**: every counter zero or below threshold for its ESP
- **would_have_killed**: at least one threshold breach → exclude from
  resurrection AND update `kill_trigger` to the correct active trigger
  (so the historical record is accurate)
- **borderline**: non-zero signals below threshold → operator review

**Sanity check before Phase A:** verify whether rolling counters (24h,
7d) actually reset on dead inboxes. The 2026-05-03 snapshot showed 42
of 241 with `hard_bounces_24h > 0` despite being dead for weeks. If
the counter is stale (not reset on kill), then a >0 value isn't
evidence of recent activity. If it does reset, a >0 value IS evidence.
Look at `sync_modules/sync_warmup.py` and the daily counter-reset job
(`reset_daily_counters` per the column comment on `total_sends_24h`).

Output: `docs/audits/<date>-zombie-bounce-audit.json` with the three
buckets.

### Phase B — Event-log lookback (paranoid, optional)

If Phase A is inconclusive:

- Query `kill_queue` for any entry on each sender_account_id where
  `trigger_type != 'disconnected_timeout'` — would surface kills that
  were queued but never processed
- Query `sync_events` / replies tables for spam complaint events on
  each sender — surfaces FBL hits that may not be reflected in
  `complaints_lifetime` if there's a sync gap
- Optionally: `bounces` table if it exists, for raw event evidence

### Phase C — Decision

Operator reviews `would_have_killed` bucket: confirm whether to update
`kill_trigger` to the correct active trigger or leave as-is. The
`borderline` bucket gets per-row operator decision.

The `clean_resurrect` bucket is the resurrection target.

## 6. Resurrection script (after Phase C)

Same pattern as `scripts/cleanup_stale_eb_pool_tags.py`
(commit landed 2026-05-02):

- Per-workspace mandatory (`--workspace SPUI`); no `--all`
- Dry-run default; `--apply` required
- Reads candidate list from Phase C output JSON
- Per inbox:
  - DB UPDATE: `inbox_state='live'`, clear `kill_trigger`/`kill_reason`/
    `killed_at`, set `inventory_pool_status='reserve'`
  - EB API: remove `flagged_disconnected_timeout` if present, apply
    `reserve` pool tag
- Audit log: `docs/audits/<date>-zombie-resurrection-<workspace>.json`

**Pool target = `reserve`** (not `live`). Rationale: graduation path is
designed exactly for this — to promote inboxes that perform well. After
resurrection, `lifecycle_tag_sync` will move them to `live` if metrics
warrant. Matches what we'd do for any new fresh inbox.

**Connected vs Not connected at resurrection time:**
- Connected → immediately usable in rotation post-resurrection
- Not connected → resurrected to `inbox_state='live' status='Not connected'`
  per ADR-009. They won't send until OAuth is restored, but that's the
  correct state. The current /reports/disconnects page will surface them.

## 7. Out-of-scope buckets — what to do with them

These 431 inboxes are NOT resurrection candidates but need disposition:

- **373 on cancelled domains.** Hypertide subscription gone. Inboxes will
  be archived/cleaned with the domain. No EB tag work needed unless
  drift surfaces.
- **58 on burned domains** (42 Connected, 16 Not connected). Domain
  reputation is shot; resurrecting individual inboxes has no operational
  value. Revisit if/when the domain comes off burned status.
- ESP-tag drift on these inboxes is OUT-OF-SCOPE for resurrection but
  may be in scope for a separate cosmetic-cleanup pass (they may carry
  stale `flagged_*` tags too).

## 8. Cleanup sweep — orthogonal but related

Independent of resurrection: the 277 `flagged_disconnected_timeout` tags
in EB are pure cosmetic noise (the trigger that wrote them is retired).
Two cleanup paths:

- (A) **Side-effect of resurrection**: the resurrection script removes
  the flag for each resurrected inbox. Covers up to 213 of 277 (those
  in clean_resurrect bucket that have the EB tag).
- (B) **Standalone sweep**: write `cleanup_flagged_disconnected_timeout.py`
  modeled on `cleanup_stale_eb_pool_tags.py`. Strips the tag from any
  inbox that carries it, regardless of resurrection decision. Covers
  all 277 in one pass.

Recommendation: do (B) first as a no-decision-required cosmetic cleanup,
then (A) as side-effect. Or do (B) only and skip the side-effect from
(A) entirely.

## 9. Decisions to surface to operator

When work resumes:

1. **Sanity-check rolling-counter behavior** before Phase A. Stale
   counter values change Phase A's bucketing significantly.
2. **Pool target on resurrection — confirm `reserve` (recommended) vs
   `live`.** Documented above; final operator call.
3. **`would_have_killed` bucket — update kill_trigger to active trigger,
   or leave as-is.** Honesty in the historical record is the argument
   for updating. No operational difference either way.
4. **Burned-domain bucket (58) — defer or revisit later.** Tied to
   broader burned-domain rehabilitation work that hasn't been planned.
5. **Cancelled-domain bucket (373) — disposition tied to cancelled-
   domain cleanup, which is its own workstream.**

## 10. Cross-references

- Discovery audit: [scripts/audit_system_accuracy.py](../../scripts/audit_system_accuracy.py)
- 2026-05-03 audit snapshot:
  [docs/audits/2026-05-03-disconnect-zombie-resurrection-candidates.json](../audits/2026-05-03-disconnect-zombie-resurrection-candidates.json)
- Active kill triggers: [sync_modules/health_checks.py](../../sync_modules/health_checks.py)
  — kill_trigger thresholds + ESP-aware logic
- ADR-009 (connection state separated from kill state):
  [docs/adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md](../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md)
- Connection state machine plan: [docs/plans/connection-state-machine.md](connection-state-machine.md)
  — Phase 1 retired disconnected_timeout in commit `94fd0fa`
- Master tracker: [docs/plans/INBOX-INTEGRITY-PROGRAM.md](INBOX-INTEGRITY-PROGRAM.md)
- EB-tag cleanup script (pattern for resurrection script):
  [scripts/cleanup_stale_eb_pool_tags.py](../../scripts/cleanup_stale_eb_pool_tags.py)
- 7-page operator reports UI (replaced Slack workflow):
  [charm-email-os/app/reports/](../../charm-email-os/app/reports/)

## 11. Estimated effort

| Phase | Effort | Risk | Dependencies |
|-------|--------|------|--------------|
| Counter-reset sanity check | 30 min | low | none |
| Phase A threshold replay | 1 hr | read-only | counter-reset finding |
| Phase B event-log lookback | 1 hr (only if A inconclusive) | read-only | none |
| Phase C operator decision | meeting | none | A + optional B |
| Resurrection script (write) | 2 hrs | low | Phase C output |
| Resurrection per workspace | 30 min each + review | low (reversible) | script ready |
| Total | ~5–6 hrs work + ops review | | |

## 12. When to pick this back up

The reports UI redesign work is the active priority. After that ships
and operators are using `/reports/*` pages, the bounce-history audit
becomes the next natural workstream (closes a known gap that the audit
script surfaces).

The 241 candidates can sit indefinitely without harm — they're dead in
DB so they don't send mail, and the only externally-visible artifact is
277 stale EB tags that are cosmetic. The cleanup-only path (item 8B
above) can run independently to reduce the cosmetic noise without
touching DB state.
