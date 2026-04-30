---
title: 2026-04-30 Deploy Runbook — Inbox Integrity Program (12 commits)
created: 2026-04-30
audience: operator deploying via Coolify
companion-docs:
  - docs/plans/INBOX-INTEGRITY-PROGRAM.md (master tracker)
  - docs/work-logs/2026-04-30-systems-accuracy-and-cleanup.md (session log)
---

# 2026-04-30 Deploy Runbook

> **Why methodic.** 12 commits, 4 production modules patched (lifecycle_tag_sync,
> health_checks, kill_processor, set_tag_sync), 1 new service to provision
> (incubation-watcher), 1 time-sensitive event tomorrow (May 1 Charm
> graduation cohort). Botching the deploy order or skipping verification
> breaks more than it fixes. Follow phases in order. Don't combine steps.

---

## 0. Pre-flight (5 min)

Verify branch state matches expectation:

```bash
# On any host with repo access
git fetch hirecharm
git log --oneline hirecharm/plan/eod-campaign-reapply | head -5
```

Should show top commit `3ef8400 fix(set_tag_sync): port silent-failure hardening`.

Confirm Coolify is responsive:

```bash
py scripts/coolify.py list-apps
```

Should list 8 active services. If anything errors here, **STOP** — fix Coolify access before continuing.

---

## 1. Deploy order — RATIONALE

Two deploys + one provision (charm-api SKIPPED — see §1.1):

| # | Action | Service | Risk | Why this order |
|--:|--------|---------|------|----------------|
| 1 | **Provision** | incubation-watcher (NEW) | ZERO — sleep-infinity container | Time-sensitive; needs to be ready before tomorrow morning. Doesn't run any production behavior. |
| 2 | **Snapshot** | Pre-deploy baseline JSON | ZERO — read-only | "Before patch" reference numbers (already captured to `docs/audits/2026-04-30-pre-deploy-baseline.json` — see §3 for use). |
| 3 | **Deploy** | emailbison-sync | HIGHEST — 4 production modules patched | Picks up all today's behavior changes. Watch logs closely first cycle. |
| ~~4~~ | ~~Deploy charm-api~~ | ~~charm-api~~ | **SKIP** — no impact today | charm-api's Dockerfile does NOT copy `sync_modules/`. None of today's patches reach this service. Skipping saves the build cycle. See §1.1. |
| 5 | **Verify** | Post-deploy queries | ZERO — read-only | Confirm baseline numbers + accuracy gates within tolerance. |

**Critical**: do NOT deploy emailbison-sync before incubation-watcher is provisioned. If
emailbison-sync deploy fails and needs rollback, you want incubation-watcher
already in place to capture the May 1 event. Reverse order means you might miss
the validation window if emailbison-sync deploy needs investigation.

### 1.1 Why charm-api is skipped today

Dockerfile review at the manager level:

```
charm-api Dockerfile copies: api/, migrations/, Hypertide/automation/...
                       NOT: sync_modules/, scripts/, docs/
```

Verified via `grep -rn "from sync_modules\|import sync_modules" api/` → **zero matches**. The only reference is one comment in `api/routes/health.py:568`. Therefore today's patches to `lifecycle_tag_sync.py`, `health_checks.py`, `kill_processor.py`, `set_tag_sync.py` have ZERO behavior impact in charm-api.

Deploying charm-api today would:
- Pull commit `5e82618`
- Build image (3-5 min)
- Run identical api/ code as before
- No log signals, no test signals, no behavior change

If you want version alignment for trace-ability, deploy at end of week with a non-rushed cycle. Today, skip.

---

## 2. Phase 1 — Provision `incubation-watcher` Coolify service

### 2.1 Create the Coolify app

In Coolify UI:

