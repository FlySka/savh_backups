from __future__ import annotations

import os
from types import SimpleNamespace
from pathlib import Path

import pytest

from savh_backup.infrastructure.storage import drive_auth
from savh_backup.infrastructure.storage.drive import GoogleDriveBackend
from savh_backup.settings.config import StorageSection


def _storage(provider: str = "google_drive") -> StorageSection:
    return StorageSection(
        provider=provider,
        drive_folder_id="folder-123",
        filesystem_dir=None,
        oauth_client_secret_path=Path("/tmp/oauth-client.json"),
        oauth_token_path=Path("/tmp/oauth-token.json"),
        chunk_size_bytes=8 * 1024 * 1024,
    )


def test_google_drive_backend_validates_folder_access_on_init(monkeypatch):
    class FakeFilesResource:
        def get(self, **kwargs):
            assert kwargs["fileId"] == "folder-123"
            assert kwargs["supportsAllDrives"] is True
            return SimpleNamespace(
                execute=lambda: {
                    "id": "folder-123",
                    "name": "Backups SAVH",
                    "mimeType": "application/vnd.google-apps.folder",
                }
            )

    class FakeService:
        def files(self):
            return FakeFilesResource()

    monkeypatch.setattr(
        "savh_backup.infrastructure.storage.drive.build_drive_service",
        lambda storage: FakeService(),
    )

    backend = GoogleDriveBackend(_storage())

    assert backend._folder_name == "Backups SAVH"


def test_google_drive_backend_raises_clear_error_for_missing_folder(monkeypatch):
    class FakeNotFoundError(Exception):
        def __init__(self) -> None:
            self.resp = SimpleNamespace(status=404)
            super().__init__("not found")

    class FakeFilesResource:
        def get(self, **kwargs):
            return SimpleNamespace(execute=lambda: (_ for _ in ()).throw(FakeNotFoundError()))

    class FakeService:
        def files(self):
            return FakeFilesResource()

    monkeypatch.setattr(
        "savh_backup.infrastructure.storage.drive.build_drive_service",
        lambda storage: FakeService(),
    )

    with pytest.raises(RuntimeError, match="configured service account"):
        GoogleDriveBackend(_storage())


def test_google_drive_backend_upload_file_returns_remote_upload(monkeypatch, tmp_path: Path):
    class FakeStatus:
        @staticmethod
        def progress() -> float:
            return 1.0

    class FakeRequest:
        def next_chunk(self):
            return (
                FakeStatus(),
                {
                    "id": "drive-file-123",
                    "name": "savh_erp_test.pgcustom",
                    "size": "6",
                    "createdTime": "2026-05-14T22:57:06Z",
                    "appProperties": {"app": "savh_backup"},
                },
            )

    class FakeFilesResource:
        def get(self, **kwargs):
            return SimpleNamespace(
                execute=lambda: {
                    "id": "folder-123",
                    "name": "Backups SAVH",
                    "mimeType": "application/vnd.google-apps.folder",
                }
            )

        def create(self, **kwargs):
            assert kwargs["supportsAllDrives"] is True
            return FakeRequest()

    class FakeService:
        def files(self):
            return FakeFilesResource()

    monkeypatch.setattr(
        "savh_backup.infrastructure.storage.drive.build_drive_service",
        lambda storage: FakeService(),
    )

    backend = GoogleDriveBackend(_storage())
    local_file = tmp_path / "savh_erp_test.pgcustom"
    local_file.write_bytes(b"backup")

    upload = backend.upload_file(
        local_file,
        remote_name=local_file.name,
        metadata={"prefix": "savh_erp", "job_id": "job-123"},
    )

    assert upload.file_id == "drive-file-123"
    assert upload.name == local_file.name
    assert upload.size_bytes == 6
    assert upload.uri == "drive://drive-file-123"


