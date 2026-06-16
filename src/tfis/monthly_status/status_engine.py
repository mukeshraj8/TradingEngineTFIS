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
    """Evaluate monthly status from workbook-backed monthly/weekly rules.

    Layer 1:
    - Determine direct monthly structure from CMH/CML versus PMH/PML.

    Layer 2:
    - Once an effective monthly status exists (direct or borrowed), apply the
      current-price transition rules:
      - non-confirmed states reverse using weekly c-percent checks
      - confirmed states reverse using monthly a-percent checks
      - non-confirmed states can also become confirmed through the second
        a/b-percent threshold.
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
        return self.classify_monthly_structure(instrument_group, levels)

    def classify_monthly_structure(
        self,
        instrument_group: str,
        levels: MonthlyStatusReferenceLevels,
    ) -> MonthlyStatusResult:
        thresholds = self._thresholds_for(instrument_group)
        bull_threshold = _pct_above(levels.PMH, thresholds.a_pct)
        bear_threshold = _pct_below(levels.PML, thresholds.a_pct)
        bull_cf_threshold = _pct_above(bull_threshold, thresholds.b_pct)
        bear_cf_threshold = _pct_below(bear_threshold, thresholds.b_pct)
        candidates = self.decision_table.build_candidates(
            instrument_group,
            levels,
            bullish_value=bull_threshold,
            bearish_value=bear_threshold,
        )

        bull_cf = levels.CMH >= bull_cf_threshold
        bear_cf = levels.CML <= bear_cf_threshold
        bull = levels.CMH >= bull_threshold
        bear = levels.CML <= bear_threshold

        if bull_cf and not bear_cf:
            return self._build_result(
                status=MonthlyStatus.BULL_CF,
                trigger_name="BULL_CF_B_THRESHOLD",
                threshold_value=bull_cf_threshold,
                reversal_dominated=False,
                candidates=candidates,
                notes=(
                    "Current month high breached the bullish confirmation "
                    "threshold derived from PMH plus a-percent and the second "
                    "b-percent expansion."
                ),
            )

        if bear_cf and not bull_cf:
            return self._build_result(
                status=MonthlyStatus.BEAR_CF,
                trigger_name="BEAR_CF_B_THRESHOLD",
                threshold_value=bear_cf_threshold,
                reversal_dominated=False,
                candidates=candidates,
                notes=(
                    "Current month low breached the bearish confirmation "
                    "threshold derived from PML minus a-percent and the second "
                    "b-percent contraction."
                ),
            )

        if bull and not bear:
            return self._build_result(
                status=MonthlyStatus.BULL,
                trigger_name="BULL_A_THRESHOLD",
                threshold_value=bull_threshold,
                reversal_dominated=False,
                candidates=candidates,
                notes=(
                    "Current month high breached the bullish threshold derived "
                    "from PMH plus a-percent."
                ),
            )

        if bear and not bull:
            return self._build_result(
                status=MonthlyStatus.BEAR,
                trigger_name="BEAR_A_THRESHOLD",
                threshold_value=bear_threshold,
                reversal_dominated=False,
                candidates=candidates,
                notes=(
                    "Current month low breached the bearish threshold derived "
                    "from PML minus a-percent."
                ),
            )

        if bull_cf or bear_cf or bull or bear:
            if levels.current_price >= bull_threshold and levels.current_price > bear_threshold:
                return self._build_result(
                    status=MonthlyStatus.BULL,
                    trigger_name="AMBIGUOUS_MONTHLY_RANGE_BULL",
                    threshold_value=bull_threshold,
                    reversal_dominated=False,
                    candidates=candidates,
                    notes=(
                        "Current month breached both bullish and bearish monthly "
                        "ranges; current price sits above the bullish threshold, "
                        "so the direct monthly structure is treated as bullish."
                    ),
                )
            if levels.current_price <= bear_threshold and levels.current_price < bull_threshold:
                return self._build_result(
                    status=MonthlyStatus.BEAR,
                    trigger_name="AMBIGUOUS_MONTHLY_RANGE_BEAR",
                    threshold_value=bear_threshold,
                    reversal_dominated=False,
                    candidates=candidates,
                    notes=(
                        "Current month breached both bullish and bearish monthly "
                        "ranges; current price sits below the bearish threshold, "
                        "so the direct monthly structure is treated as bearish."
                    ),
                )

        return self._build_result(
            status=MonthlyStatus.UNKNOWN,
            trigger_name="NO_MONTHLY_TRIGGER",
            threshold_value=None,
            reversal_dominated=False,
            candidates=candidates,
            notes=(
                "Current month did not decisively breach the previous month's "
                "bullish or bearish monthly thresholds."
            ),
        )

    def apply_current_price_transitions(
        self,
        instrument_group: str,
        levels: MonthlyStatusReferenceLevels,
        *,
        effective_status: MonthlyStatus,
    ) -> MonthlyStatusResult:
        if effective_status is MonthlyStatus.UNKNOWN:
            return self._build_result(
                status=MonthlyStatus.UNKNOWN,
                trigger_name="NO_EFFECTIVE_MONTHLY_STATUS",
                threshold_value=None,
                reversal_dominated=False,
                candidates=self.decision_table.build_candidates(
                    instrument_group,
                    levels,
                    bullish_value=_pct_above(
                        levels.PMH, self._thresholds_for(instrument_group).a_pct
                    ),
                    bearish_value=_pct_below(
                        levels.PML, self._thresholds_for(instrument_group).a_pct
                    ),
                ),
                notes=(
                    "Current month remained UNKNOWN and no historical monthly "
                    "status could be borrowed."
                ),
            )

        thresholds = self._thresholds_for(instrument_group)
        bull_threshold = _pct_above(levels.PMH, thresholds.a_pct)
        bear_threshold = _pct_below(levels.PML, thresholds.a_pct)
        bull_cf_threshold = _pct_above(bull_threshold, thresholds.b_pct)
        bear_cf_threshold = _pct_below(bear_threshold, thresholds.b_pct)
        reversal_bull_threshold = _pct_above(
            max(levels.PWH, levels.CWH), thresholds.c_pct
        )
        reversal_bear_threshold = _pct_below(
            min(levels.PWL, levels.CWL), thresholds.c_pct
        )
        candidates = self.decision_table.build_candidates(
            instrument_group,
            levels,
            bullish_value=bull_threshold,
            bearish_value=bear_threshold,
        )
        price = levels.current_price

        if effective_status is MonthlyStatus.BULL:
            if price >= bull_cf_threshold:
                return self._build_result(
                    status=MonthlyStatus.BULL_CF,
                    trigger_name="BULL_CF_B_THRESHOLD",
                    threshold_value=bull_cf_threshold,
                    reversal_dominated=False,
                    candidates=candidates,
                    notes=(
                        "Effective bullish monthly status advanced to bullish "
                        "confirmed because current price crossed the bullish "
                        "confirmation threshold."
                    ),
                )
            if price <= reversal_bear_threshold:
                return self._build_result(
                    status=MonthlyStatus.BEAR,
                    trigger_name="REVERSAL_BEAR_C_THRESHOLD",
                    threshold_value=reversal_bear_threshold,
                    reversal_dominated=True,
                    candidates=candidates,
                    notes=(
                        "Effective bullish monthly status reversed to bearish "
                        "because current price broke below MIN(PWL, CWL) by "
                        "c-percent."
                    ),
                )
            return self._build_result(
                status=MonthlyStatus.BULL,
                trigger_name="BULL_CONTINUES",
                threshold_value=bull_threshold,
                reversal_dominated=False,
                candidates=candidates,
                notes="Effective bullish monthly status remains bullish.",
            )

        if effective_status is MonthlyStatus.BULL_CF:
            if price <= bear_threshold:
                return self._build_result(
                    status=MonthlyStatus.BEAR,
                    trigger_name="BEAR_A_THRESHOLD",
                    threshold_value=bear_threshold,
                    reversal_dominated=True,
                    candidates=candidates,
                    notes=(
                        "Effective bullish confirmed monthly status reversed to "
                        "bearish because current price fell below PML by "
                        "a-percent."
                    ),
                )
            return self._build_result(
                status=MonthlyStatus.BULL_CF,
                trigger_name="BULL_CF_CONTINUES",
                threshold_value=bull_cf_threshold,
                reversal_dominated=False,
                candidates=candidates,
                notes=(
                    "Effective bullish confirmed monthly status remains bullish "
                    "confirmed."
                ),
            )

        if effective_status is MonthlyStatus.BEAR:
            if price <= bear_cf_threshold:
                return self._build_result(
                    status=MonthlyStatus.BEAR_CF,
                    trigger_name="BEAR_CF_B_THRESHOLD",
                    threshold_value=bear_cf_threshold,
                    reversal_dominated=False,
                    candidates=candidates,
                    notes=(
                        "Effective bearish monthly status advanced to bearish "
                        "confirmed because current price crossed the bearish "
                        "confirmation threshold."
                    ),
                )
            if price >= reversal_bull_threshold:
                return self._build_result(
                    status=MonthlyStatus.BULL,
                    trigger_name="REVERSAL_BULL_C_THRESHOLD",
                    threshold_value=reversal_bull_threshold,
                    reversal_dominated=True,
                    candidates=candidates,
                    notes=(
                        "Effective bearish monthly status reversed to bullish "
                        "because current price broke above MAX(PWH, CWH) by "
                        "c-percent."
                    ),
                )
            return self._build_result(
                status=MonthlyStatus.BEAR,
                trigger_name="BEAR_CONTINUES",
                threshold_value=bear_threshold,
                reversal_dominated=False,
                candidates=candidates,
                notes="Effective bearish monthly status remains bearish.",
            )

        if effective_status is MonthlyStatus.BEAR_CF:
            if price >= bull_threshold:
                return self._build_result(
                    status=MonthlyStatus.BULL,
                    trigger_name="BULL_A_THRESHOLD",
                    threshold_value=bull_threshold,
                    reversal_dominated=True,
                    candidates=candidates,
                    notes=(
                        "Effective bearish confirmed monthly status reversed to "
                        "bullish because current price rose above PMH by "
                        "a-percent."
                    ),
                )
            return self._build_result(
                status=MonthlyStatus.BEAR_CF,
                trigger_name="BEAR_CF_CONTINUES",
                threshold_value=bear_cf_threshold,
                reversal_dominated=False,
                candidates=candidates,
                notes=(
                    "Effective bearish confirmed monthly status remains bearish "
                    "confirmed."
                ),
            )

        raise ValueError(f"Unsupported effective monthly status: {effective_status}")

    def _build_result(
        self,
        *,
        status: MonthlyStatus,
        trigger_name: str,
        threshold_value: float | None,
        reversal_dominated: bool,
        candidates: list[MonthlyStatusDecisionCandidate],
        notes: str,
    ) -> MonthlyStatusResult:
        return MonthlyStatusResult(
            status=status,
            trigger_name=trigger_name,
            threshold_value=threshold_value,
            reversal_dominated=reversal_dominated,
            candidates=list(candidates),
            notes=notes,
        )

    def _thresholds_for(self, instrument_group: str) -> MonthlyStatusThresholds:
        if instrument_group not in self.thresholds_by_group:
            raise KeyError(
                f"No monthly-status thresholds configured for instrument group: {instrument_group}"
            )
        return self.thresholds_by_group[instrument_group]
