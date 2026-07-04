from __future__ import annotations

import importlib.util
from pathlib import Path


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
