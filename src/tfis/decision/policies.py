from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    ContractSelectionPolicyInput,
    ContractSelectionPolicyResult,
    EntryPolicyInput,
    EntryPolicyResult,
    GapPolicyInput,
    GapPolicyResult,
    MSLPolicyInput,
    MSLPolicyResult,
    MissedEntryPolicyInput,
    MissedEntryPolicyResult,
    ProductPolicyInput,
    ProductPolicyResult,
    TargetPolicyInput,
    TargetPolicyResult,
)


@runtime_checkable
class ProductPolicy(Protocol):
    def evaluate(self, policy_input: ProductPolicyInput) -> ProductPolicyResult: ...


@runtime_checkable
class EntryPolicy(Protocol):
    def evaluate(self, policy_input: EntryPolicyInput) -> EntryPolicyResult: ...


@runtime_checkable
class GapPolicy(Protocol):
    def evaluate(self, policy_input: GapPolicyInput) -> GapPolicyResult: ...


@runtime_checkable
class MissedEntryPolicy(Protocol):
    def evaluate(
        self,
        policy_input: MissedEntryPolicyInput,
    ) -> MissedEntryPolicyResult: ...


@runtime_checkable
class ContractSelectionPolicy(Protocol):
    def evaluate(
        self,
        policy_input: ContractSelectionPolicyInput,
    ) -> ContractSelectionPolicyResult: ...


@runtime_checkable
class TargetPolicy(Protocol):
    def evaluate(self, policy_input: TargetPolicyInput) -> TargetPolicyResult: ...


@runtime_checkable
class MSLPolicy(Protocol):
    def evaluate(self, policy_input: MSLPolicyInput) -> MSLPolicyResult: ...
