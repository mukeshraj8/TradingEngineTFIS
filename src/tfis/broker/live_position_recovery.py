from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from .broker_order_state import BrokerOrderState
from .broker_reconciliation import (
    BrokerOrderBookSnapshot,
    BrokerPositionSnapshot,
    BrokerReconciliationResult,
    BrokerReconciliationScope,
    BrokerReconciliationStatus,
    TfisPositionExpectation,
    reconcile_broker_truth,
)


class LivePositionRecoveryScenario(str, Enum):
    OVERNIGHT = "OVERNIGHT"
    EXPIRY = "EXPIRY"
    FORCED_CLOSE = "FORCED_CLOSE"
    ROLLOVER_REQUIRED = "ROLLOVER_REQUIRED"
    NEXT_DAY_RESUME = "NEXT_DAY_RESUME"


class LivePositionRecoveryAction(str, Enum):
    RESUME = "RESUME"
    FORCE_CLOSE = "FORCE_CLOSE"
    ROLLOVER = "ROLLOVER"
    BLOCK_STARTUP = "BLOCK_STARTUP"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True, slots=True)
class LivePositionRecoveryCase:
    scenario: LivePositionRecoveryScenario
    action: LivePositionRecoveryAction
    broker_truth_required: bool
    broker_reconciliation_required: bool
    operator_review_required: bool
    session_date: date
    evidence_source_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class LivePositionRecoveryPlan:
    provider: str
    strategy_code: str
    strategy_branch: str
    symbol: str
    created_at: datetime
    cases: tuple[LivePositionRecoveryCase, ...]


@dataclass(frozen=True, slots=True)
class LivePositionRecoveryIssue:
    code: str
    scenario: LivePositionRecoveryScenario | None
    message: str


@dataclass(frozen=True, slots=True)
class LivePositionRecoveryValidation:
    status: str
    issue_count: int
    issues: tuple[LivePositionRecoveryIssue, ...]
    message: str


@dataclass(frozen=True, slots=True)
class LivePositionStartupResumeValidation:
    status: str
    scope: BrokerReconciliationScope
    expected_open_position_count: int
    broker_position_count: int
    expected_order_count: int
    broker_order_count: int
    conflict_count: int
    reconciliation: BrokerReconciliationResult | None
    message: str


def validate_live_position_recovery_plan(
    plan: LivePositionRecoveryPlan,
) -> LivePositionRecoveryValidation:
    issues: list[LivePositionRecoveryIssue] = []
    for field_name in ("provider", "strategy_code", "strategy_branch", "symbol"):
        if not str(getattr(plan, field_name)).strip():
            issues.append(
                LivePositionRecoveryIssue(
                    code="LIVE_RECOVERY_IDENTITY_MISSING",
                    scenario=None,
                    message=f"{field_name} is required for live position recovery.",
                )
            )
    cases_by_scenario = {case.scenario: case for case in plan.cases}
    for scenario in LivePositionRecoveryScenario:
        case = cases_by_scenario.get(scenario)
        if case is None:
            issues.append(
                LivePositionRecoveryIssue(
                    code="LIVE_RECOVERY_SCENARIO_MISSING",
                    scenario=scenario,
                    message=f"Live recovery scenario is missing: {scenario.value}.",
                )
            )
            continue
        _validate_case(case, issues)
    status = "FAIL" if issues else "PASS"
    return LivePositionRecoveryValidation(
        status=status,
        issue_count=len(issues),
        issues=tuple(issues),
        message=(
            f"{len(issues)} live position recovery issue(s) detected."
            if issues
            else "Live position recovery plan covers overnight, expiry, forced-close, rollover-required, and next-day resume scenarios from broker truth."
        ),
    )


