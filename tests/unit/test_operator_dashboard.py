from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from tfis.dashboard import StrategyDashboardConfig, TfisOperatorDashboardBuilder


IST = ZoneInfo("Asia/Kolkata")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _strategy_config(artifact_root: Path) -> StrategyDashboardConfig:
    repo_root = _repo_root()
    return StrategyDashboardConfig(
        strategy_code="S23",
        display_name="S23 Operator Dashboard",
        artifact_root=artifact_root,
        strategy_path=repo_root / "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        reference_packet_path=repo_root / "config/reference_packets/s23_bear_put_live_decision_reference.json",
        session_id_prefix="s23-fyers-morning-supervised-decision",
    )


def test_dashboard_builds_from_stage_artifacts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    day_dir = artifact_root / "2026-06-10"
    stage_dir = day_dir / "s23-fyers-morning-supervised-decision-0916-2026-06-10"
    rc_stage_dir = day_dir / "s23-fyers-morning-supervised-decision-0930-2026-06-10"
    final_dir = day_dir / "s23-fyers-morning-supervised-decision-2026-06-10"
    stage_dir.mkdir(parents=True)
    rc_stage_dir.mkdir(parents=True)
    final_dir.mkdir(parents=True)
    preflight_payload = {
        "preflight_status": "READY",
        "option_chain_contract_count": 42,
        "option_chain_has_complete_oi": True,
    }
    (stage_dir / "snapshot_preflight_summary.json").write_text(
        json.dumps(preflight_payload),
        encoding="utf-8",
    )
    (stage_dir / "normalized_underlying_bars.json").write_text("{}", encoding="utf-8")
    (stage_dir / "normalized_option_chain_snapshot.json").write_text("{}", encoding="utf-8")
    (rc_stage_dir / "normalized_underlying_bars.json").write_text("{}", encoding="utf-8")
    (rc_stage_dir / "normalized_option_chain_snapshot.json").write_text(
        json.dumps(
            {
                "payload": {
                    "contracts": [
                        {
                            "symbol": "NIFTY_20260609_24250_PE",
                            "option_type": "PUT",
                            "strike": 24250,
                            "ltp": 171.55,
                            "oi": 656045,
                        },
                        {
                            "symbol": "NIFTY_20260609_24200_PE",
                            "option_type": "PUT",
                            "strike": 24200,
                            "ltp": 142.80,
                            "oi": 3795415,
                        },
                        {
                            "symbol": "NIFTY_20260609_24150_CE",
                            "option_type": "CALL",
                            "strike": 24150,
                            "ltp": 320.0,
                            "oi": 999999,
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (final_dir / "monthly_status_stage_0916.json").write_text(
        json.dumps(
            {
                "monthly_status": {
                    "price_used": 23255.65,
                    "status": "UNKNOWN",
                    "trigger_name": "NO_TRIGGER",
                    "notes": "No confirmed monthly-status trigger was met.",
                    "lookback_used": False,
                    "resolution_reason": "Current monthly/weekly context remained UNKNOWN.",
                    "trace": [],
                }
            }
        ),
        encoding="utf-8",
    )
    (final_dir / "trade_decision_explainer_stage_0916.json").write_text(
        json.dumps(
            {
                "stage": {
                    "stage_name": "Opening Snapshot",
                    "stage_time": "09:16",
                    "available_checkpoint_labels": ["0915"],
                    "current_day_high_so_far": 23286.9,
                    "current_day_low_so_far": 23229.15,
                    "underlying_spot_value": 23250.95,
                    "can_finalize_trade_decision": False,
                    "decision_summary": None,
                }
            }
        ),
        encoding="utf-8",
    )
    (final_dir / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "status": "READY",
                    "monthly_status": "UNKNOWN",
                    "selected_contract_symbol": "NIFTY_20260602_23800_PE",
                }
            }
        ),
        encoding="utf-8",
    )
    (final_dir / "trade_decision_summary.md").write_text("# summary\n", encoding="utf-8")
    (final_dir / "trade_decision_explainer.md").write_text("# explainer\n", encoding="utf-8")
    (final_dir / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")
    (final_dir / "paper_position_state.json").write_text("{}", encoding="utf-8")
    (final_dir / "paper_position_manager_summary.json").write_text("{}", encoding="utf-8")
    (final_dir / "paper_position_state_events.jsonl").write_text("{}\n", encoding="utf-8")
    final_ce_dir = final_dir / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    final_ce_dir.mkdir()
    (final_ce_dir / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "status": "READY",
                    "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
                    "selected_contract_symbol": "NIFTY_20260602_23850_CE",
                    "selected_contract_option_type": "CALL",
                    "selected_contract_strike": 23850,
                    "selected_contract_ltp": 239.0,
                    "selected_contract_oi": 500000,
                    "planned_entry_price": 194.25,
                    "target_price": 77.7,
                    "stoploss_price": 242.0,
                },
                "explanation": {
                    "contract_candidates": [
                        {
                            "status": "SELECTED",
                            "symbol": "NIFTY_20260602_23850_CE",
                            "strike": 23850,
                            "ltp": 239.0,
                            "oi": 500000,
                            "premium_distance_to_ideal": 1.25,
                        },
                        {
                            "status": "PASSED",
                            "symbol": "NIFTY_20260602_23900_CE",
                            "strike": 23900,
                            "ltp": 224.0,
                            "oi": 650000,
                            "premium_distance_to_ideal": 16.25,
                        },
                        {
                            "status": "REJECTED",
                            "symbol": "NIFTY_20260602_23950_CE",
                            "strike": 23950,
                            "ltp": 184.0,
                            "oi": 450000,
                            "premium_distance_to_ideal": 56.25,
                            "reason": "premium below minimum",
                        },
                        {
                            "status": "REJECTED",
                            "symbol": "NIFTY_20260602_23950_PE",
                            "strike": 23950,
                            "ltp": 312.0,
                            "oi": 900000,
                            "premium_distance_to_ideal": 73.0,
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (final_ce_dir / "paper_order_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "strategy_branch": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
                "selected_contract_symbol": "NIFTY_20260602_23850_CE",
                "status": "PAPER_ORDER_FILLED",
                "order_timestamp": "2026-06-10T09:30:00+05:30",
                "last_updated_timestamp": "2026-06-10T09:31:00+05:30",
            }
        ),
        encoding="utf-8",
    )
    final_pe_dir = final_dir / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    final_pe_dir.mkdir()
    (final_pe_dir / "trade_decision_explainer.json").write_text(
        json.dumps(
            {
                "session_date": "2026-06-10",
                "stages": [
                    {
                        "can_finalize_trade_decision": True,
                        "monthly_status": "BEAR",
                        "monthly_status_trigger": "BEAR_CONTINUES",
                        "monthly_status_price_used": 23255.65,
                        "monthly_status_resolution_reason": "Current month resolved directly from monthly structure rules.",
                        "decision_failure_code": "MINIMUM_PREMIUM_NOT_MET",
                        "decision_failure_message": "Option-chain candidates in the strike range do not meet minimum premium.",
                        "decision_failure_attempted_expiries": ["2026-06-02", "2026-06-09"],
                        "decision_failure_rejected_counts": {
                            "minimum_premium_not_met": 12,
                        },
                        "decision_summary": None,
                        "market_reference_values": {
                            "PRV_3DHH": {"value": 24168.05},
                        },
                        "provisional_formula_evaluation": [
                            {
                                "name": "start_strike",
                                "formula": "ROUND_UP(PRV_3DHH - PARAM(strike_buffer_pct)%)",
                                "resolved_formula": "ROUND_UP(24168.05 - 5.0%)",
                                "result": 23000.0,
                            },
                            {
                                "name": "end_strike",
                                "formula": "ROUND_UP(PRV_3DHH) + PARAM(strike_step)",
                                "resolved_formula": "ROUND_UP(24168.05) + 50.0",
                                "result": 24250.0,
                            },
                            {
                                "name": "ideal_premium",
                                "formula": "PRV_3DHH * 1.20%",
                                "resolved_formula": "24168.05 * 1.2%",
                                "result": 290.0166,
                            },
                            {
                                "name": "minimum_premium",
                                "formula": "PRV_3DHH * 0.90%",
                                "resolved_formula": "24168.05 * 0.9%",
                                "result": 217.51245,
                            },
                            {
                                "name": "entry",
                                "formula": "OPT_PRV_3DLL - 7.5%",
                                "resolved_formula": "230.0 - 7.5%",
                                "result": 212.75,
                            },
                            {
                                "name": "target",
                                "formula": "entry - 60.0%",
                                "resolved_formula": "212.75 - 60.0%",
                                "result": 85.1,
                            },
                            {
                                "name": "stoploss",
                                "formula": "MIN(entry + 60.0%, OPT_PRV_2DHH + 7.0%)",
                                "resolved_formula": "MIN(212.75 + 60.0%, 242.0 + 7.0%)",
                                "result": 258.94,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    trade_id = "S23-NIFTY_20260602_23800_PE-20260610T093000"
    trade_rows = [
        {
                "artifact_version": 1,
                "event_timestamp": "2026-06-10T09:30:00+05:30",
                "event_type": "OPEN",
                "trade_id": trade_id,
                "strategy_id": "S23:BEAR_PUT",
                "strategy_code": "S23",
                "strategy_branch": "BEAR_PUT",
                "symbol": "NIFTY",
                "option_type": "PUT",
                "selected_contract_symbol": "NIFTY_20260602_23800_PE",
                "expiry_date": "2026-06-02",
                "side": "SELL",
                "lots": 1,
                "quantity": 65,
                "entry_date": "2026-06-10",
                "entry_timestamp": "2026-06-10T09:30:00+05:30",
                "entry_price": 194.25,
                "target_price": 77.70,
                "stoploss_price": 242.0,
                "session_date": "2026-06-10",
                "lifecycle_status": "OPEN",
                "manager_status": "PAPER_POSITION_OPENED",
                "reason_code": "POSITION_OPENED",
                "message": "Paper position opened from final decision.",
                "state_directory": str(final_dir),
        },
        {
                "artifact_version": 1,
                "event_timestamp": "2026-06-10T09:31:00+05:30",
                "event_type": "HOLD",
                "trade_id": trade_id,
                "strategy_id": "S23:BEAR_PUT",
                "strategy_code": "S23",
                "strategy_branch": "BEAR_PUT",
                "symbol": "NIFTY",
                "option_type": "PUT",
                "selected_contract_symbol": "NIFTY_20260602_23800_PE",
                "expiry_date": "2026-06-02",
                "side": "SELL",
                "lots": 1,
                "quantity": 65,
                "entry_date": "2026-06-10",
                "entry_timestamp": "2026-06-10T09:30:00+05:30",
                "entry_price": 194.25,
                "current_price": 188.5,
                "current_bid": 188.0,
                "current_ask": 189.0,
                "target_price": 77.70,
                "stoploss_price": 242.0,
                "session_date": "2026-06-10",
                "lifecycle_status": "PAPER_POSITION_OPEN",
                "manager_status": "PAPER_POSITION_HELD",
                "reason_code": "no_exit_threshold_hit",
                "message": "Latest held state.",
                "state_directory": str(final_dir),
        },
    ]
    closed_trade_id = "S23-NIFTY_20260602_23850_CE-20260610T123000"
    trade_rows.extend(
        [
            {
                "artifact_version": 1,
                "event_timestamp": "2026-06-09T12:30:00+05:30",
                "event_type": "CLOSE",
                "trade_id": closed_trade_id,
                "strategy_id": "S23:BEAR_CALL",
                "strategy_code": "S23",
                "strategy_branch": "BEAR_CALL",
                "symbol": "NIFTY",
                "option_type": "CALL",
                "selected_contract_symbol": "NIFTY_20260602_23850_CE_CLOSED",
                "expiry_date": "2026-06-02",
                "side": "SELL",
                "lots": 1,
                "quantity": 65,
                "entry_date": "2026-06-09",
                "entry_timestamp": "2026-06-09T09:30:00+05:30",
                "entry_price": 194.25,
                "exit_price": 113.55,
                "exit_timestamp": "2026-06-09T12:30:00+05:30",
                "target_price": 77.70,
                "stoploss_price": 242.0,
                "gross_points": 80.70,
                "gross_pnl": 5245.5,
                "session_date": "2026-06-09",
                "lifecycle_status": "PAPER_POSITION_CLOSED",
                "manager_status": "PAPER_POSITION_FORCE_CLOSED",
                "reason_code": "expiry_force_close",
                "message": "Closed row should win over stale later rollover.",
                "state_directory": str(final_dir),
            },
            {
                "artifact_version": 1,
                "event_timestamp": "2026-06-11T10:20:00+05:30",
                "event_type": "ACTION_REQUIRED",
                "trade_id": closed_trade_id,
                "strategy_id": "S23:BEAR_CALL",
                "strategy_code": "S23",
                "strategy_branch": "BEAR_CALL",
                "symbol": "NIFTY",
                "option_type": "CALL",
                "selected_contract_symbol": "NIFTY_20260602_23850_CE_CLOSED",
                "expiry_date": "2026-06-02",
                "side": "SELL",
                "lots": 1,
                "quantity": 65,
                "entry_date": "2026-06-09",
                "entry_timestamp": "2026-06-09T09:30:00+05:30",
                "entry_price": 194.25,
                "target_price": 77.70,
                "stoploss_price": 242.0,
                "session_date": "2026-06-11",
                "lifecycle_status": "PAPER_ROLLOVER_REQUIRED",
                "manager_status": "PAPER_POSITION_ROLLOVER_REQUIRED",
                "reason_code": "stale_rollover_after_close",
                "message": "STALE ROLLOVER AFTER CLOSE SHOULD NOT DISPLAY",
                "rollover_required": True,
                "state_directory": str(final_dir),
            },
        ]
    )
    (final_dir / "paper_trade_ledger.jsonl").write_text(
        "\n".join(json.dumps(row) for row in trade_rows) + "\n",
        encoding="utf-8",
    )
    pending_dir = day_dir / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    pending_dir.mkdir()
    (pending_dir / "paper_order_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "strategy_branch": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
                "symbol": "NIFTY",
                "selected_contract_symbol": "NIFTY_20260602_23850_CE",
                "selected_contract_expiry": "2026-06-02",
                "selected_contract_option_type": "CALL",
                "selected_contract_strike": 23850,
                "expiry_type": "WEEKLY",
                "rollover_policy": "T_MINUS_1",
                "forced_close_time": "15:15:00",
                "no_carry_past_expiry": True,
                "order_side": "SELL",
                "trigger_rule": "SELL_TRIGGER_WHEN_PREMIUM_AT_OR_BELOW_ENTRY",
                "entry_date": "2026-06-10",
                "order_timestamp": "2026-06-10T09:30:00+05:30",
                "planned_entry_price": 194.25,
                "target_price": 77.7,
                "stoploss_price": 242.0,
                "fsl_price": 258.94,
                "lots": 1,
                "quantity": 65,
                "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
                "last_updated_timestamp": "2026-06-10T09:31:00+05:30",
                "last_market_price": 239.0,
                "last_market_bid": 238.5,
                "last_market_ask": 239.5,
                "last_reason_code": "paper_order_waiting_quote_above_entry",
                "last_message": "Selected option premium is still above entry; the paper sell order remains waiting.",
                "provenance_source_ids": [],
            }
        ),
        encoding="utf-8",
    )
    (pending_dir / "paper_order_events.jsonl").write_text("{}\n", encoding="utf-8")
    not_filled_dir = day_dir / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL_NOT_FILLED"
    not_filled_dir.mkdir()
    (not_filled_dir / "paper_order_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "strategy_branch": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
                "symbol": "NIFTY",
                "selected_contract_symbol": "NIFTY_20260602_23900_CE",
                "selected_contract_expiry": "2026-06-02",
                "selected_contract_option_type": "CALL",
                "selected_contract_strike": 23900,
                "expiry_type": "WEEKLY",
                "rollover_policy": "T_MINUS_1",
                "forced_close_time": "15:30:00",
                "no_carry_past_expiry": True,
                "order_side": "SELL",
                "trigger_rule": "SELL_TRIGGER_WHEN_PREMIUM_AT_OR_BELOW_ENTRY",
                "entry_date": "2026-06-10",
                "order_timestamp": "2026-06-10T09:30:00+05:30",
                "planned_entry_price": 190.0,
                "target_price": 76.0,
                "stoploss_price": 240.0,
                "lots": 1,
                "quantity": 65,
                "status": "PAPER_ORDER_NOT_FILLED",
                "last_updated_timestamp": "2026-06-10T15:30:05+05:30",
                "last_market_price": 231.65,
                "last_market_bid": 227.8,
                "last_market_ask": 231.8,
                "last_reason_code": "paper_order_not_triggered_by_watch_cutoff",
                "last_message": "Selected option premium did not reach entry before cutoff.",
                "provenance_source_ids": [],
            }
        ),
        encoding="utf-8",
    )
    (not_filled_dir / "paper_order_events.jsonl").write_text("{}\n", encoding="utf-8")
    stale_day_dir = artifact_root / "2026-06-09" / "s23-fyers-morning-supervised-decision-2026-06-09"
    stale_pending_dir = stale_day_dir / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    stale_pending_dir.mkdir(parents=True)
    (stale_pending_dir / "paper_order_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "strategy_branch": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
                "symbol": "NIFTY",
                "selected_contract_symbol": "NIFTY_20260609_24000_PE_STALE",
                "selected_contract_expiry": "2026-06-09",
                "selected_contract_option_type": "PUT",
                "selected_contract_strike": 24000,
                "expiry_type": "WEEKLY",
                "rollover_policy": "T_MINUS_1",
                "forced_close_time": "15:15:00",
                "no_carry_past_expiry": True,
                "order_side": "SELL",
                "trigger_rule": "SELL_TRIGGER_WHEN_PREMIUM_AT_OR_BELOW_ENTRY",
                "entry_date": "2026-06-09",
                "order_timestamp": "2026-06-09T09:30:00+05:30",
                "planned_entry_price": 200.0,
                "target_price": 80.0,
                "stoploss_price": 250.0,
                "fsl_price": None,
                "lots": 1,
                "quantity": 65,
                "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
                "last_updated_timestamp": "2026-06-09T15:30:00+05:30",
                "last_market_price": 260.0,
                "last_reason_code": "paper_order_waiting_quote_above_entry",
                "last_message": "Stale waiting order that must not carry forward.",
                "provenance_source_ids": [],
            }
        ),
        encoding="utf-8",
    )
    (stale_pending_dir / "paper_order_events.jsonl").write_text("{}\n", encoding="utf-8")

    result = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(artifact_root),)).build(
        output_root=tmp_path / "dashboard"
    )

    index_html = result.index_html.read_text(encoding="utf-8")
    strategy_html = result.strategy_pages["S23"].read_text(encoding="utf-8")
    manual_calculator_html = result.tool_pages["s23_manual_calculator"].read_text(encoding="utf-8")
    monthly_calculator_html = result.tool_pages["monthly_status_calculator"].read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))

    assert "TFIS Operator Dashboard" in index_html
    assert "2026-06-10" in strategy_html
    assert "Run Status" in strategy_html
    assert "Final Contract" in strategy_html
    assert "Final S23 Leg Decisions" in strategy_html
    assert ".final-leg-table th:nth-child(2)" in strategy_html
    assert ".final-leg-table .contract-cell strong" in strategy_html
    assert "No contract selected" in strategy_html
    assert "SELL PE" in strategy_html
    assert "MINIMUM_PREMIUM_NOT_MET" in strategy_html
    failed_pe_row = re.search(
        r"NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT.*?MINIMUM_PREMIUM_NOT_MET",
        strategy_html,
        flags=re.S,
    )
    assert failed_pe_row is not None
    assert failed_pe_row.group(0).count(">n/a<") >= 6
    assert "No entry applies because no contract qualified" in strategy_html
    assert "provisional entry/target/SL values were 212.75 / 85.10 / 258.94" in strategy_html
    assert "Option-chain candidates in the strike range do not meet minimum premium." in strategy_html
    assert "near expiry 2026-06-02; fallback expiry 2026-06-09" in strategy_html
    assert '<details class="session-summary summary-shell explanation-panel">' in strategy_html
    assert "Expand dry-run steps" in strategy_html
    assert "Calculation Explanation" in strategy_html
    assert "tfis-dashboard-open-details" in strategy_html
    assert "Step 1 - Preparation" in strategy_html
    assert "Step 2 - Monthly status" in strategy_html
    assert "Step 2a - Rule group" in strategy_html
    assert "Step 3 - Collect NIFTY spot data" in strategy_html
    assert "Step 4 - Check strike factor" in strategy_html
    assert "Step 5 - Find the strike range" in strategy_html
    assert "Step 6 - Minimum OI" in strategy_html
    assert "Step 7a - Ideal/maximum premium required" in strategy_html
    assert "Step 7b - Minimum premium required" in strategy_html
    assert "Step 8a - Near contract ideal/maximum premium search" in strategy_html
    assert "Step 8b - Near contract minimum premium fallback" in strategy_html
    assert "Step 8c - Next contract fallback" in strategy_html
    assert "Step 8d - Final weekly option" in strategy_html
    assert "Step 8d - No qualifying strike" in strategy_html
    assert "Step 8e - ORPT/RC entry timing" in strategy_html
    assert "cannot check ORPT/RC option candles or place a paper order without a selected option contract" in strategy_html
    assert "Step 9 - Entry" in strategy_html
    assert "paper order waits for the selected option premium to trade at or below this entry price" in strategy_html
    assert "Step 10 - Target" in strategy_html
    assert "Step 11 - Stop loss" in strategy_html
    assert "Eligible Strike OI Comparison" in strategy_html
    assert "eligible-strike-table th.number-cell" in strategy_html
    assert "Expiry</th>" in strategy_html
    assert ".full-scan-table th:nth-child(8)" in strategy_html
    assert ".full-scan-table .reason-cell" in strategy_html
    assert "Displayed in inferred rule-sheet search order" in strategy_html
    assert "Final strike is 23850" in strategy_html
    assert "Step 8a - Near contract ideal/maximum premium strike search" in strategy_html
    assert "Rule 8a audit: TFIS checks the near weekly contract from Start Strike to End Strike." in strategy_html
    assert "Step 8b - Near contract minimum premium strike search" in strategy_html
    assert "Step 8b was not run because Step 8a already selected the final strike." in strategy_html
    assert "Rule 8b audit: because Step 8a did not select a strike" in strategy_html
    assert "Step 8b is used only when Step 8a does not find an ideal/maximum-premium strike" in strategy_html
    assert "Expand the Step 8a strike matching audit below to validate each strike." in strategy_html
    assert "Expand the Step 8b strike matching audit below" in strategy_html
    assert "Step 8c - Next contract fallback" in strategy_html
    assert "Expand the Step 8c next-contract audit below" in strategy_html
    assert "passed audit because side CE matches CE; premium 184 present" in strategy_html
    assert "selected because side CE matches CE" in strategy_html
    assert "passed audit because side CE matches CE" in strategy_html
    assert "not selected because another strike was first in rule-sheet search order" in strategy_html
    assert "NIFTY_20260602_23950_PE" not in strategy_html
    assert "full-scan-panel" in strategy_html
    assert "full-scan-table-wrap" in strategy_html
    assert "650000" in strategy_html
    assert "NIFTY_20260602_23800_PE" in strategy_html
    assert "NIFTY_20260602_23850_CE" in strategy_html
    assert "SELL CE" in strategy_html
    assert "Trades Taken" in strategy_html
    assert "trade-table-wrap" in strategy_html
    assert "Current" in strategy_html
    assert "LTP" in strategy_html
    assert "Bid / Ask" in strategy_html
    assert "239" in strategy_html
    assert "238.50 / 239.50" in strategy_html
    assert "PAPER_POSITION_HELD" in strategy_html
    assert "Bear Put" in strategy_html
    assert "compact-cell" in strategy_html
    assert "NIFTY_20260602_23850_CE_CLOSED" not in strategy_html
    assert "PAPER_POSITION_FORCE_CLOSED" not in strategy_html
    assert "STALE ROLLOVER AFTER CLOSE SHOULD NOT DISPLAY" not in strategy_html
    assert "stale_rollover_after_close" not in strategy_html
    assert strategy_html.count(trade_id) == 1
    assert "188.50" in strategy_html
    assert "188 / 189" in strategy_html
    assert "ORDER_WAITING" in strategy_html
    assert "paper_order_state.json" in strategy_html
    assert strategy_html.count("ORDER_WAITING_FOR_TRIGGER") == 1
    assert "ORDER_NOT_FILLED" in strategy_html
    assert "paper_order_not_triggered_by_watch_cutoff" in strategy_html
    assert "NIFTY_20260609_24000_PE_STALE" not in strategy_html
    assert "Stale waiting order that must not carry forward" not in strategy_html
    assert '<details class="stage-card snapshot-panel">' in strategy_html
    assert '<summary class="stage-summary">' in strategy_html
    assert "S23 Rule Sheet Steps" in strategy_html
    assert "Step 1" in strategy_html
    assert "Preparation date/time" in strategy_html
    assert "Step 2" in strategy_html
    assert "Monthly status" in strategy_html
    assert "Step 3" in strategy_html
    assert "Rule group" in strategy_html
    assert "Step 4" in strategy_html
    assert "Strike range" in strategy_html
    assert "Step 5" in strategy_html
    assert "Near/next contract search" in strategy_html
    assert "Step 6" in strategy_html
    assert "Premium and OI" in strategy_html
    assert "Step 7" in strategy_html
    assert "Final weekly option" in strategy_html
    assert "Step 8" in strategy_html
    assert "Entry / Target / SL" in strategy_html
    assert "paper_position_state.json" in strategy_html
    assert "paper_position_manager_summary.json" in strategy_html
    assert "paper_trade_ledger.jsonl" in strategy_html
    assert "Monthly Status Calculator" in index_html
    assert "Monthly Status Calculator" in strategy_html
    assert "CalculateStrikes" in manual_calculator_html
    assert "Review Date" in manual_calculator_html
    assert "Fetch Captured Premium/OI" in manual_calculator_html
    assert "Eligible CE Strikes" in manual_calculator_html
    assert "Eligible PE Strikes" in manual_calculator_html
    assert "Rule Sheet Steps" in manual_calculator_html
    assert "Manual Review Value" in manual_calculator_html
    assert "Final CE Premium / OI" in manual_calculator_html
    assert 'PE: { trade: "Sell Put", spotRef: "d2hh", entryRef: "opt2dll"' in manual_calculator_html
    assert 'PE: { trade: "Sell Put", spotRef: "d3hh", entryRef: "opt3dll"' in manual_calculator_html
    assert "optionSide" not in manual_calculator_html
    assert "<th>Side</th><th>Trade</th>" in manual_calculator_html
    assert "CE final calculation" in manual_calculator_html
    assert "PE final calculation" in manual_calculator_html
    assert "GetMonthlyStatus" in monthly_calculator_html
    assert "Fetch Captured Monthly Data" in monthly_calculator_html
    assert "Market Structure Chart" in monthly_calculator_html
    assert 'id="monthlyStatusChart"' in monthly_calculator_html
    assert 'id="monthlyChartInspector"' in monthly_calculator_html
    assert 'id="monthlyChartLegend"' in monthly_calculator_html
    assert 'data-frame="monthly"' in monthly_calculator_html
    assert 'id="monthlyChartTooltip"' in monthly_calculator_html
    assert 'data-level-group="monthly"' in monthly_calculator_html
    assert "chartLineLegend" in monthly_calculator_html
    assert "handleMonthlyChartHover" in monthly_calculator_html
    assert "return number.toFixed(2);" in monthly_calculator_html
    assert "chart-review-marker" in monthly_calculator_html
    assert "renderMonthlyStatusChart" in monthly_calculator_html
    assert "PMH" in monthly_calculator_html
    assert "CWH" in monthly_calculator_html
    assert manifest["strategies"][0]["sessions"][0]["final_decision_status"] == "READY"
    assert manifest["strategies"][0]["sessions"][0]["final_selected_contract_symbols"] == [
        "NIFTY_20260602_23850_CE",
        "NIFTY_20260602_23800_PE",
    ]
    assert "monthly_status_index" in manifest["review_data"]
    assert "strategy_S23_index" in manifest["review_data"]
    monthly_index = json.loads(result.review_data_pages["monthly_status_index"].read_text(encoding="utf-8"))
    monthly_payload_path = result.output_root / monthly_index["dates"]["2026-06-10"]
    monthly_payload = json.loads(monthly_payload_path.read_text(encoding="utf-8"))
    assert monthly_payload["symbol"] == "NIFTY"
    assert monthly_payload["instrument_group"] == "nifty"


def test_dashboard_reconstructs_stage_from_snapshot_dir(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    day_dir = artifact_root / "2026-06-11"
    stage_dir = day_dir / "s23-fyers-morning-supervised-decision-0916-2026-06-11"
    stage_dir.mkdir(parents=True)
    (stage_dir / "snapshot_preflight_summary.json").write_text(
        json.dumps(
            {
                "preflight_status": "READY",
                "option_chain_contract_count": 2,
                "option_chain_has_complete_oi": True,
            }
        ),
        encoding="utf-8",
    )
    (stage_dir / "normalized_underlying_snapshot.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-11T09:16:01+05:30",
                "effective_timestamp": "2026-06-11T09:16:01+05:30",
                "event_type": "UNDERLYING_QUOTE",
                "normalized_by": "fyers-adapter-v1",
                "payload": {"ask": None, "bid": None, "ltp": 23250.95, "symbol": "NIFTY", "volume": None},
                "session_date": "2026-06-11",
                "source_id": "fyers:underlying_quote",
                "source_sequence": None,
                "source_type": "broker_fyers",
                "synthetic_fixture": False,
                "timezone": "Asia/Kolkata",
                "data_quality_flags": [],
            }
        ),
        encoding="utf-8",
    )
    (stage_dir / "normalized_underlying_bars.json").write_text(
        json.dumps(
            {
                "session_date": "2026-06-11",
                "symbol": "NIFTY",
                "bars": [
                    {
                        "bar_start": "2026-06-11T09:15:00+05:30",
                        "bar_end": "2026-06-11T09:15:59+05:30",
                        "open": 23229.15,
                        "high": 23286.9,
                        "low": 23229.15,
                        "close": 23255.65,
                        "volume": 1000.0,
                        "source_id": "fyers:underlying_history",
                        "symbol": "NIFTY",
                    },
                    {
                        "bar_start": "2026-06-11T09:16:00+05:30",
                        "bar_end": "2026-06-11T09:16:59+05:30",
                        "open": 23255.65,
                        "high": 23257.1,
                        "low": 23233.4,
                        "close": 23241.7,
                        "volume": 100.0,
                        "source_id": "fyers:underlying_history",
                        "symbol": "NIFTY",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (stage_dir / "normalized_underlying_daily_bars.json").write_text(
        json.dumps(
            {
                "session_date": "2026-06-11",
                "symbol": "NIFTY",
                "bars": [
                    {
                        "bar_start": "2026-05-27T15:15:00+05:30",
                        "bar_end": "2026-05-27T15:29:59+05:30",
                        "open": 23920.0,
                        "high": 24030.0,
                        "low": 23840.0,
                        "close": 24010.0,
                        "volume": 1000.0,
                        "source_id": "daily",
                        "symbol": "NIFTY",
                    },
                    {
                        "bar_start": "2026-05-28T15:15:00+05:30",
                        "bar_end": "2026-05-28T15:29:59+05:30",
                        "open": 24020.0,
                        "high": 24120.0,
                        "low": 23910.0,
                        "close": 24070.0,
                        "volume": 1000.0,
                        "source_id": "daily",
                        "symbol": "NIFTY",
                    },
                    {
                        "bar_start": "2026-05-29T15:15:00+05:30",
                        "bar_end": "2026-05-29T15:29:59+05:30",
                        "open": 23900.0,
                        "high": 24002.8,
                        "low": 23889.15,
                        "close": 23893.4,
                        "volume": 1000.0,
                        "source_id": "daily",
                        "symbol": "NIFTY",
                    },
                    {
                        "bar_start": "2026-06-10T15:15:00+05:30",
                        "bar_end": "2026-06-10T15:29:59+05:30",
                        "open": 23300.0,
                        "high": 23380.0,
                        "low": 23150.0,
                        "close": 23220.0,
                        "volume": 1000.0,
                        "source_id": "daily",
                        "symbol": "NIFTY",
                    },
                    {
                        "bar_start": "2026-06-11T09:15:00+05:30",
                        "bar_end": "2026-06-11T15:29:59+05:30",
                        "open": 23229.15,
                        "high": 23286.9,
                        "low": 23229.15,
                        "close": 23255.65,
                        "volume": 1000.0,
                        "source_id": "daily",
                        "symbol": "NIFTY",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (stage_dir / "normalized_option_chain_snapshot.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-11T09:16:03+05:30",
                "effective_timestamp": "2026-06-11T09:16:03+05:30",
                "event_type": "OPTION_CHAIN_SNAPSHOT",
                "normalized_by": "fyers-adapter-v1",
                "payload": {
                    "underlying_symbol": "NIFTY",
                    "expiry": "2026-06-18",
                    "contracts": [
                        {
                            "ask": 220.0,
                            "bid": 218.0,
                            "expiry": "2026-06-18",
                            "ltp": 219.0,
                            "oi": 1200.0,
                            "option_type": "PUT",
                            "strike": 23200.0,
                            "symbol": "NIFTY_20260618_23200_PE",
                            "volume": 100.0,
                        },
                        {
                            "ask": 260.0,
                            "bid": 258.0,
                            "expiry": "2026-06-18",
                            "ltp": 259.0,
                            "oi": 1500.0,
                            "option_type": "PUT",
                            "strike": 23300.0,
                            "symbol": "NIFTY_20260618_23300_PE",
                            "volume": 150.0,
                        },
                    ],
                },
                "session_date": "2026-06-11",
                "source_id": "fyers:option_chain",
                "source_sequence": None,
                "source_type": "broker_fyers",
                "synthetic_fixture": False,
                "timezone": "Asia/Kolkata",
                "data_quality_flags": [],
            }
        ),
        encoding="utf-8",
    )

    result = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(artifact_root),)).build(
        output_root=tmp_path / "dashboard"
    )

    strategy_html = result.strategy_pages["S23"].read_text(encoding="utf-8")
    assert "Opening Snapshot" in strategy_html
    assert "09:16" in strategy_html
    assert "Trigger" in strategy_html
    assert "normalized_underlying_bars.json" in strategy_html


def test_s23_inline_step8_audit_accepts_tuple_candidates() -> None:
    builder = TfisOperatorDashboardBuilder(strategy_configs=())
    leg = {
        "branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        "side": "SELL PE",
        "start_strike": 23000,
        "end_strike": 24250,
        "ideal_premium": 290.02,
        "minimum_premium": 217.51,
        "minimum_oi": 32500,
        "contract_candidates": (
            {
                "symbol": "NIFTY_20260630_24250_PE",
                "strike": 24250,
                "option_type": "PUT",
                "premium": 171.55,
                "oi": 656045,
                "premium_distance": 118.47,
                "status": "REJECTED",
                "reason": "premium below minimum",
            },
            {
                "symbol": "NIFTY_20260630_24200_PE",
                "strike": 24200,
                "option_type": "PUT",
                "premium": 142.80,
                "oi": 3795415,
                "premium_distance": 147.22,
                "status": "REJECTED",
                "reason": "premium below minimum",
            },
            {
                "symbol": "NIFTY_20260630_22950_PE",
                "strike": 22950,
                "option_type": "PUT",
                "premium": 320.0,
                "oi": 999999,
                "premium_distance": 29.98,
                "status": "REJECTED",
                "reason": "strike outside range",
            },
            {
                "symbol": "NIFTY_20260630_24300_PE",
                "strike": 24300,
                "option_type": "PUT",
                "premium": 320.0,
                "oi": 999999,
                "premium_distance": 29.98,
                "status": "REJECTED",
                "reason": "strike outside range",
            },
            {
                "symbol": "NIFTY_20260630_24150_CE",
                "strike": 24150,
                "option_type": "CALL",
                "premium": 320.0,
                "oi": 999999,
                "premium_distance": 29.98,
                "status": "PASS",
            },
        ),
    }

    html = builder._render_s23_step8_inline_audit(leg, "8a")

    assert "NIFTY_20260630_24250_PE" in html
    assert "NIFTY_20260630_24200_PE" in html
    assert "NIFTY_20260630_22950_PE" not in html
    assert "NIFTY_20260630_24300_PE" not in html
    assert ">23000<" in html
    assert "No PE contract was present in the captured option chain for strike 23000." in html
    assert "NIFTY_20260630_24150_CE" not in html
    assert "premium 171.55 below ideal/maximum 290.02" in html


def test_s23_inline_step8_audit_filters_to_attempted_near_expiry() -> None:
    builder = TfisOperatorDashboardBuilder(strategy_configs=())
    leg = {
        "branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "side": "SELL CE",
        "start_strike": 24950,
        "end_strike": 23700,
        "ideal_premium": 285.47,
        "minimum_premium": 214.10,
        "minimum_oi": 32500,
        "attempted_expiries": ["2026-07-07"],
        "contract_candidates": [
            {
                "symbol": "NIFTY_20260630_23900_CE",
                "expiry": "2026-06-30",
                "strike": 23900,
                "option_type": "CALL",
                "premium": 287.40,
                "oi": 2597335,
                "premium_distance": 1.93,
                "status": "REJECTED",
                "reason": "expiry mismatch",
            },
            {
                "symbol": "NIFTY_20260707_23900_CE",
                "expiry": "2026-07-07",
                "strike": 23900,
                "option_type": "CALL",
                "premium": 305.0,
                "oi": 216645,
                "premium_distance": 19.53,
                "status": "SELECTED",
            },
        ],
    }

    html = builder._render_s23_step8_inline_audit(leg, "8a")

    assert "NIFTY_20260707_23900_CE" in html
    assert "NIFTY_20260630_23900_CE" not in html


def test_reconstructed_s23_candidate_rows_keep_full_strike_range(tmp_path: Path) -> None:
    builder = TfisOperatorDashboardBuilder(strategy_configs=())
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    contracts = [
        {
            "symbol": f"NIFTY_20260630_{strike}_PE",
            "expiry": "2026-06-30",
            "option_type": "PUT",
            "strike": strike,
            "ltp": 10.0 + ((strike - 23000) / 50.0),
            "oi": 100000,
        }
        for strike in range(23000, 24251, 50)
    ]
    (stage_dir / "normalized_option_chain_snapshot.json").write_text(
        json.dumps({"payload": {"contracts": contracts}}),
        encoding="utf-8",
    )
    strategy_rule = SimpleNamespace(
        option_type=SimpleNamespace(value="PUT"),
        minimum_oi=32500,
    )
    formula_values = {
        "start_strike": {"result": 23000},
        "end_strike": {"result": 24250},
        "minimum_premium": {"result": 217.51},
        "ideal_premium": {"result": 290.02},
    }

    rows = builder._candidate_rows(
        strategy_rule=strategy_rule,
        stage_dir=stage_dir,
        formula_values=formula_values,
        selected_contract_symbol=None,
    )

    assert len(rows) == 26
    assert {row["strike"] for row in rows} == set(range(23000, 24251, 50))
    assert {row["expiry"] for row in rows} == {"2026-06-30"}
    assert any(row["symbol"] == "NIFTY_20260630_23000_PE" for row in rows)
    assert any(row["symbol"] == "NIFTY_20260630_24250_PE" for row in rows)
