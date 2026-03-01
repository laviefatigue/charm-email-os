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
from datetime import datetime
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


class DomainInfoResult(BaseModel):
    """Result from getting domain info (WHOIS data)."""
    domain: str
    success: bool
    creation_date: Optional[datetime] = None  # Actual WHOIS creation date
    expiration_date: Optional[datetime] = None
    error: Optional[str] = None


class DomainListItem(BaseModel):
    """A domain from the account's domain list."""
    domain: str
    expiration_date: Optional[datetime] = None
    registration_date: Optional[datetime] = None
    is_locked: bool = False
    is_expired: bool = False
    auto_renew: bool = False
    nameservers: list[str] = []


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
            # Dynadot uses SearchHeader, RegisterHeader, SetNsHeader, etc. based on command
            header = root.find('.//SearchHeader')
            if header is None:
                header = root.find('.//ResponseHeader')
            if header is None:
                header = root.find('.//RegisterHeader')
            if header is None:
                header = root.find('.//SetNsHeader')

            if header is not None:
                # SuccessCode: 0 = success, non-zero = error
                success_code = header.findtext('SuccessCode', '-1')
                result['status'] = 'success' if success_code == '0' else 'error'
                # Dynadot puts errors in <Error> element, but sometimes in <Status> element
                # (e.g. "insufficient_funds" for registration failures)
                error_msg = header.findtext('Error', '')
                if not error_msg and success_code != '0':
                    # Check Status field for error message (e.g., "insufficient_funds")
                    status_text = header.findtext('Status', '')
                    if status_text and status_text.lower() != 'success':
                        error_msg = status_text.replace('_', ' ')
                result['error'] = error_msg
                result['success_code'] = success_code
            else:
                # Check if root element indicates success
                if root.tag in ('SearchResponse', 'RegisterResponse', 'AccountResponse', 'SetNsResponse'):
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

            # Log raw response for debugging purchase issues
            logger.info(f"Dynadot register response for {domain}: {response.text[:1000]}")

            data = self._parse_xml_response(response.text)
            logger.info(f"Dynadot register parsed data for {domain}: {data}")

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

            # Log the raw response for debugging
            logger.info(f"Dynadot set_ns response for {domain}: {response.text[:500]}")

            data = self._parse_xml_response(response.text)
            logger.info(f"Dynadot parsed data for {domain}: {data}")

            if data.get("error"):
                logger.warning(f"Dynadot set_ns error for {domain}: {data.get('error')}")
                return False

            return data.get("status", "").lower() == "success"

        except Exception as e:
            logger.error(f"Dynadot nameserver error for {domain}: {e}")
            return False

    async def get_nameservers(self, domain: str) -> Optional[list[str]]:
        """
        Get current nameservers for a domain.

        Args:
            domain: Domain name to check

        Returns:
            List of nameserver hostnames (empty list if domain exists but parked),
            or None if domain not found/error
        """
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "key": self.api_key,
                    "command": "domain_info",
                    "domain": domain,
                },
            )
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.text)

            # Check for error response (domain not in account)
            error_elem = root.find('.//Error')
            if error_elem is not None and error_elem.text:
                logger.debug(f"Dynadot domain_info error for {domain}: {error_elem.text}")
                return None

            # Check for successful response with domain info
            # Dynadot returns: <DomainInfoResponse><DomainInfoContent><Domain>...
            domain_info = root.find('.//DomainInfoContent') or root.find('.//Domain')
            if domain_info is None:
                # No domain info means domain not in account
                logger.debug(f"Dynadot no DomainInfoContent found for {domain}")
                return None

            logger.info(f"Dynadot domain {domain} found in account")

            # Domain exists in account - now check for nameservers
            nameservers = []
            ns_container = root.find('.//NameServers')
            if ns_container is not None:
                # Primary: Look for ServerName inside NameServer elements
                for ns_elem in ns_container.findall('.//NameServer/ServerName'):
                    if ns_elem.text:
                        nameservers.append(ns_elem.text.strip())
                # Fallback: Look for ServerName directly
                if not nameservers:
                    for ns_elem in ns_container.findall('.//ServerName'):
                        if ns_elem.text:
                            nameservers.append(ns_elem.text.strip())

            # Fallback: try NsName elements (older API versions)
            if not nameservers:
                for ns_elem in root.findall('.//NsName'):
                    if ns_elem.text:
                        nameservers.append(ns_elem.text.strip())

            # Return empty list for parked domains (domain exists but no NS configured)
            # This is different from None (domain doesn't exist)
            logger.debug(f"Dynadot nameservers for {domain}: {nameservers} (empty = parked)")
            return nameservers

        except Exception as e:
            logger.error(f"Dynadot get_ns error for {domain}: {e}")
            return None

    async def get_domain_info(self, domain: str) -> DomainInfoResult:
        """
        Get domain information including actual WHOIS creation date.

        Dynadot API: GET ?command=domain_info&domain={domain}

        Args:
            domain: Domain name to query

        Returns:
            DomainInfoResult with creation_date from registrar
        """
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "key": self.api_key,
                    "command": "domain_info",
                    "domain": domain,
                },
            )
            response.raise_for_status()

            logger.info(f"Dynadot domain_info response for {domain}: {response.text[:500]}")

            # Parse XML response
            root = ET.fromstring(response.text)

            # Check for error response
            error_elem = root.find('.//Error')
            if error_elem is not None and error_elem.text:
                return DomainInfoResult(
                    domain=domain,
                    success=False,
                    error=error_elem.text,
                )

            # Look for creation date in various possible element paths
            creation_date = None
            date_paths = [
                './/CreateDate',
                './/Creation',
                './/RegistrationDate',
                './/DomainInfoContent/Domain/CreateDate',
                './/Domain/CreateDate',
            ]

            for path in date_paths:
                date_elem = root.find(path)
                if date_elem is not None and date_elem.text:
                    date_str = date_elem.text.strip()
                    try:
                        # Dynadot typically returns dates in ISO format or Unix timestamp
                        if date_str.isdigit():
                            # Unix timestamp in milliseconds
                            creation_date = datetime.fromtimestamp(int(date_str) / 1000)
                        else:
                            # Try ISO format
                            creation_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except ValueError:
                        try:
                            # Try common date formats
                            for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y"]:
                                try:
                                    creation_date = datetime.strptime(date_str, fmt)
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            logger.warning(f"Could not parse Dynadot date: {date_str}")
                    if creation_date:
                        break

            # Look for expiration date
            expiration_date = None
            expire_paths = ['.//Expiration', './/ExpireDate', './/ExpirationDate']
            for path in expire_paths:
                date_elem = root.find(path)
                if date_elem is not None and date_elem.text:
                    date_str = date_elem.text.strip()
                    try:
                        if date_str.isdigit():
                            expiration_date = datetime.fromtimestamp(int(date_str) / 1000)
                        else:
                            expiration_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                    if expiration_date:
                        break

            return DomainInfoResult(
                domain=domain,
                success=True,
                creation_date=creation_date,
                expiration_date=expiration_date,
            )

        except Exception as e:
            logger.error(f"Dynadot domain_info error for {domain}: {e}")
            return DomainInfoResult(
                domain=domain,
                success=False,
                error=str(e),
            )

    async def list_domains(self) -> list[DomainListItem]:
        """
        List all domains in the Dynadot account.

        Dynadot API: GET ?command=list_domain

        Returns:
            List of DomainListItem objects for all domains in the account
        """
        # Check if API key is configured
        if not self.api_key:
            logger.warning("Dynadot API key not configured")
            return []

        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "key": self.api_key,
                    "command": "list_domain",
                },
            )
            response.raise_for_status()

            logger.info(f"Dynadot list_domain response (first 1000 chars): {response.text[:1000]}")

            # Parse XML response
            root = ET.fromstring(response.text)

            # Check for error response
            error_elem = root.find('.//Error')
            if error_elem is not None and error_elem.text:
                logger.error(f"Dynadot list_domain error: {error_elem.text}")
                return []

            domains = []

            # Dynadot returns: <DomainInfoList><DomainInfo><Domain>...</Domain><Domain>...</Domain>...
            # There is ONE DomainInfo element containing MULTIPLE Domain children
            # Each Domain element contains the data for one domain
            domain_elements = root.findall('.//DomainInfo/Domain')
            if not domain_elements:
                # Fallback: try .//Domain directly
                domain_elements = root.findall('.//Domain')

            for domain_elem in domain_elements:

                domain_name = None

                # Try to find domain name - it's in Domain/Name
                name_elem = domain_elem.find('Name')
                if name_elem is not None and name_elem.text:
                    domain_name = name_elem.text.strip()
                else:
                    # Fallback paths
                    name_elem = domain_elem.find('DomainName')
                    if name_elem is not None and name_elem.text:
                        domain_name = name_elem.text.strip()
                    else:
                        domain_name = domain_elem.get('name') or domain_elem.text

                if not domain_name:
                    continue

                # Parse dates - also inside Domain element
                expiration_date = None
                exp_elem = domain_elem.find('Expiration')
                if exp_elem is not None and exp_elem.text:
                    try:
                        date_str = exp_elem.text.strip()
                        if date_str.isdigit():
                            expiration_date = datetime.fromtimestamp(int(date_str) / 1000)
                        else:
                            expiration_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except (ValueError, OSError):
                        pass

                registration_date = None
                reg_elem = domain_elem.find('Registration') or domain_elem.find('CreateDate')
                if reg_elem is not None and reg_elem.text:
                    try:
                        date_str = reg_elem.text.strip()
                        if date_str.isdigit():
                            registration_date = datetime.fromtimestamp(int(date_str) / 1000)
                        else:
                            registration_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except (ValueError, OSError):
                        pass

                # Parse boolean flags
                is_locked = False
                lock_elem = domain_elem.find('Locked')
                if lock_elem is not None:
                    is_locked = lock_elem.text and lock_elem.text.lower() in ('yes', 'true', '1')

                is_expired = False
                expired_elem = domain_elem.find('Expired')
                if expired_elem is not None:
                    is_expired = expired_elem.text and expired_elem.text.lower() in ('yes', 'true', '1')

                auto_renew = False
                renew_elem = domain_elem.find('AutoRenew') or domain_elem.find('Renew')
                if renew_elem is not None:
                    auto_renew = renew_elem.text and renew_elem.text.lower() in ('yes', 'true', '1')

                # Parse nameservers - inside NameServerSettings/NameServers/NameServer/ServerName
                nameservers = []
                ns_container = domain_elem.find('NameServerSettings') or domain_elem.find('NameServers')
                if ns_container is not None:
                    for ns_elem in ns_container.findall('.//ServerName'):
                        if ns_elem.text:
                            nameservers.append(ns_elem.text.strip())
                    if not nameservers:
                        for ns_elem in ns_container.findall('.//NameServer'):
                            ns_name = ns_elem.findtext('ServerName') or ns_elem.text
                            if ns_name:
                                nameservers.append(ns_name.strip())

                domains.append(DomainListItem(
                    domain=domain_name.lower(),
                    expiration_date=expiration_date,
                    registration_date=registration_date,
                    is_locked=is_locked,
                    is_expired=is_expired,
                    auto_renew=auto_renew,
                    nameservers=nameservers,
                ))

            logger.info(f"Dynadot list_domain found {len(domains)} domains")
            return domains

        except ET.ParseError as e:
            logger.error(f"Failed to parse Dynadot list_domain XML: {e}")
            return []
        except Exception as e:
            logger.error(f"Dynadot list_domain error: {e}")
            return []
