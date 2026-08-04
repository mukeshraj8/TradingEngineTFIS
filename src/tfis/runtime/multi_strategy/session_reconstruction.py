from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Mapping, Sequence

from tfis.fyers_read_only.models import CompletedCandleSet, FyersCandle, FyersQuote
from tfis.persistence import canonical_hash


MARKET_OPEN = time(9, 15)


@dataclass(frozen=True, slots=True)
class StrategyTimingPolicy:
    market_open: time
    orpt_time: time
    rc_time: time


@dataclass(frozen=True, slots=True)
class TriggerObservation:
    status: str
    activation_time: datetime
    trigger_price: Decimal
    breach_timestamp: datetime | None
    breach_source: str | None
    current_quote_breached: bool
    evidence_quality: str
    details: Mapping[str, object]

    @property
    def still_valid(self) -> bool:
        return self.breach_timestamp is None and not self.current_quote_breached


@dataclass(frozen=True, slots=True)
class StrategyReconstructionResult:
    strategy_instance_id: str
    selected_contract_authoritative: bool
    timing_policy: StrategyTimingPolicy
    opening_price: Decimal | None
    opening_bar_timestamp: datetime | None
    underlying_evidence_quality: str
    option_evidence_quality: str
    orpt_result: str
    rc_result: str
    current_entry_state: str
    normal_entry: TriggerObservation | None
    revised_entry: TriggerObservation | None
    invalid_runtime_classification: str
    evidence_hash: str
    block_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy_instance_id": self.strategy_instance_id,
            "selected_contract_authoritative": self.selected_contract_authoritative,
            "timing_policy": {
                "market_open": self.timing_policy.market_open.isoformat(),
                "orpt_time": self.timing_policy.orpt_time.isoformat(),
                "rc_time": self.timing_policy.rc_time.isoformat(),
            },
            "opening_price": str(self.opening_price) if self.opening_price is not None else None,
            "opening_bar_timestamp": self.opening_bar_timestamp.isoformat() if self.opening_bar_timestamp else None,
            "underlying_evidence_quality": self.underlying_evidence_quality,
            "option_evidence_quality": self.option_evidence_quality,
            "orpt_result": self.orpt_result,
            "rc_result": self.rc_result,
            "current_entry_state": self.current_entry_state,
            "normal_entry": _trigger_to_dict(self.normal_entry),
            "revised_entry": _trigger_to_dict(self.revised_entry),
            "invalid_runtime_classification": self.invalid_runtime_classification,
            "block_reason": self.block_reason,
            "evidence_hash": self.evidence_hash,
        }


def classify_market_session_state(now: datetime) -> str:
    current = now.timetz().replace(tzinfo=None)
    if current < MARKET_OPEN:
        return "PRE_OPEN"
    if current <= time(15, 30):
        return "LIVE"
    return "POST_CLOSE"


def selected_contract_is_authoritative(symbol: str | None) -> bool:
    return bool(symbol and symbol.startswith("NSE:"))


def classify_candle_completeness(
    candles: CompletedCandleSet | None,
    *,
    required_start: time,
    required_end: datetime,
) -> str:
    if candles is None or not candles.candles:
        return "MISSING"
    first = candles.candles[0].bar_start.timetz().replace(tzinfo=None)
    required_minute = time(required_start.hour, required_start.minute)
    first_minute = time(first.hour, first.minute)
    if first_minute > required_minute:
        return "INSUFFICIENT_TO_DETERMINE_TRIGGER_BREACH"
    last_complete = candles.candles[-1].bar_end
    if last_complete + timedelta(minutes=1) < required_end:
        return "PARTIAL_BUT_DECISIVE"
    gaps = _missing_bar_count(candles.candles)
    if gaps:
        return "PARTIAL_BUT_DECISIVE"
    return "COMPLETE_REQUIRED_INTERVAL_BARS"


def opening_price_from_candles(candles: CompletedCandleSet | None, *, market_open: time) -> tuple[Decimal | None, datetime | None]:
    if candles is None:
        return None, None
    for candle in candles.candles:
        if candle.bar_start.timetz().replace(tzinfo=None) == market_open:
            return candle.open, candle.bar_start
    return None, None


