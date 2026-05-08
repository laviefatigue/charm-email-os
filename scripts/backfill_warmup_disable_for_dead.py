"""
One-shot backfill: enqueue warmup_disable events for existing dead
inboxes that still have warmup_enabled=TRUE.

Plan F context:
  Audit on 2026-05-08 found 624 dead inboxes with warmup_enabled=TRUE
  in the DB, and 318 of them had received bounces AFTER they were killed.
  Some had been killed in February and were still bouncing in May. The
  kill cascade (pre-Plan F) wasn't disabling warmup, so EB's warmup
  daemon kept sending mail from dead infrastructure.

What this script does:
  1. SELECT all sender_accounts where inbox_state='dead' AND
     warmup_enabled=TRUE AND emailbison_account_id IS NOT NULL AND
     workspace_id IS NOT NULL (NOT NULL is required by migration 109's
     CHECK constraint).
  2. UPDATE sender_accounts SET warmup_enabled=FALSE for those rows.
  3. INSERT one warmup_disable event into event_log per inbox.
  4. The next Tier 2 TagOpWorker cycle drains them via per-workspace
     bulk EB API calls (PATCH /warmup/sender-emails/disable).

Idempotent:
  - Re-running is safe; rows already with warmup_enabled=FALSE are skipped.
  - The Tier 2 worker is itself idempotent (calling EB to disable
    already-disabled warmup is a 200 OK no-op).

Read-only flag (--dry-run):
  Default mode does NOT mutate anything. Pass --apply to actually
  UPDATE the DB rows and INSERT the events. Always run --dry-run first
  on production to see what would be touched.

Usage:
  py scripts/backfill_warmup_disable_for_dead.py            # dry-run
  py scripts/backfill_warmup_disable_for_dead.py --apply    # mutate
"""
import argparse
import asyncio
import os
import sys

import asyncpg


async def run(*, apply: bool) -> int:
    db_dsn = os.environ.get('DATABASE_URL')
    if not db_dsn:
        # Local-dev defaults match docker-compose.local.yml
        db_dsn = (
            f"postgres://"
            f"{os.environ.get('POSTGRES_USER', 'postgres')}:"
            f"{os.environ.get('POSTGRES_PASSWORD', 'localdevpassword')}"
            f"@{os.environ.get('POSTGRES_HOST', 'localhost')}:"
            f"{os.environ.get('POSTGRES_PORT', '5433')}/"
            f"{os.environ.get('POSTGRES_DB', 'postgres')}"
        )

    pool = await asyncpg.create_pool(db_dsn, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            target = await conn.fetch(
                """
                SELECT
                    sa.id              AS inbox_id,
                    sa.email_address,
                    sa.workspace_id,
                    sa.emailbison_account_id,
                    sa.killed_at,
                    sa.kill_trigger::text AS kill_trigger
                FROM sender_accounts sa
                JOIN workspaces w ON w.id = sa.workspace_id
                WHERE sa.inbox_state = 'dead'
                  AND sa.warmup_enabled = TRUE
                  AND sa.emailbison_account_id IS NOT NULL
                  AND sa.workspace_id IS NOT NULL
                  AND sa.is_active = TRUE
                  AND w.is_active = TRUE
                ORDER BY sa.killed_at DESC
                """
            )
        print(f"Targets: {len(target)} dead inboxes with warmup_enabled=TRUE")
        if not target:
            print("Nothing to do.")
            return 0

        # Per-workspace breakdown for visibility
        per_ws = {}
        for r in target:
            per_ws[r['workspace_id']] = per_ws.get(r['workspace_id'], 0) + 1
        print()
        print("Per-workspace breakdown:")
        async with pool.acquire() as conn:
            for ws_id, count in sorted(per_ws.items(), key=lambda x: -x[1]):
                name = await conn.fetchval(
                    "SELECT workspace_name FROM workspaces WHERE id = $1", ws_id
                )
                print(f"  {name:<40} {count}")

        if not apply:
            print()
            print("Dry-run — no DB mutations. Pass --apply to mutate.")
            return 0

        # Apply: UPDATE sender_accounts + INSERT into event_log per inbox
        # Wrap in a transaction so a partial failure doesn't leave drift
        # between the warmup_enabled flip and the event_log row.
        async with pool.acquire() as conn:
            async with conn.transaction():
                updated_n = await conn.fetchval(
                    """
                    UPDATE sender_accounts
                    SET warmup_enabled = FALSE,
                        updated_at = NOW()
                    WHERE id = ANY($1::uuid[])
                      AND warmup_enabled = TRUE
                      AND inbox_state = 'dead'
                    """,
                    [r['inbox_id'] for r in target],
                )
                # asyncpg returns the COMMAND TAG ('UPDATE N') from execute,
                # but fetchval returns NULL. Re-count by querying.
                updated_count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM sender_accounts
                    WHERE id = ANY($1::uuid[])
                      AND warmup_enabled = FALSE
                      AND inbox_state = 'dead'
                    """,
                    [r['inbox_id'] for r in target],
                )

                # INSERT one warmup_disable event per inbox.
                # Skip inboxes that already have a pending warmup_disable
                # to avoid stacking duplicates if this script is run twice.
                inserted = 0
                for r in target:
                    existing = await conn.fetchval(
                        """
                        SELECT 1 FROM event_log
                        WHERE event_type = 'warmup_disable'
                          AND entity_id = $1
                          AND status IN ('pending', 'processing')
                        LIMIT 1
                        """,
                        r['inbox_id'],
                    )
                    if existing:
                        continue
                    payload = (
                        '{"inbox_id":"%s",'
                        '"backfill_source":"backfill_warmup_disable_for_dead"}'
                        % str(r['inbox_id'])
                    )
                    await conn.execute(
                        """
                        INSERT INTO event_log (
                            event_type, entity_type, entity_id,
                            payload, status, workspace_id
                        ) VALUES (
                            'warmup_disable', 'inbox', $1,
                            $2::jsonb, 'pending', $3
                        )
                        """,
                        r['inbox_id'], payload, r['workspace_id'],
                    )
                    inserted += 1

        print()
        print(f"Applied: {updated_count} rows flipped to warmup_enabled=FALSE")
        print(f"Applied: {inserted} warmup_disable events inserted (status=pending)")
        print()
        print("Tier 2 TagOpWorker will drain these on its next cycle (~30 min).")
        print("Watch sync_audit_log WHERE sync_type='tag_op_drain' to confirm.")
        return 0

    finally:
        await pool.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    parser.add_argument(
        '--apply', action='store_true',
        help='Actually mutate the DB. Default is dry-run.',
    )
    args = parser.parse_args()
    return asyncio.run(run(apply=args.apply))


if __name__ == '__main__':
    sys.exit(main())