def test_google_drive_oauth_refreshes_and_persists_token(monkeypatch, tmp_path: Path):
    token_path = tmp_path / "google-oauth-token.json"
    token_path.write_text('{"refresh_token": "abc"}\n', encoding="utf-8")
    storage = StorageSection(
        provider="google_drive_oauth",
        drive_folder_id="folder-123",
        filesystem_dir=None,
        oauth_client_secret_path=tmp_path / "google-oauth-client.json",
        oauth_token_path=token_path,
        chunk_size_bytes=8 * 1024 * 1024,
    )

    class FakeCredentials:
        expired = True
        refresh_token = "refresh-token"
        valid = True

        def __init__(self) -> None:
            self.refreshed = False

        def refresh(self, request) -> None:
            self.refreshed = True
            self.expired = False

        def to_json(self) -> str:
            return '{"token": "updated"}'

    credentials = FakeCredentials()
    monkeypatch.setattr(drive_auth, "_oauth_credentials_from_file", lambda path: credentials)

    loaded = drive_auth.load_drive_credentials(storage)

    assert loaded is credentials
    assert credentials.refreshed is True
    assert token_path.read_text(encoding="utf-8") == '{"token": "updated"}\n'


def test_google_drive_oauth_requires_existing_token(tmp_path: Path):
    storage = StorageSection(
        provider="google_drive_oauth",
        drive_folder_id="folder-123",
        filesystem_dir=None,
        oauth_client_secret_path=tmp_path / "google-oauth-client.json",
        oauth_token_path=tmp_path / "google-oauth-token.json",
        chunk_size_bytes=8 * 1024 * 1024,
    )

    with pytest.raises(RuntimeError, match="Run `savh-backup google-drive-login`"):
        drive_auth.load_drive_credentials(storage)


def test_google_drive_oauth_login_writes_token(monkeypatch, tmp_path: Path):
    client_secret_path = tmp_path / "google-oauth-client.json"
    client_secret_path.write_text("{}\n", encoding="utf-8")
    token_path = tmp_path / "google-oauth-token.json"
    storage = StorageSection(
        provider="google_drive_oauth",
        drive_folder_id="folder-123",
        filesystem_dir=None,
        oauth_client_secret_path=client_secret_path,
        oauth_token_path=token_path,
        chunk_size_bytes=8 * 1024 * 1024,
    )

    class FakeCredentials:
        def to_json(self) -> str:
            return '{"token": "created"}'

    class FakeFlow:
        def run_local_server(self, **kwargs):
            assert kwargs["open_browser"] is True
            return FakeCredentials()

    monkeypatch.setattr(
        drive_auth,
        "_installed_app_flow_from_client_secret",
        lambda path: FakeFlow(),
    )

    created_token = drive_auth.run_google_drive_oauth_login(storage, open_browser=True)

    assert created_token == token_path
    assert token_path.read_text(encoding="utf-8") == '{"token": "created"}\n'


def test_google_drive_oauth_login_no_browser_uses_manual_auth_response(monkeypatch, tmp_path: Path):
    client_secret_path = tmp_path / "google-oauth-client.json"
    client_secret_path.write_text("{}\n", encoding="utf-8")
    token_path = tmp_path / "google-oauth-token.json"
    storage = StorageSection(
        provider="google_drive_oauth",
        drive_folder_id="folder-123",
        filesystem_dir=None,
        oauth_client_secret_path=client_secret_path,
        oauth_token_path=token_path,
        chunk_size_bytes=8 * 1024 * 1024,
    )

    class FakeCredentials:
        def to_json(self) -> str:
            return '{"token": "manual"}'

    class FakeFlow:
        client_config = {"installed": {"redirect_uris": ["http://localhost"]}}

        def __init__(self) -> None:
            self.redirect_uri = None
            self.credentials = FakeCredentials()
            self.authorization_response = None

        def authorization_url(self, **kwargs):
            return ("https://example.test/auth", "state-123")

        def fetch_token(self, *, authorization_response):
            assert os.environ.get("OAUTHLIB_INSECURE_TRANSPORT") == "1"
            self.authorization_response = authorization_response

    flow = FakeFlow()
    monkeypatch.setattr(
        drive_auth,
        "_installed_app_flow_from_client_secret",
        lambda path: flow,
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "http://localhost/?code=abc&state=state-123")
    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT", raising=False)

    created_token = drive_auth.run_google_drive_oauth_login(storage, open_browser=False)

    assert created_token == token_path
    assert flow.redirect_uri == "http://localhost"
    assert flow.authorization_response == "http://localhost/?code=abc&state=state-123"
    assert token_path.read_text(encoding="utf-8") == '{"token": "manual"}\n'
    assert "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