from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tfis.accounting import (
    AccountingBuildError,
    AccountingQuality,
    ChargeEvidence,
    InstrumentDimensions,
    MarkSnapshot,
    PnLFactBuilder,
    TradeFactBuilder,
    rebuild_projections,
    select_mark_for_position,
    short_option_realized_pnl,
    short_option_unrealized_pnl,
)
from tfis.accounting.reports import write_phase4i_reports
from tfis.adapters.phase4i import build_phase4i_case, build_phase4i_portfolio
from tfis.persistence import OptimisticConcurrencyError, PersistenceDatabase, UnitOfWork


def test_trade_fact_immutability_and_deterministic_identity() -> None:
    first = build_phase4i_case("bull_target")["trade_fact"]
    second = build_phase4i_case("bull_target")["trade_fact"]
    obj = _trade_obj(first)

    assert first["trade_fact_id"] == second["trade_fact_id"]
    assert first["fact_hash"] == second["fact_hash"]
    assert first["accounting_truth"] == "INTERNAL_PAPER_ACCOUNTING_TRUTH"
    with pytest.raises(FrozenInstanceError):
        obj.trade_fact_id = "mutated"  # type: ignore[misc]


def test_open_and_closed_trade_states_and_exit_reasons() -> None:
    closed = build_phase4i_case("bull_target")["trade_fact"]
    open_trade = build_phase4i_case("carry_open")["trade_fact"]
    eod = build_phase4i_case("eod_exit")["trade_fact"]

    assert closed["state"] == "CLOSED_PROVISIONAL"
    assert closed["lifecycle"]["final_exit_reason"] == "TARGET"
    assert open_trade["state"] == "OPEN_PROVISIONAL"
    assert open_trade["lifecycle"]["final_exit_reason"] == "CARRIED_FORWARD"
    assert eod["lifecycle"]["final_exit_reason"] == "EOD_EXIT"


def test_short_option_realized_unrealized_formula_and_quantity_unit() -> None:
    assert short_option_realized_pnl(Decimal("100"), Decimal("80"), 50, Decimal("1")) == Decimal("1000.00")
    assert short_option_unrealized_pnl(Decimal("100"), Decimal("91"), 50, Decimal("1")) == Decimal("450.00")
    with pytest.raises(AccountingBuildError):
        short_option_realized_pnl(Decimal("100"), Decimal("80"), -1, Decimal("1"))


def test_partial_entry_partial_exit_and_multiple_exit_fill_accounting() -> None:
    partial_entry = build_phase4i_case("partial_entry")["trade_fact"]
    partial_exit = build_phase4i_case("partial_exit")["trade_fact"]

    assert partial_entry["execution"]["partial_fill"] is True
    assert partial_exit["execution"]["partial_exit"] is True
    assert partial_exit["execution"]["confirmed_exit_quantity"] < partial_exit["execution"]["confirmed_entry_quantity"]
    expected = short_option_realized_pnl(
        Decimal(str(partial_exit["execution"]["average_entry"])),
        Decimal(str(partial_exit["execution"]["average_exit"])),
        int(partial_exit["execution"]["confirmed_exit_quantity"]),
        Decimal(str(partial_exit["instrument"]["multiplier"])),
    )
    assert Decimal(str(partial_exit["performance_inputs"]["gross_realized_pnl"])) == expected


def test_unrealized_mark_policy_ltp_fallback_and_stale_unknown() -> None:
    executable = build_phase4i_case("carry_open")
    fallback = build_phase4i_case("ltp_fallback")
    stale = build_phase4i_case("stale_mark")

    assert executable["trade_fact"]["performance_inputs"]["mark_quality"] == "EXECUTABLE_SIDE"
    assert fallback["trade_fact"]["performance_inputs"]["mark_quality"] == "DEGRADED_LTP_FALLBACK"
    assert stale["trade_fact"]["performance_inputs"]["current_unrealized_pnl"] is None
    assert stale["pnl_facts"][0]["quality_state"] == "UNKNOWN"


def test_estimated_charges_correction_and_win_loss_classification() -> None:
    winner = build_phase4i_case("bull_target")
    loser = build_phase4i_case("bear_original_sl")
    correction = build_phase4i_case("charge_correction")

    assert winner["trade_fact"]["lifecycle"]["win_loss"] == "WIN"
    assert loser["trade_fact"]["lifecycle"]["win_loss"] == "LOSS"
    assert any(fact["fact_type"] == "CHARGE_ESTIMATE" for fact in winner["pnl_facts"])
    assert correction["correction"]["fact_type"] == "CHARGE_CORRECTION"
    assert correction["correction"]["supersedes_pnl_fact_id"]


def test_duration_mfe_mae_and_path_attribution() -> None:
    revised = build_phase4i_case("revised_sl")["trade_fact"]

    assert revised["decision_context"]["normal_gap_path"] == "GAP_RECALCULATED"
    assert revised["decision_context"]["orpt_rc_path"] == "RC"
    assert revised["performance_inputs"]["duration_seconds"] > 0
    assert revised["performance_inputs"]["mfe_mae"]["quality"] == "COMPLETE"


