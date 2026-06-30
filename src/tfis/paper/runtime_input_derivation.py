from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import json
from pathlib import Path
import re
from typing import Any

from tfis.domain import MarketLevels, StrategyRule
from tfis.formulas import FormulaEngine
from tfis.market_data import UnderlyingHistoryBar
from tfis.monthly_status import (
    MonthlyStatusHistoricalBar,
    MonthlyStatusEngine,
    MonthlyStatusLookbackResolver,
    MonthlyStatusLookbackWindow,
    MonthlyStatusReferenceLevels,
    MonthlyStatusResolutionResult,
    MonthlyStatusResult,
    build_monthly_weekly_context_lookback_windows,
)
from tfis.rules import validate_s23_strategy_rule_matches_matrix

from .live_prelude import (
    S23PaperPreludeSessionContext,
    S23PaperSnapshotInput,
)
from .models import SnapshotLabel, UnderlyingQuoteEvent


class S23RuntimeInputDerivationError(RuntimeError):
    """Raised when TFIS cannot derive S23 runtime inputs safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class S23MonthlyStatusReferencePacket:
    PMH: float
    PML: float
    CMH: float
    CML: float
    PWH: float
    PWL: float
    CWH: float
    CWL: float


@dataclass(frozen=True, slots=True)
class S23MarketReferencePacket:
    d2hh: float | None = None
    d2ll: float | None = None
    d3hh: float | None = None
    d3ll: float | None = None
    d4hh: float | None = None
    d4ll: float | None = None


@dataclass(frozen=True, slots=True)
class S23DecisionReferencePacket:
    instrument_group: str
    monthly_status_levels: S23MonthlyStatusReferencePacket
    market_reference_levels: S23MarketReferencePacket
    option_reference_values: dict[str, float]
    lots: int
    quantity: int
    strategy_branch: str | None = None
    source_workbook_rule: str | None = None
    workbook_row_number: int | None = None
    fsl_price: float | None = None
    monthly_status_source: str = "tfis_reference_packet"
    monthly_status_threshold_version: str = "v1"
    runtime_value_overrides: dict[str, float] | None = None
    monthly_status_reference_date: date | None = None


@dataclass(frozen=True, slots=True)
class S23DerivedRuntimeInputs:
    monthly_status_result: MonthlyStatusResult
    monthly_status_resolution: MonthlyStatusResolutionResult
    market_levels: MarketLevels
    runtime_values: dict[str, float]
    snapshots: tuple[S23PaperSnapshotInput, ...]
    required_market_aliases: tuple[str, ...]
    required_option_aliases: tuple[str, ...]
    checkpoint_labels: tuple[str, ...]


_FORMULA_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CHECKPOINT_CANDLE_STARTS = {
    SnapshotLabel.AT_0915: (time(9, 14), time(9, 15)),
    SnapshotLabel.ORPT: (time(9, 24),),
    SnapshotLabel.RC: (time(9, 29),),
}
class S23RuntimeInputDeriver:
    def __init__(
        self,
        *,
        monthly_status_engine: MonthlyStatusEngine | None = None,
        monthly_status_lookback_resolver: MonthlyStatusLookbackResolver | None = None,
    ) -> None:
        self._monthly_status_engine = monthly_status_engine or MonthlyStatusEngine()
        self._monthly_status_lookback_resolver = (
            monthly_status_lookback_resolver
            or MonthlyStatusLookbackResolver(
                monthly_status_engine=self._monthly_status_engine
            )
        )

    def derive(
        self,
        *,
        strategy_rule: StrategyRule,
        reference_packet: S23DecisionReferencePacket,
        underlying_quote: UnderlyingQuoteEvent,
        underlying_bars: tuple[UnderlyingHistoryBar, ...],
        daily_bars: tuple[UnderlyingHistoryBar, ...] | None,
        session_context: S23PaperPreludeSessionContext,
        required_snapshot_labels: tuple[SnapshotLabel, ...] | None = None,
    ) -> S23DerivedRuntimeInputs:
        self._validate_scope(strategy_rule, reference_packet, session_context, underlying_quote)
        required_market_aliases = self._required_market_aliases(strategy_rule)
        required_option_aliases = self._required_option_aliases(strategy_rule)
        snapshots = self._derive_snapshots(
            underlying_bars=underlying_bars,
            session_context=session_context,
            required_snapshot_labels=required_snapshot_labels,
        )
        market_levels = self._build_market_levels(
            reference_levels=reference_packet.market_reference_levels,
            snapshots=snapshots,
            required_market_aliases=required_market_aliases,
        )
        runtime_values = self._build_runtime_values(
            reference_packet=reference_packet,
            required_option_aliases=required_option_aliases,
        )
        self._inject_entry_runtime_value(
            strategy_rule=strategy_rule,
            market_levels=market_levels,
            runtime_values=runtime_values,
        )
        monthly_status_price = self._resolve_monthly_status_price(
            snapshots=snapshots,
            fallback_price=underlying_quote.ltp,
        )
        monthly_status_resolution = self._classify_monthly_status(
            reference_packet=reference_packet,
            current_price=monthly_status_price,
            daily_bars=daily_bars or (),
            session_context=session_context,
            snapshots=snapshots,
        )
        return S23DerivedRuntimeInputs(
            monthly_status_result=monthly_status_resolution.resolved_result,
            monthly_status_resolution=monthly_status_resolution,
            market_levels=market_levels,
            runtime_values=runtime_values,
            snapshots=snapshots,
            required_market_aliases=required_market_aliases,
            required_option_aliases=required_option_aliases,
            checkpoint_labels=tuple(item.snapshot_label.value for item in snapshots),
        )

    def _validate_scope(
        self,
        strategy_rule: StrategyRule,
        reference_packet: S23DecisionReferencePacket,
        session_context: S23PaperPreludeSessionContext,
        underlying_quote: UnderlyingQuoteEvent,
    ) -> None:
        if strategy_rule.strategy_code != "S23":
            raise S23RuntimeInputDerivationError(
                "UNSUPPORTED_STRATEGY",
                "Runtime derivation is currently limited to S23.",
            )
        matrix_mismatches = validate_s23_strategy_rule_matches_matrix(strategy_rule)
        if matrix_mismatches:
            raise S23RuntimeInputDerivationError(
                "S23_RULE_MATRIX_MISMATCH",
                "Loaded S23 strategy rule does not match the corrected rule-sheet matrix: "
                + "; ".join(matrix_mismatches),
            )
        if strategy_rule.symbol != "NIFTY":
            raise S23RuntimeInputDerivationError(
                "UNSUPPORTED_SYMBOL",
                "Runtime derivation is currently limited to NIFTY.",
            )
        if underlying_quote.symbol != "NIFTY":
            raise S23RuntimeInputDerivationError(
                "UNDERLYING_SYMBOL_MISMATCH",
                "Underlying quote must be normalized to NIFTY.",
            )
        if underlying_quote.envelope.session_date != session_context.session_date:
            raise S23RuntimeInputDerivationError(
                "UNDERLYING_SESSION_DATE_MISMATCH",
                "Underlying quote session date does not match the TFIS session context.",
            )
        if reference_packet.lots <= 0 or reference_packet.quantity <= 0:
            raise S23RuntimeInputDerivationError(
                "INVALID_POSITION_SIZING",
                "Reference packet must contain positive lots and quantity.",
            )
        if (underlying_quote.ltp or 0.0) <= 0.0:
            raise S23RuntimeInputDerivationError(
                "MISSING_CURRENT_PRICE",
                "Underlying quote LTP is required to classify monthly status.",
            )

    def _classify_monthly_status(
        self,
        *,
        reference_packet: S23DecisionReferencePacket,
        current_price: float | None,
        daily_bars: tuple[UnderlyingHistoryBar, ...],
        session_context: S23PaperPreludeSessionContext,
        snapshots: tuple[S23PaperSnapshotInput, ...],
    ) -> MonthlyStatusResolutionResult:
        if current_price is None:
            raise S23RuntimeInputDerivationError(
                "MISSING_CURRENT_PRICE",
                "Current underlying price is required for monthly status classification.",
            )
        levels = MonthlyStatusReferenceLevels(
            PMH=reference_packet.monthly_status_levels.PMH,
            PML=reference_packet.monthly_status_levels.PML,
            CMH=reference_packet.monthly_status_levels.CMH,
            CML=reference_packet.monthly_status_levels.CML,
            PWH=reference_packet.monthly_status_levels.PWH,
            PWL=reference_packet.monthly_status_levels.PWL,
            CWH=reference_packet.monthly_status_levels.CWH,
            CWL=reference_packet.monthly_status_levels.CWL,
            current_price=float(current_price),
        )
        reference_timestamp = self._resolve_monthly_status_timestamp(
            session_context=session_context,
            snapshots=snapshots,
        )
        try:
            return self._monthly_status_lookback_resolver.resolve(
                reference_packet.instrument_group.strip().lower(),
                levels,
                current_reference_timestamp=reference_timestamp,
                lookback_windows=self._build_live_lookback_windows(
                    daily_bars=daily_bars,
                    current_reference_timestamp=reference_timestamp,
                ),
            )
        except KeyError as exc:
            raise S23RuntimeInputDerivationError(
                "MISSING_MONTHLY_STATUS_THRESHOLDS",
                str(exc),
            ) from exc

    def _derive_snapshots(
        self,
        *,
        underlying_bars: tuple[UnderlyingHistoryBar, ...],
        session_context: S23PaperPreludeSessionContext,
        required_snapshot_labels: tuple[SnapshotLabel, ...] | None = None,
    ) -> tuple[S23PaperSnapshotInput, ...]:
        if not underlying_bars:
            raise S23RuntimeInputDerivationError(
                "UNDERLYING_BARS_MISSING",
                "Morning underlying bars are required to derive TFIS checkpoints.",
            )
        required_labels = set(required_snapshot_labels or tuple(_CHECKPOINT_CANDLE_STARTS))
        bar_index = {
            bar.bar_start.timetz().replace(tzinfo=None): bar
            for bar in underlying_bars
            if bar.bar_start.date() == session_context.session_date
        }
        snapshots: list[S23PaperSnapshotInput] = []
        missing_labels: list[str] = []
        for label, candle_starts in _CHECKPOINT_CANDLE_STARTS.items():
            bar = None
            for candle_start in candle_starts:
                bar = bar_index.get(candle_start)
                if bar is not None:
                    break
            if bar is None:
                if label in required_labels:
                    missing_labels.append(label.value)
                continue
            snapshots.append(
                S23PaperSnapshotInput(
                    snapshot_label=label,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    bar_start=bar.bar_start,
                    bar_end=bar.bar_end,
                    complete=True,
                )
            )
        if missing_labels:
            raise S23RuntimeInputDerivationError(
                "CHECKPOINT_BARS_MISSING",
                "Missing required TFIS checkpoint bars: " + ", ".join(missing_labels),
            )
        return tuple(snapshots)

    def _build_market_levels(
        self,
        *,
        reference_levels: S23MarketReferencePacket,
        snapshots: tuple[S23PaperSnapshotInput, ...],
        required_market_aliases: tuple[str, ...],
    ) -> MarketLevels:
        current_day_high = max(
            float(snapshot.high)
            for snapshot in snapshots
            if snapshot.high is not None
        )
        current_day_low = min(
            float(snapshot.low)
            for snapshot in snapshots
            if snapshot.low is not None
        )
        market_levels = MarketLevels(
            d2hh=reference_levels.d2hh,
            d2ll=reference_levels.d2ll,
            d3hh=reference_levels.d3hh,
            d3ll=reference_levels.d3ll,
            d4hh=reference_levels.d4hh,
            d4ll=reference_levels.d4ll,
            current_day_high=current_day_high,
            current_day_low=current_day_low,
        )
        missing = [
            alias
            for alias in required_market_aliases
            if getattr(market_levels, FormulaEngine.ALIAS_TO_MARKET_LEVEL[alias]) is None
        ]
        if missing:
            raise S23RuntimeInputDerivationError(
                "MISSING_MARKET_REFERENCE_LEVELS",
                "Missing required TFIS market reference aliases: " + ", ".join(missing),
            )
        return market_levels

    def _build_runtime_values(
        self,
        *,
        reference_packet: S23DecisionReferencePacket,
        required_option_aliases: tuple[str, ...],
    ) -> dict[str, float]:
        runtime_values: dict[str, float] = {}
        for key, value in reference_packet.option_reference_values.items():
            runtime_values[str(key).upper()] = float(value)
        for key, value in (reference_packet.runtime_value_overrides or {}).items():
            runtime_values[str(key).upper()] = float(value)
        missing = [alias for alias in required_option_aliases if alias not in runtime_values]
        if missing:
            raise S23RuntimeInputDerivationError(
                "MISSING_OPTION_REFERENCE_VALUES",
                "Missing required TFIS option reference aliases: " + ", ".join(missing),
            )
        return runtime_values

    def _inject_entry_runtime_value(
        self,
        *,
        strategy_rule: StrategyRule,
        market_levels: MarketLevels,
        runtime_values: dict[str, float],
    ) -> None:
        needs_entry = any(
            "ENTRY" in _FORMULA_TOKEN_PATTERN.findall(formula.upper())
            for formula in (
                strategy_rule.target_formula,
                strategy_rule.stoploss_formula,
            )
        )
        if not needs_entry or "ENTRY" in runtime_values:
            return
        runtime_values["ENTRY"] = FormulaEngine().evaluate(
            strategy_rule.entry_formula,
            market_levels=market_levels,
            runtime_values=runtime_values,
            parameters=strategy_rule.parameters,
        )

    def _required_market_aliases(self, strategy_rule: StrategyRule) -> tuple[str, ...]:
        required: set[str] = set()
        for formula in self._rule_formulas(strategy_rule):
            for token in _FORMULA_TOKEN_PATTERN.findall(formula.upper()):
                if token in FormulaEngine.ALIAS_TO_MARKET_LEVEL:
                    required.add(token)
        return tuple(sorted(required))

    def _required_option_aliases(self, strategy_rule: StrategyRule) -> tuple[str, ...]:
        required: set[str] = set()
        for formula in self._rule_formulas(strategy_rule):
            for token in _FORMULA_TOKEN_PATTERN.findall(formula.upper()):
                if token in FormulaEngine.OPTION_ALIAS_NAMES:
                    required.add(token)
        return tuple(sorted(required))

    def _resolve_monthly_status_price(
        self,
        *,
        snapshots: tuple[S23PaperSnapshotInput, ...],
        fallback_price: float | None,
    ) -> float | None:
        latest_snapshot = max(snapshots, key=lambda item: item.bar_end, default=None)
        if latest_snapshot is not None and latest_snapshot.close is not None:
            return float(latest_snapshot.close)
        return fallback_price

    def _resolve_monthly_status_timestamp(
        self,
        *,
        session_context: S23PaperPreludeSessionContext,
        snapshots: tuple[S23PaperSnapshotInput, ...],
    ) -> datetime:
        latest_snapshot = max(snapshots, key=lambda item: item.bar_end, default=None)
        if latest_snapshot is not None:
            return latest_snapshot.bar_end
        return session_context.generated_at

    def _build_live_lookback_windows(
        self,
        *,
        daily_bars: tuple[UnderlyingHistoryBar, ...],
        current_reference_timestamp: datetime,
    ) -> tuple[MonthlyStatusLookbackWindow, ...]:
        historical_bars = tuple(
            MonthlyStatusHistoricalBar(
                timestamp=bar.bar_end,
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
            )
            for bar in daily_bars
            if None not in (bar.high, bar.low, bar.close)
        )
        return build_monthly_weekly_context_lookback_windows(
            historical_bars=historical_bars,
            current_reference_timestamp=current_reference_timestamp,
        )

    @staticmethod
    def _rule_formulas(strategy_rule: StrategyRule) -> tuple[str, ...]:
        return (
            strategy_rule.start_strike_formula,
            strategy_rule.end_strike_formula,
            strategy_rule.ideal_premium_formula,
            strategy_rule.minimum_premium_formula,
            strategy_rule.entry_formula,
            strategy_rule.target_formula,
            strategy_rule.stoploss_formula,
        )


def load_s23_decision_reference_packet(path: str | Path) -> S23DecisionReferencePacket:
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise S23RuntimeInputDerivationError(
            "INVALID_REFERENCE_PACKET",
            f"S23 decision reference packet must be a JSON object: {target}",
        )
    monthly_status_levels = payload.get("monthly_status_levels") or {}
    market_reference_levels = payload.get("market_reference_levels") or {}
    return S23DecisionReferencePacket(
        instrument_group=str(payload.get("instrument_group", "NIFTY")),
        monthly_status_levels=S23MonthlyStatusReferencePacket(
            PMH=float(monthly_status_levels["PMH"]),
            PML=float(monthly_status_levels["PML"]),
            CMH=float(monthly_status_levels["CMH"]),
            CML=float(monthly_status_levels["CML"]),
            PWH=float(monthly_status_levels["PWH"]),
            PWL=float(monthly_status_levels["PWL"]),
            CWH=float(monthly_status_levels["CWH"]),
            CWL=float(monthly_status_levels["CWL"]),
        ),
        market_reference_levels=S23MarketReferencePacket(
            d2hh=_optional_float(market_reference_levels.get("d2hh")),
            d2ll=_optional_float(market_reference_levels.get("d2ll")),
            d3hh=_optional_float(market_reference_levels.get("d3hh")),
            d3ll=_optional_float(market_reference_levels.get("d3ll")),
            d4hh=_optional_float(market_reference_levels.get("d4hh")),
            d4ll=_optional_float(market_reference_levels.get("d4ll")),
        ),
        option_reference_values={
            str(key).upper(): float(value)
            for key, value in dict(payload.get("option_reference_values") or {}).items()
        },
        lots=int(payload["lots"]),
        quantity=int(payload["quantity"]),
        strategy_branch=_optional_text(payload.get("strategy_branch")),
        source_workbook_rule=_optional_text(payload.get("source_workbook_rule")),
        workbook_row_number=_optional_int(payload.get("workbook_row_number")),
        fsl_price=_optional_float(payload.get("fsl_price")),
        monthly_status_source=str(
            payload.get("monthly_status_source", "tfis_reference_packet")
        ),
        monthly_status_threshold_version=str(
            payload.get("monthly_status_threshold_version", "v1")
        ),
        runtime_value_overrides=(
            {
                str(key).upper(): float(value)
                for key, value in dict(payload.get("runtime_value_overrides") or {}).items()
            }
            or None
        ),
        monthly_status_reference_date=_optional_date(
            payload.get("monthly_status_reference_date")
        ),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_date(value: object) -> date | None:
    text = _optional_text(value)
    if text is None:
        return None
    return date.fromisoformat(text)
