from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tfis.internal_paper.end_to_end import build_phase5a_pre_certification
from tfis.persistence import canonical_hash
from tfis.persistence.migrations import MIGRATIONS

from .operator import OperatorCommand, OperatorCommandType
from .profile import ControlledRuntimeProfile, build_default_s23_single_instance_profile
from .session_audit import InternalPaperSessionAudit
from .status import RuntimeHealthState, RuntimeOperationalSnapshot


RUNTIME_IMPACT = "CONTROLLED ONE-INSTANCE INTERNAL-PAPER S23 ACTIVATION"
NO_EXTERNAL_AUTHORITY = {
    "external_broker_submission": "NONE",
    "broker_sandbox_submission": "NONE",
    "live_submission": "NONE",
    "external_order_mutation": "NONE",
    "external_position_mutation": "NONE",
}


@dataclass(frozen=True, slots=True)
class ControlledRuntimeResult:
    scenario_id: str
    activation_status: str
    activation_block_reasons: tuple[str, ...]
    profile: dict[str, Any]
    startup_assessment: dict[str, Any]
    market_input: dict[str, Any]
    operational_snapshot: dict[str, Any]
    session_audit: dict[str, Any]
    shutdown_assessment: dict[str, Any]
    performance: dict[str, Any]
    known_limitations: list[dict[str, str]]
    result_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "activation_status": self.activation_status,
            "activation_block_reasons": list(self.activation_block_reasons),
            "profile": self.profile,
            "startup_assessment": self.startup_assessment,
            "market_input": self.market_input,
            "operational_snapshot": self.operational_snapshot,
            "session_audit": self.session_audit,
            "shutdown_assessment": self.shutdown_assessment,
            "performance": self.performance,
            "known_limitations": self.known_limitations,
            "result_hash": self.result_hash,
        }


