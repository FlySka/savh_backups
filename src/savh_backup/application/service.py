"""High-level backup orchestration service."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from savh_backup.infrastructure.postgres.dump import BackupArtifact, PgDumpClient
from savh_backup.settings.config import AppConfig
from savh_backup.infrastructure.runtime.lock import FileLock
from savh_backup.infrastructure.runtime.manifest import ManifestRecorder
from savh_backup.infrastructure.observability.sentry import MonitoringClient
from savh_backup.application.postprocess import BackupPostProcessor
from savh_backup.application.retention import CleanupResult, run_cleanup
from savh_backup.infrastructure.runtime.state import StateStore
from savh_backup.infrastructure.storage.base import RemoteUpload, StorageBackend

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackupRunResult:
    """Summary of one backup run."""

    job_id: str
    artifact: BackupArtifact
    remote_upload: RemoteUpload
    cleanup: CleanupResult


class BackupService:
    """Orchestrate dump, upload, retention and audit state."""

    def __init__(
        self,
        *,
        config: AppConfig,
        pg_dump: PgDumpClient,
        storage: StorageBackend,
        post_processor: BackupPostProcessor,
        manifest: ManifestRecorder,
        state: StateStore,
        monitoring: MonitoringClient,
    ) -> None:
        self._config = config
        self._pg_dump = pg_dump
        self._storage = storage
        self._post_processor = post_processor
        self._manifest = manifest
        self._state = state
        self._monitoring = monitoring

    @property
    def state(self) -> StateStore:
        """Return the state store."""

        return self._state

    def run_backup(
        self,
        *,
        reason: str,
        scheduled_at: datetime | None = None,
    ) -> BackupRunResult:
        """Run one full backup job."""

        lock_path = self._config.paths.state_dir / "backup.lock"
        with FileLock(lock_path):
            return self._run_backup_locked(reason=reason, scheduled_at=scheduled_at)

    def cleanup(self) -> CleanupResult:
        """Apply retention cleanup without creating a new backup."""

        logger.info("Starting cleanup", extra={"phase": "cleanup"})
        result = run_cleanup(
            self._storage,
            backup_dir=self._config.paths.backup_dir,
            prefix=self._config.app.prefix,
            local_days=self._config.retention.local_days,
            remote_days=self._config.retention.remote_days,
        )
        logger.info(
            "Cleanup complete",
            extra={
                "phase": "cleanup",
                "local_deleted": len(result.local_deleted),
                "remote_deleted": len(result.remote_deleted),
            },
        )
        return result

    def _run_backup_locked(
        self,
        *,
        reason: str,
        scheduled_at: datetime | None,
    ) -> BackupRunResult:
        job_id = uuid.uuid4().hex
        phase = "start"
        started_monotonic = time.monotonic()
        started_at = datetime.now(UTC)
        checkin = self._monitoring.start_checkin()
        self._manifest.append(
            {
                "event": "backup_started",
                "status": "started",
                "job_id": job_id,
                "reason": reason,
                "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                "started_at": started_at.isoformat(),
            }
        )
        try:
            phase = "dump"
            backup_path = self._next_backup_path()
            artifact = self._pg_dump.create_backup(backup_path)

            phase = "postprocess"
            processed = self._post_processor.process(artifact.path)

            phase = "upload"
            upload = self._storage.upload_file(
                processed.path,
                remote_name=processed.path.name,
                metadata={
                    "prefix": self._config.app.prefix,
                    "job_id": job_id,
                    "database": self._config.database.database,
                    "sha256": artifact.sha256,
                    "size_bytes": str(artifact.size_bytes),
                    "created_at": artifact.completed_at.isoformat(),
                    "encryption_enabled": str(processed.encryption_enabled).lower(),
                },
            )

            phase = "cleanup"
            cleanup = self.cleanup()

            completed_at = datetime.now(UTC)
            duration = time.monotonic() - started_monotonic
            self._state.mark_success(job_id=job_id, completed_at=completed_at)
            self._manifest.append(
                {
                    "event": "backup_finished",
                    "status": "success",
                    "job_id": job_id,
                    "reason": reason,
                    "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "duration_seconds": round(duration, 3),
                    "local_path": str(artifact.path),
                    "size_bytes": artifact.size_bytes,
                    "sha256": artifact.sha256,
                    "remote_file_id": upload.file_id,
                    "remote_name": upload.name,
                    "remote_uri": upload.uri,
                    "local_deleted": cleanup.local_deleted,
                    "remote_deleted": cleanup.remote_deleted,
                }
            )
            self._monitoring.finish_checkin_ok(checkin, duration=duration)
            logger.info(
                "Backup job finished",
                extra={
                    "phase": "complete",
                    "job_id": job_id,
                    "duration_seconds": round(duration, 3),
                    "remote_file_id": upload.file_id,
                },
            )
            return BackupRunResult(
                job_id=job_id,
                artifact=artifact,
                remote_upload=upload,
                cleanup=cleanup,
            )
        except Exception as exc:
            duration = time.monotonic() - started_monotonic
            self._monitoring.capture_exception(exc, phase=phase)
            self._monitoring.finish_checkin_error(checkin, duration=duration)
            self._manifest.append(
                {
                    "event": "backup_finished",
                    "status": "error",
                    "job_id": job_id,
                    "reason": reason,
                    "phase": phase,
                    "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "duration_seconds": round(duration, 3),
                    "error_type": type(exc).__name__,
                    "error": _compact_error(str(exc)),
                }
            )
            logger.exception(
                "Backup job failed",
                extra={"phase": phase, "job_id": job_id, "duration_seconds": round(duration, 3)},
            )
            raise

    def _next_backup_path(self) -> Path:
        tz = ZoneInfo(self._config.app.timezone)
        timestamp = datetime.now(tz).strftime("%Y%m%d_%H%M%S")
        safe_timezone = self._config.app.timezone.replace("/", "-")
        filename = f"{self._config.app.prefix}_{timestamp}_{safe_timezone}.pgcustom"
        return self._config.paths.backup_dir / filename


def _compact_error(value: str, limit: int = 1000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"

