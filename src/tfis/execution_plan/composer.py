from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping

from tfis.domain import BusinessEngineStatus
from tfis.domain.effective_execution_plan import (
    EffectiveExecutionFailure,
    EffectiveExecutionPath,
    EffectiveExecutionPlan,
    EffectiveExecutionPlanStatus,
    EffectiveExecutionValues,
    EffectiveRiskValueStatus,
)
from tfis.domain.opening_market_context import OpeningContextStatus, OpeningGapClassification, OpeningMarketContext
from tfis.domain.premarket_plan import PreMarketStrategyPlan


@dataclass(frozen=True, slots=True)
class EffectiveExecutionPolicies:
    gap_missed_entry: Callable[[PreMarketStrategyPlan, OpeningMarketContext], Any]
    entry_finalizer: Callable[[PreMarketStrategyPlan, OpeningMarketContext, Any | None], Any]
    target_policy: Callable[[PreMarketStrategyPlan, OpeningMarketContext, Any | None, Any], Any]
    msl_policy: Callable[[PreMarketStrategyPlan, OpeningMarketContext, Any | None, Any, Any], Any]
    timing_policy: Callable[[PreMarketStrategyPlan, OpeningMarketContext, Any | None], Any]
    risk_recalculation_mode: str = "RETAIN_UNLESS_RECALCULATED_ENTRY"


