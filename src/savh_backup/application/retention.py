"""Retention cleanup for local and remote backups."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from savh_backup.infrastructure.storage.base import APP_MARKER, StorageBackend

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupResult:
    """Summary of deleted backups."""

    local_deleted: list[str]
    remote_deleted: list[str]


def cleanup_local(
    backup_dir: Path,
    *,
    prefix: str,
    retention_days: int,
    now: datetime | None = None,
) -> list[str]:
    """Delete local app-created backups older than the retention window."""

    current = now or datetime.now(UTC)
    threshold = current - timedelta(days=retention_days)
    deleted: list[str] = []
    if not backup_dir.exists():
        return deleted
    for path in backup_dir.glob(f"{prefix}_*"):
        if not path.is_file():
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if modified_at >= threshold:
            continue
        path.unlink()
        deleted.append(path.name)
        logger.info("Deleted local backup", extra={"phase": "cleanup", "backup_name": path.name})
    return deleted


def cleanup_remote(
    storage: StorageBackend,
    *,
    prefix: str,
    retention_days: int,
    now: datetime | None = None,
) -> list[str]:
    """Delete remote app-created backups older than the retention window."""

    current = now or datetime.now(UTC)
    threshold = current - timedelta(days=retention_days)
    deleted: list[str] = []
    for remote_file in storage.list_backups(prefix=prefix):
        if remote_file.metadata.get("app") != APP_MARKER:
            continue
        if remote_file.metadata.get("prefix") != prefix:
            continue
        if remote_file.created_at >= threshold:
            continue
        storage.delete_file(remote_file.file_id)
        deleted.append(remote_file.name)
    return deleted


def run_cleanup(
    storage: StorageBackend,
    *,
    backup_dir: Path,
    prefix: str,
    local_days: int,
    remote_days: int,
    now: datetime | None = None,
) -> CleanupResult:
    """Apply local and remote retention."""

    return CleanupResult(
        local_deleted=cleanup_local(
            backup_dir,
            prefix=prefix,
            retention_days=local_days,
            now=now,
        ),
        remote_deleted=cleanup_remote(
            storage,
            prefix=prefix,
            retention_days=remote_days,
            now=now,
        ),
    )
