"""
Prefect Flow: Full Pipeline

Combines domain purchase and inbox provisioning into a single flow.
Useful for end-to-end processing of new client orders.

Usage:
    python -m hypertide_automation.flows.pipeline

    # Or via Prefect
    prefect deployment run full-pipeline-dry-run
"""

import asyncio
from typing import Optional, List

from prefect import flow, get_run_logger
from pydantic import BaseModel

from .domain_purchase_flow import (
    domain_purchase_flow,
    DomainPurchaseResult,
)
from .inbox_provision_flow import (
    inbox_provision_flow,
    InboxProvisionResult,
)


class PipelineResult(BaseModel):
    """Result of the full pipeline."""
    domain_result: Optional[DomainPurchaseResult] = None
    inbox_result: Optional[InboxProvisionResult] = None
    success: bool
    errors: List[str]


@flow(
    name="full-pipeline-flow",
    description="Full pipeline: domain purchase → inbox provisioning",
    version="1.0.0",
)
async def full_pipeline_flow(
    sheet_id: str,
    headless: bool = False,
    dry_run: bool = True,
    max_domains: int = 10,
    skip_emailbison: bool = False,
) -> PipelineResult:
    """
    Run the full automation pipeline.

    Steps:
        1. Purchase approved domains from sheet
        2. Generate and provision inboxes
        3. Upload to Email Bison

    Args:
        sheet_id: Google Sheet ID
        headless: Run browser in headless mode
        dry_run: Simulate without actual operations
        max_domains: Maximum domains per run
        skip_emailbison: Skip Email Bison upload

    Returns:
        PipelineResult with combined results
    """
    logger = get_run_logger()
    logger.info("Starting full pipeline")

    errors = []

    # Step 1: Domain Purchase
    logger.info("=== Step 1: Domain Purchase ===")
    try:
        domain_result = await domain_purchase_flow(
            sheet_id=sheet_id,
            headless=headless,
            dry_run=dry_run,
            max_domains=max_domains,
        )
        logger.info(
            f"Domain purchase complete: {domain_result.successful} purchased, "
            f"{domain_result.failed} failed"
        )
        errors.extend(domain_result.errors)
    except Exception as e:
        logger.error(f"Domain purchase flow failed: {e}")
        errors.append(f"Domain purchase: {e}")
        domain_result = None

    # Step 2: Inbox Provisioning
    logger.info("=== Step 2: Inbox Provisioning ===")
    try:
        inbox_result = await inbox_provision_flow(
            sheet_id=sheet_id,
            headless=headless,
            dry_run=dry_run,
            skip_emailbison=skip_emailbison,
            generate_new=True,
        )
        logger.info(
            f"Inbox provisioning complete: {inbox_result.inboxes_generated} generated, "
            f"{inbox_result.inboxes_uploaded} uploaded"
        )
        errors.extend(inbox_result.errors)
    except Exception as e:
        logger.error(f"Inbox provisioning flow failed: {e}")
        errors.append(f"Inbox provisioning: {e}")
        inbox_result = None

    # Determine overall success
    success = (
        (domain_result is not None and domain_result.failed == 0) and
        (inbox_result is not None and inbox_result.failed == 0)
    )

    logger.info(f"Pipeline complete: success={success}")

    return PipelineResult(
        domain_result=domain_result,
        inbox_result=inbox_result,
        success=success,
        errors=errors,
    )


def main():
    """Run the pipeline manually."""
    import os

    sheet_id = os.getenv("HYPERTIDE_SHEET_ID")
    if not sheet_id:
        print("Error: HYPERTIDE_SHEET_ID environment variable required")
        return 1

    result = asyncio.run(full_pipeline_flow(
        sheet_id=sheet_id,
        headless=False,
        dry_run=True,
    ))

    print(f"\n{'='*50}")
    print("PIPELINE RESULTS")
    print(f"{'='*50}")

    if result.domain_result:
        print(f"\nDomains:")
        print(f"  Processed: {result.domain_result.total_processed}")
        print(f"  Successful: {result.domain_result.successful}")
        print(f"  Failed: {result.domain_result.failed}")

    if result.inbox_result:
        print(f"\nInboxes:")
        print(f"  Generated: {result.inbox_result.inboxes_generated}")
        print(f"  Provisioned: {result.inbox_result.inboxes_provisioned}")
        print(f"  Uploaded: {result.inbox_result.inboxes_uploaded}")
        print(f"  Failed: {result.inbox_result.failed}")

    print(f"\nOverall Success: {result.success}")

    if result.errors:
        print(f"\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    return 0 if result.success else 1


if __name__ == "__main__":
    exit(main())
