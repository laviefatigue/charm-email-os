---
title: Inbox Integrity Program — Master Tracker
created: 2026-04-30
updated: 2026-05-12 (Plan F deployed + 706-inbox backfill applied; EOD v2 architecture revised to event-driven per operator direction)
status: ACTIVE
purpose: Single-page index of all in-flight inbox-state-machine work
review-cadence: end of each session, update statuses
---

# Inbox Integrity Program — Master Tracker

> **One page to read if you want to know everything in flight.** This index
> covers all plans, decisions, code changes, and operator actions tied to
> the inbox state machine, accuracy validation, cross-workspace integrity,
> connection handling, and emailbison-sync decomposition.
>
> If a workstream isn't here, it isn't being tracked. Add it.

---

## 1. Program scope

We're addressing four interconnected problems in the inbox state machine:

| # | Problem | Symptom |
|:-:|---------|---------|
| 1 | **Cross-workspace pollution** — Hypertide provisioning sometimes places inboxes in the wrong EB workspace | 82-inbox audit on 2026-04-29; 22 SPUI live in Sammy creating cross-tenant leak risk |
| 2 | **Connection ↔ Kill conflation** — disconnect was treated as a terminal kill, producing zombies on reconnect | ~1,200 fleet-wide rows marked dead in DB while Connected & sending in EB |
| 3 | **Silent EB tag failures** — kill/graduation paths swallowed EB API errors, producing DB↔EB drift | 6 SKMR stuck-in-incubation rows; 10 Spout pool-tag drift rows |
| 4 | **Operational sprawl** — emailbison-sync runs ~14 concerns; bugs in one are invisible because others keep running | Sammy lifecycle was processing 0 records (legitimately) but indistinguishable from "broken" without per-concern observability |

These aren't independent — fixing #2 requires verifying #3 first, fixing #4 requires the data flowing through it to be accurate (gated on #1, #2, #3).

## 2. Constituent plans

Each plan is a deep-dive document. This index is the cross-reference. Status as of 2026-05-02 (post inbox-audit-overhaul Phase 4 deploy):

| Plan | Lines | Status | What shipped | What remains |
|------|------:|--------|--------------|--------------|
| [cross-workspace-integrity-firewall.md](cross-workspace-integrity-firewall.md) | ~600 | **COMPLETE** | All 8 phases shipped + Phase 0d EB-side audit + cleanup. Migration 101 (columns) + 103 (CHECK constraint) live. `clients.domain_pattern` populated for all 11 workspaces. Phase 5a (upsert gate) + 5b (lifecycle_tag_sync guards) shipped. **HR-1 enforced structurally at DB layer.** | Phase 3 (backfill) was a no-op since 0 outliers — closed. |
| [connection-state-machine.md](connection-state-machine.md) | ~400 | PARTIAL | Phase 1 (disconnected_timeout removed) shipped 2026-04-30 | Phases 2-6 pending. Phase 2 (notification ladder) is the next natural ship. |
| [emailbison-sync-decomposition.md](emailbison-sync-decomposition.md) | ~600 | IN PROGRESS | Phase 2 (`apps/incubation-watcher/` extracted) shipped 2026-04-30 | Phase 3 (shadow validation) running — 1 day in of 7 needed. Phase 4 (cutover) gated on shadow data. Phase 4a (daemon mode) needed for shadow data to accumulate without operator intervention. |
| [kill-trigger-accuracy.md](kill-trigger-accuracy.md) | ~500 | **PARTIALLY SUPERSEDED by ADR-010** | Passes 1, 2, 3, 4 shipped (docs rewrite + bounce-FBL disable + sender-ban alert-first + body_full retention + silent-error fix). 23+25+69 = 117 unit tests. | Bounce classification work still load-bearing (read by new lifetime-rate rule). Threshold work absorbed by ADR-010. Pass 5 BLOCKED on operator (no JMRP/Postmaster). Pass 6 optional. |
| [kill-rule-rate-based-rewrite.md](kill-rule-rate-based-rewrite.md) | ~400 | **SHIPPED — fully load-bearing** | Migration 105 + code (commits `5118d59` / `b55531b` / `f42cf0e`, prod at `b55531bd`). Phase 1-4 all complete on 2026-05-04. 307 false positives revived, 63 legitimate kills processed under new rule (SKMR 27, Hello Hero 23, Search Atlas 7, Spout 4, SPUI+Linkgraph 1 each). 22+12 tests green. ADR-010 accepted. Two deploy-side bugs surfaced + fixed in passing (`force=false` cache, git remote mismatch). | Phase 5 (cleanup of legacy `_24h`/`_7d` columns + `aggregate_bounce_counts_from_events` + `_thresholds_for_esp` + `@_OBSOLETE_COUNT_RULE` tests) waits one release cycle. |
| [event-driven-architecture.md](event-driven-architecture.md) | ~700 | **LIVE in production** (cutover 2026-05-05 23:35 UTC) | Phases 1-5 all SHIPPED + cutover EXECUTED. Master at `3888dfd`. Migrations 107+108 applied; 7 triggers (`trg_*`) enabled; EventListener consuming `pg_notify`; TagOpWorker draining per-workspace. Verified end-to-end at 05:48 UTC via Charm package_assigned cascade — single UPDATE drove `package_assigned → 42 pool_changed → 84 tag_op_*` events through Tier 1+2, all completed in 1.4s with 0 failures. **Steady-state pickup latency 2-5ms** (target was <5s). 3,908 events processed in first 5.5h, 0 failed/orphaned/stalled. Cutover sequence + post-mortem: see `docs/work-logs/2026-05-05-migration-unblock-and-event-driven-planning.md` "CUTOVER EXECUTED" + "Full end-to-end verification" sections. Operator runbook: `docs/operations/2026-05-05-event-driven-cutover-runbook.md`. | Gate 5: 7-day shadow soak with `set_tag_sync` co-execution (passive, ends ~2026-05-12). Gate 6: drop `set_tag_sync` runs from poll loop (after Gate 5 clean). Phase 5+ deferred handlers (sender_ban_detected, graduated, reconnected) — design exists, ship later. **disconnect_observed handler explicitly REJECTED** per D-N (pool/conn orthogonality decision 2026-05-06). |
| [inbox-audit-overhaul.md](inbox-audit-overhaul.md) | ~150 | **MOSTLY COMPLETE** | Phases 1+2+3+4 shipped 2026-05-01/02. Migration 104 (workspace_id + JSONB columns) live; `InboxAuditor` class produces 8 integrity sections per workspace (I-1..I-7, I-9); daily dispatch wired into `emailbison_sync_worker.poll_loop`; Phase 4 subscription-cancel rollup with 14-day reuse window + `live`/`dead` × `Connected`/`Disconnected` breakdown live. First Phase 4 run 2026-05-02 00:28 UTC: 57 eligible cancel candidates across 7 workspaces. | Phase 5 (Slack restructure) + Phase 6 (SLA enforcement) pending. I-8 (pool-tag drift) deferred — requires EB API calls. |
| [eod-campaign-reapply.md](eod-campaign-reapply.md) | ~600 | **v1 SHIPPED** (operator CLI); v2 architecture revised 2026-05-12 to event-driven (no polling); awaiting L5 staging + v2 build | v1 CLI shipped at `apps/eod-reapply/`. 209 tests passing (99% coverage), tested through L4 (mocked unit + integration). Core loop: pull EB campaign senders, pull EB senders with `live` tag, diff, pause→attach→remove→verify→resume. Library function `reapply_campaign(...)` already supports v2 daemon import unchanged. Doc refresh 2026-05-08 (status, event-driven impact, sister mechanism: warmup-disable-on-kill). **v2 architecture revision 2026-05-12 per operator direction**: event-driven scheduler (pg_sleep_until + NOTIFY) replaces the original 5-min polling design; ~60% smaller schema delta (1 new table vs 2 + columns); reuses event_log + LISTEN/NOTIFY infra (Phase 1-5 already live). Concurrency model documented: same per-workspace serialization + cross-workspace parallel pattern as Tier 2 TagOpWorker. | **L5 real-EB staging gate (Barrena pilot)**, then **v2 event-driven daemon** (scheduler + handler in shared `event_handlers/` registry). Migration 111 (campaign_reapply_jobs table + trigger + CHECK broaden). |
| [warmup-disable-on-kill — TBD plan doc; sketch in eod-campaign-reapply.md "Sister mechanism"](eod-campaign-reapply.md) | — | **DESIGNED — not built** | Audit 2026-05-08 found **318 dead inboxes still receiving bounces**, some 3+ months post-kill (e.g. bhoumik@stylespui.com killed 2026-02-14, last bounce 2026-05-08 15:17 UTC). Root cause: kill cascade marks DB+EB tags but doesn't disable warmup → EB warmup daemon keeps sending → reputation bleed. **Design**: extend `kill_queued_handler` to UPDATE `warmup_enabled=FALSE` and enqueue new `warmup_disable` event type drained by Tier 2 (or sibling worker) that calls EB to disable warmup. Operator approved 2026-05-08; ~1d engineering + 1d backfill. Per ADR-006 partitioning rule, workspace-scoped EB key. | (1) Add `warmup_enabled=FALSE` to `kill_queued_handler` UPDATE. (2) Add `warmup_disable` event_type + handler. (3) Add `EmailBisonClient.disable_warmup()`. (4) Tests. (5) Backfill script for existing 318 affected. |

