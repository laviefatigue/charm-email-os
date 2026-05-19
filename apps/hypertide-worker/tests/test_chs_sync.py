"""Branch coverage for chs_sync first-sync dispatch + record aggregation.

DB-touching paths (ensure_chs_rows actual writes) are not covered here —
they share their SQL shape with scripts/seed_client_hypertide_subscriptions.py
which battle-tested the same CTE pattern in prod 2026-05-18 (211 rows).
This file covers the pure decision-tree + aggregation logic that the worker
will run on every audit pass.
"""
from __future__ import annotations

import pytest

from hypertide_worker.chs_sync import (
    aggregate_by_sub,
    classify_first_sync_from_tools,
    classify_first_sync_tool,
    pick_primary_tool,
)

# --- classify_first_sync_tool ---------------------------------------------------


@pytest.mark.parametrize(
    "tool,expected",
    [
        ("Email Bison", "client"),
        ("Instantly.ai", "client"),
        ("Smartlead.ai", "friends_and_family"),
        ("Lemlist", "friends_and_family"),         # unknown tool -> F&F (safe default)
        ("", "friends_and_family"),                # empty -> F&F
        (None, "friends_and_family"),              # missing -> F&F
    ],
)
def test_classify_first_sync_tool(tool, expected):
    assert classify_first_sync_tool(tool) == expected


# --- classify_first_sync_from_tools (multi-tool dispatch) ----------------------


@pytest.mark.parametrize(
    "tools,expected",
    [
        ({"Email Bison"}, "client"),
        ({"Instantly.ai"}, "client"),
        ({"Smartlead.ai"}, "friends_and_family"),
        (set(), "friends_and_family"),
        ({"Email Bison", "Smartlead.ai"}, "client"),         # Root Access anomaly — EB wins
        ({"Email Bison", "Instantly.ai"}, "client"),         # Stable Kernel anomaly — both ours
        ({"Smartlead.ai", "Lemlist"}, "friends_and_family"), # no operational tool present
        ({"Unknown"}, "friends_and_family"),
    ],
)
def test_classify_first_sync_from_tools(tools, expected):
    assert classify_first_sync_from_tools(tools) == expected


# --- pick_primary_tool ---------------------------------------------------------


def test_pick_primary_tool_empty_returns_none():
    assert pick_primary_tool(set()) is None


def test_pick_primary_tool_eb_wins_over_smartlead():
    """EB ranks above Smartlead in the priority list."""
    assert pick_primary_tool({"Smartlead.ai", "Email Bison"}) == "Email Bison"


def test_pick_primary_tool_eb_wins_over_instantly():
    assert pick_primary_tool({"Instantly.ai", "Email Bison"}) == "Email Bison"


def test_pick_primary_tool_instantly_over_smartlead():
    assert pick_primary_tool({"Smartlead.ai", "Instantly.ai"}) == "Instantly.ai"


def test_pick_primary_tool_unknown_falls_through():
    """Sole unknown tool returns itself rather than None."""
    assert pick_primary_tool({"Lemlist"}) == "Lemlist"


def test_pick_primary_tool_single_smartlead():
    assert pick_primary_tool({"Smartlead.ai"}) == "Smartlead.ai"


# --- aggregate_by_sub ----------------------------------------------------------


def _rec(sub_id: str, *, domain: str = "x.com", org: str | None = "Org", tool: str | None = "Email Bison", created: str | None = "2025-06-01") -> dict:
    return {
        "id": f"rec_{sub_id}_{domain}",
        "subscriptionId": sub_id,
        "domain": domain,
        "organizationName": org,
        "sendingTool": tool,
        "createdAt": created,
    }


def test_aggregate_skips_records_without_sub_id():
    """HT records without a subscriptionId are dropped, not crashed on."""
    records = [_rec("sub_1"), {"id": "rec_no_sub", "domain": "y.com"}]
    out = aggregate_by_sub(records)
    assert set(out) == {"sub_1"}


def test_aggregate_picks_earliest_created_at():
    """Multiple records per sub collapse to earliest createdAt — the historical anchor."""
    records = [
        _rec("sub_1", domain="a.com", created="2025-09-01"),
        _rec("sub_1", domain="b.com", created="2025-06-15"),   # earliest
        _rec("sub_1", domain="c.com", created="2025-12-01"),
    ]
    out = aggregate_by_sub(records)
    assert out["sub_1"].earliest_created_at == "2025-06-15"


def test_aggregate_collects_multi_tool_set():
    """Root-Access-style sub: records spanning EB + Smartlead get both tools in the set."""
    records = [
        _rec("sub_1", tool="Email Bison"),
        _rec("sub_1", tool="Smartlead.ai", domain="a.com"),
    ]
    out = aggregate_by_sub(records)
    assert out["sub_1"].sending_tools == frozenset({"Email Bison", "Smartlead.ai"})


def test_aggregate_picks_longest_org_name_as_canonical():
    """When HT has variant org_names per sub (Inkd / Inkd Stores), longer wins."""
    records = [
        _rec("sub_1", org="Inkd"),
        _rec("sub_1", org="Inkd Stores", domain="a.com"),
    ]
    out = aggregate_by_sub(records)
    assert out["sub_1"].organization_name == "Inkd Stores"


def test_aggregate_strips_whitespace_from_org_names():
    """HT data has trailing-space orgs ('Root Access ' from prod snapshot)."""
    records = [_rec("sub_1", org="Root Access ")]
    out = aggregate_by_sub(records)
    assert out["sub_1"].organization_name == "Root Access"


def test_aggregate_handles_missing_optional_fields():
    """A record with no org / tool / createdAt should still be aggregated, with Nones."""
    records = [{
        "id": "rec1",
        "subscriptionId": "sub_1",
        "domain": "x.com",
    }]
    out = aggregate_by_sub(records)
    assert out["sub_1"].organization_name is None
    assert out["sub_1"].sending_tools == frozenset()
    assert out["sub_1"].earliest_created_at is None


def test_aggregate_groups_distinct_subs_separately():
    records = [_rec("sub_1"), _rec("sub_2"), _rec("sub_1", domain="b.com")]
    out = aggregate_by_sub(records)
    assert set(out) == {"sub_1", "sub_2"}
