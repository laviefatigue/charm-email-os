"""
Domain sourcing workflow orchestration.

Coordinates the complete domain sourcing lifecycle:
1. Request creation from client onboarding
2. AI-powered domain generation
3. Multi-registrar search
4. Human approval checkpoint
5. Domain purchase execution
6. Hypertide BYOD integration

Example:
    workflow = DomainSourcingWorkflow()

    # Run end-to-end (interactive approval)
    session = await workflow.run(
        client_name="Acme Corp",
        industry="SaaS",
        brand_keywords=["outreach", "growth"],
        entra_domains=6,
        google_domains=5,
    )

    # Or step-by-step for programmatic control
    request = await workflow.create_request(client_data)
    candidates = await workflow.generate(request)
    results = await workflow.search(candidates)
    approved = await workflow.get_approval(results)  # Human checkpoint
    purchases = await workflow.purchase(approved)
    hypertide_order = await workflow.create_hypertide_order(purchases)
"""

from typing import Optional, Callable, Any
from datetime import datetime
from decimal import Decimal
import asyncio
import logging

from pydantic import BaseModel

from .models import (
    DomainRequest,
    DomainCandidate,
    DomainSearchResult,
    ApprovedDomain,
    PurchaseResult,
    DomainSourcingSession,
    DomainStatus,
    TLDPreference,
)
from .generator import (
    generate_domain_candidates,
    generate_fallback_candidates,
    DomainGeneratorConfig,
)
from .search import (
    search_registrars,
    SearchConfig,
    filter_by_price,
)
from .registrars import (
    Registrar,
    RegistrarFactory,
    RegistrarType,
)

# Import Hypertide models for integration
from ..models import (
    DomainConfig,
    OrderRequest,
    OrderType,
    SendingTool,
)

logger = logging.getLogger(__name__)


class ApprovalCallback:
    """
    Callback interface for human approval.

    Implementations can be:
    - CLI interactive (default)
    - Web UI
    - Slack bot
    - Email notification with link
    """

    async def present_candidates(
        self,
        results: list[DomainSearchResult],
        required_count: int,
    ) -> list[ApprovedDomain]:
        """
        Present candidates for approval and return approved list.

        Args:
            results: Sorted list of available domains
            required_count: How many domains are needed

        Returns:
            List of approved domains
        """
        raise NotImplementedError


class InteractiveApproval(ApprovalCallback):
    """CLI-based interactive approval."""

    async def present_candidates(
        self,
        results: list[DomainSearchResult],
        required_count: int,
    ) -> list[ApprovedDomain]:
        """Present candidates in CLI and get user selection."""
        print("\n" + "=" * 60)
        print(f"DOMAIN APPROVAL - Need {required_count} domains")
        print("=" * 60)

        # Filter to available only
        available = [r for r in results if r.is_available and r.best_price]

        if len(available) < required_count:
            print(f"\nWARNING: Only {len(available)} domains available!")
            print("Consider running more generations or adjusting criteria.")

        # Display top candidates
        print("\nTop Available Domains (sorted by value):")
        print("-" * 60)

        for i, result in enumerate(available[:min(30, len(available))]):
            deal_flag = " [DEAL!]" if result.is_deal else ""
            print(
                f"{i+1:3}. {result.candidate.domain_name:<25} "
                f"${result.best_price:>7} ({result.best_registrar.value}){deal_flag}"
            )

        print("-" * 60)
        print(f"\nEnter domain numbers to approve (comma-separated, need {required_count}):")
        print("Example: 1,3,5,7,9,11 or 'all' for first N or 'q' to quit")

        # Get user input
        selection = input("> ").strip().lower()

        if selection == 'q':
            return []

        if selection == 'all':
            # Auto-select first N
            indices = list(range(min(required_count, len(available))))
        else:
            # Parse comma-separated indices
            try:
                indices = [int(s.strip()) - 1 for s in selection.split(",")]
            except ValueError:
                print("Invalid input. Please enter numbers separated by commas.")
                return await self.present_candidates(results, required_count)

        # Create approved domain list
        approved = []
        for idx in indices:
            if 0 <= idx < len(available):
                result = available[idx]
                approved.append(ApprovedDomain(
                    domain_name=result.candidate.domain_name,
                    tld=result.candidate.tld,
                    registrar=result.best_registrar,
                    price=result.best_price,
                    candidate_id=result.candidate.id,
                    request_id=result.candidate.request_id,
                    approved_by="cli_user",
                ))

        print(f"\nApproved {len(approved)} domains:")
        for d in approved:
            print(f"  - {d.domain_name} @ ${d.price} ({d.registrar.value})")

        return approved


