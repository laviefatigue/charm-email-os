"""Unit tests for the bounce-parsing pipeline in sync_modules/sync_events.py.

These functions are pure (no I/O, no DB) — tested in isolation without the
integration-test Postgres fixture.

Coverage:
  - extract_bounce_reason  regex SMTP-code + keyword extraction
  - classify_bounce        SMTP code -> hard_blocked / hard_unknown / soft_full / soft_temp
  - is_spam_complaint      bounce-body FBL pattern matching (kept after Plan D Pass 2
                            disabled the CALL SITE; function itself remains for forensic /
                            future use)
  - detect_spam_in_response  inbox-folder active-voice phrase matching

Why this file exists: prior to 2026-05-01 there were ZERO tests for bounce parsing.
Plan D Pass 2 changes a call site in process_reply; these tests pin the parser
behavior so a regression can be caught locally before deploy.

Production-observed bounce_reason inputs are tagged in test docstrings so the
real-world coverage is explicit.
"""
from __future__ import annotations

import pytest

from sync_modules.sync_events import EventSyncModule, is_sender_ban_code


# Parser methods don't use self — bypass __init__ to avoid building dependencies.
_M = EventSyncModule.__new__(EventSyncModule)


# ──────────────────────────────────────────────────────────────────────
# classify_bounce — production code coverage
# ──────────────────────────────────────────────────────────────────────

