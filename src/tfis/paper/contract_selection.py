from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from tfis.domain import StrategyRule
from tfis.domain.enums import OptionType

from .models import OptionChainContract, OptionChainSnapshotEvent, PaperTradePlanEvent


class PaperContractSelectionFailureCode(str, Enum):
    OPTION_CHAIN_MISSING = "OPTION_CHAIN_MISSING"
    NO_CONTRACT_IN_STRIKE_RANGE = "NO_CONTRACT_IN_STRIKE_RANGE"
    MISSING_CONTRACT_OI = "MISSING_CONTRACT_OI"
    MINIMUM_OI_NOT_MET = "MINIMUM_OI_NOT_MET"
    MINIMUM_PREMIUM_NOT_MET = "MINIMUM_PREMIUM_NOT_MET"
    NO_CONTRACT_SELECTED = "NO_CONTRACT_SELECTED"


@dataclass(frozen=True, slots=True)
class S23PaperContractSelectionRequest:
    underlying_symbol: str
    expiry_date: date
    option_type: OptionType
    start_strike: float
    end_strike: float
    ideal_premium: float
    minimum_premium: float
    minimum_oi: float

    @classmethod
    def from_strategy_and_trade_plan(
        cls,
        *,
        strategy: StrategyRule,
        trade_plan: PaperTradePlanEvent,
        expiry_date: date,
        underlying_symbol: str | None = None,
    ) -> S23PaperContractSelectionRequest:
        if trade_plan.start_strike is None:
            raise ValueError("trade_plan.start_strike is required for contract selection")
        if trade_plan.end_strike is None:
            raise ValueError("trade_plan.end_strike is required for contract selection")
        if trade_plan.ideal_premium is None:
            raise ValueError("trade_plan.ideal_premium is required for contract selection")
        if trade_plan.minimum_premium is None:
            raise ValueError("trade_plan.minimum_premium is required for contract selection")

        return cls(
            underlying_symbol=underlying_symbol or strategy.symbol,
            expiry_date=expiry_date,
            option_type=strategy.option_type,
            start_strike=trade_plan.start_strike,
            end_strike=trade_plan.end_strike,
            ideal_premium=trade_plan.ideal_premium,
            minimum_premium=trade_plan.minimum_premium,
            minimum_oi=float(strategy.minimum_oi),
        )

    @property
    def strike_lower_bound(self) -> float:
        return min(self.start_strike, self.end_strike)

    @property
    def strike_upper_bound(self) -> float:
        return max(self.start_strike, self.end_strike)


@dataclass(frozen=True, slots=True)
class S23PaperContractSelectionRanking:
    premium_distance: float
    oi_used: float
    tie_break_strike: float
    tie_break_symbol: str


@dataclass(frozen=True, slots=True)
class S23PaperContractSelectionResult:
    selected: bool
    failure_code: PaperContractSelectionFailureCode | None
    selection_reason: str
    selected_contract_symbol: str | None
    expiry_date: date | None
    strike: float | None
    option_type: OptionType | None
    premium_used: float | None
    oi_used: float | None
    ranked_candidate_count: int
    rejected_candidate_counts: dict[str, int]
    ranking: S23PaperContractSelectionRanking | None = None
    selected_contract: OptionChainContract | None = None


