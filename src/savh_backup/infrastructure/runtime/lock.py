"""Filesystem lock for preventing overlapping backup jobs."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path


class LockBusy(RuntimeError):
    """Raised when another backup job is already running."""


class FileLock:
    """A small exclusive lock based on atomic file creation."""

    def __init__(self, path: Path, stale_after_seconds: int = 12 * 60 * 60) -> None:
        self._path = path
        self._stale_after_seconds = stale_after_seconds
        self._fd: int | None = None

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()

    def acquire(self) -> None:
        """Acquire lock or raise if it is held by another process."""

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._remove_stale_lock()
        try:
            self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise LockBusy(f"Backup lock is already held: {self._path}") from exc
        payload = f"pid={os.getpid()} acquired_at={datetime.now(UTC).isoformat()}\n"
        os.write(self._fd, payload.encode("utf-8"))

    def release(self) -> None:
        """Release lock."""

        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass

    def _remove_stale_lock(self) -> None:
        if not self._path.exists():
            return
        age = datetime.now(UTC).timestamp() - self._path.stat().st_mtime
        if age > self._stale_after_seconds:
            self._path.unlink(missing_ok=True)

