"""Cron-mode audit_drift entrypoint. Phase 1 = a thin wrapper that runs the
full-fleet audit and writes summary to sync_audit_log.

Phase 2 will broaden this to a true job processor that claims rows from
hypertide_jobs (job_type='audit_drift'). For Phase 1 it's invoked directly
by the daily Coolify cron.
"""
from __future__ import annotations

import logging

from ..audit import run_audit
from ..config import Config
from ..db import connect
from ..ht_client import HypertideClient

logger = logging.getLogger(__name__)


async def run() -> None:
    cfg = Config.from_env()
    conn = await connect(cfg.database_url)
    try:
        async with HypertideClient(cfg.hypertide_api_url, cfg.hypertide_api_key) as ht:
            result = await run_audit(conn, ht, apply=True)
        logger.info(
            "audit_drift complete: matched=%d (%.1f%%) friends_family=%d incoming=%d "
            "db_only=%d to_be_cancelled=%d ht_cancelled_eb_connected=%d",
            result.matched,
            result.parity_pct,
            result.ht_friends_and_family,
            result.ht_incoming_count,
            result.db_only,
            result.drift_to_be_cancelled,
            result.drift_ht_cancelled_inboxes_connected,
        )
    finally:
        await conn.close()