class TestClassifyBounce:
    """SMTP code -> bucket. All 13 production-observed code patterns covered."""

    # --- hard_unknown (bad address) ---
    def test_5_1_1_user_unknown(self):
        # Production: '550 5.1.1 | mailbox not found' (n=178 in last 30d)
        assert _M.classify_bounce("550 5.1.1 mailbox not found") == "hard_unknown"

    def test_5_1_0_address_rejected(self):
        assert _M.classify_bounce("550 5.1.0 sender address rejected") == "hard_unknown"

    def test_5_1_10_no_recipient(self):
        # Production: '550 5.1.10 | mailbox not found not found' (n=83)
        assert _M.classify_bounce("550 5.1.10 mailbox not found") == "hard_unknown"

    def test_5_4_1_with_blocked_keyword(self):
        # Production: '550 5.4.1 | mailbox not found blocked' (n=126) — stored as hard_blocked.
        # classify_bounce checks 'blocked' keyword BEFORE 'not found', so "blocked" wins
        # when both are present. This matches stored production bounce_type.
        assert _M.classify_bounce("550 5.4.1 mailbox not found blocked") == "hard_blocked"

    def test_5_4_1_only_not_found(self):
        # Production: '550 5.4.1 | mailbox not found not found' (n=56) — stored as hard_unknown.
        # Without 'blocked' keyword, falls through to 'not found' check.
        assert _M.classify_bounce("550 5.4.1 mailbox not found") == "hard_unknown"

    def test_5_4_14_hop_count(self):
        # Production: '554 5.4.14 | mailbox not found not found' (n=65) — UNDOCUMENTED before Pass 1.
        assert _M.classify_bounce("554 5.4.14 mailbox not found") == "hard_unknown"

    def test_5_2_1_inactive_account(self):
        # Production: '550 5.2.1 | mailbox not found' (n=29) — UNDOCUMENTED before Pass 1.
        assert _M.classify_bounce("550 5.2.1 mailbox not found") == "hard_unknown"

    # --- hard_blocked (reputation/policy) ---
    def test_5_7_1_generic_policy(self):
        # Production: '550 5.7.1 | mailbox not found blocked' (n=15)
        assert _M.classify_bounce("550 5.7.1 blocked policy") == "hard_blocked"

    def test_5_7_193_tenant_rejection(self):
        # Production: '550 5.7.193 | blocked spam' (n=80) — UNDOCUMENTED before Pass 1.
        assert _M.classify_bounce("550 5.7.193 blocked spam") == "hard_blocked"

    def test_5_7_350_external_server_spam(self):
        # Production: '550 5.7.350 | blocked spam' (n=49) — UNDOCUMENTED before Pass 1.
        assert _M.classify_bounce("550 5.7.350 blocked spam") == "hard_blocked"

    def test_5_7_520_anti_spam(self):
        # Production: '550 5.7.520 | blocked spam' (n=16) — UNDOCUMENTED before Pass 1.
        assert _M.classify_bounce("550 5.7.520 blocked spam") == "hard_blocked"

    def test_5_4_317_anti_spam_policy(self):
        # Production: '550 5.4.317 | spam policy' (n=17) — UNDOCUMENTED before Pass 1.
        assert _M.classify_bounce("550 5.4.317 spam policy") == "hard_blocked"

    def test_5_0_350_external_wrapper(self):
        # Production: '550 5.0.350 | blocked spam' (n=67) — UNDOCUMENTED before Pass 1.
        # Microsoft generic wrapper for non-specific recipient errors.
        assert _M.classify_bounce("550 5.0.350 blocked spam") == "hard_blocked"

    def test_5_7_51_tenant_inbound_attribution(self):
        # 5.7.51 is partner connector restriction (B2B config), NOT user complaint.
        # Pre-Pass-1 spec wrongly mapped this to spam_complaint. classify_bounce
        # itself correctly classifies as hard_blocked via the 5.7.x rule.
        assert _M.classify_bounce("550 5.7.51 blocked spam") == "hard_blocked"

    # --- soft / temporary ---
    def test_452_4_2_2_soft_full(self):
        assert _M.classify_bounce("452 4.2.2 mailbox full") == "soft_full"

    def test_552_5_2_2_soft_full(self):
        assert _M.classify_bounce("552 5.2.2 mailbox full") == "soft_full"

    def test_421_4_7_0_soft_temp(self):
        assert _M.classify_bounce("421 4.7.0 temporary failure") == "soft_temp"

    # --- keyword fallback (no SMTP code) ---
    def test_no_smtp_blocked_keyword(self):
        assert _M.classify_bounce("blocked policy") == "hard_blocked"

    def test_no_smtp_not_found_keyword(self):
        assert _M.classify_bounce("mailbox not found") == "hard_unknown"

    def test_no_smtp_temporary_keyword(self):
        assert _M.classify_bounce("temporary failure please retry") == "soft_temp"

    # --- edge cases ---
    def test_empty_returns_unknown(self):
        assert _M.classify_bounce("") == "unknown"

    def test_no_match_defaults_hard_unknown(self):
        # Unrecognized 5xx with no keywords falls through to hard_unknown
        assert _M.classify_bounce("555 some weird code") == "hard_unknown"


# ──────────────────────────────────────────────────────────────────────
# extract_bounce_reason — surfaces SMTP code + keywords from raw NDR text
# ──────────────────────────────────────────────────────────────────────

class TestExtractBounceReason:
    def test_simple_550_5_1_1(self):
        body = "Your message couldn't be delivered. 550 5.1.1 user unknown."
        out = _M.extract_bounce_reason("Undeliverable", body)
        assert "550 5.1.1" in out
        # Keywords expected too
        assert any(kw in out.lower() for kw in ["user unknown", "not found"])

    def test_5_7_193_with_blocked_keyword(self):
        # Production-shape NDR
        body = "550 5.7.193 Microsoft tenant rejected the message; suspected spam"
        out = _M.extract_bounce_reason("Undeliverable", body)
        assert "5.7.193" in out
        assert any(kw in out.lower() for kw in ["blocked", "spam"])

    def test_550_no_extended_just_keywords(self):
        body = "Your message was blocked by policy"
        out = _M.extract_bounce_reason("", body)
        assert "blocked" in out.lower()

    def test_subject_provides_signal(self):
        # When body is empty, subject can carry the signal
        out = _M.extract_bounce_reason("Undeliverable: blocked policy", "")
        assert "blocked" in out.lower()

    def test_empty_returns_empty(self):
        assert _M.extract_bounce_reason("", "") == ""


