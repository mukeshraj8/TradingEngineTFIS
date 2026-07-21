from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from tfis.paper import S23FyersSnapshotCollectorError


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_s23_fyers_live_decision_check.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "run_s23_fyers_live_decision_check_under_test",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_decision_check_cli_uses_generic_paper_runner(monkeypatch, capsys) -> None:
    module = _load_script_module()

    monkeypatch.setattr(
        module,
        "run_paper_live_decision_check",
        lambda **kwargs: SimpleNamespace(
            snapshot_artifacts=SimpleNamespace(
                session_directory=Path("D:/tmp/session"),
                normalized_underlying_snapshot_path=Path("D:/tmp/underlying_snapshot.json"),
                normalized_underlying_bars_path=Path("D:/tmp/underlying_bars.json"),
                normalized_option_chain_snapshot_path=Path("D:/tmp/option_chain.json"),
            ),
            decision_summary_json=Path("D:/tmp/summary.json"),
            decision_summary_markdown=Path("D:/tmp/summary.md"),
            decision_explainer_json=Path("D:/tmp/explainer.json"),
            decision_explainer_markdown=Path("D:/tmp/explainer.md"),
        ),
    )

    assert module.main([]) == 0
    captured = capsys.readouterr()
    assert "S23 live decision check succeeded." in captured.out
    assert "ERROR" not in captured.err


def test_live_decision_check_cli_reports_runner_failure(monkeypatch, capsys) -> None:
    module = _load_script_module()

    def _fail(**kwargs):
        raise S23FyersSnapshotCollectorError("BROKER_SNAPSHOT_FAILED", "bad request")

    monkeypatch.setattr(module, "run_paper_live_decision_check", _fail)

    assert module.main([]) == 1
    captured = capsys.readouterr()
    assert "ERROR [BROKER_SNAPSHOT_FAILED]" in captured.err
