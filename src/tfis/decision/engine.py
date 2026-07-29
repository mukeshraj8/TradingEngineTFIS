from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from tfis.domain import (
    MonthlyStatus,
    TFISDecision,
    TFISFormulaTrace,
    TFISPolicyResult,
    TFISRuntimeInput,
    TFISTradeResult,
)

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
    PolicyResult,
    PolicyStatus,
    ProductPolicyInput,
    ProductPolicyResult,
    TargetPolicyInput,
    TargetPolicyResult,
    _serializable,
)
from .registry import DecisionPolicySet, PolicyKind


POLICY_EXECUTION_ORDER = (
    PolicyKind.PRODUCT,
    PolicyKind.ENTRY,
    PolicyKind.GAP,
    PolicyKind.MISSED_ENTRY,
    PolicyKind.CONTRACT_SELECTION,
    PolicyKind.TARGET,
    PolicyKind.MSL,
)


@dataclass(frozen=True, slots=True)
class _PolicyFailure:
    reason_code: str
    reason: str
    policy_kind: PolicyKind | None = None


class TFISDecisionEngine:
    """Product-neutral, deterministic orchestration over explicitly supplied policies."""

    def __init__(self, policies: DecisionPolicySet) -> None:
        self._policies = policies

    def evaluate(self, runtime_input: TFISRuntimeInput) -> TFISDecision:
        missing = self._policies.missing_policy_kinds()
        if missing:
            names = tuple(kind.value for kind in missing)
            return self._fail_closed(
                runtime_input,
                _PolicyFailure(
                    reason_code="MISSING_REQUIRED_POLICIES",
                    reason=f"Required policies are missing: {', '.join(names)}.",
                ),
                policy_results=(),
                extra_evidence={"missing_policy_kinds": names},
            )

        if runtime_input.monthly_status is None:
            return self._fail_closed(
                runtime_input,
                _PolicyFailure(
                    reason_code="MONTHLY_STATUS_UNAVAILABLE",
                    reason="Resolved Monthly Status is required before policy evaluation.",
                ),
                policy_results=(),
            )
        if runtime_input.monthly_status is MonthlyStatus.UNKNOWN:
            return self._fail_closed(
                runtime_input,
                _PolicyFailure(
                    reason_code="MONTHLY_STATUS_UNKNOWN",
                    reason="UNKNOWN Monthly Status is not tradeable.",
                ),
                policy_results=(),
            )

        policy_results: list[PolicyResult] = []

        product = self._invoke(
            runtime_input,
            PolicyKind.PRODUCT,
            self._policies.product,
            ProductPolicyInput(runtime_input),
            ProductPolicyResult,
            policy_results,
        )
        if isinstance(product, TFISDecision):
            return product
        product_failure = self._required_pass_failure(
            PolicyKind.PRODUCT,
            product,
        )
        if product_failure is not None:
            return self._finish_failure(runtime_input, product_failure, policy_results)
        if (
            product.product_type is None
            or product.direction is None
            or product.execution_side is None
        ):
            return self._finish_failure(
                runtime_input,
                _PolicyFailure(
                    "INCOMPLETE_PRODUCT_POLICY_RESULT",
                    "Product policy must explicitly provide product type, direction, and execution side.",
                    PolicyKind.PRODUCT,
                ),
                policy_results,
            )
        if product.product_type is not runtime_input.product_type:
            return self._finish_failure(
                runtime_input,
                _PolicyFailure(
                    "PRODUCT_TYPE_MISMATCH",
                    "Product policy result does not match TFISRuntimeInput.product_type.",
                    PolicyKind.PRODUCT,
                ),
                policy_results,
            )

        entry = self._invoke(
            runtime_input,
            PolicyKind.ENTRY,
            self._policies.entry,
            EntryPolicyInput(runtime_input, product),
            EntryPolicyResult,
            policy_results,
        )
        if isinstance(entry, TFISDecision):
            return entry
        entry_failure = self._required_pass_failure(PolicyKind.ENTRY, entry)
        if entry_failure is not None:
            return self._finish_failure(runtime_input, entry_failure, policy_results)

        gap = self._invoke(
            runtime_input,
            PolicyKind.GAP,
            self._policies.gap,
            GapPolicyInput(runtime_input, product, entry),
            GapPolicyResult,
            policy_results,
        )
        if isinstance(gap, TFISDecision):
            return gap
        gap_failure = self._optional_policy_failure(PolicyKind.GAP, gap)
        if gap_failure is not None:
            return self._finish_failure(runtime_input, gap_failure, policy_results)

        missed = self._invoke(
            runtime_input,
            PolicyKind.MISSED_ENTRY,
            self._policies.missed_entry,
            MissedEntryPolicyInput(runtime_input, product, entry, gap),
            MissedEntryPolicyResult,
            policy_results,
        )
        if isinstance(missed, TFISDecision):
            return missed
        missed_failure = self._optional_policy_failure(
            PolicyKind.MISSED_ENTRY,
            missed,
        )
        if missed_failure is not None:
            return self._finish_failure(runtime_input, missed_failure, policy_results)

        contract = self._invoke(
            runtime_input,
            PolicyKind.CONTRACT_SELECTION,
            self._policies.contract_selection,
            ContractSelectionPolicyInput(runtime_input, product, entry, gap, missed),
            ContractSelectionPolicyResult,
            policy_results,
        )
        if isinstance(contract, TFISDecision):
            return contract
        contract_failure = self._optional_policy_failure(
            PolicyKind.CONTRACT_SELECTION,
            contract,
        )
        if contract_failure is not None:
            return self._finish_failure(runtime_input, contract_failure, policy_results)

        target = self._invoke(
            runtime_input,
            PolicyKind.TARGET,
            self._policies.target,
            TargetPolicyInput(runtime_input, product, entry, gap, missed, contract),
            TargetPolicyResult,
            policy_results,
        )
        if isinstance(target, TFISDecision):
            return target
        target_failure = self._optional_policy_failure(PolicyKind.TARGET, target)
        if target_failure is not None:
            return self._finish_failure(runtime_input, target_failure, policy_results)

        msl = self._invoke(
            runtime_input,
            PolicyKind.MSL,
            self._policies.msl,
            MSLPolicyInput(runtime_input, product, entry, gap, missed, contract, target),
            MSLPolicyResult,
            policy_results,
        )
        if isinstance(msl, TFISDecision):
            return msl
        msl_failure = self._optional_policy_failure(PolicyKind.MSL, msl)
        if msl_failure is not None:
            return self._finish_failure(runtime_input, msl_failure, policy_results)

        return self._build_decision(
            runtime_input,
            trade_result=TFISTradeResult.TRADE,
            policy_results=tuple(policy_results),
            product_result=product,
            entry_result=entry,
            gap_result=gap,
            missed_entry_result=missed,
            contract_result=contract,
            target_result=target,
            msl_result=msl,
        )

    def _invoke(
        self,
        runtime_input: TFISRuntimeInput,
        policy_kind: PolicyKind,
        policy: Any,
        policy_input: Any,
        expected_type: type[PolicyResult],
        policy_results: list[PolicyResult],
    ) -> PolicyResult | TFISDecision:
        try:
            result = policy.evaluate(policy_input)
        except Exception as exc:
            return self._fail_closed(
                runtime_input,
                _PolicyFailure(
                    reason_code="POLICY_EVALUATION_ERROR",
                    reason=(
                        f"{policy_kind.value} policy failed safely: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    policy_kind=policy_kind,
                ),
                policy_results=tuple(policy_results),
            )
        if not isinstance(result, expected_type):
            return self._fail_closed(
                runtime_input,
                _PolicyFailure(
                    reason_code="INVALID_POLICY_RESULT_TYPE",
                    reason=(
                        f"{policy_kind.value} policy returned {type(result).__name__}; "
                        f"expected {expected_type.__name__}."
                    ),
                    policy_kind=policy_kind,
                ),
                policy_results=tuple(policy_results),
            )
        if result.evaluated_at != runtime_input.evaluated_at:
            return self._fail_closed(
                runtime_input,
                _PolicyFailure(
                    reason_code="NONDETERMINISTIC_POLICY_TIMESTAMP",
                    reason=(
                        f"{policy_kind.value} policy timestamp must equal "
                        "TFISRuntimeInput.evaluated_at."
                    ),
                    policy_kind=policy_kind,
                ),
                policy_results=tuple(policy_results),
            )
        policy_results.append(result)
        return result

    @staticmethod
    def _required_pass_failure(
        policy_kind: PolicyKind,
        result: PolicyResult,
    ) -> _PolicyFailure | None:
        if result.status is PolicyStatus.PASSED and result.applicable:
            return None
        return TFISDecisionEngine._status_failure(policy_kind, result)

    @staticmethod
    def _optional_policy_failure(
        policy_kind: PolicyKind,
        result: PolicyResult,
    ) -> _PolicyFailure | None:
        if result.status in {PolicyStatus.PASSED, PolicyStatus.NOT_APPLICABLE}:
            return None
        return TFISDecisionEngine._status_failure(policy_kind, result)

    @staticmethod
    def _status_failure(
        policy_kind: PolicyKind,
        result: PolicyResult,
    ) -> _PolicyFailure:
        return _PolicyFailure(
            reason_code=f"POLICY_{result.status.value}",
            reason=f"{policy_kind.value} policy {result.status.value}: {result.reason}",
            policy_kind=policy_kind,
        )

    def _finish_failure(
        self,
        runtime_input: TFISRuntimeInput,
        failure: _PolicyFailure,
        policy_results: list[PolicyResult],
    ) -> TFISDecision:
        trade_result = (
            TFISTradeResult.NO_TRADE
            if failure.reason_code == "POLICY_BLOCKED"
            else TFISTradeResult.REJECTED
        )
        return self._build_decision(
            runtime_input,
            trade_result=trade_result,
            policy_results=tuple(policy_results),
            failure=failure,
        )

    def _fail_closed(
        self,
        runtime_input: TFISRuntimeInput,
        failure: _PolicyFailure,
        *,
        policy_results: tuple[PolicyResult, ...],
        extra_evidence: dict[str, Any] | None = None,
    ) -> TFISDecision:
        return self._build_decision(
            runtime_input,
            trade_result=TFISTradeResult.REJECTED,
            policy_results=policy_results,
            failure=failure,
            extra_evidence=extra_evidence,
        )

    def _build_decision(
        self,
        runtime_input: TFISRuntimeInput,
        *,
        trade_result: TFISTradeResult,
        policy_results: tuple[PolicyResult, ...],
        product_result: ProductPolicyResult | None = None,
        entry_result: EntryPolicyResult | None = None,
        gap_result: GapPolicyResult | None = None,
        missed_entry_result: MissedEntryPolicyResult | None = None,
        contract_result: ContractSelectionPolicyResult | None = None,
        target_result: TargetPolicyResult | None = None,
        msl_result: MSLPolicyResult | None = None,
        failure: _PolicyFailure | None = None,
        extra_evidence: dict[str, Any] | None = None,
    ) -> TFISDecision:
        result_evidence = tuple(result.to_dict() for result in policy_results)
        decision_material = {
            "evaluation_id": runtime_input.evaluation_id,
            "evaluated_at": runtime_input.evaluated_at,
            "policy_results": result_evidence,
            "failure": (
                {
                    "reason_code": failure.reason_code,
                    "reason": failure.reason,
                    "policy_kind": (
                        failure.policy_kind.value if failure.policy_kind else None
                    ),
                }
                if failure
                else None
            ),
        }
        digest = sha256(_canonical_bytes(decision_material)).hexdigest()[:24]
        entry_trace = None
        if entry_result is not None:
            entry_trace = entry_result.formula_trace or TFISFormulaTrace(
                name=entry_result.policy_name,
                formula=entry_result.formula,
                result=entry_result.entry_value,
                inputs=entry_result.inputs,
                evidence=entry_result.evidence,
            )
        evidence = {
            "policy_execution_order": tuple(kind.value for kind in POLICY_EXECUTION_ORDER),
            "policies_executed": tuple(result.policy_name for result in policy_results),
            "policy_results": result_evidence,
            "monthly_status": runtime_input.monthly_status,
            "monthly_status_evidence": runtime_input.monthly_status_evidence,
        }
        if extra_evidence:
            evidence.update(extra_evidence)
        return TFISDecision(
            evaluation_id=runtime_input.evaluation_id,
            decision_id=f"tfis-decision-{digest}",
            decided_at=runtime_input.evaluated_at,
            strategy_code=runtime_input.strategy_code,
            strategy_branch=runtime_input.strategy_branch,
            monthly_status_branch=(
                runtime_input.monthly_status.value
                if runtime_input.monthly_status is not None
                else None
            ),
            trade_result=trade_result,
            product_type=runtime_input.product_type,
            direction=product_result.direction if product_result else None,
            execution_side=product_result.execution_side if product_result else None,
            selected_instrument=(
                contract_result.selected_contract if contract_result else None
            ),
            entry_calculation=entry_trace,
            gap_result=gap_result.to_dict() if gap_result else {},
            missed_entry_result=(
                missed_entry_result.to_dict() if missed_entry_result else {}
            ),
            lots=runtime_input.lots,
            quantity=runtime_input.quantity,
            target_policy=_policy_result_for_decision(target_result),
            msl_policy=_policy_result_for_decision(msl_result),
            tsl_policy=None,
            aps_policy=None,
            final_exit_rule={},
            rejection_reason_code=failure.reason_code if failure else None,
            rejection_reason=failure.reason if failure else None,
            intermediate_calculation_evidence=evidence,
            data_versions={
                "data_quality": runtime_input.data_quality,
                "provenance": runtime_input.provenance,
            },
            configuration_versions={
                "strategy_version": runtime_input.strategy_version,
                "configuration_version": runtime_input.configuration_version,
                "strategy_family_id": runtime_input.strategy_family_id,
                "strategy_definition_id": runtime_input.strategy_definition_id,
                "strategy_instance_id": runtime_input.strategy_instance_id,
                "resolved_configuration_hash": runtime_input.resolved_configuration_hash,
            },
            compatibility_payload={},
            strategy_family_id=runtime_input.strategy_family_id,
            strategy_definition_id=runtime_input.strategy_definition_id,
            strategy_version_identity=runtime_input.strategy_version,
            strategy_instance_id=runtime_input.strategy_instance_id,
            resolved_configuration_hash=runtime_input.resolved_configuration_hash,
        )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _serializable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _policy_result_for_decision(
    result: TargetPolicyResult | MSLPolicyResult | None,
) -> TFISPolicyResult | None:
    if result is None:
        return None
    return TFISPolicyResult(
        policy_name=result.policy_name,
        result=result.calculated_value,
        formula_trace=TFISFormulaTrace(
            name=result.policy_name,
            formula=result.formula,
            result=result.calculated_value,
            inputs=result.inputs,
            evidence=result.evidence,
        ),
        evidence=result.to_dict(),
    )
