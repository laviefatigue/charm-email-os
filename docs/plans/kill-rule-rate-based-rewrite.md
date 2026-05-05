---
title: Kill Rule — Rate-Based Rewrite + False-Positive Resurrection
created: 2026-05-04
status: SHIPPED (Phase 1-4 complete, fully load-bearing in production)
supersedes: docs/plans/kill-trigger-accuracy.md (Passes 1-4)
related:
  - docs/concepts/kill-triggers.md
  - docs/adr/adr-010-lifetime-rate-kill-rule-2026-05-04.md
  - docs/work-logs/2026-05-04-kill-rule-rate-rewrite-and-revival.md
  - docs/adr/adr-007-drop-warning-state-2026-04-29.md
  - docs/plans/connection-state-machine.md
---

> **Implementation status (final, 2026-05-04 22:08 UTC):**
>
> Phase 1-4 SHIPPED. Rule is fully load-bearing in production.
>
> - Migration 105 applied (`hard_bounce_rate_lifetime` enum value).
> - Code shipped in commits `5118d59` (rewrite) + `b55531b` (docs) +
>   `f42cf0e` (script fix). Production at commit `b55531bd`.
> - 22 pure-function unit tests + 12 DB integration tests, all green.
> - Pre-2026-05-04 count-based tests in `test_warning_drop.py` marked
>   `@_OBSOLETE_COUNT_RULE` skip.
> - **Phase 2 (Barrena canary):** 35/35 false positives revived.
> - **Phase 3 (fleet revival):** 272/272 false positives revived
>   across Charm, Hello Hero, Linkgraph, SPUI, Search Atlas, Selery,
>   Spout, Stable Kernel. Total 307 inboxes restored.
> - **Phase 4 (load-bearing):** `KILL_RULE_DRY_RUN=false` flipped after
>   one verified dry-run cycle (40 would-kills). 63 legitimate kills
>   queued and processed. Distribution: SKMR 27 (Mary Elzey), Hello
>   Hero 23 (Jessica Jordan), Search Atlas 7, Spout 4, SPUI + Linkgraph
>   1 each.
> - **Phase 5 (cleanup) PENDING.** Removes legacy `_24h` / `_7d`
>   counter columns + the jobs that maintain them. Waits one release
>   cycle for any UI consumers to migrate.
>
> Two deploy-side bugs surfaced and were fixed in passing — see ADR-010
> § "Deploy issues encountered (post-mortem)" and the work log.

# Kill Rule — Rate-Based Rewrite + False-Positive Resurrection

## TL;DR

Replace the windowed-count kill rules (`hard_blocked_24h ≥ N`,
`hard_unknown_24h ≥ N`, etc.) with a single **lifetime-rate** rule that uses
`emails_sent_all_time` + on-demand bounce aggregation from `response_messages`.
Drop all `_24h` / `_7d` rolling counters from the kill path. Resurrect the
~400 fleet inboxes killed by count-based triggers that are still Connected in
EmailBison.

The bug class going away: counter inflation from `GREATEST(stale, fresh)`
reconciliation in `aggregate_bounce_counts_from_events`. With on-demand
aggregates from event timestamps there is no rolling counter to inflate, no
decay job to keep current, no daily reset to skip while the worker is paused.

## Why we're doing this

### Evidence (Barrena workspace, audited 2026-05-04)

- 39/39 Barrena inboxes are marked `dead` in DB.
- 39/39 Barrena inboxes are `Connected` in EmailBison.
- Lifetime bounce rates: 0.50% – 2.67% (fleet aggregate **1.10%**).
- All 39 were queued for kill within a 0.18-second window
  (`2026-04-13T21:35:13.066–.242`) — one health-check tick.
- `kill_queue.trigger_value` for those rows: hard-blocked counts of 2–13 on
  inboxes whose Google daily limit is 20. 13 hard-blocked bounces in 24h on
  a 20/day inbox is mathematically a 65% same-day rate. Those inboxes'
  lifetime rates are 0.5–2.7%. **The "24h" counter was holding many days of
  accumulated bounces.**

### Root cause