def test_daily_account_strategy_instrument_exit_path_projections_and_metrics() -> None:
    portfolio = build_phase4i_portfolio()
    projections = {item["projection_type"]: item for item in portfolio["projections"]}

    assert portfolio["rebuild_equals_incremental"] is True
    assert projections["DAILY_PORTFOLIO"]["metrics"]["total_trades"] == 5
    assert "profit_factor" in projections["STRATEGY"]["metrics"]
    assert projections["EXIT_REASON"]["metrics"]
    assert projections["PATH"]["metrics"]


def test_multi_account_dimension_isolation() -> None:
    result = build_phase4i_case("two_accounts")

    assert result["isolation"] == "PASSED"
    assert result["account_a"]["trade_fact"]["position_cycle_id"] != result["account_b"]["trade_fact"]["position_cycle_id"]
    assert any(item["projection_type"] == "DAILY_PORTFOLIO" for item in result["portfolio_projection"])


def test_fail_closed_missing_metadata_ambiguous_unit_bad_mark_and_timestamp() -> None:
    case = build_phase4i_case("bull_target")
    projection = _projection_from_trade(case["trade_fact"])
    entry_fills = tuple({"internal_fill_id": "entry", "client_order_id": "order", "fill_quantity": 1, "fill_price": "100", "recorded_timestamp": "2026-06-05T09:15:00+05:30"} for _ in range(1))
    with pytest.raises(ValueError):
        InstrumentDimensions(exchange="NSE", product="OPTION_SELLING", underlying="NIFTY", contract="C", expiry=None, strike=None, option_type="CALL", direction="CALL", lot_size=0, multiplier=Decimal("1"), tick_size=Decimal("0.05"), currency="INR")
    bad_instrument = InstrumentDimensions(exchange="NSE", product="OPTION_SELLING", underlying="NIFTY", contract=projection["identity"]["normalized_contract"], expiry=None, strike=None, option_type="CALL", direction="CALL", lot_size=1, multiplier=Decimal("1"), tick_size=Decimal("0.05"), currency="INR", quantity_unit="LOTS")
    with pytest.raises(AccountingBuildError):
        TradeFactBuilder().build(projection=projection, instrument=bad_instrument, requested_entry_quantity=1, entry_fills=entry_fills, exit_fills=(), lifecycle_requirements=(), charge_evidence=ChargeEvidence(Decimal("0"), AccountingQuality.CONFIRMED_INTERNAL_PAPER, "fixture"), decision_context={}, source_hashes={})
    with pytest.raises(AccountingBuildError):
        select_mark_for_position(side="SELL", mark=MarkSnapshot(contract="C", trading_date=date(2026, 6, 5), bid=None, ask=None, ltp=None, source_timestamp=datetime.now(), captured_timestamp=datetime.now(), freshness_seconds=-1, snapshot_hash="bad"))


def test_persistence_atomicity_idempotency_and_projection_conflict(tmp_path: Path) -> None:
    case = build_phase4i_case("bull_target")
    db = PersistenceDatabase(tmp_path / "phase4i.sqlite")
    with UnitOfWork(db) as uow:
        uow.repo.put_accounting_build_result(build_result=case, expected_projection_version=0)
        uow.repo.put_accounting_build_result(build_result=case, expected_projection_version=None)
    with pytest.raises(OptimisticConcurrencyError):
        with UnitOfWork(db) as uow:
            mutated = dict(case)
            mutated["projections"] = [dict(item) | {"projection_hash": "changed"} for item in case["projections"]]
            uow.repo.put_accounting_build_result(build_result=mutated, expected_projection_version=0)
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM accounting_trade_facts").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_reports_are_generated(tmp_path: Path) -> None:
    written = write_phase4i_reports(tmp_path / "reports", tmp_path / "phase4i.sqlite")

    assert "phase4i_summary.md" in written
    assert (tmp_path / "reports" / "phase4i_trade_trace.json").exists()
    assert "PHASE4I_M1_ACCEPT" in (tmp_path / "reports" / "phase4i_summary.md").read_text(encoding="utf-8")


def _trade_obj(data):
    from tfis.adapters.phase4i.s23_accounting import _trade_obj as convert

    return convert(data)


def _projection_from_trade(trade):
    return {
        "identity": {
            "position_cycle_id": trade["position_cycle_id"],
            "trading_session_id": trade["trading_session_id"],
            "originating_trading_date": trade["originating_trading_date"],
            "broker_account_id": "fixture",
            "logical_account_reference": trade["logical_paper_account"],
            "strategy_family_id": trade["strategy_family"],
            "strategy_definition_id": trade["strategy_definition"],
            "strategy_version": trade["strategy_version"],
            "strategy_instance_id": trade["strategy_instance"],
            "originating_execution_plan_id": "plan",
            "originating_entry_execution_intent_id": "intent",
            "normalized_contract": trade["instrument"]["contract"],
            "direction": trade["instrument"]["direction"],
            "side": "SELL",
            "authority_classification": "INTERNAL_PAPER_ONLY",
        },
        "confirmed_entry_quantity": 1,
        "remaining_quantity": 1,
        "realized_quantity": 0,
        "average_entry_price": "100",
        "average_exit_price": None,
        "entry_fill_ids": ["entry"],
        "exit_fill_ids": [],
        "lifecycle_state": "OPEN_UNPROTECTED",
        "terminal_status": None,
        "projection_hash": "projection",
    }
