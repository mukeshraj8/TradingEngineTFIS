from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from tfis.dashboard import StrategyDashboardConfig, TfisOperatorDashboardBuilder
from tfis.dashboard.operator_dashboard import (
    DashboardSelectedContractStreamHealth,
    DashboardTradeLedgerRow,
)


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


def _s21_strategy_config(artifact_root: Path) -> StrategyDashboardConfig:
    repo_root = _repo_root()
    return StrategyDashboardConfig(
        strategy_code="S21",
        display_name="S21 Operator Dashboard",
        artifact_root=artifact_root,
        strategy_path=repo_root / "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
        reference_packet_path=repo_root / "config/reference_packets/s21_banknifty_monthly_live_decision_reference.json",
        session_id_prefix="s21-fyers-morning-supervised-decision",
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
    fresh_entry_close_trade_id = "S23-NIFTY_20260602_23825_PE-20260610T100000"
    trade_rows.append(
        {
            "artifact_version": 1,
            "event_timestamp": "2026-06-10T10:00:00+05:30",
            "event_type": "CLOSE",
            "trade_id": fresh_entry_close_trade_id,
            "strategy_id": "S23:BEAR_PUT",
            "strategy_code": "S23",
            "strategy_branch": "BEAR_PUT",
            "symbol": "NIFTY",
            "option_type": "PUT",
            "selected_contract_symbol": "NIFTY_20260602_23825_PE",
            "expiry_date": "2026-06-02",
            "side": "SELL",
            "lots": 1,
            "quantity": 65,
            "entry_date": "2026-06-10",
            "entry_timestamp": "2026-06-10T09:30:00+05:30",
            "entry_price": 194.25,
            "exit_price": 77.70,
            "exit_timestamp": "2026-06-10T10:00:00+05:30",
            "target_price": 77.70,
            "stoploss_price": 242.0,
            "gross_points": 116.55,
            "gross_pnl": 7575.75,
            "session_date": "2026-06-10",
            "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
            "manager_status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED",
            "reason_code": "target_hit",
            "message": "Selected-contract quote proved target hit. The paper position was closed; a fresh S23 position must be recalculated from current market data before any new entry.",
            "fresh_entry_required": True,
            "state_directory": str(final_dir),
        }
    )
    (final_dir / "paper_trade_ledger.jsonl").write_text(
        "\n".join(json.dumps(row) for row in trade_rows) + "\n",
        encoding="utf-8",
    )
    (final_dir / "selected_contract_market_events.jsonl").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "event_kind": "selected_contract_quote",
                "observed_at": "2026-06-10T09:31:01+05:30",
                "watcher_pid": 4321,
                "symbol": "NIFTY_20260602_23800_PE",
                "payload": {
                    "ltp": 188.5,
                    "bid": 188.0,
                    "ask": 189.0,
                    "envelope": {
                        "source_id": "fixture_quote_feed",
                        "source_type": "quote",
                        "effective_timestamp": "2026-06-10T09:31:01+05:30",
                    },
                },
            }
        )
        + "\n",
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
    (pending_dir / "selected_contract_market_events.jsonl").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "event_kind": "selected_contract_quote",
                "observed_at": "2026-06-10T09:31:02+05:30",
                "watcher_pid": 9876,
                "symbol": "NIFTY_20260602_23850_CE",
                "payload": {
                    "ltp": 239.0,
                    "bid": 238.5,
                    "ask": 239.5,
                    "envelope": {
                        "source_id": "fixture_order_feed",
                        "source_type": "quote",
                        "effective_timestamp": "2026-06-10T09:31:02+05:30",
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
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
    assert "repeat(auto-fit, minmax(min(520px, 100%), 1fr))" in strategy_html
    assert "leg-explanation-nav" in strategy_html
    assert 'href="#s23-leg-explanation-nifty-op-sell-wk-diff-2d-3d-bear-call"' in strategy_html
    assert 'href="#s23-leg-explanation-nifty-op-sell-wk-diff-2d-3d-bear-put"' in strategy_html
    assert 'id="s23-leg-explanation-nifty-op-sell-wk-diff-2d-3d-bear-call"' in strategy_html
    assert 'id="s23-leg-explanation-nifty-op-sell-wk-diff-2d-3d-bear-put"' in strategy_html
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
    assert "Stream" in strategy_html
    assert "LTP" in strategy_html
    assert "Bid / Ask" in strategy_html
    assert "239" in strategy_html
    assert "238.50 / 239.50" in strategy_html
    assert "selected_contract_market_events.jsonl" in strategy_html
    assert "Events 1" in strategy_html
    assert "PID 4321" in strategy_html
    assert "PID 9876" in strategy_html
    assert "Source fixture_quote_feed" in strategy_html
    assert "Source fixture_order_feed" in strategy_html
    assert "RECORDED" in strategy_html
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
    assert "NIFTY_20260602_23825_PE" in strategy_html
    fresh_entry_close_row = re.search(
        r"NIFTY_20260602_23825_PE.*?</tr>",
        strategy_html,
        flags=re.S,
    )
    assert fresh_entry_close_row is not None
    assert "POSITION_CLOSED" in fresh_entry_close_row.group(0)
    assert "PAPER_FRESH_ENTRY_REQUIRED" not in fresh_entry_close_row.group(0)
    assert "PAPER_POSITION_FRESH_ENTRY_REQUIRED" not in fresh_entry_close_row.group(0)
    assert "Follow-up: fresh entry recalculation required." in fresh_entry_close_row.group(0)
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


def test_dashboard_builds_separate_s21_page_with_generic_explanation(tmp_path: Path) -> None:
    artifact_root = tmp_path / "s21-artifacts"
    day_dir = artifact_root / "2026-07-06"
    final_dir = day_dir / "s21-fyers-morning-supervised-decision-2026-07-06"
    final_dir.mkdir(parents=True)
    (final_dir / "monthly_status_stage_0916.json").write_text(
        json.dumps(
            {
                "monthly_status": {
                    "status": "BEAR",
                    "trigger_name": "BEAR_CONFIRMED",
                    "price_used": 56210.5,
                    "resolution_reason": "Confirmed from captured monthly structure.",
                    "lookback_used": False,
                    "notes": "BankNifty monthly status resolved for paper-mode review.",
                    "trace": [],
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
                    "monthly_status": "BEAR",
                    "selected_contract_symbol": "BANKNIFTY_20260730_56500_CE",
                }
            }
        ),
        encoding="utf-8",
    )
    (final_dir / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")
    branch_dir = final_dir / "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL"
    branch_dir.mkdir()
    (branch_dir / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "status": "READY",
                    "strategy_branch": "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
                    "selected_contract_symbol": "BANKNIFTY_20260730_56500_CE",
                    "selected_contract_option_type": "CALL",
                    "selected_contract_strike": 56500,
                    "selected_contract_ltp": 421.25,
                    "selected_contract_oi": 210000,
                    "planned_entry_price": 260.0,
                    "target_price": 104.0,
                    "stoploss_price": 416.0,
                    "selected_contract_expiry": "2026-07-30",
                },
                "explanation": {
                    "selection_reason": "Selected first strike meeting ideal premium in near monthly contract order.",
                    "entry_formula": "OPT_PRV_2DLL - 7.5%",
                    "target_formula": "entry - 60%",
                    "stoploss_formula": "MIN(entry + 60%, OPT_PRV_2DLL + 5%)",
                    "monthly": {
                        "status": "BEAR",
                        "trigger_name": "BEAR_CONFIRMED",
                        "current_price": 56210.5,
                        "resolution_reason": "Confirmed from captured monthly structure.",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (branch_dir / "paper_order_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S21",
                "strategy_branch": "S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
                "selected_contract_symbol": "BANKNIFTY_20260730_56500_CE",
                "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
                "order_timestamp": "2026-07-06T09:30:00+05:30",
                "last_updated_timestamp": "2026-07-06T09:31:00+05:30",
            }
        ),
        encoding="utf-8",
    )

    result = TfisOperatorDashboardBuilder(
        strategy_configs=(
            _strategy_config(tmp_path / "unused-s23"),
            _s21_strategy_config(artifact_root),
        )
    ).build(output_root=tmp_path / "dashboard")

    index_html = result.index_html.read_text(encoding="utf-8")
    s21_html = result.strategy_pages["S21"].read_text(encoding="utf-8")

    assert "S21 Operator Dashboard" in index_html
    assert "strategies/S21/index.html" in index_html
    assert "Final S21 Leg Decisions" in s21_html
    assert "BANKNIFTY_20260730_56500_CE" in s21_html
    assert "Strategy-specific decision audit" in s21_html
    assert "bullish S23 group" not in s21_html


def test_dashboard_builds_consolidated_trades_page(tmp_path: Path) -> None:
    s23_root = tmp_path / "s23-artifacts"
    s23_day_dir = s23_root / "2026-07-07"
    s23_final_dir = s23_day_dir / "s23-fyers-morning-supervised-decision-2026-07-07"
    s23_branch_dir = s23_final_dir / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    s23_branch_dir.mkdir(parents=True)
    (s23_final_dir / "trade_decision_summary.json").write_text(
        json.dumps({"summary": {"status": "READY", "monthly_status": "BEAR"}}),
        encoding="utf-8",
    )
    (s23_final_dir / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")
    (s23_branch_dir / "paper_order_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "strategy_branch": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
                "selected_contract_symbol": "NIFTY_20260714_24150_CE",
                "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
                "entry_date": "2026-07-07",
                "order_timestamp": "2026-07-07T09:30:00+05:30",
                "last_updated_timestamp": "2026-07-07T09:31:00+05:30",
                "planned_entry_price": 194.25,
            }
        ),
        encoding="utf-8",
    )

    s21_root = tmp_path / "s21-artifacts"
    s21_day_dir = s21_root / "2026-07-06"
    s21_final_dir = s21_day_dir / "s21-fyers-morning-supervised-decision-2026-07-06"
    s21_branch_dir = s21_final_dir / "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL"
    s21_branch_dir.mkdir(parents=True)
    (s21_final_dir / "trade_decision_summary.json").write_text(
        json.dumps({"summary": {"status": "NO_GO", "monthly_status": "BULL_CF"}}),
        encoding="utf-8",
    )
    (s21_final_dir / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")
    (s21_branch_dir / "paper_order_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S21",
                "strategy_branch": "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
                "selected_contract_symbol": "BANKNIFTY_20260728_57800_CE",
                "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
                "entry_date": "2026-07-06",
                "order_timestamp": "2026-07-06T09:30:00+05:30",
                "last_updated_timestamp": "2026-07-08T12:46:03+05:30",
                "planned_entry_price": 462.50,
            }
        ),
        encoding="utf-8",
    )

    result = TfisOperatorDashboardBuilder(
        strategy_configs=(
            _strategy_config(s23_root),
            _s21_strategy_config(s21_root),
        )
    ).build(output_root=tmp_path / "dashboard")

    index_html = result.index_html.read_text(encoding="utf-8")
    trades_html = result.trades_page.read_text(encoding="utf-8")

    assert "All Trades Monitor" in index_html
    assert 'href="trades/index.html"' in index_html
    assert "All Strategy Trades" in trades_html
    assert "S23" in trades_html
    assert "S21" in trades_html
    assert "NIFTY_20260714_24150_CE" in trades_html
    assert "BANKNIFTY_20260728_57800_CE" in trades_html


def test_s21_failed_leg_uses_strategy_aware_branch_normalization(tmp_path: Path) -> None:
    artifact_root = tmp_path / "s21-artifacts"
    day_dir = artifact_root / "2026-07-16"
    final_dir = day_dir / "s21-fyers-morning-supervised-decision-2026-07-16"
    final_dir.mkdir(parents=True)
    (final_dir / "trade_decision_summary.json").write_text(
        json.dumps({"summary": {"status": "READY", "monthly_status": "BULL"}}),
        encoding="utf-8",
    )
    (final_dir / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")

    selected_branch_dir = final_dir / "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL"
    selected_branch_dir.mkdir()
    (selected_branch_dir / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "status": "READY",
                    "strategy_branch": "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
                    "selected_contract_symbol": "BANKNIFTY_20260730_57800_CE",
                    "selected_contract_option_type": "CALL",
                    "selected_contract_strike": 57800,
                    "selected_contract_ltp": 980.0,
                    "selected_contract_oi": 210000,
                    "planned_entry_price": 462.50,
                    "target_price": 185.0,
                    "stoploss_price": 740.0,
                    "selected_contract_expiry": "2026-07-30",
                }
            }
        ),
        encoding="utf-8",
    )
    (selected_branch_dir / "paper_order_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S21",
                "strategy_branch": "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
                "selected_contract_symbol": "BANKNIFTY_20260730_57800_CE",
                "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
                "entry_date": "2026-07-16",
                "order_timestamp": "2026-07-16T09:30:00+05:30",
                "last_updated_timestamp": "2026-07-16T09:31:00+05:30",
            }
        ),
        encoding="utf-8",
    )

    failed_branch_dir = final_dir / "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT"
    failed_branch_dir.mkdir()
    (failed_branch_dir / "trade_decision_explainer.json").write_text(
        json.dumps(
            {
                "stage": {
                    "can_finalize_trade_decision": True,
                    "strategy_branch": "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
                    "monthly_status": "BULL",
                    "decision_failure_code": "MINIMUM_PREMIUM_NOT_MET",
                    "decision_failure_message": "Near monthly contracts did not satisfy minimum premium.",
                    "decision_failure_attempted_expiries": ["2026-07-30", "2026-08-27"],
                    "decision_failure_rejected_counts": {
                        "minimum_premium_not_met": 4,
                    },
                    "provisional_trade_decision_summary": {
                        "selected_contract_option_type": "PUT",
                        "planned_entry_price": 444.0,
                        "target_price": 177.6,
                        "stoploss_price": 710.4,
                    },
                    "formula_evaluation": [
                        {
                            "name": "entry",
                            "resolved_formula": "OPT_PRV_2DLL - 7.5%",
                            "result": 444.0,
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    result = TfisOperatorDashboardBuilder(
        strategy_configs=(
            _strategy_config(tmp_path / "unused-s23"),
            _s21_strategy_config(artifact_root),
        )
    ).build(output_root=tmp_path / "dashboard")

    s21_html = result.strategy_pages["S21"].read_text(encoding="utf-8")

    assert "BANKNIFTY_20260730_57800_CE" in s21_html
    assert "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT" in s21_html
    assert "MINIMUM_PREMIUM_NOT_MET" in s21_html
    assert "Near monthly contracts did not satisfy minimum premium." in s21_html
    failed_put_row = re.search(
        r"BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT.*?No contract selected.*?MINIMUM_PREMIUM_NOT_MET",
        s21_html,
        flags=re.S,
    )
    assert failed_put_row is not None


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


def test_dashboard_builder_caches_jsonl_reads_within_one_build_session(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True)
    builder = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(artifact_root),))
    jsonl_path = artifact_root / "sample.jsonl"
    jsonl_path.write_text('{"event_type":"HOLD","trade_id":"T1"}\n', encoding="utf-8")

    first_rows = builder._iter_jsonl_dicts(jsonl_path)
    jsonl_path.write_text('{"event_type":"CLOSE","trade_id":"T2"}\n', encoding="utf-8")
    second_rows = builder._iter_jsonl_dicts(jsonl_path)

    assert first_rows == second_rows
    assert second_rows[0]["trade_id"] == "T1"


def test_historical_trade_collection_skips_stream_health_scans(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    session_dir = artifact_root / "2026-07-15" / "s23-fyers-morning-supervised-decision-2026-07-15" / "LEG"
    session_dir.mkdir(parents=True)
    (session_dir / "paper_position_state.json").write_text(
        json.dumps({"lifecycle_status": "PAPER_POSITION_CLOSED"}),
        encoding="utf-8",
    )
    (session_dir / "paper_trade_ledger.jsonl").write_text(
        json.dumps(
            {
                "event_timestamp": "2026-07-15T12:57:59+05:30",
                "entry_timestamp": "2026-07-08T12:24:59+05:30",
                "exit_timestamp": "2026-07-15T12:57:59+05:30",
                "event_type": "CLOSE",
                "trade_id": "S23-LEG-NIFTY_20260721_24200_CE-20260708T122459",
                "strategy_id": "S23:LEG",
                "strategy_code": "S23",
                "strategy_branch": "LEG",
                "selected_contract_symbol": "NIFTY_20260721_24200_CE",
                "side": "SELL",
                "lots": 1,
                "quantity": 65,
                "entry_price": 209.0,
                "exit_price": 86.10,
                "target_price": 85.10,
                "stoploss_price": 258.94,
                "gross_points": 122.90,
                "gross_pnl": 7988.50,
                "lifecycle_status": "PAPER_POSITION_CLOSED",
                "manager_status": "PAPER_POSITION_CLOSED",
                "reason_code": "target_hit",
                "message": "Closed on target.",
                "state_directory": str(session_dir),
                "session_date": "2026-07-15",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    builder = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(artifact_root),))

    def fail_stream_health(*_args, **_kwargs):
        raise AssertionError("historical trade collection should not scan stream health")

    builder._selected_contract_stream_health = fail_stream_health  # type: ignore[method-assign]

    rows = builder._collect_historical_trade_rows([(_strategy_config(artifact_root), [])])

    assert len(rows) == 1
    assert rows[0].trade_id == "S23-LEG-NIFTY_20260721_24200_CE-20260708T122459"


def test_trade_row_tone_class_uses_shared_trade_status_kind(tmp_path: Path) -> None:
    builder = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(tmp_path / "artifacts"),))

    def row(
        *,
        event_type: str,
        lifecycle_status: str,
        manager_status: str,
        fresh_entry_required: bool = False,
    ) -> DashboardTradeLedgerRow:
        timestamp = datetime(2026, 7, 15, 12, 0, tzinfo=IST)
        return DashboardTradeLedgerRow(
            session_date=timestamp.date(),
            event_timestamp=timestamp,
            entry_timestamp=timestamp,
            exit_timestamp=timestamp if event_type == "CLOSE" else None,
            event_type=event_type,
            trade_id="T1",
            strategy_id="S23:LEG",
            strategy_code="S23",
            strategy_branch="LEG",
            selected_contract_symbol="NIFTY_20260721_24200_CE",
            side="SELL",
            lots=1,
            quantity=65,
            entry_price=209.0,
            current_price=180.0,
            current_bid=179.5,
            current_ask=180.5,
            exit_price=86.1 if event_type == "CLOSE" else None,
            target_price=85.1,
            stoploss_price=258.94,
            gross_points=122.9,
            gross_pnl=7988.5,
            lifecycle_status=lifecycle_status,
            manager_status=manager_status,
            reason_code="reason",
            message="message",
            fresh_entry_required=fresh_entry_required,
            reverse_entry_required=False,
            rollover_required=False,
            state_directory=None,
            stream_health=DashboardSelectedContractStreamHealth(),
            raw_artifact_links={},
        )

    assert builder._trade_row_tone_class(
        row(
            event_type="CLOSE",
            lifecycle_status="PAPER_POSITION_CLOSED",
            manager_status="PAPER_POSITION_CLOSED",
        )
    ) == "trade-row-closed"
    assert builder._trade_row_tone_class(
        row(
            event_type="HOLD",
            lifecycle_status="PAPER_FRESH_ENTRY_REQUIRED",
            manager_status="PAPER_POSITION_FRESH_ENTRY_REQUIRED",
            fresh_entry_required=True,
        )
    ) == "trade-row-action"
    assert builder._trade_row_tone_class(
        row(
            event_type="OPEN",
            lifecycle_status="ORDER_NOT_FILLED",
            manager_status="PAPER_ORDER_NOT_FILLED",
        )
    ) == "trade-row-not-filled"
    assert builder._trade_row_tone_class(
        row(
            event_type="OPEN",
            lifecycle_status="ORDER_WAITING_FOR_TRIGGER",
            manager_status="PAPER_ORDER_WAITING_FOR_TRIGGER",
        )
    ) == "trade-row-waiting"
    assert builder._trade_row_tone_class(
        row(
            event_type="HOLD",
            lifecycle_status="PAPER_POSITION_OPEN",
            manager_status="PAPER_POSITION_HELD",
        )
    ) == "trade-row-open"


def test_trade_visible_for_latest_session_uses_shared_visibility_rule(tmp_path: Path) -> None:
    builder = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(tmp_path / "artifacts"),))
    latest_session_date = datetime(2026, 7, 15, 9, 30, tzinfo=IST).date()
    timestamp = datetime(2026, 7, 14, 12, 0, tzinfo=IST)

    row = DashboardTradeLedgerRow(
        session_date=timestamp.date(),
        event_timestamp=timestamp,
        entry_timestamp=timestamp,
        exit_timestamp=timestamp,
        event_type="CLOSE",
        trade_id="T1",
        strategy_id="S23:LEG",
        strategy_code="S23",
        strategy_branch="LEG",
        selected_contract_symbol="NIFTY_20260721_24200_CE",
        side="SELL",
        lots=1,
        quantity=65,
        entry_price=209.0,
        current_price=180.0,
        current_bid=179.5,
        current_ask=180.5,
        exit_price=86.1,
        target_price=85.1,
        stoploss_price=258.94,
        gross_points=122.9,
        gross_pnl=7988.5,
        lifecycle_status="PAPER_POSITION_CLOSED",
        manager_status="PAPER_POSITION_CLOSED",
        reason_code="reason",
        message="message",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
        state_directory=None,
        stream_health=DashboardSelectedContractStreamHealth(),
        raw_artifact_links={},
    )

    assert builder._trade_visible_for_latest_session(
        row,
        latest_session_date=latest_session_date,
    ) is False


def test_display_row_for_trade_prefers_terminal_row_over_later_action(tmp_path: Path) -> None:
    builder = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(tmp_path / "artifacts"),))
    open_timestamp = datetime(2026, 7, 15, 9, 30, tzinfo=IST)
    close_timestamp = datetime(2026, 7, 15, 12, 57, 59, tzinfo=IST)
    later_action_timestamp = datetime(2026, 7, 16, 9, 30, tzinfo=IST)

    def row(
        *,
        event_timestamp: datetime,
        event_type: str,
        lifecycle_status: str,
        manager_status: str,
    ) -> DashboardTradeLedgerRow:
        return DashboardTradeLedgerRow(
            session_date=event_timestamp.date(),
            event_timestamp=event_timestamp,
            entry_timestamp=open_timestamp,
            exit_timestamp=event_timestamp if event_type == "CLOSE" else None,
            event_type=event_type,
            trade_id="T1",
            strategy_id="S23:LEG",
            strategy_code="S23",
            strategy_branch="LEG",
            selected_contract_symbol="NIFTY_20260721_24200_CE",
            side="SELL",
            lots=1,
            quantity=65,
            entry_price=209.0,
            current_price=180.0,
            current_bid=179.5,
            current_ask=180.5,
            exit_price=86.1 if event_type == "CLOSE" else None,
            target_price=85.1,
            stoploss_price=258.94,
            gross_points=122.9,
            gross_pnl=7988.5,
            lifecycle_status=lifecycle_status,
            manager_status=manager_status,
            reason_code="reason",
            message="message",
            fresh_entry_required=False,
            reverse_entry_required=False,
            rollover_required=manager_status == "PAPER_POSITION_ROLLOVER_REQUIRED",
            state_directory=None,
            stream_health=DashboardSelectedContractStreamHealth(),
            raw_artifact_links={},
        )

    display_row = builder._display_row_for_trade(
        [
            row(
                event_timestamp=open_timestamp,
                event_type="OPEN",
                lifecycle_status="PAPER_POSITION_OPEN",
                manager_status="PAPER_POSITION_OPENED",
            ),
            row(
                event_timestamp=close_timestamp,
                event_type="CLOSE",
                lifecycle_status="PAPER_POSITION_CLOSED",
                manager_status="PAPER_POSITION_CLOSED",
            ),
            row(
                event_timestamp=later_action_timestamp,
                event_type="ACTION_REQUIRED",
                lifecycle_status="PAPER_ROLLOVER_REQUIRED",
                manager_status="PAPER_POSITION_ROLLOVER_REQUIRED",
            ),
        ]
    )

    assert display_row.event_type == "CLOSE"
    assert display_row.event_timestamp == close_timestamp


