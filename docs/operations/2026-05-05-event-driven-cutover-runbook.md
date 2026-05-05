---
title: 2026-05-05 Event-Driven Cutover Runbook
created: 2026-05-05
audience: operator deploying via Coolify
companion-docs:
  - docs/plans/event-driven-architecture.md (master plan + gates)
  - docs/work-logs/2026-05-05-migration-unblock-and-event-driven-planning.md
  - apps/incubation-watcher/HANDOFF.md (v1 invocation model)
---

# 2026-05-05 Event-Driven Cutover Runbook

> **Why methodic.** Two independent flips, in this order:
>
>   1. **incubation-watcher Phase 4** — graduation traffic shifts from
>      `lifecycle_tag_sync` (in-process, in `emailbison-sync` worker) to
>      the standalone `incubation-watcher` Coolify service.
>   2. **EVENT_DRIVEN_ENABLED=true** — Tier 1 trigger handlers + Tier 2
>      tag-op worker activate. New event-log rows appear.
>
> Each flip is independently rollback-able. Flip #1 must reach the 48h
> soak gate before flip #2 even gets considered. Do NOT combine them.

---

## 0. Pre-flight (5 min)

### 0.1 Branch + commit state

The event-driven work lives on `feature/event-driven-architecture`, NOT
master. Confirm:

```bash
git fetch origin
git log --oneline origin/feature/event-driven-architecture | head -8
```

Expect (top-down):
- `bb50b78 feat(event-driven): Phase 4 — TagOpWorker (Tier 2)`
- `34089bc feat(event-driven): Phase 3 — single-row promote_to_target`
- `e71cb94 feat(event-driven): Phase 2 — handlers + HANDLER_REGISTRY`
- `df06e85 feat(event-driven): Phase 1 — event_log + triggers + listener`

Plus the (uncommitted as of this writing) Phase 5 wiring of `EventListener`
into `emailbison_sync_worker.py`. Commit that before deploying.

### 0.2 Baseline numbers — capture FIRST

```bash
psql "$DATABASE_URL" <<'SQL'
-- B1: graduation throughput last 7d (lifecycle_tag_sync only — pre-cutover)
SELECT w.workspace_name, COUNT(DISTINCT irh.target_inbox_email) AS recent_graduations
FROM inbox_rotation_history irh
JOIN workspaces w ON irh.workspace_id = w.id
WHERE irh.rotation_type = 'graduate'
  AND irh.triggered_by = 'lifecycle_tag_sync'
  AND irh.executed_at > NOW() - INTERVAL '7 days'
  AND w.is_active = TRUE
GROUP BY w.workspace_name
ORDER BY recent_graduations DESC;

-- B2: overdue incubating (must be 0 — the parity signal)
SELECT w.workspace_name, COUNT(*) AS overdue_incubating
FROM workspaces w
JOIN sender_accounts sa ON sa.workspace_id = w.id
WHERE w.is_active = TRUE AND sa.is_active = TRUE
  AND sa.inbox_state = 'live' AND sa.status = 'Connected'
  AND sa.inventory_lifecycle_status = 'incubating'
  AND sa.warmup_enabled = TRUE
  AND sa.warmup_enabled_since IS NOT NULL
  AND sa.warmup_enabled_since < NOW() - INTERVAL '20 days'
GROUP BY w.workspace_name HAVING COUNT(*) > 0;

-- B3: event_log row count by status. Pre-cutover the table does NOT exist
--     on master/production; it ships with migration 107 on the first
--     charm-api deploy after merge.
SELECT to_regclass('public.event_log') AS exists;
-- If non-null, also: SELECT status, COUNT(*) FROM event_log GROUP BY status;
SQL
```

Save the output. This is your "before" reference.

