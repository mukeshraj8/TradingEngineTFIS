from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from tfis.domain.enums import ExpiryType, OptionType, RolloverPolicy
from tfis.paper import (
    PaperSessionState,
    S23GeneratedPreludeDryRunError,
    S23GeneratedPreludeDryRunRunner,
    S23PaperIngressReadiness,
    S23PaperPositionStateStore,
)


IST = ZoneInfo("Asia/Kolkata")
BASE_EVENTS = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "s23_archive_ingress_dry_run.jsonl"
)


def _ts(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, minute, second, tzinfo=IST)


def _write_strategy_folder(tmp_path: Path) -> Path:
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "strategy.yaml").write_text(
        yaml.safe_dump(
            {
                "strategy_code": "S23",
                "unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
                "symbol": "NIFTY",
                "segment": "OPTIONS_SELL",
                "expiry_type": "WEEKLY",
                "rollover_policy": "T_MINUS_1",
                "no_carry_past_expiry": True,
                "allowed_monthly_statuses": ["BEAR", "BEAR_CF"],
                "option_type": "PUT",
                "entry_time": "09:24:59",
                "recalculation_time": "09:29:59",
                "minimum_oi": 500,
                "carry_forward_allowed": True,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (strategy_dir / "formulas.yaml").write_text(
        yaml.safe_dump(
            {
                "start_strike_formula": "ROUND_UP(PRV_3DHH - PARAM(strike_buffer_pct)%)",
                "end_strike_formula": "ROUND_UP(PRV_3DHH) + PARAM(strike_step)",
                "ideal_premium_formula": "PRV_3DHH * PARAM(ideal_premium_pct)%",
                "minimum_premium_formula": "PRV_3DHH * PARAM(minimum_premium_pct)%",
                "entry_formula": "OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
                "target_formula": "ENTRY - PARAM(target_pct)%",
                "stoploss_formula": "MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (strategy_dir / "parameters.yaml").write_text(
        yaml.safe_dump(
            {
                "strike_buffer_pct": 1.2,
                "strike_step": 50,
                "ideal_premium_pct": 1.2,
                "minimum_premium_pct": 0.9,
                "entry_discount_pct": 7.5,
                "target_pct": 60,
                "sl_entry_pct": 60,
                "sl_reference_pct": 7,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return strategy_dir


def _write_config(tmp_path: Path, *, selected_contract_symbol: str = "NIFTY_20260512_24900_PE") -> Path:
    config_path = tmp_path / "paper.s23.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "source_mode": "broker_fyers_live_paper_ingress",
                "broker": {
                    "provider": "fyers",
                    "timezone": "Asia/Kolkata",
                    "payload_fixture_path": str(tmp_path / "unused.json"),
                    "capture_stream_events": False,
                },
                "paper": {
                    "strategy_code": "S23",
                    "symbol": "NIFTY",
                    "contract_cycle": "WEEKLY",
                    "mode": "paper",
                    "operator_id": "unit-test-operator",
                    "paper_mode_enabled": True,
                    "same_day_square_off_only": True,
                    "allow_recalculation": False,
                    "allow_current_day_fsl_trp": True,
                    "kill_switch_enabled": True,
                    "session_kill_switch_active": False,
                    "no_live_orders_allowed": True,
                },
                "market": {
                    "underlying_symbol": "NIFTY",
                    "weekly_expiry": "2026-05-12",
                    "selected_contract_symbol": selected_contract_symbol,
                },
                "costs": {
                    "brokerage_per_lot": 20.0,
                    "slippage_entry_points": 1.0,
                    "slippage_exit_points": 1.0,
                    "spread_buffer_policy": "bid_ask_guard",
                    "version_label": "paper-cost-v1",
                },
                "thresholds": {
                    "max_quote_age_seconds": 5.0,
                    "max_timing_drift_seconds": 5.0,
                    "max_stale_events": 0,
                    "max_missing_chains": 0,
                    "required_selected_contract_availability_ratio": 1.0,
                    "max_no_trade_rate": 0.0,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def _write_runtime_fixture(
    tmp_path: Path,
    *,
    session_date: str = "2026-05-08",
    generated_at: str = "2026-05-08T09:30:03+05:30",
    workbook_row_number: int = 186,
    source_workbook_rule: str = "AB6_OS_Z186",
) -> Path:
    payload = {
        "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        "session_date": session_date,
        "timezone": "Asia/Kolkata",
        "generated_at": generated_at,
        "weekly_expiry": "2026-05-12",
        "monthly_status_result": {
            "status": "BEAR",
            "trigger_name": "BEAR_A_THRESHOLD",
            "threshold_value": 22100.0,
            "reversal_dominated": False,
            "notes": "fixture",
        },
        "market_levels": {
            "d2hh": 22500.0,
            "d2ll": 22300.0,
            "d3hh": 25000.0,
            "d3ll": 22200.0,
            "current_day_high": 22462.0,
            "current_day_low": 22395.0,
        },
        "runtime_values": {
            "ENTRY": 799.1,
            "OPT_LEVELS": {
                "OPT_PRV_2DHH": 763.0,
                "OPT_PRV_3DLL": 863.0,
            },
        },
        "snapshots": [
            {
                "snapshot_label": "0915",
                "open": 22410.0,
                "high": 22425.0,
                "low": 22395.0,
                "close": 22420.0,
                "bar_start": "2026-05-08T09:14:00+05:30",
                "bar_end": "2026-05-08T09:15:00+05:30",
                "complete": True,
            },
            {
                "snapshot_label": "ORPT",
                "open": 22420.0,
                "high": 22455.0,
                "low": 22400.0,
                "close": 22448.0,
                "bar_start": "2026-05-08T09:23:59+05:30",
                "bar_end": "2026-05-08T09:24:59+05:30",
                "complete": True,
            },
            {
                "snapshot_label": "RC",
                "open": 22448.0,
                "high": 22462.0,
                "low": 22435.0,
                "close": 22440.0,
                "bar_start": "2026-05-08T09:28:59+05:30",
                "bar_end": "2026-05-08T09:29:59+05:30",
                "complete": True,
            },
        ],
        "lots": 1,
        "quantity": 100,
        "source_workbook_rule": source_workbook_rule,
        "workbook_row_number": workbook_row_number,
        "fsl_price": 816.35,
    }
    path = tmp_path / "runtime_fixture.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_market_events(
    tmp_path: Path,
    *,
    mutate_option_chain=None,
) -> Path:
    lines: list[str] = []
    for raw_line in BASE_EVENTS.read_text(encoding="utf-8").splitlines():
        payload = json.loads(raw_line)
        if payload["event_type"] == "OPTION_CHAIN_SNAPSHOT" and mutate_option_chain is not None:
            payload = mutate_option_chain(payload)
        lines.append(json.dumps(payload, sort_keys=True))
    path = tmp_path / "market_events.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_carry_forward_state_dir(tmp_path: Path) -> Path:
    state_dir = tmp_path / "carry_forward_state"
    state_dir.mkdir()
    store = S23PaperPositionStateStore()
    state = store.create_open_position_state(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        selected_contract_symbol="NIFTY_20260512_25000_PE",
        expiry_date=date(2026, 5, 12),
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=RolloverPolicy.T_MINUS_1,
        forced_close_time=time(15, 15),
        no_carry_past_expiry=True,
        entry_date=date(2026, 5, 7),
        entry_timestamp=_ts(7, 9, 30),
        entry_price=799.1,
        lots=1,
        quantity=100,
        side="SELL",
        target_price=791.85,
        stoploss_price=816.35,
        fsl_price=816.35,
        trp_price=None,
        carry_forward_allowed=True,
        last_updated_timestamp=_ts(7, 15, 20),
        provenance_source_ids=("paper_order_intent.json",),
    )
    store.save_state(state_dir, state)
    return state_dir


def test_generated_fresh_entry_prelude_feeds_existing_dry_run(tmp_path: Path) -> None:
    runner = S23GeneratedPreludeDryRunRunner()
    artifact_set = runner.run_from_files(
        strategy_path=_write_strategy_folder(tmp_path),
        ingress_config_path=_write_config(tmp_path),
        runtime_fixture_path=_write_runtime_fixture(tmp_path),
        market_events_jsonl=_write_market_events(tmp_path),
        session_id="generated-prelude-fresh",
    )

    assert artifact_set.ingress_artifacts.summary.terminal_state is PaperSessionState.ORDER_PLANNED
    assert artifact_set.ingress_artifacts.summary.operational_readiness is S23PaperIngressReadiness.PASS
    provenance = json.loads(artifact_set.provenance_path.read_text(encoding="utf-8"))
    assert provenance["prelude_source"] == "generated_live_prelude"
    assert provenance["contract_selection_source"] == "runtime_option_chain_selector"


def test_generated_carry_forward_prelude_feeds_existing_dry_run(tmp_path: Path) -> None:
    runner = S23GeneratedPreludeDryRunRunner()
    artifact_set = runner.run_from_files(
        strategy_path=_write_strategy_folder(tmp_path),
        ingress_config_path=_write_config(tmp_path),
        runtime_fixture_path=_write_runtime_fixture(tmp_path),
        market_events_jsonl=_write_market_events(tmp_path),
        carry_forward_state_dir=_write_carry_forward_state_dir(tmp_path),
        session_id="generated-prelude-carry-forward",
    )

    assert artifact_set.ingress_artifacts.summary.terminal_state is PaperSessionState.NO_TRADE
    assert "missing_selected_contract_quote" in artifact_set.ingress_artifacts.summary.no_trade_reasons
    assert artifact_set.governance_events_path is not None
    governance_lines = artifact_set.governance_events_path.read_text(encoding="utf-8").splitlines()
    assert any("PAPER_POSITION_RESUMED" in line for line in governance_lines)


def test_missing_option_chain_prevents_dry_run_before_orchestrator_starts(tmp_path: Path) -> None:
    runner = S23GeneratedPreludeDryRunRunner()

    def _drop_chain(payload: dict[str, object]) -> dict[str, object]:
        payload["payload"]["contracts"] = []
        return payload

    with pytest.raises(S23GeneratedPreludeDryRunError):
        runner.run_from_files(
            strategy_path=_write_strategy_folder(tmp_path),
            ingress_config_path=_write_config(tmp_path),
            runtime_fixture_path=_write_runtime_fixture(tmp_path),
            market_events_jsonl=_write_market_events(tmp_path, mutate_option_chain=_drop_chain),
            session_id="generated-prelude-no-chain",
        )


def test_missing_oi_prevents_dry_run_before_orchestrator_starts(tmp_path: Path) -> None:
    runner = S23GeneratedPreludeDryRunRunner()

    def _drop_oi(payload: dict[str, object]) -> dict[str, object]:
        payload["payload"]["contracts"][0]["oi"] = None
        return payload

    with pytest.raises(S23GeneratedPreludeDryRunError):
        runner.run_from_files(
            strategy_path=_write_strategy_folder(tmp_path),
            ingress_config_path=_write_config(tmp_path),
            runtime_fixture_path=_write_runtime_fixture(tmp_path),
            market_events_jsonl=_write_market_events(tmp_path, mutate_option_chain=_drop_oi),
            session_id="generated-prelude-no-oi",
        )


def test_smoke_override_requires_explicit_flag(tmp_path: Path) -> None:
    runner = S23GeneratedPreludeDryRunRunner()

    def _add_override_candidate(payload: dict[str, object]) -> dict[str, object]:
        payload["payload"]["contracts"].append(
                {
                    "symbol": "NIFTY_20260512_24900_PE",
                    "option_type": "PUT",
                    "strike": 24900.0,
                    "expiry": "2026-05-12",
                    "bid": 780.0,
                    "ask": 781.5,
                    "ltp": 260.0,
                    "oi": 1000.0,
                    "volume": 410.0,
                }
            )
        return payload

    strategy_path = _write_strategy_folder(tmp_path)
    config_path = _write_config(tmp_path, selected_contract_symbol="NIFTY_20260512_24900_PE")
    runtime_fixture_path = _write_runtime_fixture(tmp_path)
    market_events_path = _write_market_events(tmp_path, mutate_option_chain=_add_override_candidate)

    normal = runner.run_from_files(
        strategy_path=strategy_path,
        ingress_config_path=config_path,
        runtime_fixture_path=runtime_fixture_path,
        market_events_jsonl=market_events_path,
        session_id="generated-prelude-normal",
    )
    override = runner.run_from_files(
        strategy_path=strategy_path,
        ingress_config_path=config_path,
        runtime_fixture_path=runtime_fixture_path,
        market_events_jsonl=market_events_path,
        session_id="generated-prelude-override",
        enable_smoke_override=True,
    )

    normal_selected = json.loads(
        (normal.ingress_artifacts.session_directory / "selected_contract.json").read_text(
            encoding="utf-8"
        )
    )
    override_selected = json.loads(
        (override.ingress_artifacts.session_directory / "selected_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert normal_selected["symbol"] == "NIFTY_20260512_25000_PE"
    assert override_selected["symbol"] == "NIFTY_20260512_24900_PE"
    assert override.provenance.contract_selection_source == "explicit_smoke_override"


def test_generated_events_preserve_deterministic_ordering(tmp_path: Path) -> None:
    runner = S23GeneratedPreludeDryRunRunner()
    artifact_set = runner.run_from_files(
        strategy_path=_write_strategy_folder(tmp_path),
        ingress_config_path=_write_config(tmp_path),
        runtime_fixture_path=_write_runtime_fixture(tmp_path),
        market_events_jsonl=_write_market_events(tmp_path),
        session_id="generated-prelude-ordering",
    )

    event_types = [
        json.loads(line)["event_type"]
        for line in artifact_set.combined_events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert event_types == [
        "CALENDAR_CONTEXT",
        "MONTHLY_STATUS_INPUT",
        "PAPER_SESSION_CONFIG",
        "COST_SLIPPAGE_SETTINGS",
        "UNDERLYING_SNAPSHOT",
        "UNDERLYING_SNAPSHOT",
        "UNDERLYING_SNAPSHOT",
        "TRADE_PLAN_INPUT",
        "UNDERLYING_QUOTE",
        "OPTION_CHAIN_SNAPSHOT",
        "SELECTED_CONTRACT_QUOTE",
    ]