1. **Add Application** → **Public Repository (or your Git source)**
2. Repo: `hirecharm/charm-email-os`
3. Branch: `plan/eod-campaign-reapply`
4. **Build Pack**: `Dockerfile`
5. **Base Directory**: `/apps/incubation-watcher`
6. **Dockerfile Path**: `Dockerfile`
7. **Custom Start Command** (CMD override): `sleep infinity`
   - Critical: the Dockerfile's default ENTRYPOINT is `incubation-watcher` and CMD is `--help`. Without override, the container exits immediately.
8. **Health Check**: disable for v1 (no /health endpoint yet)

### 2.2 Environment variables

Copy these from `emailbison-sync` service env (via `py scripts/coolify.py env-list emailbison-sync`):

```
DATABASE_URL=<from emailbison-sync>
EMAILBISON_API_URL=https://spellcast.hirecharm.com/api
LOG_LEVEL=INFO
```

DO NOT set anything else. The service is operator-invoked only in v1.

### 2.3 First deploy

Click **Deploy**. Wait for build (1-2 min for slim Python image).

### 2.4 Smoke tests

```bash
# Verify container alive
py scripts/coolify.py status incubation-watcher
# Expect: "Running"

# Verify CLI works
py scripts/coolify.py exec incubation-watcher incubation-watcher --version
# Expect: "incubation-watcher, version 0.1.0"

# Verify DB + EB connectivity end-to-end
py scripts/coolify.py exec incubation-watcher incubation-watcher check --workspace Charm
# Expected output:
#   workspace=Charm eb_workspace_id=<id>
#   eligible_for_graduation=0 (>= 14 business days)
# Exit code 0.
```

If `check --workspace Charm` returns ANY error other than "0 eligible":
- **STOP**. Investigate. Likely DATABASE_URL or EMAILBISON_API_URL misconfigured.
- Do NOT proceed to phase 3 (emailbison-sync deploy) until incubation-watcher smoke tests pass.

### 2.5 Confirm shadow mode is dormant

The service is now sitting idle. It does not poll, does not write. It only acts when operator invokes via `coolify exec`. Per `apps/incubation-watcher/HANDOFF.md` §6, this is the v1 design.

---

## 3. Phase 2 — Pre-deploy baseline (already captured)

The baseline JSON is committed at `docs/audits/2026-04-30-pre-deploy-baseline.json`. It captures 6 dimensions:

1. lifecycle_tags last successful run per workspace
2. kill_queue state (status × trigger_type)
3. New disconnected_timeout writes in last 1h (PRE-deploy: should be 0)
4. Graduations in last 24h per workspace
5. sync_audit_log error/failure counts last 1h per sync_type
6. Incubating cohort fleet-wide

### 3.1 Reference numbers (PRE-deploy, captured 2026-04-30 ~21:11 UTC)

| Metric | Pre-deploy value | Post-deploy expectation | Tolerance |
|--------|-----------------|------------------------|-----------|
| All 11 workspaces have lifecycle_tags running every ~30min | ✓ all 11 healthy | Same (all 11 should still run) | **MUST match** — if any workspace stops, immediate investigate |
| disconnected_timeout writes last 1h | 0 | **0** | ZERO tolerance |
| Graduations last 24h | 0 fleet-wide | Likely still 0 today (next big event is May 1 morning) | Any number ≥ 0 fine |
| lifecycle_tags failures last 1h | 0 | 0 ± 5 per workspace | >5 = investigate |
| set_tags failures last 1h | 0 | 0 ± 5 per workspace | >5 = investigate |
| kill_queue failures last 1h | 0 | 0 | >0 = investigate |
| campaigns failures last 1h | 10 (pre-existing, NOT caused by deploy) | ~same | Document as pre-existing baseline |
| Incubating cohort | 251 Charm + 14 SKMR + 1 Spout = 266 | Same (no row-level changes today) | Diff > ±5 = investigate |

### 3.2 Re-snapshot before deploy (deploy-window drift check)

```bash
py scripts/audit_system_accuracy.py > docs/audits/2026-04-30-pre-deploy-accuracy.txt 2>&1
```

