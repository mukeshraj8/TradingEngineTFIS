from __future__ import annotations

import importlib.util
from pathlib import Path

from tfis.paper import S23FyersSnapshotCollectorError


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_s23_fyers_0916_supervised_decision.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "run_s23_fyers_0916_supervised_decision_under_test",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_market_closed_no_candles_returns_success_without_starting_watcher(
    monkeypatch,
    capsys,
) -> None:
    module = _load_script_module()

    def fail_no_candles(**kwargs):
        raise S23FyersSnapshotCollectorError(
            "BROKER_SNAPSHOT_FAILED",
            "Unable to collect normalized FYERS snapshot inputs safely: "
            "FYERS underlying history payload returned no candles.",
        )

    monkeypatch.setattr(module, "run_paper_morning_supervised_decision", fail_no_candles)

    assert module.main([]) == 0

    captured = capsys.readouterr()
    assert "MARKET_CLOSED_NO_ACTION" in captured.out
    assert "No trade decision or supervisor startup was triggered" in captured.out
    assert captured.err == ""


def test_non_closed_market_broker_failure_still_returns_error(
    monkeypatch,
    capsys,
) -> None:
    module = _load_script_module()

    def fail_other(**kwargs):
        raise S23FyersSnapshotCollectorError(
            "BROKER_SNAPSHOT_FAILED",
            "Unable to collect normalized FYERS snapshot inputs safely: "
            "FYERS history request failed [-99]: Bad request.",
        )

    monkeypatch.setattr(module, "run_paper_morning_supervised_decision", fail_other)

    assert module.main([]) == 1

    captured = capsys.readouterr()
    assert "MARKET_CLOSED_NO_ACTION" not in captured.out
    assert "ERROR [BROKER_SNAPSHOT_FAILED]" in captured.err
