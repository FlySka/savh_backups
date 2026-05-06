from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[app]
name = "savh-erp-db-backup"
prefix = "savh_erp"
timezone = "America/Santiago"

[paths]
data_dir = "{data_dir}"
backup_dir = "{data_dir / "backups"}"
logs_dir = "{data_dir / "logs"}"
manifests_dir = "{data_dir / "manifests"}"
state_dir = "{data_dir / "state"}"

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
filesystem_dir = "{data_dir / "remote"}"
chunk_size_mb = 8

[retention]
local_days = 14
remote_days = 90

[encryption]
enabled = false

[sentry]
environment = "test"
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
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    return config_path

