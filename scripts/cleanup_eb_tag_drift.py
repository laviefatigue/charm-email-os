#!/usr/bin/env python3
"""
cleanup_eb_tag_drift.py — One-shot fixer for two pre-existing EB↔DB tag drifts.

DRIFT A — live inboxes carrying stale `flagged_*` tags.
  These are leftover tags from removed legacy triggers
  (`flagged_fresh_inbox_bounce`, `flagged_fresh_inbox_unknown`,
   `flagged_provider_block_*`) that were never cleaned up when those
  triggers were removed. The DB correctly says inbox_state='live' but EB
  still has the flagged tag attached.
  Fix: untag every `flagged_*` tag from any inbox where DB says live.

DRIFT B — dead-by-`spam_complaint` inboxes missing `flagged_spam_complaint`
          tag in EB.
  These are kill_processor silent failures from earlier cycles. The DB
  knows the inbox is dead from a spam complaint, but EB has no flagged
  tag indicating why.
  Fix: apply `flagged_spam_complaint` tag in EB.

Defaults to dry-run. --apply required to write.

Usage:
    py scripts/cleanup_eb_tag_drift.py                    # dry-run
    py scripts/cleanup_eb_tag_drift.py --workspace Spout  # one workspace
    py scripts/cleanup_eb_tag_drift.py --apply            # all workspaces, write
    py scripts/cleanup_eb_tag_drift.py --apply --audit-log d:/tmp/eb_cleanup.log
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ADMIN_API = 'https://api.wizardgrimoire.cloud/api/admin/run-sql'
ADMIN_KEY = '098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa'
EB_BASE = 'https://spellcast.hirecharm.com/api'


def run_sql(sql: str) -> Any:
    qs = urllib.parse.urlencode({'key': ADMIN_KEY, 'sql': sql})
    req = urllib.request.Request(
        f'{ADMIN_API}?{qs}', method='POST',
        headers={'User-Agent': 'curl/8.0.0', 'Accept': 'application/json'},
    )
    body = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if isinstance(body, dict) and isinstance(body.get('result'), list):
        return body['result']
    return []


def eb_request(method: str, api_key: str, path: str, json_body: Optional[Dict] = None) -> Any:
    url = f'{EB_BASE}{path}'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    data = json.dumps(json_body).encode() if json_body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    for attempt in range(3):
        try:
            r = urllib.request.urlopen(req, timeout=30)
            raw = r.read()
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            body = e.read().decode(errors='ignore')[:300]
            raise RuntimeError(f'EB {method} {path} HTTP {e.code}: {body}') from e


def eb_pull_senders(api_key: str) -> List[Dict]:
    rows: List[Dict] = []
    page = 1
    while True:
        d = eb_request('GET', api_key, f'/sender-emails?per_page=100&page={page}')
        rows.extend(d.get('data') or [])
        if page >= (d.get('meta', {}).get('last_page', 1) or 1):
            break
        page += 1
    return rows


def fetch_workspaces(name: Optional[str]) -> List[Dict]:
    where = ""
    if name:
        safe = name.replace("'", "''")
        where = f"AND w.workspace_name = '{safe}'"
    return run_sql(f"""
        SELECT w.id::text AS workspace_id, w.workspace_name, wak.key_token
        FROM workspaces w
        JOIN workspace_api_keys wak ON wak.workspace_id = w.id AND wak.is_active = TRUE
        WHERE w.is_active = TRUE AND w.emailbison_workspace_id IS NOT NULL
          {where}
        ORDER BY w.workspace_name
    """) or []


def fetch_db_state(workspace_id: str) -> List[Dict]:
    return run_sql(f"""
        SELECT sa.id::text AS db_id, sa.email_address, sa.emailbison_account_id,
               sa.inbox_state, sa.kill_trigger::text AS kill_trigger
        FROM sender_accounts sa
        WHERE sa.workspace_id = '{workspace_id}' AND sa.is_active = TRUE
    """) or []


def cleanup_workspace(ws: Dict, apply: bool, log: List[str]) -> Dict:
    ws_id = ws['workspace_id']
    ws_name = ws['workspace_name']
    api_key = ws['key_token']

    print(f'\n=== {ws_name} ===')
    log.append(f'\n=== {ws_name} ===')

    try:
        eb_senders = eb_pull_senders(api_key)
    except Exception as exc:
        msg = f'  EB ERROR: {exc!r}'
        print(msg)
        log.append(msg)
        return {'workspace_name': ws_name, 'a_fixed': 0, 'b_fixed': 0, 'errors': 1}

    eb_by_id = {str(s['id']): s for s in eb_senders}
    db_rows = fetch_db_state(ws_id)

    a_actions: List[Dict] = []  # (eb_id, email, tag_id, tag_name) for untag
    b_actions: List[Dict] = []  # (eb_id, email) for apply flagged_spam_complaint

    spam_tag_id_cache: Optional[int] = None

    for row in db_rows:
        eb = eb_by_id.get(str(row['emailbison_account_id'])) if row['emailbison_account_id'] else None
        if not eb:
            continue
        eb_tags = eb.get('tags') or []

        # DRIFT A: live in DB, has flagged_* tag in EB → untag
        if row['inbox_state'] == 'live':
            for t in eb_tags:
                if t['name'].startswith('flagged_'):
                    a_actions.append({
                        'eb_id': eb['id'], 'email': row['email_address'],
                        'tag_id': t['id'], 'tag_name': t['name'],
                    })

        # DRIFT B: dead-by-spam_complaint, missing flagged_spam_complaint tag → apply
        elif row['inbox_state'] == 'dead' and row['kill_trigger'] == 'spam_complaint':
            tag_names = [t['name'] for t in eb_tags]
            if 'flagged_spam_complaint' not in tag_names:
                b_actions.append({'eb_id': eb['id'], 'email': row['email_address']})

    print(f'  DRIFT A — live with flagged_*: {len(a_actions)}')
    print(f'  DRIFT B — dead spam missing flagged_spam_complaint: {len(b_actions)}')
    log.append(f'  DRIFT A: {len(a_actions)}, DRIFT B: {len(b_actions)}')

    if not apply:
        for a in a_actions[:5]:
            print(f'    [A dry] would untag {a["tag_name"]} from {a["email"]}')
        for b in b_actions[:5]:
            print(f'    [B dry] would apply flagged_spam_complaint to {b["email"]}')
        return {'workspace_name': ws_name, 'a_fixed': 0, 'b_fixed': 0, 'errors': 0,
                'a_count': len(a_actions), 'b_count': len(b_actions)}

    # Apply A: untag flagged_*
    a_fixed = a_errors = 0
    for a in a_actions:
        try:
            eb_request('POST', api_key, '/tags/remove-from-sender-emails',
                       json_body={'tag_ids': [a['tag_id']], 'sender_email_ids': [a['eb_id']]})
            log.append(f'    [A] untagged {a["tag_name"]} from {a["email"]}')
            a_fixed += 1
        except Exception as exc:
            log.append(f'    [A FAIL] {a["email"]} tag={a["tag_name"]}: {exc!r}')
            a_errors += 1

    # Apply B: ensure flagged_spam_complaint tag exists, then tag inbox
    b_fixed = b_errors = 0
    if b_actions:
        if spam_tag_id_cache is None:
            try:
                # get-or-create flagged_spam_complaint
                page = 1
                spam_tag = None
                while True:
                    td = eb_request('GET', api_key, f'/tags?per_page=100&page={page}')
                    for t in (td.get('data') or []):
                        if t.get('name', '').lower() == 'flagged_spam_complaint':
                            spam_tag = t
                            break
                    if spam_tag or page >= (td.get('meta', {}).get('last_page', 1) or 1):
                        break
                    page += 1
                if not spam_tag:
                    created = eb_request('POST', api_key, '/tags',
                                         json_body={'name': 'flagged_spam_complaint'})
                    spam_tag = created.get('data', created)
                spam_tag_id_cache = spam_tag['id']
            except Exception as exc:
                msg = f'  ERROR finding/creating flagged_spam_complaint tag: {exc!r}'
                print(msg)
                log.append(msg)
                return {'workspace_name': ws_name, 'a_fixed': a_fixed, 'b_fixed': 0,
                        'errors': len(b_actions)}

        for b in b_actions:
            try:
                eb_request('POST', api_key, '/tags/attach-to-sender-emails',
                           json_body={'tag_ids': [spam_tag_id_cache], 'sender_email_ids': [b['eb_id']]})
                log.append(f'    [B] applied flagged_spam_complaint to {b["email"]}')
                b_fixed += 1
            except Exception as exc:
                log.append(f'    [B FAIL] {b["email"]}: {exc!r}')
                b_errors += 1

    print(f'  Applied: A={a_fixed} (errors {a_errors}), B={b_fixed} (errors {b_errors})')
    return {'workspace_name': ws_name, 'a_fixed': a_fixed, 'b_fixed': b_fixed,
            'errors': a_errors + b_errors,
            'a_count': len(a_actions), 'b_count': len(b_actions)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', help='Single workspace name')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--audit-log', help='Write per-action audit log to this path')
    args = ap.parse_args()

    workspaces = fetch_workspaces(args.workspace)
    if not workspaces:
        print('No matching workspaces.')
        return 1

    print(f'Mode: {"APPLY" if args.apply else "DRY-RUN"}')
    print(f'Workspaces: {", ".join(w["workspace_name"] for w in workspaces)}')

    log: List[str] = []
    totals = {'a_fixed': 0, 'b_fixed': 0, 'errors': 0, 'a_count': 0, 'b_count': 0}
    for ws in workspaces:
        try:
            r = cleanup_workspace(ws, args.apply, log)
            for k in totals:
                totals[k] = totals[k] + r.get(k, 0)
        except Exception as exc:
            print(f'WORKSPACE FAILED: {ws["workspace_name"]}: {exc!r}')
            totals['errors'] += 1

    print()
    print('=' * 70)
    print('SUMMARY')
    print('=' * 70)
    if args.apply:
        print(f'  A — flagged_* tags removed from live inboxes: {totals["a_fixed"]}')
        print(f'  B — flagged_spam_complaint tags added: {totals["b_fixed"]}')
    else:
        print(f'  A — flagged_* tags to remove: {totals["a_count"]}')
        print(f'  B — flagged_spam_complaint tags to add: {totals["b_count"]}')
    print(f'  Errors: {totals["errors"]}')

    if args.audit_log:
        with open(args.audit_log, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log))
        print(f'  Audit log: {args.audit_log}')

    return 0 if totals['errors'] == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
