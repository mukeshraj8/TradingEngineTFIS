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
    fallback_expiry_dates: tuple[date, ...] = ()

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
    attempted_expiries: tuple[date, ...] = ()


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

        expiry_dates = self._expiry_search_order(request)
        failed_results: list[S23PaperContractSelectionResult] = []
        for expiry_date in expiry_dates:
            result = self._select_for_expiry(
                request,
                option_chain_snapshot,
                expiry_date=expiry_date,
            )
            if result.selected:
                if expiry_date != expiry_dates[0]:
                    return S23PaperContractSelectionResult(
                        selected=True,
                        failure_code=None,
                        selection_reason=(
                            result.selection_reason
                            + f" Near expiry {expiry_dates[0].isoformat()} failed; "
                            + f"selected fallback expiry {expiry_date.isoformat()}."
                        ),
                        selected_contract_symbol=result.selected_contract_symbol,
                        expiry_date=result.expiry_date,
                        strike=result.strike,
                        option_type=result.option_type,
                        premium_used=result.premium_used,
                        oi_used=result.oi_used,
                        ranked_candidate_count=result.ranked_candidate_count,
                        rejected_candidate_counts=result.rejected_candidate_counts,
                        ranking=result.ranking,
                        selected_contract=result.selected_contract,
                        attempted_expiries=expiry_dates,
                    )
                return S23PaperContractSelectionResult(
                    selected=True,
                    failure_code=None,
                    selection_reason=result.selection_reason,
                    selected_contract_symbol=result.selected_contract_symbol,
                    expiry_date=result.expiry_date,
                    strike=result.strike,
                    option_type=result.option_type,
                    premium_used=result.premium_used,
                    oi_used=result.oi_used,
                    ranked_candidate_count=result.ranked_candidate_count,
                    rejected_candidate_counts=result.rejected_candidate_counts,
                    ranking=result.ranking,
                    selected_contract=result.selected_contract,
                    attempted_expiries=expiry_dates,
                )
            failed_results.append(result)

        if len(failed_results) == 1:
            failed = failed_results[0]
            return self._failure(
                failure_code=failed.failure_code
                or PaperContractSelectionFailureCode.NO_CONTRACT_SELECTED,
                selection_reason=failed.selection_reason,
                rejected_candidate_counts=failed.rejected_candidate_counts,
                attempted_expiries=expiry_dates,
            )

        merged_rejected: dict[str, int] = {}
        for result in failed_results:
            for reason, count in result.rejected_candidate_counts.items():
                merged_rejected[reason] = merged_rejected.get(reason, 0) + count
        return self._failure(
            failure_code=failed_results[-1].failure_code
            or PaperContractSelectionFailureCode.NO_CONTRACT_SELECTED,
            selection_reason="; ".join(result.selection_reason for result in failed_results),
            rejected_candidate_counts=merged_rejected,
            attempted_expiries=expiry_dates,
        )

    def _select_for_expiry(
        self,
        request: S23PaperContractSelectionRequest,
        option_chain_snapshot: OptionChainSnapshotEvent,
        *,
        expiry_date: date,
    ) -> S23PaperContractSelectionResult:
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
            if contract.expiry != expiry_date:
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

        ideal_search_order = self._ordered_by_search_direction(
            candidates,
            start_strike=request.start_strike,
            end_strike=request.end_strike,
        )
        selected = None
        selection_reason = ""
        for contract in ideal_search_order:
            if contract.ltp >= request.ideal_premium:
                selected = contract
                selection_reason = (
                    "Selected first strike meeting ideal premium in rule-sheet search order."
                )
                break
        if selected is None:
            selected = next(
                contract
                for contract in ideal_search_order
                if contract.ltp >= request.minimum_premium
            )
            selection_reason = (
                "Selected first strike meeting minimum premium in rule-sheet search order."
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
            selection_reason=selection_reason,
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
            attempted_expiries=(expiry_date,),
        )

    def _failure(
        self,
        *,
        failure_code: PaperContractSelectionFailureCode,
        selection_reason: str,
        rejected_candidate_counts: dict[str, int],
        attempted_expiries: tuple[date, ...] = (),
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
            attempted_expiries=attempted_expiries,
        )

    @staticmethod
    def _expiry_search_order(
        request: S23PaperContractSelectionRequest,
    ) -> tuple[date, ...]:
        ordered: list[date] = []
        for expiry_date in (request.expiry_date, *request.fallback_expiry_dates):
            if expiry_date not in ordered:
                ordered.append(expiry_date)
        return tuple(ordered)

    @staticmethod
    def _bump(rejected: dict[str, int], reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    @staticmethod
    def _ordered_by_search_direction(
        contracts: list[OptionChainContract],
        *,
        start_strike: float,
        end_strike: float,
    ) -> list[OptionChainContract]:
        return sorted(
            contracts,
            key=lambda contract: float(contract.strike or 0.0),
            reverse=start_strike > end_strike,
        )
