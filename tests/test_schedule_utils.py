from __future__ import annotations

from datetime import UTC, datetime

from savh_backup.settings.config import ScheduleSection
from savh_backup.scheduling.utils import last_scheduled_run, sentry_crontab, should_catch_up


def _schedule() -> ScheduleSection:
    return ScheduleSection(
        day_of_week="mon,wed,fri",
        hour=23,
        minute=0,
        catch_up_hours=24,
        misfire_grace_seconds=3600,
    )


def test_last_scheduled_run_finds_previous_scheduled_window():
    now = datetime(2026, 5, 7, 3, 30, tzinfo=UTC)

    last_run = last_scheduled_run(
        now=now,
        timezone_name="America/Santiago",
        schedule=_schedule(),
    )

    assert last_run is not None
    assert last_run.weekday() == 2
    assert last_run.hour == 23


def test_should_catch_up_when_recent_run_has_no_success():
    now = datetime(2026, 5, 7, 3, 30, tzinfo=UTC)

    should_run, scheduled_at = should_catch_up(
        now=now,
        timezone_name="America/Santiago",
        schedule=_schedule(),
        has_success_after=False,
    )

    assert should_run is True
    assert scheduled_at is not None


def test_should_not_catch_up_when_success_exists():
    now = datetime(2026, 5, 7, 3, 30, tzinfo=UTC)

    should_run, _ = should_catch_up(
        now=now,
        timezone_name="America/Santiago",
        schedule=_schedule(),
        has_success_after=True,
    )

    assert should_run is False


def test_sentry_crontab_uses_cron_weekdays():
    assert sentry_crontab(_schedule()) == "0 23 * * 1,3,5"
