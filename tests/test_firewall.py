"""Unit tests for the cross-workspace integrity firewall match logic.

Covers `matches_workspace_pattern()` in sync_modules/sync_accounts.py — the
pure function that powers Plan A Phase 5a's quarantine decision.

These tests are pure (no DB) and lock the substring-match semantics:
  - NULL or empty pattern fails closed (HR-5)
  - Comma-separated patterns are split + lowercased
  - Substring-of-domain match per keyword
  - Email without `@` treated as the whole string
  - Case-insensitive

Match logic is intentionally simple per firewall plan HR-4 — no regex, no
fuzzy matching. If a pattern doesn't catch what the operator intends, the
operator updates the keyword string.
"""
from __future__ import annotations

import pytest

from sync_modules.sync_accounts import matches_workspace_pattern


class TestNullAndEmptyPatterns:
    """HR-5: NULL pattern means "no opinion → fail closed → quarantine."""

    def test_none_pattern(self):
        assert matches_workspace_pattern("a@x.com", None) is False

    def test_empty_string_pattern(self):
        assert matches_workspace_pattern("a@x.com", "") is False

    def test_whitespace_only_pattern(self):
        assert matches_workspace_pattern("a@x.com", "   ") is False

    def test_only_commas_pattern(self):
        # "," splits to ["",""], filter empty → no keywords → no match
        assert matches_workspace_pattern("a@x.com", ",,") is False


class TestSingleKeywordPatterns:
    """Per-workspace single-keyword patterns from production data."""

    def test_charm_brand_match(self):
        assert matches_workspace_pattern("a@illuminatecharm.com", "charm") is True
        assert matches_workspace_pattern("a@enhancecharm.com", "charm") is True
        assert matches_workspace_pattern("a@strengthencharm.com", "charm") is True

    def test_spoutwater_brand_match(self):
        assert matches_workspace_pattern("a@gospoutwater.com", "spoutwater") is True
        assert matches_workspace_pattern("a@joinspoutwater.com", "spoutwater") is True

    def test_kernel_catches_both_stablekernel_and_kernel_only(self):
        # Stable Kernel pattern intentionally narrowest-correct: 'kernel'
        assert matches_workspace_pattern("a@stablekernelnow.com", "kernel") is True
        assert matches_workspace_pattern("a@growwithkernel.com", "kernel") is True
        assert matches_workspace_pattern("a@optimizekernel.com", "kernel") is True

    def test_brand_keyword_not_matching_unrelated_domain(self):
        assert matches_workspace_pattern("a@randomcompany.com", "charm") is False
        assert matches_workspace_pattern("a@spoutwater.com", "charm") is False

    def test_guardare_for_barrena(self):
        # Barrena's brand operates as guardare, not barrena
        assert matches_workspace_pattern("user@discoverguardare.com", "guardare") is True
        assert matches_workspace_pattern("user@barrena.com", "guardare") is False

    def test_partial_keyword_match_is_intentional(self):
        # 'spui' substring matches *spui* anywhere in domain
        assert matches_workspace_pattern("a@growspui.com", "spui") is True
        # but it would also match adversarial 'malicious-spui-fake.net' —
        # this is the documented HR-4 simplicity tradeoff
        assert matches_workspace_pattern("a@malicious-spui-fake.net", "spui") is True


class TestMultiKeywordPatterns:
    """Charm has 9 sub-brands across the comma-separated pattern."""

    CHARM_PATTERN = "charm,growthgroupusa,alldealsgroup,globaloutreachclub,urosaf-bio,eudalie-bio,inspi-cure-eu,mydealslift,stylepad24"

    def test_charm_canonical(self):
        assert matches_workspace_pattern("user@illuminatecharm.com", self.CHARM_PATTERN) is True

    def test_charm_subbrand_growthgroupusa(self):
        assert matches_workspace_pattern("user@growthgroupusa.com", self.CHARM_PATTERN) is True

    def test_charm_subbrand_eudalie_bio(self):
        # Bio sub-brand — hyphenated keyword
        assert matches_workspace_pattern("user@eudalie-bio.com", self.CHARM_PATTERN) is True

    def test_charm_subbrand_stylepad24(self):
        assert matches_workspace_pattern("user@stylepad24.com", self.CHARM_PATTERN) is True

    def test_unrelated_domain_against_multikeyword(self):
        assert matches_workspace_pattern("user@unrelated.com", self.CHARM_PATTERN) is False


class TestCaseInsensitive:
    def test_uppercase_domain(self):
        assert matches_workspace_pattern("a@ILLUMINATECHARM.COM", "charm") is True

    def test_uppercase_pattern(self):
        assert matches_workspace_pattern("a@illuminatecharm.com", "CHARM") is True

    def test_mixed_case_both(self):
        assert matches_workspace_pattern("A@IlluminateCharm.com", "ChArM") is True


class TestPatternParsing:
    def test_whitespace_around_commas_stripped(self):
        # Operators may type with spaces; pattern parser must handle gracefully
        assert matches_workspace_pattern("a@charm.com", "charm , growthgroupusa") is True
        assert matches_workspace_pattern("a@growthgroupusa.com", "charm , growthgroupusa") is True

    def test_empty_keyword_in_list_skipped(self):
        # ",,charm,," should still match charm
        assert matches_workspace_pattern("a@charm.com", ",,charm,,") is True

    def test_trailing_comma_does_not_break(self):
        assert matches_workspace_pattern("a@charm.com", "charm,") is True


class TestEdgeCases:
    def test_email_without_at_sign_treated_as_whole_string(self):
        # Defensive: shouldn't crash. Match against whole string as if it were a domain.
        assert matches_workspace_pattern("just-text-with-charm-in-it", "charm") is True

    def test_empty_email_with_pattern(self):
        assert matches_workspace_pattern("", "charm") is False

    def test_email_with_multiple_at_signs_uses_part_after_first(self):
        # "a@b@c" — split('@', 1) → ['a', 'b@c'] → domain = 'b@c'
        assert matches_workspace_pattern("a@b@charm.com", "charm") is True

    def test_keyword_appearing_only_in_local_part_no_match(self):
        # "charm" in local part shouldn't match (we check domain only)
        assert matches_workspace_pattern("charm@randomcompany.com", "charm") is False
