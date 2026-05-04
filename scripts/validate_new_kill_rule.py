#!/usr/bin/env python3
"""
validate_new_kill_rule.py — Read-only EB-truth validator for the new
lifetime-rate kill rule.

For every active workspace:
  1. Pull all senders from EB (paginated) — capture lifetime sends, status, tags
  2. From the DB, compute lifetime hard bounces from response_messages
  3. Apply the proposed rule to each inbox:
       complaint ≥ 1                   → would-kill (spam)
       sends < 20                      → skip
       hard_bounces / sends > 5%       → would-kill (rate)
  4. Compare to current DB inbox_state. Output two diffs:
       NEW KILLS: live in DB, would be killed by new rule
       REVIVALS:  dead in DB by count-trigger, EB Connected, new rule says safe

This is read-only — no DB writes, no EB writes, no Slack posts.

Usage:
    py scripts/validate_new_kill_rule.py                    # all workspaces
    py scripts/validate_new_kill_rule.py --workspace Barrena  # one workspace
    py scripts/validate_new_kill_rule.py --workspace Barrena --verbose
    py scripts/validate_new_kill_rule.py --json-out d:/tmp/validation.json
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ADMIN_API = 'https://api.wizardgrimoire.cloud/api/admin/run-sql'
ADMIN_KEY = '098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa'
EB_BASE = 'https://spellcast.hirecharm.com/api'

# Proposed rule thresholds
MIN_SENDS = 20
MAX_RATE = 0.05  # 5% lifetime hard bounce rate
COUNT_KILL_TRIGGERS = ('hard_blocked_24h', 'hard_unknown_24h', 'hard_bounces_24h')


def run_sql(sql: str) -> List[Dict[str, Any]]:
    """Execute SQL via the admin endpoint. POST with query params (matches curl -G -X POST)."""
    qs = urllib.parse.urlencode({'key': ADMIN_KEY, 'sql': sql})
    url = f'{ADMIN_API}?{qs}'
    req = urllib.request.Request(
        url,
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
    raise RuntimeError(f'unexpected admin response: {body!r}')


def eb_fetch_all_senders(api_key: str) -> List[Dict[str, Any]]:
    """Page through /sender-emails (EB returns 15/page regardless of per_page)."""
    rows: List[Dict[str, Any]] = []
    page = 1
    while True:
        url = f'{EB_BASE}/sender-emails?per_page=100&page={page}'
        req = urllib.request.Request(
            url,
            headers={'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'},
        )
        for attempt in range(3):
            try:
                r = urllib.request.urlopen(req, timeout=30)
                d = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 502, 503, 504) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise
        rows.extend(d.get('data', []))
        meta = d.get('meta', {})
        last = meta.get('last_page', 1) or 1
        if page >= last:
            break
        page += 1
    return rows


def evaluate_rule(sends: int, hard_bounces: int, complaints: int) -> tuple[Optional[str], str]:
    """Apply the proposed Phase 1 rule. Returns (verdict, reason)."""
    if complaints >= 1:
        return ('kill', f'spam_complaint (complaints={complaints})')
    if sends < MIN_SENDS:
        return (None, f'skip (sends={sends} < {MIN_SENDS})')
    rate = hard_bounces / sends if sends else 0
    if rate > MAX_RATE:
        return ('kill', f'rate {rate*100:.2f}% > {MAX_RATE*100:.0f}% (hard={hard_bounces}, sends={sends})')
    return (None, f'safe (rate={rate*100:.2f}%)')


def evaluate_workspace(ws: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
    ws_id = ws['workspace_id']
    ws_name = ws['workspace_name']
    api_key = ws['key_token']

    print(f'\n=== {ws_name} (id={ws_id}) ===', flush=True)

    # 1. Pull EB senders
    try:
        eb_senders = eb_fetch_all_senders(api_key)
    except Exception as exc:
        print(f'  ERROR pulling EB senders: {exc!r}')
        return {
            'workspace_name': ws_name, 'workspace_id': ws_id,
            'error': f'eb_fetch: {exc!r}',
            'new_kills': [], 'revivals': [], 'live_clean': 0, 'dead_correct': 0, 'mismatch': 0,
        }
    print(f'  EB: {len(eb_senders)} senders pulled')

    # Index EB by emailbison id
    eb_by_id = {str(s['id']): s for s in eb_senders}

    # 2. Pull DB inboxes for this workspace + bounce counts.
    # Correlated subqueries instead of CTE — admin endpoint chokes on some CTE shapes.
    db_rows = run_sql(f"""
        SELECT
            sa.id::text AS db_id,
            sa.email_address,
            sa.emailbison_account_id,
            sa.inbox_state,
            sa.kill_trigger::text AS kill_trigger,
            sa.killed_at,
            sa.is_active,
            sa.complaints_lifetime,
            COALESCE(sa.emails_sent_all_time, 0) AS db_sends,
            (SELECT COUNT(*) FROM response_messages rm
             WHERE rm.sender_account_id = sa.id AND rm.folder = 'bounced'
               AND rm.bounce_type IN ('hard_blocked','hard_unknown')) AS hard_bnc,
            (SELECT COUNT(*) FROM response_messages rm
             WHERE rm.sender_account_id = sa.id AND rm.folder = 'bounced'
               AND rm.bounce_type IN ('soft_full','soft_temp')) AS soft_bnc
        FROM sender_accounts sa
        WHERE sa.workspace_id = '{ws_id}' AND sa.is_active = TRUE
        ORDER BY sa.email_address
    """)
    print(f'  DB: {len(db_rows)} active inboxes')

    new_kills: List[Dict[str, Any]] = []
    revivals: List[Dict[str, Any]] = []
    live_clean = 0
    dead_correct = 0
    no_eb_match = 0

    for row in db_rows:
        eb = eb_by_id.get(str(row['emailbison_account_id'])) if row['emailbison_account_id'] else None
        eb_sends = int(eb['emails_sent_count']) if eb else 0
        eb_bounced = int(eb['bounced_count']) if eb else 0
        eb_status = eb['status'] if eb else 'NO_EB_MATCH'
        eb_tags = [t['name'] for t in (eb.get('tags') or [])] if eb else []

        # Use EB sends as denominator if available (more authoritative); fall back to DB
        sends_for_rule = eb_sends if eb_sends > 0 else int(row['db_sends'])
        hard_bnc = int(row['hard_bnc'])
        complaints = int(row['complaints_lifetime'] or 0)

        verdict, reason = evaluate_rule(sends_for_rule, hard_bnc, complaints)
        rate_pct = (hard_bnc / sends_for_rule * 100) if sends_for_rule else 0

        case = {
            'email': row['email_address'],
            'db_state': row['inbox_state'],
            'db_kill_trigger': row['kill_trigger'],
            'eb_status': eb_status,
            'eb_sends': eb_sends,
            'eb_bounced': eb_bounced,
            'db_sends': int(row['db_sends']),
            'hard_bnc_from_response_messages': hard_bnc,
            'soft_bnc_from_response_messages': int(row['soft_bnc']),
            'complaints': complaints,
            'sends_used': sends_for_rule,
            'rate_pct': round(rate_pct, 2),
            'new_rule_verdict': verdict,
            'new_rule_reason': reason,
            'eb_tags': eb_tags,
        }

        if eb is None:
            no_eb_match += 1
            continue

        # NEW KILLS: currently live, new rule says kill
        if row['inbox_state'] == 'live' and verdict == 'kill':
            new_kills.append(case)

        # REVIVALS: currently dead by a count-based trigger, EB still Connected,
        # new rule says safe, no spam complaint
        elif (
            row['inbox_state'] == 'dead'
            and row['kill_trigger'] in COUNT_KILL_TRIGGERS
            and eb_status == 'Connected'
            and verdict is None
            and complaints == 0
        ):
            revivals.append(case)

        elif row['inbox_state'] == 'live' and verdict is None:
            live_clean += 1
        elif row['inbox_state'] == 'dead' and (verdict == 'kill' or row['kill_trigger'] not in COUNT_KILL_TRIGGERS):
            dead_correct += 1

    print(f'  Result: live_clean={live_clean}, would_kill_new={len(new_kills)}, '
          f'revival_candidates={len(revivals)}, dead_kept={dead_correct}, '
          f'no_eb_match={no_eb_match}')

    if verbose:
        if new_kills:
            print('  NEW KILLS (currently live, new rule says kill):')
            for c in new_kills:
                print(f'    {c["email"]:<45} sends={c["sends_used"]:>5} hard={c["hard_bnc_from_response_messages"]:>3} '
                      f'rate={c["rate_pct"]:>5.2f}% comp={c["complaints"]} → {c["new_rule_reason"]}')
        if revivals:
            print('  REVIVALS (dead by count-trigger, EB Connected, new rule safe):')
            for c in revivals:
                print(f'    {c["email"]:<45} sends={c["sends_used"]:>5} hard={c["hard_bnc_from_response_messages"]:>3} '
                      f'rate={c["rate_pct"]:>5.2f}% killed_by={c["db_kill_trigger"]}')

    return {
        'workspace_name': ws_name,
        'workspace_id': ws_id,
        'eb_count': len(eb_senders),
        'db_count': len(db_rows),
        'no_eb_match': no_eb_match,
        'live_clean': live_clean,
        'new_kills': new_kills,
        'revivals': revivals,
        'dead_kept': dead_correct,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', help='Limit to one workspace by name')
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--json-out', help='Write full results JSON')
    args = ap.parse_args()

    ws_filter = ''
    if args.workspace:
        ws_filter = f"AND w.workspace_name = '{args.workspace.replace(chr(39), chr(39)+chr(39))}'"

    workspaces = run_sql(f"""
        SELECT w.id::text AS workspace_id, w.workspace_name, wak.key_token
        FROM workspaces w
        JOIN workspace_api_keys wak
            ON wak.workspace_id = w.id AND wak.is_active = TRUE
        WHERE w.is_active = TRUE
          AND w.emailbison_workspace_id IS NOT NULL
          {ws_filter}
        ORDER BY w.workspace_name
    """)
    print(f'Validating {len(workspaces)} workspace(s) against new kill rule...')
    print(f'Rule: spam ≥ 1 → kill | sends < {MIN_SENDS} → skip | rate > {MAX_RATE*100:.0f}% → kill')

    results: List[Dict[str, Any]] = []
    total_new_kills = 0
    total_revivals = 0
    for ws in workspaces:
        try:
            r = evaluate_workspace(ws, verbose=args.verbose)
            results.append(r)
            total_new_kills += len(r.get('new_kills', []))
            total_revivals += len(r.get('revivals', []))
        except Exception as exc:
            print(f'  FAILED workspace {ws["workspace_name"]}: {exc!r}')
            results.append({'workspace_name': ws['workspace_name'], 'error': str(exc)})

    print()
    print('=' * 78)
    print('FLEET SUMMARY')
    print('=' * 78)
    for r in results:
        if 'error' in r:
            print(f'  {r["workspace_name"]:<30} ERROR: {r["error"][:60]}')
            continue
        print(f'  {r["workspace_name"]:<30} live_clean={r["live_clean"]:>4} '
              f'new_kills={len(r["new_kills"]):>3}  revivals={len(r["revivals"]):>3}  '
              f'dead_kept={r["dead_kept"]:>3}  no_eb={r["no_eb_match"]:>3}')
    print(f'\n  TOTAL new kills under new rule:        {total_new_kills}')
    print(f'  TOTAL revival candidates:              {total_revivals}')

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        print(f'\n  Wrote {args.json_out}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
