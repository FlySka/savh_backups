"""Sentry setup and cron check-ins."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from savh_backup.settings.config import AppConfig
from savh_backup.scheduling.utils import sentry_crontab

logger = logging.getLogger(__name__)


@dataclass
class CheckIn:
    """Running Sentry check-in state."""

    check_in_id: str | None


class MonitoringClient:
    """Thin wrapper around Sentry that degrades cleanly when disabled."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._enabled = False
        self._sentry_sdk = None
        self._monitor_status = None
        self._capture_checkin = None
        self._init_sentry()

    @property
    def enabled(self) -> bool:
        """Return whether Sentry is enabled."""

        return self._enabled

    def start_checkin(self) -> CheckIn:
        """Mark a cron check-in as in progress."""

        if not self._can_checkin():
            return CheckIn(check_in_id=None)
        try:
            check_in_id = self._capture_checkin(
                monitor_slug=self._config.sentry.monitor_slug,
                status=self._monitor_status.IN_PROGRESS,
                monitor_config={
                    "schedule": {
                        "type": "crontab",
                        "value": sentry_crontab(self._config.schedule),
                    },
                    "timezone": self._config.app.timezone,
                    "checkin_margin": self._config.sentry.checkin_margin_minutes,
                    "max_runtime": self._config.sentry.max_runtime_minutes,
                },
            )
            return CheckIn(check_in_id=str(check_in_id) if check_in_id else None)
        except Exception:
            logger.exception("Could not send Sentry check-in start")
            return CheckIn(check_in_id=None)

    def finish_checkin_ok(self, checkin: CheckIn, *, duration: float) -> None:
        """Mark a cron check-in as successful."""

        self._finish_checkin(checkin, status_name="OK", duration=duration)

    def finish_checkin_error(self, checkin: CheckIn, *, duration: float) -> None:
        """Mark a cron check-in as failed."""

        self._finish_checkin(checkin, status_name="ERROR", duration=duration)

    def capture_exception(self, exc: BaseException, *, phase: str) -> None:
        """Send an exception to Sentry with a phase tag."""

        if not self._enabled or self._sentry_sdk is None:
            return
        try:
            with self._sentry_sdk.new_scope() as scope:
                scope.set_tag("phase", phase)
                scope.set_tag("app", self._config.app.name)
                self._sentry_sdk.capture_exception(exc)
        except Exception:
            logger.exception("Could not capture exception in Sentry")

    def _finish_checkin(self, checkin: CheckIn, *, status_name: str, duration: float) -> None:
        if not self._can_checkin() or checkin.check_in_id is None:
            return
        try:
            status = getattr(self._monitor_status, status_name)
            self._capture_checkin(
                monitor_slug=self._config.sentry.monitor_slug,
                check_in_id=checkin.check_in_id,
                status=status,
                duration=duration,
            )
        except Exception:
            logger.exception("Could not send Sentry check-in finish")

    def _can_checkin(self) -> bool:
        return (
            self._enabled
            and self._config.sentry.monitor_slug is not None
            and self._capture_checkin is not None
            and self._monitor_status is not None
        )

    def _init_sentry(self) -> None:
        if not self._config.sentry.dsn:
            return
        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration

            try:
                from sentry_sdk.crons import MonitorStatus, capture_checkin
            except Exception:
                MonitorStatus = None
                capture_checkin = None

            sentry_sdk.init(
                dsn=self._config.sentry.dsn,
                environment=self._config.sentry.environment,
                send_default_pii=False,
                traces_sample_rate=0.0,
                profiles_sample_rate=0.0,
                integrations=[
                    LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
                ],
            )
            sentry_sdk.set_tag("app", self._config.app.name)
            self._sentry_sdk = sentry_sdk
            self._monitor_status = MonitorStatus
            self._capture_checkin = capture_checkin
            self._enabled = True
        except Exception:
            logger.exception("Sentry could not be initialized")

