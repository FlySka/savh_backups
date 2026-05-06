from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from savh_backup.infrastructure.postgres.dump import BackupError, PgDumpClient
from savh_backup.settings.config import DatabaseSection


def _database() -> DatabaseSection:
    return DatabaseSection(
        host="127.0.0.1",
        port=5432,
        database="savh_erp",
        user="savh_user",
        password="secret",
        include_globals=False,
    )


def test_pg_dump_client_creates_validated_artifact(tmp_path: Path, monkeypatch):
    def fake_run(command, **kwargs):
        if command[0] == "pg_dump":
            output_path = Path(command[command.index("--file") + 1])
            output_path.write_bytes(b"custom-backup")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    artifact = PgDumpClient(_database()).create_backup(tmp_path / "savh_erp_test.pgcustom")

    assert artifact.path.exists()
    assert artifact.size_bytes == len(b"custom-backup")
    assert artifact.sha256 == "4bdfdb1f6e1c8034ac92697fdae39d475194d9b84c3e7331d11a32f4f4ab7e9b"


def test_pg_dump_client_raises_on_dump_failure(tmp_path: Path, monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, "", "connection failed")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(BackupError):
        PgDumpClient(_database()).create_backup(tmp_path / "savh_erp_test.pgcustom")
