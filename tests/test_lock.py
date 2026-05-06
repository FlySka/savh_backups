from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from savh_backup.infrastructure.runtime.lock import FileLock, LockBusy


def test_file_lock_prevents_overlap(tmp_path: Path):
    lock_path = tmp_path / "backup.lock"
    with FileLock(lock_path):
        with pytest.raises(LockBusy):
            FileLock(lock_path).acquire()

    assert not lock_path.exists()


def test_file_lock_removes_stale_lock(tmp_path: Path):
    lock_path = tmp_path / "backup.lock"
    lock_path.write_text("stale", encoding="utf-8")
    stale_time = time.time() - 10
    os.utime(lock_path, (stale_time, stale_time))

    with FileLock(lock_path, stale_after_seconds=1):
        assert lock_path.exists()

