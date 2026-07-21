from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from tfis.paper import (
    PaperFreshEntryPromotionRecord,
    PaperFreshEntryPromotionSummary,
    fresh_decision_launch_marker_path,
    handoff_fresh_entry_requirement,
)


def test_handoff_fresh_entry_requirement_skips_when_not_required(tmp_path: Path) -> None:
    result = handoff_fresh_entry_requirement(
        strategy_code="S23",
        session_directory=tmp_path,
        session_date=date(2026, 7, 20),
        trade_id="trade-1",
        final_step_status="PAPER_POSITION_HELD",
        evaluated_at=datetime(2026, 7, 20, 10, 5),
        artifact_root=tmp_path,
        session_id_prefix="s23-fyers-morning-supervised-decision",
    )

    assert result.action == "not_required"
    assert not result.marker_path.exists()


def test_handoff_fresh_entry_requirement_records_promotion_before_spawn(tmp_path: Path) -> None:
    promoted_session = tmp_path / "promoted-session"
    promoted_session.mkdir()

    def _promotion_loader(_artifact_root, **_kwargs):
        return PaperFreshEntryPromotionSummary(
            session_dir=promoted_session,
            promotions=(
                PaperFreshEntryPromotionRecord(
                    branch="BRANCH",
                    status="promoted_to_waiting_order",
                    order_state_json=str(promoted_session / "paper_order_state.json"),
                ),
            ),
        )

    spawned: list[str] = []

    result = handoff_fresh_entry_requirement(
        strategy_code="S23",
        session_directory=tmp_path / "closed-session",
        session_date=date(2026, 7, 20),
        trade_id="trade-1",
        final_step_status="PAPER_POSITION_FRESH_ENTRY_REQUIRED",
        evaluated_at=datetime(2026, 7, 20, 10, 5),
        artifact_root=tmp_path,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        promotion_loader=_promotion_loader,
        runner_name="unused.py",
        spawn_runner=lambda: spawned.append("spawn") or 999,
    )

    assert result.action == "promoted_existing_blocked_decision"
    assert spawned == []
    marker_payload = json.loads(result.marker_path.read_text(encoding="utf-8"))
    assert marker_payload["mode"] == "promoted_existing_blocked_decision"
    assert marker_payload["trade_id"] == "trade-1"


def test_handoff_fresh_entry_requirement_spawns_when_promotion_unavailable(tmp_path: Path) -> None:
    session_directory = tmp_path / "closed-session"

    result = handoff_fresh_entry_requirement(
        strategy_code="S21",
        session_directory=session_directory,
        session_date=date(2026, 7, 20),
        trade_id="trade-2",
        final_step_status="PAPER_POSITION_FRESH_ENTRY_REQUIRED",
        evaluated_at=datetime(2026, 7, 20, 10, 6),
        artifact_root=tmp_path,
        session_id_prefix=None,
        runner_name="run_s21_banknifty_0916_supervised_decision.py",
        spawn_runner=lambda: 4321,
    )

    assert result.action == "spawned_fresh_supervised_runner"
    assert result.pid == 4321
    marker_payload = json.loads(
        fresh_decision_launch_marker_path(session_directory).read_text(encoding="utf-8")
    )
    assert marker_payload["runner_script"] == "run_s21_banknifty_0916_supervised_decision.py"
    assert marker_payload["pid"] == 4321
