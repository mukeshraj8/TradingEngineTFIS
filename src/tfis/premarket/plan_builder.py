from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from tfis.domain import TFISRuntimeInput
from tfis.domain.premarket_plan import (
    PreMarketContractResolution,
    PreMarketPlanFailure,
    PreMarketPlannedValues,
    PreMarketPlanStatus,
    PreMarketReferenceSet,
    PreMarketStrategyPlan,
)


StageCallable = Callable[[Mapping[str, Any]], "PreMarketStageResult"]


@dataclass(frozen=True, slots=True)
class PreMarketStageResult:
    stage_name: str
    status: str
    payload: Mapping[str, Any] = MappingProxyType({})
    evidence: Mapping[str, Any] = MappingProxyType({})
    failure_code: str | None = None
    reason: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == "PASSED"


@dataclass(frozen=True, slots=True)
class PreMarketPlanningContext:
    underlying_instrument: str
    enabled: bool = True
    fresh_entry_eligible: bool = True
    trading_day_eligible: bool = True
    carried_position_detected: bool = False
    expected_configuration_hash: str | None = None
    evidence_classification: str = "LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT"
    field_provenance: Mapping[str, str] = MappingProxyType({})
    derived_fields: tuple[str, ...] = ()
    supplemented_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreMarketStagePolicies:
    strategy_resolution: StageCallable
    monthly_status_and_branch: StageCallable
    underlying_references: StageCallable
    contract_selection: StageCallable
    base_entry: StageCallable
    target: StageCallable
    msl: StageCallable
    timing: StageCallable

    @property
    def ordered(self) -> tuple[StageCallable, ...]:
        return (
            self.strategy_resolution,
            self.monthly_status_and_branch,
            self.underlying_references,
            self.contract_selection,
            self.base_entry,
            self.target,
            self.msl,
            self.timing,
        )


