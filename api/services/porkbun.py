"""
Standalone Porkbun API integration.

Provides domain availability checking, pricing, and purchase functionality
without requiring the Hypertide module.

API Docs: https://porkbun.com/api/json/v3/documentation
"""

import asyncio
import httpx
import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DomainCheckResult(BaseModel):
    """Result from checking a single domain."""
    domain: str
    available: bool
    price: Optional[Decimal] = None
    renewal_price: Optional[Decimal] = None
    is_promotional: bool = False
    regular_price: Optional[Decimal] = None
    currency: str = "USD"
    error: Optional[str] = None


class PurchaseResult(BaseModel):
    """Result from purchasing a domain."""
    domain: str
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None


class DomainInfoResult(BaseModel):
    """Result from getting domain info (WHOIS data)."""
    domain: str
    success: bool
    creation_date: Optional[datetime] = None  # Actual WHOIS creation date
    expiration_date: Optional[datetime] = None
    error: Optional[str] = None


class PorkbunService:
    """
    Standalone Porkbun API client.

    Usage:
        async with PorkbunService() as porkbun:
            result = await porkbun.check_availability("example.com")
            if result.available:
                purchase = await porkbun.purchase("example.com")

    Or without context manager:
        porkbun = PorkbunService()
        result = await porkbun.check_availability("example.com")
        await porkbun.close()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ):
        """
        Initialize Porkbun client.

        Args:
            api_key: Porkbun API key (or use PORKBUN_API_KEY env var)
            api_secret: Porkbun API secret (or use PORKBUN_API_SECRET env var)
        """
        self.api_key = api_key or os.environ.get("PORKBUN_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("PORKBUN_API_SECRET", "")
        self.base_url = "https://api.porkbun.com/api/json/v3"
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get HTTP client, creating if needed."""
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _auth_payload(self) -> dict:
        """Get authentication payload."""
        return {
            "apikey": self.api_key,
            "secretapikey": self.api_secret,
        }

    async def ping(self) -> bool:
        """
        Test API connectivity and credentials.

        Returns:
            True if authentication is valid
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/ping",
                json=self._auth_payload(),
            )
            data = response.json()
            return data.get("status") == "SUCCESS"
        except Exception as e:
            logger.error(f"Porkbun ping failed: {e}")
            return False

    async def get_balance(self) -> Decimal:
        """
        Get account balance.

        Returns:
            Current balance in USD
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/account/getBalance",
                json=self._auth_payload(),
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "SUCCESS":
                balance = data.get("balance", "0")
                return Decimal(str(balance))
            else:
                logger.error(f"Failed to get balance: {data.get('message')}")
                return Decimal("0")
        except Exception as e:
            logger.error(f"Porkbun balance check failed: {e}")
            return Decimal("0")

    async def check_availability(self, domain: str) -> DomainCheckResult:
        """
        Check if a domain is available and get pricing.

        Args:
            domain: Full domain name (e.g., "example.com")

        Returns:
            DomainCheckResult with availability and pricing
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/domain/checkDomain/{domain}",
                json=self._auth_payload(),
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "SUCCESS":
                resp = data.get("response", {})

                # Check availability
                is_available = resp.get("avail") == "yes"

                if is_available:
                    # Get pricing
                    price_str = resp.get("price", "0")
                    regular_str = resp.get("regularPrice", price_str)
                    is_promo = resp.get("firstYearPromo") == "yes"

                    # Get renewal price from additional data
                    renewal_str = price_str
                    additional = resp.get("additional", {})
                    if "renewal" in additional:
                        renewal_str = additional["renewal"].get("price", price_str)

                    return DomainCheckResult(
                        domain=domain,
                        available=True,
                        price=Decimal(price_str),
                        renewal_price=Decimal(renewal_str),
                        is_promotional=is_promo,
                        regular_price=Decimal(regular_str) if is_promo else None,
                    )
                else:
                    return DomainCheckResult(
                        domain=domain,
                        available=False,
                    )
            else:
                return DomainCheckResult(
                    domain=domain,
                    available=False,
                    error=data.get("message"),
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"Porkbun HTTP error for {domain}: {e}")
            return DomainCheckResult(
                domain=domain,
                available=False,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Porkbun error checking {domain}: {e}")
            return DomainCheckResult(
                domain=domain,
                available=False,
                error=str(e),
            )

    async def check_bulk(
        self,
        domains: list[str],
        concurrency: int = 3,
    ) -> list[DomainCheckResult]:
        """
        Check availability for multiple domains with rate limiting.

        Porkbun has a rate limit of ~1 request per 10 seconds for domain checks,
        so we process slowly to avoid hitting limits.

        Args:
            domains: List of domain names to check
            concurrency: Max concurrent requests (default 3, keep low for rate limits)

        Returns:
            List of DomainCheckResult objects
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def check_with_semaphore(domain: str) -> DomainCheckResult:
            async with semaphore:
                result = await self.check_availability(domain)
                # Add small delay to respect rate limits
                await asyncio.sleep(0.5)
                return result

        return await asyncio.gather(*[
            check_with_semaphore(d) for d in domains
        ])

    async def purchase(
        self,
        domain: str,
        years: int = 1,
        nameservers: Optional[list[str]] = None,
    ) -> PurchaseResult:
        """
        Purchase a domain.

        Args:
            domain: Full domain name to purchase
            years: Registration period (default 1 year)
            nameservers: Custom nameservers to set (optional)

        Returns:
            PurchaseResult with success status
        """
        payload = {
            **self._auth_payload(),
            "years": years,
        }

        # Add nameservers if provided
        if nameservers:
            for i, ns in enumerate(nameservers[:4], 1):
                payload[f"ns{i}"] = ns

        try:
            response = await self.client.post(
                f"{self.base_url}/domain/register/{domain}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "SUCCESS":
                return PurchaseResult(
                    domain=domain,
                    success=True,
                    order_id=data.get("domain", domain),
                )
            else:
                error_msg = data.get("message", "Unknown error")
                logger.error(f"Porkbun purchase failed for {domain}: {error_msg}")
                return PurchaseResult(
                    domain=domain,
                    success=False,
                    error=error_msg,
                )

        except Exception as e:
            logger.error(f"Porkbun purchase error for {domain}: {e}")
            return PurchaseResult(
                domain=domain,
                success=False,
                error=str(e),
            )

    async def set_nameservers(
        self,
        domain: str,
        nameservers: list[str],
    ) -> bool:
        """
        Set nameservers for a domain.

        Args:
            domain: Domain to configure
            nameservers: List of nameserver hostnames

        Returns:
            True if successful
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/domain/updateNs/{domain}",
                json={
                    **self._auth_payload(),
                    "ns": nameservers,
                },
            )

            # Log response for debugging
            try:
                data = response.json()
                logger.info(f"Porkbun set_ns response for {domain}: status={response.status_code}, data={data}")
            except Exception:
                logger.info(f"Porkbun set_ns response for {domain}: status={response.status_code}, text={response.text[:500]}")
                data = {}

            if response.status_code >= 400:
                error_msg = data.get("message", response.text[:200])
                logger.warning(f"Porkbun set_ns error for {domain}: {error_msg}")
                return False

            return data.get("status") == "SUCCESS"
        except Exception as e:
            logger.error(f"Porkbun nameserver error for {domain}: {e}")
            return False

    async def get_nameservers(self, domain: str) -> Optional[list[str]]:
        """
        Get current nameservers for a domain.

        Args:
            domain: Domain name to check

        Returns:
            List of nameserver hostnames, or None if failed
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/domain/getNs/{domain}",
                json=self._auth_payload(),
            )
            data = response.json()

            if data.get("status") == "SUCCESS":
                # Porkbun returns ns array in response
                return data.get("ns", [])
            else:
                logger.warning(f"Porkbun get_ns failed for {domain}: {data.get('message')}")
                return None
        except Exception as e:
            logger.error(f"Porkbun get_ns error for {domain}: {e}")
            return None

    async def get_pricing(self) -> dict:
        """
        Get pricing for all TLDs.

        Returns:
            Dict mapping TLD to pricing info
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/pricing/get",
                json=self._auth_payload(),
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "SUCCESS":
                return data.get("pricing", {})
            return {}
        except Exception as e:
            logger.error(f"Porkbun pricing error: {e}")
            return {}

    async def get_domain_info(self, domain: str) -> DomainInfoResult:
        """
        Get domain information including actual WHOIS creation date.

        Porkbun API: POST /domain/info/{domain}

        Args:
            domain: Domain name to query

        Returns:
            DomainInfoResult with creation_date from registrar
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/domain/info/{domain}",
                json=self._auth_payload(),
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Porkbun domain_info response for {domain}: {data}")

            if data.get("status") == "SUCCESS":
                resp = data.get("response", {})

                # Parse creation date - Porkbun returns createDate in format "YYYY-MM-DD HH:MM:SS"
                creation_date = None
                create_date_str = resp.get("createDate")
                if create_date_str:
                    try:
                        # Try ISO format first
                        creation_date = datetime.fromisoformat(create_date_str.replace(" ", "T"))
                    except ValueError:
                        try:
                            # Fallback to common format
                            creation_date = datetime.strptime(create_date_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            logger.warning(f"Could not parse Porkbun createDate: {create_date_str}")

                # Parse expiration date
                expiration_date = None
                expire_date_str = resp.get("expireDate")
                if expire_date_str:
                    try:
                        expiration_date = datetime.fromisoformat(expire_date_str.replace(" ", "T"))
                    except ValueError:
                        try:
                            expiration_date = datetime.strptime(expire_date_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            logger.warning(f"Could not parse Porkbun expireDate: {expire_date_str}")

                return DomainInfoResult(
                    domain=domain,
                    success=True,
                    creation_date=creation_date,
                    expiration_date=expiration_date,
                )
            else:
                error_msg = data.get("message", "Unknown error")
                logger.warning(f"Porkbun domain_info failed for {domain}: {error_msg}")
                return DomainInfoResult(
                    domain=domain,
                    success=False,
                    error=error_msg,
                )

        except Exception as e:
            logger.error(f"Porkbun domain_info error for {domain}: {e}")
            return DomainInfoResult(
                domain=domain,
                success=False,
                error=str(e),
            )
