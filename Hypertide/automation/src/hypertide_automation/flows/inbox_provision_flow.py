"""
Prefect Flow: Inbox Provisioning

Google Sheets-driven workflow for provisioning inboxes and uploading to Email Bison.
Reads purchased domains, generates inbox specs, provisions in Hypertide, uploads to Email Bison.

Flow Structure:
    1. Read "purchased" domains from Google Sheet
    2. Generate inbox specifications (50/Entra, 3/Google)
    3. Add inboxes to Inboxes tab
    4. Verify inboxes exist in Hypertide
    5. Upload to Email Bison workspace

Usage:
    # Run manually
    python -m hypertide_automation.flows.inbox_provision_flow

    # Deploy to Prefect
    prefect deployment build flows/inbox_provision_flow.py:inbox_provision_flow -n "hypertide-inbox-provision"
"""

import asyncio
from datetime import datetime
from itertools import cycle
from typing import Optional, List, Dict, Any

from prefect import flow, task, get_run_logger
from prefect.tasks import task_input_hash
from pydantic import BaseModel

from .sheets import SheetsClient, SHEET_CONFIG
from ..client import HypertideClient
from ..emailbison import EmailBisonClient, InboxUpload
from ..config import get_config


# ============================================================================
# Task Models
# ============================================================================

class InboxProvisionInput(BaseModel):
    """Input for inbox provision flow."""
    sheet_id: str
    headless: bool = False
    dry_run: bool = False
    skip_emailbison: bool = False


class InboxProvisionResult(BaseModel):
    """Result of inbox provision flow."""
    inboxes_generated: int
    inboxes_provisioned: int
    inboxes_uploaded: int
    failed: int
    errors: List[str]


# ============================================================================
# Default User Names (for generating inboxes)
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
# Prefect Tasks
# ============================================================================

@task(
    name="read-purchased-domains",
    description="Read domains with status 'purchased' from Google Sheet",
    retries=2,
    retry_delay_seconds=5,
)
def read_purchased_domains(sheet_id: str) -> List[Dict[str, Any]]:
    """Read purchased domains that need inbox provisioning."""
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)
    domains = client.get_domains_by_status("purchased")

    logger.info(f"Found {len(domains)} purchased domains")
    return domains


@task(
    name="read-pending-inboxes",
    description="Read inboxes with status 'pending' from sheet",
)
def read_pending_inboxes(sheet_id: str) -> List[Dict[str, Any]]:
    """Read pending inboxes that need provisioning."""
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)
    inboxes = client.get_inboxes_by_status("pending")

    logger.info(f"Found {len(inboxes)} pending inboxes")
    return inboxes


@task(
    name="get-inbox-config",
    description="Read configuration from Config tab",
    cache_key_fn=task_input_hash,
    cache_expiration=datetime.timedelta(minutes=5),
)
def get_inbox_config(sheet_id: str) -> Dict[str, str]:
    """Get client configuration including Email Bison workspace."""
    client = SheetsClient(sheet_id=sheet_id)
    return client.get_config()


