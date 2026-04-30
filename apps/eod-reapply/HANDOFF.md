---
title: EOD Reapply v1 — Handoff & Status
date: 2026-04-29
audience: any future chat / engineer continuing this work
status: v1 code complete + tested; production audit done; pending deployment + bug-investigation work
---

# EOD Reapply — Handoff Document

This is a self-contained handoff. Read top to bottom and you'll have the full picture.

---

## 0. TL;DR

We built a one-shot CLI (`apps/eod-reapply/`) that reapplies a campaign's `live`-tagged sender set as its EmailBison sender attachment. It's intended to close a gap where dead inboxes lose the `live` tag in EB but stay attached to active campaigns until something detaches them.

**v1 code is feature-complete and rigorously tested:**
- 222 passing tests in strict mode (ruff + mypy --strict + pytest with `filterwarnings=error`)
- Two read subcommands (`check`, `reapply`)
- Multi-stage Dockerfile, GitHub Actions CI, Coolify deployment template
- All on branch `plan/eod-campaign-reapply` at HEAD `ddfe5db` (pushed to `hirecharm` remote)

**During L5 staging probes against real EB, we found two production-significant issues:**

1. **A pagination bug in our own code** (already fixed and tested) — `get_campaign_senders` was only fetching page 1, would have left 619 of 634 senders untouched on Sammy #63 if `--apply` had run.

2. **Cross-workspace inbox pollution (data integrity issue, NOT in our code)** — 82 inboxes across the fleet are registered in the wrong EB workspace. Most critical: 22 SPUI mailboxes are registered in Sammy's EB workspace and currently tagged `live`. Running EOD reapply against an active Sammy campaign would attach SPUI's mailboxes to Sammy campaigns → cross-tenant data leak.

**The eod-reapply tool itself is safe and correct. The pollution is upstream — likely Hypertide provisioning is using the wrong workspace_id at inbox-creation time.** The tool would only TRIGGER the existing data integrity issue if run against affected workspaces.

**Hard rules right now:**
- Do NOT run `eod-reapply --apply` against Sammy or Stable Kernel Market Research until pollution is reconciled.
- The tool is ready to use against the 8 clean workspaces (Barrena, Charm, Hello Hero, Linkgraph, SPUI, Search Atlas, Selery, Stable Kernel).
- Spout has 2 minor mismatches (dead, low risk) but is otherwise fine.

---

## 1. What the tool does

### Problem it solves

When `kill_processor` (in `sync_modules/kill_processor.py`) detects an inbox is dead:
- It updates `sender_accounts.inbox_state = 'dead'` in our DB ✓
- It strips the `live` / `reserve` tags in EB ✓
- **But it does NOT detach the inbox from any active EmailBison campaigns it was already part of.**

So over time, active campaigns accumulate dead senders. Sammy campaign #63 had 634 attached senders, ALL `Not connected`, before we ran the audit.

### What `eod-reapply` does

For a single (workspace, campaign) pair:
1. Pull the campaign's status (refuses unless Active/Queued/Sending).
2. Pull the campaign's schedule. Refuse to mutate unless `now > end_time + buffer` in the campaign's IANA timezone, on a sending day, and not already run for today's local date. (Bypassable with `--skip-time-check`.)
3. Pull the senders that have the `live` tag in this workspace = `target_set`.
4. Pull the campaign's currently-attached senders (paginated) = `prior_set`.
5. Diff. If empty → no-op success.
6. With `--apply`: pause campaign → attach added → remove dropped → fetch & verify set equality → resume campaign. The resume is in a `try/finally` block.

### Two subcommands

```bash
eod-reapply check    # read-only pre-flight (DB + EB auth + campaign + tag + expected diff)
eod-reapply reapply  # the actual reapply (default dry-run; --apply mutates)
```

### Exit codes (load-bearing for any scheduler)

