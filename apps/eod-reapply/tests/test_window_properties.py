"""Property-based tests for window.evaluate_window using Hypothesis.

Generated tests cover combinations no human would write:
  - Random IANA timezones
  - Random valid times across the full HH:MM space
  - Random buffer values
  - Random datetime moments across years and seasons
  - Random sending-day masks

The properties we assert hold UNIVERSALLY (not just for specific cases):
  - evaluate_window never raises for any valid input
  - run_local_date is None whenever should_run is False
  - run_local_date matches now_local.date() whenever should_run is True
  - The reason field is always non-empty
  - Idempotency: setting last_run_local_date == today_local always blocks
  - Determinism: same inputs always produce identical output
  - Buffer monotonicity: larger buffer never makes a should_run=True become False (when other inputs equal)
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo, available_timezones

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from eod_reapply.window import CampaignSchedule, evaluate_window

# ---------- Strategies ----------

# Curated subset of IANA names we care about — avoids hypothesis spending
# time on aliases like "Etc/GMT-12" that confuse human readers of failures.
_TZ_NAMES = sorted([
    tz for tz in available_timezones()
    if "/" in tz
    and not tz.startswith("Etc/")
    and not tz.startswith("posix/")
    and not tz.startswith("right/")
    and "Riyadh87" not in tz
    and "Riyadh88" not in tz
    and "Riyadh89" not in tz
])

iana_timezones = st.sampled_from(_TZ_NAMES)


@st.composite
def valid_schedule_strategy(draw):
    """Generate a valid CampaignSchedule with at least one sending day and end > start."""
    days = draw(st.lists(st.booleans(), min_size=7, max_size=7))
    if not any(days):
        # Force at least one sending day
        days[0] = True

    # start_time fully random; end_time strictly after start
    start_h = draw(st.integers(min_value=0, max_value=22))
    start_m = draw(st.integers(min_value=0, max_value=59))
    # end is at least 1 minute after start
    total_start_min = start_h * 60 + start_m
    end_offset_min = draw(st.integers(min_value=1, max_value=23 * 60 + 59 - total_start_min))
    end_total = total_start_min + end_offset_min
    end_h, end_m = divmod(end_total, 60)
    if end_h >= 24:
        end_h, end_m = 23, 59
        if total_start_min >= 23 * 60 + 59:
            # Reset start_time to leave room
            start_h, start_m = 0, 0

    return CampaignSchedule(
        monday=days[0], tuesday=days[1], wednesday=days[2], thursday=days[3],
        friday=days[4], saturday=days[5], sunday=days[6],
        start_time=time(start_h, start_m),
        end_time=time(end_h, end_m),
        timezone=draw(iana_timezones),
    )


# A buffer that, combined with end_time, won't cross midnight in any reasonable schedule
# (the predicate refuses crossings). Cap at 12 hours.
buffer_minutes_strategy = st.integers(min_value=0, max_value=720)


# Generate datetimes across a few years, always tz-aware UTC
utc_datetime_strategy = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(UTC),
)


# Last-run dates: None or a date in a wide window
last_run_date_strategy = st.one_of(
    st.none(),
    st.dates(min_value=date(2020, 1, 1), max_value=date(2031, 12, 31)),
)


# Suppress the "function-scoped fixture" warning since we use module-level strategies.
_HYPOTHESIS_SETTINGS = settings(
    max_examples=100,
    deadline=None,  # don't fail on slow zoneinfo lookups under coverage
    suppress_health_check=[HealthCheck.too_slow],
)


# =============================================================================
# Property 1: never raises on valid input
# =============================================================================

class TestNeverRaisesOnValidInput:
    @_HYPOTHESIS_SETTINGS
    @given(
        schedule=valid_schedule_strategy(),
        now_utc=utc_datetime_strategy,
        last_run_local_date=last_run_date_strategy,
        buffer_minutes=buffer_minutes_strategy,
    )
    def test_no_unexpected_exceptions(self, schedule, now_utc, last_run_local_date, buffer_minutes):
        # The only ValueError we tolerate is buffer-crosses-midnight.
        # Any other exception is a bug.
        try:
            evaluate_window(
                schedule=schedule,
                now_utc=now_utc,
                last_run_local_date=last_run_local_date,
                buffer_minutes=buffer_minutes,
            )
        except ValueError as e:
            # Only acceptable: end_time + buffer crosses midnight
            assert "crosses midnight" in str(e), f"unexpected ValueError: {e}"


# =============================================================================
# Property 2: run_local_date is None iff should_run is False
# =============================================================================

class TestRunLocalDateInvariant:
    @_HYPOTHESIS_SETTINGS
    @given(
        schedule=valid_schedule_strategy(),
        now_utc=utc_datetime_strategy,
        last_run_local_date=last_run_date_strategy,
        buffer_minutes=buffer_minutes_strategy,
    )
    def test_run_local_date_set_iff_should_run(
        self, schedule, now_utc, last_run_local_date, buffer_minutes
    ):
        try:
            d = evaluate_window(
                schedule=schedule,
                now_utc=now_utc,
                last_run_local_date=last_run_local_date,
                buffer_minutes=buffer_minutes,
            )
        except ValueError:
            return  # buffer-midnight rejection — not a property-test concern

        if d.should_run:
            assert d.run_local_date is not None, "should_run=True must set run_local_date"
            # And it must equal the date in the campaign's tz
            assert d.run_local_date == d.now_local.date()
        else:
            assert d.run_local_date is None, "should_run=False must NOT set run_local_date"


# =============================================================================
# Property 3: reason is always non-empty
# =============================================================================

class TestReasonAlwaysSet:
    @_HYPOTHESIS_SETTINGS
    @given(
        schedule=valid_schedule_strategy(),
        now_utc=utc_datetime_strategy,
        last_run_local_date=last_run_date_strategy,
        buffer_minutes=buffer_minutes_strategy,
    )
    def test_reason_non_empty(self, schedule, now_utc, last_run_local_date, buffer_minutes):
        try:
            d = evaluate_window(
                schedule=schedule, now_utc=now_utc,
                last_run_local_date=last_run_local_date, buffer_minutes=buffer_minutes,
            )
        except ValueError:
            return
        assert d.reason  # non-empty string


# =============================================================================
# Property 4: now_local is in the campaign's tz
# =============================================================================

class TestNowLocalIsInCampaignTz:
    @_HYPOTHESIS_SETTINGS
    @given(
        schedule=valid_schedule_strategy(),
        now_utc=utc_datetime_strategy,
        last_run_local_date=last_run_date_strategy,
        buffer_minutes=buffer_minutes_strategy,
    )
    def test_now_local_correctly_zoned(
        self, schedule, now_utc, last_run_local_date, buffer_minutes
    ):
        try:
            d = evaluate_window(
                schedule=schedule, now_utc=now_utc,
                last_run_local_date=last_run_local_date, buffer_minutes=buffer_minutes,
            )
        except ValueError:
            return
        # now_local must represent the same UTC instant as now_utc
        assert d.now_local.astimezone(UTC) == now_utc
        # And its tzinfo must be the campaign tz
        assert d.now_local.tzinfo == ZoneInfo(schedule.timezone)


# =============================================================================
# Property 5: idempotency — last_run_local_date == today blocks
# =============================================================================

class TestIdempotencyAlwaysBlocks:
    @_HYPOTHESIS_SETTINGS
    @given(
        schedule=valid_schedule_strategy(),
        now_utc=utc_datetime_strategy,
        buffer_minutes=buffer_minutes_strategy,
    )
    def test_already_ran_today_always_blocks(self, schedule, now_utc, buffer_minutes):
        # First, get today_local for this (schedule, now_utc)
        try:
            tz = ZoneInfo(schedule.timezone)
            today_local = now_utc.astimezone(tz).date()
        except Exception:
            return

        try:
            d = evaluate_window(
                schedule=schedule, now_utc=now_utc,
                last_run_local_date=today_local,
                buffer_minutes=buffer_minutes,
            )
        except ValueError:
            return

        # When last_run is today's local date, should_run MUST be False
        assert not d.should_run, (
            f"INV violated: last_run_local_date={today_local} == today_local "
            f"must block, but should_run=True"
        )


# =============================================================================
# Property 6: determinism — same inputs always produce identical output
# =============================================================================

class TestDeterminism:
    @_HYPOTHESIS_SETTINGS
    @given(
        schedule=valid_schedule_strategy(),
        now_utc=utc_datetime_strategy,
        last_run_local_date=last_run_date_strategy,
        buffer_minutes=buffer_minutes_strategy,
    )
    def test_same_inputs_same_output(
        self, schedule, now_utc, last_run_local_date, buffer_minutes
    ):
        try:
            d1 = evaluate_window(
                schedule=schedule, now_utc=now_utc,
                last_run_local_date=last_run_local_date, buffer_minutes=buffer_minutes,
            )
            d2 = evaluate_window(
                schedule=schedule, now_utc=now_utc,
                last_run_local_date=last_run_local_date, buffer_minutes=buffer_minutes,
            )
        except ValueError:
            return
        assert d1 == d2


# =============================================================================
# Property 7: buffer monotonicity — increasing buffer never relaxes the gate
# =============================================================================

class TestBufferMonotonicity:
    """Larger buffer means stricter time gate. So:
    - if should_run with buffer=B, it should still run with buffer=B' < B (looser gate)
    - if NOT should_run with buffer=B (because too early), might be OK with smaller B
    - it should NEVER be the case that smaller buffer turns OFF a run that larger buffer allowed
    """

    @_HYPOTHESIS_SETTINGS
    @given(
        schedule=valid_schedule_strategy(),
        now_utc=utc_datetime_strategy,
        last_run_local_date=last_run_date_strategy,
        smaller_buffer=st.integers(min_value=0, max_value=60),
        extra=st.integers(min_value=0, max_value=60),
    )
    def test_smaller_buffer_never_blocks_what_larger_allowed(
        self, schedule, now_utc, last_run_local_date, smaller_buffer, extra
    ):
        larger_buffer = smaller_buffer + extra
        try:
            d_larger = evaluate_window(
                schedule=schedule, now_utc=now_utc,
                last_run_local_date=last_run_local_date, buffer_minutes=larger_buffer,
            )
            d_smaller = evaluate_window(
                schedule=schedule, now_utc=now_utc,
                last_run_local_date=last_run_local_date, buffer_minutes=smaller_buffer,
            )
        except ValueError:
            return  # buffer-midnight, irrelevant

        # If the LARGER buffer allowed running, the SMALLER buffer must also allow running
        # (smaller buffer = trigger happens earlier, so by the time larger buffer fires, smaller already did)
        if d_larger.should_run:
            assert d_smaller.should_run, (
                f"buffer monotonicity violated: larger_buffer={larger_buffer} allowed run, "
                f"but smaller_buffer={smaller_buffer} blocked. "
                f"larger reason={d_larger.reason!r}, smaller reason={d_smaller.reason!r}"
            )
