"""
Hypertide REST API Client

Provides a typed, async client for the Hypertide API with:
- Full error handling and classification
- Comprehensive request/response logging
- Timeout management
- Response verification
- No automatic retries (manual retry via UI/Slack)

Usage:
    client = HypertideAPIClient(api_key="...")
    result = await client.create_order(order_request)
"""

import httpx
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Any
from enum import Enum
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


# =============================================================================
# Error Types
# =============================================================================

class HypertideErrorType(str, Enum):
    """Classification of Hypertide API errors for downstream handling."""
    AUTHENTICATION = "authentication"      # Invalid API key
    VALIDATION = "validation"              # Invalid request data
    DOMAIN_CONFLICT = "domain_conflict"    # Domain already in use
    PAYMENT_REQUIRED = "payment_required"  # Payment method issues
    RATE_LIMITED = "rate_limited"          # Too many requests
    SERVER_ERROR = "server_error"          # 5xx errors
    TIMEOUT = "timeout"                    # Request timed out
    NETWORK = "network"                    # Connection failed
    VERIFICATION_FAILED = "verification_failed"  # Post-creation check failed
    UNKNOWN = "unknown"                    # Unclassified error


class HypertideAPIError(Exception):
    """Hypertide API error with classification and details."""

    def __init__(
        self,
        message: str,
        error_type: HypertideErrorType,
        status_code: Optional[int] = None,
        response_body: Optional[dict] = None,
        request_id: Optional[str] = None,
        request_payload: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.response_body = response_body or {}
        self.request_id = request_id
        self.request_payload = request_payload
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/Slack."""
        return {
            "message": self.message,
            "error_type": self.error_type.value,
            "status_code": self.status_code,
            "response_body": self.response_body,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
        }

    @property
    def is_retryable(self) -> bool:
        """Check if this error type might succeed on retry."""
        return self.error_type in (
            HypertideErrorType.RATE_LIMITED,
            HypertideErrorType.SERVER_ERROR,
            HypertideErrorType.TIMEOUT,
            HypertideErrorType.NETWORK,
        )

    def __str__(self) -> str:
        return f"[{self.error_type.value}] {self.message} (status={self.status_code})"


# =============================================================================
# Response Models
# =============================================================================

class OrderCreatedResponse(BaseModel):
    """Response from successful order creation."""
    success: bool
    order_count: int = Field(default=0)
    orders: list[dict] = Field(default_factory=list)
    nameservers: Optional[dict] = None
    raw_response: dict = Field(default_factory=dict)
    verified: bool = Field(default=False, description="True if post-creation verification passed")


class DNSRecordsResponse(BaseModel):
    """Response from DNS records lookup."""
    success: bool
    domain: str
    records: list[dict] = Field(default_factory=list)
    has_url_forwarding: bool = False
    forwarding_url: Optional[str] = None


class ActiveOrdersResponse(BaseModel):
    """Response from active orders listing."""
    success: bool
    count: int = 0
    orders: list[dict] = Field(default_factory=list)


class ChargeResponse(BaseModel):
    """Response from charging saved card."""
    success: bool
    subscription_id: Optional[str] = None
    total_amount: Optional[float] = None
    coupon_applied: Optional[str] = None
    message: Optional[str] = None
    raw_response: dict = Field(default_factory=dict)


# =============================================================================
# Request Models
# =============================================================================

class BisonCredentialsPayload(BaseModel):
    """EmailBison credentials for order creation."""
    api_key: str = Field(default="")
    bison_url: str = Field(default="https://spellcast.hirecharm.com")
    username: str
    password: str
    workspace: str


class WarmupSettingsPayload(BaseModel):
    """Warmup configuration for Bison/Instantly."""
    warmup_limit: int = Field(default=5, ge=1, le=50)
    warmup_reply_rate: int = Field(default=100, ge=0, le=100)
    warmup_increment: int = Field(default=1, ge=0, le=10)


class UserPayload(BaseModel):
    """User/inbox name configuration."""
    first_name: str
    last_name: str


class CreateOrderRequest(BaseModel):
    """Full order creation request payload."""
    plan: str = Field(..., pattern="^(entra|google)$", description="Plan type: entra or google")
    domains: list[str] = Field(..., min_length=1, description="List of domain names")
    domain_option: str = Field(default="i_have_my_own_domains", description="BYOD vs purchase")
    forwarding_domain: str = Field(..., description="Client's main domain for forwarding")
    client_name: str = Field(..., description="Client/company name")
    selected_tool: str = Field(default="bison", description="Email tool (always bison)")
    tool_credentials: BisonCredentialsPayload
    users: list[UserPayload] = Field(default_factory=list, max_length=10)
    warmup_setup: dict = Field(default_factory=lambda: {"enabled": True, "settings": {}})
    profile_picture_link: Optional[str] = None


# =============================================================================
# Logging Helpers
# =============================================================================

def _sanitize_payload(payload: dict) -> dict:
    """Remove sensitive data from payload for logging."""
    if not payload:
        return {}

    sanitized = payload.copy()

    # Redact credentials
    if "tool_credentials" in sanitized:
        creds = sanitized["tool_credentials"]
        if isinstance(creds, dict):
            sanitized["tool_credentials"] = {
                k: "***REDACTED***" if k in ("password", "api_key") else v
                for k, v in creds.items()
            }

    return sanitized


def _log_context(request_id: str, job_id: Optional[str] = None, **kwargs) -> str:
    """Build structured log context."""
    parts = [f"req={request_id}"]
    if job_id:
        parts.append(f"job={job_id[:8]}")
    for k, v in kwargs.items():
        parts.append(f"{k}={v}")
    return " ".join(parts)


# =============================================================================
# API Client
# =============================================================================

class HypertideAPIClient:
    """
    Async client for Hypertide REST API.

    Features:
    - Typed request/response models
    - Comprehensive error classification
    - Full request/response logging
    - Post-creation verification
    - No automatic retries (by design)

    Example:
        async with HypertideAPIClient(api_key="...") as client:
            try:
                result = await client.create_order(order_request)
                if result.verified:
                    print("Order confirmed!")
            except HypertideAPIError as e:
                if e.error_type == HypertideErrorType.DOMAIN_CONFLICT:
                    # Handle duplicate domain
                    pass
    """

    BASE_URL = "https://backend.hypertide.io/api/v1"
    DEFAULT_TIMEOUT = 60.0  # seconds

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        verify_orders: bool = True,  # Enable post-creation verification
        job_id: Optional[str] = None,  # For logging context
    ):
        self.api_key = api_key
        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout
        self.verify_orders = verify_orders
        self.job_id = job_id
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
            )

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _classify_error(
        self,
        status_code: int,
        response_body: dict,
    ) -> HypertideErrorType:
        """Classify HTTP error into error type."""
        if status_code == 401 or status_code == 403:
            return HypertideErrorType.AUTHENTICATION
        elif status_code == 400:
            # Check for specific validation errors
            error_msg = response_body.get("message", "").lower()
            if "domain" in error_msg and ("exist" in error_msg or "already" in error_msg):
                return HypertideErrorType.DOMAIN_CONFLICT
            return HypertideErrorType.VALIDATION
        elif status_code == 402:
            return HypertideErrorType.PAYMENT_REQUIRED
        elif status_code == 409:
            return HypertideErrorType.DOMAIN_CONFLICT
        elif status_code == 429:
            return HypertideErrorType.RATE_LIMITED
        elif status_code >= 500:
            return HypertideErrorType.SERVER_ERROR
        return HypertideErrorType.UNKNOWN

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
        context: Optional[str] = None,
    ) -> dict:
        """Make an HTTP request with comprehensive logging."""
        if self._client is None:
            await self.connect()

        start_time = datetime.now(timezone.utc)
        request_id = f"req_{start_time.strftime('%Y%m%d%H%M%S%f')}"
        ctx = _log_context(request_id, self.job_id)

        # Log request
        logger.info(f"[{ctx}] {method.upper()} {endpoint}")
        if json_data:
            safe_payload = _sanitize_payload(json_data)
            logger.info(f"[{ctx}] Request payload: {json.dumps(safe_payload, default=str)}")

        try:
            response = await self._client.request(
                method=method,
                url=endpoint,
                json=json_data,
            )

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Parse response
            try:
                body = response.json()
            except Exception:
                body = {"raw_text": response.text}

            # Log response (always, not just debug)
            logger.info(f"[{ctx}] Response: status={response.status_code} elapsed={elapsed:.2f}s")
            logger.info(f"[{ctx}] Response body: {json.dumps(body, default=str)[:2000]}")

            # Check for errors
            if response.status_code >= 400:
                error_type = self._classify_error(response.status_code, body)
                message = body.get("message") or body.get("error") or f"HTTP {response.status_code}"

                logger.error(
                    f"[{ctx}] API Error: type={error_type.value} status={response.status_code} "
                    f"message={message}"
                )

                raise HypertideAPIError(
                    message=message,
                    error_type=error_type,
                    status_code=response.status_code,
                    response_body=body,
                    request_id=request_id,
                    request_payload=_sanitize_payload(json_data) if json_data else None,
                )

            return body

        except httpx.TimeoutException as e:
            logger.error(f"[{ctx}] Request timed out after {self.timeout}s: {e}")
            raise HypertideAPIError(
                message=f"Request timed out after {self.timeout}s",
                error_type=HypertideErrorType.TIMEOUT,
                request_id=request_id,
                request_payload=_sanitize_payload(json_data) if json_data else None,
            )
        except httpx.ConnectError as e:
            logger.error(f"[{ctx}] Connection failed: {e}")
            raise HypertideAPIError(
                message=f"Connection failed: {e}",
                error_type=HypertideErrorType.NETWORK,
                request_id=request_id,
            )
        except HypertideAPIError:
            raise
        except Exception as e:
            logger.exception(f"[{ctx}] Unexpected error: {e}")
            raise HypertideAPIError(
                message=str(e),
                error_type=HypertideErrorType.UNKNOWN,
                request_id=request_id,
            )

    # =========================================================================
    # API Methods
    # =========================================================================

    async def get_active_orders(self) -> ActiveOrdersResponse:
        """Get active orders for this API key."""
        body = await self._request("GET", "/orders/active")
        return ActiveOrdersResponse(
            success=body.get("success", True),
            count=body.get("count", 0),
            orders=body.get("orders", []),
        )

    async def get_pending_orders(self) -> ActiveOrdersResponse:
        """Get pending orders for this API key."""
        body = await self._request("GET", "/orders/pending")
        return ActiveOrdersResponse(
            success=body.get("success", True),
            count=body.get("count", 0),
            orders=body.get("orders", []),
        )

    async def get_dns_records(self, domain: str) -> DNSRecordsResponse:
        """Get DNS records for a domain."""
        body = await self._request("GET", f"/domains/{domain}/dns-records")
        return DNSRecordsResponse(
            success=body.get("success", True),
            domain=domain,
            records=body.get("records", []),
            has_url_forwarding=body.get("hasUrlForwarding", False),
            forwarding_url=body.get("forwardingUrl"),
        )

    async def check_domain_exists(self, domain: str) -> bool:
        """
        Check if a domain is already registered in Hypertide.

        Returns True if DNS records exist (domain is managed).
        Returns False if 404 (domain not found).
        """
        try:
            result = await self.get_dns_records(domain)
            # Domain exists if we get a successful response
            logger.info(f"Domain check: {domain} exists={result.success} records={len(result.records)}")
            return result.success
        except HypertideAPIError as e:
            if e.status_code == 404:
                logger.info(f"Domain check: {domain} not found (404)")
                return False
            # Re-raise other errors
            raise

    async def check_domain_has_active_order(self, domain: str) -> tuple[bool, Optional[dict]]:
        """
        Check if domain has DNS records AND URL forwarding configured.

        This is a stronger check than just DNS existence - it indicates
        the domain is actively configured for email infrastructure.

        Returns:
            (has_active_config, dns_response_dict)
        """
        try:
            result = await self.get_dns_records(domain)

            # Consider it "active" if it has records AND forwarding
            has_active = bool(result.records) or result.has_url_forwarding

            logger.info(
                f"Domain active check: {domain} has_records={bool(result.records)} "
                f"has_forwarding={result.has_url_forwarding} -> active={has_active}"
            )

            return has_active, result.model_dump()

        except HypertideAPIError as e:
            if e.status_code == 404:
                return False, None
            raise

    async def create_order(
        self,
        request: CreateOrderRequest,
        skip_verification: bool = False,
    ) -> OrderCreatedResponse:
        """
        Create a new Hypertide order.

        Args:
            request: Order creation request
            skip_verification: Skip post-creation verification (not recommended)

        Raises:
            HypertideAPIError: With classified error type for handling

        Returns:
            OrderCreatedResponse with order details and verification status
        """
        payload = request.model_dump(mode="json", exclude_none=True)

        logger.info(
            f"Creating order: plan={request.plan} domains={len(request.domains)} "
            f"client={request.client_name}"
        )
        logger.info(f"Order domains: {', '.join(request.domains)}")

        body = await self._request("POST", "/orders", json_data=payload)

        data = body.get("data", body)
        result = OrderCreatedResponse(
            success=body.get("success", True),
            order_count=data.get("orderCount", 0),
            orders=data.get("orders", []),
            nameservers=data.get("nameservers"),
            raw_response=body,
            verified=False,
        )

        # Post-creation verification
        if result.success and self.verify_orders and not skip_verification:
            result.verified = await self._verify_order_created(request.domains)

        logger.info(
            f"Order result: success={result.success} order_count={result.order_count} "
            f"verified={result.verified}"
        )

        return result

    async def _verify_order_created(self, domains: list[str]) -> bool:
        """
        Verify that order was actually created by checking DNS records.

        Returns True if at least one domain now has DNS records.
        """
        import asyncio

        logger.info(f"Verifying order creation for {len(domains)} domains...")

        # Wait a moment for propagation
        await asyncio.sleep(2)

        verified_count = 0
        for domain in domains[:3]:  # Check first 3 domains
            try:
                exists = await self.check_domain_exists(domain)
                if exists:
                    verified_count += 1
                    logger.info(f"  Verified: {domain} now exists in Hypertide")
            except Exception as e:
                logger.warning(f"  Verification check failed for {domain}: {e}")

        # Consider verified if at least one domain checks out
        verified = verified_count > 0
        logger.info(f"Order verification: {verified_count}/{min(3, len(domains))} domains verified")

        return verified

    async def update_forwarding(
        self,
        domains: list[str],
        forwarding_domain: str,
    ) -> dict:
        """Update URL forwarding for domains."""
        body = await self._request(
            "POST",
            "/domains/update-forwarding",
            json_data={
                "domains": domains,
                "forwardingDomain": forwarding_domain,
            },
        )
        return body

    async def cancel_subscription(
        self,
        subscription_id: str,
        domains: list[str],
        cancel_immediately: bool = False,
    ) -> dict:
        """Cancel a subscription."""
        body = await self._request(
            "POST",
            "/subscriptions/cancel",
            json_data={
                "subscriptionId": subscription_id,
                "domains": domains,
                "cancelImmediately": cancel_immediately,
            },
        )
        return body

    async def charge_card(
        self,
        record_ids: list[str],
        coupon_code: Optional[str] = None,
    ) -> ChargeResponse:
        """
        Charge the saved card for created orders.

        This must be called after create_order() to complete the purchase.
        The card must already be saved in the Hypertide account.

        Args:
            record_ids: Order record IDs from create_order() response
            coupon_code: Optional discount coupon code

        Returns:
            ChargeResponse with subscription_id and total_amount

        Raises:
            HypertideAPIError: PAYMENT_REQUIRED if no card saved,
                              VALIDATION if records already paid
        """
        payload = {"recordIds": record_ids}
        if coupon_code:
            payload["couponCode"] = coupon_code

        logger.info(f"Charging card for {len(record_ids)} orders")

        body = await self._request("POST", "/payments/charge", json_data=payload)

        data = body.get("data", body)
        result = ChargeResponse(
            success=body.get("success", True),
            subscription_id=data.get("subscriptionId"),
            total_amount=data.get("totalAmount"),
            coupon_applied=data.get("couponApplied"),
            message=body.get("message"),
            raw_response=body,
        )

        logger.info(
            f"Charge result: success={result.success} "
            f"subscription_id={result.subscription_id} "
            f"total=${result.total_amount}"
        )

        return result

    async def create_and_charge_order(
        self,
        request: CreateOrderRequest,
        coupon_code: Optional[str] = None,
        skip_verification: bool = False,
    ) -> tuple[OrderCreatedResponse, Optional[ChargeResponse]]:
        """
        Create an order AND charge the saved card in one operation.

        This is the complete flow for automated purchasing:
        1. Create order (returns record IDs)
        2. Charge card (processes payment)
        3. Verify order (checks DNS)

        Args:
            request: Order creation request
            coupon_code: Optional discount coupon
            skip_verification: Skip post-creation DNS verification

        Returns:
            Tuple of (OrderCreatedResponse, ChargeResponse or None if failed)

        Raises:
            HypertideAPIError: Various error types for different failures
        """
        # Step 1: Create order
        order_result = await self.create_order(request, skip_verification=True)

        if not order_result.success or not order_result.orders:
            logger.error("Order creation failed, skipping charge")
            return order_result, None

        # Extract record IDs from orders
        record_ids = [order.get("id") for order in order_result.orders if order.get("id")]

        if not record_ids:
            logger.error("No record IDs returned from order creation")
            return order_result, None

        # Step 2: Charge card
        try:
            charge_result = await self.charge_card(record_ids, coupon_code)
        except HypertideAPIError as e:
            logger.error(f"Charge failed: {e}")
            # Return order result with charge failure info
            order_result.raw_response["charge_error"] = e.to_dict()
            return order_result, None

        # Step 3: Verify (optional)
        if self.verify_orders and not skip_verification:
            order_result.verified = await self._verify_order_created(request.domains)

        return order_result, charge_result


# =============================================================================
# Convenience Functions
# =============================================================================

async def create_bison_order(
    api_key: str,
    plan: str,
    domains: list[str],
    forwarding_domain: str,
    client_name: str,
    bison_username: str,
    bison_password: str,
    bison_workspace: str,
    bison_url: str = "https://spellcast.hirecharm.com",
    users: Optional[list[dict]] = None,
    job_id: Optional[str] = None,
) -> OrderCreatedResponse:
    """
    Convenience function to create a Bison-integrated order.

    Example:
        result = await create_bison_order(
            api_key="your-key",
            plan="entra",
            domains=["domain1.com", "domain2.com"],
            forwarding_domain="company.com",
            client_name="Acme Corp",
            bison_username="user@email.com",
            bison_password="secret",
            bison_workspace="Acme Workspace",
        )
    """
    request = CreateOrderRequest(
        plan=plan,
        domains=domains,
        forwarding_domain=forwarding_domain,
        client_name=client_name,
        selected_tool="bison",
        tool_credentials=BisonCredentialsPayload(
            username=bison_username,
            password=bison_password,
            workspace=bison_workspace,
            bison_url=bison_url,
        ),
        users=[UserPayload(**u) for u in (users or [])],
        warmup_setup={
            "enabled": True,
            "settings": {
                "warmup_limit": 5,
                "warmup_reply_rate": 100,
                "warmup_increment": 1,
            },
        },
    )

    async with HypertideAPIClient(api_key=api_key, job_id=job_id) as client:
        return await client.create_order(request)
