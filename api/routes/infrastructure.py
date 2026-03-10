"""
Infrastructure Provisioning Routes - Waterfall SPA API V2
Handles bulk infrastructure provisioning workflow with 6-column layout
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime, timezone
import uuid
import logging
import json

from database import fetch_all, fetch_one, execute
from deps.user import get_current_user, CurrentUser
from deps.activity import log_activity
from deps.rate_limit import rate_limit, RateLimitConfig

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================
# CONSTANTS
# ============================================

PRICE_BUDGET_LIMIT = 15.0  # Dollars
DNSIMPLE_NAMESERVERS = [
    "ns1.dnsimple.com",
    "ns2.dnsimple-edge.net",
    "ns3.dnsimple.com",
    "ns4.dnsimple-edge.org",
]

# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class ProviderSummary(BaseModel):
    provider: str
    package_count: int
    domains_actual: int  # Provisioned domains (have at least 1 inbox)
    domains_healthy: int
    domains_flagged: int  # At risk (warning + critical + all disconnected)
    domains_dead: int  # Deprecated (had inboxes, all died)
    domains_awaiting: int  # Awaiting provisioning (never had inboxes)
    inboxes_live: int
    inboxes_dead: int
    inboxes_connected: int = 0  # Live + status='Connected' (actually working)
    inboxes_disconnected: int = 0  # Live but status='Not connected' (needs reconnection)
    inboxes_total: int
    daily_capacity: int
    # Capacity recommendation fields (from v_client_capacity view)
    inboxes_target: int = 0  # Target inbox count from subscription
    inbox_gap: int = 0  # How many inboxes below target (0 = at or above target)
    domain_gap: int = 0  # How many domains below target
    orders_needed: int = 0  # HyperTide orders needed to fill gap
    buffer_ratio: Optional[float] = None  # Current pipeline buffer (incubating+reserve / active)
    target_buffer_ratio: float = 0.15  # Target spare ratio from subscription

class ClientInfraSummary(BaseModel):
    client_id: str
    client_name: str
    entra: ProviderSummary
    google: ProviderSummary
    total_domains: int
    total_inboxes: int
    total_live_inboxes: int
    total_connected_inboxes: int = 0  # Aggregated across both providers

class FilterCounts(BaseModel):
    purchased: int
    not_purchased: int
    over_budget: int
    deactivated: int
    by_tld: Dict[str, int]
    by_provider: Dict[str, int]
    by_status: Dict[str, int]

class WaterfallDomainResponse(BaseModel):
    domain_id: str
    domain_name: str
    workspace_id: str
    tld: str
    domain_source: Optional[str] = "legacy"  # generated, legacy, external

    # Column 1: Domain
    generated_at: str
    legitimacy_score: Optional[float] = None
    owned_by_client: bool

    # Column 2: Pricing
    porkbun_price: Optional[float] = None
    porkbun_available: Optional[bool] = None
    dynadot_price: Optional[float] = None
    dynadot_available: Optional[bool] = None
    best_price: Optional[float] = None
    best_registrar: Optional[str] = None
    price_checked_at: Optional[str] = None
    is_over_budget: bool

    # Column 2 (continued): Purchase
    purchased_at: Optional[str] = None
    purchase_registrar: Optional[str] = None
    purchase_price: Optional[float] = None
    purchase_status: str  # not_purchased | purchased

    # Column 3: DNS
    dns_status: str  # pending | propagating | ready | mismatch | failed
    nameservers_updated_at: Optional[str] = None
    nameserver_verified_at: Optional[str] = None
    spf_configured: Optional[bool] = None
    dkim_configured: Optional[bool] = None
    dmarc_configured: Optional[bool] = None
    mx_configured: Optional[bool] = None

    # Column 4: Provider
    assigned_provider: Optional[str] = None
    detected_provider: Optional[str] = None  # Auto-detected from inbox ESP
    provider_assigned_at: Optional[str] = None

    # Column 5: HyperTide
    hypertide_status: str  # not_ordered | ordered | provisioning | complete | failed
    hypertide_order_job_id: Optional[str] = None
    hypertide_ordered_at: Optional[str] = None
    hypertide_completed_at: Optional[str] = None

    # Column 6: Status
    domain_status: str  # live | flagged | dead
    live_inbox_count: int
    dead_inbox_count: int
    connected_inbox_count: int = 0  # Live + Connected (actually operational)
    disconnected_inbox_count: int = 0  # Live but Not connected (needs reconnection)
    total_inbox_count: int
    expected_inbox_count: int
    last_inbox_synced_at: Optional[str] = None
    days_disconnected: Optional[int] = None  # Days since oldest live inbox became disconnected

    # Fulfillment & Rotation (from migration 060/061, enhanced in 062)
    max_inboxes_seen: int = 0  # Peak inbox count ever observed from HyperTide
    fulfillment_status: str = "pending"  # pending | under_delivered | fulfilled | over_delivered
    capacity_remaining_pct: Optional[float] = None  # connected / expected * 100
    rotation_recommendation: str = "not_applicable"  # healthy | monitor | consider_rotate | rotate_now
    recommended_action: str = "none"  # none | watch | reconnect | rotate

    # Error history (from migration 062)
    burn_breakdown: Optional[Dict[str, int]] = None  # e.g., {"spam_complaint": 2, "hard_blocked_24h": 1}
    inboxes_with_complaints: int = 0
    inboxes_with_blocks: int = 0
    has_compromised_inboxes: bool = False  # True if spam complaints or hard blocks

    # Computed
    is_purchased: bool
    is_ready_for_hyper_tide: bool
    is_deactivated: bool

class WaterfallResponse(BaseModel):
    workspace_id: str
    client_id: str
    domains: List[WaterfallDomainResponse]
    total_domains: int
    summary: ClientInfraSummary
    filters: Dict[str, Any]

class BulkPurchaseRequest(BaseModel):
    client_id: str
    domain_ids: List[str]

class HyperTideOrderRequest(BaseModel):
    client_id: str
    workspace_id: str
    provider: str  # entra | google
    domain_ids: List[str]
    order_count: int

# ============================================
# HELPER FUNCTIONS
# ============================================

def extract_tld(domain_name: str) -> str:
    """Extract TLD from domain name (e.g., 'example.com' -> 'com')"""
    parts = domain_name.rsplit('.', 1)
    return parts[-1] if len(parts) > 1 else ''

def calculate_domain_status(
    live_count: int,
    dead_count: int,
    connected_count: int = 0,
    disconnected_count: int = 0,
) -> str:
    """
    Calculate domain status based on inbox counts AND connection status.

    Status hierarchy:
    - dead: 2+ dead inboxes OR no live inboxes (with dead)
    - flagged: 1 dead inbox OR has live inboxes but ALL are disconnected
    - live: has connected inboxes

    Note: Disconnected inboxes are NOT functional even if inbox_state='live'.
    A domain with all disconnected inboxes should be flagged, not shown as healthy.
    """
    # Dead: killed inboxes (2+ dead, or no live with dead)
    if dead_count >= 2 or (live_count == 0 and dead_count > 0):
        return 'dead'

    # Flagged: has 1 dead inbox
    if dead_count >= 1:
        return 'flagged'

    # Flagged: has live inboxes but ALL are disconnected (no functional inboxes)
    if live_count > 0 and connected_count == 0 and disconnected_count > 0:
        return 'flagged'

    # Live: has at least one connected inbox
    if connected_count > 0:
        return 'live'

    # Default for domains not yet provisioned
    return 'live'

def calculate_dns_status(
    purchased_at: Optional[str],
    nameserver_status: Optional[str],
    nameservers_updated_at: Optional[str],
    nameserver_verified_at: Optional[str],
    domain_source: Optional[str] = None,
    has_live_inboxes: bool = False,
) -> str:
    """
    Calculate DNS status for display.

    Legacy domains with live inboxes are assumed to have working DNS
    (their inboxes prove DNS is configured correctly).
    """
    # Legacy domains with live inboxes have proven working DNS
    if domain_source == 'legacy' and has_live_inboxes:
        return 'ready'

    # Generated domains without purchase need to be purchased first
    if domain_source == 'generated' and not purchased_at:
        return 'pending'

    # Purchased domains follow normal DNS verification flow
    if not purchased_at:
        return 'pending'

    if nameserver_status == 'verified':
        return 'ready'
    elif nameserver_status == 'failed':
        return 'failed'
    elif nameserver_status == 'mismatch':
        return 'mismatch'
    elif nameservers_updated_at and not nameserver_verified_at:
        return 'propagating'

    return 'pending'

def calculate_hypertide_status(
    order_status: Optional[str],
    synced_count: int,
    is_ready: bool,
    domain_source: Optional[str] = None,
) -> str:
    """
    Calculate HyperTide status for display.

    Legacy domains with synced inboxes were provisioned externally
    and should show as 'complete' even without a HyperTide order.
    """
    # Legacy domains with inboxes were provisioned externally
    if domain_source == 'legacy' and synced_count > 0:
        return 'complete'

    if order_status == 'completed' and synced_count > 0:
        return 'complete'
    elif order_status == 'failed':
        return 'failed'
    elif order_status in ('pending', 'executing', 'processing'):
        return 'provisioning'
    elif order_status:
        return 'ordered'

    return 'not_ordered'

def transform_domain(row: dict) -> dict:
    """Transform database row to WaterfallDomainResponse format."""
    domain_name = row['domain_name']
    tld = extract_tld(domain_name)

    # Pricing
    porkbun_price = float(row['porkbun_price']) if row.get('porkbun_price') else None
    dynadot_price = float(row['dynadot_price']) if row.get('dynadot_price') else None

    # Calculate best price
    best_price = None
    best_registrar = None
    if porkbun_price and dynadot_price:
        if porkbun_price <= dynadot_price:
            best_price = porkbun_price
            best_registrar = 'porkbun'
        else:
            best_price = dynadot_price
            best_registrar = 'dynadot'
    elif porkbun_price:
        best_price = porkbun_price
        best_registrar = 'porkbun'
    elif dynadot_price:
        best_price = dynadot_price
        best_registrar = 'dynadot'

    is_over_budget = best_price is not None and best_price > PRICE_BUDGET_LIMIT

    # Inbox counts (need these first for domain_source logic)
    # NOTE: Use 'is None' check, not 'or', because 0 is a valid value (falsy in Python)
    live_inbox_count = row.get('live_inbox_count')
    if live_inbox_count is None:
        live_inbox_count = row.get('synced_inbox_count', 0)
    dead_inbox_count = row.get('dead_inbox_count') or 0
    total_inbox_count = live_inbox_count + dead_inbox_count

    # Connection status counts (for live inboxes)
    # Connected = actively working, Disconnected = needs reconnection via HyperTide
    connected_inbox_count = row.get('connected_inbox_count') or 0
    disconnected_inbox_count = row.get('disconnected_inbox_count') or 0

    # Calculate days since oldest inbox became disconnected (for 21-day warning)
    days_disconnected = None
    oldest_disconnected_at = row.get('oldest_disconnected_at')
    if oldest_disconnected_at:
        try:
            # Handle both timezone-aware and naive datetime
            if oldest_disconnected_at.tzinfo is None:
                oldest_disconnected_at = oldest_disconnected_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = now - oldest_disconnected_at
            days_disconnected = delta.days
        except Exception:
            pass  # Ignore errors in date calculation

    # Domain source determines purchase semantics
    domain_source = row.get('domain_source', 'legacy')

    # Purchase status - FIXED LOGIC
    # Legacy domains with inboxes are "purchased" externally (don't need to buy)
    # Generated domains need to be purchased
    # Purchased domains have purchased_at set
    purchased_at = row.get('purchased_at')
    is_legacy_with_inboxes = domain_source == 'legacy' and total_inbox_count > 0
    is_purchased = purchased_at is not None or is_legacy_with_inboxes
    purchase_status = 'purchased' if is_purchased else 'not_purchased'

    # DNS status - pass domain_source and inbox info
    dns_status = calculate_dns_status(
        str(purchased_at) if purchased_at else None,
        row.get('nameserver_status'),
        str(row.get('nameservers_updated_at')) if row.get('nameservers_updated_at') else None,
        str(row.get('nameserver_verified_at')) if row.get('nameserver_verified_at') else None,
        domain_source=domain_source,
        has_live_inboxes=live_inbox_count > 0,
    )

    # Expected inbox count - prefer database value, fallback to provider-based calculation
    assigned_provider = row.get('assigned_provider')
    expected_inbox_count = row.get('expected_inbox_count')
    if not expected_inbox_count:
        expected_inbox_count = 50 if assigned_provider == 'entra' else 3 if assigned_provider == 'google' else 0

    # Fulfillment & rotation tracking (from migration 060/061, enhanced in 062)
    max_inboxes_seen = row.get('max_inboxes_seen') or 0
    fulfillment_status = row.get('fulfillment_status') or 'pending'
    capacity_remaining_pct = float(row['capacity_remaining_pct']) if row.get('capacity_remaining_pct') else None
    rotation_recommendation = row.get('rotation_recommendation') or 'not_applicable'
    recommended_action = row.get('recommended_action') or 'none'

    # Error history (from migration 062)
    burn_breakdown = row.get('burn_breakdown')  # JSONB, already a dict or None
    inboxes_with_complaints = row.get('inboxes_with_complaints') or 0
    inboxes_with_blocks = row.get('inboxes_with_blocks') or 0
    has_compromised_inboxes = row.get('has_compromised_inboxes', False)

    # Domain status - factors in both inbox_state AND connection status
    domain_status = calculate_domain_status(
        live_inbox_count,
        dead_inbox_count,
        connected_inbox_count,
        disconnected_inbox_count,
    )
    is_deactivated = domain_status == 'dead'

    # HyperTide status - pass domain_source for legacy handling
    hypertide_status = calculate_hypertide_status(
        row.get('hypertide_order_status'),
        live_inbox_count,
        dns_status == 'ready' and is_purchased,
        domain_source=domain_source,
    )

    # Is ready for HyperTide order
    # Legacy domains with inboxes are already provisioned (externally), don't show "ready to order"
    is_legacy_provisioned = domain_source == 'legacy' and total_inbox_count > 0
    is_ready_for_hyper_tide = (
        is_purchased and
        dns_status == 'ready' and
        hypertide_status == 'not_ordered' and
        not is_deactivated and
        not is_legacy_provisioned
    )

    return {
        'domain_id': str(row['domain_id']),
        'domain_name': domain_name,
        'workspace_id': str(row['workspace_id']),
        'tld': tld,
        'domain_source': row.get('domain_source', 'legacy'),

        # Column 1: Domain
        'generated_at': str(row['generated_at']) if row.get('generated_at') else None,
        'legitimacy_score': float(row['legitimacy_score']) if row.get('legitimacy_score') else None,
        'owned_by_client': row.get('owned_by_client', False),

        # Column 2: Pricing
        'porkbun_price': porkbun_price,
        'porkbun_available': row.get('porkbun_available'),
        'dynadot_price': dynadot_price,
        'dynadot_available': row.get('dynadot_available'),
        'best_price': best_price,
        'best_registrar': best_registrar,
        'price_checked_at': str(row['price_checked_at']) if row.get('price_checked_at') else None,
        'is_over_budget': is_over_budget,

        # Column 2 (continued): Purchase
        'purchased_at': str(purchased_at) if purchased_at else None,
        'purchase_registrar': row.get('selected_provider'),
        'purchase_price': float(row['cached_price']) if row.get('cached_price') else None,
        'purchase_status': purchase_status,
        'purchase_job_id': str(row['domain_purchase_job_id']) if row.get('domain_purchase_job_id') else None,

        # Column 3: DNS
        'dns_status': dns_status,
        'nameservers_updated_at': str(row['nameservers_updated_at']) if row.get('nameservers_updated_at') else None,
        'nameserver_verified_at': str(row['nameserver_verified_at']) if row.get('nameserver_verified_at') else None,
        'spf_configured': row.get('spf_configured', False),
        'dkim_configured': row.get('dkim_configured', False),
        'dmarc_configured': row.get('dmarc_configured', False),
        'mx_configured': row.get('mx_configured', False),

        # Column 4: Provider (auto-detected from inbox ESP for legacy domains)
        'assigned_provider': row.get('assigned_provider') or row.get('detected_provider'),
        'detected_provider': row.get('detected_provider'),
        'provider_assigned_at': None,  # Not tracked in current schema

        # Column 5: HyperTide
        'hypertide_status': hypertide_status,
        'hypertide_order_job_id': str(row['hypertide_order_job_id']) if row.get('hypertide_order_job_id') else None,
        'hypertide_ordered_at': str(row['hypertide_ordered_at']) if row.get('hypertide_ordered_at') else None,
        'hypertide_completed_at': None,  # TODO: Track completion

        # Column 6: Status
        'domain_status': domain_status,
        'live_inbox_count': live_inbox_count,
        'dead_inbox_count': dead_inbox_count,
        'total_inbox_count': total_inbox_count,
        'expected_inbox_count': expected_inbox_count,
        'last_inbox_synced_at': str(row['last_inbox_synced_at']) if row.get('last_inbox_synced_at') else None,

        # Connection status (for live inboxes)
        'connected_inbox_count': connected_inbox_count,
        'disconnected_inbox_count': disconnected_inbox_count,
        'days_disconnected': days_disconnected,  # Days since oldest inbox became disconnected

        # Fulfillment & rotation tracking
        'max_inboxes_seen': max_inboxes_seen,
        'fulfillment_status': fulfillment_status,
        'capacity_remaining_pct': capacity_remaining_pct,
        'rotation_recommendation': rotation_recommendation,
        'recommended_action': recommended_action,

        # Error history
        'burn_breakdown': burn_breakdown,
        'inboxes_with_complaints': inboxes_with_complaints,
        'inboxes_with_blocks': inboxes_with_blocks,
        'has_compromised_inboxes': has_compromised_inboxes,

        # Computed
        'is_purchased': is_purchased,
        'is_ready_for_hyper_tide': is_ready_for_hyper_tide,
        'is_deactivated': is_deactivated,
    }

async def get_client_infra_summary(client_id: str) -> dict:
    """
    Get infrastructure summary for "Current Infrastructure" display.

    IMPORTANT: Current Infrastructure = What's available to send RIGHT NOW

    - DOMAINS: Count of live+flagged domains only (exclude dead)
    - INBOXES: Only count inboxes from live/flagged domains
    - DAILY CAPACITY: Only count connected inboxes from live/flagged domains
    - PACKAGES: live_domains ÷ domains_per_order = orders "in use"

    Dead domains (2+ dead inboxes OR 0 live inboxes) are EXCLUDED from all counts
    because they cannot send emails.
    """
    row = await fetch_one(
        """
        SELECT * FROM v_client_capacity WHERE client_id = $1
        """,
        client_id
    )

    # Get the package template name for display
    package_info = await fetch_one(
        """
        SELECT pt.name as package_name
        FROM client_subscriptions cs
        JOIN package_templates pt ON cs.package_template_id = pt.id
        WHERE cs.client_id = $1 AND cs.status = 'active'
        """,
        client_id
    )

    # CRITICAL FIX: Compute domain status and only count from LIVE/FLAGGED domains
    # Domain status: live (healthy), flagged (1 dead OR all disconnected), dead (2+ dead OR 0 live)
    domain_and_inbox_counts = await fetch_one(
        """
        WITH domain_status AS (
            -- Compute domain status for each domain
            SELECT
                dc.domain_id,
                dc.domain_name,
                dc.workspace_id,
                dc.provider_type,
                dc.live_inboxes,
                dc.dead_inboxes,
                dc.total_inboxes,
                CASE
                    -- Dead: 2+ dead inboxes OR no live inboxes (but had some)
                    WHEN dc.dead_inboxes >= 2 THEN 'dead'
                    WHEN dc.live_inboxes = 0 AND dc.dead_inboxes > 0 THEN 'dead'
                    -- Flagged: 1 dead inbox
                    WHEN dc.dead_inboxes = 1 AND dc.live_inboxes > 0 THEN 'flagged'
                    -- Live: no dead inboxes
                    WHEN dc.live_inboxes > 0 THEN 'live'
                    -- Awaiting: no inboxes yet
                    ELSE 'awaiting'
                END as domain_status
            FROM v_domain_capacity dc
            WHERE dc.workspace_id = (SELECT workspace_id FROM clients WHERE id = $1)
        )
        SELECT
            -- Domain counts by status (for display)
            COUNT(*) FILTER (WHERE ds.provider_type = 'entra' AND ds.domain_status = 'live') as entra_healthy,
            COUNT(*) FILTER (WHERE ds.provider_type = 'entra' AND ds.domain_status = 'flagged') as entra_flagged,
            COUNT(*) FILTER (WHERE ds.provider_type = 'entra' AND ds.domain_status = 'dead') as entra_dead,
            COUNT(*) FILTER (WHERE ds.provider_type = 'google' AND ds.domain_status = 'live') as google_healthy,
            COUNT(*) FILTER (WHERE ds.provider_type = 'google' AND ds.domain_status = 'flagged') as google_flagged,
            COUNT(*) FILTER (WHERE ds.provider_type = 'google' AND ds.domain_status = 'dead') as google_dead,

            -- LIVE DOMAIN COUNT: Only healthy + flagged (these can send)
            COUNT(*) FILTER (WHERE ds.provider_type = 'entra' AND ds.domain_status IN ('live', 'flagged')) as entra_live_domains,
            COUNT(*) FILTER (WHERE ds.provider_type = 'google' AND ds.domain_status IN ('live', 'flagged')) as google_live_domains,

            -- INBOX COUNTS: Only from live/flagged domains (Current Infrastructure)
            COALESCE(SUM(ds.live_inboxes) FILTER (WHERE ds.provider_type = 'entra' AND ds.domain_status IN ('live', 'flagged')), 0) as entra_inboxes_live,
            COALESCE(SUM(ds.dead_inboxes) FILTER (WHERE ds.provider_type = 'entra' AND ds.domain_status IN ('live', 'flagged')), 0) as entra_inboxes_dead,
            COALESCE(SUM(ds.live_inboxes) FILTER (WHERE ds.provider_type = 'google' AND ds.domain_status IN ('live', 'flagged')), 0) as google_inboxes_live,
            COALESCE(SUM(ds.dead_inboxes) FILTER (WHERE ds.provider_type = 'google' AND ds.domain_status IN ('live', 'flagged')), 0) as google_inboxes_dead
        FROM domain_status ds
        """,
        client_id
    )

    # CONNECTION COUNTS: Only from live/flagged domains (for daily capacity)
    connection_counts = await fetch_one(
        """
        WITH domain_status AS (
            SELECT
                dc.domain_name,
                dc.workspace_id,
                CASE
                    WHEN dc.dead_inboxes >= 2 THEN 'dead'
                    WHEN dc.live_inboxes = 0 AND dc.dead_inboxes > 0 THEN 'dead'
                    WHEN dc.dead_inboxes = 1 AND dc.live_inboxes > 0 THEN 'flagged'
                    WHEN dc.live_inboxes > 0 THEN 'live'
                    ELSE 'awaiting'
                END as domain_status
            FROM v_domain_capacity dc
            WHERE dc.workspace_id = (SELECT workspace_id FROM clients WHERE id = $1)
        )
        SELECT
            -- Entra connection status (only from live/flagged domains)
            COUNT(*) FILTER (
                WHERE sa.esp = 'microsoft'
                AND sa.inbox_state = 'live'
                AND sa.status = 'Connected'
                AND ds.domain_status IN ('live', 'flagged')
            ) as entra_connected,
            COUNT(*) FILTER (
                WHERE sa.esp = 'microsoft'
                AND sa.inbox_state = 'live'
                AND sa.status IN ('Not connected', 'Disconnected')
                AND ds.domain_status IN ('live', 'flagged')
            ) as entra_disconnected,
            -- Google connection status (only from live/flagged domains)
            COUNT(*) FILTER (
                WHERE sa.esp = 'gmail'
                AND sa.inbox_state = 'live'
                AND sa.status = 'Connected'
                AND ds.domain_status IN ('live', 'flagged')
            ) as google_connected,
            COUNT(*) FILTER (
                WHERE sa.esp = 'gmail'
                AND sa.inbox_state = 'live'
                AND sa.status IN ('Not connected', 'Disconnected')
                AND ds.domain_status IN ('live', 'flagged')
            ) as google_disconnected
        FROM sender_accounts sa
        JOIN domain_status ds ON (
            SPLIT_PART(sa.email_address, '@', 2) = ds.domain_name
            AND sa.workspace_id = ds.workspace_id
        )
        WHERE sa.workspace_id = (SELECT workspace_id FROM clients WHERE id = $1)
        """,
        client_id
    )

    if not row:
        # Return empty summary
        return {
            'client_id': client_id,
            'client_name': 'Unknown',
            'package_name': None,
            'entra': {
                'provider': 'entra',
                'package_count': 0,
                'domains_actual': 0,
                'domains_healthy': 0,
                'domains_flagged': 0,
                'domains_dead': 0,
                'domains_awaiting': 0,
                'inboxes_live': 0,
                'inboxes_dead': 0,
                'inboxes_connected': 0,
                'inboxes_disconnected': 0,
                'inboxes_total': 0,
                'daily_capacity': 0,
                'inboxes_target': 0,
                'inbox_gap': 0,
                'domain_gap': 0,
                'orders_needed': 0,
                'buffer_ratio': None,
                'target_buffer_ratio': 0.15,
            },
            'google': {
                'provider': 'google',
                'package_count': 0,
                'domains_actual': 0,
                'domains_healthy': 0,
                'domains_flagged': 0,
                'domains_dead': 0,
                'domains_awaiting': 0,
                'inboxes_live': 0,
                'inboxes_dead': 0,
                'inboxes_connected': 0,
                'inboxes_disconnected': 0,
                'inboxes_total': 0,
                'daily_capacity': 0,
                'inboxes_target': 0,
                'inbox_gap': 0,
                'domain_gap': 0,
                'orders_needed': 0,
                'buffer_ratio': None,
                'target_buffer_ratio': 0.15,
            },
            'total_domains': 0,
            'total_inboxes': 0,
            'total_live_inboxes': 0,
            'total_connected_inboxes': 0,
        }

    # Extract domain counts and statuses from our filtered query
    dic = domain_and_inbox_counts or {}

    # Domain status counts (for display)
    entra_healthy = dic.get('entra_healthy') or 0
    entra_flagged = dic.get('entra_flagged') or 0
    entra_dead = dic.get('entra_dead') or 0
    google_healthy = dic.get('google_healthy') or 0
    google_flagged = dic.get('google_flagged') or 0
    google_dead = dic.get('google_dead') or 0

    # LIVE DOMAIN COUNT: healthy + flagged (these can send, dead cannot)
    entra_live_domains = dic.get('entra_live_domains') or 0
    google_live_domains = dic.get('google_live_domains') or 0

    # INBOX COUNTS: Only from live/flagged domains (Current Infrastructure)
    entra_inboxes_live = dic.get('entra_inboxes_live') or 0
    entra_inboxes_dead = dic.get('entra_inboxes_dead') or 0
    google_inboxes_live = dic.get('google_inboxes_live') or 0
    google_inboxes_dead = dic.get('google_inboxes_dead') or 0

    entra_inboxes_total = entra_inboxes_live + entra_inboxes_dead
    google_inboxes_total = google_inboxes_live + google_inboxes_dead

    # CONNECTION COUNTS: Only from live/flagged domains
    cc = connection_counts or {}
    entra_connected = cc.get('entra_connected') or 0
    entra_disconnected = cc.get('entra_disconnected') or 0
    google_connected = cc.get('google_connected') or 0
    google_disconnected = cc.get('google_disconnected') or 0

    return {
        'client_id': str(row['client_id']),
        'client_name': row.get('client_name', 'Unknown'),
        'package_name': package_info.get('package_name') if package_info else None,
        'entra': {
            'provider': 'entra',
            'package_count': row.get('entra_packages') or 0,
            # DOMAINS: Live domains (healthy + flagged) that can send
            'domains_actual': entra_live_domains,  # CHANGED: Only live domains, not all
            'domains_healthy': entra_healthy,
            'domains_flagged': entra_flagged,
            'domains_dead': entra_dead,  # For display only (excluded from totals)
            'domains_awaiting': row.get('entra_domains_awaiting') or 0,
            # INBOXES: Only from live domains
            'inboxes_live': entra_inboxes_live,
            'inboxes_dead': entra_inboxes_dead,
            'inboxes_connected': entra_connected,
            'inboxes_disconnected': entra_disconnected,
            'inboxes_total': entra_inboxes_total,
            # CAPACITY: Only from connected inboxes on live domains
            'daily_capacity': entra_connected * 2,
            # CAPACITY RECOMMENDATIONS (from v_client_capacity)
            'inboxes_target': row.get('entra_inboxes_target') or 0,
            'inbox_gap': row.get('entra_inbox_gap') or 0,
            'domain_gap': row.get('entra_domain_gap') or 0,
            'orders_needed': row.get('entra_orders_needed') or 0,
            'buffer_ratio': float(row['entra_buffer_ratio']) if row.get('entra_buffer_ratio') else None,
            'target_buffer_ratio': float(row['spare_ratio']) if row.get('spare_ratio') else 0.15,
        },
        'google': {
            'provider': 'google',
            'package_count': row.get('google_packages') or 0,
            # DOMAINS: Live domains (healthy + flagged) that can send
            'domains_actual': google_live_domains,  # CHANGED: Only live domains, not all
            'domains_healthy': google_healthy,
            'domains_flagged': google_flagged,
            'domains_dead': google_dead,  # For display only (excluded from totals)
            'domains_awaiting': row.get('google_domains_awaiting') or 0,
            # INBOXES: Only from live domains
            'inboxes_live': google_inboxes_live,
            'inboxes_dead': google_inboxes_dead,
            'inboxes_connected': google_connected,
            'inboxes_disconnected': google_disconnected,
            'inboxes_total': google_inboxes_total,
            # CAPACITY: Only from connected inboxes on live domains
            'daily_capacity': google_connected * 20,
            # CAPACITY RECOMMENDATIONS (from v_client_capacity)
            'inboxes_target': row.get('google_inboxes_target') or 0,
            'inbox_gap': row.get('google_inbox_gap') or 0,
            'domain_gap': row.get('google_domain_gap') or 0,
            'orders_needed': row.get('google_orders_needed') or 0,
            'buffer_ratio': float(row['google_buffer_ratio']) if row.get('google_buffer_ratio') else None,
            'target_buffer_ratio': float(row['spare_ratio']) if row.get('spare_ratio') else 0.15,
        },
        # TOTALS: Only live domains and their inboxes
        'total_domains': entra_live_domains + google_live_domains,
        'total_inboxes': entra_inboxes_total + google_inboxes_total,
        'total_live_inboxes': entra_inboxes_live + google_inboxes_live,
        'total_connected_inboxes': entra_connected + google_connected,
    }

# ============================================
# ENDPOINTS
# ============================================

@router.get("/waterfall/client/{client_id}")
async def get_waterfall_by_client(
    client_id: str,
    # Lifecycle stages: not_purchased → ready → complete (+ legacy 'purchased')
    purchase_status: Optional[str] = Query(None, regex="^(all|not_purchased|ready|complete|purchased)$"),
    tld: Optional[str] = Query(None, regex="^(com|co|info)$"),
    provider: Optional[str] = Query(None, regex="^(entra|google)$"),
    status: Optional[str] = Query(None, regex="^(live|flagged|dead)$"),
    rotation_status: Optional[str] = Query(None, regex="^(all|needs_attention|healthy)$"),
    show_over_budget: bool = Query(False),
    show_deactivated: bool = Query(False),
    show_needs_reconnection: bool = Query(False),
):
    """
    Get complete waterfall view for a client's workspace (V2).

    Args:
        client_id: UUID of client
        purchase_status: Filter by purchase status (all, purchased, not_purchased)
        tld: Filter by TLD (com, co, info)
        provider: Filter by assigned provider (entra, google)
        status: Filter by domain status (live, flagged, dead)
        show_over_budget: Include domains priced over $15 (default: false)
        show_deactivated: Include dead domains (default: false)
        show_needs_reconnection: Show only domains where all inboxes disconnected (default: false)
    """
    try:
        # First, get the client's workspace_id
        client = await fetch_one(
            "SELECT id, workspace_id, name FROM clients WHERE id = $1",
            client_id
        )

        if not client:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")

        workspace_id = str(client['workspace_id'])

        # Query all domains for filter counting (before applying filters)
        # Default order: live domains first (by inbox count), then by generation date
        all_domains_query = """
            SELECT
                v.domain_id,
                v.domain_name,
                v.workspace_id,
                v.generated_at,
                v.legitimacy_score,
                v.owned_by_client,
                v.price_checked_at,
                v.cached_price,
                v.selected_provider,
                v.porkbun_price,
                v.porkbun_available,
                v.dynadot_price,
                v.dynadot_available,
                v.purchased_at,
                v.domain_purchase_job_id,
                v.purchase_job_id,
                v.nameservers_updated_at,
                v.nameserver_status,
                v.nameserver_verified_at,
                v.assigned_provider,
                v.detected_provider,
                v.spf_configured,
                v.dkim_configured,
                v.dmarc_configured,
                v.mx_configured,
                v.hypertide_order_job_id,
                v.hypertide_order_status,
                v.hypertide_ordered_at,
                v.synced_inbox_count,
                v.last_inbox_synced_at,
                COALESCE(v.live_inbox_count, v.synced_inbox_count, 0) as live_inbox_count,
                COALESCE(v.dead_inbox_count, 0) as dead_inbox_count,
                COALESCE(v.connected_inbox_count, 0) as connected_inbox_count,
                COALESCE(v.disconnected_inbox_count, 0) as disconnected_inbox_count,
                COALESCE(v.domain_source, 'legacy') as domain_source,
                -- Fulfillment & rotation tracking (migration 060/061)
                COALESCE(v.expected_inbox_count, 0) as expected_inbox_count,
                COALESCE(v.max_inboxes_seen, 0) as max_inboxes_seen,
                COALESCE(v.fulfillment_status, 'pending') as fulfillment_status,
                v.capacity_remaining_pct,
                COALESCE(v.rotation_recommendation, 'not_applicable') as rotation_recommendation,
                -- Enhanced rotation tracking (from migration 062)
                COALESCE(v.recommended_action, 'none') as recommended_action,
                v.burn_breakdown,
                COALESCE(v.inboxes_with_complaints, 0) as inboxes_with_complaints,
                COALESCE(v.inboxes_with_blocks, 0) as inboxes_with_blocks,
                COALESCE(v.has_compromised_inboxes, false) as has_compromised_inboxes,
                -- Oldest disconnection date for live inboxes (for 21-day warning)
                (SELECT MIN(sa.disconnected_at)
                 FROM sender_accounts sa
                 WHERE sa.domain_id = v.domain_id
                   AND sa.inbox_state = 'live'
                   AND sa.status IN ('Not connected', 'Disconnected')
                   AND sa.disconnected_at IS NOT NULL
                ) as oldest_disconnected_at
            FROM v_infrastructure_waterfall v
            WHERE v.workspace_id = $1
            ORDER BY v.live_inbox_count DESC, v.owned_by_client DESC, v.generated_at DESC
        """

        all_rows = await fetch_all(all_domains_query, workspace_id)

        # Transform all domains and calculate filter counts
        all_transformed = [transform_domain(row) for row in all_rows]

        # Calculate filter counts
        # Lifecycle stages:
        # - not_purchased: Need to buy domain
        # - ready: Purchased + DNS ready + no inboxes yet (need to order HyperTide)
        # - complete: Has inboxes from EmailBison (operational)
        filter_counts = {
            'not_purchased': sum(1 for d in all_transformed if not d['is_purchased']),
            'ready': sum(
                1 for d in all_transformed
                if d['is_purchased'] and d['is_ready_for_hyper_tide'] and d['total_inbox_count'] == 0
            ),
            'complete': sum(
                1 for d in all_transformed
                if d['is_purchased'] and d['total_inbox_count'] > 0
            ),
            # Legacy: all purchased domains (for backwards compatibility)
            'purchased': sum(1 for d in all_transformed if d['is_purchased']),
            'over_budget': sum(1 for d in all_transformed if d['is_over_budget']),
            'deactivated': sum(1 for d in all_transformed if d['is_deactivated']),
            'needs_reconnection': sum(
                1 for d in all_transformed
                if d['live_inbox_count'] > 0 and d['connected_inbox_count'] == 0
            ),
            'by_tld': {
                'com': sum(1 for d in all_transformed if d['tld'] == 'com'),
                'co': sum(1 for d in all_transformed if d['tld'] == 'co'),
                'info': sum(1 for d in all_transformed if d['tld'] == 'info'),
            },
            'by_provider': {
                'entra': sum(1 for d in all_transformed if d['assigned_provider'] == 'entra'),
                'google': sum(1 for d in all_transformed if d['assigned_provider'] == 'google'),
                'unassigned': sum(1 for d in all_transformed if not d['assigned_provider']),
            },
            'by_status': {
                'live': sum(1 for d in all_transformed if d['domain_status'] == 'live' and d['total_inbox_count'] > 0),
                'flagged': sum(1 for d in all_transformed if d['domain_status'] == 'flagged'),
                'dead': sum(1 for d in all_transformed if d['domain_status'] == 'dead'),
                'pending': sum(1 for d in all_transformed if d['total_inbox_count'] == 0),
            },
            'by_rotation': {
                'healthy': sum(1 for d in all_transformed if d['rotation_recommendation'] == 'healthy'),
                'monitor': sum(1 for d in all_transformed if d['rotation_recommendation'] == 'monitor'),
                'consider_rotate': sum(1 for d in all_transformed if d['rotation_recommendation'] == 'consider_rotate'),
                'rotate_now': sum(1 for d in all_transformed if d['rotation_recommendation'] == 'rotate_now'),
            },
            'by_fulfillment': {
                'fulfilled': sum(1 for d in all_transformed if d['fulfillment_status'] == 'fulfilled'),
                'over_delivered': sum(1 for d in all_transformed if d['fulfillment_status'] == 'over_delivered'),
                'under_delivered': sum(1 for d in all_transformed if d['fulfillment_status'] == 'under_delivered'),
                'pending': sum(1 for d in all_transformed if d['fulfillment_status'] == 'pending'),
            },
            'by_action': {
                'rotate': sum(1 for d in all_transformed if d['recommended_action'] == 'rotate'),
                'reconnect': sum(1 for d in all_transformed if d['recommended_action'] == 'reconnect'),
                'watch': sum(1 for d in all_transformed if d['recommended_action'] == 'watch'),
                'none': sum(1 for d in all_transformed if d['recommended_action'] == 'none'),
            },
            'compromised': sum(1 for d in all_transformed if d['has_compromised_inboxes']),
        }

        # Apply filters
        filtered_domains = all_transformed

        # Purchase status filter (lifecycle stages)
        if purchase_status == 'not_purchased':
            filtered_domains = [d for d in filtered_domains if not d['is_purchased']]
        elif purchase_status == 'ready':
            # Purchased + DNS ready + no inboxes yet (need to order HyperTide)
            filtered_domains = [
                d for d in filtered_domains
                if d['is_purchased'] and d['is_ready_for_hyper_tide'] and d['total_inbox_count'] == 0
            ]
        elif purchase_status == 'complete':
            # Has inboxes from EmailBison (operational)
            filtered_domains = [
                d for d in filtered_domains
                if d['is_purchased'] and d['total_inbox_count'] > 0
            ]
        elif purchase_status == 'purchased':
            # Legacy: all purchased domains
            filtered_domains = [d for d in filtered_domains if d['is_purchased']]

        # TLD filter
        if tld:
            filtered_domains = [d for d in filtered_domains if d['tld'] == tld]

        # Provider filter
        if provider:
            filtered_domains = [d for d in filtered_domains if d['assigned_provider'] == provider]

        # Status filter
        if status:
            filtered_domains = [d for d in filtered_domains if d['domain_status'] == status]

        # Over budget filter (hide by default)
        if not show_over_budget:
            filtered_domains = [d for d in filtered_domains if not d['is_over_budget']]

        # Deactivated filter (hide by default, but show if explicitly filtering by dead status)
        if not show_deactivated and status != 'dead':
            filtered_domains = [d for d in filtered_domains if not d['is_deactivated']]

        # Needs reconnection filter (show only domains where all live inboxes are disconnected)
        if show_needs_reconnection:
            filtered_domains = [
                d for d in filtered_domains
                if d['live_inbox_count'] > 0 and d['connected_inbox_count'] == 0
            ]

        # Rotation status filter
        if rotation_status == 'needs_attention':
            # Show domains that need attention: monitor, consider_rotate, rotate_now
            filtered_domains = [
                d for d in filtered_domains
                if d['rotation_recommendation'] in ('monitor', 'consider_rotate', 'rotate_now')
            ]
            # Sort by rotation priority: monitor (watchlist) first, then consider_rotate, then rotate_now (critical)
            rotation_priority = {'monitor': 0, 'consider_rotate': 1, 'rotate_now': 2}
            filtered_domains.sort(key=lambda d: (
                rotation_priority.get(d['rotation_recommendation'], 99),
                d['is_over_budget'],
                not d['is_purchased']
            ))
        elif rotation_status == 'healthy':
            # Show only healthy domains
            filtered_domains = [
                d for d in filtered_domains
                if d['rotation_recommendation'] == 'healthy'
            ]
            # Standard sort for healthy domains
            filtered_domains.sort(key=lambda d: (d['is_over_budget'], not d['is_purchased']))
        else:
            # Default sort: over-budget domains at bottom
            filtered_domains.sort(key=lambda d: (d['is_over_budget'], not d['is_purchased']))

        # Get infrastructure summary
        summary = await get_client_infra_summary(client_id)

        return {
            'workspace_id': workspace_id,
            'client_id': client_id,
            'domains': filtered_domains,
            'total_domains': len(filtered_domains),
            'summary': summary,
            'filters': {
                'applied_filters': {
                    'purchase_status': purchase_status or 'all',
                    'tld': tld or 'all',
                    'provider': provider or 'all',
                    'status': status or 'all',
                    'rotation_status': rotation_status or 'all',
                    'show_over_budget': show_over_budget,
                    'show_deactivated': show_deactivated,
                    'show_needs_reconnection': show_needs_reconnection,
                },
                'counts': filter_counts,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching waterfall data for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/waterfall/workspace/{workspace_id}")
async def get_waterfall_by_workspace(
    workspace_id: str,
    # Lifecycle stages: not_purchased → ready → complete (+ legacy 'purchased')
    purchase_status: Optional[str] = Query(None, regex="^(all|not_purchased|ready|complete|purchased)$"),
    tld: Optional[str] = Query(None, regex="^(com|co|info)$"),
    provider: Optional[str] = Query(None, regex="^(entra|google)$"),
    status: Optional[str] = Query(None, regex="^(live|flagged|dead)$"),
    rotation_status: Optional[str] = Query(None, regex="^(all|needs_attention|healthy)$"),
    show_over_budget: bool = Query(False),
    show_deactivated: bool = Query(False),
    show_needs_reconnection: bool = Query(False),
):
    """
    Get complete waterfall view for workspace (direct workspace query).
    """
    try:
        # Find client for this workspace
        client = await fetch_one(
            "SELECT id, name FROM clients WHERE workspace_id = $1",
            workspace_id
        )

        client_id = str(client['id']) if client else None

        # Reuse the client endpoint logic
        if client_id:
            return await get_waterfall_by_client(
                client_id=client_id,
                purchase_status=purchase_status,
                tld=tld,
                provider=provider,
                status=status,
                rotation_status=rotation_status,
                show_over_budget=show_over_budget,
                show_deactivated=show_deactivated,
                show_needs_reconnection=show_needs_reconnection,
            )

        raise HTTPException(status_code=404, detail=f"No client found for workspace {workspace_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching waterfall data for workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-purchase")
async def bulk_purchase(
    request: BulkPurchaseRequest,
    registrar: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(rate_limit(RateLimitConfig(requests=10, window_seconds=60))),
):
    """
    Bulk purchase multiple domains.
    Creates a domain_purchase_job and returns job ID.
    The hypertide_worker will pick up and process the job.

    SECURITY:
    - Requires authenticated user (X-User-Email header)
    - Rate limited to 10 requests per minute per user
    """
    # Security: Require authenticated user for purchase operations
    if not user.email:
        raise HTTPException(status_code=401, detail="Authentication required for domain purchases")

    job_id = str(uuid.uuid4())

    try:
        # Get domain names from IDs
        domains = await fetch_all(
            """
            SELECT id, domain_name,
                   COALESCE(porkbun_price, 999) as porkbun_price,
                   COALESCE(dynadot_price, 999) as dynadot_price
            FROM domains
            WHERE id = ANY($1::uuid[])
            """,
            request.domain_ids
        )

        if not domains:
            raise HTTPException(status_code=404, detail="No domains found")

        domain_names = [d['domain_name'] for d in domains]

        # Determine registrar: use specified, or pick cheapest per domain
        # For simplicity, pick the registrar with best overall price
        if not registrar:
            porkbun_total = sum(d['porkbun_price'] for d in domains)
            dynadot_total = sum(d['dynadot_price'] for d in domains)
            registrar = 'porkbun' if porkbun_total <= dynadot_total else 'dynadot'

        # Get client info
        client = await fetch_one(
            """
            SELECT c.id, c.workspace_id
            FROM domains d
            JOIN clients c ON c.workspace_id = d.workspace_id
            WHERE d.id = $1
            """,
            request.domain_ids[0]
        )

        if not client:
            raise HTTPException(status_code=404, detail="Client not found for domains")

        # Create domain_purchase_jobs record
        await execute(
            """
            INSERT INTO domain_purchase_jobs (
                id,
                client_id,
                workspace_id,
                domain_ids,
                domain_names,
                registrar,
                status,
                created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW())
            """,
            job_id,
            str(client['id']),
            str(client['workspace_id']),
            request.domain_ids,
            domain_names,
            registrar,
        )

        # Update domains with job reference
        # Note: Using job_id (no FK constraint) for domain purchases
        # purchase_job_id is reserved for inbox purchases (FK to inbox_purchase_jobs)
        await execute(
            """
            UPDATE domains
            SET job_id = $1,
                purchase_job_status = 'pending',
                updated_at = NOW()
            WHERE id = ANY($2::uuid[])
            """,
            job_id,
            request.domain_ids,
        )

        logger.info(f"Purchase job {job_id} created for {len(request.domain_ids)} domains via {registrar}")

        # Log activity for audit trail
        await log_activity(
            user=user,
            action="domain_purchase_initiated",
            resource_type="domain_purchase_job",
            resource_id=job_id,
            details={
                "domain_count": len(request.domain_ids),
                "domain_names": domain_names,
                "registrar": registrar,
                "client_id": str(client['id']),
            }
        )

        return {
            "job_id": job_id,
            "total_domains": len(request.domain_ids),
            "registrar": registrar,
            "status": "pending",
            "message": f"Purchase job created for {len(request.domain_ids)} domains via {registrar}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating purchase job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/purchase-job/{job_id}")
async def get_purchase_job_status(job_id: str):
    """
    Get the status of a domain purchase job.
    Used by frontend to poll for completion and show results.
    """
    try:
        job = await fetch_one(
            """
            SELECT
                id,
                status,
                registrar,
                successful_count,
                failed_count,
                total_cost,
                results,
                error_message,
                created_at,
                started_at,
                completed_at
            FROM domain_purchase_jobs
            WHERE id = $1
            """,
            job_id
        )

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "jobId": str(job["id"]),
            "status": job["status"],
            "registrar": job["registrar"],
            "successfulCount": job["successful_count"] or 0,
            "failedCount": job["failed_count"] or 0,
            "totalCost": float(job["total_cost"]) if job["total_cost"] else 0,
            "results": job["results"],
            "errorMessage": job["error_message"],
            "createdAt": job["created_at"].isoformat() if job["created_at"] else None,
            "startedAt": job["started_at"].isoformat() if job["started_at"] else None,
            "completedAt": job["completed_at"].isoformat() if job["completed_at"] else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching purchase job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hypertide-order")
async def create_hypertide_order(
    request: HyperTideOrderRequest,
    user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(rate_limit(RateLimitConfig(requests=5, window_seconds=60))),
):
    """
    Create HyperTide order for specified domains.
    Auto-validates domain count matches provider requirements.

    Entra: 2 domains per order
    Google: 5 domains per order

    SECURITY:
    - Requires authenticated user (X-User-Email header)
    - Rate limited to 5 requests per minute per user
    """
    # Security: Require authenticated user for HyperTide orders
    if not user.email:
        raise HTTPException(status_code=401, detail="Authentication required for HyperTide orders")

    domains_per_order = 2 if request.provider == 'entra' else 5
    expected_domains = request.order_count * domains_per_order

    if len(request.domain_ids) != expected_domains:
        raise HTTPException(
            status_code=400,
            detail=f"Expected {expected_domains} domains for {request.order_count} {request.provider} orders, got {len(request.domain_ids)}"
        )

    job_id = str(uuid.uuid4())

    try:
        # Fetch domain names for the Slack specification
        domain_rows = await fetch_all(
            "SELECT domain_name FROM domains WHERE id = ANY($1::uuid[])",
            request.domain_ids
        )
        domain_names = [row['domain_name'] for row in domain_rows]

        # Create inbox_purchase_job record
        inboxes_per_domain = 50 if request.provider == 'entra' else 3
        total_inboxes = len(request.domain_ids) * inboxes_per_domain

        await execute(
            """
            INSERT INTO inbox_purchase_jobs (
                id,
                client_id,
                workspace_id,
                status,
                provider_type,
                domain_ids,
                domain_names,
                orders_total,
                total_inboxes,
                monthly_cost,
                worker_mode
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            job_id,
            request.client_id,
            request.workspace_id,
            'pending',
            request.provider,
            request.domain_ids,
            domain_names,
            request.order_count,
            total_inboxes,
            request.order_count * 50,  # $50 per order
            'api',  # Use 'api' mode for automated Hypertide REST API orders
        )

        # Update domains with job reference
        await execute(
            """
            UPDATE domains
            SET
                infrastructure_type = $1,
                purchase_job_id = $2,
                updated_at = NOW()
            WHERE id = ANY($3::uuid[])
            """,
            request.provider,
            job_id,
            request.domain_ids,
        )

        logger.info(
            f"HyperTide order {job_id} created: {request.order_count} {request.provider} orders, "
            f"{len(request.domain_ids)} domains, {total_inboxes} inboxes"
        )

        # Log activity for audit trail
        await log_activity(
            user=user,
            action="hypertide_order_created",
            resource_type="inbox_purchase_job",
            resource_id=job_id,
            details={
                "provider": request.provider,
                "order_count": request.order_count,
                "domain_count": len(request.domain_ids),
                "domain_names": domain_names,
                "total_inboxes": total_inboxes,
                "monthly_cost": request.order_count * 50,
                "client_id": request.client_id,
            }
        )

        return {
            "job_id": job_id,
            "total_orders": request.order_count,
            "total_domains": len(request.domain_ids),
            "total_inboxes": total_inboxes,
            "status": "pending",
            "estimated_duration_seconds": request.order_count * 7200,
            "message": f"HyperTide order submitted: {request.order_count} {request.provider} orders"
        }

    except Exception as e:
        logger.error(f"Error creating HyperTide order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class HyperTideTestOrderRequest(BaseModel):
    client_id: str
    workspace_id: str
    provider: str  # entra | google
    domain_ids: List[str]
    dry_run: bool = True  # Always true for test endpoint


class HyperTideTestOrderResponse(BaseModel):
    is_valid: bool
    validation_errors: List[str]
    order_preview: Dict[str, Any]
    hypertide_response: Optional[Dict[str, Any]] = None


@router.post("/hypertide-order/test", response_model=HyperTideTestOrderResponse)
async def test_hypertide_order(request: HyperTideTestOrderRequest):
    """
    Test HyperTide order submission without charging.

    Validates all required parameters and builds the order payload.
    Does NOT actually create the order or charge any payment.

    Returns validation errors if any, plus a preview of what would be sent.
    """
    validation_errors = []

    # Validate provider
    if request.provider not in ('entra', 'google'):
        validation_errors.append(f"Invalid provider: {request.provider}. Must be 'entra' or 'google'")

    # Validate domain count
    domains_per_order = 2 if request.provider == 'entra' else 5
    if len(request.domain_ids) == 0:
        validation_errors.append("No domains provided")
    elif len(request.domain_ids) % domains_per_order != 0:
        validation_errors.append(
            f"{request.provider.title()} requires {domains_per_order} domains per order, "
            f"got {len(request.domain_ids)} (not divisible by {domains_per_order})"
        )

    # Get domain names
    domains = await fetch_all(
        "SELECT id, domain_name, nameserver_status FROM domains WHERE id = ANY($1::uuid[])",
        request.domain_ids
    )
    domain_names = [d['domain_name'] for d in domains]

    # Validate all domains exist
    if len(domains) != len(request.domain_ids):
        found_ids = {str(d['id']) for d in domains}
        missing = [did for did in request.domain_ids if did not in found_ids]
        validation_errors.append(f"Domains not found: {missing}")

    # Validate DNS status
    domains_not_verified = [d['domain_name'] for d in domains if d.get('nameserver_status') != 'verified']
    if domains_not_verified:
        validation_errors.append(f"Domains with unverified DNS: {domains_not_verified}")

    # Get client info
    client = await fetch_one("""
        SELECT c.id, c.name, c.onboarding_data, w.workspace_name
        FROM clients c
        JOIN workspaces w ON c.workspace_id = w.id
        WHERE c.id = $1
    """, request.client_id)

    if not client:
        validation_errors.append(f"Client {request.client_id} not found")
        return HyperTideTestOrderResponse(
            is_valid=False,
            validation_errors=validation_errors,
            order_preview={},
        )

    # Extract onboarding data (may be JSON string or dict)
    onboarding_raw = client.get('onboarding_data') or {}
    if isinstance(onboarding_raw, str):
        try:
            onboarding = json.loads(onboarding_raw)
        except json.JSONDecodeError:
            onboarding = {}
    else:
        onboarding = onboarding_raw
    forwarding_domain = onboarding.get('primaryDomain', '')

    if not forwarding_domain:
        validation_errors.append("Client has no primaryDomain in onboarding_data")

    # Get sender names
    sender_names = onboarding.get('baseSenderNames', [])
    users = []
    if sender_names:
        users = [
            {"first_name": n.get('firstName', ''), "last_name": n.get('lastName', '')}
            for n in sender_names[:10]  # HyperTide max 10 users
            if n.get('firstName') and n.get('lastName')
        ]

    if not users:
        validation_errors.append("Client has no sender names configured (baseSenderNames in onboarding_data)")

    # Build order preview
    order_preview = {
        "plan": request.provider,
        "domains": domain_names,
        "domain_option": "i_have_my_own_domains",
        "forwarding_domain": forwarding_domain,
        "client_name": client['name'],
        "selected_tool": "bison",
        "tool_credentials": {
            "bison_url": "https://spellcast.hirecharm.com",
            "username": "***REDACTED***",
            "password": "***REDACTED***",
            "workspace": client['workspace_name'],
        },
        "users": users,
        "warmup_setup": {
            "enabled": True,
            "settings": {
                "warmup_limit": 5,
                "warmup_reply_rate": 100,
                "warmup_increment": 1,
            }
        },
        # Calculated values
        "_calculated": {
            "order_count": len(request.domain_ids) // domains_per_order if request.provider in ('entra', 'google') else 0,
            "inboxes_per_order": 100 if request.provider == 'entra' else 15,
            "total_inboxes": (len(request.domain_ids) // domains_per_order) * (100 if request.provider == 'entra' else 15),
            "monthly_cost": (len(request.domain_ids) // domains_per_order) * 50,
        }
    }

    is_valid = len(validation_errors) == 0

    logger.info(
        f"HyperTide test order: valid={is_valid}, provider={request.provider}, "
        f"domains={len(request.domain_ids)}, errors={validation_errors}"
    )

    return HyperTideTestOrderResponse(
        is_valid=is_valid,
        validation_errors=validation_errors,
        order_preview=order_preview,
    )


@router.post("/verify-dns/{domain_id}")
async def verify_dns(domain_id: str):
    """
    Verify DNS configuration for a single domain.
    Checks nameservers match DNSimple.
    """
    # TODO: Implement actual DNS verification
    logger.info(f"DNS verification requested for domain {domain_id}")

    return {
        "domain_id": domain_id,
        "status": "pending",
        "message": "DNS verification started"
    }


@router.post("/fix-dns/{domain_id}")
async def fix_dns(domain_id: str):
    """
    Fix DNS configuration for a single domain.
    Sets nameservers to DNSimple via registrar API.
    """
    # TODO: Implement actual DNS fix via registrar API
    logger.info(f"DNS fix requested for domain {domain_id}")

    return {
        "domain_id": domain_id,
        "status": "pending",
        "message": "DNS fix started"
    }


class BulkPriceCheckRequest(BaseModel):
    workspace_id: str
    max_domains: int = 50  # Limit to prevent timeout


class BulkPriceCheckResponse(BaseModel):
    checked: int
    available: int
    unavailable: int
    errors: int
    domains: List[Dict[str, Any]]


@router.post("/bulk-price-check", response_model=BulkPriceCheckResponse)
async def bulk_check_prices(request: BulkPriceCheckRequest):
    """
    Check prices for all unpriced domains in a workspace.

    Two-phase approach for better UX:
    1. Dynadot first (fast, no rate limits) - updates DB immediately
    2. Porkbun second (rate limited) - updates DB as each completes

    Frontend can refresh to see Dynadot prices while Porkbun loads.
    """
    from services.porkbun import PorkbunService
    from services.dynadot import DynadotService

    # Get domains missing Dynadot pricing first
    domains_need_dynadot = await fetch_all("""
        SELECT id, domain_name
        FROM domains
        WHERE workspace_id = $1
        AND dynadot_price IS NULL
        AND approval_status IN ('available', 'pending')
        ORDER BY created_at DESC
        LIMIT $2
    """, request.workspace_id, request.max_domains)

    # Get domains missing Porkbun pricing
    domains_need_porkbun = await fetch_all("""
        SELECT id, domain_name
        FROM domains
        WHERE workspace_id = $1
        AND porkbun_price IS NULL
        AND approval_status IN ('available', 'pending')
        ORDER BY created_at DESC
        LIMIT $2
    """, request.workspace_id, request.max_domains)

    if not domains_need_dynadot and not domains_need_porkbun:
        return BulkPriceCheckResponse(
            checked=0, available=0, unavailable=0, errors=0, domains=[]
        )

    logger.info(f"Bulk price check: {len(domains_need_dynadot)} need Dynadot, {len(domains_need_porkbun)} need Porkbun")

    dynadot = DynadotService()
    porkbun = PorkbunService()

    checked = 0
    available = 0
    unavailable = 0
    errors = 0
    results = []

    # PHASE 1: Dynadot (fast, no rate limits)
    logger.info("Phase 1: Checking Dynadot prices...")
    for domain in domains_need_dynadot:
        domain_id = domain["id"]
        domain_name = domain["domain_name"]

        try:
            result = await dynadot.check_availability(domain_name)
            dynadot_available = result.available
            dynadot_price = float(result.price) if result.available and result.price else None

            # Update Dynadot columns only
            await execute("""
                UPDATE domains SET
                    dynadot_price = $2,
                    dynadot_available = $3,
                    price_checked_at = COALESCE(price_checked_at, NOW()),
                    updated_at = NOW()
                WHERE id = $1
            """, domain_id, dynadot_price, dynadot_available)

            checked += 1
            if dynadot_available:
                available += 1
            else:
                unavailable += 1

            results.append({
                "domain_name": domain_name,
                "dynadot_price": dynadot_price,
                "dynadot_available": dynadot_available,
                "phase": "dynadot",
            })

        except Exception as e:
            logger.warning(f"Dynadot check failed for {domain_name}: {e}")
            errors += 1

    logger.info(f"Phase 1 complete: {checked} Dynadot checks done")

    # PHASE 2: Porkbun (rate limited - 1 per 10 seconds)
    logger.info("Phase 2: Checking Porkbun prices...")
    porkbun_checked = 0
    for domain in domains_need_porkbun:
        domain_id = domain["id"]
        domain_name = domain["domain_name"]

        try:
            result = await porkbun.check_availability(domain_name)
            porkbun_available = result.available
            porkbun_price = float(result.price) if result.available and result.price else None

            # Update Porkbun columns only
            await execute("""
                UPDATE domains SET
                    porkbun_price = $2,
                    porkbun_available = $3,
                    price_checked_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
            """, domain_id, porkbun_price, porkbun_available)

            porkbun_checked += 1
            results.append({
                "domain_name": domain_name,
                "porkbun_price": porkbun_price,
                "porkbun_available": porkbun_available,
                "phase": "porkbun",
            })

        except Exception as e:
            logger.warning(f"Porkbun check failed for {domain_name}: {e}")
            errors += 1

    logger.info(f"Phase 2 complete: {porkbun_checked} Porkbun checks done")
    logger.info(f"Bulk price check complete: {checked + porkbun_checked} total, {errors} errors")

    return BulkPriceCheckResponse(
        checked=checked,
        available=available,
        unavailable=unavailable,
        errors=errors,
        domains=results,
    )


@router.get("/sender-names/client/{client_id}")
async def get_sender_names_by_client(client_id: str):
    """
    Get sender names for a client (reads from clients.onboarding_data).
    """
    try:
        client = await fetch_one(
            """
            SELECT id, onboarding_data, workspace_id
            FROM clients
            WHERE id = $1
            """,
            client_id
        )

        if not client:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")

        onboarding_data = client.get('onboarding_data')
        if isinstance(onboarding_data, str):
            onboarding_data = json.loads(onboarding_data)
        elif onboarding_data is None:
            onboarding_data = {}

        base_names = onboarding_data.get('baseSenderNames', [])

        # Transform to consistent format
        sender_names = [
            {
                "id": f"name-{i}",
                "firstName": name.get('firstName', ''),
                "lastName": name.get('lastName', ''),
                "fullName": f"{name.get('firstName', '')} {name.get('lastName', '')}".strip(),
                "isFounder": name.get('isFounder', i == 0),
            }
            for i, name in enumerate(base_names)
        ]

        return {
            "clientId": str(client['id']),
            "workspaceId": str(client['workspace_id']) if client.get('workspace_id') else None,
            "senderNames": sender_names
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching sender names for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# SIMPLE DOMAIN GENERATION (Fallback - no HyperTide required)
# ============================================

class SimpleGenerateRequest(BaseModel):
    client_id: str
    count: int = 10

class GeneratedDomain(BaseModel):
    id: str
    domain_name: str
    legitimacy_score: float

class SimpleGenerateResponse(BaseModel):
    generated: List[GeneratedDomain]
    message: str

# Common domain patterns for B2B email outreach
DOMAIN_PREFIXES = [
    "get", "try", "use", "go", "meet", "join", "hello", "with",
    "scale", "grow", "boost", "reach", "connect"
]
DOMAIN_SUFFIXES = [
    "hq", "app", "io", "now", "team", "mail", "send", "co"
]

def generate_domain_patterns(brand: str, count: int = 10) -> List[Dict[str, Any]]:
    """Generate domain name candidates using simple pattern matching."""
    import random

    candidates = []
    brand_clean = brand.lower().replace(" ", "").replace("-", "").replace(".", "")

    # Pattern 1: prefix + brand (e.g., getselery.com)
    for prefix in DOMAIN_PREFIXES:
        candidates.append({
            "name": f"{prefix}{brand_clean}.com",
            "score": 0.85,
            "pattern": "prefix"
        })

    # Pattern 2: brand + suffix (e.g., seleryhq.com)
    for suffix in DOMAIN_SUFFIXES:
        candidates.append({
            "name": f"{brand_clean}{suffix}.com",
            "score": 0.82,
            "pattern": "suffix"
        })

    # Pattern 3: action + with + brand (e.g., growwithselery.com)
    action_words = ["grow", "scale", "connect", "work", "build", "ship"]
    for action in action_words:
        candidates.append({
            "name": f"{action}with{brand_clean}.com",
            "score": 0.80,
            "pattern": "action_with"
        })

    # Pattern 4: brand + action (e.g., selerygrow.com)
    for action in ["growth", "leads", "reach", "connect", "send"]:
        candidates.append({
            "name": f"{brand_clean}{action}.com",
            "score": 0.78,
            "pattern": "brand_action"
        })

    # Shuffle and limit
    random.shuffle(candidates)
    return candidates[:count]


@router.post("/generate-domains/simple", response_model=SimpleGenerateResponse)
async def simple_generate_domains(request: SimpleGenerateRequest):
    """
    Simple domain generation without HyperTide module.
    Uses pattern-based generation from client brand name.

    This is a fallback when the full HyperTide automation module is unavailable.
    """
    try:
        # Get client info
        client = await fetch_one("""
            SELECT c.id, c.name, c.workspace_id, c.onboarding_data
            FROM clients c WHERE c.id = $1
        """, request.client_id)

        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        if not client.get('workspace_id'):
            raise HTTPException(status_code=400, detail="Client not linked to a workspace")

        workspace_id = client['workspace_id']
        brand_name = client['name']

        # Parse onboarding for additional keywords
        onboarding = client.get('onboarding_data') or {}
        if isinstance(onboarding, str):
            try:
                onboarding = json.loads(onboarding)
            except:
                onboarding = {}

        # Generate candidates using patterns
        candidates = generate_domain_patterns(brand_name, request.count * 3)

        # Filter out existing domains
        existing = await fetch_all("""
            SELECT domain_name FROM domains
            WHERE workspace_id = $1
        """, workspace_id)
        existing_names = {d['domain_name'].lower() for d in existing}

        new_domains = []
        for candidate in candidates:
            if len(new_domains) >= request.count:
                break
            if candidate['name'].lower() in existing_names:
                continue

            # Insert into database
            try:
                result = await fetch_one("""
                    INSERT INTO domains (
                        workspace_id, domain_name, legitimacy_score,
                        approval_status, domain_source, notes, rationale
                    )
                    VALUES ($1, $2, $3, 'available', 'generated', $4, $5)
                    RETURNING id, domain_name, legitimacy_score
                """,
                    workspace_id,
                    candidate['name'],
                    candidate['score'],
                    f"Simple pattern: {candidate['pattern']}",
                    f"Generated using {candidate['pattern']} pattern for {brand_name}"
                )

                if result:
                    new_domains.append(GeneratedDomain(
                        id=str(result['id']),
                        domain_name=result['domain_name'],
                        legitimacy_score=result['legitimacy_score'] or candidate['score']
                    ))
                    existing_names.add(candidate['name'].lower())

            except Exception as e:
                logger.warning(f"Failed to insert domain {candidate['name']}: {e}")
                continue

        return SimpleGenerateResponse(
            generated=new_domains,
            message=f"Generated {len(new_domains)} domain candidates for {brand_name}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simple domain generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# DOMAIN A/B SET ALLOCATION
# ============================================

class DomainSetSummary(BaseModel):
    workspace_id: str
    workspace_name: str
    a_set_domains: int
    b_set_domains: int
    burned_domains: int
    unassigned_domains: int
    a_set_connected_inboxes: int
    b_set_connected_inboxes: int
    reserve_status: str


class DomainSetDetail(BaseModel):
    domain_id: str
    domain_name: str
    pool_status: str
    live_inboxes: int
    connected_inboxes: int
    dead_inboxes: int
    domain_health: str
    provider: Optional[str]


@router.get("/domain-sets", response_model=List[DomainSetSummary])
async def get_domain_sets():
    """
    Get domain A/B set summary for all workspaces.
    Shows allocation status and reserve health.
    """
    rows = await fetch_all("""
        SELECT * FROM v_workspace_domain_sets
        ORDER BY workspace_name
    """)

    return [DomainSetSummary(
        workspace_id=str(row['workspace_id']),
        workspace_name=row['workspace_name'],
        a_set_domains=row['a_set_domains'] or 0,
        b_set_domains=row['b_set_domains'] or 0,
        burned_domains=row['burned_domains'] or 0,
        unassigned_domains=row['unassigned_domains'] or 0,
        a_set_connected_inboxes=row['a_set_connected_inboxes'] or 0,
        b_set_connected_inboxes=row['b_set_connected_inboxes'] or 0,
        reserve_status=row['reserve_status'] or 'unknown'
    ) for row in rows]


@router.get("/domain-sets/{workspace_id}", response_model=List[DomainSetDetail])
async def get_workspace_domain_sets(workspace_id: str):
    """
    Get detailed domain set allocation for a specific workspace.
    """
    rows = await fetch_all("""
        SELECT * FROM v_domain_sets
        WHERE workspace_id = $1
        ORDER BY pool_status, domain_name
    """, uuid.UUID(workspace_id))

    return [DomainSetDetail(
        domain_id=str(row['domain_id']),
        domain_name=row['domain_name'],
        pool_status=row['pool_status'] or 'unassigned',
        live_inboxes=row['live_inboxes'] or 0,
        connected_inboxes=row['connected_inboxes'] or 0,
        dead_inboxes=row['dead_inboxes'] or 0,
        domain_health=row['domain_health'] or 'unknown',
        provider=row['provider']
    ) for row in rows]


@router.post("/domain-sets/{workspace_id}/allocate")
async def allocate_domain_sets(
    workspace_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Allocate unassigned domains to A-Set and B-Set.
    Half go to A-Set (deployed), half to B-Set (reserve).
    """
    try:
        # Call the allocation function
        results = await fetch_all("""
            SELECT * FROM allocate_domain_sets($1)
        """, uuid.UUID(workspace_id))

        allocated = [
            {
                "domain_id": str(r['domain_id']),
                "domain_name": r['domain_name'],
                "new_status": r['new_status'],
                "action": r['action']
            }
            for r in results
        ]

        # Log activity
        await log_activity(
            user_id=current_user.id if current_user else None,
            action="allocate_domain_sets",
            resource_type="workspace",
            resource_id=workspace_id,
            details={"allocated_count": len(allocated)}
        )

        return {
            "success": True,
            "allocated": allocated,
            "message": f"Allocated {len(allocated)} domains to A/B sets"
        }

    except Exception as e:
        logger.error(f"Domain set allocation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# DOMAIN ENGINE V2 - PIPELINE & RUNWAY
# ============================================

class PipelineDomain(BaseModel):
    """Domain in the lifecycle pipeline"""
    domain_id: str
    domain_name: str
    provider: Optional[str]  # microsoft (entra) or google
    pipeline_status: str  # incubating | reserve | live | burned
    pool_status: str  # unassigned | reserve | live | burned
    inbox_count: int
    connected_count: int
    max_inbox_count: int  # 50 for Entra, 3 for Google
    warmup_age_days: Optional[int]
    warmup_days_required: int  # 14 for Entra, 7 for Google
    warmup_percent: int  # 0-100
    ready_in_days: int  # Days until ready for reserve
    warmup_complete: bool
    daily_capacity: int
    purchased_at: Optional[str]
    promoted_at: Optional[str]
    burned_at: Optional[str]
    burn_trigger: Optional[str]


class PipelineSummary(BaseModel):
    """Summary counts by pipeline stage"""
    incubating_count: int
    reserve_count: int
    live_count: int
    burned_count: int
    incubating_entra: int
    incubating_google: int
    reserve_entra: int
    reserve_google: int
    live_entra: int
    live_google: int


class PipelineResponse(BaseModel):
    """Full pipeline response for a client"""
    client_id: str
    summary: PipelineSummary
    incubating: List[PipelineDomain]
    reserve: List[PipelineDomain]
    live: List[PipelineDomain]


class RunwayMetrics(BaseModel):
    """Reserve runway metrics for a provider"""
    provider: str
    live_count: int
    reserve_count: int
    burned_count: int
    unassigned_count: int
    monthly_burn_rate: float
    runway_months: float
    runway_healthy: bool
    domain_kill_cascade_pct: int  # 30% for Entra, 7% for Google
    total_allocated: int
    live_percent: int
    reserve_percent: int
    live_gap_to_target: int  # How many more live domains needed for 80/20


class AllocationMetrics(BaseModel):
    """80/20 allocation compliance"""
    total_live: int
    total_reserve: int
    target_live: int  # 80% of total
    target_reserve: int  # 20% of total
    live_percent: int
    reserve_percent: int
    in_balance: bool  # True if within tolerance of 80/20


class RunwayResponse(BaseModel):
    """Full runway response for a client"""
    client_id: str
    entra: Optional[RunwayMetrics]
    google: Optional[RunwayMetrics]
    allocation: AllocationMetrics


# ============================================
# CAPACITY HARMONY MODELS
# ============================================

class ProviderCapacityHarmony(BaseModel):
    """Capacity harmony metrics for a single provider"""
    provider: str
    # Capacity gap
    capacity_required: int  # From client subscription (target inboxes)
    capacity_actual: int  # Connected inboxes from live domains
    gap: int  # How many inboxes below target
    domain_gap: int  # How many domains needed
    # Domain pipeline counts
    live: int
    reserve: int
    incubating: int
    burned: int
    # Runway metrics
    monthly_burn_rate: float
    runway_months: float
    exhaustion_date: Optional[str]  # When reserve runs out
    runway_healthy: bool
    # HyperTide in-flight
    pending_orders: int
    provisioning: int


class CapacityHarmonyResponse(BaseModel):
    """
    Capacity Harmony - Gap analysis and purchase recommendations.

    Answers the question: How many domains should we buy to maintain capacity?

    GAP = CAPACITY_REQUIRED - CAPACITY_ACTUAL
    RUNWAY = reserve_domains / monthly_domain_burn_rate
    """
    client_id: str
    client_name: str
    entra: ProviderCapacityHarmony
    google: ProviderCapacityHarmony
    # Totals
    total_gap: int  # Total inbox gap across providers
    total_domain_gap: int  # Total domains needed
    purchase_recommendation: int  # Domains to buy (considering pipeline)
    estimated_cost: float  # Based on avg $10/domain
    # Overall runway
    runway_exhaustion_date: Optional[str]  # Earliest exhaustion across providers
    runway_healthy: bool  # Both providers healthy


@router.get("/pipeline/{client_id}", response_model=PipelineResponse)
async def get_client_pipeline(client_id: str):
    """
    Get domain lifecycle pipeline for a client.
    Shows incubating, reserve, and live domains with warmup progress.

    Pipeline stages:
    - INCUBATING: Purchased + has inboxes + warming < 14 days
    - RESERVE: pool_status = 'reserve' (warmed B-Set, ready to deploy)
    - LIVE: pool_status = 'live' (A-Set, actively sending)
    """
    try:
        # Get pipeline summary using the function
        summary_row = await fetch_one("""
            SELECT * FROM get_pipeline_summary($1)
        """, uuid.UUID(client_id))

        summary = PipelineSummary(
            incubating_count=summary_row['incubating_count'] if summary_row else 0,
            reserve_count=summary_row['reserve_count'] if summary_row else 0,
            live_count=summary_row['live_count'] if summary_row else 0,
            burned_count=summary_row['burned_count'] if summary_row else 0,
            incubating_entra=summary_row['incubating_entra'] if summary_row else 0,
            incubating_google=summary_row['incubating_google'] if summary_row else 0,
            reserve_entra=summary_row['reserve_entra'] if summary_row else 0,
            reserve_google=summary_row['reserve_google'] if summary_row else 0,
            live_entra=summary_row['live_entra'] if summary_row else 0,
            live_google=summary_row['live_google'] if summary_row else 0,
        )

        # Get domain details from the view
        rows = await fetch_all("""
            SELECT
                domain_id, domain_name, provider, pipeline_status, pool_status,
                inbox_count, connected_count, max_inbox_count,
                warmup_age_days, warmup_days_required, warmup_percent,
                ready_in_days, warmup_complete, daily_capacity,
                purchased_at, promoted_at, burned_at, burn_trigger
            FROM v_domain_pipeline
            WHERE client_id = $1
            ORDER BY
                CASE pipeline_status
                    WHEN 'incubating' THEN 1
                    WHEN 'reserve' THEN 2
                    WHEN 'live' THEN 3
                    ELSE 4
                END,
                warmup_percent DESC
        """, uuid.UUID(client_id))

        def row_to_domain(row) -> PipelineDomain:
            return PipelineDomain(
                domain_id=str(row['domain_id']),
                domain_name=row['domain_name'],
                provider=row['provider'],
                pipeline_status=row['pipeline_status'] or 'unknown',
                pool_status=row['pool_status'] or 'unassigned',
                inbox_count=row['inbox_count'] or 0,
                connected_count=row['connected_count'] or 0,
                max_inbox_count=row['max_inbox_count'] or 50,
                warmup_age_days=row['warmup_age_days'],
                warmup_days_required=row['warmup_days_required'] or 14,
                warmup_percent=row['warmup_percent'] or 0,
                ready_in_days=row['ready_in_days'] or 14,
                warmup_complete=row['warmup_complete'] or False,
                daily_capacity=row['daily_capacity'] or 0,
                purchased_at=row['purchased_at'].isoformat() if row['purchased_at'] else None,
                promoted_at=row['promoted_at'].isoformat() if row['promoted_at'] else None,
                burned_at=row['burned_at'].isoformat() if row['burned_at'] else None,
                burn_trigger=row['burn_trigger'],
            )

        incubating = [row_to_domain(r) for r in rows if r['pipeline_status'] == 'incubating']
        reserve = [row_to_domain(r) for r in rows if r['pipeline_status'] == 'reserve']
        live = [row_to_domain(r) for r in rows if r['pipeline_status'] == 'live']

        return PipelineResponse(
            client_id=client_id,
            summary=summary,
            incubating=incubating,
            reserve=reserve,
            live=live,
        )

    except Exception as e:
        logger.error(f"Failed to get pipeline for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runway/{client_id}", response_model=RunwayResponse)
async def get_client_runway(client_id: str):
    """
    Get reserve runway metrics for a client.
    Shows how long reserve pools will last based on historical burn rates.

    Key metrics:
    - runway_months: How long until reserve is depleted
    - monthly_burn_rate: Average domains burned per month (90-day window)
    - 80/20 allocation: Live vs Reserve distribution
    """
    try:
        # Get runway metrics per provider
        rows = await fetch_all("""
            SELECT * FROM v_domain_runway
            WHERE client_id = $1
        """, uuid.UUID(client_id))

        entra_metrics = None
        google_metrics = None
        total_live = 0
        total_reserve = 0

        for row in rows:
            provider = row['provider']
            # Skip rows with no provider (shouldn't happen but handle gracefully)
            if not provider:
                continue
            metrics = RunwayMetrics(
                provider=provider,
                live_count=row['live_count'] or 0,
                reserve_count=row['reserve_count'] or 0,
                burned_count=row['burned_count'] or 0,
                unassigned_count=row['unassigned_count'] or 0,
                monthly_burn_rate=float(row['monthly_burn_rate'] or 0),
                runway_months=float(row['runway_months'] or 0),
                runway_healthy=row['runway_healthy'] or False,
                domain_kill_cascade_pct=row['domain_kill_cascade_pct'] or 30,
                total_allocated=row['total_allocated'] or 0,
                live_percent=row['live_percent'] or 0,
                reserve_percent=row['reserve_percent'] or 0,
                live_gap_to_target=row['live_gap_to_target'] or 0,
            )

            if provider == 'microsoft':
                entra_metrics = metrics
            elif provider == 'google':
                google_metrics = metrics

            total_live += metrics.live_count
            total_reserve += metrics.reserve_count

        # Calculate overall allocation metrics
        total = total_live + total_reserve
        target_live = int(total * 0.8) if total > 0 else 0
        target_reserve = total - target_live if total > 0 else 0
        live_pct = int(total_live / total * 100) if total > 0 else 0
        reserve_pct = 100 - live_pct if total > 0 else 0

        # Within balance if live is between 75-85%
        in_balance = 75 <= live_pct <= 85 if total > 0 else True

        allocation = AllocationMetrics(
            total_live=total_live,
            total_reserve=total_reserve,
            target_live=target_live,
            target_reserve=target_reserve,
            live_percent=live_pct,
            reserve_percent=reserve_pct,
            in_balance=in_balance,
        )

        return RunwayResponse(
            client_id=client_id,
            entra=entra_metrics,
            google=google_metrics,
            allocation=allocation,
        )

    except Exception as e:
        logger.error(f"Failed to get runway for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domain-sets/{domain_id}/promote")
async def promote_domain(
    domain_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Manually promote a B-Set domain to A-Set.
    Use when you need to expand A-Set capacity.
    """
    try:
        # Check domain is B-Set
        domain = await fetch_one("""
            SELECT id, domain_name, pool_status, workspace_id
            FROM domains WHERE id = $1
        """, uuid.UUID(domain_id))

        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found")

        if domain['pool_status'] != 'reserve':
            raise HTTPException(
                status_code=400,
                detail=f"Domain is {domain['pool_status']}, not reserve. Cannot promote."
            )

        # Promote reserve to live (B-Set to A-Set)
        await execute("""
            UPDATE domains
            SET pool_status = 'live', promoted_at = NOW()
            WHERE id = $1
        """, uuid.UUID(domain_id))

        # Log history
        await execute("""
            INSERT INTO domain_pool_history (domain_id, old_status, new_status, reason)
            VALUES ($1, 'reserve', 'live', 'manual_promotion')
        """, uuid.UUID(domain_id))

        # Log activity
        await log_activity(
            user_id=current_user.id if current_user else None,
            action="promote_domain",
            resource_type="domain",
            resource_id=domain_id,
            details={"domain_name": domain['domain_name']}
        )

        return {
            "success": True,
            "domain_name": domain['domain_name'],
            "new_status": "live",
            "message": f"Domain {domain['domain_name']} promoted to live (A-Set)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Domain promotion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# CAPACITY HARMONY ENDPOINT
# ============================================

@router.get("/capacity-harmony/{client_id}", response_model=CapacityHarmonyResponse)
async def get_capacity_harmony(client_id: str):
    """
    Get capacity harmony metrics for a client.

    Combines:
    - Gap analysis (how many inboxes/domains below target)
    - Runway prediction (when will reserve run out)
    - Purchase recommendation (how many domains to buy)

    Key formulas:
    - GAP = capacity_required - capacity_actual
    - RUNWAY = reserve_count / monthly_burn_rate
    - RECOMMENDATION = max(domain_gap, low_runway_buffer)
    """
    try:
        # Get client info
        client = await fetch_one("""
            SELECT c.id, c.name, c.workspace_id
            FROM clients c WHERE c.id = $1
        """, uuid.UUID(client_id))

        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        # Get capacity data from v_client_capacity
        capacity = await fetch_one("""
            SELECT * FROM v_client_capacity WHERE client_id = $1
        """, uuid.UUID(client_id))

        # Get runway data from v_domain_runway
        runway_rows = await fetch_all("""
            SELECT * FROM v_domain_runway WHERE client_id = $1
        """, uuid.UUID(client_id))

        # Get pipeline summary
        pipeline = await fetch_one("""
            SELECT * FROM get_pipeline_summary($1)
        """, uuid.UUID(client_id))

        # Get HyperTide in-flight orders (handle missing table gracefully)
        try:
            hypertide_orders = await fetch_one("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
                    COUNT(*) FILTER (WHERE status IN ('executing', 'processing')) as provisioning_count
                FROM hypertide_order_jobs
                WHERE workspace_id = $1
                AND status NOT IN ('completed', 'failed', 'cancelled')
            """, client['workspace_id'])
        except Exception:
            # Table may not exist in all environments
            hypertide_orders = {'pending_count': 0, 'provisioning_count': 0}

        # Process runway data
        runway_by_provider = {}
        for row in runway_rows:
            provider = row['provider']
            if provider == 'microsoft':
                provider = 'entra'
            runway_by_provider[provider] = row

        # Calculate exhaustion dates
        def calc_exhaustion_date(runway_months: float) -> Optional[str]:
            if runway_months <= 0:
                return None
            if runway_months > 24:  # More than 2 years, don't calculate
                return None
            from datetime import timedelta
            exhaust_date = datetime.now(timezone.utc) + timedelta(days=int(runway_months * 30))
            return exhaust_date.isoformat()

        # Build provider metrics
        def build_provider_harmony(
            provider: str,
            capacity_row: dict,
            runway_row: dict,
            pipeline_row: dict,
            hypertide_row: dict,
        ) -> ProviderCapacityHarmony:
            prefix = 'entra' if provider == 'entra' else 'google'

            # Capacity from subscription
            capacity_required = capacity_row.get(f'{prefix}_inboxes_target') or 0
            # Use connected inboxes as actual capacity
            capacity_actual = capacity_row.get(f'{prefix}_inboxes_live') or 0
            gap = max(0, capacity_required - capacity_actual)
            domain_gap = capacity_row.get(f'{prefix}_domain_gap') or 0

            # Runway
            monthly_burn = float(runway_row.get('monthly_burn_rate') or 0) if runway_row else 0
            runway_months = float(runway_row.get('runway_months') or 0) if runway_row else 0
            runway_healthy = runway_row.get('runway_healthy', True) if runway_row else True

            # Pipeline counts
            live = runway_row.get('live_count') or 0 if runway_row else 0
            reserve = runway_row.get('reserve_count') or 0 if runway_row else 0

            # From pipeline summary
            if provider == 'entra':
                incubating = pipeline_row.get('incubating_entra') or 0 if pipeline_row else 0
            else:
                incubating = pipeline_row.get('incubating_google') or 0 if pipeline_row else 0

            burned = runway_row.get('burned_count') or 0 if runway_row else 0

            return ProviderCapacityHarmony(
                provider=provider,
                capacity_required=capacity_required,
                capacity_actual=capacity_actual,
                gap=gap,
                domain_gap=domain_gap,
                live=live,
                reserve=reserve,
                incubating=incubating,
                burned=burned,
                monthly_burn_rate=monthly_burn,
                runway_months=runway_months,
                exhaustion_date=calc_exhaustion_date(runway_months),
                runway_healthy=runway_healthy,
                pending_orders=hypertide_row.get('pending_count') or 0 if hypertide_row else 0,
                provisioning=hypertide_row.get('provisioning_count') or 0 if hypertide_row else 0,
            )

        entra = build_provider_harmony(
            'entra',
            capacity or {},
            runway_by_provider.get('entra') or runway_by_provider.get('microsoft', {}),
            pipeline,
            hypertide_orders,
        )
        google = build_provider_harmony(
            'google',
            capacity or {},
            runway_by_provider.get('google', {}),
            pipeline,
            hypertide_orders,
        )

        # Calculate totals and recommendation
        total_gap = entra.gap + google.gap
        total_domain_gap = entra.domain_gap + google.domain_gap

        # Purchase recommendation:
        # - Cover domain gap
        # - Add buffer if runway is low (< 2 months)
        # - Subtract domains already in pipeline (incubating)
        domains_in_pipeline = entra.incubating + google.incubating
        raw_recommendation = total_domain_gap
        if not entra.runway_healthy or not google.runway_healthy:
            # Add 2 months of buffer if runway is unhealthy
            avg_burn = (entra.monthly_burn_rate + google.monthly_burn_rate)
            raw_recommendation += int(avg_burn * 2)

        purchase_recommendation = max(0, raw_recommendation - domains_in_pipeline)

        # Estimated cost at ~$10/domain average
        estimated_cost = purchase_recommendation * 10.0

        # Overall runway exhaustion (earliest)
        dates = [d for d in [entra.exhaustion_date, google.exhaustion_date] if d]
        runway_exhaustion_date = min(dates) if dates else None

        return CapacityHarmonyResponse(
            client_id=client_id,
            client_name=client['name'],
            entra=entra,
            google=google,
            total_gap=total_gap,
            total_domain_gap=total_domain_gap,
            purchase_recommendation=purchase_recommendation,
            estimated_cost=estimated_cost,
            runway_exhaustion_date=runway_exhaustion_date,
            runway_healthy=entra.runway_healthy and google.runway_healthy,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get capacity harmony for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# DOMAIN SET ALLOCATION (Live/Reserve)
# ============================================

class DomainAllocationRequest(BaseModel):
    dry_run: bool = True


class DomainAllocationResult(BaseModel):
    workspace_name: str
    dry_run: bool
    entra_surplus: int
    google_surplus: int
    entra_reserve_capacity: int
    google_reserve_capacity: int
    domains_to_reserve: int
    domains_to_live: int
    reserve_domains: List[Dict[str, Any]]
    live_domains: List[Dict[str, Any]]
    changes_applied: bool
    errors: List[str]


def score_domain_health(domain: Dict) -> float:
    """Calculate domain health score. Higher = healthier = reserve candidate."""
    score = 100.0

    if domain.get('has_spam_complaints'):
        score -= 200
    if domain.get('has_hard_blocks'):
        score -= 100

    bounce_rate = domain.get('avg_bounce_rate', 0) or 0
    score -= bounce_rate * 500

    health = domain.get('avg_health_score', 80) or 80
    score += (health - 80) * 2

    inbox_count = domain.get('inbox_count', 0) or 0
    high_bounce = domain.get('high_bounce_count', 0) or 0
    high_bounce_pct = high_bounce / max(inbox_count, 1)
    score -= high_bounce_pct * 50

    if inbox_count >= 50:
        score += 10
    elif inbox_count >= 3:
        score += 5

    return round(score, 2)


@router.post("/domain-sets/allocate/{workspace_name}", response_model=DomainAllocationResult)
async def allocate_domain_sets(
    workspace_name: str,
    request: DomainAllocationRequest,
):
    """
    Allocate domains to live/reserve sets based on capacity and health.

    Logic:
    - Reserve only created when surplus capacity exists (live > target)
    - Healthiest domains go to reserve (protected)
    - Degraded domains stay live (expendable)
    - Provider-aware: Entra and Google allocated separately
    """
    errors = []

    # Get workspace
    workspace = await fetch_one("""
        SELECT id, workspace_name FROM workspaces WHERE workspace_name = $1
    """, workspace_name)

    if not workspace:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_name}' not found")

    workspace_id = workspace['id']

    # Get capacity data
    capacity = await fetch_one("""
        SELECT
            COALESCE(entra_inboxes_target, 0) as entra_target,
            COALESCE(entra_inboxes_live, 0) as entra_live,
            COALESCE(google_inboxes_target, 0) as google_target,
            COALESCE(google_inboxes_live, 0) as google_live,
            COALESCE(target_buffer_ratio, 0.15) as spare_ratio
        FROM v_client_capacity cc
        JOIN workspaces w ON cc.workspace_id = w.id
        WHERE w.id = $1
    """, workspace_id)

    if not capacity:
        raise HTTPException(status_code=400, detail="No capacity data (missing subscription?)")

    # Calculate surplus and reserve capacity
    entra_surplus = capacity['entra_live'] - capacity['entra_target']
    google_surplus = capacity['google_live'] - capacity['google_target']
    spare_ratio = float(capacity['spare_ratio'])

    entra_reserve_cap = min(int(capacity['entra_target'] * spare_ratio), max(0, entra_surplus))
    google_reserve_cap = min(int(capacity['google_target'] * spare_ratio), max(0, google_surplus))

    # Get domains with health metrics
    domains = await fetch_all("""
        WITH domain_metrics AS (
            SELECT
                d.id as domain_id,
                d.domain_name,
                d.pool_status as current_pool_status,
                CASE
                    WHEN sa.esp = 'microsoft' THEN 'entra'
                    WHEN sa.esp = 'gmail' THEN 'google'
                    ELSE 'unknown'
                END as provider,
                COUNT(sa.id) as inbox_count,
                COUNT(sa.id) FILTER (WHERE sa.status = 'Connected') as connected_count,
                AVG(sa.health_score) as avg_health_score,
                AVG(COALESCE(sa.bounce_rate_7d, 0)) as avg_bounce_rate,
                COUNT(sa.id) FILTER (WHERE COALESCE(sa.bounce_rate_7d, 0) > 0.02) as high_bounce_count,
                COUNT(sa.id) FILTER (WHERE sa.kill_trigger = 'spam_complaint') > 0 as has_spam_complaints,
                COUNT(sa.id) FILTER (WHERE sa.kill_trigger LIKE 'provider_block%%') > 0 as has_hard_blocks
            FROM domains d
            JOIN sender_accounts sa ON sa.domain_id = d.id
            WHERE d.workspace_id = $1
              AND d.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.is_active = TRUE
            GROUP BY d.id, d.domain_name, d.pool_status, sa.esp
        )
        SELECT * FROM domain_metrics WHERE inbox_count > 0
    """, workspace_id)

    # Separate by provider and score
    entra_domains = [dict(d) for d in domains if d['provider'] == 'entra']
    google_domains = [dict(d) for d in domains if d['provider'] == 'google']

    for d in entra_domains:
        d['health_score'] = score_domain_health(d)
    for d in google_domains:
        d['health_score'] = score_domain_health(d)

    # Sort by health (highest = healthiest = reserve candidates)
    entra_domains.sort(key=lambda d: d['health_score'], reverse=True)
    google_domains.sort(key=lambda d: d['health_score'], reverse=True)

    # Select reserve domains
    def select_reserve(domains, target_inboxes):
        reserve, live = [], []
        reserve_inbox_count = 0
        for d in domains:
            if reserve_inbox_count < target_inboxes:
                reserve.append(d)
                reserve_inbox_count += d['inbox_count']
            else:
                live.append(d)
        return reserve, live

    entra_reserve, entra_live = select_reserve(entra_domains, entra_reserve_cap)
    google_reserve, google_live = select_reserve(google_domains, google_reserve_cap)

    reserve_domains = entra_reserve + google_reserve
    live_domains = entra_live + google_live

    # Apply changes if not dry run
    changes_applied = False
    if not request.dry_run:
        changes_applied = True

        # Update reserve domains
        for d in reserve_domains:
            try:
                await execute("""
                    UPDATE domains SET pool_status = 'reserve', updated_at = NOW()
                    WHERE id = $1
                """, d['domain_id'])
                await execute("""
                    UPDATE sender_accounts SET inventory_pool_status = 'reserve', updated_at = NOW()
                    WHERE domain_id = $1 AND inbox_state = 'live' AND is_active = TRUE
                """, d['domain_id'])
            except Exception as e:
                errors.append(f"Reserve {d['domain_name']}: {str(e)}")

        # Update live domains
        for d in live_domains:
            try:
                await execute("""
                    UPDATE domains SET pool_status = 'live', updated_at = NOW()
                    WHERE id = $1
                """, d['domain_id'])
                await execute("""
                    UPDATE sender_accounts SET inventory_pool_status = 'deployed', updated_at = NOW()
                    WHERE domain_id = $1 AND inbox_state = 'live' AND is_active = TRUE
                """, d['domain_id'])
            except Exception as e:
                errors.append(f"Live {d['domain_name']}: {str(e)}")

        logger.info(f"Domain allocation for {workspace_name}: {len(reserve_domains)} reserve, {len(live_domains)} live")

    # Format output
    def format_domain(d):
        return {
            'domain_name': d['domain_name'],
            'provider': d['provider'],
            'inbox_count': d['inbox_count'],
            'health_score': round(d['health_score'], 1),
            'avg_bounce_rate': round((d['avg_bounce_rate'] or 0) * 100, 2),
        }

    return DomainAllocationResult(
        workspace_name=workspace_name,
        dry_run=request.dry_run,
        entra_surplus=entra_surplus,
        google_surplus=google_surplus,
        entra_reserve_capacity=entra_reserve_cap,
        google_reserve_capacity=google_reserve_cap,
        domains_to_reserve=len(reserve_domains),
        domains_to_live=len(live_domains),
        reserve_domains=[format_domain(d) for d in reserve_domains],
        live_domains=[format_domain(d) for d in live_domains[:10]],  # Limit output
        changes_applied=changes_applied,
        errors=errors,
    )
