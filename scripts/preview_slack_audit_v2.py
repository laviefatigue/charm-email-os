#!/usr/bin/env python3
"""
preview_slack_audit_v2.py — Render the daily inbox-audit Slack message
locally against PRODUCTION data, optionally post it.

Two modes:
  1. PREVIEW (default)  — pull real data via the admin run-sql endpoint,
                          build the Block Kit payload, print human-readable
                          summary + raw JSON.
  2. APPLY (--post)     — also POST to SLACK_AUDIT_WEBHOOK_URL so we can
                          verify it renders the same in #inbox-audit.

The data queries here MUST mirror sync_modules/slack_audit_v2.py exactly,
otherwise the preview is misleading. If you change those queries in
slack_audit_v2.py, change them here too.

Usage
─────
    py scripts/preview_slack_audit_v2.py                # preview only
    py scripts/preview_slack_audit_v2.py --post         # post to Slack
    py scripts/preview_slack_audit_v2.py --post --webhook https://...
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# Ensure UTF-8 stdout on Windows.
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Make sync_modules importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from sync_modules.slack_audit_v2 import build_message  # noqa: E402

ADMIN_API = 'https://api.wizardgrimoire.cloud/api/admin/run-sql'
ADMIN_KEY = '098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa'

# These two SQL strings are deliberately copy-pasted from
# sync_modules/slack_audit_v2.py. Drift = preview lies.
SQL_PER_WORKSPACE = """
    SELECT
        w.workspace_name,
        COUNT(*) FILTER (
            WHERE sa.status IS DISTINCT FROM 'Connected'
              AND sa.inbox_state = 'live'
              AND sa.emailbison_account_id IS NOT NULL
              AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
              AND ((sa.esp = 'microsoft'
                    AND sa.disconnected_at IS NOT NULL
                    AND sa.disconnected_at < NOW() - INTERVAL '48 hours')
                   OR (COALESCE(sa.esp, 'other') != 'microsoft'
                       AND sa.disconnected_at IS NOT NULL
                       AND sa.disconnected_at < NOW() - INTERVAL '24 hours'))
        ) AS disconnects,
        COUNT(*) FILTER (
            WHERE sa.kill_trigger IS NOT NULL
              AND sa.inbox_state = 'dead'
              AND sa.is_active = TRUE
              AND sa.emailbison_account_id IS NOT NULL
              AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
        ) AS total_kills,
        COUNT(*) FILTER (
            WHERE sa.is_quarantined = TRUE AND sa.is_active = TRUE
        ) AS quarantined,
        COUNT(*) FILTER (
            WHERE sa.inventory_lifecycle_status = 'incubating'
              AND sa.is_active = TRUE
              AND COALESCE(sa.warmup_started_at, sa.created_at) < NOW() - INTERVAL '14 days'
        ) AS stuck_incubation
    FROM workspaces w
    LEFT JOIN sender_accounts sa ON sa.workspace_id = w.id
    LEFT JOIN domains d ON sa.domain_id = d.id
    WHERE w.is_active = TRUE
    GROUP BY w.id, w.workspace_name
    HAVING COUNT(sa.id) > 0
    ORDER BY w.workspace_name
"""

SQL_ROTATION_DOMAINS = """
    SELECT COUNT(*) AS c FROM (
        SELECT d.id
        FROM domains d
        JOIN sender_accounts sa ON sa.domain_id = d.id
        JOIN workspaces w ON d.workspace_id = w.id
        WHERE w.is_active = TRUE AND d.pool_status != 'cancelled'
        GROUP BY d.id
        HAVING COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') > 0
            OR COUNT(*) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block_%') > 0
            OR COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') = COUNT(*)
            OR (COUNT(*) >= 5 AND 100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / COUNT(*) >= 80)
    ) x
"""

# The actual production query uses CTE + jsonb_path_query, which chokes the
# admin run-sql endpoint. For the preview only, fetch latest-per-workspace
# audit rows and sum I-9 eligible_count in Python.
SQL_LATEST_AUDITS_PER_WORKSPACE = """
    SELECT workspace_id, audit_data
    FROM inbox_audits
    WHERE workspace_id IS NOT NULL AND audit_data IS NOT NULL
      AND audit_date = (
          SELECT MAX(audit_date) FROM inbox_audits ia2
          WHERE ia2.workspace_id = inbox_audits.workspace_id
            AND ia2.audit_data IS NOT NULL
      )
