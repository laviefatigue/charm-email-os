#!/usr/bin/env python3
"""
resurrect_false_positive_kills.py — Revive inboxes killed by the count-based
rules that the new lifetime rate rule says are healthy.

Plan reference: docs/plans/kill-rule-rate-based-rewrite.md (Phase 2-3)

Scope of revival per inbox:
  1. EmailBison: remove tags `flagged_hard_blocked_24h`, `flagged_hard_unknown_24h`,
     `flagged_hard_bounces_24h`.
  2. EmailBison: re-apply the workspace's pool tag (default 'live').
  3. DB: UPDATE sender_accounts
        SET inbox_state='live', kill_trigger=NULL, killed_at=NULL,
            inventory_pool_status='live', inventory_lifecycle_status='active'
  4. DB: UPDATE kill_queue SET status='cancelled', error_message='revived: lifetime-rate rule'
        for the matching kill row (most recent count-based one).

Eligibility (matches Phase 4 SQL in the plan):
  - is_active = TRUE
  - inbox_state = 'dead'
  - kill_trigger IN ('hard_blocked_24h','hard_unknown_24h','hard_bounces_24h')
  - status = 'Connected' (EB still connected — sanity check)
  - complaints_lifetime = 0 (never had a real complaint)
  - emails_sent_all_time >= 20 (above floor)
  - hard_bounces_lifetime / emails_sent_all_time <= 5% (rate is healthy)

Usage:
    py scripts/resurrect_false_positive_kills.py --workspace Barrena                       # dry-run (default)
    py scripts/resurrect_false_positive_kills.py --workspace Barrena --apply               # actually run
    py scripts/resurrect_false_positive_kills.py --workspace Barrena --apply --limit 5     # safety cap
    py scripts/resurrect_false_positive_kills.py --all-workspaces --apply --batch-size 50

Always defaults to dry-run. --apply is required to write anything.
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

FLAG_TAG_PREFIXES = (
    'flagged_hard_blocked_24h',
    'flagged_hard_unknown_24h',
    'flagged_hard_bounces_24h',
)
COUNT_KILL_TRIGGERS = ('hard_blocked_24h', 'hard_unknown_24h', 'hard_bounces_24h')


def run_sql(sql: str) -> Any:
    qs = urllib.parse.urlencode({'key': ADMIN_KEY, 'sql': sql})
    req = urllib.request.Request(
        f'{ADMIN_API}?{qs}',
        method='POST',
        headers={'User-Agent': 'curl/8.0.0', 'Accept': 'application/json'},
    )
    try:
        r = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='ignore')
        raise RuntimeError(f'admin API HTTP {e.code}: {body[:300]}') from e
    body = json.loads(r.read())
    if isinstance(body, dict) and 'detail' in body:
        raise RuntimeError(f'admin API error: {body["detail"]}')
    if isinstance(body, dict) and isinstance(body.get('result'), list):
        return body['result']
    if isinstance(body, dict) and body.get('result') == 'OK':
        return None
    raise RuntimeError(f'unexpected admin response: {body!r}')


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


def eb_get_paginated(api_key: str, path: str) -> List[Dict]:
    rows = []
    page = 1
    while True:
        d = eb_request('GET', api_key, f'{path}?per_page=100&page={page}')
        rows.extend(d.get('data') or [])
        meta = d.get('meta', {})
        last = meta.get('last_page', 1) or 1
        if page >= last:
            break
        page += 1
    return rows


def fetch_workspace(name: Optional[str], all_ws: bool) -> List[Dict]:
    where = ""
    if name:
        safe = name.replace("'", "''")
        where = f"AND w.workspace_name = '{safe}'"
    elif not all_ws:
        raise SystemExit("must pass --workspace NAME or --all-workspaces")
    rows = run_sql(f"""
        SELECT w.id::text AS workspace_id, w.workspace_name, wak.key_token
        FROM workspaces w
        JOIN workspace_api_keys wak ON wak.workspace_id = w.id AND wak.is_active = TRUE
        WHERE w.is_active = TRUE AND w.emailbison_workspace_id IS NOT NULL
          {where}
        ORDER BY w.workspace_name
    """)
    return rows or []


def fetch_candidates(workspace_id: str) -> List[Dict]:
    return run_sql(f"""
        SELECT
            sa.id::text AS db_id,
            sa.email_address,
            sa.emailbison_account_id,
            sa.kill_trigger::text AS kill_trigger,
            sa.killed_at,
            sa.status,
            sa.complaints_lifetime,
            COALESCE(sa.emails_sent_all_time, 0) AS emails_sent_all_time,
            (SELECT COUNT(*) FROM response_messages rm
             WHERE rm.sender_account_id = sa.id AND rm.folder = 'bounced'
               AND rm.bounce_type IN ('hard_blocked','hard_unknown')) AS hard_bnc
        FROM sender_accounts sa
        WHERE sa.workspace_id = '{workspace_id}'
          AND sa.is_active = TRUE
          AND sa.inbox_state = 'dead'
          AND sa.kill_trigger::text IN ('hard_blocked_24h','hard_unknown_24h','hard_bounces_24h')
          AND sa.status = 'Connected'
          AND COALESCE(sa.complaints_lifetime, 0) = 0
          AND COALESCE(sa.emails_sent_all_time, 0) >= 20
          AND (
              SELECT COUNT(*) FROM response_messages rm
              WHERE rm.sender_account_id = sa.id AND rm.folder = 'bounced'
                AND rm.bounce_type IN ('hard_blocked','hard_unknown')
          )::numeric / GREATEST(COALESCE(sa.emails_sent_all_time, 1), 1) <= 0.05
        ORDER BY sa.email_address
    """) or []


def revive_inbox(api_key: str, workspace_name: str, candidate: Dict, eb_lookup: Dict[str, Dict],
                 apply: bool, log_lines: List[str]) -> Dict:
    """Revive a single inbox. Returns a status dict.

    Steps when apply=True:
      1. Untag all flagged_* tags on the inbox in EB
      2. Re-add 'live' tag in EB
      3. UPDATE sender_accounts to live
      4. UPDATE kill_queue to cancelled
    """
    eb_id = candidate.get('emailbison_account_id')
    db_id = candidate['db_id']
    email = candidate['email_address']
    sends = int(candidate['emails_sent_all_time'])
    hard = int(candidate['hard_bnc'])
    rate_pct = (hard / sends * 100) if sends else 0
    eb_sender = eb_lookup.get(str(eb_id)) if eb_id else None

    log = lambda s: log_lines.append(s) or print(s)

    if not eb_sender:
        log(f'  SKIP {email}: no EB match for emailbison_id={eb_id}')
        return {'email': email, 'status': 'skipped_no_eb_match'}

    if eb_sender.get('status') != 'Connected':
        log(f'  SKIP {email}: EB status={eb_sender.get("status")} (no longer Connected)')
        return {'email': email, 'status': 'skipped_not_connected'}

    eb_tags = eb_sender.get('tags') or []
    flagged_tags = [t for t in eb_tags if any(t['name'].startswith(p) for p in FLAG_TAG_PREFIXES)]

    log(f'  REVIVE {email}: sends={sends} hard={hard} rate={rate_pct:.2f}% '
        f'killed_by={candidate["kill_trigger"]} flagged_tags={[t["name"] for t in flagged_tags]}')

    if not apply:
        return {
            'email': email, 'status': 'dry_run',
            'tags_to_remove': [t['name'] for t in flagged_tags],
            'sends': sends, 'hard': hard, 'rate_pct': rate_pct,
        }

    # Step 1: untag flagged_* in EB
    for t in flagged_tags:
        try:
            eb_request('POST', api_key, '/tags/remove-from-sender-emails',
                       json_body={'tag_ids': [t['id']], 'sender_email_ids': [eb_id]})
            log(f'    untagged {t["name"]} from EB')
        except Exception as exc:
            log(f'    FAILED to untag {t["name"]}: {exc!r}')
            return {'email': email, 'status': 'eb_untag_failed', 'error': str(exc)}

    # Step 2: re-tag as live in EB. Use get_or_create-style flow.
    # Find or create the 'live' tag for this workspace.
    try:
        all_tags = eb_get_paginated(api_key, '/tags')
        live_tag = next((t for t in all_tags if t.get('name', '').lower() == 'live'), None)
        if not live_tag:
            created = eb_request('POST', api_key, '/tags', json_body={'name': 'live'})
            live_tag = created.get('data', created)
        eb_request('POST', api_key, '/tags/attach-to-sender-emails',
                   json_body={'tag_ids': [live_tag['id']], 'sender_email_ids': [eb_id]})
        log(f'    re-tagged with "live" in EB')
    except Exception as exc:
        log(f'    FAILED to re-tag live: {exc!r}')
        return {'email': email, 'status': 'eb_retag_failed', 'error': str(exc)}

    # Step 3: DB sender_accounts restore.
    try:
        run_sql(f"""
            UPDATE sender_accounts SET
                inbox_state = 'live',
                kill_trigger = NULL,
                killed_at = NULL,
                inventory_pool_status = 'live',
                inventory_lifecycle_status = 'active',
                updated_at = NOW()
            WHERE id = '{db_id}'
        """)
        log(f'    DB sender_accounts restored to live')
    except Exception as exc:
        log(f'    FAILED to update sender_accounts: {exc!r}')
        return {'email': email, 'status': 'db_update_failed', 'error': str(exc)}

    # Step 4: kill_queue cleanup (cancel the count-based row).
    try:
        run_sql(f"""
            UPDATE kill_queue
            SET status = 'cancelled',
                error_message = 'revived 2026-05-04: lifetime-rate rule says safe (rate {rate_pct:.2f}%, sends {sends}, EB Connected)'
            WHERE inbox_id = '{db_id}'
              AND trigger_type::text IN ('hard_blocked_24h','hard_unknown_24h','hard_bounces_24h')
              AND status = 'flagged'
        """)
        log(f'    kill_queue marked cancelled')
    except Exception as exc:
        log(f'    WARN kill_queue update non-fatal: {exc!r}')

    return {'email': email, 'status': 'revived', 'sends': sends, 'hard': hard, 'rate_pct': rate_pct}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', help='Single workspace name')
    ap.add_argument('--all-workspaces', action='store_true')
    ap.add_argument('--apply', action='store_true', help='Actually run (default is dry-run)')
    ap.add_argument('--limit', type=int, help='Cap revivals at N inboxes')
    ap.add_argument('--batch-size', type=int, default=10, help='Pause every N revivals')
    ap.add_argument('--batch-pause-seconds', type=int, default=2)
    ap.add_argument('--audit-log', help='Write per-action audit log to this path')
    args = ap.parse_args()

    workspaces = fetch_workspace(args.workspace, args.all_workspaces)
    if not workspaces:
        print('No matching workspaces. Exit.')
        return 1

    print(f'Mode: {"APPLY" if args.apply else "DRY-RUN (no changes)"}')
    print(f'Workspaces: {", ".join(w["workspace_name"] for w in workspaces)}')
    print()

    log_lines: List[str] = []
    total_revived = 0
    total_skipped = 0
    total_failed = 0

    for ws in workspaces:
        ws_id = ws['workspace_id']
        ws_name = ws['workspace_name']
        api_key = ws['key_token']

        candidates = fetch_candidates(ws_id)
        if not candidates:
            print(f'=== {ws_name}: 0 candidates, skip ===\n')
            continue

        print(f'=== {ws_name}: {len(candidates)} revival candidates ===')
        # Pull EB senders once to get current tags/status
        try:
            eb_senders = eb_get_paginated(api_key, '/sender-emails')
        except Exception as exc:
            print(f'  ERROR pulling EB senders: {exc!r}\n')
            continue
        eb_lookup = {str(s['id']): s for s in eb_senders}

        revived_in_ws = 0
        for i, c in enumerate(candidates, 1):
            if args.limit and total_revived + revived_in_ws >= args.limit:
                print(f'  hit --limit {args.limit}, stop')
                break
            result = revive_inbox(api_key, ws_name, c, eb_lookup, args.apply, log_lines)
            if result['status'] == 'revived':
                revived_in_ws += 1
                total_revived += 1
            elif result['status'] == 'dry_run':
                revived_in_ws += 1
            elif result['status'].startswith('skipped'):
                total_skipped += 1
            else:
                total_failed += 1

            if args.apply and revived_in_ws and revived_in_ws % args.batch_size == 0:
                print(f'  -- batch pause ({args.batch_pause_seconds}s) --')
                time.sleep(args.batch_pause_seconds)

        print()

    print('=' * 78)
    print(f'TOTAL: revived={total_revived}, skipped={total_skipped}, failed={total_failed}')
    print('=' * 78)

    if args.audit_log:
        with open(args.audit_log, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_lines))
        print(f'Audit log: {args.audit_log}')

    return 0 if total_failed == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
