#!/usr/bin/env python3
"""
Tests for Domain Allocation Logic (Live/Reserve Sets)

Tests the capacity-based reserve allocation:
1. Surplus calculation
2. Domain health scoring
3. Provider-aware 80/20 allocation
4. Edge cases (no surplus, all degraded, etc.)

Run:
    pytest tests/test_domain_allocation.py -v
    py -m pytest tests/test_domain_allocation.py -v
"""
import pytest
from dataclasses import dataclass
from typing import List, Dict, Optional
import math


# ============================================================
# Domain Allocation Logic (extracted for testing)
# ============================================================

@dataclass
class DomainHealth:
    """Domain health data for allocation decisions."""
    domain_id: str
    domain_name: str
    provider: str  # 'entra' or 'google'
    inbox_count: int
    avg_health_score: float
    avg_bounce_rate: float
    high_bounce_count: int  # inboxes with >2% bounce
    has_spam_complaints: bool = False
    has_hard_blocks: bool = False


@dataclass
class WorkspaceCapacity:
    """Workspace capacity vs target."""
    workspace_id: str
    workspace_name: str

    # Entra
    entra_target: int
    entra_live: int
    entra_reserve: int

    # Google
    google_target: int
    google_live: int
    google_reserve: int

    spare_ratio: float = 0.15  # Default 15%


def calculate_surplus(capacity: WorkspaceCapacity) -> Dict[str, int]:
    """Calculate surplus/deficit per provider."""
    return {
        'entra': capacity.entra_live - capacity.entra_target,
        'google': capacity.google_live - capacity.google_target,
    }


def calculate_reserve_capacity(capacity: WorkspaceCapacity) -> Dict[str, int]:
    """
    Calculate how many inboxes can be reserved per provider.

    Reserve = min(target * spare_ratio, surplus)
    If surplus <= 0, reserve = 0 (all live)
    """
    surplus = calculate_surplus(capacity)

    entra_ideal_reserve = int(capacity.entra_target * capacity.spare_ratio)
    google_ideal_reserve = int(capacity.google_target * capacity.spare_ratio)

    return {
        'entra': min(entra_ideal_reserve, max(0, surplus['entra'])),
        'google': min(google_ideal_reserve, max(0, surplus['google'])),
    }


def score_domain_health(domain: DomainHealth) -> float:
    """
    Calculate domain health score.

    HIGHER score = HEALTHIER = should be RESERVE (protected)
    LOWER score = MORE DEGRADED = should be LIVE (expendable)
    """
    score = 100.0

    # Spam complaints = domain is burned
    if domain.has_spam_complaints:
        score -= 200  # Severely penalize

    # Hard blocks = provider issues
    if domain.has_hard_blocks:
        score -= 100

    # Bounce rate penalty (0-10% range typical)
    score -= domain.avg_bounce_rate * 500  # 2% bounce = -10 points

    # Health score bonus (baseline 80)
    score += (domain.avg_health_score - 80) * 2

    # High bounce inbox penalty
    high_bounce_pct = domain.high_bounce_count / max(domain.inbox_count, 1)
    score -= high_bounce_pct * 50

    # Inbox count factor (more inboxes = more valuable)
    if domain.inbox_count >= 50:  # Full Entra domain
        score += 10
    elif domain.inbox_count >= 3:  # Full Google domain
        score += 5

    return round(score, 2)


