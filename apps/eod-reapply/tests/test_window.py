"""L1 tests for window.evaluate_window — the tz-aware EOD predicate.

These are pure-function tests with frozen clocks. Every assertion is deterministic.
The test matrix covers:
  - Schedule construction validation (IANA tz, end > start)
  - Input guards (naive datetimes, negative buffer, midnight-crossing buffer)
  - Sammy/Australia (Sydney) AEDT and AEST
  - DST transitions for Sydney (south hemisphere) and New York (north hemisphere)
  - No-DST zones (Phoenix, UTC)
  - Sending-day mask (weekend-only, all-off)
  - Buffer (0, 60, 120 min)
  - Idempotency (last_run_local_date == today, == yesterday, == None)
  - IDL-adjacent zones (Pacific/Auckland)
  - Determinism (same inputs → same output)
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone, timedelta

import pytest

from eod_reapply.window import CampaignSchedule, WindowDecision, evaluate_window


# ---------- Fixture builder ----------

def make_schedule(
    *,
    tz: str = "America/New_York",
    days: tuple = (True, True, True, True, True, False, False),  # M-F
    start: time = time(8, 0),
    end: time = time(17, 0),
) -> CampaignSchedule:
    return CampaignSchedule(
        monday=days[0], tuesday=days[1], wednesday=days[2], thursday=days[3],
        friday=days[4], saturday=days[5], sunday=days[6],
        start_time=start, end_time=end, timezone=tz,
    )


# =============================================================================
# Schedule construction validation
# =============================================================================

class TestScheduleValidation:
    def test_valid_iana_timezone_accepted(self):
        s = make_schedule(tz="Australia/Sydney")
        assert s.timezone == "Australia/Sydney"

    def test_utc_accepted(self):
        s = make_schedule(tz="UTC")
        assert s.timezone == "UTC"

    def test_invalid_iana_timezone_raises(self):
        with pytest.raises(ValueError, match="Invalid IANA timezone"):
            make_schedule(tz="Not/A/Real/Zone")

    def test_empty_string_timezone_raises(self):
        with pytest.raises(ValueError, match="Invalid IANA timezone"):
            make_schedule(tz="")

    def test_garbage_timezone_raises(self):
        with pytest.raises(ValueError, match="Invalid IANA timezone"):
            make_schedule(tz="EST5EDT_NOT_REAL_FORMAT")

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match="must be strictly after"):
            make_schedule(start=time(17, 0), end=time(8, 0))

    def test_end_equals_start_raises(self):
        with pytest.raises(ValueError, match="must be strictly after"):
            make_schedule(start=time(8, 0), end=time(8, 0))

    def test_is_sending_day_indexing(self):
        s = make_schedule(days=(True, False, True, False, True, False, True))
        # 0=Mon..6=Sun
        assert s.is_sending_day(0) is True   # Mon
        assert s.is_sending_day(1) is False  # Tue
        assert s.is_sending_day(2) is True   # Wed
        assert s.is_sending_day(3) is False  # Thu
        assert s.is_sending_day(4) is True   # Fri
        assert s.is_sending_day(5) is False  # Sat
        assert s.is_sending_day(6) is True   # Sun

    def test_has_any_sending_day_true(self):
        assert make_schedule().has_any_sending_day is True

    def test_has_any_sending_day_false(self):
        assert make_schedule(days=(False,) * 7).has_any_sending_day is False


# =============================================================================
# Input guards on evaluate_window
# =============================================================================

class TestInputGuards:
    def test_naive_now_raises(self):
        s = make_schedule()
        with pytest.raises(ValueError, match="timezone-aware"):
            evaluate_window(
                schedule=s,
                now_utc=datetime(2026, 5, 1, 12, 0),  # naive!
                last_run_local_date=None,
            )

    def test_negative_buffer_raises(self):
        s = make_schedule()
        with pytest.raises(ValueError, match=">= 0"):
            evaluate_window(
                schedule=s,
                now_utc=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                last_run_local_date=None,
                buffer_minutes=-1,
            )

    def test_buffer_crossing_midnight_raises(self):
        # end_time 23:30 + 60min buffer crosses midnight — not supported in v1
        s = make_schedule(start=time(0, 0), end=time(23, 30))
        with pytest.raises(ValueError, match="crosses midnight"):
            evaluate_window(
                schedule=s,
                now_utc=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                last_run_local_date=None,
                buffer_minutes=60,
            )

    def test_buffer_exactly_at_midnight_raises(self):
        # 23:00 + 60min = exactly 24:00 → also rejected (boundary)
        s = make_schedule(start=time(0, 0), end=time(23, 0))
        with pytest.raises(ValueError, match="crosses midnight"):
            evaluate_window(
                schedule=s,
                now_utc=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                last_run_local_date=None,
                buffer_minutes=60,
            )

    def test_buffer_just_under_midnight_allowed(self):
        # 22:00 + 60min = 23:00 → valid
        s = make_schedule(start=time(0, 0), end=time(22, 0))
        # Don't care about result, just that no ValueError raised
        evaluate_window(
            schedule=s,
            now_utc=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            last_run_local_date=None,
            buffer_minutes=60,
        )


# =============================================================================
# Sammy / Australia (Sydney) — primary regression target
# =============================================================================

class TestSydneySammy:
    """Sammy workspace canonical case: M-F 8am-5pm Sydney, buffer 60min.
    Trigger time is 18:00 local Sydney every weekday."""

    SCHEDULE = make_schedule(tz="Australia/Sydney")

    def test_aedt_summer_at_trigger_exactly(self):
        # 2026-01-15 is Thursday in Sydney (AEDT, UTC+11)
        # Trigger: 18:00 AEDT = 07:00 UTC same day
        now_utc = datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run, d.reason
        assert d.run_local_date == date(2026, 1, 15)
        assert d.now_local.date() == date(2026, 1, 15)
        assert d.now_local.hour == 18

    def test_aedt_one_minute_before_trigger(self):
        # 17:59 AEDT = 06:59 UTC
        now_utc = datetime(2026, 1, 15, 6, 59, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert not d.should_run
        assert "too early" in d.reason

    def test_aedt_one_minute_after_trigger(self):
        # 18:01 AEDT = 07:01 UTC
        now_utc = datetime(2026, 1, 15, 7, 1, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run

    def test_aest_winter_at_trigger_exactly(self):
        # 2026-07-15 is Wednesday in Sydney (AEST, UTC+10)
        # Trigger: 18:00 AEST = 08:00 UTC same day
        now_utc = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run
        assert d.run_local_date == date(2026, 7, 15)

    def test_saturday_sydney_skipped(self):
        # 2026-01-17 is Saturday in Sydney
        # 19:00 Sat AEDT = 08:00 UTC
        now_utc = datetime(2026, 1, 17, 8, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert not d.should_run
        assert "saturday" in d.reason.lower()

    def test_already_ran_today_skipped(self):
        now_utc = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=date(2026, 1, 15),
        )
        assert not d.should_run
        assert "already ran" in d.reason

    def test_already_ran_yesterday_does_not_block_today(self):
        now_utc = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=date(2026, 1, 14),
        )
        assert d.should_run
        assert d.run_local_date == date(2026, 1, 15)

    def test_future_last_run_treated_as_already_ran(self):
        # Defensive: if somehow last_run is in the future, refuse to run
        now_utc = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=date(2026, 1, 20),
        )
        assert not d.should_run


# =============================================================================
# DST transitions
# =============================================================================

class TestDSTSydney:
    """Sydney is south-hemisphere — DST starts in October, ends in April.
    AEDT (UTC+11) Oct→Apr ; AEST (UTC+10) Apr→Oct.
    First Sunday of Oct: spring-forward (02:00 AEST → 03:00 AEDT).
    First Sunday of Apr: fall-back (03:00 AEDT → 02:00 AEST).
    """
    SCHEDULE = make_schedule(tz="Australia/Sydney")

    def test_first_weekday_after_spring_forward(self):
        # 2026-10-04 (Sun): AEST → AEDT spring forward at 02:00
        # 2026-10-05 (Mon): first regular weekday in AEDT
        # Trigger 18:00 AEDT Oct 5 = 07:00 UTC Oct 5
        now_utc = datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run
        assert d.run_local_date == date(2026, 10, 5)

    def test_first_weekday_after_fall_back(self):
        # 2026-04-05 (Sun): AEDT → AEST fall back at 03:00
        # 2026-04-06 (Mon): first regular weekday in AEST
        # Trigger 18:00 AEST Apr 6 = 08:00 UTC Apr 6
        now_utc = datetime(2026, 4, 6, 8, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run
        assert d.run_local_date == date(2026, 4, 6)

    def test_offset_changes_across_dst_boundary(self):
        # Same wall-clock 18:00 local on Friday before vs Monday after fall-back
        # Friday 2026-04-03 (still AEDT): 18:00 AEDT = 07:00 UTC
        # Monday 2026-04-06 (now AEST): 18:00 AEST = 08:00 UTC
        # Both should evaluate true at their respective UTC moments.
        d_aedt = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=datetime(2026, 4, 3, 7, 0, tzinfo=timezone.utc),
            last_run_local_date=None,
        )
        d_aest = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=datetime(2026, 4, 6, 8, 0, tzinfo=timezone.utc),
            last_run_local_date=None,
        )
        assert d_aedt.should_run
        assert d_aest.should_run
        # Verify the offsets actually differ
        assert d_aedt.now_local.utcoffset() != d_aest.now_local.utcoffset()


class TestDSTNewYork:
    """NY: EST (UTC-5) Nov→Mar ; EDT (UTC-4) Mar→Nov.
    Second Sunday of March: spring-forward.
    First Sunday of November: fall-back.
    """
    SCHEDULE = make_schedule(tz="America/New_York")

    def test_winter_est(self):
        # 2026-01-14 (Wed) is EST (UTC-5)
        # 18:00 EST = 23:00 UTC
        now_utc = datetime(2026, 1, 14, 23, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run

    def test_summer_edt(self):
        # 2026-07-15 (Wed) is EDT (UTC-4)
        # 18:00 EDT = 22:00 UTC
        now_utc = datetime(2026, 7, 15, 22, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run

    def test_offsets_differ_summer_vs_winter(self):
        winter = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=datetime(2026, 1, 14, 23, 0, tzinfo=timezone.utc),
            last_run_local_date=None,
        )
        summer = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=datetime(2026, 7, 15, 22, 0, tzinfo=timezone.utc),
            last_run_local_date=None,
        )
        assert winter.now_local.utcoffset() == timedelta(hours=-5)
        assert summer.now_local.utcoffset() == timedelta(hours=-4)


# =============================================================================
# No-DST zones
# =============================================================================

class TestNoDSTPhoenix:
    """America/Phoenix (Arizona) does not observe DST. Always UTC-7 (MST)."""
    SCHEDULE = make_schedule(tz="America/Phoenix")

    def test_january_offset(self):
        # 2026-01-14 (Wed). 18:00 MST = 01:00 UTC NEXT DAY (Jan 15)
        now_utc = datetime(2026, 1, 15, 1, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run
        # run_local_date is the Phoenix-local date — Jan 14, not Jan 15 UTC
        assert d.run_local_date == date(2026, 1, 14)

    def test_july_offset_unchanged(self):
        # 2026-07-15 (Wed). Same UTC-7 offset year-round.
        now_utc = datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run
        assert d.run_local_date == date(2026, 7, 15)

    def test_offsets_identical_year_round(self):
        win = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=datetime(2026, 1, 15, 1, 0, tzinfo=timezone.utc),
            last_run_local_date=None,
        )
        sum_ = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc),
            last_run_local_date=None,
        )
        assert win.now_local.utcoffset() == sum_.now_local.utcoffset()


class TestUTC:
    """UTC schedule should behave normally (and be its own reference)."""
    SCHEDULE = make_schedule(tz="UTC")

    def test_runs_at_18_00_utc(self):
        # 2026-01-14 (Wed) 18:00 UTC
        now_utc = datetime(2026, 1, 14, 18, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run
        assert d.run_local_date == date(2026, 1, 14)


# =============================================================================
# Sending-day mask
# =============================================================================

class TestSendingDayMask:
    def test_all_days_off(self):
        s = make_schedule(days=(False,) * 7)
        d = evaluate_window(
            schedule=s,
            now_utc=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            last_run_local_date=None,
        )
        assert not d.should_run
        assert "no sending days" in d.reason.lower()

    def test_weekend_only_schedule_runs_saturday(self):
        # Sat=True, Sun=True, all weekdays False
        s = make_schedule(days=(False, False, False, False, False, True, True))
        # 2026-01-17 (Sat) 18:00 EST = 23:00 UTC
        now_utc = datetime(2026, 1, 17, 23, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=s,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run
        assert d.run_local_date == date(2026, 1, 17)

    def test_weekend_only_skipped_on_weekday(self):
        s = make_schedule(days=(False, False, False, False, False, True, True))
        # 2026-01-14 (Wed) 18:00 EST
        now_utc = datetime(2026, 1, 14, 23, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=s,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert not d.should_run
        assert "wednesday" in d.reason.lower()


# =============================================================================
# Buffer behavior
# =============================================================================

class TestBuffer:
    def test_zero_buffer_runs_at_end_time_exactly(self):
        s = make_schedule()
        # Wed 2026-01-14 17:00 EST = 22:00 UTC
        now_utc = datetime(2026, 1, 14, 22, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=s,
            now_utc=now_utc,
            last_run_local_date=None,
            buffer_minutes=0,
        )
        assert d.should_run

    def test_zero_buffer_skips_before_end_time(self):
        s = make_schedule()
        # Wed 2026-01-14 16:59 EST = 21:59 UTC
        now_utc = datetime(2026, 1, 14, 21, 59, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=s,
            now_utc=now_utc,
            last_run_local_date=None,
            buffer_minutes=0,
        )
        assert not d.should_run

    def test_120min_buffer(self):
        s = make_schedule()
        # 17:00 EST + 120min = 19:00 EST = 00:00 UTC NEXT DAY
        now_utc = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=s,
            now_utc=now_utc,
            last_run_local_date=None,
            buffer_minutes=120,
        )
        assert d.should_run

    def test_120min_buffer_one_minute_early_skipped(self):
        s = make_schedule()
        # 18:59 EST = 23:59 UTC same day
        now_utc = datetime(2026, 1, 14, 23, 59, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=s,
            now_utc=now_utc,
            last_run_local_date=None,
            buffer_minutes=120,
        )
        assert not d.should_run


# =============================================================================
# IDL-adjacent (Pacific/Auckland)
# =============================================================================

class TestAuckland:
    """Pacific/Auckland is UTC+12/+13 — local date can be ahead of UTC date.
    NZDT (UTC+13) Sep/Oct → Apr ; NZST (UTC+12) Apr → Sep/Oct.
    """
    SCHEDULE = make_schedule(tz="Pacific/Auckland")

    def test_local_date_can_be_ahead_of_utc_date(self):
        # 2026-01-15 18:00 NZDT (UTC+13) = 05:00 UTC same day
        now_utc = datetime(2026, 1, 15, 5, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert d.should_run
        # run_local_date is the Auckland date
        assert d.run_local_date == date(2026, 1, 15)

    def test_morning_in_auckland_too_early(self):
        # 02:00 Auckland Jan 15 NZDT = 13:00 Jan 14 UTC
        now_utc = datetime(2026, 1, 14, 13, 0, tzinfo=timezone.utc)
        d = evaluate_window(
            schedule=self.SCHEDULE,
            now_utc=now_utc,
            last_run_local_date=None,
        )
        assert not d.should_run
        # And the Auckland-local date is Jan 15, not Jan 14 (proves astimezone works)
        assert d.now_local.date() == date(2026, 1, 15)


# =============================================================================
# Determinism
# =============================================================================

class TestDeterminism:
    def test_same_inputs_produce_same_output(self):
        s = make_schedule(tz="Australia/Sydney")
        now_utc = datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc)
        d1 = evaluate_window(schedule=s, now_utc=now_utc, last_run_local_date=None)
        d2 = evaluate_window(schedule=s, now_utc=now_utc, last_run_local_date=None)
        assert d1 == d2
        assert isinstance(d1, WindowDecision)