```
check:
  0 = all checks passed
  1 = at least one warning (degraded)
  2 = at least one failure (operator must fix before reapply)

reapply:
  0 = success / clean no-op
  1 = dry-run completed and would have made changes
  2 = failure but campaign is in original (non-paused) state
  3 = CRITICAL — campaign may be left paused. Operator must verify.
```

---

## 2. Branch, commits, code locations

### Git state

- **Branch**: `plan/eod-campaign-reapply` on `hirecharm` remote (org repo: `HireCharm/charm-email-os`)
- **HEAD**: `ddfe5db` (audit commit) — see `git log --oneline plan/eod-campaign-reapply` for full series
- **Diverged from `hirecharm/master`** by 8 commits, all related to this work
- PR-ready URL: `https://github.com/HireCharm/charm-email-os/pull/new/plan/eod-campaign-reapply`

### Commit series (newest first)

```
ddfe5db audit(cross-workspace): fleet-wide inbox-pollution scan, 82 mismatches found
2165435 fix(eod-reapply): close remaining silent-truncation paths in pagination
cd2da67 fix(eod-reapply): get_campaign_senders pagination — found via L5 probe
9640ed2 ci(eod-reapply): GitHub Actions workflow + Coolify services.md entry
b4e54c4 feat(eod-reapply): add `check` subcommand + Dockerfile for staging deployment
f289084 test(eod-reapply): mypy + ruff + Hypothesis + asyncio cancellation tests
dd581c5 test(eod-reapply): no-silent-errors hardening — strict mode, 99% coverage
0d34ab8 docs(eod-reapply): tracking patterns — JSONL log + queries on existing schema
be820bf feat(eod-reapply): v1 one-shot CLI — pause→diff→reapply→verify→resume
d22e212 docs(plans): scope EOD campaign reapply service
```

### File layout

```
apps/eod-reapply/
├── pyproject.toml                        Project deps + ruff + mypy + pytest config
├── README.md                             Operator-facing docs
├── HANDOFF.md                            ← this file
├── STAGING-RUNBOOK.md                    L5 staging gate (11 sections + 2 appendices)
├── Dockerfile                            Multi-stage Python 3.13-slim
├── .dockerignore
├── .gitignore                            Excludes .coverage, __pycache__, etc.
├── docs/
│   └── eb-api-deep-dive.md               EB API reference distilled from live OpenAPI
├── src/eod_reapply/
│   ├── __init__.py
│   ├── window.py                         Pure tz-aware EOD predicate (CampaignSchedule, evaluate_window)
│   ├── eb_client.py                      Workspace-scoped EB API subset (8 endpoints, paginated)
│   ├── reapply.py                        Orchestrator (pause→diff→attach→remove→verify→resume)
│   ├── check.py                          Read-only pre-flight diagnostic
│   ├── db.py                             workspace_api_keys + workspaces lookup
│   └── cli.py                            click entrypoint (subcommands: check, reapply)
└── tests/
    ├── test_window.py                    43 cases — TZ matrix, DST, Sammy/Sydney
    ├── test_window_properties.py         7 Hypothesis property tests (~700 generated cases)
    ├── test_eb_client.py                 49 cases — mocked httpx, errors, pagination + silent-truncation guards
    ├── test_reapply.py                   55 cases — orchestrator + invariant sweep + Sammy regression
    ├── test_reapply_cancellation.py      1 case — real asyncio.Task.cancel mid-attach
    ├── test_cli.py                       27 cases — exit codes, arg parsing
    ├── test_cli_e2e.py                   5 cases — full async pipeline against respx + mocked asyncpg
    ├── test_check.py                     24 cases — pre-flight checks + render + CLI integration
    └── test_db.py                        5 cases — fetch_workspace_context

.github/workflows/
└── eod-reapply.yml                       Path-filtered CI: ruff + mypy --strict + pytest + docker build smoke

production/coolify/services.md            (entry added documenting deployment patterns)
docs/plans/eod-campaign-reapply.md        Full v2 scoping doc (scheduler design)
docs/audits/2026-04-29-cross-workspace-pollution-audit.md  Production audit (the cross-workspace findings)
```

