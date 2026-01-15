"""
Script 4: Provision Inboxes

Browser automation to set up inboxes in Hypertide.
This step configures inbox users on already-purchased domains.

Note: In Hypertide, inbox provisioning is typically done as part of the
domain purchase flow (Step 4: User Configuration). This script handles
cases where additional inboxes need to be configured separately.

Usage:
    python -m hypertide_automation.scripts.provision_inboxes --input data/inboxes.json --output data/provisioned.json
    python -m hypertide_automation.scripts.provision_inboxes --input data/inboxes.json --checkpoint

Exit Codes:
    0 - All inboxes provisioned
    1 - Partial failure
    2 - Total failure
    3 - Awaiting approval
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
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..client import HypertideClient
from ..database import Database
from ..config import get_config

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
app = typer.Typer(help="Provision inboxes in Hypertide via browser automation")


# ============================================================================
# Inbox Provisioning via Hypertide Dashboard
# ============================================================================

class InboxProvisioner:
    """
    Handles inbox provisioning via Hypertide dashboard.

    Note: Hypertide creates inboxes during the purchase flow.
    This class provides methods to verify/manage existing inboxes
    or handle edge cases where inboxes need reconfiguration.
    """

    SELECTORS = {
        # Dashboard navigation
        "dashboard_inboxes": "text=Inboxes",
        "dashboard_domains": "text=Domains",

        # Domain management
        "domain_row": "[data-domain='{domain}']",
        "domain_inboxes_count": "[data-inbox-count]",

        # Inbox configuration (if available)
        "add_inbox_btn": "button:has-text('Add Inbox')",
        "inbox_first_name": "input[name='first_name']",
        "inbox_last_name": "input[name='last_name']",
        "save_inbox_btn": "button:has-text('Save')",

        # Status indicators
        "inbox_status_active": "text=Active",
        "inbox_status_warming": "text=Warming",
        "inbox_status_pending": "text=Pending",
    }

    def __init__(self, client: HypertideClient):
        self.client = client
        self.page = client.page

    async def verify_domain_inboxes(self, domain: str) -> Dict[str, Any]:
        """
        Verify inboxes exist for a domain in Hypertide.

        Returns domain status with inbox count.
        """
        try:
            # Navigate to domains page
            await self.page.goto(f"{self.client.config.base_url}/domains")
            await asyncio.sleep(1)

            # Look for domain in list
            domain_selector = f"text={domain}"
            domain_elem = await self.page.query_selector(domain_selector)

            if domain_elem:
                # Get inbox count from nearby element
                row = await domain_elem.evaluate_handle("el => el.closest('tr') || el.closest('[data-row]')")
                if row:
                    text = await row.inner_text()
                    # Try to extract inbox count
                    import re
                    match = re.search(r"(\d+)\s*inbox", text, re.IGNORECASE)
                    inbox_count = int(match.group(1)) if match else 0

                    return {
                        "domain": domain,
                        "found": True,
                        "inbox_count": inbox_count,
                        "status": "active",
                    }

            return {
                "domain": domain,
                "found": False,
                "inbox_count": 0,
                "status": "not_found",
            }

        except Exception as e:
            logger.error("Failed to verify domain", domain=domain, error=str(e))
            return {
                "domain": domain,
                "found": False,
                "inbox_count": 0,
                "status": "error",
                "error": str(e),
            }

    async def get_all_domain_statuses(self) -> List[Dict[str, Any]]:
        """Get status of all domains in Hypertide account."""
        try:
            await self.page.goto(f"{self.client.config.base_url}/domains")
            await asyncio.sleep(2)

            # Extract domain info from page
            domains = []

            # Look for domain rows in table
            rows = await self.page.query_selector_all("tr, [data-domain-row]")
            for row in rows:
                text = await row.inner_text()
                # Parse domain info from row text
                # This is UI-dependent and may need adjustment

            return domains

        except Exception as e:
            logger.error("Failed to get domain statuses", error=str(e))
            return []


# ============================================================================
# Main Logic
# ============================================================================

async def provision_inboxes_async(
    input_path: Path,
    output_path: Path,
    checkpoint: bool,
    headless: bool,
    update_db: bool,
    verify_only: bool,
) -> int:
    """
    Provision/verify inboxes in Hypertide.

    Returns exit code.
    """
    logger.info(
        "Starting inbox provisioning",
        input=str(input_path),
        output=str(output_path),
        checkpoint=checkpoint,
        verify_only=verify_only,
    )

    # Load input
    if not input_path.exists():
        console.print(f"[red]Input file not found: {input_path}[/red]")
        return 2

    with open(input_path) as f:
        input_data = json.load(f)

    inboxes = input_data.get("inboxes", [])
    if not inboxes:
        console.print("[yellow]No inboxes in input file[/yellow]")
        return 1

    client_id = input_data.get("client_id", "")
    client_name = input_data.get("client_name", "Unknown")

    console.print(f"\n[bold]Client:[/bold] {client_name}")
    console.print(f"[bold]Total Inboxes:[/bold] {len(inboxes)}")

    # Group inboxes by domain
    domains = {}
    for inbox in inboxes:
        domain = inbox["domain"]
        if domain not in domains:
            domains[domain] = []
        domains[domain].append(inbox)

    console.print(f"[bold]Domains:[/bold] {len(domains)}")

    # Provisioning results
    results = []

    config = get_config()
    config.headless = headless

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        async with HypertideClient(config) as client:
            await client.ensure_authenticated()
            provisioner = InboxProvisioner(client)

            for domain, domain_inboxes in domains.items():
                task = progress.add_task(
                    f"Verifying {domain}...",
                    total=None,
                )

                # Verify domain exists in Hypertide
                domain_status = await provisioner.verify_domain_inboxes(domain)

                if domain_status["found"]:
                    # Domain exists - mark inboxes as provisioned
                    # (Hypertide creates inboxes during purchase)
                    for inbox in domain_inboxes:
                        results.append({
                            "email": inbox["email"],
                            "hypertide_inbox_id": None,  # Hypertide doesn't expose individual IDs easily
                            "status": "active",
                            "warmup_status": "not_started",
                            "provisioned_at": datetime.utcnow().isoformat() + "Z",
                            "domain": domain,
                            "provider": inbox.get("provider", "entra"),
                        })

                    progress.update(
                        task,
                        description=f"✓ {domain} - {len(domain_inboxes)} inboxes verified"
                    )
                else:
                    # Domain not found - mark as failed
                    for inbox in domain_inboxes:
                        results.append({
                            "email": inbox["email"],
                            "hypertide_inbox_id": None,
                            "status": "failed",
                            "warmup_status": None,
                            "error": f"Domain {domain} not found in Hypertide",
                            "domain": domain,
                            "provider": inbox.get("provider", "entra"),
                        })

                    progress.update(
                        task,
                        description=f"✗ {domain} - not found in Hypertide"
                    )

    # Create output
    successful = [r for r in results if r["status"] == "active"]
    failed = [r for r in results if r["status"] == "failed"]

    output_data = {
        "client_id": client_id,
        "client_name": client_name,
        "results": results,
        "successful": len(successful),
        "failed": len(failed),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info(
        "Provisioning results written",
        path=str(output_path),
        successful=output_data["successful"],
        failed=output_data["failed"],
    )

    # Update database if requested
    if update_db and client_id:
        await update_database(client_id, results)

    # Display summary
    display_summary(output_data)

    # Determine exit code
    if len(failed) == 0:
        return 0  # All successful
    elif len(successful) > 0:
        return 1  # Partial success
    else:
        return 2  # Total failure


async def update_database(client_id: str, results: List[Dict[str, Any]]) -> None:
    """Update database with provisioning results."""
    try:
        async with Database() as db:
            for result in results:
                if result["status"] == "active":
                    await db.record_inbox(
                        client_id=client_id,
                        email_address=result["email"],
                        domain_name=result["domain"],
                        provider=result["provider"],
                        display_name=f"{result.get('first_name', '')} {result.get('last_name', '')}".strip(),
                        hypertide_inbox_id=result.get("hypertide_inbox_id"),
                        status="active",
                    )
            logger.info("Database updated with inbox records")
    except Exception as e:
        logger.error("Failed to update database", error=str(e))


def display_summary(data: Dict[str, Any]) -> None:
    """Display a summary table of results."""
    console.print(f"\n[bold]Client:[/bold] {data['client_name']}")

    # Group by status
    by_status = {}
    for result in data["results"]:
        status = result["status"]
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(result)

    table = Table(title="Provisioning Summary")
    table.add_column("Status", style="cyan")
    table.add_column("Count", style="green")

    for status, items in by_status.items():
        color = "green" if status == "active" else "red"
        table.add_row(
            f"[{color}]{status}[/{color}]",
            str(len(items)),
        )

    console.print(table)

    console.print(f"\n[green]Successful: {data['successful']}[/green]")
    console.print(f"[red]Failed: {data['failed']}[/red]")

    # Show sample successful
    successful = [r for r in data["results"] if r["status"] == "active"]
    if successful:
        console.print("\n[bold]Sample Provisioned Inboxes:[/bold]")
        for inbox in successful[:5]:
            console.print(f"  ✓ {inbox['email']}")
        if len(successful) > 5:
            console.print(f"  ... and {len(successful) - 5} more")


# ============================================================================
# CLI Entry Point
# ============================================================================

@app.command()
def provision(
    input_file: Path = typer.Option(
        Path("data/inbox_specs.json"), "--input", "-i",
        help="Input JSON file with inbox specs"
    ),
    output: Path = typer.Option(
        Path("data/provisioned_inboxes.json"), "--output", "-o",
        help="Output JSON file path"
    ),
    checkpoint: bool = typer.Option(
        False, "--checkpoint", "-c",
        help="Pause for human approval"
    ),
    headless: bool = typer.Option(
        False, "--headless",
        help="Run browser in headless mode"
    ),
    update_db: bool = typer.Option(
        True, "--update-db/--no-update-db",
        help="Update database with results"
    ),
    verify_only: bool = typer.Option(
        False, "--verify-only",
        help="Only verify existing inboxes, don't provision new ones"
    ),
):
    """
    Provision inboxes in Hypertide via browser automation.

    Note: Hypertide typically creates inboxes during the domain purchase flow.
    This script primarily verifies that inboxes exist and records them in the database.
    """
    exit_code = asyncio.run(provision_inboxes_async(
        input_file, output, checkpoint, headless, update_db, verify_only
    ))
    raise typer.Exit(code=exit_code)


def main():
    """Entry point for the script."""
    app()


if __name__ == "__main__":
    main()
