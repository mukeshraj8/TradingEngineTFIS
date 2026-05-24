from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from tfis.domain.enums import MonthlyStatus

from .decision_table import (
    MonthlyStatusDecisionCandidate,
    MonthlyStatusDecisionTable,
    MonthlyStatusReferenceLevels,
)
from .thresholds import MonthlyStatusThresholds, load_monthly_status_thresholds


def _pct_above(base_value: float, pct: float) -> float:
    return float(base_value) * (1.0 + (float(pct) / 100.0))


def _pct_below(base_value: float, pct: float) -> float:
    return float(base_value) * (1.0 - (float(pct) / 100.0))


@dataclass(frozen=True, slots=True)
class MonthlyStatusResult:
    status: MonthlyStatus
    trigger_name: str
    threshold_value: float | None
    reversal_dominated: bool
    candidates: list[MonthlyStatusDecisionCandidate]
    notes: str


class MonthlyStatusEngine:
    """Classify final monthly status from reference levels and configured thresholds.

    This engine is deterministic and intentionally limited to the currently
    confirmed threshold rules. It does not add gap logic, monthly close
    confirmation, or carry-forward state beyond the explicit confirmed
    thresholds.
    """

    def __init__(
        self,
        thresholds_by_group: Mapping[str, MonthlyStatusThresholds] | None = None,
    ) -> None:
        self.thresholds_by_group = dict(
            thresholds_by_group or load_monthly_status_thresholds()
        )
        self.decision_table = MonthlyStatusDecisionTable(self.thresholds_by_group)

    def classify(
        self,
        instrument_group: str,
        levels: MonthlyStatusReferenceLevels,
    ) -> MonthlyStatusResult:
        if instrument_group not in self.thresholds_by_group:
            raise KeyError(
                f"No monthly-status thresholds configured for instrument group: {instrument_group}"
            )

        thresholds = self.thresholds_by_group[instrument_group]
        bullish_value = _pct_above(levels.PMH, thresholds.a_pct)
        bearish_value = _pct_below(levels.PML, thresholds.a_pct)
        candidates = self.decision_table.build_candidates(
            instrument_group,
            levels,
            bullish_value=bullish_value,
            bearish_value=bearish_value,
        )
        candidate_map = {candidate.trigger_name: candidate for candidate in candidates}

        reversal_bear = self._is_true(candidate_map["REVERSAL_BEAR_C_THRESHOLD"])
        reversal_bull = self._is_true(candidate_map["REVERSAL_BULL_C_THRESHOLD"])
        bear_cf = self._is_true(candidate_map["BEAR_CF_B_THRESHOLD"])
        bull_cf = self._is_true(candidate_map["BULL_CF_B_THRESHOLD"])
        bear = self._is_true(candidate_map["BEAR_A_THRESHOLD"])
        bull = self._is_true(candidate_map["BULL_A_THRESHOLD"])

        if reversal_bear:
            reversal_dominated = bull or bull_cf
            notes = (
                "Reversal bearish condition dominates bullish continuation candidate(s)."
                if reversal_dominated
                else "Reversal bearish condition met."
            )
            return self._build_result(
                status=MonthlyStatus.BEAR,
                candidate=candidate_map["REVERSAL_BEAR_C_THRESHOLD"],
                reversal_dominated=reversal_dominated,
                candidates=candidates,
                notes=notes,
            )

        if reversal_bull:
            reversal_dominated = bear or bear_cf
            notes = (
                "Reversal bullish condition dominates bearish continuation candidate(s)."
                if reversal_dominated
                else "Reversal bullish condition met."
            )
            return self._build_result(
                status=MonthlyStatus.BULL,
                candidate=candidate_map["REVERSAL_BULL_C_THRESHOLD"],
                reversal_dominated=reversal_dominated,
                candidates=candidates,
                notes=notes,
            )

        if bear_cf:
            return self._build_result(
                status=MonthlyStatus.BEAR_CF,
                candidate=candidate_map["BEAR_CF_B_THRESHOLD"],
                reversal_dominated=False,
                candidates=candidates,
                notes=(
                    "Bearish confirmation threshold met from bearish_value minus b-percent."
                ),
            )

        if bull_cf:
            return self._build_result(
                status=MonthlyStatus.BULL_CF,
                candidate=candidate_map["BULL_CF_B_THRESHOLD"],
                reversal_dominated=False,
                candidates=candidates,
                notes=(
                    "Bullish confirmation threshold met from bullish_value plus b-percent."
                ),
            )

        if bear:
            return self._build_result(
                status=MonthlyStatus.BEAR,
                candidate=candidate_map["BEAR_A_THRESHOLD"],
                reversal_dominated=False,
                candidates=candidates,
                notes="Bearish reversal started but not confirmed.",
            )

        if bull:
            return self._build_result(
                status=MonthlyStatus.BULL,
                candidate=candidate_map["BULL_A_THRESHOLD"],
                reversal_dominated=False,
                candidates=candidates,
                notes="Bullish reversal started but not confirmed.",
            )

        return MonthlyStatusResult(
            status=MonthlyStatus.UNKNOWN,
            trigger_name="NO_TRIGGER",
            threshold_value=None,
            reversal_dominated=False,
            candidates=list(candidates),
            notes="No confirmed monthly-status trigger was met.",
        )

    def _build_result(
        self,
        *,
        status: MonthlyStatus,
        candidate: MonthlyStatusDecisionCandidate,
        reversal_dominated: bool,
        candidates: list[MonthlyStatusDecisionCandidate],
        notes: str,
    ) -> MonthlyStatusResult:
        return MonthlyStatusResult(
            status=status,
            trigger_name=candidate.trigger_name,
            threshold_value=candidate.threshold_value,
            reversal_dominated=reversal_dominated,
            candidates=list(candidates),
            notes=notes,
        )

    def _is_true(self, candidate: MonthlyStatusDecisionCandidate) -> bool:
        return candidate.condition_met is True