def test_trade_ledger_section_summary_uses_shared_trade_counts(tmp_path: Path) -> None:
    builder = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(tmp_path / "artifacts"),))
    timestamp = datetime(2026, 7, 15, 9, 30, tzinfo=IST)

    def row(
        *,
        trade_id: str,
        event_type: str,
        lifecycle_status: str,
        manager_status: str,
        fresh_entry_required: bool = False,
    ) -> DashboardTradeLedgerRow:
        return DashboardTradeLedgerRow(
            session_date=timestamp.date(),
            event_timestamp=timestamp,
            entry_timestamp=timestamp,
            exit_timestamp=timestamp if event_type == "CLOSE" else None,
            event_type=event_type,
            trade_id=trade_id,
            strategy_id="S23:LEG",
            strategy_code="S23",
            strategy_branch="LEG",
            selected_contract_symbol=f"NIFTY_{trade_id}",
            side="SELL",
            lots=1,
            quantity=65,
            entry_price=209.0,
            current_price=180.0,
            current_bid=179.5,
            current_ask=180.5,
            exit_price=86.1 if event_type == "CLOSE" else None,
            target_price=85.1,
            stoploss_price=258.94,
            gross_points=122.9,
            gross_pnl=7988.5,
            lifecycle_status=lifecycle_status,
            manager_status=manager_status,
            reason_code="reason",
            message="message",
            fresh_entry_required=fresh_entry_required,
            reverse_entry_required=False,
            rollover_required=False,
            state_directory=None,
            stream_health=DashboardSelectedContractStreamHealth(),
            raw_artifact_links={},
        )

    html = builder._render_trade_ledger_section(
        rows=[
            row(
                trade_id="OPEN1",
                event_type="HOLD",
                lifecycle_status="PAPER_POSITION_OPEN",
                manager_status="PAPER_POSITION_HELD",
            ),
            row(
                trade_id="ACTION1",
                event_type="ACTION_REQUIRED",
                lifecycle_status="PAPER_FRESH_ENTRY_REQUIRED",
                manager_status="PAPER_POSITION_FRESH_ENTRY_REQUIRED",
                fresh_entry_required=True,
            ),
            row(
                trade_id="CLOSED1",
                event_type="CLOSE",
                lifecycle_status="PAPER_POSITION_CLOSED",
                manager_status="PAPER_POSITION_CLOSED",
            ),
        ],
        page_path=tmp_path / "dashboard" / "trades" / "index.html",
        latest_session_date=timestamp.date(),
    )

    assert ">3<" in html
    assert re.search(r"Open Positions</span><div class=\"value\">1</div>", html)
    assert re.search(r"Action Required</span><div class=\"value\">1</div>", html)
    assert re.search(r"Closed Trades</span><div class=\"value\">1</div>", html)


