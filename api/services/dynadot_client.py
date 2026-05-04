"""
Dynadot API client.

Wraps the subset of Dynadot's API3 we need for the domain purchase pipeline:
    - check_availability       (Stage 0: MCP tool + pre-enqueue sanity)
    - register_domain          (Stage A: first money event)
    - set_nameservers          (Stage A: called immediately after register)
    - get_domain_info          (reconciler: resolves 'ambiguous' purchase jobs)

All calls use the JSON response format (`&format=json`) to avoid the brittle
regex-XML parsing of the previous registrars.py implementation. XML fallback
is retained for endpoints where Dynadot's JSON support is inconsistent.

Auth:
    Env var DYNADOT_API_KEY is the account key. Dynadot does not use a
    secret alongside the key (unlike Porkbun).

Endpoint: https://api.dynadot.com/api3.json (or /api3.xml fallback)
Docs:     https://www.dynadot.com/domain/api3.html
"""

import os
import logging
from typing import Optional
from decimal import Decimal

import httpx
from lxml import etree
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

DYNADOT_JSON_URL = "https://api.dynadot.com/api3.json"
DYNADOT_XML_URL = "https://api.dynadot.com/api3.xml"

# Hypertide uses DNSimple. These are the nameservers we flip to immediately
# after registering a domain at Dynadot.
DNSIMPLE_NAMESERVERS = [
    "ns1.dnsimple.com",
    "ns2.dnsimple-edge.net",
    "ns3.dnsimple.com",
    "ns4.dnsimple-edge.org",
]


# ═══════════════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════════════

class DynadotError(Exception):
    """Base for all Dynadot-raised errors."""


class DynadotAuthError(DynadotError):
    """API key rejected."""


class DynadotRateLimitError(DynadotError):
    """Dynadot throttled us. Caller should back off."""


class DynadotAmbiguousError(DynadotError):
    """
    Raised when a register/set_ns call times out or returns a response we
    cannot interpret cleanly. The pipeline worker MUST NOT retry in-process;
    it should mark the job 'ambiguous' and let the reconciler call
    get_domain_info() to determine ground truth.
    """


# ═══════════════════════════════════════════════════════════════════════════
# Response models
# ═══════════════════════════════════════════════════════════════════════════

class AvailabilityResult(BaseModel):
    domain: str
    available: bool
    price_cents: Optional[int] = None
    currency: str = "USD"
    premium: bool = False
    error: Optional[str] = None


class RegistrationResult(BaseModel):
    domain: str
    success: bool
    dynadot_order_id: Optional[str] = None
    cost_cents: Optional[int] = None
    error: Optional[str] = None


class DomainInfo(BaseModel):
    """Subset of Dynadot's domain-info response, used by the reconciler."""
    domain: str
    owned: bool
    expiration: Optional[str] = None
    nameservers: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════
# Client
# ═══════════════════════════════════════════════════════════════════════════

