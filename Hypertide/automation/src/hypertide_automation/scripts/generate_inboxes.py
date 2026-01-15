"""
Script 3: Generate Inboxes

Generate inbox specifications from purchased domains.
Creates inbox naming based on domain provider and configured user names.

Usage:
    python -m hypertide_automation.scripts.generate_inboxes --input data/purchased.json --output data/inboxes.json
    python -m hypertide_automation.scripts.generate_inboxes --client-id <uuid> --output data/inboxes.json

Exit Codes:
    0 - Success
    1 - No domains found
    2 - Configuration error
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from itertools import cycle

import typer
import structlog
from rich.console import Console
from rich.table import Table

from ..database import Database

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
app = typer.Typer(help="Generate inbox specifications from purchased domains")


# ============================================================================
# Default User Names
# ============================================================================

DEFAULT_USERS = [
    {"first_name": "Alex", "last_name": "Morgan"},
    {"first_name": "Jordan", "last_name": "Smith"},
    {"first_name": "Taylor", "last_name": "Johnson"},
    {"first_name": "Casey", "last_name": "Williams"},
    {"first_name": "Morgan", "last_name": "Davis"},
    {"first_name": "Riley", "last_name": "Brown"},
    {"first_name": "Quinn", "last_name": "Miller"},
    {"first_name": "Avery", "last_name": "Wilson"},
    {"first_name": "Blake", "last_name": "Anderson"},
    {"first_name": "Drew", "last_name": "Taylor"},
]


# ============================================================================
# Inbox Generation Logic
# ============================================================================

def get_inboxes_per_domain(provider: str) -> int:
    """Get number of inboxes to create per domain based on provider."""
    if provider.lower() == "entra":
        return 50  # Entra: 50 inboxes per domain
    elif provider.lower() == "google":
        return 3   # Google: 3 inboxes per domain
    else:
        return 10  # Default fallback


def generate_inbox_email(
    first_name: str,
    last_name: str,
    domain: str,
    index: int = 0,
) -> str:
    """
    Generate email address in format: first.last@domain

    If index > 0, appends number for uniqueness: first.last2@domain
    """
    base = f"{first_name.lower()}.{last_name.lower()}"
    if index > 0:
        base = f"{base}{index + 1}"
    return f"{base}@{domain}"


def generate_inboxes_for_domain(
    domain: str,
    provider: str,
    users: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Generate inbox specs for a single domain."""
    inboxes = []
    inbox_count = get_inboxes_per_domain(provider)

    # Use provided users, cycling through if we need more
    user_cycle = cycle(users) if users else cycle(DEFAULT_USERS)

    for i in range(inbox_count):
        user = next(user_cycle)
        # Calculate repeat index for this user on this domain
        user_key = f"{user['first_name']}.{user['last_name']}"
        repeat_index = sum(1 for inbox in inboxes if inbox["first_name"] == user["first_name"] and inbox["last_name"] == user["last_name"])

        email = generate_inbox_email(
            user["first_name"],
            user["last_name"],
            domain,
            repeat_index,
        )

        inboxes.append({
            "email": email,
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "domain": domain,
            "provider": provider,
        })

    return inboxes


# ============================================================================
# Main Logic
# ============================================================================

