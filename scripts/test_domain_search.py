"""
Domain Search & Purchase Test Script

Test domain availability and pricing via Porkbun API.
This is a standalone script for proving out domain sourcing capabilities.

Usage:
    1. Set environment variables or create .env file:
       PORKBUN_API_KEY=pk1_xxx
       PORKBUN_API_SECRET=sk1_xxx

    2. Run the script:
       python test_domain_search.py

    3. For purchase test (DRY RUN by default):
       python test_domain_search.py --purchase
"""

import asyncio
import os
import sys
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)


@dataclass
class DomainResult:
    """Result of a domain availability check."""
    domain: str
    available: bool
    registration_price: Optional[Decimal] = None
    renewal_price: Optional[Decimal] = None
    is_promotional: bool = False
    regular_price: Optional[Decimal] = None
    error: Optional[str] = None


class PorkbunClient:
    """Simple Porkbun API client for domain operations."""

    BASE_URL = "https://api.porkbun.com/api/json/v3"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _auth_payload(self) -> dict:
        """Get authentication payload for API requests."""
        return {
            "apikey": self.api_key,
            "secretapikey": self.api_secret,
        }

    async def ping(self) -> tuple[bool, str]:
        """Test API connectivity and authentication."""
        try:
            response = await self._client.post(
                f"{self.BASE_URL}/ping",
                json=self._auth_payload(),
            )
            if response.status_code != 200:
                return False, f"HTTP {response.status_code}: {response.text[:200]}"
            data = response.json()
            if data.get("status") == "SUCCESS":
                return True, "Connected"
            else:
                return False, f"API error: {data.get('message', 'Unknown')}"
        except Exception as e:
            return False, f"Exception: {e}"

    async def check_availability(self, domain: str) -> DomainResult:
        """Check if a domain is available for registration."""
        try:
            response = await self._client.post(
                f"{self.BASE_URL}/domain/checkDomain/{domain}",
                json=self._auth_payload(),
            )

            # Handle non-200 responses with details
            if response.status_code != 200:
                try:
                    err_data = response.json()
                    err_msg = err_data.get("message", f"HTTP {response.status_code}")
                except:
                    err_msg = f"HTTP {response.status_code}"
                return DomainResult(domain=domain, available=False, error=err_msg)

            data = response.json()

            if data.get("status") == "SUCCESS":
                # Data is nested under 'response'
                resp = data.get("response", {})

                # Availability check
                is_available = resp.get("avail") == "yes"

                # Pricing
                price_str = resp.get("price", "0")
                regular_price_str = resp.get("regularPrice", price_str)
                is_promo = resp.get("firstYearPromo") == "yes"

                # Renewal price from nested additional
                renewal_str = price_str
                additional = resp.get("additional", {})
                if "renewal" in additional:
                    renewal_str = additional["renewal"].get("price", price_str)

                return DomainResult(
                    domain=domain,
                    available=is_available,
                    registration_price=Decimal(str(price_str)),
                    renewal_price=Decimal(str(renewal_str)),
                    is_promotional=is_promo,
                    regular_price=Decimal(str(regular_price_str)) if is_promo else None,
                )
            else:
                # API error
                return DomainResult(
                    domain=domain,
                    available=False,
                    error=data.get("message"),
                )
        except Exception as e:
            return DomainResult(
                domain=domain,
                available=False,
                error=str(e),
            )

    async def check_bulk(self, domains: list[str]) -> list[DomainResult]:
        """Check availability for multiple domains with Porkbun rate limiting (1 per 10s)."""
        results = []
        for i, domain in enumerate(domains):
            if i > 0:
                print(f"    (waiting 11s for rate limit...)")
                await asyncio.sleep(11)  # Porkbun: 1 check per 10 seconds
            result = await self.check_availability(domain)
            results.append(result)
            # Print progress
            status = "AVAILABLE" if result.available else ("ERROR" if result.error else "TAKEN")
            print(f"    [{i+1}/{len(domains)}] {domain}: {status}")
        return results

    async def get_pricing(self) -> dict:
        """Get all TLD pricing from Porkbun."""
        try:
            response = await self._client.post(
                f"{self.BASE_URL}/pricing/get",
                json=self._auth_payload(),
            )
            data = response.json()
            if data.get("status") == "SUCCESS":
                return data.get("pricing", {})
            return {}
        except Exception as e:
            print(f"Get pricing failed: {e}")
            return {}

    async def purchase(
        self,
        domain: str,
        years: int = 1,
        nameservers: Optional[list[str]] = None,
    ) -> dict:
        """
        Purchase a domain via Porkbun.

        WARNING: This will charge your Porkbun account!
        """
        payload = {
            **self._auth_payload(),
            "years": years,
        }

        if nameservers:
            for i, ns in enumerate(nameservers[:4], 1):
                payload[f"ns{i}"] = ns

        try:
            response = await self._client.post(
                f"{self.BASE_URL}/domain/register/{domain}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "SUCCESS":
                return {
                    "success": True,
                    "domain": domain,
                    "message": "Domain registered successfully",
                }
            else:
                return {
                    "success": False,
                    "error": data.get("message", "Unknown error"),
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }


def print_result(result: DomainResult):
    """Pretty print a domain result."""
    if result.error:
        print(f"  {result.domain}: ERROR - {result.error}")
    elif result.available:
        price = f"${result.registration_price}"
        promo = " (SALE!)" if result.is_promotional else ""
        renewal = f" | Renewal: ${result.renewal_price}/yr"
        print(f"  [OK] {result.domain}: AVAILABLE - {price}{promo}{renewal}")
    else:
        print(f"  [--] {result.domain}: NOT AVAILABLE")


async def main():
    """Run domain search tests."""
    # Check for API credentials
    api_key = os.environ.get("PORKBUN_API_KEY")
    api_secret = os.environ.get("PORKBUN_API_SECRET")

    if not api_key or not api_secret:
        print("=" * 60)
        print("PORKBUN API CREDENTIALS NOT FOUND")
        print("=" * 60)
        print()
        print("Please set the following environment variables:")
        print("  PORKBUN_API_KEY=pk1_xxx")
        print("  PORKBUN_API_SECRET=sk1_xxx")
        print()
        print("Or create a .env file in this directory with these values.")
        print()
        print("Get your API keys from: https://porkbun.com/account/api")
        print("(Enable API access in your account settings first)")
        print()
        return

    print("=" * 60)
    print("DOMAIN SEARCH TEST - Porkbun API")
    print("=" * 60)
    print()

    # Test domains for new client - adjust these based on client industry
    # Note: Each domain takes ~11 seconds due to Porkbun rate limiting
    test_domains = [
        # Professional outreach domains (likely available)
        "reloamdemos.com",
        "leadflowpipe.com",
        "connectsalespro.com",
        # Known taken (for testing)
        "google.com",
    ]

    async with PorkbunClient(api_key, api_secret) as client:
        # Test connectivity
        print("[1] Testing API connectivity...")
        success, message = await client.ping()
        if success:
            print(f"    [OK] API connection successful\n")
        else:
            print(f"    [FAIL] {message}\n")
            return

        # Check domain availability
        print("[2] Checking domain availability...")
        print()

        results = await client.check_bulk(test_domains)

        available = [r for r in results if r.available]
        unavailable = [r for r in results if not r.available and not r.error]
        errors = [r for r in results if r.error]

        print("AVAILABLE DOMAINS:")
        if available:
            for result in available:
                print_result(result)
        else:
            print("  (none found)")

        print()
        print("UNAVAILABLE DOMAINS:")
        if unavailable:
            for result in unavailable:
                print_result(result)
        else:
            print("  (none)")

        if errors:
            print()
            print("ERRORS:")
            for result in errors:
                print_result(result)

        # Summary
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Domains checked: {len(results)}")
        print(f"  Available: {len(available)}")
        print(f"  Unavailable: {len(unavailable)}")
        print(f"  Errors: {len(errors)}")

        if available:
            cheapest = min(available, key=lambda r: r.registration_price)
            print()
            print(f"  Cheapest available: {cheapest.domain} @ ${cheapest.registration_price}")

        # Purchase test (only if --purchase flag)
        if "--purchase" in sys.argv and available:
            print()
            print("=" * 60)
            print("PURCHASE TEST (DRY RUN)")
            print("=" * 60)
            print()
            print("To actually purchase, uncomment the purchase code below.")
            print(f"Would purchase: {cheapest.domain}")
            print()

            # UNCOMMENT TO ACTUALLY PURCHASE:
            # print("Purchasing domain...")
            # result = await client.purchase(
            #     cheapest.domain,
            #     years=1,
            #     nameservers=[
            #         "ns1.hypertide.com",  # Hypertide nameservers
            #         "ns2.hypertide.com",
            #     ]
            # )
            # if result["success"]:
            #     print(f"  [OK] Successfully purchased {cheapest.domain}")
            # else:
            #     print(f"  [FAIL] Purchase failed: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
