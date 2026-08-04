from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from tfis.contract_selection import ActualOptionChainContract, build_actual_option_chain_traversal
from tfis.domain.enums import MonthlyStatus
from tfis.domain.market_levels import MarketLevels
from tfis.formulas import FormulaEngine
from tfis.fyers_read_only import (
    FyersOptionChainSnapshot,
    FyersOptionContractQuote,
    FyersReadOnlyAdapter,
    FyersReadOnlyResult,
    FyersReadOnlyStatus,
    classify_monthly_expiries,
)
from tfis.importers import load_strategy_rule
from tfis.monthly_status import (
    MonthlyStatusHistoricalBar,
    MonthlyStatusLookbackResolver,
    build_monthly_weekly_context_lookback_windows,
    derive_monthly_status_reference_levels,
    load_monthly_status_instrument_registry,
)
from tfis.paper.expiry_governance import DeterministicExpiryCalendar, PaperExpiryGovernance
from tfis.persistence import canonical_hash
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance
from tfis.strategy import StrategyEvaluator


_SELECTION_SUPPORTED = frozenset(
    {
        "S21_BANKNIFTY_OP_SELL_MONTHLY",
        "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_FOUR_BRANCH",
    }
)
_MONTHLY_STATUS_RULE_ID = "MONTHLY_STATUS.GENERIC.ENGINE.001"
_SELECTION_RULE_ID = "LIVE.ACTUAL_CHAIN.CONTRACT_SELECTION.001"
_S22_REPORT_PATH = Path("reports/s22_reliance/s22_reliance_contract_selection.json")


@dataclass(frozen=True, slots=True)
class LiveContractSelectionResult:
    status: str
    evidence: str
    strategy_instance_id: str
    selected_contract: str | None
    selected_branch: str | None
    selected_option_type: str | None
    selected_expiry: str | None
    selected_strike: str | None
    entry: str | None
    target: str | None
    original_sl: str | None
    monthly_status: str | None
    quote: Mapping[str, Any] | None
    option_history_status: str | None
    plan_payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evidence": self.evidence,
            "strategy_instance_id": self.strategy_instance_id,
            "selected_contract": self.selected_contract,
            "selected_branch": self.selected_branch,
            "selected_option_type": self.selected_option_type,
            "selected_expiry": self.selected_expiry,
            "selected_strike": self.selected_strike,
            "entry": self.entry,
            "target": self.target,
            "original_sl": self.original_sl,
            "monthly_status": self.monthly_status,
            "quote": dict(self.quote or {}),
            "option_history_status": self.option_history_status,
            "plan_payload": _json_safe(self.plan_payload),
        }


@dataclass(frozen=True, slots=True)
class HistoricalContractSelectionResult:
    status: str
    evidence: str
    recovery_mode: str
    strategy_instance_id: str
    selected_contract: str | None
    selected_branch: str | None
    selected_option_type: str | None
    selected_expiry: str | None
    selected_strike: str | None
    entry: str | None
    target: str | None
    original_sl: str | None
    monthly_status: str | None
    quote: Mapping[str, Any] | None
    option_history_status: str | None
    candidate_count: int
    rejected_candidates: tuple[Mapping[str, Any], ...]
    plan_payload: Mapping[str, Any]
    unresolved_gap: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evidence": self.evidence,
            "recovery_mode": self.recovery_mode,
            "strategy_instance_id": self.strategy_instance_id,
            "selected_contract": self.selected_contract,
            "selected_branch": self.selected_branch,
            "selected_option_type": self.selected_option_type,
            "selected_expiry": self.selected_expiry,
            "selected_strike": self.selected_strike,
            "entry": self.entry,
            "target": self.target,
            "original_sl": self.original_sl,
            "monthly_status": self.monthly_status,
            "quote": dict(self.quote or {}),
            "option_history_status": self.option_history_status,
            "candidate_count": self.candidate_count,
            "rejected_candidates": [_json_safe(item) for item in self.rejected_candidates],
            "plan_payload": _json_safe(self.plan_payload),
            "unresolved_gap": self.unresolved_gap,
        }


def supports_authoritative_live_selection(instance: EnabledStrategyInstance) -> bool:
    return instance.strategy_definition_id in _SELECTION_SUPPORTED


