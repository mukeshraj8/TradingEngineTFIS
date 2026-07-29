from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Mapping

from tfis.domain import (
    TFISContractIdentity,
    TFISDirection,
    TFISExecutionSide,
    TFISFormulaTrace,
    TFISProductType,
    TFISRuntimeInput,
)


class PolicyStatus(str, Enum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def _freeze(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(_freeze(item) for item in sorted(value, key=str))
    return value


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _serializable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _serializable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value


@dataclass(frozen=True, slots=True)
class PolicyResult:
    policy_name: str
    evaluated_at: datetime
    status: PolicyStatus
    applicable: bool
    reason: str
    requirement_id: str | None = None
    formula: str | None = None
    reference: str | None = None
    calculated_value: Any = None
    inputs: Mapping[str, Any] = MappingProxyType({})
    intermediate_values: Mapping[str, Any] = MappingProxyType({})
    quality_status: str | None = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.policy_name.strip():
            raise ValueError("policy_name must be a non-empty string")
        if not self.reason.strip():
            raise ValueError("reason must be a non-empty string")
        if self.status is PolicyStatus.NOT_APPLICABLE and self.applicable:
            raise ValueError("NOT_APPLICABLE policy results cannot be applicable")
        object.__setattr__(self, "inputs", _freeze(self.inputs))
        object.__setattr__(
            self,
            "intermediate_values",
            _freeze(self.intermediate_values),
        )
        object.__setattr__(self, "evidence", _freeze(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )


@dataclass(frozen=True, slots=True)
class ProductPolicyResult(PolicyResult):
    product_type: TFISProductType | None = None
    direction: TFISDirection | None = None
    execution_side: TFISExecutionSide | None = None
    branch: str | None = None


@dataclass(frozen=True, slots=True)
class EntryPolicyResult(PolicyResult):
    entry_value: float | None = None
    formula_trace: TFISFormulaTrace | None = None


@dataclass(frozen=True, slots=True)
class GapPolicyResult(PolicyResult):
    branch: str | None = None


@dataclass(frozen=True, slots=True)
class MissedEntryPolicyResult(PolicyResult):
    missed: bool | None = None
    branch: str | None = None


@dataclass(frozen=True, slots=True)
class ContractSelectionPolicyResult(PolicyResult):
    selected_contract: TFISContractIdentity | None = None
    candidate_count: int | None = None

    def __post_init__(self) -> None:
        super(ContractSelectionPolicyResult, self).__post_init__()
        if self.candidate_count is not None and self.candidate_count < 0:
            raise ValueError("candidate_count must be non-negative")


@dataclass(frozen=True, slots=True)
class TargetPolicyTarget:
    order: int
    target_price: float | None = None
    quantity: int | None = None
    quantity_pct: float | None = None
    formula: str | None = None
    reference: str | None = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if self.order < 0:
            raise ValueError("target order must be non-negative")
        if self.quantity is not None and self.quantity < 0:
            raise ValueError("target quantity must be non-negative")
        if self.quantity_pct is not None and not (0.0 <= self.quantity_pct <= 100.0):
            raise ValueError("target quantity_pct must be between 0 and 100")
        object.__setattr__(self, "evidence", _freeze(self.evidence))


@dataclass(frozen=True, slots=True)
class TargetPolicyResult(PolicyResult):
    targets: tuple[TargetPolicyTarget, ...] = ()

    def __post_init__(self) -> None:
        super(TargetPolicyResult, self).__post_init__()
        object.__setattr__(self, "targets", tuple(self.targets))
        orders = tuple(target.order for target in self.targets)
        if tuple(sorted(orders)) != orders:
            raise ValueError("targets must be ordered by ascending order")


@dataclass(frozen=True, slots=True)
class MSLPolicyResult(PolicyResult):
    stop_price: float | None = None
    direction: TFISDirection | None = None
    activation_timing: str | None = None
    quantity: int | None = None
    quantity_pct: float | None = None

    def __post_init__(self) -> None:
        super(MSLPolicyResult, self).__post_init__()
        if self.quantity is not None and self.quantity < 0:
            raise ValueError("MSL quantity must be non-negative")
        if self.quantity_pct is not None and not (0.0 <= self.quantity_pct <= 100.0):
            raise ValueError("MSL quantity_pct must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class ProductPolicyInput:
    runtime_input: TFISRuntimeInput


@dataclass(frozen=True, slots=True)
class EntryPolicyInput:
    runtime_input: TFISRuntimeInput
    product_result: ProductPolicyResult


@dataclass(frozen=True, slots=True)
class GapPolicyInput:
    runtime_input: TFISRuntimeInput
    product_result: ProductPolicyResult
    entry_result: EntryPolicyResult


@dataclass(frozen=True, slots=True)
class MissedEntryPolicyInput:
    runtime_input: TFISRuntimeInput
    product_result: ProductPolicyResult
    entry_result: EntryPolicyResult
    gap_result: GapPolicyResult


@dataclass(frozen=True, slots=True)
class ContractSelectionPolicyInput:
    runtime_input: TFISRuntimeInput
    product_result: ProductPolicyResult
    entry_result: EntryPolicyResult
    gap_result: GapPolicyResult
    missed_entry_result: MissedEntryPolicyResult


@dataclass(frozen=True, slots=True)
class TargetPolicyInput:
    runtime_input: TFISRuntimeInput
    product_result: ProductPolicyResult
    entry_result: EntryPolicyResult
    gap_result: GapPolicyResult
    missed_entry_result: MissedEntryPolicyResult
    contract_selection_result: ContractSelectionPolicyResult


@dataclass(frozen=True, slots=True)
class MSLPolicyInput:
    runtime_input: TFISRuntimeInput
    product_result: ProductPolicyResult
    entry_result: EntryPolicyResult
    gap_result: GapPolicyResult
    missed_entry_result: MissedEntryPolicyResult
    contract_selection_result: ContractSelectionPolicyResult
    target_result: TargetPolicyResult
