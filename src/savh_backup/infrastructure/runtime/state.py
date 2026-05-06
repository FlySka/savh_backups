"""Small JSON state store used for catch-up decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BackupState:
    """Persisted state summary."""

    last_success_at: datetime | None
    last_success_job_id: str | None


class StateStore:
    """Read and write app state."""

    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "state.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> BackupState:
        """Load current state."""

        if not self._path.exists():
            return BackupState(last_success_at=None, last_success_job_id=None)
        with self._path.open("r", encoding="utf-8") as file_obj:
            raw: dict[str, Any] = json.load(file_obj)
        return BackupState(
            last_success_at=_parse_dt(raw.get("last_success_at")),
            last_success_job_id=_parse_str(raw.get("last_success_job_id")),
        )

    def was_success_after(self, threshold: datetime) -> bool:
        """Return whether a success has been recorded after a threshold."""

        state = self.load()
        return state.last_success_at is not None and state.last_success_at >= threshold

    def mark_success(self, job_id: str, completed_at: datetime | None = None) -> None:
        """Record the last successful backup."""

        now = completed_at or datetime.now(UTC)
        payload = {
            "last_success_at": now.astimezone(UTC).isoformat(),
            "last_success_job_id": job_id,
        }
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=True, indent=2)
            file_obj.write("\n")
        tmp_path.replace(self._path)


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_str(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None