def build_authoritative_historical_selection(
    *,
    repo_root: Path,
    instance: EnabledStrategyInstance,
    adapter: FyersReadOnlyAdapter,
    instrument_records: Iterable[Any],
    session_date: date,
    now: datetime,
) -> HistoricalContractSelectionResult:
    if supports_authoritative_live_selection(instance):
        live = build_authoritative_live_selection(
            repo_root=repo_root,
            instance=instance,
            adapter=adapter,
            instrument_records=instrument_records,
            session_date=session_date,
            now=now,
        )
        if live.selected_contract is None:
            return HistoricalContractSelectionResult(
                status=_historical_blocked_status(live.status),
                evidence="HISTORICAL_RECONSTRUCTION_BLOCKED",
                recovery_mode="HISTORICAL_RECONSTRUCTION_BLOCKED",
                strategy_instance_id=instance.strategy_instance_id,
                selected_contract=None,
                selected_branch=live.selected_branch,
                selected_option_type=live.selected_option_type,
                selected_expiry=live.selected_expiry,
                selected_strike=live.selected_strike,
                entry=live.entry,
                target=live.target,
                original_sl=live.original_sl,
                monthly_status=live.monthly_status,
                quote=live.quote,
                option_history_status=live.option_history_status,
                candidate_count=len(tuple(live.plan_payload.get("branch_candidates") or ())),
                rejected_candidates=tuple(_flatten_rejections(tuple(live.plan_payload.get("branch_candidates") or ()))),
                plan_payload=_augment_historical_plan(
                    live.plan_payload,
                    recovery_mode="HISTORICAL_RECONSTRUCTION_BLOCKED",
                    selection_source="CURRENT_CHAIN_REPLAY_ATTEMPT",
                ),
                unresolved_gap=live.status,
            )
        option_history = adapter.fetch_historical_candles(
            symbol=live.selected_contract,
            resolution="1",
            range_from=session_date,
            range_to=session_date,
            exclude_incomplete_after=now,
        )
        return HistoricalContractSelectionResult(
            status="SELECTED_CONTRACT_RECONSTRUCTED",
            evidence="HISTORICAL_UNDERLYING_PLUS_CURRENT_CHAIN_RECONSTRUCTION",
            recovery_mode="HISTORICALLY_RECONSTRUCTED",
            strategy_instance_id=instance.strategy_instance_id,
            selected_contract=live.selected_contract,
            selected_branch=live.selected_branch,
            selected_option_type=live.selected_option_type,
            selected_expiry=live.selected_expiry,
            selected_strike=live.selected_strike,
            entry=live.entry,
            target=live.target,
            original_sl=live.original_sl,
            monthly_status=live.monthly_status,
            quote=live.quote,
            option_history_status=option_history.status.value,
            candidate_count=len(tuple(live.plan_payload.get("branch_candidates") or ())),
            rejected_candidates=tuple(_flatten_rejections(tuple(live.plan_payload.get("branch_candidates") or ()))),
            plan_payload=_augment_historical_plan(
                live.plan_payload,
                recovery_mode="HISTORICALLY_RECONSTRUCTED",
                selection_source="CURRENT_CHAIN_PLUS_HISTORICAL_OPTION_PATH",
            ),
            unresolved_gap=(
                "CURRENT_CHAIN_ONLY_EVIDENCE_FOR_DECISION_STAGE"
                if option_history.status is FyersReadOnlyStatus.SUCCESS
                else "SELECTED_OPTION_HISTORY_UNAVAILABLE"
            ),
        )

    if instance.symbol == "RELIANCE":
        report = _load_s22_selection_report(repo_root=repo_root)
        selected = report.get("selected_contract") if isinstance(report.get("selected_contract"), Mapping) else None
        if not selected:
            return HistoricalContractSelectionResult(
                status="BLOCKED_CHAIN_STATE_NOT_RECOVERABLE",
                evidence="S22_REPORT_SELECTION_UNAVAILABLE",
                recovery_mode="HISTORICAL_RECONSTRUCTION_BLOCKED",
                strategy_instance_id=instance.strategy_instance_id,
                selected_contract=None,
                selected_branch=str(report.get("selected_branch")) if report.get("selected_branch") is not None else None,
                selected_option_type=None,
                selected_expiry=None,
                selected_strike=None,
                entry=None,
                target=None,
                original_sl=None,
                monthly_status=str(report.get("monthly_status")) if report.get("monthly_status") is not None else None,
                quote=None,
                option_history_status=None,
                candidate_count=len(tuple(report.get("branch_candidates") or ())),
                rejected_candidates=tuple(_flatten_rejections(tuple(report.get("branch_candidates") or ()))),
                plan_payload=_augment_historical_plan(
                    report,
                    recovery_mode="HISTORICAL_RECONSTRUCTION_BLOCKED",
                    selection_source="S22_ACCEPTED_REPORT_TRACE",
                ),
                unresolved_gap="S22_SELECTED_CONTRACT_REPORT_MISSING",
            )
        selected_contract = str(selected["symbol"])
        option_history = adapter.fetch_historical_candles(
            symbol=selected_contract,
            resolution="1",
            range_from=session_date,
            range_to=session_date,
            exclude_incomplete_after=now,
        )
        quote_result = adapter.fetch_quotes((selected_contract,))
        quote_payload: Mapping[str, Any] | None = None
        if quote_result.status is FyersReadOnlyStatus.SUCCESS and quote_result.payload:
            quote = quote_result.payload[0]
            quote_payload = {
                "symbol": quote.symbol,
                "ltp": str(quote.ltp) if quote.ltp is not None else None,
                "bid": str(quote.bid) if quote.bid is not None else None,
                "ask": str(quote.ask) if quote.ask is not None else None,
                "oi": str(quote.oi) if quote.oi is not None else None,
                "source_timestamp": quote.timestamp.isoformat() if quote.timestamp is not None else None,
                "receipt_timestamp": now.isoformat(),
            }
        return HistoricalContractSelectionResult(
            status="SELECTED_CONTRACT_RECONSTRUCTED",
            evidence="REPORT_TRACE_PLUS_FYERS_HISTORY",
            recovery_mode="HISTORICALLY_RECONSTRUCTED",
            strategy_instance_id=instance.strategy_instance_id,
            selected_contract=selected_contract,
            selected_branch=str(report.get("selected_branch")) if report.get("selected_branch") is not None else None,
            selected_option_type=str(selected.get("option_type")) if selected.get("option_type") is not None else None,
            selected_expiry=str(selected.get("expiry")) if selected.get("expiry") is not None else None,
            selected_strike=str(selected.get("strike")) if selected.get("strike") is not None else None,
            entry=str(instance.deterministic_projection.get("entry") or ""),
            target=str(instance.deterministic_projection.get("target") or ""),
            original_sl=str(instance.deterministic_projection.get("original_sl") or ""),
            monthly_status=str(report.get("monthly_status")) if report.get("monthly_status") is not None else None,
            quote=quote_payload,
            option_history_status=option_history.status.value,
            candidate_count=len(tuple(report.get("branch_candidates") or ())),
            rejected_candidates=tuple(_flatten_rejections(tuple(report.get("branch_candidates") or ()))),
            plan_payload=_augment_historical_plan(
                report,
                recovery_mode="HISTORICALLY_RECONSTRUCTED",
                selection_source="S22_ACCEPTED_REPORT_TRACE_PLUS_FYERS_HISTORY",
            ),
            unresolved_gap=None if option_history.status is FyersReadOnlyStatus.SUCCESS else "SELECTED_OPTION_HISTORY_UNAVAILABLE",
        )

    return HistoricalContractSelectionResult(
        status="BLOCKED_CHAIN_STATE_NOT_RECOVERABLE",
        evidence="UNSUPPORTED_HISTORICAL_SELECTION_SCOPE",
        recovery_mode="HISTORICAL_RECONSTRUCTION_BLOCKED",
        strategy_instance_id=instance.strategy_instance_id,
        selected_contract=None,
        selected_branch=None,
        selected_option_type=None,
        selected_expiry=None,
        selected_strike=None,
        entry=None,
        target=None,
        original_sl=None,
        monthly_status=None,
        quote=None,
        option_history_status=None,
        candidate_count=0,
        rejected_candidates=(),
        plan_payload={"strategy_instance_id": instance.strategy_instance_id, "selection_source": "UNSUPPORTED_SCOPE"},
        unresolved_gap=f"UNSUPPORTED_SCOPE:{instance.strategy_definition_id}",
    )


