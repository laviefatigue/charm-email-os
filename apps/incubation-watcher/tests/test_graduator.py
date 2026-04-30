"""Smoke tests for graduator. Full test suite is a v1.1 follow-up."""
from __future__ import annotations

from uuid import uuid4

import pytest

from incubation_watcher.db import GraduationCandidate
from incubation_watcher.eb_client import EmailBisonAPIError
from incubation_watcher.graduator import (
    LIVE_TAG,
    RESERVE_TAG,
    target_pool_for_esp,
)


class TestTargetPoolForEsp:
    """ESP routing: the ONE deterministic decision in the graduator."""

    def test_microsoft_routes_to_live(self) -> None:
        assert target_pool_for_esp("microsoft") == LIVE_TAG

    def test_gmail_routes_to_reserve(self) -> None:
        assert target_pool_for_esp("gmail") == RESERVE_TAG

    def test_unknown_esp_routes_to_reserve(self) -> None:
        # Conservative default — unknown ESP goes to reserve, not live.
        # Reserve = bench, awaits promotion. Live = active sending.
        # If we got the ESP wrong, reserve is the safer place.
        assert target_pool_for_esp(None) == RESERVE_TAG
        assert target_pool_for_esp("zoho") == RESERVE_TAG
        assert target_pool_for_esp("") == RESERVE_TAG


class TestGraduationCandidate:
    """Dataclass shape checks — these protect downstream code."""

    def test_candidate_constructs(self) -> None:
        c = GraduationCandidate(
            sender_id=uuid4(),
            email_address="x@y.com",
            emailbison_account_id=12345,
            esp="gmail",
            warmup_enabled_since_iso="2026-04-14",
            business_days_elapsed=14,
        )
        assert c.email_address == "x@y.com"
        assert c.business_days_elapsed == 14

    def test_candidate_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError
        c = GraduationCandidate(
            sender_id=uuid4(),
            email_address="x@y.com",
            emailbison_account_id=1,
            esp="gmail",
            warmup_enabled_since_iso="2026-04-14",
            business_days_elapsed=14,
        )
        with pytest.raises(FrozenInstanceError):
            c.email_address = "z@y.com"  # type: ignore[misc]


class TestEmailBisonAPIError:
    """Exception model — status_code drives caller behavior."""

    def test_404_distinguishable(self) -> None:
        e = EmailBisonAPIError(404, "not found")
        assert e.status_code == 404

    def test_transient_distinguishable(self) -> None:
        e = EmailBisonAPIError(503, "service unavailable")
        assert e.status_code == 503

    def test_transport_failure_status_zero(self) -> None:
        e = EmailBisonAPIError(0, "connection refused")
        assert e.status_code == 0
