from __future__ import annotations

from pathlib import Path

from tfis.paper.operator_controls import (
    global_pause_marker_path,
    load_latest_operator_control_event,
    load_latest_operator_control_event_from_root,
    load_paper_runtime_control_state,
    load_paper_runtime_control_state_from_root,
    operator_control_event_log_path,
    paper_runtime_control_root,
    strategy_pause_marker_path,
)


def test_load_paper_runtime_control_state_detects_global_and_strategy_markers(tmp_path: Path) -> None:
    control_root = paper_runtime_control_root(tmp_path)
    control_root.mkdir(parents=True, exist_ok=True)
    global_pause_marker_path(control_root).write_text("{}", encoding="utf-8")
    strategy_pause_marker_path(control_root, "s21").write_text("{}", encoding="utf-8")
    strategy_pause_marker_path(control_root, "S23").write_text("{}", encoding="utf-8")

    state = load_paper_runtime_control_state(tmp_path)

    assert state.global_pause_active is True
    assert state.paused_strategies == frozenset({"S21", "S23"})
    assert state.strategy_paused("S21") is True
    assert state.strategy_paused("S99") is True


def test_load_paper_runtime_control_state_defaults_to_unpaused(tmp_path: Path) -> None:
    state = load_paper_runtime_control_state(tmp_path)

    assert state.global_pause_active is False
    assert state.paused_strategies == frozenset()
    assert state.strategy_paused("S21") is False


def test_load_paper_runtime_control_state_from_root_uses_explicit_directory(tmp_path: Path) -> None:
    control_root = tmp_path / "custom-controls"
    control_root.mkdir(parents=True, exist_ok=True)
    strategy_pause_marker_path(control_root, "s21").write_text("{}", encoding="utf-8")

    state = load_paper_runtime_control_state_from_root(control_root)

    assert state.control_root == control_root.resolve()
    assert state.paused_strategies == frozenset({"S21"})


def test_load_latest_operator_control_event_returns_last_valid_jsonl_row(tmp_path: Path) -> None:
    control_root = paper_runtime_control_root(tmp_path)
    control_root.mkdir(parents=True, exist_ok=True)
    operator_control_event_log_path(control_root).write_text(
        "\n".join(
            [
                '{"action":"PAUSE","scope":"GLOBAL","occurred_at":"2026-07-21T09:00:00+05:30","actor":"alice"}',
                "not-json",
                '{"action":"resume","scope":"strategy","strategy_code":"s23","occurred_at":"2026-07-21T09:05:00+05:30","actor":"bob","reason":"manual_resume"}',
            ]
        ),
        encoding="utf-8",
    )

    event = load_latest_operator_control_event(tmp_path)

    assert event is not None
    assert event.action == "RESUME"
    assert event.scope == "STRATEGY"
    assert event.strategy_code == "S23"
    assert event.actor == "bob"
    assert event.reason == "manual_resume"


def test_load_latest_operator_control_event_from_root_defaults_to_none(tmp_path: Path) -> None:
    assert load_latest_operator_control_event_from_root(tmp_path / "missing") is None
