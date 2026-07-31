from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from statistics import median
from time import perf_counter
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from tfis.coordination import OfflineTradingDayCoordinationInput, OfflineTradingDayCoordinator
from tfis.domain.carried_position_day import OfflineCarriedPositionEodDecision, OfflineCarriedPositionTradingDay
from tfis.domain.position_lifecycle import PositionLifecycleContext
from tfis.domain.trading_day_coordination import CoordinationEventType, OfflineCoordinationEvent, TradingDayCoordinationResult
from tfis.lifecycle import OfflineCarriedPositionTradingDayCoordinator, OfflineCarriedPositionTradingDayInput


class RuntimeEventType(str, Enum):
    SESSION_OPEN_OBSERVATION = "SESSION_OPEN_OBSERVATION"
    UNDERLYING_QUOTE = "UNDERLYING_QUOTE"
    OPTION_CONTRACT_QUOTE = "OPTION_CONTRACT_QUOTE"
    OI_UPDATE = "OI_UPDATE"
    OPENING_BAR_AVAILABLE = "OPENING_BAR_AVAILABLE"
    PREMARKET_PREPARATION_TIME = "PREMARKET_PREPARATION_TIME"
    MARKET_OPEN_TIME = "MARKET_OPEN_TIME"
    ORPT_TIME = "ORPT_TIME"
    RC_TIME = "RC_TIME"
    EOD_EVALUATION_TIME = "EOD_EVALUATION_TIME"
    SESSION_END_TIME = "SESSION_END_TIME"
    CONFIGURATION_READY = "CONFIGURATION_READY"
    POSITION_RECONCILIATION_AVAILABLE = "POSITION_RECONCILIATION_AVAILABLE"
    STRATEGY_ENABLED = "STRATEGY_ENABLED"
    STRATEGY_DISABLED = "STRATEGY_DISABLED"
    OPERATOR_CANCEL = "OPERATOR_CANCEL"
    RISK_CANCEL = "RISK_CANCEL"
    PROCESS_RESUME = "PROCESS_RESUME"


class RuntimeDeliveryClass(str, Enum):
    CONFLATABLE_STATE_UPDATE = "CONFLATABLE_STATE_UPDATE"
    NON_CONFLATABLE_CRITICAL_EVENT = "NON_CONFLATABLE_CRITICAL_EVENT"


class RuntimeFreshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    OUT_OF_ORDER = "OUT_OF_ORDER"


class RuntimeStreamKind(str, Enum):
    FRESH_ENTRY = "FRESH_ENTRY"
    POSITION_CYCLE = "POSITION_CYCLE"