[`aggregate_bounce_counts_from_events`](../../sync_modules/health_checks.py)
at line 273:

```python
hard_bounces_24h = GREATEST(COALESCE(sa.hard_bounces_24h, 0), COALESCE(bc.hard_bounces_24h, 0))
```

The counter is monotonically non-decreasing. Bounces only ever add; they
never age out. The 14% daily `decay_weekly_counters` job takes ~46 days to
drain a 50× spike. When kill processing was paused (memory:
[`eb-tagging-paused`](../../C:/Users/ellio/.claude/projects/d--Work-Charm-charm-email-os/memory/eb-tagging-paused.md)
re-enabled 2026-04-13), the daily reset stopped firing and bounces piled up
in the `_24h` field. When the processor resumed, every long-running
healthy inbox crossed `_24h ≥ 2` simultaneously.

### Fleet blast radius (snapshot)

```sql
SELECT trigger_type, status, COUNT(*) FROM kill_queue
WHERE trigger_type IN ('hard_blocked_24h','hard_unknown_24h','hard_bounces_24h')
  AND status = 'flagged'
GROUP BY trigger_type, status;
```

- `hard_blocked_24h` flagged: **235**
- `hard_bounces_24h` flagged: **167**
- `hard_unknown_24h` flagged: **6**
- Subtotal: **408 inboxes** killed by count-based bounce rules and still
  tagged dead in EmailBison. (Cross-reference with `sender_accounts.status =
  'Connected'` to identify resurrection candidates — see Phase 4.)

`spam_complaint` (250 flagged) and `disconnected_timeout` (277 flagged) are
**out of scope** for this plan. Spam complaints are correct kills. The
disconnect-timeout zombies are tracked in
[`zombie-resurrection-from-disconnect-timeout.md`](./zombie-resurrection-from-disconnect-timeout.md).

## Final rule spec (Phase 1 — start simple)

```
For each LIVE inbox:

  IF complaints_lifetime ≥ 1:
    KILL, trigger_type = 'spam_complaint'

  ELSE IF total_sends_lifetime < 20:
    SKIP  # too few sends to evaluate

  ELSE IF (hard_bounces_lifetime / total_sends_lifetime) > 0.05:
    KILL, trigger_type = 'hard_bounce_rate_lifetime'
```

Three branches. No count gates. No windows. No rolling counters. The denominator
is `emails_sent_all_time` (synced from EB, EB is the source of truth). The
numerator is computed on demand from `response_messages.bounce_type IN
('hard_blocked', 'hard_unknown')` — no stored counter to drift.

| Knob | Value | Env var |
|---|---|---|
| Min sends floor | 20 | `KILL_MIN_SENDS_LIFETIME` |
| Mature rate threshold | 5% | `KILL_MATURE_RATE` |
| Spam complaint threshold | 1 | `KILL_THRESHOLD_SPAM` (existing) |

### Boundary cases (test fixtures)

| Inbox shape | Lifetime rate | Verdict |
|---|---|---|
| 1 bnc / 19 sends | 5.3% | skip (< 20 sends) |
| 1 bnc / 20 sends | 5.0% | safe (5.0% not strictly > 5%) |
| 2 bnc / 20 sends | 10.0% | kill |
| 1 bnc / 25 sends | 4.0% | safe |
| 50 bnc / 1500 sends | 3.3% | safe |
| 80 bnc / 1500 sends | 5.3% | kill |
| 100 bnc / 1500 sends | 6.7% | kill |
| 1 spam complaint, any volume | — | spam kill |

### Deferred: meshed signals (Phase 6+, not this rollout)

The "right" long-term system layers complementary signals — see thread
discussion. Deferred to keep Phase 1 minimal and earnable:

- **Recent-rate signal** (e.g., 3-day window > 15%) — catches mature inboxes
  in sudden reputation collapse that lifetime rate would only detect after
  weeks. Computed on demand from event timestamps, no rolling counter.
- **Provider sender-ban code detection** — Microsoft 5.7.501-503/511/606-649/
  703/705/708/750/800 are explicit "your account is banned" signals.
  Currently alert-first per Plan D Pass 3; flip to instant-kill once
  comfortable.

