"""Workspace config handlers (Phase 2).

  package_assigned_handler — workspace package_id flipped to non-NULL.
                              Phase 3 wires up _maintain_pool_thresholds()
                              call so the workspace doesn't have to wait
                              for the next polling cycle.

For Phase 2 (this commit), this is a stub. The polling cycle still does
the work (every 60s with our shortened cadence). When Phase 3 ships
process_one / promote_one extractions, this handler calls them directly
for sub-second response.

Plan: docs/plans/event-driven-architecture.md
"""
from __future__ import annotations

import json
import logging
from typing import Dict

import asyncpg

logger = logging.getLogger(__name__)


async def package_assigned_handler(event: Dict, conn: asyncpg.Connection) -> None:
    """Workspace got a new package_id. Fire promote_to_target immediately
    so the workspace doesn't wait a poll cycle to fill capacity.

    This is the same logic _maintain_pool_thresholds runs in the poll
    cycle — we just trigger it on package assignment so the operator
    gets immediate feedback after assigning a package (instead of
    "wait 60 seconds").
    """
    from uuid import UUID
    from sync_modules.pool_promotion import (
        get_workspace_promotion_target,
        promote_to_target,
    )

    payload = event['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)

    workspace_id = event.get('workspace_id') or payload.get('workspace_id')
    if isinstance(workspace_id, str):
        workspace_id = UUID(workspace_id)

    if not workspace_id:
        logger.warning("package_assigned: missing workspace_id, skip")
        return

    target = await get_workspace_promotion_target(conn, workspace_id)
    if target is None:
        # Package was assigned but workspace is paused, or override was already
        # set such that no proactive promotion fires.
        logger.info(
            "package_assigned: workspace %s has no effective target (paused or unset)",
            workspace_id,
        )
        return

    pool = conn._holder._pool if hasattr(conn, '_holder') else None
    if pool is None:
        logger.warning(
            "package_assigned: handler couldn't access pool from conn (test context?), "
            "polling will handle promotion"
        )
        return

    result = await promote_to_target(
        pool, workspace_id, target,
        triggered_by='event_driven_package_assigned',
        rotation_type='threshold_promotion',
        reason='package_assignment_initial_fill',
    )

    logger.info(
        "package_assigned: workspace %s package=%s, target=%d, promoted=%d "
        "(deficit_at_decision=%d, reserves_at_start=%d)",
        payload.get('workspace_name'), payload.get('new_package_id'),
        target, result['promoted'],
        result['deficit_at_decision'], result['reserve_count'],
    )