class RuntimeStreamStatus(str, Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


CONFLATABLE_EVENT_TYPES = frozenset(
    {
        RuntimeEventType.UNDERLYING_QUOTE,
        RuntimeEventType.OPTION_CONTRACT_QUOTE,
        RuntimeEventType.OI_UPDATE,
    }
)


CRITICAL_EVENT_TYPES = frozenset(set(RuntimeEventType) - set(CONFLATABLE_EVENT_TYPES))


@dataclass(frozen=True, slots=True)
class NormalizedRuntimeEvent:
    event_id: str
    event_type: RuntimeEventType
    trading_date: date
    exchange: str
    session: str
    effective_timestamp: datetime
    source_timestamp: datetime
    dispatch_timestamp: datetime
    sequence_identity: int
    instrument_identity: str | None
    contract_identity: str | None = None
    strategy_instance_target: str | None = None
    position_cycle_target: str | None = None
    provenance: Mapping[str, Any] = MappingProxyType({})
    freshness: RuntimeFreshness = RuntimeFreshness.FRESH
    payload: Mapping[str, Any] = MappingProxyType({})
    payload_hash: str = ""

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must be non-empty")
        if self.sequence_identity < 0:
            raise ValueError("sequence_identity must be non-negative")
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        object.__setattr__(self, "payload", _freeze(self.payload))
        object.__setattr__(self, "payload_hash", self.payload_hash or runtime_hash(self.payload))

    @property
    def delivery_class(self) -> RuntimeDeliveryClass:
        if self.event_type in CONFLATABLE_EVENT_TYPES:
            return RuntimeDeliveryClass.CONFLATABLE_STATE_UPDATE
        return RuntimeDeliveryClass.NON_CONFLATABLE_CRITICAL_EVENT

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class InstrumentMarketSnapshot:
    snapshot_id: str
    instrument_identity: str
    trading_date: date
    ltp: float | None = None
    bid: float | None = None
    ask: float | None = None
    oi: float | None = None
    current_day_high: float | None = None
    current_day_low: float | None = None
    opening_value: float | None = None
    source_timestamp: datetime | None = None
    freshness: RuntimeFreshness = RuntimeFreshness.MISSING
    sequence_identity: int = -1
    source_event_id: str | None = None
    snapshot_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_hash", self.snapshot_hash or runtime_hash(self._business_payload()))

    def _business_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("snapshot_hash", None)
        return data

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class ContractMarketSnapshot(InstrumentMarketSnapshot):
    contract_identity: str = ""
    underlying_instrument_identity: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotUpdateResult:
    status: str
    snapshot: InstrumentMarketSnapshot | ContractMarketSnapshot | None
    reason: str
    event_id: str


class InstrumentStateOwner:
    def __init__(self, instrument_identity: str, *, contract_identity: str | None = None) -> None:
        self.instrument_identity = instrument_identity
        self.contract_identity = contract_identity
        self._snapshot: InstrumentMarketSnapshot | ContractMarketSnapshot | None = None
        self._seen: dict[str, NormalizedRuntimeEvent] = {}
        self.conflation_count = 0
        self.stale_count = 0
        self.out_of_order_count = 0

    @property
    def snapshot(self) -> InstrumentMarketSnapshot | ContractMarketSnapshot | None:
        return self._snapshot

    def apply(self, event: NormalizedRuntimeEvent) -> SnapshotUpdateResult:
        expected_contract = self.contract_identity
        if event.instrument_identity != self.instrument_identity:
            return SnapshotUpdateResult("REJECTED_WRONG_INSTRUMENT", self._snapshot, "Event instrument does not match owner.", event.event_id)
        if expected_contract and event.contract_identity != expected_contract:
            return SnapshotUpdateResult("REJECTED_WRONG_CONTRACT", self._snapshot, "Event contract does not match owner.", event.event_id)
        existing = self._seen.get(event.event_id)
        if existing is not None:
            if existing.to_dict() == event.to_dict():
                return SnapshotUpdateResult("IDEMPOTENT_DUPLICATE", self._snapshot, "Duplicate event is identical.", event.event_id)
            return SnapshotUpdateResult("CONFLICTING_DUPLICATE", self._snapshot, "Duplicate event id has conflicting content.", event.event_id)
        self._seen[event.event_id] = event
        if self._snapshot and event.trading_date != self._snapshot.trading_date:
            return SnapshotUpdateResult("REJECTED_MIXED_TRADING_DATE", self._snapshot, "Snapshot trading date would be mixed.", event.event_id)
        if self._snapshot and event.sequence_identity < self._snapshot.sequence_identity:
            self.stale_count += 1
            return SnapshotUpdateResult("STALE_IGNORED", self._snapshot, "Older sequence ignored.", event.event_id)
        if self._snapshot and event.sequence_identity == self._snapshot.sequence_identity and event.event_id != self._snapshot.source_event_id:
            self.out_of_order_count += 1
            return SnapshotUpdateResult("OUT_OF_ORDER_BLOCKED", self._snapshot, "Same sequence from a different event is not coherent.", event.event_id)
        if self._snapshot and event.delivery_class is RuntimeDeliveryClass.CONFLATABLE_STATE_UPDATE:
            self.conflation_count += 1
        self._snapshot = self._build_snapshot(event)
        return SnapshotUpdateResult("UPDATED", self._snapshot, "Snapshot updated.", event.event_id)

    def _build_snapshot(self, event: NormalizedRuntimeEvent) -> InstrumentMarketSnapshot | ContractMarketSnapshot:
        payload = event.payload
        cls = ContractMarketSnapshot if event.contract_identity else InstrumentMarketSnapshot
        kwargs = {
            "snapshot_id": f"{event.event_id}:snapshot",
            "instrument_identity": event.instrument_identity or "",
            "trading_date": event.trading_date,
            "ltp": _float(payload.get("ltp")),
            "bid": _float(payload.get("bid")),
            "ask": _float(payload.get("ask")),
            "oi": _float(payload.get("oi")),
            "current_day_high": _float(payload.get("current_day_high") or payload.get("high")),
            "current_day_low": _float(payload.get("current_day_low") or payload.get("low")),
            "opening_value": _float(payload.get("opening_value") or payload.get("open")),
            "source_timestamp": event.source_timestamp,
            "freshness": event.freshness,
            "sequence_identity": event.sequence_identity,
            "source_event_id": event.event_id,
        }
        if cls is ContractMarketSnapshot:
            kwargs["contract_identity"] = event.contract_identity or ""
            kwargs["underlying_instrument_identity"] = event.instrument_identity
        return cls(**kwargs)


@dataclass(frozen=True, slots=True)
class RuntimeSubscriptionSnapshot:
    underlying_to_strategy_instances: Mapping[str, tuple[str, ...]]
    underlying_to_position_cycles: Mapping[str, tuple[str, ...]]
    contract_to_strategy_instances: Mapping[str, tuple[str, ...]]
    contract_to_position_cycles: Mapping[str, tuple[str, ...]]
    subscription_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "underlying_to_strategy_instances", _freeze_subscription(self.underlying_to_strategy_instances))
        object.__setattr__(self, "underlying_to_position_cycles", _freeze_subscription(self.underlying_to_position_cycles))
        object.__setattr__(self, "contract_to_strategy_instances", _freeze_subscription(self.contract_to_strategy_instances))
        object.__setattr__(self, "contract_to_position_cycles", _freeze_subscription(self.contract_to_position_cycles))
        object.__setattr__(self, "subscription_hash", self.subscription_hash or runtime_hash(self.to_dict() | {"subscription_hash": ""}))

    def interested_strategies(self, *, instrument: str | None, contract: str | None) -> tuple[str, ...]:
        values: set[str] = set()
        if instrument:
            values.update(self.underlying_to_strategy_instances.get(instrument, ()))
        if contract:
            values.update(self.contract_to_strategy_instances.get(contract, ()))
        return tuple(sorted(values))

    def interested_positions(self, *, instrument: str | None, contract: str | None) -> tuple[str, ...]:
        values: set[str] = set()
        if instrument:
            values.update(self.underlying_to_position_cycles.get(instrument, ()))
        if contract:
            values.update(self.contract_to_position_cycles.get(contract, ()))
        return tuple(sorted(values))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


