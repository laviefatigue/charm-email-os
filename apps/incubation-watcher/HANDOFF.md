---
title: Incubation Watcher — Handoff & Status
date: 2026-04-30
audience: any future chat / engineer continuing this work
status: v1 scaffold complete; not yet deployed; shadow validation pending
---

# Incubation Watcher — Handoff Document

Self-contained handoff. Read top to bottom for full picture.

---

## 0. TL;DR

We extracted the incubation graduation logic from `sync_modules/lifecycle_tag_sync.py`
into a standalone Coolify-ready app at `apps/incubation-watcher/`. It mirrors
the structure of `apps/eod-reapply/` (per-workspace API keys, async httpx,
asyncpg, click CLI, multi-stage Dockerfile).

**v1 ships the scaffold + dry-run capability.** Shadow validation against
the existing `lifecycle_tag_sync` runs next. Cutover (existing module
disabled in `emailbison-sync`) only after ≥7 days of parity.

The existing module in `emailbison-sync` continues to handle production
graduation unchanged. Nothing in production is affected by this
extraction yet.

---

## 1. What's in this app

```
apps/incubation-watcher/
├── pyproject.toml                       # Python 3.11+, asyncpg, httpx, click
├── Dockerfile                           # Multi-stage Python 3.13-slim
├── .dockerignore
├── .gitignore
├── README.md                            # operator-facing
├── HANDOFF.md                           # this file
├── src/incubation_watcher/
│   ├── __init__.py                      # version
│   ├── cli.py                           # click entrypoint (check, run)
│   ├── db.py                            # workspace context + ready-to-graduate query
│   ├── eb_client.py                     # workspace-scoped EB API (list_tags, get_or_create_tag, tag, untag)
│   └── graduator.py                     # graduate_one() — the single-inbox transition
└── tests/
    ├── __init__.py
    └── test_graduator.py                # smoke tests for ESP→pool mapping + dry-run path
```

Pure-Python, no charm-email-os imports. Self-contained.

---

## 2. What it does

For one workspace at a time:

1. `fetch_workspace_context(name)` — lookup `workspace_api_keys` for the scoped Sanctum token
2. `fetch_graduation_candidates(workspace_id)` — DB query mirroring
   `lifecycle_tag_sync.py:256-281` exactly (same WHERE clause, same business-day count)
3. For each candidate: `graduate_one()`:
   a. `eb.untag_inbox(emailbison_account_id, incubating_tag_id)` — 404 swallowed
   b. `eb.tag_inbox(emailbison_account_id, target_tag_id)` — 404 = ORPHAN, skip
   c. DB transaction: `UPDATE sender_accounts` + `INSERT inbox_rotation_history`
4. Aggregate outcomes, exit with appropriate code

Order of operations matches the existing module exactly: EB-first, DB-on-success.
If step b raises non-404, row stays at `lifecycle='incubating'` and retries
on next cycle.

ESP routing:
- `esp == 'microsoft'` → tag with `live`, set `pool='live'`
- `esp == 'gmail'` or unknown → tag with `reserve`, set `pool='reserve'`

---

## 3. Why this is a separate app, not just a module

Per [docs/plans/emailbison-sync-decomposition.md](../../docs/plans/emailbison-sync-decomposition.md) §2.3 and §6:

- **Distinct failure mode**: "incubation-watcher unhealthy" maps to one specific
  concern. Today, a graduation bug is invisible inside `emailbison-sync`'s
  ~14 concerns running in one process.
- **Service-level health check**: Coolify will surface "incubation-watcher
  hasn't graduated anyone in N hours" as a service-level alert, instead of
  buried inside one of the sync worker's 30-minute cycles.
- **Atomic ownership**: this service is the sole authority for the
  incubating → reserve/live transition. After cutover.
- **Per-workspace clarity**: workspace-scoped Sanctum token is the only
  client. No `switch_workspace`, no shared state across workspaces.

The cost (one extra Coolify service, ~50 lines of duplicated EB client +
DB lookup vs the shared sync_modules) is paid once. The visibility win is
ongoing.

---

## 4. What's NOT in v1

