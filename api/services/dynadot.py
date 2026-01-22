"""
Standalone Dynadot API integration.

Provides domain availability checking, pricing, and purchase functionality.

API Docs: https://www.dynadot.com/domain/api3.html
"""

import asyncio
import httpx
import logging
import os
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _parse_dynadot_price(price_str: str) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Parse Dynadot price string into registration and renewal prices.

    Dynadot returns prices in format:
    "Registration Price: 10.88 in USD and Renewal price: 10.88 in USD and Domain is not a Premium Domain"

    Returns:
        Tuple of (registration_price, renewal_price)
    """
    if not price_str:
        return None, None

    # Try to extract registration price
    reg_match = re.search(r'Registration Price:\s*([\d.]+)', price_str, re.IGNORECASE)
    renewal_match = re.search(r'Renewal price:\s*([\d.]+)', price_str, re.IGNORECASE)

    reg_price = Decimal(reg_match.group(1)) if reg_match else None
    renewal_price = Decimal(renewal_match.group(1)) if renewal_match else None

    # If no match found, try to parse as a plain number (fallback)
    if reg_price is None:
        try:
            reg_price = Decimal(price_str.replace(",", ""))
        except:
            pass

    return reg_price, renewal_price


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

        Dynadot API returns XML with structure like:
        <SearchResponse>
          <SearchHeader><SuccessCode>0</SuccessCode></SearchHeader>
          <SearchResults>
            <SearchResult><DomainName>test.com</DomainName>...</SearchResult>
          </SearchResults>
        </SearchResponse>

        Args:
            xml_text: Raw XML response

        Returns:
            Parsed response as dict
        """
        try:
            # Log raw response for debugging (truncated)
            logger.debug(f"Dynadot raw XML (first 500 chars): {xml_text[:500]}")

            root = ET.fromstring(xml_text)
            result = {}

            # Get response header - try multiple paths
            # Dynadot uses SearchHeader, RegisterHeader, etc. based on command
            header = root.find('.//SearchHeader')
            if header is None:
                header = root.find('.//ResponseHeader')
            if header is None:
                header = root.find('.//RegisterHeader')

            if header is not None:
                # SuccessCode: 0 = success, -1 = error
                success_code = header.findtext('SuccessCode', '-1')
                result['status'] = 'success' if success_code == '0' else 'error'
                result['error'] = header.findtext('Error', '')
                result['success_code'] = success_code
            else:
                # Check if root element indicates success
                if root.tag in ('SearchResponse', 'RegisterResponse', 'AccountResponse'):
                    result['status'] = 'success'

            # Get search results - try multiple paths
            # SearchResults container holds individual SearchResult items
            search_results_container = root.find('.//SearchResults')
            if search_results_container is not None:
                results = []
                for item in search_results_container.findall('SearchResult'):
                    domain_result = {
                        'domain': item.findtext('DomainName', ''),
                        'available': item.findtext('Available', 'no').lower() == 'yes',
                        'price': item.findtext('Price', ''),
                        'currency': item.findtext('Currency', 'USD'),
                    }
                    results.append(domain_result)
                    logger.debug(f"Dynadot parsed result: {domain_result}")
                result['search_results'] = results
            else:
                # Fallback 1: Check if SearchHeader contains domain info directly
                # Dynadot sometimes returns: <SearchHeader><DomainName>...</DomainName><Available>yes</Available></SearchHeader>
                if header is not None and header.findtext('DomainName'):
                    domain_result = {
                        'domain': header.findtext('DomainName', ''),
                        'available': header.findtext('Available', 'no').lower() == 'yes',
                        'price': header.findtext('Price', ''),
                        'currency': header.findtext('Currency', 'USD'),
                    }
                    logger.info(f"Dynadot parsed from SearchHeader: {domain_result}")
                    result['search_results'] = [domain_result]
                else:
                    # Fallback 2: try direct SearchResult under root
                    results = []
                    for item in root.findall('.//SearchResult'):
                        domain_result = {
                            'domain': item.findtext('DomainName', ''),
                            'available': item.findtext('Available', 'no').lower() == 'yes',
                            'price': item.findtext('Price', ''),
                            'currency': item.findtext('Currency', 'USD'),
                        }
                        results.append(domain_result)
                    if results:
                        result['search_results'] = results

            # Get registration result
            reg_response = root.find('.//RegisterResponse')
            if reg_response is not None:
                result['registration'] = {
                    'domain': reg_response.findtext('DomainName', ''),
                    'success': reg_response.findtext('Status', '').lower() == 'success',
                    'expiration': reg_response.findtext('Expiration', ''),
                }

            logger.debug(f"Dynadot parsed result: {result}")
            return result

        except ET.ParseError as e:
            logger.error(f"Failed to parse Dynadot XML: {e}")
            logger.error(f"Raw XML was: {xml_text[:500]}")
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
        Get account balance using Dynadot's get_account_balance command.

        Returns:
            Current balance in USD
        """
        # Check if API key is configured
        if not self.api_key:
            logger.warning("Dynadot API key not configured")
            return Decimal("0")

        try:
            # Use get_account_balance command (not account_info)
            response = await self.client.get(
                self.base_url,
                params={
                    "key": self.api_key,
                    "command": "get_account_balance",
                },
            )
            response.raise_for_status()

            # Log raw response for debugging
            logger.info(f"Dynadot balance response: {response.text[:500]}")

            # Parse XML to find balance - try multiple possible element names
            root = ET.fromstring(response.text)

            # The actual structure is:
            # <GetAccountBalanceContent><BalanceList><Balance><Currency>USD</Currency><Amount>20.00</Amount></Balance></BalanceList>
            # So we need to find the Amount element within Balance

            # Try various possible element paths for the amount
            balance_paths = [
                './/Amount',  # Direct path to Amount element
                './/Balance/Amount',  # Amount inside Balance
                './/BalanceList/Balance/Amount',  # Full path
                './/GetAccountBalanceContent/BalanceList/Balance/Amount',  # Complete path
                './/Balance',  # Fallback: Balance element with text
                './/AccountBalance',  # Legacy path
            ]

            for path in balance_paths:
                balance_elem = root.find(path)
                if balance_elem is not None and balance_elem.text:
                    try:
                        balance = Decimal(balance_elem.text.strip())
                        logger.info(f"Dynadot balance found at {path}: ${balance}")
                        return balance
                    except Exception as e:
                        logger.warning(f"Failed to parse balance at {path}: {e}")

            # Log the full XML structure for debugging
            logger.warning(f"Could not find balance in Dynadot response. Full XML: {response.text}")
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
        # Check if API key is configured
        if not self.api_key:
            logger.warning("Dynadot API key not configured")
            return DomainCheckResult(
                domain=domain,
                available=False,
                error="Dynadot API key not configured",
            )

        try:
            logger.info(f"Dynadot checking availability for: {domain}")
            response = await self.client.get(
                self.base_url,
                params={
                    "key": self.api_key,
                    "command": "search",
                    "domain0": domain,
                    "show_price": "1",  # Request pricing information
                    "currency": "USD",
                },
            )
            response.raise_for_status()

            logger.info(f"Dynadot response status: {response.status_code}")
            # Log raw XML for debugging (first 1000 chars)
            logger.info(f"Dynadot raw response: {response.text[:1000]}")
            data = self._parse_xml_response(response.text)
            logger.info(f"Dynadot parsed data: {data}")

            if data.get("status", "").lower() == "success":
                results = data.get("search_results", [])
                logger.info(f"Dynadot found {len(results)} results for {domain}")

                if results:
                    result = results[0]
                    is_available = result.get("available", False)

                    if is_available:
                        price_str = result.get("price", "")
                        logger.info(f"Dynadot: {domain} is available, raw price: {price_str}")

                        # Parse the price string (handles both plain numbers and descriptive strings)
                        reg_price, renewal_price = _parse_dynadot_price(price_str)
                        logger.info(f"Dynadot: {domain} parsed prices - reg: {reg_price}, renewal: {renewal_price}")

                        return DomainCheckResult(
                            domain=domain,
                            available=True,
                            price=reg_price,
                            renewal_price=renewal_price or reg_price,
                        )
                    else:
                        logger.info(f"Dynadot: {domain} is NOT available")
                        return DomainCheckResult(
                            domain=domain,
                            available=False,
                        )
                else:
                    logger.warning(f"Dynadot: No search results returned for {domain}")

            error_msg = data.get("error", "No results returned")
            logger.warning(f"Dynadot error for {domain}: {error_msg}")
            return DomainCheckResult(
                domain=domain,
                available=False,
                error=error_msg,
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
                    "show_price": "1",  # Request pricing information
                    "currency": "USD",
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
                        price_str = result.get("price", "")
                        reg_price, renewal_price = _parse_dynadot_price(price_str)

                        results.append(DomainCheckResult(
                            domain=domain_name,
                            available=True,
                            price=reg_price,
                            renewal_price=renewal_price or reg_price,
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
