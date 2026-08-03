from __future__ import annotations

from pathlib import Path

from tfis.runtime.multi_strategy import load_enabled_strategy_registry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "s22_multi_stock_registry.yaml"


def test_s22_multi_stock_registry_keeps_only_reliance_enabled() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)

    assert [item.symbol for item in registry.enabled_instances] == ["RELIANCE"]
    assert {item.symbol for item in registry.instances} == {"RELIANCE", "TCS", "INFY"}
    assert len({item.strategy_instance_id for item in registry.instances}) == 3
    assert all(item.authority_mode == "INTERNAL_PAPER_CONTROLLED" for item in registry.instances)


def test_s22_multi_stock_registry_marks_candidate_stocks_disabled_but_not_approved() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    disabled = {item.symbol: item for item in registry.instances if not item.enabled}

    assert set(disabled) == {"TCS", "INFY"}
    assert disabled["TCS"].configured_quantity["lot_size"] == 225
    assert disabled["INFY"].configured_quantity["lot_size"] == 400
    assert all(item.market_data_source == "LIVE_FYERS_READ_ONLY_CAPTURE" for item in disabled.values())
    assert all(item.evidence_quality == "LIVE_FYERS_READ_ONLY_CAPTURE" for item in disabled.values())
    assert all(item.operator_approval_status == "NOT_APPROVED" for item in disabled.values())
