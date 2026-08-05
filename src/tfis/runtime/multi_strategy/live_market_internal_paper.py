from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tfis.persistence import canonical_hash


@dataclass(frozen=True, slots=True)
class LiveMarketInternalPaperReportResult:
    verdict: str
    report_dir: Path
    summary_path: Path
    files: tuple[str, ...]


def build_live_market_internal_paper_reports(
    *,
    repo_root: str | Path,
    report_dir: str | Path = "reports/live_market_internal_paper",
    snapshot_path: str | Path = "tmp/tfis_dashboard_v1/api/snapshot.json",
    live_supervisor_dir: str | Path = "reports/live_supervisor",
    readiness_path: str | Path = "reports/unified_readiness/authoritative_readiness_projection.json",
    authentication_diagnostics: Mapping[str, Any] | None = None,
) -> LiveMarketInternalPaperReportResult:
    root = Path(repo_root)
    report_root = root / report_dir
    report_root.mkdir(parents=True, exist_ok=True)

    snapshot = _read_json(root / snapshot_path)
    if not snapshot:
        raise FileNotFoundError(f"Snapshot not found or unreadable: {root / snapshot_path}")

    supervisor_root = root / live_supervisor_dir
    validation_summary = _read_json(supervisor_root / "validation_summary.json")
    performance_metrics = _read_json(supervisor_root / "performance_metrics.json")
    routing = _read_json(supervisor_root / "multi_strategy_live_routing.json")
    subscription_state = _read_json(supervisor_root / "subscription_owner_state.json")
    checkpoint_resume = _read_json(supervisor_root / "checkpoint_resume_contract.json")
    late_start_safety = _read_json(supervisor_root / "late_start_safety_result.json")
    account_risk_matrix = _read_json(supervisor_root / "account_risk_acceptance_matrix.json")
    supervisor_gap_register = _read_json(supervisor_root / "gap_register.json")
    failure_isolation = _read_json(supervisor_root / "failure_isolation_matrix.json")
    scheduler_contract = _read_json(supervisor_root / "scheduler_contract.json")
    complete_session_preflight = _read_json(supervisor_root / "complete_session_preflight.json")
    readiness = _read_json(root / readiness_path)

    strategies = snapshot.get("strategies") or []
    orders = snapshot.get("orders") or []
    positions = snapshot.get("positions") or []
    explanations = snapshot.get("decision_explanations") or []
    accounts = snapshot.get("accounts") or []
    analytics = snapshot.get("analytics") or {}
    system = snapshot.get("system") or {}

    by_instance: dict[str, dict[str, Any]] = {}
    order_by_instance = {row.get("strategy_instance_id"): row for row in orders if row.get("strategy_instance_id")}
    position_by_instance = {row.get("strategy_instance_id"): row for row in positions if row.get("strategy_instance_id")}
    explanations_by_instance: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in explanations:
        if isinstance(item, Mapping) and item.get("strategy_instance_id"):
            explanations_by_instance[str(item["strategy_instance_id"])].append(dict(item))

    for row in strategies:
        if not isinstance(row, Mapping):
            continue
        identity = row.get("identity") or {}
        instance_id = identity.get("strategy_instance_id")
        if not instance_id:
            continue
        instance_id = str(instance_id)
        by_instance[instance_id] = {
            "identity": dict(identity),
            "state": dict(row.get("state") or {}),
            "plan": dict(row.get("plan") or {}),
            "execution": dict(row.get("execution") or {}),
            "position": dict(row.get("position") or {}),
            "accounting": dict(row.get("accounting") or {}),
            "operations": dict(row.get("operations") or {}),
            "order_row": dict(order_by_instance.get(instance_id) or {}),
            "position_row": dict(position_by_instance.get(instance_id) or {}),
            "decision_explanations": list(explanations_by_instance.get(instance_id) or []),
        }

    source_audit = _source_level_runtime_audit(by_instance)
    monthly_status_results = _monthly_status_results(by_instance, system)
    contract_selection_audit = _stage_results(by_instance, stage="CONTRACT_SELECTION", system=system)
    orpt_rc_results = _orpt_rc_results(by_instance, system)
    entry_eligibility = _entry_eligibility(by_instance, system)
    internal_paper_orders = _internal_paper_orders(orders, system)
    fill_model_results = _fill_model_results(by_instance, system)
    positions_and_protection = _positions_and_protection(positions, system)
    account_risk_results = _account_risk_results(accounts, analytics, account_risk_matrix, by_instance, system)
    accounting_pnl = _accounting_pnl(accounts, analytics, positions, by_instance, system)
    authority_boundary = _authority_boundary(system, authentication_diagnostics, readiness, complete_session_preflight)
    persistence_integrity = _persistence_integrity(validation_summary, checkpoint_resume, system)
    performance_profile = _performance_profile(performance_metrics, scheduler_contract, system)
    restart_idempotency = _restart_idempotency(validation_summary, checkpoint_resume, late_start_safety, failure_isolation, system)
    market_data_ownership = _market_data_ownership(subscription_state, routing, system)
    session_reconstruction = _session_reconstruction(late_start_safety, routing, snapshot, system)
    dashboard_live_projection = {
        "schema_version": "tfis.live_market_internal_paper.dashboard_live_projection.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "session": system.get("session"),
        "session_id": system.get("session_id"),
        "supervisor_state": system.get("supervisor_state"),
        "broker_order_authority": system.get("broker_order_authority"),
        "projection_hash": snapshot.get("projection_hash"),
        "strategy_count": len(strategies),
        "order_count": len(orders),
        "position_count": len(positions),
        "projection_mode": system.get("projection_mode"),
        "projection": snapshot,
    }

    instance_files = {
        "s21_live_result.json": _instance_live_result(by_instance, "S21_BANKNIFTY_INTERNAL_PAPER_A", system),
        "s22_reliance_live_result.json": _instance_live_result(by_instance, "S22_RELIANCE_INTERNAL_PAPER_A", system),
        "s22_tcs_live_result.json": _instance_live_result(by_instance, "S22_TCS_DEVELOPMENT_INTERNAL_PAPER_A", system),
        "s22_infy_live_result.json": _instance_live_result(by_instance, "S22_INFY_DEVELOPMENT_INTERNAL_PAPER_A", system),
        "s23_live_result.json": _instance_live_result(by_instance, "S23_NIFTY_INTERNAL_PAPER_A", system),
    }

    gaps = _gap_register(
        by_instance=by_instance,
        analytics=analytics,
        performance_metrics=performance_metrics,
        readiness=readiness,
        supervisor_gap_register=supervisor_gap_register,
        system=system,
    )
    verdict = _milestone_verdict(gaps)

    files: dict[str, Any] = {
        "source_level_runtime_audit.json": source_audit,
        "authentication_diagnostics.json": dict(authentication_diagnostics or {}),
        "session_reconstruction.json": session_reconstruction,
        "market_data_ownership.json": market_data_ownership,
        "monthly_status_results.json": monthly_status_results,
        "contract_selection_audit.json": contract_selection_audit,
        "orpt_rc_results.json": orpt_rc_results,
        "entry_eligibility.json": entry_eligibility,
        "internal_paper_orders.json": internal_paper_orders,
        "fill_model_results.json": fill_model_results,
        "positions_and_protection.json": positions_and_protection,
        "account_risk_results.json": account_risk_results,
        "accounting_pnl.json": accounting_pnl,
        "dashboard_live_projection.json": dashboard_live_projection,
        "persistence_integrity.json": persistence_integrity,
        "performance_profile.json": performance_profile,
        "restart_idempotency.json": restart_idempotency,
        "authority_boundary.json": authority_boundary,
        "gap_register.json": gaps,
    } | instance_files

    for name, payload in files.items():
        (report_root / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary_path = report_root / "live_market_internal_paper_summary.md"
    summary_path.write_text(
        _summary_markdown(
            verdict=verdict,
            system=system,
            readiness=readiness,
            by_instance=by_instance,
            gaps=gaps,
            auth=dict(authentication_diagnostics or {}),
            performance=performance_metrics,
        ),
        encoding="utf-8",
    )
    return LiveMarketInternalPaperReportResult(
        verdict=verdict,
        report_dir=report_root,
        summary_path=summary_path,
        files=tuple(sorted([*files.keys(), summary_path.name])),
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_level_runtime_audit(by_instance: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for instance_id, payload in by_instance.items():
        evidence_quality = str(payload["state"].get("evidence_quality") or payload["plan"].get("evidence_quality") or "UNKNOWN")
        stage_classification = _classify_evidence(evidence_quality)
        for stage in ("MONTHLY_STATUS", "BRANCH", "CONTRACT_SELECTION", "PLAN_COMPOSITION", "ENTRY_ELIGIBILITY", "CURRENT_ACTION"):
            fact = next((item for item in payload["decision_explanations"] if item.get("stage") == stage), None)
            rows.append(
                {
                    "strategy_instance_id": instance_id,
                    "stage": stage,
                    "classification": stage_classification,
                    "workbook_source": (fact or {}).get("workbook_source"),
                    "rule_id": (fact or {}).get("rule_id"),
                    "evidence_quality": evidence_quality,
                    "source_review_status": "SOURCE_REVIEWED" if fact else "NOT_REVIEWED",
                }
            )
    return {
        "schema_version": "tfis.live_market_internal_paper.source_level_runtime_audit.v1",
        "rows": rows,
        "audit_hash": canonical_hash(rows),
    }


def _monthly_status_results(by_instance: Mapping[str, Mapping[str, Any]], system: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for instance_id, payload in by_instance.items():
        fact = next((item for item in payload["decision_explanations"] if item.get("stage") == "MONTHLY_STATUS"), {})
        derivation = ((fact.get("candidate_evidence") or {}).get("derivation") or {}) if isinstance(fact, Mapping) else {}
        rows.append(
            {
                "strategy_instance_id": instance_id,
                "instrument": payload["identity"].get("instrument"),
                "trading_date": system.get("trading_date"),
                "monthly_status": payload["state"].get("monthly_status"),
                "monthly_status_label": payload["state"].get("monthly_status_label"),
                "workbook_source": fact.get("workbook_source"),
                "rule_id": fact.get("rule_id"),
                "formula_text": fact.get("formula_text"),
                "input_values": fact.get("input_values"),
                "output_value": fact.get("output_value"),
                "derivation": derivation,
                "explanation_steps": derivation.get("steps") or [],
                "evidence_quality": payload["state"].get("evidence_quality"),
            }
        )
    return {
        "schema_version": "tfis.live_market_internal_paper.monthly_status_results.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "results": rows,
    }


def _stage_results(by_instance: Mapping[str, Mapping[str, Any]], *, stage: str, system: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for instance_id, payload in by_instance.items():
        fact = next((item for item in payload["decision_explanations"] if item.get("stage") == stage), {})
        rows.append(
            {
                "strategy_instance_id": instance_id,
                "instrument": payload["identity"].get("instrument"),
                "stage": stage,
                "selected_contract": payload["plan"].get("selected_contract"),
                "selected_expiry": payload["plan"].get("selected_expiry"),
                "selected_option_type": payload["plan"].get("selected_option_type"),
                "selected_strike": payload["plan"].get("selected_strike"),
                "premium": payload["plan"].get("premium"),
                "oi": payload["plan"].get("oi"),
                "rule_id": fact.get("rule_id"),
                "formula_text": fact.get("formula_text"),
                "candidate_evidence": fact.get("candidate_evidence"),
                "rejection_reason": fact.get("rejection_reason"),
                "evidence_quality": payload["state"].get("evidence_quality"),
            }
        )
    return {
        "schema_version": f"tfis.live_market_internal_paper.{stage.lower()}.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "rows": rows,
    }


def _orpt_rc_results(by_instance: Mapping[str, Mapping[str, Any]], system: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for instance_id, payload in by_instance.items():
        rows.append(
            {
                "strategy_instance_id": instance_id,
                "instrument": payload["identity"].get("instrument"),
                "orpt": payload["plan"].get("orpt"),
                "rc": payload["plan"].get("rc"),
                "orpt_state": payload["execution"].get("orpt_state"),
                "rc_state": payload["execution"].get("rc_state"),
                "opening_context": payload["execution"].get("opening_context"),
                "runtime_stage": payload["state"].get("runtime_stage"),
                "evidence_quality": payload["state"].get("evidence_quality"),
            }
        )
    return {
        "schema_version": "tfis.live_market_internal_paper.orpt_rc_results.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "rows": rows,
    }


def _entry_eligibility(by_instance: Mapping[str, Mapping[str, Any]], system: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for instance_id, payload in by_instance.items():
        fact = next((item for item in payload["decision_explanations"] if item.get("stage") == "ENTRY_ELIGIBILITY"), {})
        rows.append(
            {
                "strategy_instance_id": instance_id,
                "instrument": payload["identity"].get("instrument"),
                "entry_eligibility": payload["state"].get("entry_eligibility"),
                "entry_eligibility_label": payload["state"].get("entry_eligibility_label"),
                "current_action": payload["state"].get("current_action"),
                "base_entry": payload["plan"].get("base_entry"),
                "effective_entry": payload["execution"].get("effective_entry"),
                "rule_id": fact.get("rule_id"),
                "formula_text": fact.get("formula_text"),
                "candidate_evidence": fact.get("candidate_evidence"),
                "evidence_quality": payload["state"].get("evidence_quality"),
            }
        )
    return {
        "schema_version": "tfis.live_market_internal_paper.entry_eligibility.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "rows": rows,
    }


def _internal_paper_orders(orders: list[dict[str, Any]], system: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_market_internal_paper.internal_paper_orders.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "execution_mode": "Simulated Order - No Broker Submission",
        "broker_order_authority": system.get("broker_order_authority"),
        "rows": orders,
    }


def _fill_model_results(by_instance: Mapping[str, Mapping[str, Any]], system: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for instance_id, payload in by_instance.items():
        execution = payload["execution"]
        order_row = payload["order_row"]
        rows.append(
            {
                "strategy_instance_id": instance_id,
                "instrument": payload["identity"].get("instrument"),
                "fill_mode_label": execution.get("mode_label") or "Simulated Fill - No Broker Confirmation",
                "order_state": execution.get("order_state"),
                "fill_state": execution.get("fill_state"),
                "filled_quantity": execution.get("filled_quantity"),
                "latest_event": execution.get("latest_event"),
                "order_row": order_row,
            }
        )
    return {
        "schema_version": "tfis.live_market_internal_paper.fill_model_results.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "rows": rows,
    }


def _positions_and_protection(positions: list[dict[str, Any]], system: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_market_internal_paper.positions_and_protection.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "position_label": "Internal-Paper Position Open",
        "rows": positions,
    }


def _account_risk_results(
    accounts: list[dict[str, Any]],
    analytics: Mapping[str, Any],
    account_risk_matrix: Mapping[str, Any],
    by_instance: Mapping[str, Mapping[str, Any]],
    system: Mapping[str, Any],
) -> dict[str, Any]:
    stale_conflicts: list[dict[str, Any]] = []
    matrix = (analytics.get("account_risk_matrix") or {}) if isinstance(analytics, Mapping) else {}
    for instance_id, payload in by_instance.items():
        matrix_row = matrix.get(instance_id) or {}
        runtime_risk = payload["execution"].get("risk_result")
        matrix_decision = matrix_row.get("decision")
        if runtime_risk == "ACCEPTED" and matrix_decision == "BLOCKED_ACCOUNT":
            stale_conflicts.append(
                {
                    "strategy_instance_id": instance_id,
                    "runtime_risk_result": runtime_risk,
                    "analytics_matrix_decision": matrix_decision,
                }
            )
    return {
        "schema_version": "tfis.live_market_internal_paper.account_risk_results.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "accounts": accounts,
        "analytics_account_risk_matrix": matrix,
        "supervisor_account_risk_matrix": account_risk_matrix,
        "stale_projection_conflicts": stale_conflicts,
    }


def _accounting_pnl(
    accounts: list[dict[str, Any]],
    analytics: Mapping[str, Any],
    positions: list[dict[str, Any]],
    by_instance: Mapping[str, Mapping[str, Any]],
    system: Mapping[str, Any],
) -> dict[str, Any]:
    rows = []
    for instance_id, payload in by_instance.items():
        rows.append(
            {
                "strategy_instance_id": instance_id,
                "instrument": payload["identity"].get("instrument"),
                "configured_lots": payload["identity"].get("configured_lots"),
                "lot_size": payload["identity"].get("lot_size"),
                "quantity": payload["position"].get("quantity"),
                "average_entry": payload["position"].get("average_entry"),
                "mark": payload["position"].get("mark"),
                "target": payload["position"].get("target"),
                "active_protection": payload["position"].get("active_protection"),
                "realized_pnl": payload["accounting"].get("realized_pnl"),
                "unrealized_pnl": payload["accounting"].get("unrealized_pnl"),
            }
        )
    return {
        "schema_version": "tfis.live_market_internal_paper.accounting_pnl.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "rows": rows,
        "accounts": accounts,
        "analytics": analytics,
        "positions": positions,
    }


def _authority_boundary(
    system: Mapping[str, Any],
    authentication_diagnostics: Mapping[str, Any] | None,
    readiness: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_market_internal_paper.authority_boundary.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "execution_mode": "Live Market Internal Paper",
        "broker_order_authority": system.get("broker_order_authority"),
        "external_order_submission": system.get("external_order_submission"),
        "tfis_execution_authority": system.get("tfis_execution_authority"),
        "authentication_diagnostics": dict(authentication_diagnostics or {}),
        "preflight": preflight,
        "readiness_projection": readiness,
    }


def _persistence_integrity(validation_summary: Mapping[str, Any], checkpoint_resume: Mapping[str, Any], system: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_market_internal_paper.persistence_integrity.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "db_integrity": validation_summary.get("db_integrity"),
        "recovery": validation_summary.get("recovery"),
        "checkpoint_resume_contract": checkpoint_resume,
    }


def _performance_profile(performance_metrics: Mapping[str, Any], scheduler_contract: Mapping[str, Any], system: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_market_internal_paper.performance_profile.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "scheduler_contract": scheduler_contract,
        "performance_metrics": performance_metrics,
        "hot_path_blocker": _find_hot_path_blocker(performance_metrics),
    }


def _restart_idempotency(
    validation_summary: Mapping[str, Any],
    checkpoint_resume: Mapping[str, Any],
    late_start_safety: Mapping[str, Any],
    failure_isolation: Mapping[str, Any],
    system: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_market_internal_paper.restart_idempotency.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "checkpoint_resume": checkpoint_resume,
        "late_start_safety": late_start_safety,
        "failure_isolation": failure_isolation,
        "validation_summary": validation_summary,
    }


def _market_data_ownership(subscription_state: Mapping[str, Any], routing: Mapping[str, Any], system: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_market_internal_paper.market_data_ownership.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "subscription_owner_state": subscription_state,
        "routing": routing,
    }


def _session_reconstruction(
    late_start_safety: Mapping[str, Any],
    routing: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    system: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_market_internal_paper.session_reconstruction.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "supervisor_state": system.get("supervisor_state"),
        "late_start_safety": late_start_safety,
        "timeline_events": routing.get("timeline_events") or [],
        "system": system,
        "projection_hash": snapshot.get("projection_hash"),
    }


def _instance_live_result(by_instance: Mapping[str, Mapping[str, Any]], instance_id: str, system: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(by_instance.get(instance_id) or {})
    if not payload:
        return {
            "schema_version": "tfis.live_market_internal_paper.instance_result.v1",
            "strategy_instance_id": instance_id,
            "status": "MISSING",
        }
    return {
        "schema_version": "tfis.live_market_internal_paper.instance_result.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "strategy_instance_id": instance_id,
        **payload,
    }


def _gap_register(
    *,
    by_instance: Mapping[str, Mapping[str, Any]],
    analytics: Mapping[str, Any],
    performance_metrics: Mapping[str, Any],
    readiness: Mapping[str, Any],
    supervisor_gap_register: Mapping[str, Any],
    system: Mapping[str, Any],
) -> dict[str, Any]:
    gaps: list[dict[str, Any]] = []
    for gap in supervisor_gap_register.get("gaps") or []:
        if isinstance(gap, Mapping):
            gaps.append(dict(gap))

    matrix = (analytics.get("account_risk_matrix") or {}) if isinstance(analytics, Mapping) else {}
    for instance_id, payload in by_instance.items():
        matrix_row = matrix.get(instance_id) or {}
        if payload["execution"].get("risk_result") == "ACCEPTED" and matrix_row.get("decision") == "BLOCKED_ACCOUNT":
            gaps.append(
                {
                    "gap_id": f"LIVE-IP-GAP-RISK-{instance_id}",
                    "severity": "HIGH",
                    "file": "src/tfis/read_models/operations/projection.py",
                    "function": "build_unified_dashboard_projection",
                    "impact": "Dashboard analytics still reports stale BLOCKED_ACCOUNT while runtime execution state is ACCEPTED.",
                }
            )

    blocker = _find_hot_path_blocker(performance_metrics)
    if blocker:
        gaps.append(
            {
                "gap_id": "LIVE-IP-GAP-PERF-001",
                "severity": "HIGH",
                "file": "src/tfis/runtime/multi_strategy/supervisor.py",
                "function": "UnifiedInternalPaperSupervisor._run_once",
                "impact": blocker,
            }
        )

    for reason in readiness.get("blocking_reasons") or []:
        gaps.append(
            {
                "gap_id": f"LIVE-IP-GAP-READINESS-{len(gaps) + 1:03d}",
                "severity": "MEDIUM",
                "file": "reports/unified_readiness/authoritative_readiness_projection.json",
                "function": "authoritative_readiness_projection",
                "impact": str(reason),
            }
        )

    for instance_id in by_instance:
        if "DEVELOPMENT" in instance_id:
            gaps.append(
                {
                    "gap_id": f"LIVE-IP-GAP-NAMING-{instance_id}",
                    "severity": "LOW",
                    "file": "config/live_market_internal_paper_strategy_instances.yaml",
                    "function": "registry_instance_id",
                    "impact": "Stage-1 live-market profile still carries DEVELOPMENT naming for approved TCS/INFY internal-paper instances.",
                }
            )

    return {
        "schema_version": "tfis.live_market_internal_paper.gap_register.v1",
        "captured_at": system.get("source_timestamp") or system.get("generated_at"),
        "gaps": gaps,
    }


def _classify_evidence(evidence_quality: str) -> str:
    if "FIXTURE" in evidence_quality:
        return "FIXTURE_ONLY"
    if "HISTORY" in evidence_quality or "RECONSTRUCT" in evidence_quality:
        return "HISTORICALLY_RECONSTRUCTED"
    if "LIVE" in evidence_quality:
        return "LIVE_EVIDENCE_PROVEN"
    return "TEST_PROVEN"


def _find_hot_path_blocker(performance_metrics: Mapping[str, Any]) -> str | None:
    current_cycle = performance_metrics.get("current_cycle") or {}
    stage_metrics = current_cycle.get("stage_metrics") or []
    slow_symbol_master = next(
        (
            item for item in stage_metrics
            if isinstance(item, Mapping)
            and item.get("stage") == "provider_symbol_master_nsefo"
            and float(item.get("duration_ms") or 0.0) > 10000.0
        ),
        None,
    )
    if slow_symbol_master:
        return (
            "NSEFO symbol master fetch consumed "
            f"{slow_symbol_master.get('duration_ms')} ms inside the live supervisor cycle, which keeps the hot path well above the configured poll cadence."
        )
    return None


def _milestone_verdict(gaps: Mapping[str, Any]) -> str:
    severities = {str(item.get("severity") or "LOW") for item in (gaps.get("gaps") or []) if isinstance(item, Mapping)}
    if "CRITICAL" in severities:
        return "LIVE_MARKET_INTERNAL_PAPER_BLOCKED"
    if "HIGH" in severities:
        return "LIVE_MARKET_INTERNAL_PAPER_CONDITIONAL"
    return "LIVE_MARKET_INTERNAL_PAPER_ACCEPT"


def _summary_markdown(
    *,
    verdict: str,
    system: Mapping[str, Any],
    readiness: Mapping[str, Any],
    by_instance: Mapping[str, Mapping[str, Any]],
    gaps: Mapping[str, Any],
    auth: Mapping[str, Any],
    performance: Mapping[str, Any],
) -> str:
    lines = [
        "# Live Market Internal Paper Summary",
        "",
        f"- Verdict: `{verdict}`",
        f"- Session: `{system.get('session')}`",
        f"- Session Id: `{system.get('session_id')}`",
        f"- Source Timestamp: `{system.get('source_timestamp')}`",
        f"- Supervisor State: `{system.get('supervisor_state')}`",
        f"- Broker Order Authority: `{system.get('broker_order_authority')}`",
        f"- FYERS Authentication: `{auth.get('authentication_status') or auth.get('status') or 'UNKNOWN'}`",
        f"- Readiness Projection Verdict: `{readiness.get('verdict')}`",
        "",
        "## Instance Summary",
        "",
    ]
    for instance_id, payload in by_instance.items():
        lines.append(
            f"- `{instance_id}`: `{payload['identity'].get('instrument')}` / "
            f"`{payload['state'].get('monthly_status')}` / `{payload['state'].get('branch')}` / "
            f"`{payload['plan'].get('selected_contract')}` / `{payload['state'].get('entry_eligibility_label')}`"
        )
    lines.extend(["", "## Performance", ""])
    current_cycle = performance.get("current_cycle") or {}
    lines.append(f"- Cycle Duration Ms: `{current_cycle.get('cycle_duration_ms')}`")
    lines.append(f"- Poll Seconds: `{current_cycle.get('poll_seconds')}`")
    if performance.get("consecutive_overruns") is not None:
        lines.append(f"- Consecutive Overruns: `{performance.get('consecutive_overruns')}`")
    lines.extend(["", "## Exact Gaps", ""])
    for gap in gaps.get("gaps") or []:
        if isinstance(gap, Mapping):
            lines.append(f"- `{gap.get('gap_id')}` [{gap.get('severity', 'LOW')}]: {gap.get('impact')}")
    lines.append("")
    return "\n".join(lines)
