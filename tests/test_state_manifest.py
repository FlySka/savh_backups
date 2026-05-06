from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from savh_backup.infrastructure.runtime.manifest import ManifestRecorder
from savh_backup.infrastructure.runtime.state import StateStore


def test_state_store_records_success_and_threshold(tmp_path: Path):
    store = StateStore(tmp_path)
    completed_at = datetime(2026, 5, 6, 23, 30, tzinfo=UTC)

    store.mark_success("job-1", completed_at=completed_at)

    assert store.was_success_after(completed_at - timedelta(minutes=1)) is True
    assert store.was_success_after(completed_at + timedelta(minutes=1)) is False
    assert store.load().last_success_job_id == "job-1"


def test_manifest_appends_json_lines(tmp_path: Path):
    manifest = ManifestRecorder(tmp_path)

    manifest.append({"event": "backup_started", "job_id": "job-1"})
    manifest.append({"event": "backup_finished", "job_id": "job-1", "status": "success"})

    lines = [
        json.loads(line)
        for line in manifest.path.read_text(encoding="utf-8").splitlines()
    ]
    assert [line["event"] for line in lines] == ["backup_started", "backup_finished"]
    assert all("recorded_at" in line for line in lines)

