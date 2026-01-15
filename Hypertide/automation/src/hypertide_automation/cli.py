"""
CLI entry point for Hypertide automation.

Usage:
    # Interactive mode (prompts for order details)
    hypertide-purchase

    # From JSON file
    hypertide-purchase --from-json order.json

    # Direct parameters
    hypertide-purchase --client "Acme Corp" --domain acme.com --type entra --quantity 2
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import structlog

from .models import OrderRequest, OrderType, SendingTool
from .purchase import purchase_order
from .config import HypertideConfig, set_config

logger = structlog.get_logger()


def parse_args():
    """Parse command line arguments."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Automate Hypertide inbox purchases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Interactive mode
    hypertide-purchase

    # From JSON order file
    hypertide-purchase --from-json orders/acme-order.json

    # Direct specification
    hypertide-purchase --client "Acme Corp" --domain acme.com --type entra --quantity 2

    # Batch mode (multiple orders from JSON array)
    hypertide-purchase --batch orders/batch.json
        """
    )

    # Input modes
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--from-json",
        type=Path,
        help="Load order from JSON file"
    )
    input_group.add_argument(
        "--batch",
        type=Path,
        help="Process multiple orders from JSON array file"
    )

    # Direct parameters
    parser.add_argument("--client", help="Client name")
    parser.add_argument("--domain", help="Forwarding domain")
    parser.add_argument(
        "--type",
        choices=["entra", "google"],
        default="entra",
        help="Order type (default: entra)"
    )
    parser.add_argument(
        "--quantity",
        type=int,
        default=1,
        help="Number of orders 1-20 (default: 1)"
    )
    parser.add_argument(
        "--tool",
        choices=["bison", "smartlead", "instantly"],
        default="bison",
        help="Sending tool (default: bison)"
    )

    # Behavior options
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate order without purchasing"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Save result to JSON file"
    )

    return parser.parse_args()


def load_order_from_json(path: Path) -> OrderRequest:
    """Load order request from JSON file."""
    with open(path) as f:
        data = json.load(f)

    # Convert string enums to proper types
    if "order_type" in data:
        data["order_type"] = OrderType(data["order_type"])
    if "sending_tool" in data:
        data["sending_tool"] = SendingTool(data["sending_tool"])

    return OrderRequest(**data)


def create_order_from_args(args) -> Optional[OrderRequest]:
    """Create order request from CLI arguments."""
    if not args.client or not args.domain:
        return None

    order_type = OrderType.HYPERTIDE_ENTRA if args.type == "entra" else OrderType.HYPERTIDE_GOOGLE

    tool_map = {
        "bison": SendingTool.BISON,
        "smartlead": SendingTool.SMARTLEAD,
        "instantly": SendingTool.INSTANTLY,
    }

    return OrderRequest(
        client_name=args.client,
        forwarding_domain=args.domain,
        order_type=order_type,
        quantity=args.quantity,
        sending_tool=tool_map[args.tool],
    )


def interactive_order() -> OrderRequest:
    """Prompt user for order details interactively."""
    print("\n=== Hypertide Purchase Automation ===\n")

    client_name = input("Client name: ").strip()
    forwarding_domain = input("Forwarding domain (e.g., acme.com): ").strip()

    print("\nOrder type:")
    print("  1. Hypertide Entra (2 domains, 50 inboxes each, 5k emails/mo per order)")
    print("  2. Hypertide Google (5 domains, 3 inboxes each, 5k+ emails/mo per order)")
    type_choice = input("Select [1/2] (default: 1): ").strip() or "1"
    order_type = OrderType.HYPERTIDE_ENTRA if type_choice == "1" else OrderType.HYPERTIDE_GOOGLE

    quantity = int(input("Quantity (1-20, default: 1): ").strip() or "1")

    # Show summary
    if order_type == OrderType.HYPERTIDE_ENTRA:
        domains = quantity * 2
        inboxes = domains * 50
    else:
        domains = quantity * 5
        inboxes = domains * 3

    capacity = quantity * 5000

    print(f"\n--- Order Summary ---")
    print(f"Client: {client_name}")
    print(f"Forwarding Domain: {forwarding_domain}")
    print(f"Type: {order_type.value}")
    print(f"Quantity: {quantity} order(s)")
    print(f"Total Domains: {domains}")
    print(f"Total Inboxes: {inboxes}")
    print(f"Monthly Capacity: {capacity:,} emails")
    print(f"Estimated Cost: ${quantity * 50}/month + domain fees")

    confirm = input("\nProceed? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)

    return OrderRequest(
        client_name=client_name,
        forwarding_domain=forwarding_domain,
        order_type=order_type,
        quantity=quantity,
        sending_tool=SendingTool.BISON,
    )


async def run_purchase(order: OrderRequest, dry_run: bool = False) -> dict:
    """Execute the purchase and return result as dict."""
    if dry_run:
        print("\n[DRY RUN] Would purchase:")
        print(f"  Client: {order.client_name}")
        print(f"  Type: {order.order_type.value}")
        print(f"  Quantity: {order.quantity}")
        print(f"  Expected Domains: {order.expected_domains}")
        print(f"  Expected Inboxes: {order.expected_inboxes}")
        return {"dry_run": True, "valid": True}

    result = await purchase_order(order)
    return result.model_dump()


def main():
    """CLI entry point."""
    args = parse_args()

    # Configure
    if args.headless:
        config = HypertideConfig(headless=True)
        set_config(config)

    # Determine order source
    if args.from_json:
        order = load_order_from_json(args.from_json)
    elif args.batch:
        # Batch mode - process multiple orders
        with open(args.batch) as f:
            orders_data = json.load(f)

        results = []
        for data in orders_data:
            if "order_type" in data:
                data["order_type"] = OrderType(data["order_type"])
            if "sending_tool" in data:
                data["sending_tool"] = SendingTool(data["sending_tool"])

            order = OrderRequest(**data)
            result = asyncio.run(run_purchase(order, args.dry_run))
            results.append(result)
            print(f"Completed: {order.client_name} - Success: {result.get('success', 'N/A')}")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\nResults saved to {args.output}")

        return

    elif args.client and args.domain:
        order = create_order_from_args(args)
    else:
        order = interactive_order()

    # Execute
    result = asyncio.run(run_purchase(order, args.dry_run))

    # Output
    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nResult saved to {args.output}")
    else:
        print("\n--- Result ---")
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
