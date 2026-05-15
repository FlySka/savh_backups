"""Command line interface."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

from savh_backup.bootstrap.container import build_backup_service
from savh_backup.infrastructure.storage import StorageFactory
from savh_backup.infrastructure.storage.drive_auth import run_google_drive_oauth_login
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
        logger.info(
            "Using config file %s",
            config.source_path,
            extra={
                "phase": "startup",
                "command": args.command,
                "config_path": str(config.source_path),
            },
        )

        if args.command == "validate-config":
            _validate_runtime(config)
            logger.info("Configuration is valid", extra={"phase": "validate"})
            return 0

        if args.command == "google-drive-login":
            if config.storage.provider != "google_drive_oauth":
                raise ConfigError(
                    "google-drive-login requires storage.provider=google_drive_oauth in the selected config file"
                )
            try:
                token_path = run_google_drive_oauth_login(config.storage, open_browser=not args.no_browser)
            except (RuntimeError, ValueError) as exc:
                raise ConfigError(str(exc)) from exc
            logger.info(
                "Google Drive OAuth token saved",
                extra={"phase": "auth", "token_path": str(token_path), "config_path": str(config.source_path)},
            )
            _validate_storage(config)
            logger.info("Google Drive OAuth login complete", extra={"phase": "auth"})
            return 0

        monitoring = MonitoringClient(config)

        try:
            service = build_backup_service(config, monitoring)
        except (RuntimeError, ValueError) as exc:
            raise ConfigError(str(exc)) from exc
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
        "--no-browser",
        action="store_true",
        help="Do not automatically open the browser during google-drive-login.",
    )
    parser.add_argument(
        "command",
        choices=("scheduler", "run-once", "validate-config", "cleanup", "google-drive-login"),
        help="Command to run.",
    )
    return parser


def _validate_runtime(config: AppConfig) -> None:
    _validate_backup_tools()
    _validate_storage(config)
    logger.info(
        "Runtime config path exists",
        extra={"phase": "validate", "config_path": str(config.source_path)},
    )


def _validate_backup_tools() -> None:
    missing_tools = [tool for tool in ("pg_dump", "pg_restore") if shutil.which(tool) is None]
    if missing_tools:
        raise ConfigError(f"Missing required executable(s): {', '.join(missing_tools)}")


def _validate_storage(config: AppConfig) -> None:
    if config.storage.provider == "google_drive":
        credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not credentials_path:
            raise ConfigError("GOOGLE_APPLICATION_CREDENTIALS is required for google_drive")
        if not Path(credentials_path).exists():
            raise ConfigError(f"Google credentials file does not exist: {credentials_path}")
    elif config.storage.provider == "google_drive_oauth":
        if config.storage.oauth_client_secret_path is None:
            raise ConfigError("storage.oauth_client_secret_path is required for google_drive_oauth")
        if not config.storage.oauth_client_secret_path.exists():
            raise ConfigError(
                f"Google Drive OAuth client secret file does not exist: {config.storage.oauth_client_secret_path}"
            )
        if config.storage.oauth_token_path is None:
            raise ConfigError("storage.oauth_token_path is required for google_drive_oauth")
        if not config.storage.oauth_token_path.exists():
            raise ConfigError(
                f"Google Drive OAuth token does not exist: {config.storage.oauth_token_path}. "
                f"Run `savh-backup --config {config.source_path} google-drive-login` to authorize access."
            )
    try:
        StorageFactory.create(config.storage)
    except (RuntimeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc
