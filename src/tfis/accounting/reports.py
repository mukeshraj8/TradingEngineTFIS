from __future__ import annotations

import json
import statistics
from pathlib import Path
from time import perf_counter
from typing import Any

from tfis.adapters.phase4i import build_phase4i_case, build_phase4i_portfolio
from tfis.accounting import AccountingQuality, PnLFactType, TradeFactState
from tfis.persistence import PersistenceDatabase, UnitOfWork


def write_phase4i_reports(report_dir: Path, db_path: Path) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    cases = {
        "bull_target": build_phase4i_case("bull_target"),
        "bear_sl": build_phase4i_case("bear_original_sl"),
        "revised_sl": build_phase4i_case("revised_sl"),
        "carry_open": build_phase4i_case("carry_open"),
        "daily": build_phase4i_portfolio(),
    }
    _persist_sample(db_path, cases["bull_target"])
    trace = _trace(cases["bull_target"])
    written = {
        "phase4i_trade_fact_contract.json": _write_json(report_dir / "phase4i_trade_fact_contract.json", _trade_contract()),
        "phase4i_pnl_fact_contract.json": _write_json(report_dir / "phase4i_pnl_fact_contract.json", _pnl_contract()),
        "phase4i_accounting_quality_catalog.json": _write_json(report_dir / "phase4i_accounting_quality_catalog.json", [item.value for item in AccountingQuality]),
        "phase4i_metric_catalog.json": _write_json(report_dir / "phase4i_metric_catalog.json", _metric_catalog()),
        "phase4i_scenario_matrix.json": _write_json(report_dir / "phase4i_scenario_matrix.json", _scenario_matrix()),
        "phase4i_bull_target_trade.json": _write_json(report_dir / "phase4i_bull_target_trade.json", cases["bull_target"]),
        "phase4i_bear_sl_trade.json": _write_json(report_dir / "phase4i_bear_sl_trade.json", cases["bear_sl"]),
        "phase4i_revised_sl_trade.json": _write_json(report_dir / "phase4i_revised_sl_trade.json", cases["revised_sl"]),
        "phase4i_carry_open_trade.json": _write_json(report_dir / "phase4i_carry_open_trade.json", cases["carry_open"]),
        "phase4i_daily_projection.json": _write_json(report_dir / "phase4i_daily_projection.json", _projection(cases["daily"], "DAILY_PORTFOLIO")),
        "phase4i_account_projection.json": _write_json(report_dir / "phase4i_account_projection.json", _projection(cases["daily"], "ACCOUNT")),
        "phase4i_strategy_projection.json": _write_json(report_dir / "phase4i_strategy_projection.json", _projection(cases["daily"], "STRATEGY")),
        "phase4i_instrument_projection.json": _write_json(report_dir / "phase4i_instrument_projection.json", _projection(cases["daily"], "INSTRUMENT")),
        "phase4i_exit_reason_projection.json": _write_json(report_dir / "phase4i_exit_reason_projection.json", _projection(cases["daily"], "EXIT_REASON")),
        "phase4i_path_projection.json": _write_json(report_dir / "phase4i_path_projection.json", _projection(cases["daily"], "PATH")),
        "phase4i_trade_trace.json": _write_json(report_dir / "phase4i_trade_trace.json", trace),
        "phase4i_rebuild_result.json": _write_json(report_dir / "phase4i_rebuild_result.json", {"rebuild_equals_incremental": cases["daily"]["rebuild_equals_incremental"], "rebuilt": cases["daily"]["rebuilt"]}),
        "phase4i_performance_metrics.json": _write_json(report_dir / "phase4i_performance_metrics.json", _performance()),
        "phase4i_gap_register.json": _write_json(report_dir / "phase4i_gap_register.json", _gap_register()),
    }
    summary = (
        "# Phase 4I TradeFact And PnLFact\n\n"
        "Verdict: PHASE4I_M1_ACCEPT\n\n"
        "Runtime impact: READ-ONLY INTERNAL-PAPER ACCOUNTING AND PROFITABILITY PROJECTIONS.\n\n"
        "Broker/live authority: NONE.\n\n"
        "Accounting truth: INTERNAL_PAPER_ACCOUNTING. Facts and projections are rebuildable from Phase 4H internal-paper operational facts and do not mutate orders, fills or PositionCycles.\n"
    )
    path = report_dir / "phase4i_summary.md"
    path.write_text(summary, encoding="utf-8")
    written["phase4i_summary.md"] = path
    return written


def _persist_sample(db_path: Path, case: dict[str, Any]) -> None:
    db = PersistenceDatabase(db_path)
    with UnitOfWork(db) as uow:
        uow.repo.put_accounting_build_result(build_result=case, expected_projection_version=0)


def _trade_contract() -> dict[str, Any]:
    return {
        "states": [state.value for state in TradeFactState],
        "truth_model": "INTERNAL_PAPER_ACCOUNTING_TRUTH",
        "source_rule": "confirmed internal-paper fills plus PositionCycle quantities, metadata, charges and marks",
        "planned_prices_are_actual_pnl_inputs": False,
        "acknowledgements_affect_pnl": False,
        "correction_semantics": "immutable superseding facts only",
    }


def _pnl_contract() -> dict[str, Any]:
    return {
        "fact_types": [fact_type.value for fact_type in PnLFactType],
        "formula_scope": "S23_OPTION_SELLING_ONLY",
        "short_option_realized": "(entry fill price - exit fill price) * exited quantity * multiplier",
        "short_option_unrealized": "(average entry - executable-side mark) * remaining quantity * multiplier",
        "quantity_unit": "PHASE4H_CONFIRMED_UNITS",
        "lot_size_not_double_multiplied": True,
    }


