#!/usr/bin/env python3
"""
audit_package_assignments.py — read-only audit + recommendation for
clients.workspace_packages assignment.

Per docs/plans/INBOX-INTEGRITY-PROGRAM.md §3.7, only Stable Kernel Market
Research has a package_id assigned. Without a package, the proactive
threshold-driven promotion path doesn't fire (only kill-driven backup
promotion runs). All other workspaces operate kill-reactive only.

This script:
  1. Pulls current package state per active workspace
  2. Computes observed metrics (active inboxes, live count, 24h sends)
  3. Cross-references against available packages (50k_google, 100k_google)
  4. Produces a per-workspace recommendation for operator review
  5. Outputs CSV to docs/audits/<date>-package-recommendations.csv
     with `operator_decision` + `operator_notes` blank for fill-in

NEVER WRITES TO DB. Operator runs UPDATE statements manually after
reviewing the CSV.

Usage
-----
    py scripts/audit_package_assignments.py
"""
from __future__ import annotations

import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ADMIN_API = 'https://api.wizardgrimoire.cloud/api/admin/run-sql'
ADMIN_KEY = '098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa'
HEADERS = {'User-Agent': 'curl/8.0.0'}

OUTPUT_DIR = Path(__file__).parent.parent / 'docs' / 'audits'


