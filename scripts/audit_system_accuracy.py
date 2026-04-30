#!/usr/bin/env python3
"""
audit_system_accuracy.py — read-only accuracy audit for the Charm email-OS state.

Purpose
-------
Per the 2026-04-30 connection-state-machine plan, automated actions on inbox
state must be gated on proven accuracy of the underlying data. This script
measures four accuracy dimensions, per active workspace:

  1. Connection-status mirror      — EB.status vs DB.status
  2. Disconnect timestamp presence — EB shows disconnected vs DB.disconnected_at
  3. Membership consistency        — sender exists in both EB and DB
  4. Pool-tag mirror               — DB.inventory_pool_status vs EB tag set

Output
------
JSON written to docs/audits/2026-04-30-system-accuracy-snapshot.json with
per-workspace counters and per-row mismatches (sample-capped).

Human-readable summary printed to stdout.

This script is READ-ONLY. No DB writes, no EB writes.

Usage
-----
    py scripts/audit_system_accuracy.py [--workspace <name>]

Run with no args for full fleet audit (~2-3 min, paginated EB calls).
Run with --workspace <name> for single-workspace audit (~10 sec).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Production endpoints (read-only access via admin SQL + workspace API keys).
ADMIN_API = 'https://api.wizardgrimoire.cloud/api/admin/run-sql'
ADMIN_KEY = '098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa'
EB_BASE = 'https://spellcast.hirecharm.com/api'
HEADERS_ADMIN = {'User-Agent': 'curl/8.0.0'}

OUTPUT_DIR = Path(__file__).parent.parent / 'docs' / 'audits'
SNAPSHOT_FILE = OUTPUT_DIR / '2026-04-30-system-accuracy-snapshot.json'
WS_KEYS_FILE = Path(__file__).parent.parent / 'ws_keys.json'

# Acceptance thresholds — accuracy gates per the connection-state plan.
ACCEPTANCE = {
    'connection_status_match_pct': 99.0,
    'disconnect_timestamp_match_pct': 95.0,
    'membership_match_pct': 98.0,
    'pool_tag_drift_pct_max': 1.0,  # i.e. drift count ≤ 1% of pool members
}


def run_sql(sql: str) -> list[dict]:
    r = requests.post(ADMIN_API, params={'key': ADMIN_KEY, 'sql': sql}, headers=HEADERS_ADMIN, timeout=30)
    if r.status_code != 200:
        print(f'  SQL ERR {r.status_code}: {r.text[:200]}', file=sys.stderr)
        return []
    return r.json().get('result', [])


def fetch_eb_senders(name: str, key: str) -> list[dict]:
    """Pull all senders from a workspace via its scoped Sanctum token."""
    headers = {'Authorization': f'Bearer {key}', 'Accept': 'application/json'}
    senders: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f'{EB_BASE}/sender-emails',
            headers=headers,
            params={'page': page, 'per_page': 100},
            timeout=30,
        )
        if r.status_code != 200:
            print(f'  [{name}] EB page {page} HTTP {r.status_code}', file=sys.stderr)
            break
        body = r.json()
        senders.extend(body.get('data', []))
        meta = body.get('meta', {})
        if page >= meta.get('last_page', 0) or not body.get('data'):
            break
        page += 1
    return senders


def normalize_status(s: str | None) -> str:
    """EB returns 'Connected' / 'Not connected'. DB returns same. Normalize for comparison."""
    if not s:
        return 'unknown'
    return s.strip().lower().replace(' ', '_')


def audit_workspace(ws: dict) -> dict:
    name = ws['workspace_name']
    ws_id = ws['ws_id']
    eb_id = ws['eb_id']
    key = ws['key_token']

    print(f'\n  Auditing {name}...')

    # 1. Pull EB senders.
    eb_senders = fetch_eb_senders(name, key)
    eb_by_id: dict[int, dict] = {s['id']: s for s in eb_senders}
    eb_count = len(eb_senders)

    # 2. Pull DB sender_accounts for this workspace.
    db_rows = run_sql(f"""
        SELECT
            id::text AS db_id,
            emailbison_account_id::text AS eb_id,
            email_address,
            is_active,
            inbox_state,
            status AS conn_status,
            disconnected_at::text AS disconnected_at,
            inventory_pool_status,
            inventory_lifecycle_status,
            kill_trigger
        FROM sender_accounts
        WHERE workspace_id = '{ws_id}'
    """)
    db_by_eb_id: dict[int, dict] = {}
    for r in db_rows:
        try:
            db_by_eb_id[int(r['eb_id'])] = r
        except (TypeError, ValueError):
            continue
    db_count = len(db_rows)
    db_active_count = sum(1 for r in db_rows if r.get('is_active'))

    # 3. Membership accuracy.
    eb_only = set(eb_by_id) - set(db_by_eb_id)
    db_only = set(db_by_eb_id) - set(eb_by_id)
    in_both = set(eb_by_id) & set(db_by_eb_id)

    # 4. Connection-status mirror — only for senders in both.
    status_match = 0
    status_mismatch_samples = []
    for eb_sid in in_both:
        eb_status = normalize_status(eb_by_id[eb_sid].get('status'))
        db_status = normalize_status(db_by_eb_id[eb_sid].get('conn_status'))
        if eb_status == db_status:
            status_match += 1
        elif len(status_mismatch_samples) < 20:
            status_mismatch_samples.append({
                'eb_id': eb_sid,
                'email': eb_by_id[eb_sid].get('email'),
                'eb_status': eb_status,
                'db_status': db_status,
            })
    status_match_pct = (status_match / len(in_both) * 100) if in_both else 0.0

    # 5. Disconnect-timestamp accuracy — for senders that EB reports as Not connected.
    # Acceptance: if EB says disconnected, DB should have disconnected_at populated.
    eb_disconnected_ids = {sid for sid in in_both if normalize_status(eb_by_id[sid].get('status')) == 'not_connected'}
    db_has_timestamp = sum(
        1 for sid in eb_disconnected_ids
        if db_by_eb_id[sid].get('disconnected_at')
    )
    timestamp_match_pct = (db_has_timestamp / len(eb_disconnected_ids) * 100) if eb_disconnected_ids else 100.0

    # 6. Pool-tag mirror — DB.inventory_pool_status vs EB tags.
    pool_tag_match = 0
    pool_tag_drift = 0
    pool_drift_samples = []
    for eb_sid in in_both:
        db_pool = db_by_eb_id[eb_sid].get('inventory_pool_status')
        eb_tags = [t.get('name', '').lower() for t in eb_by_id[eb_sid].get('tags', [])]
        eb_pool = None
        for pool_name in ('live', 'reserve', 'incubating'):
            if pool_name in eb_tags:
                eb_pool = pool_name
                break
        # Compare. None vs None is fine. 'live' vs 'live' fine. Any difference = drift.
        # Note: 'incubating' is lifecycle, not pool — so DB pool=NULL + EB incubating tag is OK.
        db_lifecycle = db_by_eb_id[eb_sid].get('inventory_lifecycle_status')
        if eb_pool == 'incubating':
            # OK if DB lifecycle is incubating
            if db_lifecycle == 'incubating' and not db_pool:
                pool_tag_match += 1
                continue
        if eb_pool == db_pool:
            pool_tag_match += 1
        else:
            pool_tag_drift += 1
            if len(pool_drift_samples) < 20:
                pool_drift_samples.append({
                    'eb_id': eb_sid,
                    'email': eb_by_id[eb_sid].get('email'),
                    'db_pool': db_pool,
                    'db_lifecycle': db_lifecycle,
                    'eb_pool': eb_pool,
                    'eb_tags': eb_tags,
                })
    pool_tag_drift_pct = (pool_tag_drift / len(in_both) * 100) if in_both else 0.0

    return {
        'workspace_name': name,
        'eb_count': eb_count,
        'db_count': db_count,
        'db_active_count': db_active_count,
        'in_both': len(in_both),
        'eb_only_count': len(eb_only),
        'db_only_count': len(db_only),
        'eb_only_sample': sorted(eb_only)[:10],
        'db_only_sample': [
            {
                'eb_id': sid,
                'email': db_by_eb_id[sid].get('email_address'),
                'is_active': db_by_eb_id[sid].get('is_active'),
                'inbox_state': db_by_eb_id[sid].get('inbox_state'),
            }
            for sid in sorted(db_only)[:10]
        ],
        'connection_status_match_pct': round(status_match_pct, 1),
        'connection_status_mismatch_count': len(in_both) - status_match,
        'connection_status_mismatch_samples': status_mismatch_samples,
        'eb_disconnected_count': len(eb_disconnected_ids),
        'db_has_disconnect_timestamp_count': db_has_timestamp,
        'disconnect_timestamp_match_pct': round(timestamp_match_pct, 1),
        'pool_tag_match_count': pool_tag_match,
        'pool_tag_drift_count': pool_tag_drift,
        'pool_tag_drift_pct': round(pool_tag_drift_pct, 1),
        'pool_tag_drift_samples': pool_drift_samples,
    }


def gates_pass(audit: dict) -> tuple[bool, list[str]]:
    """Return (all_pass, failures) — failures lists any gate that didn't meet threshold."""
    failures: list[str] = []
    if audit['connection_status_match_pct'] < ACCEPTANCE['connection_status_match_pct']:
        failures.append(
            f"connection_status_match {audit['connection_status_match_pct']}% < {ACCEPTANCE['connection_status_match_pct']}%"
        )
    if audit['eb_disconnected_count'] > 0 and audit['disconnect_timestamp_match_pct'] < ACCEPTANCE['disconnect_timestamp_match_pct']:
        failures.append(
            f"disconnect_timestamp_match {audit['disconnect_timestamp_match_pct']}% < {ACCEPTANCE['disconnect_timestamp_match_pct']}%"
        )
    if audit['in_both'] > 0:
        membership_pct = audit['in_both'] / max(audit['eb_count'], audit['db_active_count']) * 100
        if membership_pct < ACCEPTANCE['membership_match_pct']:
            failures.append(f"membership_match {membership_pct:.1f}% < {ACCEPTANCE['membership_match_pct']}%")
    if audit['pool_tag_drift_pct'] > ACCEPTANCE['pool_tag_drift_pct_max']:
        failures.append(
            f"pool_tag_drift {audit['pool_tag_drift_pct']}% > {ACCEPTANCE['pool_tag_drift_pct_max']}%"
        )
    return (len(failures) == 0, failures)


