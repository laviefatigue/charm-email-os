---
title: Inbox Integrity Program — Master Tracker
created: 2026-04-30
updated: 2026-05-01 (firewall Phase 0+2 + kill-trigger Pass 1+2+4 + silent-error fix shipped)
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

Each plan is a deep-dive document. This index is the cross-reference.

| Plan | Lines | Status | Phase shipped today | Phases remaining |
|------|------:|--------|---------------------|------------------|
| [cross-workspace-integrity-firewall.md](cross-workspace-integrity-firewall.md) | ~600 | PROPOSED | none — pending operator confirm of keyword seed | All 7 phases pending |
| [connection-state-machine.md](connection-state-machine.md) | ~400 | PARTIAL | Phase 1 (disconnected_timeout removed) | Phases 2-6 pending accuracy validation |
| [emailbison-sync-decomposition.md](emailbison-sync-decomposition.md) | ~600 | PROPOSED | none | Phases 1-4 pending |
| [kill-trigger-accuracy.md](kill-trigger-accuracy.md) | ~500 | PROPOSED — Pass 1 ready | none — drafted 2026-05-01 evening | All 5 phases pending; Pass 1 (docs) shippable today |

Plus the foundational records:

| Document | Type | Status |
|----------|------|--------|
| [docs/adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md](../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md) | ADR | accepted |
| [docs/work-logs/2026-04-30-systems-accuracy-and-cleanup.md](../work-logs/2026-04-30-systems-accuracy-and-cleanup.md) | Work log | active |
| [docs/audits/2026-04-30-system-accuracy-snapshot.json](../audits/2026-04-30-system-accuracy-snapshot.json) | Audit data | snapshot — re-run periodically |
| [docs/audits/2026-04-30-zombie-review-charm.csv](../audits/2026-04-30-zombie-review-charm.csv) | Operator queue | awaiting operator |

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
| [docs/plans/inbox-audit-overhaul.md](inbox-audit-overhaul.md) | ✅ requirements catalog (deferred) | `765cd3d` |
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
| 1 | **Migration 101: schema (is_quarantined columns, no CHECK yet)** | ✅ | — | Shipped 2026-05-01 evening. Adds `is_quarantined BOOLEAN NOT NULL DEFAULT FALSE`, `quarantine_reason VARCHAR`, `quarantine_detected_at TIMESTAMPTZ` + partial index on `is_quarantined=TRUE`. Verified: 0/4786 active rows quarantined (default value). CHECK constraint `chk_quarantined_no_pool` deferred to Phase 4 / migration 103. |
| 4 | **Migration 103: chk_quarantined_no_pool CHECK constraint (HR-1 structural)** | ✅ | — | Shipped 2026-05-01 evening. Pre-check verified 0 violating rows. Constraint refuses any write where `is_quarantined=TRUE AND inventory_pool_status IS NOT NULL`. Real violation attempt against production confirmed enforcement: write rejected with `violates check constraint "chk_quarantined_no_pool"`, no row state changed. Procedural CASE branch in sync_accounts.upsert (Phase 5a) becomes belt-and-suspenders; this constraint is now load-bearing. |
| 2 | **Populate clients.domain_pattern with seed** | ✅ | — | Shipped 2026-05-01 evening. All 11 workspaces have correct domain_pattern. Verified: 0 outliers across 4,207 active inboxes when running the firewall SQL predicate against live data. |
| 3 | Backfill: quarantine existing pollution + null pool tags | ⏳ | accuracy gates passing | EB-side companion strip script needs operator approval per workspace |
| 4 | Migration 103: add CHECK constraint | ⏳ | Phase 3 done | Cannot ship before backfill nulls existing pollution |
| 5 | Code changes: gate at sync_accounts.upsert + filters in pool/lifecycle/set_tag/health | ⏳ | Phase 4 done | |
| 6 | Tests + audit gate verification | ⏳ | Phase 5 done | |
| 7 | Deploy + post-deploy verification | ⏳ | Phase 6 done | |
| 8 | eod-reapply integration (refuse target if quarantined inbox in workspace) | ⏳ | Phase 7 done | |

### 3.4 Connection state machine (Plan B)