---

## 3. Test status

```
222 passing in strict mode (ruff + mypy --strict + pytest --strict-markers --strict-config)
~30 seconds wall-clock
99% coverage (only line not covered: `if __name__ == "__main__": main()`)

How to run from app dir:
  cd apps/eod-reapply
  py -m pytest                                                # 222 tests
  py -m pytest --cov=src/eod_reapply --cov-report=term        # with coverage
  py -m ruff check src tests                                  # lint
  py -m mypy --strict src/eod_reapply                         # types
```

### What the tests cover (in layers)

- **L1 (window.py)** — pure function, TZ math. Sammy/Sydney AEDT+AEST + DST + IDL-adjacent + idempotency + Hypothesis properties.
- **L2 (eb_client.py)** — mocked httpx via respx. 8 endpoints, full error matrix, pagination contract, **silent-truncation guards** (the load-bearing Sammy regression test).
- **L3 (reapply.py)** — orchestrator with failure injection at every step. Invariant sweep proves: pause→resume always paired, dry-run never mutates, verify-set-equality required for SUCCEEDED, attach-before-remove fail-closed ordering. Plus a real `asyncio.Task.cancel` test to prove the `try/finally` resume actually fires under cancellation.
- **L4 (cli.py)** — exit code mapping, arg parsing, output rendering, end-to-end async pipeline against respx + mocked asyncpg.
- **L5 (real EB / DB)** — operator-driven; partially completed via read-only probes (see §6).

---

## 4. Deployment shape

### Three deployment patterns documented

**Local (dev / one-off)**:
```bash
cd apps/eod-reapply
pip install -e ".[dev]"
export DATABASE_URL='postgresql://...'
export EMAILBISON_API_URL='https://spellcast.hirecharm.com/api'
eod-reapply check --workspace Charm
```

**Docker (one-shot from any host)**:
```bash
cd apps/eod-reapply
docker build -t eod-reapply:latest .
docker run --rm \
  -e DATABASE_URL='...' \
  -e EMAILBISON_API_URL='...' \
  eod-reapply:latest check --workspace Charm --campaign-id 123
```

**Coolify (recommended for production)**:
- Service type: Dockerfile (build context = `apps/eod-reapply/`)
- Override CMD to `sleep infinity` so container stays up
- Env vars from Coolify secrets: `DATABASE_URL`, `EMAILBISON_API_URL`
- Operator runs via `coolify exec <service> eod-reapply check --workspace Sammy`
- See `production/coolify/services.md` for the full entry

### Not yet deployed to Coolify

The Dockerfile is ready but no service has been provisioned in Coolify yet. To deploy:
1. Create a new Coolify app pointing at this repo + `apps/eod-reapply/Dockerfile`.
2. Set env vars (DATABASE_URL, EMAILBISON_API_URL) — see existing `emailbison-sync` service for the same values.
3. Override CMD to `sleep infinity` (Coolify UI under Application Settings).
4. Deploy. Verify via `coolify status`.
5. Run `eod-reapply check --workspace Charm` via container exec.

---

## 5. Production access (where to find credentials, NOT the values themselves)

The chat picking this up will need access to a few production resources. **Do not commit credentials.**

### Coolify CLI

`scripts/coolify.py` — Python CLI wrapper for the Coolify API. Has hardcoded API token at the top of the file. Commands: `list-apps`, `status`, `env-list`, `env-set`, `deploy`, `restart`, `logs`. Used during this audit to read production env vars.

```bash
py scripts/coolify.py list-apps                       # smoke test
py scripts/coolify.py env-list emailbison-sync         # pull DATABASE_URL, etc
```

### Admin SQL endpoint

`scripts/db_vs_eb_comparison.py` — has hardcoded admin key + URL at top. Used to run arbitrary SELECT against production DB:

```python
ADMIN_API = "https://api.wizardgrimoire.cloud/api/admin/run-sql"
ADMIN_KEY = "..."  # in the script
# POST with key + sql query params, set User-Agent: curl/8.0.0 to bypass WAF
```

### Workspace API keys

`ws_keys.json` (untracked, at repo root) contains workspace-scoped Sanctum tokens for each EB workspace. Same data is in the `workspace_api_keys` table (column `key_token`, joined to `workspaces` by `workspace_id`).

If this file isn't present, regenerate by querying:
```sql
SELECT w.workspace_name, w.emailbison_workspace_id, k.key_token
FROM workspaces w
JOIN workspace_api_keys k ON k.workspace_id = w.id AND k.is_active = TRUE
WHERE w.is_active = TRUE
```

### Cleanup needed at repo root

The L5 audit produced several JSON dumps with real production data:
```
ws_keys.json, sammy63_prior.json, sammy_live_p1.json, sammy_live_p2.json,
sammy63_all.json, sammy_live_full.json, sammy63_db_audit.json,
audit_mismatches.json, audit_per_ws_summary.json, audit_per_ws_full.json,
audit_all_foreign.json
```

None are gitignored. **Do not `git add .`** until these are removed by an operator (claude can't `rm` due to permission policy).

---

## 6. Production audit findings (the critical context)

### How we got here

After v1 was complete and pushed, we ran read-only L5 probes against production EB. **Two findings:**

### Finding 1: Pagination bug (FIXED)

`EBClient.get_campaign_senders()` was making a single GET and only returning page 1. Sammy #63 actually has 634 attached senders across 43 paginated pages — we were seeing 15.

**Fixed in commit `cd2da67`** (and `2165435` extended to other paginated methods). Both `get_campaign_senders` and `list_senders_with_tag` now:
1. Paginate until `last_page` reached.
2. Track `meta.total` from page 1 and assert `len(collected) == total` at the end. Mid-fetch shape changes (data missing, last_page lost mid-stream, 204 mid-pagination, bare list on page > 1) all raise loud rather than silently truncate.

### Finding 2: Cross-workspace inbox pollution (NOT FIXED — outside the tool's scope)

Per-workspace EB scan with each workspace's own scoped API key revealed **82 senders are registered in the wrong EB workspace**. Their domain (per our `domains` table) belongs to a different client.

**Detail in `docs/audits/2026-04-29-cross-workspace-pollution-audit.md`** (commit `ddfe5db`).

#### Summary

| Workspace | EB total | foreign | foreign+live | Status |
|---|---:|---:|---:|---|
| Barrena, Charm, Hello Hero, Linkgraph, SPUI, Search Atlas, Selery, Stable Kernel | (8 workspaces) | 0 | 0 | ✓ clean |
| **Sammy** | 691 | **52** | **22** 🚨 | immediate risk |
| **Stable Kernel Market Research** | 100 | 28 | 0 | latent risk |
| Spout | 548 | 2 | 0 | minor |

#### The 22 immediate-risk inboxes

```
Sammy workspace currently has 22 SPUI mailboxes (`*@growspui.com`) registered as Sammy senders, all tagged `live`.
EB sender ids 9206-9227 (consecutive — batch creation).
Created in DB on 2026-03-31 (single day, single batch).
```

If reapply runs against any active Sammy campaign, these 22 SPUI mailboxes get attached to Sammy. SPUI's actual Google mailboxes physically send Sammy's outbound. **Cross-tenant data leak.**

The tool's existing `max_removal_pct=50` guard happens to block this for Sammy #63 (100% removal trips it), but only by accident — different campaign shapes wouldn't trip the guard.

#### Why workspace API keys are NOT the bug

EB Sanctum tokens are correctly scoped — each only returns what's in its team. The bug is **upstream** at inbox-creation:

```
Provisioning code → POST /api/sender-emails with workspace context X
But OAuth target = workspace Y's mailbox
EB has no domain-to-workspace ownership concept → registration succeeds in X
Pollution. Now any operation through X's key sees this inbox.
```

#### Pollution events are batched (smoking gun for hypertide)

Each event is a single-day batch with consecutive EB sender ids:
- 2026-03-11: 7 (Linkgraph ← Search Atlas, since cleaned in EB)
- 2026-03-31: 22 (Sammy ← SPUI, the active risk)
- 2026-04-14: 50+ (multiple pairs)

Random pollution would be temporally spread. These are batches → automated provisioning is creating EB sender records with the wrong workspace_id. **Hypertide is the prime suspect** but we couldn't directly link the rows to `inbox_purchase_jobs` (the JOIN returned 0 matches — possibly different table or code path).

---

## 7. Open work items, prioritized

### P0 — Block immediate risk (operator action)

- [ ] **Reconcile the 22 Sammy-side SPUI mismatches.** Either:
  - Remove the 22 inboxes from Sammy's EB workspace via EB UI (they're SPUI's; shouldn't be in Sammy), OR
  - Strip the `live` tag from them so they fall out of the reapply target_set.
