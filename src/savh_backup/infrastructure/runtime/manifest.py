"""Append-only JSONL manifest for backup auditability."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ManifestRecorder:
    """Write backup lifecycle events to a JSONL manifest."""

    def __init__(self, manifests_dir: Path) -> None:
        self._path = manifests_dir / "backups.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        """Return manifest file path."""

        return self._path

    def append(self, event: dict[str, Any]) -> None:
        """Append one event to the manifest."""

        payload = {
            "recorded_at": datetime.now(UTC).isoformat(),
            **event,
        }
        with self._path.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(payload, ensure_ascii=True, default=str))
            file_obj.write("\n")

