from __future__ import annotations

from pathlib import Path

from savh_backup.settings.config import ensure_runtime_directories, load_config
from savh_backup.infrastructure.storage import StorageFactory


def test_storage_factory_creates_filesystem_backend_and_tracks_metadata(config_file):
    config = load_config(config_file)
    ensure_runtime_directories(config)
    storage = StorageFactory.create(config.storage)
    local_file = config.paths.backup_dir / "savh_erp_test.pgcustom"
    local_file.write_bytes(b"backup")

    upload = storage.upload_file(
        local_file,
        remote_name=local_file.name,
        metadata={"prefix": "savh_erp", "job_id": "abc"},
    )
    listed = storage.list_backups(prefix="savh_erp")

    assert upload.file_id == local_file.name
    assert [item.file_id for item in listed] == [local_file.name]
    assert listed[0].metadata["app"] == "savh_backup"
    assert listed[0].metadata["prefix"] == "savh_erp"

    storage.delete_file(upload.file_id)

    assert storage.list_backups(prefix="savh_erp") == []

