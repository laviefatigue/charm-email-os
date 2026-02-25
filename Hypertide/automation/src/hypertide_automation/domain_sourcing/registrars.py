"""
Registrar Abstraction Layer for domain sourcing.

Provides a unified interface for checking domain availability and
pricing across multiple registrars (Porkbun, DynaDot, etc.).

Architecture:
    Registrar (ABC)
    ├── PorkbunRegistrar
    ├── DynadotRegistrar
    └── Future: NamecheapRegistrar, CloudflareRegistrar

Example:
    async with RegistrarFactory.create_all() as registrars:
        results = await asyncio.gather(*[
            r.check_availability("example.com") for r in registrars
        ])
"""

from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
from decimal import Decimal
import asyncio
import httpx
import os
import logging

from .models import RegistrarResult, RegistrarType

logger = logging.getLogger(__name__)


class RegistrarError(Exception):
    """Base exception for registrar operations."""
    pass


class RegistrarAuthError(RegistrarError):
    """Authentication failed with registrar API."""
    pass


class RegistrarRateLimitError(RegistrarError):
    """Rate limit exceeded on registrar API."""
    pass


class Registrar(ABC):
    """
    Abstract base class for domain registrar integrations.

    Each registrar implementation handles:
    - API authentication
    - Domain availability checking
    - Price retrieval (including promotional pricing)
    - Domain purchase (when approved)
    - DNS configuration (nameserver setup for Hypertide)
    """

    registrar_type: RegistrarType
    api_base_url: str

    def __init__(self, api_key: str, api_secret: Optional[str] = None):
        """
        Initialize registrar with API credentials.

        Args:
            api_key: API key for authentication
            api_secret: API secret (if required by registrar)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        """Get HTTP client, creating if needed."""
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    @abstractmethod
    async def check_availability(self, domain: str) -> RegistrarResult:
        """
        Check if a domain is available for registration.

        Args:
            domain: Full domain name (e.g., "example.com")

        Returns:
            RegistrarResult with availability and pricing info
        """
        pass

    @abstractmethod
    async def get_pricing(self, tld: str) -> dict[str, Decimal]:
        """
        Get registration and renewal pricing for a TLD.

        Args:
            tld: Top-level domain (e.g., "com", "io")

        Returns:
            Dict with 'registration' and 'renewal' prices
        """
        pass

    @abstractmethod
    async def purchase(
        self,
        domain: str,
        years: int = 1,
        nameservers: Optional[list[str]] = None,
    ) -> dict:
        """
        Purchase a domain.

        Args:
            domain: Full domain name to purchase
            years: Registration period (default 1 year)
            nameservers: Custom nameservers to set

        Returns:
            Dict with order details (order_id, status, etc.)
        """
        pass

    @abstractmethod
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
        pass

    async def check_bulk(
        self,
        domains: list[str],
        concurrency: int = 5,
    ) -> list[RegistrarResult]:
        """
        Check availability for multiple domains with rate limiting.

        Args:
            domains: List of domain names to check
            concurrency: Max concurrent requests

        Returns:
            List of RegistrarResult objects
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def check_with_semaphore(domain: str) -> RegistrarResult:
            async with semaphore:
                try:
                    return await self.check_availability(domain)
                except Exception as e:
                    logger.error(f"Error checking {domain}: {e}")
                    return RegistrarResult(
                        registrar=self.registrar_type,
                        is_available=False,
                        error=str(e),
                    )

        return await asyncio.gather(*[
            check_with_semaphore(d) for d in domains
        ])