@task(
    name="generate-inbox-specs",
    description="Generate inbox specifications from purchased domains",
)
def generate_inbox_specs(
    domains: List[Dict[str, Any]],
    users: List[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate inbox specifications for purchased domains.

    Args:
        domains: List of purchased domain records
        users: Custom user names (optional)

    Returns:
        List of inbox specifications
    """
    logger = get_run_logger()
    users = users or DEFAULT_USERS

    def get_inboxes_per_domain(provider: str) -> int:
        if provider.lower() == "entra":
            return 50
        elif provider.lower() == "google":
            return 3
        return 10

    def generate_email(first_name: str, last_name: str, domain: str, index: int = 0) -> str:
        base = f"{first_name.lower()}.{last_name.lower()}"
        if index > 0:
            base = f"{base}{index + 1}"
        return f"{base}@{domain}"

    all_inboxes = []
    user_cycle = cycle(users)

    for domain_record in domains:
        domain = domain_record["domain"]
        provider = domain_record.get("provider", "entra")
        inbox_count = get_inboxes_per_domain(provider)

        domain_inboxes = []
        for i in range(inbox_count):
            user = next(user_cycle)
            # Calculate repeat index
            repeat_index = sum(
                1 for inbox in domain_inboxes
                if inbox["first_name"] == user["first_name"]
                and inbox["last_name"] == user["last_name"]
            )

            email = generate_email(
                user["first_name"],
                user["last_name"],
                domain,
                repeat_index,
            )

            domain_inboxes.append({
                "email": email,
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "domain": domain,
                "provider": provider,
            })

        all_inboxes.extend(domain_inboxes)
        logger.info(f"Generated {len(domain_inboxes)} inboxes for {domain}")

    logger.info(f"Total inboxes generated: {len(all_inboxes)}")
    return all_inboxes


@task(
    name="add-inboxes-to-sheet",
    description="Add generated inboxes to Inboxes tab",
)
def add_inboxes_to_sheet(
    sheet_id: str,
    inboxes: List[Dict[str, Any]],
    workspace: str,
) -> int:
    """Add inbox specs to the Inboxes tab in the sheet."""
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)

    # Add workspace to each inbox
    for inbox in inboxes:
        inbox["workspace"] = workspace

    added = client.add_inboxes(inboxes)
    logger.info(f"Added {added} inboxes to sheet")
    return added


@task(
    name="mark-inboxes-provisioning",
    description="Update inbox status to 'provisioning'",
)
def mark_inboxes_provisioning(
    sheet_id: str,
    inboxes: List[Dict[str, Any]],
) -> int:
    """Mark inboxes as 'provisioning' before processing."""
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)
    updated = 0

    for inbox in inboxes:
        success = client.update_inbox_status(
            email=inbox["email"],
            status="provisioning",
        )
        if success:
            updated += 1

    logger.info(f"Marked {updated} inboxes as 'provisioning'")
    return updated


@task(
    name="verify-hypertide-inboxes",
    description="Verify inboxes exist in Hypertide",
    timeout_seconds=300,
)
async def verify_hypertide_inboxes(
    inboxes: List[Dict[str, Any]],
    headless: bool = False,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """
    Verify inboxes exist in Hypertide.

    Note: Hypertide creates inboxes during the purchase flow,
    so this task primarily verifies they're accessible.

    Returns:
        List of verification results per inbox
    """
    logger = get_run_logger()
    results = []

    if dry_run:
        logger.warning("DRY RUN - Simulating verification")
        for inbox in inboxes:
            results.append({
                "email": inbox["email"],
                "verified": True,
                "status": "active",
                "error": None,
            })
        return results

    # Group by domain for efficient verification
    domains = set(inbox["domain"] for inbox in inboxes)

    config = get_config()
    config.headless = headless

    try:
        async with HypertideClient(config) as client:
            await client.ensure_authenticated()

            # Navigate to domains page
            await client.page.goto(f"{config.base_url}/domains")
            await asyncio.sleep(2)

            # Check each domain exists
            verified_domains = set()
            for domain in domains:
                domain_elem = await client.page.query_selector(f"text={domain}")
                if domain_elem:
                    verified_domains.add(domain)
                    logger.info(f"Verified domain in Hypertide: {domain}")
                else:
                    logger.warning(f"Domain not found in Hypertide: {domain}")

            # Mark inboxes based on domain verification
            for inbox in inboxes:
                if inbox["domain"] in verified_domains:
                    results.append({
                        "email": inbox["email"],
                        "verified": True,
                        "status": "active",
                        "error": None,
                    })
                else:
                    results.append({
                        "email": inbox["email"],
                        "verified": False,
                        "status": "failed",
                        "error": f"Domain {inbox['domain']} not found in Hypertide",
                    })

    except Exception as e:
        logger.error(f"Hypertide verification failed: {e}")
        for inbox in inboxes:
            results.append({
                "email": inbox["email"],
                "verified": False,
                "status": "failed",
                "error": str(e),
            })

    verified_count = sum(1 for r in results if r["verified"])
    logger.info(f"Verified {verified_count}/{len(results)} inboxes")

    return results


@task(
    name="upload-to-emailbison",
    description="Upload verified inboxes to Email Bison workspace",
    timeout_seconds=300,
)
async def upload_to_emailbison(
    inboxes: List[Dict[str, Any]],
    verification_results: List[Dict[str, Any]],
    workspace: str,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """
    Upload verified inboxes to Email Bison.

    Args:
        inboxes: Original inbox specs
        verification_results: Results from Hypertide verification
        workspace: Email Bison workspace name
        dry_run: Simulate without actual upload

    Returns:
        List of upload results per inbox
    """
    logger = get_run_logger()

    # Build email -> verification lookup
    verified = {r["email"]: r for r in verification_results}

    # Only upload verified inboxes
    to_upload = [
        inbox for inbox in inboxes
        if verified.get(inbox["email"], {}).get("verified", False)
    ]

    if not to_upload:
        logger.warning("No verified inboxes to upload")
        return []

    logger.info(f"Uploading {len(to_upload)} inboxes to Email Bison workspace: {workspace}")

    results = []

    if dry_run:
        logger.warning("DRY RUN - Simulating Email Bison upload")
        for inbox in to_upload:
            results.append({
                "email": inbox["email"],
                "uploaded": True,
                "error": None,
            })
        return results

    try:
        async with EmailBisonClient() as eb_client:
            # Verify workspace exists
            ws = await eb_client.get_workspace(workspace)
            if not ws:
                error = f"Workspace '{workspace}' not found in Email Bison"
                logger.error(error)
                for inbox in to_upload:
                    results.append({
                        "email": inbox["email"],
                        "uploaded": False,
                        "error": error,
                    })
                return results

            # Upload each inbox
            for inbox in to_upload:
                try:
                    upload = InboxUpload(
                        email=inbox["email"],
                        first_name=inbox["first_name"],
                        last_name=inbox["last_name"],
                        provider=inbox["provider"],
                    )

                    result = await eb_client.upload_inbox(workspace, upload)
                    results.append({
                        "email": inbox["email"],
                        "uploaded": result.success,
                        "error": result.error if not result.success else None,
                    })

                except Exception as e:
                    logger.warning(f"Failed to upload {inbox['email']}: {e}")
                    results.append({
                        "email": inbox["email"],
                        "uploaded": False,
                        "error": str(e),
                    })

    except Exception as e:
        logger.error(f"Email Bison upload failed: {e}")
        for inbox in to_upload:
            results.append({
                "email": inbox["email"],
                "uploaded": False,
                "error": str(e),
            })

    uploaded_count = sum(1 for r in results if r["uploaded"])
    logger.info(f"Uploaded {uploaded_count}/{len(results)} inboxes to Email Bison")

    return results


@task(
    name="update-inbox-results",
    description="Update Google Sheet with provisioning results",
)
def update_inbox_results(
    sheet_id: str,
    verification_results: List[Dict[str, Any]],
    upload_results: List[Dict[str, Any]],
) -> Dict[str, int]:
    """
    Update sheet with inbox provisioning results.

    Status progression:
    - pending -> provisioning -> provisioned -> uploaded
    - pending -> provisioning -> failed (if verification fails)
    """
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)

    # Build lookups
    verified = {r["email"]: r for r in verification_results}
    uploaded = {r["email"]: r for r in upload_results}

    counts = {"uploaded": 0, "provisioned": 0, "failed": 0}

    for email, v_result in verified.items():
        if v_result["verified"]:
            # Check if uploaded
            u_result = uploaded.get(email)
            if u_result and u_result["uploaded"]:
                status = "uploaded"
                error = None
            else:
                status = "provisioned"
                error = u_result.get("error") if u_result else None
        else:
            status = "failed"
            error = v_result.get("error")

        success = client.update_inbox_status(
            email=email,
            status=status,
            error=error,
        )

        if success:
            counts[status] += 1

    logger.info(
        f"Updated sheet: {counts['uploaded']} uploaded, "
        f"{counts['provisioned']} provisioned, {counts['failed']} failed"
    )
    return counts


# ============================================================================
# Main Flow
# ============================================================================

@flow(
    name="inbox-provision-flow",
    description="Provision inboxes from purchased domains and upload to Email Bison",
    version="1.0.0",
    retries=0,
)
async def inbox_provision_flow(
    sheet_id: str,
    headless: bool = False,
    dry_run: bool = False,
    skip_emailbison: bool = False,
    generate_new: bool = True,
) -> InboxProvisionResult:
    """
    Main flow: Provision inboxes and upload to Email Bison.

    Process:
        1. Read purchased domains OR pending inboxes from sheet
        2. Generate inbox specs if needed (50/Entra, 3/Google)
        3. Add to Inboxes tab
        4. Verify existence in Hypertide
        5. Upload to Email Bison workspace
        6. Update sheet with results

    Args:
        sheet_id: Google Sheet ID
        headless: Run browser in headless mode
        dry_run: Simulate without actual operations
        skip_emailbison: Skip Email Bison upload step
        generate_new: Generate new inboxes from domains (vs process pending)

    Returns:
        InboxProvisionResult with summary
    """
    logger = get_run_logger()
    logger.info(f"Starting inbox provision flow (sheet: {sheet_id})")

    errors = []

    # Get configuration
    config = get_inbox_config(sheet_id)
    workspace = config.get("emailbison_workspace", "")

    if not workspace and not skip_emailbison:
        error = "No emailbison_workspace configured in Config tab"
        logger.error(error)
        return InboxProvisionResult(
            inboxes_generated=0,
            inboxes_provisioned=0,
            inboxes_uploaded=0,
            failed=0,
            errors=[error],
        )

    # Determine source of inboxes
    if generate_new:
        # Read purchased domains and generate inbox specs
        domains = read_purchased_domains(sheet_id)

        if not domains:
            logger.info("No purchased domains to provision inboxes for")
            return InboxProvisionResult(
                inboxes_generated=0,
                inboxes_provisioned=0,
                inboxes_uploaded=0,
                failed=0,
                errors=[],
            )

        # Generate inbox specs
        inboxes = generate_inbox_specs(domains)

        # Add to sheet
        add_inboxes_to_sheet(sheet_id, inboxes, workspace)

    else:
        # Process existing pending inboxes
        inboxes = read_pending_inboxes(sheet_id)

        if not inboxes:
            logger.info("No pending inboxes to provision")
            return InboxProvisionResult(
                inboxes_generated=0,
                inboxes_provisioned=0,
                inboxes_uploaded=0,
                failed=0,
                errors=[],
            )

    inboxes_generated = len(inboxes)
    logger.info(f"Processing {inboxes_generated} inboxes")

    # Mark as provisioning
    mark_inboxes_provisioning(sheet_id, inboxes)

    # Verify in Hypertide
    verification_results = await verify_hypertide_inboxes(
        inboxes=inboxes,
        headless=headless,
        dry_run=dry_run,
    )

    inboxes_provisioned = sum(1 for r in verification_results if r["verified"])

    # Upload to Email Bison
    upload_results = []
    inboxes_uploaded = 0

    if not skip_emailbison and inboxes_provisioned > 0:
        upload_results = await upload_to_emailbison(
            inboxes=inboxes,
            verification_results=verification_results,
            workspace=workspace,
            dry_run=dry_run,
        )
        inboxes_uploaded = sum(1 for r in upload_results if r["uploaded"])

    # Update sheet
    update_inbox_results(sheet_id, verification_results, upload_results)

    # Calculate failed
    failed = inboxes_generated - inboxes_provisioned

    logger.info(
        f"Flow complete: {inboxes_generated} generated, "
        f"{inboxes_provisioned} provisioned, {inboxes_uploaded} uploaded, {failed} failed"
    )

    return InboxProvisionResult(
        inboxes_generated=inboxes_generated,
        inboxes_provisioned=inboxes_provisioned,
        inboxes_uploaded=inboxes_uploaded,
        failed=failed,
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
        return 1

    result = asyncio.run(inbox_provision_flow(
        sheet_id=sheet_id,
        headless=False,
        dry_run=True,
        skip_emailbison=False,
    ))

    print(f"\nResults:")
    print(f"  Generated: {result.inboxes_generated}")
    print(f"  Provisioned: {result.inboxes_provisioned}")
    print(f"  Uploaded: {result.inboxes_uploaded}")
    print(f"  Failed: {result.failed}")

    if result.errors:
        print(f"\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    exit(main())
