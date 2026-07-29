from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime

import pytest

from tfis.decision import (
    ContractSelectionPolicyResult,
    DecisionPolicySet,
    EntryPolicyResult,
    GapPolicyResult,
    MSLPolicyResult,
    MissedEntryPolicyResult,
    POLICY_EXECUTION_ORDER,
    PolicyKind,
    PolicyRegistry,
    PolicySelection,
    PolicyStatus,
    ProductPolicyResult,
    TFISDecisionEngine,
    TargetPolicyResult,
    TargetPolicyTarget,
)
from tfis.domain import (
    MonthlyStatus,
    Segment,
    TFISContractIdentity,
    TFISDirection,
    TFISExecutionSide,
    TFISFormulaTrace,
    TFISProductType,
    TFISRuntimeInput,
    TFISTradeResult,
    product_type_from_segment,
)


EVALUATED_AT = datetime(2026, 7, 29, 9, 17)


class RecordingProductPolicy:
    def __init__(
        self,
        calls: list[str],
        *,
        direction: TFISDirection,
        side: TFISExecutionSide,
    ) -> None:
        self.calls = calls
        self.direction = direction
        self.side = side

    def evaluate(self, policy_input):
        self.calls.append("product")
        runtime_input = policy_input.runtime_input
        return ProductPolicyResult(
            policy_name="product.explicit",
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.PASSED,
            applicable=True,
            reason="Explicit product, direction, and execution side resolved.",
            requirement_id="RT-002",
            inputs={"configured_product": runtime_input.product_type},
            evidence={"source": "unit-policy-composition"},
            product_type=runtime_input.product_type,
            direction=self.direction,
            execution_side=self.side,
            branch="configured-branch",
        )


class RecordingEntryPolicy:
    def __init__(
        self,
        calls: list[str],
        *,
        status: PolicyStatus = PolicyStatus.PASSED,
    ) -> None:
        self.calls = calls
        self.status = status

    def evaluate(self, policy_input):
        self.calls.append("entry")
        return EntryPolicyResult(
            policy_name="entry.fixture",
            evaluated_at=policy_input.runtime_input.evaluated_at,
            status=self.status,
            applicable=True,
            reason="Entry evaluated from a named market-structure reference.",
            requirement_id="MS-006",
            formula="PRV_2DHH + configured_buffer",
            reference="PRV_2DHH",
            calculated_value=101.5,
            entry_value=101.5,
            inputs={"PRV_2DHH": 100.0, "configured_buffer": 1.5},
            intermediate_values={"unrounded": 101.5},
            quality_status="VALID",
            evidence={"formula_source": "fixture"},
            formula_trace=TFISFormulaTrace(
                name="entry.fixture",
                formula="PRV_2DHH + configured_buffer",
                result=101.5,
                inputs={"PRV_2DHH": 100.0, "configured_buffer": 1.5},
            ),
        )


class RecordingGapPolicy:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def evaluate(self, policy_input):
        self.calls.append("gap")
        return GapPolicyResult(
            policy_name="gap.fixture",
            evaluated_at=policy_input.runtime_input.evaluated_at,
            status=PolicyStatus.NOT_APPLICABLE,
            applicable=False,
            reason="No configured gap overlay applies.",
            requirement_id="RT-009",
            branch="NORMAL",
            inputs={"gap_context": policy_input.runtime_input.gap_context},
            evidence={"selected_branch": "NORMAL"},
        )


class RecordingMissedEntryPolicy:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def evaluate(self, policy_input):
        self.calls.append("missed_entry")
        return MissedEntryPolicyResult(
            policy_name="missed.fixture",
            evaluated_at=policy_input.runtime_input.evaluated_at,
            status=PolicyStatus.NOT_APPLICABLE,
            applicable=False,
            reason="Missed-entry recalculation is not configured.",
            requirement_id="RT-009",
            missed=False,
            branch="NORMAL",
            evidence={"selected_branch": "NORMAL"},
        )


