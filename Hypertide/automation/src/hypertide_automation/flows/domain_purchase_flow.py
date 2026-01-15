"""
Prefect Flow: Domain Purchase

Google Sheets-driven workflow for purchasing domains from Hypertide.
Reads approved domains from sheet, executes purchase, updates status.

Flow Structure:
    1. Read "approved" domains from Google Sheet
    2. Group by provider (Entra/Google)
    3. Execute Hypertide purchase automation
    4. Update sheet with results

Usage:
    # Run manually
    python -m hypertide_automation.flows.domain_purchase_flow

    # Deploy to Prefect
    prefect deployment build flows/domain_purchase_flow.py:domain_purchase_flow -n "hypertide-domain-purchase"
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from prefect import flow, task, get_run_logger
from prefect.tasks import task_input_hash
from prefect.blocks.system import Secret
from pydantic import BaseModel

from .sheets import SheetsClient, SHEET_CONFIG
from ..client import HypertideClient
from ..purchase import PurchaseAutomation
from ..models import (
    OrderRequest,
    OrderResult,
    OrderType,
    SendingTool,
    DomainConfig,
)
from ..config import get_config


# ============================================================================
# Task Models
# ============================================================================

class DomainPurchaseInput(BaseModel):
    """Input for domain purchase flow."""
    sheet_id: str
    headless: bool = False
    dry_run: bool = False
    max_domains: int = 10  # Safety limit per run


class DomainPurchaseResult(BaseModel):
    """Result of domain purchase flow."""
    total_processed: int
    successful: int
    failed: int
    domains: List[Dict[str, Any]]
    errors: List[str]


# ============================================================================
# Prefect Tasks
# ============================================================================

@task(
    name="read-approved-domains",
    description="Read domains with status 'approved' from Google Sheet",
    retries=2,
    retry_delay_seconds=5,
)
def read_approved_domains(sheet_id: str, max_domains: int = 10) -> List[Dict[str, Any]]:
    """
    Read approved domains from Google Sheet.

    Args:
        sheet_id: Google Sheet ID
        max_domains: Maximum domains to process in one run

    Returns:
        List of approved domain records
    """
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)
    domains = client.get_approved_domains()

    logger.info(f"Found {len(domains)} approved domains in sheet")

    # Respect safety limit
    if len(domains) > max_domains:
        logger.warning(f"Limiting to {max_domains} domains (found {len(domains)})")
        domains = domains[:max_domains]

    return domains


@task(
    name="mark-domains-purchasing",
    description="Update domain status to 'purchasing' in sheet",
)
def mark_domains_purchasing(sheet_id: str, domains: List[Dict[str, Any]]) -> int:
    """Mark domains as 'purchasing' before processing."""
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)
    updated = 0

    for domain in domains:
        success = client.update_domain_status(
            domain=domain["domain"],
            status="purchasing",
        )
        if success:
            updated += 1

    logger.info(f"Marked {updated} domains as 'purchasing'")
    return updated


@task(
    name="get-sheet-config",
    description="Read configuration from Config tab",
    cache_key_fn=task_input_hash,
    cache_expiration=datetime.timedelta(minutes=5),
)
def get_sheet_config(sheet_id: str) -> Dict[str, str]:
    """Get client configuration from sheet's Config tab."""
    client = SheetsClient(sheet_id=sheet_id)
    return client.get_config()


