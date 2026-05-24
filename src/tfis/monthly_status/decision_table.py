from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from tfis.domain.enums import MonthlyStatus

from .thresholds import MonthlyStatusThresholds, load_monthly_status_thresholds


def _require_finite_number(name: str, value: float) -> float:
    numeric_value = float(value)
    if not isfinite(numeric_value):
        raise ValueError(f"{name} must be finite")
    return numeric_value


def _pct_above(base_value: float, pct: float) -> float:
    return base_value * (1.0 + (pct / 100.0))


def _pct_below(base_value: float, pct: float) -> float:
    return base_value * (1.0 - (pct / 100.0))


@dataclass(frozen=True, slots=True)
class MonthlyStatusReferenceLevels:
    PMH: float
    PML: float
    CMH: float
    CML: float
    PWH: float
    PWL: float
    CWH: float
    CWL: float
    current_price: float

    def __post_init__(self) -> None:
        for field_name in (
            "PMH",
            "PML",
            "CMH",
            "CML",
            "PWH",
            "PWL",
            "CWH",
            "CWL",
            "current_price",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_finite_number(field_name, getattr(self, field_name)),
            )


@dataclass(frozen=True, slots=True)
class MonthlyStatusDecisionCandidate:
    candidate_status: MonthlyStatus
    trigger_name: str
    threshold_value: float | None
    condition_met: bool | None
    confidence: str
    notes: str

    def __post_init__(self) -> None:
        if self.candidate_status == MonthlyStatus.UNKNOWN:
            raise ValueError("candidate_status must be a directional monthly status")
        if self.confidence not in {"HIGH", "MEDIUM", "LOW"}:
            raise ValueError("confidence must be one of HIGH, MEDIUM, or LOW")
        if not isinstance(self.trigger_name, str) or not self.trigger_name.strip():
            raise ValueError("trigger_name must be a non-empty string")
        if not isinstance(self.notes, str):
            raise TypeError("notes must be a string")
        if self.threshold_value is not None:
            object.__setattr__(
                self,
                "threshold_value",
                _require_finite_number("threshold_value", self.threshold_value),
            )


