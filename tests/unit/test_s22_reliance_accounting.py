from __future__ import annotations

from tfis.adapters.phase5e import build_s22_reliance_certification


def test_s22_reliance_short_option_accounting_uses_exchange_units_once() -> None:
    certification = build_s22_reliance_certification()
    accounting = certification["s22_reliance_accounting"]
    trade = accounting["trade_fact"]
    pnl = accounting["pnl_facts"][0]

    assert trade["instrument"]["underlying"] == "RELIANCE"
    assert trade["instrument"]["lot_size"] == 500
    assert trade["instrument"]["multiplier"] == "1"
    assert trade["execution"]["requested_entry_quantity"] == 500
    assert trade["decision_context"]["configured_lots"] == 1
    assert trade["decision_context"]["exchange_quantity"] == 500
    assert trade["decision_context"]["double_lot_multiplication"] is False
    assert pnl["gross_pnl"] == "17250.00"
    assert pnl["net_pnl"] == "17235.00"
    assert pnl["calculation_version"] == "tfis.short_option_accounting.v1"


def test_s22_reliance_dashboard_projection_is_read_only_state() -> None:
    certification = build_s22_reliance_certification()
    projection = certification["s22_reliance_dashboard_projection"]

    assert projection["strategy_instance"] == "S22_RELIANCE_ACCOUNT_A_INTERNAL_PAPER"
    assert projection["underlying"] == "RELIANCE"
    assert projection["monthly_status"] == "BEAR_CF"
    assert projection["branch"] == "BEAR_CALL"
    assert projection["plan_state"] == "PREPARED"
    assert projection["order_state"] == "FILLED_INTERNAL"
    assert projection["realized_pnl"] == "17250.00"
    assert projection["health"] == "CONDITIONAL"
    assert "selected option historical candles absent" in projection["alerts"][0]
