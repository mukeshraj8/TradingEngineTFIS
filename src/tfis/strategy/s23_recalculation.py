from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.domain.market_levels import MarketLevels
from tfis.domain.trade_plan import TradePlan


S23_BULL_CALL_UNIQUE_CODE = "NIFTY_OP_SELL_WK_DIFF_2D_3D"
S23_BULL_PUT_UNIQUE_CODE = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT"
S23_BEAR_CALL_UNIQUE_CODE = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
S23_BEAR_PUT_UNIQUE_CODE = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"


@dataclass(frozen=True, slots=True)
class IntradaySnapshot:
    timestamp: datetime
    spot_low: float
    spot_high: float
    option_low: float
    option_high: float


@dataclass(frozen=True, slots=True)
class RecalculationInput:
    branch_unique_code: str
    option_type: OptionType
    monthly_status: MonthlyStatus
    base_trade_plan: TradePlan
    market_levels: MarketLevels
    option_levels: dict[str, float]
    parameters: dict[str, float]
    intraday_snapshot_at_orpt: IntradaySnapshot
    intraday_snapshot_at_recalc: IntradaySnapshot
    entry_missed: bool


@dataclass(frozen=True, slots=True)
class RecalculationResult:
    recalculated: bool
    reason: str
    recalculated_start_strike: int | None
    recalculated_end_strike: int | None
    recalculated_ideal_premium: float | None
    recalculated_minimum_premium: float | None
    recalculated_entry_price: float | None
    source_rule: str | None
    audit_notes: tuple[str, ...]


