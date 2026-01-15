"""
Script 1: Check Domains

Query database for domains pending purchase from Hypertide.
Outputs a JSON file with domain list for the next pipeline step.

Usage:
    python -m hypertide_automation.scripts.check_domains --client-id <uuid> --output data/domains.json
    python -m hypertide_automation.scripts.check_domains --status approved --output data/domains.json

Exit Codes:
    0 - Success, domains found
    1 - No domains to purchase
    2 - Database error
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

from ..database import Database, DatabaseConfig

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
app = typer.Typer(help="Check domains pending purchase from Hypertide")


# ============================================================================
# Data Models for JSON Output
# ============================================================================

def create_domain_entry(
    domain: str,
    tld: str,
    provider: str,
    source: str = "approval",
    registrar: Optional[str] = None,
    purchase_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Create a domain entry for the output JSON."""
    return {
        "domain": domain,
        "tld": tld,
        "provider": provider,  # 'entra' or 'google'
        "source": source,      # 'byod', 'hypertide', 'approval'
        "registrar": registrar,
        "purchase_price": purchase_price,
    }


def create_output(
    client_id: str,
    client_name: str,
    forwarding_domain: str,
    domains: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create the output JSON structure."""
    return {
        "client_id": client_id,
        "client_name": client_name,
        "forwarding_domain": forwarding_domain,
        "domains": domains,
        "total_domains": len(domains),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


# ============================================================================
# Domain Extraction from Approval Requests
# ============================================================================

def extract_domains_from_approval(approval: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract domain list from a domain approval request.

    The approval request has tier_1_results, tier_2_results, tier_3_results
    as JSONB arrays with domain info, and approved_domains with final selection.
    """
    domains = []

    # Try to get from approved_domains first (final selection)
    approved = approval.get("approved_domains")
    if approved:
        if isinstance(approved, str):
            try:
                approved = json.loads(approved)
            except json.JSONDecodeError:
                approved = []

        for domain_info in approved:
            if isinstance(domain_info, dict):
                domain_name = domain_info.get("domain", "")
                domains.append(create_domain_entry(
                    domain=domain_name,
                    tld=domain_name.split(".")[-1] if "." in domain_name else "com",
                    provider=domain_info.get("provider", "entra"),
                    source="approval",
                    registrar=domain_info.get("registrar"),
                    purchase_price=domain_info.get("price"),
                ))
            elif isinstance(domain_info, str):
                # Just a domain string
                domains.append(create_domain_entry(
                    domain=domain_info,
                    tld=domain_info.split(".")[-1] if "." in domain_info else "com",
                    provider="entra",  # Default
                    source="approval",
                ))

    # If no approved_domains, try tier results
    if not domains:
        for tier_key in ["tier_1_results", "tier_2_results", "tier_3_results"]:
            tier_data = approval.get(tier_key)
            if tier_data:
                if isinstance(tier_data, str):
                    try:
                        tier_data = json.loads(tier_data)
                    except json.JSONDecodeError:
                        continue

                for domain_info in tier_data:
                    if isinstance(domain_info, dict):
                        domain_name = domain_info.get("domain", "")
                        if domain_name and domain_name not in [d["domain"] for d in domains]:
                            domains.append(create_domain_entry(
                                domain=domain_name,
                                tld=domain_name.split(".")[-1] if "." in domain_name else "com",
                                provider=domain_info.get("provider", "entra"),
                                source=f"tier_{tier_key.split('_')[1]}",
                                registrar=domain_info.get("registrar"),
                                purchase_price=domain_info.get("price"),
                            ))

    return domains


# ============================================================================
# Main Logic
# ============================================================================

async def check_domains_async(
    client_id: Optional[str],
    status: str,
    output_path: Path,
) -> int:
    """
    Query database for domains and output to JSON.

    Returns exit code.
    """
    logger.info(
        "Checking domains",
        client_id=client_id,
        status=status,
        output=str(output_path),
    )

    try:
        async with Database() as db:
            # Get approval requests
            approvals = await db.get_approved_domains(
                client_id=client_id,
                status=status,
            )

            if not approvals:
                logger.warning("No domain approval requests found", status=status)
                console.print(f"[yellow]No domains found with status '{status}'[/yellow]")
                return 1

            # Process each approval
            all_results = []
            for approval in approvals:
                approval_client_id = str(approval.get("client_id", ""))
                client_name = approval.get("client_name", "Unknown")
                client_slug = approval.get("client_slug", "")

                # Get client for forwarding domain
                client = await db.get_client_by_id(approval_client_id)
                forwarding_domain = ""
                if client:
                    # Try various fields for forwarding domain
                    forwarding_domain = (
                        client.get("domain") or
                        client.get("website") or
                        client.get("slug", "") + ".com"
                    )

                # Extract domains from approval
                domains = extract_domains_from_approval(approval)

                if domains:
                    result = create_output(
                        client_id=approval_client_id,
                        client_name=client_name,
                        forwarding_domain=forwarding_domain,
                        domains=domains,
                    )
                    all_results.append(result)

            if not all_results:
                logger.warning("No domains extracted from approvals")
                console.print("[yellow]No domains to purchase found in approval requests[/yellow]")
                return 1

            # If single client requested, output that client's domains
            # Otherwise, output all
            if client_id and len(all_results) == 1:
                output_data = all_results[0]
            else:
                # Aggregate all domains
                total_domains = []
                for result in all_results:
                    for domain in result["domains"]:
                        domain["client_id"] = result["client_id"]
                        domain["client_name"] = result["client_name"]
                        total_domains.append(domain)

                output_data = {
                    "multi_client": True,
                    "clients": [r["client_id"] for r in all_results],
                    "domains": total_domains,
                    "total_domains": len(total_domains),
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                }

            # Write output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(output_data, f, indent=2, default=str)

            logger.info(
                "Domains written to file",
                path=str(output_path),
                count=output_data["total_domains"],
            )

            # Display summary
            display_summary(output_data)

            return 0

    except Exception as e:
        logger.error("Database error", error=str(e))
        console.print(f"[red]Database error: {e}[/red]")
        return 2


def display_summary(data: Dict[str, Any]) -> None:
    """Display a summary table of domains."""
    table = Table(title="Domains to Purchase")
    table.add_column("Domain", style="cyan")
    table.add_column("TLD", style="green")
    table.add_column("Provider", style="magenta")
    table.add_column("Source", style="yellow")
    table.add_column("Price", style="blue")

    for domain in data.get("domains", []):
        price = domain.get("purchase_price")
        price_str = f"${price:.2f}" if price else "-"
        table.add_row(
            domain["domain"],
            domain["tld"],
            domain["provider"],
            domain["source"],
            price_str,
        )

    console.print(table)
    console.print(f"\n[green]Total: {data['total_domains']} domains[/green]")


# ============================================================================
# CLI Entry Point
# ============================================================================

@app.command()
def check(
    client_id: Optional[str] = typer.Option(
        None, "--client-id", "-c",
        help="Filter by specific client UUID"
    ),
    status: str = typer.Option(
        "approved", "--status", "-s",
        help="Filter by approval status (default: approved)"
    ),
    output: Path = typer.Option(
        Path("data/domains_to_purchase.json"), "--output", "-o",
        help="Output JSON file path"
    ),
):
    """
    Check database for domains pending purchase.

    Queries domain_approval_requests table for approved domains
    and outputs them as JSON for the next pipeline step.
    """
    exit_code = asyncio.run(check_domains_async(client_id, status, output))
    raise typer.Exit(code=exit_code)


def main():
    """Entry point for the script."""
    app()


if __name__ == "__main__":
    main()
