"""Storage backend factory."""

from __future__ import annotations

from savh_backup.settings.config import StorageSection
from savh_backup.infrastructure.storage.base import StorageBackend
from savh_backup.infrastructure.storage.drive import GoogleDriveBackend
from savh_backup.infrastructure.storage.filesystem import FileSystemBackend


class StorageFactory:
    """Create storage backends from config."""

    @staticmethod
    def create(storage: StorageSection) -> StorageBackend:
        """Return the configured storage backend."""

        if storage.provider == "google_drive":
            return GoogleDriveBackend(storage)
        if storage.provider == "filesystem":
            if storage.filesystem_dir is None:
                raise ValueError("filesystem_dir is required")
            return FileSystemBackend(storage.filesystem_dir)
        raise ValueError(f"Unsupported storage provider: {storage.provider}")