@task(
    name="group-domains-by-provider",
    description="Group domains by provider type (entra/google)",
)
def group_domains_by_provider(
    domains: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """Group domains by their provider."""
    grouped = {"entra": [], "google": []}

    for domain in domains:
        provider = domain.get("provider", "entra").lower()
        if provider in grouped:
            grouped[provider].append(domain)
        else:
            grouped["entra"].append(domain)

    return grouped


@task(
    name="purchase-provider-domains",
    description="Purchase domains for a specific provider via Hypertide",
    timeout_seconds=600,  # 10 minute timeout per provider
)
async def purchase_provider_domains(
    provider: str,
    domains: List[Dict[str, Any]],
    client_name: str,
    forwarding_domain: str,
    headless: bool = False,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """
    Purchase domains from Hypertide for a specific provider.

    Args:
        provider: "entra" or "google"
        domains: List of domain records to purchase
        client_name: Client name for Hypertide
        forwarding_domain: Forwarding domain for inbox setup
        headless: Run browser in headless mode
        dry_run: If True, simulate without actual purchase

    Returns:
        List of purchase results per domain
    """
    logger = get_run_logger()
    results = []

    if not domains:
        logger.info(f"No {provider} domains to purchase")
        return results

    logger.info(f"Purchasing {len(domains)} {provider} domains")

    if dry_run:
        logger.warning("DRY RUN - Simulating purchases")
        for domain in domains:
            results.append({
                "domain": domain["domain"],
                "provider": provider,
                "success": True,
                "hypertide_id": f"DRY-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "error": None,
            })
        return results

    # Determine order type
    order_type = (
        OrderType.HYPERTIDE_ENTRA
        if provider == "entra"
        else OrderType.HYPERTIDE_GOOGLE
    )

    # Calculate quantity (domains per order)
    domains_per_order = 2 if provider == "entra" else 5
    quantity = max(1, (len(domains) + domains_per_order - 1) // domains_per_order)

    # Create domain configs
    domain_configs = [
        DomainConfig(
            name=d["domain"].rsplit(".", 1)[0],
            tld=d["domain"].rsplit(".", 1)[-1] if "." in d["domain"] else "com",
            use_hypertide_domain=True,
        )
        for d in domains
    ]

    # Create order request
    order_request = OrderRequest(
        client_name=client_name,
        forwarding_domain=forwarding_domain,
        order_type=order_type,
        quantity=quantity,
        sending_tool=SendingTool.BISON,
        domains=domain_configs,
        use_saved_payment=True,
    )

    # Execute purchase
    config = get_config()
    config.headless = headless

    try:
        async with HypertideClient(config) as ht_client:
            await ht_client.ensure_authenticated()
            automation = PurchaseAutomation(ht_client)

            order_result = await automation.execute(order_request)

            # Map results back to domains
            for domain in domains:
                results.append({
                    "domain": domain["domain"],
                    "provider": provider,
                    "success": order_result.success,
                    "hypertide_id": order_result.order_id if order_result.success else None,
                    "error": order_result.error_message if not order_result.success else None,
                })

    except Exception as e:
        logger.error(f"Purchase automation failed: {e}")
        for domain in domains:
            results.append({
                "domain": domain["domain"],
                "provider": provider,
                "success": False,
                "hypertide_id": None,
                "error": str(e),
            })

    return results


@task(
    name="update-sheet-results",
    description="Update Google Sheet with purchase results",
)
def update_sheet_results(
    sheet_id: str,
    results: List[Dict[str, Any]],
) -> Dict[str, int]:
    """
    Update sheet with purchase results.

    Args:
        sheet_id: Google Sheet ID
        results: List of purchase results

    Returns:
        Dict with counts of updates by status
    """
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)
    counts = {"purchased": 0, "failed": 0}

    for result in results:
        status = "purchased" if result["success"] else "failed"

        success = client.update_domain_status(
            domain=result["domain"],
            status=status,
            hypertide_id=result.get("hypertide_id"),
            error=result.get("error"),
        )

        if success:
            counts[status] += 1

    logger.info(f"Updated sheet: {counts['purchased']} purchased, {counts['failed']} failed")
    return counts


# ============================================================================
# Main Flow
# ============================================================================

@flow(
    name="domain-purchase-flow",
    description="Purchase approved domains from Google Sheet via Hypertide",
    version="1.0.0",
    retries=0,  # Don't retry the whole flow
)
async def domain_purchase_flow(
    sheet_id: str,
    headless: bool = False,
    dry_run: bool = False,
    max_domains: int = 10,
) -> DomainPurchaseResult:
    """
    Main flow: Purchase domains from Hypertide based on Google Sheet.

    Process:
        1. Read domains with status="approved" from Domains tab
        2. Get client config (name, forwarding domain) from Config tab
        3. Mark domains as "purchasing"
        4. Group by provider and execute Hypertide purchase
        5. Update sheet with results (purchased/failed)

    Args:
        sheet_id: Google Sheet ID (from URL)
        headless: Run browser in headless mode
        dry_run: Simulate purchases without executing
        max_domains: Maximum domains to process per run

    Returns:
        DomainPurchaseResult with summary and details
    """
    logger = get_run_logger()
    logger.info(f"Starting domain purchase flow (sheet: {sheet_id})")

    errors = []
    all_results = []

    # Step 1: Read approved domains
    domains = read_approved_domains(sheet_id, max_domains)

    if not domains:
        logger.info("No approved domains to process")
        return DomainPurchaseResult(
            total_processed=0,
            successful=0,
            failed=0,
            domains=[],
            errors=[],
        )

    # Step 2: Get configuration
    config = get_sheet_config(sheet_id)
    client_name = config.get("client_name", "Unknown Client")
    forwarding_domain = config.get("forwarding_domain", "")

    if not forwarding_domain:
        error = "No forwarding_domain configured in Config tab"
        logger.error(error)
        errors.append(error)
        # Mark all as failed
        for domain in domains:
            all_results.append({
                "domain": domain["domain"],
                "provider": domain.get("provider", "entra"),
                "success": False,
                "hypertide_id": None,
                "error": error,
            })
        update_sheet_results(sheet_id, all_results)
        return DomainPurchaseResult(
            total_processed=len(domains),
            successful=0,
            failed=len(domains),
            domains=all_results,
            errors=errors,
        )

    logger.info(f"Client: {client_name}, Forwarding: {forwarding_domain}")

    # Step 3: Mark as purchasing
    mark_domains_purchasing(sheet_id, domains)

    # Step 4: Group by provider
    grouped = group_domains_by_provider(domains)
    logger.info(f"Grouped: {len(grouped['entra'])} Entra, {len(grouped['google'])} Google")

    # Step 5: Purchase each provider group
    for provider in ["entra", "google"]:
        provider_domains = grouped[provider]
        if provider_domains:
            try:
                results = await purchase_provider_domains(
                    provider=provider,
                    domains=provider_domains,
                    client_name=client_name,
                    forwarding_domain=forwarding_domain,
                    headless=headless,
                    dry_run=dry_run,
                )
                all_results.extend(results)
            except Exception as e:
                error = f"{provider} purchase failed: {e}"
                logger.error(error)
                errors.append(error)
                for domain in provider_domains:
                    all_results.append({
                        "domain": domain["domain"],
                        "provider": provider,
                        "success": False,
                        "hypertide_id": None,
                        "error": str(e),
                    })

    # Step 6: Update sheet with results
    update_sheet_results(sheet_id, all_results)

    # Summary
    successful = sum(1 for r in all_results if r["success"])
    failed = len(all_results) - successful

    logger.info(f"Flow complete: {successful} purchased, {failed} failed")

    return DomainPurchaseResult(
        total_processed=len(all_results),
        successful=successful,
        failed=failed,
        domains=all_results,
        errors=errors,
    )


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Run the flow manually (for testing)."""
    import os

    sheet_id = os.getenv("HYPERTIDE_SHEET_ID")
    if not sheet_id:
        print("Error: HYPERTIDE_SHEET_ID environment variable required")
        print("Set it to your Google Sheet ID (from the URL)")
        return 1

    result = asyncio.run(domain_purchase_flow(
        sheet_id=sheet_id,
        headless=False,
        dry_run=True,  # Default to dry run for safety
    ))

    print(f"\nResults:")
    print(f"  Total processed: {result.total_processed}")
    print(f"  Successful: {result.successful}")
    print(f"  Failed: {result.failed}")

    if result.errors:
        print(f"\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    exit(main())