Compare to morning's snapshot (`docs/audits/2026-04-30-system-accuracy-snapshot.json`). Should show 9 of 11 workspaces passing. SPUI / Spout failure is pre-existing (membership / pool drift) — confirmed in the baseline as known-bad.

If a workspace that was passing this morning is NOW failing, that's drift in the deploy window — investigate before pushing the button.

---

## 4. Phase 3 — Deploy `emailbison-sync` (the risky one)

### 4.1 Trigger deploy

```bash
py scripts/coolify.py deploy l4g44o00s4cccg804osswgcc
```

UUID: `l4g44o00s4cccg804osswgcc` (emailbison-sync).

### 4.2 Watch logs DURING the deploy

Open a separate terminal and tail logs:

```bash
py scripts/coolify.py logs emailbison-sync --tail 100 --follow
```

Build takes 1-2 min, then container restarts. Watch for these signals during the FIRST sync cycle (~30 sec after restart):

#### Expected GOOD signals

```
[GRADUATE] m.elzey@... (gmail) - incubating -> reserve
[ORPHAN] inbox 9999 (...) not in workspace EB — skipping graduation
[RACE] ... eligibility flipped between fetch and DB transaction (rare)
```

These are the new instrumentation working as intended. `[ORPHAN]` means the silent-failure patch is catching workspace-orphan cases. `[RACE]` means the race-check is firing (should be VERY rare).

#### Expected ABSENT signals (if these appear, investigate)

- `[ERROR] Unexpected exception graduating ...` — the broad-except catching real code bugs. **One-off is fine** (transient asyncpg). **Multiple in a row across different inboxes is concerning.**
- Stack traces from asyncpg / httpx — should be wrapped in audit.add_error now.

### 4.3 First cycle verification (5 min after deploy)

```bash
# Verify lifecycle_tag_sync is still firing
py -c "
import requests, json
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa',
          'sql':'''SELECT w.workspace_name,
                          MAX(s.completed_at)::timestamp AS last_lifecycle_run,
                          NOW() - MAX(s.completed_at) AS staleness
                   FROM sync_audit_log s JOIN workspaces w ON w.id = s.workspace_id
                   WHERE s.sync_type = 'lifecycle_tags' AND w.is_active = TRUE
                   GROUP BY w.workspace_name ORDER BY w.workspace_name'''},
  headers={'User-Agent':'curl/8.0.0'})
for r in r.json().get('result', []):
    print(f\"  {r['workspace_name']:<35} last_run={r['last_lifecycle_run']} staleness={r['staleness']}\")
"
```

Expected: every active workspace has `staleness < 35 minutes` (the cycle interval is 30 min).

If any workspace shows `staleness > 1 hour`, that's a regression — lifecycle_tag_sync may be failing for it. Investigate via container logs filtering on workspace name.

### 4.4 Confirm `disconnected_timeout` is no longer being WRITTEN

```bash
py -c "
import requests, json
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa',
          'sql':'''SELECT COUNT(*) AS new_disconnected_kills_post_deploy
                   FROM kill_queue
                   WHERE created_at > NOW() - INTERVAL '15 minutes'
                     AND trigger_type = 'disconnected_timeout' '''},
  headers={'User-Agent':'curl/8.0.0'})
print(r.json())
"
```

Expected: 0. Phase 1 of the connection-state-machine plan has removed this trigger. If non-zero, the patch didn't deploy — re-verify Coolify pulled latest.

### 4.5 Module-specific verification (5 explicit checks per patch)

These checks tie EACH commit to an observable signal. Run all 5 within 30 min of deploy. Each maps to a specific patch.

#### Check 1: lifecycle_tag_sync ORPHAN handling (commit `94fd0fa`)

```bash
py scripts/coolify.py logs emailbison-sync --tail 500 | grep "ORPHAN"
```

