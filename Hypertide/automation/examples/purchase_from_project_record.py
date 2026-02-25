"""
Example: Purchase Hypertide order from project record.

This example shows how you would integrate the automation
with your project record system.

Your workflow:
1. New client signs → Project record created in your DB
2. Project record contains: inbox count, domains, inbox names
3. This script reads the project record and executes purchase
"""

import asyncio
from typing import Any

# Import the automation package
from hypertide_automation import (
    HypertideClient,
    PurchaseAutomation,
    OrderRequest,
    OrderType,
    SendingTool,
    DomainConfig,
    InboxConfig,
)


async def purchase_for_client(project_record: dict[str, Any]) -> dict:
    """
    Execute Hypertide purchase based on project record.

    Args:
        project_record: Your project record from database

    Returns:
        Result dictionary with order details
    """

    # Map your project record to OrderRequest
    order = OrderRequest(
        client_name=project_record["client_name"],
        forwarding_domain=project_record["client_domain"],
        order_type=OrderType.HYPERTIDE_ENTRA,  # or HYPERTIDE_GOOGLE based on your logic
        quantity=project_record["orders_needed"],
        sending_tool=SendingTool.BISON,

        # Optional: Custom domains if pre-selected
        domains=[
            DomainConfig(name=d["name"], tld=d["tld"])
            for d in project_record.get("domains", [])
        ],

        # Optional: Custom inbox names if pre-generated
        inbox_names=[
            InboxConfig(first_name=i["first"], last_name=i["last"])
            for i in project_record.get("inbox_names", [])
        ],
    )

    # Execute purchase
    async with HypertideClient() as client:
        # First time: will prompt for manual login
        # Subsequent runs: uses saved session
        await client.ensure_authenticated()

        automation = PurchaseAutomation(client)
        result = await automation.execute(order)

        return result.model_dump()


# ============================================================================
# Example: Integration with your database
# ============================================================================

async def process_new_client_onboarding(client_id: str):
    """
    Example function that would be called when a new client signs.

    This integrates with your existing project record system.
    """

    # 1. Fetch project record from your database
    project_record = await fetch_project_record(client_id)  # Your DB function

    # 2. Calculate how many orders needed based on their requirements
    monthly_emails_needed = project_record["target_monthly_emails"]
    orders_needed = calculate_orders_needed(monthly_emails_needed)

    # 3. Generate domain names (your naming convention)
    domains = generate_domain_names(
        base=project_record["client_name"],
        count=orders_needed * 2  # 2 domains per Entra order
    )

    # 4. Generate inbox names (your naming convention)
    inbox_names = generate_inbox_names(
        count=orders_needed * 100  # 100 inboxes per order (2 domains x 50)
    )

    # 5. Build the project record for automation
    purchase_record = {
        "client_name": project_record["client_name"],
        "client_domain": project_record["primary_domain"],
        "orders_needed": orders_needed,
        "domains": domains,
        "inbox_names": inbox_names,
    }

    # 6. Execute the Hypertide purchase
    result = await purchase_for_client(purchase_record)

    # 7. Update your database with the result
    if result["success"]:
        await update_project_record(client_id, {
            "hypertide_order_id": result["order_id"],
            "inbox_count": result["total_inboxes"],
            "monthly_capacity": result["monthly_capacity"],
            "status": "infrastructure_provisioned"
        })
    else:
        await flag_for_manual_review(client_id, result["error_message"])

    return result


# ============================================================================
# Placeholder functions (replace with your actual implementations)
# ============================================================================

async def fetch_project_record(client_id: str) -> dict:
    """Fetch from your database."""
    # Example record
    return {
        "client_name": "Acme Corp",
        "primary_domain": "acme.com",
        "target_monthly_emails": 25000,  # Needs 5 orders
    }


def calculate_orders_needed(monthly_emails: int) -> int:
    """Calculate Hypertide orders needed for target volume."""
    # Each Entra order = 5,000 emails/month
    import math
    return min(20, max(1, math.ceil(monthly_emails / 5000)))


def generate_domain_names(base: str, count: int) -> list[dict]:
    """Generate domain names based on your naming convention."""
    # Example: outreach-acme.com, connect-acme.io, etc.
    prefixes = ["outreach", "connect", "reach", "hello", "contact", "mail"]
    tlds = ["com", "io", "co"]

    domains = []
    for i in range(count):
        prefix = prefixes[i % len(prefixes)]
        tld = tlds[i % len(tlds)]
        domains.append({
            "name": f"{prefix}-{base.lower().replace(' ', '')}",
            "tld": tld
        })
    return domains


def generate_inbox_names(count: int) -> list[dict]:
    """Generate inbox names (first.last format)."""
    # You might pull from a names database or use your naming system
    first_names = ["alex", "jordan", "taylor", "morgan", "casey", "riley"]
    last_names = ["smith", "johnson", "williams", "brown", "jones", "davis"]

    names = []
    for i in range(count):
        names.append({
            "first": first_names[i % len(first_names)],
            "last": last_names[i % len(last_names)]
        })
    return names


async def update_project_record(client_id: str, data: dict):
    """Update your database."""
    print(f"Would update {client_id} with: {data}")


async def flag_for_manual_review(client_id: str, error: str):
    """Flag for manual review."""
    print(f"ALERT: {client_id} needs manual review: {error}")


# ============================================================================
# Run example
# ============================================================================

if __name__ == "__main__":
    # Simple example: purchase from a project record
    example_project = {
        "client_name": "Demo Corp",
        "client_domain": "demo.com",
        "orders_needed": 2,  # 4 domains, 200 inboxes, 10k emails/mo
        "domains": [
            {"name": "outreach-demo", "tld": "com"},
            {"name": "connect-demo", "tld": "com"},
            {"name": "reach-demo", "tld": "io"},
            {"name": "hello-demo", "tld": "io"},
        ],
        "inbox_names": []  # Let Hypertide auto-generate
    }

    result = asyncio.run(purchase_for_client(example_project))

    print("\n=== Purchase Result ===")
    print(f"Success: {result['success']}")
    if result['success']:
        print(f"Order ID: {result['order_id']}")
        print(f"Total Inboxes: {result['total_inboxes']}")
        print(f"Monthly Capacity: {result['monthly_capacity']:,} emails")
    else:
        print(f"Error: {result['error_message']}")