def test_strategy_page_prefers_current_position_truth_over_stale_carry_forward_block(tmp_path: Path) -> None:
    artifact_root = tmp_path / "s23-artifacts"
    latest_day_dir = artifact_root / "2026-07-14"
    latest_final_dir = latest_day_dir / "s23-fyers-morning-supervised-decision-2026-07-14"
    latest_final_dir.mkdir(parents=True)
    (latest_final_dir / "monthly_status_stage_0916.json").write_text(
        json.dumps({"monthly_status": {"status": "BULL", "trigger_name": "BULLISH"}}),
        encoding="utf-8",
    )
    (latest_final_dir / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "status": "IN_PROGRESS",
                    "monthly_status": "BULL",
                    "selected_contract_symbol": "NIFTY_20260721_23950_CE",
                }
            }
        ),
        encoding="utf-8",
    )
    (latest_final_dir / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")
    branch_dir = latest_final_dir / "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    branch_dir.mkdir()
    (branch_dir / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "status": "READY",
                    "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
                    "selected_contract_symbol": "NIFTY_20260721_23950_CE",
                    "selected_contract_option_type": "CALL",
                    "selected_contract_expiry": "2026-07-21",
                    "selected_contract_strike": 23950,
                    "selected_contract_ltp": 304.95,
                    "selected_contract_oi": 50700,
                    "planned_entry_price": 212.75,
                    "target_price": 85.10,
                    "stoploss_price": 258.94,
                    "order_placement_blocked": True,
                    "order_placement_block_reason": "OPEN_CARRY_FORWARD_POSITION",
                }
            }
        ),
        encoding="utf-8",
    )

    carried_trade_dir = (
        artifact_root
        / "2026-07-08"
        / "s23-fyers-morning-supervised-decision-2026-07-08"
        / "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    )
    carried_trade_dir.mkdir(parents=True)
    (carried_trade_dir / "paper_position_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "symbol": "NIFTY",
                "option_type": "CALL",
                "selected_contract_symbol": "NIFTY_20260721_24200_CE",
                "expiry_date": "2026-07-21",
                "expiry_type": "WEEKLY",
                "entry_date": "2026-07-08",
                "entry_timestamp": "2026-07-08T12:24:59+05:30",
                "entry_price": 209.0,
                "lots": 1,
                "quantity": 65,
                "side": "SELL",
                "target_price": 85.10,
                "stoploss_price": 258.94,
                "fsl_price": None,
                "trp_price": None,
                "carry_forward_allowed": False,
                "no_carry_past_expiry": True,
                "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
                "last_updated_timestamp": "2026-07-15T12:57:59+05:30",
                "provenance_source_ids": ["paper_order_state.json", "s23_paper_position_watch"],
            }
        ),
        encoding="utf-8",
    )

    result = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(artifact_root),)).build(
        output_root=tmp_path / "dashboard"
    )

    strategy_html = result.strategy_pages["S23"].read_text(encoding="utf-8")
    assert "PAPER_FRESH_ENTRY_REQUIRED" in strategy_html
    assert "OPEN_CARRY_FORWARD_POSITION" not in strategy_html


