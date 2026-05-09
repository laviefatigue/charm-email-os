"""Branch coverage for classifier.classify(). Decision tree must remain stable."""
from __future__ import annotations

import pytest

from hypertide_worker.classifier import (
    Classification,
    HTState,
    classify,
    expected_inbox_count,
)


def _ht(domain: str = "x.com", status: str = "Done", payment: str = "Paid") -> dict:
    return {
        "id": "rec1",
        "domain": domain,
        "status": status,
        "paymentStatus": payment,
        "subscriptionId": "sub_1",
        "productId": "prod_1",
    }


def _rev(cancellation_type: str = "none", current_status: str = "", to_be_cancelled: bool = False) -> dict:
    return {
        "recordId": "rec1",
        "domain": "x.com",
        "cancellationType": cancellation_type,
        "currentStatus": current_status,
        "toBeCancelled": to_be_cancelled,
    }


# --- Each branch in classify() --------------------------------------------------


def test_done_no_revert():
    """Live record, no revert info — treated as live."""
    c = classify(_ht(), None)
    assert c.state is HTState.LIVE
    assert c.is_subscribed is True
    assert c.is_to_be_cancelled is False


def test_done_with_none_revert():
    c = classify(_ht(), _rev())
    assert c.state is HTState.LIVE
    assert c.is_subscribed is True


def test_cancelled_terminal():
    c = classify(_ht(status="NPC"), _rev(cancellation_type="cancelled", current_status="cancelled"))
    assert c.state is HTState.CANCELLED
    assert c.is_subscribed is False
    assert c.is_to_be_cancelled is False


def test_executed_terminal():
    c = classify(
        _ht(status="NPC"),
        _rev(cancellation_type="executed", current_status="partial_product_cancelled_at_2025-12-23"),
    )
    assert c.state is HTState.CANCELLED
    assert c.is_subscribed is False


def test_full_subscription_scheduled():
    c = classify(
        _ht(status="Done"),
        _rev(
            cancellation_type="full_subscription",
            current_status="to_be_cancelled_complete_subscription",
            to_be_cancelled=True,
        ),
    )
    assert c.state is HTState.SCHEDULED_CANCEL
    assert c.is_subscribed is True
    assert c.is_to_be_cancelled is True


def test_partial_product_scheduled():
    c = classify(
        _ht(status="Done"),
        _rev(
            cancellation_type="partial_product",
            current_status="partial_product_cancellation_date:2026-05-05T18:13:15.000Z",
            to_be_cancelled=True,
        ),
    )
    assert c.state is HTState.SCHEDULED_CANCEL
    assert c.is_subscribed is True
    assert c.is_to_be_cancelled is True


def test_unknown_drift():
    """HT says NPC but Stripe says active — drift case."""
    c = classify(_ht(status="NPC"), _rev(cancellation_type="unknown", current_status="active"))
    assert c.state is HTState.DRIFT
    assert c.is_subscribed is True
    assert c.is_to_be_cancelled is False


def test_npc_none_undocumented():
    c = classify(_ht(status="NPC"), _rev(cancellation_type="none"))
    assert c.state is HTState.NPC_NONE
    assert c.is_subscribed is False  # treat as effectively cancelled


def test_in_flight_todo():
    c = classify(_ht(status="Todo"), _rev())
    assert c.state is HTState.IN_FLIGHT
    assert c.is_subscribed is True


def test_in_flight_in_progress():
    c = classify(_ht(status="In progress"), _rev())
    assert c.state is HTState.IN_FLIGHT
    assert c.is_subscribed is True


def test_other_unknown_status():
    c = classify(_ht(status="WeirdNewState"), _rev())
    assert c.state is HTState.OTHER


# --- expected_inbox_count branches ---------------------------------------------


@pytest.mark.parametrize(
    "payment,expected",
    [
        ("Paid", 52),
        ("Google", 3),
        ("Google-Solo", 3),
        ("Unknown", None),
        ("", None),
        (None, None),
    ],
)
def test_expected_inbox_count(payment, expected):
    assert expected_inbox_count(payment) == expected
