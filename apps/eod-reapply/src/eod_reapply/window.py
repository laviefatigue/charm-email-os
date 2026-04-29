"""
Timezone-aware EOD window predicate.

Pure function. No I/O. The orchestrator (and the future scheduler) consult this
to decide whether a given campaign's reapply window is open right now.

Idempotency is keyed on the campaign's local date in its own IANA timezone, not
UTC. A single UTC day can span two local dates (and vice versa), so using UTC
date as the key would either double-fire or skip days.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class CampaignSchedule:
    """Mirror of EmailBison's GET /api/campaigns/{id}/schedule response.

    Validated at construction:
    - timezone must be a resolvable IANA name
    - end_time must be strictly after start_time (no overnight schedules in v1)
    """
    monday: bool
    tuesday: bool
    wednesday: bool
    thursday: bool
    friday: bool
    saturday: bool
    sunday: bool
    start_time: time
    end_time: time
    timezone: str

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Invalid IANA timezone: {self.timezone!r}") from e
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid IANA timezone: {self.timezone!r}") from e

        if self.end_time <= self.start_time:
            raise ValueError(
                f"end_time ({self.end_time}) must be strictly after start_time "
                f"({self.start_time}); v1 does not support overnight schedules"
            )

    def is_sending_day(self, weekday: int) -> bool:
        """weekday: 0=Monday .. 6=Sunday (matches datetime.weekday())."""
        return (
            self.monday, self.tuesday, self.wednesday, self.thursday,
            self.friday, self.saturday, self.sunday,
        )[weekday]

    @property
    def has_any_sending_day(self) -> bool:
        return any((
            self.monday, self.tuesday, self.wednesday, self.thursday,
            self.friday, self.saturday, self.sunday,
        ))


@dataclass(frozen=True)
class WindowDecision:
    """Result of evaluate_window. Always populated; should_run is the gate."""
    should_run: bool
    reason: str
    run_local_date: Optional[date]
    now_local: datetime


def evaluate_window(
    *,
    schedule: CampaignSchedule,
    now_utc: datetime,
    last_run_local_date: Optional[date],
    buffer_minutes: int = 60,
) -> WindowDecision:
    """Decide whether reapply should run for this campaign right now.

    Args:
        schedule: campaign schedule pulled from EB.
        now_utc: timezone-aware UTC datetime. Naive input is rejected.
        last_run_local_date: most recent successful reapply's run_local_date,
            or None if never run. Compared against today's local date in the
            campaign's tz.
        buffer_minutes: how long after end_time we wait before firing. Default 60.

    Raises:
        ValueError if now_utc is naive, buffer is negative, or end_time + buffer
        crosses midnight (overnight buffers not supported in v1).
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware (got naive datetime)")
    if buffer_minutes < 0:
        raise ValueError(f"buffer_minutes must be >= 0, got {buffer_minutes}")

    tz = ZoneInfo(schedule.timezone)
    now_local = now_utc.astimezone(tz)

    if not schedule.has_any_sending_day:
        return WindowDecision(
            should_run=False,
            reason="schedule has no sending days configured",
            run_local_date=None,
            now_local=now_local,
        )

    end_seconds = schedule.end_time.hour * 3600 + schedule.end_time.minute * 60 + schedule.end_time.second
    if end_seconds + buffer_minutes * 60 >= 86400:
        raise ValueError(
            f"end_time ({schedule.end_time}) + buffer ({buffer_minutes}min) crosses midnight; "
            f"v1 does not support overnight reapply windows"
        )

    today_local_date = now_local.date()
    today_local_weekday = now_local.weekday()

    if last_run_local_date is not None and last_run_local_date >= today_local_date:
        return WindowDecision(
            should_run=False,
            reason=f"already ran for local_date={last_run_local_date.isoformat()}",
            run_local_date=None,
            now_local=now_local,
        )

    if not schedule.is_sending_day(today_local_weekday):
        return WindowDecision(
            should_run=False,
            reason=f"today ({_WEEKDAY_NAMES[today_local_weekday]}) is not a sending day",
            run_local_date=None,
            now_local=now_local,
        )

    end_local_today = datetime.combine(today_local_date, schedule.end_time, tzinfo=tz)
    trigger_at = end_local_today + timedelta(minutes=buffer_minutes)

    if now_local < trigger_at:
        return WindowDecision(
            should_run=False,
            reason=f"too early: now_local={now_local.isoformat()} < trigger_at={trigger_at.isoformat()}",
            run_local_date=None,
            now_local=now_local,
        )

    return WindowDecision(
        should_run=True,
        reason="window open",
        run_local_date=today_local_date,
        now_local=now_local,
    )