**Reference values from 2026-05-05 baseline (verified against production):**
- B1: Charm 248, SKMR 94, Sammy 5, Spout 1 = 348 graduations / 7d
- B2: **0 rows** (clean parity — incubation-watcher would graduate nothing
  lifecycle_tag_sync hasn't already handled)
- B3: **`event_log` table does not exist on production yet.** Migrations
  107 + 108 are on `feature/event-driven-architecture` only. They apply
  on the first `charm-api` deploy after merge — see §3.2.
- Production `_migrations` table uses column `name` (not `version`);
  highest applied is `105_kill_trigger_lifetime_rate.sql` as of 2026-05-05.

### 0.3 Coolify access

```bash
py scripts/coolify.py list-apps
```

Should list `emailbison-sync`, `incubation-watcher`, `charm-api`, and the
purchase/strategy/domain workers. If anything errors, **STOP** — fix
Coolify access first.

---

## 1. Cutover order — RATIONALE

| # | Action | Risk | Why this order |
|--:|--------|------|----------------|
| 1 | incubation-watcher: 24h shadow-compare | ZERO — read-only | Final receipts before flipping APPLY=true |
| 2 | incubation-watcher: APPLY=true (per-workspace) | LOW — idempotent with lifecycle_tag_sync | Both modules can write the same graduations; EB returns 200 OK on duplicates |
| 3 | 48h soak with both running | LOW | Watch for divergence in `inbox_rotation_history.triggered_by` distribution |
| 4 | Drop graduate branch from `lifecycle_tag_sync` | LOW | Reduces double-write traffic; incubation-watcher becomes sole source |
| 5a | Merge feature branch → master | ZERO — code only | Land Phase 1-5 commits on master. |
| 5b | Deploy **charm-api** (NOT emailbison-sync first) | LOW | charm-api owns the migration runner; 107 + 108 apply on its boot. emailbison-sync would crash on listener startup if migrations weren't there yet. |
| 5c | Verify event_log + 7 triggers exist (§3.3) | ZERO — read-only | Schema gate before flipping anything. |
| 5d | Deploy emailbison-sync with flag OFF | LOW | Code reaches prod with `EVENT_DRIVEN_ENABLED=false`. Pure no-op. |
| 6 | Set `EVENT_DRIVEN_ENABLED=true` in emailbison-sync env | MEDIUM | Tier 1 listener activates. Watch event_log fill. |
| 7 | 7-day shadow soak with co-execution | LOW | Tier 2 (tag_op_worker) and `set_tag_sync` both run. Both idempotent. |
| 8 | Drop `set_tag_sync` runs (Gate 6) | LOW | Worker becomes sole tag-write authority |

Do NOT skip steps 3 or 7. The soak is what the watchdog (Tier 1) and
audit log (Tier 2) get to actually observe in production traffic. No
synthetic test replaces this.

---

## 2. Phase 1 — Incubation-watcher cutover (48h)

### 2.1 Pre-flip: 24h shadow-compare

For each workspace with active graduations (Charm, Stable Kernel Market
Research, Sammy, Spout):

```bash
py scripts/coolify.py exec incubation-watcher \
  incubation-watcher shadow-compare \
    --workspace Charm \
    --since 2026-05-04T00:00:00Z
```

> **NB on the CLI's exit-code semantics.** The CLI flags ANY non-empty
> set difference as divergence — including `actual_only` rows. But
> `actual_only` is **structural**, not a bug: by the time you query, the
> rows lifecycle_tag_sync just graduated have left `inventory_lifecycle_status='incubating'`
> and so no longer match the watcher's predicate. Read the CLI output
> carefully:
>
>   - `watcher_only > 0` → REAL divergence. The watcher would graduate
>     rows the existing module is NOT graduating. **STOP and investigate.**
>   - `actual_only > 0` and `watcher_only == 0` → expected. The existing
>     module is keeping pace; nothing the watcher would catch is being missed.
>     **Safe to proceed.**
>
> Pre-flight on 2026-05-05 returned `watcher_only=0` for all 4 workspaces,
> with `actual_only` matching the 24h graduation throughput (Charm 3,
> Spout 1, SKMR 0, Sammy 0). Receipts: `d:/tmp/shadow_compare_per_workspace.py`.

**Pass condition (rephrased):** `watcher_only == 0` for every workspace.
Treat any CLI exit code as informational; verify the count yourself.

If `watcher_only > 0`: the watcher's candidate set has rows the
existing module hasn't caught. Investigate BEFORE flipping. Likely
causes:
- Workspace's package_size changed in the window (target target_live_count drift)
- A graduate was reverted manually (rare; check `inbox_rotation_history` for `rotation_type='revert'`)
- A `business_days_elapsed` boundary case at exactly 14 days

If exit code 2: config error. Check DATABASE_URL + EMAILBISON_API_URL in
the incubation-watcher service env.

### 2.2 Flip APPLY=true (per-workspace, ONE AT A TIME)

Start with the smallest workspace by graduation throughput (Spout).

```bash
# Coolify: emailbison-sync env
py scripts/coolify.py env-set emailbison-sync \
  LIFECYCLE_TAG_SYNC_GRADUATE_DISABLED_FOR_WORKSPACES=Spout

# Coolify: incubation-watcher invocation
# Per HANDOFF.md §6, v1 is operator-invoked. Run:
py scripts/coolify.py exec incubation-watcher \
  incubation-watcher run --workspace Spout --apply
```

Watch the output. Expect either:
- `result: {'graduated': 0, 'dry_run': 0}` (no candidates this cycle), OR
- `result: {'graduated': N}` with each row marked `[OK]`

If any row is `[FAIL]` or `[ORPHAN]`: investigate, do not proceed to
larger workspaces.

### 2.3 Promote to remaining workspaces

Once Spout is stable for 6h with 0 errors:

```bash
py scripts/coolify.py env-set emailbison-sync \
  LIFECYCLE_TAG_SYNC_GRADUATE_DISABLED_FOR_WORKSPACES="Spout,Sammy,Stable Kernel Market Research,Charm"

# Then run incubation-watcher for each, ideally on a cron loop.
# v2 of incubation-watcher will daemonize; v1 needs manual cycles.
```

### 2.4 48h soak — monitor

```sql
-- Should be 0 across the soak window.
SELECT w.workspace_name, COUNT(*) AS overdue_incubating
FROM workspaces w
JOIN sender_accounts sa ON sa.workspace_id = w.id
WHERE w.is_active = TRUE AND sa.is_active = TRUE
  AND sa.inbox_state = 'live' AND sa.status = 'Connected'
  AND sa.inventory_lifecycle_status = 'incubating'
  AND sa.warmup_enabled_since < NOW() - INTERVAL '20 days'
GROUP BY w.workspace_name HAVING COUNT(*) > 0;

-- Recent triggered_by distribution.
-- During 48h soak: expect mix of 'lifecycle_tag_sync' AND 'incubation_watcher'.
-- After soak completes: expect 'incubation_watcher' only.
SELECT triggered_by, COUNT(*)
FROM inbox_rotation_history
WHERE rotation_type = 'graduate'
  AND executed_at > NOW() - INTERVAL '24 hours'
GROUP BY triggered_by;
```

### 2.5 Drop graduate branch from lifecycle_tag_sync

After 48h clean:

```bash
git checkout master
# Edit sync_modules/lifecycle_tag_sync.py — remove the graduate branch
# (the LIFECYCLE_TAG_SYNC_GRADUATE_DISABLED_FOR_WORKSPACES path becomes the
# default and the workspace allowlist gate gets removed)
git commit -m "chore(lifecycle): drop graduate branch — owned by incubation-watcher"
```

Deploy via Coolify. After this, `LIFECYCLE_TAG_SYNC_GRADUATE_DISABLED_FOR_WORKSPACES`
env can be removed.

### 2.6 Rollback (Phase 1)

If anything goes sideways during the 48h soak:

```bash
py scripts/coolify.py env-unset emailbison-sync \
  LIFECYCLE_TAG_SYNC_GRADUATE_DISABLED_FOR_WORKSPACES
py scripts/coolify.py deploy emailbison-sync
```

`lifecycle_tag_sync` resumes graduating immediately. Stop running
`incubation-watcher run --apply` until you've root-caused.

The incubation-watcher service itself stays up — it's just dormant
again (per v1 HANDOFF.md §6, no daemon mode).

---

## 3. Phase 2 — Event-driven Tier 1 cutover

**Pre-condition:** Phase 1 above is complete, 48h soak is clean,
`incubation-watcher` is sole graduator. Don't start Phase 2 until then.

### 3.1 Merge feature branch to master

```bash
git checkout master
git pull origin master
git merge --no-ff origin/feature/event-driven-architecture
# Resolve conflicts if any (event-driven is mostly additive; the only
# touched-file overlap is emailbison_sync_worker.py)
```

Expected diff in `emailbison_sync_worker.py`:
- New env: `EVENT_DRIVEN_ENABLED` (default `false`)
- New fields: `self.event_listener`, `self._event_tasks`
- New methods: `_start_event_driven`, `_stop_event_driven`
- Boot log: `Event-driven (Tier 1 listener): OFF`
- New poll loop branch: `run_tag_op_drain` (already merged in Phase 4 commit)

### 3.2 Deploy charm-api FIRST — migrations apply on its boot

The migration runner (`api/migration_runner.py`) is invoked from
`api/main.py` startup. **emailbison-sync does NOT run migrations**;
its Dockerfile copies `migrations/` only for reference. So the order
matters: deploy charm-api first, let it apply 107 + 108, then deploy
emailbison-sync.

```bash
git push origin master
py scripts/coolify.py deploy charm-api --force
```

Watch charm-api logs:

```
INFO: Found 2 pending migration(s)
INFO: Applied migration: 107_event_log.sql
INFO: Applied migration: 108_event_triggers.sql
INFO: Applied 2 database migration(s)
```

If anything other than this prints, **STOP**. Migration failures are
caught + logged but the API will still start. Don't proceed until both
migrations show in `_migrations` (see §3.3).

### 3.3 Pre-flip dry-run: confirm schema state

```sql
-- 107 + 108 applied?  Note: column is `name`, not `version`.
SELECT name, applied_at FROM _migrations
WHERE name IN ('107_event_log.sql', '108_event_triggers.sql')
ORDER BY name;

-- event_log table exists?
SELECT to_regclass('public.event_log') AS exists;
-- Expect: 'event_log' (NULL means migration didn't apply)

-- 7 triggers wired? Note: trigger names use `trg_` prefix per migration
-- 108. Each trigger fires emit_event() which writes event_log + pg_notify.
SELECT tgname, tgrelid::regclass AS tbl, tgenabled
FROM pg_trigger
WHERE tgname IN (
  'trg_response_messages_bounce_observed',
  'trg_kill_queue_pending',
  'trg_sender_accounts_died',
  'trg_sender_accounts_pickup',
  'trg_sender_accounts_pool_changed',
  'trg_domains_burned',
  'trg_workspaces_package_assigned'
)
ORDER BY tgname;
```

Expect:
- 2 migrations applied
- `event_log` regclass is non-null
- 7 triggers (one per registered handler: bounce_observed, kill_queued,
  inbox_died, inbox_pickup, pool_changed, domain_burned, package_assigned)
- All `tgenabled='O'` (origin/enabled)

> **NB:** Triggers fire regardless of `EVENT_DRIVEN_ENABLED`. Once 108
> applies, every bounce/kill/pool-change/etc writes a row to event_log
> (status='emitted') and emits pg_notify. With the listener off, those
> rows accumulate harmlessly — when you flip the flag, the listener's
> `_drain_pending` catch-up logic processes them in `emitted_at` order.
> Expect event_log to gain rows immediately after this step.

If any of these fail: do NOT deploy emailbison-sync. Re-deploy
charm-api with `--force` to retry the migrations.

### 3.4 Deploy emailbison-sync with flag OFF — verify no behavior change

```bash
py scripts/coolify.py deploy emailbison-sync --force
```

In emailbison-sync logs (first poll cycle, ~30s after deploy):

```
[<timestamp>] EmailBison Sync Worker starting...
  Event-driven (Tier 1 listener): OFF
  ...
[<timestamp>] Worker initialized successfully
```

The `OFF` line is the boot signal that confirms the flag is correctly
read. **STOP if this line says ON unexpectedly** — env var leaked.

Watch logs for 30 min. Expected: no event-driven log lines, polling
behaves exactly as before. Tag op drain prints a message every 30 min
saying it touched 0 workspaces (event_log has no pending rows because
nothing is producing them yet).

### 3.5 Flip EVENT_DRIVEN_ENABLED=true

```bash
py scripts/coolify.py env-set emailbison-sync EVENT_DRIVEN_ENABLED=true
py scripts/coolify.py deploy emailbison-sync --force
```

In logs, ~30s after redeploy, expect:

```
  Event-driven (Tier 1 listener): ON
  Event-driven: listener registered 7 handlers, watchdog spawned
```

If you see `Failed to start event-driven tasks:` followed by an error,
check:
- Migrations 107 + 108 are applied
- `EventListener` import works (`from sync_modules.event_listener import EventListener`)
- `HANDLER_REGISTRY` has all 7 keys

The listener is non-fatal: even if startup fails, polling continues.

### 3.6 First-cycle smoke (5 min after flip)

```sql
-- Triggers should be firing on real bounce/kill traffic.
-- Expect a steady trickle of 'completed' rows.
SELECT event_type, status, COUNT(*)
FROM event_log
WHERE emitted_at > NOW() - INTERVAL '10 minutes'
GROUP BY event_type, status
ORDER BY event_type, status;

-- No rows should be stuck in 'processing' for > 5 min (watchdog interval).
SELECT id, event_type, handler_started_at, NOW() - handler_started_at AS age
FROM event_log
WHERE status = 'processing'
  AND handler_started_at < NOW() - INTERVAL '5 minutes';
-- Expect: 0 rows.

-- No 'orphaned' rows yet (watchdog hasn't promoted any to orphan).
SELECT COUNT(*) FROM event_log WHERE status = 'orphaned';
```

If `processing` rows are accumulating with old `handler_started_at`:
the listener is dispatching but handlers are blocking the LISTEN
connection. This was the Phase 3 bug — should be fixed, but if it
recurs, the symptom is a single very-old `processing` row. Roll back.

### 3.7 24h shadow soak

For 24h, both `set_tag_sync` and Tier 2 `tag_op_worker` are running.
Both write the same tag changes; EB API returns 200 OK on duplicates.

Watch:

```sql
-- Tag op events draining cleanly
SELECT event_type, status, COUNT(*)
FROM event_log
WHERE event_type LIKE 'tag_op_%'
  AND emitted_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type, status;

-- Failure rate
SELECT event_type, error_message, COUNT(*)
FROM event_log
WHERE status = 'failed' AND emitted_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type, error_message
ORDER BY COUNT(*) DESC LIMIT 20;
```

**Pass conditions for 24h gate:**
- `failed` rate < 1% of all emitted events
- `orphaned` count < 5 over the 24h window
- `set_tag_sync` audit log shows no anomalies (failure rate within ± 1
  std-dev of pre-flip baseline)
- Tag drift cleanup (run `scripts/cleanup_eb_tag_drift.py` in --dry-run
  mode) shows ≤ baseline drift count

### 3.8 7-day shadow soak — Gate 5

Same queries as §3.7, run daily. Required before dropping `set_tag_sync`.

### 3.9 Rollback (Phase 2)

The flag flip is fully reversible:

```bash
py scripts/coolify.py env-set emailbison-sync EVENT_DRIVEN_ENABLED=false
py scripts/coolify.py deploy emailbison-sync --force
```

In ~30s the listener stops. Triggers continue inserting `event_log`
rows (the triggers are DB-side; flag doesn't disable them), but with
no listener those rows accumulate as `status='emitted'`. That's fine —
when the flag is re-enabled, the listener's catch-up logic
(`_drain_pending`) processes them in order.

Tag op events that have already been claimed and processed by Tier 2
remain `status='completed'`. No partial state.

If the rollback is permanent (ie. the architecture has a flaw we
didn't catch), follow with:

```sql
-- Stop the triggers from firing (keep the table for forensics)
ALTER TABLE event_log DISABLE TRIGGER ALL;
-- Or, more surgical: drop specific triggers
DROP TRIGGER IF EXISTS event_bounce_observed ON sender_account_events;
-- etc.
```

The DB schema doesn't have to be reverted; migrations 107 + 108 stay
applied. They're additive.

---

## 4. Verification cookbook

### 4.1 Health: events flowing end-to-end

```sql
-- Last 1h activity by event type
SELECT event_type,
       COUNT(*) FILTER (WHERE status = 'completed') AS ok,
       COUNT(*) FILTER (WHERE status = 'emitted')   AS pending,
       COUNT(*) FILTER (WHERE status = 'processing') AS in_flight,
       COUNT(*) FILTER (WHERE status = 'failed')    AS failed,
       COUNT(*) FILTER (WHERE status = 'orphaned')  AS orphaned,
       MIN(handler_completed_at - emitted_at)       AS min_lag,
       AVG(handler_completed_at - emitted_at)       AS avg_lag,
       MAX(handler_completed_at - emitted_at)       AS max_lag
FROM event_log
WHERE emitted_at > NOW() - INTERVAL '1 hour'
GROUP BY event_type
ORDER BY event_type;
```

**Healthy signals:**
- `avg_lag` < 5s for all event types
- `max_lag` < 30s
- `failed + orphaned` < 1% of total
- `in_flight` close to 0 most of the time

### 4.2 Workspace partitioning audit

The CHECK constraint enforces that all `tag_op_*` events have a
`workspace_id`. Confirm the constraint exists and is satisfied:

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'event_log'::regclass
  AND contype = 'c';

-- Should return zero rows (no violations)
SELECT id, event_type
FROM event_log
WHERE event_type LIKE 'tag_op_%' AND workspace_id IS NULL;
```

### 4.3 Idempotency replay

If a Tier 2 worker run failed mid-batch and you want to confirm the
remaining events are picked up:

```sql
-- Find still-pending tag ops for a workspace
SELECT id, event_type, payload, retry_count
FROM event_log
WHERE event_type LIKE 'tag_op_%'
  AND workspace_id = '<workspace_uuid>'
  AND status IN ('emitted', 'failed')
  AND (retry_after IS NULL OR retry_after < NOW())
ORDER BY emitted_at LIMIT 20;
```

The Tier 2 worker runs every 30 min. To force-run a cycle without
waiting:

```bash
# Currently no admin endpoint; restart the worker to pick up the
# next-cycle SHOULD_RUN gate immediately.
py scripts/coolify.py restart emailbison-sync
```

(Followup: an admin endpoint `POST /api/sync/event-driven/drain` would
let us trigger this without a restart. Out of scope for cutover.)

---

## 5. Stop-the-line tripwires

If any of these fire during cutover, halt + investigate:

| Tripwire | Likely cause | First-action |
|----------|--------------|--------------|
| Worker boot logs `Event-driven: ON` when env says false | Stale env var or unread shutdown | Check `py scripts/coolify.py env-list emailbison-sync \| grep EVENT` |
| `event_log` rows in `processing` status > 10min after deploy | Listener acquired pool conn that's blocked elsewhere | Restart emailbison-sync; if recurs, check `pg_stat_activity` for long queries |
| Bounce/kill rate spikes immediately after flag flip | Trigger fires and handler enqueues kill that wouldn't have fired in poll mode (parity bug) | Roll back flag; compare evaluate_lifetime_rule logic in handler vs `health_checks.py` |
| Tag drift count grows post-flip | Tier 2 worker is failing silently | Check `event_log WHERE event_type LIKE 'tag_op_%' AND status = 'failed'` |
| `incubation_watcher` graduates an inbox `lifecycle_tag_sync` is also processing | Cutover flag race during Phase 1 transition | Both writes are idempotent; row will end at the same final state. Audit log entries duplicate but harmless |

---

## 6. Open items / followups

- v2 of incubation-watcher needs a daemon mode so we can drop the
  manual `coolify exec` cycles. Tracked in HANDOFF.md.
- Admin endpoint `POST /api/sync/event-driven/drain` (see §4.3) for
  on-demand Tier 2 cycle.
- Gate 6 (drop `set_tag_sync`) is a separate runbook — write it once
  the 7-day soak passes.
- Disconnect-ladder + sender-ban handlers (Phase 5+) are deferred per
  plan; they get added to `HANDLER_REGISTRY` in their own cutovers.