class RecordingContractPolicy:
    def __init__(
        self,
        calls: list[str],
        *,
        selected_contract: TFISContractIdentity | None = None,
    ) -> None:
        self.calls = calls
        self.selected_contract = selected_contract

    def evaluate(self, policy_input):
        self.calls.append("contract_selection")
        return ContractSelectionPolicyResult(
            policy_name="contract.fixture",
            evaluated_at=policy_input.runtime_input.evaluated_at,
            status=(
                PolicyStatus.PASSED
                if self.selected_contract is not None
                else PolicyStatus.NOT_APPLICABLE
            ),
            applicable=self.selected_contract is not None,
            reason=(
                "Configured contract selected."
                if self.selected_contract is not None
                else "No separate contract selection applies."
            ),
            requirement_id="RT-010",
            selected_contract=self.selected_contract,
            candidate_count=1 if self.selected_contract is not None else 0,
            evidence={"selection_order": ("configured",)},
        )


class RecordingTargetPolicy:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def evaluate(self, policy_input):
        self.calls.append("target")
        return TargetPolicyResult(
            policy_name="target.fixture",
            evaluated_at=policy_input.runtime_input.evaluated_at,
            status=PolicyStatus.PASSED,
            applicable=True,
            reason="Single target resolved.",
            requirement_id="RT-011",
            formula="ENTRY * 1.02",
            calculated_value=103.53,
            targets=(TargetPolicyTarget(order=1, target_price=103.53, quantity=1),),
            evidence={"source": "unit"},
        )


class RecordingMSLPolicy:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def evaluate(self, policy_input):
        self.calls.append("msl")
        return MSLPolicyResult(
            policy_name="msl.fixture",
            evaluated_at=policy_input.runtime_input.evaluated_at,
            status=PolicyStatus.PASSED,
            applicable=True,
            reason="Initial MSL resolved.",
            requirement_id="RT-012",
            formula="ENTRY * 0.98",
            calculated_value=99.47,
            stop_price=99.47,
            direction=policy_input.product_result.direction,
            activation_timing="INITIAL",
            quantity=1,
            evidence={"source": "unit"},
        )


def test_engine_runs_policies_in_fixed_order_and_emits_structured_evidence() -> None:
    calls: list[str] = []
    contract = TFISContractIdentity(
        symbol="TEST-FUT",
        segment=Segment.FUTURES,
        product_type=TFISProductType.FUTURES,
    )
    engine = TFISDecisionEngine(
        _policy_set(
            calls,
            direction=TFISDirection.LONG,
            side=TFISExecutionSide.BUY,
            selected_contract=contract,
        )
    )

    decision = engine.evaluate(_runtime_input())

    assert decision.trade_result is TFISTradeResult.TRADE
    assert calls == [
        "product",
        "entry",
        "gap",
        "missed_entry",
        "contract_selection",
        "target",
        "msl",
    ]
    assert decision.direction is TFISDirection.LONG
    assert decision.execution_side is TFISExecutionSide.BUY
    assert decision.selected_instrument == contract
    assert decision.entry_calculation is not None
    assert decision.entry_calculation.result == 101.5
    evidence = decision.intermediate_calculation_evidence
    assert evidence["policy_execution_order"] == tuple(
        kind.value for kind in POLICY_EXECUTION_ORDER
    )
    assert evidence["policies_executed"] == (
        "product.explicit",
        "entry.fixture",
        "gap.fixture",
        "missed.fixture",
        "contract.fixture",
        "target.fixture",
        "msl.fixture",
    )
    assert evidence["policy_results"][1]["requirement_id"] == "MS-006"
    assert evidence["policy_results"][1]["intermediate_values"] == {
        "unrounded": 101.5
    }


def test_engine_output_is_deterministic_for_identical_input_and_results() -> None:
    first = TFISDecisionEngine(_policy_set([])).evaluate(_runtime_input())
    second = TFISDecisionEngine(_policy_set([])).evaluate(_runtime_input())

    assert first.to_json() == second.to_json()
    assert first.decision_id == second.decision_id
    assert first.decided_at == EVALUATED_AT


