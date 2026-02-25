"""
Google Sheet Dashboard Creator

Programmatically creates the Hypertide automation dashboard with all required tabs,
formatting, and data validation.

Usage:
    # With service account JSON file
    python -m hypertide_automation.flows.sheet_creator --credentials /path/to/service-account.json --name "Client Name"

    # Share with your email
    python -m hypertide_automation.flows.sheet_creator --credentials key.json --name "Acme Corp" --share user@example.com
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="Create Hypertide automation dashboard in Google Sheets")


# ============================================================================
# Sheet Structure Configuration
# ============================================================================

DASHBOARD_CONFIG = {
    "tabs": {
        "requests": {
            "name": "Requests",
            "headers": [
                "keyword",
                "tld_preferences",
                "provider",
                "max_price",
                "inboxes_per_domain",
                "status",
                "submitted_at",
                "processed_at",
                "notes",
            ],
            "col_widths": {
                "keyword": 150,
                "tld_preferences": 120,
                "provider": 80,
                "max_price": 80,
                "inboxes_per_domain": 120,
                "status": 100,
                "submitted_at": 150,
                "processed_at": 150,
                "notes": 200,
            },
            "description": "Enter domain keywords here. System generates variations and checks prices.",
        },
        "domains": {
            "name": "Domains",
            "headers": [
                "domain",
                "tld",
                "registrar",
                "price",
                "renewal_price",
                "available",
                "provider",
                "status",
                "approved_by",
                "approved_at",
                "hypertide_id",
                "purchased_at",
                "error",
            ],
            "col_widths": {
                "domain": 200,
                "tld": 60,
                "registrar": 100,
                "price": 80,
                "renewal_price": 100,
                "available": 80,
                "provider": 80,
                "status": 100,
                "approved_by": 120,
                "approved_at": 150,
                "hypertide_id": 120,
                "purchased_at": 150,
                "error": 200,
            },
            "description": "Generated domains with pricing. Mark 'approved' to purchase.",
        },
        "inboxes": {
            "name": "Inboxes",
            "headers": [
                "email",
                "first_name",
                "last_name",
                "domain",
                "provider",
                "status",
                "workspace",
                "hypertide_inbox_id",
                "uploaded_at",
                "error",
            ],
            "col_widths": {
                "email": 250,
                "first_name": 100,
                "last_name": 100,
                "domain": 180,
                "provider": 80,
                "status": 100,
                "workspace": 150,
                "hypertide_inbox_id": 150,
                "uploaded_at": 150,
                "error": 200,
            },
            "description": "Generated inboxes for purchased domains.",
        },
        "config": {
            "name": "Config",
            "headers": ["key", "value", "description"],
            "col_widths": {
                "key": 200,
                "value": 300,
                "description": 400,
            },
            "default_values": [
                ("client_name", "", "Client/company name for Hypertide orders"),
                ("forwarding_domain", "", "Domain for email forwarding (e.g., client.com)"),
                ("emailbison_workspace", "", "Email Bison workspace name for uploads"),
                ("default_provider", "entra", "Default provider: entra or google"),
                ("default_max_price", "15.00", "Maximum price per domain (USD)"),
                ("entra_inboxes_per_domain", "50", "Number of inboxes per Entra domain"),
                ("google_inboxes_per_domain", "3", "Number of inboxes per Google domain"),
                ("auto_approve_under_price", "", "Auto-approve domains under this price (leave empty to disable)"),
                ("preferred_registrars", "porkbun,namecheap,dynadot", "Comma-separated list of preferred registrars"),
                ("preferred_tlds", "com,io,co,net", "Comma-separated list of preferred TLDs"),
            ],
            "description": "Configuration settings for the automation.",
        },
        "summary": {
            "name": "Summary",
            "headers": [],  # Custom layout
            "description": "Dashboard overview with costs and status.",
        },
    },
    "status_values": {
        "requests": ["pending", "processing", "completed", "failed"],
        "domains": ["suggested", "quoted", "approved", "rejected", "purchasing", "purchased", "failed"],
        "inboxes": ["pending", "approved", "provisioning", "provisioned", "uploaded", "failed"],
    },
}


# ============================================================================
# Sheet Creator Class
# ============================================================================

class DashboardCreator:
    """Creates and configures the Hypertide automation dashboard."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self, credentials_path: str):
        """
        Initialize with service account credentials.

        Args:
            credentials_path: Path to service account JSON file
        """
        self.credentials_path = credentials_path
        self._gc: Optional[gspread.Client] = None

    def _connect(self) -> gspread.Client:
        """Establish connection to Google Sheets API."""
        if self._gc is None:
            creds = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=self.SCOPES,
            )
            self._gc = gspread.authorize(creds)
        return self._gc

    def create_dashboard(
        self,
        name: str,
        share_with: Optional[List[str]] = None,
        folder_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new dashboard spreadsheet.

        Args:
            name: Name for the spreadsheet
            share_with: List of email addresses to share with
            folder_id: Google Drive folder ID (optional)

        Returns:
            Dict with sheet_id, url, and other metadata
        """
        gc = self._connect()

        # Create spreadsheet
        title = f"Hypertide Dashboard - {name}"
        spreadsheet = gc.create(title, folder_id=folder_id)

        console.print(f"[green]Created spreadsheet:[/green] {title}")
        console.print(f"[blue]Sheet ID:[/blue] {spreadsheet.id}")

        # Create tabs
        self._create_tabs(spreadsheet)

        # Set up formatting
        self._format_tabs(spreadsheet)

        # Add data validation
        self._add_validation(spreadsheet)

        # Add summary dashboard
        self._create_summary_dashboard(spreadsheet, name)

        # Share with users
        if share_with:
            for email in share_with:
                try:
                    spreadsheet.share(email, perm_type="user", role="writer")
                    console.print(f"[green]Shared with:[/green] {email}")
                except Exception as e:
                    console.print(f"[yellow]Could not share with {email}:[/yellow] {e}")

        return {
            "sheet_id": spreadsheet.id,
            "url": spreadsheet.url,
            "title": title,
            "created_at": datetime.utcnow().isoformat(),
        }

    def _create_tabs(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Create all required tabs."""
        config = DASHBOARD_CONFIG["tabs"]

        # Rename default Sheet1 to first tab
        first_tab = list(config.keys())[0]
        default_sheet = spreadsheet.sheet1
        default_sheet.update_title(config[first_tab]["name"])

        # Create remaining tabs
        for tab_key in list(config.keys())[1:]:
            tab_config = config[tab_key]
            spreadsheet.add_worksheet(
                title=tab_config["name"],
                rows=1000,
                cols=len(tab_config.get("headers", [])) or 10,
            )

        console.print(f"[green]Created {len(config)} tabs[/green]")

    def _format_tabs(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Format headers and columns for all tabs."""
        config = DASHBOARD_CONFIG["tabs"]

        for tab_key, tab_config in config.items():
            if tab_key == "summary":
                continue  # Summary has custom layout

            ws = spreadsheet.worksheet(tab_config["name"])
            headers = tab_config.get("headers", [])

            if headers:
                # Write headers
                ws.update("A1", [headers])

                # Format header row (bold, background color)
                ws.format("1:1", {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.95},
                })

                # Freeze header row
                ws.freeze(rows=1)

            # Add default config values if this is the config tab
            if tab_key == "config" and "default_values" in tab_config:
                values = [[k, v, d] for k, v, d in tab_config["default_values"]]
                ws.update("A2", values)

        console.print("[green]Formatted all tabs[/green]")

    def _add_validation(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Add data validation for status columns."""
        status_config = DASHBOARD_CONFIG["status_values"]
        tabs_config = DASHBOARD_CONFIG["tabs"]

        for tab_key, statuses in status_config.items():
            if tab_key not in tabs_config:
                continue

            tab_config = tabs_config[tab_key]
            headers = tab_config.get("headers", [])

            if "status" not in headers:
                continue

            ws = spreadsheet.worksheet(tab_config["name"])
            status_col_idx = headers.index("status")
            col_letter = chr(ord("A") + status_col_idx)

            # Create dropdown validation for status column
            # Note: gspread validation API is limited, using batch_update
            validation_rule = {
                "setDataValidation": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "endRowIndex": 1000,
                        "startColumnIndex": status_col_idx,
                        "endColumnIndex": status_col_idx + 1,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [{"userEnteredValue": s} for s in statuses],
                        },
                        "showCustomUi": True,
                        "strict": True,
                    },
                }
            }

            spreadsheet.batch_update({"requests": [validation_rule]})

        console.print("[green]Added status dropdowns[/green]")

    def _create_summary_dashboard(
        self,
        spreadsheet: gspread.Spreadsheet,
        client_name: str,
    ) -> None:
        """Create the summary dashboard tab."""
        ws = spreadsheet.worksheet("Summary")

        # Dashboard layout
        dashboard_content = [
            [f"HYPERTIDE DASHBOARD - {client_name.upper()}", "", "", ""],
            ["", "", "", ""],
            ["DOMAINS", "", "INBOXES", ""],
            ["Total Suggested:", "=COUNTA(Domains!A:A)-1", "Total Generated:", "=COUNTA(Inboxes!A:A)-1"],
            ["Approved:", '=COUNTIF(Domains!H:H,"approved")', "Approved:", '=COUNTIF(Inboxes!F:F,"approved")'],
            ["Purchased:", '=COUNTIF(Domains!H:H,"purchased")', "Provisioned:", '=COUNTIF(Inboxes!F:F,"provisioned")'],
            ["Failed:", '=COUNTIF(Domains!H:H,"failed")', "Uploaded:", '=COUNTIF(Inboxes!F:F,"uploaded")'],
            ["", "", "Failed:", '=COUNTIF(Inboxes!F:F,"failed")'],
            ["", "", "", ""],
            ["COSTS", "", "", ""],
            ["Estimated Total:", '=SUMIF(Domains!H:H,"approved",Domains!D:D)', "", ""],
            ["Actual Spent:", '=SUMIF(Domains!H:H,"purchased",Domains!D:D)', "", ""],
            ["", "", "", ""],
            ["REQUESTS", "", "", ""],
            ["Pending:", '=COUNTIF(Requests!F:F,"pending")', "", ""],
            ["Processing:", '=COUNTIF(Requests!F:F,"processing")', "", ""],
            ["Completed:", '=COUNTIF(Requests!F:F,"completed")', "", ""],
            ["", "", "", ""],
            ["Last Updated:", "=NOW()", "", ""],
        ]

        ws.update("A1", dashboard_content)

        # Format title
        ws.format("A1", {
            "textFormat": {"bold": True, "fontSize": 16},
        })

        # Format section headers
        ws.format("A3", {"textFormat": {"bold": True}})
        ws.format("C3", {"textFormat": {"bold": True}})
        ws.format("A10", {"textFormat": {"bold": True}})
        ws.format("A14", {"textFormat": {"bold": True}})

        console.print("[green]Created summary dashboard[/green]")