async def generate_inboxes_async(
    input_path: Optional[Path],
    client_id: Optional[str],
    output_path: Path,
    users_file: Optional[Path],
) -> int:
    """
    Generate inbox specifications.

    Returns exit code.
    """
    logger.info(
        "Generating inbox specs",
        input=str(input_path) if input_path else "database",
        client_id=client_id,
        output=str(output_path),
    )

    # Load custom users if provided
    users = DEFAULT_USERS
    if users_file and users_file.exists():
        with open(users_file) as f:
            custom_users = json.load(f)
            if isinstance(custom_users, list):
                users = custom_users
                logger.info("Loaded custom users", count=len(users))

    # Get domains from input file or database
    domains = []
    client_name = "Unknown"
    emailbison_workspace = ""

    if input_path and input_path.exists():
        with open(input_path) as f:
            input_data = json.load(f)

        # Get successful domain purchases
        for result in input_data.get("results", []):
            if result.get("success", False):
                domains.append({
                    "domain": result["domain"],
                    "provider": result.get("provider", "entra"),
                    "hypertide_order_id": result.get("hypertide_order_id"),
                })

        client_id = input_data.get("client_id", client_id)
        client_name = input_data.get("client_name", "Unknown")

    elif client_id:
        # Load from database
        try:
            async with Database() as db:
                # Get client info
                client = await db.get_client_by_id(client_id)
                if client:
                    client_name = client.get("name", "Unknown")
                    emailbison_workspace = client.get("emailbison_workspace", "")

                # Get purchased domains
                purchased = await db.get_purchased_domains(client_id)
                for p in purchased:
                    domains.append({
                        "domain": p["domain_name"],
                        "provider": p.get("assigned_provider", "entra"),
                        "hypertide_domain_id": p.get("hypertide_domain_id"),
                    })

        except Exception as e:
            logger.error("Database error", error=str(e))
            console.print(f"[red]Database error: {e}[/red]")
            return 2

    else:
        console.print("[red]Must provide either --input file or --client-id[/red]")
        return 2

    if not domains:
        console.print("[yellow]No domains found to generate inboxes for[/yellow]")
        return 1

    # Get workspace from database if not already set
    if not emailbison_workspace and client_id:
        try:
            async with Database() as db:
                client = await db.get_client_by_id(client_id)
                if client:
                    emailbison_workspace = client.get("emailbison_workspace", "")
        except Exception:
            pass

    # Generate inboxes for each domain
    all_inboxes = []
    for domain_info in domains:
        domain = domain_info["domain"]
        provider = domain_info.get("provider", "entra")

        inboxes = generate_inboxes_for_domain(domain, provider, users)
        all_inboxes.extend(inboxes)

        logger.info(
            "Generated inboxes",
            domain=domain,
            provider=provider,
            count=len(inboxes),
        )

    # Create output
    output_data = {
        "client_id": client_id,
        "client_name": client_name,
        "emailbison_workspace": emailbison_workspace,
        "domains": [d["domain"] for d in domains],
        "inboxes": all_inboxes,
        "total_inboxes": len(all_inboxes),
        "by_provider": {
            "entra": len([i for i in all_inboxes if i["provider"] == "entra"]),
            "google": len([i for i in all_inboxes if i["provider"] == "google"]),
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info(
        "Inbox specs written",
        path=str(output_path),
        total=output_data["total_inboxes"],
    )

    # Display summary
    display_summary(output_data)

    return 0


def display_summary(data: Dict[str, Any]) -> None:
    """Display a summary of generated inboxes."""
    console.print(f"\n[bold]Client:[/bold] {data['client_name']}")
    console.print(f"[bold]Workspace:[/bold] {data['emailbison_workspace'] or 'Not set'}")
    console.print(f"[bold]Domains:[/bold] {len(data['domains'])}")

    table = Table(title="Inbox Summary by Domain")
    table.add_column("Domain", style="cyan")
    table.add_column("Provider", style="magenta")
    table.add_column("Inboxes", style="green")

    # Group by domain
    domain_counts = {}
    for inbox in data["inboxes"]:
        domain = inbox["domain"]
        provider = inbox["provider"]
        key = (domain, provider)
        domain_counts[key] = domain_counts.get(key, 0) + 1

    for (domain, provider), count in domain_counts.items():
        table.add_row(domain, provider, str(count))

    console.print(table)

    console.print(f"\n[bold]Total Inboxes:[/bold] {data['total_inboxes']}")
    console.print(f"  Entra: {data['by_provider']['entra']}")
    console.print(f"  Google: {data['by_provider']['google']}")

    # Show sample inboxes
    console.print("\n[bold]Sample Inboxes:[/bold]")
    for inbox in data["inboxes"][:5]:
        console.print(f"  {inbox['email']}")
    if len(data["inboxes"]) > 5:
        console.print(f"  ... and {len(data['inboxes']) - 5} more")


# ============================================================================
# CLI Entry Point
# ============================================================================

@app.command()
def generate(
    input_file: Optional[Path] = typer.Option(
        None, "--input", "-i",
        help="Input JSON file with purchased domains"
    ),
    client_id: Optional[str] = typer.Option(
        None, "--client-id", "-c",
        help="Client UUID to load domains from database"
    ),
    output: Path = typer.Option(
        Path("data/inbox_specs.json"), "--output", "-o",
        help="Output JSON file path"
    ),
    users_file: Optional[Path] = typer.Option(
        None, "--users", "-u",
        help="JSON file with custom user names [{first_name, last_name}, ...]"
    ),
):
    """
    Generate inbox specifications from purchased domains.

    Creates inbox naming based on domain provider:
    - Entra: 50 inboxes per domain
    - Google: 3 inboxes per domain

    Uses default user names or custom names from --users file.
    """
    if not input_file and not client_id:
        console.print("[red]Must provide either --input file or --client-id[/red]")
        raise typer.Exit(code=2)

    exit_code = asyncio.run(generate_inboxes_async(
        input_file, client_id, output, users_file
    ))
    raise typer.Exit(code=exit_code)


def main():
    """Entry point for the script."""
    app()


if __name__ == "__main__":
    main()