def build_authoritative_live_selection(
    *,
    repo_root: Path,
    instance: EnabledStrategyInstance,
    adapter: FyersReadOnlyAdapter,
    instrument_records: Iterable[Any],
    session_date: date,
    now: datetime,
) -> LiveContractSelectionResult:
    if not supports_authoritative_live_selection(instance):
        raise ValueError(f"Unsupported live contract-selection scope: {instance.strategy_definition_id}")

    rules = _load_strategy_rules(repo_root=repo_root, symbol=instance.symbol)
    underlying_symbol = _monthly_status_fyers_symbol(repo_root=repo_root, symbol=instance.symbol)
    underlying_history = adapter.fetch_historical_candles(
        symbol=underlying_symbol,
        resolution="D",
        range_from=session_date - timedelta(days=180),
        range_to=session_date,
        exclude_incomplete_after=now,
    )
    if underlying_history.status is not FyersReadOnlyStatus.SUCCESS:
        return _blocked(
            instance=instance,
            status="BLOCKED_UNDERLYING_HISTORY_UNAVAILABLE",
            evidence="READ_ONLY_PROVIDER_UNAVAILABLE",
            details={"underlying_history_status": underlying_history.status.value},
        )

    underlying_bars = tuple(underlying_history.payload.candles)
    if len(underlying_bars) < 5:
        return _blocked(
            instance=instance,
            status="BLOCKED_UNDERLYING_HISTORY_INSUFFICIENT",
            evidence="INSUFFICIENT_HISTORICAL_CONTEXT",
            details={"underlying_history_bar_count": len(underlying_bars)},
        )

    monthly_status_payload = _resolve_monthly_status(repo_root=repo_root, symbol=instance.symbol, candles=underlying_bars)
    monthly_status = MonthlyStatus(monthly_status_payload["monthly_status"])
    branch_rules = tuple(rule for rule in rules if monthly_status in rule.allowed_monthly_statuses)
    if not branch_rules:
        return _blocked(
            instance=instance,
            status="NO_TRADE_BY_RULE",
            evidence="MONTHLY_STATUS_BRANCH_BLOCK",
            details={"monthly_status": monthly_status.value},
        )

    market_levels, market_reference_payload = _market_levels_from_underlying_history(underlying_bars)
    records = tuple(instrument_records)
    branch_candidates: list[dict[str, Any]] = []
    for rule in branch_rules:
        branch_candidates.append(
            _evaluate_branch_candidate(
                repo_root=repo_root,
                instance=instance,
                rule=rule,
                market_levels=market_levels,
                market_reference_payload=market_reference_payload,
                adapter=adapter,
                records=records,
                session_date=session_date,
                now=now,
            )
        )

    qualifying = [item for item in branch_candidates if item["decision"] == "SELECTED"]
    if not qualifying:
        status = _blocked_status_from_candidates(branch_candidates)
        return _blocked(
            instance=instance,
            status=status,
            evidence="LIVE_ACTUAL_CHAIN_SELECTION_FAILED_CLOSED",
            details={
                "monthly_status": monthly_status.value,
                "branch_candidates": branch_candidates,
                "market_references": market_reference_payload,
                "monthly_status_evidence": monthly_status_payload,
            },
        )

    ranked = sorted(
        qualifying,
        key=lambda item: (
            0 if item["qualification_phase"] == "IDEAL_PREMIUM" else 1,
            Decimal(item["selected_contract"]["strike"]),
            item["selected_contract"]["symbol"],
        ),
    )
    if len(ranked) > 1 and _same_strength(ranked[0], ranked[1]):
        return _blocked(
            instance=instance,
            status="BLOCKED_AMBIGUOUS_BRANCH_SELECTION",
            evidence="LIVE_ACTUAL_CHAIN_BRANCH_TIE_FAIL_CLOSED",
            details={
                "monthly_status": monthly_status.value,
                "branch_candidates": branch_candidates,
                "market_references": market_reference_payload,
                "monthly_status_evidence": monthly_status_payload,
            },
        )

    selected = ranked[0]
    contract = selected["selected_contract"]
    option_symbol = str(contract["symbol"])
    option_history = adapter.fetch_historical_candles(
        symbol=option_symbol,
        resolution="D",
        range_from=session_date - timedelta(days=30),
        range_to=session_date,
        exclude_incomplete_after=now,
    )
    if option_history.status is not FyersReadOnlyStatus.SUCCESS:
        return _blocked(
            instance=instance,
            status="BLOCKED_SELECTED_OPTION_HISTORY_UNAVAILABLE",
            evidence="READ_ONLY_PROVIDER_UNAVAILABLE",
            details={
                "monthly_status": monthly_status.value,
                "branch_candidates": branch_candidates,
                "selected_branch": selected["branch_id"],
                "selected_contract": contract,
                "option_history_status": option_history.status.value,
            },
        )

    option_runtime_values = _selected_option_runtime_values(option_history.payload.candles)
    trade_plan = StrategyEvaluator().evaluate(
        selected["strategy_rule"],
        market_levels=market_levels,
        runtime_values=option_runtime_values,
    )
    quote_payload = _quote_payload_from_contract(selected["contract_quote"], receipt_timestamp=now)
    plan_payload = {
        "schema_version": "tfis.live_contract_selection.plan.v1",
        "strategy_definition_id": instance.strategy_definition_id,
        "strategy_instance_id": instance.strategy_instance_id,
        "trading_date": session_date.isoformat(),
        "monthly_status": monthly_status.value,
        "monthly_status_evidence": monthly_status_payload,
        "market_references": market_reference_payload,
        "branch_resolution_method": (
            "Monthly Status family plus strongest fully supported actual-chain candidate; "
            "ideal premium outranks minimum premium, ties fail closed."
        ),
        "selected_branch": selected["branch_id"],
        "selected_contract": contract,
        "qualification_phase": selected["qualification_phase"],
        "selected_option_runtime_references": option_runtime_values,
        "branch_candidates": branch_candidates,
        "timing": {
            "orpt": selected["strategy_rule"].entry_time.isoformat(),
            "rc": selected["strategy_rule"].recalculation_time.isoformat(),
        },
        "entry": f"{Decimal(str(trade_plan.entry_price)):.2f}",
        "target": f"{Decimal(str(trade_plan.target_price)):.2f}",
        "original_sl": f"{Decimal(str(trade_plan.stoploss_price)):.2f}",
        "plan_hash": "",
        "source_rule_ids": (
            _MONTHLY_STATUS_RULE_ID,
            _SELECTION_RULE_ID,
            selected["strategy_rule"].unique_code,
        ),
        "evidence_quality": "LIVE_AUTHORITATIVE_SELECTED_CONTRACT",
    }
    plan_payload = _json_safe(plan_payload)
    plan_payload["plan_hash"] = canonical_hash({k: v for k, v in plan_payload.items() if k != "plan_hash"})
    return LiveContractSelectionResult(
        status="LIVE_AUTHORITATIVE_SELECTED_CONTRACT",
        evidence="LIVE_READ_ONLY_RUNTIME_SELECTION",
        strategy_instance_id=instance.strategy_instance_id,
        selected_contract=option_symbol,
        selected_branch=selected["branch_id"],
        selected_option_type=str(contract["option_type"]),
        selected_expiry=str(contract["expiry"]),
        selected_strike=str(contract["strike"]),
        entry=plan_payload["entry"],
        target=plan_payload["target"],
        original_sl=plan_payload["original_sl"],
        monthly_status=monthly_status.value,
        quote=quote_payload,
        option_history_status=option_history.status.value,
        plan_payload=plan_payload,
    )