class AutoApproval(ApprovalCallback):
    """Automatic approval based on criteria (no human in loop)."""

    def __init__(
        self,
        max_price: Decimal = Decimal("10.00"),
        prefer_deals: bool = True,
        min_legitimacy_score: float = 0.6,
    ):
        self.max_price = max_price
        self.prefer_deals = prefer_deals
        self.min_legitimacy_score = min_legitimacy_score

    async def present_candidates(
        self,
        results: list[DomainSearchResult],
        required_count: int,
    ) -> list[ApprovedDomain]:
        """Automatically approve based on criteria."""
        # Filter by criteria
        eligible = [
            r for r in results
            if r.is_available
            and r.best_price
            and r.best_price <= self.max_price
            and r.candidate.legitimacy_score >= self.min_legitimacy_score
        ]

        # Sort: deals first, then by price
        if self.prefer_deals:
            eligible.sort(key=lambda r: (not r.is_deal, r.best_price))
        else:
            eligible.sort(key=lambda r: r.best_price)

        # Take required count
        selected = eligible[:required_count]

        approved = []
        for result in selected:
            approved.append(ApprovedDomain(
                domain_name=result.candidate.domain_name,
                tld=result.candidate.tld,
                registrar=result.best_registrar,
                price=result.best_price,
                candidate_id=result.candidate.id,
                request_id=result.candidate.request_id,
                approved_by="auto_approval",
            ))

        logger.info(f"Auto-approved {len(approved)} domains")
        return approved


