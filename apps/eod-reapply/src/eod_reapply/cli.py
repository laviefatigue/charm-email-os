"""CLI entrypoint for the EOD reapply tool.

Operator runs this on demand for a single (workspace, campaign) pair. Default
behavior is dry-run; mutation requires explicit --apply.

Exit codes:
    0 — success: campaign senders match target, OR no-diff fast path, OR
        skipped because campaign isn't active / time gate not open (no-op).
    1 — dry-run completed and would have made changes. Operator review required.
    2 — failure, but campaign was NOT left in a degraded state.
    3 — CRITICAL: campaign may be left paused. OPERATOR ACTION REQUIRED.

The exit code is the load-bearing signal for any future scheduler. Stdout is
human-readable + machine-readable JSON summary.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import click

from .db import fetch_workspace_context
from .eb_client import EBClient
from .reapply import ReapplyResult, ReapplyStatus, reapply_campaign


# Status → exit code mapping. Single source of truth.
_EXIT_CODE_BY_STATUS = {
    ReapplyStatus.SUCCEEDED:                0,
    ReapplyStatus.SKIPPED_NO_DIFF:          0,
    ReapplyStatus.SKIPPED_NOT_ACTIVE:       0,
    ReapplyStatus.SKIPPED_TIME_GATE:        0,
    ReapplyStatus.SKIPPED_DRY_RUN:          1,  # changes detected, awaiting --apply
    ReapplyStatus.SKIPPED_EMPTY_LIVE:       2,
    ReapplyStatus.SKIPPED_OVERSIZED_REMOVAL: 2,
    ReapplyStatus.FAILED_PRE_PAUSE:         2,
    ReapplyStatus.FAILED_POST_RESUME:       2,
    ReapplyStatus.FAILED_LEFT_PAUSED:       3,
}


def exit_code_for(status: ReapplyStatus) -> int:
    return _EXIT_CODE_BY_STATUS[status]


def render_summary(result: ReapplyResult) -> str:
    """Human-readable single-block summary."""
    lines = []
    lines.append("=" * 72)
    lines.append(f"REAPPLY RESULT — {result.workspace_name} / campaign #{result.campaign_id}")
    lines.append("=" * 72)
    lines.append(f"  status:        {result.status.value}")
    lines.append(f"  dry_run:       {result.is_dry_run}")
    lines.append(f"  target set:    {len(result.target_set)} senders {result.target_set if len(result.target_set) <= 10 else '[...]'}")
    lines.append(f"  prior set:     {len(result.prior_set)} senders {result.prior_set if len(result.prior_set) <= 10 else '[...]'}")
    lines.append(f"  to attach:     {len(result.attached_ids)} {result.attached_ids}")
    lines.append(f"  to remove:     {len(result.removed_ids)} {result.removed_ids}")
    if result.final_set:
        lines.append(f"  final set:     {len(result.final_set)} senders {result.final_set if len(result.final_set) <= 10 else '[...]'}")
    if result.verify_passed is not None:
        lines.append(f"  verify_passed: {result.verify_passed}")
    if result.error_step:
        lines.append(f"  error_step:    {result.error_step}")
    if result.error_message:
        lines.append(f"  error:         {result.error_message}")
    lines.append("=" * 72)
    if result.operator_action_required:
        lines.append("")
        lines.append("!!! OPERATOR ACTION REQUIRED !!!")
        lines.append("Campaign may be paused. Verify status in EB UI and resume manually.")
        lines.append("")
    return "\n".join(lines)


def render_json(result: ReapplyResult) -> str:
    d = asdict(result)
    d["status"] = result.status.value
    d["operator_action_required"] = result.operator_action_required
    return json.dumps(d, indent=2, default=str)


async def _async_run(
    *,
    database_url: str,
    eb_base_url: str,
    workspace_name: str,
    campaign_id: int,
    live_tag_name: str,
    apply_changes: bool,
    skip_time_check: bool,
    buffer_minutes: int,
    min_target_size: int,
    max_removal_pct: float,
) -> ReapplyResult:
    conn = await asyncpg.connect(database_url)
    try:
        ctx = await fetch_workspace_context(conn, workspace_name)
    finally:
        await conn.close()

    if ctx is None:
        click.echo(
            f"ERROR: workspace {workspace_name!r} not found, inactive, or missing API key",
            err=True,
        )
        # Synthesize a result so the caller can format/exit consistently.
        return ReapplyResult(
            status=ReapplyStatus.FAILED_PRE_PAUSE,
            campaign_id=campaign_id,
            workspace_name=workspace_name,
            error_step="workspace_lookup",
            error_message=f"workspace {workspace_name!r} not found / no active key",
            is_dry_run=not apply_changes,
        )

    async with EBClient(base_url=eb_base_url, api_key=ctx.api_key) as eb:
        return await reapply_campaign(
            eb=eb,
            workspace_name=ctx.workspace_name,
            campaign_id=campaign_id,
            live_tag_name=live_tag_name,
            apply=apply_changes,
            skip_time_check=skip_time_check,
            buffer_minutes=buffer_minutes,
            now_utc=datetime.now(timezone.utc),
            last_run_local_date=None,  # v1: operator-driven, no DB-side idempotency
            min_target_size=min_target_size,
            max_removal_pct=max_removal_pct,
        )


@click.group()
def main() -> None:
    """EOD campaign sender-tag reapply tool."""


@main.command()
@click.option("--workspace", "workspace_name", required=True, help="Workspace name (matches workspaces.workspace_name)")
@click.option("--campaign-id", type=int, required=True, help="EmailBison campaign id (numeric)")
@click.option("--live-tag", "live_tag_name", default="live", show_default=True, help="Tag name to filter senders")
@click.option("--apply", "apply_changes", is_flag=True, default=False, help="Actually mutate. Without this flag, runs as dry-run.")
@click.option("--skip-time-check", is_flag=True, default=False, help="Bypass the EOD time gate. USE CAREFULLY.")
@click.option("--buffer-minutes", type=int, default=60, show_default=True, help="Minutes after end_time before reapply may fire")
@click.option("--min-target-size", type=int, default=1, show_default=True, help="Refuse if live set has fewer senders than this")
@click.option("--max-removal-pct", type=float, default=50.0, show_default=True, help="Refuse if removing more than this % of current senders")
@click.option("--database-url", envvar="DATABASE_URL", help="Postgres URL (or env DATABASE_URL)")
@click.option("--eb-base-url", envvar="EMAILBISON_API_URL", default="https://spellcast.hirecharm.com/api", show_default=True, help="EB API base URL (or env EMAILBISON_API_URL)")
@click.option("--json-only", is_flag=True, default=False, help="Print only the JSON result (for scripting)")
def reapply(
    workspace_name: str,
    campaign_id: int,
    live_tag_name: str,
    apply_changes: bool,
    skip_time_check: bool,
    buffer_minutes: int,
    min_target_size: int,
    max_removal_pct: float,
    database_url: Optional[str],
    eb_base_url: str,
    json_only: bool,
) -> None:
    """Reapply the live tag set as the campaign's sender attachment."""
    if not database_url:
        click.echo("ERROR: --database-url or DATABASE_URL env var is required", err=True)
        sys.exit(2)

    if skip_time_check:
        click.echo("WARNING: --skip-time-check bypasses the EOD time gate", err=True)

    if apply_changes:
        click.echo("MODE: APPLY (will mutate EB state)", err=True)
    else:
        click.echo("MODE: DRY-RUN (no mutations; pass --apply to execute)", err=True)

    result = asyncio.run(_async_run(
        database_url=database_url,
        eb_base_url=eb_base_url,
        workspace_name=workspace_name,
        campaign_id=campaign_id,
        live_tag_name=live_tag_name,
        apply_changes=apply_changes,
        skip_time_check=skip_time_check,
        buffer_minutes=buffer_minutes,
        min_target_size=min_target_size,
        max_removal_pct=max_removal_pct,
    ))

    if json_only:
        click.echo(render_json(result))
    else:
        click.echo(render_summary(result))
        click.echo("")
        click.echo("JSON:")
        click.echo(render_json(result))

    sys.exit(exit_code_for(result.status))


if __name__ == "__main__":
    main()
