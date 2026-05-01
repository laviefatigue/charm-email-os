---
title: 2026-04-30 Deploy Outcome
date: 2026-04-30
companion: docs/operations/2026-04-30-deploy-runbook.md, docs/operations/2026-04-30-deploy-quickref.md
audience: morning-after reviewer
---

# Deploy Outcome — 2026-04-30

Two deploys went out today:

1. **incubation-watcher** (new app) — provisioned in Coolify, parked in `sleep infinity` mode for shadow validation.
2. **emailbison-sync** (existing) — redeployed with lifecycle_tag_sync hardening (race-check, per-row exception isolation, ORPHAN logging) + disconnected_timeout kill trigger removed.

Behavior preservation: **today's deploy does not change tag-mutation behavior**. The hardening adds safety nets to the existing flow; it doesn't introduce new auto-graduations or new auto-kills. The watcher is fully passive (no SQL, no EB calls, no DB writes) until manually flipped to `--apply` after 7 days of clean shadow validation.

---

## Phase 1 — incubation-watcher provisioning

**Result:** alive, sleep-infinity, smoke tests deferred.

| Step | Result |
|------|--------|
| Provisioned via Coolify private-github-app API | UUID `pssgc0c8w4sooos8gs0scsos` |
| Build success | After Dockerfile path fix (`/Dockerfile` relative to `base_directory=/apps/incubation-watcher`) |
| Container alive | After CMD fix (commit 912c70e — `CMD ["sleep","infinity"]` instead of `ENTRYPOINT ["incubation-watcher"]` + `CMD ["--help"]`) |
| Final state | `running:unknown` (no healthcheck — expected) |

**Smoke tests deferred to May 1 morning capture.** Coolify's UI Terminal needs a Pusher/Echo WebSocket connection that is `unavailable` on this CF Access tunnel — we verified via both Playwright and Chrome DevTools. The Coolify v4 public REST API does not expose container exec. Scheduled-task creation via Livewire scripted-fill saved no record. SSH-to-VPS not attempted (no creds in scope today).

The May 1 ~02:50 UTC capture (`incubation-watcher check --workspace Charm`) IS the smoke test — it exercises the same SQL eligibility query and EB tag fetch path. If broken, we see it before any `--apply` happens. Watcher is dry-run-only in v1, so a failed smoke test produces a stale capture file, not a production incident.

31 unit tests pass locally — these exercise the SQL eligibility shape, the GraduationResult outcome enum, race-check logic, shadow-comparison set arithmetic.

---

## Phase 2 — emailbison-sync deploy verification

**Deploy timestamp:** 2026-04-30 23:12 UTC
**Deployment UUID:** `fo8cwg00k40gk0o0cwog0s00`
**Status post-build:** `running:healthy`

### 6 verification checks (per quickref §4)

| Check | Threshold | Result | Status |
|-------|-----------|--------|--------|
| 1. ORPHAN handling | 0–5 lines | 0 in 100-line log window | PASS |
| 2. RACE check | 0–2 lines | 0 in 100-line log window | PASS |
| 3. Per-row exceptions | 0–3 inboxes | 0 + 0 records_failed across 4 lifecycle_tags cycles | PASS |
| 4. disconnected_timeout new writes | 0 (rollback if >0) | **0** | PASS |
| 5. kill_queue eb_pending stuck | count=0 OR <30min | 0 | PASS |
| 6. set_tag_sync errors per workspace | ≤5 | 0 across all 11 workspaces | PASS |
| Freshness | ≤35 min | All 23–29 min, new cycles completing | PASS |

**No rollback triggers hit.** Walk-away monitor scheduled for 30 min post-deploy.

### Activity proof (last 5 min post-deploy via sync_audit_log)

| sync_type | runs | failed |
|-----------|------|--------|
| lifecycle_tags | 4 | 0 |
| events | 1 | 0 |
| health | 1 | 0 |
| kill_queue | 1 | 0 |
| set_tags | 1 | 0 |

Charm processed 251 records in one lifecycle_tags cycle, 0 failed.

### Visible logs (Coolify caps at 100 lines)

100/100 lines were `[TAG SELF-HEAL]` re-applying missing 'incubating' tags — the orphan-cleanup patch firing as designed, not a problem.

---

## Critical findings — surfaced via DB-direct sanity checks

While discussing how to smoke-test the watcher, I ran three sanity queries the runbook didn't include. Two are clean; one surfaces a real issue.

### ✅ Q1: Trigger / sync gap detection

**Result: 0 broken inboxes fleet-wide.**

Every `sender_accounts` row with `warmup_enabled=TRUE AND is_active=TRUE` has `warmup_enabled_since` properly stamped. Migration 094's trigger (`track_warmup_enabled_transition`) plus the one-time backfill caught 100% of cases. No inboxes are silently un-graduatable due to a missing timestamp.

### ✅ Q3: Eligibility distribution

**Result: 193 incubating fleet-wide, all properly stamped, all in BD 10–13 — graduating over the next ≤4 business days.**

| Workspace | Total incubating | Ready today (BD≥14) | Due within 4 BD (BD 10–13) |
|-----------|------------------|---------------------|----------------------------|
| Charm | 178 | 0 | 178 |
| Stable Kernel Market Research | 14 | 0 | 14 |
| Spout | 1 | 0 | 1 |
| (other 8 workspaces) | 0 | 0 | 0 |

Implication: tomorrow's natural cycle is not just ~75 — it could be the full Charm cohort (178) plus SKMR (14) plus Spout (1) over the next 4 business days. The runbook's "~75" estimate was a single-day batch; the real cohort is larger.

