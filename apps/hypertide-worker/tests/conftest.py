"""Test fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture
def ht_active_response():
    """Sample /orders/active body covering each observed enum value."""
    return {
        "success": True,
        "count": 5,
        "orders": [
            {
                "id": "rec_done_paid",
                "domain": "test1.com",
                "status": "Done",
                "paymentStatus": "Paid",
                "subscriptionId": "sub_paid_1",
                "productId": "prod_paid_1",
                "sendingTool": "Email Bison",
                "createdAt": "2026-04-01",
                "organizationName": "Test Org",
                "forwardingDomain": "test.com",
            },
            {
                "id": "rec_done_google",
                "domain": "test2.com",
                "status": "Done",
                "paymentStatus": "Google",
                "subscriptionId": "sub_g_1",
                "productId": "prod_g_1",
                "sendingTool": "Email Bison",
                "createdAt": "2026-04-02",
                "organizationName": "Test Org",
                "forwardingDomain": "test.com",
            },
            {
                "id": "rec_npc",
                "domain": "test3.com",
                "status": "NPC",
                "paymentStatus": "Paid",
                "subscriptionId": "sub_paid_1",
                "productId": "prod_paid_1",
                "sendingTool": "Email Bison",
                "createdAt": "2026-03-01",
                "organizationName": "Test Org",
                "forwardingDomain": "test.com",
            },
            {
                "id": "rec_todo",
                "domain": "test4.com",
                "status": "Todo",
                "paymentStatus": "Google",
                "subscriptionId": "sub_g_2",
                "productId": "prod_g_2",
                "sendingTool": "Email Bison",
                "createdAt": "2026-05-07",
                "organizationName": "Test Org",
                "forwardingDomain": "test.com",
            },
            {
                "id": "rec_in_progress",
                "domain": "test5.com",
                "status": "In progress",
                "paymentStatus": "Paid",
                "subscriptionId": "sub_paid_2",
                "productId": "prod_paid_2",
                "sendingTool": "Email Bison",
                "createdAt": "2026-05-06",
                "organizationName": "Test Org",
                "forwardingDomain": "test.com",
            },
        ],
        "requestId": "req_test",
    }


@pytest.fixture
def verify_revert_response():
    """Sample verify-revert body matching the active records."""
    return {
        "success": True,
        "canRevert": False,
        "summary": {"total": 5, "revertible": 1, "nonRevertible": 4},
        "records": [
            {
                "recordId": "rec_done_paid",
                "domain": "test1.com",
                "subscriptionId": "sub_paid_1",
                "currentStatus": "",
                "cancellationType": "none",
                "toBeCancelled": False,
                "revertible": False,
                "reason": "No cancellation status found",
            },
            {
                "recordId": "rec_done_google",
                "domain": "test2.com",
                "subscriptionId": "sub_g_1",
                "currentStatus": "to_be_cancelled_complete_subscription",
                "cancellationType": "full_subscription",
                "toBeCancelled": True,
                "revertible": True,
                "reason": "Full subscription cancellation is scheduled and can be reverted",
            },
            {
                "recordId": "rec_npc",
                "domain": "test3.com",
                "subscriptionId": "sub_paid_1",
                "currentStatus": "cancelled",
                "cancellationType": "cancelled",
                "toBeCancelled": False,
                "revertible": False,
                "reason": "Subscription is already cancelled in Stripe and cannot be reverted",
            },
        ],
    }
