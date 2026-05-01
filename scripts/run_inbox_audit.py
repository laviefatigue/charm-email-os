#!/usr/bin/env python3
"""
run_inbox_audit.py — operator CLI for the per-workspace inbox audit.

Phase 2 of the inbox-audit-overhaul. Invokes sync_modules/inbox_auditor.py
to produce a per-workspace audit, persist to inbox_audits, and print a
human-readable summary.

Usage
─────
    py scripts/run_inbox_audit.py --workspace Charm
    py scripts/run_inbox_audit.py --all
    py scripts/run_inbox_audit.py --all --print-only   # don't persist

Exit codes:
  0  — audits ran successfully (regardless of section severity)
  1  — workspace not found / DB connection failure
  2  — partial — at least one workspace failed audit

Requires DATABASE_URL env var (postgres connection string). For local
ops, pull from Coolify env: `py scripts/coolify.py env-list emailbison-sync`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg

# Make sync_modules importable when run from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from sync_modules.inbox_auditor import InboxAuditor


async def _connect_db() -> asyncpg.Pool:
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print('ERROR: DATABASE_URL not set', file=sys.stderr)
        sys.exit(1)
    return await asyncpg.create_pool(db_url, min_size=1, max_size=2)


async def _list_active_workspaces(pool: asyncpg.Pool) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, workspace_name FROM workspaces "
            "WHERE is_active = TRUE ORDER BY workspace_name"
        )
    return [{'id': r['id'], 'name': r['workspace_name']} for r in rows]


async def _resolve_workspace(pool: asyncpg.Pool, name_or_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, workspace_name FROM workspaces "
            "WHERE workspace_name = $1 AND is_active = TRUE",
            name_or_id,
        )
    if row:
        return {'id': row['id'], 'name': row['workspace_name']}
    return None


async def _audit_one(
    auditor: InboxAuditor, workspace: dict, persist: bool, json_out: bool
) -> int:
    try:
        result = await auditor.audit_workspace(workspace['id'])
    except Exception as e:
        print(f"  [{workspace['name']}] FAILED: {e!r}", file=sys.stderr)
        return 1

    if json_out:
        print(json.dumps(result.to_audit_data(), indent=2, default=str))
    else:
        print(f"\n{result.summary()}")
        print(f"  inboxes in scope: {len(result.inbox_id_set)}")
        for section in result.sections:
            marker = {'critical': '🔴', 'warn': '🟡', 'info': '🟢'}.get(section.severity, '⚪')
            print(f"  {marker} {section.code:5} {section.name:50} count={section.count}")
            if section.count > 0 and section.sample_ids:
                print(f"          sample: {', '.join(section.sample_ids[:3])}")

    if persist:
        try:
            audit_id = await auditor.persist(result)
            print(f"  Persisted as inbox_audits.id={audit_id}")
        except Exception as e:
            print(f"  PERSIST FAILED: {e!r}", file=sys.stderr)
            return 1

    return 0


async def main_async():
    p = argparse.ArgumentParser(description='Per-workspace inbox audit (Phase 2 of overhaul).')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--workspace', help='workspace_name (case-sensitive)')
    g.add_argument('--all', action='store_true', help='run for all 11 active workspaces')
    p.add_argument('--print-only', action='store_true',
                   help='do NOT persist to inbox_audits, just print result')
    p.add_argument('--json', action='store_true',
                   help='emit raw JSON instead of human-readable summary')
    args = p.parse_args()

    pool = await _connect_db()
    auditor = InboxAuditor(pool)
    persist = not args.print_only

    try:
        if args.all:
            workspaces = await _list_active_workspaces(pool)
            print(f'Auditing {len(workspaces)} active workspaces...')
            failures = 0
            for ws in workspaces:
                if await _audit_one(auditor, ws, persist, args.json) != 0:
                    failures += 1
            print(f'\nDone. {len(workspaces) - failures} of {len(workspaces)} succeeded.')
            return 2 if failures > 0 else 0
        else:
            ws = await _resolve_workspace(pool, args.workspace)
            if ws is None:
                print(f"ERROR: workspace {args.workspace!r} not found or inactive", file=sys.stderr)
                return 1
            return await _audit_one(auditor, ws, persist, args.json)
    finally:
        await pool.close()


if __name__ == '__main__':
    sys.exit(asyncio.run(main_async()))
