from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from savh_backup.application.retention import cleanup_local, cleanup_remote
from savh_backup.infrastructure.storage.base import APP_MARKER, RemoteFile


class FakeStorage:
    def __init__(self, files: list[RemoteFile]) -> None:
        self.files = files
        self.deleted: list[str] = []

    def upload_file(self, path, *, remote_name, metadata):
        raise NotImplementedError

    def list_backups(self, *, prefix: str) -> list[RemoteFile]:
        return self.files

    def delete_file(self, file_id: str) -> None:
        self.deleted.append(file_id)


def test_cleanup_local_deletes_only_old_prefixed_files(tmp_path: Path):
    now = datetime(2026, 5, 6, tzinfo=UTC)
    old = tmp_path / "savh_erp_old.pgcustom"
    new = tmp_path / "savh_erp_new.pgcustom"
    other = tmp_path / "other_old.pgcustom"
    for path in (old, new, other):
        path.write_text("x", encoding="utf-8")
    old_time = (now - timedelta(days=15)).timestamp()
    new_time = (now - timedelta(days=2)).timestamp()
    os.utime(old, (old_time, old_time))
    os.utime(new, (new_time, new_time))
    os.utime(other, (old_time, old_time))

    deleted = cleanup_local(tmp_path, prefix="savh_erp", retention_days=14, now=now)

    assert deleted == ["savh_erp_old.pgcustom"]
    assert not old.exists()
    assert new.exists()
    assert other.exists()


def test_cleanup_remote_deletes_only_owned_old_files():
    now = datetime(2026, 5, 6, tzinfo=UTC)
    storage = FakeStorage(
        [
            RemoteFile(
                file_id="old",
                name="savh_erp_old.pgcustom",
                created_at=now - timedelta(days=91),
                metadata={"app": APP_MARKER, "prefix": "savh_erp"},
            ),
            RemoteFile(
                file_id="foreign",
                name="savh_erp_foreign.pgcustom",
                created_at=now - timedelta(days=91),
                metadata={"app": "other", "prefix": "savh_erp"},
            ),
            RemoteFile(
                file_id="new",
                name="savh_erp_new.pgcustom",
                created_at=now - timedelta(days=10),
                metadata={"app": APP_MARKER, "prefix": "savh_erp"},
            ),
        ]
    )

    deleted = cleanup_remote(storage, prefix="savh_erp", retention_days=90, now=now)

    assert deleted == ["savh_erp_old.pgcustom"]
    assert storage.deleted == ["old"]
