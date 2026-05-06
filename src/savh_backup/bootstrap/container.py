"""Factories for the runnable app service."""

from __future__ import annotations

from savh_backup.infrastructure.postgres.dump import PgDumpClient
from savh_backup.settings.config import AppConfig
from savh_backup.infrastructure.runtime.manifest import ManifestRecorder
from savh_backup.infrastructure.observability.sentry import MonitoringClient
from savh_backup.application.postprocess import PostProcessorFactory
from savh_backup.application.service import BackupService
from savh_backup.infrastructure.runtime.state import StateStore
from savh_backup.infrastructure.storage import StorageFactory


def build_backup_service(config: AppConfig, monitoring: MonitoringClient) -> BackupService:
    """Build the backup service graph."""

    return BackupService(
        config=config,
        pg_dump=PgDumpClient(config.database),
        storage=StorageFactory.create(config.storage),
        post_processor=PostProcessorFactory.create(config.encryption),
        manifest=ManifestRecorder(config.paths.manifests_dir),
        state=StateStore(config.paths.state_dir),
        monitoring=monitoring,
    )

