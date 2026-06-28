from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from tfis.domain import MarketLevels, StrategyRule, TradePlan
from tfis.domain.enums import OptionType
from tfis.monthly_status import MonthlyStatusResult
from tfis.rules import validate_s23_strategy_rule_matches_matrix
from tfis.strategy import StrategyEvaluator

from .contract_selection import (
    PaperContractSelectionFailureCode,
    S23PaperContractSelectionRequest,
    S23PaperContractSelectionResult,
    S23PaperContractSelector,
)
from .expiry_governance import S23PaperExpiryGovernance
from .models import (
    CalendarContextEvent,
    EventEnvelope,
    MonthlyStatusInputEvent,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    PaperTradePlanEvent,
    SelectedContractQuoteEvent,
    SnapshotLabel,
    UnderlyingSnapshotEvent,
)
from .position_state import (
    S23PaperPositionState,
    S23PaperPositionStateEvent,
    S23PaperPositionStateEventType,
    S23PaperPositionStateStatus,
)


class S23LivePreludeError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        contract_selection: S23PaperContractSelectionResult | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.contract_selection = contract_selection


class S23PaperPreludeMode(str, Enum):
    FRESH_ENTRY = "FRESH_ENTRY"
    CARRY_FORWARD_RESUME = "CARRY_FORWARD_RESUME"


@dataclass(frozen=True, slots=True)
class S23PaperSnapshotInput:
    snapshot_label: SnapshotLabel
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    bar_start: datetime
    bar_end: datetime
    complete: bool = True


@dataclass(frozen=True, slots=True)
class S23PaperPreludeSessionContext:
    session_date: date
    timezone: str
    generated_at: datetime
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    is_holiday: bool = False
    source_type: str = "live_prelude_builder"
    source_id_prefix: str = "live-prelude"


@dataclass(frozen=True, slots=True)
class S23PaperLivePreludeRequest:
    strategy_rule: StrategyRule
    strategy_branch: str
    monthly_status_result: MonthlyStatusResult
    market_levels: MarketLevels
    runtime_values: dict[str, object]
    option_chain_snapshot: OptionChainSnapshotEvent | None
    snapshots: tuple[S23PaperSnapshotInput, ...]
    session_context: S23PaperPreludeSessionContext
    expiry_governance: S23PaperExpiryGovernance
    lots: int
    quantity: int
    monthly_status_reference_date: date | None = None
    monthly_status_source: str = "monthly_status_engine"
    monthly_status_threshold_version: str = "v1"
    source_workbook_rule: str | None = None
    workbook_row_number: int | None = None
    fsl_price: float | None = None
    carry_forward_position: S23PaperPositionState | None = None
    smoke_override_enabled: bool = False
    smoke_override_selected_contract_symbol: str | None = None
    allow_branch_pinned_unknown_monthly_status: bool = False
    trade_plan_override: TradePlan | None = None


@dataclass(frozen=True, slots=True)
class S23PaperLivePreludeResult:
    mode: S23PaperPreludeMode
    selected_branch: str
    calendar_context_event: CalendarContextEvent
    monthly_status_event: MonthlyStatusInputEvent
    snapshot_events: tuple[UnderlyingSnapshotEvent, ...]
    trade_plan_event: PaperTradePlanEvent | None
    selected_contract_event: SelectedContractQuoteEvent | None
    governance_events: tuple[S23PaperPositionStateEvent, ...]
    resume_event: S23PaperPositionStateEvent | None
    contract_selection: S23PaperContractSelectionResult | None
    trade_plan: TradePlan | None
    selected_contract_provenance: str | None

    @property
    def prelude_events(self) -> tuple[object, ...]:
        events: list[object] = [
            self.calendar_context_event,
            self.monthly_status_event,
            *self.snapshot_events,
        ]
        if self.trade_plan_event is not None:
            events.append(self.trade_plan_event)
        if self.selected_contract_event is not None:
            events.append(self.selected_contract_event)
        return tuple(events)


_BLOCKED_WORKBOOK_ROWS = frozenset({190, 191})