class DynadotClient:
    """
    Async Dynadot client. Safe to share across coroutines; owns one
    httpx.AsyncClient bound to the caller's event loop.

    Usage:
        async with DynadotClient() as dd:
            result = await dd.check_availability("example.com")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("DYNADOT_API_KEY", "")
        if not self.api_key:
            raise DynadotAuthError("DYNADOT_API_KEY not set")
        self._timeout = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "DynadotClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    # ── Internal HTTP helpers ────────────────────────────────────────────

    async def _get_json(self, params: dict) -> dict:
        """
        Call Dynadot's JSON endpoint with the API key injected.
        Raises DynadotAuthError on 401, DynadotRateLimitError on 429.
        """
        params = {"key": self.api_key, **params}
        try:
            response = await self.client.get(DYNADOT_JSON_URL, params=params)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            raise DynadotAmbiguousError(f"Dynadot request failed: {e}") from e

        if response.status_code == 401:
            raise DynadotAuthError("Dynadot rejected API key")
        if response.status_code == 429:
            raise DynadotRateLimitError("Dynadot rate limit")
        if response.status_code >= 500:
            # Server-side errors are ambiguous — the call may have succeeded
            # at Dynadot even if the response didn't reach us.
            raise DynadotAmbiguousError(
                f"Dynadot 5xx response: {response.status_code}"
            )
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as e:
            raise DynadotError(f"Dynadot returned non-JSON: {e}") from e

    async def _get_xml(self, params: dict) -> etree._Element:
        """Fallback for endpoints without reliable JSON support."""
        params = {"key": self.api_key, **params}
        try:
            response = await self.client.get(DYNADOT_XML_URL, params=params)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            raise DynadotAmbiguousError(f"Dynadot request failed: {e}") from e
        if response.status_code == 401:
            raise DynadotAuthError("Dynadot rejected API key")
        if response.status_code == 429:
            raise DynadotRateLimitError("Dynadot rate limit")
        if response.status_code >= 500:
            raise DynadotAmbiguousError(
                f"Dynadot 5xx response: {response.status_code}"
            )
        response.raise_for_status()
        try:
            return etree.fromstring(response.content)
        except etree.XMLSyntaxError as e:
            raise DynadotError(f"Dynadot XML malformed: {e}") from e

    # ── Public API ───────────────────────────────────────────────────────

    async def check_availability(self, domain: str) -> AvailabilityResult:
        """
        Check if a domain is registrable and at what price.
        Rate limit: keep batches under ~5 concurrent to stay below Dynadot's
        per-account throttle.
        """
        try:
            data = await self._get_json({"command": "search", "domain0": domain})
        except DynadotAmbiguousError as e:
            return AvailabilityResult(domain=domain, available=False, error=str(e))

        # Dynadot JSON shape: {"SearchResponse": {"ResponseCode": 0, "SearchResults": [...]}}
        envelope = data.get("SearchResponse") or data.get("Response") or {}
        response_code = envelope.get("ResponseCode")
        if response_code not in (0, "0"):
            msg = envelope.get("Error") or envelope.get("ResponseText") or "unknown"
            return AvailabilityResult(domain=domain, available=False, error=msg)

        results = envelope.get("SearchResults") or []
        if not results:
            return AvailabilityResult(domain=domain, available=False, error="no results")
        first = results[0]

        # Field names in Dynadot's response vary by schema revision; try the
        # common ones in order.
        is_available = str(first.get("Available", "")).lower() in ("yes", "true", "1")
        price_raw = (
            first.get("Price")
            or first.get("PriceList", {}).get("Price")
            or first.get("RegisterPrice")
        )
        cost_cents = None
        if price_raw:
            try:
                cost_cents = int(Decimal(str(price_raw)) * 100)
            except (ValueError, TypeError):
                cost_cents = None

        premium = str(first.get("Premium", "")).lower() in ("yes", "true", "1")

        return AvailabilityResult(
            domain=domain,
            available=is_available,
            price_cents=cost_cents,
            premium=premium,
        )

    async def register_domain(
        self,
        domain: str,
        years: int = 1,
        nameservers: Optional[list[str]] = None,
    ) -> RegistrationResult:
        """
        Register a domain at Dynadot.

        IMPORTANT: on DynadotAmbiguousError the caller MUST mark the job
        'ambiguous' and defer to the reconciler. Do NOT retry in-process.

        Passing nameservers here is a one-shot optimization — Dynadot supports
        setting NS at register time, which saves a second API call. If not
        passed, call set_nameservers() separately (needed for the DNSimple flip).
        """
        params: dict = {"command": "register", "domain": domain, "duration": years}
        if nameservers:
            for i, ns in enumerate(nameservers[:4]):
                params[f"ns{i}"] = ns

        try:
            data = await self._get_json(params)
        except DynadotAmbiguousError:
            raise  # caller handles

        envelope = data.get("RegisterResponse") or data.get("Response") or {}
        response_code = envelope.get("ResponseCode")

        if response_code in (0, "0"):
            # Dynadot doesn't return an "order id" per se — the domain itself
            # is the identifier. Record that so downstream code is uniform.
            return RegistrationResult(
                domain=domain,
                success=True,
                dynadot_order_id=domain,
            )

        # Non-success responses fall into two camps: known failures (like
        # "domain already registered") and ambiguous (network mid-reply).
        error_msg = envelope.get("Error") or envelope.get("ResponseText") or "register failed"

        # Phrases that indicate Dynadot is uncertain about our request state.
        # Be conservative — anything that might mean "succeeded but response
        # was lost" raises ambiguous.
        ambiguous_markers = ("timeout", "processing", "pending", "in progress")
        if any(m in error_msg.lower() for m in ambiguous_markers):
            raise DynadotAmbiguousError(f"Register uncertain: {error_msg}")

        return RegistrationResult(domain=domain, success=False, error=error_msg)

    async def set_nameservers(
        self,
        domain: str,
        nameservers: list[str],
    ) -> bool:
        """
        Point a domain's NS records to the given nameserver list.

        For the Hypertide pipeline, nameservers is always DNSIMPLE_NAMESERVERS.
        """
        if not nameservers:
            raise ValueError("nameservers required")

        params: dict = {"command": "set_ns", "domain": domain}
        for i, ns in enumerate(nameservers[:4]):
            params[f"ns{i}"] = ns

        data = await self._get_json(params)
        envelope = data.get("SetNsResponse") or data.get("Response") or {}
        return envelope.get("ResponseCode") in (0, "0")

    async def get_domain_info(self, domain: str) -> DomainInfo:
        """
        Query Dynadot for a domain's current state in OUR account.
        Used by the reconciler to resolve ambiguous register/set_ns outcomes.

        Returns owned=False if the domain is not in our account (either never
        registered, or registered under a different account).
        """
        try:
            data = await self._get_json({"command": "domain_info", "domain": domain})
        except DynadotAmbiguousError as e:
            logger.warning(f"domain_info ambiguous for {domain}: {e}")
            return DomainInfo(domain=domain, owned=False)

        envelope = data.get("DomainInfoResponse") or data.get("Response") or {}
        response_code = envelope.get("ResponseCode")
        if response_code not in (0, "0"):
            # Dynadot returns non-zero response code when the domain is not
            # in the account — that's "owned=False", not an error.
            return DomainInfo(domain=domain, owned=False)

        detail = envelope.get("DomainInfo") or {}
        nameservers = []
        ns_field = detail.get("NameServers") or {}
        for i in range(4):
            ns = ns_field.get(f"ServerName{i}") if isinstance(ns_field, dict) else None
            if ns:
                nameservers.append(ns)

        return DomainInfo(
            domain=domain,
            owned=True,
            expiration=detail.get("Expiration"),
            nameservers=nameservers,
        )

    async def list_domains(self) -> list[str]:
        """
        List all domains in our Dynadot account. Used by the reconciler as a
        last-resort ground-truth check when domain_info is also ambiguous.

        Uses XML endpoint because list_domain's JSON response has been flaky.
        """
        root = await self._get_xml({"command": "list_domain"})
        # Schema: <list_domain_response><DomainInfoList><DomainInfo><Name>...
        domains = []
        for name_el in root.iter("Name"):
            if name_el.text:
                domains.append(name_el.text.strip())
        return domains
