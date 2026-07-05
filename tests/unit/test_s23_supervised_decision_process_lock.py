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


def _load_decision_script_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_s23_fyers_0916_supervised_decision.py"
    spec = importlib.util.spec_from_file_location("run_s23_fyers_0916_supervised_decision", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_s23_supervised_decision_process_lock_path_is_scoped_to_lock_root(tmp_path: Path) -> None:
    module = _load_decision_script_module()
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    lock_root = tmp_path / "tmp" / "process_locks" / "s23_supervised_decision"

    lock_path = module._supervised_decision_process_lock_path(
        artifact_root=artifact_root,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        lock_root=lock_root,
    )

    assert lock_path.parent == lock_root
    assert lock_path.name.startswith("s23_supervised_decision_")
    assert lock_path.name.endswith(".pid.json")
    assert str(artifact_root) not in lock_path.name


def test_s23_supervised_decision_lock_identity_is_stable_per_artifact_root_and_prefix(
    tmp_path: Path,
) -> None:
    module = _load_decision_script_module()
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    lock_root = tmp_path / "tmp" / "process_locks" / "s23_supervised_decision"

    first = module._supervised_decision_process_lock_path(
        artifact_root=artifact_root,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        lock_root=lock_root,
    )
    second = module._supervised_decision_process_lock_path(
        artifact_root=artifact_root,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        lock_root=lock_root,
    )
    other_prefix = module._supervised_decision_process_lock_path(
        artifact_root=artifact_root,
        session_id_prefix="s23-other-supervised-decision",
        lock_root=lock_root,
    )

    assert first == second
    assert first != other_prefix


def test_s23_supervised_decision_duplicate_live_pid_fails_closed_with_metadata(
    tmp_path: Path,
) -> None:
    module = _load_decision_script_module()
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    lock_root = tmp_path / "tmp" / "process_locks" / "s23_supervised_decision"
    lock_path = module._supervised_decision_process_lock_path(
        artifact_root=artifact_root,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        lock_root=lock_root,
    )
    logs: list[str] = []

    acquire_process_lock(
        lock_path,
        label="s23-supervised-decision:s23-fyers-morning-supervised-decision",
        metadata={
            "artifact_root": str(artifact_root.resolve()),
            "session_id_prefix": "s23-fyers-morning-supervised-decision",
            "strategy_paths": ["config/strategies/options_sell/nifty/S23"],
        },
        pid_provider=lambda: 1111,
        process_exists=lambda pid: pid == 1111,
        logger=logs.append,
    )

    with pytest.raises(ProcessLockError) as exc_info:
        acquire_process_lock(
            lock_path,
            label="s23-supervised-decision:s23-fyers-morning-supervised-decision",
            metadata={"artifact_root": str(artifact_root.resolve())},
            pid_provider=lambda: 2222,
            process_exists=lambda pid: pid == 1111,
            logger=logs.append,
        )

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert exc_info.value.code == CRITICAL_DUPLICATE_PROCESS_SHUTDOWN
    assert exc_info.value.existing_pid == 1111
    assert payload["pid"] == 1111
    assert payload["metadata"]["session_id_prefix"] == "s23-fyers-morning-supervised-decision"
    assert any(CRITICAL_DUPLICATE_PROCESS_SHUTDOWN in item for item in logs)
