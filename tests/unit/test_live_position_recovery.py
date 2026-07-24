from __future__ import annotations

from datetime import date, datetime, timezone

from tfis.broker import (
    BrokerPositionSnapshot,
    BrokerReconciliationScope,
    LivePositionRecoveryAction,
    LivePositionRecoveryCase,
    LivePositionRecoveryPlan,
    LivePositionRecoveryScenario,
    TfisPositionExpectation,
    validate_live_position_recovery_plan,
    validate_live_position_startup_resume,
)


def test_live_position_recovery_plan_passes_all_required_scenarios() -> None:
    validation = validate_live_position_recovery_plan(_complete_plan())

    assert validation.status == "PASS"
    assert validation.issue_count == 0
    assert "overnight, expiry, forced-close, rollover-required, and next-day resume" in validation.message


def test_live_position_recovery_plan_fails_missing_scenarios() -> None:
    plan = LivePositionRecoveryPlan(
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH",
        symbol="NIFTY_OPT",
        created_at=datetime(2026, 7, 22, 16, 0, tzinfo=timezone.utc),
        cases=(_case(LivePositionRecoveryScenario.OVERNIGHT, LivePositionRecoveryAction.RESUME),),
    )

    validation = validate_live_position_recovery_plan(plan)

    assert validation.status == "FAIL"
    assert {issue.scenario for issue in validation.issues} >= {
        LivePositionRecoveryScenario.EXPIRY,
        LivePositionRecoveryScenario.FORCED_CLOSE,
        LivePositionRecoveryScenario.ROLLOVER_REQUIRED,
        LivePositionRecoveryScenario.NEXT_DAY_RESUME,
    }


def test_live_position_recovery_plan_requires_broker_truth_and_reconciliation() -> None:
    bad_case = LivePositionRecoveryCase(
        scenario=LivePositionRecoveryScenario.NEXT_DAY_RESUME,
        action=LivePositionRecoveryAction.RESUME,
        broker_truth_required=False,
        broker_reconciliation_required=False,
        operator_review_required=False,
        session_date=date(2026, 7, 23),
        evidence_source_id="broker:positions",
        reason_code="next_day_resume",
    )
    plan = LivePositionRecoveryPlan(
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH",
        symbol="NIFTY_OPT",
        created_at=datetime(2026, 7, 22, 16, 0, tzinfo=timezone.utc),
        cases=tuple(
            bad_case if case.scenario is LivePositionRecoveryScenario.NEXT_DAY_RESUME else case
            for case in _complete_plan().cases
        ),
    )

    validation = validate_live_position_recovery_plan(plan)

    assert validation.status == "FAIL"
    assert {issue.code for issue in validation.issues} >= {
        "LIVE_RECOVERY_BROKER_TRUTH_NOT_REQUIRED",
        "LIVE_RECOVERY_RECONCILIATION_NOT_REQUIRED",
    }


def test_live_position_recovery_plan_requires_operator_review_for_risky_cases() -> None:
    bad_case = LivePositionRecoveryCase(
        scenario=LivePositionRecoveryScenario.EXPIRY,
        action=LivePositionRecoveryAction.FORCE_CLOSE,
        broker_truth_required=True,
        broker_reconciliation_required=True,
        operator_review_required=False,
        session_date=date(2026, 7, 23),
        evidence_source_id="broker:positions",
        reason_code="expiry_force_close",
    )
    plan = LivePositionRecoveryPlan(
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH",
        symbol="NIFTY_OPT",
        created_at=datetime(2026, 7, 22, 16, 0, tzinfo=timezone.utc),
        cases=tuple(
            bad_case if case.scenario is LivePositionRecoveryScenario.EXPIRY else case
            for case in _complete_plan().cases
        ),
    )

    validation = validate_live_position_recovery_plan(plan)

    assert validation.status == "FAIL"
    assert any(
        issue.code == "LIVE_RECOVERY_OPERATOR_REVIEW_NOT_REQUIRED"
        and issue.scenario is LivePositionRecoveryScenario.EXPIRY
        for issue in validation.issues
    )


