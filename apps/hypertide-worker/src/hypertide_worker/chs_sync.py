"""Subscription-keyed sync into client_hypertide_subscriptions (chs).

Step 5 of docs/plans/hypertide-data-model-and-change-tracking.md.

What this replaces: the legacy "no DB domain row = friends-and-family" branch
in audit.py. That heuristic could never tell a real new customer from an
operational gap. Now every HT subscription in /orders/active gets a chs row,
classified by sending_tool per DECISION 5 (revised):
  - Email Bison or Instantly.ai → client_status='client'
  - Smartlead.ai or unknown      → client_status='friends_and_family'

The classification is positive evidence (sending_tool) rather than
absence-of-evidence (no DB match).

What this does NOT do:
  - Update client_status of existing clients (operator-owned decision).
  - Re-point existing chs.client_id (operator may have manually merged).
  - Touch domains.* (audit.py still owns the per-record snapshot UPDATE).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


# Tools whose HT subscriptions are part of CharmOS-managed inbox infrastructure.
# Subs on these tools default to client_status='client' on first sight; all other
# tools (and missing tool) default to 'friends_and_family' (safe failure).
_OPERATIONAL_TOOLS: frozenset[str] = frozenset({"Email Bison", "Instantly.ai"})


@dataclass
class ChsSyncResult:
    """Per-run counters. Subscription-level, not record-level."""

    subs_seen: int = 0                       # unique sub_ids in this audit pass
    already_bound: int = 0                   # had a chs row before this pass
    last_seen_touched: int = 0               # UPDATE chs SET last_seen_at = NOW()
    org_name_refreshed: int = 0              # UPDATE when HT renamed an org
    new_chs_existing_client: int = 0         # NEW chs into an EXISTING clients row
    new_clients_client_status: int = 0       # NEW clients row, client_status='client'
    new_clients_fnf: int = 0                 # NEW clients row, client_status='friends_and_family'
    skipped_no_sub_id: int = 0               # HT records with no subscriptionId (shouldn't happen)
    new_client_examples: list[dict[str, Any]] = field(default_factory=list)


def classify_first_sync_tool(sending_tool: str | None) -> str:
    """Map a single sending_tool to a client_status. Pure; trivially testable."""
    if sending_tool and sending_tool in _OPERATIONAL_TOOLS:
        return "client"
    return "friends_and_family"


def classify_first_sync_from_tools(tools: set[str]) -> str:
    """
    Multi-tool dispatch. Three HT subs in the 2026-05-06 snapshot had records
    with multiple sending_tools (Root Access x2 EB+Smartlead, Stable Kernel
    Network HT EB+Instantly). Rule: if ANY tool is operational, the sub is
    operational. Smartlead-only (and empty) fall through to F&F.
    """
    if tools & _OPERATIONAL_TOOLS:
        return "client"
    return "friends_and_family"


def pick_primary_tool(tools: set[str]) -> str | None:
    """
    For chs.notes — surface the most-authoritative tool of a sub's record set.
    Priority: Email Bison > Instantly.ai > Smartlead.ai > anything else.
    None on empty input.
    """
    for preferred in ("Email Bison", "Instantly.ai", "Smartlead.ai"):
        if preferred in tools:
            return preferred
    return next(iter(sorted(tools))) if tools else None


@dataclass(frozen=True)
class _SubAggregate:
    """Collapsed view of all HT records sharing one subscription_id."""

    sub_id: str
    organization_name: str | None
    sending_tools: frozenset[str]
    earliest_created_at: str | None        # YYYY-MM-DD per HT's date format


def aggregate_by_sub(ht_records: list[dict[str, Any]]) -> dict[str, _SubAggregate]:
    """Group HT records by subscription_id. Skips records without a sub_id."""
    by_sub: dict[str, dict[str, Any]] = {}
    for rec in ht_records:
        sid = rec.get("subscriptionId")
        if not sid:
            continue
        slot = by_sub.setdefault(sid, {"orgs": set(), "tools": set(), "earliest": None})
        if org := rec.get("organizationName"):
            slot["orgs"].add(org.strip())
        if tool := rec.get("sendingTool"):
            slot["tools"].add(tool)
        ca = rec.get("createdAt")
        if ca and (slot["earliest"] is None or ca < slot["earliest"]):
            slot["earliest"] = ca
    out: dict[str, _SubAggregate] = {}
    for sid, slot in by_sub.items():
        # Pick the longest org_name as canonical (HT often has variants like
        # "Inkd" + "Inkd Stores" — longest tends to be the more specific
        # marketing variant the operator named the sub for in Stripe).
        orgs: set[str] = slot["orgs"]
        canonical_org = max(orgs, key=len) if orgs else None
        out[sid] = _SubAggregate(
            sub_id=sid,
            organization_name=canonical_org,
            sending_tools=frozenset(slot["tools"]),
            earliest_created_at=slot["earliest"],
        )
    return out


async def ensure_chs_rows(
    conn: asyncpg.Connection,
    ht_records: list[dict[str, Any]],
    *,
    apply: bool = False,
    notes_prefix: str | None = None,
) -> ChsSyncResult:
    """
    Walk every HT subscription in this pass and reconcile chs:
      - existing chs row → touch last_seen_at; refresh organization_name if HT renamed it
      - missing chs row  → classify by sending_tool, create chs (and a new clients row if needed)

    apply=False is read-only; counters are populated, no writes.

    notes_prefix defaults to "synced YYYY-MM-DD"; appended with sending_tool
    for each new chs row.
    """
    result = ChsSyncResult()
    now = datetime.now()                                 # naive — used only for notes prefix date
    if notes_prefix is None:
        notes_prefix = f"synced {now.date().isoformat()}"

    sub_aggregates = aggregate_by_sub(ht_records)
    result.subs_seen = len(sub_aggregates)
    result.skipped_no_sub_id = sum(1 for r in ht_records if not r.get("subscriptionId"))
    if not sub_aggregates:
        return result

    # --- Discover existing chs bindings -------------------------------------
    existing_rows = await conn.fetch(
        "SELECT subscription_id, organization_name "
        "FROM client_hypertide_subscriptions WHERE subscription_id = ANY($1::text[])",
        list(sub_aggregates.keys()),
    )
    existing_map: dict[str, str | None] = {r["subscription_id"]: r["organization_name"] for r in existing_rows}
    result.already_bound = len(existing_map)

    known_subs = [sid for sid in sub_aggregates if sid in existing_map]
    new_subs = [sid for sid in sub_aggregates if sid not in existing_map]

    # --- Branch 1: known subs — touch + maybe rename ------------------------
    if known_subs:
        result.last_seen_touched = len(known_subs)
        renamed: list[tuple[str, str]] = []
        for sid in known_subs:
            agg = sub_aggregates[sid]
            prior = existing_map.get(sid)
            if agg.organization_name and agg.organization_name != prior:
                renamed.append((sid, agg.organization_name))
        result.org_name_refreshed = len(renamed)
        if apply:
            await conn.execute(
                "UPDATE client_hypertide_subscriptions SET last_seen_at = NOW() "
                "WHERE subscription_id = ANY($1::text[])",
                known_subs,
            )
            if renamed:
                await conn.executemany(
                    "UPDATE client_hypertide_subscriptions SET organization_name = $1 "
                    "WHERE subscription_id = $2",
                    [(name, sid) for sid, name in renamed],
                )

    # --- Branch 2: new subs — classify + INSERT -----------------------------
    for sid in new_subs:
        agg = sub_aggregates[sid]
        status = classify_first_sync_from_tools(set(agg.sending_tools))
        tool = pick_primary_tool(set(agg.sending_tools))
        if status == "client":
            result.new_clients_client_status += 1
        else:
            result.new_clients_fnf += 1
        result.new_client_examples.append({
            "sub_id": sid,
            "org_name": agg.organization_name,
            "sending_tool": tool,
            "client_status": status,
            "created_at": agg.earliest_created_at,
        })
        if apply:
            await _insert_new_client_and_chs(
                conn,
                sub_id=sid,
                org_name=agg.organization_name or "(no org)",
                client_status=status,
                created_at=agg.earliest_created_at,
                sending_tool=tool,
                notes_prefix=notes_prefix,
            )

    if apply and new_subs:
        logger.info(
            "chs_sync: created %d new chs (%d client, %d F&F) for first-sight subs",
            len(new_subs), result.new_clients_client_status, result.new_clients_fnf,
        )

    return result


async def _insert_new_client_and_chs(
    conn: asyncpg.Connection,
    *,
    sub_id: str,
    org_name: str,
    client_status: str,
    created_at: str | None,
    sending_tool: str | None,
    notes_prefix: str,
) -> None:
    """
    Atomic per-sub: INSERT a new clients row, then INSERT the chs binding row
    pointing at it. CTE keeps it one round-trip and one transaction.

    ON CONFLICT on chs.subscription_id is a belt-and-suspenders idempotency
    guard — the caller already filtered by existing chs rows, but a parallel
    audit could race here.
    """
    notes = f"{notes_prefix}, sending_tool={sending_tool or 'unknown'}"
    await conn.execute(
        """
        WITH new_client AS (
            INSERT INTO clients (name, client_status, primary_hypertide_organization_name)
            VALUES ($1, $2, $1)
            RETURNING id
        )
        INSERT INTO client_hypertide_subscriptions
            (subscription_id, client_id, subscription_created_at, organization_name, notes)
        SELECT $3, id, $4::date, $1, $5 FROM new_client
        ON CONFLICT (subscription_id) DO NOTHING
        """,
        org_name,
        client_status,
        sub_id,
        created_at,
        notes,
    )