class RuntimeSubscriptionIndex:
    def __init__(self) -> None:
        self._underlying_strategy: dict[str, set[str]] = {}
        self._underlying_position: dict[str, set[str]] = {}
        self._contract_strategy: dict[str, set[str]] = {}
        self._contract_position: dict[str, set[str]] = {}

    def add_strategy(self, strategy_instance_id: str, *, underlying: str | None = None, contract: str | None = None) -> None:
        if underlying:
            self._underlying_strategy.setdefault(underlying, set()).add(strategy_instance_id)
        if contract:
            self._contract_strategy.setdefault(contract, set()).add(strategy_instance_id)

    def add_position(self, position_cycle_id: str, *, underlying: str | None = None, contract: str | None = None) -> None:
        if underlying:
            self._underlying_position.setdefault(underlying, set()).add(position_cycle_id)
        if contract:
            self._contract_position.setdefault(contract, set()).add(position_cycle_id)

    def remove_strategy(self, strategy_instance_id: str) -> None:
        _remove_value(self._underlying_strategy, strategy_instance_id)
        _remove_value(self._contract_strategy, strategy_instance_id)

    def remove_position(self, position_cycle_id: str) -> None:
        _remove_value(self._underlying_position, position_cycle_id)
        _remove_value(self._contract_position, position_cycle_id)

    def snapshot(self) -> RuntimeSubscriptionSnapshot:
        return RuntimeSubscriptionSnapshot(
            _copy_subscriptions(self._underlying_strategy),
            _copy_subscriptions(self._underlying_position),
            _copy_subscriptions(self._contract_strategy),
            _copy_subscriptions(self._contract_position),
        )


