"""Tests for shadow-validation comparison logic.

The set-difference math is what acceptance hinges on — if these are wrong,
operator gets misleading "parity" reports and we'd cut over a buggy watcher.
"""
from __future__ import annotations

from datetime import UTC, datetime

from incubation_watcher.shadow import ShadowComparison, render_comparison


def _comp(proposed: set[str], actual: set[str]) -> ShadowComparison:
    return ShadowComparison(
        workspace_name="TestWS",
        since=datetime(2026, 5, 1, tzinfo=UTC),
        proposed_emails=frozenset(proposed),
        actual_emails=frozenset(actual),
    )


class TestSetDifferences:
    def test_empty_sets_no_divergence(self) -> None:
        c = _comp(set(), set())
        assert c.matched == frozenset()
        assert c.watcher_only == frozenset()
        assert c.actual_only == frozenset()
        assert not c.has_divergence

    def test_perfect_parity(self) -> None:
        emails = {"a@x.com", "b@x.com", "c@x.com"}
        c = _comp(emails, emails)
        assert c.matched == frozenset(emails)
        assert c.watcher_only == frozenset()
        assert c.actual_only == frozenset()
        assert not c.has_divergence

    def test_watcher_proposed_extra(self) -> None:
        # Watcher proposed b@x.com that existing module didn't graduate
        c = _comp({"a@x.com", "b@x.com"}, {"a@x.com"})
        assert c.matched == frozenset({"a@x.com"})
        assert c.watcher_only == frozenset({"b@x.com"})
        assert c.actual_only == frozenset()
        assert c.has_divergence

    def test_actual_graduated_unproposed(self) -> None:
        # Existing module graduated c@x.com that watcher didn't propose
        c = _comp({"a@x.com"}, {"a@x.com", "c@x.com"})
        assert c.matched == frozenset({"a@x.com"})
        assert c.watcher_only == frozenset()
        assert c.actual_only == frozenset({"c@x.com"})
        assert c.has_divergence

    def test_complete_disjoint(self) -> None:
        c = _comp({"a@x.com"}, {"z@x.com"})
        assert c.matched == frozenset()
        assert c.watcher_only == frozenset({"a@x.com"})
        assert c.actual_only == frozenset({"z@x.com"})
        assert c.has_divergence


class TestRenderComparison:
    def test_zero_divergence_renders_clean(self) -> None:
        c = _comp({"a@x.com"}, {"a@x.com"})
        out = render_comparison(c)
        joined = "\n".join(out)
        assert "zero divergence" in joined
        assert "DIVERGENCE" not in joined
        assert "Investigate" not in joined

    def test_watcher_only_rendered(self) -> None:
        c = _comp({"a@x.com", "b@x.com"}, {"a@x.com"})
        out = render_comparison(c)
        joined = "\n".join(out)
        assert "watcher_only: b@x.com" in joined
        assert "DIVERGENCE" in joined
        assert "Investigate" in joined

    def test_actual_only_rendered(self) -> None:
        c = _comp({"a@x.com"}, {"a@x.com", "c@x.com"})
        out = render_comparison(c)
        joined = "\n".join(out)
        assert "actual_only:  c@x.com" in joined
        assert "DIVERGENCE" in joined

    def test_both_directions_rendered(self) -> None:
        c = _comp({"watcher@x.com", "shared@x.com"}, {"shared@x.com", "actual@x.com"})
        out = render_comparison(c)
        joined = "\n".join(out)
        assert "watcher_only: watcher@x.com" in joined
        assert "actual_only:  actual@x.com" in joined
        # 1 watcher_only + 1 actual_only — both sections present
        assert joined.count("DIVERGENCE:") == 2

    def test_counts_in_output(self) -> None:
        c = _comp({"a@x.com", "b@x.com"}, {"a@x.com", "c@x.com"})
        out = render_comparison(c)
        joined = "\n".join(out)
        assert "proposed (by watcher, RIGHT NOW):    2" in joined
        assert "actual   (by existing module):       2" in joined
        assert "matched  (both proposed AND actual): 1" in joined


class TestShadowComparisonImmutability:
    def test_emails_are_frozen(self) -> None:
        # frozenset means caller can't accidentally mutate the test data
        c = _comp({"a@x.com"}, {"a@x.com"})
        assert isinstance(c.proposed_emails, frozenset)
        assert isinstance(c.actual_emails, frozenset)
        # And the dataclass is frozen
        try:
            c.workspace_name = "Other"  # type: ignore[misc]
            raise AssertionError("expected FrozenInstanceError")
        except Exception:
            pass  # Expected
