"""Schedule helpers independent from APScheduler."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from savh_backup.settings.config import ScheduleSection

DAY_TO_WEEKDAY = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

DAY_TO_CRON = {
    "mon": "1",
    "tue": "2",
    "wed": "3",
    "thu": "4",
    "fri": "5",
    "sat": "6",
    "sun": "0",
}


def parse_days(day_of_week: str) -> list[str]:
    """Parse configured weekday names."""

    days = [part.strip().lower() for part in day_of_week.split(",") if part.strip()]
    if not days:
        raise ValueError("day_of_week cannot be empty")
    invalid = [day for day in days if day not in DAY_TO_WEEKDAY]
    if invalid:
        raise ValueError(f"Unsupported day_of_week values: {', '.join(invalid)}")
    return days


def last_scheduled_run(
    *,
    now: datetime,
    timezone_name: str,
    schedule: ScheduleSection,
) -> datetime | None:
    """Return the last scheduled run at or before now."""

    tz = ZoneInfo(timezone_name)
    localized_now = now.astimezone(tz)
    weekdays = {DAY_TO_WEEKDAY[day] for day in parse_days(schedule.day_of_week)}
    scheduled_time = time(hour=schedule.hour, minute=schedule.minute, tzinfo=tz)
    for offset in range(8):
        candidate_date = localized_now.date() - timedelta(days=offset)
        if candidate_date.weekday() not in weekdays:
            continue
        candidate = datetime.combine(candidate_date, scheduled_time)
        if candidate <= localized_now:
            return candidate
    return None


def should_catch_up(
    *,
    now: datetime,
    timezone_name: str,
    schedule: ScheduleSection,
    has_success_after: bool,
) -> tuple[bool, datetime | None]:
    """Return whether startup should catch up a recently missed run."""

    last_run = last_scheduled_run(now=now, timezone_name=timezone_name, schedule=schedule)
    if last_run is None:
        return False, None
    age = now.astimezone(last_run.tzinfo) - last_run
    if age > timedelta(hours=schedule.catch_up_hours):
        return False, last_run
    if has_success_after:
        return False, last_run
    return True, last_run


def sentry_crontab(schedule: ScheduleSection) -> str:
    """Return a crontab expression compatible with Sentry monitors."""

    days = ",".join(DAY_TO_CRON[day] for day in parse_days(schedule.day_of_week))
    return f"{schedule.minute} {schedule.hour} * * {days}"