class PorkbunRegistrar(Registrar):
    """
    Porkbun registrar integration.

    API Docs: https://porkbun.com/api/json/v3/documentation

    Known for:
    - Competitive pricing
    - Frequent sales/promotions
    - Free WHOIS privacy
    - Good API
    """

    registrar_type = RegistrarType.PORKBUN
    api_base_url = "https://api.porkbun.com/api/json/v3"

    async def check_availability(self, domain: str) -> RegistrarResult:
        """
        Check domain availability via Porkbun API.

        Endpoint: POST /domain/checkDomain/{domain}
        Rate limit: 1 check per 10 seconds
        """
        try:
            response = await self.client.post(
                f"{self.api_base_url}/domain/checkDomain/{domain}",
                json={
                    "apikey": self.api_key,
                    "secretapikey": self.api_secret,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "SUCCESS":
                # Response data is nested under 'response' key
                resp = data.get("response", {})

                # Check availability
                is_available = resp.get("avail") == "yes"

                # Pricing
                price_str = resp.get("price", "0")
                regular_str = resp.get("regularPrice", price_str)
                is_promo = resp.get("firstYearPromo") == "yes"

                # Renewal from nested additional
                renewal_str = price_str
                additional = resp.get("additional", {})
                if "renewal" in additional:
                    renewal_str = additional["renewal"].get("price", price_str)

                return RegistrarResult(
                    registrar=self.registrar_type,
                    is_available=is_available,
                    registration_price=Decimal(price_str),
                    renewal_price=Decimal(renewal_str),
                    is_promotional=is_promo,
                    regular_price=Decimal(regular_str) if is_promo else None,
                    whois_privacy_included=True,  # Porkbun includes free WHOIS privacy
                )
            else:
                # API error
                return RegistrarResult(
                    registrar=self.registrar_type,
                    is_available=False,
                    error=data.get("message"),
                )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise RegistrarAuthError("Porkbun API authentication failed")
            elif e.response.status_code == 429:
                raise RegistrarRateLimitError("Porkbun rate limit exceeded")
            logger.error(f"Porkbun HTTP error for {domain}: {e}")
            return RegistrarResult(
                registrar=self.registrar_type,
                is_available=False,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Porkbun error checking {domain}: {e}")
            return RegistrarResult(
                registrar=self.registrar_type,
                is_available=False,
                error=str(e),
            )

    async def get_pricing(self, tld: str) -> dict[str, Decimal]:
        """
        Get TLD pricing from Porkbun.

        Endpoint: POST /pricing/get
        """
        try:
            response = await self.client.post(
                f"{self.api_base_url}/pricing/get",
                json={
                    "apikey": self.api_key,
                    "secretapikey": self.api_secret,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "SUCCESS":
                pricing = data.get("pricing", {}).get(tld, {})
                return {
                    "registration": Decimal(pricing.get("registration", "0")),
                    "renewal": Decimal(pricing.get("renewal", "0")),
                }
            return {"registration": Decimal("0"), "renewal": Decimal("0")}
        except Exception as e:
            logger.error(f"Porkbun pricing error for {tld}: {e}")
            return {"registration": Decimal("0"), "renewal": Decimal("0")}

    async def purchase(
        self,
        domain: str,
        years: int = 1,
        nameservers: Optional[list[str]] = None,
    ) -> dict:
        """
        Purchase a domain via Porkbun.

        Endpoint: POST /domain/register
        """
        payload = {
            "apikey": self.api_key,
            "secretapikey": self.api_secret,
            "years": years,
        }

        if nameservers:
            for i, ns in enumerate(nameservers[:4], 1):  # Max 4 nameservers
                payload[f"ns{i}"] = ns

        try:
            response = await self.client.post(
                f"{self.api_base_url}/domain/register/{domain}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "SUCCESS":
                return {
                    "success": True,
                    "order_id": data.get("domain"),
                    "domain": domain,
                    "message": "Domain registered successfully",
                }
            else:
                return {
                    "success": False,
                    "error": data.get("message", "Unknown error"),
                }
        except Exception as e:
            logger.error(f"Porkbun purchase error for {domain}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def set_nameservers(
        self,
        domain: str,
        nameservers: list[str],
    ) -> bool:
        """
        Set nameservers for a domain at Porkbun.

        Endpoint: POST /domain/updateNs/{domain}
        """
        try:
            response = await self.client.post(
                f"{self.api_base_url}/domain/updateNs/{domain}",
                json={
                    "apikey": self.api_key,
                    "secretapikey": self.api_secret,
                    "ns": nameservers,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("status") == "SUCCESS"
        except Exception as e:
            logger.error(f"Porkbun nameserver error for {domain}: {e}")
            return False


class DynadotRegistrar(Registrar):
    """
    Dynadot registrar integration.

    API Docs: https://www.dynadot.com/domain/api3.html

    Known for:
    - Very competitive pricing on many TLDs
    - Good bulk pricing
    - Simple API
    """

    registrar_type = RegistrarType.DYNADOT
    api_base_url = "https://api.dynadot.com/api3.xml"

    async def check_availability(self, domain: str) -> RegistrarResult:
        """
        Check domain availability via Dynadot API.

        Endpoint: GET /api3.xml?key={key}&command=search&domain0={domain}
        """
        try:
            response = await self.client.get(
                self.api_base_url,
                params={
                    "key": self.api_key,
                    "command": "search",
                    "domain0": domain,
                },
            )
            response.raise_for_status()

            # Dynadot returns XML, need to parse
            # For simplicity, checking for "available" in response
            content = response.text

            # Parse basic availability from XML
            is_available = "<Available>yes</Available>" in content.lower() or \
                           "available>yes<" in content.lower()

            if is_available:
                # Extract price if available (simplified parsing)
                # Full implementation would use XML parser
                import re
                price_match = re.search(r"<Price>(\d+\.?\d*)</Price>", content)
                price = Decimal(price_match.group(1)) if price_match else Decimal("10.00")

                return RegistrarResult(
                    registrar=self.registrar_type,
                    is_available=True,
                    registration_price=price,
                    renewal_price=price,  # Dynadot usually same price
                    whois_privacy_included=False,  # Dynadot charges extra
                )
            else:
                return RegistrarResult(
                    registrar=self.registrar_type,
                    is_available=False,
                )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise RegistrarAuthError("Dynadot API authentication failed")
            logger.error(f"Dynadot HTTP error for {domain}: {e}")
            return RegistrarResult(
                registrar=self.registrar_type,
                is_available=False,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Dynadot error checking {domain}: {e}")
            return RegistrarResult(
                registrar=self.registrar_type,
                is_available=False,
                error=str(e),
            )

    async def get_pricing(self, tld: str) -> dict[str, Decimal]:
        """
        Get TLD pricing from Dynadot.

        Endpoint: GET /api3.xml?key={key}&command=get_tld_pricing
        """
        try:
            response = await self.client.get(
                self.api_base_url,
                params={
                    "key": self.api_key,
                    "command": "get_tld_pricing",
                },
            )
            response.raise_for_status()

            # Simplified - would need full XML parsing
            # Return placeholder for now
            return {"registration": Decimal("10.00"), "renewal": Decimal("10.00")}
        except Exception as e:
            logger.error(f"Dynadot pricing error for {tld}: {e}")
            return {"registration": Decimal("0"), "renewal": Decimal("0")}

    async def purchase(
        self,
        domain: str,
        years: int = 1,
        nameservers: Optional[list[str]] = None,
    ) -> dict:
        """
        Purchase a domain via Dynadot.

        Endpoint: GET /api3.xml?key={key}&command=register&domain={domain}&duration={years}
        """
        try:
            params = {
                "key": self.api_key,
                "command": "register",
                "domain": domain,
                "duration": years,
            }

            if nameservers:
                params["ns0"] = nameservers[0] if len(nameservers) > 0 else ""
                params["ns1"] = nameservers[1] if len(nameservers) > 1 else ""
                params["ns2"] = nameservers[2] if len(nameservers) > 2 else ""
                params["ns3"] = nameservers[3] if len(nameservers) > 3 else ""

            response = await self.client.get(self.api_base_url, params=params)
            response.raise_for_status()

            content = response.text
            success = "<Status>success</Status>" in content.lower() or \
                      "status>success<" in content.lower()

            if success:
                return {
                    "success": True,
                    "domain": domain,
                    "message": "Domain registered successfully",
                }
            else:
                return {
                    "success": False,
                    "error": "Registration failed",
                }
        except Exception as e:
            logger.error(f"Dynadot purchase error for {domain}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def set_nameservers(
        self,
        domain: str,
        nameservers: list[str],
    ) -> bool:
        """
        Set nameservers for a domain at Dynadot.

        Endpoint: GET /api3.xml?key={key}&command=set_ns&domain={domain}&ns0={ns}&...
        """
        try:
            params = {
                "key": self.api_key,
                "command": "set_ns",
                "domain": domain,
            }
            for i, ns in enumerate(nameservers[:4]):
                params[f"ns{i}"] = ns

            response = await self.client.get(self.api_base_url, params=params)
            response.raise_for_status()

            content = response.text
            return "success" in content.lower()
        except Exception as e:
            logger.error(f"Dynadot nameserver error for {domain}: {e}")
            return False


class RegistrarFactory:
    """
    Factory for creating registrar instances with environment-based configuration.

    Usage:
        # Create all configured registrars
        registrars = RegistrarFactory.create_all()

        # Create specific registrar
        porkbun = RegistrarFactory.create(RegistrarType.PORKBUN)
    """

    @staticmethod
    def create(registrar_type: RegistrarType) -> Registrar:
        """
        Create a single registrar instance.

        Credentials are loaded from environment variables:
        - PORKBUN_API_KEY, PORKBUN_API_SECRET
        - DYNADOT_API_KEY
        """
        if registrar_type == RegistrarType.PORKBUN:
            api_key = os.environ.get("PORKBUN_API_KEY", "")
            api_secret = os.environ.get("PORKBUN_API_SECRET", "")
            if not api_key or not api_secret:
                raise RegistrarAuthError(
                    "PORKBUN_API_KEY and PORKBUN_API_SECRET must be set"
                )
            return PorkbunRegistrar(api_key, api_secret)

        elif registrar_type == RegistrarType.DYNADOT:
            api_key = os.environ.get("DYNADOT_API_KEY", "")
            if not api_key:
                raise RegistrarAuthError("DYNADOT_API_KEY must be set")
            return DynadotRegistrar(api_key)

        else:
            raise ValueError(f"Unsupported registrar: {registrar_type}")

    @staticmethod
    def create_all() -> list[Registrar]:
        """
        Create all registrars that have credentials configured.

        Returns registrars silently if credentials are missing.
        """
        registrars = []

        # Try Porkbun
        try:
            registrars.append(RegistrarFactory.create(RegistrarType.PORKBUN))
        except RegistrarAuthError:
            logger.debug("Porkbun credentials not configured, skipping")

        # Try Dynadot
        try:
            registrars.append(RegistrarFactory.create(RegistrarType.DYNADOT))
        except RegistrarAuthError:
            logger.debug("Dynadot credentials not configured, skipping")

        return registrars

    @staticmethod
    def get_configured_registrars() -> list[RegistrarType]:
        """Return list of registrar types that have credentials configured."""
        configured = []

        if os.environ.get("PORKBUN_API_KEY") and os.environ.get("PORKBUN_API_SECRET"):
            configured.append(RegistrarType.PORKBUN)

        if os.environ.get("DYNADOT_API_KEY"):
            configured.append(RegistrarType.DYNADOT)

        return configured
