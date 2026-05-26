from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import math

from tfis.domain.enums import OptionType
from tfis.domain.market_levels import MarketLevels
from tfis.domain.trade_plan import TradePlan


S23_CURRENT_DAY_FSL_TRIGGER_TIME = time(9, 15, 0)
S23_CURRENT_DAY_ORPT_TIME = time(9, 24, 59)
S23_CURRENT_DAY_RC_TIME = time(9, 29, 59)

S23_BULL_CALL_UNIQUE_CODE = "NIFTY_OP_SELL_WK_DIFF_2D_3D"
S23_BULL_PUT_UNIQUE_CODE = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT"
S23_BEAR_CALL_UNIQUE_CODE = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
S23_BEAR_PUT_UNIQUE_CODE = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"

S23_COMMON_PARAMETERS = {
    "strike_buffer_pct": 5.0,
    "ideal_premium_pct": 1.20,
    "minimum_premium_pct": 0.90,
    "entry_discount_pct": 7.50,
}


@dataclass(frozen=True, slots=True)
class CurrentDaySnapshot:
    timestamp: datetime
    spot_low: float
    spot_high: float
    option_low: float
    option_high: float


@dataclass(frozen=True, slots=True)
class CurrentDayFslTrpTriggerResult:
    fsl_trp_missed: bool
    rule_name: str
    compared_value: float
    threshold_stoploss_price: float
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class S23CurrentDayFslTrpInput:
    branch_unique_code: str
    base_trade_plan: TradePlan
    market_levels: MarketLevels
    option_levels: dict[str, float]
    trigger_snapshot_at_0915: CurrentDaySnapshot
    snapshot_at_orpt: CurrentDaySnapshot
    snapshot_at_recalc: CurrentDaySnapshot


@dataclass(frozen=True, slots=True)
class S23CurrentDayFslTrpResult:
    applied: bool
    reason: str
    row_number: int | None
    trigger_result: CurrentDayFslTrpTriggerResult
    effective_option_type: OptionType | None
    recalculated_start_strike: int | None
    recalculated_end_strike: int | None
    recalculated_ideal_premium: float | None
    recalculated_minimum_premium: float | None
    recalculated_entry_price: float | None
    recalculated_stoploss_price: float | None
    entry_override_source_cell: str | None
    lifecycle_start_after: datetime | None
    source_rule: str | None
    unsupported_fields: tuple[str, ...]
    audit_notes: tuple[str, ...]