def _load_strategy_rules(*, repo_root: Path, symbol: str) -> tuple[Any, ...]:
    strategy_root = repo_root / "config" / "strategies" / "options_sell" / symbol.lower()
    loaded = [load_strategy_rule(path) for path in sorted(strategy_root.iterdir()) if path.is_dir()]
    if not loaded:
        raise ValueError(f"No strategy folders found for {symbol}: {strategy_root}")
    return tuple(loaded)


def _monthly_status_fyers_symbol(*, repo_root: Path, symbol: str) -> str:
    registry = load_monthly_status_instrument_registry(repo_root / "config" / "monthly_status_instruments.yaml")
    return registry.get(symbol).spot_symbol


def _resolve_monthly_status(*, repo_root: Path, symbol: str, candles: Iterable[Any]) -> dict[str, Any]:
    registry = load_monthly_status_instrument_registry(repo_root / "config" / "monthly_status_instruments.yaml")
    instrument = registry.get(symbol)
    historical = tuple(
        MonthlyStatusHistoricalBar(
            timestamp=bar.bar_end,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
        )
        for bar in candles
    )
    current_reference_timestamp = historical[-1].timestamp
    levels = derive_monthly_status_reference_levels(historical_bars=historical, as_of=current_reference_timestamp.date())
    windows = build_monthly_weekly_context_lookback_windows(
        historical_bars=historical,
        current_reference_timestamp=current_reference_timestamp,
    )
    resolution = MonthlyStatusLookbackResolver().resolve(
        instrument.instrument_group,
        levels,
        current_reference_timestamp=current_reference_timestamp,
        lookback_windows=windows,
    )
    payload = {
        "instrument_identity": {"symbol": symbol, "instrument_group": instrument.instrument_group},
        "evaluation_timestamp": current_reference_timestamp.isoformat(),
        "monthly_status": resolution.resolved_result.status.value,
        "current_window_direct_status": resolution.current_window_result.status.value,
        "borrowed_window_status": resolution.borrowed_window_result.status.value if resolution.borrowed_window_result else None,
        "lookback_used": resolution.lookback_used,
        "checked_lookback_windows": resolution.checked_lookback_windows,
        "reason": resolution.reason,
        "trigger_name": resolution.resolved_result.trigger_name,
        "threshold_value": resolution.resolved_result.threshold_value,
        "source_monthly_references": {
            "PMH": levels.PMH,
            "PML": levels.PML,
            "CMH": levels.CMH,
            "CML": levels.CML,
            "PWH": levels.PWH,
            "PWL": levels.PWL,
            "CWH": levels.CWH,
            "CWL": levels.CWL,
            "current_price": levels.current_price,
        },
        "transition_evidence": {"notes": resolution.resolved_result.notes},
        "source_rule_id": _MONTHLY_STATUS_RULE_ID,
    }
    payload["result_hash"] = canonical_hash(payload)
    return payload