| Result | Action |
|--------|--------|
| 0 lines | Normal (no orphans currently — everything in DB still in EB) |
| 1-5 lines | Expected — patch is surfacing previously-silent workspace-orphans |
| >10 lines from same workspace | Investigate that workspace specifically — Hypertide may have moved many at once |

#### Check 2: lifecycle_tag_sync race-check (commit `d775761`)

```bash
py scripts/coolify.py logs emailbison-sync --tail 500 | grep "RACE"
```

| Result | Action |
|--------|--------|
| 0 lines | Normal — eligibility flips during sync are rare |
| 1-2 lines | Acceptable transient |
| ≥3 lines | Investigate — operator may be toggling warmup_enabled while sync runs |

#### Check 3: per-row exception isolation (commit `d775761`, `3ef8400`)

```bash
py scripts/coolify.py logs emailbison-sync --tail 500 | grep -E "ERROR.*graduating|ERROR.*tagging|ERROR.*cleaning|ERROR.*tag reconcile"
```

| Result | Action |
|--------|--------|
| 0 lines | Patch is dormant — no unexpected exceptions caught |
| 1-3 lines from different inboxes | Acceptable — broad-except surfacing real edge cases |
| **≥10 lines, especially same exception type** | **ROLLBACK** — likely real code bug being eaten by broad-except |

Look at the `e!r` repr in each line — same exception class repeating across many inboxes is the bug signature.

#### Check 4: disconnected_timeout no longer written (commit `94fd0fa`)

```bash
py -c "
import requests
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa',
          'sql':'''SELECT COUNT(*) AS new_disc_kills
                   FROM kill_queue
                   WHERE created_at > NOW() - INTERVAL '30 minutes'
                     AND trigger_type = 'disconnected_timeout' '''},
  headers={'User-Agent':'curl/8.0.0'})
print(r.json())
"
```

| Result | Action |
|--------|--------|
| count = 0 | ✓ patch deployed correctly |
| count > 0 | **ROLLBACK** — patch did not deploy. Coolify pulled wrong commit. |

Note: existing `flagged` rows from before the patch are FINE — only new entries should be 0.

#### Check 5: kill_processor pool-tag strip retry (commit `e7bbd59`)

```bash
py -c "
import requests
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa',
          'sql':'''SELECT COUNT(*) AS eb_pending_count, MIN(updated_at)::timestamp AS oldest_pending
                   FROM kill_queue WHERE status = 'eb_pending' '''},
  headers={'User-Agent':'curl/8.0.0'})
print(r.json())
"
```

| Result | Action |
|--------|--------|
| count = 0 | Steady state |
| count > 0, oldest < 30 min | Expected during deploy window — kills retrying |
| count > 0, oldest > 2h | Investigate — retry path stuck somehow |

#### Check 6: set_tag_sync per-domain isolation (commit `3ef8400`)

```bash
py -c "
import requests
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa',
          'sql':'''SELECT w.workspace_name, COUNT(*) AS recent_runs,
                          SUM(s.records_failed) AS errors_30min
                   FROM sync_audit_log s JOIN workspaces w ON w.id = s.workspace_id
                   WHERE s.sync_type = 'set_tags'
                     AND s.started_at > NOW() - INTERVAL '30 minutes'
                   GROUP BY w.workspace_name ORDER BY errors_30min DESC LIMIT 5'''},
  headers={'User-Agent':'curl/8.0.0'})
print(r.json())
"
```

| Result | Action |
|--------|--------|
| All workspaces errors_30min ≤ 5 | Normal |
| Single workspace errors > 10 | Investigate that workspace |
| Multiple workspaces errors > 5 | Investigate — broad systemic issue |

### 4.6 Walk-away monitor (30 min)

After Checks 1-6 done, walk away for 30 min. The next sync cycle should fire. Re-run Check 4 — should still be 0. Re-run Check 1 — log line count should not be growing rapidly.

---

