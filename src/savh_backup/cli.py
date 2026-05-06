"""Command line interface."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

from savh_backup.bootstrap.container import build_backup_service
from savh_backup.settings.config import AppConfig, ConfigError, ensure_runtime_directories, load_config
from savh_backup.infrastructure.observability.logging_setup import configure_logging
from savh_backup.infrastructure.observability.sentry import MonitoringClient

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        ensure_runtime_directories(config)
        configure_logging(config.paths.logs_dir)
        monitoring = MonitoringClient(config)

        if args.command == "validate-config":
            _validate_runtime(config)
            logger.info("Configuration is valid", extra={"phase": "validate"})
            return 0

        service = build_backup_service(config, monitoring)
        if args.command == "run-once":
            service.run_backup(reason="manual")
            return 0
        if args.command == "cleanup":
            service.cleanup()
            return 0
        if args.command == "scheduler":
            from savh_backup.application.scheduler import run_scheduler

            run_scheduler(config, service)
            return 0
        parser.error(f"Unknown command: {args.command}")
        return 2
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception:
        logger.exception("Command failed", extra={"phase": "cli"})
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="savh-backup")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config TOML. Defaults to SAVH_BACKUP_CONFIG or config/config.toml.",
    )
    parser.add_argument(
        "command",
        choices=("scheduler", "run-once", "validate-config", "cleanup"),
        help="Command to run.",
    )
    return parser


def _validate_runtime(config: AppConfig) -> None:
    missing_tools = [tool for tool in ("pg_dump", "pg_restore") if shutil.which(tool) is None]
    if missing_tools:
        raise ConfigError(f"Missing required executable(s): {', '.join(missing_tools)}")
    if config.storage.provider == "google_drive":
        credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not credentials_path:
            raise ConfigError("GOOGLE_APPLICATION_CREDENTIALS is required for google_drive")
        if not Path(credentials_path).exists():
            raise ConfigError(f"Google credentials file does not exist: {credentials_path}")
    logger.info(
        "Runtime config path exists",
        extra={"phase": "validate", "config_path": str(config.source_path)},
    )
