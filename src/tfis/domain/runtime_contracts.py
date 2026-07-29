from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Mapping

from .enums import MonthlyStatus, Segment


class TFISProductType(str, Enum):
    FUTURES = "FUTURES"
    OPTION_BUYING = "OPTION_BUYING"
    OPTION_SELLING = "OPTION_SELLING"
    EQUITY = "EQUITY"


class TFISDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class TFISExecutionSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TFISTradeResult(str, Enum):
    TRADE = "TRADE"
    NO_TRADE = "NO_TRADE"
    REJECTED = "REJECTED"
    CARRY_FORWARD = "CARRY_FORWARD"
    UNKNOWN = "UNKNOWN"


class TFISQuantityEffectType(str, Enum):
    ABSOLUTE = "ABSOLUTE"
    PERCENTAGE = "PERCENTAGE"
    REMAINING = "REMAINING"


def product_type_from_segment(segment: Segment) -> TFISProductType:
    if segment is Segment.FUTURES:
        return TFISProductType.FUTURES
    if segment is Segment.OPTIONS_BUY:
        return TFISProductType.OPTION_BUYING
    if segment is Segment.OPTIONS_SELL:
        return TFISProductType.OPTION_SELLING
    if segment is Segment.EQUITY:
        return TFISProductType.EQUITY
    raise ValueError(f"Unsupported segment for TFIS product type: {segment!r}")


