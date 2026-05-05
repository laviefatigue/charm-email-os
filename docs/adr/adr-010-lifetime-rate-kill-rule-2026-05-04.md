---
title: "ADR-010: Lifetime-Rate Kill Rule (post-2026-05-04 rewrite)"
created: 2026-05-04
status: accepted
deciders: laviefatigue
supersedes:
  - "ADR-005 (differentiated bounce thresholds — count tables now historical)"
  - "ADR-007 (drop warning state — Google ESP-aware count thresholds, replaced by ESP-agnostic lifetime rate)"
related:
  - docs/plans/kill-rule-rate-based-rewrite.md
  - docs/concepts/kill-triggers.md
  - docs/adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md
tags: [adr, kill-triggers, reputation, accepted]
---

# ADR-010: Lifetime-Rate Kill Rule

## Status

**Accepted and fully shipped 2026-05-04.**

- Code committed (`5118d59`) + comprehensive docs (`b55531b`) + script
  fix (`f42cf0e`).
- Migration 105 applied (adds `hard_bounce_rate_lifetime` to
  `kill_trigger_type` enum).
- Deployed to charm-api + emailbison-sync (commit `b55531bd` live).
- Phase 1-4 complete. `KILL_RULE_DRY_RUN=false` flipped at ~22:08 UTC
  after one verified dry-run cycle showed 40 legitimate would-kills.
- 307 false-positive inboxes resurrected (35 Barrena + 272 fleet).
- 63 legitimate kills queued + processed (kill_processor cycle ran
  immediately after flag flip, all `flagged_hard_bounce_rate_lifetime`
  tags applied in EB).

### Deploy issues encountered (post-mortem)

Two unrelated deploy bugs surfaced today and were fixed in passing:

1. **`scripts/coolify.py deploy` defaulted to `force=false`.** Coolify
   reuses cached git state on `force=false`, which silently deployed
   commit `baf90cf7` (the prior commit on master) instead of `5118d59`.
   Diagnosis: production worker logs showed `Health: 11 workspaces, 0
   with triggers [OK]` even though the validator predicted 50+ kills.
   Fix: changed default to `force=true` in commit `f42cf0e`.

2. **Git remote mismatch.** Local `origin` points to
   `laviefatigue/charm-email-os`; production Coolify pulls from
   `HireCharm/charm-email-os`. The kill-rule rewrite was pushed to
   `origin` but not `hirecharm`, so even a `force=true` deploy
   couldn't pick it up. Fix: pushed to both remotes; both now at
   `f42cf0e`. The local working tree retains both remotes (`origin`
   and `hirecharm`) — operators must remember to `git push hirecharm
   master` for production deploys to pick up changes.

## Context

### Trigger incident (2026-04-14)

The Barrena workspace had 39 inboxes queued for kill in a 0.18-second
window (`2026-04-13T21:35:13.066–.242` UTC, all by a single
health-check tick). Production audit on 2026-05-04 confirmed:

- All 39 EB senders are `Connected`.
- Lifetime bounce rates: 0.50% – 2.67% (fleet aggregate **1.10%**).
- Lifetime sends per inbox: 700–1615 (mature, well-warmed Gmail
  workspace OAuth inboxes).
- Industry-healthy. Google Postmaster Tools and AWS SES would not
  flag these.

The `kill_queue` rows show `trigger_value` of 2–13 hard-blocked bounces
"in 24h" on inboxes whose Google daily-send limit is 20. **13 hard-blocked
bounces in 24 hours on a 20/day inbox is mathematically a 65% same-day
rate**, while the inbox's lifetime rate is 0.87%. The "_24h" counter was
not actually 24-hour-bounded — it was holding many days of accumulated
bounces.

### Root cause

`sync_modules/health_checks.py:aggregate_bounce_counts_from_events` used
the pattern:

```sql
hard_blocked_24h = GREATEST(COALESCE(sa.hard_blocked_24h, 0),
                            COALESCE(bc.blocked_24h, 0))
```

This is monotonically non-decreasing — bounces only ever add; they never
age out. When kill processing was paused (memory:
`eb-tagging-paused.md`, re-enabled 2026-04-13), the daily reset
(`reset_daily_counters`) stopped firing while bounces kept accumulating
in `response_messages`. The next reconciliation set the `_24h` field to
the maximum, which by then included weeks of history. When kill
processing resumed, every long-running healthy inbox crossed
`hard_blocked_24h ≥ 2` simultaneously.

The 14% daily decay in `decay_weekly_counters` takes ~46 days to drain
a 50× spike. Daily reset to 0 is the only fast-correcting mechanism, and
it's gated on a worker job that can fail silently.

