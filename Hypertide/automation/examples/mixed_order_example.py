"""
Mixed Order Example - Client Onboarding Automation

This example demonstrates how to use the Hypertide automation for clients
who need BOTH Entra and Google inboxes.

Example scenario:
- Client: Acme Corp
- Needs: 500 Entra inboxes + 100 Google inboxes
- System calculates: 5 Entra orders + 7 Google orders
- Automation executes both purchase flows sequentially
"""

import asyncio
from hypertide_automation import (
    # High-level mixed order interface
    purchase_mixed_order,
    MixedOrderRequest,
    InboxTarget,
    BisonCredentials,
    InboxConfig,
    # Lower-level if needed
    calculate_optimal_orders,
    create_order_bundle,
)


async def onboard_client_example():
    """
    Example: Onboard a new client with mixed inbox requirements.
    """
    # Define the order using inbox targets (not order quantities)
    # The system automatically calculates optimal order quantities
    request = MixedOrderRequest(
        client_name="Acme Corp",
        forwarding_domain="acme.com",

        # Specify WHAT you need (inbox counts)
        inbox_target=InboxTarget(
            entra_inboxes=500,   # System calculates: 5 Entra orders
            google_inboxes=100,  # System calculates: 7 Google orders
        ),

        # Bison credentials (shared across all orders)
        bison_credentials=BisonCredentials(
            username="your-bison-user@email.com",
            password="your-bison-password",
            workspace="Acme Workspace",
            bison_url="https://spellcast.hirecharm.com"
        ),

        # Inbox users (distributed evenly across all inboxes)
        users=[
            InboxConfig(first_name="alex", last_name="morgan"),
            InboxConfig(first_name="jordan", last_name="smith"),
            InboxConfig(first_name="taylor", last_name="chen"),
        ],
    )

    # Execute the purchase (handles multiple checkouts automatically)
    print(f"Starting purchase for {request.client_name}")
    print(f"Target: {request.inbox_target.entra_inboxes} Entra + {request.inbox_target.google_inboxes} Google inboxes")

    result = await purchase_mixed_order(request)

    # Check results
    if result.success:
        print(f"\n✅ All orders completed successfully!")
        print(f"   Total inboxes: {result.total_inboxes}")
        print(f"   Monthly capacity: {result.total_monthly_capacity:,} emails/mo")

        for order_result in result.order_results:
            print(f"   - {order_result.order_type.value}: {order_result.total_inboxes} inboxes")
    else:
        print(f"\n❌ Some orders failed:")
        for error in result.errors:
            print(f"   - {error}")

        # Partial success info
        print(f"\n   Successful: {result.successful_orders}/{result.total_orders}")
        print(f"   Total inboxes provisioned: {result.total_inboxes}")


def preview_order_calculation():
    """
    Preview what orders will be created without executing.

    Useful for:
    - Validating before purchase
    - Cost estimation
    - Integration with project records
    """
    # Example targets
    targets = [
        InboxTarget(entra_inboxes=100, google_inboxes=0),      # Entra only
        InboxTarget(entra_inboxes=0, google_inboxes=45),       # Google only
        InboxTarget(entra_inboxes=500, google_inboxes=100),    # Mixed
        InboxTarget(entra_inboxes=1000, google_inboxes=200),   # Large mixed
    ]

    print("Order Calculation Preview")
    print("=" * 70)

    for target in targets:
        breakdown = calculate_optimal_orders(target)

        print(f"\nTarget: {target.entra_inboxes} Entra + {target.google_inboxes} Google")
        print(f"  Entra:  {breakdown.entra_orders} orders → {breakdown.entra_inboxes_actual} inboxes ({breakdown.entra_domains} domains)")
        print(f"  Google: {breakdown.google_orders} orders → {breakdown.google_inboxes_actual} inboxes ({breakdown.google_domains} domains)")
        print(f"  Total:  {breakdown.total_inboxes} inboxes, {breakdown.total_monthly_capacity:,} emails/mo")
        print(f"  Est. monthly cost: ${breakdown.estimated_monthly_cost:.2f}")
        print(f"  Is mixed order: {breakdown.is_mixed}")


async def integration_with_project_record():
    """
    Example: Integration with your project record database.

    This shows how the automation fits into your client onboarding system.
    """
    # Simulated project record from your database
    project_record = {
        "id": "proj_123",
        "client_name": "TechStartup Inc",
        "domain": "techstartup.io",
        "monthly_volume_target": 50000,  # emails/month
        "preferred_split": {
            "entra_percentage": 80,  # 80% Entra
            "google_percentage": 20,  # 20% Google
        },
        "bison_workspace": "TechStartup Workspace",
        "contacts": [
            {"first": "mike", "last": "johnson"},
            {"first": "sarah", "last": "williams"},
        ]
    }

    # Calculate inbox needs from monthly volume
    # Rule of thumb: ~100 emails/inbox/month for cold outreach
    total_inboxes_needed = project_record["monthly_volume_target"] // 100

    entra_inboxes = int(total_inboxes_needed * project_record["preferred_split"]["entra_percentage"] / 100)
    google_inboxes = int(total_inboxes_needed * project_record["preferred_split"]["google_percentage"] / 100)

    # Preview the order
    breakdown = calculate_optimal_orders(
        InboxTarget(entra_inboxes=entra_inboxes, google_inboxes=google_inboxes)
    )

    print(f"Project: {project_record['client_name']}")
    print(f"Volume target: {project_record['monthly_volume_target']:,} emails/mo")
    print(f"Calculated needs: {entra_inboxes} Entra + {google_inboxes} Google inboxes")
    print(f"Order plan: {breakdown.entra_orders} Entra + {breakdown.google_orders} Google orders")
    print(f"Actual inboxes: {breakdown.total_inboxes}")
    print(f"Est. cost: ${breakdown.estimated_monthly_cost:.2f}/mo")

    # Build the request
    request = MixedOrderRequest(
        client_name=project_record["client_name"],
        forwarding_domain=project_record["domain"],
        inbox_target=InboxTarget(
            entra_inboxes=entra_inboxes,
            google_inboxes=google_inboxes,
        ),
        bison_credentials=BisonCredentials(
            username="your-bison-user@email.com",  # From your secrets
            password="your-bison-password",         # From your secrets
            workspace=project_record["bison_workspace"],
            bison_url="https://spellcast.hirecharm.com"
        ),
        users=[
            InboxConfig(first_name=c["first"], last_name=c["last"])
            for c in project_record["contacts"]
        ]
    )

    # Execute (commented out for demo)
    # result = await purchase_mixed_order(request)
    #
    # # Update project record with results
    # await db.update_project(project_record["id"], {
    #     "hypertide_order_ids": [r.order_id for r in result.order_results],
    #     "provisioned_inboxes": result.total_inboxes,
    #     "status": "provisioned" if result.success else "needs_review",
    # })


if __name__ == "__main__":
    # Preview calculations (no browser needed)
    preview_order_calculation()

    # Run actual purchase (uncomment to execute)
    # asyncio.run(onboard_client_example())

    # Integration example (preview only)
    # asyncio.run(integration_with_project_record())
