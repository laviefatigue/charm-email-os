"""
Hypertide Order Service

Business logic layer for order creation with:
- Comprehensive duplicate detection (DB + API + pending jobs)
- No automatic retries
- Status tracking with detailed logging
- Integration with Slack notifications

Usage:
    service = HypertideOrderService(api_key="...", db_conn=conn)
    result = await service.create_order(request)
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional, Protocol
from uuid import UUID

from .client import (
    HypertideAPIClient,
    HypertideAPIError,
    HypertideErrorType,
    CreateOrderRequest as APICreateOrderRequest,
    BisonCredentialsPayload,
    UserPayload,
    WarmupSettingsPayload,
)
from .models import (
    PlanType,
    OrderStatus,
    FailureReason,
    SingleOrderRequest,
    BatchOrderRequest,
    OrderResult,
    BatchOrderResult,
    BisonCredentials,
    InboxUser,
    PLAN_SPECS,
    group_domains_for_orders,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Logging Context
# =============================================================================

def _log(level: str, job_id: Optional[UUID], message: str, **kwargs):
    """Structured logging with job context."""
    ctx = f"[job={str(job_id)[:8]}]" if job_id else "[no-job]"
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    full_msg = f"{ctx} {message} {extra}".strip()

    getattr(logger, level)(full_msg)


# =============================================================================
# Database Protocol
# =============================================================================

class DatabaseProtocol(Protocol):
    """Protocol for database operations (allows mocking in tests)."""

    async def check_domain_exists(self, domain: str) -> bool:
        """Check if domain exists in our database with active infrastructure."""
        ...

    async def check_domains_exist(self, domains: list[str]) -> list[str]:
        """Check which domains already exist. Returns list of existing domains."""
        ...

    async def check_domains_in_pending_jobs(self, domains: list[str]) -> list[str]:
        """Check which domains are in pending/executing jobs. Returns list."""
        ...

    async def save_order_job(self, job: dict) -> UUID:
        """Save order job to database."""
        ...

    async def update_order_status(
        self,
        job_id: UUID,
        status: OrderStatus,
        **kwargs,
    ) -> None:
        """Update order job status."""
        ...

    async def get_order_job(self, job_id: UUID) -> Optional[dict]:
        """Get order job by ID."""
        ...


# =============================================================================
# Null Database (for standalone usage)
# =============================================================================

class NullDatabase:
    """No-op database for standalone API usage without persistence."""

    async def check_domain_exists(self, domain: str) -> bool:
        return False

    async def check_domains_exist(self, domains: list[str]) -> list[str]:
        return []

    async def check_domains_in_pending_jobs(self, domains: list[str]) -> list[str]:
        return []

    async def save_order_job(self, job: dict) -> UUID:
        return job.get("id", UUID("00000000-0000-0000-0000-000000000000"))

    async def update_order_status(self, job_id: UUID, status: OrderStatus, **kwargs) -> None:
        pass

    async def get_order_job(self, job_id: UUID) -> Optional[dict]:
        return None


# =============================================================================
# Duplicate Check Result
# =============================================================================

class DuplicateCheckResult:
    """Result of comprehensive duplicate checking."""

    def __init__(self):
        self.db_existing: list[str] = []      # Domains with infrastructure in DB
        self.db_pending: list[str] = []       # Domains in pending/executing jobs
        self.api_existing: list[str] = []     # Domains found in Hypertide API
        self.api_errors: list[str] = []       # Domains where API check failed

    @property
    def all_duplicates(self) -> list[str]:
        """All domains that should not be ordered."""
        return list(set(self.db_existing + self.db_pending + self.api_existing))

    @property
    def has_duplicates(self) -> bool:
        return len(self.all_duplicates) > 0

    @property
    def has_pending(self) -> bool:
        return len(self.db_pending) > 0

    def to_dict(self) -> dict:
        return {
            "db_existing": self.db_existing,
            "db_pending": self.db_pending,
            "api_existing": self.api_existing,
            "api_errors": self.api_errors,
            "all_duplicates": self.all_duplicates,
        }


# =============================================================================
# Order Service
# =============================================================================

class HypertideOrderService:
    """
    Service layer for Hypertide order creation.

    Features:
    - Comprehensive duplicate detection (DB + pending jobs + API)
    - EmailBison-only integration
    - No automatic retries
    - Detailed logging with job context
    - Status callbacks for Slack integration

    Example:
        service = HypertideOrderService(
            api_key="your-key",
            database=your_db_adapter,
            on_order_started=notify_slack_started,
            on_order_failed=notify_slack_failed,
            on_order_completed=notify_slack_completed,
        )

        result = await service.create_single_order(order_request)
    """

    def __init__(
        self,
        api_key: str,
        database: Optional[DatabaseProtocol] = None,
        # Callbacks for status notifications (Slack, etc.)
        on_order_started: Optional[callable] = None,
        on_order_failed: Optional[callable] = None,
        on_order_completed: Optional[callable] = None,
        # Options
        check_api_duplicates: bool = True,
        check_db_duplicates: bool = True,
        check_pending_jobs: bool = True,
        verify_orders: bool = True,
    ):
        self.api_key = api_key
        self.database = database or NullDatabase()
        self.on_order_started = on_order_started
        self.on_order_failed = on_order_failed
        self.on_order_completed = on_order_completed
        self.check_api_duplicates = check_api_duplicates
        self.check_db_duplicates = check_db_duplicates
        self.check_pending_jobs = check_pending_jobs
        self.verify_orders = verify_orders
        self._client: Optional[HypertideAPIClient] = None

    async def __aenter__(self):
        self._client = HypertideAPIClient(
            api_key=self.api_key,
            verify_orders=self.verify_orders,
        )
        await self._client.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.close()
            self._client = None

    # =========================================================================
    # Duplicate Detection
    # =========================================================================

    async def check_duplicates(
        self,
        domains: list[str],
        job_id: Optional[UUID] = None,
    ) -> DuplicateCheckResult:
        """
        Comprehensive duplicate check across all sources.

        Checks:
        1. Database - domains with existing infrastructure
        2. Database - domains in pending/executing jobs
        3. API - domains registered in Hypertide

        Returns DuplicateCheckResult with detailed breakdown.
        """
        result = DuplicateCheckResult()

        _log("info", job_id, f"Starting duplicate check for {len(domains)} domains")

        # 1. Check database for existing infrastructure
        if self.check_db_duplicates:
            result.db_existing = await self.database.check_domains_exist(domains)
            if result.db_existing:
                _log("warning", job_id, f"Found {len(result.db_existing)} domains with existing infrastructure",
                     domains=result.db_existing[:5])

        # 2. Check database for pending jobs
        if self.check_pending_jobs:
            result.db_pending = await self.database.check_domains_in_pending_jobs(domains)
            if result.db_pending:
                _log("warning", job_id, f"Found {len(result.db_pending)} domains in pending jobs",
                     domains=result.db_pending[:5])

        # 3. Check API (only for domains not already flagged)
        if self.check_api_duplicates and self._client:
            already_flagged = set(result.db_existing + result.db_pending)
            remaining = [d for d in domains if d not in already_flagged]

            _log("info", job_id, f"Checking {len(remaining)} domains via Hypertide API")

            for domain in remaining:
                try:
                    has_active, dns_info = await self._client.check_domain_has_active_order(domain)
                    if has_active:
                        result.api_existing.append(domain)
                        _log("warning", job_id, f"Domain {domain} already exists in Hypertide API")
                except HypertideAPIError as e:
                    if e.status_code != 404:
                        result.api_errors.append(domain)
                        _log("error", job_id, f"API check failed for {domain}: {e}")

        # Summary
        _log("info", job_id,
             f"Duplicate check complete: db_existing={len(result.db_existing)} "
             f"db_pending={len(result.db_pending)} api_existing={len(result.api_existing)} "
             f"total_duplicates={len(result.all_duplicates)}")

        return result

    # =========================================================================
    # Order Creation
    # =========================================================================

    async def create_single_order(
        self,
        request: SingleOrderRequest,
    ) -> OrderResult:
        """
        Create a single Hypertide order.

        Flow:
        1. Log order details
        2. Check for duplicates (DB + pending + API)
        3. Notify started
        4. Call Hypertide API
        5. Verify order created
        6. Notify success/failure
        7. Return result

        No automatic retries - failures require manual intervention.
        """
        job_id = request.job_id or request.order_id

        result = OrderResult(
            order_id=request.order_id,
            success=False,
            plan=request.plan,
            domains=request.domains,
        )

        _log("info", job_id, "Starting order creation",
             plan=request.plan.value,
             domains=len(request.domains),
             client=request.client_name)
        _log("info", job_id, f"Domains: {', '.join(request.domains)}")

        try:
            # 1. Check duplicates BEFORE notifying started
            _log("info", job_id, "Phase 1: Checking for duplicates")
            dupe_check = await self.check_duplicates(request.domains, job_id)

            if dupe_check.has_duplicates:
                all_dupes = dupe_check.all_duplicates
                result.error_message = f"Duplicate domains found: {', '.join(all_dupes)}"
                result.failure_reason = FailureReason.DOMAIN_CONFLICT
                result.completed_at = datetime.now(timezone.utc)

                _log("error", job_id, "Order blocked due to duplicates",
                     duplicates=all_dupes,
                     check_result=json.dumps(dupe_check.to_dict()))

                # Special handling for pending jobs
                if dupe_check.has_pending:
                    result.error_message = (
                        f"Domains in pending jobs: {', '.join(dupe_check.db_pending)}. "
                        f"Wait for those jobs to complete or cancel them first."
                    )

                if self.on_order_failed:
                    await self.on_order_failed(request, result)

                return result

            # 2. Notify started (only after duplicate check passes)
            _log("info", job_id, "Phase 2: Sending started notification")
            if self.on_order_started:
                await self.on_order_started(request)

            # 3. Build and send API request
            _log("info", job_id, "Phase 3: Calling Hypertide API")
            api_request = self._build_api_request(request)

            if self._client is None:
                self._client = HypertideAPIClient(
                    api_key=self.api_key,
                    verify_orders=self.verify_orders,
                    job_id=str(job_id),
                )
                await self._client.connect()

            # Set job context for logging
            self._client.job_id = str(job_id)

            # Create order AND charge card (complete flow)
            response, charge_response = await self._client.create_and_charge_order(api_request)

            # 4. Process response
            _log("info", job_id, "Phase 4: Processing API response",
                 success=response.success,
                 order_count=response.order_count,
                 verified=response.verified,
                 charged=charge_response is not None)

            result.success = response.success and (charge_response is not None)
            result.hypertide_order_ids = [o.get("id", "") for o in response.orders]
            result.nameservers = response.nameservers
            result.inboxes_created = self._calculate_inboxes(request.plan, len(request.domains))
            result.monthly_cost = self._calculate_cost(request.plan, len(request.domains))
            result.completed_at = datetime.now(timezone.utc)

            # Store charge info
            if charge_response:
                result.subscription_id = charge_response.subscription_id
                _log("info", job_id, "Payment processed",
                     subscription_id=charge_response.subscription_id,
                     total_amount=charge_response.total_amount)
            else:
                # Order created but charge failed
                _log("error", job_id, "Order created but payment failed - order may be unpaid")
                result.error_message = "Order created but payment failed"

            # Check verification status
            if response.success and not response.verified:
                _log("warning", job_id, "Order reported success but verification failed - proceed with caution")

            # 5. Notify success
            if self.on_order_completed:
                await self.on_order_completed(request, result)

            _log("info", job_id, "Order completed successfully",
                 inboxes=result.inboxes_created,
                 cost=f"${result.monthly_cost}/mo",
                 hypertide_ids=result.hypertide_order_ids)

            return result

        except HypertideAPIError as e:
            result.error_message = e.message
            result.failure_reason = self._map_error_type(e.error_type)
            result.completed_at = datetime.now(timezone.utc)

            _log("error", job_id, "Order failed with API error",
                 error_type=e.error_type.value,
                 status_code=e.status_code,
                 message=e.message,
                 response=json.dumps(e.response_body)[:500])

            if self.on_order_failed:
                await self.on_order_failed(request, result)

            return result

        except Exception as e:
            result.error_message = str(e)
            result.failure_reason = FailureReason.UNKNOWN
            result.completed_at = datetime.now(timezone.utc)

            _log("error", job_id, f"Order failed with unexpected error: {e}")
            logger.exception(f"[job={str(job_id)[:8]}] Full traceback:")

            if self.on_order_failed:
                await self.on_order_failed(request, result)

            return result

    async def create_batch_order(
        self,
        request: BatchOrderRequest,
    ) -> BatchOrderResult:
        """
        Create multiple orders as a batch.

        Processes orders sequentially (no parallel API calls).
        Continues processing even if some orders fail.
        """
        result = BatchOrderResult(
            batch_id=request.batch_id,
            job_id=request.job_id,
            client_id=request.client_id,
            client_name=request.client_name,
            success=False,
        )

        _log("info", request.job_id, f"Starting batch order: {len(request.orders)} orders")

        # Pre-check all domains for duplicates
        all_domains = []
        for order in request.orders:
            all_domains.extend(order.domains)

        dupe_check = await self.check_duplicates(all_domains, request.job_id)
        if dupe_check.has_duplicates:
            result.duplicate_domains = dupe_check.all_duplicates
            _log("warning", request.job_id,
                 f"Batch has {len(result.duplicate_domains)} duplicate domains")

        # Process each order
        for i, order in enumerate(request.orders, 1):
            _log("info", request.job_id, f"Processing order {i}/{len(request.orders)}")

            # Skip orders with duplicate domains
            order_dupes = [d for d in order.domains if d in result.duplicate_domains]
            if order_dupes:
                order_result = OrderResult(
                    order_id=order.order_id,
                    success=False,
                    plan=order.plan,
                    domains=order.domains,
                    error_message=f"Duplicate domains: {', '.join(order_dupes)}",
                    failure_reason=FailureReason.DOMAIN_CONFLICT,
                    completed_at=datetime.now(timezone.utc),
                )
                result.add_result(order_result)
                continue

            # Inject shared credentials if not set
            if not order.bison_credentials:
                order.bison_credentials = request.bison_credentials

            # Inherit job_id
            order.job_id = request.job_id

            # Process order
            order_result = await self.create_single_order(order)
            result.add_result(order_result)

        result.completed_at = datetime.now(timezone.utc)

        # Final status
        result.success = result.failed_orders == 0
        result.partial_success = result.successful_orders > 0 and result.failed_orders > 0

        _log("info", request.job_id,
             f"Batch completed: {result.successful_orders}/{result.total_orders} succeeded",
             total_inboxes=result.total_inboxes,
             total_cost=f"${result.total_monthly_cost}/mo")

        return result

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_api_request(self, request: SingleOrderRequest) -> APICreateOrderRequest:
        """Convert internal request to API request format."""
        return APICreateOrderRequest(
            plan=request.plan.value,
            domains=request.domains,
            domain_option="i_have_my_own_domains",
            forwarding_domain=request.forwarding_domain,
            client_name=request.client_name,
            selected_tool="bison",
            tool_credentials=BisonCredentialsPayload(
                api_key=request.bison_credentials.api_key,
                bison_url=request.bison_credentials.bison_url,
                username=request.bison_credentials.username,
                password=request.bison_credentials.password,
                workspace=request.bison_credentials.workspace,
            ),
            users=[
                UserPayload(first_name=u.first_name, last_name=u.last_name)
                for u in request.users
            ],
            warmup_setup={
                "enabled": request.warmup_enabled,
                "settings": {
                    "warmup_limit": request.warmup_limit,
                    "warmup_reply_rate": request.warmup_reply_rate,
                    "warmup_increment": request.warmup_increment,
                },
            },
        )

    def _calculate_inboxes(self, plan: PlanType, domain_count: int) -> int:
        """Calculate total inboxes for given domains."""
        spec = PLAN_SPECS[plan]
        return domain_count * spec["inboxes_per_domain"]

    def _calculate_cost(self, plan: PlanType, domain_count: int) -> float:
        """Calculate monthly cost for given domains."""
        spec = PLAN_SPECS[plan]
        domains_per_order = spec["domains_per_order"]
        orders = (domain_count + domains_per_order - 1) // domains_per_order
        return orders * spec["cost_per_order"]

    def _map_error_type(self, error_type: HypertideErrorType) -> FailureReason:
        """Map API error type to failure reason."""
        mapping = {
            HypertideErrorType.AUTHENTICATION: FailureReason.AUTHENTICATION,
            HypertideErrorType.VALIDATION: FailureReason.VALIDATION,
            HypertideErrorType.DOMAIN_CONFLICT: FailureReason.DOMAIN_CONFLICT,
            HypertideErrorType.PAYMENT_REQUIRED: FailureReason.PAYMENT_REQUIRED,
            HypertideErrorType.RATE_LIMITED: FailureReason.API_ERROR,
            HypertideErrorType.SERVER_ERROR: FailureReason.API_ERROR,
            HypertideErrorType.TIMEOUT: FailureReason.TIMEOUT,
            HypertideErrorType.NETWORK: FailureReason.NETWORK_ERROR,
            HypertideErrorType.VERIFICATION_FAILED: FailureReason.UNKNOWN,
        }
        return mapping.get(error_type, FailureReason.UNKNOWN)


# =============================================================================
# Convenience Functions
# =============================================================================

async def create_order_simple(
    api_key: str,
    client_id: UUID,
    client_name: str,
    plan: PlanType,
    domains: list[str],
    forwarding_domain: str,
    bison_username: str,
    bison_password: str,
    bison_workspace: str,
    bison_url: str = "https://spellcast.hirecharm.com",
    users: Optional[list[dict]] = None,
) -> OrderResult:
    """
    Simple function to create a single order.

    Example:
        result = await create_order_simple(
            api_key="key",
            client_id=uuid4(),
            client_name="Acme Corp",
            plan=PlanType.ENTRA,
            domains=["domain1.com", "domain2.com"],
            forwarding_domain="acme.com",
            bison_username="user@email.com",
            bison_password="secret",
            bison_workspace="Acme Workspace",
        )
    """
    request = SingleOrderRequest(
        client_id=client_id,
        client_name=client_name,
        plan=plan,
        domains=domains,
        forwarding_domain=forwarding_domain,
        bison_credentials=BisonCredentials(
            username=bison_username,
            password=bison_password,
            workspace=bison_workspace,
            bison_url=bison_url,
        ),
        users=[InboxUser(**u) for u in (users or [])],
    )

    async with HypertideOrderService(api_key=api_key) as service:
        return await service.create_single_order(request)
