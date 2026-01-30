"""
Hypertide Automation - Programmatic inbox infrastructure purchasing.

This module provides browser automation for Hypertide's web interface,
enabling automated purchasing of Entra and Google inbox orders.

Supports mixed orders (Entra + Google) through the MixedOrderRequest
and BundlePurchaseAutomation classes.
"""

from .models import (
    # Core types
    InboxType,
    OrderType,
    SendingTool,
    DomainStatus,
    # Configuration
    DomainConfig,
    InboxConfig,
    # Single order types
    OrderRequest,
    OrderResult,
    ExistingDomain,
    # Mixed order support
    InboxTarget,
    OrderBreakdown,
    BisonCredentials,
    MixedOrderRequest,
    OrderBundle,
    BundleResult,
    # Utility functions
    calculate_optimal_orders,
    create_order_bundle,
)
from .client import HypertideClient
from .purchase import (
    PurchaseAutomation,
    BundlePurchaseAutomation,
    purchase_order,
    purchase_mixed_order,
)
from .config import HypertideConfig, StripeConfig, set_config, get_config
from .exceptions import (
    HypertideError,
    AuthenticationError,
    SessionExpiredError,
    NavigationError,
    OrderError,
    PaymentError,
    PaymentTimeoutError,
    HypertideUnavailableError,
    RetryExhaustedError,
)

__version__ = "0.3.0"  # Bumped for reliability improvements
__all__ = [
    # Client
    "HypertideClient",
    # Automation
    "PurchaseAutomation",
    "BundlePurchaseAutomation",
    # Convenience functions
    "purchase_order",
    "purchase_mixed_order",
    # Core types
    "InboxType",
    "OrderType",
    "SendingTool",
    "DomainStatus",
    # Configuration models
    "DomainConfig",
    "InboxConfig",
    # Single order
    "OrderRequest",
    "OrderResult",
    "ExistingDomain",
    # Mixed order support
    "InboxTarget",
    "OrderBreakdown",
    "BisonCredentials",
    "MixedOrderRequest",
    "OrderBundle",
    "BundleResult",
    # Utility functions
    "calculate_optimal_orders",
    "create_order_bundle",
    # Config
    "HypertideConfig",
    "StripeConfig",
    "set_config",
    "get_config",
    # Exceptions
    "HypertideError",
    "AuthenticationError",
    "SessionExpiredError",
    "NavigationError",
    "OrderError",
    "PaymentError",
    "PaymentTimeoutError",
    "HypertideUnavailableError",
    "RetryExhaustedError",
]