# ──────────────────────────────────────────────────────────────────────
# is_spam_complaint — bounce-body FBL heuristic
# Note: Plan D Pass 2 disables the CALL SITE in process_reply;
# the function itself is preserved for forensic/future use.
# ──────────────────────────────────────────────────────────────────────

class TestIsSpamComplaint:
    def test_feedback_type_header_TRUE(self):
        # Real ARF-format header — high-confidence FBL signal
        body = "Feedback-Type: abuse\nUser-Agent: Yahoo!"
        assert _M.is_spam_complaint(body, "") is True

    def test_microsoft_junk_indicator_header_TRUE(self):
        body = "X-MS-Exchange-Message-Is-Junk: True"
        assert _M.is_spam_complaint(body, "") is True

    def test_feedback_id_gmail_header_TRUE(self):
        body = "Feedback-ID: campaign-123:tenant-abc:gmail"
        assert _M.is_spam_complaint(body, "") is True

    def test_arf_intro_TRUE(self):
        body = "This is an email abuse report for an email message received from..."
        assert _M.is_spam_complaint(body, "") is True

    def test_admin_policy_block_FALSE_POSITIVE_GUARD(self):
        # Canonical false-positive case: SGMC m.elzey production kill 2026-05-01.
        # Microsoft 365 admin mail-flow rule blocking — NOT a user complaint.
        # body_preview alone (first 500 chars) does NOT contain FBL patterns.
        # The full body — which we don't store — may have contained pass-through
        # original-message headers that triggered the heuristic. THIS test pins
        # the behavior on the body content we have visibility into.
        body = (
            "A custom mail flow rule created by an admin at sgmc.org "
            "has blocked your message. This user is no longer employed with SGMC, "
            "message refused. Blocked by mail flow rule."
        )
        assert _M.is_spam_complaint(body, "550 blocked policy") is False

    def test_5_7_51_tenant_attribution_FALSE(self):
        # Partner-connector restriction body, no FBL keywords
        body = "RestrictDomainsToIPAddresses set; partner connector restriction"
        assert _M.is_spam_complaint(body, "550 5.7.51") is False

    def test_5_7_1_with_complaint_keyword_TRUE(self):
        # SMTP+keyword fallback: 550 5.7.1 + 'complaint' in body
        body = "Recipient filed a complaint about this message"
        assert _M.is_spam_complaint(body, "550 5.7.1") is True

    def test_5_7_511_alone_FALSE(self):
        # 5.7.511 is IP block; without complaint keywords, should NOT trigger
        body = "Access denied, banned sender. Apply at delist@microsoft.com"
        assert _M.is_spam_complaint(body, "550 5.7.511") is False

    def test_empty_returns_false(self):
        assert _M.is_spam_complaint("", "") is False

    def test_none_returns_false(self):
        assert _M.is_spam_complaint(None, None) is False


# ──────────────────────────────────────────────────────────────────────
# detect_spam_in_response — folder='inbox' active-voice phrase match
# ──────────────────────────────────────────────────────────────────────

class TestDetectSpamInResponse:
    def test_marked_as_spam_TRUE(self):
        assert _M.detect_spam_in_response("I marked this as spam", "") is True

    def test_reported_as_spam_TRUE(self):
        assert _M.detect_spam_in_response("Reported you as spam", "") is True

    def test_moved_to_junk_TRUE(self):
        assert _M.detect_spam_in_response("Moved to junk folder", "") is True

    def test_reported_to_google_TRUE(self):
        # Heuristic checks substring 'reported to google' — must be contiguous
        assert _M.detect_spam_in_response("I'm going to be reported to Google", "") is True

    def test_reported_you_to_google_FALSE(self):
        # Note current limitation: "reported YOU to google" doesn't match because the
        # phrase list checks 'reported to google' as contiguous substring. Pinned as
        # known false-negative; out-of-scope for Pass 2.
        assert _M.detect_spam_in_response("I reported you to Google for spam", "") is False

    def test_not_interested_FALSE(self):
        assert _M.detect_spam_in_response("Thanks but not interested", "") is False

    def test_passive_observation_FALSE(self):
        # 'going to my spam folder' is observation, not active complaint.
        # The heuristic checks specific phrases — 'going to my spam folder' is
        # not in the list. Pinned: should be False.
        assert _M.detect_spam_in_response(
            "Hey, your emails keep going to my spam folder lately", ""
        ) is False

    def test_subject_signal_TRUE(self):
        # Subject line can carry the signal too
        assert _M.detect_spam_in_response("", "Re: I marked this as spam") is True

    def test_empty_returns_false(self):
        assert _M.detect_spam_in_response("", "") is False

    def test_none_safe(self):
        assert _M.detect_spam_in_response(None, None) is False


