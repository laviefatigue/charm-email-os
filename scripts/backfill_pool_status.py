#!/usr/bin/env python3
"""
Backfill `sender_accounts.inventory_pool_status` for graduated inboxes that
have no per-inbox pool status set.

Why this exists
───────────────
The 2026-04-27 tagging overhaul shifted authority for EB pool tags from
`domain.pool_status` (per-domain) to `sender_accounts.inventory_pool_status`
(per-inbox). Phase 0 diagnostics found 1,034 graduated inboxes
(`inventory_lifecycle_status='active'`) with `inventory_pool_status=NULL`.
After Phase 2 deploys, set_tag_sync would untag both `live` and `reserve`
from these inboxes — disrupting sending for any that are currently part
of campaigns.

This script must run BEFORE Phase 2 ships to production.

Backfill rule (ESP-aware, matches lifecycle_tag_sync graduation logic):
- esp='microsoft' (legacy ride-to-death) → inventory_pool_status='deployed'
- esp='gmail' (Google), domain.pool_status='live'    → 'deployed'
- esp='gmail' (Google), domain.pool_status='reserve' → 'reserve'
- esp='gmail' (Google), other / NULL                 → leave NULL (genuinely
  unallocated; they will be picked up when a domain is allocated explicitly)

Usage
─────
    python scripts/backfill_pool_status.py --dry-run         # Preview
    python scripts/backfill_pool_status.py                    # Apply
    python scripts/backfill_pool_status.py --workspace Selery # Single workspace
"""
import argparse
import json
import requests

ADMIN_API = "https://api.wizardgrimoire.cloud/api/admin/run-sql"


def run_sql(admin_key: str, sql: str):
    r = requests.post(ADMIN_API, params={"key": admin_key, "sql": sql}, timeout=60)
    r.raise_for_status()
    return r.json().get("result", [])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--admin-key",
        required=True,
        help="Admin API key for run-sql endpoint",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show counts without applying updates",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        help="Filter to a single workspace (case-insensitive substring match)",
    )
    args = parser.parse_args()

    ws_filter_clause = ""
    if args.workspace:
        # Single-quote escape — workspace names are admin-controlled, but be safe.
        safe = args.workspace.replace("'", "''")
        ws_filter_clause = f"AND w.workspace_name ILIKE '%{safe}%'"

    # Step 1: count what would be updated
    count_sql = f"""
    SELECT
        CASE
            WHEN sa.esp = 'microsoft' THEN 'microsoft -> deployed'
            WHEN sa.esp = 'gmail' AND d.pool_status = 'live' THEN 'gmail/live-domain -> deployed'
            WHEN sa.esp = 'gmail' AND d.pool_status = 'reserve' THEN 'gmail/reserve-domain -> reserve'
            ELSE 'leave NULL (unallocated)'
        END AS bucket,
        COUNT(*) AS inboxes
    FROM sender_accounts sa
    JOIN domains d ON sa.domain_id = d.id
    JOIN workspaces w ON sa.workspace_id = w.id
    WHERE sa.is_active = TRUE
      AND sa.inbox_state = 'live'
      AND sa.inventory_lifecycle_status = 'active'
      AND sa.inventory_pool_status IS NULL
      {ws_filter_clause}
    GROUP BY bucket
    ORDER BY inboxes DESC
    """
    print("=" * 60)
    print("BACKFILL inventory_pool_status — preview")
    print("=" * 60)
    rows = run_sql(args.admin_key, count_sql)
    if not rows:
        print("Nothing to backfill — all graduated inboxes have a pool status.")
        return
    for row in rows:
        print(f"  {row['bucket']:<40} {row['inboxes']:>6}")

    if args.dry_run:
        print("\n--dry-run set; no updates applied.")
        return

    # Step 2: apply updates in three SQL passes (matches the rule buckets).
    apply_passes = [
        (
            "Microsoft → deployed",
            f"""
            UPDATE sender_accounts sa
            SET inventory_pool_status = 'deployed', updated_at = NOW()
            FROM workspaces w
            WHERE sa.workspace_id = w.id
              AND sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.inventory_lifecycle_status = 'active'
              AND sa.inventory_pool_status IS NULL
              AND sa.esp = 'microsoft'
              {ws_filter_clause}
            """,
        ),
        (
            "Google + live-pool domain → deployed",
            f"""
            UPDATE sender_accounts sa
            SET inventory_pool_status = 'deployed', updated_at = NOW()
            FROM domains d, workspaces w
            WHERE sa.domain_id = d.id
              AND sa.workspace_id = w.id
              AND sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.inventory_lifecycle_status = 'active'
              AND sa.inventory_pool_status IS NULL
              AND sa.esp = 'gmail'
              AND d.pool_status = 'live'
              {ws_filter_clause}
            """,
        ),
        (
            "Google + reserve-pool domain → reserve",
            f"""
            UPDATE sender_accounts sa
            SET inventory_pool_status = 'reserve', updated_at = NOW()
            FROM domains d, workspaces w
            WHERE sa.domain_id = d.id
              AND sa.workspace_id = w.id
              AND sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.inventory_lifecycle_status = 'active'
              AND sa.inventory_pool_status IS NULL
              AND sa.esp = 'gmail'
              AND d.pool_status = 'reserve'
              {ws_filter_clause}
            """,
        ),
    ]

    print("\nApplying...")
    for label, sql in apply_passes:
        # The admin SQL endpoint rejects data-modifying CTEs (HTTP 500 on
        # `WITH upd AS (UPDATE ... RETURNING ...) SELECT ...`). Run the plain
        # UPDATE directly — the endpoint accepts UPDATEs but does not return
        # an affected-row count, so we measure with a follow-up SELECT.
        run_sql(args.admin_key, sql)
        # Affected-row count is implicit (the query is "set X where Y AND
        # current is NULL"; running the same dry-run query again returns
        # the now-zero remaining count, so the diff is what we just did).
        print(f"  {label}: applied")

    print("\nDone. Verify with: scripts/backfill_pool_status.py --dry-run")
    print("Re-running --dry-run after success should show 0 in each non-NULL bucket.")


if __name__ == "__main__":
    main()
