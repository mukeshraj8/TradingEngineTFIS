from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from tfis.execution_intent.models import (
    ExecutionAuthorityMode,
    ExecutionInstrument,
    ExecutionIntent,
    ExecutionIntentEvidence,
    ExecutionIntentPurpose,
    IntentValidationDecision,
    RequestedExecutionAction,
)
from tfis.execution_intent.reports import build_validation_input
from tfis.execution_intent.validation import ExecutionIntentValidator
from tfis.execution_intent.pricing import normalize_executable_price
from tfis.internal_paper import (
    DeterministicExecutionScenarioDefinition,
    DeterministicMarketEvidence,
    InternalPaperAuthorityGrant,
    InternalPaperExecutionScenario,
    SequentialAccountIntentCandidate,
    SequentialAccountIntentProcessor,
    SimulatedPaperAccountSnapshot,
)
from tfis.persistence import canonical_hash

from .registry import EnabledStrategyInstance


RULE_MATRIX_VERSION = "tfis_authoritative_workbook_rule_matrix.v1"
MONTHLY_DERIVATION_REPORTS: dict[str, tuple[str, ...]] = {
    "S22_RELIANCE_INTERNAL_PAPER_A": ("reports/s22_reliance/s22_reliance_monthly_status.json",),
}


@dataclass(frozen=True, slots=True)
class DecisionExplanationFact:
    decision_id: str
    trading_session_id: str
    strategy_instance_id: str
    instrument: str
    stage: str
    rule_id: str
    workbook_source: str
    formula_text: str
    input_values: Mapping[str, Any]
    output_value: Mapping[str, Any]
    candidate_evidence: Mapping[str, Any]
    rejection_reason: str | None
    evidence_source: str
    evidence_quality: str
    calculation_timestamp: str
    evidence_mode: str
    parent_decision_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "trading_session_id": self.trading_session_id,
            "strategy_instance_id": self.strategy_instance_id,
            "instrument": self.instrument,
            "stage": self.stage,
            "rule_id": self.rule_id,
            "workbook_source": self.workbook_source,
            "formula_text": self.formula_text,
            "input_values": dict(self.input_values),
            "output_value": dict(self.output_value),
            "candidate_evidence": dict(self.candidate_evidence),
            "rejection_reason": self.rejection_reason,
            "evidence_source": self.evidence_source,
            "evidence_quality": self.evidence_quality,
            "calculation_timestamp": self.calculation_timestamp,
            "evidence_mode": self.evidence_mode,
            "parent_decision_id": self.parent_decision_id,
        }


def _load_monthly_derivation_for_fast_track(
    *,
    instance: EnabledStrategyInstance,
    continuity: Mapping[str, Any],
) -> dict[str, Any]:
    payload: Mapping[str, Any] | None = None
    source_path: str | None = None
    repo_root = Path(__file__).resolve().parents[4]
    for relative_path in MONTHLY_DERIVATION_REPORTS.get(instance.strategy_instance_id, ()):
        target = repo_root / relative_path
        try:
            candidate = json.loads(target.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        if isinstance(candidate, Mapping):
            payload = candidate
            source_path = relative_path
            break

    final_status = continuity.get("monthly_status") or continuity.get("plan_payload", {}).get("monthly_status")
    if payload is None:
        return {
            "available": False,
            "source_path": source_path,
            "rule_id": continuity.get("plan_payload", {}).get("monthly_status_rule_id") or "MONTHLY_STATUS.GENERIC.ENGINE.001",
            "workbook_source": "MONTHLY_STATUS_ENGINE_SUMMARY_ONLY",
            "formula_text": "Monthly Status came from the generic monthly-status engine, but this snapshot does not include the full monthly reference packet for this instrument.",
            "evaluation_timestamp": None,
            "current_window_direct_status": None,
            "borrowed_window_status": None,
            "lookback_used": None,
            "checked_lookback_windows": None,
            "trigger_name": None,
            "threshold_value": None,
            "reason": f"Final Monthly Status is {final_status or 'not available'}, but the step-by-step monthly reference packet was not persisted for this instrument in the current fast-track snapshot.",
            "references": {},
            "steps": [
                {
                    "step": 1,
                    "title": "Read the final Monthly Status from the generic engine output",
                    "result": final_status or "Not available in this snapshot",
                    "detail": "This fast-track snapshot preserved the final Monthly Status value but did not persist the full monthly reference packet for this instrument.",
                    "values": {
                        "monthly_status": final_status,
                        "instrument": instance.symbol,
                    },
                },
                {
                    "step": 2,
                    "title": "Use that status as the first gate before branch selection",
                    "result": continuity.get("selected_branch") or continuity.get("plan_payload", {}).get("selected_branch") or "Branch not available",
                    "detail": "TFIS uses Monthly Status first. Only after that does the strategy continue to branch mapping and contract selection.",
                    "values": {
                        "selected_branch": continuity.get("selected_branch") or continuity.get("plan_payload", {}).get("selected_branch"),
                    },
                },
            ],
        }

    references = payload.get("source_monthly_references") if isinstance(payload.get("source_monthly_references"), Mapping) else {}
    transition_evidence = payload.get("transition_evidence") if isinstance(payload.get("transition_evidence"), Mapping) else {}
    trace = transition_evidence.get("trace") if isinstance(transition_evidence.get("trace"), list) else []
    steps = [
        {
            "step": 1,
            "title": "Load monthly and weekly reference levels",
            "result": "Reference levels loaded",
            "detail": "TFIS loaded the previous-month, current-month, previous-week, current-week, and current-price levels needed by the generic monthly-status engine.",
            "values": dict(references),
        },
        {
            "step": 2,
            "title": "Check whether the current month alone is decisive",
            "result": payload.get("current_window_direct_status") or "Not available in this snapshot",
            "detail": "The engine first asks whether the current month directly proves a bullish or bearish monthly state.",
            "values": {
                "current_window_direct_status": payload.get("current_window_direct_status"),
                "evaluation_timestamp": payload.get("evaluation_timestamp"),
            },
        },
    ]
    for item in trace:
        if not isinstance(item, Mapping):
            continue
        steps.append(
            {
                "step": len(steps) + 1,
                "title": f"Evaluate {str(item.get('window_label') or 'historical context').replace('_', ' ')}",
                "result": item.get("status") or "Not available in this snapshot",
                "detail": str(item.get("notes") or "The engine reviewed this context while resolving the final Monthly Status."),
                "values": {
                    "context_month": item.get("context_month_label"),
                    "context_week": item.get("context_week_label"),
                    "trigger_name": item.get("trigger_name"),
                    "threshold_value": item.get("threshold_value"),
                    "used_for_resolution": item.get("used_for_resolution"),
                },
            }
        )
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Lock the final Monthly Status",
            "result": payload.get("monthly_status") or final_status or "Not available in this snapshot",
            "detail": str(payload.get("reason") or transition_evidence.get("notes") or "The engine resolved the final Monthly Status."),
            "values": {
                "trigger_name": payload.get("trigger_name"),
                "threshold_value": payload.get("threshold_value"),
                "lookback_used": payload.get("lookback_used"),
            },
        }
    )
    return {
        "available": True,
        "source_path": source_path,
        "rule_id": payload.get("source_rule_id") or "MONTHLY_STATUS.GENERIC.ENGINE.001",
        "workbook_source": "MONTHLY_STATUS_ENGINE_AUTHORITY_PACKET",
        "formula_text": "Monthly Status is derived by the generic monthly-status engine from monthly and weekly reference levels, then resolved through direct classification or lookback continuation logic.",
        "evaluation_timestamp": payload.get("evaluation_timestamp"),
        "current_window_direct_status": payload.get("current_window_direct_status"),
        "borrowed_window_status": payload.get("borrowed_window_status"),
        "lookback_used": payload.get("lookback_used"),
        "checked_lookback_windows": payload.get("checked_lookback_windows"),
        "trigger_name": payload.get("trigger_name"),
        "threshold_value": payload.get("threshold_value"),
        "reason": payload.get("reason"),
        "references": dict(references),
        "steps": steps,
    }