Plus the foundational records:

| Document | Type | Status |
|----------|------|--------|
| [docs/adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md](../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md) | ADR | accepted |
| [docs/adr/adr-010-lifetime-rate-kill-rule-2026-05-04.md](../adr/adr-010-lifetime-rate-kill-rule-2026-05-04.md) | ADR | accepted (2026-05-04) |
| [docs/work-logs/2026-05-04-kill-rule-rate-rewrite-and-revival.md](../work-logs/2026-05-04-kill-rule-rate-rewrite-and-revival.md) | Work log | Phase 1-4 shipped: 307 revivals + 63 kills + post-mortem on two deploy-side bugs |
| [docs/work-logs/2026-04-30-systems-accuracy-and-cleanup.md](../work-logs/2026-04-30-systems-accuracy-and-cleanup.md) | Work log | active |
| [docs/audits/2026-04-30-system-accuracy-snapshot.json](../audits/2026-04-30-system-accuracy-snapshot.json) | Audit data | snapshot — re-run periodically |
| [docs/audits/2026-04-30-zombie-review-charm.csv](../audits/2026-04-30-zombie-review-charm.csv) | Operator queue | awaiting operator |

---

## 2.1 Production deploy gotcha (2026-05-04 lesson)

The repo has TWO remotes. **Both must be pushed for production deploys to pick up changes:**

```sh
git push origin master      # backup / dev
git push hirecharm master   # production — Coolify pulls from here
py scripts/coolify.py deploy <APP_NAME>   # force=true is now default (commit f42cf0e)
```

`origin` points to `laviefatigue/charm-email-os` (personal fork).
`hirecharm` points to `HireCharm/charm-email-os` (Coolify source).
Pushing to only one and triggering a Coolify deploy silently deploys
stale code. Diagnosed and fixed during the kill-rule rewrite —
see [docs/work-logs/2026-05-04-kill-rule-rate-rewrite-and-revival.md](../work-logs/2026-05-04-kill-rule-rate-rewrite-and-revival.md) § "Post-mortem."

## 2.2 Coolify env-var duplication self-heal (2026-05-05 lesson)

Coolify allows multiple env entries with the same key (each has its
own UUID). Coolify PATCH on the collection endpoint only updates the
first match, leaving stale duplicates with old values. This bit us
2026-05-05 when `KILL_RULE_DRY_RUN` had two entries (`false` + `true`)
and the rule's behavior on container restart became non-deterministic.

`scripts/coolify.py env-set` now self-heals on every call: if multiple
entries share the key, extras are deleted before the PATCH/POST. Fix
shipped in commit `c51ce9e`. **Always use `scripts/coolify.py env-set`,
never set env vars via the Coolify UI directly** — UI sets bypass the
self-heal.

## 2.3 Per-workspace EB API key partitioning (load-bearing rule)

**Every EB API call uses a workspace-scoped key.** No global key. Ever.

This is enforced in:
- `kill_processor.py` — `process_workspace_queue(workspace_id, name)` per ADR-006
- `workspace_writes.py` — orchestrator iterates workspaces, builds workspace-scoped client per workspace
- `set_tag_sync.py` — same pattern
- `lifecycle_tag_sync.py` — same
- `scripts/resurrect_false_positive_kills.py` — uses `workspace_api_keys.key_token` per inbox
- `scripts/cleanup_eb_tag_drift.py` — same

The event-driven architecture ([event-driven-architecture.md](event-driven-architecture.md))
inherits this rule. Tier 2 batch tag worker iterates workspaces with
their own EB clients; `event_log.workspace_id` is NOT NULL via CHECK
constraint for any tag_op event.

If you ever need to add an EB-touching code path, **start by reading
the workspace's `workspace_api_keys.key_token`**. There is no other
correct way.

---

## 3. Status board — every workstream

Status keys: ✅ done · 🚧 in progress · ⏳ pending · 🔒 blocked · 👤 operator-owned

### 3.1 Code changes (patches + scripts)