class S23PaperLivePreludeBuilder:
    def __init__(
        self,
        *,
        strategy_evaluator: StrategyEvaluator | None = None,
        contract_selector: S23PaperContractSelector | None = None,
    ) -> None:
        self._strategy_evaluator = strategy_evaluator or StrategyEvaluator()
        self._contract_selector = contract_selector or S23PaperContractSelector()

    def build(self, request: S23PaperLivePreludeRequest) -> S23PaperLivePreludeResult:
        self._validate_scope(request)
        self._validate_workbook_path(request)

        calendar_event = self._build_calendar_context_event(request)
        monthly_status_event = self._build_monthly_status_event(request)
        snapshot_events = self._build_snapshot_events(request)

        if request.carry_forward_position is not None:
            resume_event = self._build_resume_event(request)
            governance_events = request.expiry_governance.build_events(
                request.carry_forward_position,
                session_date=request.session_context.session_date,
                event_timestamp=request.session_context.generated_at,
                current_time=request.session_context.generated_at.timetz().replace(tzinfo=None),
                provenance_source_ids=(monthly_status_event.envelope.source_id,),
            )
            return S23PaperLivePreludeResult(
                mode=S23PaperPreludeMode.CARRY_FORWARD_RESUME,
                selected_branch=request.strategy_branch,
                calendar_context_event=calendar_event,
                monthly_status_event=monthly_status_event,
                snapshot_events=snapshot_events,
                trade_plan_event=None,
                selected_contract_event=None,
                governance_events=governance_events,
                resume_event=resume_event,
                contract_selection=None,
                trade_plan=None,
                selected_contract_provenance="carry_forward_position_state",
            )

        trade_plan = request.trade_plan_override or self._strategy_evaluator.evaluate(
            request.strategy_rule,
            market_levels=request.market_levels,
            runtime_values=request.runtime_values,
        )
        selection = self._select_contract(request, trade_plan)
        if not selection.selected or selection.selected_contract is None:
            code = (
                selection.failure_code.value
                if selection.failure_code is not None
                else PaperContractSelectionFailureCode.NO_CONTRACT_SELECTED.value
            )
            raise S23LivePreludeError(
                code,
                selection.selection_reason,
                contract_selection=selection,
            )

        reference_snapshot = self._resolve_order_reference_snapshot(snapshot_events)
        trade_plan_event = self._build_trade_plan_event(
            request,
            trade_plan=trade_plan,
            reference_snapshot=reference_snapshot,
        )
        selected_contract_event = self._build_selected_contract_event(
            request,
            selected_contract=selection.selected_contract,
            reference_snapshot=reference_snapshot,
            provenance=(
                "smoke_override"
                if request.smoke_override_enabled
                and request.smoke_override_selected_contract_symbol
                else "runtime_option_chain_selection"
            ),
        )
        return S23PaperLivePreludeResult(
            mode=S23PaperPreludeMode.FRESH_ENTRY,
            selected_branch=request.strategy_branch,
            calendar_context_event=calendar_event,
            monthly_status_event=monthly_status_event,
            snapshot_events=snapshot_events,
            trade_plan_event=trade_plan_event,
            selected_contract_event=selected_contract_event,
            governance_events=(),
            resume_event=None,
            contract_selection=selection,
            trade_plan=trade_plan,
            selected_contract_provenance=(
                "smoke_override"
                if request.smoke_override_enabled
                and request.smoke_override_selected_contract_symbol
                else "runtime_option_chain_selection"
            ),
        )

    def _validate_scope(self, request: S23PaperLivePreludeRequest) -> None:
        rule = request.strategy_rule
        if rule.strategy_code != "S23":
            raise S23LivePreludeError("UNSUPPORTED_STRATEGY", "Only S23 is supported.")
        matrix_mismatches = validate_s23_strategy_rule_matches_matrix(rule)
        if matrix_mismatches:
            raise S23LivePreludeError(
                "S23_RULE_MATRIX_MISMATCH",
                "Loaded S23 strategy rule does not match the corrected rule-sheet matrix: "
                + "; ".join(matrix_mismatches),
            )
        if rule.symbol != "NIFTY":
            raise S23LivePreludeError("UNSUPPORTED_SYMBOL", "Only NIFTY is supported.")
        if rule.option_type not in {OptionType.CALL, OptionType.PUT}:
            raise S23LivePreludeError(
                "UNSUPPORTED_OPTION_TYPE",
                "Prelude generation requires an options strategy branch with CE or PE.",
            )
        if request.option_chain_snapshot is not None and request.option_chain_snapshot.underlying_symbol != "NIFTY":
            raise S23LivePreludeError(
                "UNSUPPORTED_OPTION_CHAIN_UNDERLYING",
                "Only NIFTY option-chain snapshots are supported.",
            )
        if (
            request.monthly_status_result.status not in rule.allowed_monthly_statuses
            and not (
                request.allow_branch_pinned_unknown_monthly_status
                and request.monthly_status_result.status.value == "UNKNOWN"
                and self._branches_match(request.strategy_branch, rule.unique_code)
            )
        ):
            raise S23LivePreludeError(
                "MONTHLY_STATUS_BRANCH_MISMATCH",
                "Selected branch is not eligible for the supplied monthly status.",
            )
        if request.lots <= 0 or request.quantity <= 0:
            raise S23LivePreludeError(
                "INVALID_POSITION_SIZING",
                "Prelude generation requires positive lots and quantity.",
            )

    @staticmethod
    def _branches_match(left: str, right: str) -> bool:
        normalized_left = left.strip().upper()
        normalized_right = right.strip().upper()
        return (
            normalized_left == normalized_right
            or normalized_left.endswith(normalized_right)
            or normalized_right.endswith(normalized_left)
        )

    def _validate_workbook_path(self, request: S23PaperLivePreludeRequest) -> None:
        blocked_by_rule = False
        if request.source_workbook_rule:
            normalized = request.source_workbook_rule.strip().upper()
            blocked_by_rule = normalized.endswith("190") or normalized.endswith("191")
        if request.workbook_row_number in _BLOCKED_WORKBOOK_ROWS or blocked_by_rule:
            raise S23LivePreludeError(
                "UNSUPPORTED_WORKBOOK_PATH",
                "Workbook rows 190-191 remain blocked for runtime implementation.",
            )

    def _select_contract(
        self,
        request: S23PaperLivePreludeRequest,
        trade_plan: TradePlan,
    ) -> S23PaperContractSelectionResult:
        if request.option_chain_snapshot is None:
            return self._contract_selector.select(
                S23PaperContractSelectionRequest(
                    underlying_symbol=request.strategy_rule.symbol,
                    expiry_date=request.expiry_governance.resolve_expiry_date(
                        request.strategy_rule,
                        request.session_context.session_date,
                    ),
                    option_type=request.strategy_rule.option_type or OptionType.PUT,
                    start_strike=float(trade_plan.start_strike or 0),
                    end_strike=float(trade_plan.end_strike or 0),
                    ideal_premium=float(trade_plan.ideal_premium or 0),
                    minimum_premium=float(trade_plan.minimum_premium or 0),
                    minimum_oi=float(request.strategy_rule.minimum_oi),
                ),
                None,
            )

        if request.smoke_override_enabled and request.smoke_override_selected_contract_symbol:
            return self._select_smoke_override_contract(request, trade_plan)

        near_expiry = request.expiry_governance.resolve_expiry_date(
            request.strategy_rule,
            request.session_context.session_date,
        )
        later_expiries = self._fallback_expiries_from_snapshot(
            request.option_chain_snapshot,
            near_expiry=near_expiry,
        )
        if request.expiry_governance.should_select_next_expiry(
            request.strategy_rule,
            request.session_context.session_date,
        ):
            # Fresh entries inside the rollover window must not use the current weekly expiry.
            if not later_expiries:
                return S23PaperContractSelectionResult(
                    selected=False,
                    failure_code=PaperContractSelectionFailureCode.NO_CONTRACT_SELECTED,
                    selection_reason=(
                        "Fresh S23 entries inside the rollover window must use the next "
                        f"weekly expiry, but no expiry after {near_expiry.isoformat()} "
                        "was present in the option-chain snapshot."
                    ),
                    selected_contract_symbol=None,
                    expiry_date=None,
                    strike=None,
                    option_type=None,
                    premium_used=None,
                    oi_used=None,
                    ranked_candidate_count=0,
                    rejected_candidate_counts={"next_expiry_missing": 1},
                    attempted_expiries=(near_expiry,),
                )
            primary_expiry = later_expiries[0]
            fallback_expiries = tuple(
                expiry for expiry in later_expiries[1:] if expiry != primary_expiry
            )
        else:
            primary_expiry = near_expiry
            fallback_expiries = later_expiries
        selection_request = S23PaperContractSelectionRequest(
            underlying_symbol=request.strategy_rule.symbol,
            expiry_date=primary_expiry,
            option_type=request.strategy_rule.option_type or OptionType.PUT,
            start_strike=float(trade_plan.start_strike or 0),
            end_strike=float(trade_plan.end_strike or 0),
            ideal_premium=float(trade_plan.ideal_premium or 0),
            minimum_premium=float(trade_plan.minimum_premium or 0),
            minimum_oi=float(request.strategy_rule.minimum_oi),
            fallback_expiry_dates=fallback_expiries,
        )
        return self._contract_selector.select(selection_request, request.option_chain_snapshot)

    @staticmethod
    def _fallback_expiries_from_snapshot(
        option_chain_snapshot: OptionChainSnapshotEvent,
        *,
        near_expiry,
    ):
        later_expiries = sorted(
            {
                contract.expiry
                for contract in option_chain_snapshot.contracts
                if contract.expiry is not None and contract.expiry > near_expiry
            }
        )
        return tuple(later_expiries[:1])

    def _select_smoke_override_contract(
        self,
        request: S23PaperLivePreludeRequest,
        trade_plan: TradePlan,
    ) -> S23PaperContractSelectionResult:
        assert request.option_chain_snapshot is not None
        assert request.smoke_override_selected_contract_symbol is not None
        matching = tuple(
            contract
            for contract in request.option_chain_snapshot.contracts
            if contract.symbol == request.smoke_override_selected_contract_symbol
        )
        filtered_snapshot = OptionChainSnapshotEvent(
            envelope=request.option_chain_snapshot.envelope,
            underlying_symbol=request.option_chain_snapshot.underlying_symbol,
            expiry=request.option_chain_snapshot.expiry,
            contracts=matching,
        )
        selection = self._contract_selector.select(
            S23PaperContractSelectionRequest(
                underlying_symbol=request.strategy_rule.symbol,
                expiry_date=request.option_chain_snapshot.expiry,
                option_type=request.strategy_rule.option_type or OptionType.PUT,
                start_strike=float(trade_plan.start_strike or 0),
                end_strike=float(trade_plan.end_strike or 0),
                ideal_premium=float(trade_plan.ideal_premium or 0),
                minimum_premium=float(trade_plan.minimum_premium or 0),
                minimum_oi=float(request.strategy_rule.minimum_oi),
            ),
            filtered_snapshot,
        )
        if selection.selected and selection.selected_contract is not None:
            return S23PaperContractSelectionResult(
                selected=True,
                failure_code=None,
                selection_reason=(
                    "Smoke override selected contract was applied after passing runtime filters."
                ),
                selected_contract_symbol=selection.selected_contract_symbol,
                expiry_date=selection.expiry_date,
                strike=selection.strike,
                option_type=selection.option_type,
                premium_used=selection.premium_used,
                oi_used=selection.oi_used,
                ranked_candidate_count=selection.ranked_candidate_count,
                rejected_candidate_counts=selection.rejected_candidate_counts,
                ranking=selection.ranking,
                selected_contract=selection.selected_contract,
            )
        return selection

    def _build_calendar_context_event(
        self,
        request: S23PaperLivePreludeRequest,
    ) -> CalendarContextEvent:
        weekly_expiry = self._resolve_expiry_date(request)
        timestamp = self._session_datetime(
            request.session_context.session_date,
            time(9, 0),
            request.session_context.timezone,
        )
        return CalendarContextEvent(
            envelope=EventEnvelope(
                event_type=PaperEventType.CALENDAR_CONTEXT,
                session_date=request.session_context.session_date,
                effective_timestamp=timestamp,
                captured_at=timestamp + timedelta(seconds=1),
                timezone=request.session_context.timezone,
                source_type=request.session_context.source_type,
                source_id=f"{request.session_context.source_id_prefix}:calendar",
                synthetic_fixture=False,
                normalized_by="live-prelude-v1",
                source_sequence=1,
                data_quality_flags=(),
            ),
            is_holiday=request.session_context.is_holiday,
            is_expiry_day=request.session_context.session_date == weekly_expiry,
            weekly_expiry=weekly_expiry,
            market_open=request.session_context.market_open,
            market_close=request.session_context.market_close,
        )

    def _build_monthly_status_event(
        self,
        request: S23PaperLivePreludeRequest,
    ) -> MonthlyStatusInputEvent:
        timestamp = self._session_datetime(
            request.session_context.session_date,
            time(9, 0, 30),
            request.session_context.timezone,
        )
        return MonthlyStatusInputEvent(
            envelope=EventEnvelope(
                event_type=PaperEventType.MONTHLY_STATUS_INPUT,
                session_date=request.session_context.session_date,
                effective_timestamp=timestamp,
                captured_at=timestamp + timedelta(seconds=1),
                timezone=request.session_context.timezone,
                source_type=request.session_context.source_type,
                source_id=f"{request.session_context.source_id_prefix}:monthly-status",
                synthetic_fixture=False,
                normalized_by="live-prelude-v1",
                source_sequence=2,
                data_quality_flags=(),
            ),
            monthly_status=request.monthly_status_result.status,
            status_source=request.monthly_status_source,
            reference_date=(
                request.monthly_status_reference_date
                or request.session_context.session_date
            ),
            threshold_version=request.monthly_status_threshold_version,
        )

    def _build_snapshot_events(
        self,
        request: S23PaperLivePreludeRequest,
    ) -> tuple[UnderlyingSnapshotEvent, ...]:
        events: list[UnderlyingSnapshotEvent] = []
        for index, snapshot in enumerate(
            sorted(request.snapshots, key=lambda item: item.bar_end),
            start=3,
        ):
            events.append(
                UnderlyingSnapshotEvent(
                    envelope=EventEnvelope(
                        event_type=PaperEventType.UNDERLYING_SNAPSHOT,
                        session_date=request.session_context.session_date,
                        effective_timestamp=snapshot.bar_end,
                        captured_at=snapshot.bar_end + timedelta(seconds=1),
                        timezone=request.session_context.timezone,
                        source_type=request.session_context.source_type,
                        source_id=(
                            f"{request.session_context.source_id_prefix}:snapshot:{snapshot.snapshot_label.value.lower()}"
                        ),
                        synthetic_fixture=False,
                        normalized_by="live-prelude-v1",
                        source_sequence=index,
                        data_quality_flags=(),
                    ),
                    snapshot_label=snapshot.snapshot_label,
                    open=snapshot.open,
                    high=snapshot.high,
                    low=snapshot.low,
                    close=snapshot.close,
                    bar_start=snapshot.bar_start,
                    bar_end=snapshot.bar_end,
                    complete=snapshot.complete,
                )
            )
        return tuple(events)

    def _build_trade_plan_event(
        self,
        request: S23PaperLivePreludeRequest,
        *,
        trade_plan: TradePlan,
        reference_snapshot: UnderlyingSnapshotEvent,
    ) -> PaperTradePlanEvent:
        return PaperTradePlanEvent(
            envelope=EventEnvelope(
                event_type=PaperEventType.TRADE_PLAN_INPUT,
                session_date=request.session_context.session_date,
                effective_timestamp=reference_snapshot.bar_end,
                captured_at=request.session_context.generated_at,
                timezone=request.session_context.timezone,
                source_type=request.session_context.source_type,
                source_id=f"{request.session_context.source_id_prefix}:trade-plan",
                synthetic_fixture=False,
                normalized_by="live-prelude-v1",
                source_sequence=10,
                data_quality_flags=(),
            ),
            strategy_branch=request.strategy_branch,
            order_side="SELL",
            lots=request.lots,
            quantity=request.quantity,
            planned_entry_price=trade_plan.entry_price,
            target_price=trade_plan.target_price,
            stoploss_price=trade_plan.stoploss_price,
            order_reference_time=reference_snapshot.bar_end,
            order_reference_label=reference_snapshot.snapshot_label.value,
            start_strike=float(trade_plan.start_strike) if trade_plan.start_strike is not None else None,
            end_strike=float(trade_plan.end_strike) if trade_plan.end_strike is not None else None,
            ideal_premium=trade_plan.ideal_premium,
            minimum_premium=trade_plan.minimum_premium,
            source_workbook_rule=request.source_workbook_rule,
            workbook_row_number=request.workbook_row_number,
            fsl_price=request.fsl_price,
        )

    def _build_selected_contract_event(
        self,
        request: S23PaperLivePreludeRequest,
        *,
        selected_contract: OptionChainContract,
        reference_snapshot: UnderlyingSnapshotEvent,
        provenance: str,
    ) -> SelectedContractQuoteEvent:
        flags = ("smoke_override_selected_contract",) if provenance == "smoke_override" else ()
        return SelectedContractQuoteEvent(
            envelope=EventEnvelope(
                event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
                session_date=request.session_context.session_date,
                effective_timestamp=reference_snapshot.bar_end,
                captured_at=request.session_context.generated_at,
                timezone=request.session_context.timezone,
                source_type=request.session_context.source_type,
                source_id=f"{request.session_context.source_id_prefix}:selected-contract:{provenance}",
                synthetic_fixture=False,
                normalized_by="live-prelude-v1",
                source_sequence=11,
                data_quality_flags=flags,
            ),
            symbol=selected_contract.symbol,
            option_type=selected_contract.option_type,
            strike=selected_contract.strike,
            expiry=selected_contract.expiry,
            bid=selected_contract.bid,
            ask=selected_contract.ask,
            ltp=selected_contract.ltp,
            oi=selected_contract.oi,
            volume=selected_contract.volume,
        )

    def _build_resume_event(
        self,
        request: S23PaperLivePreludeRequest,
    ) -> S23PaperPositionStateEvent:
        assert request.carry_forward_position is not None
        return S23PaperPositionStateEvent(
            timestamp=request.session_context.generated_at,
            event_type=S23PaperPositionStateEventType.PAPER_POSITION_RESUMED,
            strategy_code=request.carry_forward_position.strategy_code,
            unique_code=request.carry_forward_position.unique_code,
            selected_contract_symbol=request.carry_forward_position.selected_contract_symbol,
            lifecycle_status=S23PaperPositionStateStatus.PAPER_POSITION_RESUMED,
            session_date=request.session_context.session_date,
            reason_code="paper_position_resumed",
            message="Paper carry-forward position was resumed for the new session.",
            provenance_source_ids=request.carry_forward_position.provenance_source_ids,
        )

    @staticmethod
    def _resolve_order_reference_snapshot(
        snapshots: tuple[UnderlyingSnapshotEvent, ...],
    ) -> UnderlyingSnapshotEvent:
        for label in (SnapshotLabel.RC, SnapshotLabel.ORPT, SnapshotLabel.AT_0915):
            for snapshot in snapshots:
                if snapshot.snapshot_label is label:
                    return snapshot
        raise S23LivePreludeError(
            "MISSING_ORDER_REFERENCE_SNAPSHOT",
            "Prelude generation requires an RC, ORPT, or 0915 snapshot.",
        )

    @staticmethod
    def _session_datetime(session_date: date, value: time, timezone: str) -> datetime:
        return datetime.combine(session_date, value, tzinfo=ZoneInfo(timezone))

    @staticmethod
    def _resolve_expiry_date(request: S23PaperLivePreludeRequest) -> date:
        return request.expiry_governance.resolve_expiry_date(
            request.strategy_rule,
            request.session_context.session_date,
        )
