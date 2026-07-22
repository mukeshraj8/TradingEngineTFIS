from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import tfis.runtime.process_lock as process_lock_module
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


def test_reused_live_pid_lock_is_reclaimed_when_process_start_is_newer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "tfis-watch.pid.json"
    lock_path.write_text(
        json.dumps(
            {
                "pid": 1234,
                "label": "stale-watch",
                "created_at": "2026-07-21T03:39:52+00:00",
            }
        ),
        encoding="utf-8",
    )
    logs: list[str] = []

    monkeypatch.setattr(
        process_lock_module,
        "_process_created_at",
        lambda pid: datetime.fromisoformat("2026-07-21T03:50:00+00:00") if pid == 1234 else None,
    )

    handle = acquire_process_lock(
        lock_path,
        label="s21-supervised-decision:trade-1",
        pid_provider=lambda: 5678,
        process_exists=lambda pid: pid == 1234,
        logger=logs.append,
    )

    assert handle.pid == 5678
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == 5678
    assert any(STALE_PROCESS_LOCK_RECLAIMED in item for item in logs)


def test_live_pid_lock_remains_blocking_when_process_start_matches_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "tfis-watch.pid.json"
    lock_path.write_text(
        json.dumps(
            {
                "pid": 1234,
                "label": "existing-watch",
                "created_at": "2026-07-21T03:39:52+00:00",
            }
        ),
        encoding="utf-8",
    )
    logs: list[str] = []

    monkeypatch.setattr(
        process_lock_module,
        "_process_created_at",
        lambda pid: datetime.fromisoformat("2026-07-21T03:39:50+00:00") if pid == 1234 else None,
    )

    with pytest.raises(ProcessLockError) as exc_info:
        acquire_process_lock(
            lock_path,
            label="s21-supervised-decision:trade-1",
            pid_provider=lambda: 5678,
            process_exists=lambda pid: pid == 1234,
            logger=logs.append,
        )

    assert exc_info.value.code == CRITICAL_DUPLICATE_PROCESS_SHUTDOWN
    assert exc_info.value.existing_pid == 1234
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == 1234


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


def test_windows_process_exists_treats_access_denied_without_handle_as_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Kernel32:
        @staticmethod
        def OpenProcess(_access: int, _inherit: bool, _pid: int) -> int:
            return 0

        @staticmethod
        def CloseHandle(_handle: int) -> None:
            return None

        @staticmethod
        def GetLastError() -> int:
            return 5

    fake_ctypes = SimpleNamespace(windll=SimpleNamespace(kernel32=_Kernel32()))
    monkeypatch.setattr(process_lock_module.os, "name", "nt", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "ctypes", fake_ctypes)

    assert process_lock_module._process_exists(15048) is False


def test_windows_process_exists_treats_exited_handle_as_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Kernel32:
        @staticmethod
        def OpenProcess(_access: int, _inherit: bool, _pid: int) -> int:
            return 123

        @staticmethod
        def GetExitCodeProcess(_handle: int, exit_code_pointer: object) -> int:
            exit_code_pointer._obj.value = 0
            return 1

        @staticmethod
        def CloseHandle(_handle: int) -> None:
            return None

    fake_ctypes = SimpleNamespace(
        c_ulong=lambda: SimpleNamespace(value=0),
        byref=lambda value: SimpleNamespace(_obj=value),
        windll=SimpleNamespace(kernel32=_Kernel32()),
    )
    monkeypatch.setattr(process_lock_module.os, "name", "nt", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "ctypes", fake_ctypes)

    assert process_lock_module._process_exists(15048) is False


def test_windows_process_exists_treats_still_active_handle_as_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Kernel32:
        @staticmethod
        def OpenProcess(_access: int, _inherit: bool, _pid: int) -> int:
            return 123

        @staticmethod
        def GetExitCodeProcess(_handle: int, exit_code_pointer: object) -> int:
            exit_code_pointer._obj.value = 259
            return 1

        @staticmethod
        def CloseHandle(_handle: int) -> None:
            return None

    fake_ctypes = SimpleNamespace(
        c_ulong=lambda: SimpleNamespace(value=0),
        byref=lambda value: SimpleNamespace(_obj=value),
        windll=SimpleNamespace(kernel32=_Kernel32()),
    )
    monkeypatch.setattr(process_lock_module.os, "name", "nt", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "ctypes", fake_ctypes)

    assert process_lock_module._process_exists(15048) is True
