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
    """Workspace got a new package_id. Trigger threshold maintenance.

    Phase 2 stub: log only. Polling-based _maintain_pool_thresholds runs
    every 60s and will promote reserves to fill the deficit.

    Phase 3 will:
        from sync_modules.workspace_writes import maintain_pool_thresholds_one
        await maintain_pool_thresholds_one(conn, workspace_id)
    """
    payload = event['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)

    logger.info(
        "package_assigned: workspace %s got package %s "
        "(Phase 2 stub — promotion via 60s poll until Phase 3)",
        payload.get('workspace_name'), payload.get('new_package_id'),
    )