def _market_levels_from_underlying_history(candles: Iterable[Any]) -> tuple[MarketLevels, dict[str, str]]:
    completed = tuple(candles)
    last2 = completed[-2:]
    last3 = completed[-3:]
    refs = {
        "2DHH": f"{max(bar.high for bar in last2):.2f}",
        "2DLL": f"{min(bar.low for bar in last2):.2f}",
        "3DHH": f"{max(bar.high for bar in last3):.2f}",
        "3DLL": f"{min(bar.low for bar in last3):.2f}",
    }
    return (
        MarketLevels(
            d2hh=float(refs["2DHH"]),
            d2ll=float(refs["2DLL"]),
            d3hh=float(refs["3DHH"]),
            d3ll=float(refs["3DLL"]),
        ),
        refs,
    )


def _evaluate_branch_candidate(
    *,
    repo_root: Path,
    instance: EnabledStrategyInstance,
    rule: Any,
    market_levels: MarketLevels,
    market_reference_payload: Mapping[str, str],
    adapter: FyersReadOnlyAdapter,
    records: tuple[Any, ...],
    session_date: date,
    now: datetime,
) -> dict[str, Any]:
    primary_expiry, fallback_expiry = _resolve_expiry_candidates(rule=rule, records=records, session_date=session_date)
    if primary_expiry is None:
        return {
            "branch_id": rule.unique_code,
            "decision": "BLOCKED_EXPIRY_EVIDENCE",
            "selected_contract": None,
            "qualification_phase": None,
            "attempted_expiries": (),
            "rejections": [{"reason": "EXPIRY_EVIDENCE_MISSING"}],
        }

    formula_engine = FormulaEngine()
    runtime_values: dict[str, object] = {}
    start_reference = Decimal(str(formula_engine.evaluate(rule.start_strike_formula, market_levels=market_levels, runtime_values=runtime_values, parameters=rule.parameters)))
    end_reference = Decimal(str(formula_engine.evaluate(rule.end_strike_formula, market_levels=market_levels, runtime_values=runtime_values, parameters=rule.parameters)))
    ideal_premium = Decimal(str(formula_engine.evaluate(rule.ideal_premium_formula, market_levels=market_levels, runtime_values=runtime_values, parameters=rule.parameters)))
    minimum_premium = Decimal(str(formula_engine.evaluate(rule.minimum_premium_formula, market_levels=market_levels, runtime_values=runtime_values, parameters=rule.parameters)))
    traversal_policy = _extract_traversal_policy(rule)
    attempts: list[dict[str, Any]] = []
    for expiry_kind, expiry in (("PRIMARY", primary_expiry), ("FALLBACK", fallback_expiry)):
        if expiry is None:
            continue
        chain_result = adapter.fetch_option_chain(
            underlying=_monthly_status_fyers_symbol(repo_root=repo_root, symbol=instance.symbol),
            expiry=expiry,
            strike_count=50,
            instrument_records=records,
        )
        if chain_result.status is not FyersReadOnlyStatus.SUCCESS:
            attempts.append(
                {
                    "expiry_kind": expiry_kind,
                    "expiry": expiry.isoformat(),
                    "decision": "BLOCKED_OPTION_CHAIN_UNAVAILABLE",
                    "status": chain_result.status.value,
                    "rejections": [{"reason": chain_result.status.value}],
                }
            )
            continue
        attempt = _select_from_actual_chain(
            chain=chain_result.payload,
            expected_underlying=chain_result.payload.underlying,
            expiry=expiry,
            option_type=rule.option_type.value,
            start_reference=start_reference,
            end_reference=end_reference,
            traversal_policy=traversal_policy,
            ideal_premium=ideal_premium,
            minimum_premium=minimum_premium,
            minimum_oi=Decimal(str(rule.minimum_oi)),
        )
        attempt["expiry_kind"] = expiry_kind
        attempt["expiry"] = expiry.isoformat()
        attempts.append(attempt)
        if attempt["decision"] == "SELECTED":
            attempt["branch_id"] = rule.unique_code
            attempt["strategy_rule"] = rule
            attempt["contract_quote"] = attempt["selected_contract_quote"]
            attempt["attempted_expiries"] = tuple(item["expiry"] for item in attempts)
            attempt["start_reference_strike"] = str(start_reference)
            attempt["end_reference_strike"] = str(end_reference)
            attempt["ideal_premium"] = str(ideal_premium)
            attempt["minimum_premium"] = str(minimum_premium)
            attempt["minimum_oi"] = str(rule.minimum_oi)
            attempt["market_references"] = dict(market_reference_payload)
            return attempt
    return {
        "branch_id": rule.unique_code,
        "decision": _blocked_decision_from_attempts(attempts),
        "selected_contract": None,
        "qualification_phase": None,
        "attempted_expiries": tuple(item["expiry"] for item in attempts),
        "rejections": attempts,
    }


