"""Storage backend contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

APP_MARKER = "savh_backup"


@dataclass(frozen=True)
class RemoteUpload:
    """Result of uploading a backup to remote storage."""

    file_id: str
    name: str
    uri: str
    size_bytes: int | None
    created_at: datetime | None


@dataclass(frozen=True)
class RemoteFile:
    """Remote file eligible for retention cleanup."""

    file_id: str
    name: str
    created_at: datetime
    metadata: dict[str, str]


class StorageBackend(Protocol):
    """Interface for remote backup storage."""

    def upload_file(
        self,
        path: Path,
        *,
        remote_name: str,
        metadata: dict[str, str],
    ) -> RemoteUpload:
        """Upload a local file and return remote metadata."""

    def list_backups(self, *, prefix: str) -> list[RemoteFile]:
        """List app-owned remote backup files for a prefix."""

    def delete_file(self, file_id: str) -> None:
        """Delete one remote file."""