"""


def run_sql(sql: str) -> list[dict]:
    r = requests.post(
        ADMIN_API,
        params={'key': ADMIN_KEY, 'sql': sql},
        headers={'User-Agent': 'curl/8.0.0'},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if isinstance(body, dict) and isinstance(body.get('result'), list):
        return body['result']
    if isinstance(body, dict) and 'detail' in body:
        raise RuntimeError(f'admin API error: {body["detail"]}')
    raise RuntimeError(f'unexpected admin API response: {body!r}')


def render_human_preview(message: dict, ws_stats: list, domain_summary: dict) -> str:
    """Render an ASCII approximation of how the Slack message will look."""
    lines = []
    lines.append('=' * 78)
    lines.append('SLACK MESSAGE PREVIEW (rendered locally from prod data)')
    lines.append('=' * 78)
    lines.append('')
    today = datetime.now(timezone.utc).strftime('%B %d, %Y')
    lines.append(f'  Daily Inbox Audit — {today}')
    lines.append('  ' + '-' * 60)
    lines.append('')
    lines.append('  By workspace  (cumulative — disc / kills / quarantined / stuck):')
    lines.append('')
    for w in ws_stats:
        bits = []
        if w['disconnects']: bits.append(f"{w['disconnects']} disc")
        if w['total_kills']: bits.append(f"{w['total_kills']} kills")
        if w['quarantined']: bits.append(f"{w['quarantined']} quar")
        if w['stuck_incubation']: bits.append(f"{w['stuck_incubation']} stuck")
        bits_str = ', '.join(bits) if bits else '(clean)'
        lines.append(f'    {w["workspace_name"]:<35} {bits_str}')
    lines.append('')
    lines.append('  ' + '-' * 60)
    lines.append('  Domain-level signals:')
    lines.append(f'    {domain_summary["rotation"]} domains flagged for rotation')
    lines.append(f'    {domain_summary["cancel_eligible"]} domains eligible to cancel')
    lines.append('')
    lines.append('  ' + '-' * 60)
    lines.append('  Buttons (download CSV directly from API):')
    actions_block = next((b for b in message['blocks'] if b.get('type') == 'actions'), None)
    if actions_block:
        for elem in actions_block.get('elements', []):
            label = elem.get('text', {}).get('text', '?')
            url = elem.get('url', '(no URL — PUBLIC_API_URL unset)')
            lines.append(f'    [{label}]  ->  {url}')
    lines.append('')
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='Preview daily Slack audit v2.')
    parser.add_argument('--post', action='store_true',
                        help='POST to SLACK_AUDIT_WEBHOOK_URL after preview.')
    parser.add_argument('--webhook',
                        help='Override SLACK_AUDIT_WEBHOOK_URL (otherwise from env).')
    parser.add_argument('--public-api-url',
                        help='Override PUBLIC_API_URL for button URLs.')
    parser.add_argument('--save-json',
                        help='Path to save the full Block Kit JSON.')
    args = parser.parse_args()

    # Allow --public-api-url to override env var BEFORE importing build_message.
    if args.public_api_url:
        os.environ['PUBLIC_API_URL'] = args.public_api_url
        import importlib, sync_modules.slack_audit_v2 as sav2
        importlib.reload(sav2)
        global build_message  # noqa: PLW0603
        build_message = sav2.build_message

    print('Pulling per-workspace stats from prod...')
    ws_stats = run_sql(SQL_PER_WORKSPACE)
    print(f'  {len(ws_stats)} active workspaces')

    print('Pulling domain rollup...')
    rotation = run_sql(SQL_ROTATION_DOMAINS)

    # Sum I-9 eligible_count across the latest audit per workspace (Python-side
    # because the admin endpoint can't handle the production CTE shape).
    audits = run_sql(SQL_LATEST_AUDITS_PER_WORKSPACE)
    cancel_eligible = 0
    for row in audits:
        ad = row.get('audit_data')
        if isinstance(ad, str):
            ad = json.loads(ad)
        if not ad:
            continue
        for section in ad.get('sections', []) or []:
            if section.get('code') == 'I-9':
                cancel_eligible += int(section.get('details', {}).get('eligible_count') or 0)
                break
    domain_summary = {
        'rotation': int(rotation[0]['c'] if rotation else 0),
        'cancel_eligible': cancel_eligible,
    }
    print(f'  {domain_summary["rotation"]} rotation, {domain_summary["cancel_eligible"]} cancel-eligible')
    print()

    message = build_message(ws_stats, domain_summary)

    print(render_human_preview(message, ws_stats, domain_summary))

    if args.save_json:
        Path(args.save_json).write_text(json.dumps(message, indent=2), encoding='utf-8')
        print(f'  Saved Block Kit JSON: {args.save_json}')

    if not args.post:
        print()
        print('Dry-run only. Re-run with --post to actually push to Slack.')
        return 0

    webhook = args.webhook or os.getenv('SLACK_AUDIT_WEBHOOK_URL')
    if not webhook:
        print('ERROR: --post requires SLACK_AUDIT_WEBHOOK_URL or --webhook',
              file=sys.stderr)
        return 1

    print()
    print('Posting to Slack...')
    r = requests.post(
        webhook,
        json=message,
        headers={'Content-Type': 'application/json'},
        timeout=30,
    )
    if r.status_code == 200:
        print(f'  OK ({r.status_code})')
        return 0
    else:
        print(f'  FAIL ({r.status_code}): {r.text[:300]}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
