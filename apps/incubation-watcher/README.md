# Incubation Watcher

Per-workspace incubation graduation daemon. Extracted from
`sync_modules/lifecycle_tag_sync.py` per the
[emailbison-sync decomposition plan](../../docs/plans/emailbison-sync-decomposition.md).

## What it owns

When an inbox completes 14 business days of continuous warmup, it should
graduate from `inventory_lifecycle_status='incubating'` to `'active'` and
get a pool tag — `live` for Microsoft Entra (ride-to-death) or `reserve`
for Google (bench, awaits promotion via kill-driven deficit).

This service performs that graduation per workspace, using the
workspace's own scoped EmailBison API key (no `switch_workspace`).

## Status

**v1 — operator-invoked, NOT yet running in production.** The existing
`lifecycle_tag_sync` in `emailbison-sync` continues to handle production
graduation. This service ships in shadow / read-only mode first, and only
takes over once parity is verified for ≥7 days.

## Subcommands

```bash
incubation-watcher check --workspace Charm
# Read-only. Lists inboxes eligible for graduation in Charm.

incubation-watcher run --workspace Charm
# Dry-run. Same as check, but exercises the orchestrator path
# (resolves tag IDs in EB, computes target pool per ESP).

incubation-watcher run --workspace Charm --apply
# Real run. Untag 'incubating' in EB, tag destination, update DB,
# log to inbox_rotation_history. Atomic per inbox.
```

## Exit codes

| Subcommand | Code | Meaning |
|------------|:----:|---------|
| check | 0 | Listed candidates (count is in stdout) |
| check | 2 | Workspace not found / inactive / no API key |
| run | 0 | All candidates handled (graduated / dry_run) |
| run | 1 | At least one transient EB failure — retry next cycle |
| run | 2 | At least one workspace orphan (sender not in this EB workspace) |
| run | 3 | Config / connection error |

## Environment variables

| Variable | Required | Default |
|----------|:--------:|---------|
| `DATABASE_URL` | YES | — |
| `EMAILBISON_API_URL` | no | `https://spellcast.hirecharm.com/api` |
| `LOG_LEVEL` | no | `INFO` |

## Coolify deployment (when ready)

Same pattern as `apps/eod-reapply/`:

1. Service type: Dockerfile
2. Build context: `apps/incubation-watcher/`
3. CMD override: `sleep infinity` for v1 (operator-invoked).
   When v2 daemon mode lands, override with the daemon entry.
4. Env vars: `DATABASE_URL`, `EMAILBISON_API_URL` from Coolify secrets.
5. Operator runs:
   ```bash
   coolify exec incubation-watcher incubation-watcher check --workspace Charm
   ```

## Why a separate service

Per the decomposition plan §2.3:

- **Distinct failure mode**: "incubation-watcher unhealthy" is a clear
  signal. Today, when graduation fails for one workspace, it's lost in
  the noise of `emailbison-sync` running 14 other concerns.
- **Per-workspace API key clarity**: each invocation uses one workspace's
  scoped Sanctum token. No workspace context-switching, no shared client.
- **Test surface isolation**: the graduation logic can be exercised end-
  to-end against a single workspace without standing up the full sync
  worker.
- **Atomic ownership**: this service is the sole authority for the
  incubating → reserve/live transition. No coordination with other
  services mid-flow.

## Compatibility with existing emailbison-sync

The existing `sync_modules/lifecycle_tag_sync.py` continues to run inside
`emailbison-sync` until cutover. During shadow validation:

- Both paths read the same DB
- Both paths apply the same EB tags via the same workspace API key
- Both paths log to `inbox_rotation_history`

There is a brief race window where both could try to graduate the same
inbox simultaneously. The DB transaction in `update_graduation` means
the second write is a no-op (lifecycle is already 'active') — but the
second EB tag operation is wasted. That's acceptable for shadow validation.

After cutover (`ENABLE_LIFECYCLE_TAGGING=false` in `emailbison-sync`),
this service is the only path.

## Testing

```bash
pip install -e ".[dev]"
py -m pytest                                    # all tests
py -m ruff check src tests                      # lint
py -m mypy --strict src/incubation_watcher      # types
```

## Related

- Plan: [docs/plans/emailbison-sync-decomposition.md](../../docs/plans/emailbison-sync-decomposition.md) §6.2
- Tracker: [docs/plans/INBOX-INTEGRITY-PROGRAM.md](../../docs/plans/INBOX-INTEGRITY-PROGRAM.md) §3.5
- Source module being mirrored: [sync_modules/lifecycle_tag_sync.py](../../sync_modules/lifecycle_tag_sync.py) (`_graduate_mature_inboxes`)
- Reference architecture: [apps/eod-reapply/](../eod-reapply/)
