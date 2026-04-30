---
title: 2026-04-30 Deploy — Operator Quick Reference
audience: operator running the deploy
companion: docs/operations/2026-04-30-deploy-runbook.md (full procedure)
---

# Deploy Quick Reference

> One-page copy-paste card. Pair with the full runbook for context.

## Order of operations

```
1. Provision incubation-watcher (Coolify UI)
2. Snapshot baseline already captured — see §3 of runbook
3. Deploy emailbison-sync   ← THE deploy with behavior change
4. Run 6 verification checks
5. SKIP charm-api today (no impact)
6. May 1 morning capture (~02:50 UTC)
```

---

## Phase 1 — Provision incubation-watcher (Coolify UI)

```
Add Application → Public Repository
  Repo: hirecharm/charm-email-os
  Branch: plan/eod-campaign-reapply
  Build Pack: Dockerfile
  Base Directory: /apps/incubation-watcher
  Dockerfile Path: Dockerfile
  Custom Start Command: sleep infinity   ← critical
  Health Check: disabled

Env vars (copy from emailbison-sync):
  DATABASE_URL=<from emailbison-sync env>
  EMAILBISON_API_URL=https://spellcast.hirecharm.com/api
  LOG_LEVEL=INFO
```

Smoke tests (all 3 must pass):

```bash
py scripts/coolify.py exec incubation-watcher incubation-watcher --version
# Expect: incubation-watcher, version 0.1.0

py scripts/coolify.py exec incubation-watcher incubation-watcher --help
# Expect: 3 commands: check, run, shadow-compare

py scripts/coolify.py exec incubation-watcher incubation-watcher check --workspace Charm
# Expect: eligible_for_graduation=0  (none at 14 BD yet today)
```

Any failure here → STOP. Fix before phase 3.

---

## Phase 3 — Deploy emailbison-sync

```bash
py scripts/coolify.py deploy l4g44o00s4cccg804osswgcc
```

Open log tail in second terminal:

```bash
py scripts/coolify.py logs emailbison-sync --tail 100 --follow
```

**Build takes 1-2 min.** First sync cycle ~30 sec after restart.

### Watch first cycle for these signals

| Signal | Meaning |
|--------|---------|
| `[GRADUATE]` | Existing module graduating (good — normal) |
| `[ORPHAN] inbox NNN ... not in workspace EB` | Workspace-orphan caught (good — patch working) |
| `[RACE] ... eligibility flipped` | Race-check caught a flip (good — should be RARE) |
| `[ERROR] Unexpected exception ...` | Broad-except caught something (investigate) |

---

## Phase 4 — Six verification checks (run all, in order)

### Check 1 — ORPHAN handling
```bash
py scripts/coolify.py logs emailbison-sync --tail 500 | grep "ORPHAN"
```
Pass: 0-5 lines. Investigate if >10 from same workspace.

### Check 2 — Race-check
```bash
py scripts/coolify.py logs emailbison-sync --tail 500 | grep "RACE"
```
Pass: 0-2 lines. Investigate if ≥3.

### Check 3 — Per-row exception isolation
```bash
py scripts/coolify.py logs emailbison-sync --tail 500 | grep -E "ERROR.*graduating|ERROR.*tagging|ERROR.*cleaning|ERROR.*tag reconcile"
```
Pass: 0-3 different inboxes. **ROLLBACK if ≥10 same exception type.**

### Check 4 — disconnected_timeout NO new writes
```bash
py -c "
import requests
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa',
          'sql':'SELECT COUNT(*) FROM kill_queue WHERE created_at > NOW() - INTERVAL %s30 minutes%s AND trigger_type = %sdisconnected_timeout%s'.replace('%s', chr(39))},
  headers={'User-Agent':'curl/8.0.0'})
print(r.json())
"
```
Pass: 0. **ROLLBACK if > 0.**

### Check 5 — kill_queue eb_pending state
```bash
py -c "
import requests
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa',
          'sql':'SELECT COUNT(*), MIN(updated_at)::text FROM kill_queue WHERE status = ' + chr(39) + 'eb_pending' + chr(39)},
  headers={'User-Agent':'curl/8.0.0'})
print(r.json())
"
```
Pass: count=0 OR oldest pending < 30 min ago.