class PreMarketStrategyPlanBuilder:
    """Builds immutable pre-market plans from explicitly supplied stages."""

    plan_version = "tfis.premarket_strategy_plan.v1"

    def build(
        self,
        runtime_input: TFISRuntimeInput,
        resolved_strategy_configuration: Mapping[str, Any],
        planning_context: PreMarketPlanningContext,
        stage_policies: PreMarketStagePolicies,
    ) -> PreMarketStrategyPlan:
        initial_failure = self._initial_failure(
            runtime_input,
            resolved_strategy_configuration,
            planning_context,
        )
        if initial_failure is not None:
            return self._blocked_plan(
                runtime_input,
                resolved_strategy_configuration,
                planning_context,
                initial_failure,
                {},
            )
        if planning_context.carried_position_detected:
            return self._no_action_plan(
                runtime_input,
                resolved_strategy_configuration,
                planning_context,
                PreMarketPlanFailure("fresh_entry_boundary", "MANAGING_CARRIED_POSITION", "Existing carried position prevents fresh-entry planning."),
            )

        context: dict[str, Any] = {
            "runtime_input": runtime_input,
            "resolved_strategy_configuration": resolved_strategy_configuration,
            "planning_context": planning_context,
        }
        stages: list[PreMarketStageResult] = []
        for policy in stage_policies.ordered:
            stage = policy(MappingProxyType(context))
            stages.append(stage)
            context.update(dict(stage.payload))
            if not stage.passed:
                return self._blocked_plan(
                    runtime_input,
                    resolved_strategy_configuration,
                    planning_context,
                    PreMarketPlanFailure(stage.stage_name, stage.failure_code or "PREMARKET_STAGE_BLOCKED", stage.reason or "Pre-market stage blocked."),
                    {item.stage_name: _stage_payload(item) for item in stages},
                )

        missing = self._missing_required_fields(context)
        if missing:
            return self._blocked_plan(
                runtime_input,
                resolved_strategy_configuration,
                planning_context,
                PreMarketPlanFailure("plan_validation", "MISSING_REQUIRED_PLAN_FIELD", f"Missing required plan fields: {', '.join(missing)}."),
                {item.stage_name: _stage_payload(item) for item in stages},
                missing_fields=tuple(missing),
            )
        return self._prepared_plan(
            runtime_input,
            resolved_strategy_configuration,
            planning_context,
            context,
            tuple(stages),
        )

    def _initial_failure(
        self,
        runtime_input: TFISRuntimeInput,
        resolved_strategy_configuration: Mapping[str, Any],
        planning_context: PreMarketPlanningContext,
    ) -> PreMarketPlanFailure | None:
        if not runtime_input.strategy_family_id:
            return PreMarketPlanFailure("identity", "MISSING_STRATEGY_IDENTITY", "Strategy family identity is required.")
        if not runtime_input.strategy_definition_id:
            return PreMarketPlanFailure("identity", "MISSING_STRATEGY_IDENTITY", "Strategy definition identity is required.")
        if not runtime_input.strategy_instance_id:
            return PreMarketPlanFailure("identity", "MISSING_STRATEGY_IDENTITY", "Strategy instance identity is required.")
        if not runtime_input.resolved_configuration_hash:
            return PreMarketPlanFailure("configuration", "MISSING_RESOLVED_CONFIGURATION", "Resolved configuration hash is required.")
        if not resolved_strategy_configuration:
            return PreMarketPlanFailure("configuration", "MISSING_RESOLVED_CONFIGURATION", "Resolved configuration payload is required.")
        if not planning_context.enabled:
            return PreMarketPlanFailure("eligibility", "STRATEGY_DISABLED", "Strategy instance is disabled.")
        if not planning_context.trading_day_eligible:
            return PreMarketPlanFailure("eligibility", "TRADING_DAY_INELIGIBLE", "Trading day is not eligible.")
        if planning_context.expected_configuration_hash and planning_context.expected_configuration_hash != runtime_input.resolved_configuration_hash:
            return PreMarketPlanFailure("configuration", "CONFIGURATION_HASH_MISMATCH", "Resolved configuration hash does not match planning context.")
        return None

    def _missing_required_fields(self, context: Mapping[str, Any]) -> list[str]:
        required = {
            "product_policy": "product",
            "branch": "resolved_branch",
            "underlying_references": "completed underlying historical references",
            "contract_selection": "contract selection",
            "selected_contract": "selected contract",
            "selected_contract_references": "selected-contract historical references",
            "base_entry": "Base Entry",
            "target": "preliminary Target",
            "msl": "preliminary MSL",
            "normal_orpt": "normal ORPT",
            "rc_time": "RC time",
        }
        missing: list[str] = []
        for key, label in required.items():
            if context.get(key) in (None, {}, ()):
                missing.append(label)
        runtime_input = context["runtime_input"]
        if runtime_input.quantity is None or runtime_input.quantity <= 0:
            missing.append("valid quantity")
        if runtime_input.lots is None or runtime_input.lots <= 0:
            missing.append("valid lots")
        return missing

    def _prepared_plan(
        self,
        runtime_input: TFISRuntimeInput,
        resolved_strategy_configuration: Mapping[str, Any],
        planning_context: PreMarketPlanningContext,
        context: Mapping[str, Any],
        stages: tuple[PreMarketStageResult, ...],
    ) -> PreMarketStrategyPlan:
        selected = context["selected_contract"]
        target = context["target"]
        msl = context["msl"]
        return PreMarketStrategyPlan(
            plan_id=f"{runtime_input.evaluation_id}:premarket",
            plan_version=self.plan_version,
            strategy_family=runtime_input.strategy_family_id or runtime_input.strategy_code,
            strategy_definition=runtime_input.strategy_definition_id or runtime_input.strategy_branch or runtime_input.strategy_code,
            strategy_version=runtime_input.strategy_version or "",
            strategy_instance_id=runtime_input.strategy_instance_id or "",
            resolved_configuration_hash=runtime_input.resolved_configuration_hash or "",
            trading_date=runtime_input.session_date,
            enabled=planning_context.enabled,
            fresh_entry_eligible=planning_context.fresh_entry_eligible,
            plan_status=PreMarketPlanStatus.PREPARED,
            block_code=None,
            block_reason=None,
            monthly_status=runtime_input.monthly_status,
            resolved_branch=str(context["branch"]),
            product=runtime_input.product_type,
            underlying_instrument=planning_context.underlying_instrument,
            references=PreMarketReferenceSet(
                underlying=context["underlying_references"],
                selected_contract=context["selected_contract_references"],
                provenance=context.get("reference_provenance", {}),
                as_of=runtime_input.evaluated_at,
            ),
            contract_resolution=PreMarketContractResolution(
                expiry_candidates=tuple(context.get("expiry_candidates") or (selected.expiry,)),
                strike_candidates=tuple(context.get("strike_candidates") or (selected.strike,)),
                selected_expiry=selected.expiry,
                selected_strike=selected.strike,
                selected_contract=selected,
                premium=_metadata_float(selected, "ltp"),
                oi=_metadata_float(selected, "oi"),
                oi_unit=str(context.get("oi_unit") or "LOTS"),
                qualification_evidence=context["contract_selection"].to_dict(),
            ),
            planned_values=PreMarketPlannedValues(
                base_entry=_engine_value(context["base_entry"], "base_entry"),
                preliminary_target=target.calculated_value,
                preliminary_msl=msl.calculated_value,
                order_side=context["product_policy"].execution_side,
                position_intent=str(context.get("position_intent") or "SHORT_OPTION"),
                direction=context["product_policy"].direction,
                quantity=runtime_input.quantity,
                lots=runtime_input.lots,
                normal_orpt=context["normal_orpt"],
                rc_time=context["rc_time"],
                policy_identities={
                    "product": context["product_policy"].policy_name,
                    "contract_selection": context["contract_selection"].policy_name,
                    "entry": context.get("entry_policy_identity") or "",
                    "target": target.policy_name,
                    "msl": msl.policy_name,
                    "gap_missed_entry": str(context.get("gap_missed_entry_policy_identity") or "NOT_CONFIGURED_PREMARKET"),
                    "execution_risk": str(context.get("execution_risk_policy_identity") or "OFFLINE_PREMARKET_NONE"),
                },
            ),
            stage_evidence={item.stage_name: _stage_payload(item) for item in stages},
            missing_fields=(),
            derived_fields=planning_context.derived_fields,
            supplemented_fields=planning_context.supplemented_fields,
            field_provenance=planning_context.field_provenance,
        )

    def _blocked_plan(
        self,
        runtime_input: TFISRuntimeInput,
        resolved_strategy_configuration: Mapping[str, Any],
        planning_context: PreMarketPlanningContext,
        failure: PreMarketPlanFailure,
        stage_evidence: Mapping[str, Any],
        *,
        missing_fields: tuple[str, ...] = (),
    ) -> PreMarketStrategyPlan:
        return PreMarketStrategyPlan(
            plan_id=f"{runtime_input.evaluation_id}:premarket",
            plan_version=self.plan_version,
            strategy_family=runtime_input.strategy_family_id or runtime_input.strategy_code or "UNKNOWN",
            strategy_definition=runtime_input.strategy_definition_id or runtime_input.strategy_branch or runtime_input.strategy_code or "UNKNOWN",
            strategy_version=runtime_input.strategy_version or "",
            strategy_instance_id=runtime_input.strategy_instance_id or "UNKNOWN",
            resolved_configuration_hash=runtime_input.resolved_configuration_hash or "",
            trading_date=runtime_input.session_date,
            enabled=planning_context.enabled,
            fresh_entry_eligible=planning_context.fresh_entry_eligible,
            plan_status=PreMarketPlanStatus.BLOCKED_PREMARKET,
            block_code=failure.code,
            block_reason=failure.reason,
            monthly_status=runtime_input.monthly_status,
            resolved_branch=runtime_input.strategy_branch,
            product=runtime_input.product_type,
            underlying_instrument=planning_context.underlying_instrument,
            references=PreMarketReferenceSet(),
            contract_resolution=PreMarketContractResolution(),
            planned_values=PreMarketPlannedValues(quantity=runtime_input.quantity, lots=runtime_input.lots),
            stage_evidence=stage_evidence,
            missing_fields=missing_fields,
            field_provenance=planning_context.field_provenance,
            failures=(failure,),
        )

    def _no_action_plan(
        self,
        runtime_input: TFISRuntimeInput,
        resolved_strategy_configuration: Mapping[str, Any],
        planning_context: PreMarketPlanningContext,
        failure: PreMarketPlanFailure,
    ) -> PreMarketStrategyPlan:
        return PreMarketStrategyPlan(
            plan_id=f"{runtime_input.evaluation_id}:premarket",
            plan_version=self.plan_version,
            strategy_family=runtime_input.strategy_family_id or runtime_input.strategy_code or "UNKNOWN",
            strategy_definition=runtime_input.strategy_definition_id or runtime_input.strategy_branch or runtime_input.strategy_code or "UNKNOWN",
            strategy_version=runtime_input.strategy_version or "",
            strategy_instance_id=runtime_input.strategy_instance_id or "UNKNOWN",
            resolved_configuration_hash=runtime_input.resolved_configuration_hash or "",
            trading_date=runtime_input.session_date,
            enabled=planning_context.enabled,
            fresh_entry_eligible=False,
            plan_status=PreMarketPlanStatus.NO_ACTION_TODAY,
            block_code=failure.code,
            block_reason=failure.reason,
            monthly_status=runtime_input.monthly_status,
            resolved_branch=runtime_input.strategy_branch,
            product=runtime_input.product_type,
            underlying_instrument=planning_context.underlying_instrument,
            references=PreMarketReferenceSet(),
            contract_resolution=PreMarketContractResolution(),
            planned_values=PreMarketPlannedValues(quantity=runtime_input.quantity, lots=runtime_input.lots),
            stage_evidence={},
            missing_fields=(),
            field_provenance=planning_context.field_provenance,
            failures=(failure,),
        )


