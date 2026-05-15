"""Google Drive authentication helpers."""

from __future__ import annotations

import builtins
from contextlib import contextmanager
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from savh_backup.settings.config import StorageSection

SERVICE_ACCOUNT_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
OAUTH_USER_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def build_drive_service(storage: StorageSection) -> Any:
    credentials = load_drive_credentials(storage)
    return _build_google_drive_service(credentials)


def load_drive_credentials(storage: StorageSection) -> Any:
    if storage.provider == "google_drive":
        return _load_service_account_credentials()
    if storage.provider == "google_drive_oauth":
        return _load_oauth_user_credentials(storage)
    raise ValueError(f"Unsupported Drive provider: {storage.provider}")


def run_google_drive_oauth_login(storage: StorageSection, *, open_browser: bool = True) -> Path:
    if storage.provider != "google_drive_oauth":
        raise ValueError("google_drive_oauth login requires storage.provider=google_drive_oauth")

    client_secret_path = _required_path(
        storage.oauth_client_secret_path,
        "storage.oauth_client_secret_path is required for google_drive_oauth",
    )
    if not client_secret_path.exists():
        raise RuntimeError(f"Google Drive OAuth client secret file does not exist: {client_secret_path}")

    token_path = _required_path(
        storage.oauth_token_path,
        "storage.oauth_token_path is required for google_drive_oauth",
    )

    flow = _installed_app_flow_from_client_secret(client_secret_path)
    if open_browser:
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            open_browser=True,
            authorization_prompt_message="Open the following URL in your browser and finish the Google Drive authorization flow: {url}",
            success_message="Google Drive authorization complete. You can close this window.",
        )
    else:
        credentials = _run_no_browser_oauth_flow(flow)
    _write_credentials(token_path, credentials)
    return token_path


def _load_service_account_credentials() -> Any:
    from google.oauth2 import service_account

    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is required for Google Drive")
    return service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SERVICE_ACCOUNT_DRIVE_SCOPES,
    )


def _load_oauth_user_credentials(storage: StorageSection) -> Any:
    token_path = _required_path(
        storage.oauth_token_path,
        "storage.oauth_token_path is required for google_drive_oauth",
    )
    if not token_path.exists():
        raise RuntimeError(
            f"Google Drive OAuth token does not exist: {token_path}. "
            "Run `savh-backup google-drive-login` to authorize access to your personal Drive."
        )

    try:
        credentials = _oauth_credentials_from_file(token_path)
    except Exception as exc:
        raise RuntimeError(f"Could not read Google Drive OAuth token: {token_path}") from exc

    if getattr(credentials, "expired", False) and getattr(credentials, "refresh_token", None):
        _refresh_credentials(credentials)
        _write_credentials(token_path, credentials)

    if not getattr(credentials, "valid", False):
        raise RuntimeError(
            f"Google Drive OAuth token is invalid or expired without refresh support: {token_path}. "
            "Run `savh-backup google-drive-login` again."
        )
    return credentials


def _oauth_credentials_from_file(token_path: Path) -> Any:
    from google.oauth2.credentials import Credentials

    return Credentials.from_authorized_user_file(str(token_path), OAUTH_USER_DRIVE_SCOPES)


def _refresh_credentials(credentials: Any) -> None:
    from google.auth.transport.requests import Request

    credentials.refresh(Request())


def _installed_app_flow_from_client_secret(client_secret_path: Path) -> Any:
    from google_auth_oauthlib.flow import InstalledAppFlow

    return InstalledAppFlow.from_client_secrets_file(
        str(client_secret_path),
        OAUTH_USER_DRIVE_SCOPES,
    )


def _build_google_drive_service(credentials: Any) -> Any:
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _run_no_browser_oauth_flow(flow: Any) -> Any:
    redirect_uri = _default_redirect_uri(flow)
    flow.redirect_uri = redirect_uri
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    builtins.print("Open this URL in your browser and approve access:")
    builtins.print(authorization_url)
    authorization_response = builtins.input(
        "Paste the full redirect URL after Google finishes the login flow: "
    ).strip()
    if not authorization_response:
        raise RuntimeError("No authorization response was provided")
    with _temporary_oauthlib_insecure_transport(_requires_insecure_transport_override(redirect_uri)):
        flow.fetch_token(authorization_response=authorization_response)
    return flow.credentials


def _default_redirect_uri(flow: Any) -> str:
    client_config = getattr(flow, "client_config", {})
    installed = client_config.get("installed") if isinstance(client_config, dict) else None
    redirect_uris = installed.get("redirect_uris") if isinstance(installed, dict) else None
    if isinstance(redirect_uris, list) and redirect_uris:
        return str(redirect_uris[0])
    return "http://localhost"


def _requires_insecure_transport_override(redirect_uri: str) -> bool:
    parsed = urlparse(redirect_uri)
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}


@contextmanager
def _temporary_oauthlib_insecure_transport(enabled: bool):
    if not enabled:
        yield
        return

    previous = os.environ.get("OAUTHLIB_INSECURE_TRANSPORT")
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
        else:
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = previous


def _write_credentials(path: Path, credentials: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.to_json() + "\n", encoding="utf-8")


def _required_path(path: Path | None, message: str) -> Path:
    if path is None:
        raise RuntimeError(message)
    return path