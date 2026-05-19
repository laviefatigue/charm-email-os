"""Branch coverage for change_detector verdict classification.

The DB-touching detection logic (detect_status_changes) is integration-tested
in prod (idempotent — re-runs produce no-ops). This file covers the pure
verdict-classification decision tree.
"""

import pytest

from hypertide_worker.change_detector import classify_verdict


@pytest.mark.parametrize(
    "rows,expected_verdict,expected_reasons",
    [
        # No domain rows for this client at all → can't evaluate
        ([], "pending", []),

        # Client has domains but none have verdict columns populated
        # (this happens when burns predate migration 125, or when no burn fired)
        ([{"qualifies_for_cancellation_at": None, "qualifies_for_cancellation_reason": None}],
         "unjustified", []),

        # Single domain with a verdict → justified
        ([{"qualifies_for_cancellation_at": "2026-04-01", "qualifies_for_cancellation_reason": "spam_complaint"}],
         "justified", ["spam_complaint"]),

        # Multiple domains, mixed verdicts — single positive evidence is enough
        (
            [
                {"qualifies_for_cancellation_at": None, "qualifies_for_cancellation_reason": None},
                {"qualifies_for_cancellation_at": "2026-04-01", "qualifies_for_cancellation_reason": "workspace_circuit_breaker"},
            ],
            "justified",
            ["workspace_circuit_breaker"],
        ),

        # Multiple positive verdicts → reasons deduplicated and sorted
        (
            [
                {"qualifies_for_cancellation_at": "2026-04-01", "qualifies_for_cancellation_reason": "spam_complaint"},
                {"qualifies_for_cancellation_at": "2026-04-02", "qualifies_for_cancellation_reason": "hard_bounce_rate_lifetime"},
                {"qualifies_for_cancellation_at": "2026-04-03", "qualifies_for_cancellation_reason": "spam_complaint"},
            ],
            "justified",
            ["hard_bounce_rate_lifetime", "spam_complaint"],
        ),

        # Burn fired but reason field is empty (defensive — shouldn't happen but)
        ([{"qualifies_for_cancellation_at": "2026-04-01", "qualifies_for_cancellation_reason": ""}],
         "justified", []),
        ([{"qualifies_for_cancellation_at": "2026-04-01", "qualifies_for_cancellation_reason": None}],
         "justified", []),
    ],
)
def test_classify_verdict(rows, expected_verdict, expected_reasons):
    verdict, reasons = classify_verdict(rows)
    assert verdict == expected_verdict
    assert reasons == expected_reasons


def test_classify_verdict_reasons_are_sorted_deterministically():
    """Reasons list must be deterministic for downstream consumers (event row,
    Slack alerts) — same input = same array order."""
    rows = [
        {"qualifies_for_cancellation_at": "2026-04-01", "qualifies_for_cancellation_reason": "zzz_late"},
        {"qualifies_for_cancellation_at": "2026-04-01", "qualifies_for_cancellation_reason": "aaa_early"},
        {"qualifies_for_cancellation_at": "2026-04-01", "qualifies_for_cancellation_reason": "mmm_middle"},
    ]
    _, reasons = classify_verdict(rows)
    assert reasons == ["aaa_early", "mmm_middle", "zzz_late"]
