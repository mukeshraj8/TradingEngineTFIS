from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Literal

from tfis.backtest.entry_missed import EntryMissedInput, EntryMissedResult, S23EntryMissedDetector
from tfis.backtest.hsre_option_references import (
    HsreSelectedContractReferencePacket,
    NiftyHsreSelectedContractReferenceBuilder,
    option_reference_packet_to_dict,
)
from tfis.backtest.hsre_s23_base_decision import (
    HsreS23BaseDecisionBuilder,
    HsreS23BaseDecisionPacket,
    hsre_s23_base_decision_packet_to_dict,
)
from tfis.backtest.nifty_hsre_data_adapter import (
    HistoricalOptionIdentity,
    HistoricalOptionMinuteBar,
    HistoricalSpotMinuteBar,
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
from tfis.backtest.recalculation import IntradaySnapshot, RecalculationInput, RecalculationResult, S23RecalculationEngine
from tfis.domain.enums import MonthlyStatus
from tfis.domain.market_levels import MarketLevels
from tfis.domain.strategy_rule import StrategyRule
from tfis.domain.trade_plan import TradePlan
from tfis.importers.yaml_strategy_loader import load_strategy_rule
from tfis.market_metadata import minimum_oi_units


HsreS23FinalDecisionStatus = Literal[
    "NORMAL_ORDER_READY",
    "RECALCULATED_ORDER_READY",
    "NO_QUALIFYING_RECALCULATED_CONTRACT",
    "INSUFFICIENT_RECALCULATED_OPTION_HISTORY",
    "RC_REJECTED",
    "EVIDENCE_INCOMPLETE",
    "BASE_DECISION_NOT_READY",
]


@dataclass(frozen=True, slots=True)
class HsreS23TimingAuthority:
    planning_time: str
    orpt_cutoff: str
    rc_cutoff: str
    effective_order_time: str
    source_strategy_unique_code: str
    source_config_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HsreS23MinuteEvidence:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    source_file: str


@dataclass(frozen=True, slots=True)
class HsreS23SnapshotEvidence:
    cutoff: str
    option_bar: HsreS23MinuteEvidence
    spot_bar: HsreS23MinuteEvidence
    spot_high_through_cutoff: float
    spot_low_through_cutoff: float
    option_high_through_cutoff: float
    option_low_through_cutoff: float
    spot_source_timestamps: tuple[str, ...]
    option_source_timestamps: tuple[str, ...]
    no_lookahead_assertions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HsreS23EntryMissedEvidence:
    rule_name: str
    option_type: str
    base_entry: float
    compared_orpt_option_low: float
    comparison: str
    entry_missed: bool
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HsreS23RecalculatedSelectionAudit:
    search_direction: str
    search_range: str
    premium_rule: str
    oi_rule: str
    candidate_count: int
    expiry_rejected: int
    oi_rejected: int
    premium_rejected: int
    qualified_count: int
    attempted_expiries: tuple[str, ...]
    selection_selected: bool
    selection_reason: str
    selected_symbol: str | None


@dataclass(frozen=True, slots=True)
class HsreS23RecalculationEvidence:
    original_contract: str
    original_strike: int
    original_entry: float
    recalculation_rule: str | None
    recalculation_reason: str
    recalculated_start_strike: int | None
    recalculated_end_strike: int | None
    recalculated_ideal_premium: float | None
    recalculated_minimum_premium: float | None
    recalculated_entry: float | None
    audit_notes: tuple[str, ...]
    selection_audit: HsreS23RecalculatedSelectionAudit | None


@dataclass(frozen=True, slots=True)
class HsreS23RcEvidence:
    rc_snapshot: HsreS23SnapshotEvidence
    exact_comparator_or_rule_used: str
    rc_passed: bool
    rc_result: str


@dataclass(frozen=True, slots=True)
class HsreS23FinalOrderDecisionPacket:
    session_date: str
    monthly_status: str | None
    branch: str | None
    status: HsreS23FinalDecisionStatus
    status_reason: str
    timing_authority: HsreS23TimingAuthority | None
    base_packet_hash: str | None
    base_contract: str | None
    base_entry: float | None
    base_target: float | None
    base_stoploss: float | None
    orpt_evidence: HsreS23SnapshotEvidence | None
    entry_missed_result: HsreS23EntryMissedEvidence | None
    recalculation_required: bool
    recalculation_inputs: dict[str, Any]
    recalculation_result: HsreS23RecalculationEvidence | None
    recalculated_contract: str | None
    recalculated_option_reference_packet: HsreSelectedContractReferencePacket | None
    rc_required: bool
    rc_evidence: HsreS23RcEvidence | None
    final_effective_contract: str | None
    final_effective_entry: float | None
    final_effective_target: float | None
    final_effective_stoploss: float | None
    final_decision_verdict: str
    provenance: dict[str, Any]
    no_lookahead_evidence: tuple[str, ...]


class HsreS23FinalOrderDecisionBuilder:
    """Build a historical S23 final-order decision without fill or lifecycle simulation."""

    def __init__(
        self,
        provider: NiftyHsreHistoricalMarketDataProvider,
        *,
        base_decision_builder: HsreS23BaseDecisionBuilder | None = None,
        reference_builder: NiftyHsreSelectedContractReferenceBuilder | None = None,
        entry_missed_detector: S23EntryMissedDetector | None = None,
        recalculation_engine: S23RecalculationEngine | None = None,
        option_selector: OptionChainSelector | None = None,
    ) -> None:
        self.provider = provider
        self.base_decision_builder = base_decision_builder or HsreS23BaseDecisionBuilder(provider)
        self.reference_builder = reference_builder or NiftyHsreSelectedContractReferenceBuilder(provider)
        self.entry_missed_detector = entry_missed_detector or S23EntryMissedDetector()
        self.recalculation_engine = recalculation_engine or S23RecalculationEngine()
        self.option_selector = option_selector or OptionChainSelector()

    def build_for_session(
        self,
        *,
        session_date: date,
        planning_time: time = time(9, 16),
    ) -> HsreS23FinalOrderDecisionPacket:
        base_packet = self.base_decision_builder.build_for_session(
            session_date=session_date,
            evaluation_time=planning_time,
        )
        return self.build_from_base_packet(base_packet, planning_time=planning_time)

    def build_from_base_packet(
        self,
        base_packet: HsreS23BaseDecisionPacket,
        *,
        planning_time: time = time(9, 16),
    ) -> HsreS23FinalOrderDecisionPacket:
        if base_packet.status != "READY":
            return self._minimal_packet(
                base_packet=base_packet,
                status="BASE_DECISION_NOT_READY",
                status_reason=base_packet.status_reason,
            )
        if base_packet.selected_symbol is None or base_packet.trade_plan is None:
            return self._minimal_packet(
                base_packet=base_packet,
                status="BASE_DECISION_NOT_READY",
                status_reason="Base packet is READY but lacks selected contract or trade plan.",
            )

        rule = self._load_rule(base_packet)
        timing = self._timing_authority(rule, planning_time)
        session_date = date.fromisoformat(base_packet.session_date)
        identity = parse_nifty_option_symbol(base_packet.selected_symbol)
        market_levels = self._market_levels(base_packet)
        option_levels = self._option_levels(base_packet)
        base_trade_plan = self._trade_plan(base_packet, rule)

        try:
            orpt_evidence = self._snapshot_evidence(
                session_date=session_date,
                identity=identity,
                cutoff=rule.entry_time,
            )
        except HsreDataError as exc:
            return self._minimal_packet(
                base_packet=base_packet,
                status="EVIDENCE_INCOMPLETE",
                status_reason=str(exc),
                rule=rule,
                timing=timing,
            )

        orpt_snapshot = self._intraday_snapshot(orpt_evidence)
        entry_missed = self.entry_missed_detector.detect(
            EntryMissedInput(
                option_type=rule.option_type,
                entry_price=base_trade_plan.entry_price,
                orpt_snapshot=orpt_snapshot,
            )
        )
        entry_evidence = self._entry_evidence(
            option_type=rule.option_type.value if rule.option_type is not None else "",
            base_entry=base_trade_plan.entry_price,
            result=entry_missed,
        )
        if not entry_missed.entry_missed:
            return self._packet(
                base_packet=base_packet,
                rule=rule,
                timing=timing,
                status="NORMAL_ORDER_READY",
                status_reason="Base entry was not missed at ORPT; final order remains the base order.",
                orpt_evidence=orpt_evidence,
                entry_missed_result=entry_evidence,
                recalculation_required=False,
                recalculation_inputs={},
                recalculation_result=None,
                recalculated_contract=None,
                recalculated_reference_packet=None,
                rc_required=False,
                rc_evidence=None,
                final_contract=base_packet.selected_symbol,
                final_entry=base_trade_plan.entry_price,
                final_target=base_trade_plan.target_price,
                final_stoploss=base_trade_plan.stoploss_price,
                verdict="NORMAL_ORDER_READY",
            )

        try:
            rc_snapshot_evidence = self._snapshot_evidence(
                session_date=session_date,
                identity=identity,
                cutoff=rule.recalculation_time,
            )
        except HsreDataError as exc:
            return self._packet(
                base_packet=base_packet,
                rule=rule,
                timing=timing,
                status="EVIDENCE_INCOMPLETE",
                status_reason=str(exc),
                orpt_evidence=orpt_evidence,
                entry_missed_result=entry_evidence,
                recalculation_required=True,
                recalculation_inputs={},
                recalculation_result=None,
                recalculated_contract=None,
                recalculated_reference_packet=None,
                rc_required=True,
                rc_evidence=None,
                final_contract=None,
                final_entry=None,
                final_target=None,
                final_stoploss=None,
                verdict="EVIDENCE_INCOMPLETE",
            )

        rc_snapshot = self._intraday_snapshot(rc_snapshot_evidence)
        recalculation = self.recalculation_engine.recalculate(
            RecalculationInput(
                branch_unique_code=rule.unique_code,
                option_type=rule.option_type,
                monthly_status=MonthlyStatus(base_packet.monthly_status or "UNKNOWN"),
                base_trade_plan=base_trade_plan,
                market_levels=market_levels,
                option_levels=option_levels,
                parameters=rule.parameters,
                intraday_snapshot_at_orpt=orpt_snapshot,
                intraday_snapshot_at_recalc=rc_snapshot,
                entry_missed=True,
            )
        )
        rc_evidence = HsreS23RcEvidence(
            rc_snapshot=rc_snapshot_evidence,
            exact_comparator_or_rule_used=(
                recalculation.source_rule
                or "S23 recalculation engine returned no recalculated rule."
            ),
            rc_passed=bool(recalculation.recalculated),
            rc_result=recalculation.reason,
        )
        if not recalculation.recalculated:
            return self._packet(
                base_packet=base_packet,
                rule=rule,
                timing=timing,
                status="RC_REJECTED",
                status_reason=recalculation.reason,
                orpt_evidence=orpt_evidence,
                entry_missed_result=entry_evidence,
                recalculation_required=True,
                recalculation_inputs=self._recalculation_inputs(orpt_snapshot, rc_snapshot),
                recalculation_result=self._recalculation_evidence(
                    base_packet=base_packet,
                    recalculation=recalculation,
                    selection_audit=None,
                ),
                recalculated_contract=None,
                recalculated_reference_packet=None,
                rc_required=True,
                rc_evidence=rc_evidence,
                final_contract=None,
                final_entry=None,
                final_target=None,
                final_stoploss=None,
                verdict="RC_REJECTED",
            )

        contracts = [
            HsreS23BaseDecisionBuilder._chain_observation_to_contract(item)
            for item in self.provider.get_option_chain(
                session_date,
                rule.recalculation_time,
                exact=True,
            )
        ]
        request = OptionSelectionRequest(
            option_type=rule.option_type,
            start_strike=self._required_int(recalculation.recalculated_start_strike, "start_strike"),
            end_strike=self._required_int(recalculation.recalculated_end_strike, "end_strike"),
            ideal_premium=self._required_float(
                recalculation.recalculated_ideal_premium,
                "ideal_premium",
            ),
            minimum_premium=self._required_float(
                recalculation.recalculated_minimum_premium,
                "minimum_premium",
            ),
            minimum_oi=minimum_oi_units(rule.symbol, session_date),
            timestamp=datetime.combine(session_date, rule.recalculation_time),
        )
        stats = HsreS23BaseDecisionBuilder._candidate_stats(request, contracts)
        selection = self.option_selector.select(request, contracts)
        selection_audit = self._selection_audit(request, stats, selection)
        recalculation_evidence = self._recalculation_evidence(
            base_packet=base_packet,
            recalculation=recalculation,
            selection_audit=selection_audit,
        )
        if not selection.selected or selection.selected_contract is None:
            return self._packet(
                base_packet=base_packet,
                rule=rule,
                timing=timing,
                status="NO_QUALIFYING_RECALCULATED_CONTRACT",
                status_reason=selection.selection_reason,
                orpt_evidence=orpt_evidence,
                entry_missed_result=entry_evidence,
                recalculation_required=True,
                recalculation_inputs=self._recalculation_inputs(orpt_snapshot, rc_snapshot),
                recalculation_result=recalculation_evidence,
                recalculated_contract=None,
                recalculated_reference_packet=None,
                rc_required=True,
                rc_evidence=rc_evidence,
                final_contract=None,
                final_entry=None,
                final_target=None,
                final_stoploss=None,
                verdict="NO_QUALIFYING_RECALCULATED_CONTRACT",
            )

        selected = selection.selected_contract
        selected_identity = parse_nifty_option_symbol(selected.symbol)
        reference_packet = None
        if not self._same_identity(identity, selected_identity):
            reference_packet = self.reference_builder.build_references(
                session_date=session_date,
                identity=selected_identity,
            )
            if reference_packet.status != "READY":
                return self._packet(
                    base_packet=base_packet,
                    rule=rule,
                    timing=timing,
                    status="INSUFFICIENT_RECALCULATED_OPTION_HISTORY",
                    status_reason=reference_packet.status_reason,
                    orpt_evidence=orpt_evidence,
                    entry_missed_result=entry_evidence,
                    recalculation_required=True,
                    recalculation_inputs=self._recalculation_inputs(orpt_snapshot, rc_snapshot),
                    recalculation_result=recalculation_evidence,
                    recalculated_contract=selected.symbol,
                    recalculated_reference_packet=reference_packet,
                    rc_required=True,
                    rc_evidence=rc_evidence,
                    final_contract=None,
                    final_entry=None,
                    final_target=None,
                    final_stoploss=None,
                    verdict="INSUFFICIENT_RECALCULATED_OPTION_HISTORY",
                )

        final_entry = self._required_float(recalculation.recalculated_entry_price, "entry")
        final_target = self._target_from_entry(final_entry, rule)
        final_stoploss = self._stoploss_from_entry_and_rc(final_entry, rc_snapshot.option_high, rule)
        return self._packet(
            base_packet=base_packet,
            rule=rule,
            timing=timing,
            status="RECALCULATED_ORDER_READY",
            status_reason="Entry was missed at ORPT; RC recalculation selected a final order contract.",
            orpt_evidence=orpt_evidence,
            entry_missed_result=entry_evidence,
            recalculation_required=True,
            recalculation_inputs=self._recalculation_inputs(orpt_snapshot, rc_snapshot),
            recalculation_result=recalculation_evidence,
            recalculated_contract=selected.symbol,
            recalculated_reference_packet=reference_packet,
            rc_required=True,
            rc_evidence=rc_evidence,
            final_contract=selected.symbol,
            final_entry=final_entry,
            final_target=final_target,
            final_stoploss=final_stoploss,
            verdict="RECALCULATED_ORDER_READY",
        )

    @staticmethod
    def stable_packet_hash(packet: HsreS23FinalOrderDecisionPacket) -> str:
        encoded = json.dumps(
            hsre_s23_final_order_decision_packet_to_dict(packet, for_hash=True),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _snapshot_evidence(
        self,
        *,
        session_date: date,
        identity: HistoricalOptionIdentity,
        cutoff: time,
    ) -> HsreS23SnapshotEvidence:
        spot_bars = self.provider.get_spot_bars_through(session_date, cutoff)
        option_bars = tuple(
            bar for bar in self.provider.get_contract_session_bars(session_date, identity)
            if bar.timestamp <= datetime.combine(session_date, cutoff)
        )
        if not spot_bars:
            raise HsreDataError(
                f"No spot bars available through {cutoff.isoformat()} for {session_date.isoformat()}"
            )
        if not option_bars:
            raise HsreDataError(
                f"No option bars for {identity.raw_symbol} through {cutoff.isoformat()} on {session_date.isoformat()}"
            )
        cutoff_ts = datetime.combine(session_date, cutoff)
        spot_bar = self._bar_at_or_before(spot_bars, cutoff_ts)
        option_bar = self._bar_at_or_before(option_bars, cutoff_ts)
        return HsreS23SnapshotEvidence(
            cutoff=cutoff_ts.isoformat(),
            option_bar=self._option_evidence(option_bar),
            spot_bar=self._spot_evidence(spot_bar),
            spot_high_through_cutoff=max(bar.high for bar in spot_bars),
            spot_low_through_cutoff=min(bar.low for bar in spot_bars),
            option_high_through_cutoff=max(bar.high for bar in option_bars),
            option_low_through_cutoff=min(bar.low for bar in option_bars),
            spot_source_timestamps=tuple(bar.timestamp.isoformat() for bar in spot_bars),
            option_source_timestamps=tuple(bar.timestamp.isoformat() for bar in option_bars),
            no_lookahead_assertions=(
                f"spot_rows_limited_to_timestamp_lte_{cutoff_ts.isoformat()}",
                f"option_rows_limited_to_timestamp_lte_{cutoff_ts.isoformat()}",
            ),
        )

    @staticmethod
    def _bar_at_or_before(
        bars: tuple[HistoricalSpotMinuteBar, ...] | tuple[HistoricalOptionMinuteBar, ...],
        cutoff: datetime,
    ) -> HistoricalSpotMinuteBar | HistoricalOptionMinuteBar:
        eligible = [bar for bar in bars if bar.timestamp <= cutoff]
        if not eligible:
            raise HsreDataError(f"No bar at or before {cutoff.isoformat()}")
        return sorted(eligible, key=lambda bar: bar.timestamp)[-1]

    @staticmethod
    def _intraday_snapshot(evidence: HsreS23SnapshotEvidence) -> IntradaySnapshot:
        return IntradaySnapshot(
            timestamp=datetime.fromisoformat(evidence.cutoff),
            spot_low=evidence.spot_bar.low,
            spot_high=evidence.spot_bar.high,
            option_low=evidence.option_bar.low,
            option_high=evidence.option_bar.high,
        )

    @staticmethod
    def _option_evidence(bar: HistoricalOptionMinuteBar) -> HsreS23MinuteEvidence:
        return HsreS23MinuteEvidence(
            timestamp=bar.timestamp.isoformat(),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            source_file=str(bar.source_file),
        )

    @staticmethod
    def _spot_evidence(bar: HistoricalSpotMinuteBar) -> HsreS23MinuteEvidence:
        return HsreS23MinuteEvidence(
            timestamp=bar.timestamp.isoformat(),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            source_file=str(bar.source_file),
        )

    def _packet(
        self,
        *,
        base_packet: HsreS23BaseDecisionPacket,
        rule: StrategyRule,
        timing: HsreS23TimingAuthority,
        status: HsreS23FinalDecisionStatus,
        status_reason: str,
        orpt_evidence: HsreS23SnapshotEvidence,
        entry_missed_result: HsreS23EntryMissedEvidence,
        recalculation_required: bool,
        recalculation_inputs: dict[str, Any],
        recalculation_result: HsreS23RecalculationEvidence | None,
        recalculated_contract: str | None,
        recalculated_reference_packet: HsreSelectedContractReferencePacket | None,
        rc_required: bool,
        rc_evidence: HsreS23RcEvidence | None,
        final_contract: str | None,
        final_entry: float | None,
        final_target: float | None,
        final_stoploss: float | None,
        verdict: str,
    ) -> HsreS23FinalOrderDecisionPacket:
        return HsreS23FinalOrderDecisionPacket(
            session_date=base_packet.session_date,
            monthly_status=base_packet.monthly_status,
            branch=base_packet.resolved_strategy_unique_code,
            status=status,
            status_reason=status_reason,
            timing_authority=timing,
            base_packet_hash=self.base_decision_builder.stable_packet_hash(base_packet),
            base_contract=base_packet.selected_symbol,
            base_entry=base_packet.base_entry,
            base_target=base_packet.base_target,
            base_stoploss=base_packet.base_stoploss,
            orpt_evidence=orpt_evidence,
            entry_missed_result=entry_missed_result,
            recalculation_required=recalculation_required,
            recalculation_inputs=recalculation_inputs,
            recalculation_result=recalculation_result,
            recalculated_contract=recalculated_contract,
            recalculated_option_reference_packet=recalculated_reference_packet,
            rc_required=rc_required,
            rc_evidence=rc_evidence,
            final_effective_contract=final_contract,
            final_effective_entry=final_entry,
            final_effective_target=final_target,
            final_effective_stoploss=final_stoploss,
            final_decision_verdict=verdict,
            provenance={
                "base_packet": hsre_s23_base_decision_packet_to_dict(base_packet),
                "business_components_reused": (
                    "HsreS23BaseDecisionBuilder",
                    "S23EntryMissedDetector",
                    "S23RecalculationEngine",
                    "OptionChainSelector",
                    "NiftyHsreSelectedContractReferenceBuilder",
                ),
            },
            no_lookahead_evidence=(
                "orpt_option_and_spot_inputs_limited_to_orpt_cutoff",
                "rc_option_and_spot_inputs_limited_to_rc_cutoff",
                "recalculated_option_chain_selection_uses_exact_rc_timestamp",
                "recalculated_opt_prv_rebuild_excludes_current_session_when_contract_changes",
                "no_fill_lifecycle_or_pnl_simulation_performed",
            ),
        )

    def _minimal_packet(
        self,
        *,
        base_packet: HsreS23BaseDecisionPacket,
        status: HsreS23FinalDecisionStatus,
        status_reason: str,
        rule: StrategyRule | None = None,
        timing: HsreS23TimingAuthority | None = None,
    ) -> HsreS23FinalOrderDecisionPacket:
        return HsreS23FinalOrderDecisionPacket(
            session_date=base_packet.session_date,
            monthly_status=base_packet.monthly_status,
            branch=base_packet.resolved_strategy_unique_code,
            status=status,
            status_reason=status_reason,
            timing_authority=timing,
            base_packet_hash=self.base_decision_builder.stable_packet_hash(base_packet)
            if base_packet.status == "READY" else None,
            base_contract=base_packet.selected_symbol,
            base_entry=base_packet.base_entry,
            base_target=base_packet.base_target,
            base_stoploss=base_packet.base_stoploss,
            orpt_evidence=None,
            entry_missed_result=None,
            recalculation_required=False,
            recalculation_inputs={},
            recalculation_result=None,
            recalculated_contract=None,
            recalculated_option_reference_packet=None,
            rc_required=False,
            rc_evidence=None,
            final_effective_contract=None,
            final_effective_entry=None,
            final_effective_target=None,
            final_effective_stoploss=None,
            final_decision_verdict=status,
            provenance={
                "rule_loaded": rule.unique_code if rule is not None else None,
                "base_packet": hsre_s23_base_decision_packet_to_dict(base_packet),
            },
            no_lookahead_evidence=(),
        )

    def _load_rule(self, base_packet: HsreS23BaseDecisionPacket) -> StrategyRule:
        if not base_packet.resolved_strategy_unique_code:
            raise HsreDataError("Base packet has no resolved strategy branch.")
        for path in base_packet.strategy_config_paths:
            config_path = Path(path)
            if config_path.name == "strategy.yaml":
                return load_strategy_rule(config_path.parent)
        return load_strategy_rule(self._strategy_dir(base_packet.resolved_strategy_unique_code))

    @staticmethod
    def _market_levels(base_packet: HsreS23BaseDecisionPacket) -> MarketLevels:
        return MarketLevels(**base_packet.underlying_references_used)

    @staticmethod
    def _option_levels(base_packet: HsreS23BaseDecisionPacket) -> dict[str, float]:
        levels = base_packet.strategy_evaluator_inputs.get("runtime_values", {}).get("OPT_LEVELS")
        if not isinstance(levels, dict):
            raise HsreDataError("Base packet lacks OPT_LEVELS runtime values.")
        return {str(key): float(value) for key, value in levels.items()}

    @staticmethod
    def _trade_plan(base_packet: HsreS23BaseDecisionPacket, rule: StrategyRule) -> TradePlan:
        if base_packet.trade_plan is None:
            raise HsreDataError("Base packet lacks trade_plan.")
        return TradePlan(
            strategy_code=str(base_packet.trade_plan["strategy_code"]),
            symbol=str(base_packet.trade_plan["symbol"]),
            option_type=rule.option_type,
            start_strike=base_packet.trade_plan["start_strike"],
            end_strike=base_packet.trade_plan["end_strike"],
            ideal_premium=base_packet.trade_plan["ideal_premium"],
            minimum_premium=base_packet.trade_plan["minimum_premium"],
            entry_price=float(base_packet.trade_plan["entry_price"]),
            stoploss_price=float(base_packet.trade_plan["stoploss_price"]),
            target_price=float(base_packet.trade_plan["target_price"]),
        )

    @staticmethod
    def _timing_authority(rule: StrategyRule, planning_time: time) -> HsreS23TimingAuthority:
        strategy_dir = HsreS23FinalOrderDecisionBuilder._strategy_dir(rule.unique_code)
        paths = tuple(
            str(path)
            for path in (
                strategy_dir / "strategy.yaml",
                strategy_dir / "formulas.yaml",
                strategy_dir / "parameters.yaml",
            )
            if path.exists()
        )
        return HsreS23TimingAuthority(
            planning_time=planning_time.isoformat(),
            orpt_cutoff=rule.entry_time.isoformat(),
            rc_cutoff=rule.recalculation_time.isoformat(),
            effective_order_time=rule.entry_time.isoformat(),
            source_strategy_unique_code=rule.unique_code,
            source_config_paths=paths,
        )

    @staticmethod
    def _strategy_dir(unique_code: str) -> Path:
        strategy_root = Path("config") / "strategies" / "options_sell" / "nifty"
        direct = strategy_root / unique_code
        if direct.exists():
            return direct
        prefixed = strategy_root / f"S23_{unique_code}"
        if prefixed.exists():
            return prefixed
        return direct

    @staticmethod
    def _entry_evidence(
        *,
        option_type: str,
        base_entry: float,
        result: EntryMissedResult,
    ) -> HsreS23EntryMissedEvidence:
        return HsreS23EntryMissedEvidence(
            rule_name=result.rule_name,
            option_type=option_type,
            base_entry=base_entry,
            compared_orpt_option_low=result.compared_value,
            comparison=f"{result.compared_value} < {base_entry}",
            entry_missed=result.entry_missed,
            notes=result.notes,
        )

    @staticmethod
    def _selection_audit(
        request: OptionSelectionRequest,
        stats: dict[str, int],
        selection: OptionSelectionResult,
    ) -> HsreS23RecalculatedSelectionAudit:
        return HsreS23RecalculatedSelectionAudit(
            search_direction="descending" if request.start_strike > request.end_strike else "ascending",
            search_range=f"{request.start_strike}-{request.end_strike}",
            premium_rule=(
                f"ideal >= {request.ideal_premium}; minimum >= {request.minimum_premium}"
            ),
            oi_rule=f"oi >= {request.minimum_oi}",
            candidate_count=stats.get("candidate_count", 0),
            expiry_rejected=stats.get("expiry_rejection_count", 0),
            oi_rejected=stats.get("oi_rejection_count", 0),
            premium_rejected=stats.get("premium_rejection_count", 0),
            qualified_count=stats.get("qualified_count", 0),
            attempted_expiries=tuple(item.isoformat() for item in selection.attempted_expiries),
            selection_selected=selection.selected,
            selection_reason=selection.selection_reason,
            selected_symbol=selection.selected_contract.symbol
            if selection.selected_contract is not None else None,
        )

    @staticmethod
    def _recalculation_evidence(
        *,
        base_packet: HsreS23BaseDecisionPacket,
        recalculation: RecalculationResult,
        selection_audit: HsreS23RecalculatedSelectionAudit | None,
    ) -> HsreS23RecalculationEvidence:
        return HsreS23RecalculationEvidence(
            original_contract=str(base_packet.selected_symbol),
            original_strike=int(base_packet.selected_strike or 0),
            original_entry=float(base_packet.base_entry or 0.0),
            recalculation_rule=recalculation.source_rule,
            recalculation_reason=recalculation.reason,
            recalculated_start_strike=recalculation.recalculated_start_strike,
            recalculated_end_strike=recalculation.recalculated_end_strike,
            recalculated_ideal_premium=recalculation.recalculated_ideal_premium,
            recalculated_minimum_premium=recalculation.recalculated_minimum_premium,
            recalculated_entry=recalculation.recalculated_entry_price,
            audit_notes=recalculation.audit_notes,
            selection_audit=selection_audit,
        )

    @staticmethod
    def _recalculation_inputs(
        orpt_snapshot: IntradaySnapshot,
        rc_snapshot: IntradaySnapshot,
    ) -> dict[str, Any]:
        return {
            "orpt_snapshot": asdict(orpt_snapshot),
            "rc_snapshot": asdict(rc_snapshot),
        }

    @staticmethod
    def _target_from_entry(entry: float, rule: StrategyRule) -> float:
        return entry * (1.0 - float(rule.parameters["target_pct"]) / 100.0)

    @staticmethod
    def _stoploss_from_entry_and_rc(entry: float, rc_option_high: float, rule: StrategyRule) -> float:
        return min(
            entry * (1.0 + float(rule.parameters["sl_entry_pct"]) / 100.0),
            rc_option_high * (1.0 + float(rule.parameters.get("sl_reference_pct", 0.0)) / 100.0),
        )

    @staticmethod
    def _required_float(value: float | None, name: str) -> float:
        if value is None:
            raise HsreDataError(f"Missing recalculated {name}")
        return float(value)

    @staticmethod
    def _required_int(value: int | None, name: str) -> int:
        if value is None:
            raise HsreDataError(f"Missing recalculated {name}")
        return int(value)

    @staticmethod
    def _same_identity(left: HistoricalOptionIdentity, right: HistoricalOptionIdentity) -> bool:
        return (
            left.underlying == right.underlying
            and left.expiry == right.expiry
            and left.strike == right.strike
            and left.option_type is right.option_type
        )


def hsre_s23_final_order_decision_packet_to_dict(
    packet: HsreS23FinalOrderDecisionPacket,
    *,
    for_hash: bool = False,
) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if hasattr(value, "__dataclass_fields__"):
            return {key: convert(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            result = {str(key): convert(item) for key, item in value.items()}
            if for_hash:
                for path_key in ("source_file", "source_files", "source_config_paths", "strategy_config_paths", "data_root"):
                    result.pop(path_key, None)
            return result
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value

    payload = convert(packet)
    if for_hash:
        timing = payload.get("timing_authority")
        if isinstance(timing, dict):
            timing.pop("source_config_paths", None)
    return payload