class WebApproval(ApprovalCallback):
    """
    Web/API-based approval with tiered display.

    Stores results in database and waits for HTTP callback with selection.
    Used for async human approval via web UI or Slack.
    """

    def __init__(
        self,
        approval_id: str,
        db_connection: Any = None,
        notification_callback: Optional[Callable] = None,
    ):
        """
        Initialize web approval.

        Args:
            approval_id: UUID of the approval request in database
            db_connection: Database connection for storing/retrieving results
            notification_callback: Optional async function to notify human
        """
        self.approval_id = approval_id
        self.db = db_connection
        self.notification_callback = notification_callback

    async def present_candidates(
        self,
        results: list[DomainSearchResult],
        required_count: int,
    ) -> list[ApprovedDomain]:
        """
        Store results in database and wait for HTTP callback.

        This method:
        1. Groups results by price tier
        2. Stores in domain_approval_requests table
        3. Optionally sends notification (Slack, email, etc.)
        4. Returns empty list (approval happens asynchronously)

        The actual approval comes via API endpoint that calls
        get_approved_domains() when human submits selection.
        """
        import json

        # Group by price tier
        tier_1 = []  # Deals: $0 - $3
        tier_2 = []  # Budget: $3.01 - $5
        tier_3 = []  # Fallback: $5.01 - $8

        for result in results:
            if not result.is_available or not result.best_price:
                continue

            result_dict = result.model_dump()

            if result.best_price <= Decimal("3.00"):
                tier_1.append(result_dict)
            elif result.best_price <= Decimal("5.00"):
                tier_2.append(result_dict)
            elif result.best_price <= Decimal("8.00"):
                tier_3.append(result_dict)

        # Sort each tier by price
        for tier in [tier_1, tier_2, tier_3]:
            tier.sort(key=lambda r: Decimal(str(r.get("best_price", 999))))

        # Store in database (if db connection provided)
        if self.db:
            await self.db.execute(
                """
                UPDATE leadswarm.domain_approval_requests
                SET tier_1_results = $1,
                    tier_2_results = $2,
                    tier_3_results = $3,
                    tier_1_count = $4,
                    tier_2_count = $5,
                    tier_3_count = $6,
                    total_found = $7,
                    search_completed_at = NOW()
                WHERE id = $8
                """,
                json.dumps(tier_1),
                json.dumps(tier_2),
                json.dumps(tier_3),
                len(tier_1),
                len(tier_2),
                len(tier_3),
                len(tier_1) + len(tier_2) + len(tier_3),
                self.approval_id,
            )

        # Send notification if callback provided
        if self.notification_callback:
            try:
                await self.notification_callback(
                    approval_id=self.approval_id,
                    tier_summary={
                        "tier_1": len(tier_1),
                        "tier_2": len(tier_2),
                        "tier_3": len(tier_3),
                    },
                    required_count=required_count,
                )
            except Exception as e:
                logger.warning(f"Notification callback failed: {e}")

        logger.info(
            f"Web approval created: {len(tier_1)} deals, "
            f"{len(tier_2)} budget, {len(tier_3)} fallback"
        )

        # Return empty - approval happens asynchronously
        return []

    @staticmethod
    async def get_approved_domains(
        db_connection: Any,
        approval_id: str,
        selected_domains: list[str],
        approved_by: str,
    ) -> list[ApprovedDomain]:
        """
        Convert human selection to ApprovedDomain list.

        Called by API endpoint when human submits selection.

        Args:
            db_connection: Database connection
            approval_id: UUID of the approval request
            selected_domains: List of domain names selected by human
            approved_by: Username/email of approver

        Returns:
            List of ApprovedDomain objects ready for purchase
        """
        import json

        # Get stored results
        record = await db_connection.fetchrow(
            """
            SELECT tier_1_results, tier_2_results, tier_3_results
            FROM leadswarm.domain_approval_requests
            WHERE id = $1
            """,
            approval_id,
        )

        # Combine all tiers
        all_results = []
        for tier_json in [record["tier_1_results"], record["tier_2_results"], record["tier_3_results"]]:
            if tier_json:
                all_results.extend(json.loads(tier_json) if isinstance(tier_json, str) else tier_json)

        # Find selected domains
        approved = []
        for result in all_results:
            domain_name = result.get("candidate", {}).get("domain_name")
            if domain_name in selected_domains:
                approved.append(ApprovedDomain(
                    domain_name=domain_name,
                    tld=result.get("candidate", {}).get("tld"),
                    registrar=RegistrarType(result.get("best_registrar")),
                    price=Decimal(str(result.get("best_price"))),
                    candidate_id=result.get("candidate", {}).get("id"),
                    request_id=result.get("candidate", {}).get("request_id"),
                    approved_by=approved_by,
                ))

        # Update approval record
        await db_connection.execute(
            """
            UPDATE leadswarm.domain_approval_requests
            SET status = 'approved',
                approved_domains = $1,
                approved_by = $2,
                approved_at = NOW()
            WHERE id = $3
            """,
            json.dumps([d.model_dump() for d in approved]),
            approved_by,
            approval_id,
        )

        logger.info(f"Web approval completed: {len(approved)} domains selected")
        return approved


