"""
Custom exceptions for Hypertide automation.
"""


class HypertideError(Exception):
    """Base exception for Hypertide automation."""
    pass


class AuthenticationError(HypertideError):
    """Failed to authenticate with Hypertide."""
    pass


class SessionExpiredError(AuthenticationError):
    """Browser session has expired, need to re-authenticate."""
    pass


class NavigationError(HypertideError):
    """Failed to navigate to expected page."""
    pass


class ElementNotFoundError(HypertideError):
    """Expected UI element not found on page."""

    def __init__(self, selector: str, page_url: str):
        self.selector = selector
        self.page_url = page_url
        super().__init__(f"Element '{selector}' not found on {page_url}")


class OrderError(HypertideError):
    """Error during order process."""
    pass


class DomainUnavailableError(OrderError):
    """Requested domain is not available."""

    def __init__(self, domain: str):
        self.domain = domain
        super().__init__(f"Domain '{domain}' is not available")


class PaymentError(HypertideError):
    """Error during Stripe payment."""
    pass


class PaymentDeclinedError(PaymentError):
    """Payment was declined by Stripe."""
    pass


class PaymentTimeoutError(PaymentError):
    """Payment process timed out."""
    pass


class ValidationError(HypertideError):
    """Order validation failed."""
    pass


class QuantityError(ValidationError):
    """Invalid quantity specified."""

    def __init__(self, quantity: int, max_quantity: int = 20):
        self.quantity = quantity
        self.max_quantity = max_quantity
        super().__init__(f"Quantity {quantity} exceeds maximum of {max_quantity}")


class ConfigurationError(HypertideError):
    """Configuration is invalid or missing."""
    pass


class HypertideUnavailableError(HypertideError):
    """Hypertide site is not accessible."""

    def __init__(self, url: str, reason: str = ""):
        self.url = url
        self.reason = reason
        msg = f"Hypertide site unavailable at {url}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class RetryExhaustedError(HypertideError):
    """All retry attempts failed."""

    def __init__(self, operation: str, attempts: int, last_error: Exception):
        self.operation = operation
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Operation '{operation}' failed after {attempts} attempts. "
            f"Last error: {last_error}"
        )
