"""Filesystem storage backend for local tests and dry deployments."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from savh_backup.infrastructure.storage.base import APP_MARKER, RemoteFile, RemoteUpload


class FileSystemBackend:
    """Store uploaded backups in a local directory."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def upload_file(
        self,
        path: Path,
        *,
        remote_name: str,
        metadata: dict[str, str],
    ) -> RemoteUpload:
        """Copy a backup into the filesystem backend directory."""

        destination = self._root_dir / remote_name
        shutil.copy2(path, destination)
        properties = {"app": APP_MARKER, **metadata}
        metadata_path = self._metadata_path(destination)
        with metadata_path.open("w", encoding="utf-8") as file_obj:
            json.dump(properties, file_obj, ensure_ascii=True, indent=2)
            file_obj.write("\n")
        created_at = datetime.fromtimestamp(destination.stat().st_mtime, UTC)
        return RemoteUpload(
            file_id=destination.name,
            name=destination.name,
            uri=str(destination),
            size_bytes=destination.stat().st_size,
            created_at=created_at,
        )

    def list_backups(self, *, prefix: str) -> list[RemoteFile]:
        """List app-owned backups in the filesystem backend."""

        files: list[RemoteFile] = []
        for path in self._root_dir.glob(f"{prefix}_*"):
            if path.name.endswith(".metadata.json") or not path.is_file():
                continue
            metadata = self._load_metadata(path)
            if metadata.get("app") != APP_MARKER or metadata.get("prefix") != prefix:
                continue
            files.append(
                RemoteFile(
                    file_id=path.name,
                    name=path.name,
                    created_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
                    metadata=metadata,
                )
            )
        return files

    def delete_file(self, file_id: str) -> None:
        """Delete a stored backup and its sidecar metadata."""

        path = self._root_dir / file_id
        path.unlink(missing_ok=True)
        self._metadata_path(path).unlink(missing_ok=True)

    def _load_metadata(self, path: Path) -> dict[str, str]:
        metadata_path = self._metadata_path(path)
        if not metadata_path.exists():
            return {}
        with metadata_path.open("r", encoding="utf-8") as file_obj:
            raw = json.load(file_obj)
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items()}

    def _metadata_path(self, path: Path) -> Path:
        return path.with_name(path.name + ".metadata.json")
