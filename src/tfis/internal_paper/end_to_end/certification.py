from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tfis.persistence import canonical_hash


AUTHORITY_MODE = "INTERNAL_PAPER_CERTIFICATION_ONLY"


def _hash(data: dict[str, Any]) -> str:
    return canonical_hash(data)


@dataclass(frozen=True, slots=True)
class CertificationAuthority:
    authority_grant_id: str
    broker_account_id: str
    trading_session_id: str
    strategy_instance_id: str
    valid_scope: str = "S23_CALL_SIDE_INTERNAL_PAPER_CERTIFICATION"
    authority_mode: str = AUTHORITY_MODE
    external_broker_submission_permitted: bool = False
    broker_sandbox_submission_permitted: bool = False
    live_submission_permitted: bool = False
    external_order_mutation_permitted: bool = False
    external_position_mutation_permitted: bool = False
    reusable_as_live_authority: bool = False
    grant_hash: str = field(init=False)

    def __post_init__(self) -> None:
        flags = (
            self.external_broker_submission_permitted,
            self.broker_sandbox_submission_permitted,
            self.live_submission_permitted,
            self.external_order_mutation_permitted,
            self.external_position_mutation_permitted,
            self.reusable_as_live_authority,
        )
        if any(flags):
            raise ValueError("Phase 5A-Pre certification authority cannot permit external mutation.")
        object.__setattr__(self, "grant_hash", _hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "authority_grant_id": self.authority_grant_id,
            "broker_account_id": self.broker_account_id,
            "trading_session_id": self.trading_session_id,
            "strategy_instance_id": self.strategy_instance_id,
            "valid_scope": self.valid_scope,
            "authority_mode": self.authority_mode,
            "external_broker_submission_permitted": self.external_broker_submission_permitted,
            "broker_sandbox_submission_permitted": self.broker_sandbox_submission_permitted,
            "live_submission_permitted": self.live_submission_permitted,
            "external_order_mutation_permitted": self.external_order_mutation_permitted,
            "external_position_mutation_permitted": self.external_position_mutation_permitted,
            "reusable_as_live_authority": self.reusable_as_live_authority,
        }
        if include_hash:
            data["grant_hash"] = self.grant_hash
        return data


@dataclass(frozen=True, slots=True)
class CertificationScenarioResult:
    scenario_id: str
    status: str
    startup_sequence: tuple[str, ...]
    shutdown_sequence: tuple[str, ...]
    authority: CertificationAuthority
    component_artifacts: dict[str, Any]
    event_counts: dict[str, int]
    order_counts: dict[str, int]
    fill_counts: dict[str, int]
    position_result: dict[str, Any]
    accounting_result: dict[str, Any]
    projection_result: dict[str, Any]
    trace: list[dict[str, Any]]
    idempotency: dict[str, Any]
    warnings: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    scenario_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "startup_sequence", tuple(self.startup_sequence))
        object.__setattr__(self, "shutdown_sequence", tuple(self.shutdown_sequence))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "scenario_hash", _hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "scenario_id": self.scenario_id,
            "status": self.status,
            "startup_sequence": list(self.startup_sequence),
            "shutdown_sequence": list(self.shutdown_sequence),
            "authority": self.authority.to_dict(),
            "component_artifacts": self.component_artifacts,
            "event_counts": self.event_counts,
            "order_counts": self.order_counts,
            "fill_counts": self.fill_counts,
            "position_result": self.position_result,
            "accounting_result": self.accounting_result,
            "projection_result": self.projection_result,
            "trace": self.trace,
            "idempotency": self.idempotency,
            "warnings": list(self.warnings),
            "failures": list(self.failures),
        }
        if include_hash:
            data["scenario_hash"] = self.scenario_hash
        return data


@dataclass(frozen=True, slots=True)
class EndToEndCertificationRun:
    certification_run_id: str
    scenario_id: str
    trading_session_id: str
    strategy_instance_id: str
    logical_paper_account: str
    configuration_hash: str
    rule_matrix_version: str
    source_fixture_identity: str
    initial_schema_version: int
    authority_grant_id: str
    started_at: datetime
    completed_at: datetime
    scenarios: tuple[CertificationScenarioResult, ...]
    scorecard: dict[str, Any]
    known_failure_register: list[dict[str, Any]]
    run_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenarios", tuple(self.scenarios))
        object.__setattr__(self, "run_hash", _hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "certification_run_id": self.certification_run_id,
            "scenario_id": self.scenario_id,
            "trading_session_id": self.trading_session_id,
            "strategy_instance_id": self.strategy_instance_id,
            "logical_paper_account": self.logical_paper_account,
            "configuration_hash": self.configuration_hash,
            "rule_matrix_version": self.rule_matrix_version,
            "source_fixture_identity": self.source_fixture_identity,
            "initial_schema_version": self.initial_schema_version,
            "authority_grant_id": self.authority_grant_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "scenarios": [item.to_dict() for item in self.scenarios],
            "scorecard": self.scorecard,
            "known_failure_register": self.known_failure_register,
        }
        if include_hash:
            data["run_hash"] = self.run_hash
        return data