class MonthlyStatusDecisionTable:
    """Build diagnostic monthly-status candidate rows from thresholds.

    This class is intentionally a transparent specification aid only. It does
    not choose a final monthly status, does not persist state, and does not
    replace the future MonthlyStatusEngine.
    """

    def __init__(
        self,
        thresholds_by_group: Mapping[str, MonthlyStatusThresholds] | None = None,
    ) -> None:
        self.thresholds_by_group = dict(
            thresholds_by_group or load_monthly_status_thresholds()
        )

    def build_candidates(
        self,
        instrument_group: str,
        reference_levels: MonthlyStatusReferenceLevels,
        *,
        bullish_value: float | None = None,
        bearish_value: float | None = None,
    ) -> list[MonthlyStatusDecisionCandidate]:
        if instrument_group not in self.thresholds_by_group:
            raise KeyError(
                f"No monthly-status thresholds configured for instrument group: {instrument_group}"
            )

        thresholds = self.thresholds_by_group[instrument_group]
        current_price = reference_levels.current_price

        bull_threshold = _pct_above(reference_levels.PMH, thresholds.a_pct)
        bear_threshold = _pct_below(reference_levels.PML, thresholds.a_pct)
        reversal_bull_base = max(reference_levels.PWH, reference_levels.CWH)
        reversal_bull_threshold = _pct_above(reversal_bull_base, thresholds.c_pct)
        reversal_bear_base = min(reference_levels.PWL, reference_levels.CWL)
        reversal_bear_threshold = _pct_below(reversal_bear_base, thresholds.c_pct)

        candidates = [
            MonthlyStatusDecisionCandidate(
                candidate_status=MonthlyStatus.BULL,
                trigger_name="BULL_A_THRESHOLD",
                threshold_value=bull_threshold,
                condition_met=current_price >= bull_threshold,
                confidence="HIGH",
                notes="Diagnostic BULL candidate from PMH plus a-percent threshold.",
            ),
            MonthlyStatusDecisionCandidate(
                candidate_status=MonthlyStatus.BEAR,
                trigger_name="BEAR_A_THRESHOLD",
                threshold_value=bear_threshold,
                condition_met=current_price <= bear_threshold,
                confidence="HIGH",
                notes="Diagnostic BEAR candidate from PML minus a-percent threshold.",
            ),
            self._build_cf_candidate(
                candidate_status=MonthlyStatus.BULL_CF,
                trigger_name="BULL_CF_B_THRESHOLD",
                current_price=current_price,
                base_value=bullish_value,
                threshold_pct=thresholds.b_pct,
                direction="above",
                notes_when_resolved=(
                    "Diagnostic BULL_CF candidate from bullish reference plus "
                    "b-percent threshold."
                ),
                notes_when_missing=(
                    "Bullish reference value is not available yet; BULL_CF remains "
                    "unresolved until the future engine defines or provides it."
                ),
            ),
            self._build_cf_candidate(
                candidate_status=MonthlyStatus.BEAR_CF,
                trigger_name="BEAR_CF_B_THRESHOLD",
                current_price=current_price,
                base_value=bearish_value,
                threshold_pct=thresholds.b_pct,
                direction="below",
                notes_when_resolved=(
                    "Diagnostic BEAR_CF candidate from bearish reference minus "
                    "b-percent threshold."
                ),
                notes_when_missing=(
                    "Bearish reference value is not available yet; BEAR_CF remains "
                    "unresolved until the future engine defines or provides it."
                ),
            ),
            MonthlyStatusDecisionCandidate(
                candidate_status=MonthlyStatus.BULL,
                trigger_name="REVERSAL_BULL_C_THRESHOLD",
                threshold_value=reversal_bull_threshold,
                condition_met=current_price >= reversal_bull_threshold,
                confidence="MEDIUM",
                notes=(
                    "Diagnostic reversal BULL candidate from MAX(PWH, CWH) plus "
                    "c-percent threshold."
                ),
            ),
            MonthlyStatusDecisionCandidate(
                candidate_status=MonthlyStatus.BEAR,
                trigger_name="REVERSAL_BEAR_C_THRESHOLD",
                threshold_value=reversal_bear_threshold,
                condition_met=current_price <= reversal_bear_threshold,
                confidence="MEDIUM",
                notes=(
                    "Diagnostic reversal BEAR candidate from MIN(PWL, CWL) minus "
                    "c-percent threshold."
                ),
            ),
        ]
        return candidates

    def _build_cf_candidate(
        self,
        *,
        candidate_status: MonthlyStatus,
        trigger_name: str,
        current_price: float,
        base_value: float | None,
        threshold_pct: float,
        direction: str,
        notes_when_resolved: str,
        notes_when_missing: str,
    ) -> MonthlyStatusDecisionCandidate:
        if base_value is None:
            return MonthlyStatusDecisionCandidate(
                candidate_status=candidate_status,
                trigger_name=trigger_name,
                threshold_value=None,
                condition_met=None,
                confidence="LOW",
                notes=notes_when_missing,
            )

        normalized_base = _require_finite_number(f"{trigger_name}_base_value", base_value)
        if direction == "above":
            threshold_value = _pct_above(normalized_base, threshold_pct)
            condition_met = current_price >= threshold_value
        elif direction == "below":
            threshold_value = _pct_below(normalized_base, threshold_pct)
            condition_met = current_price <= threshold_value
        else:
            raise ValueError(f"Unsupported direction for CF candidate: {direction}")

        return MonthlyStatusDecisionCandidate(
            candidate_status=candidate_status,
            trigger_name=trigger_name,
            threshold_value=threshold_value,
            condition_met=condition_met,
            confidence="MEDIUM",
            notes=notes_when_resolved,
        )


def build_monthly_status_decision_table(
    instrument_group: str,
    reference_levels: MonthlyStatusReferenceLevels,
    *,
    bullish_value: float | None = None,
    bearish_value: float | None = None,
    thresholds_by_group: Mapping[str, MonthlyStatusThresholds] | None = None,
) -> list[MonthlyStatusDecisionCandidate]:
    return MonthlyStatusDecisionTable(thresholds_by_group).build_candidates(
        instrument_group,
        reference_levels,
        bullish_value=bullish_value,
        bearish_value=bearish_value,
    )
