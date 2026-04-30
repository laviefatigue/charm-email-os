"""CLI entrypoint for incubation-watcher.

Subcommands:

  check    Read-only diagnostic. Lists candidates eligible for graduation
           in a single workspace. No writes.

  run      Process a single workspace. By default `--apply=False` — same as
           check, just with the orchestrator path exercised. `--apply` flips
           to real writes (EB tag + DB transition + rotation history).

  daemon   (Future, v2) Continuous loop across all active workspaces.

Exit codes:
  check:    0 = listed (regardless of count)     | 2 = config / connection error
  run:      0 = success (counts in stdout)       | 1 = transient failures (retry next cycle)
                                                 | 2 = orphan skipped (EB workspace mismatch)
                                                 | 3 = config / connection error

Env vars:
  DATABASE_URL              postgres connection string  [required]
  EMAILBISON_API_URL        EB base URL                 [default: https://spellcast.hirecharm.com/api]
  LOG_LEVEL                 INFO | DEBUG | WARNING       [default: INFO]
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections import Counter
from typing import Any

import asyncpg
import click

from . import __version__
from .db import (
    INCUBATION_BUSINESS_DAYS,
    fetch_graduation_candidates,
    fetch_workspace_context,
)
from .eb_client import EBClient, EmailBisonAPIError
from .graduator import (
    INCUBATING_TAG,
    LIVE_TAG,
    RESERVE_TAG,
    GraduationResult,
    graduate_one,
)

DEFAULT_EB_BASE = "https://spellcast.hirecharm.com/api"


def _setup_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


@click.group()
@click.version_option(__version__)
def main() -> None:
    """Incubation Watcher — per-workspace incubation graduation daemon."""
    _setup_logging()


@main.command("check")
@click.option("--workspace", required=True, help="Workspace name (case-sensitive)")
def check(workspace: str) -> None:
    """List inboxes eligible for graduation in WORKSPACE. Read-only."""
    sys.exit(asyncio.run(_run_check(workspace)))


@main.command("run")
@click.option("--workspace", required=True, help="Workspace name (case-sensitive)")
@click.option("--apply", is_flag=True, default=False, help="Mutate EB + DB. Without this, dry-run only.")
def run(workspace: str, apply: bool) -> None:
    """Process WORKSPACE: graduate eligible inboxes (dry-run by default)."""
    sys.exit(asyncio.run(_run_workspace(workspace, apply=apply)))


async def _connect_db() -> asyncpg.Pool:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise click.ClickException("DATABASE_URL not set")
    return await asyncpg.create_pool(db_url, min_size=1, max_size=2)


async def _run_check(workspace: str) -> int:
    pool = await _connect_db()
    try:
        async with pool.acquire() as conn:
            ctx = await fetch_workspace_context(conn, workspace)
            if ctx is None:
                click.echo(f"[FAIL] workspace {workspace!r} not found, inactive, or has no API key", err=True)
                return 2
            candidates = await fetch_graduation_candidates(conn, ctx.workspace_id)
        click.echo(f"workspace={ctx.workspace_name} eb_workspace_id={ctx.emailbison_workspace_id}")
        click.echo(f"eligible_for_graduation={len(candidates)} (>= {INCUBATION_BUSINESS_DAYS} business days)")
        for c in candidates:
            click.echo(
                f"  {c.email_address:<55} "
                f"esp={c.esp or '-':<10} "
                f"warmup_since={c.warmup_enabled_since_iso} "
                f"bd_elapsed={c.business_days_elapsed}"
            )
        return 0
    finally:
        await pool.close()


async def _run_workspace(workspace: str, *, apply: bool) -> int:
    pool = await _connect_db()
    eb_base = os.environ.get("EMAILBISON_API_URL", DEFAULT_EB_BASE)

    results: list[GraduationResult] = []
    try:
        async with pool.acquire() as conn:
            ctx = await fetch_workspace_context(conn, workspace)
            if ctx is None:
                click.echo(f"[FAIL] workspace {workspace!r} not found, inactive, or has no API key", err=True)
                return 3
            candidates = await fetch_graduation_candidates(conn, ctx.workspace_id)

        if not candidates:
            click.echo(f"workspace={ctx.workspace_name}: 0 candidates — nothing to do")
            return 0

        async with EBClient(base_url=eb_base, api_key=ctx.api_key) as eb:
            # Resolve tag IDs once per run.
            try:
                incubating_tag_id = await eb.get_or_create_tag_id(INCUBATING_TAG)
                live_tag_id = await eb.get_or_create_tag_id(LIVE_TAG)
                reserve_tag_id = await eb.get_or_create_tag_id(RESERVE_TAG)
            except EmailBisonAPIError as e:
                click.echo(f"[FAIL] tag resolution: {e}", err=True)
                return 3

            click.echo(
                f"workspace={ctx.workspace_name} candidates={len(candidates)} "
                f"apply={apply} incubating={incubating_tag_id} live={live_tag_id} reserve={reserve_tag_id}"
            )

            async with pool.acquire() as conn:
                for c in candidates:
                    res = await graduate_one(
                        db_conn=conn,
                        eb=eb,
                        workspace_id=ctx.workspace_id,
                        candidate=c,
                        incubating_tag_id=incubating_tag_id,
                        live_tag_id=live_tag_id,
                        reserve_tag_id=reserve_tag_id,
                        apply=apply,
                    )
                    results.append(res)

        # Summary
        outcomes: Counter[str] = Counter(r.outcome for r in results)
        click.echo(f"\nresult: {dict(outcomes)}")
        for r in results:
            marker = {
                "graduated": "[OK]",
                "dry_run": "[DRY]",
                "orphan_skipped": "[ORPHAN]",
                "transient_failed": "[FAIL]",
            }.get(r.outcome, "[?]")
            extra = f" reason={r.error}" if r.error else ""
            click.echo(f"  {marker:<10} {r.candidate.email_address:<55} -> {r.target_pool}{extra}")

        # Exit code mapping
        if outcomes.get("transient_failed", 0) > 0:
            return 1
        if outcomes.get("orphan_skipped", 0) > 0:
            return 2
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":  # pragma: no cover
    main()


# Stub for typing — `main` is referenced as a callable from pyproject.scripts.
_: Any = main