class S23CurrentDayFslTrpEngine:
    """Workbook-backed S23 current-day FSL/TRP handling for rows 183-188.

    This layer is intentionally:

    - opt-in only
    - separate from the older ORPT missed-entry recalculation path
    - limited to the exact workbook-backed row mappings confirmed for `AB6 OS`
      rows `183-188`

    It must not infer additional branch mappings when the workbook leaves a
    branch blank or only confirms FSL handling.
    """

    TRIGGER_RULE_NAME = "S23_CURRENT_DAY_FSL_TRP_0915_OPTION_HIGH_CHECK_V1"

    def apply(self, handling_input: S23CurrentDayFslTrpInput) -> S23CurrentDayFslTrpResult:
        trigger_result = self._detect_fsl_trp_missed(handling_input)
        branch_code = handling_input.branch_unique_code

        if branch_code == S23_BULL_CALL_UNIQUE_CODE:
            if trigger_result.fsl_trp_missed:
                return self._row_184_bull_call_missed(handling_input, trigger_result)
            return self._row_183_bull_call_not_missed(handling_input, trigger_result)

        if branch_code == S23_BEAR_CALL_UNIQUE_CODE:
            if trigger_result.fsl_trp_missed:
                return self._row_185_bear_call_missed(handling_input, trigger_result)
            return self._unsupported_not_missed_branch(
                handling_input,
                trigger_result,
                reason="bear_call_not_missed_not_confirmed",
                note=(
                    "AB6 OS rows 183-188 do not confirm a dedicated current-day "
                    "Bear/Bear CF Call not-missed row; base trade plan was kept."
                ),
            )

        if branch_code == S23_BULL_PUT_UNIQUE_CODE:
            if trigger_result.fsl_trp_missed:
                return self._row_187_bull_put_missed_fsl_only(
                    handling_input,
                    trigger_result,
                )
            return self._unsupported_not_missed_branch(
                handling_input,
                trigger_result,
                reason="bull_put_not_missed_not_confirmed",
                note=(
                    "AB6 OS rows 183-188 do not confirm a dedicated current-day "
                    "Bull/Bull CF Put not-missed row; base trade plan was kept."
                ),
            )

        if branch_code == S23_BEAR_PUT_UNIQUE_CODE:
            if trigger_result.fsl_trp_missed:
                return self._row_188_bear_put_missed_fsl_only(
                    handling_input,
                    trigger_result,
                )
            return self._row_186_bear_put_not_missed(handling_input, trigger_result)

        return S23CurrentDayFslTrpResult(
            applied=False,
            reason="unsupported_branch",
            row_number=None,
            trigger_result=trigger_result,
            effective_option_type=handling_input.base_trade_plan.option_type,
            recalculated_start_strike=None,
            recalculated_end_strike=None,
            recalculated_ideal_premium=None,
            recalculated_minimum_premium=None,
            recalculated_entry_price=None,
            recalculated_stoploss_price=None,
            entry_override_source_cell=None,
            lifecycle_start_after=None,
            source_rule=None,
            unsupported_fields=(),
            audit_notes=(
                f"Unsupported S23 current-day FSL/TRP branch: {branch_code}",
            ),
        )

    def _detect_fsl_trp_missed(
        self,
        handling_input: S23CurrentDayFslTrpInput,
    ) -> CurrentDayFslTrpTriggerResult:
        compared_value = float(handling_input.trigger_snapshot_at_0915.option_high)
        threshold = float(handling_input.base_trade_plan.stoploss_price)
        missed = compared_value > threshold
        option_type = handling_input.base_trade_plan.option_type
        option_type_label = option_type.value if option_type is not None else "UNKNOWN"
        return CurrentDayFslTrpTriggerResult(
            fsl_trp_missed=missed,
            rule_name=self.TRIGGER_RULE_NAME,
            compared_value=compared_value,
            threshold_stoploss_price=threshold,
            notes=(
                (
                    "Applied workbook FSL/TRP trigger at 09:15:00 using current-day "
                    "option high versus the base stoploss price."
                ),
                (
                    f"Checked {option_type_label} side at "
                    f"{handling_input.trigger_snapshot_at_0915.timestamp.isoformat()}: "
                    "current_day_option_high > stoploss_price."
                ),
            ),
        )

    def _row_183_bull_call_not_missed(
        self,
        handling_input: S23CurrentDayFslTrpInput,
        trigger_result: CurrentDayFslTrpTriggerResult,
    ) -> S23CurrentDayFslTrpResult:
        reference_value = min(
            self._require_market_level(handling_input.market_levels.d3ll, "PRV_3DLL"),
            handling_input.snapshot_at_orpt.spot_low,
        )
        entry_reference = min(
            self._require_option_level(handling_input.option_levels, "OPT_PRV_3DLL"),
            handling_input.snapshot_at_orpt.option_low,
        )
        return S23CurrentDayFslTrpResult(
            applied=True,
            reason="s23_current_day_fsl_trp_row_183_applied",
            row_number=183,
            trigger_result=trigger_result,
            effective_option_type=OptionType.CALL,
            recalculated_start_strike=self._round_down(
                self._pct_above(reference_value, S23_COMMON_PARAMETERS["strike_buffer_pct"])
            ),
            recalculated_end_strike=self._round_down(reference_value) - 1,
            recalculated_ideal_premium=self._pct_of(
                reference_value,
                S23_COMMON_PARAMETERS["ideal_premium_pct"],
            ),
            recalculated_minimum_premium=self._pct_of(
                reference_value,
                S23_COMMON_PARAMETERS["minimum_premium_pct"],
            ),
            recalculated_entry_price=self._pct_below(
                entry_reference,
                S23_COMMON_PARAMETERS["entry_discount_pct"],
            ),
            recalculated_stoploss_price=None,
            entry_override_source_cell="AB6_OS_Z183",
            lifecycle_start_after=handling_input.snapshot_at_orpt.timestamp,
            source_rule="AB6_OS_ROW_183",
            unsupported_fields=("target_price", "stoploss_price"),
            audit_notes=(
                "Row 183 applied exactly as workbook-backed current-day Bull/Bull CF Call not-missed handling.",
                "Used MIN(PRV_3DLL, CDLL_at_ORPT) for current-day strike and premium recalculation.",
                "Used MIN(OPT_PRV_3DLL, OPT_CDLL_at_ORPT) minus 7.50% for the current-day option entry override from AB6_OS_Z183.",
                "Target and stoploss remain inherited from the base trade plan because row 183 does not confirm additional override cells for those fields.",
            ),
        )

    def _row_184_bull_call_missed(
        self,
        handling_input: S23CurrentDayFslTrpInput,
        trigger_result: CurrentDayFslTrpTriggerResult,
    ) -> S23CurrentDayFslTrpResult:
        strike_reference = max(
            self._require_market_level(handling_input.market_levels.d2hh, "PRV_2DHH"),
            handling_input.snapshot_at_recalc.spot_high,
        )
        premium_reference = min(
            self._require_market_level(handling_input.market_levels.d2hh, "PRV_2DHH"),
            handling_input.snapshot_at_recalc.spot_low,
        )
        entry_reference = min(
            self._require_option_level(handling_input.option_levels, "OPT_PRV_2DLL"),
            handling_input.snapshot_at_recalc.option_low,
        )
        return S23CurrentDayFslTrpResult(
            applied=True,
            reason="s23_current_day_fsl_trp_row_184_applied",
            row_number=184,
            trigger_result=trigger_result,
            effective_option_type=OptionType.PUT,
            recalculated_start_strike=self._round_up(
                self._pct_below(strike_reference, S23_COMMON_PARAMETERS["strike_buffer_pct"])
            ),
            recalculated_end_strike=self._round_up(strike_reference) + 1,
            recalculated_ideal_premium=self._pct_of(
                premium_reference,
                S23_COMMON_PARAMETERS["ideal_premium_pct"],
            ),
            recalculated_minimum_premium=self._pct_of(
                premium_reference,
                S23_COMMON_PARAMETERS["minimum_premium_pct"],
            ),
            recalculated_entry_price=self._pct_below(
                entry_reference,
                S23_COMMON_PARAMETERS["entry_discount_pct"],
            ),
            recalculated_stoploss_price=self._pct_above(
                handling_input.snapshot_at_recalc.option_high,
                7.0,
            ),
            entry_override_source_cell="AB6_OS_Z184",
            lifecycle_start_after=handling_input.snapshot_at_recalc.timestamp,
            source_rule="AB6_OS_ROW_184",
            unsupported_fields=("target_price",),
            audit_notes=(
                "Row 184 applied exactly as workbook-directed for Bull/Bull CF Call FSL/TRP missed handling.",
                "Workbook confirmation keeps the Put-side Q/R/S/U/W/Z family intentional for this missed Bull/Bull CF Call branch.",
                "Used MAX(PRV_2DHH, CDHH_at_recalc) for strike range and MIN(PRV_2DHH, CDLL_at_recalc) for premium thresholds.",
                "Used MIN(OPT_PRV_2DLL, OPT_CDLL_at_recalc) minus 7.50% for the current-day option entry override from AB6_OS_Z184.",
                "Used current-day option HH at recalculation time plus 7% for the new FSL.",
                "Target remains inherited because row 184 does not confirm an additional target override cell.",
            ),
        )

    def _row_185_bear_call_missed(
        self,
        handling_input: S23CurrentDayFslTrpInput,
        trigger_result: CurrentDayFslTrpTriggerResult,
    ) -> S23CurrentDayFslTrpResult:
        reference_value = min(
            self._require_market_level(handling_input.market_levels.d2ll, "PRV_2DLL"),
            handling_input.snapshot_at_recalc.spot_low,
        )
        entry_reference = min(
            self._require_option_level(handling_input.option_levels, "OPT_PRV_2DLL"),
            handling_input.snapshot_at_recalc.option_low,
        )
        return S23CurrentDayFslTrpResult(
            applied=True,
            reason="s23_current_day_fsl_trp_row_185_applied",
            row_number=185,
            trigger_result=trigger_result,
            effective_option_type=OptionType.CALL,
            recalculated_start_strike=self._round_down(
                self._pct_above(reference_value, S23_COMMON_PARAMETERS["strike_buffer_pct"])
            ),
            recalculated_end_strike=self._round_down(reference_value) - 1,
            recalculated_ideal_premium=self._pct_of(
                reference_value,
                S23_COMMON_PARAMETERS["ideal_premium_pct"],
            ),
            recalculated_minimum_premium=self._pct_of(
                reference_value,
                S23_COMMON_PARAMETERS["minimum_premium_pct"],
            ),
            recalculated_entry_price=self._pct_below(
                entry_reference,
                S23_COMMON_PARAMETERS["entry_discount_pct"],
            ),
            recalculated_stoploss_price=self._pct_above(
                handling_input.snapshot_at_recalc.option_high,
                10.0,
            ),
            entry_override_source_cell="AB6_OS_Z185",
            lifecycle_start_after=handling_input.snapshot_at_recalc.timestamp,
            source_rule="AB6_OS_ROW_185",
            unsupported_fields=("target_price",),
            audit_notes=(
                "Row 185 applied exactly as workbook-backed Bear/Bear CF Call FSL/TRP missed handling.",
                "Used MIN(PRV_2DLL, CDLL_at_recalc) for current-day strike and premium recalculation.",
                "Used MIN(OPT_PRV_2DLL, OPT_CDLL_at_recalc) minus 7.50% for the current-day option entry override from AB6_OS_Z185.",
                "Used current-day option HH at recalculation time plus 10% for the new FSL.",
                "Target remains inherited because row 185 does not confirm an additional target override cell.",
            ),
        )

    def _row_186_bear_put_not_missed(
        self,
        handling_input: S23CurrentDayFslTrpInput,
        trigger_result: CurrentDayFslTrpTriggerResult,
    ) -> S23CurrentDayFslTrpResult:
        strike_reference = max(
            self._require_market_level(handling_input.market_levels.d3hh, "PRV_3DHH"),
            handling_input.snapshot_at_orpt.spot_high,
        )
        premium_reference = min(
            self._require_market_level(handling_input.market_levels.d3hh, "PRV_3DHH"),
            handling_input.snapshot_at_orpt.spot_low,
        )
        entry_reference = min(
            self._require_option_level(handling_input.option_levels, "OPT_PRV_3DLL"),
            handling_input.snapshot_at_orpt.option_low,
        )
        return S23CurrentDayFslTrpResult(
            applied=True,
            reason="s23_current_day_fsl_trp_row_186_applied",
            row_number=186,
            trigger_result=trigger_result,
            effective_option_type=OptionType.PUT,
            recalculated_start_strike=self._round_up(
                self._pct_below(strike_reference, S23_COMMON_PARAMETERS["strike_buffer_pct"])
            ),
            recalculated_end_strike=self._round_up(strike_reference) + 1,
            recalculated_ideal_premium=self._pct_of(
                premium_reference,
                S23_COMMON_PARAMETERS["ideal_premium_pct"],
            ),
            recalculated_minimum_premium=self._pct_of(
                premium_reference,
                S23_COMMON_PARAMETERS["minimum_premium_pct"],
            ),
            recalculated_entry_price=self._pct_below(
                entry_reference,
                S23_COMMON_PARAMETERS["entry_discount_pct"],
            ),
            recalculated_stoploss_price=None,
            entry_override_source_cell="AB6_OS_Z186",
            lifecycle_start_after=handling_input.snapshot_at_orpt.timestamp,
            source_rule="AB6_OS_ROW_186",
            unsupported_fields=("target_price", "stoploss_price"),
            audit_notes=(
                "Row 186 applied exactly as workbook-backed Put Sell SL not-missed handling.",
                "Used MAX(PRV_3DHH, CDHH_at_ORPT) for strike range and MIN(PRV_3DHH, CDLL_at_ORPT) for premium thresholds.",
                "Used MIN(OPT_PRV_3DLL, OPT_CDLL_at_ORPT) minus 7.50% for the current-day option entry override from AB6_OS_Z186.",
                "Target and stoploss remain inherited from the base trade plan because row 186 does not confirm additional override cells for those fields.",
            ),
        )

    def _row_187_bull_put_missed_fsl_only(
        self,
        handling_input: S23CurrentDayFslTrpInput,
        trigger_result: CurrentDayFslTrpTriggerResult,
    ) -> S23CurrentDayFslTrpResult:
        return S23CurrentDayFslTrpResult(
            applied=True,
            reason="s23_current_day_fsl_trp_row_187_fsl_only_applied",
            row_number=187,
            trigger_result=trigger_result,
            effective_option_type=OptionType.PUT,
            recalculated_start_strike=None,
            recalculated_end_strike=None,
            recalculated_ideal_premium=None,
            recalculated_minimum_premium=None,
            recalculated_entry_price=None,
            recalculated_stoploss_price=self._pct_above(
                handling_input.snapshot_at_recalc.option_high,
                10.0,
            ),
            entry_override_source_cell=None,
            lifecycle_start_after=handling_input.snapshot_at_recalc.timestamp,
            source_rule="AB6_OS_ROW_187",
            unsupported_fields=(
                "start_strike",
                "end_strike",
                "ideal_premium",
                "minimum_premium",
                "entry_price",
                "target_price",
            ),
            audit_notes=(
                "Row 187 applied as FSL-only exactly as workbook-backed.",
                "R/S/U/W/Z are blank in the workbook, so strike, premium, and entry recalculation must not be inferred.",
                "Used current-day option HH at recalculation time plus 10% for the new FSL.",
                "Workbook note: 'When You Call And Put Position is Exited'.",
            ),
        )

    def _row_188_bear_put_missed_fsl_only(
        self,
        handling_input: S23CurrentDayFslTrpInput,
        trigger_result: CurrentDayFslTrpTriggerResult,
    ) -> S23CurrentDayFslTrpResult:
        return S23CurrentDayFslTrpResult(
            applied=True,
            reason="s23_current_day_fsl_trp_row_188_fsl_only_applied",
            row_number=188,
            trigger_result=trigger_result,
            effective_option_type=OptionType.PUT,
            recalculated_start_strike=None,
            recalculated_end_strike=None,
            recalculated_ideal_premium=None,
            recalculated_minimum_premium=None,
            recalculated_entry_price=None,
            recalculated_stoploss_price=self._pct_above(
                handling_input.snapshot_at_recalc.option_high,
                7.0,
            ),
            entry_override_source_cell=None,
            lifecycle_start_after=handling_input.snapshot_at_recalc.timestamp,
            source_rule="AB6_OS_ROW_188",
            unsupported_fields=(
                "start_strike",
                "end_strike",
                "ideal_premium",
                "minimum_premium",
                "entry_price",
                "target_price",
            ),
            audit_notes=(
                "Row 188 applied as FSL-only exactly as workbook-backed.",
                "R/S/U/W/Z are blank in the workbook, so strike, premium, and entry recalculation must not be inferred.",
                "Used current-day option HH at recalculation time plus 7% for the new FSL.",
                "Workbook note: 'This is Only Applicable for Same Day'.",
            ),
        )

    def _unsupported_not_missed_branch(
        self,
        handling_input: S23CurrentDayFslTrpInput,
        trigger_result: CurrentDayFslTrpTriggerResult,
        *,
        reason: str,
        note: str,
    ) -> S23CurrentDayFslTrpResult:
        return S23CurrentDayFslTrpResult(
            applied=False,
            reason=reason,
            row_number=None,
            trigger_result=trigger_result,
            effective_option_type=handling_input.base_trade_plan.option_type,
            recalculated_start_strike=None,
            recalculated_end_strike=None,
            recalculated_ideal_premium=None,
            recalculated_minimum_premium=None,
            recalculated_entry_price=None,
            recalculated_stoploss_price=None,
            entry_override_source_cell=None,
            lifecycle_start_after=None,
            source_rule=None,
            unsupported_fields=(),
            audit_notes=(note,),
        )

    def _require_market_level(self, value: float | None, alias: str) -> float:
        if value is None:
            raise ValueError(f"Missing market level for S23 current-day FSL/TRP: {alias}")
        return float(value)

    def _require_option_level(self, option_levels: dict[str, float], alias: str) -> float:
        value = option_levels.get(alias)
        if value is None:
            raise ValueError(
                f"Missing option reference for S23 current-day FSL/TRP: {alias}"
            )
        return float(value)

    def _pct_of(self, base_value: float, pct: float) -> float:
        return float(base_value) * (float(pct) / 100.0)

    def _pct_above(self, base_value: float, pct: float) -> float:
        return float(base_value) * (1.0 + (float(pct) / 100.0))

    def _pct_below(self, base_value: float, pct: float) -> float:
        return float(base_value) * (1.0 - (float(pct) / 100.0))

    def _round_down(self, value: float) -> int:
        return int(math.floor(float(value)))

    def _round_up(self, value: float) -> int:
        return int(math.ceil(float(value)))