def test_missing_policy_fails_closed_without_running_any_policy() -> None:
    calls: list[str] = []
    policies = _policy_set(calls)
    policies = DecisionPolicySet(
        product=policies.product,
        entry=policies.entry,
        gap=None,
        missed_entry=policies.missed_entry,
        contract_selection=policies.contract_selection,
        target=policies.target,
        msl=policies.msl,
    )

    decision = TFISDecisionEngine(policies).evaluate(_runtime_input())

    assert decision.trade_result is TFISTradeResult.REJECTED
    assert decision.rejection_reason_code == "MISSING_REQUIRED_POLICIES"
    assert decision.intermediate_calculation_evidence["missing_policy_kinds"] == (
        "GAP",
    )
    assert calls == []
    assert decision.direction is None
    assert decision.execution_side is None


@pytest.mark.parametrize("monthly_status", [None, MonthlyStatus.UNKNOWN])
def test_unavailable_or_unknown_monthly_status_cannot_trade(
    monthly_status: MonthlyStatus | None,
) -> None:
    calls: list[str] = []

    decision = TFISDecisionEngine(_policy_set(calls)).evaluate(
        _runtime_input(monthly_status=monthly_status)
    )

    assert decision.trade_result is TFISTradeResult.REJECTED
    assert decision.rejection_reason_code in {
        "MONTHLY_STATUS_UNAVAILABLE",
        "MONTHLY_STATUS_UNKNOWN",
    }
    assert calls == []


def test_blocked_policy_produces_no_trade_and_stops_later_policies() -> None:
    calls: list[str] = []
    policies = _policy_set(calls)
    policies = DecisionPolicySet(
        product=policies.product,
        entry=RecordingEntryPolicy(calls, status=PolicyStatus.BLOCKED),
        gap=policies.gap,
        missed_entry=policies.missed_entry,
        contract_selection=policies.contract_selection,
        target=policies.target,
        msl=policies.msl,
    )

    decision = TFISDecisionEngine(policies).evaluate(_runtime_input())

    assert decision.trade_result is TFISTradeResult.NO_TRADE
    assert decision.rejection_reason_code == "POLICY_BLOCKED"
    assert calls == ["product", "entry"]


def test_unavailable_policy_rejects_and_preserves_policy_evidence() -> None:
    calls: list[str] = []
    policies = _policy_set(calls)
    policies = DecisionPolicySet(
        product=policies.product,
        entry=RecordingEntryPolicy(calls, status=PolicyStatus.UNAVAILABLE),
        gap=policies.gap,
        missed_entry=policies.missed_entry,
        contract_selection=policies.contract_selection,
        target=policies.target,
        msl=policies.msl,
    )

    decision = TFISDecisionEngine(policies).evaluate(_runtime_input())

    assert decision.trade_result is TFISTradeResult.REJECTED
    assert decision.rejection_reason_code == "POLICY_UNAVAILABLE"
    assert decision.intermediate_calculation_evidence["policy_results"][-1][
        "quality_status"
    ] == "VALID"
    assert calls == ["product", "entry"]


def test_policy_exception_is_captured_as_fail_closed_evidence() -> None:
    class RaisingEntryPolicy:
        def evaluate(self, policy_input):
            raise RuntimeError("fixture failure")

    calls: list[str] = []
    policies = _policy_set(calls)
    policies = DecisionPolicySet(
        product=policies.product,
        entry=RaisingEntryPolicy(),
        gap=policies.gap,
        missed_entry=policies.missed_entry,
        contract_selection=policies.contract_selection,
        target=policies.target,
        msl=policies.msl,
    )

    decision = TFISDecisionEngine(policies).evaluate(_runtime_input())

    assert decision.trade_result is TFISTradeResult.REJECTED
    assert decision.rejection_reason_code == "POLICY_EVALUATION_ERROR"
    assert "RuntimeError: fixture failure" in (decision.rejection_reason or "")
    assert decision.intermediate_calculation_evidence["policies_executed"] == (
        "product.explicit",
    )


@pytest.mark.parametrize(
    ("segment", "direction", "side"),
    [
        (Segment.FUTURES, TFISDirection.LONG, TFISExecutionSide.BUY),
        (Segment.FUTURES, TFISDirection.SHORT, TFISExecutionSide.SELL),
        (Segment.EQUITY, TFISDirection.LONG, TFISExecutionSide.BUY),
        (Segment.EQUITY, TFISDirection.SHORT, TFISExecutionSide.SELL),
    ],
)
def test_futures_and_equity_support_explicit_buy_sell_long_short_without_options(
    segment: Segment,
    direction: TFISDirection,
    side: TFISExecutionSide,
) -> None:
    runtime_input = _runtime_input(segment=segment)
    assert runtime_input.option_chain_context is None

    decision = TFISDecisionEngine(
        _policy_set([], direction=direction, side=side)
    ).evaluate(runtime_input)

    assert decision.trade_result is TFISTradeResult.TRADE
    assert decision.product_type is product_type_from_segment(segment)
    assert decision.direction is direction
    assert decision.execution_side is side
    assert decision.selected_instrument is None