| # | Phase | Status | Blocker | Notes |
|:-:|-------|:------:|---------|-------|
| 1 | Remove `disconnected_timeout` from KILL_THRESHOLDS | ✅ | — | Shipped commit `94fd0fa` |
| 2 | Notification ladder (24h/3d/7d/20d Slack alerts) | ⏳ | accuracy gate: disconnect timestamps validated | Could ship as read-only signal first |
| 3 | EB connection tags (`disconnected_24h`, etc) auto-applied | ⏳ | accuracy gate: status mirror validated | Defer until accuracy proven |
| 4 | Drop `status='Connected'` filter from pool_promotion | ⏳ | accuracy gates passing | |
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
| 5 | Out-of-band FBL ingestion (`apps/fbl-consumer/` — Microsoft JMRP + Gmail Postmaster Tools) | ⏳ | 30 days clean post-Phase 2 | Separate project. Real spam complaint detection. ARF email parsing + Postmaster Tools API. |
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

### 3.6 Operator-driven actions (require human review/decision)

| Workstream | Status | Notes |
|------------|:------:|-------|
| ~~Deploy commits to charm-api + emailbison-sync~~ | ✅ | **emailbison-sync DEPLOYED 2026-04-30 23:12 UTC** (deployment uuid `fo8cwg00k40gk0o0cwog0s00`). 6/6 verification checks PASS, walk-away monitor scheduled. charm-api skipped per quickref §5 (no relevant changes). See deploy-outcome work log. |
| Charm zombie CSV review (142 rows, 127 currently Connected) | 👤 | [docs/audits/2026-04-30-zombie-review-charm.csv](../audits/2026-04-30-zombie-review-charm.csv) — fill `operator_decision` column, run SQL by hand |
| Re-run accuracy audit weekly | 👤 | `py scripts/audit_system_accuracy.py` |
| ~~Investigate Spout's 641 disconnected_timeout zombies~~ — RECLASSIFIED 2026-04-30 end of session: Spout has 0 disconnected_timeout zombies. The 641 dead+Connected are CORRECTLY reputation-killed (183 spam, 162 hard_bounces, 267 fresh-inbox failures). 553 of 641 came from a single 2026-02-14 mass provisioning event (550 inboxes killed across 10 *spoutwater.com domains). New investigation: **Hypertide root-cause for the 2026-02-14 batch failure.** | 👤 | See work-log §"Workstream D investigation — Spout 641 reclassified" |
| Cleanup the 10 Spout pool-tag drift rows (operator EB-side untag) | 👤 | Patch shipped to prevent recurrence; existing 10 need manual tag strip via EB UI or scripted untag with operator approval |
| Strip flagged_disconnected_timeout from EB during zombie restoration | 👤 | Per-row, alongside operator restoration in §3.4 Phase 5 |

### 3.7 Future / next-sprint

| Item | Owner | Blocker |
|------|-------|---------|
| ADR-008 step 2 — collapse inventory_lifecycle_status + inventory_pool_status into single inbox_status | system | Firewall (Plan A) shipped first |
| Workspace package assignments | operator | Decide which packages each workspace gets (SKMR likely 50k_google) |
| v3-vs-ours kill-trigger comparison on a sending workspace | system | Pick a sending workspace (Hello Hero / Spout / Selery / Search Atlas) |
| inbox_audits overhaul ([requirements catalog](inbox-audit-overhaul.md)) | deferred | User confirmed: deferred — focus on state machine first. Captured requirements: per-workspace audit, snapshot inbox sets, integrity sections (I-1..I-9), **subscription-cancel signal for domains where all inboxes are dead** (added 2026-04-30), SLA on corrections workflow. |

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
| D-G | Observation before automation — accuracy gates must pass before automated actions on system data | this session's revision | The system was demonstrably wrong for months; trust must be earned |
| D-H | Decomposition scope: extract incubation-watcher only first, decide on rest after 30-day validation | decomposition plan §2.1 | Avoid premature 6-service commitment |
| D-I | NULL pattern in clients.domain_pattern → quarantine all inboxes (fail-closed) | firewall plan §10 D-2 | New clients must be configured before any inbox can pool |
| D-J | Restoration is operator-driven, manual SQL per row, smallest-workspace-first | connection plan §8 | The system that produced the bug cannot be trusted to auto-fix the bug |

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
TODAY (2026-04-30) — shipped + deployed
─────────────────────────────────────────────────────────────────────
   ✅ lifecycle_tag_sync workspace-orphan handling
   ✅ lifecycle_tag_sync race-check + per-row exception isolation
   ✅ disconnected_timeout removed as kill trigger
   ✅ kill_processor pool-tag strip retry-on-transient
   ✅ set_tag_sync per-row exception isolation
   ✅ accuracy audit script + Charm zombie CSV
   ✅ apps/incubation-watcher/ extracted, 31 unit tests pass
   ✅ shadow-compare subcommand for May 1 parity validation
   ✅ Methodic deploy runbook + quickref + baseline JSON
   ✅ ADR-009 + plan docs + work logs + production docs

   ✅ DEPLOYED 2026-04-30 evening
       - incubation-watcher provisioned (Coolify uuid pssgc0c8w4sooos8gs0scsos)
         alive in sleep-infinity mode (operator-invoked, no daemon yet)
       - emailbison-sync redeployed at 23:12 UTC (deployment fo8cwg00k40gk0o0cwog0s00)
         6/6 verification checks PASS, walk-away monitor scheduled

   ⚠ DISCOVERED 2026-04-30 evening (audit Q2)
       - clients.domain_pattern coverage = 0% in production
         (NULL for 9 workspaces, "" for Charm + Selery)
       - Mitigated today by manual eyeball — all 193 incubating inboxes
         match expected workspace pattern by inspection
       - Firewall plan Phase 0a updated to reflect this gap