- [ ] **Investigate the SKMR ← Sammy 28 mismatches** to determine whether the domain ownership is wrong (fix `domains.workspace_id`) or the senders are misregistered (fix `sender_accounts` + EB).

### P1 — Code-level guards (Claude can do these)

- [ ] **Add cross-workspace tenant guard to `eod-reapply`.** ~30 min.
  - New `ReapplyStatus.SKIPPED_CROSS_WORKSPACE_TENANT`, exit code 2.
  - In `reapply.py`: after computing target_set, look up each sender's domain owner in DB. If any disagree with the campaign's workspace, refuse to proceed.
  - In `check.py`: add as a check that fails loud (FAIL status) when foreign senders are in target_set.
  - Tests: regression on the Sammy/SPUI shape — 22 senders all from a different workspace, must trip the guard.
  - This makes the tool incapable of triggering a cross-tenant leak even with current pollution.

- [ ] **Postgres trigger** to enforce `sender_accounts.workspace_id = domains.workspace_id` at INSERT/UPDATE. ~15 min DDL. Full SQL is in the audit doc (rec #5). Stops the bleeding for new pollution.

### P2 — Process / monitoring

- [ ] **Productionize the cross-workspace audit as a daily Slack-alerting cron.** ~2 hours. Pattern is the same SQL + per-workspace EB scan as today's audit. Output to `audit_logs` or Slack channel. New script: `scripts/audit_cross_workspace_pollution.py`.

- [ ] **Deploy `eod-reapply` to Coolify** (Pattern A — sleeping container). See §4. ~30 min.

### P3 — Hypertide investigation (operator/dev with provisioning context)

- [ ] **Find the code path** that created EB sender records on 2026-03-31 (22 SPUI inboxes into Sammy) and 2026-04-14 (50+ inboxes). Likely files: `Hypertide/automation/src/hypertide_automation/emailbison.py` and any provisioning scripts that POST to `/api/sender-emails`. Look for: workspace_id parameter passing wrong, default falling back to Sammy, admin key being used with wrong context.

### P4 — Real `--apply` staging run (operator-driven)

- [ ] After P0 + P1 done, do the real L5 staging gate: pick a Charm test campaign (Charm has zero current Active campaigns — would need to create one), use the A/B/C/D/E sender setup recipe in `STAGING-RUNBOOK.md` Appendix A, walk through sections 4–9. This closes the 5 remaining open questions in `docs/eb-api-deep-dive.md` §8 (eventual consistency on attach/remove, idempotent attach/remove behavior, pause synchronicity, `skip_webhooks` support).

### P5 — v2 (scheduler) — out of scope until v1 is in production

- See `docs/plans/eod-campaign-reapply.md` for the full v2 scope. New tables (`campaign_schedules`, `campaign_reapply_runs`), poll loop, idempotency keying, Coolify continuous worker.

---

## 8. Hard rules — what NOT to do

1. **DO NOT run `eod-reapply --apply` against Sammy or Stable Kernel Market Research.** They have foreign-domain inboxes that would cause cross-tenant data leaks.

2. **DO NOT `git add .`** at the repo root until production data dumps are deleted. See §5 for the file list.

3. **DO NOT push directly to `master`.** All work is on `plan/eod-campaign-reapply`. Open a PR when ready.

4. **DO NOT skip the staging runbook** before any production `--apply` run. The 5 remaining open EB API questions (§7 P4) need real-mutation observations.

5. **DO NOT modify `kill_processor.py` or `lifecycle_tag_sync.py`** as part of the EOD reapply scope. Those are owned by the existing sync engine. The tool's job is to reconcile EB campaign attachments — nothing else.

---

## 9. Quick reference for the new chat

### How to verify the tool still works

```bash
cd apps/eod-reapply
py -m pytest                                                  # expect 222/222 pass
py -m ruff check src tests                                    # expect clean
py -m mypy --strict src/eod_reapply                           # expect clean
PYTHONPATH=src py -m eod_reapply.cli check --help             # expect help text
PYTHONPATH=src py -m eod_reapply.cli reapply --help           # expect help text
```

### How to query production state

```bash
# Coolify
py scripts/coolify.py list-apps
py scripts/coolify.py env-list emailbison-sync

# Direct EB (need ws_keys.json with workspace tokens)
SAMMY_KEY=$(py -c "import json; print([w['key_token'] for w in json.load(open('ws_keys.json'))['result'] if w['workspace_name']=='Sammy'][0])")
curl -sS -H "Authorization: Bearer $SAMMY_KEY" "https://spellcast.hirecharm.com/api/tags" | py -m json.tool

# Admin SQL (need scripts/db_vs_eb_comparison.py for the key)
# IMPORTANT: set User-Agent: curl/8.0.0 to bypass Cloudflare WAF
curl -sS -X POST "https://api.wizardgrimoire.cloud/api/admin/run-sql?key=...&sql=SELECT+1" -H "User-Agent: curl/8.0.0"
```

### How to re-run the cross-workspace audit

The audit script is conceptually:

```python
# 1. domain_owner = SELECT domain_name, workspace_name FROM domains JOIN workspaces (the source of truth)
# 2. For each active workspace W with an API key:
#      For each sender s in EB workspace W:
#        domain = s.email.split('@')[1]
#        if domain_owner.get(domain) != W.name:
#          FOREIGN
# 3. Cross-reference EB live tag set per workspace to identify immediate vs latent risk
```

See the audit doc for full pseudocode + the SQL schema reads needed.

### Reference docs in the repo

- `apps/eod-reapply/README.md` — operator-facing usage
- `apps/eod-reapply/STAGING-RUNBOOK.md` — L5 gate before any real production `--apply`
- `apps/eod-reapply/docs/eb-api-deep-dive.md` — EB API reference (curl recipes, response shapes, open questions)
- `docs/plans/eod-campaign-reapply.md` — full scoping doc (v1 + v2)
- `docs/audits/2026-04-29-cross-workspace-pollution-audit.md` — the production audit findings (most important context for the new chat)
- `production/coolify/services.md` — service registry with eod-reapply entry

### Project-level conventions

- Workspace API keys are stored in `workspace_api_keys.key_token` (plaintext, joined via `workspace_id`). Each is workspace-scoped (Sanctum bound to a team_id at creation).
- Domain ownership is in `domains.workspace_id`. This is the source of truth for which workspace owns a domain.
- Inbox state is tracked in `sender_accounts`:
  - `inbox_state` enum: `live`, `dead`, `incubating`, etc.
  - `inventory_pool_status` enum: `live`, `reserve`, `incubating`, NULL.
  - `is_active` boolean: tracked in EB or removed.
  - `killed_at`, `disconnected_at`, `kill_trigger`: failure metadata.
- Campaign-inbox attachments tracked in `campaign_inboxes` (updated by `sync_campaigns.sync_campaign_inbox_assignments` after each campaign sync, ~1hr).
- The tool deliberately writes no new tables in v1. Operational metrics queryable from existing data — see `apps/eod-reapply/README.md` "Tracking & operational metrics" section.

---

## 10. Where to start as the next chat

If the work is **"add the cross-workspace tenant guard"** (P1):
- Edit `apps/eod-reapply/src/eod_reapply/reapply.py`: add `SKIPPED_CROSS_WORKSPACE_TENANT` to `ReapplyStatus`, add a check after the diff computation that DB-queries each target sender's domain owner, fails if any disagree.
- Edit `apps/eod-reapply/src/eod_reapply/check.py`: add a `cross_workspace_tenants` check that reports FAIL for any foreign-domain senders in target_set.
- Edit `apps/eod-reapply/src/eod_reapply/cli.py`: update exit code mapping for the new status.
- New tests in `apps/eod-reapply/tests/test_reapply.py` and `tests/test_check.py`.
- Run `py -m pytest && py -m ruff check src tests && py -m mypy --strict src/eod_reapply`. Commit.

If the work is **"deploy to Coolify"** (P2):
- Use `scripts/coolify.py` to inspect the existing `emailbison-sync` service for env-var patterns.
- Create a new service in Coolify UI pointing at `apps/eod-reapply/Dockerfile`.
- Override CMD to `sleep infinity`.
- Set env vars from secrets (DATABASE_URL, EMAILBISON_API_URL).
- Smoke-test via container exec.

If the work is **"investigate Hypertide"** (P3):
- The audit found 50+ inboxes were created on 2026-04-14 across multiple workspace pairs. Look at git history for that date in `Hypertide/` directory and `pipeline_handlers/`. Smoking gun: any code that calls EB's `POST /api/sender-emails` with a workspace_id parameter.
- Check audit_logs table for any provisioning entries on the implicated dates (2026-03-11, 2026-03-31, 2026-04-14).
- Cross-reference with `inbox_purchase_jobs`, `inbox_rotation_history`.

If the work is **"real --apply staging run"** (P4):
- Prereq: P0 + P1 done.
- Read `apps/eod-reapply/STAGING-RUNBOOK.md` end-to-end. Appendix A has the test campaign setup recipe.
- Charm has no active campaigns currently — would need to either create one or use a workspace that does. Avoid Sammy and SKMR until pollution is fixed.

---

## 11. The user's known concerns / preferences (from the working session)

- Wanted thorough testing, not yes-man behavior. Pushed for deeper checks at every layer.
- Concerned about silent errors — every audit pass should ask "are there any silent errors?" The pagination silent-truncation bug surfaced from this discipline.
- Knows EB and the sync system in detail. Caught the cross-workspace pollution intuition immediately when domains looked wrong.
- Wants minimal DB bloat — declined adding new tables in v1, opted for JSONL append for run history. New tables are v2 scope only when there's a real query that needs them.
- Aware that reapply tool itself is correct; the upstream provisioning bug is the actual problem to chase.

---

## 12. Final state numbers (as of this handoff)

- v1 code: 222 tests, 99% coverage, ruff/mypy/pytest all clean
- 8 commits on `plan/eod-campaign-reapply`, all pushed to `hirecharm`
- 8 of 11 active workspaces are pollution-free
- 22 immediate-risk cross-workspace mismatches (Sammy ← SPUI)
- 60 latent-risk mismatches (Sammy ← Spout, SKMR ← Sammy, Spout ← SPUI)
- Tool is deployed nowhere yet (Coolify service not provisioned)
- Real `--apply` against any production campaign has never been run
