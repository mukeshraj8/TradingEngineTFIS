from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum

from tfis.domain.enums import MonthlyStatus, OptionType


class PaperEventType(str, Enum):
    UNDERLYING_QUOTE = "UNDERLYING_QUOTE"
    UNDERLYING_SNAPSHOT = "UNDERLYING_SNAPSHOT"
    OPTION_CHAIN_SNAPSHOT = "OPTION_CHAIN_SNAPSHOT"
    SELECTED_CONTRACT_QUOTE = "SELECTED_CONTRACT_QUOTE"
    SELECTED_CONTRACT_BAR = "SELECTED_CONTRACT_BAR"
    CALENDAR_CONTEXT = "CALENDAR_CONTEXT"
    MONTHLY_STATUS_INPUT = "MONTHLY_STATUS_INPUT"
    PAPER_SESSION_CONFIG = "PAPER_SESSION_CONFIG"
    COST_SLIPPAGE_SETTINGS = "COST_SLIPPAGE_SETTINGS"
    TRADE_PLAN_INPUT = "TRADE_PLAN_INPUT"


class SnapshotLabel(str, Enum):
    PRE_OPEN = "PRE_OPEN"
    AT_0915 = "0915"
    ORPT = "ORPT"
    RC = "RC"
    EOD = "EOD"


class PaperSessionState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PRE_MARKET_READY = "PRE_MARKET_READY"
    WAITING_FOR_0915 = "WAITING_FOR_0915"
    WAITING_FOR_ORPT = "WAITING_FOR_ORPT"
    WAITING_FOR_RC = "WAITING_FOR_RC"
    DECISION_READY = "DECISION_READY"
    ORDER_PLANNED = "ORDER_PLANNED"
    PAPER_ORDER_OPEN = "PAPER_ORDER_OPEN"
    PAPER_POSITION_OPEN = "PAPER_POSITION_OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    PAPER_POSITION_CLOSED = "PAPER_POSITION_CLOSED"
    EOD_SQUARE_OFF = "EOD_SQUARE_OFF"
    SESSION_COMPLETE = "SESSION_COMPLETE"
    NO_TRADE = "NO_TRADE"
    ABORTED = "ABORTED"


class PaperReadinessStatus(str, Enum):
    READY = "READY"
    NO_TRADE = "NO_TRADE"
    ABORTED = "ABORTED"


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_type: PaperEventType
    session_date: date
    effective_timestamp: datetime
    captured_at: datetime
    timezone: str
    source_type: str
    source_id: str
    synthetic_fixture: bool
    normalized_by: str
    source_sequence: int | None = None
    data_quality_flags: tuple[str, ...] = ()
    integrity_hash: str | None = None


@dataclass(frozen=True, slots=True)
class UnderlyingQuoteEvent:
    envelope: EventEnvelope
    symbol: str
    ltp: float | None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    source_latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class UnderlyingSnapshotEvent:
    envelope: EventEnvelope
    snapshot_label: SnapshotLabel
    high: float | None
    low: float | None
    bar_start: datetime
    bar_end: datetime
    complete: bool
    open: float | None = None
    close: float | None = None


@dataclass(frozen=True, slots=True)
class OptionChainContract:
    symbol: str
    option_type: OptionType | None
    strike: float | None
    expiry: date | None
    bid: float | None
    ask: float | None
    ltp: float | None
    oi: float | None
    volume: float | None = None


@dataclass(frozen=True, slots=True)
class OptionChainSnapshotEvent:
    envelope: EventEnvelope
    underlying_symbol: str
    expiry: date
    contracts: tuple[OptionChainContract, ...]


@dataclass(frozen=True, slots=True)
class SelectedContractQuoteEvent:
    envelope: EventEnvelope
    symbol: str
    option_type: OptionType | None
    strike: float | None
    expiry: date | None
    bid: float | None
    ask: float | None
    ltp: float | None
    oi: float | None
    volume: float | None = None


@dataclass(frozen=True, slots=True)
class SelectedContractBarEvent:
    envelope: EventEnvelope
    symbol: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    bar_start: datetime
    bar_end: datetime
    volume: float | None = None


@dataclass(frozen=True, slots=True)
class CalendarContextEvent:
    envelope: EventEnvelope
    is_holiday: bool
    is_expiry_day: bool
    weekly_expiry: date | None
    market_open: time | None
    market_close: time | None


@dataclass(frozen=True, slots=True)
class MonthlyStatusInputEvent:
    envelope: EventEnvelope
    monthly_status: MonthlyStatus | None
    status_source: str
    reference_date: date | None
    threshold_version: str


@dataclass(frozen=True, slots=True)
class PaperSessionConfigEvent:
    envelope: EventEnvelope
    strategy_code: str
    paper_mode_enabled: bool
    same_day_square_off_only: bool
    allow_recalculation: bool
    allow_current_day_fsl_trp: bool
    kill_switch_enabled: bool
    operator_id: str
    symbol: str = "NIFTY"
    contract_cycle: str = "WEEKLY"
    mode: str = "paper"


@dataclass(frozen=True, slots=True)
class CostSlippageSettingsEvent:
    envelope: EventEnvelope
    brokerage_per_lot: float | None
    slippage_entry_points: float | None
    slippage_exit_points: float | None
    spread_buffer_policy: str
    version_label: str


@dataclass(frozen=True, slots=True)
class PaperTradePlanEvent:
    envelope: EventEnvelope
    strategy_branch: str
    order_side: str
    lots: int | None
    quantity: int | None
    planned_entry_price: float | None
    target_price: float | None
    stoploss_price: float | None
    order_reference_time: datetime | None
    order_reference_label: str
    start_strike: float | None = None
    end_strike: float | None = None
    ideal_premium: float | None = None
    minimum_premium: float | None = None
    source_workbook_rule: str | None = None
    workbook_row_number: int | None = None
    fsl_price: float | None = None


@dataclass(frozen=True, slots=True)
class PaperValidationIssue:
    code: str
    message: str
    readiness_status: PaperReadinessStatus
    field_name: str | None = None
    event_type: PaperEventType | None = None


@dataclass(frozen=True, slots=True)
class PaperValidationResult:
    readiness_status: PaperReadinessStatus
    issues: tuple[PaperValidationIssue, ...]
    evaluated_state: PaperSessionState
    validated_at: datetime
    required_snapshot_labels: tuple[SnapshotLabel, ...] = ()
    missing_snapshot_labels: tuple[SnapshotLabel, ...] = ()
    warnings: tuple[str, ...] = ()
    no_trade_reasons: tuple[str, ...] = ()
    abort_reasons: tuple[str, ...] = ()

    @property
    def is_ready(self) -> bool:
        return self.readiness_status is PaperReadinessStatus.READY


@dataclass(frozen=True, slots=True)
class PaperDataSourceReference:
    event_type: PaperEventType
    source_type: str
    source_id: str
    synthetic_fixture: bool


@dataclass(frozen=True, slots=True)
class PaperSessionManifest:
    strategy_code: str
    symbol: str
    contract_cycle: str
    mode: str
    session_date: date
    readiness_status: PaperReadinessStatus
    evaluated_state: PaperSessionState
    overlays_enabled: tuple[str, ...]
    data_sources: tuple[PaperDataSourceReference, ...]
    cost_slippage_version: str
    no_trade_reasons: tuple[str, ...]
    abort_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    synthetic_fixture_used: bool
    generated_at: datetime
    brokerage_per_lot: float | None = None
    slippage_entry_points: float | None = None
    slippage_exit_points: float | None = None
    spread_buffer_policy: str | None = None
