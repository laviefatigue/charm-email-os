#!/usr/bin/env python3
"""
Day.AI Watcher Worker

Polls Day.AI for opportunities in configured "won" stages, diffs against
postgres state, and (when DETECT_ONLY=false) triggers client onboarding via
charm-api.

Architecture — matches the emailbison-sync pattern:
    Long-running process, internal asyncio poll loop, state in Postgres.
    Tables (migration 093): dayai_watcher_state, dayai_watcher_runs.

Modes:
    DETECT_ONLY=true  (default)  Observe + record. Never POSTs to charm-api.
                                 Used for the 1-2 week initial observation
                                 window to validate detection accuracy.
    DETECT_ONLY=false            Acts on transitions by POSTing newly-won
                                 opportunities to charm-api's /api/clients/
                                 pending-from-dayai. Requires CHARM_API_TOKEN.

Environment variables:
    DAY_AI_BASE_URL              Day.AI API base URL. Default: https://day.ai
    CLIENT_ID                    Day.AI OAuth client ID (required)
    CLIENT_SECRET                Day.AI OAuth client secret (required)
    REFRESH_TOKEN                Day.AI OAuth refresh token (required)
    WORKSPACE_ID                 Optional Day.AI workspace hint
    WATCHED_WON_STAGE_IDS        Comma-separated stage IDs to watch (required)
    POLL_INTERVAL_SECONDS        Seconds between polls. Default: 600 (10 min)
    POSTGRES_HOST                Required
    POSTGRES_PORT                Default: 5432
    POSTGRES_USER                Default: charm
    POSTGRES_PASSWORD            Required
    POSTGRES_DB                  Default: postgres
    CHARM_API_URL                Default: https://api.wizardgrimoire.cloud
    CHARM_API_TOKEN              Required ONLY when DETECT_ONLY=false
    DETECT_ONLY                  "true" or "false". Default: "true"
    LOG_LEVEL                    Default: info

Supersedes the Node-based HireCharm/dayai-watcher. See DECISION_dayai_python_module
in charm-kb for the rationale + retirement plan.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx

from dayai import DayAIClient, OpportunitySnapshot

logger = logging.getLogger("dayai_watcher")


# --- Configuration ----------------------------------------------------------

def _env(key: str, default: str | None = None, required: bool = False) -> str:
    v = os.getenv(key, default)
    if required and not v:
        raise RuntimeError(f"Missing required env var: {key}")
    return v or ""


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes", "on")


POLL_INTERVAL = int(_env("POLL_INTERVAL_SECONDS", "600"))
DETECT_ONLY = _bool("DETECT_ONLY", default=True)

POSTGRES_HOST = _env("POSTGRES_HOST", required=True)
POSTGRES_PORT = int(_env("POSTGRES_PORT", "5432"))
POSTGRES_USER = _env("POSTGRES_USER", "charm")
POSTGRES_PASSWORD = _env("POSTGRES_PASSWORD", required=True)
POSTGRES_DB = _env("POSTGRES_DB", "postgres")

CHARM_API_URL = _env("CHARM_API_URL", "https://api.wizardgrimoire.cloud")
CHARM_API_TOKEN = _env("CHARM_API_TOKEN", "")

WATCHED_WON_STAGE_IDS = [
    s.strip() for s in _env("WATCHED_WON_STAGE_IDS", "").split(",") if s.strip()
]


# --- Postgres state access --------------------------------------------------

async def start_run(pool: asyncpg.Pool) -> int:
    """Insert a new dayai_watcher_runs row, return its id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO dayai_watcher_runs (started_at)
            VALUES (NOW())
            RETURNING id
            """
        )
        return int(row["id"])


async def finish_run(
    pool: asyncpg.Pool,
    run_id: int,
    *,
    opportunities_seen: int,
    newly_won: int,
    sent_to_charm: int,
    errors: int,
    error_messages: list[str] | None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE dayai_watcher_runs SET
                ended_at           = NOW(),
                opportunities_seen = $2,
                newly_won          = $3,
                sent_to_charm      = $4,
                errors             = $5,
                error_messages     = $6
            WHERE id = $1
            """,
            run_id,
            opportunities_seen,
            newly_won,
            sent_to_charm,
            errors,
            error_messages,
        )


