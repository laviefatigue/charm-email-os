"""
CLI commands for domain sourcing workflow.

Provides command-line interface for:
- Running complete sourcing workflow
- Generating domain candidates
- Searching registrars
- Quick fuzzy searches
- Managing approval and purchase

Usage:
    # Full workflow (interactive)
    python -m hypertide_automation.domain_sourcing.cli source \
        --client "Acme Corp" \
        --industry "SaaS" \
        --entra 6 \
        --google 5 \
        --keywords "outreach,growth,scale"

    # Quick fuzzy search
    python -m hypertide_automation.domain_sourcing.cli fuzzy "acme-growth.com"

    # Generate candidates only
    python -m hypertide_automation.domain_sourcing.cli generate \
        --client "Acme Corp" \
        --industry "SaaS" \
        --output candidates.json
"""

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import DomainRequest, DomainSearchResult
from .generator import generate_domain_candidates, generate_fallback_candidates, DomainGeneratorConfig
from .search import search_registrars, fuzzy_search, SearchConfig
from .workflow import DomainSourcingWorkflow, AutoApproval
from .registrars import RegistrarFactory

app = typer.Typer(
    name="domain-source",
    help="Domain sourcing CLI for Hypertide infrastructure",
)
console = Console()


def display_results_table(results: list[DomainSearchResult], title: str = "Search Results"):
    """Display search results in a rich table."""
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Domain", style="green")
    table.add_column("Price", justify="right", style="yellow")
    table.add_column("Registrar", style="blue")
    table.add_column("Score", justify="right")
    table.add_column("Deal", justify="center")

    available = [r for r in results if r.is_available and r.best_price]

    for i, result in enumerate(available[:30], 1):
        deal = "[green]✓[/green]" if result.is_deal else ""
        table.add_row(
            str(i),
            result.candidate.domain_name,
            f"${result.best_price:.2f}",
            result.best_registrar.value if result.best_registrar else "N/A",
            f"{result.value_score:.2f}",
            deal,
        )

    console.print(table)

    # Summary
    deals = len([r for r in available if r.is_deal])
    console.print(f"\n[bold]Summary:[/bold] {len(available)} available, {deals} deals")


@app.command()
def source(
    client: str = typer.Option(..., "--client", "-c", help="Client/company name"),
    industry: str = typer.Option(..., "--industry", "-i", help="Industry vertical"),
    entra: int = typer.Option(0, "--entra", "-e", help="Required Entra domains"),
    google: int = typer.Option(0, "--google", "-g", help="Required Google domains"),
    keywords: str = typer.Option("", "--keywords", "-k", help="Brand keywords (comma-separated)"),
    max_price: float = typer.Option(15.0, "--max-price", help="Maximum price per domain"),
    target_price: float = typer.Option(8.0, "--target-price", help="Target price for deals"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Skip actual purchases"),
    auto_approve: bool = typer.Option(False, "--auto", "-a", help="Auto-approve domains"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save session to JSON"),
):
    """
    Run the complete domain sourcing workflow.

    Example:
        domain-source source -c "Acme Corp" -i "SaaS" -e 6 -g 5 -k "outreach,growth"
    """
    # Parse keywords
    brand_keywords = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

    if entra == 0 and google == 0:
        console.print("[red]Error: Must specify --entra or --google domain count[/red]")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold]Domain Sourcing Workflow[/bold]\n\n"
        f"Client: {client}\n"
        f"Industry: {industry}\n"
        f"Entra Domains: {entra}\n"
        f"Google Domains: {google}\n"
        f"Keywords: {', '.join(brand_keywords) if brand_keywords else 'None'}\n"
        f"Target Price: ${target_price}\n"
        f"Max Price: ${max_price}",
        title="Configuration",
    ))

    async def run_workflow():
        # Configure workflow
        search_config = SearchConfig(
            target_price=Decimal(str(target_price)),
            max_price=Decimal(str(max_price)),
        )

        if auto_approve:
            approval = AutoApproval(max_price=Decimal(str(max_price)))
        else:
            approval = None  # Use default interactive

        workflow = DomainSourcingWorkflow(
            search_config=search_config,
            approval_callback=approval,
        )

        async with workflow:
            session = await workflow.run(
                client_name=client,
                industry=industry,
                entra_domains=entra,
                google_domains=google,
                brand_keywords=brand_keywords,
                dry_run=dry_run,
            )

        return session

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running workflow...", total=None)
        session = asyncio.run(run_workflow())
        progress.remove_task(task)

    # Display results
    console.print(f"\n[bold]Workflow Status:[/bold] {session.status}")
    console.print(f"[bold]Candidates Generated:[/bold] {len(session.candidates)}")
    console.print(f"[bold]Search Results:[/bold] {len(session.search_results)}")
    console.print(f"[bold]Approved:[/bold] {len(session.approved)}")

    if session.purchases:
        successful = [p for p in session.purchases if p.success]
        console.print(f"[bold]Purchased:[/bold] {len(successful)}/{len(session.purchases)}")

        if successful:
            console.print("\n[green]Successfully Purchased Domains:[/green]")
            for p in successful:
                console.print(f"  ✓ {p.domain_name} @ ${p.actual_price}")

    # Save to file if requested
    if output:
        session_dict = session.model_dump(mode="json")
        with open(output, "w") as f:
            json.dump(session_dict, f, indent=2, default=str)
        console.print(f"\n[dim]Session saved to {output}[/dim]")


