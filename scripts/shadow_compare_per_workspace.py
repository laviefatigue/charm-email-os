"""
Per-workspace shadow-compare receipts for the incubation-watcher cutover.

Companion to docs/operations/2026-05-05-event-driven-cutover-runbook.md §2.1.

Mirrors apps/incubation-watcher/src/incubation_watcher/shadow.py + db.py logic
in a single round-trip across the 4 workspaces with active graduations
(Charm, Stable Kernel Market Research, Sammy, Spout). Run as a sanity
check before flipping APPLY=true on incubation-watcher.

For each workspace:
  proposed = current eligible-for-graduation set (watcher's predicate, NOW)
  actual   = inbox_rotation_history rows from lifecycle_tag_sync in last 24h

Parity signal that matters: watcher_only (rows the watcher would graduate
that lifecycle_tag_sync has NOT graduated yet). actual_only is structural
since graduated rows leave the watcher's predicate (lifecycle = 'active'
not 'incubating'); it is recent-throughput, not a bug.

Pass condition: watcher_only == 0 for every workspace.

Usage:
    py scripts/shadow_compare_per_workspace.py
"""
import json
import sys
import urllib.parse
import urllib.request

ADMIN_API = "https://api.wizardgrimoire.cloud/api/admin/run-sql"
ADMIN_KEY = "098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa"

WORKSPACES = ["Charm", "Stable Kernel Market Research", "Sammy", "Spout"]


def post_sql(sql: str) -> list[dict]:
    qs = urllib.parse.urlencode({"key": ADMIN_KEY, "sql": sql})
    req = urllib.request.Request(
        f"{ADMIN_API}?{qs}",
        method="POST",
        headers={"Accept": "application/json", "User-Agent": "curl/8.0.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read())
    return body.get("result", [])


SQL_PROPOSED = """
SELECT w.workspace_name, sa.email_address
FROM workspaces w
JOIN sender_accounts sa ON sa.workspace_id = w.id
WHERE w.is_active = TRUE
  AND w.workspace_name IN ('Charm','Stable Kernel Market Research','Sammy','Spout')
  AND sa.inbox_state = 'live'
  AND sa.is_active = TRUE
  AND sa.warmup_enabled = TRUE
  AND sa.warmup_enabled_since IS NOT NULL
  AND sa.inventory_lifecycle_status = 'incubating'
  AND sa.emailbison_account_id IS NOT NULL
  AND (
    SELECT COUNT(*)
    FROM generate_series(
      sa.warmup_enabled_since::date,
      CURRENT_DATE - INTERVAL '1 day',
      INTERVAL '1 day'
    ) AS d
    WHERE EXTRACT(DOW FROM d) NOT IN (0, 6)
  ) >= 14
ORDER BY w.workspace_name, sa.email_address
"""

SQL_ACTUAL = """
SELECT DISTINCT w.workspace_name, irh.target_inbox_email AS email_address
FROM workspaces w
JOIN inbox_rotation_history irh ON irh.workspace_id = w.id
WHERE w.is_active = TRUE
  AND w.workspace_name IN ('Charm','Stable Kernel Market Research','Sammy','Spout')
  AND irh.rotation_type = 'graduate'
  AND irh.triggered_by = 'lifecycle_tag_sync'
  AND irh.executed_at >= NOW() - INTERVAL '24 hours'
ORDER BY w.workspace_name, email_address
"""


def main() -> int:
    proposed_rows = post_sql(SQL_PROPOSED)
    actual_rows = post_sql(SQL_ACTUAL)

    by_ws: dict[str, dict[str, set[str]]] = {
        w: {"proposed": set(), "actual": set()} for w in WORKSPACES
    }
    for row in proposed_rows:
        w = row["workspace_name"]
        if w in by_ws:
            by_ws[w]["proposed"].add(row["email_address"])
    for row in actual_rows:
        w = row["workspace_name"]
        if w in by_ws:
            by_ws[w]["actual"].add(row["email_address"])

    print("=" * 84)
    print(
        f"{'Workspace':<35} {'proposed':>9} {'actual_24h':>11} "
        f"{'watcher_only':>13} {'actual_only':>12}"
    )
    print("-" * 84)
    real_divergence = 0
    for w in WORKSPACES:
        p = by_ws[w]["proposed"]
        a = by_ws[w]["actual"]
        watcher_only = p - a
        actual_only = a - p
        real_divergence += len(watcher_only)
        print(
            f"{w:<35} {len(p):>9} {len(a):>11} "
            f"{len(watcher_only):>13} {len(actual_only):>12}"
        )
        if watcher_only:
            for e in sorted(watcher_only)[:5]:
                print(f"  ! watcher_only: {e}")
    print("=" * 84)
    print(
        "Parity signal = watcher_only. actual_only is informational "
        "(recent graduation\nthroughput; structurally non-empty since "
        "graduated rows leave the watcher's\nincubating predicate)."
    )
    if real_divergence == 0:
        print(
            "\nRESULT: zero parity divergence (watcher_only=0 across "
            "all 4 workspaces)."
        )
        print("        Safe to flip APPLY=true per runbook §2.2.")
        return 0
    print(
        f"\nRESULT: {real_divergence} watcher_only rows. "
        "Investigate BEFORE flipping APPLY=true."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