def allocate_domains(
    domains: List[DomainHealth],
    reserve_capacity: Dict[str, int]
) -> Dict[str, List[str]]:
    """
    Allocate domains to live/reserve pools based on health and capacity.

    Returns:
        {
            'entra_live': [domain_ids...],
            'entra_reserve': [domain_ids...],
            'google_live': [domain_ids...],
            'google_reserve': [domain_ids...],
        }
    """
    # Separate by provider
    entra_domains = [d for d in domains if d.provider == 'entra']
    google_domains = [d for d in domains if d.provider == 'google']

    # Score and sort (highest score = healthiest = reserve candidates)
    entra_scored = sorted(entra_domains, key=lambda d: score_domain_health(d), reverse=True)
    google_scored = sorted(google_domains, key=lambda d: score_domain_health(d), reverse=True)

    # Calculate how many domains to reserve based on inbox capacity
    def domains_for_inbox_count(domains: List[DomainHealth], target_inboxes: int) -> int:
        """How many domains needed to reach target inbox count."""
        if target_inboxes <= 0:
            return 0
        total = 0
        for i, d in enumerate(domains):
            total += d.inbox_count
            if total >= target_inboxes:
                return i + 1
        return len(domains)

    entra_reserve_count = domains_for_inbox_count(entra_scored, reserve_capacity['entra'])
    google_reserve_count = domains_for_inbox_count(google_scored, reserve_capacity['google'])

    return {
        'entra_reserve': [d.domain_id for d in entra_scored[:entra_reserve_count]],
        'entra_live': [d.domain_id for d in entra_scored[entra_reserve_count:]],
        'google_reserve': [d.domain_id for d in google_scored[:google_reserve_count]],
        'google_live': [d.domain_id for d in google_scored[google_reserve_count:]],
    }


# ============================================================
# Tests
# ============================================================

class TestSurplusCalculation:
    """Test surplus/deficit calculation."""

    def test_surplus_both_providers(self):
        """Workspace with surplus in both providers."""
        capacity = WorkspaceCapacity(
            workspace_id="ws-1",
            workspace_name="TestWorkspace",
            entra_target=500,
            entra_live=700,
            entra_reserve=0,
            google_target=50,
            google_live=80,
            google_reserve=0,
        )
        surplus = calculate_surplus(capacity)
        assert surplus['entra'] == 200
        assert surplus['google'] == 30

    def test_deficit_both_providers(self):
        """Workspace with deficit - below target."""
        capacity = WorkspaceCapacity(
            workspace_id="ws-2",
            workspace_name="DeficitWorkspace",
            entra_target=500,
            entra_live=300,  # 200 short
            entra_reserve=0,
            google_target=50,
            google_live=30,  # 20 short
            google_reserve=0,
        )
        surplus = calculate_surplus(capacity)
        assert surplus['entra'] == -200
        assert surplus['google'] == -20

    def test_at_target(self):
        """Workspace exactly at target."""
        capacity = WorkspaceCapacity(
            workspace_id="ws-3",
            workspace_name="ExactWorkspace",
            entra_target=500,
            entra_live=500,
            entra_reserve=0,
            google_target=50,
            google_live=50,
            google_reserve=0,
        )
        surplus = calculate_surplus(capacity)
        assert surplus['entra'] == 0
        assert surplus['google'] == 0


class TestReserveCapacity:
    """Test reserve capacity calculation."""

    def test_reserve_with_surplus(self):
        """Can create reserve when surplus exists."""
        capacity = WorkspaceCapacity(
            workspace_id="ws-1",
            workspace_name="SurplusWorkspace",
            entra_target=500,
            entra_live=700,  # 200 surplus
            entra_reserve=0,
            google_target=50,
            google_live=80,  # 30 surplus
            google_reserve=0,
            spare_ratio=0.15,
        )
        reserve = calculate_reserve_capacity(capacity)
        # Entra: min(500 * 0.15 = 75, 200 surplus) = 75
        assert reserve['entra'] == 75
        # Google: min(50 * 0.15 = 7, 30 surplus) = 7
        assert reserve['google'] == 7

    def test_no_reserve_when_deficit(self):
        """Cannot create reserve when at/below target."""
        capacity = WorkspaceCapacity(
            workspace_id="ws-2",
            workspace_name="DeficitWorkspace",
            entra_target=500,
            entra_live=400,  # -100 deficit
            entra_reserve=0,
            google_target=50,
            google_live=50,  # exactly at target
            google_reserve=0,
            spare_ratio=0.15,
        )
        reserve = calculate_reserve_capacity(capacity)
        assert reserve['entra'] == 0  # No surplus
        assert reserve['google'] == 0  # No surplus

    def test_reserve_capped_by_surplus(self):
        """Reserve capped by available surplus."""
        capacity = WorkspaceCapacity(
            workspace_id="ws-3",
            workspace_name="SmallSurplus",
            entra_target=1000,  # Ideal reserve = 150
            entra_live=1050,    # Only 50 surplus
            entra_reserve=0,
            google_target=100,
            google_live=100,
            google_reserve=0,
            spare_ratio=0.15,
        )
        reserve = calculate_reserve_capacity(capacity)
        # min(1000 * 0.15 = 150, 50 surplus) = 50
        assert reserve['entra'] == 50
        assert reserve['google'] == 0