def run_sql(sql: str) -> list[dict]:
    r = requests.post(ADMIN_API, params={'key': ADMIN_KEY, 'sql': sql}, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        print(f'  SQL ERR {r.status_code}: {r.text[:200]}', file=sys.stderr)
        return []
    return r.json().get('result', [])


def recommendation(metrics: dict) -> tuple[str, str]:
    """
    Produce (recommended_package_name, rationale) for operator review.

    Heuristic — NOT authoritative:
      - Estimate monthly sends ≈ 30 × sends_24h
      - 50k_google fits if monthly < 75k AND active inbox count < 200
      - 100k_google fits if monthly >= 75k OR live count > 200
      - 'review_volume' if metrics are 0 (workspace dormant or paused)
      - 'review_oversized' if live count exceeds 100k_google target (300)
      - 'review_no_inboxes' if active = 0
    """
    active = metrics['active']
    live = metrics['live_count']
    sends_24h = metrics['sends_24h']
    monthly_proj = sends_24h * 30

    if metrics['package_name']:
        return ('keep_current', f"Already assigned to {metrics['package_name']}")

    if active == 0:
        return ('review_no_inboxes', 'Workspace has 0 active inboxes — no package needed yet')

    if sends_24h == 0 and live == 0:
        return ('review_volume', 'No live inboxes and no recent sends — dormant or never activated; needs operator context')

    if sends_24h == 0 and live > 0:
        return ('review_paused', f'Has {live} live inboxes but 0 sends in 24h — possibly paused or pre-launch')

    if live > 300:
        return ('review_oversized', f'live_count={live} exceeds 100k_google target (300) — investigate over-provisioning')

    if monthly_proj >= 75000 or live > 150:
        return ('100k_google', f'Projected monthly ~{monthly_proj}, live={live} — fits 100k_google (target_live=300)')

    if active > 0:
        return ('50k_google', f'Projected monthly ~{monthly_proj}, live={live} — fits 50k_google (target_live=150)')

    return ('review_unknown', 'Could not classify — needs operator review')


def main() -> int:
    print('Pulling package state per active workspace...\n')
    rows = run_sql("""
        SELECT w.id::text AS workspace_id, w.workspace_name,
               w.package_id::text AS package_id,
               w.target_live_count_override,
               w.pause_pool_transitions,
               p.name AS package_name,
               p.target_live_count AS pkg_target_live,
               p.target_reserve_count AS pkg_target_reserve,
               p.target_monthly_sends AS pkg_target_monthly,
               (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.workspace_id=w.id AND sa.is_active=TRUE) AS active,
               (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.workspace_id=w.id AND sa.is_active=TRUE AND sa.inventory_pool_status='live') AS live_count,
               (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.workspace_id=w.id AND sa.is_active=TRUE AND sa.inventory_pool_status='reserve') AS reserve_count,
               (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.workspace_id=w.id AND sa.is_active=TRUE AND sa.inventory_lifecycle_status='incubating') AS incubating_count,
               (SELECT COALESCE(SUM(sa.total_sends_24h),0) FROM sender_accounts sa WHERE sa.workspace_id=w.id AND sa.is_active=TRUE) AS sends_24h
        FROM workspaces w
        LEFT JOIN workspace_packages p ON p.id = w.package_id
        WHERE w.is_active = TRUE
        ORDER BY sends_24h DESC, w.workspace_name
    """)

    print(f"  {'WORKSPACE':<35} {'CURRENT PKG':<14} {'ACT':>4} {'LIVE':>4} {'RES':>4} {'INC':>4} "
          f"{'24H':>5} {'30D':>7} {'RECOMMEND':<22} {'WHY'}")
    print('  ' + '-' * 130)

    fleet_summary: list[dict] = []
    for r in rows:
        rec, why = recommendation(r)
        fleet_summary.append({**r, 'recommended_package': rec, 'rationale': why})
        cur = r['package_name'] or '(none)'
        active = r['active']
        live = r['live_count']
        res = r['reserve_count']
        incub = r['incubating_count']
        s24 = r['sends_24h']
        proj = s24 * 30
        print(f"  {r['workspace_name']:<35} {cur:<14} {active:>4} {live:>4} {res:>4} {incub:>4} "
              f"{s24:>5} {proj:>7} {rec:<22} {why[:60]}")

    # Write CSV for operator
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f'{today}-package-recommendations.csv'
    fieldnames = [
        'workspace_name', 'workspace_id', 'current_package',
        'active_inboxes', 'live_count', 'reserve_count', 'incubating_count',
        'sends_24h', 'projected_monthly_sends',
        'recommended_package', 'rationale',
        'pause_pool_transitions', 'target_live_count_override',
        'operator_decision', 'operator_notes',
    ]
    with out.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in fleet_summary:
            w.writerow({
                'workspace_name': r['workspace_name'],
                'workspace_id': r['workspace_id'],
                'current_package': r['package_name'] or '',
                'active_inboxes': r['active'],
                'live_count': r['live_count'],
                'reserve_count': r['reserve_count'],
                'incubating_count': r['incubating_count'],
                'sends_24h': r['sends_24h'],
                'projected_monthly_sends': r['sends_24h'] * 30,
                'recommended_package': r['recommended_package'],
                'rationale': r['rationale'],
                'pause_pool_transitions': r['pause_pool_transitions'],
                'target_live_count_override': r['target_live_count_override'] or '',
                'operator_decision': '',
                'operator_notes': '',
            })

    print(f"\n  CSV written to {out.relative_to(out.parents[2])}")

    # Quick stat summary
    counts: dict[str, int] = {}
    for r in fleet_summary:
        counts[r['recommended_package']] = counts.get(r['recommended_package'], 0) + 1
    print('\n  Recommendation distribution:')
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f'    {k:<22} {v}')

    print(
        '\nNext steps for operator:\n'
        '  1. Review CSV row-by-row, fill operator_decision column with the'
        ' approved package name (or `skip`).\n'
        '  2. For each row with operator_decision != current_package, run:\n'
        "     UPDATE workspaces SET package_id = (SELECT id FROM"
        " workspace_packages WHERE name = '<decision>'),\n"
        '            package_assigned_at = NOW(), updated_at = NOW()\n'
        "     WHERE id = '<workspace_id>';\n"
        '  3. Verify with: SELECT workspace_name, package_id FROM workspaces'
        ' WHERE is_active = TRUE;\n'
    )

    return 0


if __name__ == '__main__':
    sys.exit(main())
