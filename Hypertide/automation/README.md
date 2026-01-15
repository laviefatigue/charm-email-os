# Hypertide Automation

Automated purchasing for Hypertide cold email infrastructure.

## Overview

This package automates the Hypertide web interface to execute inbox purchases programmatically. It's designed to integrate with your client onboarding system - when a new client signs, their project record dictates how many inboxes to purchase, and this automation executes it.

**Important**: Hypertide has NO API. This uses Playwright browser automation.

## Installation

```bash
# Clone/navigate to this directory
cd automation

# Install with pip
pip install -e .

# Install Playwright browsers (first time only)
playwright install chromium
```

## Quick Start

### CLI Usage

```bash
# Interactive mode
hypertide-purchase

# From JSON file
hypertide-purchase --from-json orders/acme.json

# Direct parameters
hypertide-purchase --client "Acme Corp" --domain acme.com --type entra --quantity 2

# Batch mode (multiple orders)
hypertide-purchase --batch orders/batch.json --output results.json

# Dry run (validate without purchasing)
hypertide-purchase --from-json order.json --dry-run
```

### Python API

```python
import asyncio
from hypertide_automation import (
    HypertideClient,
    PurchaseAutomation,
    OrderRequest,
    OrderType,
    SendingTool,
)

async def main():
    # Create order request
    order = OrderRequest(
        client_name="Acme Corp",
        forwarding_domain="acme.com",
        order_type=OrderType.HYPERTIDE_ENTRA,
        quantity=2,  # 4 domains, 200 inboxes, 10k emails/mo
        sending_tool=SendingTool.BISON,
    )

    # Execute purchase
    async with HypertideClient() as client:
        # First run: prompts for manual login
        # Subsequent runs: uses saved session
        await client.ensure_authenticated()

        automation = PurchaseAutomation(client)
        result = await automation.execute(order)

        if result.success:
            print(f"Order created: {result.order_id}")
            print(f"Total inboxes: {result.total_inboxes}")
        else:
            print(f"Failed: {result.error_message}")

asyncio.run(main())
```

## Order Types

| Type | Domains/Order | Inboxes/Domain | Total Inboxes/Order | Monthly Capacity |
|------|--------------|----------------|---------------------|------------------|
| **Entra** | 2 | 50 | 100 | 5,000 |
| **Google** | 5 | 3 | 15 | 5,000+ |

## Mixed Orders (Entra + Google)

Clients often need both Entra and Google inboxes. The automation handles this automatically:

```python
from hypertide_automation import (
    purchase_mixed_order,
    MixedOrderRequest,
    InboxTarget,
    BisonCredentials,
    InboxConfig,
)

async def onboard_client():
    request = MixedOrderRequest(
        client_name="Acme Corp",
        forwarding_domain="acme.com",

        # Specify target inbox counts (system calculates orders)
        inbox_target=InboxTarget(
            entra_inboxes=500,   # → 5 Entra orders
            google_inboxes=100,  # → 7 Google orders
        ),

        # Bison credentials (shared across all orders)
        bison_credentials=BisonCredentials(
            username="user@email.com",
            password="secret",
            workspace="Acme Workspace",
            bison_url="https://send.hirecharm.com"
        ),

        # Inbox users
        users=[
            InboxConfig(first_name="alex", last_name="morgan"),
            InboxConfig(first_name="jordan", last_name="smith"),
        ]
    )

    # Executes TWO purchase flows automatically
    result = await purchase_mixed_order(request)

    if result.success:
        print(f"Total inboxes: {result.total_inboxes}")
        for order in result.order_results:
            print(f"  {order.order_type.value}: {order.total_inboxes} inboxes")
```

### Preview Order Calculations