### Why count-based rules fail structurally on cold outreach

Even with perfect counter maintenance, "≥ 2 hard-blocked bounces in any
24-hour window" eventually fires on every long-running healthy inbox:

- Cold outreach has irreducible background bounce variance (recipient
  policies, tenant rules, anti-spam configs change).
- A Gmail inbox at 20 sends/day across 80 days = 1,600 sends. At a
  healthy 1% hard-blocked rate, that's 16 hard-blocked bounces over
  the inbox's life. **Somewhere in those 80 days, two will land on the
  same calendar day** — pigeonhole is not "if" but "when."
- Microsoft at 2 sends/day pushes detection from days to months but
  the same logic applies.

Count thresholds in any window confuse "concentrated bad day" with
"ongoing reputation damage." The 20-send-floor patch helped but didn't
fix the structural issue.

## Decision

Replace the windowed-count kill rules with a **single ESP-agnostic
lifetime-rate rule**:

```
For each LIVE inbox:

  IF complaints_lifetime ≥ 1:
    KILL, trigger_type = 'spam_complaint'

  ELSE IF emails_sent_all_time < 20:
    SKIP  # insufficient data

  ELSE IF (hard_bounces_lifetime / emails_sent_all_time) > 5%:
    KILL, trigger_type = 'hard_bounce_rate_lifetime'
```

### Numerator: `hard_bounces_lifetime`

Computed on demand from `response_messages` at every health-check tick:

```sql
SELECT COUNT(*) FROM response_messages
WHERE sender_account_id = $1
  AND folder = 'bounced'
  AND bounce_type IN ('hard_blocked', 'hard_unknown')
```

**No stored counter.** No window to drift, no decay to keep current,
no daily reset to skip. The `received_at` timestamps are exact; if
present in the table, the bounce happened.

### Denominator: `emails_sent_all_time`

Synced from EB `sender.emails_sent_count` on every sender-emails sync.
EB owns the truth for sends. Drift verified at < 0.5% across a 12-inbox
sample on 2026-05-04 (Barrena).

### Soft bounces are captured but never kill

`bounce_type IN ('soft_full', 'soft_temp')` rows are still classified
and stored in `response_messages` for analytics. They do not enter the
kill rate calculation. Soft bounces (mailbox-full, temp DNS issues,
TLS hiccups) are not reputation signals.

### Spam complaint is unchanged

`complaints_lifetime ≥ 1 → instant kill` stays. Coverage is poor
(phrase-match on lead replies; no JMRP, no Postmaster Tools — see
`docs/concepts/kill-triggers.md` § HARD CONSTRAINT) but a phrase-match
is high-quality signal when it does fire.

### Removed rules (entire branches deleted from `evaluate_inbox_health`)

- `hard_blocked_24h ≥ N` (was Microsoft 2 / Google 1)
- `hard_unknown_24h ≥ N` (was Microsoft 3 / Google 1)
- `hard_bounces_24h ≥ N` (was Microsoft 2 / Google 1)
- `hard_bounce_rate_7d > 2.0%` (windowed, redundant with lifetime)
- `bounce_rate_all_7d > 5.0%` (included soft bounces)
- `total_sends_24h ≥ 20 OR total_sends_7d ≥ 20` floor (replaced by
  `emails_sent_all_time ≥ 20`)
- `_thresholds_for_esp` ESP dispatch (rule is now ESP-agnostic)

These count-trigger types remain in the `kill_trigger_type` enum and
in `INBOX_KILLING_TRIGGERS` for historical kill_queue / sender_account
rows. New kills emit `hard_bounce_rate_lifetime` or `spam_complaint`
only.

### Thresholds (env-tunable)

| Knob | Default | Env var |
|---|---|---|
| Spam complaint count | 1 | `KILL_THRESHOLD_SPAM` (existing) |
| Min sends to evaluate | 20 | `KILL_MIN_SENDS_LIFETIME` |
| Mature rate threshold | 5% | `KILL_MATURE_RATE` |
| Dry-run flag | true (initial) | `KILL_RULE_DRY_RUN` |

5% chosen to match Google Postmaster Tools / AWS SES "high bounce" range.
Below this is normal cold-outreach variance.

## Consequences

### Eliminated

- **Counter inflation bug class.** No stored rolling counter anywhere
  in the kill-decision path. Cannot replay the 2026-04-14 incident.
- **Reset-job dependency.** `reset_daily_counters` and
  `decay_weekly_counters` no longer affect kill decisions. They still
  run for legacy column maintenance (UI consumers); will be removed in
  a follow-up cleanup.
- **ESP-aware threshold dispatch.** A single rate threshold replaces
  the Google 1/1/1 vs Microsoft 2/3/2 dispatch. Postmaster Tools
  applies the same rate to both ESPs; we do too.
- **Windowed-counter aggregation job.**
  `aggregate_bounce_counts_from_events` is no longer load-bearing for
  kills. It can stay for legacy columns or be deleted in cleanup.

### Trade-offs

- **Mid-life-collapse detection is slower.** A mature inbox at 1.0%
  lifetime rate that suddenly bombs out at 30% will take ~3 weeks to
  cross 5% lifetime. Mitigations:
  - `spam_complaint` instant-kill catches active reputation damage.
  - EB's connection-state machine catches provider hard rejections.
  - Future Phase 6 may add a 3d-window signal computed on demand from
    event timestamps (no stored counter, no inflation risk).

- **Slightly more aggressive on small denominators.** `2 hard bounces /
  20 sends = 10%` kills under the new rule. Pre-rewrite this required
  2 bounces in any 24h window with the 20-send floor, which was
  comparable. Net effect: similar.

- **No early panic for catastrophic bombing in first 20 sends.** An
  inbox that produces 19 bounces in its first 19 sends gets skipped
  (under floor) until send #20. Acceptable: that inbox isn't going
  anywhere if every send bounces, and EB's connection state will
  catch the underlying provider problem.

### Resurrection of false-positive kills

The validator at `scripts/validate_new_kill_rule.py` audited the entire
fleet against the new rule on 2026-05-04. Identified 309 inboxes that
had been killed by count-based rules, are still `Connected` in EB, have
no spam complaint, and read as healthy under the new rule. Resurrected
via `scripts/resurrect_false_positive_kills.py`:

- **Phase 2 (Barrena canary):** 35/35 revived. Validator confirms 0
  remaining false positives.
- **Phase 3 (fleet-wide):** 272/272 revived across Charm, Hello Hero,
  Linkgraph, SPUI, Search Atlas, Selery, Spout, Stable Kernel.

Total: **307 inboxes restored to live state** with healthy rates,
flagged tags removed in EB, `live` tag re-applied, `kill_queue` rows
marked `cancelled` with audit notes.

### Legitimate kills now queued

The same validator identified 58 inboxes currently `live` in DB whose
lifetime rate exceeds 5%. Dominant patterns:

- **Stable Kernel Market Research / Mary Elzey** — 21 inboxes at 8–25%
  lifetime rate. Operator had previously flagged these as
  "should-have-been-killed."
- **Hello Hero / Jessica Jordan** — 23 inboxes at 5–10% lifetime rate
  spanning 6 hellohero domains (`gohellohero`, `tryhellohero`, etc.).
  Coherent list-quality pattern.
- **Scattered single-inbox cases** in Search Atlas, Selery, Linkgraph,
  Spout, SPUI.

These will fire as `flagged_hard_bounce_rate_lifetime` once
`KILL_RULE_DRY_RUN` flips to `false`.

## Verification

- 22 pure-function unit tests passing
  (`tests/test_kill_rule_unit.py`) covering boundary cases including a
  named regression test for the Barrena shapes (1500-send / 0.5-1.7%
  rate inboxes must not kill).
- 12 DB-integration tests
  (`tests/test_kill_rule_lifetime.py`) covering end-to-end behavior
  with real Postgres + `response_messages`. Skip without Docker; pass
  in CI.
- Pre-rewrite count-based tests in `tests/test_warning_drop.py` marked
  `@_OBSOLETE_COUNT_RULE` skip with deprecation note.
- Production validator (`scripts/validate_new_kill_rule.py`) ran
  fleet-wide read-only audit before deploy. 309 false positives + 50
  legitimate new-kills identified; resurrection executed in batches
  with per-action audit log; post-resurrection re-validation shows
  steady state.

## Notes

### What stays from prior ADRs

- **ADR-006 (tagging-kill overhaul):** workspace-scoped EB API keys,
  per-workspace `process_workspace_queue`, cross-domain reserve
  promotion — all unchanged.
- **ADR-009 (connection state separated from kill state):** disconnect
  is not a kill trigger. Notification ladder owns it.
- **Domain burn evaluation:** rate-based with 0.3% / 1.0% thresholds,
  workspace circuit breaker, ESP-aware promotion logic — unchanged.

### Pre-existing issues surfaced

The migration runner (`api/migration_runner.py`) has been stuck on
`076_domain_level_ab_sets.sql` (CHECK constraint failure on existing
data) for some time. This blocks 18+ pending migrations from auto-applying
on charm-api startup. Migration 105 was applied directly via the admin
endpoint; the rest of the backlog needs separate attention.
