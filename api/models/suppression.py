"""
Suppression module models — per-client domain blacklist system.

Each client (identified by workspace_id / client_id) has their own isolated
suppression list. No suppression data from one client can affect another.
"""

from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime
from uuid import UUID


# ── Type aliases ──────────────────────────────────────────────────────────────

SuppressionAddedBy = Literal["manual", "csv_import", "api"]
MatchType = Literal["direct", "umbrella"]


# ── Config models ─────────────────────────────────────────────────────────────

class SuppressionConfig(BaseModel):
    """Full suppression config for a client. Returned by GET /config."""
    client_id: UUID
    workspace_id: Optional[UUID] = None
    is_enabled: bool
    api_token: str
    token_created_at: datetime
    token_last_used_at: Optional[datetime] = None
    domain_count: int
    last_import_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SuppressionConfigUpdate(BaseModel):
    """Fields that can be PATCHed on a config row."""
    is_enabled: Optional[bool] = None
    notes: Optional[str] = None


class TokenRotateResponse(BaseModel):
    """Returned after a successful token rotation."""
    api_token: str
    token_created_at: datetime


# ── Domain seed list models ───────────────────────────────────────────────────

class SuppressionDomain(BaseModel):
    """A single protected domain entry."""
    id: UUID
    client_id: UUID
    domain: str
    umbrella_domain: Optional[str] = None
    added_by: SuppressionAddedBy
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SuppressionDomainCreate(BaseModel):
    """Create a single domain entry manually."""
    domain: str
    umbrella_domain: Optional[str] = None
    notes: Optional[str] = None


class SuppressionDomainBulkItem(BaseModel):
    """One row in a bulk import payload."""
    domain: str
    umbrella_domain: Optional[str] = None
    notes: Optional[str] = None


class SuppressionDomainBulkCreate(BaseModel):
    """Bulk import request — up to 10,000 domains per call."""
    domains: list[SuppressionDomainBulkItem]
    source: SuppressionAddedBy = "csv_import"
    # When True: deletes all existing domains for this client before inserting.
    # Use only for full seed list replacements. Requires explicit UI confirmation.
    replace_all: bool = False


class SuppressionDomainBulkResult(BaseModel):
    """Result summary returned after a bulk import."""
    inserted: int
    skipped_duplicates: int
    rejected_invalid: int
    invalid_entries: list[str]   # samples of rejected values with reason
    total_after: int             # total domain count after this import


class SuppressionDomainList(BaseModel):
    """Paginated list of domain entries."""
    items: list[SuppressionDomain]
    total: int
    page: int
    page_size: int


# ── Clay check endpoint models ────────────────────────────────────────────────

class SuppressionCheckRequest(BaseModel):
    """
    Request body for POST /suppressions/check (Clay endpoint).

    Both fields are optional — if only email is provided, the domain is
    extracted from it. If both are provided, both are checked.
    The call is suppressed if EITHER domain matches a rule.
    """
    email: Optional[str] = None
    company_domain: Optional[str] = None


class SuppressionCheckResponse(BaseModel):
    """
    Response from the Clay check endpoint. Always HTTP 200.
    Clay treats non-200 responses as pipeline errors, not as suppression verdicts.
    """
    suppressed: bool
    reason: Optional[str] = None           # human-readable explanation
    matched_domain: Optional[str] = None   # the rule that triggered (if suppressed)
    match_type: Optional[MatchType] = None # 'direct' or 'umbrella'
    client_id: UUID


# ── Scan models ───────────────────────────────────────────────────────────────

class SuppressionScanRequest(BaseModel):
    """
    Retroactive scan request. Checks all leads with suppression_status IS NULL
    against the client's current domain list and stamps them accordingly.
    """
    campaign_id: Optional[UUID] = None   # if None, scans all campaigns for the workspace


class SuppressionScanResult(BaseModel):
    """Summary of a retroactive scan run."""
    scanned: int            # leads evaluated in this run
    suppressed: int         # leads newly stamped as suppressed
    already_evaluated: int  # leads skipped (suppression_status was not NULL)
    duration_ms: int


# ── Stats model ───────────────────────────────────────────────────────────────

class SuppressionStats(BaseModel):
    """Aggregate stats for the dashboard card."""
    is_enabled: bool
    domain_count: int
    last_import_at: Optional[datetime] = None
    leads_suppressed_total: int
    leads_checked_total: int
    check_calls_today: int
    check_calls_7d: int
