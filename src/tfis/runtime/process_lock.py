from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable


CRITICAL_DUPLICATE_PROCESS_SHUTDOWN = "CRITICAL_DUPLICATE_PROCESS_SHUTDOWN"
STALE_PROCESS_LOCK_RECLAIMED = "STALE_PROCESS_LOCK_RECLAIMED"
PID_REUSE_LOCK_TOLERANCE = timedelta(seconds=5)


class ProcessLockError(RuntimeError):
    def __init__(self, code: str, message: str, *, lock_path: Path, existing_pid: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.lock_path = lock_path
        self.existing_pid = existing_pid


@dataclass(frozen=True)
class ProcessLockHandle:
    lock_path: Path
    pid: int
    label: str

    def release(self) -> None:
        payload = _read_lock_payload(self.lock_path)
        if _payload_pid(payload) != self.pid:
            return
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            return


def acquire_process_lock(
    lock_path: Path,
    *,
    label: str,
    metadata: dict[str, Any] | None = None,
    pid_provider: Callable[[], int] = os.getpid,
    process_exists: Callable[[int], bool] | None = None,
    logger: Callable[[str], None] | None = None,
) -> ProcessLockHandle:
    resolved_lock_path = Path(lock_path)
    resolved_lock_path.parent.mkdir(parents=True, exist_ok=True)
    pid = int(pid_provider())
    exists = process_exists or _process_exists

    for _attempt in range(2):
        payload = _read_lock_payload(resolved_lock_path)
        existing_pid = _payload_pid(payload)
        if existing_pid is not None and existing_pid != pid:
            if exists(existing_pid) and _process_matches_payload(existing_pid, payload):
                message = (
                    f"{CRITICAL_DUPLICATE_PROCESS_SHUTDOWN}: {label} duplicate startup blocked; "
                    f"lock={resolved_lock_path}; existing_pid={existing_pid}; attempted_pid={pid}"
                )
                _log(logger, message)
                raise ProcessLockError(
                    CRITICAL_DUPLICATE_PROCESS_SHUTDOWN,
                    message,
                    lock_path=resolved_lock_path,
                    existing_pid=existing_pid,
                )
            try:
                resolved_lock_path.unlink()
            except FileNotFoundError:
                pass
            _log(
                logger,
                (
                    f"{STALE_PROCESS_LOCK_RECLAIMED}: {label} removed stale lock; "
                    f"lock={resolved_lock_path}; stale_pid={existing_pid}; new_pid={pid}"
                ),
            )

        try:
            fd = os.open(
                str(resolved_lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            continue

        payload_to_write = {
            "pid": pid,
            "label": label,
            "created_at": datetime.now(UTC).isoformat(),
            "cwd": str(Path.cwd()),
            "argv": list(sys.argv),
            "metadata": metadata or {},
        }
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload_to_write, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return ProcessLockHandle(lock_path=resolved_lock_path, pid=pid, label=label)

    payload = _read_lock_payload(resolved_lock_path)
    existing_pid = _payload_pid(payload)
    message = (
        f"{CRITICAL_DUPLICATE_PROCESS_SHUTDOWN}: {label} duplicate startup blocked after lock race; "
        f"lock={resolved_lock_path}; existing_pid={existing_pid}; attempted_pid={pid}"
    )
    _log(logger, message)
    raise ProcessLockError(
        CRITICAL_DUPLICATE_PROCESS_SHUTDOWN,
        message,
        lock_path=resolved_lock_path,
        existing_pid=existing_pid,
    )


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if handle:
            exit_code = ctypes.c_ulong()
            try:
                if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == still_active
                return False
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _process_matches_payload(pid: int, payload: dict[str, Any] | None) -> bool:
    if pid <= 0:
        return False
    if not payload:
        return True
    lock_created_at = _payload_created_at(payload)
    if lock_created_at is None:
        return True
    process_created_at = _process_created_at(pid)
    if process_created_at is None:
        return True
    return process_created_at <= (lock_created_at + PID_REUSE_LOCK_TOLERANCE)


def _process_created_at(pid: int) -> datetime | None:
    if pid <= 0:
        return None
    if os.name == "nt":
        return _windows_process_created_at(pid)
    return None


def _windows_process_created_at(pid: int) -> datetime | None:
    import ctypes

    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information,
        False,
        pid,
    )
    if not handle:
        return None

    filetime_factory = getattr(ctypes, "c_ulonglong", None)
    if filetime_factory is None:
        return None

    created = filetime_factory()
    exited = filetime_factory()
    kernel = filetime_factory()
    user = filetime_factory()
    try:
        ok = ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        return datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=created.value / 10)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _payload_created_at(payload: dict[str, Any] | None) -> datetime | None:
    if not payload:
        return None
    raw = payload.get("created_at")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _read_lock_payload(lock_path: Path) -> dict[str, Any] | None:
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_pid(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    try:
        return int(payload.get("pid"))
    except (TypeError, ValueError):
        return None


def _log(logger: Callable[[str], None] | None, message: str) -> None:
    if logger is None:
        return
    logger(message)
