from __future__ import annotations

from pathlib import Path

from tfis.paper import (
    paper_morning_supervised_market_closed_no_action,
    paper_morning_supervised_process_lock_path,
)


def test_paper_morning_supervised_market_closed_no_action_matches_no_candle_failures() -> None:
    assert paper_morning_supervised_market_closed_no_action(
        code="BROKER_SNAPSHOT_FAILED",
        message="FYERS underlying history payload returned no candles.",
    )
    assert not paper_morning_supervised_market_closed_no_action(
        code="BROKER_SNAPSHOT_FAILED",
        message="FYERS history request failed [-99]: Bad request.",
    )
    assert not paper_morning_supervised_market_closed_no_action(
        code="OTHER_FAILURE",
        message="FYERS underlying history payload returned no candles.",
    )


def test_paper_morning_supervised_process_lock_path_is_strategy_specific(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    s21_path = paper_morning_supervised_process_lock_path(
        artifact_root=artifact_root,
        session_id_prefix="s21-fyers-morning-supervised-decision",
        lock_root=tmp_path / "locks",
        strategy_code="S21",
    )
    s23_path = paper_morning_supervised_process_lock_path(
        artifact_root=artifact_root,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        lock_root=tmp_path / "locks",
        strategy_code="S23",
    )

    assert s21_path.name.startswith("s21_supervised_decision_")
    assert s23_path.name.startswith("s23_supervised_decision_")
    assert s21_path != s23_path