def _resolve_expiry_candidates(*, rule: Any, records: tuple[Any, ...], session_date: date) -> tuple[date | None, date | None]:
    governance = PaperExpiryGovernance(DeterministicExpiryCalendar())
    if rule.expiry_policy.expiry_type.value == "MONTHLY":
        classified = classify_monthly_expiries(records, underlying=rule.symbol, as_of=session_date)
        primary = classified.next_monthly_expiry if governance.should_select_next_expiry(rule, session_date) else classified.near_monthly_expiry
        fallback = (
            None
            if primary is None
            else (classified.next_monthly_expiry if primary == classified.near_monthly_expiry else None)
        )
        return primary, fallback
    expiries = sorted(
        {
            record.expiry
            for record in records
            if getattr(record, "underlying", None) == rule.symbol
            and getattr(record, "expiry", None) is not None
            and record.expiry >= session_date
            and getattr(record, "option_type", None) in {"CALL", "PUT"}
        }
    )
    if not expiries:
        return None, None
    primary = expiries[1] if governance.should_select_next_expiry(rule, session_date) and len(expiries) > 1 else expiries[0]
    fallback = next((expiry for expiry in expiries if expiry > primary), None)
    return primary, fallback


def _select_from_actual_chain(
    *,
    chain: FyersOptionChainSnapshot,
    expected_underlying: str,
    expiry: date,
    option_type: str,
    start_reference: Decimal,
    end_reference: Decimal,
    traversal_policy: Mapping[str, Any],
    ideal_premium: Decimal,
    minimum_premium: Decimal,
    minimum_oi: Decimal,
) -> dict[str, Any]:
    traversal = build_actual_option_chain_traversal(
        tuple(_raw_contract_dict(contract) for contract in chain.contracts),
        expected_underlying=expected_underlying,
        expiry=expiry,
        option_type=option_type,
        traversal_direction=str(traversal_policy["traversal_direction"]),
        start_reference_strike=start_reference,
        start_round_mode=str(traversal_policy["start_round_mode"]),
        end_reference_strike=end_reference,
        end_round_mode=str(traversal_policy["end_round_mode"]),
        end_offset_steps=int(traversal_policy["end_offset_steps"]),
        exchange="NSE",
        source_timestamp=chain.captured_at.isoformat(),
        chain_quality_flags=chain.warnings,
    )
    minimum_candidate: ActualOptionChainContract | None = None
    rejections: list[dict[str, Any]] = []
    for contract in traversal.contracts:
        if contract.ltp is None:
            rejections.append({"reason": "PREMIUM_MISSING", "contract_id": contract.contract_id})
            continue
        if contract.oi is None:
            rejections.append({"reason": "OI_MISSING", "contract_id": contract.contract_id})
            continue
        if contract.oi < minimum_oi:
            rejections.append({"reason": "OI_BELOW_MINIMUM", "contract_id": contract.contract_id, "oi": str(contract.oi)})
            continue
        if contract.ltp >= ideal_premium:
            return {
                "decision": "SELECTED",
                "qualification_phase": "IDEAL_PREMIUM",
                "selected_contract": _selected_contract_dict(contract),
                "selected_contract_quote": contract,
                "option_chain_quality": [item.value for item in traversal.quality_codes],
                "strike_candidates": [str(item) for item in traversal.ordered_candidate_strikes],
                "resolved_start_strike": str(traversal.resolved_start_strike) if traversal.resolved_start_strike is not None else None,
                "resolved_end_strike": str(traversal.resolved_end_strike) if traversal.resolved_end_strike is not None else None,
                "rejections": rejections + list(traversal.rejected_contracts),
            }
        if contract.ltp >= minimum_premium and minimum_candidate is None:
            minimum_candidate = contract
        rejections.append({"reason": "IDEAL_PREMIUM_NOT_MET", "contract_id": contract.contract_id, "ltp": str(contract.ltp)})
    if minimum_candidate is not None:
        return {
            "decision": "SELECTED",
            "qualification_phase": "MINIMUM_PREMIUM",
            "selected_contract": _selected_contract_dict(minimum_candidate),
            "selected_contract_quote": minimum_candidate,
            "option_chain_quality": [item.value for item in traversal.quality_codes],
            "strike_candidates": [str(item) for item in traversal.ordered_candidate_strikes],
            "resolved_start_strike": str(traversal.resolved_start_strike) if traversal.resolved_start_strike is not None else None,
            "resolved_end_strike": str(traversal.resolved_end_strike) if traversal.resolved_end_strike is not None else None,
            "rejections": rejections + list(traversal.rejected_contracts),
        }
    if not traversal.contracts:
        return {
            "decision": "BLOCKED_OPTION_CHAIN_UNAVAILABLE" if not chain.contracts else "NO_QUALIFYING_CONTRACT",
            "qualification_phase": None,
            "selected_contract": None,
            "option_chain_quality": [item.value for item in traversal.quality_codes],
            "strike_candidates": [str(item) for item in traversal.ordered_candidate_strikes],
            "resolved_start_strike": str(traversal.resolved_start_strike) if traversal.resolved_start_strike is not None else None,
            "resolved_end_strike": str(traversal.resolved_end_strike) if traversal.resolved_end_strike is not None else None,
            "rejections": rejections + list(traversal.rejected_contracts),
        }
    blocked = "NO_QUALIFYING_CONTRACT"
    if any(item.get("reason") == "PREMIUM_MISSING" for item in rejections):
        blocked = "BLOCKED_PREMIUM_MISSING"
    elif any(item.get("reason") == "OI_MISSING" for item in rejections):
        blocked = "BLOCKED_OI_MISSING"
    return {
        "decision": blocked,
        "qualification_phase": None,
        "selected_contract": None,
        "option_chain_quality": [item.value for item in traversal.quality_codes],
        "strike_candidates": [str(item) for item in traversal.ordered_candidate_strikes],
        "resolved_start_strike": str(traversal.resolved_start_strike) if traversal.resolved_start_strike is not None else None,
        "resolved_end_strike": str(traversal.resolved_end_strike) if traversal.resolved_end_strike is not None else None,
        "rejections": rejections + list(traversal.rejected_contracts),
    }


