from __future__ import annotations

from datetime import datetime, time, timezone

from tfis.broker import (
    LiveExitProtectionMode,
    LiveExitProtectionPlan,
    LiveExitProtectionRule,
    LiveExitProtectionRuleType,
    validate_live_exit_protection_plan,
)


def test_live_exit_protection_plan_passes_with_all_required_rules() -> None:
    validation = validate_live_exit_protection_plan(_complete_plan())

    assert validation.status == "PASS"
    assert validation.issue_count == 0
    assert "target, stoploss, forced close, emergency exit, and kill switch" in validation.message


def test_live_exit_protection_plan_fails_missing_required_rules() -> None:
    plan = LiveExitProtectionPlan(
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH",
        symbol="NIFTY_OPT",
        quantity=-75,
        created_at=datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc),
        rules=(
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.TARGET,
                mode=LiveExitProtectionMode.EVENT_DRIVEN,
                enabled=True,
                price=80.0,
            ),
        ),
    )

    validation = validate_live_exit_protection_plan(plan)

    assert validation.status == "FAIL"
    assert {issue.rule_type for issue in validation.issues} >= {
        LiveExitProtectionRuleType.STOPLOSS,
        LiveExitProtectionRuleType.FORCED_CLOSE,
        LiveExitProtectionRuleType.EMERGENCY_EXIT,
        LiveExitProtectionRuleType.KILL_SWITCH,
    }


def test_live_exit_protection_plan_fails_invalid_prices_and_time() -> None:
    plan = LiveExitProtectionPlan(
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH",
        symbol="NIFTY_OPT",
        quantity=-75,
        created_at=datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc),
        rules=(
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.TARGET,
                mode=LiveExitProtectionMode.EVENT_DRIVEN,
                enabled=True,
                price=0,
            ),
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.STOPLOSS,
                mode=LiveExitProtectionMode.EVENT_DRIVEN,
                enabled=True,
                price=None,
            ),
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.FORCED_CLOSE,
                mode=LiveExitProtectionMode.EVENT_DRIVEN,
                enabled=True,
            ),
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.EMERGENCY_EXIT,
                mode=LiveExitProtectionMode.BROKER_SIDE,
                enabled=True,
            ),
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.KILL_SWITCH,
                mode=LiveExitProtectionMode.BROKER_SIDE,
                enabled=True,
            ),
        ),
    )

    validation = validate_live_exit_protection_plan(plan)

    assert validation.status == "FAIL"
    assert {issue.code for issue in validation.issues} >= {
        "LIVE_EXIT_TARGET_PRICE_INVALID",
        "LIVE_EXIT_STOPLOSS_PRICE_INVALID",
        "LIVE_EXIT_FORCED_CLOSE_TIME_MISSING",
    }


def test_live_exit_protection_plan_requires_ingress_and_operator_approval() -> None:
    plan = LiveExitProtectionPlan(
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH",
        symbol="NIFTY_OPT",
        quantity=-75,
        created_at=datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc),
        rules=_complete_plan().rules,
        market_event_ingress_required=False,
        operator_approval_required=False,
    )

    validation = validate_live_exit_protection_plan(plan)

    assert validation.status == "FAIL"
    assert {issue.code for issue in validation.issues} >= {
        "LIVE_EXIT_MARKET_EVENT_INGRESS_NOT_REQUIRED",
        "LIVE_EXIT_OPERATOR_APPROVAL_NOT_REQUIRED",
    }


def _complete_plan() -> LiveExitProtectionPlan:
    return LiveExitProtectionPlan(
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH",
        symbol="NIFTY_OPT",
        quantity=-75,
        created_at=datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc),
        rules=(
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.TARGET,
                mode=LiveExitProtectionMode.EVENT_DRIVEN,
                enabled=True,
                price=80.0,
            ),
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.STOPLOSS,
                mode=LiveExitProtectionMode.EVENT_DRIVEN,
                enabled=True,
                price=260.0,
            ),
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.FORCED_CLOSE,
                mode=LiveExitProtectionMode.EVENT_DRIVEN,
                enabled=True,
                trigger_time=time(15, 15),
            ),
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.EMERGENCY_EXIT,
                mode=LiveExitProtectionMode.BROKER_SIDE,
                enabled=True,
            ),
            LiveExitProtectionRule(
                rule_type=LiveExitProtectionRuleType.KILL_SWITCH,
                mode=LiveExitProtectionMode.BROKER_SIDE,
                enabled=True,
            ),
        ),
    )
