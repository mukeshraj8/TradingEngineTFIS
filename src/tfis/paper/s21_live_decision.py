from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

from tfis.domain import StrategyRule, TradePlan
from tfis.domain.enums import OptionType
from tfis.rules import get_s21_leg_rule
from tfis.strategy import StrategyEvaluator

from .contract_selection import (
    PaperContractSelectionFailureCode,
    S23PaperContractSelectionRanking,
    S23PaperContractSelectionResult,
)
from .fyers_snapshot_collector import (
    PaperCollectedSnapshotInputs,
)
from .lifecycle_runtime_config import (
    PaperLifecycleBrokerConfig,
    build_paper_broker_adapter_from_broker_config,
)
from .live_decision import (
    S23PaperLiveDecisionBuilder,
    S23PaperLiveDecisionError,
    S23PaperLiveDecisionResult,
)
from .live_ingress import PaperLiveIngressConfig
from .live_prelude import (
    PaperLivePreludeBuilder,
    PaperLivePreludeRequest,
)
from .models import OptionChainContract, OptionChainSnapshotEvent, SnapshotLabel
from .position_state import PaperPositionState
from .runtime_input_derivation import PaperDecisionReferencePacket


class S21HistoricalOptionReferenceProvider:
    """Fetch and cache completed prior-session option HH/LL references for S21.

    The provider is S21-specific by design. S23 never calls it.
    """

    def __init__(self, *, config_path: str) -> None:
        self._config_path = str(config_path)
        self._cache: dict[tuple[date, str], dict[str, float] | None] = {}

    def get_many(
        self,
        *,
        contracts: tuple[OptionChainContract, ...],
        session_date: date,
    ) -> dict[str, dict[str, float]]:
        missing = tuple(
            contract for contract in contracts
            if (session_date, contract.symbol) not in self._cache
        )
        if missing:
            self._fetch_missing(missing, session_date=session_date)
        return {
            contract.symbol: refs
            for contract in contracts
            if (refs := self._cache.get((session_date, contract.symbol))) is not None
        }

    def get_cached(self, *, symbol: str, session_date: date) -> dict[str, float] | None:
        return self._cache.get((session_date, symbol))

    def _fetch_missing(
        self,
        contracts: tuple[OptionChainContract, ...],
        *,
        session_date: date,
    ) -> None:
        config = PaperLiveIngressConfig.from_yaml(self._config_path)
        adapter = build_paper_broker_adapter_from_broker_config(
            PaperLifecycleBrokerConfig(
                provider=config.broker.provider,
                timezone=config.broker.timezone,
                payload_fixture_path=config.broker.payload_fixture_path,
                capture_stream_events=config.broker.capture_stream_events,
                option_chain_strike_count=config.broker.option_chain_strike_count,
            )
        )
        adapter.connect()
        try:
            if not hasattr(adapter, "get_daily_bars_for_symbol") or not hasattr(
                adapter, "to_fyers_option_symbol"
            ):
                for contract in contracts:
                    self._cache[(session_date, contract.symbol)] = None
                return
            for contract in contracts:
                key = (session_date, contract.symbol)
                try:
                    raw_symbol = adapter.to_fyers_option_symbol(contract.symbol)  # type: ignore[attr-defined]
                    bars = adapter.get_daily_bars_for_symbol(  # type: ignore[attr-defined]
                        raw_symbol=raw_symbol,
                        normalized_symbol=contract.symbol,
                        session_date=session_date,
                        lookback_days=14,
                        continuous=False,
                    )
                    completed = tuple(
                        bar for bar in bars
                        if bar.bar_start.date() < session_date
                        and bar.high is not None
                        and bar.low is not None
                    )
                    if len(completed) < 3:
                        self._cache[key] = None
                        continue
                    last2 = completed[-2:]
                    last3 = completed[-3:]
                    self._cache[key] = {
                        "OPT_PRV_2DHH": max(float(bar.high) for bar in last2),
                        "OPT_PRV_2DLL": min(float(bar.low) for bar in last2),
                        "OPT_PRV_3DHH": max(float(bar.high) for bar in last3),
                        "OPT_PRV_3DLL": min(float(bar.low) for bar in last3),
                    }
                except Exception:
                    # Candidate-specific history failure rejects only that candidate.
                    self._cache[key] = None
        finally:
            adapter.disconnect()