def _extract_traversal_policy(rule: Any) -> dict[str, Any]:
    start_formula = rule.start_strike_formula.upper()
    end_formula = rule.end_strike_formula.upper()
    if start_formula.startswith("ROUND_DOWN("):
        start_round_mode = "DOWN"
        traversal_direction = "DESCENDING_START_TO_END"
    elif start_formula.startswith("ROUND_UP("):
        start_round_mode = "UP"
        traversal_direction = "ASCENDING_START_TO_END"
    else:
        raise ValueError(f"Unsupported start-strike rounding formula: {rule.start_strike_formula}")
    if end_formula.startswith("ROUND_DOWN("):
        end_round_mode = "DOWN"
    elif end_formula.startswith("ROUND_UP("):
        end_round_mode = "UP"
    else:
        raise ValueError(f"Unsupported end-strike rounding formula: {rule.end_strike_formula}")
    if "+ PARAM(STRIKE_STEP)" in end_formula:
        end_offset_steps = 1
    elif "- PARAM(STRIKE_STEP)" in end_formula:
        end_offset_steps = -1
    else:
        end_offset_steps = 0
    return {
        "start_round_mode": start_round_mode,
        "end_round_mode": end_round_mode,
        "end_offset_steps": end_offset_steps,
        "traversal_direction": traversal_direction,
    }


def _selected_option_runtime_values(candles: Iterable[Any]) -> dict[str, float]:
    completed = tuple(candles)
    if len(completed) < 3:
        raise ValueError("Selected-option historical candles require at least three completed sessions.")
    last2 = completed[-2:]
    last3 = completed[-3:]
    return {
        "OPT_PRV_2DHH": float(max(bar.high for bar in last2)),
        "OPT_PRV_2DLL": float(min(bar.low for bar in last2)),
        "OPT_PRV_3DHH": float(max(bar.high for bar in last3)),
        "OPT_PRV_3DLL": float(min(bar.low for bar in last3)),
    }


def _selected_contract_dict(contract: ActualOptionChainContract) -> dict[str, Any]:
    return {
        "symbol": contract.contract_id,
        "exchange": contract.exchange,
        "underlying": contract.underlying,
        "expiry": contract.expiry.isoformat(),
        "strike": str(contract.strike),
        "option_type": contract.option_type,
        "ltp": str(contract.ltp) if contract.ltp is not None else None,
        "oi": str(contract.oi) if contract.oi is not None else None,
        "oi_unit": contract.oi_unit,
        "bid": str(contract.bid) if contract.bid is not None else None,
        "ask": str(contract.ask) if contract.ask is not None else None,
        "quote_timestamp": contract.quote_timestamp,
        "source_timestamp": contract.source_timestamp,
    }


def _quote_payload_from_contract(contract: ActualOptionChainContract, *, receipt_timestamp: datetime) -> dict[str, Any]:
    return {
        "symbol": contract.contract_id,
        "ltp": str(contract.ltp) if contract.ltp is not None else None,
        "bid": str(contract.bid) if contract.bid is not None else None,
        "ask": str(contract.ask) if contract.ask is not None else None,
        "oi": str(contract.oi) if contract.oi is not None else None,
        "oi_unit": contract.oi_unit,
        "source_timestamp": contract.quote_timestamp or contract.source_timestamp,
        "receipt_timestamp": receipt_timestamp.isoformat(),
        "data_quality": list(contract.data_quality),
    }


def _raw_contract_dict(contract: FyersOptionContractQuote) -> dict[str, Any]:
    return {
        "symbol": contract.symbol,
        "exchange": "NSE",
        "underlying": contract.underlying,
        "expiry": contract.expiry.isoformat(),
        "strike": str(contract.strike),
        "option_type": contract.option_type,
        "tick_size": str(contract.tick_size) if contract.tick_size is not None else None,
        "lot_size": contract.lot_size,
        "bid": str(contract.bid) if contract.bid is not None else None,
        "ask": str(contract.ask) if contract.ask is not None else None,
        "ltp": str(contract.ltp) if contract.ltp is not None else None,
        "oi": str(contract.oi) if contract.oi is not None else None,
        "oi_unit": contract.oi_unit,
        "quote_timestamp": contract.quote_timestamp.isoformat() if contract.quote_timestamp is not None else None,
        "source_quality": contract.source_quality,
    }


