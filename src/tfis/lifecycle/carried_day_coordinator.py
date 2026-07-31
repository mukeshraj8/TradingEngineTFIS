from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from tfis.domain.carried_position_day import (
    CarriedPositionDayStage,
    CarriedPositionDayTransition,
    CarriedPositionEodOutcome,
    CarriedPositionIntradayState,
    OfflineCarriedPositionEodDecision,
    OfflineCarriedPositionTradingDay,
)
from tfis.domain.position_lifecycle import LifecycleActionRequirement, PositionLifecycleContext, build_offline_lifecycle_handoff


@dataclass(frozen=True, slots=True)
class OfflineCarriedPositionTradingDayInput:
    day_id: str
    lifecycle_context: PositionLifecycleContext
    eod_decision_factory: Callable[[PositionLifecycleContext], OfflineCarriedPositionEodDecision] | None = None


class OfflineCarriedPositionTradingDayCoordinator:
    def coordinate(self, request: OfflineCarriedPositionTradingDayInput) -> OfflineCarriedPositionTradingDay:
        started = perf_counter()
        context = request.lifecycle_context
        handoff = build_offline_lifecycle_handoff(context, f"{request.day_id}:offline-lifecycle-handoff")
        transitions = self._transitions(context)
        intraday = self._intraday_state(context)
        block_code = None
        block_reason = None
        terminal = CarriedPositionDayStage.COMPLETED_OFFLINE

        if intraday in (CarriedPositionIntradayState.BLOCKED, CarriedPositionIntradayState.WAITING_FOR_AUTHORIZED_OBSERVATION):
            block_code = context.action_requirement.value
            block_reason = "Lifecycle context is not sufficient for offline carried-position day completion."
            terminal = CarriedPositionDayStage.BLOCKED

        eod_decision: OfflineCarriedPositionEodDecision | None = None
        if terminal is not CarriedPositionDayStage.BLOCKED and intraday is not CarriedPositionIntradayState.EXIT_REQUIRED_FROM_OPEN:
            if request.eod_decision_factory is None:
                block_code = "MISSING_EOD_DECISION"
                block_reason = "15:00 carried-position EOD decision is required before offline handoff completion."
                terminal = CarriedPositionDayStage.BLOCKED
                intraday = CarriedPositionIntradayState.BLOCKED
            else:
                eod_decision = request.eod_decision_factory(context)
                transitions.append(
                    CarriedPositionDayTransition(
                        CarriedPositionDayStage.EOD_DECISION_READY,
                        context.opening_evidence.observation_timestamp if context.opening_evidence else None,
                        f"15:00 EOD decision resolved as {eod_decision.outcome.value}.",
                        {"eod_decision": eod_decision.decision_hash},
                    )
                )
                if eod_decision.outcome is CarriedPositionEodOutcome.RULE_AUTHORITY_UNRESOLVED:
                    block_code = "EOD_RULE_AUTHORITY_UNRESOLVED"
                    block_reason = "15:00 carried-position EOD decision has unresolved rule authority."
                    terminal = CarriedPositionDayStage.BLOCKED
                    intraday = CarriedPositionIntradayState.BLOCKED

        transitions.append(
            CarriedPositionDayTransition(
                CarriedPositionDayStage.OFFLINE_HANDOFF_READY,
                context.opening_evidence.observation_timestamp if context.opening_evidence else None,
                "Offline lifecycle handoff produced without mutation authority.",
                {"lifecycle_handoff": handoff.evidence_hash},
            )
        )
        transitions.append(
            CarriedPositionDayTransition(
                terminal,
                context.opening_evidence.observation_timestamp if context.opening_evidence else None,
                "Offline carried-position day completed." if terminal is CarriedPositionDayStage.COMPLETED_OFFLINE else block_reason or "Offline carried-position day blocked.",
                self._artifact_hashes(context, handoff, eod_decision),
            )
        )

        return OfflineCarriedPositionTradingDay(
            day_id=request.day_id,
            trading_date=context.trading_date,
            strategy_family=context.strategy_family,
            strategy_definition=context.strategy_definition,
            strategy_version=context.strategy_version,
            strategy_instance_id=context.strategy_instance_id,
            configuration_hash=context.configuration_hash,
            position_cycle_id=context.position_snapshot.position_cycle_id if context.position_snapshot else None,
            lifecycle_context=context,
            lifecycle_handoff=handoff,
            intraday_state=intraday,
            eod_decision=eod_decision,
            terminal_stage=terminal,
            transition_evidence=tuple(transitions),
            block_code=block_code,
            block_reason=block_reason,
            policy_identities=context.policy_identities,
            performance={"coordination_seconds": perf_counter() - started},
        )

    def _transitions(self, context: PositionLifecycleContext) -> list[CarriedPositionDayTransition]:
        timestamp = context.opening_evidence.observation_timestamp if context.opening_evidence else None
        transitions = [
            CarriedPositionDayTransition(
                CarriedPositionDayStage.POSITION_RECONCILED,
                timestamp,
                f"Position reconciliation status is {context.position_snapshot.reconciliation_status.value if context.position_snapshot else 'MISSING'}.",
                {"lifecycle_context": context.context_hash},
            ),
            CarriedPositionDayTransition(
                CarriedPositionDayStage.TARGET_PROTECTION_ASSESSED,
                timestamp,
                f"Target-first opening assessment produced {context.opening_status.value}.",
                {"lifecycle_context": context.context_hash},
            ),
        ]
        if context.action_requirement is LifecycleActionRequirement.NORMAL_SL_PLACEMENT_REQUIRED:
            transitions.append(
                CarriedPositionDayTransition(
                    CarriedPositionDayStage.ORPT_ORIGINAL_SL_ASSESSED,
                    timestamp,
                    "ORPT original-SL evaluation requires normal SL placement.",
                    {"lifecycle_context": context.context_hash},
                )
            )
        if context.action_requirement is LifecycleActionRequirement.REVISED_SL_PLACEMENT_REQUIRED:
            transitions.append(
                CarriedPositionDayTransition(
                    CarriedPositionDayStage.RC_REVISED_FSL_ASSESSED,
                    timestamp,
                    "ORPT original-SL missed; RC revised FSL/TRP requirement recorded.",
                    {"lifecycle_context": context.context_hash},
                )
            )
        transitions.append(
            CarriedPositionDayTransition(
                CarriedPositionDayStage.INTRADAY_LIFECYCLE_READY,
                timestamp,
                f"Intraday lifecycle state derived from {context.action_requirement.value}.",
                {"lifecycle_context": context.context_hash},
            )
        )
        return transitions

    def _intraday_state(self, context: PositionLifecycleContext) -> CarriedPositionIntradayState:
        if context.action_requirement is LifecycleActionRequirement.EXIT_REQUIRED:
            return CarriedPositionIntradayState.EXIT_REQUIRED_FROM_OPEN
        if context.action_requirement is LifecycleActionRequirement.NORMAL_SL_PLACEMENT_REQUIRED:
            return CarriedPositionIntradayState.NORMAL_SL_REQUIRED
        if context.action_requirement is LifecycleActionRequirement.REVISED_SL_PLACEMENT_REQUIRED:
            return CarriedPositionIntradayState.REVISED_FSL_REQUIRED
        if context.action_requirement is LifecycleActionRequirement.WAIT_FOR_AUTHORIZED_OBSERVATION:
            return CarriedPositionIntradayState.WAITING_FOR_AUTHORIZED_OBSERVATION
        return CarriedPositionIntradayState.BLOCKED

    def _artifact_hashes(
        self,
        context: PositionLifecycleContext,
        handoff,
        eod_decision: OfflineCarriedPositionEodDecision | None,
    ) -> dict[str, str]:
        artifacts = {"lifecycle_context": context.context_hash, "lifecycle_handoff": handoff.evidence_hash}
        if eod_decision is not None:
            artifacts["eod_decision"] = eod_decision.decision_hash
        return artifacts