class S21PaperLivePreludeBuilder(PaperLivePreludeBuilder):
    """S21-only prelude builder with rule-book candidate qualification."""

    def __init__(
        self,
        *,
        reference_provider: S21HistoricalOptionReferenceProvider,
        strategy_evaluator: StrategyEvaluator | None = None,
    ) -> None:
        super().__init__(strategy_evaluator=strategy_evaluator)
        self._reference_provider = reference_provider
        self._s21_strategy_evaluator = strategy_evaluator or StrategyEvaluator()

    def build(self, request: PaperLivePreludeRequest):
        if request.strategy_rule.strategy_code != "S21":
            return super().build(request)

        first = super().build(request)
        selection = first.contract_selection
        if selection is None or not selection.selected or selection.selected_contract is None:
            return first

        selected_refs = self._reference_provider.get_cached(
            symbol=selection.selected_contract.symbol,
            session_date=request.session_context.session_date,
        )
        if not selected_refs:
            return first

        runtime_values = dict(request.runtime_values)
        runtime_values.update(selected_refs)
        corrected_plan = self._s21_strategy_evaluator.evaluate(
            request.strategy_rule,
            market_levels=request.market_levels,
            runtime_values=runtime_values,
        )
        return super().build(
            replace(
                request,
                runtime_values=runtime_values,
                trade_plan_override=corrected_plan,
            )
        )

    def _select_contract(
        self,
        request: PaperLivePreludeRequest,
        trade_plan: TradePlan,
    ) -> S23PaperContractSelectionResult:
        if request.strategy_rule.strategy_code != "S21":
            return super()._select_contract(request, trade_plan)

        if request.option_chain_snapshot is None:
            return S23PaperContractSelectionResult(
                selected=False,
                failure_code=PaperContractSelectionFailureCode.OPTION_CHAIN_MISSING,
                selection_reason="S21 runtime selection requires a normalized option chain.",
                selected_contract_symbol=None,
                expiry_date=None,
                strike=None,
                option_type=None,
                premium_used=None,
                oi_used=None,
                ranked_candidate_count=0,
                rejected_candidate_counts={},
            )

        if request.smoke_override_enabled and request.smoke_override_selected_contract_symbol:
            # Keep the existing explicit smoke path unchanged.
            return super()._select_contract(request, trade_plan)

        near_expiry = request.expiry_governance.resolve_expiry_date(
            request.strategy_rule,
            request.session_context.session_date,
        )
        # AB6 OS S21 authority: "No. of Expiry to Check" = 1 Exp.
        # S21 therefore evaluates only the resolved Near monthly expiry.
        # Do not fall through to Next merely because Near does not qualify.
        expiry_order = (near_expiry,)

        effective_lot_size = float(request.quantity) / float(request.lots)
        minimum_oi = (
            float(request.strategy_rule.parameters.get("minimum_lots", 500.0))
            * effective_lot_size
        )
        # Contract qualification follows the same S23 option-selling stage
        # semantics: exact contract premium + exact contract OI. Historical
        # OPT_PRV aliases are loaded only after final contract selection.

        aggregate_rejected: dict[str, int] = {}
        attempted: list[date] = []
        for expiry in expiry_order:
            attempted.append(expiry)
            result = self._select_for_expiry(
                request=request,
                trade_plan=trade_plan,
                expiry=expiry,
                minimum_oi=minimum_oi,
            )
            for key, count in result.rejected_candidate_counts.items():
                aggregate_rejected[key] = aggregate_rejected.get(key, 0) + count
            if result.selected:
                reason = result.selection_reason
                if expiry != near_expiry:
                    reason = (
                        f"Near monthly expiry {near_expiry.isoformat()} did not qualify; "
                        f"{reason}"
                    )
                return replace(
                    result,
                    selection_reason=reason,
                    attempted_expiries=tuple(attempted),
                    rejected_candidate_counts=aggregate_rejected,
                )

        return S23PaperContractSelectionResult(
            selected=False,
            failure_code=PaperContractSelectionFailureCode.NO_CONTRACT_SELECTED,
            selection_reason=(
                "No S21 candidate satisfied rule-book option-chain premium and OI "
                "qualification in the single allowed monthly expiry."
            ),
            selected_contract_symbol=None,
            expiry_date=None,
            strike=None,
            option_type=None,
            premium_used=None,
            oi_used=None,
            ranked_candidate_count=0,
            rejected_candidate_counts=aggregate_rejected,
            attempted_expiries=tuple(attempted),
        )

    def _select_for_expiry(
        self,
        *,
        request: PaperLivePreludeRequest,
        trade_plan: TradePlan,
        expiry: date,
        minimum_oi: float,
    ) -> S23PaperContractSelectionResult:
        assert request.option_chain_snapshot is not None
        lower = min(float(trade_plan.start_strike), float(trade_plan.end_strike))
        upper = max(float(trade_plan.start_strike), float(trade_plan.end_strike))
        rejected: dict[str, int] = {}

        def bump(key: str) -> None:
            rejected[key] = rejected.get(key, 0) + 1

        candidates: list[OptionChainContract] = []
        for contract in request.option_chain_snapshot.contracts:
            if contract.expiry != expiry:
                continue
            if contract.option_type is not request.strategy_rule.option_type:
                continue
            if contract.strike is None:
                bump("missing_strike")
                continue
            if not (lower <= float(contract.strike) <= upper):
                continue
            if contract.oi is None:
                bump("missing_oi")
                continue
            if float(contract.oi) < minimum_oi:
                bump("minimum_oi_not_met")
                continue
            candidates.append(contract)

        if not candidates:
            return S23PaperContractSelectionResult(
                selected=False,
                failure_code=PaperContractSelectionFailureCode.NO_CONTRACT_IN_STRIKE_RANGE,
                selection_reason="No S21 contracts in range passed the 500-lot OI gate.",
                selected_contract_symbol=None,
                expiry_date=None,
                strike=None,
                option_type=None,
                premium_used=None,
                oi_used=None,
                ranked_candidate_count=0,
                rejected_candidate_counts=rejected,
                attempted_expiries=(expiry,),
            )

        ascending = float(trade_plan.end_strike) >= float(trade_plan.start_strike)
        forward = tuple(
            sorted(
                candidates,
                key=lambda item: (float(item.strike or 0.0), item.symbol),
                reverse=not ascending,
            )
        )
        def premium(contract: OptionChainContract) -> float | None:
            # Match the proven S23 contract-selection stage: use the premium
            # carried by this exact option-chain contract. Do not substitute a
            # historical OPT_PRV entry reference.
            return float(contract.ltp) if contract.ltp is not None else None

        selected: OptionChainContract | None = None
        selected_premium: float | None = None
        phase = ""
        for contract in forward:
            value = premium(contract)
            if value is None:
                bump("missing_option_chain_premium")
                continue
            if value >= float(trade_plan.ideal_premium):
                selected = contract
                selected_premium = value
                phase = "IDEAL_PREMIUM_START_TO_END"
                break

        if selected is None:
            for contract in reversed(forward):
                value = premium(contract)
                if value is None:
                    continue
                if value >= float(trade_plan.minimum_premium):
                    selected = contract
                    selected_premium = value
                    phase = "MINIMUM_PREMIUM_END_TO_START"
                    break

        if selected is None:
            return S23PaperContractSelectionResult(
                selected=False,
                failure_code=PaperContractSelectionFailureCode.MINIMUM_PREMIUM_NOT_MET,
                selection_reason=(
                    "S21 candidates did not satisfy exact-contract option-chain "
                    "premium against Ideal/Minimum Premium."
                ),
                selected_contract_symbol=None,
                expiry_date=None,
                strike=None,
                option_type=None,
                premium_used=None,
                oi_used=None,
                ranked_candidate_count=len(candidates),
                rejected_candidate_counts=rejected,
                attempted_expiries=(expiry,),
            )

        assert selected_premium is not None
        return S23PaperContractSelectionResult(
            selected=True,
            failure_code=None,
            selection_reason=(
                f"S21 selected {selected.symbol} via {phase}; "
                f"option_chain_ltp={selected_premium:.4f}, "
                f"OI={float(selected.oi or 0.0):.0f}, minimum_OI={minimum_oi:.0f}."
            ),
            selected_contract_symbol=selected.symbol,
            expiry_date=selected.expiry,
            strike=selected.strike,
            option_type=selected.option_type,
            premium_used=selected_premium,
            oi_used=selected.oi,
            ranked_candidate_count=len(candidates),
            rejected_candidate_counts=rejected,
            ranking=S23PaperContractSelectionRanking(
                premium_distance=abs(
                    selected_premium - float(trade_plan.ideal_premium)
                ),
                oi_used=float(selected.oi or 0.0),
                tie_break_strike=float(selected.strike or 0.0),
                tie_break_symbol=selected.symbol,
            ),
            selected_contract=selected,
            attempted_expiries=(expiry,),
        )