Both are added incrementally after Phase 1 ships and earns its keep.

### What stays unchanged

- **Bounce classification.** `extract_bounce_reason` in
  [`sync_modules/sync_events.py`](../../sync_modules/sync_events.py) keeps
  parsing SMTP codes and writing `bounce_type` ∈ `{hard_blocked,
  hard_unknown, soft_full, soft_temp, unknown}` to `response_messages`.
  Soft bounces are still captured for analytics; they just don't drive
  kills.
- **Spam complaint detection.** `detect_spam_in_response` and the lifetime
  `complaints_lifetime` counter stay. Phrase-match on lead replies remains
  our primary reputation defense.
- **Domain burn logic.** Spam-complaint domain burn evaluation (rate-based
  with 0.3% / 1.0% thresholds, workspace circuit breaker, ESP-aware
  promotion) in [`kill_processor.py`](../../sync_modules/kill_processor.py)
  is unchanged. We only changed *what triggers an inbox kill*; the
  downstream consequences are the same.
- **Connection state separation.** ADR-009 stays. `disconnected_timeout`
  is not a kill trigger; connection state drives the notification ladder.
- **Cross-domain promotion.** Pool promotion logic stays.

## Schema

**No new columns. No migrations.** Use existing fields.

### Denominator: lifetime sends

`sender_accounts.emails_sent_all_time` — synced from EB
`sender.emails_sent_count` on every sender-emails sync. Authoritative
because EB owns the truth for sends.

### Numerator: lifetime hard bounces

Computed on demand from `response_messages`:

```sql
SELECT COUNT(*) FROM response_messages
WHERE sender_account_id = $1
  AND folder = 'bounced'
  AND bounce_type IN ('hard_blocked', 'hard_unknown')
```

No window. No decay. No reset.

### Columns we stop maintaining for kill purposes

These columns can stay (some are read by the UI / reports), but they are
**no longer load-bearing for kill decisions**:

- `hard_bounces_24h`, `hard_blocked_24h`, `hard_unknown_24h`
- `hard_bounces_7d`, `soft_bounces_7d`
- `bounce_rate_7d`, `hard_bounce_rate_7d`, `total_bounce_rate_7d`

Consider these informational-only after rollout. We can drop them in a
follow-up cleanup if no UI consumer remains.

## Code changes

### 1. `sync_modules/health_checks.py`

**Replace `evaluate_inbox_health` (lines ~369-600)** with the 3-branch rule
spec above. Remove:

- The `has_min_send_volume` 24h/7d gate (replaced by single `total_sends_lifetime
  < 20` skip).
- All `hard_blocked_24h`, `hard_unknown_24h`, `hard_bounces_24h` count
  branches.
- `hard_bounce_rate_7d` and `bounce_rate_all_7d` rate branches (replaced
  by single lifetime rate).
- ESP-aware threshold dispatch (`_thresholds_for_esp`). Lifetime rate is
  ESP-agnostic — Postmaster Tools applies the same percentage to Gmail and
  Microsoft.

**Inline the bounce count** inside the per-inbox loop (one query per
inbox, indexed on `(sender_account_id, folder, bounce_type)` — verify
index in Phase 0):

```python
hard_bounces = await self.db.fetchval("""
    SELECT COUNT(*) FROM response_messages
    WHERE sender_account_id = $1
      AND folder = 'bounced'
      AND bounce_type IN ('hard_blocked', 'hard_unknown')
""", inbox['id'])
```

If per-inbox queries are too expensive, replace with a single CTE-style
prefetch in `check_workspace_health`. Decision deferred to Phase 1
benchmarking.

**Remove `aggregate_bounce_counts_from_events` from the kill path.** Either
delete it, or keep it for legacy column maintenance and explicitly note
in a comment that it does not feed kill decisions.

### 2. `sync_modules/health_checks.py` — counter maintenance jobs

`reset_daily_counters` and `decay_weekly_counters` no longer affect kill
decisions. Either:

- **(a) Keep both running** to maintain the `_24h` / `_7d` columns for UI
  consumers that haven't migrated yet.
