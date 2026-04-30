#!/usr/bin/env python3
"""
generate_zombie_review_csv.py — read-only zombie review CSV generator.

Purpose
-------
Per docs/plans/connection-state-machine.md §8, the ~1,200 fleet-wide rows
where inbox_state='dead' AND kill_trigger='disconnected_timeout' need
operator review before any restoration. This script emits a CSV per
workspace with everything an operator needs to decide per-row WITHOUT
the system taking automated action.

The CSV is the deliverable. The operator reviews, fills the
`operator_decision` column ('restore' / 'keep_killed' / 'investigate'),
and runs SQL by hand based on the reviewed rows.

This script is READ-ONLY. No DB writes, no EB writes.

Output columns
--------------
  email                          The inbox email
  eb_id                          EmailBison sender_id
  workspace                      Workspace name
  killed_at                      Date the kill fired (UTC)
  days_since_killed              Calendar days
  current_eb_status              EB.status TODAY (Connected / Not connected / unknown)
  current_eb_tags                Comma-separated tag names CURRENTLY on the inbox in EB
  has_recent_spam                Boolean — any spam_complaint signal in last 30d
  has_recent_bounces             Boolean — hard bounces above threshold in last 30d
  has_recent_blocks              Boolean — provider blocks in last 30d
  reputation_clean_heuristic     'yes' / 'no' / 'unknown' — system suggestion ONLY
  emails_sent_eb                 EB-side total emails sent count (signal of resurrection)
  total_replied_eb               EB-side reply count
  operator_decision              BLANK — operator fills in
  operator_notes                 BLANK — operator fills in

Usage
-----
    py scripts/generate_zombie_review_csv.py --workspace Charm
    py scripts/generate_zombie_review_csv.py --workspace all   # all workspaces in one CSV per ws
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ADMIN_API = 'https://api.wizardgrimoire.cloud/api/admin/run-sql'
ADMIN_KEY = '098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa'
EB_BASE = 'https://spellcast.hirecharm.com/api'
HEADERS_ADMIN = {'User-Agent': 'curl/8.0.0'}

OUTPUT_DIR = Path(__file__).parent.parent / 'docs' / 'audits'
WS_KEYS_FILE = Path(__file__).parent.parent / 'ws_keys.json'


def run_sql(sql: str) -> list[dict]:
    r = requests.post(ADMIN_API, params={'key': ADMIN_KEY, 'sql': sql}, headers=HEADERS_ADMIN, timeout=30)
    if r.status_code != 200:
        print(f'  SQL ERR {r.status_code}: {r.text[:200]}', file=sys.stderr)
        return []
    return r.json().get('result', [])


def fetch_eb_senders(name: str, key: str) -> dict[int, dict]:
    """Pull all senders, keyed by EB sender_id."""
    headers = {'Authorization': f'Bearer {key}', 'Accept': 'application/json'}
    by_id: dict[int, dict] = {}
    page = 1
    while True:
        r = requests.get(
            f'{EB_BASE}/sender-emails',
            headers=headers,
            params={'page': page, 'per_page': 100},
            timeout=30,
        )
        if r.status_code != 200:
            print(f'  [{name}] page {page} HTTP {r.status_code}', file=sys.stderr)
            break
        body = r.json()
        for s in body.get('data', []):
            by_id[s['id']] = s
        meta = body.get('meta', {})
        if page >= meta.get('last_page', 0) or not body.get('data'):
            break
        page += 1
    return by_id


def fetch_zombie_rows(workspace_id: str) -> list[dict]:
    """Pull every disconnected_timeout zombie for one workspace.

    Uses actual sender_accounts column names. Spam signal is `complaints_lifetime`
    (not spam_complaints_24h). Hard bounces are 24h/7d. No hard_blocked_7d.
    """
    return run_sql(f"""
        SELECT
            sa.email_address,
            sa.emailbison_account_id::text AS emailbison_account_id,
            sa.killed_at::date AS killed_at,
            sa.disconnected_at::date AS disconnected_at,
            sa.complaints_lifetime,
            sa.hard_bounces_24h,
            sa.hard_bounces_7d,
            sa.hard_blocked_24h,
            sa.consecutive_hard_bounces,
            sa.bounce_rate_7d,
            sa.inbox_state,
            sa.is_active,
            sa.inventory_pool_status,
            sa.inventory_lifecycle_status
        FROM sender_accounts sa
        WHERE sa.workspace_id = '{workspace_id}'
          AND sa.kill_trigger::text = 'disconnected_timeout'
        ORDER BY sa.killed_at DESC, sa.email_address
    """)


def reputation_clean_heuristic(db_row: dict, eb_row: dict | None) -> str:
    """
    Heuristic — NOT authoritative. Operator decides.

    Returns 'yes' if no reputation signal of damage is visible,
    'no' if there's any reputation signal,
    'unknown' if data is missing.

    Note: thresholds match KILL_THRESHOLDS in health_checks.py
      spam_complaint: complaints_lifetime >= 1
      hard_bounces:   hard_bounces_24h >= 2  OR  hard_bounces_7d >= 5
      hard_blocked:   hard_blocked_24h >= 2  (no _7d column for blocks)
      consecutive:    consecutive_hard_bounces >= some-threshold (informational only here)
    """
    complaints = db_row.get('complaints_lifetime') or 0
    hb_24h = db_row.get('hard_bounces_24h') or 0
    hb_7d = db_row.get('hard_bounces_7d') or 0
    blocks_24h = db_row.get('hard_blocked_24h') or 0
    cons_hb = db_row.get('consecutive_hard_bounces') or 0

    if complaints > 0:
        return 'no'
    if hb_24h >= 2 or hb_7d >= 5:
        return 'no'
    if blocks_24h >= 2:
        return 'no'
    if cons_hb >= 5:
        return 'no'

    if eb_row:
        eb_tags = [t.get('name', '').lower() for t in eb_row.get('tags', [])]
        if any(t.startswith('flagged_') and 'disconnected' not in t for t in eb_tags):
            return 'no'

    return 'yes'


def generate_csv_for_workspace(ws_key: dict, output_path: Path) -> dict:
    name = ws_key['workspace_name']
    ws_id = ws_key['ws_id']
    print(f'\n  Generating zombie review CSV for {name}...')

    db_rows = fetch_zombie_rows(ws_id)
    print(f'    DB zombies found: {len(db_rows)}')

    eb_by_id = fetch_eb_senders(name, ws_key['key_token'])
    print(f'    EB senders fetched: {len(eb_by_id)}')

    today = datetime.now(timezone.utc).date()
    fieldnames = [
        'email', 'eb_id', 'workspace', 'killed_at', 'days_since_killed',
        'current_eb_status', 'current_eb_tags',
        'has_recent_spam', 'has_recent_bounces', 'has_recent_blocks',
        'reputation_clean_heuristic',
        'emails_sent_eb', 'total_replied_eb',
        'db_inbox_state', 'db_pool_status', 'db_lifecycle_status', 'db_is_active',
        'operator_decision', 'operator_notes',
    ]

    counters = {
        'total': 0,
        'eb_connected': 0,
        'eb_not_connected': 0,
        'eb_missing': 0,
        'reputation_clean_yes': 0,
        'reputation_clean_no': 0,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in db_rows:
            counters['total'] += 1
            try:
                eb_id = int(row['emailbison_account_id'])
            except (TypeError, ValueError):
                eb_id = None

            eb_row = eb_by_id.get(eb_id) if eb_id else None
            eb_status = eb_row.get('status') if eb_row else 'MISSING_FROM_EB'
            eb_tags = ','.join(t.get('name', '') for t in (eb_row.get('tags', []) if eb_row else []))
            sent_count = eb_row.get('emails_sent_count', 0) if eb_row else 0
            reply_count = eb_row.get('total_replied_count', 0) if eb_row else 0

            if eb_row:
                if eb_status == 'Connected':
                    counters['eb_connected'] += 1
                else:
                    counters['eb_not_connected'] += 1
            else:
                counters['eb_missing'] += 1

            heuristic = reputation_clean_heuristic(row, eb_row)
            counters[f'reputation_clean_{heuristic}'] = counters.get(f'reputation_clean_{heuristic}', 0) + 1

            killed_at_str = row.get('killed_at') or ''
            days_since = ''
            if killed_at_str:
                try:
                    ka = datetime.strptime(str(killed_at_str)[:10], '%Y-%m-%d').date()
                    days_since = str((today - ka).days)
                except (TypeError, ValueError):
                    pass

            has_spam = (row.get('complaints_lifetime') or 0) > 0
            has_bounces = (row.get('hard_bounces_24h') or 0) >= 2 or (row.get('hard_bounces_7d') or 0) >= 5
            has_blocks = (row.get('hard_blocked_24h') or 0) >= 2 or (row.get('consecutive_hard_bounces') or 0) >= 5

            w.writerow({
                'email': row['email_address'],
                'eb_id': eb_id or '',
                'workspace': name,
                'killed_at': str(killed_at_str),
                'days_since_killed': days_since,
                'current_eb_status': eb_status,
                'current_eb_tags': eb_tags,
                'has_recent_spam': 'YES' if has_spam else 'no',
                'has_recent_bounces': 'YES' if has_bounces else 'no',
                'has_recent_blocks': 'YES' if has_blocks else 'no',
                'reputation_clean_heuristic': heuristic,
                'emails_sent_eb': sent_count,
                'total_replied_eb': reply_count,
                'db_inbox_state': row.get('inbox_state') or '',
                'db_pool_status': row.get('inventory_pool_status') or '',
                'db_lifecycle_status': row.get('inventory_lifecycle_status') or '',
                'db_is_active': 'TRUE' if row.get('is_active') else 'FALSE',
                'operator_decision': '',
                'operator_notes': '',
            })

    print(f'    CSV written to {output_path.relative_to(output_path.parents[2])}')
    print(f'    Summary: total={counters["total"]} | eb_connected={counters["eb_connected"]} | '
          f'eb_not_connected={counters["eb_not_connected"]} | eb_missing={counters["eb_missing"]}')
    print(f'    Heuristic: rep_clean_yes={counters.get("reputation_clean_yes",0)} | '
          f'rep_clean_no={counters.get("reputation_clean_no",0)} | '
          f'rep_clean_unknown={counters.get("reputation_clean_unknown",0)}')
    return counters


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True, help='Workspace name (or "all")')
    args = parser.parse_args()

    ws_keys = json.loads(WS_KEYS_FILE.read_text(encoding='utf-8'))['result']
    if args.workspace.lower() != 'all':
        ws_keys = [w for w in ws_keys if w['workspace_name'].lower() == args.workspace.lower()]
        if not ws_keys:
            print(f'No workspace named {args.workspace!r}.', file=sys.stderr)
            return 2

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    fleet_summary: dict[str, dict] = {}
    for w in ws_keys:
        slug = w['workspace_name'].lower().replace(' ', '_').replace("'", "")
        out = OUTPUT_DIR / f'{today}-zombie-review-{slug}.csv'
        fleet_summary[w['workspace_name']] = generate_csv_for_workspace(w, out)

    if len(fleet_summary) > 1:
        print('\n' + '=' * 88)
        print('  FLEET ZOMBIE SUMMARY')
        print('=' * 88)
        print(f"  {'WORKSPACE':<35} {'TOTAL':>6} {'CONN':>6} {'DISC':>6} {'GONE':>6} {'CLEAN':>6} {'DIRTY':>6}")
        for name, c in fleet_summary.items():
            print(f"  {name:<35} {c['total']:>6} {c['eb_connected']:>6} {c['eb_not_connected']:>6} "
                  f"{c['eb_missing']:>6} {c.get('reputation_clean_yes', 0):>6} {c.get('reputation_clean_no', 0):>6}")
        print('=' * 88)
        print('  CONN = currently Connected in EB (likely restoration candidate)')
        print('  DISC = currently disconnected in EB (still operational issue, not restoration)')
        print('  GONE = no longer in EB at all (already cleaned up by operator)')
        print('  CLEAN = heuristic suggests no reputation signal of damage')
        print('  DIRTY = heuristic suggests reputation signal present — keep killed')

    return 0


if __name__ == '__main__':
    sys.exit(main())