async def is_newly_won(pool: asyncpg.Pool, opp_id: str) -> bool:
    """Return True if this opp has never been recorded in dayai_watcher_state."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM dayai_watcher_state WHERE opp_id = $1", opp_id
        )
        return row is None


async def record_opp(
    pool: asyncpg.Pool, opp: OpportunitySnapshot, *, newly_won: bool
) -> None:
    """
    INSERT a new opp (first observation) or UPDATE last_poll_saw_at + snapshot
    on subsequent polls.

    Safe to call concurrently for different opp_ids; single-row UPSERT ensures
    no lost updates within a given opp.
    """
    async with pool.acquire() as conn:
        if newly_won:
            await conn.execute(
                """
                INSERT INTO dayai_watcher_state (opp_id, dayai_snapshot)
                VALUES ($1, $2::jsonb)
                ON CONFLICT (opp_id) DO UPDATE SET
                    last_poll_saw_at = NOW(),
                    dayai_snapshot    = EXCLUDED.dayai_snapshot
                """,
                opp.id,
                json.dumps(opp.to_jsonb()),
            )
        else:
            await conn.execute(
                """
                UPDATE dayai_watcher_state
                   SET last_poll_saw_at = NOW(),
                       dayai_snapshot    = $2::jsonb
                 WHERE opp_id = $1
                """,
                opp.id,
                json.dumps(opp.to_jsonb()),
            )


async def mark_sent_to_charm(
    pool: asyncpg.Pool, opp_id: str, charm_client_id: str
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE dayai_watcher_state
               SET sent_to_charm_at  = NOW(),
                   charm_client_id   = $2::uuid
             WHERE opp_id = $1
            """,
            opp_id,
            charm_client_id,
        )


# --- charm-api integration (DETECT_ONLY=false only) ------------------------