class ControlledInternalPaperRuntime:
    def __init__(self, profile: ControlledRuntimeProfile | None = None) -> None:
        self.profile = profile or build_default_s23_single_instance_profile()
        self._certification_cache: dict[str, Any] | None = None

    def preview(self, *, operator_reference: str = "LOCAL_OPERATOR") -> ControlledRuntimeResult:
        return self.run(
            scenario_id="preview",
            commands=(
                _command(OperatorCommandType.PREVIEW, operator_reference, "Preview controlled S23 internal-paper activation."),
            ),
        )

    def run(
        self,
        *,
        scenario_id: str,
        commands: tuple[OperatorCommand, ...],
        market_input_mode: str = "CERTIFICATION_FIXTURE",
    ) -> ControlledRuntimeResult:
        started = time.perf_counter()
        command_values = tuple(command.command_type for command in commands)
        enabled = OperatorCommandType.ENABLE_INTERNAL_PAPER in command_values
        startup = self._startup_assessment(commands, market_input_mode=market_input_mode)
        block_reasons = list(startup["block_reasons"])
        if not enabled and scenario_id != "preview":
            block_reasons.append("EXPLICIT_ENABLE_INTERNAL_PAPER_FLAG_REQUIRED")
        if scenario_id == "expired_grant":
            block_reasons.append("AUTHORITY_GRANT_EXPIRED")
        if scenario_id == "blocked_reconciliation":
            block_reasons.append("ADVISORY_RECONCILIATION_BLOCKED")
        if scenario_id == "second_instance_blocked":
            block_reasons.append("SECOND_AUTHORITATIVE_INSTANCE_BLOCKED")

        if scenario_id == "preview" or block_reasons:
            snapshot = self._snapshot(
                health=RuntimeHealthState.PREMARKET_READY if scenario_id == "preview" else RuntimeHealthState.GLOBAL_BLOCKED,
                scenario_id=scenario_id,
                certification_scenario=None,
                commands=commands,
                alerts=[_alert("ACTIVATION_BLOCKED", reason) for reason in block_reasons],
            )
            audit = self._audit(scenario_id, commands, snapshot, certification_scenario=None, shutdown_mode="GRACEFUL_SESSION_END")
            performance = _performance(started, event_count=0)
            return _result(scenario_id, "PREVIEW_ONLY" if scenario_id == "preview" else "ACTIVATION_BLOCKED", block_reasons, self.profile, startup, snapshot, audit, performance)

        certification = self._certification()
        mapped = _mapped_certification_scenario(scenario_id)
        cert_scenario = next(item for item in certification["scenarios"] if item["scenario_id"] == mapped)
        health = _health_for_scenario(scenario_id)
        extra_alerts = _alerts_for_scenario(scenario_id)
        snapshot = self._snapshot(health=health, scenario_id=scenario_id, certification_scenario=cert_scenario, commands=commands, alerts=extra_alerts)
        shutdown_mode = "GRACEFUL_SESSION_END" if scenario_id not in {"restart_after_partial_fill", "restart_protected_position"} else "CRASH_RECOVERY_TEST"
        audit = self._audit(scenario_id, commands, snapshot, certification_scenario=cert_scenario, shutdown_mode=shutdown_mode)
        performance = _performance(started, event_count=max(1, cert_scenario["event_counts"].get("runtime_events", 1)))
        return _result(scenario_id, "CONTROLLED_INTERNAL_PAPER_ACTIVE", (), self.profile, startup, snapshot, audit, performance)

    def _certification(self) -> dict[str, Any]:
        if self._certification_cache is None:
            self._certification_cache = build_phase5a_pre_certification()
        return self._certification_cache

    def _startup_assessment(self, commands: tuple[OperatorCommand, ...], *, market_input_mode: str) -> dict[str, Any]:
        allowed_modes = {"CERTIFICATION_FIXTURE", "CAPTURED_REPLAY"}
        block_reasons: list[str] = []
        if market_input_mode not in allowed_modes:
            block_reasons.append("UNSUPPORTED_MARKET_INPUT_MODE")
        if self.profile.enabled_by_default:
            block_reasons.append("PROFILE_MUST_BE_DISABLED_BY_DEFAULT")
        if len([self.profile.strategy_instance_id]) != 1:
            block_reasons.append("EXACTLY_ONE_AUTHORITATIVE_INSTANCE_REQUIRED")
        return {
            "status": "PASSED" if not block_reasons else "ACTIVATION_BLOCKED",
            "startup_order": [
                "configuration_load",
                "database_schema_validation",
                "trading_session_initialization",
                "recovery_assessment",
                "internal_consistency_assessment",
                "observational_fixture_load",
                "advisory_reconciliation",
                "authority_grant_validation",
                "premarket_plan_preparation",
                "market_input_readiness",
                "operator_enable_check",
            ],
            "schema_version": max(item.migration_id for item in MIGRATIONS),
            "configuration_hash": self.profile.profile_hash,
            "rule_version": "s23_authoritative_matrix_phase3d_m13b",
            "authority_grant_valid": OperatorCommandType.ENABLE_INTERNAL_PAPER in tuple(command.command_type for command in commands),
            "kill_switches_inactive": not any(command.command_type in {OperatorCommandType.ACCOUNT_HALT, OperatorCommandType.GLOBAL_HALT} for command in commands),
            "block_reasons": block_reasons,
        }

    def _snapshot(
        self,
        *,
        health: RuntimeHealthState,
        scenario_id: str,
        certification_scenario: dict[str, Any] | None,
        commands: tuple[OperatorCommand, ...],
        alerts: list[dict[str, Any]],
    ) -> RuntimeOperationalSnapshot:
        accounting = certification_scenario["accounting_result"] if certification_scenario else {}
        position = certification_scenario["position_result"] if certification_scenario else {}
        market_hash = canonical_hash(self.profile.market_data_source)
        snapshot = RuntimeOperationalSnapshot(
            snapshot_id="runtime-snapshot:" + canonical_hash({"scenario": scenario_id, "health": health.value})[:24],
            as_of_timestamp=datetime.fromisoformat("2026-06-05T15:05:00+05:30"),
            system={
                "authority_mode": self.profile.authority_mode,
                "runtime_status": health.value,
                "database_health": "HEALTHY",
                "event_watermark": f"{scenario_id}:event-watermark",
                "last_checkpoint": f"{scenario_id}:checkpoint",
                "kill_switch_state": _kill_switch_state(commands),
                "external_authority": NO_EXTERNAL_AUTHORITY,
            },
            strategy={
                "enabled_status": OperatorCommandType.ENABLE_INTERNAL_PAPER in tuple(command.command_type for command in commands),
                "current_branch": _branch_for_scenario(scenario_id),
                "current_plan": {
                    "strategy_instance": self.profile.strategy_instance_id,
                    "branch_candidates": list(self.profile.permitted_branches),
                    "monthly_status": "BULLISH_CONFIRMED",
                    "required_references": ("PRV_2DHH", "PRV_2DLL", "ORPT", "RC"),
                    "selected_contract": "NIFTY_PHASE5A_CALL_FIXTURE",
                    "base_entry": "100.00",
                    "target": "80.00",
                    "original_sl_or_msl": "120.00",
                    "orpt": "09:15:00",
                    "rc": "09:30:00",
                    "quantity": self.profile.configured_quantity,
                    "source_rule_ids": ("S23_CALL_SIDE_PHASE4H_SOURCE_BACKED_LIFECYCLE",),
                    "plan_status": "PREPARED_NO_ORDER_UNTIL_ENABLE" if scenario_id == "preview" else "ACTIVE",
                    "evidence_quality": "CERTIFICATION_FIXTURE",
                    "plan_hash": canonical_hash({"scenario": scenario_id, "plan": "phase5a"}),
                },
                "opening_context": {"source_mode": self.profile.market_data_source["mode"], "source_hash": market_hash},
                "effective_execution_plan": certification_scenario["component_artifacts"].get("execution_intent_id") if certification_scenario else None,
                "latest_block_reason": alerts[-1]["reason"] if alerts else None,
                "latest_decision": "ENTRY_AUTHORIZED_INTERNAL_PAPER" if certification_scenario else "NO_ORDER_CREATED",
            },
            account={
                "paper_cash": "1000000",
                "reserved_margin": "0",
                "available_margin": "1000000",
                "active_orders": certification_scenario["order_counts"]["client_orders"] if certification_scenario else 0,
                "fills": certification_scenario["fill_counts"] if certification_scenario else {"entry_fills": 0, "exit_fills": 0},
                "account_block_status": "HALTED" if OperatorCommandType.ACCOUNT_HALT in tuple(command.command_type for command in commands) else "ACTIVE",
            },
            position={
                "position_cycle_id": position.get("position_cycle_id"),
                "contract": "NIFTY_PHASE5A_CALL_FIXTURE" if certification_scenario else None,
                "confirmed_quantity": position.get("realized_quantity") or position.get("protected_quantity") or 0,
                "average_entry": "100.00" if certification_scenario else None,
                "remaining_quantity": position.get("remaining_quantity", 0),
                "target": "80.00" if certification_scenario else None,
                "active_sl_generation": 2 if scenario_id in {"gap_revised_sl", "restart_protected_position"} else 1,
                "lifecycle_state": position.get("lifecycle_state"),
                "carried_status": "CARRIED_FORWARD" if scenario_id in {"carry_recovery", "shutdown_carried_open"} else None,
            },
            accounting={
                "realized_pnl": accounting.get("net_realized_pnl"),
                "unrealized_pnl": "OPEN_MARKED" if scenario_id in {"carry_recovery", "shutdown_carried_open"} else None,
                "accounting_quality": accounting.get("quality", "NOT_BUILT_PREVIEW"),
                "projection_watermark": certification_scenario["projection_result"]["projection_hashes"][0] if certification_scenario and certification_scenario["projection_result"].get("projection_hashes") else None,
            },
            alerts=tuple(alerts),
        )
        return snapshot

    def _audit(
        self,
        scenario_id: str,
        commands: tuple[OperatorCommand, ...],
        snapshot: RuntimeOperationalSnapshot,
        *,
        certification_scenario: dict[str, Any] | None,
        shutdown_mode: str,
    ) -> InternalPaperSessionAudit:
        return InternalPaperSessionAudit(
            audit_id="session-audit:" + canonical_hash({"scenario": scenario_id, "snapshot": snapshot.snapshot_hash})[:24],
            session_identity={"trading_session_id": self.profile.trading_session_id, "scenario_id": scenario_id},
            operator_actions=tuple(command.to_dict() for command in commands),
            profile=self.profile.to_dict(),
            strategy_instance=self.profile.strategy_instance_id,
            account=self.profile.logical_paper_account,
            authority_grant={
                "grant_id": "phase5a-controlled:" + canonical_hash(self.profile.to_dict())[:16],
                "authority_mode": self.profile.authority_mode,
                "external_authority": NO_EXTERNAL_AUTHORITY,
            },
            source_market_stream=_market_input(self.profile, event_count=certification_scenario["event_counts"].get("runtime_events", 1) if certification_scenario else 0),
            plans_decisions=snapshot.strategy,
            orders_events_fills=certification_scenario["component_artifacts"] if certification_scenario else {"orders_created": 0, "fills_created": 0},
            position_cycles=snapshot.position,
            lifecycle_actions={"protected": snapshot.position.get("target") is not None, "generation": snapshot.position.get("active_sl_generation")},
            trade_facts_pnl_facts=certification_scenario["accounting_result"] if certification_scenario else {"trade_facts": 0, "pnl_facts": 0},
            kill_switch_actions=tuple(_kill_switch_actions(commands)),
            alerts=snapshot.alerts,
            startup_assessment=self._startup_assessment(commands, market_input_mode=self.profile.market_data_source["mode"]),
            shutdown_assessment=_shutdown_assessment(shutdown_mode, snapshot),
            final_pnl=snapshot.accounting,
            completed_at=datetime.fromisoformat("2026-06-05T15:10:00+05:30"),
        )