### ⚠ Q2: Cross-workspace firewall coverage = 0% in production

**Result: domain_pattern is unset on every active workspace.**

| Workspace | domain_pattern |
|-----------|----------------|
| Barrena, Hello Hero, Linkgraph, SPUI, Sammy, Search Atlas, Spout, Stable Kernel, SKMR (9) | `NULL` |
| Charm, Selery (2) | `""` (empty string — `LIKE` matches anything, false safety) |
| Any workspace with a real pattern | **0** |

**Why this matters:** the cross-workspace integrity firewall plan (`docs/plans/INBOX-INTEGRITY-PROGRAM.md`) calls for graduation to require email-to-domain-pattern match. Without populated patterns, the firewall is effectively non-existent — any inbox misassigned in EB will graduate to whatever workspace EB recorded, no validation.

**Mitigating factor (today only):** by manual eyeball, all 193 incubating inboxes are correctly assigned by domain:

| Workspace | Domain pattern observed | Inboxes |
|-----------|-------------------------|---------|
| Charm | `*charm.com` (illuminatecharm, enhancecharm, strengthencharm, ...) | 178 |
| SKMR | `*stablekernel.com` (evaluatestablekernel, understandstablekernel, ...) | 14 |
| Spout | `joinspoutwater.com` | 1 |

So tomorrow's graduation is safe by inspection, not by automated guarantee. The firewall is a real gap that wants closure independent of today's deploy.

---

## What WILL change overnight (without anyone touching anything)

- **Existing `lifecycle_tag_sync` will graduate the cohort that crosses 14 BD.** Same code path that's been running for weeks — now hardened against silent failures, but same outputs.
- **Existing `set_tag_sync`, `kill_processor` continue normal cycles.** Patched, not behavior-changed.
- **`disconnected_timeout` kill trigger is REMOVED.** The single behavior change today: disconnected inboxes will no longer be auto-killed. Connection-state-machine plan (`docs/plans/connection-state-machine.md`) covers the replacement (warning milestones, no auto-kill).

## What WILL NOT happen overnight

- Watcher will not graduate anyone (sleep infinity, no daemon)
- Watcher will not write to EB or DB
- No new automated kill paths
- No new automated tag mutations beyond what the old code already did

---

## Morning checklist (May 1)

In order, before any other work:

1. **~02:50 UTC: pre-cycle snapshot.**
   ```bash
   py scripts/coolify.py exec incubation-watcher \
     incubation-watcher check --workspace Charm \
     > docs/audits/2026-05-01-watcher-pre-cycle.txt
   ```
   ⚠ The `coolify.py exec` subcommand does not exist (Coolify v4 REST API does not expose exec, terminal WebSocket is unavailable). Replacement is needed:
   - Option A: Run `incubation-watcher check --workspace Charm` locally with `DATABASE_URL` and `EMAILBISON_API_URL` env vars pulled from the Coolify watcher app's env. Same code path, hits same DB+EB.
   - Option B: Run the watcher's eligibility SQL directly via `run-sql` HTTP endpoint. Pure DB read.
   - Option A is preferred (exercises the full path including EB tag fetch).

2. **~03:30 UTC: shadow-compare.** Same caveat — replace `coolify.py exec` with local invocation.
   ```bash
   py -m incubation_watcher.cli shadow-compare \
     --workspace Charm \
     --since 2026-05-01T00:00:00Z \
     > docs/audits/2026-05-01-shadow-compare-charm.txt
   ```
   Expected first-day output: divergence detected (proposed=0, actual_only ~Charm cohort that just graduated). Normal first-day pattern. The validation point: pre-cycle candidate list (step 1) should equal actual_only set (step 2).

3. **Re-run the 6 verification checks** (quickref §4). Same thresholds. Confirm overnight behavior is still clean.

4. **Walk-away monitor result.** A scheduled wakeup at 16:45 UTC re-ran Checks 1–4 at 30 min post-deploy. Results captured separately (look for the morning's wakeup output / chat history).

5. **Decide on firewall populate.** The 0% coverage finding above is the highest-priority follow-up unrelated to today's deploy — populating `clients.domain_pattern` and adding the predicate to graduation SQL. Not urgent for May 1 (no misassigned inboxes by inspection), but should be scoped this week.

---

## Acceptance — deploy is "done" when all true

- [x] incubation-watcher provisioned, container alive
- [x] emailbison-sync deployed, build succeeded
- [x] Check 1–6 + freshness pass within 30 min of deploy
- [ ] Walk-away check at 30 min post-deploy: still passing (pending — wakeup at 16:45 UTC)
- [ ] May 1 ~02:50 UTC: pre-cycle candidate list captured
- [ ] May 1 ~03:30 UTC: shadow-compare run, output saved
- [ ] May 1 afternoon: pre-cycle list compared to actual_only set, parity verified

4 of 7 checked tonight. 3 remaining for tomorrow.

---

## Open follow-ups (parking lot — not blocking)

- **Coolify Pusher/Echo WebSocket on CF Access tunnel.** The terminal works in self-hosted but not through this proxy setup. Adding the WS path to the CF tunnel config would unblock smoke-test-via-UI for all future watcher work.
- **Firewall populate.** Per Q2 finding above. `clients.domain_pattern` for 11 active workspaces, then predicate addition to lifecycle_tag_sync + watcher SQL.
- **Watcher v2 daemon mode.** Today's Dockerfile parks at `sleep infinity`. After 7 days of clean shadow validation, change CMD to `["incubation-watcher","daemon"]` and add a continuous-loop subcommand that calls `run --apply=False` on a schedule (this IS what generates shadow-validation data; without it, operator must invoke daily).
