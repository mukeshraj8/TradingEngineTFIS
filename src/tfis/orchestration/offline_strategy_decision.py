from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from tfis.domain import TFISDecision, TFISDecisionEvidencePacket


class OfflineStage(Protocol):
    stage_name: str

    def run(self, context: Mapping[str, Any]) -> "OfflineStageResult":
        ...


@dataclass(frozen=True, slots=True)
class OfflineStageResult:
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
class OfflineStrategyDecisionResult:
    decision: TFISDecision
    evidence_packet: TFISDecisionEvidencePacket
    stages: tuple[OfflineStageResult, ...]
    field_comparison: Mapping[str, Mapping[str, Any]]
    mismatch_classifications: Mapping[str, str]
    deterministic_hash: str
    performance: Mapping[str, float | int]


class OfflineStrategyDecisionOrchestrator:
    """Runs explicitly supplied offline stages without strategy-specific logic."""

    def evaluate(
        self,
        initial_context: Mapping[str, Any],
        stages: tuple[OfflineStage, ...],
    ) -> OfflineStrategyDecisionResult:
        started = perf_counter()
        context: dict[str, Any] = dict(initial_context)
        results: list[OfflineStageResult] = []
        for stage in stages:
            stage_result = stage.run(MappingProxyType(context))
            results.append(stage_result)
            context.update(dict(stage_result.payload))
            if not stage_result.passed:
                break
        decision = context["decision"]
        packet = context["evidence_packet"]
        business_hash = _business_hash(
            {
                "decision": json.loads(decision.to_json()),
                "evidence_packet": json.loads(packet.to_json()),
                "stages": [
                    {
                        "stage_name": item.stage_name,
                        "status": item.status,
                        "failure_code": item.failure_code,
                        "reason": item.reason,
                    }
                    for item in results
                ],
                "field_comparison": context.get("field_comparison", {}),
                "mismatch_classifications": context.get("mismatch_classifications", {}),
            }
        )
        return OfflineStrategyDecisionResult(
            decision=decision,
            evidence_packet=packet,
            stages=tuple(results),
            field_comparison=MappingProxyType(dict(context.get("field_comparison", {}))),
            mismatch_classifications=MappingProxyType(dict(context.get("mismatch_classifications", {}))),
            deterministic_hash=business_hash,
            performance=MappingProxyType(
                {
                    "stage_count": len(results),
                    "duration_seconds": perf_counter() - started,
                    "evidence_packet_size_bytes": len(packet.to_json().encode("utf-8")),
                }
            ),
        )


def _business_hash(value: Any) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
