from __future__ import annotations

import json
from pathlib import Path

from tfis.paper.decision_summary_discovery import (
    discover_trade_decision_summaries,
    discover_trade_decision_summary_symbols,
    resolve_final_trade_decision_summary,
    resolve_trade_decision_artifact_dir,
)


def test_discover_trade_decision_summaries_returns_branch_and_summary_view(tmp_path: Path) -> None:
    session_dir = tmp_path / "2026-07-20" / "s23-fyers-morning-supervised-decision-2026-07-20"
    branch_dir = session_dir / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    branch_dir.mkdir(parents=True)
    summary_path = branch_dir / "trade_decision_summary.json"
    order_state_path = branch_dir / "paper_order_state.json"
    summary_path.write_text(
        json.dumps(
            {
                "summary": {
                    "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
                    "status": "READY",
                    "selected_contract_symbol": "NIFTY_20260721_23950_CE",
                },
                "explanation": {"note": "fixture"},
            }
        ),
        encoding="utf-8",
    )
    order_state_path.write_text("{}", encoding="utf-8")

    candidates = discover_trade_decision_summaries(session_dir)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.session_directory == session_dir
    assert candidate.branch_directory == branch_dir
    assert candidate.summary_path == summary_path
    assert candidate.order_state_path == order_state_path
    assert candidate.branch == "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    assert candidate.summary["selected_contract_symbol"] == "NIFTY_20260721_23950_CE"
    assert candidate.payload["explanation"]["note"] == "fixture"


def test_discover_trade_decision_summary_symbols_returns_unique_non_empty_symbols(
    tmp_path: Path,
) -> None:
    session_dir = tmp_path / "2026-07-21" / "s23-fyers-morning-supervised-decision-2026-07-21"
    first_branch = session_dir / "A_BRANCH"
    second_branch = session_dir / "B_BRANCH"
    third_branch = session_dir / "C_BRANCH"
    for path in (first_branch, second_branch, third_branch):
        path.mkdir(parents=True)
    (first_branch / "trade_decision_summary.json").write_text(
        json.dumps({"summary": {"selected_contract_symbol": "NIFTY_20260728_24300_PE"}}),
        encoding="utf-8",
    )
    (second_branch / "trade_decision_summary.json").write_text(
        json.dumps({"summary": {"selected_contract_symbol": "NIFTY_20260728_24300_PE"}}),
        encoding="utf-8",
    )
    (third_branch / "trade_decision_summary.json").write_text(
        json.dumps({"summary": {"selected_contract_symbol": ""}}),
        encoding="utf-8",
    )

    assert discover_trade_decision_summary_symbols(session_dir) == (
        "NIFTY_20260728_24300_PE",
    )


def test_resolve_trade_decision_artifact_dir_prefers_top_level_then_matching_branch(
    tmp_path: Path,
) -> None:
    session_dir = tmp_path / "2026-07-21" / "s23-fyers-morning-supervised-decision-2026-07-21"
    session_dir.mkdir(parents=True)
    top_level_summary = session_dir / "trade_decision_summary.json"
    top_level_summary.write_text(
        json.dumps({"summary": {"status": "READY"}}),
        encoding="utf-8",
    )

    assert resolve_trade_decision_artifact_dir(
        session_dir,
        preferred_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
    ) == session_dir

    top_level_summary.unlink()
    branch_dir = session_dir / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    branch_dir.mkdir()
    (branch_dir / "trade_decision_summary.json").write_text(
        json.dumps({"summary": {"strategy_branch": branch_dir.name, "status": "READY"}}),
        encoding="utf-8",
    )

    assert resolve_trade_decision_artifact_dir(
        session_dir,
        preferred_branch=branch_dir.name,
    ) == branch_dir


def test_resolve_final_trade_decision_summary_returns_branch_summary_view(
    tmp_path: Path,
) -> None:
    session_dir = tmp_path / "2026-07-21" / "s23-fyers-morning-supervised-decision-2026-07-21"
    branch_dir = session_dir / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    branch_dir.mkdir(parents=True)
    (branch_dir / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "strategy_branch": branch_dir.name,
                    "status": "READY",
                    "selected_contract_symbol": "NIFTY_20260728_24300_PE",
                }
            }
        ),
        encoding="utf-8",
    )

    candidate = resolve_final_trade_decision_summary(
        session_dir,
        preferred_branch=branch_dir.name,
    )

    assert candidate is not None
    assert candidate.artifact_directory == branch_dir
    assert candidate.summary_path == branch_dir / "trade_decision_summary.json"
    assert candidate.summary is not None
    assert candidate.summary["selected_contract_symbol"] == "NIFTY_20260728_24300_PE"
