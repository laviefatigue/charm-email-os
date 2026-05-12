"""Tests for backfill helpers that touch production-schema constraints."""
from __future__ import annotations

import pytest

from hypertide_worker.backfill import (
    _ct_to_str,
    _infer_infrastructure_type,
    _infer_workspace_id,
)


# --- _infer_infrastructure_type: must match the CHECK constraint exactly ----


@pytest.mark.parametrize(
    "payment,expected",
    [
        ("Paid", "entra"),
        ("Google", "google"),
        ("Google-Solo", "google"),
        ("Unknown", None),
        ("", None),
        (None, None),
    ],
)
def test_infer_infrastructure_type(payment, expected):
    """The domains.infrastructure_type CHECK accepts only 'entra' | 'google' | NULL."""
    assert _infer_infrastructure_type(payment) == expected


# --- _ct_to_str: defensive against None revert ---------------------------------


def test_ct_to_str_with_none():
    assert _ct_to_str(None) is None


def test_ct_to_str_with_value():
    assert _ct_to_str({"cancellationType": "full_subscription"}) == "full_subscription"


def test_ct_to_str_missing_field():
    assert _ct_to_str({}) == "none"


def test_ct_to_str_empty_string():
    assert _ct_to_str({"cancellationType": ""}) == "none"


# --- _infer_workspace_id: suffix + forwarding-domain heuristic -----------------


def _ws(*names: str) -> dict[str, int]:
    """Build a mock ws_by_name catalog."""
    return {name: i + 1 for i, name in enumerate(names)}


def test_workspace_id_suffix_match_spout():
    rec = {"domain": "boostspoutwater.com", "forwardingDomain": ""}
    ws = _ws("Spout", "Selery")
    assert _infer_workspace_id(rec, ws) == 1


def test_workspace_id_suffix_match_search_atlas():
    rec = {"domain": "growsearchatlas.com", "forwardingDomain": ""}
    ws = _ws("Search Atlas")
    assert _infer_workspace_id(rec, ws) == 1


def test_workspace_id_forwarding_stable_kernel_mr():
    """forwardingDomain heuristic routes SKMR-flagged records to the MR workspace."""
    rec = {
        "domain": "anything.com",
        "forwardingDomain": "stablekernel.com/services/market-research",
    }
    ws = _ws("Stable Kernel", "Stable Kernel Market Research")
    assert _infer_workspace_id(rec, ws) == 2


def test_workspace_id_forwarding_stable_kernel():
    rec = {"domain": "anything.com", "forwardingDomain": "stablekernel.com"}
    ws = _ws("Stable Kernel", "Stable Kernel Market Research")
    assert _infer_workspace_id(rec, ws) == 1


def test_workspace_id_unresolvable_returns_none():
    """When no heuristic matches, return None — backfill must skip these."""
    rec = {"domain": "unknown.com", "forwardingDomain": "different.com"}
    ws = _ws("Charm", "Spout")
    assert _infer_workspace_id(rec, ws) is None


def test_workspace_id_apostrophe_match_inkd():
    """Ink'd (with apostrophe) must match the inkdstores suffix."""
    rec = {"domain": "anyinkdstores.com", "forwardingDomain": ""}
    ws = _ws("Ink'd")
    assert _infer_workspace_id(rec, ws) == 1
