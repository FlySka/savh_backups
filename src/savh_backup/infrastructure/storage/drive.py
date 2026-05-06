"""Google Drive storage backend."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from savh_backup.settings.config import StorageSection
from savh_backup.infrastructure.storage.base import APP_MARKER, RemoteFile, RemoteUpload

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleDriveBackend:
    """Upload and manage backups in a Google Drive folder."""

    def __init__(self, storage: StorageSection) -> None:
        if not storage.drive_folder_id:
            raise ValueError("drive_folder_id is required")
        self._folder_id = storage.drive_folder_id
        self._chunk_size_bytes = storage.chunk_size_bytes
        self._service = _build_drive_service()

    def upload_file(
        self,
        path: Path,
        *,
        remote_name: str,
        metadata: dict[str, str],
    ) -> RemoteUpload:
        """Upload a file to Google Drive using a resumable upload."""

        from googleapiclient.http import MediaFileUpload

        app_properties = {"app": APP_MARKER, **metadata}
        body = {
            "name": remote_name,
            "parents": [self._folder_id],
            "appProperties": app_properties,
        }
        media = MediaFileUpload(
            str(path),
            mimetype="application/octet-stream",
            chunksize=self._chunk_size_bytes,
            resumable=True,
        )
        request = self._service.files().create(
            body=body,
            media_body=media,
            fields="id,name,size,createdTime,appProperties",
            supportsAllDrives=True,
        )
        response: dict[str, Any] | None = None
        while response is None:
            status, response = request.next_chunk()
            if status is not None:
                logger.info(
                    "Drive upload progress",
                    extra={"phase": "upload", "progress": round(status.progress(), 4)},
                )
        logger.info(
            "Drive upload complete",
            extra={"phase": "upload", "drive_file_id": response["id"], "name": response["name"]},
        )
        return RemoteUpload(
            file_id=str(response["id"]),
            name=str(response["name"]),
            uri=f"drive://{response['id']}",
            size_bytes=_optional_int(response.get("size")),
            created_at=_parse_drive_dt(response.get("createdTime")),
        )

    def list_backups(self, *, prefix: str) -> list[RemoteFile]:
        """List app-owned backup files inside the configured Drive folder."""

        files: list[RemoteFile] = []
        page_token: str | None = None
        query = (
            f"'{_escape_query(self._folder_id)}' in parents "
            "and trashed = false "
            f"and appProperties has {{ key='app' and value='{APP_MARKER}' }} "
            f"and appProperties has {{ key='prefix' and value='{_escape_query(prefix)}' }}"
        )
        while True:
            response = (
                self._service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id,name,createdTime,appProperties,size)",
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            for item in response.get("files", []):
                created_at = _parse_drive_dt(item.get("createdTime"))
                if created_at is None:
                    continue
                properties = item.get("appProperties") or {}
                files.append(
                    RemoteFile(
                        file_id=str(item["id"]),
                        name=str(item["name"]),
                        created_at=created_at,
                        metadata={str(k): str(v) for k, v in properties.items()},
                    )
                )
            page_token = response.get("nextPageToken")
            if not page_token:
                return files

    def delete_file(self, file_id: str) -> None:
        """Delete a remote Google Drive file."""

        self._service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        logger.info("Deleted Drive backup", extra={"phase": "cleanup", "drive_file_id": file_id})


def _build_drive_service() -> Any:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is required for Google Drive")
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _parse_drive_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