def evaluate_option_sell_trigger(
    *,
    bars: CompletedCandleSet | None,
    current_quote: FyersQuote | None,
    activation_time: datetime,
    trigger_price: Decimal,
    evidence_quality: str,
    status: str,
) -> TriggerObservation:
    details: dict[str, object] = {"evaluation_rule": "LOW_LT_ENTRY_MEANS_TRIGGER_BREACHED_FOR_OPTION_SELLING"}
    breach_timestamp: datetime | None = None
    breach_source: str | None = None
    if bars is None or not bars.candles:
        return TriggerObservation(
            status=status,
            activation_time=activation_time,
            trigger_price=trigger_price,
            breach_timestamp=None,
            breach_source=None,
            current_quote_breached=False,
            evidence_quality="MISSING",
            details=details | {"reason": "OPTION_BARS_MISSING"},
        )
    for candle in bars.candles:
        if candle.bar_end <= activation_time:
            continue
        if candle.low < trigger_price:
            breach_timestamp = candle.bar_end
            breach_source = "HISTORICAL_CANDLE_LOW"
            details["breach_bar"] = candle.to_dict()
            break
    current_quote_breached = False
    if breach_timestamp is None and current_quote is not None and current_quote.ltp is not None and current_quote.ltp < trigger_price:
        current_quote_breached = True
        breach_source = "CURRENT_LTP"
        details["current_quote_ltp"] = str(current_quote.ltp)
    return TriggerObservation(
        status=status,
        activation_time=activation_time,
        trigger_price=trigger_price,
        breach_timestamp=breach_timestamp,
        breach_source=breach_source,
        current_quote_breached=current_quote_breached,
        evidence_quality=evidence_quality,
        details=details,
    )


def reconstruct_option_selling_entry(
    *,
    strategy_instance_id: str,
    timing_policy: StrategyTimingPolicy,
    now: datetime,
    invalid_runtime_classification: str,
    selected_contract_authoritative: bool,
    base_entry: Decimal,
    revised_entry: Decimal | None,
    underlying_bars: CompletedCandleSet | None,
    option_bars: CompletedCandleSet | None,
    current_quote: FyersQuote | None,
) -> StrategyReconstructionResult:
    opening_price, opening_bar_timestamp = opening_price_from_candles(underlying_bars, market_open=timing_policy.market_open)
    underlying_quality = classify_candle_completeness(
        underlying_bars,
        required_start=timing_policy.market_open,
        required_end=now,
    )
    option_quality = classify_candle_completeness(
        option_bars,
        required_start=timing_policy.orpt_time,
        required_end=now,
    )
    if not selected_contract_authoritative:
        payload = StrategyReconstructionResult(
            strategy_instance_id=strategy_instance_id,
            selected_contract_authoritative=False,
            timing_policy=timing_policy,
            opening_price=opening_price,
            opening_bar_timestamp=opening_bar_timestamp,
            underlying_evidence_quality=underlying_quality,
            option_evidence_quality="MISSING",
            orpt_result="ORPT_BLOCKED_MISSING_EVIDENCE",
            rc_result="RC_BLOCKED_MISSING_EVIDENCE",
            current_entry_state="BLOCKED_INSUFFICIENT_HISTORICAL_EVIDENCE",
            normal_entry=None,
            revised_entry=None,
            invalid_runtime_classification=invalid_runtime_classification,
            block_reason="SELECTED_CONTRACT_NOT_AUTHORITATIVE_FOR_CURRENT_SESSION",
            evidence_hash="",
        )
        return _with_hash(payload)
    if option_quality in {"MISSING", "INSUFFICIENT_TO_DETERMINE_TRIGGER_BREACH"}:
        payload = StrategyReconstructionResult(
            strategy_instance_id=strategy_instance_id,
            selected_contract_authoritative=True,
            timing_policy=timing_policy,
            opening_price=opening_price,
            opening_bar_timestamp=opening_bar_timestamp,
            underlying_evidence_quality=underlying_quality,
            option_evidence_quality=option_quality,
            orpt_result="ORPT_BLOCKED_MISSING_EVIDENCE",
            rc_result="RC_BLOCKED_MISSING_EVIDENCE",
            current_entry_state="BLOCKED_INSUFFICIENT_HISTORICAL_EVIDENCE",
            normal_entry=None,
            revised_entry=None,
            invalid_runtime_classification=invalid_runtime_classification,
            block_reason="SELECTED_OPTION_HISTORY_INSUFFICIENT",
            evidence_hash="",
        )
        return _with_hash(payload)

    activation_orpt = _combine(now.date(), timing_policy.orpt_time, now.tzinfo)
    normal = evaluate_option_sell_trigger(
        bars=option_bars,
        current_quote=current_quote,
        activation_time=activation_orpt,
        trigger_price=base_entry,
        evidence_quality=option_quality,
        status="NORMAL_ENTRY",
    )
    if normal.still_valid:
        payload = StrategyReconstructionResult(
            strategy_instance_id=strategy_instance_id,
            selected_contract_authoritative=True,
            timing_policy=timing_policy,
            opening_price=opening_price,
            opening_bar_timestamp=opening_bar_timestamp,
            underlying_evidence_quality=underlying_quality,
            option_evidence_quality=option_quality,
            orpt_result="ORPT_ENTRY_NOT_MISSED",
            rc_result="RC_NOT_REQUIRED",
            current_entry_state="NORMAL_ENTRY_STILL_VALID",
            normal_entry=normal,
            revised_entry=None,
            invalid_runtime_classification=invalid_runtime_classification,
            evidence_hash="",
        )
        return _with_hash(payload)

    if revised_entry is None:
        payload = StrategyReconstructionResult(
            strategy_instance_id=strategy_instance_id,
            selected_contract_authoritative=True,
            timing_policy=timing_policy,
            opening_price=opening_price,
            opening_bar_timestamp=opening_bar_timestamp,
            underlying_evidence_quality=underlying_quality,
            option_evidence_quality=option_quality,
            orpt_result="ORPT_ENTRY_MISSED_WAITING_FOR_RC",
            rc_result="RC_NO_TRADE_BY_RULE",
            current_entry_state="NORMAL_ENTRY_ALREADY_MISSED",
            normal_entry=normal,
            revised_entry=None,
            invalid_runtime_classification=invalid_runtime_classification,
            evidence_hash="",
        )
        return _with_hash(payload)

    activation_rc = _combine(now.date(), timing_policy.rc_time, now.tzinfo)
    revised = evaluate_option_sell_trigger(
        bars=option_bars,
        current_quote=current_quote,
        activation_time=activation_rc,
        trigger_price=revised_entry,
        evidence_quality=option_quality,
        status="RC_ENTRY",
    )
    if revised.still_valid:
        payload = StrategyReconstructionResult(
            strategy_instance_id=strategy_instance_id,
            selected_contract_authoritative=True,
            timing_policy=timing_policy,
            opening_price=opening_price,
            opening_bar_timestamp=opening_bar_timestamp,
            underlying_evidence_quality=underlying_quality,
            option_evidence_quality=option_quality,
            orpt_result="ORPT_ENTRY_MISSED_WAITING_FOR_RC",
            rc_result="RC_ENTRY_STILL_VALID",
            current_entry_state="RC_ENTRY_STILL_VALID",
            normal_entry=normal,
            revised_entry=revised,
            invalid_runtime_classification=invalid_runtime_classification,
            evidence_hash="",
        )
        return _with_hash(payload)

    payload = StrategyReconstructionResult(
        strategy_instance_id=strategy_instance_id,
        selected_contract_authoritative=True,
        timing_policy=timing_policy,
        opening_price=opening_price,
        opening_bar_timestamp=opening_bar_timestamp,
        underlying_evidence_quality=underlying_quality,
        option_evidence_quality=option_quality,
        orpt_result="ORPT_ENTRY_MISSED_WAITING_FOR_RC",
        rc_result="RC_ENTRY_ALREADY_MISSED",
        current_entry_state="RC_ENTRY_ALREADY_MISSED",
        normal_entry=normal,
        revised_entry=revised,
        invalid_runtime_classification=invalid_runtime_classification,
        evidence_hash="",
    )
    return _with_hash(payload)


