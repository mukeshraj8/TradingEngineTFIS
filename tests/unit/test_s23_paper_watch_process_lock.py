from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tfis.runtime import (
    CRITICAL_DUPLICATE_PROCESS_SHUTDOWN,
    ProcessLockError,
    acquire_process_lock,
)


def _load_watch_script_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_s23_paper_position_watch.py"
    spec = importlib.util.spec_from_file_location("run_s23_paper_position_watch", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_s23_paper_watch_process_lock_path_is_scoped_to_lock_root(tmp_path: Path) -> None:
    module = _load_watch_script_module()
    state_dir = tmp_path / "data" / "strategies" / "S23" / "run" / "branch"
    lock_root = tmp_path / "tmp" / "process_locks" / "s23_paper_watch"

    lock_path = module._watch_process_lock_path(state_dir, lock_root=lock_root)

    assert lock_path.parent == lock_root
    assert lock_path.name.startswith("s23_paper_watch_")
    assert lock_path.name.endswith(".pid.json")
    assert str(state_dir) not in lock_path.name


def test_s23_paper_watch_lock_identity_is_stable_per_state_directory(tmp_path: Path) -> None:
    module = _load_watch_script_module()
    lock_root = tmp_path / "tmp" / "process_locks" / "s23_paper_watch"
    state_dir = tmp_path / "data" / "strategies" / "S23" / "2026-07-06" / "branch"
    sibling_state_dir = tmp_path / "data" / "strategies" / "S23" / "2026-07-06" / "other-branch"

    first = module._watch_process_lock_path(state_dir, lock_root=lock_root)
    second = module._watch_process_lock_path(state_dir, lock_root=lock_root)
    sibling = module._watch_process_lock_path(sibling_state_dir, lock_root=lock_root)

    assert first == second
    assert first != sibling


def test_s23_paper_watch_duplicate_live_pid_fails_closed_with_metadata(tmp_path: Path) -> None:
    module = _load_watch_script_module()
    lock_root = tmp_path / "tmp" / "process_locks" / "s23_paper_watch"
    state_dir = tmp_path / "data" / "strategies" / "S23" / "2026-07-06" / "branch"
    lock_path = module._watch_process_lock_path(state_dir, lock_root=lock_root)
    logs: list[str] = []

    acquire_process_lock(
        lock_path,
        label="s23-paper-watch:S23-trade-1",
        metadata={
            "trade_id": "S23-trade-1",
            "session_date": "2026-07-06",
            "selected_contract_symbol": "NIFTY_20260714_23900_CE",
            "state_directory": str(state_dir.resolve()),
        },
        pid_provider=lambda: 1111,
        process_exists=lambda pid: pid == 1111,
        logger=logs.append,
    )

    with pytest.raises(ProcessLockError) as exc_info:
        acquire_process_lock(
            lock_path,
            label="s23-paper-watch:S23-trade-1",
            metadata={"trade_id": "S23-trade-1"},
            pid_provider=lambda: 2222,
            process_exists=lambda pid: pid == 1111,
            logger=logs.append,
        )

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert exc_info.value.code == CRITICAL_DUPLICATE_PROCESS_SHUTDOWN
    assert exc_info.value.existing_pid == 1111
    assert payload["pid"] == 1111
    assert payload["metadata"]["selected_contract_symbol"] == "NIFTY_20260714_23900_CE"
    assert any(CRITICAL_DUPLICATE_PROCESS_SHUTDOWN in item for item in logs)