def build_current_entry_actions(
    *,
    registry_instances: Iterable[EnabledStrategyInstance],
    continuities: Mapping[str, Mapping[str, Any]],
    now: datetime,
    trading_session_id: str,
) -> dict[str, Any]:
    instances = {item.strategy_instance_id: item for item in registry_instances}
    valid_candidates: list[SequentialAccountIntentCandidate] = []
    skipped: dict[str, Any] = {}
    explanation_facts: list[dict[str, Any]] = []

    for sequence, strategy_instance_id in enumerate(sorted(instances), start=1):
        instance = instances[strategy_instance_id]
        continuity = continuities.get(strategy_instance_id) or {}
        current_entry_state = str(continuity.get("current_entry_state") or "")
        selected_contract = str(continuity.get("selected_contract") or "")
        evidence_mode = str(continuity.get("recovery_mode") or "LIVE_OBSERVED")
        explanation_facts.extend(
            build_explanation_facts(
                instance=instance,
                continuity=continuity,
                now=now,
                trading_session_id=trading_session_id,
            )
        )
        if current_entry_state not in {"NORMAL_ENTRY_STILL_VALID", "RC_ENTRY_STILL_VALID"}:
            skipped[strategy_instance_id] = {
                "decision": "NO_ORDER",
                "reason": current_entry_state or continuity.get("status") or "BLOCKED",
                "selected_contract": selected_contract or None,
                "evidence_mode": evidence_mode,
            }
            continue
        if not selected_contract:
            skipped[strategy_instance_id] = {
                "decision": "NO_ORDER",
                "reason": "SELECTED_CONTRACT_MISSING",
                "selected_contract": None,
                "evidence_mode": evidence_mode,
            }
            continue

        intent = _build_entry_intent(
            instance=instance,
            continuity=continuity,
            now=now,
            trading_session_id=trading_session_id,
        )
        validation = ExecutionIntentValidator().validate(build_validation_input(intent, validation_id=f"fast-track:{strategy_instance_id}"))
        if validation.decision is not IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE:
            skipped[strategy_instance_id] = {
                "decision": "NO_ORDER",
                "reason": f"VALIDATION_{validation.decision.value}",
                "selected_contract": selected_contract,
                "evidence_mode": evidence_mode,
                "validation_failures": [item.code for item in validation.failures],
            }
            continue
        candidate = SequentialAccountIntentCandidate(
            intent=intent,
            validation_result=validation,
            grant=_build_internal_paper_grant(intent),
            scenario=_build_entry_scenario(intent),
            qualification_timestamp=now,
            intent_creation_sequence=sequence,
        )
        valid_candidates.append(candidate)

    if valid_candidates:
        account_snapshots = {
            candidate.intent.broker_account_id: _build_account_snapshot(candidate.intent.broker_account_id)
            for candidate in valid_candidates
        }
        processed = SequentialAccountIntentProcessor().process(valid_candidates, account_snapshots=account_snapshots)
    else:
        processed = {}

    outcomes_by_instance: dict[str, Any] = {}
    for account_result in processed.values():
        for outcome in account_result.outcomes:
            outcomes_by_instance[outcome.strategy_instance_id] = outcome.to_dict()

    for strategy_instance_id in instances:
        outcomes_by_instance.setdefault(strategy_instance_id, skipped.get(strategy_instance_id) or {
            "decision": "NO_ORDER",
            "reason": "NOT_QUALIFIED",
        })

    for strategy_instance_id, outcome in sorted(outcomes_by_instance.items()):
        continuity = continuities.get(strategy_instance_id) or {}
        explanation_facts.append(
            _action_explanation_fact(
                instance=instances[strategy_instance_id],
                continuity=continuity,
                outcome=outcome,
                now=now,
                trading_session_id=trading_session_id,
            )
        )

    return {
        "schema_version": "tfis.fast_track.current_entry_actions.v1",
        "captured_at": now.isoformat(),
        "trading_session_id": trading_session_id,
        "external_broker_order_authority": "NONE",
        "outcomes": outcomes_by_instance,
        "explanation_facts": explanation_facts,
    }


