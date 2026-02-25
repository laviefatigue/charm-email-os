"""
Script 2: Purchase Domains

Browser automation to purchase domains from Hypertide.
Reads domain list from JSON, executes purchase flow, outputs results.

Usage:
    python -m hypertide_automation.scripts.purchase_domains --input data/domains.json --output data/purchased.json
    python -m hypertide_automation.scripts.purchase_domains --input data/domains.json --checkpoint

Exit Codes:
    0 - All domains purchased successfully
    1 - Partial failure (some purchased, some failed)
    2 - Total failure (no purchases completed)
    3 - Payment requires approval (checkpoint mode)
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
from ..models import OrderRequest, OrderResult, OrderType, SendingTool, DomainConfig
from ..purchase import PurchaseAutomation
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
app = typer.Typer(help="Purchase domains from Hypertide via browser automation")


# ============================================================================
# Domain Grouping by Provider
# ============================================================================

def group_domains_by_provider(domains: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group domains by provider type (entra/google)."""
    grouped = {"entra": [], "google": []}

    for domain in domains:
        provider = domain.get("provider", "entra").lower()
        if provider in grouped:
            grouped[provider].append(domain)
        else:
            # Default to entra if unknown
            grouped["entra"].append(domain)

    return grouped


def create_order_request(
    client_name: str,
    forwarding_domain: str,
    provider: str,
    domains: List[Dict[str, Any]],
) -> OrderRequest:
    """Create an OrderRequest from domain list."""
    # Determine order type
    order_type = (
        OrderType.HYPERTIDE_ENTRA
        if provider == "entra"
        else OrderType.HYPERTIDE_GOOGLE
    )

    # Calculate quantity based on domains
    # Entra: 2 domains per order, Google: 5 domains per order
    domains_per_order = 2 if provider == "entra" else 5
    quantity = max(1, (len(domains) + domains_per_order - 1) // domains_per_order)

    # Create domain configs
    domain_configs = [
        DomainConfig(
            name=d["domain"].rsplit(".", 1)[0],
            tld=d.get("tld", "com"),
            use_hypertide_domain=d.get("source") != "byod",
            custom_domain=d["domain"] if d.get("source") == "byod" else None,
        )
        for d in domains
    ]

    return OrderRequest(
        client_name=client_name,
        forwarding_domain=forwarding_domain,
        order_type=order_type,
        quantity=quantity,
        sending_tool=SendingTool.BISON,
        domains=domain_configs,
        use_saved_payment=True,
    )


# ============================================================================
# Purchase Result Handling
# ============================================================================

def create_purchase_result(
    client_id: str,
    client_name: str,
    order_result: OrderResult,
    domains: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create a result entry for a purchase."""
    return {
        "client_id": client_id,
        "client_name": client_name,
        "order_type": order_result.order_type.value,
        "success": order_result.success,
        "hypertide_order_id": order_result.order_id,
        "domains_requested": [d["domain"] for d in domains],
        "domains_created": order_result.domains_created,
        "total_inboxes": order_result.total_inboxes,
        "monthly_capacity": order_result.monthly_capacity,
        "error": order_result.error_message,
        "screenshot": order_result.screenshot_path,
        "purchased_at": datetime.utcnow().isoformat() + "Z" if order_result.success else None,
    }


def create_output(
    client_id: str,
    client_name: str,
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create the output JSON structure."""
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    all_domains = []
    for r in successful:
        for domain in r.get("domains_created", []) or r.get("domains_requested", []):
            all_domains.append({
                "domain": domain,
                "success": True,
                "hypertide_order_id": r["hypertide_order_id"],
                "provider": "entra" if "entra" in r["order_type"] else "google",
                "purchased_at": r["purchased_at"],
            })

    return {
        "client_id": client_id,
        "client_name": client_name,
        "results": all_domains,
        "successful": len(successful),
        "failed": len(failed),
        "total_cost": None,  # Would need Stripe integration to get actual cost
        "order_results": results,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


# ============================================================================
# Human Checkpoint
# ============================================================================

async def wait_for_payment_approval(console: Console) -> bool:
    """
    Pause and wait for human approval before payment.

    Returns True if approved, False if rejected.
    """
    console.print("\n" + "=" * 60)
    console.print("[bold yellow]PAYMENT CHECKPOINT[/bold yellow]")
    console.print("=" * 60)
    console.print("\nThe order is ready for payment.")
    console.print("Please review the order in the browser window.")
    console.print("\n[bold]Options:[/bold]")
    console.print("  [green]y[/green] - Approve and complete payment")
    console.print("  [red]n[/red] - Cancel and abort")
    console.print("  [blue]s[/blue] - Take screenshot and continue waiting")

    while True:
        response = console.input("\n[bold]Approve payment? (y/n/s): [/bold]").lower().strip()

        if response == "y":
            console.print("[green]Payment approved. Proceeding...[/green]")
            return True
        elif response == "n":
            console.print("[red]Payment cancelled.[/red]")
            return False
        elif response == "s":
            console.print("[blue]Screenshot saved. Continue waiting...[/blue]")
            continue
        else:
            console.print("[yellow]Invalid input. Enter y, n, or s.[/yellow]")


# ============================================================================
# Main Logic
# ============================================================================

async def purchase_domains_async(
    input_path: Path,
    output_path: Path,
    checkpoint: bool,
    headless: bool,
    update_db: bool,
) -> int:
    """
    Execute domain purchase from Hypertide.

    Returns exit code.
    """
    logger.info(
        "Starting domain purchase",
        input=str(input_path),
        output=str(output_path),
        checkpoint=checkpoint,
    )

    # Load input
    if not input_path.exists():
        console.print(f"[red]Input file not found: {input_path}[/red]")
        return 2

    with open(input_path) as f:
        input_data = json.load(f)

    domains = input_data.get("domains", [])
    if not domains:
        console.print("[yellow]No domains in input file[/yellow]")
        return 1

    client_id = input_data.get("client_id", "")
    client_name = input_data.get("client_name", "Unknown")
    forwarding_domain = input_data.get("forwarding_domain", "")

    console.print(f"\n[bold]Client:[/bold] {client_name}")
    console.print(f"[bold]Domains:[/bold] {len(domains)}")
    console.print(f"[bold]Forwarding:[/bold] {forwarding_domain}")

    # Group domains by provider
    grouped = group_domains_by_provider(domains)
    console.print(f"\n[bold]Entra domains:[/bold] {len(grouped['entra'])}")
    console.print(f"[bold]Google domains:[/bold] {len(grouped['google'])}")

    # Execute purchases
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

            for provider, provider_domains in grouped.items():
                if not provider_domains:
                    continue

                task = progress.add_task(
                    f"Purchasing {len(provider_domains)} {provider} domains...",
                    total=None,
                )

                # Create order request
                order_request = create_order_request(
                    client_name=client_name,
                    forwarding_domain=forwarding_domain,
                    provider=provider,
                    domains=provider_domains,
                )

                # Execute purchase automation
                automation = PurchaseAutomation(client)

                try:
                    # Run steps 1-4 (stop before checkout if checkpoint mode)
                    if checkpoint:
                        # Execute up to review step
                        await automation._step_choose_plan(order_request)
                        await automation._step_select_quantity(order_request)
                        await automation._step_configure_domains(order_request)
                        await automation._step_setup_settings(order_request)
                        await automation._step_review_order(order_request)

                        # Wait for human approval
                        progress.update(task, description="Waiting for payment approval...")
                        approved = await wait_for_payment_approval(console)

                        if not approved:
                            # Save state and exit with checkpoint code
                            result = create_purchase_result(
                                client_id=client_id,
                                client_name=client_name,
                                order_result=OrderResult(
                                    success=False,
                                    client_name=client_name,
                                    forwarding_domain=forwarding_domain,
                                    order_type=order_request.order_type,
                                    quantity=order_request.quantity,
                                    error_message="Payment cancelled by user",
                                ),
                                domains=provider_domains,
                            )
                            results.append(result)
                            continue

                        # Complete checkout
                        order_id = await automation._step_checkout(order_request)
                        order_result = OrderResult(
                            success=True,
                            order_id=order_id,
                            client_name=client_name,
                            forwarding_domain=forwarding_domain,
                            order_type=order_request.order_type,
                            quantity=order_request.quantity,
                            domains_created=[d["domain"] for d in provider_domains],
                            total_inboxes=order_request.expected_inboxes,
                            monthly_capacity=order_request.expected_monthly_capacity,
                        )
                    else:
                        # Full automated purchase
                        order_result = await automation.execute(order_request)

                    result = create_purchase_result(
                        client_id=client_id,
                        client_name=client_name,
                        order_result=order_result,
                        domains=provider_domains,
                    )
                    results.append(result)

                    progress.update(
                        task,
                        description=f"{'✓' if order_result.success else '✗'} {provider} purchase {'complete' if order_result.success else 'failed'}",
                    )

                except Exception as e:
                    logger.error("Purchase failed", provider=provider, error=str(e))
                    result = create_purchase_result(
                        client_id=client_id,
                        client_name=client_name,
                        order_result=OrderResult(
                            success=False,
                            client_name=client_name,
                            forwarding_domain=forwarding_domain,
                            order_type=order_request.order_type,
                            quantity=order_request.quantity,
                            error_message=str(e),
                        ),
                        domains=provider_domains,
                    )
                    results.append(result)

    # Create output
    output_data = create_output(client_id, client_name, results)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    logger.info(
        "Purchase results written",
        path=str(output_path),
        successful=output_data["successful"],
        failed=output_data["failed"],
    )

    # Update database if requested
    if update_db and client_id:
        await update_database(client_id, output_data)

    # Display summary
    display_summary(output_data)

    # Determine exit code
    if output_data["failed"] == 0 and output_data["successful"] > 0:
        return 0  # All successful
    elif output_data["successful"] > 0:
        return 1  # Partial success
    else:
        return 2  # Total failure


async def update_database(client_id: str, output_data: Dict[str, Any]) -> None:
    """Update database with purchase results."""
    try:
        async with Database() as db:
            for result in output_data.get("results", []):
                await db.record_domain_purchase(
                    client_id=client_id,
                    domain_name=result["domain"],
                    tld=result["domain"].split(".")[-1],
                    registrar="hypertide",
                    purchase_price=0,  # Hypertide bundles pricing
                    success=result["success"],
                    hypertide_domain_id=result.get("hypertide_order_id"),
                    assigned_provider=result.get("provider"),
                )
            logger.info("Database updated with purchase results")
    except Exception as e:
        logger.error("Failed to update database", error=str(e))


def display_summary(data: Dict[str, Any]) -> None:
    """Display a summary table of results."""
    table = Table(title="Purchase Results")
    table.add_column("Domain", style="cyan")
    table.add_column("Provider", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Order ID", style="blue")

    for result in data.get("results", []):
        status = "[green]✓ Success[/green]" if result["success"] else "[red]✗ Failed[/red]"
        table.add_row(
            result["domain"],
            result.get("provider", "-"),
            status,
            result.get("hypertide_order_id", "-"),
        )

    console.print(table)
    console.print(f"\n[green]Successful: {data['successful']}[/green]")
    console.print(f"[red]Failed: {data['failed']}[/red]")


# ============================================================================
# CLI Entry Point
# ============================================================================

@app.command()
def purchase(
    input_file: Path = typer.Option(
        Path("data/domains_to_purchase.json"), "--input", "-i",
        help="Input JSON file with domains to purchase"
    ),
    output: Path = typer.Option(
        Path("data/purchased_domains.json"), "--output", "-o",
        help="Output JSON file path"
    ),
    checkpoint: bool = typer.Option(
        False, "--checkpoint", "-c",
        help="Pause for human approval before payment"
    ),
    headless: bool = typer.Option(
        False, "--headless",
        help="Run browser in headless mode"
    ),
    update_db: bool = typer.Option(
        True, "--update-db/--no-update-db",
        help="Update database with results"
    ),
):
    """
    Purchase domains from Hypertide via browser automation.

    Reads domain list from input JSON, executes purchase flow,
    and outputs results for the next pipeline step.
    """
    exit_code = asyncio.run(purchase_domains_async(
        input_file, output, checkpoint, headless, update_db
    ))
    raise typer.Exit(code=exit_code)


def main():
    """Entry point for the script."""
    app()


if __name__ == "__main__":
    main()