def test_registry_uses_only_explicit_names_and_exposes_missing_selection() -> None:
    calls: list[str] = []
    policies = _policy_set(calls)
    registry = PolicyRegistry(
        {
            (PolicyKind.PRODUCT, "configured-product"): policies.product,
            (PolicyKind.ENTRY, "configured-entry"): policies.entry,
            (PolicyKind.GAP, "configured-gap"): policies.gap,
            (PolicyKind.MISSED_ENTRY, "configured-missed"): policies.missed_entry,
            (
                PolicyKind.CONTRACT_SELECTION,
                "configured-contract",
            ): policies.contract_selection,
            (PolicyKind.TARGET, "configured-target"): policies.target,
            (PolicyKind.MSL, "configured-msl"): policies.msl,
        }
    )
    selection = PolicySelection(
        product="configured-product",
        entry="configured-entry",
        gap="configured-gap",
        missed_entry="configured-missed",
        contract_selection="missing-contract",
        target="configured-target",
        msl="configured-msl",
    )

    composed = registry.compose(selection)
    decision = TFISDecisionEngine(composed).evaluate(_runtime_input())

    assert composed.selection == selection
    assert composed.contract_selection is None
    assert decision.rejection_reason_code == "MISSING_REQUIRED_POLICIES"
    assert calls == []


def test_policy_results_are_immutable() -> None:
    result = RecordingEntryPolicy([]).evaluate(
        type("Input", (), {"runtime_input": _runtime_input()})()
    )

    with pytest.raises(FrozenInstanceError):
        result.entry_value = 1.0  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.inputs["PRV_2DHH"] = 1.0  # type: ignore[index]


def _policy_set(
    calls: list[str],
    *,
    direction: TFISDirection = TFISDirection.LONG,
    side: TFISExecutionSide = TFISExecutionSide.BUY,
    selected_contract: TFISContractIdentity | None = None,
) -> DecisionPolicySet:
    return DecisionPolicySet(
        product=RecordingProductPolicy(
            calls,
            direction=direction,
            side=side,
        ),
        entry=RecordingEntryPolicy(calls),
        gap=RecordingGapPolicy(calls),
        missed_entry=RecordingMissedEntryPolicy(calls),
        contract_selection=RecordingContractPolicy(
            calls,
            selected_contract=selected_contract,
        ),
        target=RecordingTargetPolicy(calls),
        msl=RecordingMSLPolicy(calls),
    )


def _runtime_input(
    *,
    segment: Segment = Segment.FUTURES,
    monthly_status: MonthlyStatus | None = MonthlyStatus.BEAR,
) -> TFISRuntimeInput:
    return TFISRuntimeInput(
        evaluation_id="eval-generic-1",
        evaluated_at=EVALUATED_AT,
        strategy_code="GENERIC_TEST",
        strategy_version="v1",
        strategy_branch="CONFIGURED_BRANCH",
        symbol="TEST",
        segment=segment,
        product_type=product_type_from_segment(segment),
        account_id=None,
        lots=1,
        quantity=1,
        session_date=date(2026, 7, 29),
        session_label="morning",
        timezone="Asia/Calcutta",
        price_source="fixture",
        cmp=100.0,
        contract=None,
        monthly_status=monthly_status,
        monthly_status_evidence={"source": "shared-monthly-status-engine"},
        market_structure_references={"PRV_2DHH": 100.0},
        current_week_references={},
        current_month_references={},
        gap_context={},
        option_chain_context=None,
        data_quality={"status": "VALID"},
        provenance={"source": "unit"},
        configuration_snapshot={"policy_selection": "explicit"},
        configuration_version="v1",
        runtime_values={},
        product_specific={},
    )