@dataclass(frozen=True, slots=True)
class RuntimeCoherentSnapshotPolicy:
    max_age_seconds: int
    max_underlying_contract_skew_seconds: int


@dataclass(frozen=True, slots=True)
class RuntimeSnapshotCoherenceResult:
    status: str
    reason: str
    underlying_snapshot_hash: str | None
    contract_snapshot_hash: str | None


def validate_snapshot_coherence(
    *,
    trading_date: date,
    evaluation_timestamp: datetime,
    underlying: InstrumentMarketSnapshot | None,
    contract: ContractMarketSnapshot | None = None,
    policy: RuntimeCoherentSnapshotPolicy = RuntimeCoherentSnapshotPolicy(120, 120),
) -> RuntimeSnapshotCoherenceResult:
    if underlying is None:
        return RuntimeSnapshotCoherenceResult("MISSING_UNDERLYING", "Underlying snapshot is required.", None, None)
    if underlying.trading_date != trading_date or (contract and contract.trading_date != trading_date):
        return RuntimeSnapshotCoherenceResult("MIXED_TRADING_DATE", "Snapshot trading date does not match evaluation date.", underlying.snapshot_hash, contract.snapshot_hash if contract else None)
    if underlying.source_timestamp is None:
        return RuntimeSnapshotCoherenceResult("STALE_FIELD", "Underlying snapshot has no source timestamp.", underlying.snapshot_hash, contract.snapshot_hash if contract else None)
    if abs((evaluation_timestamp - underlying.source_timestamp).total_seconds()) > policy.max_age_seconds:
        return RuntimeSnapshotCoherenceResult("STALE_SNAPSHOT", "Underlying snapshot exceeds max-age policy.", underlying.snapshot_hash, contract.snapshot_hash if contract else None)
    if contract and contract.source_timestamp:
        skew = abs((underlying.source_timestamp - contract.source_timestamp).total_seconds())
        if skew > policy.max_underlying_contract_skew_seconds:
            return RuntimeSnapshotCoherenceResult("INCOHERENT_UNDERLYING_CONTRACT_TIMESTAMPS", "Underlying and contract timestamps exceed skew policy.", underlying.snapshot_hash, contract.snapshot_hash)
    return RuntimeSnapshotCoherenceResult("COHERENT", "Snapshot set is coherent.", underlying.snapshot_hash, contract.snapshot_hash if contract else None)


@dataclass(frozen=True, slots=True)
class FreshEntryRuntimeCoordinator:
    strategy_instance_id: str
    trading_date: date
    coordination_input_factory: Callable[[tuple[OfflineCoordinationEvent, ...]], OfflineTradingDayCoordinationInput]
    status: RuntimeStreamStatus = RuntimeStreamStatus.CREATED
    consumed_event_ids: tuple[str, ...] = ()
    latest_result: TradingDayCoordinationResult | None = None
    block_code: str | None = None

    def consume(self, events: tuple[NormalizedRuntimeEvent, ...]) -> FreshEntryRuntimeCoordinator:
        if self.status is RuntimeStreamStatus.DISABLED:
            return self
        relevant = tuple(event for event in events if event.strategy_instance_target in (None, self.strategy_instance_id))
        offline_events = tuple(_to_fresh_offline_event(event, self.strategy_instance_id) for event in relevant if _fresh_event_type(event) is not None)
        if not offline_events:
            return replace(self, status=RuntimeStreamStatus.ACTIVE)
        request = self.coordination_input_factory(offline_events)
        result = OfflineTradingDayCoordinator().coordinate(request)
        status = RuntimeStreamStatus.COMPLETED if result.block_code is None else RuntimeStreamStatus.BLOCKED
        return replace(self, status=status, consumed_event_ids=tuple(event.event_id for event in relevant), latest_result=result, block_code=result.block_code)