class DomainSourcingWorkflow:
    """
    Main workflow orchestrator for domain sourcing.

    Coordinates all stages from request to Hypertide integration.
    """

    def __init__(
        self,
        generator_config: Optional[DomainGeneratorConfig] = None,
        search_config: Optional[SearchConfig] = None,
        approval_callback: Optional[ApprovalCallback] = None,
    ):
        """
        Initialize workflow with configuration.

        Args:
            generator_config: AI domain generator config
            search_config: Registrar search config
            approval_callback: Human approval interface (default: InteractiveApproval)
        """
        self.generator_config = generator_config or DomainGeneratorConfig()
        self.search_config = search_config or SearchConfig()
        self.approval_callback = approval_callback or InteractiveApproval()
        self._registrars: Optional[list[Registrar]] = None

    async def __aenter__(self):
        """Initialize registrar connections."""
        self._registrars = RegistrarFactory.create_all()
        for r in self._registrars:
            await r.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close registrar connections."""
        if self._registrars:
            for r in self._registrars:
                await r.__aexit__(exc_type, exc_val, exc_tb)

    def create_request(
        self,
        client_name: str,
        industry: str,
        entra_domains: int = 0,
        google_domains: int = 0,
        brand_keywords: Optional[list[str]] = None,
        target_audience: str = "",
        max_price: Decimal = Decimal("15.00"),
        target_price: Decimal = Decimal("8.00"),
    ) -> DomainRequest:
        """
        Create a domain sourcing request from client data.

        Args:
            client_name: Client company name
            industry: Industry vertical
            entra_domains: Required domains for Microsoft Entra (Azure)
            google_domains: Required domains for Google Workspace
            brand_keywords: Keywords for domain generation
            target_audience: Who the client sells to
            max_price: Maximum price per domain
            target_price: Target price for deals

        Returns:
            DomainRequest ready for generation
        """
        return DomainRequest(
            client_name=client_name,
            industry=industry,
            brand_keywords=brand_keywords or [],
            target_audience=target_audience,
            required_entra_domains=entra_domains,
            required_google_domains=google_domains,
            max_price_per_domain=max_price,
            target_price_per_domain=target_price,
        )

    async def generate(
        self,
        request: DomainRequest,
        use_fallback: bool = False,
    ) -> list[DomainCandidate]:
        """
        Generate domain name candidates.

        Args:
            request: Domain sourcing request
            use_fallback: Use pattern-based generation instead of AI

        Returns:
            List of generated domain candidates
        """
        if use_fallback:
            return generate_fallback_candidates(request)
        else:
            try:
                return await generate_domain_candidates(request, self.generator_config)
            except Exception as e:
                logger.warning(f"AI generation failed, using fallback: {e}")
                return generate_fallback_candidates(request)

    async def search(
        self,
        candidates: list[DomainCandidate],
    ) -> list[DomainSearchResult]:
        """
        Search registrars for domain availability and pricing.

        Args:
            candidates: List of domain candidates

        Returns:
            Sorted list of search results (best value first)
        """
        return await search_registrars(
            candidates,
            self.search_config,
            self._registrars,
        )

    async def get_approval(
        self,
        results: list[DomainSearchResult],
        required_count: int,
    ) -> list[ApprovedDomain]:
        """
        Get human approval for domain selection.

        Args:
            results: Search results to present
            required_count: Number of domains needed

        Returns:
            List of approved domains
        """
        return await self.approval_callback.present_candidates(results, required_count)

    async def purchase(
        self,
        approved: list[ApprovedDomain],
        nameservers: Optional[list[str]] = None,
    ) -> list[PurchaseResult]:
        """
        Purchase approved domains from their respective registrars.

        Args:
            approved: List of approved domains
            nameservers: Optional nameservers to set (for Hypertide)

        Returns:
            List of purchase results
        """
        results = []

        # Group by registrar for efficiency
        by_registrar: dict[RegistrarType, list[ApprovedDomain]] = {}
        for domain in approved:
            if domain.registrar not in by_registrar:
                by_registrar[domain.registrar] = []
            by_registrar[domain.registrar].append(domain)

        # Purchase from each registrar
        for registrar_type, domains in by_registrar.items():
            registrar = RegistrarFactory.create(registrar_type)
            async with registrar:
                for domain in domains:
                    try:
                        purchase_result = await registrar.purchase(
                            domain.domain_name,
                            years=1,
                            nameservers=nameservers,
                        )

                        success = purchase_result.get("success", False)
                        result = PurchaseResult(
                            approved_domain=domain,
                            success=success,
                            registrar_order_id=purchase_result.get("order_id"),
                            actual_price=domain.price,
                            nameservers_set=bool(nameservers) and success,
                            nameservers=nameservers or [],
                            error=purchase_result.get("error"),
                        )
                        results.append(result)

                        if success:
                            logger.info(f"Purchased: {domain.domain_name}")
                        else:
                            logger.error(
                                f"Failed to purchase {domain.domain_name}: "
                                f"{purchase_result.get('error')}"
                            )

                    except Exception as e:
                        logger.error(f"Purchase error for {domain.domain_name}: {e}")
                        results.append(PurchaseResult(
                            approved_domain=domain,
                            success=False,
                            error=str(e),
                        ))

        return results

    def create_hypertide_domains(
        self,
        purchases: list[PurchaseResult],
    ) -> list[DomainConfig]:
        """
        Convert purchased domains to Hypertide BYOD DomainConfig objects.

        Args:
            purchases: List of successful purchase results

        Returns:
            List of DomainConfig for Hypertide order
        """
        configs = []

        for purchase in purchases:
            if purchase.success:
                domain = purchase.approved_domain
                configs.append(DomainConfig(
                    name=domain.domain_name.rsplit(".", 1)[0],  # Remove TLD
                    tld=domain.tld,
                    use_hypertide_domain=False,  # BYOD mode
                    custom_domain=domain.domain_name,
                ))

        return configs

    async def run(
        self,
        client_name: str,
        industry: str,
        entra_domains: int = 0,
        google_domains: int = 0,
        brand_keywords: Optional[list[str]] = None,
        dry_run: bool = False,
    ) -> DomainSourcingSession:
        """
        Run the complete domain sourcing workflow.

        This is the main entry point for end-to-end execution:
        1. Create request
        2. Generate candidates
        3. Search registrars
        4. Get human approval
        5. Purchase domains
        6. Return session with results

        Args:
            client_name: Client company name
            industry: Industry vertical
            entra_domains: Required Entra domains
            google_domains: Required Google domains
            brand_keywords: Keywords for generation
            dry_run: If True, skip actual purchases

        Returns:
            Complete session with all results
        """
        # Step 1: Create request
        request = self.create_request(
            client_name=client_name,
            industry=industry,
            entra_domains=entra_domains,
            google_domains=google_domains,
            brand_keywords=brand_keywords,
        )

        # Initialize session
        session = DomainSourcingSession(request=request, status="generating")

        # Step 2: Generate candidates
        logger.info(f"Generating domain candidates for {client_name}")
        session.candidates = await self.generate(request)
        session.status = "searching"

        # Step 3: Search registrars
        logger.info(f"Searching {len(session.candidates)} candidates across registrars")
        session.search_results = await self.search(session.candidates)
        session.status = "pending_approval"

        # Step 4: Get approval
        required = request.total_domains_needed
        session.approved = await self.get_approval(session.search_results, required)

        if not session.approved:
            logger.warning("No domains approved, aborting workflow")
            session.status = "cancelled"
            return session

        # Step 5: Purchase (unless dry run)
        if dry_run:
            logger.info("DRY RUN - skipping purchases")
            session.status = "dry_run_complete"
        else:
            session.status = "purchasing"
            session.purchases = await self.purchase(session.approved)

            successful = [p for p in session.purchases if p.success]
            failed = [p for p in session.purchases if not p.success]

            if failed:
                logger.warning(f"{len(failed)} purchases failed")
                session.status = "partial"
            elif successful:
                session.status = "completed"
            else:
                session.status = "failed"

        session.completed_at = datetime.utcnow()
        return session


# Convenience functions for simpler usage

async def approve_domains(
    results: list[DomainSearchResult],
    required_count: int,
    auto: bool = False,
    max_price: Decimal = Decimal("10.00"),
) -> list[ApprovedDomain]:
    """
    Convenience function for domain approval.

    Args:
        results: Search results to approve from
        required_count: How many domains needed
        auto: Use automatic approval instead of interactive
        max_price: Max price for auto-approval

    Returns:
        List of approved domains
    """
    if auto:
        callback = AutoApproval(max_price=max_price)
    else:
        callback = InteractiveApproval()

    return await callback.present_candidates(results, required_count)


async def purchase_approved_domains(
    approved: list[ApprovedDomain],
    nameservers: Optional[list[str]] = None,
) -> list[PurchaseResult]:
    """
    Convenience function to purchase approved domains.

    Args:
        approved: Approved domains to purchase
        nameservers: Optional nameservers to set

    Returns:
        List of purchase results
    """
    workflow = DomainSourcingWorkflow()
    async with workflow:
        return await workflow.purchase(approved, nameservers)