def _freeze_value(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(_freeze_value(item) for item in sorted(value, key=str))
    return value


def _serializable_value(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _serializable_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _serializable_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_serializable_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _serializable_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _validate_order(order: int, name: str) -> None:
    if order < 0:
        raise ValueError(f"{name} must be non-negative")


def _validate_ordered(values: tuple[int, ...], name: str) -> None:
    if tuple(sorted(values)) != values:
        raise ValueError(f"{name} must be ordered by ascending order")


def _validate_quantity_effect(quantity: int | None, quantity_pct: float | None) -> None:
    if quantity is not None and quantity < 0:
        raise ValueError("quantity must be non-negative")
    if quantity_pct is not None and not (0.0 <= float(quantity_pct) <= 100.0):
        raise ValueError("quantity_pct must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class TFISContractIdentity:
    symbol: str | None = None
    exchange: str | None = None
    segment: Segment | None = None
    product_type: TFISProductType | None = None
    expiry: date | None = None
    strike: float | None = None
    option_type: str | None = None
    token: str | None = None
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)


@dataclass(frozen=True, slots=True)
class TFISOptionChainContext:
    as_of: datetime | None = None
    expiry_candidates: tuple[date, ...] = ()
    selected_expiry: date | None = None
    candidate_count: int | None = None
    reference_values: Mapping[str, Any] = MappingProxyType({})
    validation: Mapping[str, Any] = MappingProxyType({})
    provenance: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "expiry_candidates", tuple(self.expiry_candidates))
        object.__setattr__(self, "reference_values", _freeze_value(self.reference_values))
        object.__setattr__(self, "validation", _freeze_value(self.validation))
        object.__setattr__(self, "provenance", _freeze_value(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)


@dataclass(frozen=True, slots=True)
class TFISFormulaTrace:
    name: str
    formula: str | None = None
    resolved_formula: str | None = None
    result: Any = None
    inputs: Mapping[str, Any] = MappingProxyType({})
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", _freeze_value(self.inputs))
        object.__setattr__(self, "evidence", _freeze_value(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)


@dataclass(frozen=True, slots=True)
class TFISPolicyResult:
    policy_name: str
    result: Any = None
    formula_trace: TFISFormulaTrace | None = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze_value(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)


@dataclass(frozen=True, slots=True)
class TargetStep:
    order: int
    label: str
    target_price: float | None = None
    quantity: int | None = None
    quantity_pct: float | None = None
    quantity_effect: TFISQuantityEffectType = TFISQuantityEffectType.ABSOLUTE
    activation_conditions: Mapping[str, Any] = MappingProxyType({})
    formula_trace: TFISFormulaTrace | None = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        _validate_order(self.order, "target order")
        _validate_quantity_effect(self.quantity, self.quantity_pct)
        object.__setattr__(self, "activation_conditions", _freeze_value(self.activation_conditions))
        object.__setattr__(self, "evidence", _freeze_value(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def comparison_key(self) -> str:
        return self.to_json()


@dataclass(frozen=True, slots=True)
class StopPlan:
    label: str
    stop_price: float | None = None
    quantity: int | None = None
    quantity_pct: float | None = None
    quantity_effect: TFISQuantityEffectType = TFISQuantityEffectType.REMAINING
    activation_conditions: Mapping[str, Any] = MappingProxyType({})
    formula_trace: TFISFormulaTrace | None = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        _validate_quantity_effect(self.quantity, self.quantity_pct)
        object.__setattr__(self, "activation_conditions", _freeze_value(self.activation_conditions))
        object.__setattr__(self, "evidence", _freeze_value(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def comparison_key(self) -> str:
        return self.to_json()


@dataclass(frozen=True, slots=True)
class TrailingStopStep:
    order: int
    label: str
    trigger_conditions: Mapping[str, Any]
    stop_price: float | None = None
    quantity: int | None = None
    quantity_pct: float | None = None
    quantity_effect: TFISQuantityEffectType = TFISQuantityEffectType.REMAINING
    formula_trace: TFISFormulaTrace | None = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        _validate_order(self.order, "trailing stop order")
        _validate_quantity_effect(self.quantity, self.quantity_pct)
        object.__setattr__(self, "trigger_conditions", _freeze_value(self.trigger_conditions))
        object.__setattr__(self, "evidence", _freeze_value(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def comparison_key(self) -> str:
        return self.to_json()


@dataclass(frozen=True, slots=True)
class APSAction:
    order: int
    label: str
    action_type: str
    side: TFISExecutionSide | None = None
    quantity: int | None = None
    quantity_pct: float | None = None
    quantity_effect: TFISQuantityEffectType = TFISQuantityEffectType.REMAINING
    activation_conditions: Mapping[str, Any] = MappingProxyType({})
    formula_trace: TFISFormulaTrace | None = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        _validate_order(self.order, "APS action order")
        _validate_quantity_effect(self.quantity, self.quantity_pct)
        object.__setattr__(self, "activation_conditions", _freeze_value(self.activation_conditions))
        object.__setattr__(self, "evidence", _freeze_value(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def comparison_key(self) -> str:
        return self.to_json()


@dataclass(frozen=True, slots=True)
class ExitRule:
    order: int
    label: str
    side: TFISExecutionSide | None = None
    quantity: int | None = None
    quantity_pct: float | None = None
    quantity_effect: TFISQuantityEffectType = TFISQuantityEffectType.REMAINING
    activation_conditions: Mapping[str, Any] = MappingProxyType({})
    formula_trace: TFISFormulaTrace | None = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        _validate_order(self.order, "exit rule order")
        _validate_quantity_effect(self.quantity, self.quantity_pct)
        object.__setattr__(self, "activation_conditions", _freeze_value(self.activation_conditions))
        object.__setattr__(self, "evidence", _freeze_value(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def comparison_key(self) -> str:
        return self.to_json()


@dataclass(frozen=True, slots=True)
class LifecyclePlan:
    plan_id: str
    product_type: TFISProductType
    direction: TFISDirection
    entry_side: TFISExecutionSide
    exit_side: TFISExecutionSide | None = None
    position_quantity: int | None = None
    targets: tuple[TargetStep, ...] = ()
    stop_plan: StopPlan | None = None
    trailing_stop_steps: tuple[TrailingStopStep, ...] = ()
    aps_actions: tuple[APSAction, ...] = ()
    exit_rules: tuple[ExitRule, ...] = ()
    activation_conditions: Mapping[str, Any] = MappingProxyType({})
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id must be a non-empty string")
        object.__setattr__(self, "targets", tuple(self.targets))
        object.__setattr__(self, "trailing_stop_steps", tuple(self.trailing_stop_steps))
        object.__setattr__(self, "aps_actions", tuple(self.aps_actions))
        object.__setattr__(self, "exit_rules", tuple(self.exit_rules))
        _validate_ordered(tuple(item.order for item in self.targets), "targets")
        _validate_ordered(tuple(item.order for item in self.trailing_stop_steps), "trailing stop steps")
        _validate_ordered(tuple(item.order for item in self.aps_actions), "APS actions")
        _validate_ordered(tuple(item.order for item in self.exit_rules), "exit rules")
        object.__setattr__(self, "activation_conditions", _freeze_value(self.activation_conditions))
        object.__setattr__(self, "evidence", _freeze_value(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def comparison_key(self) -> str:
        return self.to_json()


@dataclass(frozen=True, slots=True)
class TFISRuntimeInput:
    evaluation_id: str
    evaluated_at: datetime
    strategy_code: str
    strategy_version: str | None
    strategy_branch: str | None
    symbol: str
    segment: Segment
    product_type: TFISProductType
    account_id: str | None
    lots: int | None
    quantity: int | None
    session_date: date
    session_label: str | None
    timezone: str
    price_source: str | None
    cmp: float | None
    contract: TFISContractIdentity | None
    monthly_status: MonthlyStatus | None
    monthly_status_evidence: Mapping[str, Any]
    market_structure_references: Mapping[str, Any]
    current_week_references: Mapping[str, Any]
    current_month_references: Mapping[str, Any]
    gap_context: Mapping[str, Any]
    option_chain_context: TFISOptionChainContext | None
    data_quality: Mapping[str, Any]
    provenance: Mapping[str, Any]
    configuration_snapshot: Mapping[str, Any]
    configuration_version: str | None
    runtime_values: Mapping[str, Any] = MappingProxyType({})
    product_specific: Mapping[str, Any] = MappingProxyType({})
    strategy_family_id: str | None = None
    strategy_definition_id: str | None = None
    strategy_instance_id: str | None = None
    resolved_configuration_hash: str | None = None

    def __post_init__(self) -> None:
        if not self.evaluation_id.strip():
            raise ValueError("evaluation_id must be a non-empty string")
        if not self.strategy_code.strip():
            raise ValueError("strategy_code must be a non-empty string")
        if self.strategy_instance_id is not None and not self.strategy_instance_id.strip():
            raise ValueError("strategy_instance_id must be non-empty when provided")
        if self.strategy_definition_id is not None and not self.strategy_definition_id.strip():
            raise ValueError("strategy_definition_id must be non-empty when provided")
        if not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if product_type_from_segment(self.segment) is not self.product_type:
            raise ValueError("product_type must match segment")
        for name in (
            "monthly_status_evidence",
            "market_structure_references",
            "current_week_references",
            "current_month_references",
            "gap_context",
            "data_quality",
            "provenance",
            "configuration_snapshot",
            "runtime_values",
            "product_specific",
        ):
            object.__setattr__(self, name, _freeze_value(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def comparison_key(self) -> str:
        return self.to_json()


@dataclass(frozen=True, slots=True)
class TFISDecision:
    evaluation_id: str
    decision_id: str
    decided_at: datetime
    strategy_code: str
    strategy_branch: str | None
    monthly_status_branch: str | None
    trade_result: TFISTradeResult
    product_type: TFISProductType
    direction: TFISDirection | None
    execution_side: TFISExecutionSide | None
    selected_instrument: TFISContractIdentity | None
    entry_calculation: TFISFormulaTrace | None
    gap_result: Mapping[str, Any]
    missed_entry_result: Mapping[str, Any]
    lots: int | None
    quantity: int | None
    target_policy: TFISPolicyResult | None
    msl_policy: TFISPolicyResult | None
    tsl_policy: TFISPolicyResult | None
    aps_policy: TFISPolicyResult | None
    final_exit_rule: Mapping[str, Any]
    rejection_reason_code: str | None
    rejection_reason: str | None
    intermediate_calculation_evidence: Mapping[str, Any]
    data_versions: Mapping[str, Any]
    configuration_versions: Mapping[str, Any]
    compatibility_payload: Mapping[str, Any] = MappingProxyType({})
    strategy_family_id: str | None = None
    strategy_definition_id: str | None = None
    strategy_version_identity: str | None = None
    strategy_instance_id: str | None = None
    resolved_configuration_hash: str | None = None

    def __post_init__(self) -> None:
        if not self.evaluation_id.strip():
            raise ValueError("evaluation_id must be a non-empty string")
        if not self.decision_id.strip():
            raise ValueError("decision_id must be a non-empty string")
        if not self.strategy_code.strip():
            raise ValueError("strategy_code must be a non-empty string")
        for name in (
            "gap_result",
            "missed_entry_result",
            "final_exit_rule",
            "intermediate_calculation_evidence",
            "data_versions",
            "configuration_versions",
            "compatibility_payload",
        ):
            object.__setattr__(self, name, _freeze_value(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return _serializable_value(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def comparison_key(self) -> str:
        return self.to_json()