class EffectiveExecutionPlanComposer:
    schema_version = "tfis.effective_execution_plan.v1"

    def compose(
        self,
        premarket_plan: PreMarketStrategyPlan | None,
        opening_context: OpeningMarketContext | None,
        policies: EffectiveExecutionPolicies,
        *,
        plan_revision: int = 1,
        supersedes_plan_id: str | None = None,
    ) -> EffectiveExecutionPlan:
        started = perf_counter()
        if premarket_plan is None:
            return self._blocked(None, opening_context, "compatibility", "MISSING_PLAN", "Pre-market plan is required.", plan_revision, supersedes_plan_id, started)
        if opening_context is None:
            return self._blocked(premarket_plan, None, "compatibility", "MISSING_CONTEXT", "Opening context is required.", plan_revision, supersedes_plan_id, started)
        failures = self._compatibility_failures(premarket_plan, opening_context)
        if failures:
            first = failures[0]
            return self._blocked(premarket_plan, opening_context, first.stage, first.code, first.reason, plan_revision, supersedes_plan_id, started, failures=tuple(failures))
        if opening_context.context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT:
            return self._blocked(premarket_plan, opening_context, "opening_validation", "OPENING_CONTEXT_BLOCKED", "Opening context is blocked.", plan_revision, supersedes_plan_id, started, missing=opening_context.missing_fields)
        if opening_context.context_status is OpeningContextStatus.PARTIAL:
            return self._insufficient(premarket_plan, opening_context, "opening_validation", "INSUFFICIENT_OPENING_EVIDENCE", "Opening context is partial.", plan_revision, supersedes_plan_id, started, missing=opening_context.missing_fields)

        gme = None
        path = EffectiveExecutionPath.NORMAL_RETAINED
        gap_applicability = "NOT_APPLICABLE"
        if opening_context.gap_context.classification not in (OpeningGapClassification.NO_GAP, OpeningGapClassification.NOT_APPLICABLE):
            gme = policies.gap_missed_entry(premarket_plan, opening_context)
            gap_applicability = "APPLICABLE"
            if getattr(gme, "status", None) is not BusinessEngineStatus.PASSED:
                return self._blocked(premarket_plan, opening_context, "gap_missed_entry", "GAP_MISSED_ENTRY_BLOCKED", "Gap/Missed-Entry blocked.", plan_revision, supersedes_plan_id, started, gme=gme)
            recalc = gme.recalculation.status.value
            if recalc == "COMPLETED_BY_COMPATIBILITY_POLICY":
                path = EffectiveExecutionPath.GAP_RECALCULATED
            elif recalc == "NOT_REQUIRED":
                path = EffectiveExecutionPath.GAP_RETAINED
            else:
                return self._blocked(premarket_plan, opening_context, "gap_missed_entry", "UNRESOLVED_RECALCULATION_AUTHORITY", f"Unsupported recalculation status {recalc}.", plan_revision, supersedes_plan_id, started, gme=gme)

        entry = policies.entry_finalizer(premarket_plan, opening_context, gme)
        if getattr(entry, "status", None) is not BusinessEngineStatus.PASSED:
            return self._blocked(premarket_plan, opening_context, "entry", "ENTRY_FINALIZATION_FAILED", "Entry finalization failed.", plan_revision, supersedes_plan_id, started, gme=gme, entry=entry)
        target = policies.target_policy(premarket_plan, opening_context, gme, entry)
        if target.get("status") == "BLOCKED":
            return self._blocked(premarket_plan, opening_context, "target", "TARGET_POLICY_FAILURE", str(target.get("reason")), plan_revision, supersedes_plan_id, started, gme=gme, entry=entry)
        msl = policies.msl_policy(premarket_plan, opening_context, gme, entry, target)
        if msl.get("status") == "BLOCKED":
            return self._blocked(premarket_plan, opening_context, "msl", "MSL_POLICY_FAILURE", str(msl.get("reason")), plan_revision, supersedes_plan_id, started, gme=gme, entry=entry, target=target)
        timing = policies.timing_policy(premarket_plan, opening_context, gme)
        if timing.get("authorized_time") is None:
            return self._blocked(premarket_plan, opening_context, "timing", "INVALID_AUTHORIZED_TIME", "Authorized time is required.", plan_revision, supersedes_plan_id, started, gme=gme, entry=entry, target=target, msl=msl)

        recalculated = path is EffectiveExecutionPath.GAP_RECALCULATED
        return self._plan(
            premarket_plan,
            opening_context,
            plan_revision,
            supersedes_plan_id,
            EffectiveExecutionPlanStatus.READY_OFFLINE,
            path,
            "ELIGIBLE_OFFLINE",
            None,
            None,
            True,
            EffectiveExecutionValues(
                premarket_plan.planned_values.base_entry,
                _entry_value(entry),
                premarket_plan.planned_values.preliminary_target,
                target["value"],
                premarket_plan.planned_values.preliminary_msl,
                msl["value"],
                premarket_plan.planned_values.normal_orpt,
                timing["authorized_time"],
                timing.get("order_type"),
                EffectiveRiskValueStatus.RECALCULATED if recalculated and target.get("recalculated") else EffectiveRiskValueStatus.RETAINED_FROM_PREMARKET,
                EffectiveRiskValueStatus.RECALCULATED if recalculated and msl.get("recalculated") else EffectiveRiskValueStatus.RETAINED_FROM_PREMARKET,
            ),
            gap_applicability,
            gme,
            recalculated,
            timing.get("reason"),
            started,
            stage_evidence={"gap_missed_entry": _safe(gme), "entry": _safe(entry), "target": target, "msl": msl, "timing": timing},
        )

    def _compatibility_failures(self, plan: PreMarketStrategyPlan, context: OpeningMarketContext) -> list[EffectiveExecutionFailure]:
        failures: list[EffectiveExecutionFailure] = []
        if context.source_plan_id != plan.plan_id or context.source_plan_hash != plan.plan_hash:
            failures.append(EffectiveExecutionFailure("compatibility", "PLAN_CONTEXT_HASH_MISMATCH", "Opening context does not reference this plan."))
        if context.trading_date != plan.trading_date:
            failures.append(EffectiveExecutionFailure("compatibility", "TRADING_DATE_MISMATCH", "Trading dates differ."))
        context_strategy_instance = getattr(context, "strategy_instance_id", plan.strategy_instance_id)
        if context_strategy_instance != plan.strategy_instance_id:
            failures.append(EffectiveExecutionFailure("compatibility", "STRATEGY_INSTANCE_MISMATCH", "Strategy instances differ."))
        context_configuration_hash = getattr(context, "resolved_configuration_hash", plan.resolved_configuration_hash)
        if context_configuration_hash != plan.resolved_configuration_hash:
            failures.append(EffectiveExecutionFailure("compatibility", "CONFIGURATION_HASH_MISMATCH", "Resolved configuration hashes differ."))
        if context.underlying_instrument != (plan.underlying_instrument or ""):
            failures.append(EffectiveExecutionFailure("compatibility", "UNDERLYING_MISMATCH", "Underlying differs."))
        selected = plan.contract_resolution.selected_contract
        if selected is None or context.selected_contract.symbol != selected.symbol:
            failures.append(EffectiveExecutionFailure("compatibility", "SELECTED_CONTRACT_MISMATCH", "Selected contract differs."))
        if plan.planned_values.normal_orpt is None:
            failures.append(EffectiveExecutionFailure("compatibility", "MISSING_ORPT", "Plan ORPT is required."))
        if plan.planned_values.rc_time is None and context.rc_observation.availability.value == "AVAILABLE":
            failures.append(EffectiveExecutionFailure("compatibility", "MISSING_RC_TIME", "Plan RC time is required when RC evidence is available."))
        if not plan.planned_values.policy_identities:
            failures.append(EffectiveExecutionFailure("compatibility", "MISSING_POLICY_IDENTITIES", "Plan policy identities are required."))
        return failures

    def _blocked(self, plan, context, stage, code, reason, revision, supersedes, started, *, failures=(), missing=(), **evidence):
        return self._minimal(plan, context, revision, supersedes, EffectiveExecutionPlanStatus.BLOCKED, EffectiveExecutionPath.BLOCKED_OPENING_VALIDATION if stage == "opening_validation" else EffectiveExecutionPath.BLOCKED_GAP_EVALUATION, stage, code, reason, started, failures=failures or (EffectiveExecutionFailure(stage, code, reason),), missing=missing, evidence=evidence)

    def _insufficient(self, plan, context, stage, code, reason, revision, supersedes, started, *, missing=()):
        return self._minimal(plan, context, revision, supersedes, EffectiveExecutionPlanStatus.INSUFFICIENT_EVIDENCE, EffectiveExecutionPath.BLOCKED_OPENING_VALIDATION, stage, code, reason, started, failures=(EffectiveExecutionFailure(stage, code, reason),), missing=missing, evidence={})

    def _minimal(self, plan, context, revision, supersedes, status, path, stage, code, reason, started, *, failures, missing, evidence):
        base = plan.planned_values if plan else None
        return self._plan(
            plan,
            context,
            revision,
            supersedes,
            status,
            path,
            "NOT_ELIGIBLE",
            code,
            reason,
            False,
            EffectiveExecutionValues(
                base.base_entry if base else None,
                None,
                base.preliminary_target if base else None,
                None,
                base.preliminary_msl if base else None,
                None,
                base.normal_orpt if base else None,
                None,
                None,
                EffectiveRiskValueStatus.BLOCKED,
                EffectiveRiskValueStatus.BLOCKED,
            ),
            "UNKNOWN",
            evidence.get("gme"),
            False,
            reason,
            started,
            failures=failures,
            missing=missing,
            stage_evidence={key: _safe(value) for key, value in evidence.items()},
        )

    def _plan(self, plan, context, revision, supersedes, status, path, eligibility, code, reason, candidate, values, gap_applicability, gme, recalculated, retain_reason, started, *, failures=(), missing=(), stage_evidence=None):
        selected = plan.contract_resolution.selected_contract if plan else None
        return EffectiveExecutionPlan(
            execution_plan_id=f"{plan.plan_id if plan else 'missing-plan'}:{context.context_id if context else 'missing-context'}:execution:{revision}",
            schema_version=self.schema_version,
            trading_date=plan.trading_date if plan else (context.trading_date if context else None),
            strategy_family=plan.strategy_family if plan else "UNKNOWN",
            strategy_definition=plan.strategy_definition if plan else "UNKNOWN",
            strategy_version=plan.strategy_version if plan else "",
            strategy_instance_id=plan.strategy_instance_id if plan else "UNKNOWN",
            source_premarket_plan_id=plan.plan_id if plan else "",
            source_premarket_plan_hash=plan.plan_hash if plan else "",
            source_opening_context_id=context.context_id if context else "",
            source_opening_context_hash=context.context_hash if context else "",
            plan_revision=revision,
            supersedes_plan_id=supersedes,
            plan_status=status,
            path_classification=path,
            final_eligibility=eligibility,
            block_code=code,
            block_reason=reason,
            downstream_execution_permission="NONE",
            offline_execution_candidate=candidate,
            product=plan.product if plan else None,
            underlying=plan.underlying_instrument if plan else None,
            selected_expiry=plan.contract_resolution.selected_expiry if plan else None,
            selected_strike=plan.contract_resolution.selected_strike if plan else None,
            selected_contract=selected,
            order_side=plan.planned_values.order_side if plan else None,
            position_intent=plan.planned_values.position_intent if plan else None,
            quantity=plan.planned_values.quantity if plan else None,
            lots=plan.planned_values.lots if plan else None,
            values=values,
            opening_gap_classification=context.gap_context.classification.value if context else None,
            gap_missed_entry_applicability=gap_applicability,
            gap_missed_entry_status=gme.missed_entry.status.value if gme else None,
            recalculation_required=recalculated,
            recalculation_inputs={"source": "opening_context"} if recalculated else {},
            recalculation_output=dict(gme.recalculation.compatibility_outputs) if recalculated and gme else {},
            retain_recalculate_block_reason=retain_reason,
            policy_identities=plan.planned_values.policy_identities if plan else {},
            stage_evidence=stage_evidence or {},
            missing_fields=missing,
            failures=failures,
            performance={"composition_seconds": perf_counter() - started},
        )


def _entry_value(entry: Any) -> float | None:
    effective = getattr(entry, "effective_entry", None)
    if effective is None:
        return None
    return float(effective.value)


def _safe(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "deterministic_hash") and hasattr(value, "entry_status"):
        return {
            "engine_id": value.engine_id,
            "status": value.status.value,
            "entry_status": value.entry_status.value,
            "base_entry": {
                "value": str(value.base_entry.value) if value.base_entry and value.base_entry.value is not None else None,
                "source": value.base_entry.source.value if value.base_entry else None,
                "downstream_permission": value.base_entry.downstream_permission.value if value.base_entry else None,
            }
            if value.base_entry
            else None,
            "effective_entry": {
                "value": str(value.effective_entry.value) if value.effective_entry and value.effective_entry.value is not None else None,
                "status": value.effective_entry.status.value if value.effective_entry else None,
                "source": value.effective_entry.source.value if value.effective_entry else None,
                "downstream_permission": value.effective_entry.downstream_permission.value if value.effective_entry else None,
            }
            if value.effective_entry
            else None,
            "downstream_permission": value.downstream_permission.value,
            "deterministic_hash": value.deterministic_hash,
            "failures": [failure.value for failure in value.failures],
        }
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "to_json"):
        return value.to_json()
    return value