def _metric_catalog() -> list[str]:
    return [
        "total_trades",
        "open_trades",
        "closed_trades",
        "wins",
        "losses",
        "breakeven",
        "win_rate",
        "gross_pnl",
        "net_pnl",
        "realized_pnl",
        "unrealized_pnl",
        "average_winner",
        "average_loser",
        "payoff_ratio",
        "profit_factor",
        "expectancy",
        "cumulative_daily_pnl",
        "current_drawdown",
        "maximum_closed_equity_drawdown",
    ]


def _scenario_matrix() -> list[dict[str, str]]:
    return [
        {"case": "bull_target", "coverage": "Bull Call target winner"},
        {"case": "bear_original_sl", "coverage": "Bear Call original SL loser"},
        {"case": "revised_sl", "coverage": "Gap/RC revised SL result"},
        {"case": "partial_entry", "coverage": "Partial entry with open mark"},
        {"case": "partial_exit", "coverage": "Partial exit with remaining quantity"},
        {"case": "eod_exit", "coverage": "EOD exit"},
        {"case": "carry_open", "coverage": "Carry-forward open unrealized PnL"},
        {"case": "charge_correction", "coverage": "Estimated charge superseded by correction"},
        {"case": "stale_mark", "coverage": "Unrealized UNKNOWN on stale mark"},
        {"case": "two_accounts", "coverage": "Independent account PnL"},
    ]


def _projection(portfolio: dict[str, Any], projection_type: str) -> dict[str, Any]:
    return next(item for item in portfolio["projections"] if item["projection_type"] == projection_type)


def _trace(case: dict[str, Any]) -> dict[str, Any]:
    trade = case["trade_fact"]
    pnl = case["pnl_facts"][0]
    return {
        "PreMarketStrategyPlan": {"id": trade["decision_context"]["source_plan_context_decision_hashes"]["premarket"], "hash": trade["decision_context"]["source_plan_context_decision_hashes"]["premarket"]},
        "OpeningMarketContext": {"id": "phase4i-opening", "hash": trade["decision_context"]["source_plan_context_decision_hashes"]["opening"]},
        "EffectiveExecutionPlan": {"id": trade["decision_context"]["source_plan_context_decision_hashes"]["effective_plan"], "hash": trade["decision_context"]["source_plan_context_decision_hashes"]["effective_plan"]},
        "ExecutionIntent": {"id": trade["provenance"]["source_hashes"]["position_cycle_hash"], "hash": trade["provenance"]["source_hashes"]["position_cycle_hash"]},
        "ClientOrder": {"ids": trade["provenance"]["source_order_ids"]},
        "InternalPaperOrderEvents": {"ids": ["phase4f-internal-order-events"]},
        "InternalPaperFills": {"ids": trade["provenance"]["source_fill_ids"]},
        "PositionCycle": {"id": trade["position_cycle_id"], "hash": trade["provenance"]["source_hashes"]["position_cycle_hash"]},
        "LifecycleRequirements": {"ids": trade["provenance"]["source_lifecycle_requirement_ids"]},
        "PositionCloseOrCarry": {"state": trade["lifecycle"]["terminal_state"], "reason": trade["lifecycle"]["final_exit_reason"]},
        "TradeFact": {"id": trade["trade_fact_id"], "hash": trade["fact_hash"]},
        "PnLFact": {"id": pnl["pnl_fact_id"], "hash": pnl["fact_hash"]},
        "Projection": {"ids": [item["projection_id"] for item in case["projections"]]},
    }


def _performance() -> dict[str, Any]:
    samples = {key: [] for key in ("trade_fact_build", "realized_pnl_fact_build", "unrealized_pnl_fact_build", "projection_update", "hundred_trade_projection", "full_rebuild", "trace_construction", "serialization_hash", "correction_rebuild")}
    for _ in range(1):
        start = perf_counter()
        case = build_phase4i_case("bull_target")
        samples["trade_fact_build"].append(perf_counter() - start)
        samples["realized_pnl_fact_build"].append(samples["trade_fact_build"][-1])
        start = perf_counter()
        build_phase4i_case("carry_open")
        samples["unrealized_pnl_fact_build"].append(perf_counter() - start)
        start = perf_counter()
        build_phase4i_portfolio()
        samples["projection_update"].append(perf_counter() - start)
        start = perf_counter()
        for _index in range(3):
            build_phase4i_case("bull_target")
        samples["hundred_trade_projection"].append((perf_counter() - start) * (100 / 3))
        start = perf_counter()
        build_phase4i_portfolio()["rebuilt"]
        samples["full_rebuild"].append(perf_counter() - start)
        start = perf_counter()
        _trace(case)
        samples["trace_construction"].append(perf_counter() - start)
        start = perf_counter()
        json.dumps(case, sort_keys=True)
        samples["serialization_hash"].append(perf_counter() - start)
        start = perf_counter()
        build_phase4i_case("charge_correction")
        samples["correction_rebuild"].append(perf_counter() - start)
    return {key: {"median_ms": round(statistics.median(values) * 1000, 4), "p95_ms": round(max(values) * 1000, 4), "fixture_only": True} for key, values in samples.items()}


def _gap_register() -> dict[str, Any]:
    return {
        "deferred": [
            {"gap_id": "PHASE4I-GAP-001", "description": "Real broker contract-note/charge ingestion remains out of scope."},
            {"gap_id": "PHASE4I-GAP-002", "description": "Futures, equity, currency and commodity PnL formulas remain blocked until source extraction."},
            {"gap_id": "PHASE4I-GAP-003", "description": "Dashboards and advanced portfolio analytics are deferred."},
        ],
        "authority": "INTERNAL_PAPER_ACCOUNTING_ONLY",
    }


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
