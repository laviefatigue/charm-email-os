"""
Pure-function unit tests for the post-2026-05-04 lifetime-rate kill rule.

No Postgres, no Docker, no fixtures — just the rule logic in isolation.
DB-integration coverage of the same boundary cases lives in
tests/test_kill_rule_lifetime.py.

Plan reference: docs/plans/kill-rule-rate-based-rewrite.md
"""
from __future__ import annotations

import pytest

from sync_modules.health_checks import evaluate_lifetime_rule


# ──────────────────────────────────────────────────────────────────────────
# Boundary table from the plan doc.
# Format: (complaints, sends, hard_bounces, expected_trigger)
# expected_trigger=None means "rule should not fire"
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "complaints,sends,hard,expected_trigger",
    [
        # Spam complaint trumps everything, regardless of volume.
        (1, 0,    0,   'spam_complaint'),
        (1, 1500, 0,   'spam_complaint'),
        (5, 100,  100, 'spam_complaint'),
        # Below 20-send floor — skip even if rate is catastrophic.
        (0, 0,    0,   None),
        (0, 19,   1,   None),   # 5.3% but under floor
        (0, 19,   19,  None),   # 100% bounce rate but no signal — too few sends
        # Exactly 5% must NOT kill (rule is strictly > 5%).
        (0, 100,  5,   None),   # 5.0%
        (0, 20,   1,   None),   # 5.0%
        (0, 1500, 75,  None),   # 5.0%
        # Over 5% on small denominator → kill.
        (0, 20,   2,   'hard_bounce_rate_lifetime'),    # 10.0%
        (0, 25,   2,   'hard_bounce_rate_lifetime'),    # 8.0%
        (0, 25,   1,   None),                           # 4.0%
        # Mature inbox shapes (typical Charm fleet — 700-1600 lifetime sends).
        (0, 1500, 50,  None),                           # 3.3%
        (0, 1500, 80,  'hard_bounce_rate_lifetime'),    # 5.3%
        (0, 1500, 100, 'hard_bounce_rate_lifetime'),    # 6.7%
        # Clean inbox at any volume → safe.
        (0, 200,  0,   None),
        (0, 5000, 0,   None),
        # Stable Kernel Market Research case from the audit — should kill.
        (0, 21,   4,   'hard_bounce_rate_lifetime'),    # 19.05% — Mary Elzey
    ],
)
def test_lifetime_rule_boundaries(complaints, sends, hard, expected_trigger):
    verdict = evaluate_lifetime_rule(complaints, sends, hard)
    if expected_trigger is None:
        assert verdict is None, (
            f"Expected no kill for complaints={complaints} sends={sends} "
            f"hard={hard}, got {verdict}"
        )
    else:
        assert verdict is not None, (
            f"Expected {expected_trigger} for complaints={complaints} "
            f"sends={sends} hard={hard}, got None"
        )
        assert verdict[0] == expected_trigger


def test_lifetime_rule_value_and_threshold_shape():
    """The (value, threshold) tuple is what kill_queue.trigger_value/_threshold use."""
    # Spam: value is the complaint count, threshold is spam_threshold (1).
    v, val, thr = evaluate_lifetime_rule(complaints=3, sends=100, hard_bounces=0)
    assert v == 'spam_complaint'
    assert val == 3.0
    assert thr == 1.0

    # Rate: value is the fractional rate, threshold is rate_threshold (0.05).
    v, val, thr = evaluate_lifetime_rule(complaints=0, sends=100, hard_bounces=10)
    assert v == 'hard_bounce_rate_lifetime'
    assert val == pytest.approx(0.10)
    assert thr == pytest.approx(0.05)


def test_lifetime_rule_custom_thresholds():
    """Threshold knobs are tunable per-call — env vars wire through these."""
    # Tighten the rate threshold to 2% — 3% rate now kills.
    v = evaluate_lifetime_rule(
        complaints=0, sends=100, hard_bounces=3, rate_threshold=0.02
    )
    assert v[0] == 'hard_bounce_rate_lifetime'

    # Loosen the floor — eligible at 10 sends instead of 20.
    v = evaluate_lifetime_rule(
        complaints=0, sends=15, hard_bounces=2, min_sends=10
    )
    assert v[0] == 'hard_bounce_rate_lifetime'  # 13.3% > 5%

    # Tighten the spam threshold — 1 complaint no longer fires when threshold=2.
    v = evaluate_lifetime_rule(
        complaints=1, sends=100, hard_bounces=0, spam_threshold=2
    )
    assert v is None


def test_lifetime_rule_division_by_zero_safe():
    """sends=0 must not raise ZeroDivisionError."""
    assert evaluate_lifetime_rule(complaints=0, sends=0, hard_bounces=0) is None
    # Even with bounces > 0, sends=0 is below the floor and skips.
    assert evaluate_lifetime_rule(complaints=0, sends=0, hard_bounces=5) is None


def test_lifetime_rule_inflation_immunity():
    """Regression test for the 2026-04-14 Barrena mass-kill.

    Prior bug: rolling _24h counter accumulated when reset job failed,
    eventually crossing thresholds on healthy inboxes. The lifetime rule
    has no rolling counter — both numerator and denominator are
    monotonic-increasing lifetime totals. Inflation is impossible.

    This test enshrines the rule's correctness on the exact inbox shapes
    that were falsely killed: 700-1600 lifetime sends with healthy bounce
    rates (0.5-2.7%). All must read as safe.
    """
    safe_cases = [
        (0, 1615, 8),    # d.fiori@joinguardare.com — 0.50%
        (0, 1602, 10),   # d.fiori@meetguardare.com — 0.62%
        (0, 1577, 19),   # d.fiori@useguardare.com — 1.20%
        (0, 1573, 26),   # dane@useguardare.com — 1.65%
        (0, 730,  3),    # d.fiori@streamguardare.com — 0.41%
        (0, 1496, 11),   # l.dawson@fixguardare.com — 0.74%
    ]
    for complaints, sends, hard in safe_cases:
        verdict = evaluate_lifetime_rule(complaints, sends, hard)
        rate = hard / sends * 100
        assert verdict is None, (
            f"Barrena regression: {sends} sends, {hard} bounces ({rate:.2f}%) "
            f"must not kill, got {verdict}"
        )
