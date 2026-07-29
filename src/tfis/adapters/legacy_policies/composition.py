from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from tfis.decision import PolicyKind, PolicyRegistry, PolicySelection
from tfis.domain import StrategyRule

from .policies import (
    LegacyUnsupportedGapPolicyAdapter,
    LegacyUnsupportedMissedEntryPolicyAdapter,
    S21ContractSelectionPolicyAdapter,
    S21EntryPolicyAdapter,
    S21MSLPolicyAdapter,
    S21ProductPolicyAdapter,
    S21TargetPolicyAdapter,
    S23ContractSelectionPolicyAdapter,
    S23EntryPolicyAdapter,
    S23GapPolicyAdapter,
    S23MSLPolicyAdapter,
    S23MissedEntryPolicyAdapter,
    S23ProductPolicyAdapter,
    S23TargetPolicyAdapter,
)


@dataclass(frozen=True, slots=True)
class StrategyPolicyComposition:
    strategy_code: str
    policy_selection: PolicySelection


_POLICY_SELECTIONS: Mapping[str, PolicySelection] = MappingProxyType(
    {
        "S21": PolicySelection(
            product="legacy.s21.option_selling.product",
            entry="legacy.s21.option_selling.entry",
            gap="legacy.option_selling.gap.not_configured",
            missed_entry="legacy.option_selling.missed_entry.not_configured",
            contract_selection="legacy.s21.option_selling.contract_selection",
            target="legacy.s21.option_selling.target",
            msl="legacy.s21.option_selling.msl",
        ),
        "S23": PolicySelection(
            product="legacy.s23.option_selling.product",
            entry="legacy.s23.option_selling.entry",
            gap="legacy.s23.gap.not_configured",
            missed_entry="legacy.s23.missed_entry.not_configured",
            contract_selection="legacy.s23.option_selling.contract_selection",
            target="legacy.s23.option_selling.target",
            msl="legacy.s23.option_selling.msl",
        ),
    }
)


def policy_selection_for_strategy(strategy_code: str) -> StrategyPolicyComposition:
    selection = _POLICY_SELECTIONS.get(strategy_code)
    if selection is None:
        raise KeyError(f"No legacy policy composition configured for {strategy_code!r}")
    return StrategyPolicyComposition(
        strategy_code=strategy_code,
        policy_selection=selection,
    )


class LegacyPolicyRegistryFactory:
    """Builds an explicit registry for one legacy strategy rule."""

    def build(self, strategy_rule: StrategyRule) -> PolicyRegistry:
        if strategy_rule.strategy_code == "S21":
            return PolicyRegistry(
                {
                    (
                        PolicyKind.PRODUCT,
                        "legacy.s21.option_selling.product",
                    ): S21ProductPolicyAdapter(strategy_rule),
                    (
                        PolicyKind.ENTRY,
                        "legacy.s21.option_selling.entry",
                    ): S21EntryPolicyAdapter(strategy_rule),
                    (
                        PolicyKind.GAP,
                        "legacy.option_selling.gap.not_configured",
                    ): LegacyUnsupportedGapPolicyAdapter(),
                    (
                        PolicyKind.MISSED_ENTRY,
                        "legacy.option_selling.missed_entry.not_configured",
                    ): LegacyUnsupportedMissedEntryPolicyAdapter(),
                    (
                        PolicyKind.CONTRACT_SELECTION,
                        "legacy.s21.option_selling.contract_selection",
                    ): S21ContractSelectionPolicyAdapter(strategy_rule),
                    (
                        PolicyKind.TARGET,
                        "legacy.s21.option_selling.target",
                    ): S21TargetPolicyAdapter(strategy_rule),
                    (
                        PolicyKind.MSL,
                        "legacy.s21.option_selling.msl",
                    ): S21MSLPolicyAdapter(strategy_rule),
                }
            )
        if strategy_rule.strategy_code == "S23":
            return PolicyRegistry(
                {
                    (
                        PolicyKind.PRODUCT,
                        "legacy.s23.option_selling.product",
                    ): S23ProductPolicyAdapter(strategy_rule),
                    (
                        PolicyKind.ENTRY,
                        "legacy.s23.option_selling.entry",
                    ): S23EntryPolicyAdapter(strategy_rule),
                    (PolicyKind.GAP, "legacy.s23.gap.not_configured"): S23GapPolicyAdapter(),
                    (
                        PolicyKind.MISSED_ENTRY,
                        "legacy.s23.missed_entry.not_configured",
                    ): S23MissedEntryPolicyAdapter(),
                    (
                        PolicyKind.CONTRACT_SELECTION,
                        "legacy.s23.option_selling.contract_selection",
                    ): S23ContractSelectionPolicyAdapter(strategy_rule),
                    (
                        PolicyKind.TARGET,
                        "legacy.s23.option_selling.target",
                    ): S23TargetPolicyAdapter(strategy_rule),
                    (
                        PolicyKind.MSL,
                        "legacy.s23.option_selling.msl",
                    ): S23MSLPolicyAdapter(strategy_rule),
                }
            )
        raise KeyError(
            f"No legacy policy registry configured for {strategy_rule.strategy_code!r}"
        )
