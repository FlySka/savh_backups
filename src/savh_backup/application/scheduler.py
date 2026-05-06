"""APScheduler runtime."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from savh_backup.settings.config import AppConfig
from savh_backup.scheduling.utils import last_scheduled_run, should_catch_up
from savh_backup.application.service import BackupService

logger = logging.getLogger(__name__)


def run_scheduler(config: AppConfig, service: BackupService) -> None:
    """Run catch-up and then start the blocking scheduler."""

    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    _run_startup_catchup(config, service)

    scheduler = BlockingScheduler(timezone=ZoneInfo(config.app.timezone))
    trigger = CronTrigger(
        day_of_week=config.schedule.day_of_week,
        hour=config.schedule.hour,
        minute=config.schedule.minute,
        timezone=ZoneInfo(config.app.timezone),
    )
    scheduler.add_job(
        lambda: service.run_backup(reason="scheduled", scheduled_at=datetime.now(UTC)),
        trigger=trigger,
        id="savh-db-backup",
        name="SAVH ERP DB backup",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=config.schedule.misfire_grace_seconds,
        replace_existing=True,
    )
    logger.info(
        "Scheduler started",
        extra={
            "phase": "scheduler",
            "day_of_week": config.schedule.day_of_week,
            "hour": config.schedule.hour,
            "minute": config.schedule.minute,
            "timezone": config.app.timezone,
        },
    )
    scheduler.start()


def _run_startup_catchup(config: AppConfig, service: BackupService) -> None:
    now = datetime.now(UTC)
    last_run = last_scheduled_run(now=now, timezone_name=config.app.timezone, schedule=config.schedule)
    has_success_after = False
    if last_run is not None:
        has_success_after = service.state.was_success_after(last_run.astimezone(UTC))
    should_run, scheduled_at = should_catch_up(
        now=now,
        timezone_name=config.app.timezone,
        schedule=config.schedule,
        has_success_after=has_success_after,
    )
    if not should_run:
        logger.info(
            "No startup catch-up needed",
            extra={
                "phase": "scheduler",
                "last_scheduled_run": scheduled_at.isoformat() if scheduled_at else None,
            },
        )
        return
    logger.warning(
        "Startup catch-up backup will run",
        extra={"phase": "scheduler", "scheduled_at": scheduled_at.isoformat() if scheduled_at else None},
    )
    service.run_backup(reason="catch-up", scheduled_at=scheduled_at)