class S23RecalculationEngine:
    """Diagnostic missed-entry recalculation helper for the canonical S23 branches.

    This layer is intentionally separate from:

    - base strategy formulas
    - monthly-status classification
    - branch selection
    - historical backtest defaults

    It only computes high-confidence recalculated candidate values when the
    caller explicitly marks `entry_missed=True`.
    """

    def recalculate(self, recalculation_input: RecalculationInput) -> RecalculationResult:
        if not recalculation_input.entry_missed:
            return RecalculationResult(
                recalculated=False,
                reason="entry_not_missed",
                recalculated_start_strike=None,
                recalculated_end_strike=None,
                recalculated_ideal_premium=None,
                recalculated_minimum_premium=None,
                recalculated_entry_price=None,
                source_rule=None,
                audit_notes=(
                    "Entry was not marked as missed, so no recalculation was applied.",
                ),
            )

        branch_code = recalculation_input.branch_unique_code
        if branch_code == S23_BULL_CALL_UNIQUE_CODE:
            return self._recalculate_bull_call(recalculation_input)
        if branch_code == S23_BEAR_CALL_UNIQUE_CODE:
            return self._recalculate_bear_call(recalculation_input)
        if branch_code == S23_BULL_PUT_UNIQUE_CODE:
            return self._recalculate_bull_put(recalculation_input)
        if branch_code == S23_BEAR_PUT_UNIQUE_CODE:
            return self._recalculate_bear_put(recalculation_input)

        return RecalculationResult(
            recalculated=False,
            reason="unsupported_branch",
            recalculated_start_strike=None,
            recalculated_end_strike=None,
            recalculated_ideal_premium=None,
            recalculated_minimum_premium=None,
            recalculated_entry_price=None,
            source_rule=None,
            audit_notes=(
                f"Unsupported S23 recalculation branch: {branch_code}",
            ),
        )

    def _recalculate_bull_call(
        self,
        recalculation_input: RecalculationInput,
    ) -> RecalculationResult:
        parameters = self._require_parameters(recalculation_input)
        reference_value = min(
            self._require_market_level(recalculation_input.market_levels.d3ll, "PRV_3DLL"),
            recalculation_input.intraday_snapshot_at_recalc.spot_low,
        )
        entry_reference = min(
            self._require_option_level(recalculation_input.option_levels, "OPT_PRV_3DLL"),
            recalculation_input.intraday_snapshot_at_recalc.option_low,
        )
        return RecalculationResult(
            recalculated=True,
            reason="s23_bull_call_recalculated",
            recalculated_start_strike=self._round_down(
                self._pct_above(reference_value, parameters["strike_buffer_pct"])
            ),
            recalculated_end_strike=self._round_down(reference_value) - 1,
            recalculated_ideal_premium=self._pct_of(
                reference_value,
                parameters["ideal_premium_pct"],
            ),
            recalculated_minimum_premium=self._pct_of(
                reference_value,
                parameters["minimum_premium_pct"],
            ),
            recalculated_entry_price=self._pct_below(
                entry_reference,
                parameters["entry_discount_pct"],
            ),
            source_rule="S23_BULL_CALL_RECALC_V1",
            audit_notes=(
                "Used MIN(PRV_3DLL, recalc_spot_low) for strike and premium recalculation.",
                "Used MIN(OPT_PRV_3DLL, recalc_option_low) for recalculated entry.",
            ),
        )

    def _recalculate_bear_call(
        self,
        recalculation_input: RecalculationInput,
    ) -> RecalculationResult:
        parameters = self._require_parameters(recalculation_input)
        reference_value = min(
            self._require_market_level(recalculation_input.market_levels.d2ll, "PRV_2DLL"),
            recalculation_input.intraday_snapshot_at_recalc.spot_low,
        )
        entry_reference = min(
            self._require_option_level(recalculation_input.option_levels, "OPT_PRV_2DLL"),
            recalculation_input.intraday_snapshot_at_recalc.option_low,
        )
        return RecalculationResult(
            recalculated=True,
            reason="s23_bear_call_recalculated",
            recalculated_start_strike=self._round_down(
                self._pct_above(reference_value, parameters["strike_buffer_pct"])
            ),
            recalculated_end_strike=self._round_down(reference_value) - 1,
            recalculated_ideal_premium=self._pct_of(
                reference_value,
                parameters["ideal_premium_pct"],
            ),
            recalculated_minimum_premium=self._pct_of(
                reference_value,
                parameters["minimum_premium_pct"],
            ),
            recalculated_entry_price=self._pct_below(
                entry_reference,
                parameters["entry_discount_pct"],
            ),
            source_rule="S23_BEAR_CALL_RECALC_V1",
            audit_notes=(
                "Used MIN(PRV_2DLL, recalc_spot_low) for strike and premium recalculation.",
                "Used MIN(OPT_PRV_2DLL, recalc_option_low) for recalculated entry.",
            ),
        )

    def _recalculate_bull_put(
        self,
        recalculation_input: RecalculationInput,
    ) -> RecalculationResult:
        parameters = self._require_parameters(recalculation_input)
        strike_reference = max(
            self._require_market_level(recalculation_input.market_levels.d2hh, "PRV_2DHH"),
            recalculation_input.intraday_snapshot_at_recalc.spot_high,
        )
        premium_reference = min(
            self._require_market_level(recalculation_input.market_levels.d2hh, "PRV_2DHH"),
            recalculation_input.intraday_snapshot_at_recalc.spot_low,
        )
        entry_reference = min(
            self._require_option_level(recalculation_input.option_levels, "OPT_PRV_2DLL"),
            recalculation_input.intraday_snapshot_at_recalc.option_low,
        )
        return RecalculationResult(
            recalculated=True,
            reason="s23_bull_put_recalculated",
            recalculated_start_strike=self._round_up(
                self._pct_below(strike_reference, parameters["strike_buffer_pct"])
            ),
            recalculated_end_strike=self._round_up(strike_reference) + 1,
            recalculated_ideal_premium=self._pct_of(
                premium_reference,
                parameters["ideal_premium_pct"],
            ),
            recalculated_minimum_premium=self._pct_of(
                premium_reference,
                parameters["minimum_premium_pct"],
            ),
            recalculated_entry_price=self._pct_below(
                entry_reference,
                parameters["entry_discount_pct"],
            ),
            source_rule="S23_BULL_PUT_RECALC_V1",
            audit_notes=(
                "Used MAX(PRV_2DHH, recalc_spot_high) for recalculated strike range.",
                "Used MIN(PRV_2DHH, recalc_spot_low) for recalculated ideal and minimum premium.",
                "Used MIN(OPT_PRV_2DLL, recalc_option_low) for recalculated entry.",
            ),
        )

    def _recalculate_bear_put(
        self,
        recalculation_input: RecalculationInput,
    ) -> RecalculationResult:
        parameters = self._require_parameters(recalculation_input)
        strike_reference = max(
            self._require_market_level(recalculation_input.market_levels.d3hh, "PRV_3DHH"),
            recalculation_input.intraday_snapshot_at_recalc.spot_high,
        )
        premium_reference = min(
            self._require_market_level(recalculation_input.market_levels.d3hh, "PRV_3DHH"),
            recalculation_input.intraday_snapshot_at_recalc.spot_low,
        )
        entry_reference = min(
            self._require_option_level(recalculation_input.option_levels, "OPT_PRV_3DLL"),
            recalculation_input.intraday_snapshot_at_recalc.option_low,
        )
        return RecalculationResult(
            recalculated=True,
            reason="s23_bear_put_recalculated",
            recalculated_start_strike=self._round_up(
                self._pct_below(strike_reference, parameters["strike_buffer_pct"])
            ),
            recalculated_end_strike=self._round_up(strike_reference) + 1,
            recalculated_ideal_premium=self._pct_of(
                premium_reference,
                parameters["ideal_premium_pct"],
            ),
            recalculated_minimum_premium=self._pct_of(
                premium_reference,
                parameters["minimum_premium_pct"],
            ),
            recalculated_entry_price=self._pct_below(
                entry_reference,
                parameters["entry_discount_pct"],
            ),
            source_rule="S23_BEAR_PUT_RECALC_V1",
            audit_notes=(
                "Used MAX(PRV_3DHH, recalc_spot_high) for recalculated strike range.",
                "Used MIN(PRV_3DHH, recalc_spot_low) for recalculated ideal and minimum premium.",
                "Used MIN(OPT_PRV_3DLL, recalc_option_low) for recalculated entry.",
            ),
        )

    def _require_market_level(self, value: float | None, alias: str) -> float:
        if value is None:
            raise ValueError(f"Missing market level for recalculation: {alias}")
        return float(value)

    def _require_option_level(self, option_levels: dict[str, float], alias: str) -> float:
        value = option_levels.get(alias)
        if value is None:
            raise ValueError(f"Missing option reference for recalculation: {alias}")
        return float(value)

    def _require_parameters(self, recalculation_input: RecalculationInput) -> dict[str, float]:
        required = (
            "strike_buffer_pct",
            "ideal_premium_pct",
            "minimum_premium_pct",
            "entry_discount_pct",
        )
        missing = tuple(name for name in required if name not in recalculation_input.parameters)
        if missing:
            raise ValueError(
                "Missing S23 recalculation parameter(s): " + ", ".join(missing)
            )
        return recalculation_input.parameters

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