# ============================================================================
# CLI
# ============================================================================

@app.command()
def create(
    credentials: Path = typer.Option(
        ..., "--credentials", "-c",
        help="Path to Google service account JSON file"
    ),
    name: str = typer.Option(
        ..., "--name", "-n",
        help="Client/project name for the dashboard"
    ),
    share: Optional[List[str]] = typer.Option(
        None, "--share", "-s",
        help="Email addresses to share the sheet with (can specify multiple)"
    ),
    folder: Optional[str] = typer.Option(
        None, "--folder", "-f",
        help="Google Drive folder ID to create sheet in"
    ),
    output_env: bool = typer.Option(
        False, "--output-env",
        help="Output environment variable export commands"
    ),
):
    """
    Create a new Hypertide automation dashboard in Google Sheets.

    Example:
        python -m hypertide_automation.flows.sheet_creator -c key.json -n "Acme Corp" -s user@example.com
    """
    if not credentials.exists():
        console.print(f"[red]Credentials file not found: {credentials}[/red]")
        raise typer.Exit(code=1)

    creator = DashboardCreator(str(credentials))

    try:
        result = creator.create_dashboard(
            name=name,
            share_with=share,
            folder_id=folder,
        )

        # Display results
        console.print("\n[bold green]Dashboard created successfully![/bold green]\n")

        table = Table(title="Dashboard Details")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Sheet ID", result["sheet_id"])
        table.add_row("URL", result["url"])
        table.add_row("Title", result["title"])

        console.print(table)

        if output_env:
            console.print("\n[bold]Environment variables:[/bold]")
            console.print(f'export HYPERTIDE_SHEET_ID="{result["sheet_id"]}"')
            console.print(f'# Or on Windows:')
            console.print(f'set HYPERTIDE_SHEET_ID={result["sheet_id"]}')

        console.print(f"\n[bold]Next steps:[/bold]")
        console.print(f"1. Open the sheet: {result['url']}")
        console.print(f"2. Fill in the Config tab with client settings")
        console.print(f"3. Add domain requests to the Requests tab")
        console.print(f"4. Run: ht-flow-domains to process requests")

    except Exception as e:
        console.print(f"[red]Error creating dashboard: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def validate(
    credentials: Path = typer.Option(
        ..., "--credentials", "-c",
        help="Path to Google service account JSON file"
    ),
    sheet_id: str = typer.Option(
        ..., "--sheet-id", "-s",
        help="Google Sheet ID to validate"
    ),
):
    """
    Validate an existing dashboard has all required tabs and columns.
    """
    if not credentials.exists():
        console.print(f"[red]Credentials file not found: {credentials}[/red]")
        raise typer.Exit(code=1)

    try:
        creds = Credentials.from_service_account_file(
            str(credentials),
            scopes=DashboardCreator.SCOPES,
        )
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(sheet_id)

        console.print(f"[green]Connected to:[/green] {spreadsheet.title}")

        # Check tabs
        existing_tabs = [ws.title for ws in spreadsheet.worksheets()]
        required_tabs = [cfg["name"] for cfg in DASHBOARD_CONFIG["tabs"].values()]

        table = Table(title="Tab Validation")
        table.add_column("Tab", style="cyan")
        table.add_column("Status", style="green")

        all_valid = True
        for tab in required_tabs:
            if tab in existing_tabs:
                table.add_row(tab, "[green]✓ Found[/green]")
            else:
                table.add_row(tab, "[red]✗ Missing[/red]")
                all_valid = False

        console.print(table)

        if all_valid:
            console.print("\n[bold green]Dashboard is valid![/bold green]")
        else:
            console.print("\n[bold yellow]Some tabs are missing. Run 'create' to fix.[/bold yellow]")

    except Exception as e:
        console.print(f"[red]Validation error: {e}[/red]")
        raise typer.Exit(code=1)


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
