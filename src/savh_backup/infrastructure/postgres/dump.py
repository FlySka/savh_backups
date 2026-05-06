"""PostgreSQL dump and validation workflow."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from savh_backup.core.checksum import sha256_file
from savh_backup.settings.config import DatabaseSection

logger = logging.getLogger(__name__)


class BackupError(RuntimeError):
    """Raised when creating or validating a backup fails."""


@dataclass(frozen=True)
class BackupArtifact:
    """Created PostgreSQL backup file."""

    path: Path
    sha256: str
    size_bytes: int
    started_at: datetime
    completed_at: datetime


class PgDumpClient:
    """Create and validate PostgreSQL custom-format dumps."""

    def __init__(self, database: DatabaseSection) -> None:
        self._database = database

    def create_backup(self, output_path: Path) -> BackupArtifact:
        """Create a PostgreSQL custom-format dump and validate it."""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(UTC)
        logger.info("Starting pg_dump", extra={"phase": "dump", "backup_path": str(output_path)})
        command = [
            "pg_dump",
            "--format=custom",
            "--file",
            str(output_path),
            "--host",
            self._database.host,
            "--port",
            str(self._database.port),
            "--username",
            self._database.user,
            self._database.database,
        ]
        self._run(command, "pg_dump")
        self.validate_backup(output_path)
        completed_at = datetime.now(UTC)
        sha256 = sha256_file(output_path)
        size_bytes = output_path.stat().st_size
        logger.info(
            "Backup file created",
            extra={
                "phase": "dump",
                "backup_path": str(output_path),
                "size_bytes": size_bytes,
                "sha256": sha256,
            },
        )
        return BackupArtifact(
            path=output_path,
            sha256=sha256,
            size_bytes=size_bytes,
            started_at=started_at,
            completed_at=completed_at,
        )

    def validate_backup(self, output_path: Path) -> None:
        """Validate that pg_restore can read the generated custom archive."""

        logger.info(
            "Validating backup with pg_restore --list",
            extra={"phase": "dump", "backup_path": str(output_path)},
        )
        self._run(["pg_restore", "--list", str(output_path)], "pg_restore --list")

    def _run(self, command: list[str], label: str) -> None:
        env = os.environ.copy()
        env["PGPASSWORD"] = self._database.password
        env.setdefault("PGAPPNAME", "savh-erp-db-backup")
        result = subprocess.run(
            command,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            logger.error(
                "%s failed",
                label,
                extra={
                    "phase": "dump",
                    "returncode": result.returncode,
                    "stderr": _compact(result.stderr),
                },
            )
            raise BackupError(f"{label} failed with exit code {result.returncode}")


def _compact(value: str, limit: int = 2000) -> str:
    sanitized = value.strip()
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[:limit] + "...[truncated]"