TOMORROW MORNING (May 1)
─────────────────────────
   ⏳ ~02:50 UTC: pre-cycle candidate snapshot (incubation-watcher check)
   ⏳ ~03:30 UTC: shadow-compare run, output saved
   ⏳ Afternoon: pre-cycle list compared to actual_only set, parity verified
   ⏳ Re-run 6 verification checks at start of day

THIS WEEK (operator-driven)
─────────────────────────────
   👤 Operator review Charm zombie CSV (142 rows)
   ✅ Firewall keyword seed confirmed + clients.domain_pattern populated (2026-05-01)
   ✅ Generated-domain cleanup (143 unpurchased rows soft-deleted, 4 forward-prevention code changes)
   👤 Generate Spout zombie CSV + investigate root cause
   🚧 Re-run accuracy audit, verify SPUI gap closed (sync timing)
   ✅ Kill-trigger accuracy Pass 1 — kill-triggers.md SMTP table rewrite (commit a206da3)
   ✅ Kill-trigger accuracy Pass 2 — bounce-FBL inference disabled + 69 parser tests (commit 8dd3011)
   ✅ Kill-trigger accuracy Pass 4 — body_full kept for bounces + silent-error fix (commit 995cd74)
   ⏳ Kill-trigger accuracy Pass 3 — sender-ban code detection (5.7.501-511 family)
   ⏳ Kill-trigger accuracy Pass 6 — apply silent-error pattern to sync_campaigns + sync_engagement
   ✅ Firewall Phase 1 — migration 101 shipped (is_quarantined columns + partial index)
   ✅ Firewall Phase 5a — gate at sync_accounts.upsert (commit f43b7b4)
   ✅ Firewall Phase 5b — lifecycle_tag_sync downstream guards (commit c9a437c)
   ✅ Firewall Phase 4 — migration 103 chk_quarantined_no_pool CHECK constraint (HR-1 structural)
   ✅ Firewall Phase 0d — fleet EB audit + Sammy zombie cleanup (22 reattributed)
   ⏳ Firewall Phase 3 — backfill quarantine state on existing rows (currently no-op since 0 outliers)

NEXT WEEK (gated on this-week's outcomes)
───────────────────────────────────────────
   ⏳ Firewall Phase 1-3: schema + populate + backfill (per workspace)
   ⏳ Connection plan Phase 2: notification ladder (24h/3d/7d/20d)
   ⏳ Begin apps/incubation-watcher/ extraction (decomposition)

NEXT SPRINT (gated on firewall + decomposition validation)
─────────────────────────────────────────────────────────────
   ⏳ ADR-008 step 2: collapse pool + lifecycle into inbox_status
   ⏳ Decide on extracting kill-watcher, inventory-manager, tag-writer
   ⏳ Workspace package assignments
   ⏳ inbox_audits overhaul (deferred this sprint)
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
