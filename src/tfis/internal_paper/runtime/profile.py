from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tfis.persistence import canonical_hash


@dataclass(frozen=True, slots=True)
class ControlledRuntimeProfile:
    profile_id: str
    enabled_by_default: bool
    authority_mode: str
    logical_paper_account: str
    strategy_instance_id: str
    strategy_definition_id: str
    strategy_version: str
    trading_session_id: str
    configured_quantity: int
    permitted_branches: tuple[str, ...]
    permitted_purposes: tuple[str, ...]
    persistence_database_path: str
    market_data_source: dict[str, str]
    operator_controls: tuple[str, ...]
    shutdown_behavior: tuple[str, ...]
    external_broker_enabled: bool = False
    live_writes_enabled: bool = False
    broker_sandbox_enabled: bool = False
    profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.enabled_by_default:
            raise ValueError("Controlled internal-paper runtime profile must be disabled by default.")
        if self.authority_mode != "INTERNAL_PAPER_CONTROLLED":
            raise ValueError("Unsupported controlled runtime authority mode.")
        if self.configured_quantity <= 0:
            raise ValueError("Configured quantity must be positive.")
        if any((self.external_broker_enabled, self.live_writes_enabled, self.broker_sandbox_enabled)):
            raise ValueError("Controlled runtime profile cannot enable external authority.")
        object.__setattr__(self, "permitted_branches", tuple(self.permitted_branches))
        object.__setattr__(self, "permitted_purposes", tuple(self.permitted_purposes))
        object.__setattr__(self, "operator_controls", tuple(self.operator_controls))
        object.__setattr__(self, "shutdown_behavior", tuple(self.shutdown_behavior))
        object.__setattr__(self, "profile_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "profile_id": self.profile_id,
            "enabled_by_default": self.enabled_by_default,
            "authority_mode": self.authority_mode,
            "logical_paper_account": self.logical_paper_account,
            "strategy_instance_id": self.strategy_instance_id,
            "strategy_definition_id": self.strategy_definition_id,
            "strategy_version": self.strategy_version,
            "trading_session_id": self.trading_session_id,
            "configured_quantity": self.configured_quantity,
            "permitted_branches": list(self.permitted_branches),
            "permitted_purposes": list(self.permitted_purposes),
            "persistence_database_path": self.persistence_database_path,
            "market_data_source": self.market_data_source,
            "operator_controls": list(self.operator_controls),
            "shutdown_behavior": list(self.shutdown_behavior),
            "external_broker_enabled": self.external_broker_enabled,
            "live_writes_enabled": self.live_writes_enabled,
            "broker_sandbox_enabled": self.broker_sandbox_enabled,
        }
        if include_hash:
            data["profile_hash"] = self.profile_hash
        return data


def build_default_s23_single_instance_profile() -> ControlledRuntimeProfile:
    return ControlledRuntimeProfile(
        profile_id="internal_paper_s23_single_instance",
        enabled_by_default=False,
        authority_mode="INTERNAL_PAPER_CONTROLLED",
        logical_paper_account="INTERNAL_PAPER_ACCOUNT",
        strategy_instance_id="S23_FOUR_BRANCH_INTERNAL_PAPER_CONTROLLED",
        strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_FOUR_BRANCH",
        strategy_version="s23.phase5b.controlled.v1",
        trading_session_id="NSE:2026-06-05",
        configured_quantity=50,
        permitted_branches=("BULL_CALL", "BEAR_CALL", "BULL_PUT", "BEAR_PUT"),
        permitted_purposes=("ENTRY", "TARGET", "ORIGINAL_SL", "REVISED_SL", "EOD_EXIT"),
        persistence_database_path="data/internal_paper/phase5a/s23_single_instance.sqlite",
        market_data_source={
            "mode": "CERTIFICATION_FIXTURE",
            "source_identity": "PHASE5A_PRE_ACCEPTED_FIXTURES",
            "timestamp_policy": "EVENT_TIME_ONLY",
            "dispatch_policy": "DETERMINISTIC_SEQUENTIAL",
        },
        operator_controls=(
            "preview",
            "enable_internal_paper",
            "disable_new_entries",
            "stop_strategy",
            "preserve_lifecycle",
            "account_halt",
            "global_halt",
            "resume_after_recovery",
            "graceful_shutdown",
            "status",
            "export_session_summary",
        ),
        shutdown_behavior=(
            "GRACEFUL_SESSION_END",
            "OPERATOR_STOP",
            "FAILURE_SAFE_STOP",
            "KILL_SWITCH_STOP",
            "CRASH_RECOVERY_TEST",
        ),
    )
