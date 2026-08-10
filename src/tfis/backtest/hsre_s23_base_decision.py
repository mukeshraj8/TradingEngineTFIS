from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from enum import Enum
from typing import Any, Literal

from tfis.backtest.hsre_market_context import (
    DEFAULT_NIFTY_STRATEGY_ROOT,
    HsreMarketContextPacket,
    NiftyHsreMarketContextBuilder,
    packet_to_dict as market_context_packet_to_dict,
)
from tfis.backtest.hsre_option_references import (
    HsreSelectedContractReferencePacket,
    NiftyHsreSelectedContractReferenceBuilder,
    option_reference_packet_to_dict,
)
from tfis.backtest.nifty_hsre_data_adapter import (
    HsreDataError,
    NiftyHsreHistoricalMarketDataProvider,
    parse_nifty_option_symbol,
)
from tfis.backtest.option_chain import (
    OptionChainContract,
    OptionChainSelector,
    OptionSelectionRequest,
    OptionSelectionResult,
)
from tfis.domain.enums import OptionType
from tfis.domain.strategy_rule import StrategyRule
from tfis.domain.trade_plan import TradePlan
from tfis.formulas import FormulaEngine
from tfis.market_metadata import (
    NIFTY_MINIMUM_OI_LOTS,
    effective_lot_size,
    minimum_oi_units as resolve_minimum_oi_units,
)
from tfis.strategy import StrategyBranchSelector, StrategyEvaluator


HsreS23BaseDecisionStatus = Literal[
    "READY",
    "NO_ACTIVE_BRANCH",
    "NO_QUALIFYING_CONTRACT",
    "INSUFFICIENT_OPTION_LOOKBACK",
    "INSUFFICIENT_MARKET_CONTEXT",
    "EVALUATION_FAILED",
]


@dataclass(frozen=True, slots=True)
class HsreS23CandidateAudit:
    strategy_unique_code: str
    option_type: str
    start_strike: int | None
    end_strike: int | None
    ideal_premium: float | None
    minimum_premium: float | None
    minimum_oi_lots: int
    historical_lot_size: int
    minimum_oi_units: int
    available_expiries: tuple[str, ...]
    attempted_expiries: tuple[str, ...]
    candidate_count: int
    expiry_rejection_count: int
    oi_rejection_count: int
    premium_rejection_count: int
    qualified_count: int
    selection_selected: bool
    selection_reason: str
    selected_symbol: str | None
    option_lookback_status: str | None
    final_status: HsreS23BaseDecisionStatus
    final_reason: str


@dataclass(frozen=True, slots=True)
class HsreS23BaseDecisionPacket:
    session_date: str
    evaluation_timestamp: str
    status: HsreS23BaseDecisionStatus
    status_reason: str
    monthly_status: str | None
    monthly_status_trigger: str | None
    monthly_status_provenance: dict[str, Any]
    resolved_strategy_code: str | None
    resolved_strategy_unique_code: str | None
    strategy_config_paths: tuple[str, ...]
    strategy_config_hashes: dict[str, str]
    underlying_references_used: dict[str, Any]
    current_day_context_through_evaluation: dict[str, Any]
    available_expiries: tuple[str, ...]
    candidate_count: int
    premium_rejection_count: int
    oi_rejection_count: int
    expiry_rejection_count: int
    qualified_count: int
    minimum_oi_lots: int
    historical_lot_size: int | None
    minimum_oi_units: int | None
    selected_symbol: str | None
    selected_expiry: str | None
    selected_strike: int | None
    selected_option_type: str | None
    selected_premium_0916: float | None
    selected_oi_0916: int | None
    selected_volume_0916: int | None
    selected_contract_bid_ask_placeholder: bool
    option_reference_packet: HsreSelectedContractReferencePacket | None
    strategy_evaluator_inputs: dict[str, Any]
    base_entry: float | None
    base_target: float | None
    base_stoploss: float | None
    trade_plan: dict[str, Any] | None
    branch_attempts: tuple[HsreS23CandidateAudit, ...]
    provenance: dict[str, Any]
    no_lookahead_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HsreS23JanuaryDiscovery:
    year: int
    first_attempted_session: str | None
    first_base_order_ready_session: str | None
    accepted_packet_hash: str | None
    attempts: tuple[dict[str, Any], ...]


class HsreS23BaseDecisionBuilder:
    """Build the first historical S23 base-order decision packet from HSRE data."""

    def __init__(
        self,
        provider: NiftyHsreHistoricalMarketDataProvider,
        *,
        strategy_root: str | Path = DEFAULT_NIFTY_STRATEGY_ROOT,
        context_builder: NiftyHsreMarketContextBuilder | None = None,
        reference_builder: NiftyHsreSelectedContractReferenceBuilder | None = None,
        branch_selector: StrategyBranchSelector | None = None,
        option_selector: OptionChainSelector | None = None,
        strategy_evaluator: StrategyEvaluator | None = None,
        formula_engine: FormulaEngine | None = None,
    ) -> None:
        self.provider = provider
        self.strategy_root = Path(strategy_root)
        self.context_builder = context_builder or NiftyHsreMarketContextBuilder(
            provider,
            strategy_root=self.strategy_root,
        )
        self.reference_builder = reference_builder or NiftyHsreSelectedContractReferenceBuilder(provider)
        self.branch_selector = branch_selector or StrategyBranchSelector()
        self.option_selector = option_selector or OptionChainSelector()
        self.strategy_evaluator = strategy_evaluator or StrategyEvaluator()
        self.formula_engine = formula_engine or FormulaEngine()

    def build_for_session(
        self,
        *,
        session_date: date,
        evaluation_time: time = time(9, 16),
    ) -> HsreS23BaseDecisionPacket:
        evaluation_timestamp = datetime.combine(session_date, evaluation_time)
        try:
            context = self.context_builder.build_context(
                session_date=session_date,
                evaluation_time=evaluation_time,
            )
        except HsreDataError as exc:
            return self._minimal_packet(
                session_date=session_date,
                evaluation_timestamp=evaluation_timestamp,
                status="INSUFFICIENT_MARKET_CONTEXT",
                status_reason=str(exc),
            )

        if context.context_status != "READY" or context.market_levels is None:
            return self._packet_from_context(
                context=context,
                status="INSUFFICIENT_MARKET_CONTEXT",
                status_reason=context.status_reason,
                attempts=(),
            )

        strategy_paths = tuple(sorted(path for path in self.strategy_root.iterdir() if path.is_dir()))
        active_rules = tuple(
            sorted(
                self.branch_selector.select(strategy_paths, context.monthly_status or ""),
                key=lambda rule: rule.unique_code,
            )
        )
        if not active_rules:
            return self._packet_from_context(
                context=context,
                status="NO_ACTIVE_BRANCH",
                status_reason=f"No active S23 branch for monthly status {context.monthly_status!r}.",
                attempts=(),
            )

        chain_rows = self.provider.get_option_chain(
            session_date,
            evaluation_time,
            exact=True,
        )
        contracts = [self._chain_observation_to_contract(item) for item in chain_rows]
        available_expiries = tuple(
            expiry.isoformat() for expiry in sorted({item.expiry for item in contracts})
        )

        attempts: list[HsreS23CandidateAudit] = []
        for rule in active_rules:
            attempt = self._attempt_rule(
                context=context,
                rule=rule,
                contracts=contracts,
                evaluation_timestamp=evaluation_timestamp,
                available_expiries=available_expiries,
            )
            attempts.append(attempt[0])
            if attempt[1] is not None:
                return attempt[1]

        status_priority = (
            "INSUFFICIENT_OPTION_LOOKBACK",
            "NO_QUALIFYING_CONTRACT",
            "EVALUATION_FAILED",
        )
        final_status = next(
            (
                status for status in status_priority
                if any(item.final_status == status for item in attempts)
            ),
            attempts[-1].final_status if attempts else "NO_QUALIFYING_CONTRACT",
        )
        return self._packet_from_context(
            context=context,
            status=final_status,
            status_reason="; ".join(item.final_reason for item in attempts),
            attempts=tuple(attempts),
            available_expiries=available_expiries,
        )

    def discover_first_january_base_order(
        self,
        *,
        year: int = 2024,
        evaluation_time: time = time(9, 16),
    ) -> HsreS23JanuaryDiscovery:
        attempts: list[dict[str, Any]] = []
        first_attempted = None
        first_ready = None
        accepted_hash = None
        sessions = [
            item for item in self.provider.available_spot_sessions()
            if item.year == year and item.month == 1
        ]
        for session in sessions:
            packet = self.build_for_session(
                session_date=session,
                evaluation_time=evaluation_time,
            )
            if first_attempted is None:
                first_attempted = session.isoformat()
            attempts.append(
                {
                    "session_date": session.isoformat(),
                    "monthly_status": packet.monthly_status,
                    "branch": packet.resolved_strategy_unique_code
                    or ",".join(item.strategy_unique_code for item in packet.branch_attempts),
                    "contract_selection_result": self._selection_summary(packet),
                    "option_lookback_status": (
                        packet.option_reference_packet.status
                        if packet.option_reference_packet is not None
                        else None
                    ),
                    "final_status": packet.status,
                    "reason": packet.status_reason,
                }
            )
            if packet.status == "READY":
                first_ready = session.isoformat()
                accepted_hash = self.stable_packet_hash(packet)
                break
        return HsreS23JanuaryDiscovery(
            year=year,
            first_attempted_session=first_attempted,
            first_base_order_ready_session=first_ready,
            accepted_packet_hash=accepted_hash,
            attempts=tuple(attempts),
        )

    def _attempt_rule(
        self,
        *,
        context: HsreMarketContextPacket,
        rule: StrategyRule,
        contracts: list[OptionChainContract],
        evaluation_timestamp: datetime,
        available_expiries: tuple[str, ...],
    ) -> tuple[HsreS23CandidateAudit, HsreS23BaseDecisionPacket | None]:
        assert context.market_levels is not None
        if rule.option_type is None:
            audit = self._audit(
                rule=rule,
                available_expiries=available_expiries,
                final_status="EVALUATION_FAILED",
                final_reason="S23 option rule has no option_type.",
            )
            return audit, None
        try:
            session_date = date.fromisoformat(context.session_date)
            lot_size = effective_lot_size(rule.symbol, session_date)
            minimum_oi = resolve_minimum_oi_units(rule.symbol, session_date)
            start_strike = int(
                self.formula_engine.evaluate(
                    rule.start_strike_formula,
                    market_levels=context.market_levels,
                    parameters=rule.parameters,
                )
            )
            end_strike = int(
                self.formula_engine.evaluate(
                    rule.end_strike_formula,
                    market_levels=context.market_levels,
                    parameters=rule.parameters,
                )
            )
            ideal_premium = self.formula_engine.evaluate(
                rule.ideal_premium_formula,
                market_levels=context.market_levels,
                parameters=rule.parameters,
            )
            minimum_premium = self.formula_engine.evaluate(
                rule.minimum_premium_formula,
                market_levels=context.market_levels,
                parameters=rule.parameters,
            )
        except Exception as exc:
            audit = self._audit(
                rule=rule,
                available_expiries=available_expiries,
                final_status="EVALUATION_FAILED",
                final_reason=f"Pre-selection formula evaluation failed: {exc}",
            )
            return audit, None

        request = OptionSelectionRequest(
            option_type=rule.option_type,
            start_strike=start_strike,
            end_strike=end_strike,
            ideal_premium=ideal_premium,
            minimum_premium=minimum_premium,
            minimum_oi=minimum_oi,
            timestamp=evaluation_timestamp,
        )
        stats = self._candidate_stats(request, contracts)
        selection = self.option_selector.select(request, contracts)
        if not selection.selected or selection.selected_contract is None:
            audit = self._audit(
                rule=rule,
                start_strike=start_strike,
                end_strike=end_strike,
                ideal_premium=ideal_premium,
                minimum_premium=minimum_premium,
                historical_lot_size=lot_size,
                minimum_oi_units=minimum_oi,
                available_expiries=available_expiries,
                selection=selection,
                stats=stats,
                final_status="NO_QUALIFYING_CONTRACT",
                final_reason=selection.selection_reason,
            )
            return audit, None

        selected = selection.selected_contract
        identity = parse_nifty_option_symbol(selected.symbol)
        reference_packet = self.reference_builder.build_references(
            session_date=date.fromisoformat(context.session_date),
            identity=identity,
        )
        if reference_packet.status != "READY":
            audit = self._audit(
                rule=rule,
                start_strike=start_strike,
                end_strike=end_strike,
                ideal_premium=ideal_premium,
                minimum_premium=minimum_premium,
                historical_lot_size=lot_size,
                minimum_oi_units=minimum_oi,
                available_expiries=available_expiries,
                selection=selection,
                stats=stats,
                option_lookback_status=reference_packet.status,
                final_status="INSUFFICIENT_OPTION_LOOKBACK",
                final_reason=reference_packet.status_reason,
            )
            return audit, None

        option_snapshot = self.reference_builder.to_option_levels_snapshot(
            reference_packet,
            timestamp=evaluation_timestamp,
        )
        runtime_values = {"OPT_LEVELS": dict(option_snapshot.opt_levels)}
        try:
            trade_plan = self.strategy_evaluator.evaluate(
                rule,
                market_levels=context.market_levels,
                runtime_values=runtime_values,
            )
        except Exception as exc:
            audit = self._audit(
                rule=rule,
                start_strike=start_strike,
                end_strike=end_strike,
                ideal_premium=ideal_premium,
                minimum_premium=minimum_premium,
                historical_lot_size=lot_size,
                minimum_oi_units=minimum_oi,
                available_expiries=available_expiries,
                selection=selection,
                stats=stats,
                option_lookback_status=reference_packet.status,
                final_status="EVALUATION_FAILED",
                final_reason=f"StrategyEvaluator failed: {exc}",
            )
            return audit, None

        audit = self._audit(
            rule=rule,
            start_strike=start_strike,
            end_strike=end_strike,
            ideal_premium=ideal_premium,
            minimum_premium=minimum_premium,
            historical_lot_size=lot_size,
            minimum_oi_units=minimum_oi,
            available_expiries=available_expiries,
            selection=selection,
            stats=stats,
            option_lookback_status=reference_packet.status,
            final_status="READY",
            final_reason="Base S23 decision packet is ready.",
        )
        return audit, self._packet_from_context(
            context=context,
            status="READY",
            status_reason="Base S23 decision packet is ready.",
            rule=rule,
            selected=selected,
            reference_packet=reference_packet,
            runtime_values=runtime_values,
            trade_plan=trade_plan,
            attempts=(audit,),
            available_expiries=available_expiries,
            stats=stats,
        )

    def _packet_from_context(
        self,
        *,
        context: HsreMarketContextPacket,
        status: HsreS23BaseDecisionStatus,
        status_reason: str,
        attempts: tuple[HsreS23CandidateAudit, ...],
        rule: StrategyRule | None = None,
        selected: OptionChainContract | None = None,
        reference_packet: HsreSelectedContractReferencePacket | None = None,
        runtime_values: dict[str, Any] | None = None,
        trade_plan: TradePlan | None = None,
        available_expiries: tuple[str, ...] = (),
        stats: dict[str, int] | None = None,
    ) -> HsreS23BaseDecisionPacket:
        market_levels = context.market_levels
        underlying = {} if market_levels is None else asdict(market_levels)
        active_stats = stats or {}
        config_paths = self._strategy_config_paths(rule) if rule is not None else ()
        packet_session_date = date.fromisoformat(context.session_date)
        packet_lot_size = effective_lot_size("NIFTY", packet_session_date)
        packet_minimum_oi_units = resolve_minimum_oi_units("NIFTY", packet_session_date)
        return HsreS23BaseDecisionPacket(
            session_date=context.session_date,
            evaluation_timestamp=context.evaluation_timestamp,
            status=status,
            status_reason=status_reason,
            monthly_status=context.monthly_status,
            monthly_status_trigger=context.monthly_status_trigger,
            monthly_status_provenance=dict(context.monthly_status_provenance),
            resolved_strategy_code=rule.strategy_code if rule is not None else None,
            resolved_strategy_unique_code=rule.unique_code if rule is not None else None,
            strategy_config_paths=tuple(str(path) for path in config_paths),
            strategy_config_hashes={str(path): self._sha256_file(path) for path in config_paths},
            underlying_references_used=underlying,
            current_day_context_through_evaluation={
                "current_day_high": context.current_day_high_through_evaluation,
                "current_day_low": context.current_day_low_through_evaluation,
                "evaluation_timestamp": context.evaluation_timestamp,
            },
            available_expiries=available_expiries,
            candidate_count=active_stats.get("candidate_count", 0),
            premium_rejection_count=active_stats.get("premium_rejection_count", 0),
            oi_rejection_count=active_stats.get("oi_rejection_count", 0),
            expiry_rejection_count=active_stats.get("expiry_rejection_count", 0),
            qualified_count=active_stats.get("qualified_count", 0),
            minimum_oi_lots=NIFTY_MINIMUM_OI_LOTS,
            historical_lot_size=packet_lot_size,
            minimum_oi_units=packet_minimum_oi_units,
            selected_symbol=selected.symbol if selected is not None else None,
            selected_expiry=selected.expiry.isoformat() if selected is not None else None,
            selected_strike=selected.strike if selected is not None else None,
            selected_option_type=selected.option_type.value if selected is not None else None,
            selected_premium_0916=selected.ltp if selected is not None else None,
            selected_oi_0916=selected.oi if selected is not None else None,
            selected_volume_0916=selected.volume if selected is not None else None,
            selected_contract_bid_ask_placeholder=selected is not None and selected.bid == selected.ask == selected.ltp,
            option_reference_packet=reference_packet,
            strategy_evaluator_inputs={
                "market_levels": underlying,
                "runtime_values": runtime_values or {},
            },
            base_entry=trade_plan.entry_price if trade_plan is not None else None,
            base_target=trade_plan.target_price if trade_plan is not None else None,
            base_stoploss=trade_plan.stoploss_price if trade_plan is not None else None,
            trade_plan=asdict(trade_plan) if trade_plan is not None else None,
            branch_attempts=attempts,
            provenance={
                "market_context": market_context_packet_to_dict(context),
                "option_reference": option_reference_packet_to_dict(reference_packet)
                if reference_packet is not None else None,
                "selection_history_policy": (
                    "Existing OptionChainSelector stops at selected premium/OI "
                    "contract; M2 fails closed if that selected contract lacks "
                    "M1C history because no existing selector rule continues on "
                    "option-history insufficiency."
                ),
            },
            no_lookahead_evidence=(
                "spot_context_limited_to_evaluation_timestamp",
                "option_chain_exact_0916_rows_only",
                "selected_contract_references_use_completed_prior_sessions_only",
                "strategy_evaluator_runtime_values_contain_only_ready_opt_prv_snapshot",
            ),
        )

    def _minimal_packet(
        self,
        *,
        session_date: date,
        evaluation_timestamp: datetime,
        status: HsreS23BaseDecisionStatus,
        status_reason: str,
    ) -> HsreS23BaseDecisionPacket:
        return HsreS23BaseDecisionPacket(
            session_date=session_date.isoformat(),
            evaluation_timestamp=evaluation_timestamp.isoformat(),
            status=status,
            status_reason=status_reason,
            monthly_status=None,
            monthly_status_trigger=None,
            monthly_status_provenance={},
            resolved_strategy_code=None,
            resolved_strategy_unique_code=None,
            strategy_config_paths=(),
            strategy_config_hashes={},
            underlying_references_used={},
            current_day_context_through_evaluation={},
            available_expiries=(),
            candidate_count=0,
            premium_rejection_count=0,
            oi_rejection_count=0,
            expiry_rejection_count=0,
            qualified_count=0,
            minimum_oi_lots=NIFTY_MINIMUM_OI_LOTS,
            historical_lot_size=None,
            minimum_oi_units=None,
            selected_symbol=None,
            selected_expiry=None,
            selected_strike=None,
            selected_option_type=None,
            selected_premium_0916=None,
            selected_oi_0916=None,
            selected_volume_0916=None,
            selected_contract_bid_ask_placeholder=False,
            option_reference_packet=None,
            strategy_evaluator_inputs={},
            base_entry=None,
            base_target=None,
            base_stoploss=None,
            trade_plan=None,
            branch_attempts=(),
            provenance={},
            no_lookahead_evidence=(),
        )

    def _audit(
        self,
        *,
        rule: StrategyRule,
        available_expiries: tuple[str, ...],
        final_status: HsreS23BaseDecisionStatus,
        final_reason: str,
        start_strike: int | None = None,
        end_strike: int | None = None,
        ideal_premium: float | None = None,
        minimum_premium: float | None = None,
        historical_lot_size: int | None = None,
        minimum_oi_units: int | None = None,
        selection: OptionSelectionResult | None = None,
        stats: dict[str, int] | None = None,
        option_lookback_status: str | None = None,
    ) -> HsreS23CandidateAudit:
        stats = stats or {}
        selected = selection.selected_contract if selection is not None else None
        return HsreS23CandidateAudit(
            strategy_unique_code=rule.unique_code,
            option_type=rule.option_type.value if rule.option_type is not None else "",
            start_strike=start_strike,
            end_strike=end_strike,
            ideal_premium=ideal_premium,
            minimum_premium=minimum_premium,
            minimum_oi_lots=NIFTY_MINIMUM_OI_LOTS,
            historical_lot_size=historical_lot_size or 0,
            minimum_oi_units=minimum_oi_units or rule.minimum_oi,
            available_expiries=available_expiries,
            attempted_expiries=tuple(
                item.isoformat() for item in (selection.attempted_expiries if selection else ())
            ),
            candidate_count=stats.get("candidate_count", 0),
            expiry_rejection_count=stats.get("expiry_rejection_count", 0),
            oi_rejection_count=stats.get("oi_rejection_count", 0),
            premium_rejection_count=stats.get("premium_rejection_count", 0),
            qualified_count=stats.get("qualified_count", 0),
            selection_selected=bool(selection.selected) if selection is not None else False,
            selection_reason=selection.selection_reason if selection is not None else "",
            selected_symbol=selected.symbol if selected is not None else None,
            option_lookback_status=option_lookback_status,
            final_status=final_status,
            final_reason=final_reason,
        )

    @staticmethod
    def _candidate_stats(
        request: OptionSelectionRequest,
        contracts: list[OptionChainContract],
    ) -> dict[str, int]:
        timestamp_matches = [
            item for item in contracts if item.timestamp == request.timestamp
        ]
        type_matches = [
            item for item in timestamp_matches if item.option_type == request.option_type
        ]
        expiry_dates = request.expiry_dates or tuple(
            sorted({item.expiry for item in type_matches})[:2]
        )
        expiry_matches = [item for item in type_matches if item.expiry in expiry_dates]
        lower = min(request.start_strike, request.end_strike)
        upper = max(request.start_strike, request.end_strike)
        strike_matches = [item for item in expiry_matches if lower <= item.strike <= upper]
        oi_matches = [item for item in strike_matches if item.oi >= request.minimum_oi]
        premium_matches = [item for item in oi_matches if item.ltp >= request.minimum_premium]
        return {
            "candidate_count": len(type_matches),
            "expiry_rejection_count": len(type_matches) - len(expiry_matches),
            "oi_rejection_count": len(strike_matches) - len(oi_matches),
            "premium_rejection_count": len(oi_matches) - len(premium_matches),
            "qualified_count": len(premium_matches),
        }

    @staticmethod
    def _chain_observation_to_contract(observation: Any) -> OptionChainContract:
        return OptionChainContract(
            timestamp=observation.timestamp,
            symbol=observation.identity.raw_symbol,
            option_type=observation.identity.option_type,
            strike=observation.identity.strike,
            expiry=observation.identity.expiry,
            bid=observation.ltp,
            ask=observation.ltp,
            ltp=observation.ltp,
            oi=observation.oi,
            volume=observation.volume,
        )

    def _strategy_config_paths(self, rule: StrategyRule | None) -> tuple[Path, ...]:
        if rule is None:
            return ()
        strategy_root = self.strategy_root / rule.unique_code
        paths = (
            strategy_root / "strategy.yaml",
            strategy_root / "formulas.yaml",
            strategy_root / "parameters.yaml",
        )
        return tuple(path for path in paths if path.is_file())

    @staticmethod
    def _sha256_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _selection_summary(packet: HsreS23BaseDecisionPacket) -> str:
        if packet.selected_symbol:
            return f"selected {packet.selected_symbol}"
        if packet.branch_attempts:
            return "; ".join(item.selection_reason or item.final_reason for item in packet.branch_attempts)
        return packet.status_reason

    @staticmethod
    def stable_packet_hash(packet: HsreS23BaseDecisionPacket) -> str:
        encoded = json.dumps(
            hsre_s23_base_decision_packet_to_dict(packet, for_hash=True),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def hsre_s23_base_decision_packet_to_dict(
    packet: HsreS23BaseDecisionPacket,
    *,
    for_hash: bool = False,
) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if hasattr(value, "__dataclass_fields__"):
            return {key: convert(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            result = {str(key): convert(item) for key, item in value.items()}
            if for_hash:
                for path_key in ("data_root", "source_files", "strategy_config_paths"):
                    result.pop(path_key, None)
            return result
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if isinstance(value, Enum):
            return value.value
        return value

    payload = convert(packet)
    if for_hash:
        payload.pop("strategy_config_paths", None)
    return payload
