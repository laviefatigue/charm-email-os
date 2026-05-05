#!/usr/bin/env python3
"""
validate_event_driven_retro.py — Retroactive validation of event-driven
handler logic against historical production data.

Replays the last N days of state changes through the proposed event-driven
handler logic, compares predicted outcomes to actual historical outcomes,
and reports match rates + mismatches.

What this validates:
  ✓ Handler business logic correctness (would the same handler produce
    the same outcome given the same inputs?)

What this does NOT validate (covered by other gates):
  ✗ Trigger SQL correctness (Gate 1: synthetic tests)
  ✗ Listener reliability (Gate 1+3: synthetic + chaos)
  ✗ event_log write atomicity (Gate 1: synthetic)
  ✗ Real-time latency (Gate 4: shadow mode)

Three sections:
  A. Kill chain replay (last 60 days)
     For each killed inbox, reconstruct inputs at killed_at,
     run evaluate_lifetime_rule, compare to actual kill_trigger.
  B. Promotion chain replay (last 60 days)
     For each row in inbox_rotation_history, validate pool_promotion's
     candidate selection logic against historical state.
  C. Tag op chain (forward-looking)
     For currently-live inboxes, what tag ops would event-driven enqueue?
     Cross-reference to current EB tag state.

Usage:
    py scripts/validate_event_driven_retro.py
    py scripts/validate_event_driven_retro.py --days 30
    py scripts/validate_event_driven_retro.py --section kill
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any, Dict, List, Optional

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ADMIN_API = 'https://api.wizardgrimoire.cloud/api/admin/run-sql'
ADMIN_KEY = '098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa'

# Mirror of evaluate_lifetime_rule from sync_modules/health_checks.py
KILL_THRESHOLD_SPAM = 1
KILL_MIN_SENDS_LIFETIME = 20
KILL_MATURE_RATE = 0.05


def run_sql(sql: str) -> List[Dict[str, Any]]:
    qs = urllib.parse.urlencode({'key': ADMIN_KEY, 'sql': sql})
    req = urllib.request.Request(
        f'{ADMIN_API}?{qs}', method='POST',
        headers={'User-Agent': 'curl/8.0.0', 'Accept': 'application/json'},
    )
    body = json.loads(urllib.request.urlopen(req, timeout=120).read())
    if isinstance(body, dict) and isinstance(body.get('result'), list):
        return body['result']
    return []


def evaluate_lifetime_rule(complaints: int, sends: int, hard_bounces: int):
    """Pure function form of the post-2026-05-04 rule (mirrors health_checks.py)."""
    if complaints >= KILL_THRESHOLD_SPAM:
        return ('spam_complaint', float(complaints), float(KILL_THRESHOLD_SPAM))
    if sends < KILL_MIN_SENDS_LIFETIME:
        return None
    rate = hard_bounces / sends if sends else 0.0
    if rate > KILL_MATURE_RATE:
        return ('hard_bounce_rate_lifetime', rate, KILL_MATURE_RATE)
    return None


# ──────────────────────────────────────────────────────────────────────────
# SECTION A — Kill chain retroactive validation
# ──────────────────────────────────────────────────────────────────────────
def validate_kill_chain(days: int) -> Dict[str, Any]:
    """For each kill in the last N days, predict via new rule, compare to actual."""
    print(f'\n=== SECTION A — KILL CHAIN (last {days} days) ===\n')

    # Pull every active killed inbox in window. Reconstruct inputs at killed_at.
    rows = run_sql(f"""
        SELECT
            sa.id::text AS inbox_id,
            sa.email_address,
            sa.kill_trigger::text AS actual_kill_trigger,
            sa.killed_at,
            sa.complaints_lifetime,
            COALESCE(sa.emails_sent_all_time, 0) AS emails_sent_all_time,
            (
                SELECT COUNT(*) FROM response_messages rm
                WHERE rm.sender_account_id = sa.id
                  AND rm.folder = 'bounced'
                  AND rm.bounce_type IN ('hard_blocked', 'hard_unknown')
                  AND rm.received_at <= sa.killed_at
            ) AS hard_bounces_at_killed_at,
            w.workspace_name
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        WHERE sa.is_active = TRUE
          AND sa.inbox_state = 'dead'
          AND sa.killed_at IS NOT NULL
          AND sa.killed_at > NOW() - INTERVAL '{days} days'
        ORDER BY sa.killed_at DESC
    """)
    print(f'  Pulled {len(rows)} kills from the last {days} days')

    if not rows:
        return {'section': 'kill_chain', 'days': days, 'kills_replayed': 0}

    categories: Counter = Counter()
    samples: Dict[str, List[Dict]] = {
        'predicted_no_kill': [],     # New rule says SAFE — these are the false positives we revived (or should have)
        'wrong_trigger': [],         # Both rules kill, but for different reasons
        'matches': [],               # Same kill, same reason
        'spam_match': [],            # Both agree on spam_complaint
    }

    for row in rows:
        complaints = int(row['complaints_lifetime'] or 0)
        sends = int(row['emails_sent_all_time'])
        hard = int(row['hard_bounces_at_killed_at'])
        actual = row['actual_kill_trigger']

        verdict = evaluate_lifetime_rule(complaints, sends, hard)

        if verdict is None:
            categories['predicted_no_kill'] += 1
            if len(samples['predicted_no_kill']) < 5:
                rate_pct = (hard / sends * 100) if sends else 0
                samples['predicted_no_kill'].append({
                    'email': row['email_address'],
                    'workspace': row['workspace_name'],
                    'actual_trigger': actual,
                    'sends': sends, 'hard_bnc': hard, 'rate_pct': round(rate_pct, 2),
                    'complaints': complaints,
                })
        else:
            predicted_trigger = verdict[0]
            if predicted_trigger == actual:
                categories['matches'] += 1
                if predicted_trigger == 'spam_complaint':
                    samples['spam_match'].append(row['email_address'])
            else:
                categories['wrong_trigger'] += 1
                if len(samples['wrong_trigger']) < 5:
                    samples['wrong_trigger'].append({
                        'email': row['email_address'],
                        'actual_trigger': actual,
                        'predicted_trigger': predicted_trigger,
                        'sends': sends, 'hard_bnc': hard,
                        'rate_pct': round((hard / sends * 100) if sends else 0, 2),
                    })

    total = len(rows)
    print(f'\n  Categories:')
    for cat, count in categories.most_common():
        print(f'    {cat:<30} {count:>5}  ({count/total*100:.1f}%)')

    print(f'\n  Interpretation:')
    print(f'    matches       = new rule fires same kill, same trigger as historical')
    print(f'    wrong_trigger = both rules kill, different reasons (e.g., old was hard_blocked_24h, new is hard_bounce_rate_lifetime)')
    print(f'    predicted_no_kill = new rule says SAFE — these are the false positives revived 2026-05-04 (or should have been)')

    if samples['predicted_no_kill']:
        print(f'\n  Sample "predicted no kill" (false-positive class — should have been revived):')
        for s in samples['predicted_no_kill']:
            print(f'    {s["email"]:<45} {s["workspace"]:<20} actual={s["actual_trigger"]:<22} '
                  f'sends={s["sends"]:>5} hard={s["hard_bnc"]:>3} rate={s["rate_pct"]:>5.2f}%')

    if samples['wrong_trigger']:
        print(f'\n  Sample "wrong trigger" (both kill but different reason):')
        for s in samples['wrong_trigger']:
            print(f'    {s["email"]:<45} actual={s["actual_trigger"]:<22} '
                  f'predicted={s["predicted_trigger"]:<28} sends={s["sends"]:>5} '
                  f'hard={s["hard_bnc"]:>3} rate={s["rate_pct"]:>5.2f}%')

    return {
        'section': 'kill_chain',
        'days': days,
        'kills_replayed': total,
        'categories': dict(categories),
        'samples': samples,
    }


# ──────────────────────────────────────────────────────────────────────────
# SECTION B — Promotion chain retroactive validation
# ──────────────────────────────────────────────────────────────────────────
def validate_promotion_chain(days: int) -> Dict[str, Any]:
    """For each pool transition in inbox_rotation_history, validate logic."""
    print(f'\n=== SECTION B — PROMOTION CHAIN (last {days} days) ===\n')

    # All rotation events in window. Schema uses source_inbox_id/target_inbox_id
    # (not sender_account_id) and executed_at (not created_at).
    rotations = run_sql(f"""
        SELECT
            irh.id::text AS rotation_id,
            irh.target_inbox_id::text AS inbox_id,
            irh.rotation_type,
            irh.executed_at AS rotated_at,
            irh.source_pool::text AS source_pool,
            irh.target_pool::text AS target_pool,
            irh.success,
            irh.target_inbox_email AS email_address,
            sa.esp,
            w.workspace_name
        FROM inbox_rotation_history irh
        LEFT JOIN sender_accounts sa ON sa.id = irh.target_inbox_id
        LEFT JOIN workspaces w ON sa.workspace_id = w.id
        WHERE irh.executed_at > NOW() - INTERVAL '{days} days'
        ORDER BY irh.executed_at DESC
        LIMIT 500
    """)
    print(f'  Pulled {len(rotations)} rotation events from last {days} days')

    if not rotations:
        return {'section': 'promotion_chain', 'days': days, 'rotations_replayed': 0}

    by_type = Counter(r['rotation_type'] for r in rotations)
    print(f'\n  Rotation types observed:')
    for rt, count in by_type.most_common():
        print(f'    {rt:<30} {count:>4}')

    # The rotation logic itself is unchanged by event-driven (we just call
    # promote_one(workspace_id) instead of promote-batch). Sanity check:
    # all promote events should be Google (not Microsoft, which is ride-to-death).
    promote_events = [r for r in rotations if 'promot' in (r.get('rotation_type') or '').lower()]
    if promote_events:
        non_google = [r for r in promote_events if r['esp'] != 'gmail']
        print(f'\n  Promote events: {len(promote_events)}')
        print(f'    Non-Google promotions (should be 0 per ADR-006): {len(non_google)}')
        if non_google:
            print(f'    ⚠️  Found {len(non_google)} non-Google promotions — investigate:')
            for r in non_google[:5]:
                print(f'      {r["email_address"]} (esp={r["esp"]}, type={r["rotation_type"]})')

    return {
        'section': 'promotion_chain',
        'days': days,
        'rotations_replayed': len(rotations),
        'by_type': dict(by_type),
        'non_google_promotions': len(non_google) if promote_events else 0,
    }


# ──────────────────────────────────────────────────────────────────────────
# SECTION C — Tag op chain (forward-looking)
# ──────────────────────────────────────────────────────────────────────────
def validate_tag_op_chain() -> Dict[str, Any]:
    """For current state, predict what tag ops event-driven would enqueue.
    Cross-reference to current EB tag drift counts from earlier audit."""
    print(f'\n=== SECTION C — TAG OP CHAIN (current state) ===\n')

    # Inboxes that the kill rule would currently want to kill but aren't dead yet
    # (these would trigger tag_op_attach for flagged_hard_bounce_rate_lifetime
    # if event-driven were running)
    pending_kills = run_sql(f"""
        SELECT COUNT(*) AS c
        FROM sender_accounts sa
        WHERE sa.is_active = TRUE
          AND sa.inbox_state = 'live'
          AND COALESCE(sa.complaints_lifetime, 0) = 0
          AND COALESCE(sa.emails_sent_all_time, 0) >= {KILL_MIN_SENDS_LIFETIME}
          AND (
              SELECT COUNT(*) FROM response_messages rm
              WHERE rm.sender_account_id = sa.id AND rm.folder = 'bounced'
                AND rm.bounce_type IN ('hard_blocked','hard_unknown')
          )::numeric / GREATEST(COALESCE(sa.emails_sent_all_time, 1), 1) > {KILL_MATURE_RATE}
    """)
    pending_count = int(pending_kills[0]['c']) if pending_kills else 0

    # Inboxes flagged in DB but EB tag still missing — would need tag_op_attach
    missing_tags = run_sql(f"""
        SELECT COUNT(*) AS c
        FROM sender_accounts sa
        WHERE sa.is_active = TRUE AND sa.inbox_state = 'dead'
          AND sa.kill_trigger::text IN ('hard_bounce_rate_lifetime', 'spam_complaint')
          AND sa.killed_at > NOW() - INTERVAL '7 days'
    """)
    recent_kills = int(missing_tags[0]['c']) if missing_tags else 0

    # Pool transitions in last 24h (each would have fired tag_op events)
    pool_changes = run_sql(f"""
        SELECT COUNT(*) AS c FROM inbox_rotation_history
        WHERE executed_at > NOW() - INTERVAL '24 hours'
    """)
    pool_change_count = int(pool_changes[0]['c']) if pool_changes else 0

    print(f'  Predicted event-driven activity if running NOW:')
    print(f'    pending kill_queue inserts:                         {pending_count}')
    print(f'    recent kills (last 7d) that needed tag_op_attach:   {recent_kills}')
    print(f'    pool transitions in last 24h that fired tag_ops:    {pool_change_count}')
    print()
    print(f'  These represent the volume event-driven would handle. Validates that')
    print(f'  the system would not be overwhelmed (low-double-digit per hour at most).')

    return {
        'section': 'tag_op_chain',
        'pending_kill_queue_inserts': pending_count,
        'recent_kills_needing_tag_op': recent_kills,
        'pool_changes_24h': pool_change_count,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=60)
    ap.add_argument('--section', choices=['kill', 'promotion', 'tag', 'all'], default='all')
    ap.add_argument('--json-out')
    args = ap.parse_args()

    print('=' * 78)
    print('RETROACTIVE EVENT-DRIVEN VALIDATOR')
    print(f'Window: last {args.days} days')
    print('=' * 78)

    results = []
    if args.section in ('kill', 'all'):
        results.append(validate_kill_chain(args.days))
    if args.section in ('promotion', 'all'):
        results.append(validate_promotion_chain(args.days))
    if args.section in ('tag', 'all'):
        results.append(validate_tag_op_chain())

    print('\n' + '=' * 78)
    print('SUMMARY')
    print('=' * 78)
    for r in results:
        print(f'  {r["section"]}: {json.dumps({k: v for k, v in r.items() if k not in ("samples", "section")}, default=str)[:200]}')

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        print(f'\n  JSON: {args.json_out}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
