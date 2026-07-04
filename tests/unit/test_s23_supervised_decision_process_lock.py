from __future__ import annotations

import importlib.util
from pathlib import Path


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