def _with_hash(result: StrategyReconstructionResult) -> StrategyReconstructionResult:
    payload = result.to_dict()
    payload["evidence_hash"] = None
    return StrategyReconstructionResult(
        strategy_instance_id=result.strategy_instance_id,
        selected_contract_authoritative=result.selected_contract_authoritative,
        timing_policy=result.timing_policy,
        opening_price=result.opening_price,
        opening_bar_timestamp=result.opening_bar_timestamp,
        underlying_evidence_quality=result.underlying_evidence_quality,
        option_evidence_quality=result.option_evidence_quality,
        orpt_result=result.orpt_result,
        rc_result=result.rc_result,
        current_entry_state=result.current_entry_state,
        normal_entry=result.normal_entry,
        revised_entry=result.revised_entry,
        invalid_runtime_classification=result.invalid_runtime_classification,
        block_reason=result.block_reason,
        evidence_hash=canonical_hash(payload),
    )


def _combine(day: date, value: time, tzinfo) -> datetime:
    return datetime.combine(day, value, tzinfo=tzinfo)


def _missing_bar_count(candles: Sequence[FyersCandle]) -> int:
    missing = 0
    for previous, current in zip(candles, candles[1:]):
        if current.bar_start - previous.bar_start > timedelta(minutes=1):
            missing += 1
    return missing


def _trigger_to_dict(value: TriggerObservation | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "status": value.status,
        "activation_time": value.activation_time.isoformat(),
        "trigger_price": str(value.trigger_price),
        "breach_timestamp": value.breach_timestamp.isoformat() if value.breach_timestamp else None,
        "breach_source": value.breach_source,
        "current_quote_breached": value.current_quote_breached,
        "evidence_quality": value.evidence_quality,
        "still_valid": value.still_valid,
        "details": dict(value.details),
    }