- **(b) Delete both.** Cleaner; risk is UI surfaces showing stale data.

Recommendation: **(a) for one release cycle**, then audit UI consumers,
then (b).

### 3. `sync_modules/kill_processor.py`

Add `'fresh_inbox_panic'` and `'hard_bounce_rate_lifetime'` to
`INBOX_KILLING_TRIGGERS`. Remove deprecated values (`hard_blocked_24h`,
etc.) from the set; new kills won't carry those trigger types but old
queue rows might still reference them, so keep recognition for backward
compat.

Tag-name mapping (`flagged_{trigger_type}`):

- `flagged_fresh_inbox_panic` (new)
- `flagged_hard_bounce_rate_lifetime` (new)
- `flagged_spam_complaint` (existing)

### 4. `api/routes/health.py` (if applicable)

Search for handlers that filter on `kill_trigger IN
('hard_blocked_24h', ...)`. Keep them for historical display but don't
add the new trigger types to "current kill rules" UI labels until
operator review.

### 5. Documentation

Update [`docs/concepts/kill-triggers.md`](../concepts/kill-triggers.md):

- Replace the ESP-aware count thresholds tables with the single
  lifetime-rate rule.
- Add a "Pre-rewrite history" section linking back to the count-based
  rules for archaeological purposes.
- Update env var table.

## Resurrection (Phase 4 — false-positive recovery)

### Identification query

```sql
WITH bounce_counts AS (
    SELECT sender_account_id,
           COUNT(*) FILTER (WHERE bounce_type IN ('hard_blocked', 'hard_unknown')) AS hard_bnc
    FROM response_messages
    WHERE folder = 'bounced'
    GROUP BY sender_account_id
)
SELECT
    sa.id,
    sa.email_address,
    sa.kill_trigger,
    sa.killed_at::date AS killed,
    sa.status AS conn_status,
    sa.emails_sent_all_time,
    COALESCE(bc.hard_bnc, 0) AS hard_bounces,
    CASE
        WHEN sa.emails_sent_all_time = 0 THEN NULL
        ELSE ROUND(100.0 * COALESCE(bc.hard_bnc, 0) / sa.emails_sent_all_time, 2)
    END AS hard_rate_pct,
    w.workspace_name
FROM sender_accounts sa
JOIN workspaces w ON sa.workspace_id = w.id
LEFT JOIN bounce_counts bc ON bc.sender_account_id = sa.id
WHERE sa.is_active = TRUE
  AND sa.inbox_state = 'dead'
  AND sa.kill_trigger IN ('hard_blocked_24h', 'hard_unknown_24h', 'hard_bounces_24h')
  AND sa.status = 'Connected'              -- still working in EB
  AND sa.complaints_lifetime = 0            -- no spam complaint
  AND sa.emails_sent_all_time >= 20
  AND (100.0 * COALESCE(bc.hard_bnc, 0) / sa.emails_sent_all_time) <= 5.0
ORDER BY w.workspace_name, sa.email_address;
```

This returns inboxes that were killed by a count-based rule, are still
Connected in EB, have no spam complaint, and are healthy under the new
rule. **These are the resurrection candidates.**

### Per-inbox revival action

For each candidate row:

1. **EmailBison untag.** Remove all tags whose name starts with
   `flagged_hard_blocked_24h`, `flagged_hard_unknown_24h`,
   `flagged_hard_bounces_24h`.
2. **Re-tag inbox as live.** Apply the workspace's pool-membership tag
   (whatever the lifecycle_tag_sync uses for live inboxes) and any A-Set
   pool tag.
3. **DB state restore:**
   ```sql
   UPDATE sender_accounts SET
       inbox_state = 'live',
       inventory_lifecycle_status = 'graduated',
       inventory_pool_status = 'deployed',  -- or 'reserve' if domain logic dictates
       killed_at = NULL,
       kill_trigger = NULL,
       updated_at = NOW()
   WHERE id = $1;
   ```
