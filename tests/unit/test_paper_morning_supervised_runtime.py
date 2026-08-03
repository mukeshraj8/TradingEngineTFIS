from __future__ import annotations

from pathlib import Path

from tfis.paper import (
    S23FyersSnapshotCollectorError,
    paper_morning_supervised_market_closed_no_action,
    paper_morning_supervised_process_lock_path,
    run_paper_morning_supervised_decision_with_no_candle_retries,
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


def test_no_candle_retry_helper_retries_and_returns_success() -> None:
    attempts = 0
    sleeps: list[float] = []
    messages: list[str] = []

    def run_once() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise S23FyersSnapshotCollectorError(
                "BROKER_SNAPSHOT_FAILED",
                "FYERS underlying history payload returned no candles.",
            )
        return "ok"

    result = run_paper_morning_supervised_decision_with_no_candle_retries(
        run_once,
        no_candle_retries=2,
        retry_delay_seconds=1.5,
        sleeper=sleeps.append,
        retry_logger=messages.append,
    )

    assert result == "ok"
    assert attempts == 2
    assert sleeps == [1.5]
    assert messages == [
        "BROKER_SNAPSHOT_NO_CANDLES_RETRY: attempt=1 remaining=1 delay_seconds=1.5"
    ]


def test_no_candle_retry_helper_does_not_retry_other_broker_failures() -> None:
    attempts = 0

    def run_once() -> str:
        nonlocal attempts
        attempts += 1
        raise S23FyersSnapshotCollectorError(
            "BROKER_SNAPSHOT_FAILED",
            "FYERS history request failed [-99]: Bad request.",
        )

    try:
        run_paper_morning_supervised_decision_with_no_candle_retries(
            run_once,
            no_candle_retries=2,
            retry_delay_seconds=0,
        )
    except S23FyersSnapshotCollectorError as exc:
        assert exc.code == "BROKER_SNAPSHOT_FAILED"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected broker snapshot failure")

    assert attempts == 1
