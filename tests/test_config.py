from __future__ import annotations

import pytest

from savh_backup.settings.config import ConfigError, ensure_runtime_directories, load_config


def test_load_config_from_toml_and_env(config_file):
    config = load_config(config_file)

    assert config.app.prefix == "savh_erp"
    assert config.database.database == "savh_erp"
    assert config.database.password == "secret"
    assert config.storage.provider == "filesystem"
    assert config.storage.chunk_size_bytes == 8 * 1024 * 1024


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

    with pytest.raises(ConfigError, match="PGPASSWORD"):
        load_config(config_file)

