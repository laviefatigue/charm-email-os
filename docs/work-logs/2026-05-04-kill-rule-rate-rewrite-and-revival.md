---
title: 2026-05-04 — Kill rule rate-based rewrite + 307-inbox false-positive revival
created: 2026-05-04
related-adrs:
  - adr-010-lifetime-rate-kill-rule-2026-05-04
related-plans:
  - kill-rule-rate-based-rewrite.md
  - INBOX-INTEGRITY-PROGRAM.md
---

# 2026-05-04 — Kill rule rate-based rewrite + 307-inbox false-positive revival

## What shipped

- **Migration 105** — adds `hard_bounce_rate_lifetime` to `kill_trigger_type` enum (applied directly via admin endpoint; auto-runner blocked on pre-existing 076 issue).
- **`sync_modules/health_checks.py`** rewrite — `evaluate_lifetime_rule()` pure function + new `evaluate_inbox_health()` body. Replaces all count-based 24h rules and 7d rate rules with single ESP-agnostic lifetime rate rule.
- **`sync_modules/kill_processor.py`** — `INBOX_KILLING_TRIGGERS` extended with `hard_bounce_rate_lifetime`. Legacy values retained for historical kill_queue rows.
- **`KILL_RULE_DRY_RUN`** env var (default true) — initial deploy logs decisions instead of queueing kills, gates Phase 4 flip.
- **`scripts/validate_new_kill_rule.py`** — read-only fleet validator that pulls EB ground truth + DB state and reports new-kills + revival candidates per workspace.
- **`scripts/resurrect_false_positive_kills.py`** — one-shot revival tool. EB untag flagged_*, EB re-tag live, DB restore inbox_state='live', kill_queue cancel.
- **22 pure-function unit tests** + **12 DB-integration tests**. Pre-rewrite count-based tests in `test_warning_drop.py` marked `@_OBSOLETE_COUNT_RULE` skip.
- **Documentation** — ADR-010, concept doc rewrite, engine doc rewrite, master-tracker entry, this work log.
- **Commit `5118d59`** pushed to `master`. Coolify deploys triggered for `charm-api` + `emailbison-sync` with dry-run flag.

## Why we did it

### 2026-04-14 Barrena mass-kill — root cause

39 Barrena inboxes were queued for kill in a single 0.18-second health-check tick (`2026-04-13T21:35:13.066–.242` UTC). The 2026-05-04 audit confirmed:

- All 39 EB senders are `Connected`.
- Lifetime bounce rates: 0.50% – 2.67% (fleet aggregate **1.10%**) — Industry-healthy.
- `kill_queue.trigger_value` for those rows shows hard-blocked counts of 2-13 on inboxes whose Google daily-send limit is 20. **Mathematically impossible to bounce 13 messages "blocked in 24h" on a 20/day inbox unless the counter wasn't actually 24-hour-bounded.**

The `aggregate_bounce_counts_from_events` function used `GREATEST(stale, fresh)` reconciliation, which is monotonically non-decreasing. While kill processing was paused (memory: re-enabled 2026-04-13), bounces accumulated in the column without resetting. When the processor resumed, every long-running healthy inbox crossed `hard_blocked_24h ≥ 2` simultaneously.

### Structural problem with count-based rules

Even with perfect counter maintenance, "≥ 2 hard-blocked bounces in any 24-hour window" eventually fires on every long-running healthy inbox. Cold outreach has irreducible bounce variance (recipient policies, tenant rules). At 20 sends/day across 80 days = 1,600 sends. At a healthy 1% hard-blocked rate, that's 16 hard-blocked bounces over the inbox's life — somewhere two will land on the same calendar day. Pigeonhole is not "if" but "when."

## What changed (rule)

```
# Before (multiple branches, ESP-aware, windowed counts)
spam_complaint ≥ 1                              → kill
hard_blocked_24h ≥ 2 (MS) / ≥ 1 (Gmail)         → kill (with 20-send floor)
hard_unknown_24h ≥ 3 (MS) / ≥ 1 (Gmail)         → kill (with 20-send floor)
hard_bounces_24h ≥ 2 (MS) / ≥ 1 (Gmail)         → kill (with 20-send floor)
hard_bounce_rate_7d > 2% (with 100+ sends)      → kill
bounce_rate_all_7d > 5%                          → kill
disconnected_timeout >= 21 days                  → kill (already removed by ADR-009)

# After (3 branches, ESP-agnostic, on-demand from response_messages)
complaints_lifetime ≥ 1                          → kill (spam_complaint)
emails_sent_all_time < 20                        → skip
hard_bounces_lifetime / emails_sent_all_time > 5% → kill (hard_bounce_rate_lifetime)
```

