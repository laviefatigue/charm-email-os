"""
Hypertide API - REST API client for Hypertide inbox purchasing.

This package provides:
- HypertideAPIClient: Low-level async API client
- HypertideOrderService: Business logic with duplicate detection
- SlackNotifier: Slack notifications for order events
- Worker: Background job processor

Quick Start:
    from hypertide_api import HypertideOrderService, SingleOrderRequest, BisonCredentials, PlanType

    async with HypertideOrderService(api_key="your-key") as service:
        request = SingleOrderRequest(
            client_id=uuid4(),
            client_name="Acme Corp",
            plan=PlanType.ENTRA,
            domains=["domain1.com", "domain2.com"],
            forwarding_domain="acme.com",
            bison_credentials=BisonCredentials(
                username="user@email.com",
                password="secret",
                workspace="Acme Workspace",
            ),
        )
        result = await service.create_single_order(request)
        print(f"Created {result.inboxes_created} inboxes")
"""

from .client import (
    HypertideAPIClient,
    HypertideAPIError,
    HypertideErrorType,
    CreateOrderRequest,
    BisonCredentialsPayload,
    UserPayload,
    WarmupSettingsPayload,
    OrderCreatedResponse,
    DNSRecordsResponse,
    ActiveOrdersResponse,
    ChargeResponse,
    create_bison_order,
)

from .models import (
    PlanType,
    OrderStatus,
    FailureReason,
    BisonCredentials,
    InboxUser,
    SingleOrderRequest,
    BatchOrderRequest,
    OrderResult,
    BatchOrderResult,
    OrderJobRecord,
    PLAN_SPECS,
    calculate_orders_needed,
    group_domains_for_orders,
)

from .service import (
    HypertideOrderService,
    DatabaseProtocol,
    NullDatabase,
    DuplicateCheckResult,
    create_order_simple,
)

from .notifications import (
    SlackNotifier,
    SlackColor,
    create_slack_notifier,
)

__version__ = "1.0.0"
__all__ = [
    # Client
    "HypertideAPIClient",
    "HypertideAPIError",
    "HypertideErrorType",
    "CreateOrderRequest",
    "BisonCredentialsPayload",
    "UserPayload",
    "WarmupSettingsPayload",
    "OrderCreatedResponse",
    "DNSRecordsResponse",
    "ActiveOrdersResponse",
    "ChargeResponse",
    "create_bison_order",
    # Models
    "PlanType",
    "OrderStatus",
    "FailureReason",
    "BisonCredentials",
    "InboxUser",
    "SingleOrderRequest",
    "BatchOrderRequest",
    "OrderResult",
    "BatchOrderResult",
    "OrderJobRecord",
    "PLAN_SPECS",
    "calculate_orders_needed",
    "group_domains_for_orders",
    # Service
    "HypertideOrderService",
    "DatabaseProtocol",
    "NullDatabase",
    "create_order_simple",
    # Notifications
    "SlackNotifier",
    "SlackColor",
    "create_slack_notifier",
]