class S23PaperContractSelector:
    def select(
        self,
        request: S23PaperContractSelectionRequest,
        option_chain_snapshot: OptionChainSnapshotEvent | None,
    ) -> S23PaperContractSelectionResult:
        if option_chain_snapshot is None or not option_chain_snapshot.contracts:
            return self._failure(
                failure_code=PaperContractSelectionFailureCode.OPTION_CHAIN_MISSING,
                selection_reason="Runtime selection requires a non-empty normalized option chain.",
                rejected_candidate_counts={},
            )

        rejected: dict[str, int] = {}
        strike_filtered = False
        missing_oi_seen = False
        minimum_oi_failure = False
        minimum_premium_failure = False
        candidates: list[OptionChainContract] = []

        for contract in option_chain_snapshot.contracts:
            if option_chain_snapshot.underlying_symbol != request.underlying_symbol:
                self._bump(rejected, "underlying_mismatch")
                continue
            if contract.expiry != request.expiry_date:
                self._bump(rejected, "expiry_mismatch")
                continue
            if contract.option_type is not request.option_type:
                self._bump(rejected, "option_type_mismatch")
                continue
            if contract.strike is None:
                self._bump(rejected, "missing_strike")
                continue
            if not (request.strike_lower_bound <= contract.strike <= request.strike_upper_bound):
                strike_filtered = True
                self._bump(rejected, "strike_out_of_range")
                continue
            if contract.ltp is None:
                self._bump(rejected, "missing_premium")
                continue
            if contract.ltp < request.minimum_premium:
                minimum_premium_failure = True
                self._bump(rejected, "minimum_premium_not_met")
                continue
            if contract.oi is None:
                missing_oi_seen = True
                self._bump(rejected, "missing_oi")
                continue
            if contract.oi < request.minimum_oi:
                minimum_oi_failure = True
                self._bump(rejected, "minimum_oi_not_met")
                continue
            candidates.append(contract)

        if not candidates:
            if missing_oi_seen:
                return self._failure(
                    failure_code=PaperContractSelectionFailureCode.MISSING_CONTRACT_OI,
                    selection_reason="Option-chain candidates in the strike range are missing OI.",
                    rejected_candidate_counts=rejected,
                )
            if minimum_oi_failure:
                return self._failure(
                    failure_code=PaperContractSelectionFailureCode.MINIMUM_OI_NOT_MET,
                    selection_reason=(
                        "Option-chain candidates in the strike range do not meet minimum OI."
                    ),
                    rejected_candidate_counts=rejected,
                )
            if minimum_premium_failure:
                return self._failure(
                    failure_code=PaperContractSelectionFailureCode.MINIMUM_PREMIUM_NOT_MET,
                    selection_reason=(
                        "Option-chain candidates in the strike range do not meet minimum premium."
                    ),
                    rejected_candidate_counts=rejected,
                )
            if strike_filtered:
                return self._failure(
                    failure_code=PaperContractSelectionFailureCode.NO_CONTRACT_IN_STRIKE_RANGE,
                    selection_reason="No option-chain contracts fall inside the requested strike range.",
                    rejected_candidate_counts=rejected,
                )
            return self._failure(
                failure_code=PaperContractSelectionFailureCode.NO_CONTRACT_SELECTED,
                selection_reason="No option-chain contract satisfied the runtime selection filters.",
                rejected_candidate_counts=rejected,
            )

        selected = min(
            candidates,
            key=lambda contract: (
                abs(contract.ltp - request.ideal_premium),
                -float(contract.oi or 0.0),
                float(contract.strike or 0.0),
                contract.symbol,
            ),
        )
        ranking = S23PaperContractSelectionRanking(
            premium_distance=abs(float(selected.ltp) - request.ideal_premium),
            oi_used=float(selected.oi or 0.0),
            tie_break_strike=float(selected.strike or 0.0),
            tie_break_symbol=selected.symbol,
        )
        return S23PaperContractSelectionResult(
            selected=True,
            failure_code=None,
            selection_reason="Selected contract closest to ideal premium while satisfying OI filters.",
            selected_contract_symbol=selected.symbol,
            expiry_date=selected.expiry,
            strike=selected.strike,
            option_type=selected.option_type,
            premium_used=selected.ltp,
            oi_used=selected.oi,
            ranked_candidate_count=len(candidates),
            rejected_candidate_counts=rejected,
            ranking=ranking,
            selected_contract=selected,
        )

    def _failure(
        self,
        *,
        failure_code: PaperContractSelectionFailureCode,
        selection_reason: str,
        rejected_candidate_counts: dict[str, int],
    ) -> S23PaperContractSelectionResult:
        return S23PaperContractSelectionResult(
            selected=False,
            failure_code=failure_code,
            selection_reason=selection_reason,
            selected_contract_symbol=None,
            expiry_date=None,
            strike=None,
            option_type=None,
            premium_used=None,
            oi_used=None,
            ranked_candidate_count=0,
            rejected_candidate_counts=dict(sorted(rejected_candidate_counts.items())),
            ranking=None,
            selected_contract=None,
        )

    @staticmethod
    def _bump(rejected: dict[str, int], reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1
