from __future__ import annotations

from pathlib import Path

from tfis.runtime.multi_strategy import load_enabled_strategy_registry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "s22_multi_stock_registry.yaml"


def test_s22_multi_stock_registry_enables_reliance_tcs_and_infy_for_controlled_internal_paper() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)

    assert [item.symbol for item in registry.enabled_instances] == ["RELIANCE", "TCS", "INFY"]
    assert {item.symbol for item in registry.instances} == {"RELIANCE", "TCS", "INFY"}
    assert len({item.strategy_instance_id for item in registry.instances}) == 3
    assert all(item.authority_mode == "INTERNAL_PAPER_CONTROLLED" for item in registry.instances)
    assert {item.account_reference for item in registry.instances} == {"DEVELOPMENT_INTERNAL_PAPER_ACCOUNT_A"}


def test_s22_multi_stock_registry_preserves_tomorrow_plan_for_tcs_and_infy() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    rows = {item.symbol: item for item in registry.instances}

    assert rows["TCS"].enabled is True
    assert rows["INFY"].enabled is True
    assert rows["TCS"].configured_quantity["lot_size"] == 225
    assert rows["INFY"].configured_quantity["lot_size"] == 400
    assert rows["TCS"].market_data_source == "LIVE_FYERS_READ_ONLY_CAPTURE"
    assert rows["INFY"].market_data_source == "LIVE_FYERS_READ_ONLY_CAPTURE"
    assert rows["TCS"].evidence_quality == "ACTUAL_CHAIN_REPORT_PLUS_FYERS_HISTORY"
    assert rows["INFY"].evidence_quality == "ACTUAL_CHAIN_REPORT_PLUS_FYERS_HISTORY"
    assert rows["TCS"].operator_approval_status == "APPROVED_INTERNAL_PAPER"
    assert rows["INFY"].operator_approval_status == "APPROVED_INTERNAL_PAPER"
    assert rows["TCS"].deterministic_projection["monthly_status"] == "BEAR_CF"
    assert rows["INFY"].deterministic_projection["monthly_status"] == "BEAR"
    assert rows["TCS"].deterministic_projection["selected_contract"] == "NSE:TCS26AUG2380CE"
    assert rows["INFY"].deterministic_projection["selected_contract"] == "NSE:INFY26AUG1140CE"


def test_s22_multi_stock_registry_serialization_preserves_dashboard_audit_state() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    payload = registry.to_dict()

    rows = {item["underlying"]["symbol"]: item for item in payload["instances"]}
    assert rows["RELIANCE"]["enabled"] is True
    assert rows["TCS"]["enabled"] is True
    assert rows["INFY"]["enabled"] is True
    assert rows["TCS"]["operator_approval_status"] == "APPROVED_INTERNAL_PAPER"
    assert rows["INFY"]["operator_approval_status"] == "APPROVED_INTERNAL_PAPER"
    assert rows["TCS"]["external_authority"]["external_broker_submission"] == "NONE"
    assert rows["INFY"]["external_authority"]["live_submission"] == "NONE"