def build_explanation_facts(
    *,
    instance: EnabledStrategyInstance,
    continuity: Mapping[str, Any],
    now: datetime,
    trading_session_id: str,
) -> list[dict[str, Any]]:
    quote = continuity.get("quote") if isinstance(continuity.get("quote"), Mapping) else {}
    plan = continuity.get("plan_payload") if isinstance(continuity.get("plan_payload"), Mapping) else {}
    reconstruction = continuity.get("reconstruction") if isinstance(continuity.get("reconstruction"), Mapping) else {}
    formulas = plan.get("formula_catalog") if isinstance(plan.get("formula_catalog"), Mapping) else {}
    raw_prices = plan.get("raw_prices") if isinstance(plan.get("raw_prices"), Mapping) else {}
    normalized_prices = plan.get("normalized_prices") if isinstance(plan.get("normalized_prices"), Mapping) else {}
    selected_contract = str(continuity.get("selected_contract") or "")
    evidence_mode = str(continuity.get("recovery_mode") or "LIVE_OBSERVED")
    selected_branch = str(continuity.get("selected_branch") or plan.get("selected_branch") or instance.deterministic_projection.get("branch") or "")
    rejected_candidates = list(continuity.get("rejected_candidates") or plan.get("rejected_candidates") or ())
    selected_contract_payload = plan.get("selected_contract") if isinstance(plan.get("selected_contract"), Mapping) else {}
    evaluated_contracts = list(plan.get("evaluated_contracts") or ())
    monthly_derivation = _load_monthly_derivation_for_fast_track(instance=instance, continuity=continuity)

    decision_root = f"{instance.strategy_instance_id}:{canonical_hash({'contract': selected_contract, 'ts': now.isoformat()})[:12]}"
    facts: list[DecisionExplanationFact] = [
        DecisionExplanationFact(
            decision_id=f"{decision_root}:monthly",
            trading_session_id=trading_session_id,
            strategy_instance_id=instance.strategy_instance_id,
            instrument=instance.symbol,
            stage="MONTHLY_STATUS",
            rule_id=str(monthly_derivation.get("rule_id") or "MONTHLY_STATUS.GENERIC.ENGINE.001"),
            workbook_source=str(monthly_derivation.get("workbook_source") or "MONTHLY_STATUS_ENGINE"),
            formula_text=str(monthly_derivation.get("formula_text") or "Monthly Status emitted by the generic monthly-status engine."),
            input_values={
                "instrument": instance.symbol,
                "evaluation_timestamp": monthly_derivation.get("evaluation_timestamp"),
                "monthly_references": dict(monthly_derivation.get("references") or {}),
            },
            output_value={
                "monthly_status": continuity.get("monthly_status"),
                "derivation_summary": monthly_derivation.get("reason"),
            },
            candidate_evidence={"derivation": monthly_derivation},
            rejection_reason=None,
            evidence_source=str(continuity.get("evidence") or "UNKNOWN"),
            evidence_quality=str(monthly_derivation.get("available") and "DERIVATION_PACKET_AVAILABLE" or "SUMMARY_ONLY"),
            calculation_timestamp=now.isoformat(),
            evidence_mode=evidence_mode,
        ),
        DecisionExplanationFact(
            decision_id=f"{decision_root}:contract",
            trading_session_id=trading_session_id,
            strategy_instance_id=instance.strategy_instance_id,
            instrument=instance.symbol,
            stage="CONTRACT_SELECTION",
            rule_id=str(plan.get("contract_selection_rule_id") or "LIVE.ACTUAL_CHAIN.CONTRACT_SELECTION.001"),
            workbook_source=", ".join(plan.get("source_cells") or ["TFIS authoritative rule matrix / accepted selection policy"]),
            formula_text=(
                "Scan actual listed contracts for the approved expiry set, then keep only the contracts that satisfy branch, option side, "
                "strike search path, OI, and premium rules before freezing one final selected contract."
            ),
            input_values={
                "monthly_status": continuity.get("monthly_status"),
                "branch": selected_branch,
                "candidate_count": continuity.get("candidate_count") or plan.get("candidate_count"),
                "market_references": dict(plan.get("market_references") or {}),
                "source_cells": list(plan.get("source_cells") or ()),
            },
            output_value={
                "selected_contract": selected_contract or None,
                "selected_option_type": continuity.get("selected_option_type"),
                "selected_expiry": continuity.get("selected_expiry"),
                "selected_strike": continuity.get("selected_strike"),
                "premium": quote.get("ltp") or selected_contract_payload.get("ltp"),
                "oi": quote.get("oi") or selected_contract_payload.get("oi"),
            },
            candidate_evidence={
                "evaluated_contracts": evaluated_contracts,
                "rejected_candidates": rejected_candidates,
                "plan_hash": plan.get("plan_hash"),
                "selection_source": plan.get("selection_source") or continuity.get("evidence"),
                "selection_report_path": plan.get("selection_report_path"),
                "source_cells": list(plan.get("source_cells") or ()),
                "workbook_row_id": plan.get("workbook_row_id"),
                "selected_option_references": dict(plan.get("selected_option_references") or {}),
                "formula_catalog": dict(formulas),
                "evidence_origin": dict(plan.get("evidence_origin") or {}),
                "quote": dict(quote),
            },
            rejection_reason=None if selected_contract else str(continuity.get("unresolved_gap") or continuity.get("status") or "NO_QUALIFYING_CONTRACT"),
            evidence_source=str(continuity.get("evidence") or "UNKNOWN"),
            evidence_quality=str(continuity.get("option_history_status") or "UNKNOWN"),
            calculation_timestamp=now.isoformat(),
            evidence_mode=evidence_mode,
            parent_decision_id=f"{decision_root}:monthly",
        ),
        DecisionExplanationFact(
            decision_id=f"{decision_root}:plan",
            trading_session_id=trading_session_id,
            strategy_instance_id=instance.strategy_instance_id,
            instrument=instance.symbol,
            stage="PLAN_COMPOSITION",
            rule_id=str(plan.get("entry_rule_id") or "S22.ENTRY_ORPT_RC.001"),
            workbook_source=", ".join(plan.get("source_cells") or ["TFIS authoritative rule matrix"]),
            formula_text=" / ".join(
                item
                for item in (
                    formulas.get("base_entry"),
                    formulas.get("target"),
                    formulas.get("original_sl"),
                    formulas.get("revised_entry"),
                    formulas.get("revised_sl"),
                )
                if item
            ) or "Plan formulas unavailable",
            input_values={
                "market_references": dict(plan.get("market_references") or {}),
                "selected_option_references": dict(plan.get("selected_option_references") or {}),
            },
            output_value={
                "base_entry": continuity.get("entry") or normalized_prices.get("base_entry"),
                "target": continuity.get("target") or normalized_prices.get("target"),
                "original_sl": continuity.get("original_sl") or normalized_prices.get("original_sl"),
                "raw_prices": dict(raw_prices),
                "normalized_prices": dict(normalized_prices),
            },
            candidate_evidence={
                "workbook_row_id": plan.get("workbook_row_id"),
                "rule_matrix_version": plan.get("rule_matrix_version"),
                "formula_catalog": dict(formulas),
                "source_cells": list(plan.get("source_cells") or ()),
            },
            rejection_reason=None,
            evidence_source=str((plan.get("evidence_origin") or {}).get("selected_option_history") or continuity.get("evidence") or "UNKNOWN"),
            evidence_quality=str(continuity.get("option_history_status") or "UNKNOWN"),
            calculation_timestamp=now.isoformat(),
            evidence_mode=evidence_mode,
            parent_decision_id=f"{decision_root}:contract",
        ),
        DecisionExplanationFact(
            decision_id=f"{decision_root}:entry",
            trading_session_id=trading_session_id,
            strategy_instance_id=instance.strategy_instance_id,
            instrument=instance.symbol,
            stage="ENTRY_ELIGIBILITY",
            rule_id="GLOBAL.HISTORICAL.RECONSTRUCTION.ENTRY.001",
            workbook_source="TFIS authoritative timing matrix / accepted historical reconstruction rules",
            formula_text="Reconstruct ORPT, RC, and current entry validity from authoritative timestamped option history without backdating action.",
            input_values={
                "base_entry": continuity.get("entry") or instance.deterministic_projection.get("entry"),
                "revised_entry": reconstruction.get("revised_entry"),
                "orpt_result": continuity.get("orpt_result"),
                "rc_result": continuity.get("rc_result"),
                "latest_quote_ltp": quote.get("ltp"),
            },
            output_value={
                "current_entry_state": continuity.get("current_entry_state"),
                "trigger_breach_timestamp": _breach_timestamp_from_reconstruction(reconstruction),
            },
            candidate_evidence={"reconstruction": reconstruction},
            rejection_reason=str(reconstruction.get("block_reason")) if reconstruction.get("block_reason") else None,
            evidence_source=str(continuity.get("evidence") or "UNKNOWN"),
            evidence_quality=str(reconstruction.get("option_evidence_quality") or continuity.get("option_history_status") or "UNKNOWN"),
            calculation_timestamp=now.isoformat(),
            evidence_mode=evidence_mode,
            parent_decision_id=f"{decision_root}:contract",
        ),
    ]
    return [item.to_dict() for item in facts]