| Workstream | Status | Owner | Commit | Notes |
|------------|:------:|-------|--------|-------|
| [lifecycle_tag_sync silent-failure patch (workspace orphan on EB 404)](../../sync_modules/lifecycle_tag_sync.py) | ✅ | system | `94fd0fa` | Skips ORPHAN inboxes loudly instead of retrying forever |
| [lifecycle_tag_sync race-condition + loop-kill hardening (4 functions)](../../sync_modules/lifecycle_tag_sync.py) | ✅ | system | `d775761` | (1) Race re-check inside DB transaction. (2) Per-row except Exception in 4 loops. (3) 404 vs transient distinction in _remove_live_from_dead. |
| [Phase 1: remove disconnected_timeout from kill triggers](../../sync_modules/health_checks.py) | ✅ | system | `94fd0fa` | Stops new disconnect-zombies from being created |
| [kill_processor pool-tag strip silent-failure patch](../../sync_modules/kill_processor.py) | ✅ | system | `e7bbd59` | Distinguishes 404 from transient errors; transient errors raise to outer except for retry |
| [set_tag_sync silent-failure hardening (3 bugs in per-domain + per-inbox loops)](../../sync_modules/set_tag_sync.py) | ✅ | system | `3ef8400` | Per-domain Exception isolation, MS branch broad-except, general branch broad-except |
| [scripts/audit_system_accuracy.py](../../scripts/audit_system_accuracy.py) | ✅ | system | `94fd0fa` | Read-only DB↔EB drift gate |
| [scripts/generate_zombie_review_csv.py](../../scripts/generate_zombie_review_csv.py) | ✅ | system | `94fd0fa` | Read-only operator review queue per workspace |
| [scripts/audit_disconnect_milestones.py](../../scripts/audit_disconnect_milestones.py) | ✅ | system | `6a6bd68` | Read-only disconnect ladder + subscription-cancel signal |
| [scripts/audit_package_assignments.py](../../scripts/audit_package_assignments.py) | ✅ | system | `f33d355` | Read-only workspace package recommendation CSV |
| **[Event-driven Phase 1-5 cutover (Tier 1 listener + Tier 2 TagOpWorker LIVE)](../operations/2026-05-05-event-driven-cutover-runbook.md)** | ✅ | system | `df06e85` → `3283b40` | 5 phases shipped + cutover executed 2026-05-05 23:35 UTC. End-to-end verified at 05:48 via Charm cascade. 3,908 events / 0 failures in first 5.5h. |
| [scripts/audit_tags_fleet.py — split connection-health from tag drift](../../scripts/audit_tags_fleet.py) | ✅ | system | `3888dfd` | Categorizer skips disconnected inboxes for tag-drift checks (matches set_tag_sync's line 467 skip). Output now has two sections: actionable drift + informational connection health. Pre-fix audit reported 3 missing_reserve_tag in Charm; post-fix: 0 actionable drift fleet-wide. |
| [scripts/shadow_compare_per_workspace.py — per-workspace incubation parity check](../../scripts/shadow_compare_per_workspace.py) | ✅ | system | `a5a5b3d` | Companion to runbook §2.1. Mirrors apps/incubation-watcher/shadow.py logic across all 4 graduating workspaces in one round-trip. Verified watcher_only=0 fleet-wide pre-cutover. |
| Charm `workspace.package_id` set to `50k_google` base (operational) | ✅ | operator | (DB UPDATE 2026-05-06 15:30 UTC) | Resolved Charm latent-capacity stall (42 graduated Gmail reserves were idle). Side effect: triggered the first end-to-end event-driven cascade verification — `package_assigned → 42 pool_changed → 84 tag_op_*` all drained successfully. |

### 3.2 Documentation (today's session)

| Document | Status | Commit |
|----------|:------:|--------|
| [docs/plans/cross-workspace-integrity-firewall.md](cross-workspace-integrity-firewall.md) | ✅ written | `94fd0fa` |
| [docs/plans/connection-state-machine.md](connection-state-machine.md) | ✅ written | `94fd0fa` |
| [docs/plans/emailbison-sync-decomposition.md](emailbison-sync-decomposition.md) | ✅ written | `94fd0fa` |
| [docs/adr/adr-009-...md](../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md) | ✅ written | `6d5f2a3` |
| [docs/work-logs/2026-04-30-...md](../work-logs/2026-04-30-systems-accuracy-and-cleanup.md) | ✅ written | `94fd0fa` + `6d5f2a3` |
| [docs/concepts/kill-triggers.md](../concepts/kill-triggers.md) | ✅ updated (disconnected_timeout removed from tables) | `6d5f2a3` |
| [production/coolify/services.md](../../production/coolify/services.md) | ✅ updated (connection state, silent-failure hardening, audits) | `6d5f2a3` |
| [docs/plans/inbox-audit-overhaul.md](inbox-audit-overhaul.md) | ✅ Phases 1–4 SHIPPED — production-live, 5+6 pending | `f36d70d` + `534d56e` + `ce931d3` + `642e9c4` + `4be0887` + `bfb7e2a` |
| [apps/incubation-watcher/HANDOFF.md](../../apps/incubation-watcher/HANDOFF.md) | ✅ self-contained handoff | `72b901d` |
| **[docs/operations/2026-04-30-deploy-runbook.md](../operations/2026-04-30-deploy-runbook.md)** | ✅ **METHODIC DEPLOY RUNBOOK — operator's primary doc for landing today's 13 commits** | `675d3aa` |
| [docs/operations/2026-04-30-deploy-quickref.md](../operations/2026-04-30-deploy-quickref.md) | ✅ written | `bc5744b` |
| **[docs/work-logs/2026-04-30-deploy-outcome.md](../work-logs/2026-04-30-deploy-outcome.md)** | ✅ **TODAY'S DEPLOY OUTCOME — 6/6 verification checks PASS, walk-away monitor scheduled, May 1 morning checklist** | (this commit) |
| **[docs/plans/kill-trigger-accuracy.md](kill-trigger-accuracy.md)** | ✅ **drafted 2026-05-01 evening — bounce classification + spam_complaint correctness, 5-phase plan** | (this commit) |
| **THIS DOC** (`INBOX-INTEGRITY-PROGRAM.md`) | 🚧 updated end of evening session 2026-05-01 | — |

### 3.3 Cross-workspace integrity firewall (Plan A)

| # | Phase | Status | Blocker | Notes |
|:-:|-------|:------:|---------|-------|
| 0 | Operator confirms keyword seed table (§6 of plan) | ✅ | — | All 11 active workspace patterns confirmed 2026-05-01 via data-driven extraction. See D-F + D-L. |
| 0a | **Audit 2026-04-30 evening: confirmed firewall coverage = 0% in production** | ✅ | — | 9 of 11 active workspaces had `clients.domain_pattern = NULL`; Charm + Selery had empty string `""`. RESOLVED Phase 2. |
| 0b | **Cleanup 2026-05-01: soft-deleted 143 unpurchased candidate domains + forward prevention** | ✅ | — | Charm 86 + Selery 57 unpurchased rows had `is_active=TRUE` despite never being purchased. Soft-deleted. Forward prevention: 4 code changes (commit `ba39fe5`). Active count now: Charm 40, Selery 50, others unchanged. |
| 0c | Audit 2026-05-01: data-driven domain pattern extraction per workspace | ✅ | — | Pulled all owned domains, extracted brand keywords. 0 inbox-level cross-pollution detected across all 11 workspaces / 4,207 active inboxes. 4 new Charm sub-brands (eudalie-bio, inspi-cure-eu, mydealslift, stylepad24) confirmed legitimate per D-F. |
| 0d | Fleet-wide EB tenant audit + Sammy zombie cleanup | ✅ | — | Pulled all 11 workspaces' EB tenants via API. Found Sammy EB clean (historical "22 SPUI in Sammy" issue resolved). Found 2 setspui rows in Spout EB tenant (cross-tenant duplicates with eb_ids 8860/8859 — Phase 5a dedup prevented DB pollution). 22 SPUI-domain DB rows still labeled `workspace_id=Sammy` (cosmetic — already dead/inactive, EB confirmed in SPUI tenant since 2026-04-30 17:34 kill). Cleanup SQL: moved 22 to `workspace_id=SPUI`, annotated 2 setspui rows. SPUI now: 82 active+live / 13 active+dead / 81 inactive+live / 45 inactive+dead (was 23 dead, +22 zombies = 45). Operator action remaining: clean 2 cross-tenant duplicates from EB Spout via EB UI. |
| 1 | **Migration 101: schema (is_quarantined columns, no CHECK yet)** | ✅ | — | Shipped 2026-05-01 evening (commit `96b6257`). 3 columns + partial index. 0/4786 quarantined initially. |
| 2 | **Populate clients.domain_pattern with seed** | ✅ | — | Shipped 2026-05-01 (commit `9c799b1`). All 11 workspaces. Verified 0 outliers across 4,207 active inboxes. |
| 3 | Backfill: quarantine existing pollution | ✅ closed | — | NO-OP — the 2026-05-01 fleet audit (Phase 0d) confirmed 0 cross-tenant pollution at the inbox level across all 11 workspaces. Phase 0d cleanup additionally moved 22 SPUI-Sammy zombies. No backfill SQL needed. |
| 4 | **Migration 103: chk_quarantined_no_pool CHECK constraint** | ✅ | — | Shipped 2026-05-01 evening (commit `060cabe`). HR-1 enforced structurally. Real violation attempt rejected with proper error. |
| 5a | **Phase 5a: gate at sync_accounts.upsert** | ✅ | — | Shipped 2026-05-01 (commit `f43b7b4`). `matches_workspace_pattern()` helper + 25 unit tests. Per-row `is_quarantined` computed at upsert time. Pool forced NULL on quarantined rows. Shadow check verified 0 false positives. |
| 5b | **Phase 5b: lifecycle_tag_sync downstream guards** | ✅ | — | Shipped 2026-05-01 (commit `c9a437c`). 3 SQL guards added: `_graduate_mature_inboxes` SELECT + UPDATE race-check + `_tag_new_warmup_inboxes` SELECT. Refuses to graduate or EB-tag quarantined rows. |
| 6 | Tests + audit gate verification | ✅ | — | 25 firewall unit tests at `tests/test_firewall.py`; full test suite 221 passed / 29 skipped. Production shadow check: 0 outliers across 4,207 active inboxes. |
| 7 | Deploy + post-deploy verification | ✅ | — | emailbison-sync redeployed twice for Phase 5a + 5b. Verified `running:healthy` post-deploy. Active accounts sync (Barrena 39 records / 0 failed) confirmed firewall code path executes cleanly in production. |
| 8 | eod-reapply integration (refuse target if quarantined inbox in workspace) | ⏳ | — | Future — when an operator runs eod-reapply, refuse to retarget any quarantined inbox in the target workspace. Currently no quarantined rows so it's a no-op; ship when convenient. |

### 3.4 Connection state machine (Plan B)

> **2026-05-06 architectural anchor:** D-N codified pool_status and connection
> status as orthogonal axes. Disconnected inboxes keep their pool role across
> disconnects; EB triggers reconnect automatically; operators handle remedy if
> auto-reconnect fails. This locks Phase 4 below as REJECTED — `set_tag_sync`'s
> Connected filter is correct, not a bug. Phase 2 (notification ladder) remains
> the next natural ship and is now strategically aligned: it surfaces
> disconnect signals so operators can act, without trying to mutate pool state.

| # | Phase | Status | Blocker | Notes |
|:-:|-------|:------:|---------|-------|
| 1 | Remove `disconnected_timeout` from KILL_THRESHOLDS | ✅ | — | Shipped commit `94fd0fa` |
| 2 | ~~Notification ladder (24h/3d/7d/20d Slack alerts)~~ → Disconnect report (LIST) | ✅ **ALREADY SHIPPED** as part of 7-page operator queue UI (commit `35e538c`) | — | **Re-scoped per operator 2026-05-06 → discovered already shipped.** The `/reports/disconnects` page (frontend `charm-email-os/app/reports/disconnects/page.tsx` + backend `api/routes/reports.py:57 report_disconnects`) lists every disconnected inbox, **grouped by workspace** (`groupBy="workspace_name"`), with `hours_disconnected` column, ESP-aware thresholds (Microsoft 48h, Google/other 24h), `needs_attention` badge, "Past threshold only" toggle, CSV download. Sorted by oldest disconnect first within each workspace. **No new work needed.** Optional follow-up: change `hours_disconnected` (1.5h precision) to `days_disconnected` if operator prefers, but current format is more useful for short disconnects. |
| 3 | EB connection tags (`disconnected_24h`, etc) auto-applied | ⏳ | accuracy gate: status mirror validated | Defer until accuracy proven |
| 4 | ~~Drop `status='Connected'` filter from pool_promotion~~ | ❌ REJECTED | — | Per D-N (2026-05-06): pool and connection are orthogonal axes. `set_tag_sync` line 467 skip-on-disconnect is CORRECT — disconnected inboxes can't receive EB tag pushes anyway, and pool_status is preserved for resume-on-reconnect. Phase 4 would have introduced bugs, not fixed them. |
| 5 | Operator-driven zombie restoration per workspace (CSV review) | 👤 | operator | Charm CSV ready; smallest-workspace-first sequence in plan §8 |
| 6 | EB tag cleanup for restored zombies (operator-confirmed) | 👤 | Phase 5 in progress | |

### 3.4b Kill-trigger accuracy (Plan D — bounce classification + spam_complaint correctness)

| # | Phase | Status | Blocker | Notes |
|:-:|-------|:------:|---------|-------|
| 0 | Forensic audit + plan drafted | ✅ | — | [kill-trigger-accuracy.md](kill-trigger-accuracy.md). Proved 0/383 historical spam_complaint kills had direct evidence; 5/5 sampled were FPs from bounce-text heuristic firing on admin-policy NDRs. |
| 1 | Rewrite `docs/concepts/kill-triggers.md` SMTP table — full B2B map (MS365 + Google Workspace, ~25 codes incl. 8 production codes) | ✅ | — | Shipped commit `a206da3`. Zero behavior change — pure documentation. Provider column, sender-ban severity flags, JMRP + Postmaster Tools out-of-band FBL section. |
| 2 | Disable bounce-FBL inference at `sync_events.py:468-470` | ✅ | — | Shipped commit `8dd3011`. One-line `is_spam=False` for `folder='bounced'`. Production sample: 2/72 hard_blocked bounces (2.8%) were firing the false-positive heuristic — both fitnessintl.com mail-flow rule blocks. Function preserved for future use; only call site disabled. **69-test parser suite** at `tests/test_bounce_parsing.py` pins behavior. |
| 3 | **Add sender-ban code detection (5.7.501-511 family) — alert-first** | ✅ | — | Shipped 2026-05-01 evening (commit 5688789). 10 exact codes + 5.7.606-649 IP range. 5.7.509 (DMARC reject) deliberately excluded after production sanity check showed 11 hits/30d (alignment issue, not ban). Slack alerts at critical level on first hit. NO kill behavior change — alert-first per plan. 23 unit tests + production verification: 0 alerts would have fired in last 30 days. |
| 4 | Keep `body_full` for bounces + silent-error fix at `sync_campaign_replies` | ✅ | — | Shipped commit `995cd74`. Three changes: (a) `body_full` no longer wiped for bounces (forensic capability) — existing 90-day `cleanup_bounce_messages` retention covers cleanup. (b) Per-reply errors now reach `audit.add_error()` instead of `print()`. (c) Per-folder fetch errors same fix. `[silent-error-fallback]` print marker for legacy callers. |
| 5 | ~~Out-of-band FBL ingestion~~ — **BLOCKED on operator decisions, not engineering** | 🔒 | ⚠ Charm has no Postmaster Tools access, no JMRP enrollment | **Confirmed 2026-05-01 via EB-API audit + operator confirmation.** EB's `/replies?folder=spam` always empty; `emailbison_campaigns.complaints` always 0; no FBL recipient registered. Practical implication: complaint detection is heuristic-only via `detect_spam_in_response` phrase match. See `docs/concepts/kill-triggers.md` § "Spam complaint detection" for full constraint analysis. Future-pending engineering: engagement decay detection (uses open/reply data we already sync as a proxy reputation signal). |
| 6 | Apply same audit.add_error pattern to sync_modules/sync_campaigns.py + sync_engagement.py | ⏳ | — | Production audit at 2026-05-01 19:30 UTC: campaigns sync has 242 records_failed/24h with `error_message=null` (61 of 222 runs status=partial); engagement sync has 1597 records_failed/24h with same null pattern (7 of 11 runs partial). Counts are tracked, root cause is not. Apply Pass 4 pattern to surface error detail. Different module from sync_events; out of scope for original Plan D but discovered via Pass 4 audit. |

### 3.5 Decomposition (Plan C — minimum-viable scope)

| # | Phase | Status | Blocker | Notes |
|:-:|-------|:------:|---------|-------|
| 1 | Validate baseline accuracy (audit script passes for relevant workspaces) | 🚧 | 9 of 11 pass; SPUI + Spout fail | Could proceed for the 9 passing |
| 2 | Extract `apps/incubation-watcher/` (lifecycle_tag_sync only) | ✅ | — | Shipped 2026-04-30 evening. Coolify UUID `pssgc0c8w4sooos8gs0scsos`. Container alive in `sleep infinity` mode for shadow validation (no daemon yet — operator-invoked). 31 unit tests pass. |
| 3 | Shadow-mode validation 7+ days | 🚧 | starts May 1 morning capture | First capture: `incubation-watcher check --workspace Charm` at ~02:50 UTC, then `shadow-compare --since 2026-05-01T00:00:00Z` at ~03:30 UTC. ⚠ `coolify.py exec` does not exist — use local invocation with prod env vars OR `run-sql` HTTP endpoint. |
| 4 | Switch ownership: feature-flag off in emailbison-sync, on in incubation-watcher | ⏳ | 7 days clean shadow validation | |
| 4a | v2 daemon mode (continuous loop) | ⏳ | after Phase 4 cutover OR alongside it | Today's Dockerfile is `CMD ["sleep","infinity"]`. v2 changes to `CMD ["incubation-watcher","daemon"]` + new `daemon` subcommand that loops `run --apply=False` on a schedule. Without daemon mode, operator must invoke daily — the shadow-validation data the cutover decision needs. |
| 5 | Decide whether to extract `kill-watcher`, `inventory-manager`, `tag-writer` based on Phase 4 outcomes | ⏳ | 30 days post-Phase-4 | Don't commit to all 6 services until incubation-watcher proves the pattern |

### 3.5b EOD Campaign Reapply (Plan E)

| # | Phase | Status | Blocker | Notes |
|:-:|-------|:------:|---------|-------|
| 1 | v1 CLI: per-(workspace, campaign) reapply tool | ✅ | — | Shipped at `apps/eod-reapply/`. 243 tests now (post PR 1). Library function `reapply_campaign(...)` consumed by v2 daemon unchanged. |
| 2 | L5 real-EB staging gate | ✅ ATTACH validated 2026-05-13 | REMOVE path needs fresh test campaign | Ran against Charm Test-Campaign 271. Two latent bugs found+fixed during staging: filter-shape silent-ignore (`tag_ids[0]` is correct; `filters[tag_ids][]` silently returns workspace total) and async-delete false-negative (verify needs settle-retry). See `apps/eod-reapply/docs/staging-results.md`. |
| 3a | v2 event-driven scheduler design | ✅ | — | 2026-05-12: revised v2 architecture to event-driven (no polling). Per-workspace asyncio.Lock for same-workspace serialization. Schema discipline: 1 new table, no cache table, no parallel runs table. Reuses event_log. See `eod-campaign-reapply.md` § "Architecture v2". |
| 3b-PR1 | v2 daemon scaffold (dry-run-only) | ✅ SHIPPED 2026-05-13 | — | Migration 111 adds `campaign_reapply_jobs` + `workspaces.eod_reapply_enabled` flag (default FALSE). `apps/eod-reapply/src/eod_reapply/daemon.py` provides enqueuer + worker coroutines. CLI subcommand `eod-reapply daemon`. **`apply=False` hard-locked in PR 1.** 18 new tests. Deploy via Coolify Pattern C (services.md). |
| 3b-PR2 | apply-mode + crash recovery + alerting | ⏳ NEXT | PR 1 deployed + dry-run-validated | Flip `dry_run_only=False`, add startup-scan resume-by-us, Slack alert on `FAILED_LEFT_PAUSED`. ~half day. |
| 3b-PR3 | validation audit (killed-inbox-no-sends-post-EOD) | ⏳ | PR 2 in apply-mode | Daily check: for kill events with `T_kill`, ensure no campaign sends from that inbox after that campaign's `T_eod`. Closes the loop without operator scrutiny. ~half day. |
| 4 | Workspace allowlist phased rollout | ⏳ | PR 2 ships | Start with Charm (flag flips from FALSE→TRUE in DB); add one workspace at a time per plan §"Rollout plan". |

### 3.5c Warmup-disable on kill (Plan F — designed 2026-05-08)

| # | Phase | Status | Blocker | Notes |
|:-:|-------|:------:|---------|-------|
| 0 | Audit + design | ✅ | — | Audit found 318 dead inboxes still receiving bounces (e.g. bhoumik@stylespui.com killed 2026-02-14, last bounce 2026-05-08 15:17 UTC). Design sketched in `eod-campaign-reapply.md` §"Sister mechanism". Operator approved 2026-05-08. |
| 1 | Add `warmup_enabled = FALSE` to `kill_queued_handler` UPDATE | ⏳ | — | One-line addition to `sync_modules/event_handlers/kill_chain.py` UPDATE. Same transaction as `inbox_state=dead`. |
| 2 | Add `warmup_disable` event_type | ⏳ | — | Extend event_log schema (the existing CHECK constraint already requires workspace_id NOT NULL on tag_op_*; same applies). Migration. |
| 3 | Handler in Tier 2 `TagOpWorker` (or sibling `WarmupOpWorker`) | ⏳ | Phase 2 | Per-workspace batching reuses existing infrastructure. Per-workspace EB key per ADR-006. Idempotent. |
| 4 | `EmailBisonClient.disable_warmup(account_id)` | ⏳ | — | Need OpenAPI lookup for the right EB endpoint. |
| 5 | Tests (handler logic, idempotency, partitioning) | ⏳ | Phase 1-4 | Pattern from existing `test_event_handlers.py` + `test_tag_op_worker.py`. |
| 6 | Backfill script for the existing 318 affected | ⏳ | Phases 1-5 ship | One-shot: SELECT dead inboxes WHERE warmup_enabled=TRUE → enqueue warmup_disable for each. Tier 2 picks them up on next cycle. |

### 3.6 Operator-driven actions (require human review/decision)

| Workstream | Status | Notes |
|------------|:------:|-------|
| ~~Deploy commits to charm-api + emailbison-sync~~ | ✅ | **emailbison-sync DEPLOYED 2026-04-30 23:12 UTC** (deployment uuid `fo8cwg00k40gk0o0cwog0s00`). 6/6 verification checks PASS, walk-away monitor scheduled. charm-api skipped per quickref §5 (no relevant changes). See deploy-outcome work log. |
| ~~Charm `package_id`~~ → `50k_google` base | ✅ | Operator UPDATE 2026-05-06 15:30 UTC. Resolved latent-capacity stall; 42 reserves promoted to live via the event-driven cascade. |
| **Hello Hero `package_id` is still NULL** | 👤 | Same situation Charm was in pre-2026-05-06. Hello Hero has 422 live + 79 untagged inboxes. Single SQL UPDATE same as Charm. Coordinate with operator before applying — it'll trigger the event-driven cascade and promote any eligible reserves. |
| Charm zombie CSV review (142 rows, 127 currently Connected) | 👤 | [docs/audits/2026-04-30-zombie-review-charm.csv](../audits/2026-04-30-zombie-review-charm.csv) — fill `operator_decision` column, run SQL by hand |
| Re-run accuracy audit weekly | 👤 | `py scripts/audit_system_accuracy.py` (also: `py scripts/audit_tags_fleet.py` post-3888dfd for the split drift+conn-health view) |
| ~~Investigate Spout's 641 disconnected_timeout zombies~~ — RECLASSIFIED 2026-04-30 end of session: Spout has 0 disconnected_timeout zombies. The 641 dead+Connected are CORRECTLY reputation-killed (183 spam, 162 hard_bounces, 267 fresh-inbox failures). 553 of 641 came from a single 2026-02-14 mass provisioning event (550 inboxes killed across 10 *spoutwater.com domains). New investigation: **Hypertide root-cause for the 2026-02-14 batch failure.** | 👤 | See work-log §"Workstream D investigation — Spout 641 reclassified" |
| Cleanup the 10 Spout pool-tag drift rows (operator EB-side untag) | 👤 | Patch shipped to prevent recurrence; existing 10 need manual tag strip via EB UI or scripted untag with operator approval |
| Strip flagged_disconnected_timeout from EB during zombie restoration | 👤 | Per-row, alongside operator restoration in §3.4 Phase 5 |
| Investigate 21-inbox Selery batch-disconnect (Ryan/James/Brittany operators, ~360 sends each) | 👤 | Surfaced 2026-05-06 via audit_tags_fleet.py split. Pattern: 3 humans across 7+ Selery domains, all disconnected after similar send counts → likely OAuth/token/credential issue affecting the cluster. Per D-N (pool/conn orthogonal): system won't auto-remedy, operator handles. |
| Investigate SKMR's 30/35 domains touched by deaths (3 fully dead = cancel candidates) | 👤 | Surfaced 2026-05-06. acceleratestablekernel.com / runstablekernel.com / uncoverstablekernel.com are fully dead (3/3 inboxes). 12 more at 1/3 dead, 15 at 2/3 dead. SKMR domain attrition is workspace-systemic — likely the spam_complaint kill chain (24 in 30d). Worth eyeballing outreach pattern. |

### 3.7 Future / next-sprint

| Item | Owner | Blocker |
|------|-------|---------|
| ADR-008 step 2 — collapse inventory_lifecycle_status + inventory_pool_status into single inbox_status | system | Firewall (Plan A) shipped first |
| Workspace package assignments | operator | Decide which packages each workspace gets (SKMR likely 50k_google) |
| v3-vs-ours kill-trigger comparison on a sending workspace | system | Pick a sending workspace (Hello Hero / Spout / Selery / Search Atlas) |
| inbox_audits overhaul ([plan](inbox-audit-overhaul.md)) | Phases 1–4 SHIPPED | Per-workspace audit live. Subscription-cancel queue (57 eligible domains) populated daily via `audit_data.sections[I-9].details.domains[]`. Phase 5 Slack restructure + Phase 6 SLA enforcement pending. |

---

## 4. Decision log (locked-in)

These are not up for re-debate. Codified across plan docs and ADRs.

| # | Decision | Source | Why it's locked |
|:-:|----------|--------|-----------------|
| D-A | Connection state and kill state are independent tracks | ADR-009 | Conflation produced 1,200 zombies; correctness requires separation |
| D-B | The system never auto-removes inboxes from EmailBison | connection-state-machine.md §0 | Operator handles all destructive cleanup; no exceptions |
| D-C | The system never auto-cancels Hypertide subscriptions | connection-state-machine.md §0 | Same as D-B |
| D-D | Reputation triggers (5) are the ONLY kill triggers | ADR-009 §3 | spam_complaint, hard_bounces_24h, hard_blocked_24h, hard_unknown_24h, fresh_inbox_bounce |
| D-E | Cross-workspace pattern matching uses `clients.domain_pattern` (single field, comma-separated for multi-brand) | firewall plan §6.5 | Schema field already exists; simplest viable pattern |
| D-F | Charm multi-keyword pattern: 9 legitimate brand keywords — `charm` (canonical), `growthgroupusa`, `alldealsgroup`, `globaloutreachclub`, `urosaf-bio`, `eudalie-bio`, `inspi-cure-eu`, `mydealslift`, `stylepad24` | operator confirmed 2026-04-30, extended 2026-05-01 with 4 new sub-brands | Charm operates these as legitimate sub-clients testing through the Charm workspace. Each runs 2-3 inboxes following Charm's per-domain pattern. |
| D-K | Generated domain candidates start `is_active=FALSE`; flipped to TRUE only on `approval_status` transition to `legacy` (operator bulk mark) or `purchased` (Dynadot confirm) | operator-driven cleanup 2026-05-01 (143 unpurchased rows soft-deleted) | Generated = idea, not real. Active set must reference owned domains only. Forward prevention shipped commit `ba39fe5` (4 code changes across infrastructure.py, domains.py, domain_sourcing.py). |
| D-L | Domain pattern matching uses comma-separated substring approach in `clients.domain_pattern`. SQL predicate: `EXISTS (SELECT 1 FROM unnest(string_to_array(c.domain_pattern, ',')) AS pat WHERE email_address ILIKE '%' \|\| trim(pat) \|\| '%')`. Handles both multi-keyword (Charm 9-pattern) and concatenated-brand (linkgraph, hellohero, searchatlas, stablekernel, spoutwater) cases natively. | operator confirmed 2026-05-01 | Verified 0 outliers across all 4,207 active inboxes in 11 workspaces. |
| D-M | **Charm operates with NO out-of-band complaint feedback channel.** Not enrolled in Microsoft JMRP. No Gmail Postmaster Tools access. EB's `/replies?folder=spam` always empty, `emailbison_campaigns.complaints` always 0. Complaint detection is response-parsing only — `detect_spam_in_response` phrase match on lead replies. The Health V3 `1 spam complaint = death` rule fires correctly when triggered, but coverage is much lower than the spec implies. **Real reputation defense is `hard_blocked_24h ≥ 2` + sender-ban code detection (Pass 3).** | operator confirmed 2026-05-01 | This locks in the response-parsing-only constraint. Plan D Pass 5 (apps/fbl-consumer) is BLOCKED until operator enrolls in JMRP and/or Postmaster Tools. Until then, build engagement-decay detection as the proxy reputation signal. |
| D-G | Observation before automation — accuracy gates must pass before automated actions on system data | this session's revision | The system was demonstrably wrong for months; trust must be earned |
| D-H | Decomposition scope: extract incubation-watcher only first, decide on rest after 30-day validation | decomposition plan §2.1 | Avoid premature 6-service commitment |
| D-I | NULL pattern in clients.domain_pattern → quarantine all inboxes (fail-closed) | firewall plan §10 D-2 | New clients must be configured before any inbox can pool |
| D-J | Restoration is operator-driven, manual SQL per row, smallest-workspace-first | connection plan §8 | The system that produced the bug cannot be trusted to auto-fix the bug |
| D-N | **`inventory_pool_status` and `status` (connection) are orthogonal axes.** Disconnected inboxes keep their pool role across disconnects so they resume on reconnect; EB triggers reconnect automatically; operators handle remedy if EB doesn't recover. The system does NOT clear pool_status on disconnect, and there is NO automated DB-side remedy. | operator decision 2026-05-06 (during audit_tags_fleet review) | Conflating the two would force pool re-planning on every transient connection blip. Codified in `set_tag_sync.py:467` (deliberate skip-on-disconnect) and `audit_tags_fleet.py` (3888dfd: separate connection-health bucket from drift). Memory: `pool-vs-connection-orthogonal.md`. |

## 5. Open decisions (need operator input before unblocking)

| # | Decision | Default if unanswered | Block on |
|:-:|----------|----------------------|----------|
| O-1 | Confirm keyword seed for all 11 active workspaces | proposed table in firewall plan §6 | Phase 0 of firewall plan |
| O-2 | When to schedule deploy of `94fd0fa` + `6d5f2a3`? | "this week" | Production sync rolls in patch |
| O-3 | Which workspace pilots the zombie restoration first? | Stable Kernel (smallest, 6 zombies) per plan §8 | Phase 5 of connection plan |
| O-4 | Spout root-cause investigation timeline | open | §3.6 Spout investigation |
| O-5 | Backfill the 10 Spout pool-tag drift rows now (EB-side strip), or leave for next operator review pass? | leave | Cosmetic only; not blocking new kills |
| O-6 | When to begin `apps/incubation-watcher/` extraction work? | after 7-day validation of `94fd0fa` patches in production | §3.5 Phase 2 |

## 6. Risks & mitigations

| Risk | Probability | Impact | Mitigation |
|------|:-----------:|:------:|------------|
| New Hypertide pollution batch lands before firewall ships | Medium-High | Cross-tenant exposure | Manual operator review of audit; firewall is the durable mitigation |
| Operator forgets to set domain_pattern on new client → all inboxes quarantine | Medium | New client onboarding stalls | Audit alert when NULL-pattern client has any inbox; documented in plan §10 |
| Zombie restoration accidentally restores reputation-killed row | Low | Inbox returns to active, reputational risk re-emerges | Per-row review with `reputation_clean_heuristic` column; operator validates before SQL |
| kill_processor patch causes new EB-pending retry loops on persistent EB issues | Low | Slack alert noise | Audit metric on `kill_queue.status='eb_pending' > 4 retries` to surface persistent failures |
| Decomposition introduces a regression that's only visible in shadow mode | Medium | Delayed extraction | 7+ day shadow validation before switch; rollback by feature-flag |
| Accuracy audit results drift between snapshots (regression undetected) | Medium | Decisions made on stale data | Run audit weekly; alert on any gate flipping pass→fail |

## 7. Vocabulary (pinned)

Confusion source. Words mean specific things in this program; use them precisely.

| Term | Meaning | Field(s) | Authority |
|------|---------|----------|-----------|
| **Kill** | Reputation-driven termination; brand damage; terminal | `inbox_state='dead'`, `kill_trigger=<reputation>` | One of 5 reputation triggers fired |
| **Decommission** | Operator-decided cleanup of a chronically disconnected inbox | (no system flag — operator action) | Operator only — system never decommissions |
| **Resurrection / Restore** | Reverse a wrongly-applied dead state on a row that was killed under the now-removed disconnected_timeout rule | Manual SQL: clear kill_trigger, killed_at; restore inbox_state, pool, lifecycle | Operator only — per-row review |
| **Quarantine** | Foreign inbox flagged as not belonging to its workspace; cannot hold any pool tag | `is_quarantined=TRUE` (post-firewall) | Pattern match against client.domain_pattern |
| **Zombie** | Row marked dead in DB while still actively connected and sending in EB | `inbox_state='dead' AND status='Connected'` | Pre-existing condition from old kill rules |
| **Drift** | Mismatch between DB-side state and EB-side state | various | Identified by accuracy audit |
| **Orphan** | DB row whose EB sender is not in this workspace anymore | (no flag — surfaces as `[ORPHAN]` log + audit error) | EB returns 404 on tag operation |

## 8. Sequencing (the "what ships when" diagram)

```
SHIPPED (2026-04-30 + 2026-05-01) — 20 commits across 2 sessions
─────────────────────────────────────────────────────────────────────

SILENT-FAILURE HARDENING (foundation, shipped 2026-04-30)
   ✅ lifecycle_tag_sync workspace-orphan handling (94fd0fa)
   ✅ lifecycle_tag_sync race-check + per-row exception isolation (d775761)
   ✅ disconnected_timeout removed as kill trigger (94fd0fa)
   ✅ kill_processor pool-tag strip retry-on-transient (e7bbd59)
   ✅ set_tag_sync per-row exception isolation (3ef8400)
   ✅ accuracy audit script + Charm zombie CSV
   ✅ apps/incubation-watcher/ extracted, 31 unit tests pass
   ✅ shadow-compare subcommand
   ✅ ADR-009 + plan docs + deploy runbook

PRODUCTION DEPLOYS (2026-04-30 + 2026-05-01)
   ✅ incubation-watcher provisioned (sleep-infinity, operator-invoked)
   ✅ emailbison-sync redeployed multiple times — last with Plan A Phase 5
   ✅ charm-api redeployed for domain is_active semantic
   ✅ Master fast-forwarded to feature branch — branches in sync

PLAN A — CROSS-WORKSPACE INTEGRITY FIREWALL (complete)
   ✅ Phase 0  — keyword seeds confirmed for 11 workspaces
   ✅ Phase 0a — audit found firewall coverage = 0% (problem statement)
   ✅ Phase 0b — 143 unpurchased domains soft-deleted + 4 forward-prevention code changes
   ✅ Phase 0c — data-driven pattern extraction, 0 inbox-level pollution
   ✅ Phase 0d — fleet EB-tenant audit + 22 SPUI-Sammy zombies reattributed
   ✅ Phase 1  — migration 101: is_quarantined columns + partial index
   ✅ Phase 2  — clients.domain_pattern populated for 11 workspaces
   ✅ Phase 3  — backfill closed (no-op since 0 outliers)
   ✅ Phase 4  — migration 103: chk_quarantined_no_pool CHECK (HR-1 structural)
   ✅ Phase 5a — gate at sync_accounts.upsert + 25 unit tests + shadow-verified
   ✅ Phase 5b — lifecycle_tag_sync downstream guards (3 SQL filters)
   ✅ Phase 6  — tests + audit gates passing
   ✅ Phase 7  — deploy + post-deploy verification
   ⏳ Phase 8  — eod-reapply integration (no-op currently; ship when convenient)

PLAN D — KILL-TRIGGER ACCURACY (Passes 1-4 + 3 done; 5 blocked, 6 optional)
   ✅ Pass 1  — kill-triggers.md SMTP table rewrite (full B2B map)
   ✅ Pass 2  — bounce-FBL inference disabled + 69 parser tests
   ✅ Pass 3  — sender-ban code detection (alert-first; 23 tests)
   ✅ Pass 4  — body_full retention for bounces + silent-error fix
   🔒 Pass 5  — out-of-band FBL ingestion (BLOCKED on operator decisions, see D-M)
   ⏳ Pass 6  — apply silent-error pattern to sync_campaigns + sync_engagement (optional follow-up)

CONNECTION STATE MACHINE (Plan B — Phase 1 only)
   ✅ Phase 1 — disconnected_timeout removed (2026-04-30)

DECOMPOSITION (Plan C — Phase 2 only; shadow validation in flight)
   ✅ Phase 2 — apps/incubation-watcher/ extracted
   🚧 Phase 3 — 7-day shadow validation (Day 1 of 7)

INBOX AUDIT OVERHAUL (Phases 1–4 shipped; 5–6 pending)
   ✅ Phase 1  — migration 104: workspace_id + inbox_id_set + audit_data JSONB
   ✅ Phase 2  — InboxAuditor class + idempotent persist (per-workspace)
   ✅ Phase 3  — integrity sections I-1..I-7, I-9 (I-8 deferred — needs EB API)
   ✅ Worker  — daily dispatch wired into emailbison_sync_worker.poll_loop
   ✅ Phase 4  — subscription-cancel rollup with 14-day reuse window
                + live/dead × connected/disconnected breakdown per domain
                + recency_eligible boolean → 57 eligible across 7 workspaces
   ⏳ Phase 5  — Slack restructure (per-workspace channels, action lists)
   ⏳ Phase 6  — SLA enforcement (24h escalate, 7d page) on pending audits


EVENT-DRIVEN ARCHITECTURE (Phases 1–5 shipped; LIVE in production 2026-05-05)
   ✅ Phase 1 — migration 107 (event_log) + migration 108 (7 triggers) + EventListener
                + Gate 1 12 trigger correctness tests
   ✅ Phase 2 — 7 handler implementations (kill_chain.py, lifecycle.py, domain.py,
                workspace.py) + HANDLER_REGISTRY + Gate 2 10 idempotency tests
   ✅ Phase 3 — extracted single-row promote_to_target + listener fix (handlers run
                on fresh pool conn, not LISTEN conn) + DRY refactor
   ✅ Phase 4 — TagOpWorker (Tier 2 batch worker) + bulk EB API methods
                (tag_inboxes_bulk + untag_inboxes_bulk) + 10 tests + poll loop wired
   ✅ Phase 5 — wire EventListener + run_watchdog into emailbison_sync_worker.start()
                gated by EVENT_DRIVEN_ENABLED env (default false)
   ✅ Cutover — merged feature → master (a5a5b3d), deploy charm-api (migrations apply),
                deploy emailbison-sync (flag OFF), drained 559 backlogged emitted rows,
                set EVENT_DRIVEN_ENABLED=true (23:35 UTC), redeploy. 1.5h watch:
                1,800 events / 0 failures. End-to-end verified at 05:48 UTC via
                Charm package_assigned cascade (single UPDATE → 84 tag_op_* drained
                in 1.4s through Tier 2). Master at 3283b40.
   🚧 Gate 5  — 7-day shadow soak with set_tag_sync co-execution (passive, ~2026-05-12)
   ⏳ Gate 6  — drop set_tag_sync runs from poll loop (after Gate 5 clean)
   ⏳ Phase 5+ — sender_ban_detected / graduated / reconnected handlers (deferred,
                designs exist; ship later as needed)
   ❌ disconnect_observed handler — REJECTED per D-N (pool/conn orthogonal; no
                automated DB-side remedy on disconnect)


SESSION 2026-05-06 (operational + audit + cutover)
─────────────────────────────────────────────────────────────────────
   ✅ Charm package_id → 50k_google base (DB UPDATE, 42 reserves promoted live)
   ✅ Pool/conn orthogonality codified (D-N + memory + audit script split)
   ✅ scripts/audit_tags_fleet.py — separate connection-health from tag drift (3888dfd)
   ✅ scripts/shadow_compare_per_workspace.py — added (a5a5b3d)
   ✅ Cutover runbook published + updated 4× through pre-flight discoveries


PENDING — operator-driven (no system code work)
─────────────────────────────────────────────────────────────────────
   👤 Hello Hero package_id (NULL → 50k_google base) — same fix as Charm
   👤 Charm zombie CSV review (142 rows, 127 currently Connected)
   👤 Subscription-cancel candidates (57 eligible across 7 workspaces — see
       inbox_audits.audit_data->'sections'->I-9 for live per-domain rollup)
   👤 20d+ disconnect queue (666 fleet-wide)
   👤 21-inbox Selery batch-disconnect investigation (Ryan/James/Brittany cluster)
   👤 SKMR domain attrition (3 fully-dead domains for cancel; 27 partially-dead)
   👤 Clean 2 cross-tenant SPUI duplicates from EB Spout (eb_ids 8860, 8859)
   👤 Operator decision: enroll in JMRP and/or Postmaster Tools (unblocks Pass 5)
   👤 Hypertide subscription-data sync — IN PROGRESS in a separate chat (will
       address Hypertide root-cause for 2026-02-14 Spout batch + ongoing
       subscription state visibility once landed)


PENDING — system code, shippable next session (ranked, updated 2026-05-13)
─────────────────────────────────────────────────────────────────────
   1. ~~Plan F: warmup-disable-on-kill~~ ✅ SHIPPED 2026-04-13 (709/709 events
      drained: 706 backfill + 3 organic).
   2. ~~Plan E Phase 2: EOD reapply L5 ATTACH staging~~ ✅ SHIPPED 2026-05-13
      against Charm Test-Campaign 271. Two latent bugs found+fixed mid-staging
      (filter-shape silent-ignore; async-delete false-negative). See
      apps/eod-reapply/docs/staging-results.md.
   3. ~~Plan E PR 1: v2 daemon scaffold (dry-run-only)~~ ✅ SHIPPED 2026-05-13.
      Migration 111 + workspaces.eod_reapply_enabled flag + daemon module + CLI
      subcommand + 18 new tests. apply=False hard-locked. Deploy via Coolify
      Pattern C; flip Charm's flag to validate dry-run output.
   4. Plan E PR 2: apply-mode + crash recovery + alerting. ~half day.
   5. Plan E PR 3: validation audit (killed-inbox-no-sends-post-EOD). ~half day.
   6. Plan E REMOVE-path validation (needs fresh active test campaign — operator
      action).
   7. Kill-rule Phase 5 cleanup — drop legacy `_24h`/`_7d` columns + obsolete
      code paths + `@_OBSOLETE_COUNT_RULE` tests (release cycle elapsed)
   8. Inbox-audit Phase 5 (Slack restructure) — rebuild daily Slack post around
      the I-* sections + the new operator-queue UI (commit 35e538c)
   9. Inbox-audit Phase 6 — SLA enforcement (24h escalate, 7d page)
  10. Plan D Pass 6 — sync_campaigns + sync_engagement silent-error pattern
  11. Decomposition Phase 4a — incubation-watcher v2 daemon mode
  12. Decomposition Phase 4 — watcher cutover (independent timeline; runs to its
      own clock per pool/conn lessons)
  13. Plan D Pass 3 alert→kill flip (gated on 7 days of clean alert data)
  14. Engagement decay detection — proxy reputation signal

   ❌ Removed: "disconnect report section" — already shipped as
      `/reports/disconnects` page in the 7-page operator queue UI
      (commit 35e538c). Plan B Phase 2 now ✅ in §3.4.


NEXT SPRINT (after current pending queue drains)
─────────────────────────────────────────────────────────────────────
   ⏳ ADR-008 step 2 — collapse pool + lifecycle into single inbox_status
   ⏳ Decide on extracting kill-watcher, inventory-manager, tag-writer
       (30 days post-incubation-watcher cutover)
```

---

## 9. How to use this document

| If you want to know... | Start here |
|------------------------|------------|
| What was decided and why | §4 Decision log + linked ADRs |
| What's open and needs my input | §5 Open decisions |
| What's currently in progress | §3 Status board, look for 🚧 |
| What's blocked on me as operator | §3.6 + §5, look for 👤 |
| The big picture of why all this | §1 Program scope |
| Specific plan details | §2 links to deep-dive docs |
| What got committed today | §3.1 + §3.2 |
| What might break | §6 Risks |
| What does this term mean | §7 Vocabulary |
| When does X happen | §8 Sequencing |

## 10. Update protocol

End of each working session, the assistant updates:

1. **§3 Status board** — flip statuses on completed workstreams, add new ones discovered
2. **§4 Decision log** — append any newly-locked decisions
3. **§5 Open decisions** — remove answered ones, add new ones surfaced
4. **§3.1 / §3.2** — link any new commits or documents
5. **§8 Sequencing** — refresh based on what shipped vs deferred

Updated date in frontmatter. Brief commit message: `docs(integrity-program): <session summary>`.

The work-log doc (`docs/work-logs/<date>-...md`) captures session-level detail; this tracker captures program-level state. They cross-reference.