def test_live_position_startup_resume_passes_when_broker_truth_matches() -> None:
    validation = validate_live_position_startup_resume(
        scope=BrokerReconciliationScope.PRE_STARTUP,
        expected_positions=(
            TfisPositionExpectation(
                provider="fyers",
                strategy_code="S23",
                strategy_branch="BRANCH",
                symbol="NIFTY_OPT",
                expected_quantity=-75,
                expected_average_price=194.25,
            ),
        ),
        broker_positions=(
            BrokerPositionSnapshot(
                provider="fyers",
                symbol="NIFTY_OPT",
                quantity=-75,
                average_price=194.25,
                source_id="broker:positions:2026-07-23",
            ),
        ),
    )

    assert validation.status == "PASS"
    assert validation.expected_open_position_count == 1
    assert validation.broker_position_count == 1
    assert validation.conflict_count == 0
    assert validation.reconciliation is not None
    assert "agree with supplied broker truth" in validation.message


def test_live_position_startup_resume_fails_when_open_position_lacks_broker_truth() -> None:
    validation = validate_live_position_startup_resume(
        scope=BrokerReconciliationScope.AFTER_RESTART,
        expected_positions=(
            TfisPositionExpectation(
                provider="fyers",
                strategy_code="S23",
                strategy_branch="BRANCH",
                symbol="NIFTY_OPT",
                expected_quantity=-75,
            ),
        ),
        broker_positions=(),
    )

    assert validation.status == "FAIL"
    assert validation.reconciliation is None
    assert validation.conflict_count == 1
    assert "Broker position truth is required" in validation.message


def test_live_position_startup_resume_fails_broker_truth_mismatch() -> None:
    validation = validate_live_position_startup_resume(
        scope=BrokerReconciliationScope.AFTER_RESTART,
        expected_positions=(
            TfisPositionExpectation(
                provider="fyers",
                strategy_code="S21",
                strategy_branch="BRANCH",
                symbol="BANKNIFTY_OPT",
                expected_quantity=-35,
            ),
        ),
        broker_positions=(
            BrokerPositionSnapshot(
                provider="fyers",
                symbol="BANKNIFTY_OPT",
                quantity=-20,
            ),
        ),
    )

    assert validation.status == "FAIL"
    assert validation.reconciliation is not None
    assert validation.reconciliation.conflicts[0].code == "BROKER_POSITION_QUANTITY_MISMATCH"


def _complete_plan() -> LivePositionRecoveryPlan:
    return LivePositionRecoveryPlan(
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH",
        symbol="NIFTY_OPT",
        created_at=datetime(2026, 7, 22, 16, 0, tzinfo=timezone.utc),
        cases=(
            _case(LivePositionRecoveryScenario.OVERNIGHT, LivePositionRecoveryAction.RESUME),
            _case(LivePositionRecoveryScenario.EXPIRY, LivePositionRecoveryAction.FORCE_CLOSE),
            _case(LivePositionRecoveryScenario.FORCED_CLOSE, LivePositionRecoveryAction.FORCE_CLOSE),
            _case(LivePositionRecoveryScenario.ROLLOVER_REQUIRED, LivePositionRecoveryAction.ROLLOVER),
            _case(LivePositionRecoveryScenario.NEXT_DAY_RESUME, LivePositionRecoveryAction.RESUME),
        ),
    )


def _case(
    scenario: LivePositionRecoveryScenario,
    action: LivePositionRecoveryAction,
) -> LivePositionRecoveryCase:
    return LivePositionRecoveryCase(
        scenario=scenario,
        action=action,
        broker_truth_required=True,
        broker_reconciliation_required=True,
        operator_review_required=scenario
        in {
            LivePositionRecoveryScenario.EXPIRY,
            LivePositionRecoveryScenario.FORCED_CLOSE,
            LivePositionRecoveryScenario.ROLLOVER_REQUIRED,
        },
        session_date=date(2026, 7, 23),
        evidence_source_id="broker:positions:orderbook",
        reason_code=scenario.value.lower(),
    )