def test_latest_strategy_position_override_status_returns_none_for_active_carried_forward_state(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "s23-artifacts"
    state_dir = (
        artifact_root
        / "2026-07-15"
        / "s23-fyers-morning-supervised-decision-2026-07-15"
        / "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    )
    state_dir.mkdir(parents=True)
    (state_dir / "paper_position_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "lifecycle_status": "PAPER_POSITION_CARRIED_FORWARD",
                "last_updated_timestamp": "2026-07-15T15:00:00+05:30",
            }
        ),
        encoding="utf-8",
    )

    builder = TfisOperatorDashboardBuilder(strategy_configs=(_strategy_config(artifact_root),))

    assert builder._latest_strategy_position_override_status(_strategy_config(artifact_root)) is None


def test_dashboard_builds_historical_trades_page_with_filters(tmp_path: Path) -> None:
    s23_root = tmp_path / "s23-artifacts"
    s21_root = tmp_path / "s21-artifacts"

    s23_session = s23_root / "2026-07-08" / "s23-fyers-morning-supervised-decision-2026-07-08" / "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    s23_session.mkdir(parents=True)
    (s23_session / "paper_position_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "symbol": "NIFTY",
                "option_type": "CALL",
                "selected_contract_symbol": "NIFTY_20260721_24200_CE",
                "expiry_date": "2026-07-21",
                "expiry_type": "WEEKLY",
                "entry_date": "2026-07-08",
                "entry_timestamp": "2026-07-08T12:24:59+05:30",
                "entry_price": 209.0,
                "lots": 1,
                "quantity": 65,
                "side": "SELL",
                "target_price": 85.10,
                "stoploss_price": 258.94,
                "fsl_price": None,
                "trp_price": None,
                "carry_forward_allowed": False,
                "no_carry_past_expiry": True,
                "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
                "last_updated_timestamp": "2026-07-15T12:57:59+05:30",
                "provenance_source_ids": ["paper_order_state.json", "s23_paper_position_watch"],
            }
        ),
        encoding="utf-8",
    )
    (s23_session / "paper_trade_ledger.jsonl").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "event_timestamp": "2026-07-15T12:57:59+05:30",
                "entry_timestamp": "2026-07-08T12:24:59+05:30",
                "exit_timestamp": "2026-07-15T12:57:59+05:30",
                "event_type": "CLOSE",
                "trade_id": "S23-NIFTY_OP_SELL_WK_DIFF_2D_3D-NIFTY_20260721_24200_CE-20260708T122459",
                "strategy_id": "S23:NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "strategy_code": "S23",
                "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "selected_contract_symbol": "NIFTY_20260721_24200_CE",
                "side": "SELL",
                "lots": 1,
                "quantity": 65,
                "entry_price": 209.0,
                "exit_price": 86.10,
                "target_price": 85.10,
                "stoploss_price": 258.94,
                "gross_points": 122.9,
                "gross_pnl": 7988.5,
                "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
                "manager_status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED",
                "reason_code": "target_hit",
                "message": "Selected-contract bar proved target hit.",
                "fresh_entry_required": True,
                "reverse_entry_required": False,
                "rollover_required": False,
                "state_directory": str(s23_session),
                "session_date": "2026-07-15",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    s21_session = s21_root / "2026-07-09" / "s21-fyers-morning-supervised-decision-2026-07-09" / "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL"
    s21_session.mkdir(parents=True)
    (s21_session / "paper_position_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S21",
                "unique_code": "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
                "symbol": "BANKNIFTY",
                "option_type": "CALL",
                "selected_contract_symbol": "BANKNIFTY_20260728_57200_CE",
                "expiry_date": "2026-07-28",
                "expiry_type": "MONTHLY",
                "entry_date": "2026-07-09",
                "entry_timestamp": "2026-07-09T10:15:00+05:30",
                "entry_price": 462.5,
                "lots": 1,
                "quantity": 35,
                "side": "SELL",
                "target_price": 185.0,
                "stoploss_price": 740.0,
                "fsl_price": None,
                "trp_price": None,
                "carry_forward_allowed": False,
                "no_carry_past_expiry": True,
                "lifecycle_status": "PAPER_POSITION_CLOSED",
                "last_updated_timestamp": "2026-07-09T14:45:00+05:30",
                "provenance_source_ids": ["paper_order_state.json", "paper_position_watch"],
            }
        ),
        encoding="utf-8",
    )
    (s21_session / "paper_trade_ledger.jsonl").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "event_timestamp": "2026-07-09T14:45:00+05:30",
                "entry_timestamp": "2026-07-09T10:15:00+05:30",
                "exit_timestamp": "2026-07-09T14:45:00+05:30",
                "event_type": "CLOSE",
                "trade_id": "S21-BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL-BANKNIFTY_20260728_57200_CE-20260709T101500",
                "strategy_id": "S21:BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
                "strategy_code": "S21",
                "strategy_branch": "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
                "selected_contract_symbol": "BANKNIFTY_20260728_57200_CE",
                "side": "SELL",
                "lots": 1,
                "quantity": 35,
                "entry_price": 462.5,
                "exit_price": 220.0,
                "target_price": 185.0,
                "stoploss_price": 740.0,
                "gross_points": 242.5,
                "gross_pnl": 8487.5,
                "lifecycle_status": "PAPER_POSITION_CLOSED",
                "manager_status": "PAPER_POSITION_FORCE_CLOSED",
                "reason_code": "forced_close",
                "message": "Session close forced the paper exit.",
                "fresh_entry_required": False,
                "reverse_entry_required": False,
                "rollover_required": False,
                "state_directory": str(s21_session),
                "session_date": "2026-07-09",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = TfisOperatorDashboardBuilder(
        strategy_configs=(
            _strategy_config(s23_root),
            _s21_strategy_config(s21_root),
        )
    ).build(output_root=tmp_path / "dashboard")

    index_html = result.index_html.read_text(encoding="utf-8")
    trades_html = result.trades_page.read_text(encoding="utf-8")
    history_html = result.historical_trades_page.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))

    assert 'href="trades/history/index.html"' in index_html
    assert 'href="history/index.html"' in trades_html
    assert "Historical Trades" in history_html
    assert "historicalStrategyFilter" in history_html
    assert "historicalRangePreset" in history_html
    assert "Current Year" in history_html
    assert "Date Range" in history_html
    assert "NIFTY_20260721_24200_CE" in history_html
    assert "BANKNIFTY_20260728_57200_CE" in history_html
    assert manifest["historical_trades_page"].replace("\\", "/") == "trades/history/index.html"


