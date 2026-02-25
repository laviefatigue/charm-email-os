"""
Google Sheets client for Hypertide automation.

Provides read/write access to the domain and inbox tracking sheets.
Uses gspread with service account authentication.

Sheet Structure:
    - Domains Tab: Track domain purchases
    - Inboxes Tab: Track inbox provisioning
    - Config Tab: Client settings (workspace, forwarding domain, etc.)
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
import structlog

logger = structlog.get_logger()


# ============================================================================
# Configuration
# ============================================================================

SHEET_CONFIG = {
    # Sheet names
    "requests_tab": "Requests",
    "domains_tab": "Domains",
    "inboxes_tab": "Inboxes",
    "config_tab": "Config",
    "summary_tab": "Summary",

    # Request columns (0-indexed) - NEW for domain generation workflow
    "request_cols": {
        "keyword": 0,
        "tld_preferences": 1,
        "provider": 2,
        "max_price": 3,
        "inboxes_per_domain": 4,
        "status": 5,
        "submitted_at": 6,
        "processed_at": 7,
        "notes": 8,
    },

    # Domain columns (0-indexed) - EXPANDED with price/registrar info
    "domain_cols": {
        "domain": 0,
        "tld": 1,
        "registrar": 2,       # porkbun / dynadot / etc
        "price": 3,           # purchase price quote
        "renewal_price": 4,   # annual renewal
        "available": 5,       # TRUE / FALSE
        "provider": 6,        # entra / google
        "status": 7,          # suggested / quoted / approved / rejected / purchasing / purchased / failed
        "approved_by": 8,
        "approved_at": 9,
        "hypertide_id": 10,
        "purchased_at": 11,
        "error": 12,
    },

    # Inbox columns (0-indexed)
    "inbox_cols": {
        "email": 0,
        "first_name": 1,
        "last_name": 2,
        "domain": 3,
        "provider": 4,
        "status": 5,          # pending / approved / provisioning / provisioned / uploaded / failed
        "workspace": 6,
        "uploaded_at": 7,
        "error": 8,
    },

    # Status values
    "request_statuses": {
        "pending": "pending",
        "processing": "processing",
        "completed": "completed",
        "failed": "failed",
    },

    "domain_statuses": {
        "suggested": "suggested",     # Generated, no price yet
        "quoted": "quoted",           # Price retrieved, awaiting approval
        "approved": "approved",       # Ready for purchase
        "rejected": "rejected",       # User rejected (too expensive, etc)
        "purchasing": "purchasing",
        "purchased": "purchased",
        "failed": "failed",
    },

    "inbox_statuses": {
        "pending": "pending",
        "approved": "approved",
        "provisioning": "provisioning",
        "provisioned": "provisioned",
        "uploaded": "uploaded",
        "failed": "failed",
    },
}


# ============================================================================
# Google Sheets Client
# ============================================================================

class SheetsClient:
    """
    Client for Google Sheets integration.

    Usage:
        client = SheetsClient(sheet_id="your-sheet-id")
        domains = client.get_approved_domains()
        client.update_domain_status("example.com", "purchased", hypertide_id="HT-123")
    """

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(
        self,
        sheet_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize the Sheets client.

        Args:
            sheet_id: Google Sheet ID (from URL). Falls back to HYPERTIDE_SHEET_ID env var.
            credentials_path: Path to service account JSON. Falls back to GOOGLE_CREDENTIALS_PATH.
        """
        self.sheet_id = sheet_id or os.getenv("HYPERTIDE_SHEET_ID")
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_CREDENTIALS_PATH",
            str(Path.home() / ".config" / "gcloud" / "service-account.json")
        )

        if not self.sheet_id:
            raise ValueError("Sheet ID required. Set HYPERTIDE_SHEET_ID env var or pass sheet_id.")

        self._gc: Optional[gspread.Client] = None
        self._sheet: Optional[gspread.Spreadsheet] = None

    def _connect(self) -> None:
        """Establish connection to Google Sheets."""
        if self._gc is None:
            creds = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=self.SCOPES,
            )
            self._gc = gspread.authorize(creds)
            self._sheet = self._gc.open_by_key(self.sheet_id)
            logger.info("Connected to Google Sheet", sheet_id=self.sheet_id)

    @property
    def sheet(self) -> gspread.Spreadsheet:
        """Get the spreadsheet, connecting if necessary."""
        if self._sheet is None:
            self._connect()
        return self._sheet

    # =========================================================================
    # Domain Operations
    # =========================================================================

    def get_domains_worksheet(self) -> gspread.Worksheet:
        """Get the Domains worksheet."""
        return self.sheet.worksheet(SHEET_CONFIG["domains_tab"])

    def get_all_domains(self) -> List[Dict[str, Any]]:
        """Get all domains from the sheet."""
        ws = self.get_domains_worksheet()
        rows = ws.get_all_values()

        if not rows or len(rows) < 2:
            return []

        # Skip header row
        domains = []
        cols = SHEET_CONFIG["domain_cols"]

        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or not row[0]:  # Skip empty rows
                continue

            # Parse price values safely
            price = None
            renewal_price = None
            try:
                if len(row) > cols["price"] and row[cols["price"]]:
                    price = float(row[cols["price"]].replace("$", "").replace(",", ""))
            except (ValueError, AttributeError):
                pass
            try:
                if len(row) > cols["renewal_price"] and row[cols["renewal_price"]]:
                    renewal_price = float(row[cols["renewal_price"]].replace("$", "").replace(",", ""))
            except (ValueError, AttributeError):
                pass

            domain = {
                "row": row_idx,
                "domain": row[cols["domain"]] if len(row) > cols["domain"] else "",
                "tld": row[cols["tld"]] if len(row) > cols["tld"] else "",
                "registrar": row[cols["registrar"]] if len(row) > cols["registrar"] else "",
                "price": price,
                "renewal_price": renewal_price,
                "available": row[cols["available"]].upper() == "TRUE" if len(row) > cols["available"] and row[cols["available"]] else False,
                "provider": row[cols["provider"]] if len(row) > cols["provider"] else "entra",
                "status": row[cols["status"]] if len(row) > cols["status"] else "suggested",
                "approved_by": row[cols["approved_by"]] if len(row) > cols["approved_by"] else "",
                "approved_at": row[cols["approved_at"]] if len(row) > cols["approved_at"] else "",
                "hypertide_id": row[cols["hypertide_id"]] if len(row) > cols["hypertide_id"] else "",
                "purchased_at": row[cols["purchased_at"]] if len(row) > cols["purchased_at"] else "",
                "error": row[cols["error"]] if len(row) > cols["error"] else "",
            }
            domains.append(domain)

        return domains

    def get_approved_domains(self) -> List[Dict[str, Any]]:
        """Get domains with status 'approved'."""
        all_domains = self.get_all_domains()
        return [d for d in all_domains if d["status"] == "approved"]

    def get_domains_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get domains with a specific status."""
        all_domains = self.get_all_domains()
        return [d for d in all_domains if d["status"] == status]

    def update_domain_status(
        self,
        domain: str,
        status: str,
        hypertide_id: Optional[str] = None,
        error: Optional[str] = None,
        approved_by: Optional[str] = None,
    ) -> bool:
        """
        Update a domain's status in the sheet.

        Args:
            domain: Domain name to update
            status: New status value
            hypertide_id: Hypertide order/domain ID (optional)
            error: Error message if failed (optional)
            approved_by: User who approved (optional)

        Returns:
            True if updated, False if domain not found
        """
        ws = self.get_domains_worksheet()
        all_domains = self.get_all_domains()

        for d in all_domains:
            if d["domain"] == domain:
                row = d["row"]
                cols = SHEET_CONFIG["domain_cols"]

                # Update status
                ws.update_cell(row, cols["status"] + 1, status)

                # Update approval info
                if status == "approved":
                    if approved_by:
                        ws.update_cell(row, cols["approved_by"] + 1, approved_by)
                    ws.update_cell(row, cols["approved_at"] + 1, datetime.utcnow().isoformat())

                # Update hypertide_id if provided
                if hypertide_id:
                    ws.update_cell(row, cols["hypertide_id"] + 1, hypertide_id)

                # Update timestamp for purchased status
                if status == "purchased":
                    ws.update_cell(row, cols["purchased_at"] + 1, datetime.utcnow().isoformat())

                # Update error if provided
                if error:
                    ws.update_cell(row, cols["error"] + 1, error)
                elif status == "purchased":
                    ws.update_cell(row, cols["error"] + 1, "")  # Clear error on success

                logger.info("Updated domain status", domain=domain, status=status)
                return True

        logger.warning("Domain not found in sheet", domain=domain)
        return False

    def batch_update_domain_status(
        self,
        updates: List[Dict[str, Any]],
    ) -> int:
        """
        Batch update multiple domains.

        Args:
            updates: List of {domain, status, hypertide_id?, error?}

        Returns:
            Number of domains updated
        """
        updated = 0
        for update in updates:
            if self.update_domain_status(
                domain=update["domain"],
                status=update["status"],
                hypertide_id=update.get("hypertide_id"),
                error=update.get("error"),
            ):
                updated += 1
        return updated

    def add_domains(self, domains: List[Dict[str, Any]]) -> int:
        """
        Add new domains to the sheet (from domain generation flow).

        Args:
            domains: List of domain dicts with:
                - domain: full domain name
                - tld: top-level domain
                - registrar: registrar name
                - price: purchase price (float)
                - renewal_price: renewal price (float)
                - available: True/False
                - provider: entra/google
                - status: suggested/quoted

        Returns:
            Number of domains added
        """
        ws = self.get_domains_worksheet()
        cols = SHEET_CONFIG["domain_cols"]

        rows_to_add = []
        for d in domains:
            # Build row in correct column order
            row = [""] * (max(cols.values()) + 1)
            row[cols["domain"]] = d.get("domain", "")
            row[cols["tld"]] = d.get("tld", "")
            row[cols["registrar"]] = d.get("registrar", "")
            row[cols["price"]] = f"${d['price']:.2f}" if d.get("price") else ""
            row[cols["renewal_price"]] = f"${d['renewal_price']:.2f}" if d.get("renewal_price") else ""
            row[cols["available"]] = "TRUE" if d.get("available") else "FALSE"
            row[cols["provider"]] = d.get("provider", "entra")
            row[cols["status"]] = d.get("status", "suggested")
            rows_to_add.append(row)

        if rows_to_add:
            ws.append_rows(rows_to_add)
            logger.info("Added domains to sheet", count=len(rows_to_add))

        return len(rows_to_add)

    def get_purchased_domains(self) -> List[Dict[str, Any]]:
        """Get domains with status 'purchased' (for inbox generation)."""
        all_domains = self.get_all_domains()
        return [d for d in all_domains if d["status"] == "purchased"]

    # =========================================================================
    # Request Operations (for domain generation workflow)
    # =========================================================================

    def get_requests_worksheet(self) -> gspread.Worksheet:
        """Get the Requests worksheet."""
        return self.sheet.worksheet(SHEET_CONFIG["requests_tab"])

    def get_all_requests(self) -> List[Dict[str, Any]]:
        """Get all requests from the sheet."""
        ws = self.get_requests_worksheet()
        rows = ws.get_all_values()

        if not rows or len(rows) < 2:
            return []

        requests = []
        cols = SHEET_CONFIG["request_cols"]

        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or not row[0]:  # Skip empty rows
                continue

            # Parse max_price safely
            max_price = None
            try:
                if len(row) > cols["max_price"] and row[cols["max_price"]]:
                    max_price = float(row[cols["max_price"]].replace("$", "").replace(",", ""))
            except (ValueError, AttributeError):
                pass

            # Parse inboxes_per_domain safely
            inboxes_per_domain = 50  # default
            try:
                if len(row) > cols["inboxes_per_domain"] and row[cols["inboxes_per_domain"]]:
                    inboxes_per_domain = int(row[cols["inboxes_per_domain"]])
            except (ValueError, AttributeError):
                pass

            request = {
                "row": row_idx,
                "keyword": row[cols["keyword"]] if len(row) > cols["keyword"] else "",
                "tld_preferences": row[cols["tld_preferences"]] if len(row) > cols["tld_preferences"] else "com,net,io",
                "provider": row[cols["provider"]] if len(row) > cols["provider"] else "entra",
                "max_price": max_price,
                "inboxes_per_domain": inboxes_per_domain,
                "status": row[cols["status"]] if len(row) > cols["status"] else "pending",
                "submitted_at": row[cols["submitted_at"]] if len(row) > cols["submitted_at"] else "",
                "processed_at": row[cols["processed_at"]] if len(row) > cols["processed_at"] else "",
                "notes": row[cols["notes"]] if len(row) > cols["notes"] else "",
            }
            requests.append(request)

        return requests

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """Get requests with status 'pending'."""
        all_requests = self.get_all_requests()
        return [r for r in all_requests if r["status"] == "pending"]

    def update_request_status(
        self,
        row: int,
        status: str,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Update a request's status in the sheet.

        Args:
            row: Row number in sheet
            status: New status value
            notes: Optional notes to add

        Returns:
            True if updated successfully
        """
        ws = self.get_requests_worksheet()
        cols = SHEET_CONFIG["request_cols"]

        try:
            ws.update_cell(row, cols["status"] + 1, status)

            if status == "processing":
                pass  # No timestamp for processing
            elif status in ["completed", "failed"]:
                ws.update_cell(row, cols["processed_at"] + 1, datetime.utcnow().isoformat())

            if notes:
                ws.update_cell(row, cols["notes"] + 1, notes)

            logger.info("Updated request status", row=row, status=status)
            return True
        except Exception as e:
            logger.error("Failed to update request", row=row, error=str(e))
            return False

    # =========================================================================
    # Inbox Operations
    # =========================================================================

    def get_inboxes_worksheet(self) -> gspread.Worksheet:
        """Get the Inboxes worksheet."""
        return self.sheet.worksheet(SHEET_CONFIG["inboxes_tab"])

    def get_all_inboxes(self) -> List[Dict[str, Any]]:
        """Get all inboxes from the sheet."""
        ws = self.get_inboxes_worksheet()
        rows = ws.get_all_values()

        if not rows or len(rows) < 2:
            return []

        inboxes = []
        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or not row[0]:
                continue

            inbox = {
                "row": row_idx,
                "email": row[0] if len(row) > 0 else "",
                "first_name": row[1] if len(row) > 1 else "",
                "last_name": row[2] if len(row) > 2 else "",
                "domain": row[3] if len(row) > 3 else "",
                "provider": row[4] if len(row) > 4 else "entra",
                "status": row[5] if len(row) > 5 else "pending",
                "workspace": row[6] if len(row) > 6 else "",
                "uploaded_at": row[7] if len(row) > 7 else "",
                "error": row[8] if len(row) > 8 else "",
            }
            inboxes.append(inbox)

        return inboxes

    def get_inboxes_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get inboxes with a specific status."""
        all_inboxes = self.get_all_inboxes()
        return [i for i in all_inboxes if i["status"] == status]

    def add_inboxes(self, inboxes: List[Dict[str, Any]]) -> int:
        """
        Add new inboxes to the sheet.

        Args:
            inboxes: List of {email, first_name, last_name, domain, provider, workspace}

        Returns:
            Number of inboxes added
        """
        ws = self.get_inboxes_worksheet()

        rows_to_add = []
        for inbox in inboxes:
            row = [
                inbox.get("email", ""),
                inbox.get("first_name", ""),
                inbox.get("last_name", ""),
                inbox.get("domain", ""),
                inbox.get("provider", "entra"),
                "pending",  # Initial status
                inbox.get("workspace", ""),
                "",  # uploaded_at
                "",  # error
            ]
            rows_to_add.append(row)

        if rows_to_add:
            ws.append_rows(rows_to_add)
            logger.info("Added inboxes to sheet", count=len(rows_to_add))

        return len(rows_to_add)

    def update_inbox_status(
        self,
        email: str,
        status: str,
        error: Optional[str] = None,
    ) -> bool:
        """Update an inbox's status."""
        ws = self.get_inboxes_worksheet()
        all_inboxes = self.get_all_inboxes()

        for inbox in all_inboxes:
            if inbox["email"] == email:
                row = inbox["row"]
                cols = SHEET_CONFIG["inbox_cols"]

                ws.update_cell(row, cols["status"] + 1, status)

                if status == "uploaded":
                    ws.update_cell(row, cols["uploaded_at"] + 1, datetime.utcnow().isoformat())

                if error:
                    ws.update_cell(row, cols["error"] + 1, error)
                elif status in ["provisioned", "uploaded"]:
                    ws.update_cell(row, cols["error"] + 1, "")

                logger.info("Updated inbox status", email=email, status=status)
                return True

        return False

    # =========================================================================
    # Config Operations
    # =========================================================================

    def get_config(self) -> Dict[str, str]:
        """Get configuration from the Config tab."""
        try:
            ws = self.sheet.worksheet(SHEET_CONFIG["config_tab"])
            rows = ws.get_all_values()

            config = {}
            for row in rows:
                if len(row) >= 2 and row[0]:
                    config[row[0]] = row[1]

            return config
        except gspread.WorksheetNotFound:
            logger.warning("Config tab not found in sheet")
            return {}

    def get_client_name(self) -> str:
        """Get client name from config."""
        return self.get_config().get("client_name", "Unknown")

    def get_workspace(self) -> str:
        """Get Email Bison workspace from config."""
        return self.get_config().get("emailbison_workspace", "")

    def get_forwarding_domain(self) -> str:
        """Get forwarding domain from config."""
        return self.get_config().get("forwarding_domain", "")


# ============================================================================
# Convenience Functions
# ============================================================================

def get_sheets_client(sheet_id: Optional[str] = None) -> SheetsClient:
    """Get a configured SheetsClient instance."""
    return SheetsClient(sheet_id=sheet_id)
