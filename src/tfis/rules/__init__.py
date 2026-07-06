"""Rule contracts for TradingEngineTFIS."""

from .s23_rule_matrix import (
    S23_LEG_RULES,
    S23LegRule,
    S23MonthlyGroup,
    get_s23_leg_rule,
    validate_s23_strategy_rule_matches_matrix,
)
from .s21_rule_matrix import (
    S21_LEG_RULES,
    S21LegRule,
    S21MonthlyGroup,
    get_s21_leg_rule,
    validate_s21_strategy_rule_matches_matrix,
)

__all__ = [
    "S21_LEG_RULES",
    "S21LegRule",
    "S21MonthlyGroup",
    "S23_LEG_RULES",
    "S23LegRule",
    "S23MonthlyGroup",
    "get_s21_leg_rule",
    "get_s23_leg_rule",
    "validate_s21_strategy_rule_matches_matrix",
    "validate_s23_strategy_rule_matches_matrix",
]
