from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tfis.persistence import canonical_hash

from .models import InternalPaperConsistencyStatus, InternalPaperRecoveryStatus


@dataclass(frozen=True, slots=True)
class InternalPaperRecoveryAssessment:
    assessment_id: str
    status: InternalPaperRecoveryStatus
    active_order_count: int
    fill_count: int
    latest_event_sequence: int
    findings: tuple[str, ...]
    resume_automatically: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "status": self.status.value,
            "active_order_count": self.active_order_count,
            "fill_count": self.fill_count,
            "latest_event_sequence": self.latest_event_sequence,
            "findings": list(self.findings),
            "resume_automatically": self.resume_automatically,
            "assessment_hash": canonical_hash(
                {
                    "assessment_id": self.assessment_id,
                    "status": self.status.value,
                    "active_order_count": self.active_order_count,
                    "fill_count": self.fill_count,
                    "latest_event_sequence": self.latest_event_sequence,
                    "findings": self.findings,
                    "resume_automatically": self.resume_automatically,
                }
            ),
        }


@dataclass(frozen=True, slots=True)
class InternalPaperStateConsistencyAssessment:
    assessment_id: str
    status: InternalPaperConsistencyStatus
    persisted_order_count: int
    persisted_event_count: int
    persisted_fill_count: int
    projection_count: int
    findings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "status": self.status.value,
            "persisted_order_count": self.persisted_order_count,
            "persisted_event_count": self.persisted_event_count,
            "persisted_fill_count": self.persisted_fill_count,
            "projection_count": self.projection_count,
            "findings": list(self.findings),
        }


def assess_internal_paper_recovery(*, active_order_count: int, fill_count: int, latest_event_sequence: int, mismatch_count: int = 0) -> InternalPaperRecoveryAssessment:
    if mismatch_count:
        status = InternalPaperRecoveryStatus.INTERNAL_PAPER_REVIEW_REQUIRED
        findings = ("projection mismatch requires review",)
    elif active_order_count or fill_count:
        status = InternalPaperRecoveryStatus.INTERNAL_PAPER_RECOVERABLE
        findings = ("internal paper state can be recovered with explicit resume input",)
    else:
        status = InternalPaperRecoveryStatus.INTERNAL_PAPER_RECOVERABLE
        findings = ("no active internal paper state",)
    return InternalPaperRecoveryAssessment(
        assessment_id="internal-paper-recovery:" + canonical_hash({"active_order_count": active_order_count, "fill_count": fill_count, "latest_event_sequence": latest_event_sequence, "mismatch_count": mismatch_count})[:24],
        status=status,
        active_order_count=active_order_count,
        fill_count=fill_count,
        latest_event_sequence=latest_event_sequence,
        findings=findings,
    )


def assess_internal_paper_consistency(*, persisted_order_count: int, persisted_event_count: int, persisted_fill_count: int, projection_count: int) -> InternalPaperStateConsistencyAssessment:
    status = InternalPaperConsistencyStatus.MATCHED if projection_count <= persisted_order_count and persisted_event_count >= persisted_order_count else InternalPaperConsistencyStatus.REVIEW_REQUIRED
    return InternalPaperStateConsistencyAssessment(
        assessment_id="internal-paper-consistency:" + canonical_hash({"orders": persisted_order_count, "events": persisted_event_count, "fills": persisted_fill_count, "projections": projection_count})[:24],
        status=status,
        persisted_order_count=persisted_order_count,
        persisted_event_count=persisted_event_count,
        persisted_fill_count=persisted_fill_count,
        projection_count=projection_count,
        findings=() if status is InternalPaperConsistencyStatus.MATCHED else ("internal paper state mismatch",),
    )