@app.command()
def generate(
    client: str = typer.Option(..., "--client", "-c", help="Client/company name"),
    industry: str = typer.Option(..., "--industry", "-i", help="Industry vertical"),
    count: int = typer.Option(30, "--count", "-n", help="Number of domains to generate"),
    keywords: str = typer.Option("", "--keywords", "-k", help="Brand keywords (comma-separated)"),
    fallback: bool = typer.Option(False, "--fallback", "-f", help="Use fallback (no AI)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
):
    """
    Generate domain name candidates using AI.

    Example:
        domain-source generate -c "Acme Corp" -i "SaaS" -k "outreach,growth" -n 50
    """
    brand_keywords = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

    # Create request
    request = DomainRequest(
        client_name=client,
        industry=industry,
        brand_keywords=brand_keywords,
        required_entra_domains=count // 2,  # Just for generation count
        required_google_domains=count // 2,
    )

    console.print(f"[bold]Generating {request.generation_count} domain candidates...[/bold]")

    async def gen():
        if fallback:
            return generate_fallback_candidates(request)
        else:
            try:
                return await generate_domain_candidates(request)
            except Exception as e:
                console.print(f"[yellow]AI generation failed, using fallback: {e}[/yellow]")
                return generate_fallback_candidates(request)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating...", total=None)
        candidates = asyncio.run(gen())
        progress.remove_task(task)

    # Display results
    table = Table(title="Generated Candidates", show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Domain", style="green")
    table.add_column("Legitimacy", justify="right")
    table.add_column("Rationale")

    for i, c in enumerate(candidates[:20], 1):
        table.add_row(
            str(i),
            c.domain_name,
            f"{c.legitimacy_score:.2f}",
            c.generation_rationale[:40] + "..." if len(c.generation_rationale) > 40 else c.generation_rationale,
        )

    console.print(table)

    if len(candidates) > 20:
        console.print(f"\n[dim]... and {len(candidates) - 20} more[/dim]")

    # Save if requested
    if output:
        data = [c.model_dump(mode="json") for c in candidates]
        with open(output, "w") as f:
            json.dump(data, f, indent=2, default=str)
        console.print(f"\n[dim]Saved {len(candidates)} candidates to {output}[/dim]")


@app.command()
def search(
    input_file: Path = typer.Argument(..., help="JSON file with domain candidates"),
    max_price: float = typer.Option(15.0, "--max-price", help="Maximum price filter"),
    target_price: float = typer.Option(8.0, "--target-price", help="Target price for deals"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save results to JSON"),
):
    """
    Search registrars for domain candidates from a JSON file.

    Example:
        domain-source search candidates.json --max-price 10
    """
    from .models import DomainCandidate

    # Load candidates
    with open(input_file) as f:
        data = json.load(f)

    candidates = [DomainCandidate(**d) for d in data]
    console.print(f"[bold]Loaded {len(candidates)} candidates[/bold]")

    # Check registrar configuration
    configured = RegistrarFactory.get_configured_registrars()
    if not configured:
        console.print("[red]Error: No registrar API keys configured![/red]")
        console.print("Set PORKBUN_API_KEY/PORKBUN_API_SECRET or DYNADOT_API_KEY")
        raise typer.Exit(1)

    console.print(f"[dim]Configured registrars: {', '.join(r.value for r in configured)}[/dim]")

    async def run_search():
        config = SearchConfig(
            target_price=Decimal(str(target_price)),
            max_price=Decimal(str(max_price)),
        )
        return await search_registrars(candidates, config)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Searching {len(candidates)} domains...", total=None)
        results = asyncio.run(run_search())
        progress.remove_task(task)

    display_results_table(results)

    # Save if requested
    if output:
        data = [r.model_dump(mode="json") for r in results]
        with open(output, "w") as f:
            json.dump(data, f, indent=2, default=str)
        console.print(f"\n[dim]Saved {len(results)} results to {output}[/dim]")


@app.command()
def fuzzy(
    domain: str = typer.Argument(..., help="Domain to search (e.g., 'example.com')"),
    max_price: float = typer.Option(15.0, "--max-price", help="Maximum price filter"),
    variations: int = typer.Option(10, "--variations", "-v", help="Max variations to try"),
):
    """
    Quick fuzzy search for a single domain.

    Searches the exact domain plus variations across all registrars.

    Example:
        domain-source fuzzy "acme-growth.com" --max-price 10
    """
    # Validate domain format
    if "." not in domain:
        console.print("[red]Error: Invalid domain format. Use 'name.tld' (e.g., 'example.com')[/red]")
        raise typer.Exit(1)

    # Check registrar configuration
    configured = RegistrarFactory.get_configured_registrars()
    if not configured:
        console.print("[red]Error: No registrar API keys configured![/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Fuzzy searching:[/bold] {domain}")
    console.print(f"[dim]Registrars: {', '.join(r.value for r in configured)}[/dim]")

    async def run_fuzzy():
        return await fuzzy_search(
            domain,
            target_price=Decimal(str(max_price)),
            max_results=variations * 2,
        )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Searching...", total=None)
        results = asyncio.run(run_fuzzy())
        progress.remove_task(task)

    if results:
        display_results_table(results, title=f"Results for '{domain}'")
    else:
        console.print("[yellow]No available domains found.[/yellow]")


@app.command()
def registrars():
    """
    Show configured registrar status.

    Checks which registrar API keys are configured.
    """
    console.print("[bold]Registrar Configuration Status[/bold]\n")

    import os

    # Porkbun
    porkbun_key = os.environ.get("PORKBUN_API_KEY", "")
    porkbun_secret = os.environ.get("PORKBUN_API_SECRET", "")
    porkbun_status = "[green]✓ Configured[/green]" if (porkbun_key and porkbun_secret) else "[red]✗ Not configured[/red]"
    console.print(f"Porkbun: {porkbun_status}")
    if not (porkbun_key and porkbun_secret):
        console.print("  [dim]Set PORKBUN_API_KEY and PORKBUN_API_SECRET[/dim]")

    # Dynadot
    dynadot_key = os.environ.get("DYNADOT_API_KEY", "")
    dynadot_status = "[green]✓ Configured[/green]" if dynadot_key else "[red]✗ Not configured[/red]"
    console.print(f"Dynadot: {dynadot_status}")
    if not dynadot_key:
        console.print("  [dim]Set DYNADOT_API_KEY[/dim]")

    # LLM for generation
    console.print("\n[bold]AI Generation Configuration[/bold]\n")

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openai_status = "[green]✓ Configured[/green]" if openai_key else "[yellow]○ Not configured (will use fallback)[/yellow]"
    console.print(f"OpenAI: {openai_status}")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    anthropic_status = "[green]✓ Configured[/green]" if anthropic_key else "[dim]○ Not configured[/dim]"
    console.print(f"Anthropic: {anthropic_status}")


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