def test_all_trades_monitor_keeps_terminal_close_after_latest_session_date(tmp_path: Path) -> None:
    s23_root = tmp_path / "s23-artifacts"
    latest_day = s23_root / "2026-07-14"
    latest_final = latest_day / "s23-fyers-morning-supervised-decision-2026-07-14"
    latest_final.mkdir(parents=True)
    (latest_final / "monthly_status_stage_0916.json").write_text(
        json.dumps({"monthly_status": {"status": "BULL", "trigger_name": "BULLISH"}}),
        encoding="utf-8",
    )
    (latest_final / "trade_decision_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "status": "IN_PROGRESS",
                    "monthly_status": "BULL",
                    "selected_contract_symbol": "NIFTY_20260721_23950_CE",
                }
            }
        ),
        encoding="utf-8",
    )
    (latest_final / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")

    trade_dir = (
        s23_root
        / "2026-07-08"
        / "s23-fyers-morning-supervised-decision-2026-07-08"
        / "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    )
    trade_dir.mkdir(parents=True)
    (trade_dir / "paper_position_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "symbol": "NIFTY",
                "option_type": "CALL",
                "selected_contract_symbol": "NIFTY_20260721_24200_CE",
                "expiry_date": "2026-07-21",
                "expiry_type": "WEEKLY",
                "entry_date": "2026-07-08",
                "entry_timestamp": "2026-07-08T12:24:59+05:30",
                "entry_price": 209.0,
                "lots": 1,
                "quantity": 65,
                "side": "SELL",
                "target_price": 85.10,
                "stoploss_price": 258.94,
                "fsl_price": None,
                "trp_price": None,
                "carry_forward_allowed": False,
                "no_carry_past_expiry": True,
                "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
                "last_updated_timestamp": "2026-07-15T12:57:59+05:30",
                "provenance_source_ids": ["paper_order_state.json", "s23_paper_position_watch"],
            }
        ),
        encoding="utf-8",
    )
    (trade_dir / "paper_trade_ledger.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "artifact_version": 1,
                        "event_timestamp": "2026-07-14T15:35:26+05:30",
                        "entry_timestamp": "2026-07-08T12:24:59+05:30",
                        "event_type": "HOLD",
                        "trade_id": "S23-NIFTY_OP_SELL_WK_DIFF_2D_3D-NIFTY_20260721_24200_CE-20260708T122459",
                        "strategy_id": "S23:NIFTY_OP_SELL_WK_DIFF_2D_3D",
                        "strategy_code": "S23",
                        "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
                        "selected_contract_symbol": "NIFTY_20260721_24200_CE",
                        "side": "SELL",
                        "lots": 1,
                        "quantity": 65,
                        "entry_price": 209.0,
                        "target_price": 85.10,
                        "stoploss_price": 258.94,
                        "gross_points": 116.95,
                        "gross_pnl": 7601.75,
                        "lifecycle_status": "PAPER_POSITION_CARRIED_FORWARD",
                        "manager_status": "PAPER_POSITION_HELD",
                        "reason_code": "s23_1500_carry_forward_stop_inactive",
                        "message": "Position carried forward.",
                        "fresh_entry_required": False,
                        "reverse_entry_required": False,
                        "rollover_required": False,
                        "state_directory": str(trade_dir),
                        "session_date": "2026-07-14",
                    }
                ),
                json.dumps(
                    {
                        "artifact_version": 1,
                        "event_timestamp": "2026-07-15T12:57:59+05:30",
                        "entry_timestamp": "2026-07-08T12:24:59+05:30",
                        "exit_timestamp": "2026-07-15T12:57:59+05:30",
                        "event_type": "CLOSE",
                        "trade_id": "S23-NIFTY_OP_SELL_WK_DIFF_2D_3D-NIFTY_20260721_24200_CE-20260708T122459",
                        "strategy_id": "S23:NIFTY_OP_SELL_WK_DIFF_2D_3D",
                        "strategy_code": "S23",
                        "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
                        "selected_contract_symbol": "NIFTY_20260721_24200_CE",
                        "side": "SELL",
                        "lots": 1,
                        "quantity": 65,
                        "entry_price": 209.0,
                        "exit_price": 86.10,
                        "target_price": 85.10,
                        "stoploss_price": 258.94,
                        "gross_points": 122.9,
                        "gross_pnl": 7988.5,
                        "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
                        "manager_status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED",
                        "reason_code": "target_hit",
                        "message": "Selected-contract bar proved target hit.",
                        "fresh_entry_required": True,
                        "reverse_entry_required": False,
                        "rollover_required": False,
                        "state_directory": str(trade_dir),
                        "session_date": "2026-07-15",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = TfisOperatorDashboardBuilder(
        strategy_configs=(_strategy_config(s23_root),)
    ).build(output_root=tmp_path / "dashboard")

    trades_html = result.trades_page.read_text(encoding="utf-8")
    assert "NIFTY_20260721_24200_CE" in trades_html
    assert "POSITION_CLOSED" in trades_html
    assert "2026-07-15 12:57:59+05:30" in trades_html
    assert "Closed Trades" in trades_html
    assert ">1<" in trades_html
    assert "trade-row-closed" in trades_html
    assert "badge-position_closed" in trades_html


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
