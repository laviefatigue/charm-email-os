# eod-reapply

One-shot CLI that reapplies a campaign's `live`-tagged sender set as its EmailBison sender attachment. Closes the loop that `kill_processor` leaves open: dead inboxes lose the `live` tag in EB, but stay attached to active campaigns until something — this tool — reconciles the attachment.

## Status

**v1 — operator-invoked. Not deployed as a service.**

Tested up through L4 (mocked unit + integration). **Not yet through L5** (real-EB staging). See [STAGING-RUNBOOK.md](./STAGING-RUNBOOK.md) — that gate is mandatory before any production use.

## What it does, in one paragraph

For a single (workspace, campaign) pair:

1. Pull the campaign's status and refuse if not Active/Queued/Sending.
2. Pull the campaign's schedule. Refuse to mutate unless `now` is past `end_time + buffer` in the campaign's IANA timezone, on a sending day, and not already run for today's local date. (Bypassable with `--skip-time-check`.)
3. Resolve the `live` tag id in this workspace. Pull the senders that have it. Pull the senders currently attached to the campaign. Compute the diff.
4. If diff is empty → no-op success.
5. If `--apply`: pause campaign → attach added → remove dropped → fetch & verify set equality → resume campaign. The resume is in a `finally` block.

## Run

```bash
cd apps/eod-reapply
pip install -e .

export DATABASE_URL='postgresql://...'
export EMAILBISON_API_URL='https://spellcast.hirecharm.com/api'

# Dry-run (default — no mutations)
eod-reapply reapply --workspace "Charm" --campaign-id 123

# Apply
eod-reapply reapply --workspace "Charm" --campaign-id 123 --apply

# Bypass the EOD time gate (use with care)
eod-reapply reapply --workspace "Charm" --campaign-id 123 --apply --skip-time-check
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success or benign no-op (no-diff, not-active, time-gate-closed) |
| 1 | Dry-run completed and would have made changes |
| 2 | Failed but campaign is in its original (non-paused) state |
| 3 | **CRITICAL** — campaign may be left paused. Operator must verify and resume. |

## Layout

```
apps/eod-reapply/
├── pyproject.toml
├── README.md
├── STAGING-RUNBOOK.md          ← L5 gate before production
├── src/eod_reapply/
│   ├── __init__.py
│   ├── window.py               ← pure tz-aware predicate (L1)
│   ├── eb_client.py            ← workspace-scoped EB API subset (L2)
│   ├── reapply.py              ← orchestrator (L3)
│   ├── db.py                   ← workspace_api_keys lookup
│   └── cli.py                  ← entrypoint (L4)
└── tests/
    ├── test_window.py          ← 43 cases — TZ matrix, DST, Sammy-Sydney
    ├── test_eb_client.py       ← 38 cases — mocked httpx, error paths
    ├── test_reapply.py         ← 49 cases — orchestrator + invariant sweep
    └── test_cli.py             ← 27 cases — exit codes, arg parsing
```

## Running the tests

```bash
cd apps/eod-reapply
py -m pytest          # 157 tests, ~9s
py -m pytest -v       # verbose
py -m pytest tests/test_window.py -v   # one suite
```

## Roadmap (v2)

The orchestrator is exposed as a library function (`reapply_campaign(...)`) so the v2 scheduler can import it without changes:

- New tables: `campaign_schedules` (cache of EB schedule data), `campaign_reapply_runs` (idempotency keyed on `(campaign_id, run_local_date)`).
- A poll loop that, every ~5 minutes, evaluates the time gate for every active campaign and calls `reapply_campaign(...)` for ones whose window is open and haven't run today.
- Coolify-deployable worker. See [docs/plans/eod-campaign-reapply.md](../../docs/plans/eod-campaign-reapply.md) for the full v2 scope.

## Pre-requisites that haven't been resolved yet

These don't block v1 (the CLI works without them) but flag risks:

1. **`api/routes/strategy.py:1572` hardcodes `America/New_York` when creating campaigns via Strategy AI.** Non-US workspaces get the wrong baseline schedule. The EOD reapply tool will surface this as wrong-window reapplies for those campaigns. Fix tracked separately.
2. **`workspace_api_keys.key_token` is plaintext.** This tool reads it directly. Same posture as the existing sync worker; flagged for future encryption-at-rest work.