### Check 6 — set_tag_sync errors per workspace
```bash
py -c "
import requests
sql = '''SELECT w.workspace_name, SUM(s.records_failed) AS errors
        FROM sync_audit_log s JOIN workspaces w ON w.id = s.workspace_id
        WHERE s.sync_type = 'set_tags' AND s.started_at > NOW() - INTERVAL '30 minutes'
        GROUP BY w.workspace_name ORDER BY errors DESC NULLS LAST LIMIT 5'''
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa', 'sql': sql},
  headers={'User-Agent':'curl/8.0.0'})
print(r.json())
"
```
Pass: all workspaces errors ≤ 5. Investigate any > 5.

### Lifecycle_tags freshness sanity check
```bash
py -c "
import requests
sql = '''SELECT w.workspace_name, MAX(s.completed_at)::text AS last_run,
                EXTRACT(EPOCH FROM (NOW() - MAX(s.completed_at)))/60 AS minutes_stale
         FROM workspaces w
         LEFT JOIN sync_audit_log s ON s.workspace_id = w.id AND s.sync_type = 'lifecycle_tags'
         WHERE w.is_active = TRUE
         GROUP BY w.workspace_name ORDER BY minutes_stale DESC NULLS LAST'''
r = requests.post('https://api.wizardgrimoire.cloud/api/admin/run-sql',
  params={'key':'098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa', 'sql': sql},
  headers={'User-Agent':'curl/8.0.0'})
for row in r.json().get('result', []):
    print(f\"{row['workspace_name']:<35} stale_min={float(row['minutes_stale']):.1f}\")
"
```
Pass: all workspaces stale_min ≤ 35.

---

## Phase 5 — Walk-away monitor (30 min)

Re-run Checks 1, 2, 3, 4 thirty minutes after deploy. Same thresholds.

If all pass at the 30-min mark, deploy is operationally complete. ✓

---

## Phase 6 — May 1 morning capture (~02:50 UTC)

Pre-graduation snapshot:
```bash
py scripts/coolify.py exec incubation-watcher \
  incubation-watcher check --workspace Charm \
  > docs/audits/2026-05-01-watcher-pre-cycle.txt
```

After existing module's first cycle (~03:30 UTC):
```bash
py scripts/coolify.py exec incubation-watcher \
  incubation-watcher shadow-compare \
    --workspace Charm \
    --since 2026-05-01T00:00:00Z \
  > docs/audits/2026-05-01-shadow-compare-charm.txt
```

Expected first-day output: divergence detected (proposed=0 because all just graduated; actual_only ~75 = the cohort that just graduated). This is normal first-day pattern.

The validation point is comparing the pre-cycle candidate list (first command) to the actual_only set (from second command). They should be the same 75 inboxes.

---

## Rollback (if needed)

```bash
# Coolify UI → emailbison-sync → Deployments → previous successful build → Redeploy
# OR via CLI if supported:
py scripts/coolify.py deploy l4g44o00s4cccg804osswgcc --tag e4551f9
```

`e4551f9` is yesterday's tip — pre-today work. Loses today's hardening but restores known-working state.

---

## Acceptance — deploy is "done" when all true

- [ ] incubation-watcher provisioned, all 3 smoke tests pass
- [ ] emailbison-sync deployed, build succeeded
- [ ] Check 1-6 + freshness check all pass within 30 min of deploy
- [ ] Walk-away check at 30 min post-deploy: still passing
- [ ] Tomorrow ~02:50 UTC: pre-cycle candidate list captured
- [ ] Tomorrow ~03:30 UTC: shadow-compare run, output saved
- [ ] Tomorrow afternoon: pre-cycle list compared to actual_only set, parity verified

7 boxes. All must check.

---

## On-call escalation triggers

| Signal | Action |
|--------|--------|
| Check 4 returns count > 0 | **ROLLBACK** |
| Check 3 returns ≥10 lines same exception type | **ROLLBACK** |
| Lifecycle_tags staleness > 2h on any workspace | **INVESTIGATE** (don't rollback yet) |
| EB UI shows cross-tenant inbox visible on a campaign | **HALT all reapply ops** (separate issue, not deploy-caused) |
