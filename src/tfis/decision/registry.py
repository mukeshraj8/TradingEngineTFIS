from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .policies import (
    ContractSelectionPolicy,
    EntryPolicy,
    GapPolicy,
    MSLPolicy,
    MissedEntryPolicy,
    ProductPolicy,
    TargetPolicy,
)


class PolicyKind(str, Enum):
    PRODUCT = "PRODUCT"
    ENTRY = "ENTRY"
    GAP = "GAP"
    MISSED_ENTRY = "MISSED_ENTRY"
    CONTRACT_SELECTION = "CONTRACT_SELECTION"
    TARGET = "TARGET"
    MSL = "MSL"


PolicyImplementation = (
    ProductPolicy
    | EntryPolicy
    | GapPolicy
    | MissedEntryPolicy
    | ContractSelectionPolicy
    | TargetPolicy
    | MSLPolicy
)


@dataclass(frozen=True, slots=True)
class PolicySelection:
    product: str
    entry: str
    gap: str
    missed_entry: str
    contract_selection: str
    target: str
    msl: str

    def __post_init__(self) -> None:
        for name in (
            "product",
            "entry",
            "gap",
            "missed_entry",
            "contract_selection",
            "target",
            "msl",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} policy selection must be non-empty")


@dataclass(frozen=True, slots=True)
class DecisionPolicySet:
    product: ProductPolicy | None
    entry: EntryPolicy | None
    gap: GapPolicy | None
    missed_entry: MissedEntryPolicy | None
    contract_selection: ContractSelectionPolicy | None
    target: TargetPolicy | None
    msl: MSLPolicy | None
    selection: PolicySelection | None = None

    def missing_policy_kinds(self) -> tuple[PolicyKind, ...]:
        values = (
            (PolicyKind.PRODUCT, self.product),
            (PolicyKind.ENTRY, self.entry),
            (PolicyKind.GAP, self.gap),
            (PolicyKind.MISSED_ENTRY, self.missed_entry),
            (PolicyKind.CONTRACT_SELECTION, self.contract_selection),
            (PolicyKind.TARGET, self.target),
            (PolicyKind.MSL, self.msl),
        )
        return tuple(kind for kind, policy in values if policy is None)


class PolicyRegistry:
    """Immutable policy registry keyed only by explicit kind and policy name."""

    def __init__(
        self,
        policies: Mapping[tuple[PolicyKind, str], PolicyImplementation],
    ) -> None:
        normalized: dict[tuple[PolicyKind, str], PolicyImplementation] = {}
        for (kind, name), policy in policies.items():
            if not isinstance(kind, PolicyKind):
                raise TypeError("policy registry keys must use PolicyKind")
            normalized_name = name.strip()
            if not normalized_name:
                raise ValueError("policy registry names must be non-empty")
            key = (kind, normalized_name)
            if key in normalized:
                raise ValueError(f"duplicate policy registration: {kind.value}/{name}")
            normalized[key] = policy
        self._policies = MappingProxyType(normalized)

    def compose(self, selection: PolicySelection) -> DecisionPolicySet:
        return DecisionPolicySet(
            product=self._policies.get((PolicyKind.PRODUCT, selection.product)),
            entry=self._policies.get((PolicyKind.ENTRY, selection.entry)),
            gap=self._policies.get((PolicyKind.GAP, selection.gap)),
            missed_entry=self._policies.get(
                (PolicyKind.MISSED_ENTRY, selection.missed_entry)
            ),
            contract_selection=self._policies.get(
                (PolicyKind.CONTRACT_SELECTION, selection.contract_selection)
            ),
            target=self._policies.get((PolicyKind.TARGET, selection.target)),
            msl=self._policies.get((PolicyKind.MSL, selection.msl)),
            selection=selection,
        )