@dataclass(frozen=True, slots=True)
class PositionCycleRuntimeCoordinator:
    position_cycle_id: str
    trading_date: date
    lifecycle_context_factory: Callable[[tuple[NormalizedRuntimeEvent, ...]], PositionLifecycleContext]
    eod_decision_factory: Callable[[PositionLifecycleContext], OfflineCarriedPositionEodDecision] | None = None
    status: RuntimeStreamStatus = RuntimeStreamStatus.CREATED
    consumed_event_ids: tuple[str, ...] = ()
    latest_result: OfflineCarriedPositionTradingDay | None = None
    block_code: str | None = None

    def consume(self, events: tuple[NormalizedRuntimeEvent, ...]) -> PositionCycleRuntimeCoordinator:
        relevant = tuple(event for event in events if event.position_cycle_target in (None, self.position_cycle_id))
        critical_names = {event.event_type for event in relevant}
        if RuntimeEventType.POSITION_RECONCILIATION_AVAILABLE not in critical_names:
            return replace(self, status=RuntimeStreamStatus.ACTIVE)
        needs_rc = RuntimeEventType.RC_TIME in critical_names or any(event.event_type is RuntimeEventType.OPTION_CONTRACT_QUOTE and event.payload.get("observation") == "RC" for event in relevant)
        needs_eod = RuntimeEventType.EOD_EVALUATION_TIME in critical_names
        context = self.lifecycle_context_factory(relevant)
        factory = self.eod_decision_factory if needs_eod or needs_rc else None
        result = OfflineCarriedPositionTradingDayCoordinator().coordinate(OfflineCarriedPositionTradingDayInput(f"m15-{self.position_cycle_id}", context, factory))
        status = RuntimeStreamStatus.COMPLETED if result.block_code is None else RuntimeStreamStatus.BLOCKED
        return replace(self, status=status, consumed_event_ids=tuple(event.event_id for event in relevant), latest_result=result, block_code=result.block_code)


@dataclass(frozen=True, slots=True)
class RuntimeCheckpoint:
    runtime_stream_identity: str
    current_state: str
    consumed_event_ids: tuple[str, ...]
    latest_snapshot_hashes: Mapping[str, str]
    artifact_hashes: Mapping[str, str]
    configuration_hash: str
    rule_matrix_version: str
    checkpoint_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "consumed_event_ids", tuple(self.consumed_event_ids))
        object.__setattr__(self, "latest_snapshot_hashes", _freeze(self.latest_snapshot_hashes))
        object.__setattr__(self, "artifact_hashes", _freeze(self.artifact_hashes))
        object.__setattr__(self, "checkpoint_hash", self.checkpoint_hash or runtime_hash(self.to_dict() | {"checkpoint_hash": ""}))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class RuntimeSimulationResult:
    schema_version: str
    trading_date: date
    processed_event_ids: tuple[str, ...]
    critical_event_ids: tuple[str, ...]
    conflation_diagnostics: Mapping[str, int]
    subscription_snapshot: RuntimeSubscriptionSnapshot
    fresh_entry_results: Mapping[str, TradingDayCoordinationResult]
    position_cycle_results: Mapping[str, OfflineCarriedPositionTradingDay]
    blocked_streams: Mapping[str, str]
    checkpoints: Mapping[str, RuntimeCheckpoint]
    performance: Mapping[str, float | int]
    authority: Mapping[str, bool | str]
    result_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "processed_event_ids", tuple(self.processed_event_ids))
        object.__setattr__(self, "critical_event_ids", tuple(self.critical_event_ids))
        object.__setattr__(self, "conflation_diagnostics", _freeze(self.conflation_diagnostics))
        object.__setattr__(self, "fresh_entry_results", _freeze(self.fresh_entry_results))
        object.__setattr__(self, "position_cycle_results", _freeze(self.position_cycle_results))
        object.__setattr__(self, "blocked_streams", _freeze(self.blocked_streams))
        object.__setattr__(self, "checkpoints", _freeze(self.checkpoints))
        object.__setattr__(self, "performance", _freeze(self.performance))
        object.__setattr__(self, "authority", _freeze(self.authority))
        object.__setattr__(self, "result_hash", self.result_hash or runtime_hash(self._business_payload()))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return _canonical_json(self._business_payload() | {"result_hash": self.result_hash})

    def _business_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("result_hash", None)
        data.pop("performance", None)
        return _strip_performance(data)


