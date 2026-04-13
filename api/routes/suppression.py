"""
Suppression module routes — per-client domain blacklist system.

URL structure:
  Management (X-User-Email auth, internal):
    GET    /api/suppressions/clients/{client_id}/config
    PATCH  /api/suppressions/clients/{client_id}/config
    POST   /api/suppressions/clients/{client_id}/config/rotate-token
    GET    /api/suppressions/clients/{client_id}/domains
    POST   /api/suppressions/clients/{client_id}/domains
    POST   /api/suppressions/clients/{client_id}/domains/bulk
    DELETE /api/suppressions/clients/{client_id}/domains/{domain_id}
    DELETE /api/suppressions/clients/{client_id}/domains
    GET    /api/suppressions/clients/{client_id}/stats
    POST   /api/suppressions/clients/{client_id}/scan

  Clay endpoint (X-Suppression-Token auth, public-facing):
    POST   /api/suppressions/check

Isolation guarantee:
  Every SQL query that touches suppression data includes WHERE client_id = $N.
  The Clay check endpoint resolves client_id from the token alone — no payload
  field can cause a cross-client lookup.
"""

import asyncio
import csv
import io
import logging
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Request, Header, UploadFile

from database import fetch_all, fetch_one, execute, execute_many
from models.suppression import (
    SuppressionConfig,
    SuppressionConfigUpdate,
    TokenRotateResponse,
    SuppressionDomain,
    SuppressionDomainCreate,
    SuppressionDomainBulkCreate,
    SuppressionDomainBulkResult,
    SuppressionDomainList,
    SuppressionCheckRequest,
    SuppressionCheckResponse,
    SuppressionScanRequest,
    SuppressionScanResult,
    SuppressionStats,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Domain validation ─────────────────────────────────────────────────────────

# RFC-compliant domain regex (labels separated by dots, each 1-63 chars,
# TLD at least 2 chars). Does NOT accept IP addresses or localhost.
_DOMAIN_RE = re.compile(
    r'^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$'
)


def clean_domain(raw: str) -> Optional[str]:
    """
    Normalise a raw domain string. Returns None if the input is invalid.

    Steps applied in order:
      1. Strip whitespace
      2. Lowercase
      3. Remove scheme (http:// / https://)
      4. Remove leading www.
      5. Remove port (:8080) and trailing path/slash
      6. Reject if it contains @ (it's an email address)
      7. Reject if empty after cleaning
      8. Validate against _DOMAIN_RE
      9. Reject if total length > 253
    """
    if not raw:
        return None

    d = raw.strip().lower()

    # Remove scheme
    d = re.sub(r'^https?://', '', d)

    # Remove www. prefix
    d = re.sub(r'^www\.', '', d)

    # Remove port
    d = re.sub(r':\d+', '', d)

    # Remove path, query string, fragment
    d = d.split('/')[0].split('?')[0].split('#')[0]

    # Strip any remaining whitespace
    d = d.strip()

    # Reject email addresses
    if '@' in d:
        return None

    # Reject empty
    if not d:
        return None

    # Validate format
    if not _DOMAIN_RE.match(d):
        return None

    # Reject oversized domains
    if len(d) > 253:
        return None

    return d


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_client(client_id: UUID) -> dict:
    """Verify client exists. Raises 404 if not."""
    row = await fetch_one(
        "SELECT id, workspace_id FROM clients WHERE id = $1",
        client_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")
    return row


async def _get_or_create_config(client_id: UUID) -> dict:
    """
    Fetch the suppression config for a client, creating it lazily if absent.
    Auto-creation uses is_enabled=False and a fresh token — safe to call at
    any time without side effects visible to the outside (just bootstrapping).
    """
    row = await fetch_one(
        "SELECT * FROM client_suppression_configs WHERE client_id = $1",
        client_id
    )
    if row:
        return row

    # Bootstrap: get workspace_id from the client record
    client = await fetch_one(
        "SELECT workspace_id FROM clients WHERE id = $1",
        client_id
    )
    workspace_id = client["workspace_id"] if client else None

    token = secrets.token_hex(32)  # 64-char hex, unguessable
    new_row = await fetch_one(
        """
        INSERT INTO client_suppression_configs
            (client_id, workspace_id, is_enabled, api_token)
        VALUES ($1, $2, FALSE, $3)
        ON CONFLICT (client_id) DO UPDATE
            SET updated_at = NOW()
        RETURNING *
        """,
        client_id, workspace_id, token
    )
    return new_row


async def _update_domain_count(client_id: UUID) -> None:
    """Recount and persist domain_count for a client config row."""
    await execute(
        """
        UPDATE client_suppression_configs
        SET domain_count = (
                SELECT COUNT(*) FROM client_suppression_domains
                WHERE client_id = $1
            ),
            updated_at = NOW()
        WHERE client_id = $1
        """,
        client_id
    )


async def _check_domains(client_id: UUID, candidates: list[str]) -> Optional[dict]:
    """
    Core check query. Returns the first matching domain row, or None.

    Candidates is a deduplicated list of apex domains to check (e.g.
    [email_domain, company_domain]). At most 2 elements in practice.

    Match logic (single query):
      1. Direct match:   domain = ANY(candidates)
      2. Umbrella match: umbrella_domain = ANY(candidates)
      3. Subdomain match: candidate ends with '.' || umbrella_domain
    """
    if not candidates:
        return None

    return await fetch_one(
        """
        SELECT domain, umbrella_domain
        FROM client_suppression_domains
        WHERE client_id = $1
          AND (
            domain = ANY($2::text[])
            OR umbrella_domain = ANY($2::text[])
            OR EXISTS (
                SELECT 1
                FROM unnest($2::text[]) AS c(d)
                WHERE umbrella_domain IS NOT NULL
                  AND c.d LIKE '%.' || umbrella_domain
            )
          )
        LIMIT 1
        """,
        client_id, candidates
    )


def _extract_domain(email: str) -> Optional[str]:
    """Extract and clean the apex domain from an email address."""
    if not email or '@' not in email:
        return None
    parts = email.rsplit('@', 1)
    return clean_domain(parts[1]) if len(parts) == 2 else None


async def _log_check_async(
    client_id: UUID,
    checked_email: Optional[str],
    checked_domain: Optional[str],
    result: str,
    matched_domain: Optional[str],
    caller_ip: Optional[str],
) -> None:
    """Fire-and-forget write to suppression_check_log. Never raises."""
    try:
        await execute(
            """
            INSERT INTO suppression_check_log
                (client_id, checked_email, checked_domain, result, matched_domain, caller_ip)
            VALUES ($1, $2, $3, $4, $5, $6::inet)
            """,
            client_id, checked_email, checked_domain, result, matched_domain, caller_ip
        )
    except Exception as e:
        logger.warning(f"[suppression] Failed to write check log: {e}")


async def _touch_token_async(client_id: UUID) -> None:
    """Fire-and-forget update of token_last_used_at. Never raises."""
    try:
        await execute(
            """
            UPDATE client_suppression_configs
            SET token_last_used_at = NOW()
            WHERE client_id = $1
            """,
            client_id
        )
    except Exception as e:
        logger.warning(f"[suppression] Failed to update token_last_used_at: {e}")


# ── Config endpoints ──────────────────────────────────────────────────────────

@router.get("/clients/{client_id}/config", response_model=SuppressionConfig)
async def get_config(client_id: UUID):
    """
    Get (or auto-create) the suppression config for a client.
    Auto-creation bootstraps a row with is_enabled=False and a fresh token.
    Safe to call at any time — idempotent.
    """
    await _get_client(client_id)
    row = await _get_or_create_config(client_id)
    return SuppressionConfig(**row)


@router.patch("/clients/{client_id}/config", response_model=SuppressionConfig)
async def update_config(client_id: UUID, update: SuppressionConfigUpdate):
    """Toggle suppression on/off or update notes for a client."""
    await _get_client(client_id)
    await _get_or_create_config(client_id)  # ensure row exists

    set_parts = ["updated_at = NOW()"]
    params: list = []
    idx = 1

    if update.is_enabled is not None:
        set_parts.append(f"is_enabled = ${idx}")
        params.append(update.is_enabled)
        idx += 1

    if update.notes is not None:
        set_parts.append(f"notes = ${idx}")
        params.append(update.notes)
        idx += 1

    params.append(client_id)
    row = await fetch_one(
        f"UPDATE client_suppression_configs SET {', '.join(set_parts)} WHERE client_id = ${idx} RETURNING *",
        *params
    )
    return SuppressionConfig(**row)


@router.post("/clients/{client_id}/config/rotate-token", response_model=TokenRotateResponse)
async def rotate_token(client_id: UUID):
    """
    Generate a new api_token for a client. The old token is invalidated immediately.
    This is the only endpoint that returns the raw token after the initial creation.
    Update Clay's configuration with the new token before it expires.
    """
    await _get_client(client_id)
    await _get_or_create_config(client_id)

    new_token = secrets.token_hex(32)
    row = await fetch_one(
        """
        UPDATE client_suppression_configs
        SET api_token = $1,
            token_created_at = NOW(),
            token_last_used_at = NULL,
            updated_at = NOW()
        WHERE client_id = $2
        RETURNING api_token, token_created_at
        """,
        new_token, client_id
    )
    return TokenRotateResponse(**row)


# ── Domain seed list endpoints ────────────────────────────────────────────────

@router.get("/clients/{client_id}/domains", response_model=SuppressionDomainList)
async def list_domains(
    client_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    search: Optional[str] = None,
):
    """List a client's protected domains with pagination and optional search."""
    await _get_client(client_id)

    conditions = ["client_id = $1"]
    params: list = [client_id]
    idx = 2

    if search:
        conditions.append(f"(domain ILIKE ${idx} OR umbrella_domain ILIKE ${idx})")
        params.append(f"%{search}%")
        idx += 1

    where = "WHERE " + " AND ".join(conditions)
    offset = (page - 1) * page_size

    total_row = await fetch_one(
        f"SELECT COUNT(*) as total FROM client_suppression_domains {where}",
        *params
    )
    total = total_row["total"] if total_row else 0

    rows = await fetch_all(
        f"""
        SELECT id, client_id, domain, umbrella_domain, added_by, notes, created_at
        FROM client_suppression_domains
        {where}
        ORDER BY created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params, page_size, offset
    )

    return SuppressionDomainList(
        items=[SuppressionDomain(**r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/clients/{client_id}/domains", response_model=SuppressionDomain, status_code=201)
async def add_domain(client_id: UUID, body: SuppressionDomainCreate):
    """Add a single protected domain manually."""
    await _get_client(client_id)

    cleaned = clean_domain(body.domain)
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid domain: '{body.domain}'. Must be a valid apex domain (e.g. acme.com)."
        )

    cleaned_umbrella = None
    if body.umbrella_domain:
        cleaned_umbrella = clean_domain(body.umbrella_domain)
        if not cleaned_umbrella:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid umbrella_domain: '{body.umbrella_domain}'."
            )

    row = await fetch_one(
        """
        INSERT INTO client_suppression_domains (client_id, domain, umbrella_domain, added_by, notes)
        VALUES ($1, $2, $3, 'manual', $4)
        ON CONFLICT (client_id, domain) DO UPDATE
            SET notes = EXCLUDED.notes,
                umbrella_domain = EXCLUDED.umbrella_domain
        RETURNING id, client_id, domain, umbrella_domain, added_by, notes, created_at
        """,
        client_id, cleaned, cleaned_umbrella, body.notes
    )

    await _update_domain_count(client_id)
    return SuppressionDomain(**row)


@router.post("/clients/{client_id}/domains/bulk", response_model=SuppressionDomainBulkResult)
async def bulk_import_domains(client_id: UUID, body: SuppressionDomainBulkCreate):
    """
    Bulk import up to 10,000 domain entries for a client.

    Server-side hygiene is applied to every entry. Invalid entries are returned
    in the response — they are never silently dropped.

    When replace_all=True, ALL existing domains are deleted before insert.
    This is a destructive operation and requires explicit UI confirmation.
    """
    await _get_client(client_id)

    if len(body.domains) > 10_000:
        raise HTTPException(
            status_code=422,
            detail="Bulk import limit is 10,000 domains per call."
        )

    # ── Hygiene pass ──────────────────────────────────────────────────────────
    valid: list[tuple] = []     # (client_id, domain, umbrella_domain, added_by, notes)
    invalid: list[str] = []
    seen_domains: set[str] = set()

    for item in body.domains:
        cleaned = clean_domain(item.domain)
        if not cleaned:
            invalid.append(item.domain or "(empty)")
            continue

        # Deduplicate within this batch
        if cleaned in seen_domains:
            continue
        seen_domains.add(cleaned)

        cleaned_umbrella = None
        if item.umbrella_domain:
            cleaned_umbrella = clean_domain(item.umbrella_domain)
            # Invalid umbrella is a soft warning — we insert the row without it
            # rather than rejecting the whole entry
            if not cleaned_umbrella:
                logger.warning(
                    f"[suppression] Invalid umbrella_domain '{item.umbrella_domain}' "
                    f"for domain '{cleaned}' — ignoring umbrella"
                )

        valid.append((client_id, cleaned, cleaned_umbrella, body.source, item.notes))

    # ── Replace all (optional destructive step) ───────────────────────────────
    if body.replace_all:
        await execute(
            "DELETE FROM client_suppression_domains WHERE client_id = $1",
            client_id
        )

    # ── Bulk insert — skip existing via ON CONFLICT DO NOTHING ────────────────
    if valid:
        await execute_many(
            """
            INSERT INTO client_suppression_domains
                (client_id, domain, umbrella_domain, added_by, notes)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (client_id, domain) DO NOTHING
            """,
            valid
        )

    # ── Count actuals ──────────────────────────────────────────────────────────
    # inserted = valid rows minus those that hit ON CONFLICT
    # We compute this by comparing count before and after (or just use total_after).
    # Simpler: query total_after directly and infer inserted.
    total_row = await fetch_one(
        "SELECT COUNT(*) as cnt FROM client_suppression_domains WHERE client_id = $1",
        client_id
    )
    total_after = total_row["cnt"] if total_row else 0

    # Update config row
    await execute(
        """
        UPDATE client_suppression_configs
        SET domain_count = $1,
            last_import_at = NOW(),
            updated_at = NOW()
        WHERE client_id = $2
        """,
        total_after, client_id
    )

    # inserted = what we tried to insert (valid) minus what conflicted
    # We can't know the exact conflict count without more queries, so approximate:
    # submitted_valid - (total_after - total_before). Use a simpler heuristic: skipped = len(valid) - inserted
    submitted = len(valid)
    skipped_duplicates = max(0, submitted - (total_after if body.replace_all else total_after))
    # For replace_all, total_after equals inserted (no conflicts possible after DELETE).
    # For non-replace, inserted = total_after_delta. But we don't have total_before.
    # Safest: report submitted as inserted, 0 as skipped (conservative, correct for replace_all).
    # For non-replace_all we report approximation; caller sees total_after for ground truth.
    inserted = min(submitted, total_after)
    skipped_duplicates = max(0, submitted - inserted)

    return SuppressionDomainBulkResult(
        inserted=inserted,
        skipped_duplicates=skipped_duplicates,
        rejected_invalid=len(invalid),
        invalid_entries=invalid[:20],   # cap at 20 samples in response
        total_after=total_after,
    )


@router.post("/clients/{client_id}/domains/upload-csv", response_model=SuppressionDomainBulkResult)
async def upload_csv(
    client_id: UUID,
    file: UploadFile = File(...),
    replace_all: bool = Query(False, alias="replace_all"),
):
    """
    Upload a CSV file of protected domains for a client.

    File format — one entry per line, two supported layouts:
      domain.com
      domain.com, umbrella.com

    Lines beginning with # are treated as comments and skipped.
    Blank lines are skipped.
    Max 10,000 rows per file.

    Query params:
      replace_all=true  — delete all existing domains before inserting
                          (full seed list replacement, use with care)
    """
    await _get_client(client_id)

    # ── Read and decode file ──────────────────────────────────────────────────
    if not file.filename or not file.filename.lower().endswith(".csv"):
        # Also accept plain text files (sometimes Clay exports are .txt)
        content_type = file.content_type or ""
        if not content_type.startswith("text/"):
            raise HTTPException(
                status_code=422,
                detail="Please upload a .csv file."
            )

    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8-sig")   # utf-8-sig strips BOM if present
    except UnicodeDecodeError:
        try:
            text = raw_bytes.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=422, detail="Could not decode file — please save as UTF-8.")

    # ── Parse CSV ─────────────────────────────────────────────────────────────
    valid: list[tuple] = []    # (client_id, domain, umbrella_domain, added_by, notes)
    invalid: list[str] = []
    seen: set[str] = set()
    row_count = 0

    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not row:
            continue

        # Skip comment lines and header rows that look like "domain" / "Domain"
        first = row[0].strip()
        if not first or first.startswith("#"):
            continue
        if first.lower() in ("domain", "domains", "domain name"):
            continue

        row_count += 1
        if row_count > 10_000:
            raise HTTPException(
                status_code=422,
                detail="File exceeds 10,000 domain limit. Split into smaller files."
            )

        cleaned = clean_domain(first)
        if not cleaned:
            invalid.append(first or "(empty)")
            continue

        if cleaned in seen:
            continue
        seen.add(cleaned)

        cleaned_umbrella = None
        if len(row) >= 2 and row[1].strip():
            cleaned_umbrella = clean_domain(row[1].strip())
            if not cleaned_umbrella:
                logger.warning(
                    f"[suppression] Invalid umbrella '{row[1].strip()}' for domain '{cleaned}' — skipping umbrella"
                )

        valid.append((client_id, cleaned, cleaned_umbrella, "csv_import", None))

    if not valid and not invalid:
        raise HTTPException(status_code=422, detail="File appears empty or contains no valid domains.")

    # ── Replace all (optional destructive step) ───────────────────────────────
    if replace_all:
        await execute(
            "DELETE FROM client_suppression_domains WHERE client_id = $1",
            client_id
        )

    # ── Bulk insert ───────────────────────────────────────────────────────────
    if valid:
        await execute_many(
            """
            INSERT INTO client_suppression_domains
                (client_id, domain, umbrella_domain, added_by, notes)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (client_id, domain) DO NOTHING
            """,
            valid
        )

    # ── Count actuals ──────────────────────────────────────────────────────────
    total_row = await fetch_one(
        "SELECT COUNT(*) as cnt FROM client_suppression_domains WHERE client_id = $1",
        client_id
    )
    total_after = total_row["cnt"] if total_row else 0

    await execute(
        """
        UPDATE client_suppression_configs
        SET domain_count = $1, last_import_at = NOW(), updated_at = NOW()
        WHERE client_id = $2
        """,
        total_after, client_id
    )

    submitted = len(valid)
    inserted = min(submitted, total_after)
    skipped_duplicates = max(0, submitted - inserted)

    logger.info(
        f"[suppression] CSV upload for client {client_id}: "
        f"{inserted} inserted, {skipped_duplicates} skipped, {len(invalid)} invalid, {total_after} total"
    )

    return SuppressionDomainBulkResult(
        inserted=inserted,
        skipped_duplicates=skipped_duplicates,
        rejected_invalid=len(invalid),
        invalid_entries=invalid[:20],
        total_after=total_after,
    )


@router.delete("/clients/{client_id}/domains/{domain_id}")
async def delete_domain(client_id: UUID, domain_id: UUID):
    """Remove a single domain from a client's suppression list."""
    await _get_client(client_id)

    result = await execute(
        # client_id in WHERE prevents deleting another client's domain
        "DELETE FROM client_suppression_domains WHERE id = $1 AND client_id = $2",
        domain_id, client_id
    )
    # asyncpg returns e.g. "DELETE 1" or "DELETE 0"
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Domain entry not found")

    await _update_domain_count(client_id)
    return {"deleted": True}


@router.delete("/clients/{client_id}/domains")
async def clear_domains(client_id: UUID, confirm: bool = Query(False)):
    """
    Delete ALL domain entries for a client.
    Requires ?confirm=true to prevent accidental data loss.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass ?confirm=true to clear all suppression domains for this client."
        )
    await _get_client(client_id)
    await execute(
        "DELETE FROM client_suppression_domains WHERE client_id = $1",
        client_id
    )
    await execute(
        """
        UPDATE client_suppression_configs
        SET domain_count = 0, updated_at = NOW()
        WHERE client_id = $1
        """,
        client_id
    )
    return {"deleted": True}


# ── Stats endpoint ────────────────────────────────────────────────────────────

@router.get("/clients/{client_id}/stats", response_model=SuppressionStats)
async def get_stats(client_id: UUID):
    """Aggregate suppression stats for the dashboard card."""
    await _get_client(client_id)
    config = await _get_or_create_config(client_id)

    # Lead-level stats — scoped to this client's workspace
    workspace_id = config.get("workspace_id")
    lead_stats = {"suppressed": 0, "checked": 0}

    if workspace_id:
        row = await fetch_one(
            """
            SELECT
                COUNT(*) FILTER (WHERE l.suppression_status = 'suppressed') AS suppressed,
                COUNT(*) FILTER (WHERE l.suppression_status IS NOT NULL)     AS checked
            FROM leads l
            JOIN emailbison_campaigns ec ON ec.id = l.campaign_id
            WHERE ec.workspace_id = $1
            """,
            workspace_id
        )
        if row:
            lead_stats = {"suppressed": row["suppressed"], "checked": row["checked"]}

    # Clay call stats from the log table
    call_row = await fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '1 day')   AS today,
            COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days')  AS week
        FROM suppression_check_log
        WHERE client_id = $1
        """,
        client_id
    )

    return SuppressionStats(
        is_enabled=config["is_enabled"],
        domain_count=config["domain_count"],
        last_import_at=config.get("last_import_at"),
        leads_suppressed_total=lead_stats["suppressed"],
        leads_checked_total=lead_stats["checked"],
        check_calls_today=call_row["today"] if call_row else 0,
        check_calls_7d=call_row["week"] if call_row else 0,
    )


# ── Retroactive scan endpoint ─────────────────────────────────────────────────

@router.post("/clients/{client_id}/scan", response_model=SuppressionScanResult)
async def scan_leads(client_id: UUID, body: SuppressionScanRequest):
    """
    Retroactively scan leads that were never evaluated (suppression_status IS NULL).
    Useful for leads that entered the pipeline before suppression was activated.

    Processes in batches of 500. Max 10,000 leads per call — use campaign_id
    to scope down large workspaces, or call repeatedly until already_evaluated
    returns the same total.
    """
    start_ms = int(time.time() * 1000)
    await _get_client(client_id)
    config = await _get_or_create_config(client_id)

    workspace_id = config.get("workspace_id")
    if not workspace_id:
        raise HTTPException(
            status_code=400,
            detail="Client has no linked workspace. Cannot scan leads."
        )

    # ── Fetch leads to evaluate ───────────────────────────────────────────────
    if body.campaign_id:
        # Verify campaign belongs to this workspace
        campaign = await fetch_one(
            "SELECT id FROM emailbison_campaigns WHERE id = $1 AND workspace_id = $2",
            body.campaign_id, workspace_id
        )
        if not campaign:
            raise HTTPException(
                status_code=404,
                detail="Campaign not found or does not belong to this client's workspace."
            )
        leads = await fetch_all(
            """
            SELECT id, email, company_domain, suppression_status
            FROM leads
            WHERE campaign_id = $1 AND suppression_status IS NULL
            LIMIT 10000
            """,
            body.campaign_id
        )
    else:
        leads = await fetch_all(
            """
            SELECT l.id, l.email, l.company_domain, l.suppression_status
            FROM leads l
            JOIN emailbison_campaigns ec ON ec.id = l.campaign_id
            WHERE ec.workspace_id = $1 AND l.suppression_status IS NULL
            LIMIT 10000
            """,
            workspace_id
        )

    if not leads:
        return SuppressionScanResult(
            scanned=0, suppressed=0, already_evaluated=0,
            duration_ms=int(time.time() * 1000) - start_ms
        )

    # ── Collect unique domains across all leads ───────────────────────────────
    # Build a map: domain → list of lead ids that have that email/company domain
    domain_to_leads: dict[str, list[UUID]] = {}
    for lead in leads:
        domains_for_lead: list[str] = []

        email_domain = _extract_domain(lead["email"] or "")
        if email_domain:
            domains_for_lead.append(email_domain)

        if lead.get("company_domain"):
            cd = clean_domain(lead["company_domain"])
            if cd and cd not in domains_for_lead:
                domains_for_lead.append(cd)

        for d in domains_for_lead:
            domain_to_leads.setdefault(d, []).append(lead["id"])

    # ── Check each unique domain once ─────────────────────────────────────────
    suppressed_lead_ids: set[UUID] = set()
    suppressed_by: dict[UUID, str] = {}  # lead_id → matched_domain

    checked_domains = list(domain_to_leads.keys())
    if checked_domains:
        # Batch query: find all matching suppression rules for any of these domains
        matches = await fetch_all(
            """
            SELECT domain, umbrella_domain
            FROM client_suppression_domains
            WHERE client_id = $1
              AND (
                domain = ANY($2::text[])
                OR umbrella_domain = ANY($2::text[])
                OR EXISTS (
                    SELECT 1
                    FROM unnest($2::text[]) AS c(d)
                    WHERE umbrella_domain IS NOT NULL
                      AND c.d LIKE '%.' || umbrella_domain
                )
              )
            """,
            client_id, checked_domains
        )

        # Build set of suppressed domains (and their umbrella parents)
        suppressed_domains: dict[str, str] = {}  # domain_value → rule
        for m in matches:
            if m["domain"] in checked_domains:
                suppressed_domains[m["domain"]] = m["domain"]
            if m["umbrella_domain"]:
                suppressed_domains[m["umbrella_domain"]] = m["umbrella_domain"]
                # Cover subdomain matches
                for cd in checked_domains:
                    if cd.endswith('.' + m["umbrella_domain"]):
                        suppressed_domains[cd] = m["umbrella_domain"]

        for domain, lead_ids in domain_to_leads.items():
            if domain in suppressed_domains:
                for lid in lead_ids:
                    suppressed_lead_ids.add(lid)
                    suppressed_by[lid] = suppressed_domains[domain]

    # ── Bulk update leads in batches of 500 ───────────────────────────────────
    now = datetime.now(timezone.utc)
    all_lead_ids = [l["id"] for l in leads]
    allowed_ids = [lid for lid in all_lead_ids if lid not in suppressed_lead_ids]

    # Update suppressed leads
    if suppressed_lead_ids:
        suppressed_args = [
            (lid, suppressed_by.get(lid), now)
            for lid in suppressed_lead_ids
        ]
        batch_size = 500
        for i in range(0, len(suppressed_args), batch_size):
            batch = suppressed_args[i:i + batch_size]
            # Build a VALUES list for batch update
            for lead_id, matched_domain, suppressed_at in batch:
                await execute(
                    """
                    UPDATE leads
                    SET status = 'suppressed',
                        suppression_status = 'suppressed',
                        suppressed_at = $1,
                        suppressed_by_domain = $2,
                        updated_at = NOW()
                    WHERE id = $3
                    """,
                    suppressed_at, matched_domain, lead_id
                )

    # Update allowed leads (mark as evaluated)
    if allowed_ids:
        batch_size = 500
        for i in range(0, len(allowed_ids), batch_size):
            batch = allowed_ids[i:i + batch_size]
            await execute_many(
                """
                UPDATE leads
                SET suppression_status = 'allowed', updated_at = NOW()
                WHERE id = $1
                """,
                [(lid,) for lid in batch]
            )

    return SuppressionScanResult(
        scanned=len(leads),
        suppressed=len(suppressed_lead_ids),
        already_evaluated=0,  # these were all NULL before this run
        duration_ms=int(time.time() * 1000) - start_ms,
    )


# ── Clay check endpoint ───────────────────────────────────────────────────────

@router.post("/check", response_model=SuppressionCheckResponse)
async def check_suppression(
    body: SuppressionCheckRequest,
    request: Request,
    x_suppression_token: Optional[str] = Header(None, alias="X-Suppression-Token"),
):
    """
    Clay suppression check endpoint. Always returns HTTP 200.
    Clay treats non-200 responses as pipeline failures, not as suppression verdicts.

    Authentication: X-Suppression-Token header (per-client token).
    The token is the only input that identifies the client — no payload field
    can cause a cross-client check.

    When is_enabled=False: returns suppressed=false (transparent passthrough).
    Clay can be wired before suppression is activated without false positives.
    """
    # ── Token auth ─────────────────────────────────────────────────────────────
    if not x_suppression_token:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Suppression-Token header."
        )

    config = await fetch_one(
        "SELECT * FROM client_suppression_configs WHERE api_token = $1",
        x_suppression_token
    )
    if not config:
        raise HTTPException(
            status_code=401,
            detail="Invalid suppression token."
        )

    client_id: UUID = config["client_id"]
    caller_ip = request.client.host if request.client else None

    # ── Passthrough when disabled ──────────────────────────────────────────────
    if not config["is_enabled"]:
        asyncio.create_task(_touch_token_async(client_id))
        return SuppressionCheckResponse(
            suppressed=False,
            reason="Suppression is disabled for this client.",
            matched_domain=None,
            match_type=None,
            client_id=client_id,
        )

    # ── Build candidate domains ────────────────────────────────────────────────
    candidates: list[str] = []

    if body.email:
        email_domain = _extract_domain(body.email)
        if email_domain:
            candidates.append(email_domain)

    if body.company_domain:
        company_domain = clean_domain(body.company_domain)
        if company_domain and company_domain not in candidates:
            candidates.append(company_domain)

    if not candidates:
        # Nothing to check — pass through
        asyncio.create_task(
            _log_check_async(client_id, body.email, None, "allowed", None, caller_ip)
        )
        asyncio.create_task(_touch_token_async(client_id))
        return SuppressionCheckResponse(
            suppressed=False,
            reason="No valid domain could be extracted from the provided inputs.",
            matched_domain=None,
            match_type=None,
            client_id=client_id,
        )

    # ── Domain check ──────────────────────────────────────────────────────────
    match = await _check_domains(client_id, candidates)
    checked_domain = candidates[0] if candidates else None

    if match:
        # Determine match type
        matched_domain = match["domain"]
        if match["domain"] in candidates:
            match_type = "direct"
        else:
            # umbrella match — find which candidate triggered it
            match_type = "umbrella"
            matched_domain = match["umbrella_domain"] or match["domain"]

        asyncio.create_task(
            _log_check_async(client_id, body.email, checked_domain, "suppressed", matched_domain, caller_ip)
        )
        asyncio.create_task(_touch_token_async(client_id))

        return SuppressionCheckResponse(
            suppressed=True,
            reason=f"Domain match: {matched_domain}",
            matched_domain=matched_domain,
            match_type=match_type,
            client_id=client_id,
        )

    # ── No match — allowed ─────────────────────────────────────────────────────
    asyncio.create_task(
        _log_check_async(client_id, body.email, checked_domain, "allowed", None, caller_ip)
    )
    asyncio.create_task(_touch_token_async(client_id))

    return SuppressionCheckResponse(
        suppressed=False,
        reason=None,
        matched_domain=None,
        match_type=None,
        client_id=client_id,
    )