```python
from hypertide_automation import calculate_optimal_orders, InboxTarget

target = InboxTarget(entra_inboxes=500, google_inboxes=100)
breakdown = calculate_optimal_orders(target)

print(f"Entra: {breakdown.entra_orders} orders = {breakdown.entra_inboxes_actual} inboxes")
print(f"Google: {breakdown.google_orders} orders = {breakdown.google_inboxes_actual} inboxes")
print(f"Est. monthly cost: ${breakdown.estimated_monthly_cost}")
```

## Integration with Project Records

See `examples/purchase_from_project_record.py` for a complete integration example.

Your workflow:
1. New client signs → Project record created
2. Project record specifies: inbox count, domain names, inbox names
3. This automation reads the record and executes purchase
4. Results stored back in your database

```python
async def onboard_new_client(client_id: str):
    # Fetch from your DB
    project = await db.get_project(client_id)

    # Build order
    order = OrderRequest(
        client_name=project["name"],
        forwarding_domain=project["domain"],
        order_type=OrderType.HYPERTIDE_ENTRA,
        quantity=calculate_orders_needed(project["monthly_volume"]),
    )

    # Execute
    result = await purchase_order(order)

    # Update DB
    await db.update_project(client_id, {
        "hypertide_order_id": result.order_id,
        "status": "provisioned" if result.success else "needs_review"
    })
```

## Authentication

**First run**: The browser opens and you manually login to Hypertide. The session is saved.

**Subsequent runs**: Uses saved session (stored in `~/.hypertide/session`).

Session location can be changed:
```python
from hypertide_automation import HypertideConfig

config = HypertideConfig(
    session_storage_path=Path("/custom/path/session")
)
```

## Payment Handling

The automation assumes:
1. You have a saved payment method in Stripe (auto-selects)
2. OR you manually complete payment when the checkout appears

For fully automated payments:
- Ensure saved card in Hypertide/Stripe
- Set `use_saved_payment=True` in OrderRequest

## Configuration

Environment variables:
```bash
HYPERTIDE_EMAIL=your@email.com     # Optional, for reference
HYPERTIDE_HEADLESS=false           # Run browser headless
HYPERTIDE_SLOW_MO=100              # Slow down for debugging (ms)
HYPERTIDE_TIMEOUT=30000            # Default timeout (ms)
```

Or configure programmatically:
```python
from hypertide_automation import HypertideConfig, set_config

config = HypertideConfig(
    headless=True,
    slow_mo=50,
    timeout=60000,
)
set_config(config)
```

## Error Handling

The automation captures screenshots on failure:
```python
result = await automation.execute(order)

if not result.success:
    print(f"Error: {result.error_message}")
    print(f"Screenshot: {result.screenshot_path}")
```

Common errors:
- `AuthenticationError`: Session expired, need to re-login
- `DomainUnavailableError`: Requested domain not available
- `PaymentError`: Stripe payment failed
- `PaymentTimeoutError`: Checkout didn't complete in time

## Project Structure

```
automation/
├── pyproject.toml
├── src/
│   └── hypertide_automation/
│       ├── __init__.py
│       ├── models.py      # OrderRequest, OrderResult, etc.
│       ├── client.py      # HypertideClient (Playwright wrapper)
│       ├── purchase.py    # PurchaseAutomation flow
│       ├── config.py      # Configuration
│       ├── exceptions.py  # Custom exceptions
│       └── cli.py         # CLI entry point
├── examples/
│   ├── purchase_from_project_record.py
│   ├── order.example.json
│   └── batch.example.json
└── tests/
```

## UI Selectors

If Hypertide updates their UI, you may need to update selectors in `purchase.py`:

```python
SELECTORS = {
    "entra_plan_card": "text=Hypertide Entra",
    "google_plan_card": "text=Hypertide Google",
    # ... update as needed
}
```

## Limitations

1. **No API**: All operations go through browser automation
2. **Session management**: Need to re-authenticate if session expires
3. **UI changes**: May break if Hypertide updates their interface
4. **Payment**: Requires manual completion or saved card

## Support

For Hypertide platform issues: support@hypertide.io

For automation bugs: Check screenshots in `./screenshots/` directory