# ──────────────────────────────────────────────────────────────────────
# Smoke: classification covers ALL production-observed bounce_reason
# strings from the 2026-05-01 audit (top 13 by frequency)
# ──────────────────────────────────────────────────────────────────────

PRODUCTION_BOUNCE_REASONS = [
    # (bounce_reason, expected_bounce_type, frequency_in_30d)
    # Pulled from response_messages 2026-05-01 for last-30-day window.
    # Expected values are the bounce_type stored at the time of audit —
    # i.e. what classify_bounce ACTUALLY returned in production.
    ("554 blocked", "hard_blocked", 223),
    ("550 blocked", "hard_blocked", 132),
    ("550 5.4.1 mailbox not found blocked", "hard_blocked", 126),  # 'blocked' keyword wins
    ("mailbox not found", "hard_unknown", 82),
    ("550 5.1.1 mailbox not found", "hard_unknown", 68),
    ("550 5.0.350 blocked spam", "hard_blocked", 67),
    ("550 5.1.1 user unknown mailbox not found", "hard_unknown", 66),
    ("554 5.4.14 mailbox not found not found", "hard_unknown", 65),
    ("550 5.1.10 mailbox not found not found", "hard_unknown", 64),
    ("550 5.4.1 mailbox not found not found", "hard_unknown", 56),  # no 'blocked' = falls through to 'not found'
    ("550 5.7.350 blocked spam", "hard_blocked", 49),
    ("550 5.7.193 blocked spam", "hard_blocked", 47),
    ("550 5.2.1 mailbox not found", "hard_unknown", 29),
    ("temporary", "soft_temp", 25),
    ("550 mailbox not found blocked", "hard_blocked", 23),
    ("550 5.1.10 mailbox not found spam", "hard_unknown", 19),  # 'not found' wins over 'spam' — note positional ambiguity
    ("550 blocked spam", "hard_blocked", 18),
    ("550 5.4.317 spam policy", "hard_blocked", 17),
    ("550 5.7.520 blocked spam", "hard_blocked", 16),
    ("550 5.7.1 mailbox not found blocked", "hard_blocked", 15),  # 5.7.x rule wins
    ("550 5.4.1 blocked", "hard_blocked", 13),
    ("blocked policy", "hard_blocked", 12),
]


# ──────────────────────────────────────────────────────────────────────
# is_sender_ban_code — Plan D Pass 3 alert-first detection
# ──────────────────────────────────────────────────────────────────────