| Feature | Status | Why deferred |
|---------|:------:|--------------|
| Daemon poll loop | NOT in v1 | Operator-invoked CLI is enough for shadow validation. v2 adds a continuous loop. |
| `_tag_new_warmup_inboxes` | NOT in v1 | Adds the 'incubating' tag to brand-new inboxes. Existing module still does this; v2 of this app picks it up. |
| `_untag_incubating_from_active` | NOT in v1 | Orphan-cleanup pass. Existing module still does this; v2 picks it up. |
| `_remove_live_from_dead` | NOT in v1 | Dead-state safety net. Existing module still does this; arguably belongs in `kill-watcher` per decomposition plan. |
| Daemon health endpoint | NOT in v1 | v1 is operator-invoked; v2 adds /health for Coolify. |
| Cross-workspace fanout | NOT in v1 | One workspace per CLI invocation. v2 daemon iterates all active workspaces. |
| Full test suite (matching eod-reapply's 222) | NOT in v1 | Smoke tests only for now. Build out as the app matures. |

This is the **minimum viable extraction** per decomposition plan §15 — extract
incubation only, validate the pattern, decide on the other 4 services after
30 days of operational evidence.

---

## 5. How to run it locally

```bash
cd apps/incubation-watcher
pip install -e ".[dev]"

export DATABASE_URL='postgresql://...'
export EMAILBISON_API_URL='https://spellcast.hirecharm.com/api'

# Read-only — list candidates
incubation-watcher check --workspace Charm

# Dry-run — exercises orchestrator path, no writes
incubation-watcher run --workspace Charm

# Real — mutates EB tags + DB
incubation-watcher run --workspace Charm --apply
```

---

## 6. Shadow validation plan

Before flipping ownership from `emailbison-sync` to this service:

1. Deploy this service to Coolify with CMD override `sleep infinity`.
2. Set up a daily cron (or scheduled task) that runs:
   ```bash
   incubation-watcher run --workspace <each_active_workspace>
   # WITHOUT --apply
   ```
   This exercises the full orchestrator including EB tag-id resolution
   (which IS a real EB call, but read-only).
3. Capture the output. Compare against:
   - DB rotation_history: did the existing module graduate anyone in
     this window?
   - This service's stdout: did it propose to graduate the same set?
4. Acceptance criterion: 7 consecutive days with zero divergence
   (proposed-set == actually-graduated-set).
5. After acceptance: set `ENABLE_LIFECYCLE_TAGGING=false` in
   `emailbison-sync`, set `incubation-watcher` to `--apply` mode in its
   daemon. Watch for 7 days. If clean, decommission the existing module.

---

## 7. Tests

```bash
cd apps/incubation-watcher
py -m pytest                                              # all tests
py -m ruff check src tests                                # lint
py -m mypy --strict src/incubation_watcher                # types
```

v1 tests are smoke-level — `target_pool_for_esp` correctness, dry-run
returns the right outcome, EBClient exception model. The DB query is
not mocked yet because the SQL must match the existing module's SQL byte-
for-byte; that's tested in shadow validation, not unit tests.

---

## 8. Failure modes

| Mode | What happens | Mitigation |
|------|--------------|------------|
| EB 404 on untag (incubating not present) | Swallowed — that's the goal | n/a |
| EB 404 on tag destination (orphan) | Logged ORPHAN, skip the row, exit code 2 | sync_accounts.mark_stale_accounts in emailbison-sync flips is_active=FALSE within 1h |
| EB 5xx / network on tag | Row stays at incubating, exit code 1 | Retry next cycle (or operator re-runs) |
| DB connection failure | exit code 3 | Coolify restarts; pool re-acquired |
| Workspace not found / inactive / no API key | exit code 2/3 | Operator catches in alert; usually means key revoked |
| Two services try to graduate same inbox concurrently (during shadow validation) | Second UPDATE is a no-op (lifecycle already 'active'); second tag is wasted | Acceptable for shadow window |

---

## 9. Open issues / next-session priorities

In priority order:

1. **Add full unit tests** to match eod-reapply's discipline (mypy strict, ruff clean, ≥99% coverage). Today's smoke tests are placeholder.
2. **Ship to Coolify** with CMD `sleep infinity`. Provision env vars.
3. **Set up shadow validation cron**. 7 days minimum before any cutover discussion.
4. **Extend to handle `_tag_new_warmup_inboxes`** — currently in `emailbison-sync` only. Once shadow shows graduation parity, the new-warmup tagger is a small addition.
5. **Decide whether `_untag_incubating_from_active` belongs here or in a separate orphan-cleanup module.** The original module does it; arguments either way.

---

## 10. References

- Plan: [docs/plans/emailbison-sync-decomposition.md](../../docs/plans/emailbison-sync-decomposition.md) §6.2
- Tracker: [docs/plans/INBOX-INTEGRITY-PROGRAM.md](../../docs/plans/INBOX-INTEGRITY-PROGRAM.md)
- Reference arch: [apps/eod-reapply/](../eod-reapply/) (HANDOFF.md, src/, tests/)
- Module being mirrored: [sync_modules/lifecycle_tag_sync.py](../../sync_modules/lifecycle_tag_sync.py)
- Production services list: [production/coolify/services.md](../../production/coolify/services.md)