def _blocked(
    *,
    instance: EnabledStrategyInstance,
    status: str,
    evidence: str,
    details: Mapping[str, Any],
) -> LiveContractSelectionResult:
    payload = {
        "schema_version": "tfis.live_contract_selection.plan.v1",
        "strategy_definition_id": instance.strategy_definition_id,
        "strategy_instance_id": instance.strategy_instance_id,
        "status": status,
        "details": dict(details),
        "plan_hash": "",
    }
    payload["plan_hash"] = canonical_hash({k: v for k, v in payload.items() if k != "plan_hash"})
    return LiveContractSelectionResult(
        status=status,
        evidence=evidence,
        strategy_instance_id=instance.strategy_instance_id,
        selected_contract=None,
        selected_branch=None,
        selected_option_type=None,
        selected_expiry=None,
        selected_strike=None,
        entry=None,
        target=None,
        original_sl=None,
        monthly_status=str(details.get("monthly_status")) if details.get("monthly_status") is not None else None,
        quote=None,
        option_history_status=str(details.get("option_history_status")) if details.get("option_history_status") is not None else None,
        plan_payload=_json_safe(payload),
    )


def _blocked_decision_from_attempts(attempts: Iterable[Mapping[str, Any]]) -> str:
    decisions = [str(item.get("decision") or "") for item in attempts]
    for preferred in (
        "BLOCKED_PREMIUM_MISSING",
        "BLOCKED_OI_MISSING",
        "BLOCKED_OPTION_CHAIN_UNAVAILABLE",
        "BLOCKED_EXPIRY_EVIDENCE",
        "BLOCKED_CONTRACT_IDENTITY",
    ):
        if preferred in decisions:
            return preferred
    return "NO_QUALIFYING_CONTRACT"


def _blocked_status_from_candidates(candidates: Iterable[Mapping[str, Any]]) -> str:
    for preferred in (
        "BLOCKED_PREMIUM_MISSING",
        "BLOCKED_OI_MISSING",
        "BLOCKED_OPTION_CHAIN_UNAVAILABLE",
        "BLOCKED_EXPIRY_EVIDENCE",
        "BLOCKED_CONTRACT_IDENTITY",
        "BLOCKED_AMBIGUOUS_BRANCH_SELECTION",
    ):
        if any(str(item.get("decision") or "") == preferred for item in candidates):
            return preferred
    return "NO_QUALIFYING_CONTRACT"


def _same_strength(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left.get("qualification_phase") == right.get("qualification_phase")
        and (left.get("selected_contract") or {}).get("strike") == (right.get("selected_contract") or {}).get("strike")
    )


def _historical_blocked_status(status: str) -> str:
    mapping = {
        "BLOCKED_OPTION_CHAIN_UNAVAILABLE": "BLOCKED_CHAIN_STATE_NOT_RECOVERABLE",
        "BLOCKED_PREMIUM_MISSING": "BLOCKED_PREMIUM_HISTORY_MISSING",
        "BLOCKED_OI_MISSING": "BLOCKED_OI_HISTORY_MISSING",
        "BLOCKED_EXPIRY_EVIDENCE": "BLOCKED_CHAIN_STATE_NOT_RECOVERABLE",
        "BLOCKED_UNDERLYING_HISTORY_UNAVAILABLE": "BLOCKED_CHAIN_STATE_NOT_RECOVERABLE",
        "BLOCKED_UNDERLYING_HISTORY_INSUFFICIENT": "BLOCKED_CHAIN_STATE_NOT_RECOVERABLE",
        "BLOCKED_SELECTED_OPTION_HISTORY_UNAVAILABLE": "BLOCKED_PREMIUM_HISTORY_MISSING",
        "BLOCKED_AMBIGUOUS_BRANCH_SELECTION": "BLOCKED_IDENTITY_AMBIGUITY",
    }
    return mapping.get(status, "BLOCKED_CHAIN_STATE_NOT_RECOVERABLE")


def _flatten_rejections(branch_candidates: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    flattened: list[Mapping[str, Any]] = []
    for candidate in branch_candidates:
        if isinstance(candidate.get("rejections"), Iterable) and not isinstance(candidate.get("rejections"), (str, bytes)):
            flattened.extend(item for item in candidate.get("rejections") or () if isinstance(item, Mapping))
            continue
        if isinstance(candidate.get("expiry_attempts"), Iterable) and not isinstance(candidate.get("expiry_attempts"), (str, bytes)):
            for attempt in candidate.get("expiry_attempts") or ():
                if isinstance(attempt, Mapping):
                    for item in attempt.get("rejected_candidates") or ():
                        if isinstance(item, Mapping):
                            flattened.append(item)
    return [_json_safe(item) for item in flattened]


def _augment_historical_plan(
    payload: Mapping[str, Any],
    *,
    recovery_mode: str,
    selection_source: str,
) -> dict[str, Any]:
    plan = dict(_json_safe(payload))
    plan["recovery_mode"] = recovery_mode
    plan["selection_source"] = selection_source
    plan["selection_hash"] = canonical_hash({k: v for k, v in plan.items() if k != "selection_hash"})
    return plan


def _load_s22_selection_report(*, repo_root: Path) -> dict[str, Any]:
    target = repo_root / _S22_REPORT_PATH
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return str(value)
