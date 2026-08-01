from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from tfis.persistence import canonical_hash


class AccountingTruthModel(str, Enum):
    INTERNAL_PAPER_ACCOUNTING_TRUTH = "INTERNAL_PAPER_ACCOUNTING_TRUTH"


class TradeFactState(str, Enum):
    OPEN_PROVISIONAL = "OPEN_PROVISIONAL"
    OPEN_ACCOUNTING_COMPLETE = "OPEN_ACCOUNTING_COMPLETE"
    CLOSED_PROVISIONAL = "CLOSED_PROVISIONAL"
    CLOSED_ACCOUNTING_COMPLETE = "CLOSED_ACCOUNTING_COMPLETE"
    CORRECTED = "CORRECTED"
    UNKNOWN_ACCOUNTING_STATE = "UNKNOWN_ACCOUNTING_STATE"
    INVALID = "INVALID"


class PnLFactType(str, Enum):
    REALIZED_TRADE_PNL = "REALIZED_TRADE_PNL"
    UNREALIZED_POSITION_PNL = "UNREALIZED_POSITION_PNL"
    DAILY_ACCOUNT_PNL = "DAILY_ACCOUNT_PNL"
    DAILY_STRATEGY_PNL = "DAILY_STRATEGY_PNL"
    DAILY_INSTRUMENT_PNL = "DAILY_INSTRUMENT_PNL"
    DAILY_PORTFOLIO_PNL = "DAILY_PORTFOLIO_PNL"
    CHARGE_ESTIMATE = "CHARGE_ESTIMATE"
    CHARGE_CORRECTION = "CHARGE_CORRECTION"
    ACCOUNTING_CORRECTION = "ACCOUNTING_CORRECTION"


