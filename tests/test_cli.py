from __future__ import annotations

import json
import subprocess
from pathlib import Path

from savh_backup.cli import main
from savh_backup.settings.config import ensure_runtime_directories, load_config


def _write_oauth_config(tmp_path: Path, *, create_client_secret: bool, create_token: bool) -> tuple[Path, Path, Path]:
    client_secret_path = tmp_path / "google-oauth-client.json"
    token_path = tmp_path / "google-oauth-token.json"
    if create_client_secret:
        client_secret_path.write_text("{}\n", encoding="utf-8")
    if create_token:
        token_path.write_text('{"token": "ready"}\n', encoding="utf-8")

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[app]
name = "savh-erp-db-backup"
prefix = "savh_erp"
timezone = "America/Santiago"

[paths]
data_dir = "{tmp_path / 'data'}"
backup_dir = "{tmp_path / 'data' / 'backups'}"
logs_dir = "{tmp_path / 'data' / 'logs'}"
manifests_dir = "{tmp_path / 'data' / 'manifests'}"
state_dir = "{tmp_path / 'data' / 'state'}"

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
oauth_client_secret_path = "{client_secret_path}"
oauth_token_path = "{token_path}"
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
    return config_path, client_secret_path, token_path


def test_run_once_via_cli_creates_backup_manifest_and_state(config_file, monkeypatch):
    config = load_config(config_file)
    ensure_runtime_directories(config)
    assert config.storage.filesystem_dir is not None

    def fake_run(command, **kwargs):
        if command[0] == "pg_dump":
            output_path = Path(command[command.index("--file") + 1])
            output_path.write_bytes(b"custom-backup")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "pg_restore":
            return subprocess.CompletedProcess(command, 0, "archive listing", "")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    exit_code = main(["--config", str(config_file), "run-once"])

    assert exit_code == 0

    backups = sorted(config.paths.backup_dir.glob("savh_erp_*.pgcustom"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"custom-backup"

    remote_files = sorted(config.storage.filesystem_dir.glob("savh_erp_*.pgcustom"))
    assert len(remote_files) == 1
    assert remote_files[0].read_bytes() == b"custom-backup"

    metadata_path = remote_files[0].with_name(remote_files[0].name + ".metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["app"] == "savh_backup"
    assert metadata["prefix"] == "savh_erp"
    assert metadata["database"] == "savh_erp"

    manifest_path = config.paths.manifests_dir / "backups.jsonl"
    manifest_lines = manifest_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(manifest_lines) == 2
    assert [json.loads(line)["status"] for line in manifest_lines] == ["started", "success"]

    state_path = config.paths.state_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_success_job_id"]
    assert state["last_success_at"]


def test_validate_config_reports_storage_error_cleanly(config_file, monkeypatch, capsys):
    monkeypatch.setattr("savh_backup.cli.shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        "savh_backup.cli.StorageFactory.create",
        lambda storage: (_ for _ in ()).throw(RuntimeError("drive inaccessible")),
    )

    exit_code = main(["--config", str(config_file), "validate-config"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Configuration error: drive inaccessible" in captured.err


def test_run_once_reports_service_build_error_cleanly(config_file, monkeypatch, capsys):
    monkeypatch.setattr(
        "savh_backup.cli.build_backup_service",
        lambda config, monitoring: (_ for _ in ()).throw(RuntimeError("drive inaccessible")),
    )

    exit_code = main(["--config", str(config_file), "run-once"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Configuration error: drive inaccessible" in captured.err


def test_validate_config_reports_missing_oauth_token_cleanly(tmp_path: Path, monkeypatch, capsys):
    config_path, _, token_path = _write_oauth_config(
        tmp_path,
        create_client_secret=True,
        create_token=False,
    )
    monkeypatch.setattr("savh_backup.cli.shutil.which", lambda tool: f"/usr/bin/{tool}")

    exit_code = main(["--config", str(config_path), "validate-config"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert f"Google Drive OAuth token does not exist: {token_path}" in captured.err
    assert "google-drive-login" in captured.err


def test_google_drive_login_runs_oauth_flow_and_validates_storage(tmp_path: Path, monkeypatch):
    config_path, _, token_path = _write_oauth_config(
        tmp_path,
        create_client_secret=True,
        create_token=False,
    )

    captured: dict[str, object] = {}

    def fake_login(storage, *, open_browser: bool):
        captured["provider"] = storage.provider
        captured["open_browser"] = open_browser
        token_path.write_text('{"token": "created"}\n', encoding="utf-8")
        return token_path

    monkeypatch.setattr("savh_backup.cli.run_google_drive_oauth_login", fake_login)
    monkeypatch.setattr("savh_backup.cli.StorageFactory.create", lambda storage: object())

    exit_code = main(["--config", str(config_path), "--no-browser", "google-drive-login"])

    assert exit_code == 0
    assert captured == {"provider": "google_drive_oauth", "open_browser": False}
    assert token_path.exists()


def test_google_drive_login_reports_missing_client_secret_cleanly(tmp_path: Path, capsys):
    config_path, client_secret_path, _ = _write_oauth_config(
        tmp_path,
        create_client_secret=False,
        create_token=False,
    )

    exit_code = main(["--config", str(config_path), "google-drive-login"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert f"Google Drive OAuth client secret file does not exist: {client_secret_path}" in captured.err