4. **kill_queue cleanup.** Mark the original kill_queue row's `status =
   'cancelled'` and write a `notes` field linking to this resurrection.

Pool-status decision (`deployed` vs `reserve`) follows the existing
`pool_promotion.pick_promotion_candidates` logic — we may need to leave
the inbox at `NULL` and let the next promotion cycle absorb it. Decide
during Phase 4 review.

### Audit log

Every revived inbox writes one row to a new audit table or to
`kill_queue.notes`:

```
revived_at: 2026-05-XX
reviver: laviefatigue (or the script identity)
prior_kill_trigger: hard_blocked_24h
prior_kill_value: 7
prior_kill_at: 2026-04-14
new_rule_verdict: safe (rate=1.10%, sends=1605, hard_bnc=15)
```

## Rollout phases

### Phase 0 — Pre-flight (read-only, today)

1. Verify `response_messages (sender_account_id, folder, bounce_type)`
   index exists. Add migration if not.
2. Run identification query. Capture the count of resurrection candidates
   (expect ~400 across the fleet, ~38 of which are Barrena's).
3. Confirm `emails_sent_all_time` is being updated by the sender-emails
   sync (sample 20 random inboxes, compare to EB
   `sender.emails_sent_count`). If drift > 5%, **stop** and fix sync
   first.
4. Snapshot current state for rollback: dump `sender_accounts.id,
   inbox_state, kill_trigger, killed_at, inventory_pool_status` to a CSV
   under `docs/work-logs/2026-05-XX-pre-rewrite-snapshot.csv`.

### Phase 1 — Code rewrite + dry-run mode

1. Implement the rule rewrite in `health_checks.py`.
2. Add an env-var gate: `KILL_RULE_DRY_RUN=true` (default true on first
   deploy). When set, evaluate the new rule but log decisions instead of
   queueing kills.
3. Deploy to charm-api + sync worker.
4. Watch one full health-check cycle (15 min). Verify the dry-run log
   shows expected counts:
   - **Should-have-killed**: inboxes that meet the new rule (rate-based)
     and were also killed by the old rule. Sanity check: most should be
     spam_complaint or genuinely high-rate inboxes.
   - **Would-NOT-have-killed**: false-positive identification — should
     match the resurrection candidate count.
5. **Gate to Phase 2:** ratio of should-kill : would-not-kill makes sense
   to operator. Slack the summary, request confirmation.

### Phase 2 — Resurrection dry-run on Barrena (canary)

1. Run identification query, filter to Barrena workspace_id.
2. Print the candidate list (expect ~38 — three Barrena inboxes were
   killed for `spam_complaint` and stay dead).
3. Operator visual confirmation: the list matches the EB-truth audit from
   2026-05-04.
4. **Gate to Phase 3:** operator approves Barrena revival.

### Phase 3 — Resurrect Barrena

1. Execute revival action against the Barrena candidates only.
2. Tag manipulation goes through the workspace's EB API key (Plan A
   firewall — never cross-workspace).
3. Run the daily inbox-audit Slack message manually (`scripts/preview_slack_audit_v2.py
   --post`) so the operator can see Barrena now showing live inboxes.
4. **Soak for 24h.** Verify:
   - Revived Barrena inboxes start receiving campaign assignments
     (workspace_writes / campaign attachment).
   - No new kills fired against the revived set under the new rule.
   - EB still shows them Connected.
5. **Gate to Phase 4:** Barrena soak clean.

### Phase 4 — Flip dry-run off + fleet-wide resurrection

1. Set `KILL_RULE_DRY_RUN=false`. Redeploy. New rule is now load-bearing.
2. Run identification query against the rest of the fleet (~370
   candidates). Print to a file under
   `docs/work-logs/2026-05-XX-resurrection-fleet.csv`.
3. Operator review of the file before running the revival batch.
4. Execute revival in **batches of 50 with 5-min pauses** between
   batches. Each batch:
   - Hits one or more workspaces.
   - Uses the workspace-scoped EB API key.
   - Logs to per-workspace audit trail.
5. Final state check: count of `inbox_state='dead' AND kill_trigger IN
   ('hard_blocked_24h', 'hard_unknown_24h', 'hard_bounces_24h')` should
   drop to ~0 (anything left is either spam_complaint, genuinely
   high-rate, or actually disconnected).

### Phase 5 — Cleanup (1 release later)

1. Remove the `KILL_RULE_DRY_RUN` env var and its conditional path.
2. Remove deprecated count branches in `kill_processor.py` if no kill
   queue rows reference them anymore.
3. Audit UI / API consumers of `hard_bounces_24h`, `hard_blocked_24h`,
   etc. Migrate any remaining ones to lifetime-rate fields.
4. Drop or no-op `aggregate_bounce_counts_from_events`,
   `reset_daily_counters`, `decay_weekly_counters` if no longer needed.

## Tests

### Unit (new file `tests/sync_modules/test_evaluate_inbox_health_lifetime.py`)

Each fixture from the boundary-cases table maps to one test:

```python
@pytest.mark.parametrize("hard_bnc,sends,complaints,expected_trigger", [
    (0, 19, 0, None),                          # under floor
    (5, 20, 0, 'fresh_inbox_panic'),           # 25% panic
    (4, 20, 0, None),                          # 20% safe
    (1, 25, 0, None),                          # 4% safe
    (10, 1500, 0, None),                       # 0.67% safe
    (50, 1500, 0, None),                       # 3.3% safe
    (100, 1500, 0, 'hard_bounce_rate_lifetime'), # 6.7% kill
    (11, 30, 0, 'hard_bounce_rate_lifetime'),  # 36.6% kill
    (0, 1500, 1, 'spam_complaint'),            # spam wins regardless
])
async def test_evaluate_inbox_health(...):
```

### Integration

1. **Inflated counter no longer kills.** Seed a sender with
   `hard_blocked_24h = 50` (simulating inflation) but `emails_sent_all_time
   = 1500` and only 5 hard bounces in `response_messages`. Run health
   check. Assert no kill queued.
2. **Resurrection script idempotent.** Run the resurrection action twice;
   second run should be a no-op (no double-tag, no DB error).
3. **Cross-workspace isolation.** Run resurrection against Barrena;
   assert no other workspace's inboxes were touched.

## Monitoring

Add to the daily Slack inbox audit (`sync_modules/slack_audit_v2.py`):

- `revivals_24h` — count of inboxes resurrected in the last 24h.
- `kills_by_trigger_24h` — count of new kills by trigger_type. Should be
  dominated by `spam_complaint` and `hard_bounce_rate_lifetime` after
  rollout. Sustained `fresh_inbox_panic` activity is a signal that warmup
  is misbehaving.

## Rollback

If Phase 1 dry-run shows the new rule mass-killing inboxes (would-kill
count >> spam_complaint baseline), do not flip dry-run off. Investigate
data — likely `emails_sent_all_time` is stale or `response_messages`
bounce counts are off — fix that, re-run dry-run.

If Phase 3 Barrena resurrection misbehaves (e.g., revived inboxes
immediately re-killed, or EB returns an error during un-tag), roll back
that batch:

```sql
-- Per inbox: restore dead state from snapshot
UPDATE sender_accounts SET
    inbox_state = 'dead',
    kill_trigger = '<from snapshot>',
    killed_at = '<from snapshot>'
WHERE id = $1;
```

Re-tag with the original `flagged_*` tag in EB. The pre-rewrite snapshot
CSV from Phase 0 is the source of truth.

## Open questions for the operator

1. **Dry-run gate name** — `KILL_RULE_DRY_RUN` ok, or prefer something
   else?
2. **Pool status on revive** — restore to `deployed` directly, or leave
   `NULL` and let the next pool_promotion cycle decide?
3. **Resurrection identity** — should the audit log attribute revivals
   to a service identity, or to `laviefatigue`?
4. **Soft bounce columns** — keep `soft_bounces_7d` updated for UI, or
   drop?

## Scope explicitly NOT in this plan

- Disconnect-timeout zombies — separate plan.
- Spam complaint detection improvements (JMRP, Postmaster Tools) — out of
  scope.
- Domain burn rule changes — unchanged.
- ESP-aware kill thresholds — collapsed into a single ESP-agnostic rule
  by design.
- Counter column removal (Phase 5 placeholder, not committed yet).