class DeterministicRuntimeCoordinator:
    schema_version = "tfis.phase3d.m15.runtime_coordination.v1"

    def run(
        self,
        *,
        trading_date: date,
        events: Iterable[NormalizedRuntimeEvent],
        subscriptions: RuntimeSubscriptionIndex,
        fresh_streams: Mapping[str, FreshEntryRuntimeCoordinator] | None = None,
        position_streams: Mapping[str, PositionCycleRuntimeCoordinator] | None = None,
        configuration_hash: str = "UNKNOWN",
        rule_matrix_version: str = "tfis_authoritative_workbook_rule_matrix.v1",
        expected_checkpoint_hashes: Mapping[str, str] | None = None,
    ) -> RuntimeSimulationResult:
        started = perf_counter()
        ordered = tuple(sorted(events, key=lambda item: (item.effective_timestamp, item.sequence_identity, item.event_id)))
        processed: list[str] = []
        critical: list[str] = []
        blocked: dict[str, str] = {}
        owners: dict[tuple[str, str | None], InstrumentStateOwner] = {}
        pending_conflatable: dict[tuple[str | None, str | None, RuntimeEventType], NormalizedRuntimeEvent] = {}
        latencies: list[float] = []
        subscription_snapshot = subscriptions.snapshot()

        for event in ordered:
            event_start = perf_counter()
            if event.trading_date != trading_date:
                blocked[f"event:{event.event_id}"] = "WRONG_TRADING_DATE"
                continue
            if event.delivery_class is RuntimeDeliveryClass.CONFLATABLE_STATE_UPDATE:
                pending_conflatable[(event.instrument_identity, event.contract_identity, event.event_type)] = event
            else:
                critical.append(event.event_id)
                if event.event_type is RuntimeEventType.SESSION_END_TIME:
                    processed.append(event.event_id)
                    break
            if event.event_type in {RuntimeEventType.UNDERLYING_QUOTE, RuntimeEventType.OPTION_CONTRACT_QUOTE, RuntimeEventType.OI_UPDATE, RuntimeEventType.SESSION_OPEN_OBSERVATION, RuntimeEventType.OPENING_BAR_AVAILABLE}:
                owner_key = (event.instrument_identity or "", event.contract_identity)
                owner = owners.setdefault(owner_key, InstrumentStateOwner(event.instrument_identity or "", contract_identity=event.contract_identity))
                update = owner.apply(event)
                if update.status.startswith("REJECTED") or update.status == "CONFLICTING_DUPLICATE":
                    blocked[f"event:{event.event_id}"] = update.status
            processed.append(event.event_id)
            latencies.append(perf_counter() - event_start)

        routed_events = tuple(ordered)
        fresh_results: dict[str, TradingDayCoordinationResult] = {}
        position_results: dict[str, OfflineCarriedPositionTradingDay] = {}
        checkpoints: dict[str, RuntimeCheckpoint] = {}

        for stream_id, stream in sorted((fresh_streams or {}).items()):
            if _checkpoint_mismatch(stream_id, expected_checkpoint_hashes, configuration_hash, rule_matrix_version):
                blocked[stream_id] = "CHECKPOINT_MISMATCH"
                continue
            interested = self._events_for_strategy(routed_events, subscription_snapshot, stream.strategy_instance_id)
            next_stream = stream.consume(interested)
            if next_stream.latest_result:
                fresh_results[stream_id] = next_stream.latest_result
            if next_stream.block_code:
                blocked[stream_id] = next_stream.block_code
            checkpoints[stream_id] = _fresh_checkpoint(stream_id, next_stream, owners, configuration_hash, rule_matrix_version)

        for stream_id, stream in sorted((position_streams or {}).items()):
            if _checkpoint_mismatch(stream_id, expected_checkpoint_hashes, configuration_hash, rule_matrix_version):
                blocked[stream_id] = "CHECKPOINT_MISMATCH"
                continue
            interested = self._events_for_position(routed_events, subscription_snapshot, stream.position_cycle_id)
            next_stream = stream.consume(interested)
            if next_stream.latest_result:
                position_results[stream_id] = next_stream.latest_result
            if next_stream.block_code:
                blocked[stream_id] = next_stream.block_code
            checkpoints[stream_id] = _position_checkpoint(stream_id, next_stream, owners, configuration_hash, rule_matrix_version)

        owner_conflations = sum(owner.conflation_count for owner in owners.values())
        performance = {
            "event_count": len(processed),
            "strategy_instance_count": len(fresh_streams or {}),
            "position_cycle_count": len(position_streams or {}),
            "instrument_count": len(owners),
            "quote_burst_size": len([event for event in ordered if event.delivery_class is RuntimeDeliveryClass.CONFLATABLE_STATE_UPDATE]),
            "total_processing_seconds": perf_counter() - started,
            "per_event_median_seconds": median(latencies) if latencies else 0.0,
            "per_event_p95_seconds": sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0.0,
            "maximum_pending_conflatable_updates": len(pending_conflatable),
            "critical_event_processing_count": len(critical),
        }
        return RuntimeSimulationResult(
            schema_version=self.schema_version,
            trading_date=trading_date,
            processed_event_ids=tuple(processed),
            critical_event_ids=tuple(critical),
            conflation_diagnostics={"owner_conflations": owner_conflations, "pending_latest_updates": len(pending_conflatable)},
            subscription_snapshot=subscription_snapshot,
            fresh_entry_results=fresh_results,
            position_cycle_results=position_results,
            blocked_streams=blocked,
            checkpoints=checkpoints,
            performance=performance,
            authority={
                "mode": "SHADOW_ONLY",
                "broker_submission": False,
                "paper_submission": False,
                "live_submission": False,
                "order_modification": False,
                "order_cancellation": False,
                "position_mutation": False,
                "square_off_execution": False,
                "carry_persistence": False,
            },
        )

    def _events_for_strategy(self, events: tuple[NormalizedRuntimeEvent, ...], subscriptions: RuntimeSubscriptionSnapshot, strategy_id: str) -> tuple[NormalizedRuntimeEvent, ...]:
        selected = []
        for event in events:
            if event.strategy_instance_target is not None:
                if event.strategy_instance_target == strategy_id:
                    selected.append(event)
                continue
            if strategy_id in subscriptions.interested_strategies(instrument=event.instrument_identity, contract=event.contract_identity):
                selected.append(event)
        return tuple(selected)

    def _events_for_position(self, events: tuple[NormalizedRuntimeEvent, ...], subscriptions: RuntimeSubscriptionSnapshot, position_id: str) -> tuple[NormalizedRuntimeEvent, ...]:
        selected = []
        for event in events:
            if event.position_cycle_target is not None:
                if event.position_cycle_target == position_id:
                    selected.append(event)
                continue
            if position_id in subscriptions.interested_positions(instrument=event.instrument_identity, contract=event.contract_identity):
                selected.append(event)
        return tuple(selected)


