from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from tfis.fyers_read_only.models import InstrumentMasterRecord
from tfis.read_models.operations.models import AccountRiskProjection, StrategyInstanceReadModel
from tfis.read_models.operations.projection import _order_row, _position_row
from tfis.read_models.operations.projection import _build_analytics_model
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance, EnabledStrategyRegistry
from tfis.runtime.multi_strategy.supervisor import (
    _account_risk_matrix,
    _live_instance_result,
    _read_symbol_master_cache,
    _write_symbol_master_cache,
)


IST = ZoneInfo("Asia/Calcutta")
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_live_market_internal_paper.py"


def test_symbol_master_cache_round_trip_restores_records(tmp_path: Path) -> None:
    cache_path = tmp_path / "nsefo_symbol_master_cache.json"
    record = InstrumentMasterRecord(
        source_symbol="NSE:NIFTY26AUG24300CE",
        instrument_id="token-1",
        exchange="NSEFO",
        segment="NSEFO",
        instrument_type="OPTION",
        underlying="NIFTY",
        expiry=date(2026, 8, 26),
        strike=Decimal("24300"),
        option_type="CALL",
        lot_size=50,
        tick_size=Decimal("0.05"),
        instrument_token="token-1",
        status="ACTIVE",
        source_row={
            "symbol": "NSE:NIFTY26AUG24300CE",
            "expiry": "2026-08-26",
            "strike": "24300",
            "option_type": "CE",
            "lot_size": "50",
            "tick_size": "0.05",
            "underlying": "NIFTY",
            "segment": "NSEFO",
            "instrument_type": "OPTION",
            "fyToken": "token-1",
        },
        source_version="FYERS_TEST_CACHE",
        downloaded_at=datetime(2026, 8, 5, 8, 45, tzinfo=IST),
        source_hash="hash-1",
    )

    _write_symbol_master_cache(
        cache_path,
        exchange="NSEFO",
        source_version="FYERS_TEST_CACHE",
        downloaded_at=record.downloaded_at,
        records=(record,),
    )

    restored = _read_symbol_master_cache(cache_path)

    assert len(restored) == 1
    assert restored[0].source_symbol == "NSE:NIFTY26AUG24300CE"
    assert restored[0].underlying == "NIFTY"
    assert restored[0].strike == Decimal("24300")
    assert restored[0].option_type == "CALL"


def test_build_analytics_model_uses_runtime_risk_acceptance() -> None:
    read_model = StrategyInstanceReadModel(
        identity={
            "strategy_instance_id": "S21_BANKNIFTY_INTERNAL_PAPER_A",
            "strategy": "S21",
            "instrument": "BANKNIFTY",
            "account": "INTERNAL_PAPER_ACCOUNT_A",
            "margin_limit_pct": 25,
        },
        state={"branch": "BULL_CALL", "runtime_stage": "WAITING_FOR_MARKET"},
        plan={},
        execution={"risk_result": "ACCEPTED"},
        position={"health": "NO_POSITION"},
        accounting={"realized_pnl": "0.00", "unrealized_pnl": "0.00"},
        operations={},
    )
    account = AccountRiskProjection(
        account_reference="INTERNAL_PAPER_ACCOUNT_A",
        display_name="FYERS Read-Only Internal Paper Account",
        status="ACTIVE",
        limits={},
        usage={},
        accepted_instances=("S21_BANKNIFTY_INTERNAL_PAPER_A",),
        rejected_instances=(),
        alerts=(),
    )

    analytics = _build_analytics_model(
        read_models=(read_model,),
        positions=(
            {
                "strategy_instance_id": "S21_BANKNIFTY_INTERNAL_PAPER_A",
                "instrument": "BANKNIFTY",
                "fresh_or_carried": "FRESH",
                "realized_pnl": "0.00",
                "unrealized_pnl": "0.00",
                "health": "NO_POSITION",
                "technical_details": {"eod_action": "OPEN"},
            },
        ),
        account=account,
        blocked=[],
        realized=Decimal("0.00"),
        unrealized=Decimal("0.00"),
    )

    assert analytics["account_risk_matrix"]["S21_BANKNIFTY_INTERNAL_PAPER_A"]["decision"] == "ACCEPTED_INTENT"
    assert analytics["blocked_funnel"] == {"prepared": 1, "blocked": 0, "accepted": 1}


