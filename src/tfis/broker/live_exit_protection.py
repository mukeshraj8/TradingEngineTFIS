from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum


class LiveExitProtectionError(RuntimeError):
    """Raised when a live exit-protection plan is unsafe or incomplete."""


class LiveExitProtectionMode(str, Enum):
    BROKER_SIDE = "BROKER_SIDE"
    EVENT_DRIVEN = "EVENT_DRIVEN"


class LiveExitProtectionRuleType(str, Enum):
    TARGET = "TARGET"
    STOPLOSS = "STOPLOSS"
    FORCED_CLOSE = "FORCED_CLOSE"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"
    KILL_SWITCH = "KILL_SWITCH"


@dataclass(frozen=True, slots=True)
class LiveExitProtectionRule:
    rule_type: LiveExitProtectionRuleType
    mode: LiveExitProtectionMode
    enabled: bool
    price: float | None = None
    trigger_time: time | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class LiveExitProtectionPlan:
    provider: str
    strategy_code: str
    strategy_branch: str
    symbol: str
    quantity: int
    created_at: datetime
    rules: tuple[LiveExitProtectionRule, ...]
    market_event_ingress_required: bool = True
    operator_approval_required: bool = True


@dataclass(frozen=True, slots=True)
class LiveExitProtectionIssue:
    code: str
    rule_type: LiveExitProtectionRuleType | None
    message: str


@dataclass(frozen=True, slots=True)
class LiveExitProtectionValidation:
    status: str
    issue_count: int
    issues: tuple[LiveExitProtectionIssue, ...]
    message: str


def validate_live_exit_protection_plan(
    plan: LiveExitProtectionPlan,
) -> LiveExitProtectionValidation:
    issues: list[LiveExitProtectionIssue] = []
    _validate_plan_identity(plan, issues)
    rules_by_type = {rule.rule_type: rule for rule in plan.rules if rule.enabled}
    for rule_type in LiveExitProtectionRuleType:
        if rule_type not in rules_by_type:
            issues.append(
                LiveExitProtectionIssue(
                    code="LIVE_EXIT_RULE_MISSING",
                    rule_type=rule_type,
                    message=f"Live exit protection rule is missing: {rule_type.value}.",
                )
            )
    target = rules_by_type.get(LiveExitProtectionRuleType.TARGET)
    if target is not None and (target.price is None or target.price <= 0):
        issues.append(
            LiveExitProtectionIssue(
                code="LIVE_EXIT_TARGET_PRICE_INVALID",
                rule_type=LiveExitProtectionRuleType.TARGET,
                message="Live target protection requires a positive target price.",
            )
        )
    stoploss = rules_by_type.get(LiveExitProtectionRuleType.STOPLOSS)
    if stoploss is not None and (stoploss.price is None or stoploss.price <= 0):
        issues.append(
            LiveExitProtectionIssue(
                code="LIVE_EXIT_STOPLOSS_PRICE_INVALID",
                rule_type=LiveExitProtectionRuleType.STOPLOSS,
                message="Live stoploss protection requires a positive stoploss price.",
            )
        )
    forced_close = rules_by_type.get(LiveExitProtectionRuleType.FORCED_CLOSE)
    if forced_close is not None and forced_close.trigger_time is None:
        issues.append(
            LiveExitProtectionIssue(
                code="LIVE_EXIT_FORCED_CLOSE_TIME_MISSING",
                rule_type=LiveExitProtectionRuleType.FORCED_CLOSE,
                message="Live forced-close protection requires a trigger time.",
            )
        )
    if not plan.market_event_ingress_required:
        issues.append(
            LiveExitProtectionIssue(
                code="LIVE_EXIT_MARKET_EVENT_INGRESS_NOT_REQUIRED",
                rule_type=None,
                message="Live exit protection must require market-event ingress.",
            )
        )
    if not plan.operator_approval_required:
        issues.append(
            LiveExitProtectionIssue(
                code="LIVE_EXIT_OPERATOR_APPROVAL_NOT_REQUIRED",
                rule_type=None,
                message="Live exit protection must require operator approval.",
            )
        )
    status = "FAIL" if issues else "PASS"
    return LiveExitProtectionValidation(
        status=status,
        issue_count=len(issues),
        issues=tuple(issues),
        message=(
            f"{len(issues)} live exit protection issue(s) detected."
            if issues
            else "Live exit protection plan includes target, stoploss, forced close, emergency exit, and kill switch rules."
        ),
    )


def _validate_plan_identity(
    plan: LiveExitProtectionPlan,
    issues: list[LiveExitProtectionIssue],
) -> None:
    for field_name in ("provider", "strategy_code", "strategy_branch", "symbol"):
        if not str(getattr(plan, field_name)).strip():
            issues.append(
                LiveExitProtectionIssue(
                    code="LIVE_EXIT_IDENTITY_MISSING",
                    rule_type=None,
                    message=f"{field_name} is required for live exit protection.",
                )
            )
    if plan.quantity == 0:
        issues.append(
            LiveExitProtectionIssue(
                code="LIVE_EXIT_QUANTITY_MISSING",
                rule_type=None,
                message="quantity must be non-zero for live exit protection.",
            )
        )


__all__ = [
    "LiveExitProtectionError",
    "LiveExitProtectionIssue",
    "LiveExitProtectionMode",
    "LiveExitProtectionPlan",
    "LiveExitProtectionRule",
    "LiveExitProtectionRuleType",
    "LiveExitProtectionValidation",
    "validate_live_exit_protection_plan",
]
