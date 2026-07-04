from __future__ import annotations

import json
from pathlib import Path

import pytest

from tfis.runtime import (
    CRITICAL_DUPLICATE_PROCESS_SHUTDOWN,
    STALE_PROCESS_LOCK_RECLAIMED,
    ProcessLockError,
    acquire_process_lock,
)


def test_duplicate_alive_pid_fails_closed_and_leaves_original_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "tfis-watch.pid.json"
    lock_path.write_text(
        json.dumps({"pid": 1234, "label": "existing-watch"}),
        encoding="utf-8",
    )
    logs: list[str] = []

    with pytest.raises(ProcessLockError) as exc_info:
        acquire_process_lock(
            lock_path,
            label="s23-paper-watch:trade-1",
            pid_provider=lambda: 5678,
            process_exists=lambda pid: pid == 1234,
            logger=logs.append,
        )

    assert exc_info.value.code == CRITICAL_DUPLICATE_PROCESS_SHUTDOWN
    assert exc_info.value.existing_pid == 1234
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == 1234
    assert any(CRITICAL_DUPLICATE_PROCESS_SHUTDOWN in item for item in logs)


def test_stale_pid_lock_is_reclaimed_and_released(tmp_path: Path) -> None:
    lock_path = tmp_path / "tfis-watch.pid.json"
    lock_path.write_text(
        json.dumps({"pid": 1234, "label": "stale-watch"}),
        encoding="utf-8",
    )
    logs: list[str] = []

    handle = acquire_process_lock(
        lock_path,
        label="s23-paper-watch:trade-1",
        pid_provider=lambda: 5678,
        process_exists=lambda _pid: False,
        logger=logs.append,
    )

    assert handle.pid == 5678
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == 5678
    assert any(STALE_PROCESS_LOCK_RECLAIMED in item for item in logs)

    handle.release()

    assert not lock_path.exists()


def test_release_does_not_remove_foreign_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "tfis-watch.pid.json"
    handle = acquire_process_lock(
        lock_path,
        label="s23-paper-watch:trade-1",
        pid_provider=lambda: 1111,
        process_exists=lambda _pid: False,
    )
    lock_path.write_text(
        json.dumps({"pid": 2222, "label": "replacement-watch"}),
        encoding="utf-8",
    )

    handle.release()

    assert lock_path.exists()
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == 2222