def build_development_dashboard_projection(
    *,
    registry_instances: Iterable[EnabledStrategyInstance],
    baseline_results: Mapping[str, Mapping[str, Any]],
    current_entry_actions: Mapping[str, Any],
    now: datetime,
    trading_session_id: str,
) -> dict[str, Any]:
    instances = {item.strategy_instance_id: item for item in registry_instances}
    outcomes = current_entry_actions.get("outcomes") if isinstance(current_entry_actions.get("outcomes"), Mapping) else {}
    explanation_facts = list(current_entry_actions.get("explanation_facts") or ())
    strategies: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    realized_total = Decimal("0")
    unrealized_total = Decimal("0")
    account_accepts: dict[str, list[str]] = {}
    account_rejects: dict[str, list[str]] = {}

    for strategy_instance_id in sorted(instances):
        instance = instances[strategy_instance_id]
        baseline = baseline_results.get(strategy_instance_id) or {}
        selection = baseline.get("selection") if isinstance(baseline.get("selection"), Mapping) else {}
        reconstruction = baseline.get("reconstruction") if isinstance(baseline.get("reconstruction"), Mapping) else {}
        plan = selection.get("plan_payload") if isinstance(selection.get("plan_payload"), Mapping) else {}
        selected_contract = str(selection.get("selected_contract") or "")
        selected_quote = selection.get("quote") if isinstance(selection.get("quote"), Mapping) else {}
        outcome = outcomes.get(strategy_instance_id) if isinstance(outcomes, Mapping) else {}
        decision = str((outcome or {}).get("decision") or "NO_ORDER")
        final_state = str((outcome or {}).get("final_state") or "")
        health = "HEALTHY" if decision == "PROCESSED_INTERNAL_PAPER" else "DEGRADED_EVIDENCE"
        raw_entry = Decimal(str(selection.get("entry") or "0"))
        current_mark = Decimal(str(selected_quote.get("ltp") or selection.get("entry") or "0"))
        quantity = int(instance.configured_quantity.get("lots", 0)) * int(instance.configured_quantity.get("lot_size", 0))
        unrealized = Decimal("0")
        if decision == "PROCESSED_INTERNAL_PAPER" and raw_entry > 0 and quantity > 0:
            unrealized = (raw_entry - current_mark) * Decimal(quantity)
        unrealized_total += unrealized
        if decision == "PROCESSED_INTERNAL_PAPER":
            account_accepts.setdefault(instance.account_reference, []).append(strategy_instance_id)
        else:
            account_rejects.setdefault(instance.account_reference, []).append(strategy_instance_id)

        strategies.append(
            {
                "identity": {
                    "strategy": instance.strategy_definition_id.split("_")[0],
                    "instrument": instance.symbol,
                    "account": instance.account_reference,
                    "instance": strategy_instance_id,
                },
                "state": {
                    "monthly_status": selection.get("monthly_status"),
                    "branch": selection.get("selected_branch"),
                    "runtime_stage": reconstruction.get("current_entry_state"),
                    "health": health,
                    "evidence_quality": selection.get("evidence"),
                },
                "plan": {
                    "selected_contract": selected_contract,
                    "candidate_contract_count": selection.get("candidate_count") or plan.get("candidate_count"),
                    "expiry_candidates": [selection.get("selected_expiry")] if selection.get("selected_expiry") else [],
                    "premium": selected_quote.get("ltp"),
                    "oi": selected_quote.get("oi"),
                    "base_entry": selection.get("entry"),
                    "target": selection.get("target"),
                    "original_sl": selection.get("original_sl"),
                    "orpt": plan.get("orpt_time"),
                    "rc": plan.get("rc_time"),
                    "evidence_quality": selection.get("evidence"),
                    "block_reason": (outcome or {}).get("reason"),
                    "market_references": dict(plan.get("market_references") or {}),
                },
                "execution": {
                    "order_state": final_state or decision,
                    "selected_contract": selected_contract,
                },
                "position": {
                    "health": "OPEN_PROTECTED" if decision == "PROCESSED_INTERNAL_PAPER" else "NOT_OPEN",
                    "selected_contract": selected_contract,
                },
                "accounting": {
                    "realized_pnl": f"{realized_total:.2f}",
                    "unrealized_pnl": f"{unrealized:.2f}",
                    "selected_contract": selected_contract,
                },
                "operations": {
                    "alerts": [
                        {
                            "code": (outcome or {}).get("reason") or "NO_ALERT",
                            "severity": "WARNING" if decision != "PROCESSED_INTERNAL_PAPER" else "INFO",
                        }
                    ],
                },
            }
        )
        if decision == "PROCESSED_INTERNAL_PAPER":
            orders.append(
                {
                    "account": instance.account_reference,
                    "strategy": instance.strategy_definition_id.split("_")[0],
                    "instance": strategy_instance_id,
                    "position_cycle": (outcome or {}).get("client_order_id") or "",
                    "instrument": instance.symbol,
                    "contract": selected_contract,
                    "execution_contract": selected_contract,
                    "purpose": "ENTRY",
                    "generation": 1,
                    "requested_quantity": quantity,
                    "filled_quantity": quantity,
                    "price": selection.get("entry"),
                    "state": final_state or decision,
                    "age": "00:00:00",
                    "latest_event": "INTERNAL_FULL_FILL",
                    "failure": "",
                }
            )
            positions.append(
                {
                    "account": instance.account_reference,
                    "strategy": instance.strategy_definition_id.split("_")[0],
                    "instrument": instance.symbol,
                    "contract": selected_contract,
                    "position_contract": selected_contract,
                    "fresh_or_carried": "FRESH",
                    "quantity": quantity,
                    "average_entry": selection.get("entry"),
                    "mark": selected_quote.get("ltp"),
                    "target": selection.get("target"),
                    "active_sl": selection.get("original_sl"),
                    "protection_status": "PROTECTED",
                    "realized_pnl": "0.00",
                    "unrealized_pnl": f"{unrealized:.2f}",
                    "exit_deadline": "15:00:00",
                    "health": "OPEN_PROTECTED",
                }
            )
        if decision != "PROCESSED_INTERNAL_PAPER":
            alerts.append(
                {
                    "severity": "WARNING",
                    "code": (outcome or {}).get("reason") or "NO_ORDER",
                    "strategy_instance_id": strategy_instance_id,
                    "instrument": instance.symbol,
                }
            )

    accounts = []
    for account_reference in sorted({item.account_reference for item in instances.values()}):
        accepted = account_accepts.get(account_reference, [])
        rejected = account_rejects.get(account_reference, [])
        accounts.append(
            {
                "account_reference": account_reference,
                "status": "HEALTHY" if not rejected else "CONDITIONAL",
                "limits": {"max_margin_usage_pct": 70, "max_new_entries_per_session": 3},
                "usage": {"accepted_instances": len(accepted), "rejected_instances": len(rejected)},
                "accepted_instances": accepted,
                "rejected_instances": rejected,
                "alerts": [],
                "projection_hash": canonical_hash({"account": account_reference, "accepted": accepted, "rejected": rejected}),
            }
        )

    strategy_instances = _build_fast_track_strategy_instances(strategies)
    strategy_definitions = _build_fast_track_strategy_definitions(strategy_instances)
    strategy_status_counts = _build_fast_track_strategy_status_counts(strategy_instances)
    strategy_filter_options = _build_fast_track_strategy_filter_options(strategy_instances, strategy_definitions)
    navigation = {
        "operator_mode": [
            "Command Centre",
            "Strategies",
            "Orders",
            "Positions",
            "Accounts",
            "Risk",
            "Historical Trades",
            "Alerts",
            "Audit",
            "Settings",
        ],
        "engineering_mode": [
            "Decision Explorer",
            "Monthly Status",
            "Contract Selection",
            "Manual Validation",
            "Replay",
            "Explanation Library",
            "Diagnostics",
            "Source Trace",
        ],
        "strategy_groups": _build_fast_track_strategy_groups(strategy_definitions, strategy_status_counts),
        "product_modes_share_backend_truth": True,
    }
    strategy_families = _build_fast_track_strategy_families(strategy_instances)

    projection = {
        "schema_version": "tfis.fast_track.dashboard_projection.v3",
        "system": {
            "broker_order_authority": "NONE",
            "session": trading_session_id,
            "generated_at": now.isoformat(),
            "projection_version": "dashboard_v3",
        },
        "navigation": navigation,
        "command_centre": {
            "active_orders": len(orders),
            "blocked_instances": sum(1 for item in strategies if item["execution"]["order_state"] != "FILLED_INTERNAL"),
            "broker_sessions": "READ_ONLY_INTERNAL_PAPER",
            "critical_alerts": len(alerts),
            "enabled_strategy_instances": len(strategies),
            "margin_usage_pct": 0,
            "market_state": "HISTORICAL_RECONSTRUCTION",
            "open_positions": len(positions),
            "plans_prepared": len(strategies),
            "realized_pnl": f"{realized_total:.2f}",
            "system_state": "HEALTHY" if not alerts else "CONDITIONAL",
            "unprotected_positions": 0,
            "unrealized_pnl": f"{unrealized_total:.2f}",
            "strategy_definition_summaries": strategy_definitions,
        },
        "strategy_families": strategy_families,
        "strategy_definitions": strategy_definitions,
        "strategy_instances": strategy_instances,
        "strategy_status_counts": strategy_status_counts,
        "strategy_filter_options": strategy_filter_options,
        "strategies": strategies,
        "accounts": accounts,
        "orders": orders,
        "positions": positions,
        "analytics": {
            "strategy_count": len(strategies),
            "decision_explanation_facts": len(explanation_facts),
            "processed_internal_paper": len(orders),
            "no_order": len(strategies) - len(orders),
        },
        "alerts": alerts,
        "audit": [],
        "decision_explanations": explanation_facts,
    }
    projection["projection_hash"] = canonical_hash({k: v for k, v in projection.items() if k != "projection_hash"})
    return projection