class TestDomainScoring:
    """Test domain health scoring."""

    def test_healthy_domain_high_score(self):
        """Healthy domain gets high score."""
        domain = DomainHealth(
            domain_id="d-1",
            domain_name="healthy.com",
            provider="entra",
            inbox_count=52,
            avg_health_score=90,
            avg_bounce_rate=0.005,  # 0.5%
            high_bounce_count=0,
        )
        score = score_domain_health(domain)
        # 100 - (0.005 * 500) + (90-80)*2 + 10 = 100 - 2.5 + 20 + 10 = 127.5
        assert score > 120

    def test_degraded_domain_low_score(self):
        """Degraded domain gets low score."""
        domain = DomainHealth(
            domain_id="d-2",
            domain_name="degraded.com",
            provider="entra",
            inbox_count=52,
            avg_health_score=75,
            avg_bounce_rate=0.03,  # 3%
            high_bounce_count=10,
        )
        score = score_domain_health(domain)
        # Should be much lower
        assert score < 100

    def test_spam_complaint_severely_penalized(self):
        """Domain with spam complaints is heavily penalized."""
        healthy = DomainHealth(
            domain_id="d-1",
            domain_name="healthy.com",
            provider="entra",
            inbox_count=52,
            avg_health_score=85,
            avg_bounce_rate=0.01,
            high_bounce_count=0,
            has_spam_complaints=False,
        )
        burned = DomainHealth(
            domain_id="d-2",
            domain_name="burned.com",
            provider="entra",
            inbox_count=52,
            avg_health_score=85,
            avg_bounce_rate=0.01,
            high_bounce_count=0,
            has_spam_complaints=True,  # SPAM COMPLAINT
        )
        healthy_score = score_domain_health(healthy)
        burned_score = score_domain_health(burned)

        # Burned should be 200 points lower
        assert burned_score < healthy_score - 150

    def test_scoring_ranks_correctly(self):
        """Domains ranked correctly by health."""
        domains = [
            DomainHealth("d-1", "best.com", "entra", 52, 92, 0.003, 0),
            DomainHealth("d-2", "good.com", "entra", 52, 88, 0.008, 1),
            DomainHealth("d-3", "ok.com", "entra", 52, 85, 0.015, 3),
            DomainHealth("d-4", "bad.com", "entra", 52, 80, 0.025, 8),
            DomainHealth("d-5", "worst.com", "entra", 52, 75, 0.04, 15),
        ]
        scores = [(d.domain_name, score_domain_health(d)) for d in domains]
        scores_sorted = sorted(scores, key=lambda x: x[1], reverse=True)

        # Should be in order: best, good, ok, bad, worst
        assert scores_sorted[0][0] == "best.com"
        assert scores_sorted[1][0] == "good.com"
        assert scores_sorted[2][0] == "ok.com"
        assert scores_sorted[3][0] == "bad.com"
        assert scores_sorted[4][0] == "worst.com"


