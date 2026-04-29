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

## Tracking & operational metrics

v1 deliberately does **not** add new tables. Existing schema already captures the inbox-flow data, and the CLI's JSON output gives per-run audit. Two patterns:

### Per-run history — append the JSON output to a logfile

The CLI's `--json-only` flag emits a single JSON object per run. Pipe to a JSONL log:

```bash
mkdir -p ~/.local/share/eod-reapply
eod-reapply reapply --workspace Sammy --campaign-id 123 --apply --json-only \
  >> ~/.local/share/eod-reapply/runs.jsonl
```

Query with `jq`:

```bash
# All runs for a workspace
jq 'select(.workspace_name=="Sammy")' ~/.local/share/eod-reapply/runs.jsonl

# Only failures that left a campaign paused
jq 'select(.status=="failed_left_paused")' ~/.local/share/eod-reapply/runs.jsonl

# Sum of inboxes attached + removed across all runs today
jq -s '[.[] | select(.status=="succeeded")]
       | {attached: ([.[].attached_ids|length]|add), removed: ([.[].removed_ids|length]|add)}' \
   ~/.local/share/eod-reapply/runs.jsonl
```

### Capacity questions — query existing tables

The user-facing question *"how many inboxes do we need to add back to reserve?"* is answered by data the existing sync engine already maintains. No reapply-specific table required.

**Daily live-set shrinkage per workspace** (last 30 days — counts inboxes detached from any campaign, regardless of cause):

```sql
SELECT
    w.workspace_name,
    DATE(ci.removed_at) AS day,
    COUNT(DISTINCT ci.sender_account_id) AS inboxes_removed
FROM campaign_inboxes ci
JOIN emailbison_campaigns ec ON ci.campaign_id = ec.id
JOIN workspaces w ON ec.workspace_id = w.id
WHERE ci.removed_at >= NOW() - INTERVAL '30 days'
  AND ci.removed_at IS NOT NULL
GROUP BY w.workspace_name, DATE(ci.removed_at)
ORDER BY day DESC, inboxes_removed DESC;
```

> **Lag note:** `campaign_inboxes` is updated by `sync_campaign_inbox_assignments()` after each campaign sync (~1 hour cycle). Reapply changes show up on the next sync, not instantly. For real-time per-run data, use the JSONL log above.

**Current live vs reserve gap per workspace** (right now):

```sql
SELECT
    w.workspace_name,
    COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'live')        AS live_count,
    COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve')     AS reserve_count,
    COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'incubating')  AS incubating_count
FROM sender_accounts sa
JOIN workspaces w ON sa.workspace_id = w.id
WHERE sa.is_active = TRUE
  AND w.is_active = TRUE
GROUP BY w.workspace_name
ORDER BY w.workspace_name;
```

**Cross-reference: are recent removals causing live-set pressure?** Combine the two:

```sql
WITH attrition AS (
    SELECT ec.workspace_id, COUNT(DISTINCT ci.sender_account_id) AS removed_7d
    FROM campaign_inboxes ci
    JOIN emailbison_campaigns ec ON ci.campaign_id = ec.id
    WHERE ci.removed_at >= NOW() - INTERVAL '7 days'
    GROUP BY ec.workspace_id
),
pool AS (
    SELECT workspace_id,
           COUNT(*) FILTER (WHERE inventory_pool_status='live') AS live_now,
           COUNT(*) FILTER (WHERE inventory_pool_status='reserve') AS reserve_now
    FROM sender_accounts WHERE is_active = TRUE
    GROUP BY workspace_id
)
SELECT w.workspace_name,
       p.live_now,
       p.reserve_now,
       COALESCE(a.removed_7d, 0) AS removed_last_7d,
       CASE WHEN p.reserve_now < COALESCE(a.removed_7d, 0)
            THEN 'NEEDS BACKFILL — reserve smaller than weekly attrition'
            ELSE 'ok' END AS signal
FROM workspaces w
JOIN pool p ON p.workspace_id = w.id
LEFT JOIN attrition a ON a.workspace_id = w.id
WHERE w.is_active = TRUE
ORDER BY w.workspace_name;
```

### Why no `campaign_reapply_runs` table in v1

Considered and rejected. Reasoning:

- **`campaign_inboxes` is already the source of truth** for "which inboxes are attached to which campaigns over time." Adding a parallel reapply-specific table creates two sources of truth that can diverge under partial-failure.
- **Per-run audit** is solved by JSONL append (above). No additional persistence required for an operator-invoked tool.
- **Idempotency keying** ("did I run this campaign already today?") is a v2 (scheduler) concern. Without that query, the table would be decorative.
- **Schema discipline:** Charm has 70+ tables. New tables get added when they earn it, not pre-emptively.

The v2 scheduler is when `campaign_reapply_runs` is justified — because v2 has a real query for it. Until then, every metric the operator needs is already answerable.

## Layout

```
apps/eod-reapply/
├── pyproject.toml
├── README.md
├── STAGING-RUNBOOK.md              ← L5 gate before production
├── docs/
│   └── eb-api-deep-dive.md         ← EB API reference distilled from live OpenAPI
├── src/eod_reapply/
│   ├── __init__.py
│   ├── window.py                   ← pure tz-aware predicate (L1)
│   ├── eb_client.py                ← workspace-scoped EB API subset (L2)
│   ├── reapply.py                  ← orchestrator (L3)
│   ├── db.py                       ← workspace_api_keys lookup
│   └── cli.py                      ← entrypoint (L4)
└── tests/
    ├── test_window.py              ← 43 cases — TZ matrix, DST, Sammy-Sydney
    ├── test_eb_client.py           ← 44 cases — mocked httpx, errors, defensive shapes, pagination safety
    ├── test_reapply.py             ← 53 cases — orchestrator + invariant sweep + defensive resume
    ├── test_cli.py                 ← 27 cases — exit codes, arg parsing, output rendering
    ├── test_cli_e2e.py             ← 5 cases — full async pipeline against respx + mocked asyncpg
    └── test_db.py                  ← 5 cases — fetch_workspace_context query shape + result mapping
```

## Running the tests

```bash
cd apps/eod-reapply
py -m pytest                                              # 177 tests, ~21s, 99% coverage
py -m pytest -v                                           # verbose
py -m pytest --strict-markers --strict-config             # warnings as errors (filterwarnings = ["error"] in pyproject)
py -m pytest --cov=src/eod_reapply --cov-report=term-missing   # coverage breakdown
py -m pytest tests/test_window.py -v                      # single suite
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