class AccountingQuality(str, Enum):
    CONFIRMED_INTERNAL_PAPER = "CONFIRMED_INTERNAL_PAPER"
    PROVISIONAL_ESTIMATED_CHARGES = "PROVISIONAL_ESTIMATED_CHARGES"
    PROVISIONAL_MARK = "PROVISIONAL_MARK"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
    ACCOUNTING_COMPLETE = "ACCOUNTING_COMPLETE"
    CORRECTED = "CORRECTED"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class WinLossClassification(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    OPEN = "OPEN"
    UNKNOWN_ACCOUNTING_STATE = "UNKNOWN_ACCOUNTING_STATE"


class ExitReason(str, Enum):
    TARGET = "TARGET"
    ORIGINAL_SL = "ORIGINAL_SL"
    REVISED_SL = "REVISED_SL"
    EOD_EXIT = "EOD_EXIT"
    RISK_EXIT = "RISK_EXIT"
    OPERATOR_EXIT = "OPERATOR_EXIT"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    OPEN = "OPEN"
    CARRIED_FORWARD = "CARRIED_FORWARD"
    UNKNOWN = "UNKNOWN"


class MarkQuality(str, Enum):
    EXECUTABLE_SIDE = "EXECUTABLE_SIDE"
    DEGRADED_LTP_FALLBACK = "DEGRADED_LTP_FALLBACK"
    UNKNOWN_STALE_OR_UNAVAILABLE = "UNKNOWN_STALE_OR_UNAVAILABLE"


class ExcursionQuality(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class InstrumentDimensions:
    exchange: str
    product: str
    underlying: str
    contract: str
    expiry: str | None
    strike: Decimal | None
    option_type: str | None
    direction: str
    lot_size: int
    multiplier: Decimal
    tick_size: Decimal
    currency: str
    quantity_unit: str = "PHASE4H_CONFIRMED_UNITS"
    metadata_version: str = "phase4i.s23.option_selling.v1"

    def __post_init__(self) -> None:
        if self.product != "OPTION_SELLING":
            raise ValueError("Phase 4I only supports S23 option-selling accounting.")
        if self.lot_size <= 0 or self.multiplier <= 0 or self.tick_size <= 0:
            raise ValueError("Instrument lot size, multiplier and tick size must be positive.")

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class ChargeEvidence:
    charges: Decimal | None
    quality: AccountingQuality
    source: str
    evidence_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.charges is not None and self.charges < 0:
            raise ValueError("Charges cannot be negative.")
        object.__setattr__(self, "evidence_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("evidence_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class MarkSnapshot:
    contract: str
    trading_date: date
    bid: Decimal | None
    ask: Decimal | None
    ltp: Decimal | None
    source_timestamp: datetime
    captured_timestamp: datetime
    freshness_seconds: int
    snapshot_hash: str
    mark_policy: str = "CONSERVATIVE_EXECUTABLE_SIDE"

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class MfeMaeResult:
    mfe: Decimal | None
    mae: Decimal | None
    quality: ExcursionQuality
    observation_count: int
    evidence_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("evidence_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class TradeFact:
    trade_fact_id: str
    trade_id: str
    position_cycle_id: str
    trading_session_id: str
    originating_trading_date: date
    final_trading_date: date | None
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance: str
    logical_paper_account: str
    configuration_hash: str
    rule_matrix_version: str
    trade_fact_version: str
    instrument: InstrumentDimensions
    decision_context: Mapping[str, Any]
    execution: Mapping[str, Any]
    lifecycle: Mapping[str, Any]
    performance_inputs: Mapping[str, Any]
    provenance: Mapping[str, Any]
    state: TradeFactState
    accounting_truth: AccountingTruthModel = AccountingTruthModel.INTERNAL_PAPER_ACCOUNTING_TRUTH
    supersedes_trade_fact_id: str | None = None
    fact_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_context", _freeze(self.decision_context))
        object.__setattr__(self, "execution", _freeze(self.execution))
        object.__setattr__(self, "lifecycle", _freeze(self.lifecycle))
        object.__setattr__(self, "performance_inputs", _freeze(self.performance_inputs))
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        object.__setattr__(self, "fact_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("fact_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class PnLFact:
    pnl_fact_id: str
    fact_type: PnLFactType
    as_of_timestamp: datetime
    trading_date: date
    source_identities: Mapping[str, Any]
    account: str
    strategy: str
    instrument: Mapping[str, Any]
    gross_pnl: Decimal | None
    charges: Decimal | None
    net_pnl: Decimal | None
    realized_unrealized: str
    currency: str
    metadata_version: str
    calculation_version: str
    quality_state: AccountingQuality
    evidence_hash: str
    supersedes_pnl_fact_id: str | None = None
    fact_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_identities", _freeze(self.source_identities))
        object.__setattr__(self, "instrument", _freeze(self.instrument))
        object.__setattr__(self, "fact_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("fact_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class AccountingProjection:
    projection_id: str
    projection_type: str
    dimensions: Mapping[str, Any]
    metrics: Mapping[str, Any]
    source_fact_ids: tuple[str, ...]
    watermark: str
    quality: AccountingQuality
    projection_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimensions", _freeze(self.dimensions))
        object.__setattr__(self, "metrics", _freeze(self.metrics))
        object.__setattr__(self, "source_fact_ids", tuple(self.source_fact_ids))
        object.__setattr__(self, "projection_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("projection_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class AccountingBuildResult:
    trade_fact: TradeFact
    pnl_facts: tuple[PnLFact, ...]
    projections: tuple[AccountingProjection, ...]
    result_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pnl_facts", tuple(self.pnl_facts))
        object.__setattr__(self, "projections", tuple(self.projections))
        object.__setattr__(self, "result_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("result_hash", None)
        return data


def _freeze(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))})
    if isinstance(value, tuple | list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(_freeze(item) for item in sorted(value, key=str))
    return value


def _serializable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        result: dict[str, Any] = {}
        for item in fields(value):
            try:
                result[item.name] = _serializable(getattr(value, item.name))
            except AttributeError:
                continue
        return result
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    return value
