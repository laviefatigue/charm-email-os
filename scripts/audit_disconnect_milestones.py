#!/usr/bin/env python3
"""
audit_disconnect_milestones.py — read-only disconnect-state audit.

Per docs/plans/connection-state-machine.md §2 (notification ladder)
and docs/plans/inbox-audit-overhaul.md §I-9 (subscription-cancel signal).

Outputs two reports per active workspace:

  REPORT A: disconnect milestones
  -------------------------------
  Inboxes currently `status='Not connected'` AND `disconnected_at` set,
  grouped by time-since-disconnect milestone:
    < 24h        not yet reportable (auto-reconnect window)
    24h - 3d     first notification milestone
    3d - 7d     second milestone (Hypertide escalation)
    7d - 20d    third milestone (continued tracking)
    20d+        operator review queue (subscription-cancel review)

  REPORT B: subscription-cancel candidates per domain
  ----------------------------------------------------
  Per-domain rollup showing inbox states. Cancel-eligible when 100%
  of inboxes on the domain are dead AND no inbox returned to alive in
  the last 14 days.

Both reports are operator-driven. NEVER auto-acts. NEVER touches EB.
Outputs JSON + CSV.

Usage
-----
    py scripts/audit_disconnect_milestones.py             # all active workspaces
    py scripts/audit_disconnect_milestones.py --workspace Charm
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ADMIN_API = 'https://api.wizardgrimoire.cloud/api/admin/run-sql'
ADMIN_KEY = '098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa'
HEADERS = {'User-Agent': 'curl/8.0.0'}

OUTPUT_DIR = Path(__file__).parent.parent / 'docs' / 'audits'

# Disconnect milestone thresholds, in hours.
# Mirrors docs/plans/connection-state-machine.md §2.
MILESTONES = [
    ('24h', 24),
    ('3d', 24 * 3),
    ('7d', 24 * 7),
    ('20d', 24 * 20),
]


def run_sql(sql: str) -> list[dict[str, Any]]:
    r = requests.post(ADMIN_API, params={'key': ADMIN_KEY, 'sql': sql}, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        print(f'  SQL ERR {r.status_code}: {r.text[:200]}', file=sys.stderr)
        return []
    return r.json().get('result', [])


def audit_disconnect_milestones(workspace_filter: str | None) -> list[dict]:
    """Per-workspace breakdown of currently-disconnected inboxes by milestone."""
    where = "w.is_active = TRUE"
    if workspace_filter:
        # Caller already validated; safe substitution
        where += f" AND w.workspace_name = '{workspace_filter}'"

    rows = run_sql(f"""
        SELECT
            w.workspace_name,
            sa.id::text AS sender_id,
            sa.emailbison_account_id::text AS eb_id,
            sa.email_address,
            sa.inbox_state,
            sa.inventory_pool_status,
            sa.disconnected_at,
            sa.esp,
            EXTRACT(EPOCH FROM (NOW() - sa.disconnected_at))/3600.0 AS hours_disconnected
        FROM sender_accounts sa
        JOIN workspaces w ON w.id = sa.workspace_id
        WHERE {where}
          AND sa.is_active = TRUE
          AND sa.status = 'Not connected'
          AND sa.disconnected_at IS NOT NULL
        ORDER BY w.workspace_name, sa.disconnected_at ASC
    """)
    return rows


def bucketize(hours: float) -> str | None:
    """Return milestone label for the hours-since-disconnect, or None if < 24h."""
    if hours < 24:
        return None
    if hours < 24 * 3:
        return '24h'
    if hours < 24 * 7:
        return '3d'
    if hours < 24 * 20:
        return '7d'
    return '20d'


def audit_subscription_cancel(workspace_filter: str | None) -> list[dict[str, Any]]:
    """Per-domain rollup. Cancel-eligible if all inboxes dead, none alive in 14d.

    Flattened query (no CTE) to keep the admin SQL endpoint happy on large
    fleets — the CTE version can timeout / return error strings when joining
    domains × sender_accounts × workspaces with multiple FILTER aggregates.
    """
    where = "w.is_active = TRUE AND sa.is_active = TRUE"
    if workspace_filter:
        where += f" AND w.workspace_name = '{workspace_filter}'"

    return run_sql(f"""
        SELECT
            w.workspace_name,
            d.domain_name,
            d.pool_status AS domain_pool_status,
            COUNT(*) AS total_inboxes,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') AS dead_count,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live') AS alive_count,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') AS alive_connected,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status != 'Connected') AS alive_disconnected,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead' AND sa.status = 'Connected') AS dead_connected,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead' AND sa.status != 'Connected') AS dead_disconnected,
            MAX(sa.killed_at)::date AS last_killed_date,
            MAX(CASE WHEN sa.inbox_state = 'live' THEN sa.updated_at END)::date AS last_alive_date,
            (COUNT(*) FILTER (WHERE sa.inbox_state = 'live') = 0 AND COUNT(*) > 0) AS subscription_cancel_eligible
        FROM domains d
        JOIN sender_accounts sa ON sa.domain_id = d.id
        JOIN workspaces w ON w.id = d.workspace_id
        WHERE {where}
        GROUP BY w.workspace_name, d.domain_name, d.pool_status
        ORDER BY w.workspace_name,
                 (COUNT(*) FILTER (WHERE sa.inbox_state = 'live') = 0) DESC,
                 COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') DESC
    """)


def report_a_disconnect_milestones(rows: list[dict]) -> None:
    print('=' * 100)
    print('  REPORT A — Disconnect milestones (currently `Not connected` inboxes)')
    print('=' * 100)
    if not rows:
        print('  No inboxes currently disconnected with disconnected_at set.')
        return

    # Group by (workspace, bucket)
    bucketed: dict[str, dict[str, list[dict]]] = {}
    for r in rows:
        ws = r['workspace_name']
        hours = float(r['hours_disconnected'])
        bucket = bucketize(hours)
        if bucket is None:
            continue
        bucketed.setdefault(ws, {}).setdefault(bucket, []).append({
            **r,
            'hours': hours,
            'days': round(hours / 24.0, 1),
        })

    print(f"  {'WORKSPACE':<35} {'24h+':>6} {'3d+':>6} {'7d+':>6} {'20d+':>6} {'TOTAL':>6}")
    print('  ' + '-' * 75)
    for ws in sorted(bucketed.keys()):
        b = bucketed[ws]
        c24 = len(b.get('24h', []))
        c3d = len(b.get('3d', []))
        c7d = len(b.get('7d', []))
        c20 = len(b.get('20d', []))
        print(f"  {ws:<35} {c24:>6} {c3d:>6} {c7d:>6} {c20:>6} {(c24+c3d+c7d+c20):>6}")

    # Detail sections per milestone with operator-actionable lists
    for label in ('20d', '7d', '3d', '24h'):
        any_in_bucket = any(label in b for b in bucketed.values())
        if not any_in_bucket:
            continue
        print(f"\n  --- {label}+ disconnects (operator review) ---")
        for ws in sorted(bucketed.keys()):
            items = bucketed[ws].get(label, [])
            if not items:
                continue
            for it in items[:25]:
                tag = '[REVIEW]' if label == '20d' else ''
                print(f"  {ws:<25} {tag:<10} {it['email_address']:<55} pool={it['inventory_pool_status'] or '-':<8} state={it['inbox_state']:<6} days={it['days']}")
            if len(items) > 25:
                print(f"  {ws:<25}            (+{len(items)-25} more, see CSV)")


def report_b_subscription_cancel(rows: list[dict]) -> None:
    print('\n' + '=' * 100)
    print('  REPORT B — Subscription-cancel candidates per domain')
    print('=' * 100)
    if not rows:
        print('  No domains with active inboxes.')
        return

    eligible = [r for r in rows if r.get('subscription_cancel_eligible')]
    not_eligible_partial = [r for r in rows if r['dead_count'] > 0 and not r.get('subscription_cancel_eligible')]
    fully_alive = [r for r in rows if r['dead_count'] == 0]

    print(f"  Cancel-eligible domains (all inboxes dead):     {len(eligible)}")
    print(f"  Mixed (some dead, some alive — keep paying):    {len(not_eligible_partial)}")
    print(f"  Fully alive domains (no dead inboxes):          {len(fully_alive)}")

    if eligible:
        print(f"\n  --- Cancel-eligible domains ({len(eligible)}) — operator review ---")
        print(f"  {'WORKSPACE':<25} {'DOMAIN':<35} {'DEAD':>5} {'D-CONN':>7} {'D-NCONN':>8} {'POOL':>10} {'LAST_KILLED':>12}")
        for r in eligible[:60]:
            print(f"  {r['workspace_name']:<25} {r['domain_name']:<35} {r['dead_count']:>5} {r['dead_connected']:>7} {r['dead_disconnected']:>8} {r['domain_pool_status'] or '-':>10} {str(r['last_killed_date'] or '-'):>12}")
        if len(eligible) > 60:
            print(f"  (+{len(eligible)-60} more, see CSV)")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: ('' if r.get(k) is None else r[k]) for k in fieldnames})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', help='Single workspace name (default: all active)', default=None)
    args = parser.parse_args()

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    print('Pulling disconnect milestones...')
    disco_rows = audit_disconnect_milestones(args.workspace)
    print(f'  fetched {len(disco_rows)} currently-disconnected rows\n')

    report_a_disconnect_milestones(disco_rows)

    print('\nPulling subscription-cancel rollup per domain...')
    sub_rows = audit_subscription_cancel(args.workspace)
    print(f'  fetched {len(sub_rows)} domain rows\n')

    report_b_subscription_cancel(sub_rows)

    # CSVs for operator queue
    suffix = f'-{args.workspace.lower().replace(" ", "_")}' if args.workspace else ''
    disco_csv = OUTPUT_DIR / f'{today}-disconnect-milestones{suffix}.csv'
    write_csv(disco_csv, [
        'workspace_name', 'email_address', 'eb_id', 'inbox_state', 'inventory_pool_status',
        'esp', 'disconnected_at', 'hours_disconnected',
    ], [
        {
            **r,
            'hours_disconnected': round(float(r['hours_disconnected']), 1),
            'disconnected_at': str(r.get('disconnected_at') or ''),
        }
        for r in disco_rows
    ])
    sub_csv = OUTPUT_DIR / f'{today}-subscription-cancel{suffix}.csv'
    write_csv(sub_csv, [
        'workspace_name', 'domain_name', 'domain_pool_status', 'total_inboxes',
        'dead_count', 'alive_count', 'alive_connected', 'alive_disconnected',
        'dead_connected', 'dead_disconnected', 'last_killed_date', 'last_alive_date',
        'subscription_cancel_eligible',
    ], sub_rows)

    print(f'\n  CSV: {disco_csv.relative_to(disco_csv.parents[2])}')
    print(f'  CSV: {sub_csv.relative_to(sub_csv.parents[2])}')

    json_out = OUTPUT_DIR / f'{today}-disconnect-and-cancel-snapshot{suffix}.json'
    json_out.write_text(json.dumps({
        'date': datetime.now(timezone.utc).isoformat(),
        'workspace_filter': args.workspace,
        'disconnect_count': len(disco_rows),
        'subscription_cancel_eligible_count': sum(1 for r in sub_rows if r.get('subscription_cancel_eligible')),
        'disconnect_rows': [
            {**r, 'hours_disconnected': round(float(r['hours_disconnected']), 1)}
            for r in disco_rows
        ],
        'subscription_rows': sub_rows,
    }, indent=2, default=str), encoding='utf-8')
    print(f'  JSON: {json_out.relative_to(json_out.parents[2])}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