def validate_live_position_startup_resume(
    *,
    scope: BrokerReconciliationScope,
    expected_positions: tuple[TfisPositionExpectation, ...],
    broker_positions: tuple[BrokerPositionSnapshot, ...],
    expected_orders: tuple[BrokerOrderState, ...] = (),
    broker_orders: tuple[BrokerOrderBookSnapshot, ...] = (),
    price_tolerance: float = 0.01,
) -> LivePositionStartupResumeValidation:
    expected_open_positions = tuple(
        item for item in expected_positions if item.expected_quantity != 0
    )
    if expected_open_positions and not broker_positions:
        return LivePositionStartupResumeValidation(
            status="FAIL",
            scope=scope,
            expected_open_position_count=len(expected_open_positions),
            broker_position_count=0,
            expected_order_count=len(expected_orders),
            broker_order_count=len(broker_orders),
            conflict_count=len(expected_open_positions),
            reconciliation=None,
            message=(
                "Broker position truth is required before startup/resume when "
                "TFIS expects open or carried live positions."
            ),
        )
    reconciliation = reconcile_broker_truth(
        scope=scope,
        expected_positions=expected_positions,
        broker_positions=broker_positions,
        expected_orders=expected_orders,
        broker_orders=broker_orders,
        price_tolerance=price_tolerance,
    )
    status = (
        "PASS"
        if reconciliation.status is BrokerReconciliationStatus.PASS
        else "FAIL"
    )
    return LivePositionStartupResumeValidation(
        status=status,
        scope=scope,
        expected_open_position_count=len(expected_open_positions),
        broker_position_count=len(broker_positions),
        expected_order_count=len(expected_orders),
        broker_order_count=len(broker_orders),
        conflict_count=reconciliation.conflict_count,
        reconciliation=reconciliation,
        message=(
            "Live startup/resume position expectations agree with supplied broker truth."
            if status == "PASS"
            else reconciliation.message
        ),
    )


def _validate_case(
    case: LivePositionRecoveryCase,
    issues: list[LivePositionRecoveryIssue],
) -> None:
    if not case.broker_truth_required:
        issues.append(
            LivePositionRecoveryIssue(
                code="LIVE_RECOVERY_BROKER_TRUTH_NOT_REQUIRED",
                scenario=case.scenario,
                message=f"Live recovery scenario must require broker truth: {case.scenario.value}.",
            )
        )
    if not case.broker_reconciliation_required:
        issues.append(
            LivePositionRecoveryIssue(
                code="LIVE_RECOVERY_RECONCILIATION_NOT_REQUIRED",
                scenario=case.scenario,
                message=f"Live recovery scenario must require broker reconciliation: {case.scenario.value}.",
            )
        )
    if not str(case.evidence_source_id).strip():
        issues.append(
            LivePositionRecoveryIssue(
                code="LIVE_RECOVERY_EVIDENCE_SOURCE_MISSING",
                scenario=case.scenario,
                message=f"Live recovery evidence source is missing: {case.scenario.value}.",
            )
        )
    if not str(case.reason_code).strip():
        issues.append(
            LivePositionRecoveryIssue(
                code="LIVE_RECOVERY_REASON_CODE_MISSING",
                scenario=case.scenario,
                message=f"Live recovery reason code is missing: {case.scenario.value}.",
            )
        )
    if case.scenario in {
        LivePositionRecoveryScenario.EXPIRY,
        LivePositionRecoveryScenario.FORCED_CLOSE,
        LivePositionRecoveryScenario.ROLLOVER_REQUIRED,
    } and not case.operator_review_required:
        issues.append(
            LivePositionRecoveryIssue(
                code="LIVE_RECOVERY_OPERATOR_REVIEW_NOT_REQUIRED",
                scenario=case.scenario,
                message=f"Live recovery scenario must require operator review: {case.scenario.value}.",
            )
        )


__all__ = [
    "LivePositionRecoveryAction",
    "LivePositionRecoveryCase",
    "LivePositionRecoveryIssue",
    "LivePositionRecoveryPlan",
    "LivePositionRecoveryScenario",
    "LivePositionRecoveryValidation",
    "LivePositionStartupResumeValidation",
    "validate_live_position_recovery_plan",
    "validate_live_position_startup_resume",
]