## 5. Phase 4 — `charm-api` deploy SKIPPED (see §1.1 for why)

Net behavior change today from deploying charm-api: **zero**. Skip it. If you want trace-time version alignment, deploy at end of week with a non-rushed cycle.

---

## 6. Phase 5 — Post-deploy full verification (15 min)

### 6.1 Accuracy audit re-run

```bash
py scripts/audit_system_accuracy.py
```

Compare to the pre-deploy snapshot from §3.1. Should be:
- Same 9 of 11 workspaces passing
- SPUI / Spout still failing (those are pre-existing data issues, not patch regressions)
- No NEW workspaces failing

### 6.2 Audit error metric

```bash
py -c "
import requests, json
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa',
          'sql':'''SELECT sync_type, COUNT(*) FILTER (WHERE error_count > 0) AS runs_with_errors,
                          SUM(error_count) AS total_errors
                   FROM sync_audit_log
                   WHERE started_at > NOW() - INTERVAL '1 hour'
                     AND sync_type IN ('lifecycle_tags', 'set_tags', 'kill_queue')
                   GROUP BY sync_type'''},
  headers={'User-Agent':'curl/8.0.0'})
print(json.dumps(r.json().get('result', []), default=str, indent=2))
"
```

Expected: errors should be at or near 0 in the first hour post-deploy. Some `workspace_orphan` audit errors are EXPECTED — they're the new instrumentation surfacing what was previously silent. Worth investigating any workspace with >5 errors per cycle.

### 6.3 Slack channel check

The existing `inbox_audits` Slack still fires twice daily at 6am/1pm Pacific. If you've tied alerting to `[ERROR]` or `[ORPHAN]` log lines in Coolify, watch those channels too.

---

## 7. Phase 6 — May 1 morning capture (TIME-SENSITIVE)

Tomorrow morning, before the existing module's first sync cycle (~03:00 UTC), capture incubation-watcher's proposed graduation set:

### 7.1 Wait for existing module's first cycle

The existing `lifecycle_tag_sync` runs every 30 min. After the first run post-midnight UTC, the Charm Apr-13 cohort should graduate. Watch:

```bash
py scripts/coolify.py logs emailbison-sync --tail 200 | grep "Charm.*GRADUATE"
```

### 7.2 Run shadow-compare via the watcher's CLI subcommand

Once existing module has run at least once after the cutoff, invoke the comparison directly. The subcommand queries DB for both candidate set AND actual graduations and emits the diff in one shot — no manual file shuffling.

```bash
py scripts/coolify.py exec incubation-watcher \
  incubation-watcher shadow-compare \
    --workspace Charm \
    --since 2026-05-01T00:00:00Z \
  > docs/audits/2026-05-01-shadow-compare-charm.txt 2>&1
```

Exit code:
- `0` = zero divergence (proposed == actual)
- `1` = divergence detected (operator MUST investigate before cutover)
- `2` = config / connection error

### 7.3 Read the output

Expected for first run:
```
workspace=Charm
since=2026-05-01T00:00:00+00:00

proposed (by watcher, RIGHT NOW):    0     ← all just graduated, no longer in 'incubating'
actual   (by existing module):       ~75   ← Charm Apr-13 cohort
matched  (both proposed AND actual): 0

DIVERGENCE: 75 inbox(es) graduated by existing module but NOT proposed by watcher:
  - actual_only: m.elzey@<domain>...
  ...

RESULT: divergence detected. Investigate BEFORE any cutover.
```

This **exit-1 on first run is expected and correct** — by the time you run shadow-compare, the existing module has already graduated the cohort, so they're no longer eligible (`lifecycle='active'` instead of 'incubating'). The "watcher would propose 0" is the correct state.

The validation point is: did the watcher's pre-graduation candidate list (captured BEFORE existing module's cycle) match the actual_only set? Use a separate `incubation-watcher check --workspace Charm` BEFORE existing module fires to capture the predicted list.