def print_summary(audits: list[dict]) -> None:
    print('\n' + '=' * 90)
    print('  ACCURACY AUDIT SUMMARY — 2026-04-30')
    print('=' * 90)
    print(f"  {'WORKSPACE':<35} {'CONN%':>7} {'DISC%':>7} {'POOL DRIFT':>12} {'ORPHANS':>10} {'PASS'}")
    print('  ' + '-' * 88)
    for a in audits:
        passed, failures = gates_pass(a)
        flag = '  ✓  ' if passed else ' FAIL'
        orphans = f"{a['eb_only_count']}/{a['db_only_count']}"
        print(
            f"  {a['workspace_name']:<35} "
            f"{a['connection_status_match_pct']:>7.1f} "
            f"{a['disconnect_timestamp_match_pct']:>7.1f} "
            f"{a['pool_tag_drift_count']:>4} ({a['pool_tag_drift_pct']:>3.1f}%)"
            f" {orphans:>10} "
            f"{flag}"
        )
        if not passed:
            for f in failures:
                print(f"      — {f}")
    print('  ' + '-' * 88)
    print('  Legend: CONN% = connection-status mirror, DISC% = disconnect-timestamp coverage,')
    print('          POOL DRIFT = pool-tag mismatch count, ORPHANS = EB-only / DB-only ids')
    print('  Gates:  CONN ≥99%, DISC ≥95% (when applicable), POOL DRIFT ≤1%, MEMBERSHIP ≥98%')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', help='Audit single workspace by name', default=None)
    args = parser.parse_args()

    print('Loading workspace API keys...')
    ws_keys = json.loads(WS_KEYS_FILE.read_text(encoding='utf-8'))['result']

    if args.workspace:
        ws_keys = [w for w in ws_keys if w['workspace_name'].lower() == args.workspace.lower()]
        if not ws_keys:
            print(f'No workspace named {args.workspace!r} found.', file=sys.stderr)
            return 2

    audits: list[dict] = []
    for ws in ws_keys:
        audits.append(audit_workspace(ws))

    print_summary(audits)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {
        'audit_date': datetime.now(timezone.utc).isoformat(),
        'acceptance_thresholds': ACCEPTANCE,
        'workspaces': audits,
    }
    SNAPSHOT_FILE.write_text(json.dumps(snapshot, indent=2, default=str), encoding='utf-8')
    print(f'\n  Snapshot saved to {SNAPSHOT_FILE.relative_to(SNAPSHOT_FILE.parents[2])}')

    # Exit code: 0 if all pass, 1 if any fail. Useful for CI gating later.
    any_fail = any(not gates_pass(a)[0] for a in audits)
    return 1 if any_fail else 0


if __name__ == '__main__':
    sys.exit(main())