def _build_fast_track_strategy_instances(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in strategies:
        runtime_stage = str(item.get("state", {}).get("runtime_stage") or "")
        position_state = str(item.get("position", {}).get("health") or "")
        execution_state = str(item.get("execution", {}).get("order_state") or "")
        evidence = item.get("state", {}).get("evidence_quality")
        rows.append(
            {
                "strategy_instance_id": item.get("identity", {}).get("instance"),
                "strategy_definition_id": item.get("identity", {}).get("strategy"),
                "strategy_code": item.get("identity", {}).get("strategy"),
                "strategy_display_name": item.get("identity", {}).get("strategy"),
                "family": item.get("identity", {}).get("product_label") or item.get("identity", {}).get("product") or "Unknown",
                "segment": item.get("identity", {}).get("segment_label") or item.get("identity", {}).get("segment") or "Unknown",
                "instrument": item.get("identity", {}).get("instrument"),
                "enabled": True,
                "enabled_label": "Enabled",
                "account": item.get("identity", {}).get("account"),
                "monthly_status": item.get("state", {}).get("monthly_status"),
                "branch": item.get("state", {}).get("branch"),
                "current_stage": runtime_stage,
                "selected_contract": item.get("plan", {}).get("selected_contract"),
                "entry": item.get("plan", {}).get("base_entry"),
                "position": position_state,
                "position_label": position_state.replace("_", " ").title(),
                "fresh_or_carried": item.get("position", {}).get("fresh_or_carried") or "FRESH",
                "realized_pnl": item.get("accounting", {}).get("realized_pnl") or "0.00",
                "unrealized_pnl": item.get("accounting", {}).get("unrealized_pnl") or "0.00",
                "health": item.get("state", {}).get("health"),
                "health_label": str(item.get("state", {}).get("health") or "").replace("_", " ").title(),
                "evidence": evidence,
                "evidence_label": str(evidence or "").replace("_", " ").title(),
                "last_update": item.get("state", {}).get("last_update"),
                "alerts": tuple(item.get("operations", {}).get("alerts") or ()),
                "has_alerts": bool(item.get("operations", {}).get("alerts")),
                "entry_available": runtime_stage in {"NORMAL_ENTRY_STILL_VALID", "RC_ENTRY_STILL_VALID", "ENTRY_AVAILABLE"},
                "blocked": runtime_stage.startswith("BLOCKED"),
                "no_trade": execution_state == "NO_ORDER" and not position_state.startswith("OPEN"),
                "qualified": bool(item.get("plan", {}).get("selected_contract")),
            }
        )
    return rows


def _build_fast_track_strategy_definitions(strategy_instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in strategy_instances:
        grouped.setdefault(str(row["strategy_definition_id"]), []).append(row)
    rows: list[dict[str, Any]] = []
    for definition_id, items in sorted(grouped.items()):
        rows.append(
            {
                "strategy_definition_id": definition_id,
                "strategy_code": definition_id,
                "display_name": definition_id,
                "family": items[0]["family"],
                "segment": items[0]["segment"],
                "supported_count": len(items),
                "enabled_count": len(items),
                "prepared_count": sum(1 for item in items if item["current_stage"]),
                "qualified_count": sum(1 for item in items if item["qualified"]),
                "entry_available_count": sum(1 for item in items if item["entry_available"]),
                "open_count": sum(1 for item in items if str(item["position"]).startswith("OPEN")),
                "carried_count": sum(1 for item in items if item["fresh_or_carried"] == "CARRIED"),
                "blocked_count": sum(1 for item in items if item["blocked"]),
                "no_trade_count": sum(1 for item in items if item["no_trade"]),
                "realized_pnl": f"{sum(Decimal(str(item['realized_pnl'])) for item in items):.2f}",
                "unrealized_pnl": f"{sum(Decimal(str(item['unrealized_pnl'])) for item in items):.2f}",
                "margin_usage_pct": sum(18 for item in items if str(item["position"]).startswith("OPEN")),
                "health": "HEALTHY" if all(str(item["health"]).upper() == "HEALTHY" for item in items) else "DEGRADED_EVIDENCE",
                "evidence_quality": ", ".join(sorted({str(item["evidence"]) for item in items if item["evidence"]})),
                "last_update": max(str(item["last_update"] or "") for item in items),
            }
        )
    return rows


def _build_fast_track_strategy_status_counts(strategy_instances: list[dict[str, Any]]) -> dict[str, Any]:
    def counts(items: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "all": len(items),
            "enabled": sum(1 for item in items if item["enabled"]),
            "entry_available": sum(1 for item in items if item["entry_available"]),
            "open_positions": sum(1 for item in items if str(item["position"]).startswith("OPEN")),
            "carried": sum(1 for item in items if item["fresh_or_carried"] == "CARRIED"),
            "blocked": sum(1 for item in items if item["blocked"]),
            "no_trade": sum(1 for item in items if item["no_trade"]),
            "missing_evidence": sum(1 for item in items if str(item["evidence"]).upper() in {"DEGRADED_EVIDENCE", "DETERMINISTIC_TIMING_SUPPLEMENT"}),
            "alerts": sum(1 for item in items if item["has_alerts"]),
        }

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in strategy_instances:
        grouped.setdefault(str(row["strategy_definition_id"]), []).append(row)
    return {
        "global": counts(strategy_instances),
        "by_definition": {definition_id: counts(items) for definition_id, items in sorted(grouped.items())},
    }


def _build_fast_track_strategy_filter_options(
    strategy_instances: list[dict[str, Any]],
    strategy_definitions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "definitions": [
            {
                "strategy_definition_id": item["strategy_definition_id"],
                "strategy_code": item["strategy_code"],
                "display_name": item["display_name"],
            }
            for item in strategy_definitions
        ],
        "accounts": sorted({str(item["account"]) for item in strategy_instances}),
        "monthly_statuses": sorted({str(item["monthly_status"]) for item in strategy_instances if item["monthly_status"]}),
        "branches": sorted({str(item["branch"]) for item in strategy_instances if item["branch"]}),
        "stages": sorted({str(item["current_stage"]) for item in strategy_instances if item["current_stage"]}),
        "health": sorted({str(item["health"]) for item in strategy_instances if item["health"]}),
        "evidence": sorted({str(item["evidence"]) for item in strategy_instances if item["evidence"]}),
        "sort_fields": [
            {"key": "realized_pnl", "label": "Realized P&L"},
            {"key": "unrealized_pnl", "label": "Unrealized P&L"},
            {"key": "current_stage", "label": "Current Stage"},
            {"key": "last_update", "label": "Last Update"},
            {"key": "instrument", "label": "Instrument"},
        ],
        "page_sizes": [10, 20, 50],
    }


def _build_fast_track_strategy_groups(
    strategy_definitions: list[dict[str, Any]],
    strategy_status_counts: Mapping[str, Any],
) -> list[dict[str, Any]]:
    definitions = []
    family = strategy_definitions[0]["family"] if strategy_definitions else "Unclassified"
    for item in strategy_definitions:
        definitions.append(
            {
                "strategy_definition_id": item["strategy_definition_id"],
                "strategy_code": item["strategy_code"],
                "display_name": item["display_name"],
                "enabled_count": item["enabled_count"],
                "supported_count": item["supported_count"],
                "status_counts": strategy_status_counts.get("by_definition", {}).get(item["strategy_definition_id"], {}),
            }
        )
    return [{"family": family, "definitions": definitions}]


def _build_fast_track_strategy_families(strategy_instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    family = strategy_instances[0]["family"] if strategy_instances else "Unclassified"
    return [
        {
            "family": family,
            "instrument_count": len(strategy_instances),
            "strategy_count": len({str(item["strategy_code"]) for item in strategy_instances}),
            "active_positions": sum(1 for item in strategy_instances if str(item["position"]).startswith("OPEN")),
            "blocked": sum(1 for item in strategy_instances if item["blocked"]),
            "no_trade": sum(1 for item in strategy_instances if item["no_trade"]),
            "daily_pnl": f"{sum(Decimal(str(item['realized_pnl'])) + Decimal(str(item['unrealized_pnl'])) for item in strategy_instances):.2f}",
            "evidence_quality": ", ".join(sorted({str(item["evidence"]) for item in strategy_instances if item["evidence"]})),
            "health": "HEALTHY" if all(str(item["health"]).upper() == "HEALTHY" for item in strategy_instances) else "DEGRADED_EVIDENCE",
            "scalability_demo": False,
        }
    ]


def build_candidate_rejection_audit(
    *,
    continuities: Mapping[str, Mapping[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "tfis.fast_track.candidate_rejection_audit.v1",
        "captured_at": now.isoformat(),
        "instances": {
            strategy_instance_id: {
                "selected_contract": continuity.get("selected_contract"),
                "candidate_count": continuity.get("candidate_count"),
                "rejected_candidates": list(continuity.get("rejected_candidates") or ()),
            }
            for strategy_instance_id, continuity in sorted(continuities.items())
        },
    }


def write_fast_track_reports(
    *,
    report_dir: Path,
    session_date: date,
    trading_session_id: str,
    baseline_results: Mapping[str, Mapping[str, Any]],
    current_entry_actions: Mapping[str, Any],
    tcs_result: Mapping[str, Any],
    infy_result: Mapping[str, Any],
    registry_instances: Iterable[EnabledStrategyInstance] | None = None,
) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.fromisoformat(str(current_entry_actions["captured_at"]))
    projection = build_development_dashboard_projection(
        registry_instances=tuple(registry_instances or ()),
        baseline_results=baseline_results,
        current_entry_actions=current_entry_actions,
        now=captured_at,
        trading_session_id=trading_session_id,
    ) if registry_instances is not None else None
    files: dict[str, Any] = {
        "historical_reconstruction_status.json": {
            "schema_version": "tfis.fast_track.historical_reconstruction_status.v1",
            "trading_date": session_date.isoformat(),
            "trading_session_id": trading_session_id,
            "instances": {
                key: {
                    "selected_contract": value.get("selection", {}).get("selected_contract"),
                    "current_entry_state": value.get("reconstruction", {}).get("current_entry_state"),
                    "evidence_mode": value.get("selection", {}).get("recovery_mode"),
                }
                for key, value in sorted(baseline_results.items())
            },
            "external_broker_order_authority": "NONE",
        },
        "today_s21_result.json": baseline_results.get("S21_BANKNIFTY_INTERNAL_PAPER_A"),
        "today_s22_result.json": baseline_results.get("S22_RELIANCE_INTERNAL_PAPER_A"),
        "today_s23_result.json": baseline_results.get("S23_NIFTY_INTERNAL_PAPER_A"),
        "current_entry_actions.json": current_entry_actions,
        "explanation_fact_contract.json": {
            "schema_version": "tfis.fast_track.explanation_fact_contract.v1",
            "fact_fields": list(DecisionExplanationFact.__dataclass_fields__),
            "fact_count": len(tuple(current_entry_actions.get("explanation_facts") or ())),
        },
        "candidate_rejection_audit.json": build_candidate_rejection_audit(
            continuities={
                key: {
                    **(value.get("selection") or {}),
                    **(value.get("reconstruction") or {}),
                }
                for key, value in baseline_results.items()
            },
            now=captured_at,
        ),
        "dashboard_explainability_result.json": {
            "schema_version": "tfis.fast_track.dashboard_explainability_result.v1",
            "strategy_count": len(baseline_results),
            "explanation_fact_count": len(tuple(current_entry_actions.get("explanation_facts") or ())),
            "immutable_runtime_fact_source": True,
            "frontend_formula_execution": False,
            "status": "BACKEND_FACTS_READY_FOR_DASHBOARD_CONSUMPTION",
            "dashboard_projection_path": "dashboard_projection.json" if projection is not None else None,
        },
        "tcs_development_result.json": tcs_result,
        "infy_development_result.json": infy_result,
        "manual_replay_result.json": {
            "schema_version": "tfis.fast_track.manual_replay_result.v1",
            "status": "NOT_IMPLEMENTED_IN_THIS_SLICE",
            "reason": "Fast-track completion reused runtime and report facts only; no separate manual replay surface was added in this patch.",
        },
        "remaining_real_gaps.json": {
            "schema_version": "tfis.fast_track.remaining_real_gaps.v1",
            "gaps": [
                {
                    "gap_id": "FAST_TRACK_GAP_001",
                    "status": "OPEN",
                    "description": "This slice remains development-internal-paper only; TCS and INFY must stay disabled outside the dedicated development registry/profile.",
                },
            ],
        },
    }
    if projection is not None:
        files["dashboard_projection.json"] = projection
        files["dashboard_snapshot_summary.json"] = {
            "schema_version": "tfis.fast_track.dashboard_snapshot_summary.v1",
            "projection_hash": projection["projection_hash"],
            "strategy_count": len(projection["strategies"]),
            "decision_explanation_count": len(projection["decision_explanations"]),
            "external_broker_order_authority": projection["system"]["broker_order_authority"],
        }
    for strategy_instance_id, payload in sorted(baseline_results.items()):
        files[f"{strategy_instance_id.lower()}_isolated_result.json"] = _build_isolated_instance_report(
            strategy_instance_id=strategy_instance_id,
            baseline_payload=payload,
            current_entry_actions=current_entry_actions,
            projection=projection,
            trading_session_id=trading_session_id,
            captured_at=captured_at,
        )
    written: dict[str, Path] = {}
    for name, payload in files.items():
        path = report_dir / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[name] = path
    return written


def _build_isolated_instance_report(
    *,
    strategy_instance_id: str,
    baseline_payload: Mapping[str, Any],
    current_entry_actions: Mapping[str, Any],
    projection: Mapping[str, Any] | None,
    trading_session_id: str,
    captured_at: datetime,
) -> dict[str, Any]:
    selection = baseline_payload.get("selection") if isinstance(baseline_payload.get("selection"), Mapping) else {}
    reconstruction = baseline_payload.get("reconstruction") if isinstance(baseline_payload.get("reconstruction"), Mapping) else {}
    action = (current_entry_actions.get("outcomes") or {}).get(strategy_instance_id, {})
    explanation_facts = [
        item
        for item in current_entry_actions.get("explanation_facts") or ()
        if isinstance(item, Mapping) and item.get("strategy_instance_id") == strategy_instance_id
    ]
    projection_strategy = {}
    projection_position = {}
    projection_orders: list[Mapping[str, Any]] = []
    projection_account = {}
    if projection is not None:
        projection_strategy = next(
            (
                item
                for item in projection.get("strategies") or ()
                if isinstance(item, Mapping)
                and isinstance(item.get("identity"), Mapping)
                and item["identity"].get("instance") == strategy_instance_id
            ),
            {},
        )
        projection_instrument = (
            projection_strategy.get("identity", {}).get("instrument")
            if isinstance(projection_strategy.get("identity"), Mapping)
            else selection.get("symbol")
        )
        projection_position = next(
            (
                item
                for item in projection.get("positions") or ()
                if isinstance(item, Mapping)
                and item.get("instrument") == projection_instrument
                and item.get("contract") == selection.get("selected_contract")
            ),
            {},
        )
        projection_orders = [
            item
            for item in projection.get("orders") or ()
            if isinstance(item, Mapping) and item.get("instance") == strategy_instance_id
        ]
        account_reference = (
            projection_strategy.get("identity", {}).get("account")
            if isinstance(projection_strategy.get("identity"), Mapping)
            else None
        )
        projection_account = next(
            (
                item
                for item in projection.get("accounts") or ()
                if isinstance(item, Mapping) and item.get("account_reference") == account_reference
            ),
            {},
        )

    return {
        "schema_version": "tfis.fast_track.strategy_isolated_result.v1",
        "captured_at": captured_at.isoformat(),
        "trading_session_id": trading_session_id,
        "strategy_instance_id": strategy_instance_id,
        "identity": {
            "strategy": projection_strategy.get("identity", {}).get("strategy"),
            "instrument": projection_strategy.get("identity", {}).get("instrument") or selection.get("symbol"),
            "account": projection_strategy.get("identity", {}).get("account"),
        },
        "selection": selection,
        "reconstruction": reconstruction,
        "action": action,
        "position_cycle": {
            "orders": projection_orders,
            "position": projection_position,
        },
        "accounting": projection_strategy.get("accounting") if isinstance(projection_strategy.get("accounting"), Mapping) else {},
        "dashboard_strategy": projection_strategy,
        "dashboard_account": projection_account,
        "decision_explanations": explanation_facts,
        "external_broker_order_authority": "NONE",
    }


def _build_entry_intent(
    *,
    instance: EnabledStrategyInstance,
    continuity: Mapping[str, Any],
    now: datetime,
    trading_session_id: str,
) -> ExecutionIntent:
    quantity = int(instance.configured_quantity["lots"]) * int(instance.configured_quantity["lot_size"])
    raw_entry_price = Decimal(str(continuity.get("entry") or instance.deterministic_projection.get("entry") or "0"))
    selected_contract = str(continuity.get("selected_contract"))
    strike = continuity.get("selected_strike")
    expiry = continuity.get("selected_expiry")
    option_type = continuity.get("selected_option_type")
    tick_size = Decimal("0.05")
    entry_price = normalize_executable_price(raw_entry_price, tick_size)
    instrument = ExecutionInstrument(
        exchange="NSE",
        segment="DERIVATIVE",
        product=instance.product,
        underlying=instance.symbol,
        contract=selected_contract,
        expiry=date.fromisoformat(str(expiry)) if expiry else None,
        strike=Decimal(str(strike)) if strike not in (None, "") else None,
        option_type=str(option_type) if option_type else None,
        lot_size=int(instance.configured_quantity["lot_size"]),
        tick_size=tick_size,
        multiplier=Decimal("1"),
        currency="INR",
    )
    evidence_payload = {
        "continuity": continuity.get("current_entry_state"),
        "contract": selected_contract,
        "captured_at": now.isoformat(),
        "raw_entry_price": str(raw_entry_price),
        "normalized_entry_price": str(entry_price) if entry_price is not None else None,
    }
    evidence = ExecutionIntentEvidence(
        source_rule_ids=("FAST_TRACK.HISTORICAL.RECONSTRUCTION.ENTRY.001",),
        configuration_hash=instance.rule_config_hash,
        rule_matrix_version=RULE_MATRIX_VERSION,
        market_snapshot_hash=canonical_hash(evidence_payload),
        reconciliation_result_id=f"fast-track:reconciliation:{instance.strategy_instance_id}",
        reconciliation_result_hash=canonical_hash({"reconciliation": "SHADOW_READY", "instance": instance.strategy_instance_id}),
        recovery_assessment_id=f"fast-track:recovery:{instance.strategy_instance_id}",
        recovery_assessment_hash=canonical_hash({"recovery_mode": continuity.get("recovery_mode"), "instance": instance.strategy_instance_id}),
        evidence_packet_hash=canonical_hash({"evidence": evidence_payload, "instance": instance.strategy_instance_id}),
        provenance={
            "source": continuity.get("evidence"),
            "recovery_mode": continuity.get("recovery_mode"),
            "current_entry_state": continuity.get("current_entry_state"),
            "raw_entry_price": str(raw_entry_price),
            "normalized_entry_price": str(entry_price) if entry_price is not None else None,
            "price_normalization_rule": "NEAREST_TICK_ROUND_HALF_UP",
        },
        authority_mode=ExecutionAuthorityMode.VALIDATED_NOT_SUBMITTABLE,
    )
    action = RequestedExecutionAction(
        purpose=ExecutionIntentPurpose.ENTRY,
        side="SELL",
        requested_quantity=quantity,
        quantity_unit="LOTS",
        order_type="LIMIT",
        limit_price=entry_price,
        trigger_price=None,
        time_in_force="DAY",
        authorized_not_before=now,
        authorized_not_after=now + timedelta(minutes=5),
        maximum_allowed_slippage=Decimal("0.00"),
        protection_generation=1,
    )
    intent_seed = {
        "strategy_instance_id": instance.strategy_instance_id,
        "contract": selected_contract,
        "authorized_not_before": now.isoformat(),
        "entry": str(entry_price),
    }
    intent_hash_seed = canonical_hash(intent_seed)
    return ExecutionIntent(
        execution_intent_id=f"fast-track:{instance.strategy_instance_id}:{intent_hash_seed[:12]}",
        schema_version="phase4e.execution_intent.v1",
        trading_session_id=trading_session_id,
        trading_date=now.date(),
        strategy_family_id="OPTION_SELLING",
        strategy_definition_id=instance.strategy_definition_id,
        strategy_version=instance.strategy_version,
        strategy_instance_id=instance.strategy_instance_id,
        broker_account_id=instance.account_reference,
        position_cycle_id=None,
        source_artifact_type="HistoricalReconstructionResult",
        source_artifact_id=f"historical-reconstruction:{instance.strategy_instance_id}:{now.date().isoformat()}",
        source_artifact_hash=canonical_hash({"selection": selected_contract, "state": continuity.get("current_entry_state")}),
        idempotency_key=f"fast-track-entry:{instance.strategy_instance_id}:{selected_contract}",
        instrument=instrument,
        action=action,
        evidence=evidence,
    )


def _build_internal_paper_grant(intent: ExecutionIntent) -> InternalPaperAuthorityGrant:
    return InternalPaperAuthorityGrant(
        grant_id=f"fast-track-grant:{intent.execution_intent_id}",
        broker_account_id=intent.broker_account_id,
        trading_session_id=intent.trading_session_id,
        strategy_instance_id=intent.strategy_instance_id,
        allowed_intent_purposes=("ENTRY",),
        maximum_quantity=intent.action.requested_quantity,
        valid_from=intent.action.authorized_not_before - timedelta(minutes=1),
        valid_until=(intent.action.authorized_not_after or intent.action.authorized_not_before + timedelta(minutes=5)),
        configuration_hash=intent.evidence.configuration_hash,
        rule_version=intent.evidence.rule_matrix_version,
        issued_by="FAST_TRACK_DEVELOPMENT",
        reason="Current-time internal-paper action from authoritative historical reconstruction.",
    )


def _build_entry_scenario(intent: ExecutionIntent) -> DeterministicExecutionScenarioDefinition:
    price = intent.action.limit_price or Decimal("0.00")
    return DeterministicExecutionScenarioDefinition(
        scenario_id=f"fast-track:{intent.strategy_instance_id}:entry",
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        market_evidence=DeterministicMarketEvidence(
            bid=max(Decimal("0.05"), price - Decimal("0.05")),
            ask=price + Decimal("0.05"),
            ltp=price,
            high=price + Decimal("1.00"),
            low=max(Decimal("0.05"), price - Decimal("1.00")),
            source_timestamp=intent.action.authorized_not_before,
            snapshot_hash=canonical_hash({"contract": intent.instrument.contract, "price": str(price)}),
        ),
        event_time=intent.action.authorized_not_before,
        fill_quantity=intent.action.requested_quantity,
        fill_price=price,
        rejection_reason=None,
        cancel_reason=None,
    )


def _build_account_snapshot(account_reference: str) -> SimulatedPaperAccountSnapshot:
    return SimulatedPaperAccountSnapshot(
        broker_account_id=account_reference,
        opening_paper_cash=Decimal("1000000"),
        reserved_margin=Decimal("0"),
        released_margin=Decimal("0"),
        available_paper_margin=Decimal("1000000"),
        simulated_charges=Decimal("0"),
        active_order_reservation=Decimal("0"),
        margin_per_quantity=Decimal("100"),
        account_enabled=True,
        account_blocked=False,
        active_order_count=0,
        max_active_order_count=10,
    )


def _breach_timestamp_from_reconstruction(reconstruction: Mapping[str, Any]) -> str | None:
    for key in ("normal_entry", "revised_entry"):
        payload = reconstruction.get(key)
        if isinstance(payload, Mapping):
            breach = payload.get("breach_timestamp")
            if breach:
                return str(breach)
    return None


def _action_explanation_fact(
    *,
    instance: EnabledStrategyInstance,
    continuity: Mapping[str, Any],
    outcome: Mapping[str, Any],
    now: datetime,
    trading_session_id: str,
) -> dict[str, Any]:
    plan = continuity.get("plan_payload") if isinstance(continuity.get("plan_payload"), Mapping) else {}
    raw_prices = plan.get("raw_prices") if isinstance(plan.get("raw_prices"), Mapping) else {}
    normalized_prices = plan.get("normalized_prices") if isinstance(plan.get("normalized_prices"), Mapping) else {}
    selected_contract = str(continuity.get("selected_contract") or "")
    raw_entry = raw_prices.get("base_entry") or continuity.get("entry")
    normalized_entry = normalized_prices.get("base_entry")
    if normalized_entry in (None, "") and raw_entry not in (None, ""):
        normalized_entry = str(normalize_executable_price(Decimal(str(raw_entry)), Decimal("0.05")))
    decision_root = f"{instance.strategy_instance_id}:{canonical_hash({'contract': selected_contract, 'ts': now.isoformat()})[:12]}"
    return DecisionExplanationFact(
        decision_id=f"{decision_root}:action",
        trading_session_id=trading_session_id,
        strategy_instance_id=instance.strategy_instance_id,
        instrument=instance.symbol,
        stage="CURRENT_ACTION",
        rule_id="GLOBAL.SEQUENTIAL.ACCOUNT.ACCEPTANCE.001",
        workbook_source="TFIS global sequential account acceptance rule / executable price normalization rule",
        formula_text="Normalize raw executable price to tick size, keep external broker authority NONE, and process qualifying intents sequentially per account.",
        input_values={
            "raw_entry_price": raw_entry,
            "normalized_entry_price": normalized_entry,
            "current_entry_state": continuity.get("current_entry_state"),
        },
        output_value={
            "decision": outcome.get("decision"),
            "final_state": outcome.get("final_state"),
            "queue_position": outcome.get("queue_position"),
            "required_margin": outcome.get("required_margin"),
            "effective_available_margin": outcome.get("effective_available_margin"),
        },
        candidate_evidence={
            "warning": outcome.get("warning"),
            "client_order_id": outcome.get("client_order_id"),
        },
        rejection_reason=str(outcome.get("reason")) if outcome.get("reason") else None,
        evidence_source=str(continuity.get("evidence") or "UNKNOWN"),
        evidence_quality=str(continuity.get("option_history_status") or "UNKNOWN"),
        calculation_timestamp=now.isoformat(),
        evidence_mode=str(continuity.get("recovery_mode") or "LIVE_OBSERVED"),
        parent_decision_id=f"{decision_root}:entry",
    ).to_dict()