def _stage_payload(stage: PreMarketStageResult) -> dict[str, Any]:
    return {
        "status": stage.status,
        "failure_code": stage.failure_code,
        "reason": stage.reason,
        "payload": {key: _safe_value(value) for key, value in stage.payload.items()},
        "evidence": dict(stage.evidence),
    }


def _safe_value(value: Any) -> Any:
    if hasattr(value, "deterministic_hash") and hasattr(value, "entry_status"):
        return {
            "engine_id": value.engine_id,
            "status": _enum_value(value.status),
            "entry_status": _enum_value(value.entry_status),
            "quality": _enum_value(value.quality),
            "base_entry": _entry_value(getattr(value, "base_entry", None)),
            "effective_entry": _entry_value(getattr(value, "effective_entry", None)),
            "downstream_permission": _enum_value(value.downstream_permission),
            "failures": [_enum_value(item) for item in value.failures],
            "warnings": [_enum_value(item) for item in value.warnings],
            "deterministic_hash": value.deterministic_hash,
        }
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "to_json"):
        return value.to_json()
    return value


def _entry_value(candidate: Any) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "value": str(getattr(candidate, "value", "")),
        "source": _enum_value(getattr(candidate, "source", None)),
        "status": _enum_value(getattr(candidate, "status", None)),
        "quality": _enum_value(getattr(candidate, "quality", None)),
    }


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _metadata_float(selected: Any, key: str) -> float | None:
    value = selected.metadata.get(key)
    return None if value is None else float(value)


def _engine_value(result: Any, attr: str) -> float | None:
    candidate = getattr(result, attr, None)
    if candidate is None:
        return None
    value = getattr(candidate, "value", None)
    return None if value is None else float(value)