def test_account_risk_matrix_accepts_authoritative_selected_contract_before_market_open() -> None:
    registry = EnabledStrategyRegistry(
        schema_version="tfis.enabled_strategy_instances.v1",
        session_scope={"trading_session_id": "NSE:2026-08-05:LIVE_MARKET_INTERNAL_PAPER"},
        accounts=({"account_reference": "INTERNAL_PAPER_ACCOUNT_A"},),
        risk={"aggregate_option_selling_exposure": 5},
        instances=(
            EnabledStrategyInstance(
                strategy_definition_id="S21_BANKNIFTY_OP_SELL_MONTHLY",
                strategy_version="s21.test.v1",
                strategy_instance_id="S21_BANKNIFTY_INTERNAL_PAPER_A",
                account_reference="INTERNAL_PAPER_ACCOUNT_A",
                underlying={"exchange": "NSE", "symbol": "BANKNIFTY", "instrument_type": "INDEX"},
                product="OPTION_SELLING",
                enabled=True,
                configured_quantity={"lots": 1, "lot_size": 15},
                authority_mode="INTERNAL_PAPER_CONTROLLED",
                market_data_source="FYERS_READ_ONLY",
                rule_config_hash="hash-1",
                risk_allocation={"max_positions": 1, "max_margin_usage_pct": 20},
                operator_approval_status="APPROVED_INTERNAL_PAPER",
                evidence_quality="LIVE_READ_ONLY_RUNTIME_SELECTION",
            ),
        ),
    )

    matrix = _account_risk_matrix(
        registry,
        {
            "S21_BANKNIFTY_INTERNAL_PAPER_A": {
                "status": "LIVE_AUTHORITATIVE_SELECTED_CONTRACT",
                "selected_contract": "NSE:BANKNIFTY26AUG56900CE",
                "entry": "947.29",
            }
        },
        late_start=False,
    )

    assert matrix["S21_BANKNIFTY_INTERNAL_PAPER_A"]["decision"] == "ACCEPTED_INTENT"


def test_live_instance_result_promotes_filled_internal_order_to_open_position() -> None:
    instance = EnabledStrategyInstance(
        strategy_definition_id="S22_STOCKS_OP_SELL_MONTHLY_DIFF_2D_4D",
        strategy_version="s22.test.v1",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        account_reference="INTERNAL_PAPER_ACCOUNT_A",
        underlying={"exchange": "NSE", "symbol": "RELIANCE", "instrument_type": "STOCK"},
        product="OPTION_SELLING",
        enabled=True,
        configured_quantity={"lots": 1, "lot_size": 500},
        authority_mode="INTERNAL_PAPER_CONTROLLED",
        market_data_source="FYERS_READ_ONLY",
        rule_config_hash="hash-1",
        risk_allocation={"max_positions": 1, "max_margin_usage_pct": 20},
        operator_approval_status="APPROVED_INTERNAL_PAPER",
        evidence_quality="LIVE_READ_ONLY_RUNTIME_SELECTION",
    )
    result = _live_instance_result(
        instance,
        now=datetime(2026, 8, 5, 10, 5, tzinfo=IST),
        session_id="NSE:2026-08-05:UNIFIED_INTERNAL_PAPER",
        continuity={
            "selected_contract": "NSE:RELIANCE26AUG1260CE",
            "selected_branch": "BEAR_CALL",
            "selected_option_type": "CE",
            "selected_expiry": "2026-08-27",
            "selected_strike": "1260",
            "entry": "57.50",
            "target": "23.00",
            "original_sl": "92.00",
            "evidence": "LIVE_FYERS_READ_ONLY_CAPTURE",
            "selected_contract_quote": {"ltp": "47.75", "bid": "47.70", "ask": "47.80"},
            "quote": {"ltp": "47.75", "bid": "47.70", "ask": "47.80"},
            "current_entry_state": "NORMAL_ENTRY_STILL_VALID",
            "orpt_result": "ORPT_ENTRY_NOT_MISSED",
            "rc_result": "RC_NOT_REQUIRED",
        },
        timing={"market_open": "PAST_WINDOW", "orpt": "PAST_WINDOW", "rc": "PAST_WINDOW", "eod_carry": "FUTURE_WINDOW"},
        selected_contract_reads=(),
        late_start=False,
        action_state={
            "order_state": "FILLED_INTERNAL",
            "fill_state": "FILLED_INTERNAL",
            "final_state": "FILLED_INTERNAL",
            "position_cycle_id": "pc:test",
            "filled_quantity": 500,
            "remaining_quantity": 500,
            "average_entry": "57.50",
            "entry_price": "57.50",
            "entry_time": "2026-08-05T09:25:00+05:30",
            "latest_event": "INTERNAL_FULL_FILL",
            "mark": "47.75",
        },
    )

    assert result["execution"]["order_state"] == "FILLED_INTERNAL"
    assert result["position"]["health"] == "OPEN_PROTECTED"
    assert result["position"]["entry_time"] == "2026-08-05T09:25:00+05:30"
    assert result["accounting"]["unrealized_pnl"] == "4875.00"

    order = _order_row(instance, result)
    position = _position_row(instance, result)
    assert order["lots"] == 1
    assert order["entry_time"] == "2026-08-05T09:25:00+05:30"
    assert position["lots"] == 1
    assert position["entry_time"] == "2026-08-05T09:25:00+05:30"