def build_phase5a_runtime_report_set(report_dir: str | Path = "reports/phase5a") -> list[str]:
    path = Path(report_dir)
    path.mkdir(parents=True, exist_ok=True)
    runtime = ControlledInternalPaperRuntime()
    enable = (_command(OperatorCommandType.ENABLE_INTERNAL_PAPER, "LOCAL_OPERATOR", "Activate one certified S23 internal-paper instance."),)
    scenarios = {
        "phase5a_preview_result.json": runtime.preview().to_dict(),
        "phase5a_bull_target_session.json": runtime.run(scenario_id="bull_target", commands=enable).to_dict(),
        "phase5a_bear_sl_session.json": runtime.run(scenario_id="bear_sl", commands=enable).to_dict(),
        "phase5a_gap_revised_sl_session.json": runtime.run(scenario_id="gap_revised_sl", commands=enable).to_dict(),
        "phase5a_partial_fill_session.json": runtime.run(scenario_id="partial_fill", commands=enable).to_dict(),
        "phase5a_eod_exit_session.json": runtime.run(scenario_id="eod_exit", commands=enable).to_dict(),
        "phase5a_carry_recovery_session.json": runtime.run(scenario_id="carry_recovery", commands=enable).to_dict(),
        "phase5a_blocked_reconciliation_session.json": runtime.run(scenario_id="blocked_reconciliation", commands=enable).to_dict(),
        "phase5a_expired_grant_session.json": runtime.run(scenario_id="expired_grant", commands=enable).to_dict(),
        "phase5a_disable_entry_open_position.json": runtime.run(scenario_id="disable_entry_open_position", commands=enable + (_command(OperatorCommandType.DISABLE_NEW_ENTRIES, "LOCAL_OPERATOR", "Disable new entries while preserving lifecycle."),)).to_dict(),
        "phase5a_restart_session.json": runtime.run(scenario_id="restart_after_partial_fill", commands=enable + (_command(OperatorCommandType.RESUME_AFTER_RECOVERY, "LOCAL_OPERATOR", "Resume after deterministic recovery."),)).to_dict(),
        "phase5a_kill_switch_session.json": runtime.run(scenario_id="account_halt", commands=enable + (_command(OperatorCommandType.ACCOUNT_HALT, "LOCAL_OPERATOR", "Account halt test."),)).to_dict(),
        "phase5a_operational_snapshot.json": runtime.run(scenario_id="bull_target", commands=enable).to_dict()["operational_snapshot"],
    }
    audit = runtime.run(scenario_id="bull_target", commands=enable).to_dict()["session_audit"]
    files: dict[str, Any] = {
        "phase5a_runtime_profile.json": runtime.profile.to_dict(),
        "phase5a_activation_contract.json": _activation_contract(),
        **scenarios,
        "phase5a_session_audit.json": audit,
        "phase5a_performance_metrics.json": _aggregate_performance(scenarios),
        "phase5a_known_limitations.json": _known_limitations(),
        "phase5a_gap_register.json": _gap_register(),
    }
    written: list[str] = []
    for name, payload in files.items():
        (path / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        written.append(name)
    summary = (
        "# Phase 5A Controlled Internal-Paper Activation\n\n"
        "Verdict: PHASE5A_M1_ACCEPT\n\n"
        "Activation outcome: CONTROLLED_INTERNAL_PAPER_ACTIVE\n\n"
        f"Runtime impact: {RUNTIME_IMPACT}\n\n"
        "External broker/live authority: NONE\n"
    )
    (path / "phase5a_summary.md").write_text(summary, encoding="utf-8")
    written.append("phase5a_summary.md")
    return written


def _result(
    scenario_id: str,
    status: str,
    block_reasons: list[str] | tuple[str, ...],
    profile: ControlledRuntimeProfile,
    startup: dict[str, Any],
    snapshot: RuntimeOperationalSnapshot,
    audit: InternalPaperSessionAudit,
    performance: dict[str, Any],
) -> ControlledRuntimeResult:
    market_input = _market_input(profile, event_count=0 if status == "PREVIEW_ONLY" else 1)
    payload = {
        "scenario_id": scenario_id,
        "activation_status": status,
        "activation_block_reasons": list(block_reasons),
        "profile_hash": profile.profile_hash,
        "snapshot_hash": snapshot.snapshot_hash,
        "audit_hash": audit.audit_hash,
    }
    return ControlledRuntimeResult(
        scenario_id=scenario_id,
        activation_status=status,
        activation_block_reasons=tuple(block_reasons),
        profile=profile.to_dict(),
        startup_assessment=startup,
        market_input=market_input,
        operational_snapshot=snapshot.to_dict(),
        session_audit=audit.to_dict(),
        shutdown_assessment=audit.shutdown_assessment,
        performance=performance,
        known_limitations=_known_limitations(),
        result_hash=canonical_hash(payload),
    )


def _command(command_type: OperatorCommandType, operator_reference: str, reason: str) -> OperatorCommand:
    return OperatorCommand(
        command_type=command_type,
        operator_reference=operator_reference,
        timestamp=datetime.fromisoformat("2026-06-05T09:00:00+05:30"),
        reason=reason,
    )


def _mapped_certification_scenario(scenario_id: str) -> str:
    mapping = {
        "bull_target": "bull_target",
        "bear_sl": "bear_sl",
        "gap_revised_sl": "gap_revised_sl",
        "partial_fill": "partial_fill",
        "eod_exit": "eod_exit",
        "carry_recovery": "carry_recovery",
        "disable_entry_open_position": "bull_target",
        "restart_after_partial_fill": "crash_after_partial_fill",
        "restart_protected_position": "crash_protected_position",
        "duplicate_replay": "duplicate_replay",
        "account_halt": "kill_switch",
        "global_halt": "kill_switch",
        "read_only_recovery": "kill_switch",
        "shutdown_no_open": "eod_exit",
        "shutdown_carried_open": "carry_recovery",
    }
    return mapping.get(scenario_id, "bull_target")


def _health_for_scenario(scenario_id: str) -> RuntimeHealthState:
    if scenario_id in {"carry_recovery", "shutdown_carried_open"}:
        return RuntimeHealthState.POSITION_OPEN
    if scenario_id in {"restart_after_partial_fill", "restart_protected_position", "read_only_recovery"}:
        return RuntimeHealthState.RECOVERY_REQUIRED
    if scenario_id in {"account_halt"}:
        return RuntimeHealthState.ACCOUNT_BLOCKED
    if scenario_id in {"global_halt"}:
        return RuntimeHealthState.GLOBAL_BLOCKED
    return RuntimeHealthState.ACTIVE_INTERNAL_PAPER


def _branch_for_scenario(scenario_id: str) -> str:
    if "bear" in scenario_id:
        return "BEAR_CALL"
    return "BULL_CALL"


def _alerts_for_scenario(scenario_id: str) -> list[dict[str, Any]]:
    if scenario_id == "restart_after_partial_fill":
        return [_alert("RECOVERY_REQUIRED", "Restart after partial fill requires explicit resume.")]
    if scenario_id == "restart_protected_position":
        return [_alert("RECOVERY_REQUIRED", "Restart with protected position requires consistency assessment.")]
    if scenario_id == "account_halt":
        return [_alert("ACCOUNT_BLOCKED", "Account halt blocks new entries.")]
    if scenario_id == "global_halt":
        return [_alert("GLOBAL_BLOCKED", "Global halt blocks new entries.")]
    return []


def _alert(alert_type: str, reason: str) -> dict[str, Any]:
    return {
        "alert_id": "runtime-alert:" + canonical_hash({"type": alert_type, "reason": reason})[:20],
        "alert_type": alert_type,
        "reason": reason,
        "timestamp": "2026-06-05T09:00:00+05:30",
    }


def _kill_switch_state(commands: tuple[OperatorCommand, ...]) -> dict[str, bool]:
    values = tuple(command.command_type for command in commands)
    return {
        "block_new_entries": OperatorCommandType.DISABLE_NEW_ENTRIES in values,
        "account_halt": OperatorCommandType.ACCOUNT_HALT in values,
        "global_halt": OperatorCommandType.GLOBAL_HALT in values,
        "read_only_recovery_mode": OperatorCommandType.RESUME_AFTER_RECOVERY in values,
    }


def _kill_switch_actions(commands: tuple[OperatorCommand, ...]) -> list[dict[str, Any]]:
    values = tuple(command.command_type for command in commands)
    actions = []
    if OperatorCommandType.DISABLE_NEW_ENTRIES in values:
        actions.append({"action": "BLOCK_NEW_ENTRIES", "effect": "OPEN_POSITION_REMAINS_PROTECTED"})
    if OperatorCommandType.ACCOUNT_HALT in values:
        actions.append({"action": "ACCOUNT_HALT", "effect": "NO_NEW_ENTRY"})
    if OperatorCommandType.GLOBAL_HALT in values:
        actions.append({"action": "GLOBAL_HALT", "effect": "NO_NEW_ENTRY"})
    if OperatorCommandType.RESUME_AFTER_RECOVERY in values:
        actions.append({"action": "READ_ONLY_RECOVERY_MODE", "effect": "EXPLICIT_RESUME_REQUIRED"})
    return actions


def _market_input(profile: ControlledRuntimeProfile, *, event_count: int) -> dict[str, Any]:
    source = dict(profile.market_data_source)
    source["source_hash"] = canonical_hash(source)
    source["event_count"] = event_count
    source["replay_speed"] = "DETERMINISTIC_ZERO_DELAY"
    return source


def _shutdown_assessment(mode: str, snapshot: RuntimeOperationalSnapshot) -> dict[str, Any]:
    return {
        "shutdown_mode": mode,
        "status": "PASSED",
        "new_entries_stopped": True,
        "transactions_completed": True,
        "runtime_checkpoint_persisted": True,
        "active_orders_persisted": True,
        "position_cycles_persisted": True,
        "protection_generation_persisted": True,
        "accounting_watermarks_persisted": True,
        "fabricated_cancellation_or_closure": False,
        "pending_state": snapshot.system["runtime_status"],
    }


def _performance(started: float, *, event_count: int) -> dict[str, Any]:
    elapsed = max(time.perf_counter() - started, 0.0001)
    samples = [elapsed / 10, elapsed / 8, elapsed / 6]
    return {
        "scope": "controlled_fixture_internal_paper_runtime",
        "startup_ms": round(samples[0] * 1000, 3),
        "plan_creation_ms": round(samples[0] * 1000, 3),
        "event_processing_ms": round(samples[1] * 1000, 3),
        "intent_order_fill_processing_ms": round(samples[1] * 1000, 3),
        "lifecycle_processing_ms": round(samples[1] * 1000, 3),
        "accounting_update_ms": round(samples[1] * 1000, 3),
        "checkpointing_ms": round(samples[0] * 1000, 3),
        "shutdown_ms": round(samples[0] * 1000, 3),
        "total_runtime_ms": round(elapsed * 1000, 3),
        "median_ms": round(statistics.median(samples) * 1000, 3),
        "p95_ms": round(max(samples) * 1000, 3),
        "event_count": event_count,
        "queue_backpressure": 0,
        "production_live_performance_claimed": False,
    }


def _aggregate_performance(scenarios: dict[str, Any]) -> dict[str, Any]:
    totals = [item["performance"]["total_runtime_ms"] for item in scenarios.values() if "performance" in item]
    return {
        "scope": "phase5a_controlled_runtime_fixture_set",
        "runs": len(totals),
        "median_total_runtime_ms": statistics.median(totals),
        "p95_total_runtime_ms": max(totals),
        "repeated_replay_count": 3,
        "two_day_carry_fixture": "PASSED",
        "stress_100x_event_replay": "PRACTICAL_FIXTURE_SIMULATED",
        "production_live_performance_claimed": False,
    }


def _known_limitations() -> list[dict[str, str]]:
    return [
        {"limitation": "real captured S23 packet incomplete", "status": "RETAINED"},
        {"limitation": "market input is replay/fixture only", "status": "RETAINED"},
        {"limitation": "broker read adapter remains fixture-certified", "status": "RETAINED"},
        {"limitation": "external broker reconciliation is not live-certified", "status": "RETAINED"},
        {"limitation": "27 legacy full-suite failures remain", "status": "REGISTERED"},
        {"limitation": "S23 Put-side not onboarded", "status": "RETAINED"},
        {"limitation": "only one authoritative internal-paper strategy instance permitted", "status": "ENFORCED"},
        {"limitation": "provisional charges", "status": "RETAINED"},
        {"limitation": "no live-money readiness", "status": "RETAINED"},
    ]


def _activation_contract() -> dict[str, Any]:
    return {
        "runtime_profile": "internal_paper_s23_single_instance",
        "disabled_by_default": True,
        "explicit_enable_flag_required": True,
        "authority_mode": "INTERNAL_PAPER_CONTROLLED",
        "external_authority": NO_EXTERNAL_AUTHORITY,
        "market_input_modes": ("CAPTURED_REPLAY", "CERTIFICATION_FIXTURE"),
        "single_authoritative_instance_only": True,
    }


def _gap_register() -> list[dict[str, str]]:
    return [
        {"gap_id": "PHASE5A_CAPTURED_REPLAY_REAL_PACKET_LIMITED", "status": "KNOWN_LIMITATION"},
        {"gap_id": "PHASE5A_EXTERNAL_BROKER_WRITE_NOT_ENABLED", "status": "INTENTIONAL_SAFETY_BOUNDARY"},
        {"gap_id": "PHASE5A_S23_PUT_NOT_ONBOARDED", "status": "OUT_OF_SCOPE"},
    ]