class TestIsSenderBanCode:
    """Microsoft sender-ban SMTP codes — direct accusations from MS that we're banned."""

    # --- Exact match codes ---
    def test_5_7_501_spam_abuse(self):
        assert is_sender_ban_code("550 5.7.501 Access denied, spam abuse detected") == "5.7.501"

    def test_5_7_502_banned_sender(self):
        assert is_sender_ban_code("5.7.502 banned sender") == "5.7.502"

    def test_5_7_503_banned_sender(self):
        assert is_sender_ban_code("550 5.7.503 banned sender") == "5.7.503"

    def test_5_7_508_ipv6_rate(self):
        assert is_sender_ban_code("550 5.7.508 IPv6 send rate") == "5.7.508"

    def test_5_7_509_dmarc_reject_is_NOT_ban(self):
        # Excluded after production sanity check (11 hits in 30d) showed
        # this is a DMARC ALIGNMENT issue, not a Microsoft ban verdict.
        # Handled by existing hard_blocked_24h count rule instead.
        assert is_sender_ban_code("550 5.7.509 sender domain DMARC reject policy") is None

    def test_5_7_511_blocklist(self):
        assert is_sender_ban_code("550 5.7.511 banned sender, IP blocklist") == "5.7.511"

    def test_5_7_703_tenant_block(self):
        assert is_sender_ban_code("550 5.7.703 tenant allow/block list") == "5.7.703"

    def test_5_7_705_tenant_threshold(self):
        assert is_sender_ban_code("550 5.7.705 tenant threshold exceeded") == "5.7.705"

    def test_5_7_708_tenant_traffic(self):
        assert is_sender_ban_code("550 5.7.708 access denied traffic not accepted") == "5.7.708"

    def test_5_7_750_unregistered_domain(self):
        assert is_sender_ban_code("550 5.7.750 unregistered domain") == "5.7.750"

    def test_5_7_800_ehlo_banned(self):
        assert is_sender_ban_code("550 5.7.800 EHLO sender domain banned") == "5.7.800"

    # --- IP range 5.7.606..649 ---
    def test_5_7_606_banned_ip(self):
        assert is_sender_ban_code("550 5.7.606 banned IP") == "5.7.606"

    def test_5_7_625_middle_of_range(self):
        assert is_sender_ban_code("5.7.625 banned IP") == "5.7.625"

    def test_5_7_649_top_of_range(self):
        assert is_sender_ban_code("550 5.7.649 banned") == "5.7.649"

    # --- Boundary conditions ---
    def test_5_7_605_below_range(self):
        # 605 is below the 606..649 range
        assert is_sender_ban_code("5.7.605 something") is None

    def test_5_7_650_above_range(self):
        assert is_sender_ban_code("5.7.650 something") is None

    def test_5_7_700_above_range_unrelated(self):
        # 700 is below the 703..708 set; should not match
        assert is_sender_ban_code("5.7.700 something") is None

    # --- Non-sender-ban codes return None ---
    def test_5_7_1_generic_policy_returns_none(self):
        # 5.7.1 is generic policy — not sender-ban
        assert is_sender_ban_code("550 5.7.1 blocked policy") is None

    def test_5_7_350_recipient_filter_returns_none(self):
        # 5.7.350 is recipient-side spam filter, not sender ban
        assert is_sender_ban_code("550 5.7.350 blocked spam") is None

    def test_5_7_193_tenant_returns_none(self):
        assert is_sender_ban_code("550 5.7.193 blocked spam") is None

    def test_5_7_51_connector_returns_none(self):
        # 5.7.51 is partner connector restriction, not sender ban
        assert is_sender_ban_code("550 5.7.51 blocked spam") is None

    def test_5_1_1_mailbox_unknown_returns_none(self):
        # 5.1.1 is bad address; unrelated
        assert is_sender_ban_code("550 5.1.1 user unknown") is None

    def test_empty_returns_none(self):
        assert is_sender_ban_code("") is None
        assert is_sender_ban_code(None) is None


@pytest.mark.parametrize("reason,expected,_freq", PRODUCTION_BOUNCE_REASONS)
def test_production_bounce_classification_smoke(reason, expected, _freq):
    """Smoke test against last-30-day production bounce_reason distribution.

    The (reason, expected) pairs are pulled from response_messages with their
    stored bounce_type at audit time. If classify_bounce regresses, this catches
    a real-world miss before any code change ships.
    """
    actual = _M.classify_bounce(reason)
    assert actual == expected, (
        f"Production regression: bounce_reason={reason!r} classified as "
        f"{actual!r}, expected {expected!r} (production frequency={_freq})"
    )
