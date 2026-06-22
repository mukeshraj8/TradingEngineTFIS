from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
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
    final_dir = day_dir / "s23-fyers-morning-supervised-decision-2026-06-10"
    stage_dir.mkdir(parents=True)
    final_dir.mkdir(parents=True)
    (stage_dir / "snapshot_preflight_summary.json").write_text(
        json.dumps(
            {
                "preflight_status": "READY",
                "option_chain_contract_count": 42,
                "option_chain_has_complete_oi": True,
            }
        ),
        encoding="utf-8",
    )
    for filename in ("normalized_underlying_bars.json", "normalized_option_chain_snapshot.json"):
        (stage_dir / filename).write_text("{}", encoding="utf-8")
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
    assert "NIFTY_20260602_23800_PE" in strategy_html
    assert "Monthly Status Calculator" in index_html
    assert "Monthly Status Calculator" in strategy_html
    assert "CalculateStrikes" in manual_calculator_html
    assert "Review Date" in manual_calculator_html
    assert "Fetch Captured Premium/OI" in manual_calculator_html
    assert "Eligible CE Strikes" in manual_calculator_html
    assert "Eligible PE Strikes" in manual_calculator_html
    assert "<th>Side</th><th>Trade</th>" in manual_calculator_html
    assert "CE final calculation" in manual_calculator_html
    assert "PE final calculation" in manual_calculator_html
    assert "GetMonthlyStatus" in monthly_calculator_html
    assert "Fetch Captured Monthly Data" in monthly_calculator_html
    assert "PMH" in monthly_calculator_html
    assert "CWH" in monthly_calculator_html
    assert manifest["strategies"][0]["sessions"][0]["final_decision_status"] == "READY"
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