### 7.4 Acceptance criterion

Run shadow-compare daily during the validation window. The robust pattern:

1. **At ~02:50 UTC** (10 min before existing module's first cycle): `incubation-watcher check --workspace Charm` → save candidate list to file
2. **At ~03:30 UTC** (after first cycle): query `inbox_rotation_history` for actual graduations since `2026-05-01T00:00:00Z`
3. Diff manually OR run `shadow-compare --since 2026-05-01T00:00:00Z` to verify subsequent cycles have parity (later runs of the watcher reflect "what's eligible now, not what was eligible before")

After 7 consecutive days of zero divergence (in the §1 capture comparison), ready to discuss watcher cutover.

---

## 8. Rollback procedures

### 8.1 If `emailbison-sync` deploy breaks production

Symptom: lifecycle_tag_sync stops graduating, kill_queue stops draining, audit_log shows error_count surge across workspaces.

```bash
# Redeploy at the prior tip (before today's work)
py scripts/coolify.py deploy l4g44o00s4cccg804osswgcc --tag e4551f9
```

If `--tag` isn't supported by the Coolify CLI, revert via UI:
- Coolify UI → emailbison-sync → Deployments → select previous successful build → Redeploy

The prior tip `e4551f9` was committed 2026-04-29 21:49 (HANDOFF.md commit). Reverting to it loses today's hardening but restores known-working state.

### 8.2 If `charm-api` deploy breaks API

Symptom: 5xx errors on `https://api.wizardgrimoire.cloud/health`.

Same procedure — redeploy at `e4551f9` via Coolify UI.

### 8.3 If `incubation-watcher` provisioning fails

Symptom: container exits, smoke tests fail, can't run CLI.

Just stop the service. No production impact (it doesn't write anywhere yet). Re-investigate Dockerfile build context or env vars.

---

## 9. Decision points / on-call escalation

If during deploy you see:

| Signal | Decision |
|--------|----------|
| First cycle has 0 graduations across all workspaces | Probably fine — depends on cohort timing. Re-check in 24h. |
| First cycle has `[ORPHAN]` in 3+ workspaces | Investigate but don't rollback — these are PRE-EXISTING orphans now newly visible |
| First cycle has `[ERROR]` (broad-except) for >10% of candidates | **Rollback** — likely a real code bug |
| `disconnected_timeout` kill still being created | **Rollback** — patch didn't deploy |
| Lifecycle_tags audit_log staleness > 2 hours for any workspace | **Investigate** — may not need rollback yet |
| Cross-tenant inbox visible in EB UI on a campaign | **Halt all reapply operations** — not a deploy issue, but firewall hasn't shipped yet |

---

## 10. Acceptance — when this deploy is "done"

- [ ] All 4 phases completed
- [ ] §6.1 accuracy audit shows same 9 of 11 workspaces passing
- [ ] §6.2 audit error counts at or near baseline
- [ ] §4.3 lifecycle_tags staleness < 35 min for all workspaces
- [ ] §4.4 zero new `disconnected_timeout` kill_queue entries
- [ ] §7.1 May 1 morning watcher capture saved to disk
- [ ] §7.4 watcher proposed list compared to actual graduations (parity established)

When all 7 are checked, today's deploy is operationally complete. Shadow validation continues for 7 days before any incubation-watcher cutover.

---

## 11. Companion docs

- Master tracker: [INBOX-INTEGRITY-PROGRAM.md](../plans/INBOX-INTEGRITY-PROGRAM.md)
- Today's session log: [2026-04-30-systems-accuracy-and-cleanup.md](../work-logs/2026-04-30-systems-accuracy-and-cleanup.md)
- Service registry: [services.md](../../production/coolify/services.md)
- ADR-009 (the architectural decision): [adr-009-...md](../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md)
- Incubation-watcher handoff: [apps/incubation-watcher/HANDOFF.md](../../apps/incubation-watcher/HANDOFF.md)