async def post_to_charm_api(
    http: httpx.AsyncClient, opp: OpportunitySnapshot
) -> str:
    """
    POST a newly-won opportunity to charm-api. Returns the created client UUID.

    Only called when DETECT_ONLY=false. The endpoint is planned for Gate 2;
    until it ships, this function will 404 and the caller will record the error.
    """
    if not CHARM_API_TOKEN:
        raise RuntimeError(
            "CHARM_API_TOKEN is required when DETECT_ONLY=false. Refusing to POST."
        )
    payload = {
        "dayai_opp_id": opp.id,
        "title": opp.title,
        "domain": opp.domain,
        "amount": opp.amount,
        "expected_close_date": opp.expected_close_date,
        "dayai_snapshot": opp.to_jsonb(),
    }
    resp = await http.post(
        f"{CHARM_API_URL.rstrip('/')}/api/clients/pending-from-dayai",
        json=payload,
        headers={
            "Authorization": f"Bearer {CHARM_API_TOKEN}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    body = resp.json()
    client_id = body.get("client_id")
    if not client_id:
        raise RuntimeError(f"charm-api response missing client_id: {body!r}")
    return str(client_id)


# --- Main poll cycle --------------------------------------------------------

async def run_once(
    dayai: DayAIClient, pool: asyncpg.Pool, http: httpx.AsyncClient
) -> None:
    """One full poll cycle: fetch, diff, record, optionally POST."""
    run_id = await start_run(pool)
    seen = 0
    newly_won = 0
    sent = 0
    errors = 0
    error_messages: list[str] = []

    try:
        logger.info(
            "poll start detect_only=%s stage_ids=%d",
            DETECT_ONLY,
            len(WATCHED_WON_STAGE_IDS),
        )
        opps = await dayai.list_opportunities_in_stages(WATCHED_WON_STAGE_IDS)
        seen = len(opps)

        for opp in opps:
            try:
                first_time = await is_newly_won(pool, opp.id)
                await record_opp(pool, opp, newly_won=first_time)

                if first_time:
                    newly_won += 1
                    if DETECT_ONLY:
                        logger.info(
                            "detected_would_post opp_id=%s title=%r domain=%s amount=%s",
                            opp.id,
                            opp.title,
                            opp.domain,
                            opp.amount,
                        )
                    else:
                        try:
                            client_id = await post_to_charm_api(http, opp)
                            await mark_sent_to_charm(pool, opp.id, client_id)
                            sent += 1
                            logger.info(
                                "posted_to_charm opp_id=%s charm_client_id=%s",
                                opp.id,
                                client_id,
                            )
                        except Exception as e:
                            errors += 1
                            msg = f"charm-api POST failed for opp {opp.id}: {e}"
                            error_messages.append(msg[:500])
                            logger.exception(msg)
            except Exception as e:
                errors += 1
                msg = f"processing opp {opp.id} failed: {e}"
                error_messages.append(msg[:500])
                logger.exception(msg)

        logger.info(
            "poll end seen=%d newly_won=%d sent_to_charm=%d errors=%d",
            seen,
            newly_won,
            sent,
            errors,
        )
    except Exception as e:
        errors += 1
        error_messages.append(f"poll cycle failed: {e}"[:500])
        logger.exception("poll cycle failed")
    finally:
        await finish_run(
            pool,
            run_id,
            opportunities_seen=seen,
            newly_won=newly_won,
            sent_to_charm=sent,
            errors=errors,
            error_messages=error_messages or None,
        )


# --- Main ------------------------------------------------------------------

async def main() -> int:
    level = os.getenv("LOG_LEVEL", "info").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)r}',
    )

    if not WATCHED_WON_STAGE_IDS:
        logger.error(
            "WATCHED_WON_STAGE_IDS is empty — worker has nothing to watch. Exiting."
        )
        return 2

    logger.info(
        "dayai-watcher starting detect_only=%s poll_interval=%ds stage_ids=%s",
        DETECT_ONLY,
        POLL_INTERVAL,
        WATCHED_WON_STAGE_IDS,
    )

    # Signal handling for clean shutdown (SIGTERM from Coolify stop)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                # Windows asyncio doesn't support signal handlers on ProactorEventLoop
                pass

    pool = await asyncpg.create_pool(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
        min_size=1,
        max_size=4,
        command_timeout=30,
    )
    if pool is None:
        logger.error("failed to create asyncpg pool")
        return 1

    async with DayAIClient.from_env() as dayai, httpx.AsyncClient() as http:
        # Sanity check: one whoami call so a broken config fails immediately
        # rather than after a long idle wait.
        try:
            identity = await dayai.whoami()
            logger.info("day.ai whoami: %s", _summarize_whoami(identity))
        except Exception:
            logger.exception("day.ai whoami failed — check OAuth credentials")
            await pool.close()
            return 1

        # One-shot support for manual runs (container overridden with --once)
        if "--once" in sys.argv:
            await run_once(dayai, pool, http)
            await pool.close()
            return 0

        while not stop.is_set():
            try:
                await run_once(dayai, pool, http)
            except Exception:
                logger.exception("unhandled exception in poll cycle; continuing")
            # Sleep until POLL_INTERVAL or shutdown signal, whichever is first.
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass

    logger.info("dayai-watcher shutting down")
    await pool.close()
    return 0


def _summarize_whoami(identity: dict[str, Any]) -> str:
    """Compact one-line summary of whoami for startup logs."""
    # Shape varies; just show top-level keys and obvious identifiers.
    keys = list(identity.keys())[:8]
    wid = identity.get("workspaceId") or identity.get("workspace_id")
    email = identity.get("email") or (identity.get("user") or {}).get("email")
    parts = []
    if wid:
        parts.append(f"workspace={wid}")
    if email:
        parts.append(f"user={email}")
    parts.append(f"keys={keys}")
    return " ".join(parts)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
