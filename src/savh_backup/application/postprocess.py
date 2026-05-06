"""Post-processing extension points for generated backups."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from savh_backup.settings.config import EncryptionSection


class PostProcessorError(RuntimeError):
    """Raised when post-processing fails."""


@dataclass(frozen=True)
class ProcessedBackup:
    """Backup artifact after optional post-processing."""

    path: Path
    encryption_enabled: bool


class BackupPostProcessor:
    """Interface for backup post-processing."""

    def process(self, path: Path) -> ProcessedBackup:
        """Process a backup and return the uploadable file."""

        raise NotImplementedError


class NoopPostProcessor(BackupPostProcessor):
    """Pass backups through unchanged."""

    def process(self, path: Path) -> ProcessedBackup:
        """Return the original path without encryption."""

        return ProcessedBackup(path=path, encryption_enabled=False)


class PostProcessorFactory:
    """Create post-processors from config."""

    @staticmethod
    def create(encryption: EncryptionSection) -> BackupPostProcessor:
        """Return the configured post-processor."""

        if encryption.enabled:
            raise PostProcessorError("Encryption is reserved for a future version")
        return NoopPostProcessor()