def runtime_hash(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _fresh_event_type(event: NormalizedRuntimeEvent) -> CoordinationEventType | None:
    mapping = {
        RuntimeEventType.CONFIGURATION_READY: CoordinationEventType.STARTUP_COMPLETED,
        RuntimeEventType.PREMARKET_PREPARATION_TIME: CoordinationEventType.PREMARKET_DATA_READY,
        RuntimeEventType.MARKET_OPEN_TIME: CoordinationEventType.MARKET_OPEN_OBSERVED,
        RuntimeEventType.SESSION_OPEN_OBSERVATION: CoordinationEventType.MARKET_OPEN_OBSERVED,
        RuntimeEventType.ORPT_TIME: CoordinationEventType.ORPT_REACHED,
        RuntimeEventType.RC_TIME: CoordinationEventType.RC_REACHED,
        RuntimeEventType.EOD_EVALUATION_TIME: CoordinationEventType.OFFLINE_HANDOFF_REQUESTED,
        RuntimeEventType.OPERATOR_CANCEL: CoordinationEventType.OPERATOR_CANCELLED,
        RuntimeEventType.RISK_CANCEL: CoordinationEventType.RISK_CANCELLED,
        RuntimeEventType.SESSION_END_TIME: CoordinationEventType.SESSION_ENDED,
    }
    return mapping.get(event.event_type)


def _to_fresh_offline_event(event: NormalizedRuntimeEvent, strategy_instance_id: str) -> OfflineCoordinationEvent:
    mapped = _fresh_event_type(event)
    if mapped is None:
        raise ValueError("event cannot be converted to fresh-entry offline event")
    return OfflineCoordinationEvent(
        event_id=event.event_id,
        strategy_instance_id=strategy_instance_id,
        trading_date=event.trading_date,
        event_type=mapped,
        effective_timestamp=event.effective_timestamp,
        source_timestamp=event.source_timestamp,
        source_classification=event.freshness.value,
        provenance={"runtime_event_id": event.event_id, "runtime_event_type": event.event_type.value},
        sequence_identity=event.sequence_identity,
        instrument=event.instrument_identity,
    )


def _checkpoint_mismatch(stream_id: str, expected: Mapping[str, str] | None, configuration_hash: str, rule_matrix_version: str) -> bool:
    if not expected or stream_id not in expected:
        return False
    probe = runtime_hash({"configuration_hash": configuration_hash, "rule_matrix_version": rule_matrix_version, "stream_id": stream_id})
    return expected[stream_id] not in {probe}


def _fresh_checkpoint(
    stream_id: str,
    stream: FreshEntryRuntimeCoordinator,
    owners: Mapping[tuple[str, str | None], InstrumentStateOwner],
    configuration_hash: str,
    rule_matrix_version: str,
) -> RuntimeCheckpoint:
    result = stream.latest_result
    artifacts = {}
    if result:
        artifacts = {
            "premarket_plan": result.premarket_plan_hash or "",
            "opening_context": result.opening_context_hash or "",
            "effective_plan": result.effective_execution_plan_hash or "",
            "handoff": result.execution_handoff_id or "",
        }
    return RuntimeCheckpoint(stream_id, stream.status.value, stream.consumed_event_ids, _snapshot_hashes(owners), artifacts, configuration_hash, rule_matrix_version)


def _position_checkpoint(
    stream_id: str,
    stream: PositionCycleRuntimeCoordinator,
    owners: Mapping[tuple[str, str | None], InstrumentStateOwner],
    configuration_hash: str,
    rule_matrix_version: str,
) -> RuntimeCheckpoint:
    result = stream.latest_result
    artifacts = {}
    if result:
        artifacts = {
            "lifecycle_context": result.lifecycle_context.context_hash,
            "lifecycle_handoff": result.lifecycle_handoff.evidence_hash,
            "eod_decision": result.eod_decision.decision_hash if result.eod_decision else "",
        }
    return RuntimeCheckpoint(stream_id, stream.status.value, stream.consumed_event_ids, _snapshot_hashes(owners), artifacts, configuration_hash, rule_matrix_version)


def _snapshot_hashes(owners: Mapping[tuple[str, str | None], InstrumentStateOwner]) -> dict[str, str]:
    return {
        ":".join(key_item for key_item in key if key_item): owner.snapshot.snapshot_hash
        for key, owner in sorted(owners.items(), key=lambda item: (item[0][0], item[0][1] or ""))
        if owner.snapshot
    }


def _freeze_subscription(value: Mapping[str, Iterable[str]]) -> MappingProxyType:
    return MappingProxyType({str(key): tuple(sorted(str(item) for item in items)) for key, items in sorted(value.items())})


def _copy_subscriptions(value: Mapping[str, set[str]]) -> dict[str, tuple[str, ...]]:
    return {key: tuple(sorted(items)) for key, items in sorted(value.items()) if items}


def _remove_value(mapping: dict[str, set[str]], value: str) -> None:
    empty: list[str] = []
    for key, items in mapping.items():
        items.discard(value)
        if not items:
            empty.append(key)
    for key in empty:
        del mapping[key]


def _float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


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
    if isinstance(value, Decimal):
        return str(value)
    return value


def _strip_performance(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _strip_performance(item) for key, item in value.items() if key != "performance"}
    if isinstance(value, list):
        return [_strip_performance(item) for item in value]
    return value
