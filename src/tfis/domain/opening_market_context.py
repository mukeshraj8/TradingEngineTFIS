from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

from .runtime_contracts import TFISContractIdentity


class OpeningContextStatus(str, Enum):
    BUILDING = "BUILDING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED_OPENING_CONTEXT = "BLOCKED_OPENING_CONTEXT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OpeningTimestampClassification(str, Enum):
    OFFICIAL_EXCHANGE_OPEN = "OFFICIAL_EXCHANGE_OPEN"
    FIRST_LOCAL_TICK = "FIRST_LOCAL_TICK"
    FIRST_COMPLETE_LOCAL_QUOTE = "FIRST_COMPLETE_LOCAL_QUOTE"
    DERIVED_OPENING_BAR = "DERIVED_OPENING_BAR"
    ORPT_OBSERVATION = "ORPT_OBSERVATION"
    RC_OBSERVATION = "RC_OBSERVATION"
    UNSUPPORTED = "UNSUPPORTED"
    UNAVAILABLE = "UNAVAILABLE"


class OpeningGapClassification(str, Enum):
    NO_GAP = "NO_GAP"
    GAP_UP = "GAP_UP"
    GAP_DOWN = "GAP_DOWN"
    ABNORMAL_OPENING = "ABNORMAL_OPENING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OpeningGapDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OpeningFreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OpeningObservationAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    STALE = "STALE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class OpeningFailure:
    code: str
    field: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class OpeningQuoteEvidence:
    instrument: str
    ltp: float | None
    bid: float | None
    ask: float | None
    oi: float | None = None
    oi_unit: str | None = None
    source_timestamp: datetime | None = None
    freshness: OpeningFreshnessStatus = OpeningFreshnessStatus.MISSING
    provenance: str | None = None
    timestamp_classification: OpeningTimestampClassification = OpeningTimestampClassification.UNAVAILABLE
    source_label: str | None = None
    candidate_timestamps: tuple[datetime, ...] = ()
    selection_policy_identity: str | None = None
    selection_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_timestamps", tuple(sorted(self.candidate_timestamps)))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class OpeningBarEvidence:
    instrument: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    bar_timestamp: datetime | None
    provenance: str | None
    timestamp_classification: OpeningTimestampClassification = OpeningTimestampClassification.DERIVED_OPENING_BAR

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class TimedOpeningObservation:
    label: str
    configured_timestamp: datetime | None
    underlying_observation: OpeningQuoteEvidence | OpeningBarEvidence | None = None
    selected_contract_observation: OpeningQuoteEvidence | OpeningBarEvidence | None = None
    availability: OpeningObservationAvailability = OpeningObservationAvailability.MISSING
    provenance: str | None = None
    policy_applicability: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class OpeningGapContext:
    classification: OpeningGapClassification
    direction: OpeningGapDirection
    comparison_reference: str | None
    comparison_value: float | None
    gap_amount: float | None
    gap_percentage: float | None
    abnormal_opening_classification: str | None
    policy_identity: str | None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class OpeningConsumerReadiness:
    normal_opening_validation: OpeningContextStatus
    gap_missed_entry_evaluation: OpeningContextStatus
    orpt_only_flow: OpeningContextStatus
    orpt_plus_rc_flow: OpeningContextStatus
    carried_position_observation: OpeningContextStatus
    reasons: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", _freeze(self.reasons))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class OpeningMarketContext:
    context_id: str
    schema_version: str
    trading_date: date
    exchange: str
    session_id: str
    underlying_instrument: str
    selected_contract: TFISContractIdentity
    source_plan_id: str
    source_plan_hash: str
    scheduled_exchange_open_time: time | None
    official_exchange_open_timestamp: datetime | None
    first_local_quote_timestamp: datetime | None
    opening_bar_timestamp: datetime | None
    timestamp_classification: OpeningTimestampClassification
    underlying_opening_evidence: OpeningQuoteEvidence | OpeningBarEvidence | None
    selected_contract_opening_evidence: OpeningQuoteEvidence | None
    gap_context: OpeningGapContext
    orpt_observation: TimedOpeningObservation
    rc_observation: TimedOpeningObservation
    consumer_readiness: OpeningConsumerReadiness
    context_status: OpeningContextStatus
    missing_fields: tuple[str, ...] = ()
    derived_fields: tuple[str, ...] = ()
    supplemented_fields: tuple[str, ...] = ()
    stale_fields: tuple[str, ...] = ()
    data_quality_failures: tuple[OpeningFailure, ...] = ()
    evidence_classification: str = "SYNTHETIC_FIXTURE"
    performance: Mapping[str, float | int] = MappingProxyType({})
    context_hash: str = ""

    def __post_init__(self) -> None:
        if not self.context_id.strip():
            raise ValueError("context_id must be non-empty")
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))
        object.__setattr__(self, "derived_fields", tuple(self.derived_fields))
        object.__setattr__(self, "supplemented_fields", tuple(self.supplemented_fields))
        object.__setattr__(self, "stale_fields", tuple(self.stale_fields))
        object.__setattr__(self, "data_quality_failures", tuple(self.data_quality_failures))
        object.__setattr__(self, "performance", _freeze(self.performance))
        object.__setattr__(self, "context_hash", self.context_hash or opening_context_hash(self._business_payload()))

    @property
    def execution_permission(self) -> str:
        return "NONE"

    @property
    def lifecycle_action(self) -> str:
        return "NONE"

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def _business_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("context_hash", None)
        data.pop("performance", None)
        return data


def opening_context_hash(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(_serializable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _freeze(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(_freeze(item) for item in sorted(value, key=str))
    return value


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _serializable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value
