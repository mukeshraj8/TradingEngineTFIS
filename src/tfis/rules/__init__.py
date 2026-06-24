"""Rule contracts for TradingEngineTFIS."""

from .s23_rule_matrix import (
    S23_LEG_RULES,
    S23LegRule,
    S23MonthlyGroup,
    get_s23_leg_rule,
    validate_s23_strategy_rule_matches_matrix,
)

__all__ = [
    "S23_LEG_RULES",
    "S23LegRule",
    "S23MonthlyGroup",
    "get_s23_leg_rule",
    "validate_s23_strategy_rule_matches_matrix",
]