def test_live_instance_result_keeps_pending_internal_order_visible_without_position() -> None:
    instance = EnabledStrategyInstance(
        strategy_definition_id="S22_STOCKS_OP_SELL_MONTHLY_DIFF_2D_4D",
        strategy_version="s22.test.v1",
        strategy_instance_id="S22_TCS_INTERNAL_PAPER_A",
        account_reference="INTERNAL_PAPER_ACCOUNT_A",
        underlying={"exchange": "NSE", "symbol": "TCS", "instrument_type": "STOCK"},
        product="OPTION_SELLING",
        enabled=True,
        configured_quantity={"lots": 1, "lot_size": 225},
        authority_mode="INTERNAL_PAPER_CONTROLLED",
        market_data_source="FYERS_READ_ONLY",
        rule_config_hash="hash-1",
        risk_allocation={"max_positions": 1, "max_margin_usage_pct": 20},
        operator_approval_status="APPROVED_INTERNAL_PAPER",
        evidence_quality="LIVE_READ_ONLY_RUNTIME_SELECTION",
    )
    result = _live_instance_result(
        instance,
        now=datetime(2026, 8, 5, 10, 5, tzinfo=IST),
        session_id="NSE:2026-08-05:UNIFIED_INTERNAL_PAPER",
        continuity={
            "selected_contract": "NSE:TCS26AUG2380CE",
            "selected_branch": "BEAR_CALL",
            "selected_option_type": "CE",
            "selected_expiry": "2026-08-27",
            "selected_strike": "2380",
            "entry": "64.05",
            "target": "25.60",
            "original_sl": "102.45",
            "evidence": "LIVE_FYERS_READ_ONLY_CAPTURE",
            "selected_contract_quote": {"ltp": "64.00", "bid": "63.95", "ask": "64.10"},
            "quote": {"ltp": "64.00", "bid": "63.95", "ask": "64.10"},
            "current_entry_state": "NORMAL_ENTRY_STILL_VALID",
            "orpt_result": "ORPT_ENTRY_NOT_MISSED",
            "rc_result": "RC_NOT_REQUIRED",
        },
        timing={"market_open": "PAST_WINDOW", "orpt": "PAST_WINDOW", "rc": "PAST_WINDOW", "eod_carry": "FUTURE_WINDOW"},
        selected_contract_reads=(),
        late_start=False,
        action_state={
            "order_state": "READY_INTERNAL",
            "fill_state": "NO_FILL",
            "final_state": "READY_INTERNAL",
            "position_cycle_id": "pc:test-tcs",
            "filled_quantity": 0,
            "remaining_quantity": 0,
            "entry_price": "64.05",
            "entry_time": "2026-08-05T09:25:00+05:30",
            "latest_event": "WAITING_FOR_FILL",
            "mark": "64.00",
        },
    )

    assert result["execution"]["order_state"] == "READY_INTERNAL"
    assert result["position"]["health"] == "NO_POSITION"
    order = _order_row(instance, result)
    assert order["status"] == "READY_INTERNAL"
    assert order["entry_time"] == "2026-08-05T09:25:00+05:30"


def test_live_market_launcher_seed_projection_stays_empty_until_supervisor_writes_live_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    spec = importlib.util.spec_from_file_location("run_live_market_internal_paper_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class _FakeCoordinator:
        def __init__(self, registry: object) -> None:
            self.registry = registry

        def run_deterministic_session(self) -> dict[str, object]:
            return {
                "dashboard_projection": {
                    "system": {
                        "runtime": "UNIFIED_S21_S22_S23_INTERNAL_PAPER",
                        "market_state": "DETERMINISTIC_SESSION",
                    },
                    "command_centre": {
                        "active_orders": 5,
                        "pending_orders": 5,
                        "open_positions": 5,
                        "plans_prepared": 5,
                        "system_state": "HEALTHY",
                        "broker_sessions": "READ_ONLY_OR_INTERNAL",
                    },
                    "orders": [{"instrument": "RELIANCE"}],
                    "positions": [{"instrument": "RELIANCE"}],
                    "historical_trades": [{"instrument": "RELIANCE"}],
                    "projection_hash": "seed-hash",
                }
            }

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "load_enabled_strategy_registry", lambda _path: object())
    monkeypatch.setattr(module, "MultiStrategyRuntimeCoordinator", _FakeCoordinator)

    projection_path = tmp_path / "tmp" / "live_market_internal_paper" / "dashboard_seed_projection.json"
    module._write_dashboard_seed_projection(
        registry_path="config/live_market_internal_paper_strategy_instances.yaml",
        projection_path=projection_path,
    )

    payload = json.loads(projection_path.read_text(encoding="utf-8"))

    assert payload["system"]["market_state"] == "WAITING_FOR_SUPERVISOR_SNAPSHOT"
    assert payload["system"]["supervisor_state"] == "WAITING_FOR_SUPERVISOR_SNAPSHOT"
    assert payload["command_centre"]["open_positions"] == 0
    assert payload["command_centre"]["active_orders"] == 0
    assert payload["orders"] == []
    assert payload["positions"] == []
    assert payload["historical_trades"] == []