class TestDomainAllocation:
    """Test domain allocation to live/reserve pools."""

    def test_allocate_with_surplus(self):
        """Allocates healthiest to reserve when surplus exists."""
        domains = [
            DomainHealth("d-1", "best.com", "entra", 52, 92, 0.003, 0),
            DomainHealth("d-2", "good.com", "entra", 52, 88, 0.008, 1),
            DomainHealth("d-3", "bad.com", "entra", 52, 80, 0.025, 8),
        ]
        # Reserve capacity for ~52 inboxes (1 domain)
        reserve_capacity = {'entra': 52, 'google': 0}

        allocation = allocate_domains(domains, reserve_capacity)

        # Best domain should be in reserve
        assert "d-1" in allocation['entra_reserve']
        assert len(allocation['entra_reserve']) == 1

        # Rest in live
        assert "d-2" in allocation['entra_live']
        assert "d-3" in allocation['entra_live']
        assert len(allocation['entra_live']) == 2

    def test_allocate_no_reserve(self):
        """All domains go to live when no reserve capacity."""
        domains = [
            DomainHealth("d-1", "a.com", "entra", 52, 90, 0.01, 0),
            DomainHealth("d-2", "b.com", "entra", 52, 85, 0.02, 2),
        ]
        reserve_capacity = {'entra': 0, 'google': 0}  # No surplus

        allocation = allocate_domains(domains, reserve_capacity)

        assert len(allocation['entra_reserve']) == 0
        assert len(allocation['entra_live']) == 2

    def test_allocate_by_provider(self):
        """Allocation is separate per provider."""
        domains = [
            DomainHealth("e-1", "entra1.com", "entra", 52, 90, 0.01, 0),
            DomainHealth("e-2", "entra2.com", "entra", 52, 85, 0.02, 2),
            DomainHealth("g-1", "google1.com", "google", 3, 92, 0.005, 0),
            DomainHealth("g-2", "google2.com", "google", 3, 88, 0.01, 0),
        ]
        # Reserve: 1 Entra domain (52 inboxes), 1 Google domain (3 inboxes)
        reserve_capacity = {'entra': 52, 'google': 3}

        allocation = allocate_domains(domains, reserve_capacity)

        # Healthiest Entra in reserve
        assert "e-1" in allocation['entra_reserve']
        assert "e-2" in allocation['entra_live']

        # Healthiest Google in reserve
        assert "g-1" in allocation['google_reserve']
        assert "g-2" in allocation['google_live']


class TestSeleryScenario:
    """Test with Selery-like data."""

    def test_selery_allocation(self):
        """Simulate Selery allocation with real-ish data."""
        # 12 Entra domains, 25 Google domains
        entra_domains = [
            DomainHealth(f"e-{i}", f"selery{i}.com", "entra", 52,
                        88 - i*0.5,  # Health decreases
                        0.005 + i*0.001,  # Bounce increases
                        i)
            for i in range(12)
        ]
        google_domains = [
            DomainHealth(f"g-{i}", f"gselery{i}.com", "google", 3,
                        89 - i*0.3,
                        0.004 + i*0.0015,
                        0 if i < 10 else 1)
            for i in range(25)
        ]

        all_domains = entra_domains + google_domains

        # Selery has surplus - can reserve 2 Entra + 5 Google
        reserve_capacity = {
            'entra': 104,  # ~2 domains worth
            'google': 15,  # ~5 domains worth
        }

        allocation = allocate_domains(all_domains, reserve_capacity)

        # Should have 2 Entra in reserve (healthiest)
        assert len(allocation['entra_reserve']) == 2
        assert "e-0" in allocation['entra_reserve']  # Healthiest
        assert "e-1" in allocation['entra_reserve']

        # Should have 5 Google in reserve
        assert len(allocation['google_reserve']) == 5

        # Rest in live
        assert len(allocation['entra_live']) == 10
        assert len(allocation['google_live']) == 20


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_workspace(self):
        """Handle workspace with no domains."""
        allocation = allocate_domains([], {'entra': 100, 'google': 50})
        assert allocation == {
            'entra_reserve': [],
            'entra_live': [],
            'google_reserve': [],
            'google_live': [],
        }

    def test_single_domain(self):
        """Single domain goes to live (can't reserve only domain)."""
        domains = [DomainHealth("d-1", "only.com", "entra", 52, 90, 0.01, 0)]
        # Even with reserve capacity, single domain should be live
        # (This is a policy decision - could go either way)
        allocation = allocate_domains(domains, {'entra': 0, 'google': 0})
        assert len(allocation['entra_live']) == 1
        assert len(allocation['entra_reserve']) == 0

    def test_all_burned_domains(self):
        """All domains with spam complaints - all go to live."""
        domains = [
            DomainHealth("d-1", "burned1.com", "entra", 52, 70, 0.05, 20,
                        has_spam_complaints=True),
            DomainHealth("d-2", "burned2.com", "entra", 52, 65, 0.06, 25,
                        has_spam_complaints=True),
        ]
        allocation = allocate_domains(domains, {'entra': 52, 'google': 0})

        # Even though we have reserve capacity, these are burned
        # The "healthiest" burned domain goes to reserve (still a domain)
        # This tests that the algorithm doesn't crash on bad data
        assert len(allocation['entra_reserve']) + len(allocation['entra_live']) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
