"""
Hypertide Automation Prefect Flows.

Google Sheets-driven dashboard for domain purchasing and inbox provisioning.

Flows:
    domain_generation_flow - Generate variations, check prices, populate Domains tab
    domain_purchase_flow   - Purchase approved domains via Hypertide
    inbox_provision_flow   - Generate inboxes, provision, upload to Email Bison
    full_pipeline_flow     - Combined end-to-end flow

Sheet Structure:
    Requests Tab:
        | keyword | tld_preferences | provider | max_price | inboxes_per_domain | status | ...
        Status: pending → processing → completed/failed

    Domains Tab:
        | domain | tld | registrar | price | renewal_price | available | provider | status | ...
        Status: suggested → approved → purchasing → purchased/failed

    Inboxes Tab:
        | email | first_name | last_name | domain | provider | status | workspace | ...
        Status: pending → provisioning → provisioned → uploaded/failed

    Config Tab:
        | key | value | description |
        Required: client_name, forwarding_domain, emailbison_workspace

    Summary Tab:
        Dashboard with counts, costs, and status overview
"""

from .sheets import SheetsClient, SHEET_CONFIG
from .sheet_creator import DashboardCreator
from .domain_generation_flow import domain_generation_flow, DomainGenerationResult
from .domain_purchase_flow import domain_purchase_flow, DomainPurchaseResult
from .inbox_provision_flow import inbox_provision_flow, InboxProvisionResult
from .pipeline import full_pipeline_flow, PipelineResult

__all__ = [
    # Sheets client
    "SheetsClient",
    "SHEET_CONFIG",
    "DashboardCreator",
    # Flows
    "domain_generation_flow",
    "domain_purchase_flow",
    "inbox_provision_flow",
    "full_pipeline_flow",
    # Result types
    "DomainGenerationResult",
    "DomainPurchaseResult",
    "InboxProvisionResult",
    "PipelineResult",
]
