"""
Script 5: Upload to Email Bison

Upload provisioned inboxes to Email Bison workspace.
Final step in the pipeline - connects Hypertide inboxes to Email Bison.

Usage:
    python -m hypertide_automation.scripts.upload_to_emailbison --input data/provisioned.json
    python -m hypertide_automation.scripts.upload_to_emailbison --client-id <uuid>

Exit Codes:
    0 - All inboxes uploaded
    1 - Partial failure
    2 - Workspace not found
    3 - API error
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import typer
import structlog
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from ..database import Database
from ..emailbison import EmailBisonClient, InboxUpload, UploadResult

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()
console = Console()
app = typer.Typer(help="Upload provisioned inboxes to Email Bison workspace")


# ============================================================================
# Main Logic
# ============================================================================

async def upload_to_emailbison_async(
    input_path: Optional[Path],
    client_id: Optional[str],
    workspace: Optional[str],
    update_db: bool,
    dry_run: bool,
) -> int:
    """
    Upload inboxes to Email Bison.

    Returns exit code.
    """
    logger.info(
        "Starting Email Bison upload",
        input=str(input_path) if input_path else "database",
        client_id=client_id,
        workspace=workspace,
        dry_run=dry_run,
    )

    # Load inboxes from input file or database
    inboxes = []
    client_name = "Unknown"
    emailbison_workspace = workspace

    if input_path and input_path.exists():
        with open(input_path) as f:
            input_data = json.load(f)

        # Get successful provisioned inboxes
        for result in input_data.get("results", []):
            if result.get("status") == "active":
                # Parse name from email if not provided
                email = result["email"]
                parts = email.split("@")[0].split(".")
                first_name = parts[0].title() if parts else "User"
                last_name = parts[1].title() if len(parts) > 1 else "Name"

                inboxes.append({
                    "email": email,
                    "first_name": result.get("first_name", first_name),
                    "last_name": result.get("last_name", last_name),
                    "provider": result.get("provider", "entra"),
                    "domain": result.get("domain", email.split("@")[1]),
                })

        client_id = client_id or input_data.get("client_id")
        client_name = input_data.get("client_name", "Unknown")
        emailbison_workspace = emailbison_workspace or input_data.get("emailbison_workspace")

    elif client_id:
        # Load from database
        try:
            async with Database() as db:
                # Get client info
                client = await db.get_client_by_id(client_id)
                if client:
                    client_name = client.get("name", "Unknown")
                    emailbison_workspace = emailbison_workspace or client.get("emailbison_workspace", "")

                # Get active inboxes not yet uploaded
                db_inboxes = await db.get_client_inboxes(client_id, status="active")
                for inbox in db_inboxes:
                    email = inbox["email_address"]
                    parts = email.split("@")[0].split(".")
                    first_name = parts[0].title() if parts else "User"
                    last_name = parts[1].title() if len(parts) > 1 else "Name"

                    inboxes.append({
                        "email": email,
                        "first_name": inbox.get("first_name", first_name),
                        "last_name": inbox.get("last_name", last_name),
                        "provider": inbox.get("provider", "entra"),
                        "domain": inbox.get("domain_name", email.split("@")[1]),
                        "db_id": str(inbox.get("id")),
                    })

        except Exception as e:
            logger.error("Database error", error=str(e))
            console.print(f"[red]Database error: {e}[/red]")
            return 3

    else:
        console.print("[red]Must provide either --input file or --client-id[/red]")
        return 3

    if not inboxes:
        console.print("[yellow]No inboxes to upload[/yellow]")
        return 1

    if not emailbison_workspace:
        console.print("[red]Email Bison workspace not specified[/red]")
        console.print("Use --workspace or ensure client has emailbison_workspace set in database")
        return 2

    console.print(f"\n[bold]Client:[/bold] {client_name}")
    console.print(f"[bold]Workspace:[/bold] {emailbison_workspace}")
    console.print(f"[bold]Inboxes:[/bold] {len(inboxes)}")

    if dry_run:
        console.print("\n[yellow]DRY RUN - No actual uploads will be made[/yellow]")
        display_inboxes_to_upload(inboxes)
        return 0

    # Upload to Email Bison
    results: List[UploadResult] = []

    async with EmailBisonClient() as eb_client:
        # Verify workspace exists
        ws = await eb_client.get_workspace(emailbison_workspace)
        if not ws:
            console.print(f"[red]Workspace '{emailbison_workspace}' not found in Email Bison[/red]")
            console.print("Please create the workspace manually in Email Bison first.")
            return 2

        console.print(f"[green]Workspace found: {ws.get('name')}[/green]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("Uploading inboxes...", total=len(inboxes))

            for inbox in inboxes:
                # Create upload request
                upload = InboxUpload(
                    email=inbox["email"],
                    first_name=inbox["first_name"],
                    last_name=inbox["last_name"],
                    provider=inbox["provider"],
                )

                # Upload
                result = await eb_client.upload_inbox(emailbison_workspace, upload)
                results.append(result)

                # Log progress
                status = "✓" if result.success else "✗"
                progress.update(
                    task,
                    advance=1,
                    description=f"{status} {inbox['email'][:30]}..."
                )

    # Summary
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    logger.info(
        "Upload completed",
        successful=len(successful),
        failed=len(failed),
    )

    # Update database if requested
    if update_db and client_id:
        await update_database_status(inboxes, results)

    # Display results
    display_upload_summary(results, emailbison_workspace)

    # Determine exit code
    if len(failed) == 0:
        return 0  # All successful
    elif len(successful) > 0:
        return 1  # Partial success
    else:
        return 3  # API error / total failure


async def update_database_status(
    inboxes: List[Dict[str, Any]],
    results: List[UploadResult],
) -> None:
    """Update database with Email Bison upload results."""
    try:
        async with Database() as db:
            for inbox, result in zip(inboxes, results):
                if result.success and inbox.get("db_id"):
                    await db.update_inbox_status(
                        inbox_id=inbox["db_id"],
                        status="active",
                        warmup_status="not_started",
                    )
            logger.info("Database updated with Email Bison status")
    except Exception as e:
        logger.error("Failed to update database", error=str(e))


def display_inboxes_to_upload(inboxes: List[Dict[str, Any]]) -> None:
    """Display inboxes that would be uploaded."""
    table = Table(title="Inboxes to Upload")
    table.add_column("Email", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Provider", style="magenta")

    for inbox in inboxes[:20]:
        table.add_row(
            inbox["email"],
            f"{inbox['first_name']} {inbox['last_name']}",
            inbox["provider"],
        )

    if len(inboxes) > 20:
        table.add_row("...", f"({len(inboxes) - 20} more)", "...")

    console.print(table)


def display_upload_summary(results: List[UploadResult], workspace: str) -> None:
    """Display upload results summary."""
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    console.print(f"\n[bold]Upload to: {workspace}[/bold]")
    console.print(f"[green]Successful: {len(successful)}[/green]")
    console.print(f"[red]Failed: {len(failed)}[/red]")

    if successful:
        console.print("\n[bold]Uploaded Inboxes:[/bold]")
        for result in successful[:5]:
            console.print(f"  ✓ {result.email}")
        if len(successful) > 5:
            console.print(f"  ... and {len(successful) - 5} more")

    if failed:
        console.print("\n[bold red]Failed Uploads:[/bold red]")
        for result in failed[:5]:
            console.print(f"  ✗ {result.email}: {result.error}")
        if len(failed) > 5:
            console.print(f"  ... and {len(failed) - 5} more")


# ============================================================================
# CLI Entry Point
# ============================================================================

@app.command()
def upload(
    input_file: Optional[Path] = typer.Option(
        None, "--input", "-i",
        help="Input JSON file with provisioned inboxes"
    ),
    client_id: Optional[str] = typer.Option(
        None, "--client-id", "-c",
        help="Client UUID to load inboxes from database"
    ),
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w",
        help="Email Bison workspace name (overrides client setting)"
    ),
    update_db: bool = typer.Option(
        True, "--update-db/--no-update-db",
        help="Update database with upload status"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Show what would be uploaded without making changes"
    ),
):
    """
    Upload provisioned inboxes to Email Bison workspace.

    Connects Hypertide-provisioned inboxes to their Email Bison workspace
    for campaign management and warmup tracking.

    Note: The Email Bison workspace must already exist (API doesn't support creation).
    """
    if not input_file and not client_id:
        console.print("[red]Must provide either --input file or --client-id[/red]")
        raise typer.Exit(code=3)

    exit_code = asyncio.run(upload_to_emailbison_async(
        input_file, client_id, workspace, update_db, dry_run
    ))
    raise typer.Exit(code=exit_code)


def main():
    """Entry point for the script."""
    app()


if __name__ == "__main__":
    main()
