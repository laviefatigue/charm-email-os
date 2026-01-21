"""
Standalone Dynadot API integration.

Provides domain availability checking, pricing, and purchase functionality.

API Docs: https://www.dynadot.com/domain/api3.html
"""

import asyncio
import httpx
import logging
import os
import xml.etree.ElementTree as ET
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
    currency: str = "USD"
    error: Optional[str] = None


class PurchaseResult(BaseModel):
    """Result from purchasing a domain."""
    domain: str
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None


class DynadotService:
    """
    Standalone Dynadot API client.

    Usage:
        async with DynadotService() as dynadot:
            result = await dynadot.check_availability("example.com")
            if result.available:
                purchase = await dynadot.purchase("example.com")

    Or without context manager:
        dynadot = DynadotService()
        result = await dynadot.check_availability("example.com")
        await dynadot.close()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
    ):
        """
        Initialize Dynadot client.

        Args:
            api_key: Dynadot API key (or use DYNADOT_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get("DYNADOT_API_KEY", "")
        self.base_url = "https://api.dynadot.com/api3.xml"
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

    def _parse_xml_response(self, xml_text: str) -> dict:
        """
        Parse Dynadot XML response into a dict.

        Args:
            xml_text: Raw XML response

        Returns:
            Parsed response as dict
        """
        try:
            root = ET.fromstring(xml_text)
            result = {}

            # Get response header
            header = root.find('.//ResponseHeader')
            if header is not None:
                result['status'] = header.findtext('Status', '')
                result['error'] = header.findtext('Error', '')
                result['success_code'] = header.findtext('SuccessCode', '')

            # Get search results
            search_response = root.find('.//SearchResponse')
            if search_response is not None:
                results = []
                for item in search_response.findall('.//SearchResult'):
                    domain_result = {
                        'domain': item.findtext('DomainName', ''),
                        'available': item.findtext('Available', 'no').lower() == 'yes',
                        'price': item.findtext('Price', ''),
                        'currency': item.findtext('Currency', 'USD'),
                    }
                    results.append(domain_result)
                result['search_results'] = results

            # Get registration result
            reg_response = root.find('.//RegisterResponse')
            if reg_response is not None:
                result['registration'] = {
                    'domain': reg_response.findtext('DomainName', ''),
                    'success': reg_response.findtext('Status', '').lower() == 'success',
                    'expiration': reg_response.findtext('Expiration', ''),
                }

            return result

        except ET.ParseError as e:
            logger.error(f"Failed to parse Dynadot XML: {e}")
            return {'status': 'error', 'error': str(e)}

    async def ping(self) -> bool:
        """
        Test API connectivity and credentials.

        Returns:
            True if authentication is valid
        """
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "key": self.api_key,
                    "command": "account_info",
                },
            )
            data = self._parse_xml_response(response.text)
            return data.get("status", "").lower() == "success"
        except Exception as e:
            logger.error(f"Dynadot ping failed: {e}")
            return False

    async def get_balance(self) -> Decimal:
        """
        Get account balance.

        Returns:
            Current balance in USD
        """
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "key": self.api_key,
                    "command": "account_info",
                },
            )
            response.raise_for_status()

            # Parse XML to find balance
            root = ET.fromstring(response.text)
            balance_elem = root.find('.//AccountBalance')
            if balance_elem is not None:
                return Decimal(balance_elem.text or "0")
            return Decimal("0")

        except Exception as e:
            logger.error(f"Dynadot balance check failed: {e}")
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
            response = await self.client.get(
                self.base_url,
                params={
                    "key": self.api_key,
                    "command": "search",
                    "domain0": domain,
                },
            )
            response.raise_for_status()

            data = self._parse_xml_response(response.text)

            if data.get("status", "").lower() == "success":
                results = data.get("search_results", [])
                if results:
                    result = results[0]
                    is_available = result.get("available", False)

                    if is_available:
                        price_str = result.get("price", "0")
                        try:
                            price = Decimal(price_str.replace(",", ""))
                        except:
                            price = None

                        return DomainCheckResult(
                            domain=domain,
                            available=True,
                            price=price,
                            renewal_price=price,  # Dynadot doesn't distinguish
                        )
                    else:
                        return DomainCheckResult(
                            domain=domain,
                            available=False,
                        )

            return DomainCheckResult(
                domain=domain,
                available=False,
                error=data.get("error", "Unknown error"),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Dynadot HTTP error for {domain}: {e}")
            return DomainCheckResult(
                domain=domain,
                available=False,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Dynadot error checking {domain}: {e}")
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
        Check availability for multiple domains.

        Dynadot supports checking multiple domains in a single request.

        Args:
            domains: List of domain names to check
            concurrency: Max concurrent requests (for batching)

        Returns:
            List of DomainCheckResult objects
        """
        # Dynadot can check up to 100 domains in one request
        batch_size = 100
        results = []

        for i in range(0, len(domains), batch_size):
            batch = domains[i:i + batch_size]

            try:
                # Build params with domain0, domain1, etc.
                params = {
                    "key": self.api_key,
                    "command": "search",
                }
                for j, domain in enumerate(batch):
                    params[f"domain{j}"] = domain

                response = await self.client.get(self.base_url, params=params)
                response.raise_for_status()

                data = self._parse_xml_response(response.text)
                search_results = data.get("search_results", [])

                for result in search_results:
                    domain_name = result.get("domain", "")
                    is_available = result.get("available", False)

                    if is_available:
                        price_str = result.get("price", "0")
                        try:
                            price = Decimal(price_str.replace(",", ""))
                        except:
                            price = None

                        results.append(DomainCheckResult(
                            domain=domain_name,
                            available=True,
                            price=price,
                            renewal_price=price,
                        ))
                    else:
                        results.append(DomainCheckResult(
                            domain=domain_name,
                            available=False,
                        ))

                # Small delay between batches
                if i + batch_size < len(domains):
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Dynadot bulk check error: {e}")
                # Add error results for this batch
                for domain in batch:
                    results.append(DomainCheckResult(
                        domain=domain,
                        available=False,
                        error=str(e),
                    ))

        return results

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
        params = {
            "key": self.api_key,
            "command": "register",
            "domain": domain,
            "duration": years,
        }

        # Add nameservers if provided
        if nameservers:
            for i, ns in enumerate(nameservers):
                params[f"ns{i}"] = ns

        try:
            response = await self.client.get(self.base_url, params=params)
            response.raise_for_status()

            data = self._parse_xml_response(response.text)

            if data.get("status", "").lower() == "success":
                reg_info = data.get("registration", {})
                return PurchaseResult(
                    domain=domain,
                    success=True,
                    order_id=reg_info.get("expiration", domain),
                )
            else:
                error_msg = data.get("error", "Unknown error")
                logger.error(f"Dynadot purchase failed for {domain}: {error_msg}")
                return PurchaseResult(
                    domain=domain,
                    success=False,
                    error=error_msg,
                )

        except Exception as e:
            logger.error(f"Dynadot purchase error for {domain}: {e}")
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
            params = {
                "key": self.api_key,
                "command": "set_ns",
                "domain": domain,
            }
            for i, ns in enumerate(nameservers):
                params[f"ns{i}"] = ns

            response = await self.client.get(self.base_url, params=params)
            response.raise_for_status()

            data = self._parse_xml_response(response.text)
            return data.get("status", "").lower() == "success"

        except Exception as e:
            logger.error(f"Dynadot nameserver error for {domain}: {e}")
            return False