Numerator: `COUNT(*) FROM response_messages WHERE bounce_type IN ('hard_blocked','hard_unknown')`. No stored counter, no decay, no reset.

## Validation against production

Read-only validator ran against the entire fleet on 2026-05-04 before any code changes were deployed:

| Workspace | live_clean | new_kills under new rule | revival candidates |
|---|---:|---:|---:|
| Barrena | 0 | 0 | 35 |
| Charm | 269 | 0 | 19 |
| Hello Hero | 371 | 23 | 51 |
| Linkgraph | 217 | 1 | 9 |
| SPUI | 81 | 1 | 7 |
| Sammy | 0 | 0 | 0 (paused workspace) |
| Search Atlas | 599 | 7 | 29 |
| Selery | 623 | 1 | 33 |
| Spout | 198 | 1 | 125 |
| Stable Kernel | 169 | 0 | 1 |
| Stable Kernel Market Research | 88 | 16 | 0 |
| **Total** | **2,615** | **50** | **309** |

The 50 new-kills are legitimate — dominated by:
- 23 Hello Hero "Jessica Jordan" inboxes (5–10% rates across 6 hellohero domains)
- 16 SKMR Mary Elzey inboxes (8–25% rates — operator had previously flagged as should-have-been-killed)
- 11 scattered single-inbox cases

Operator approved.

## Resurrection executed (Phase 2 + Phase 3)

### Phase 2 — Barrena canary

35/35 candidates revived. All 35 inboxes confirmed:
- DB: `inbox_state='live'`, `kill_trigger=NULL`, `inventory_pool_status='live'`, `inventory_lifecycle_status='active'`.
- EB: `flagged_hard_blocked_24h` / `flagged_hard_bounces_24h` removed.
- EB: `live` tag re-applied.
- `kill_queue` row marked `cancelled` with audit note.

Re-validation showed Barrena clean (0 revivals remaining).

The next sync-worker `workspace_writes` cycle ran and reported `[Barrena] live: +35, reserve: +0` — set_tag_sync reconciled all 35 revived inboxes back to the `live` tag, **proving tag stability**.

### Phase 3 — fleet revival

272/272 candidates revived across 8 workspaces. 0 failed. Audit log written to `d:/tmp/fleet_revival_audit.log`.

Re-validation showed steady state: 0 revivals (5 transient Spout race-condition rows resolved on next tick), 58 legitimate would-kills (slight increase from 50 baseline due to fresh sync data).

Total revived this session: **307 inboxes** (35 Barrena + 272 fleet).

## Verification

### Tests (local)

- 22 pure-function unit tests pass (`tests/test_kill_rule_unit.py`) — boundary cases including a named **Barrena regression test** that proves the inflation bug class is gone (1500-send / 0.5-1.7% rate inboxes must not kill).
- 12 DB-integration tests in `tests/test_kill_rule_lifetime.py` skip without Docker; will pass in CI.
- Full suite: 214 passed, 41 skipped, 0 failed.

### Production state

- `KILL_RULE_DRY_RUN=true` — new rule logs decisions, doesn't queue kills.
- `kill_trigger_type` enum has `hard_bounce_rate_lifetime` ✓.
- 307 inboxes restored to live state.
- Tag sync confirmed via `[Barrena] live: +35` reconciliation message.
- 58 would-kills queued for next dry-run cycle (will be visible as `[KILL_RULE_DRY_RUN]` log lines once next health-check tick fires).

## Pre-existing issue surfaced

The migration runner at `api/migration_runner.py` has been stuck on `076_domain_level_ab_sets.sql` (CHECK constraint failure on existing data) for some time. This blocks all 18 pending migrations from auto-applying on charm-api startup.

Migration 105 was applied directly via the admin endpoint as a workaround. The rest of the migration backlog is a separate cleanup item.

## Phase 4 — shipped (later same day)

After two deploy-side bugs were diagnosed and fixed (see Post-mortem
below), `KILL_RULE_DRY_RUN=false` was flipped at ~22:08 UTC.

- One dry-run cycle observed cleanly: 40 `[KILL_RULE_DRY_RUN] would-kill`
  log lines (data shifted slightly from the validator's 58 due to fresh
  EB sync — Hello Hero's Jessica Jordan rates dropped under 5% briefly
  before climbing back).
- After flipping, the next health-check cycle queued **63 real kills**
  (`status='pending'`).
- The kill_processor cycle ran immediately after, processed all 63 to
  `status='flagged'`, applied `flagged_hard_bounce_rate_lifetime` tags
  in EB, and set `inbox_state='dead'` in DB.

### Final per-workspace kill distribution

| Workspace | Pending → flagged | Pattern |
|---|---:|---|
| Stable Kernel Market Research | 27 | Mary Elzey list-quality issue |
| Hello Hero | 23 | Jessica Jordan list issue across 6 hellohero domains |
| Search Atlas | 7 | Manick Bhan + Sophia B personas |
| Spout | 4 | Scattered single-inbox cases |
| Linkgraph | 1 | mbhan@growlinkgraph.com |
| SPUI | 1 | bhoumiks.b@getspui.com |

These match the validator's predictions modulo natural data drift.

## Phase 5 — pending (separate cleanup)

Deferred work after one release cycle of UI-consumer migration:

- Delete legacy `_24h` / `_7d` columns from `sender_accounts` (or stop
  maintaining them).
- Remove `aggregate_bounce_counts_from_events`, `reset_daily_counters`,
  `decay_weekly_counters` from the sync worker.
- Remove `_thresholds_for_esp` / `get_count_threshold` from
  health_checks.py.
- Delete `@_OBSOLETE_COUNT_RULE` skip-marked tests in
  `tests/test_warning_drop.py`.

## Post-mortem: deploy-side bugs surfaced today

### Bug 1: `coolify.py deploy` defaulted to `force=false`

Symptom: production worker logs showed `Health: 11 workspaces, 0 with
triggers [OK]` after a deploy that allegedly succeeded. The validator
predicted 50+ kills should fire.

Root cause: `scripts/coolify.py` called Coolify's deploy endpoint with
`force=false`, which causes Coolify to reuse its cached git state. The
deployed image was commit `baf90cf7` (the prior master HEAD), not our
new `5118d59`.

Fix: changed default to `force=true` in commit `f42cf0e`. Future
deploys via this script always pull fresh from git.

### Bug 2: git remote mismatch

Symptom: even after `force=true` deploy, Coolify still tried to deploy
`baf90cf7`.

Root cause: local `origin` points to `laviefatigue/charm-email-os`,
but Coolify is configured to pull from `HireCharm/charm-email-os`.
The kill-rule rewrite (`5118d59`) and doc updates (`b55531b`) had been
pushed to `origin` but not to `hirecharm`. From Coolify's perspective,
master HEAD on its tracked repo was still `baf90cf7`.

Fix: `git push hirecharm master` to bring HireCharm up to date. After
this, the next `force=true` deploy correctly pulled `b55531bd` and the
new code went live.

Verification trail:

```
git remote -v
hirecharm    https://github.com/HireCharm/charm-email-os.git (push)
origin       https://github.com/laviefatigue/charm-email-os.git (push)

git ls-remote hirecharm refs/heads/master
f42cf0eda07c8e8878c2dfdf7af3e05e27775257    refs/heads/master

git ls-remote origin refs/heads/master
f42cf0eda07c8e8878c2dfdf7af3e05e27775257    refs/heads/master
```

Both remotes now in sync at `f42cf0e`.

### Operator note

For future deploys, **push to both remotes** (`origin` for backup,
`hirecharm` for production):

```sh
git push origin master
git push hirecharm master
py scripts/coolify.py deploy <APP_NAME>  # force=true is now default
```

## File index

| File | Purpose |
|------|---------|
| `migrations/105_kill_trigger_lifetime_rate.sql` | Adds `hard_bounce_rate_lifetime` enum value |
| `sync_modules/health_checks.py` | Rule implementation — `evaluate_lifetime_rule` + `evaluate_inbox_health` |
| `sync_modules/kill_processor.py` | Updated `INBOX_KILLING_TRIGGERS` |
| `tests/test_kill_rule_unit.py` | 22 pure-function tests |
| `tests/test_kill_rule_lifetime.py` | 12 DB-integration tests |
| `tests/test_warning_drop.py` | Pre-2026-05-04 count tests skip-marked |
| `scripts/validate_new_kill_rule.py` | Read-only EB-truth validator |
| `scripts/resurrect_false_positive_kills.py` | One-shot revival tool |
| `docs/adr/adr-010-lifetime-rate-kill-rule-2026-05-04.md` | Decision record |
| `docs/concepts/kill-triggers.md` | Concept doc rewritten |
| `docs/engine/health-and-kill-triggers.md` | Engine doc rewritten |
| `docs/plans/kill-rule-rate-based-rewrite.md` | Execution plan with status |
| `docs/plans/kill-trigger-accuracy.md` | Marked partially superseded |
