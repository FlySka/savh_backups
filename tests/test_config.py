from __future__ import annotations

from pathlib import Path

import pytest

from savh_backup.settings.config import ConfigError, ensure_runtime_directories, load_config


def test_load_config_from_toml_and_env(config_file):
    config = load_config(config_file)

    assert config.app.prefix == "savh_erp"
    assert config.database.database == "savh_erp"
    assert config.database.password == "secret"
    assert config.storage.provider == "filesystem"
    assert config.storage.oauth_client_secret_path is None
    assert config.storage.oauth_token_path is None
    assert config.storage.chunk_size_bytes == 8 * 1024 * 1024


def test_google_drive_placeholder_folder_id_is_rejected(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[app]
name = "savh-erp-db-backup"
prefix = "savh_erp"
timezone = "America/Santiago"

[paths]
data_dir = "data"
backup_dir = "data/backups"
logs_dir = "data/logs"
manifests_dir = "data/manifests"
state_dir = "data/state"

[database]
include_globals = false

[schedule]
day_of_week = "mon,wed,fri"
hour = 23
minute = 0
catch_up_hours = 24
misfire_grace_seconds = 3600

[storage]
provider = "google_drive"
drive_folder_id = "REEMPLAZAR_CON_FOLDER_ID"
chunk_size_mb = 8

[retention]
local_days = 14
remote_days = 90

[encryption]
enabled = false

[sentry]
environment = "production"
monitor_slug = "savh-erp-db-backup"
checkin_margin_minutes = 60
max_runtime_minutes = 180
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("PGHOST", "127.0.0.1")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGDATABASE", "savh_erp")
    monkeypatch.setenv("PGUSER", "savh_user")
    monkeypatch.setenv("PGPASSWORD", "secret")

    with pytest.raises(ConfigError, match="example placeholder"):
        load_config(config_path)


def test_google_drive_oauth_defaults_resolve_from_config_path(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[app]
name = "savh-erp-db-backup"
prefix = "savh_erp"
timezone = "America/Santiago"

[paths]
data_dir = "data"
backup_dir = "data/backups"
logs_dir = "data/logs"
manifests_dir = "data/manifests"
state_dir = "data/state"

[database]
include_globals = false

[schedule]
day_of_week = "mon,wed,fri"
hour = 23
minute = 0
catch_up_hours = 24
misfire_grace_seconds = 3600

[storage]
provider = "google_drive_oauth"
drive_folder_id = "folder-123"
chunk_size_mb = 8

[retention]
local_days = 14
remote_days = 90

[encryption]
enabled = false

[sentry]
environment = "development"
monitor_slug = "savh-erp-db-backup"
checkin_margin_minutes = 60
max_runtime_minutes = 180
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("PGHOST", "127.0.0.1")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGDATABASE", "savh_erp")
    monkeypatch.setenv("PGUSER", "savh_user")
    monkeypatch.setenv("PGPASSWORD", "secret")

    config = load_config(config_path)

    assert config.storage.provider == "google_drive_oauth"
    assert config.storage.oauth_client_secret_path == tmp_path.parent / "secrets" / "google-oauth-client.json"
    assert config.storage.oauth_token_path == tmp_path.parent / "secrets" / "google-oauth-token.json"


def test_google_drive_oauth_requires_folder_id(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[app]
name = "savh-erp-db-backup"
prefix = "savh_erp"
timezone = "America/Santiago"

[paths]
data_dir = "data"
backup_dir = "data/backups"
logs_dir = "data/logs"
manifests_dir = "data/manifests"
state_dir = "data/state"

[database]
include_globals = false

[schedule]
day_of_week = "mon,wed,fri"
hour = 23
minute = 0
catch_up_hours = 24
misfire_grace_seconds = 3600

[storage]
provider = "google_drive_oauth"
chunk_size_mb = 8

[retention]
local_days = 14
remote_days = 90

[encryption]
enabled = false

[sentry]
environment = "development"
monitor_slug = "savh-erp-db-backup"
checkin_margin_minutes = 60
max_runtime_minutes = 180
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("PGHOST", "127.0.0.1")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGDATABASE", "savh_erp")
    monkeypatch.setenv("PGUSER", "savh_user")
    monkeypatch.setenv("PGPASSWORD", "secret")

    with pytest.raises(ConfigError, match="storage.drive_folder_id is required for google_drive_oauth"):
        load_config(config_path)


def test_ensure_runtime_directories_creates_paths(config_file):
    config = load_config(config_file)
    ensure_runtime_directories(config)

    assert config.paths.backup_dir.is_dir()
    assert config.paths.logs_dir.is_dir()
    assert config.paths.manifests_dir.is_dir()
    assert config.paths.state_dir.is_dir()
    assert config.storage.filesystem_dir is not None
    assert config.storage.filesystem_dir.is_dir()


def test_missing_database_env_is_rejected(config_file, monkeypatch):
    monkeypatch.delenv("PGPASSWORD")
    monkeypatch.chdir(config_file.parent)

    with pytest.raises(ConfigError, match="PGPASSWORD"):
        load_config(config_file)


def test_load_config_uses_dotenv_for_local_poetry_runs(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.local.toml"
    config_path.write_text(
        """
[app]
name = "savh-erp-db-backup"
prefix = "savh_erp"
timezone = "America/Santiago"

[paths]
data_dir = "data"
backup_dir = "data/backups"
logs_dir = "data/logs"
manifests_dir = "data/manifests"
state_dir = "data/state"

[database]
include_globals = false

[schedule]
day_of_week = "mon,wed,fri"
hour = 23
minute = 0
catch_up_hours = 24
misfire_grace_seconds = 3600

[storage]
provider = "filesystem"
filesystem_dir = "data/remote"
chunk_size_mb = 8

[retention]
local_days = 14
remote_days = 90

[encryption]
enabled = false

[sentry]
environment = "development"
monitor_slug = "savh-erp-db-backup"
checkin_margin_minutes = 60
max_runtime_minutes = 180
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "SAVH_BACKUP_CONFIG=config.local.toml",
                "PGHOST=127.0.0.1",
                "PGPORT=5432",
                "PGDATABASE=savh_erp",
                "PGUSER=savh_user",
                "PGPASSWORD=secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for key in ("SAVH_BACKUP_CONFIG", "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        monkeypatch.delenv(key, raising=False)

    config = load_config()

    assert config.source_path == config_path
    assert config.database.host == "127.0.0.1"
    assert config.storage.provider == "filesystem"
    assert config.paths.backup_dir == tmp_path / "data" / "backups"

