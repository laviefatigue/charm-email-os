"""
Pool Promotion — domain-aware reserve→deployed selection and execution.

One module shared by:
  - kill_processor._promote_backup_inbox (kill-driven, n=1)
  - WorkspaceWriteOrchestrator._maintain_pool_thresholds (threshold-driven, n=deficit)

Promotion selection rules (in priority order)
─────────────────────────────────────────────
1. Partially-tapped reserve domains first.
   A "tapped" reserve domain is one where SOME of its graduated Google inboxes
   are already deployed AND others are still reserve. We finish these domains
   before opening a new one — the operational hygiene principle is "if you've
   started consuming a domain, finish it" so the live pool stays as
   homogeneous-by-domain as possible. Within tier 1, order by domains with
   the FEWEST remaining reserves first (closest to fully promoted).

2. Untapped reserve domains second.
   Domains where all graduated Google inboxes are still reserve. Order by
   the OLDEST warmup_enabled_since on the domain — most established sender
   reputation goes first.

3. Within a domain, the OLDEST reserve inbox wins.

Microsoft is excluded from promotion entirely (legacy ride-to-death).

Every transition writes a row to inbox_rotation_history with rotation_type
matching the trigger ('promote' for kill-replacement, 'threshold_promotion'
for proactive maintenance, 'manual_override' for admin actions).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


async def pick_promotion_candidates(
    db: asyncpg.Pool,
    workspace_id: UUID,
    n: int,
) -> List[asyncpg.Record]:
    """
    Pick up to `n` reserve Google inboxes to promote to deployed, ordered by
    the domain-aware policy described in the module docstring.

    Filters:
      - esp = 'gmail'                       (Microsoft is ride-to-death; not eligible)
      - is_active = TRUE
      - inbox_state = 'live'
      - status = 'Connected'                (disconnected can't actually send)
      - inventory_pool_status = 'reserve'
      - inventory_lifecycle_status = 'active'
      - domain.pool_status NOT IN ('burned', 'cancelled')

    Returns asyncpg Records with at minimum: id, email_address, domain_id,
    domain_name, warmup_enabled_since.
    """
    if n <= 0:
        return []

    return await db.fetch("""
        WITH domain_state AS (
            SELECT
                d.id                           AS domain_id,
                d.domain_name,
                d.pool_status                  AS domain_pool_status,
                COUNT(*) FILTER (
                    WHERE sa.inventory_pool_status = 'live'
                )                              AS deployed_count,
                COUNT(*) FILTER (
                    WHERE sa.inventory_pool_status = 'reserve'
                )                              AS reserve_count,
                MIN(sa.warmup_enabled_since) FILTER (
                    WHERE sa.inventory_pool_status = 'reserve'
                )                              AS oldest_reserve_warmup
            FROM domains d
            JOIN sender_accounts sa ON sa.domain_id = d.id
            WHERE d.workspace_id = $1
              AND sa.esp = 'gmail'
              AND sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.status = 'Connected'
              AND sa.inventory_lifecycle_status = 'active'
              AND d.pool_status NOT IN ('burned', 'cancelled')
            GROUP BY d.id, d.domain_name, d.pool_status
            HAVING COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve') > 0
        )
        SELECT
            sa.id,
            sa.email_address,
            sa.domain_id,
            ds.domain_name,
            sa.warmup_enabled_since,
            ds.deployed_count,
            ds.reserve_count
        FROM sender_accounts sa
        JOIN domain_state ds ON sa.domain_id = ds.domain_id
        WHERE sa.inventory_pool_status = 'reserve'
          AND sa.esp = 'gmail'
          AND sa.is_active = TRUE
          AND sa.inbox_state = 'live'
          AND sa.status = 'Connected'
          AND sa.inventory_lifecycle_status = 'active'
        ORDER BY
            -- Tier 1: partially-tapped domains first
            CASE WHEN ds.deployed_count > 0 THEN 0 ELSE 1 END,
            -- Within tier 1: closest to finished (fewest remaining reserves) first
            ds.reserve_count ASC,
            -- Within tier 2: oldest domain warmup first
            ds.oldest_reserve_warmup ASC NULLS LAST,
            -- Within a domain: oldest inbox first
            sa.warmup_enabled_since ASC NULLS LAST,
            sa.id  -- deterministic tiebreaker
        LIMIT $2
    """, workspace_id, n)


async def promote_inbox_to_deployed(
    db: asyncpg.Pool,
    inbox_id: UUID,
    workspace_id: UUID,
    reason: str,
    triggered_by: str,
    rotation_type: str = 'promote',
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Promote a single inbox: set inventory_pool_status='live' AND log to
    inbox_rotation_history. Returns True if the row was promoted, False if
    it was already deployed (no-op) or the inbox doesn't exist.

    The DB UPDATE and the audit INSERT happen in a single transaction so we
    cannot end up with a promotion that lacks a history row (or vice versa).

    set_tag_sync's verified write loop applies the EB tag in the next
    cycle by reading the per-inbox `inventory_pool_status` as authority.

    Args:
        rotation_type: 'promote' for kill-driven, 'threshold_promotion' for
                       proactive maintenance, 'manual_override' for admin actions
        triggered_by:  'kill_processor' | 'orchestrator' | 'admin_api' | etc.
        metadata:      arbitrary JSON context (target_count, deficit, etc.)
    """
    async with db.acquire() as conn:
        async with conn.transaction():
            # Read current state inside the transaction so we don't double-promote.
            row = await conn.fetchrow("""
                SELECT id, email_address, domain_id, inventory_pool_status
                FROM sender_accounts
                WHERE id = $1
                FOR UPDATE
            """, inbox_id)

            if row is None:
                logger.warning("[pool_promotion] inbox %s not found", inbox_id)
                return False

            if row['inventory_pool_status'] == 'live':
                logger.debug(
                    "[pool_promotion] inbox %s (%s) already deployed; skipping",
                    inbox_id, row['email_address'],
                )
                return False

            from_pool = row['inventory_pool_status']

            await conn.execute("""
                UPDATE sender_accounts
                SET inventory_pool_status = 'live',
                    updated_at = NOW()
                WHERE id = $1
            """, inbox_id)

            await conn.execute("""
                INSERT INTO inbox_rotation_history (
                    workspace_id, rotation_type,
                    target_inbox_id, target_inbox_email,
                    source_pool, target_pool,
                    reason, triggered_by,
                    success, executed_at, metadata
                ) VALUES (
                    $1, $2,
                    $3, $4,
                    $5, 'live',
                    $6, $7,
                    TRUE, NOW(), $8::jsonb
                )
            """,
                workspace_id, rotation_type,
                inbox_id, row['email_address'],
                from_pool,
                reason, triggered_by,
                json.dumps(metadata or {}),
            )

    logger.info(
        "[pool_promotion] %s: %s %s -> deployed (reason: %s)",
        rotation_type, row['email_address'], from_pool, reason,
    )
    return True


async def count_pool_state(
    db: asyncpg.Pool,
    workspace_id: UUID,
    pool: str,
    esp: str = 'gmail',
) -> int:
    """
    Count Google inboxes in a given pool state for a workspace.
    Filters: is_active, inbox_state='live', status='Connected'.
    Used by the orchestrator's threshold maintenance phase.
    """
    return await db.fetchval("""
        SELECT COUNT(*)
        FROM sender_accounts sa
        JOIN domains d ON sa.domain_id = d.id
        WHERE sa.workspace_id = $1
          AND sa.esp = $2
          AND sa.is_active = TRUE
          AND sa.inbox_state = 'live'
          AND sa.status = 'Connected'
          AND sa.inventory_pool_status = $3
          AND d.pool_status NOT IN ('burned', 'cancelled')
    """, workspace_id, esp, pool) or 0


async def count_pool_state_conn(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    pool: str,
    esp: str = 'gmail',
) -> int:
    """Same as count_pool_state but takes a Connection (for use inside handlers
    that already hold a pool-acquired conn). Avoids the double-acquire pattern."""
    return await conn.fetchval("""
        SELECT COUNT(*)
        FROM sender_accounts sa
        JOIN domains d ON sa.domain_id = d.id
        WHERE sa.workspace_id = $1
          AND sa.esp = $2
          AND sa.is_active = TRUE
          AND sa.inbox_state = 'live'
          AND sa.status = 'Connected'
          AND sa.inventory_pool_status = $3
          AND d.pool_status NOT IN ('burned', 'cancelled')
    """, workspace_id, esp, pool) or 0


async def promote_to_target(
    db: asyncpg.Pool,
    workspace_id: UUID,
    target_live_count: int,
    *,
    triggered_by: str = 'event_driven',
    rotation_type: str = 'threshold_promotion',
    reason: str = 'event_driven_threshold_fill',
) -> Dict[str, Any]:
    """Promote Google reserves until current_live reaches target_live_count.

    Single-row entry point shared by:
      - WorkspaceWriteOrchestrator._maintain_pool_thresholds (per-workspace
        polling cycle, every 60s)
      - sync_modules.event_handlers.kill_chain.inbox_died_handler (event-
        driven, fires immediately when an inbox dies)
      - sync_modules.event_handlers.workspace.package_assigned_handler
        (event-driven, fires when a workspace gets a package)

    Returns a dict with:
      'promoted'           — count of inboxes promoted (≤ deficit)
      'deficit_at_decision' — target - current_live at start
      'reserve_count'      — Google reserves available at start
      'no_candidates'      — True if deficit > 0 but pick returned empty

    Caller decides whether to alert on insufficient reserves
    (`no_candidates=True`). This function never alerts; it just promotes
    or no-ops.

    Per ADR-006: only Google inboxes are promoted (Microsoft is ride-to-
    death). pick_promotion_candidates handles that filter.
    """
    current_live = await count_pool_state(db, workspace_id, 'live', esp='gmail')
    deficit = target_live_count - current_live
    reserve_count = await count_pool_state(db, workspace_id, 'reserve', esp='gmail')

    if deficit <= 0:
        return {
            'promoted': 0, 'deficit_at_decision': deficit,
            'reserve_count': reserve_count, 'no_candidates': False,
        }

    candidates = await pick_promotion_candidates(db, workspace_id, deficit)
    if not candidates:
        return {
            'promoted': 0, 'deficit_at_decision': deficit,
            'reserve_count': reserve_count, 'no_candidates': True,
        }

    promoted = 0
    for cand in candidates:
        ok = await promote_inbox_to_deployed(
            db, cand['id'], workspace_id,
            reason=reason,
            triggered_by=triggered_by,
            rotation_type=rotation_type,
            metadata={
                'target_live_count': target_live_count,
                'deficit_at_decision': deficit,
                'domain_id': str(cand.get('domain_id')) if cand.get('domain_id') else None,
            },
        )
        if ok:
            promoted += 1

    return {
        'promoted': promoted, 'deficit_at_decision': deficit,
        'reserve_count': reserve_count, 'no_candidates': False,
    }


async def get_workspace_promotion_target(
    conn: asyncpg.Connection,
    workspace_id: UUID,
) -> Optional[int]:
    """Resolve a workspace's effective live target.

    Returns:
      target_live_count_override if set,
      else package.target_live_count,
      else None (no package = no proactive promotion).

    Honors workspace.pause_pool_transitions: returns None when paused.
    """
    row = await conn.fetchrow("""
        SELECT
            w.target_live_count_override,
            COALESCE(w.pause_pool_transitions, FALSE) AS paused,
            p.target_live_count AS package_target
        FROM workspaces w
        LEFT JOIN workspace_packages p ON p.id = w.package_id
        WHERE w.id = $1
    """, workspace_id)

    if not row or row['paused']:
        return None

    return row['target_live_count_override'] or row['package_target']
