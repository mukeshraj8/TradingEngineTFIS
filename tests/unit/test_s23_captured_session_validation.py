from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_validation_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_s23_captured_session_validation.py"
    spec = importlib.util.spec_from_file_location("run_s23_captured_session_validation", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_captured_sessions_reports_decision_and_lifecycle_gaps(tmp_path: Path) -> None:
    module = _load_validation_module()
    root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    day = root / "2026-07-02"
    for stage in ("0916", "0925", "0930"):
        stage_dir = day / f"s23-fyers-morning-supervised-decision-{stage}-2026-07-02"
        stage_dir.mkdir(parents=True)
        (stage_dir / "normalized_option_chain_snapshot.json").write_text("{}", encoding="utf-8")
    branch = (
        day
        / "s23-fyers-morning-supervised-decision-2026-07-02"
        / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    )
    branch.mkdir(parents=True)
    (branch / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "status": "READY",
                    "selected_contract_symbol": "NIFTY_20260714_24200_PE",
                    "selected_contract_expiry": "2026-07-14",
                    "selected_contract_option_type": "PUT",
                    "selected_contract_strike": 24200,
                    "selected_contract_ltp": 219.1,
                    "selected_contract_oi": 217425,
                    "planned_entry_price": 212.75,
                    "target_price": 85.1,
                    "stoploss_price": 258.94,
                    "monthly_status": "BEAR",
                    "contract_selection_reason": "selected fallback expiry",
                    "contract_selection_attempted_expiries": ["2026-07-07", "2026-07-14"],
                }
            }
        ),
        encoding="utf-8",
    )
    (branch / "paper_order_state.json").write_text(
        json.dumps({"status": "PAPER_ORDER_FILLED", "fill_price": 212.35}),
        encoding="utf-8",
    )

    sessions = module.validate_captured_sessions(root)

    assert len(sessions) == 1
    session = sessions[0]
    assert session.session_date == "2026-07-02"
    assert session.stage_coverage == ("0916", "0925", "0930")
    assert session.selected_branch_count == 1
    assert session.order_count == 1
    assert session.replay_readiness == "ORDER_REVIEWABLE_PRICE_STREAM_MISSING"
    assert "selected_contract_intraday_price_stream_not_persisted" in session.gaps
    assert session.branches[0].attempted_expiries == ("2026-07-07", "2026-07-14")


def test_validate_captured_sessions_reconstructs_blocked_fresh_calculation(tmp_path: Path) -> None:
    module = _load_validation_module()
    root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    day = root / "2026-07-03"
    stage_dir = day / "s23-fyers-morning-supervised-decision-0930-2026-07-03"
    stage_dir.mkdir(parents=True)
    (stage_dir / "normalized_option_chain_snapshot.json").write_text(
        json.dumps(
            {
                "session_date": "2026-07-03",
                "effective_timestamp": "2026-07-03T09:30:00+05:30",
                "captured_at": "2026-07-03T09:30:01+05:30",
                "timezone": "Asia/Kolkata",
                "source_type": "test_fixture",
                "source_id": "chain",
                "synthetic_fixture": True,
                "normalized_by": "test",
                "payload": {
                    "underlying_symbol": "NIFTY",
                    "expiry": "2026-07-07",
                    "contracts": [
                        {
                            "symbol": "NIFTY_20260707_24100_CE",
                            "option_type": "CALL",
                            "strike": 24100,
                            "expiry": "2026-07-07",
                            "bid": 285,
                            "ask": 287,
                            "ltp": 286.85,
                            "oi": 3734250,
                            "volume": 1,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    branch = (
        day
        / "s23-fyers-morning-supervised-decision-2026-07-03"
        / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    )
    branch.mkdir(parents=True)
    (branch / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "status": "READY",
                    "mode": "CARRY_FORWARD_RESUME",
                    "monthly_status": "BEAR",
                    "selected_contract_symbol": None,
                    "planned_entry_price": None,
                    "target_price": None,
                    "stoploss_price": None,
                    "notes": ["Fresh entry planning was skipped because an open carry-forward position exists."],
                },
                "explanation": {
                    "formula_evaluation": [
                        {"name": "start_strike", "result": 24150},
                        {"name": "end_strike", "result": 23800},
                        {"name": "ideal_premium", "result": 286.74},
                        {"name": "minimum_premium", "result": 215.05},
                        {"name": "entry", "result": 194.25},
                        {"name": "target", "result": 77.70},
                        {"name": "stoploss", "result": 242.00},
                    ],
                    "contract_selection_thresholds": {"minimum_oi": 32500},
                },
            }
        ),
        encoding="utf-8",
    )

    session = module.validate_captured_sessions(root)[0]
    branch_summary = session.branches[0]

    assert session.replay_readiness == "CALCULATION_RECONSTRUCTED_ORDER_BLOCKED"
    assert branch_summary.selected_contract_symbol == "NIFTY_20260707_24100_CE"
    assert branch_summary.planned_entry_price == 194.25
    assert branch_summary.order_placement_blocked is True
    assert branch_summary.calculation_source == "review_reconstructed_from_captured_snapshot"