class S21PaperLiveDecisionBuilder(S23PaperLiveDecisionBuilder):
    """S21 decision builder isolated from the proven S23 runtime path."""

    def __init__(self, *, config_path: str) -> None:
        self._s21_reference_provider = S21HistoricalOptionReferenceProvider(
            config_path=config_path
        )
        prelude_builder = S21PaperLivePreludeBuilder(
            reference_provider=self._s21_reference_provider
        )
        super().__init__(prelude_builder=prelude_builder)

    def build(
        self,
        *,
        strategy_rule: StrategyRule,
        reference_packet: PaperDecisionReferencePacket,
        collected_inputs: PaperCollectedSnapshotInputs,
        carry_forward_position: PaperPositionState | None = None,
        smoke_override_enabled: bool = False,
        smoke_override_selected_contract_symbol: str | None = None,
        allow_branch_pinned_unknown_monthly_status: bool = False,
        require_orpt_rc_timing_bars: bool = True,
        required_snapshot_labels: tuple[SnapshotLabel, ...] | None = None,
    ) -> S23PaperLiveDecisionResult:
        if strategy_rule.strategy_code != "S21":
            return super().build(
                strategy_rule=strategy_rule,
                reference_packet=reference_packet,
                collected_inputs=collected_inputs,
                carry_forward_position=carry_forward_position,
                smoke_override_enabled=smoke_override_enabled,
                smoke_override_selected_contract_symbol=smoke_override_selected_contract_symbol,
                allow_branch_pinned_unknown_monthly_status=allow_branch_pinned_unknown_monthly_status,
                require_orpt_rc_timing_bars=require_orpt_rc_timing_bars,
                required_snapshot_labels=required_snapshot_labels,
            )

        reference_derivation = self._live_reference_deriver.derive(
            base_reference_packet=reference_packet,
            collected_inputs=collected_inputs,
        )
        effective_reference_packet = reference_derivation.effective_reference_packet
        derived_inputs = self._runtime_input_deriver.derive(
            strategy_rule=strategy_rule,
            reference_packet=effective_reference_packet,
            underlying_quote=collected_inputs.underlying_quote,
            underlying_bars=collected_inputs.underlying_bars,
            daily_bars=collected_inputs.daily_bars,
            session_context=collected_inputs.session_context,
            required_snapshot_labels=required_snapshot_labels,
        )
        prelude_request = self._build_prelude_request(
            strategy_rule=strategy_rule,
            reference_packet=effective_reference_packet,
            derived_inputs=derived_inputs,
            collected_inputs=collected_inputs,
            carry_forward_position=carry_forward_position,
            smoke_override_enabled=smoke_override_enabled,
            smoke_override_selected_contract_symbol=smoke_override_selected_contract_symbol,
            allow_branch_pinned_unknown_monthly_status=allow_branch_pinned_unknown_monthly_status,
        )
        prelude_result = self._prelude_builder.build(prelude_request)

        selected = (
            prelude_result.contract_selection.selected_contract
            if prelude_result.contract_selection is not None
            else None
        )
        if selected is not None:
            selected_refs = self._s21_reference_provider.get_cached(
                symbol=selected.symbol,
                session_date=collected_inputs.session_context.session_date,
            )
            if selected_refs:
                corrected_values = dict(derived_inputs.runtime_values)
                corrected_values.update(selected_refs)
                derived_inputs = replace(
                    derived_inputs,
                    runtime_values=corrected_values,
                )

        timing_audit = self._build_orpt_rc_timing_audit(
            strategy_rule=strategy_rule,
            prelude_result=prelude_result,
            derived_inputs=derived_inputs,
            collected_inputs=collected_inputs,
        )
        if require_orpt_rc_timing_bars and str(timing_audit.get("status", "")).startswith("MISSING_"):
            raise S23PaperLiveDecisionError(
                str(timing_audit.get("status")),
                str(timing_audit.get("reason")),
            )
        recalculated_plan = timing_audit.get("recalculated_trade_plan")
        if recalculated_plan is not None:
            prelude_result = self._prelude_builder.build(
                replace(
                    prelude_request,
                    runtime_values=dict(derived_inputs.runtime_values),
                    trade_plan_override=recalculated_plan,
                )
            )

        summary = self._build_summary(
            strategy_rule=strategy_rule,
            reference_packet=effective_reference_packet,
            derived_inputs=derived_inputs,
            prelude_result=prelude_result,
            allow_branch_pinned_unknown_monthly_status=allow_branch_pinned_unknown_monthly_status,
        )
        explanation = self._build_explanation(
            strategy_rule=strategy_rule,
            reference_packet=effective_reference_packet,
            derived_inputs=derived_inputs,
            prelude_result=prelude_result,
            collected_inputs=collected_inputs,
            summary=summary,
            reference_derivation=reference_derivation,
        )
        explanation["orpt_rc_timing"] = self._serializable_timing_audit(timing_audit)
        explanation["s21_option_reference_source"] = (
            "selected_contract_completed_prior_daily_history"
        )
        return S23PaperLiveDecisionResult(
            derived_runtime_inputs=derived_inputs,
            prelude_result=prelude_result,
            summary=summary,
            explanation=explanation,
        )
