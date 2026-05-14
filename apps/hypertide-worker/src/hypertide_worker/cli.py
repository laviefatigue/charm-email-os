"""CLI entrypoints. Single command per Phase 1 surface; Phase 2 adds daemon mode."""
from __future__ import annotations

import asyncio
import json
import logging
import sys

import click

from .audit import AuditResult, run_audit
from .backfill import BackfillResult, run_backfill
from .config import Config, ConfigError
from .db import connect
from .ht_client import HypertideClient

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)


@click.group()
def cli() -> None:
    """Hypertide reconciliation worker."""


@cli.command("audit")
@click.option("--apply", is_flag=True, help="Persist hypertide_* updates (default: dry-run).")
def audit_cmd(apply: bool) -> None:
    """Full-fleet HT<->DB audit. Default dry-run; --apply writes."""
    asyncio.run(_audit(apply))


@cli.command("backfill")
@click.option("--apply", is_flag=True, help="Persist flag-is_legacy and any onboarding INSERTs (default: dry-run).")
@click.option(
    "--onboard-workspace", "onboard_workspace", default=None,
    help=(
        "Explicit one-shot onboarding for a workspace whose HT records don't yet "
        "have DB rows (e.g. 'Ink''d'). Default: only flag is_legacy on existing DB "
        "rows. HT-only records are otherwise treated as friends-and-family and ignored."
    ),
)
def backfill_cmd(apply: bool, onboard_workspace: str | None) -> None:
    """Align in-scope DB rows to HT state. is_legacy flagging by default; --onboard-workspace adds INSERTs."""
    asyncio.run(_backfill(apply, onboard_workspace))


@cli.command("inspect-domain")
@click.argument("domain_name")
def inspect_domain_cmd(domain_name: str) -> None:
    """Show DB row + matching HT record + verify-revert state for one domain."""
    asyncio.run(_inspect(domain_name))


@cli.command("mark-legacy")
@click.option(
    "--workspace", "ws_name",
    help="Restrict to a specific workspace; otherwise applies fleet-wide.",
)
@click.option("--apply", is_flag=True, help="Apply (default: dry-run).")
def mark_legacy_cmd(ws_name: str | None, apply: bool) -> None:
    """Set is_legacy=TRUE on in-scope DB rows with no HT match."""
    asyncio.run(_mark_legacy(ws_name, apply))


def main() -> None:
    try:
        cli()
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(2)


# ---- Async impls ----------------------------------------------------------


async def _audit(apply: bool) -> None:
    cfg = Config.from_env()
    conn = await connect(cfg.database_url)
    try:
        async with HypertideClient(cfg.hypertide_api_url, cfg.hypertide_api_key) as ht:
            result = await run_audit(conn, ht, apply=apply)
        _print_audit_result(result, apply)
    finally:
        await conn.close()


async def _backfill(apply: bool, onboard_workspace: str | None) -> None:
    cfg = Config.from_env()
    conn = await connect(cfg.database_url)
    try:
        async with HypertideClient(cfg.hypertide_api_url, cfg.hypertide_api_key) as ht:
            result = await run_backfill(
                conn, ht, apply=apply, onboard_workspace=onboard_workspace
            )
        _print_backfill_result(result, apply, onboard_workspace)
    finally:
        await conn.close()


async def _inspect(domain_name: str) -> None:
    cfg = Config.from_env()
    conn = await connect(cfg.database_url)
    try:
        db_row = await conn.fetchrow(
            """
            SELECT d.*, w.workspace_name, w.manages_via_hypertide
            FROM domains d LEFT JOIN workspaces w ON w.id = d.workspace_id
            WHERE LOWER(d.domain_name) = LOWER($1)
            """,
            domain_name,
        )
        async with HypertideClient(cfg.hypertide_api_url, cfg.hypertide_api_key) as ht:
            active = await ht.get_active_orders()
            ht_rec = next(
                (o for o in active if o["domain"].lower() == domain_name.lower()),
                None,
            )
            rev_records: list[dict] = []
            if ht_rec and ht_rec.get("subscriptionId"):
                rev_records = await ht.verify_revert_subscription(ht_rec["subscriptionId"])
            rev = next(
                (r for r in rev_records if r.get("recordId") == (ht_rec or {}).get("id")),
                None,
            )
        click.echo("=== DB ===")
        click.echo(json.dumps(dict(db_row) if db_row else None, indent=2, default=str))
        click.echo("\n=== Hypertide /orders/active ===")
        click.echo(json.dumps(ht_rec, indent=2, default=str))
        click.echo("\n=== Hypertide verify-revert ===")
        click.echo(json.dumps(rev, indent=2, default=str))
    finally:
        await conn.close()


async def _mark_legacy(ws_name: str | None, apply: bool) -> None:
    cfg = Config.from_env()
    conn = await connect(cfg.database_url)
    try:
        async with HypertideClient(cfg.hypertide_api_url, cfg.hypertide_api_key) as ht:
            active = await ht.get_active_orders()
        ht_domains = {o["domain"].lower() for o in active}
        params = []
        sql = """
            SELECT d.id, d.domain_name, w.workspace_name
            FROM domains d JOIN workspaces w ON w.id = d.workspace_id
            WHERE w.manages_via_hypertide = TRUE
              AND d.is_legacy = FALSE
              AND d.hypertide_record_id IS NULL
        """
        if ws_name:
            sql += " AND w.workspace_name = $1"
            params.append(ws_name)
        candidates = await conn.fetch(sql, *params)
        unmatched = [r for r in candidates if r["domain_name"].lower() not in ht_domains]
        click.echo(f"Found {len(unmatched)} domains to mark is_legacy=TRUE.")
        if apply and unmatched:
            await conn.execute(
                "UPDATE domains SET is_legacy = TRUE WHERE id = ANY($1::uuid[])",
                [r["id"] for r in unmatched],
            )
            click.echo(f"Applied. {len(unmatched)} rows flagged.")
        elif unmatched:
            for r in unmatched[:30]:
                click.echo(f"  {r['workspace_name']:<32}  {r['domain_name']}")
            if len(unmatched) > 30:
                click.echo(f"  ... and {len(unmatched) - 30} more")
    finally:
        await conn.close()


# ---- Pretty-printers ------------------------------------------------------


def _print_audit_result(r: AuditResult, applied: bool) -> None:
    click.echo("=" * 70)
    click.echo(f"Hypertide audit  ({'APPLIED' if applied else 'DRY RUN'})")
    click.echo("=" * 70)
    click.echo(f"  HT active records (total):       {r.ht_active_count}")
    click.echo(f"  HT pending records:              {r.ht_pending_count}")
    click.echo("")
    click.echo("  --- parity (our DB is source of truth for what we manage) ---")
    click.echo(f"  DB in-scope rows (our universe): {r.db_in_scope_count}")
    click.echo(f"  Matched to HT:                   {r.matched}  ({r.parity_pct}%)")
    click.echo(f"  DB-only (legacy / pre-HT):       {r.db_only}")
    click.echo(f"  HT friends-and-family (ignored): {r.ht_friends_and_family}")
    click.echo("")
    click.echo("  --- drift signals ---")
    click.echo(f"  Scheduled-cancel queued:         {r.drift_to_be_cancelled}")
    click.echo(f"  HT cancelled / DB still alive:   {r.drift_cancelled_db_alive}")
    click.echo(f"  HT cancelled / EB still conn:    {r.drift_ht_cancelled_inboxes_connected}   <-- act on these")
    click.echo(f"     ... of which still sending:   {r.drift_ht_cancelled_still_sending}")
    if applied:
        click.echo(f"\n  Rows updated:                    {r.rows_updated}")
    if r.by_workspace:
        click.echo("\nPer workspace:")
        for ws, states in sorted(r.by_workspace.items()):
            click.echo(f"  {ws:<32}  {dict(states)}")
    if r.drift_examples:
        click.echo("\nTop HT-cancelled-but-EB-connected drift (sorted by sends_24h):")
        click.echo(f"  {'domain':<36} {'workspace':<24} {'conn':>4} {'snd':>4} {'sends_24h':>10}")
        for ex in r.drift_examples[:20]:
            click.echo(
                f"  {ex['domain']:<36} {(ex['workspace'] or '-')[:24]:<24} "
                f"{ex['connected_inboxes']:>4} {ex['still_sending_inboxes']:>4} "
                f"{ex['total_sends_24h']:>10}"
            )


def _print_backfill_result(r: "BackfillResult", applied: bool, onboard_workspace: str | None) -> None:
    click.echo("=" * 70)
    mode = "APPLIED" if applied else "DRY RUN"
    if onboard_workspace:
        mode += f" (onboarding workspace: {onboard_workspace})"
    click.echo(f"Hypertide backfill  ({mode})")
    click.echo("=" * 70)
    click.echo(f"  is_legacy flags to set:           {r.is_legacy_flagged}")
    click.echo(f"  HT-only friends-and-family:       {r.ht_only_friends_and_family}  (informational, not synced)")
    if onboard_workspace:
        click.echo(f"  Domains to INSERT (onboarding):   {r.inserted}")
        click.echo(f"   ├─ workspace assigned:           {r.workspace_assigned}")
        click.echo(f"   └─ workspace unresolved:         {r.workspace_unresolved}")
    if r.by_workspace:
        click.echo("\nInserts per workspace:")
        for ws, n in sorted(r.by_workspace.items()):
            click.echo(f"  {ws:<32}  {n}")
