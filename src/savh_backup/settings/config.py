"""Configuration loading for the backup app."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


class ConfigError(RuntimeError):
    """Raised when the app configuration is invalid."""


_PLACEHOLDER_DRIVE_FOLDER_IDS = {"REEMPLAZAR_CON_FOLDER_ID", "CHANGE_ME", "YOUR_FOLDER_ID"}


@dataclass(frozen=True)
class AppSection:
    """General app settings."""

    name: str
    prefix: str
    timezone: str


@dataclass(frozen=True)
class PathsSection:
    """Filesystem paths used by the app."""

    data_dir: Path
    backup_dir: Path
    logs_dir: Path
    manifests_dir: Path
    state_dir: Path


@dataclass(frozen=True)
class DatabaseSection:
    """PostgreSQL connection settings."""

    host: str
    port: int
    database: str
    user: str
    password: str
    include_globals: bool


@dataclass(frozen=True)
class ScheduleSection:
    """Cron schedule settings."""

    day_of_week: str
    hour: int
    minute: int
    catch_up_hours: int
    misfire_grace_seconds: int


@dataclass(frozen=True)
class StorageSection:
    """Storage backend settings."""

    provider: str
    drive_folder_id: str | None
    filesystem_dir: Path | None
    oauth_client_secret_path: Path | None
    oauth_token_path: Path | None
    chunk_size_bytes: int


@dataclass(frozen=True)
class RetentionSection:
    """Backup retention settings."""

    local_days: int
    remote_days: int


@dataclass(frozen=True)
class EncryptionSection:
    """Backup encryption settings."""

    enabled: bool


@dataclass(frozen=True)
class SentrySection:
    """Sentry settings."""

    dsn: str | None
    environment: str
    monitor_slug: str | None
    checkin_margin_minutes: int
    max_runtime_minutes: int


@dataclass(frozen=True)
class AppConfig:
    """Complete app configuration."""

    app: AppSection
    paths: PathsSection
    database: DatabaseSection
    schedule: ScheduleSection
    storage: StorageSection
    retention: RetentionSection
    encryption: EncryptionSection
    sentry: SentrySection
    source_path: Path


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load configuration from TOML and environment variables.

    Args:
        path: Optional TOML config path. Defaults to `SAVH_BACKUP_CONFIG` or
            `config/config.toml`.

    Returns:
        Parsed app configuration.

    Raises:
        ConfigError: If required values are missing or invalid.
    """

    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    config_path = Path(path or os.environ.get("SAVH_BACKUP_CONFIG", "config/config.toml")).expanduser()
    if not config_path.is_absolute():
        config_path = config_path.resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file does not exist: {config_path}")

    with config_path.open("rb") as file_obj:
        raw = tomllib.load(file_obj)

    app_raw = _section(raw, "app")
    paths_raw = _section(raw, "paths")
    database_raw = _section(raw, "database")
    schedule_raw = _section(raw, "schedule")
    storage_raw = _section(raw, "storage")
    retention_raw = _section(raw, "retention")
    encryption_raw = _section(raw, "encryption")
    sentry_raw = _section(raw, "sentry")

    storage_provider = _str(storage_raw, "provider")

    config = AppConfig(
        app=AppSection(
            name=_str(app_raw, "name"),
            prefix=_str(app_raw, "prefix"),
            timezone=_str(app_raw, "timezone"),
        ),
        paths=PathsSection(
            data_dir=_path(paths_raw, "data_dir", config_path),
            backup_dir=_path(paths_raw, "backup_dir", config_path),
            logs_dir=_path(paths_raw, "logs_dir", config_path),
            manifests_dir=_path(paths_raw, "manifests_dir", config_path),
            state_dir=_path(paths_raw, "state_dir", config_path),
        ),
        database=DatabaseSection(
            host=_env_required("PGHOST"),
            port=_env_int("PGPORT", 5432),
            database=_env_required("PGDATABASE"),
            user=_env_required("PGUSER"),
            password=_env_required("PGPASSWORD"),
            include_globals=bool(database_raw.get("include_globals", False)),
        ),
        schedule=ScheduleSection(
            day_of_week=_str(schedule_raw, "day_of_week"),
            hour=_int(schedule_raw, "hour"),
            minute=_int(schedule_raw, "minute"),
            catch_up_hours=_int(schedule_raw, "catch_up_hours"),
            misfire_grace_seconds=_int(schedule_raw, "misfire_grace_seconds"),
        ),
        storage=StorageSection(
            provider=storage_provider,
            drive_folder_id=_optional_str(storage_raw, "drive_folder_id"),
            filesystem_dir=_optional_path(storage_raw, "filesystem_dir", config_path),
            oauth_client_secret_path=_storage_optional_path(
                storage_raw,
                "oauth_client_secret_path",
                config_path,
                default="../secrets/google-oauth-client.json" if storage_provider == "google_drive_oauth" else None,
            ),
            oauth_token_path=_storage_optional_path(
                storage_raw,
                "oauth_token_path",
                config_path,
                default="../secrets/google-oauth-token.json" if storage_provider == "google_drive_oauth" else None,
            ),
            chunk_size_bytes=_chunk_size_bytes(storage_raw),
        ),
        retention=RetentionSection(
            local_days=_int(retention_raw, "local_days"),
            remote_days=_int(retention_raw, "remote_days"),
        ),
        encryption=EncryptionSection(
            enabled=bool(encryption_raw.get("enabled", False)),
        ),
        sentry=SentrySection(
            dsn=_env_optional("SENTRY_DSN"),
            environment=_str(sentry_raw, "environment"),
            monitor_slug=_optional_str(sentry_raw, "monitor_slug"),
            checkin_margin_minutes=_int(sentry_raw, "checkin_margin_minutes"),
            max_runtime_minutes=_int(sentry_raw, "max_runtime_minutes"),
        ),
        source_path=config_path,
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    """Validate parsed configuration."""

    if not config.app.prefix:
        raise ConfigError("app.prefix cannot be empty")
    if config.schedule.hour < 0 or config.schedule.hour > 23:
        raise ConfigError("schedule.hour must be between 0 and 23")
    if config.schedule.minute < 0 or config.schedule.minute > 59:
        raise ConfigError("schedule.minute must be between 0 and 59")
    if config.schedule.catch_up_hours <= 0:
        raise ConfigError("schedule.catch_up_hours must be positive")
    if config.retention.local_days < 0 or config.retention.remote_days < 0:
        raise ConfigError("retention days cannot be negative")
    if config.storage.chunk_size_bytes < 256 * 1024:
        raise ConfigError("storage.chunk_size_mb must be at least 1")
    if config.storage.chunk_size_bytes % (256 * 1024) != 0:
        raise ConfigError("storage.chunk_size_mb must produce a multiple of 256 KiB")
    if config.storage.provider in {"google_drive", "google_drive_oauth"}:
        if not config.storage.drive_folder_id:
            raise ConfigError(f"storage.drive_folder_id is required for {config.storage.provider}")
        if config.storage.drive_folder_id in _PLACEHOLDER_DRIVE_FOLDER_IDS:
            raise ConfigError(
                "storage.drive_folder_id still uses the example placeholder; set the real Google Drive folder id or switch to filesystem for local runs"
            )
        if config.storage.provider == "google_drive_oauth":
            if config.storage.oauth_client_secret_path is None:
                raise ConfigError("storage.oauth_client_secret_path is required for google_drive_oauth")
            if config.storage.oauth_token_path is None:
                raise ConfigError("storage.oauth_token_path is required for google_drive_oauth")
    elif config.storage.provider == "filesystem":
        if config.storage.filesystem_dir is None:
            raise ConfigError("storage.filesystem_dir is required for filesystem")
    else:
        raise ConfigError(f"Unsupported storage provider: {config.storage.provider}")
    if config.encryption.enabled:
        raise ConfigError("encryption.enabled=true is reserved for a future version")


def ensure_runtime_directories(config: AppConfig) -> None:
    """Create runtime directories used for logs, state, manifests and backups."""

    for path in (
        config.paths.data_dir,
        config.paths.backup_dir,
        config.paths.logs_dir,
        config.paths.manifests_dir,
        config.paths.state_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    if config.storage.provider == "filesystem" and config.storage.filesystem_dir is not None:
        config.storage.filesystem_dir.mkdir(parents=True, exist_ok=True)


def _section(raw: dict[str, object], name: str) -> dict[str, object]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing [{name}] section")
    return value


def _str(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"Missing or invalid string: {key}")
    return value


def _optional_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Invalid string: {key}")
    return value or None


def _int(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Missing or invalid integer: {key}")
    return value


def _path(raw: dict[str, object], key: str, config_path: Path) -> Path:
    return _resolve_path(_str(raw, key), config_path)


def _optional_path(raw: dict[str, object], key: str, config_path: Path) -> Path | None:
    value = _optional_str(raw, key)
    if value is None:
        return None
    return _resolve_path(value, config_path)


def _storage_optional_path(
    raw: dict[str, object],
    key: str,
    config_path: Path,
    *,
    default: str | None,
) -> Path | None:
    value = _optional_str(raw, key)
    if value is None:
        if default is None:
            return None
        value = default
    return _resolve_path(value, config_path)


def _resolve_path(value: str, config_path: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (config_path.parent / path).resolve()


def _env_required(key: str) -> str:
    value = os.environ.get(key)
    if value is None or value == "":
        raise ConfigError(f"Missing required environment variable: {key}")
    return value


def _env_optional(key: str) -> str | None:
    value = os.environ.get(key)
    return value or None


def _env_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid integer environment variable: {key}") from exc


def _chunk_size_bytes(raw: dict[str, object]) -> int:
    chunk_size_mb = _int(raw, "chunk_size_mb")
    return chunk_size_mb * 1024 * 1024

