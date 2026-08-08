from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.rules import get_s21_leg_rule


S21_BRANCHES = (
    "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
    "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
    "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
    "BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT",
)


# AB6 OS S21 authority: "No. of Expiry to Check" = 1 Exp.
# Keep this explicit so replay and runtime cannot silently widen S21 to Near+Next.
S21_NUMBER_OF_EXPIRIES_TO_CHECK = 1


class S21StrategyEngineError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OptionContractEvidence:
    symbol: str
    option_type: str
    strike: float
    expiry: str
    oi: float | None
    chain_ltp: float | None = None


@dataclass(frozen=True, slots=True)
class OptionHistoricalReferences:
    symbol: str
    references: dict[str, float]
    source: str


@dataclass(frozen=True, slots=True)
class MinuteBarEvidence:
    symbol: str
    bar_start: str
    high: float | None
    low: float | None
    open: float | None = None
    close: float | None = None


@dataclass(frozen=True, slots=True)
class S21StrategyEvidence:
    session_date: str
    monthly_status: str
    monthly_status_source: str
    underlying_references: dict[str, float]
    option_chain: tuple[OptionContractEvidence, ...]
    option_historical_references: dict[str, OptionHistoricalReferences]
    option_minute_bars: dict[str, tuple[MinuteBarEvidence, ...]]
    spot_bars: dict[str, dict[str, float | str | None]]
    branch_parameters: dict[str, dict[str, float]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    symbol: str
    expiry: str
    strike: float
    option_type: str
    phase: str
    oi: float | None
    required_oi: float
    candidate_premium: float | None
    premium_source: str
    required_premium: float
    oi_pass: bool
    premium_pass: bool
    status: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class S21LegDecision:
    unique_code: str
    option_type: str
    spot_reference_alias: str
    spot_reference_value: float
    start_strike: float
    end_strike: float
    ideal_premium: float
    minimum_premium: float
    minimum_oi_units: float
    candidate_decisions: tuple[CandidateDecision, ...]
    selected_contract: str | None
    selected_expiry: str | None
    selected_strike: float | None
    selection_phase: str | None
    selected_option_references: dict[str, float] | None
    entry: float | None
    target: float | None
    stoploss: float | None
    orpt_status: str
    rc_status: str
    order_time: str | None
    evidence_gaps: tuple[str, ...]
    verdict: str


@dataclass(frozen=True, slots=True)
class S21StrategyDecision:
    session_date: str
    monthly_status: str
    monthly_status_source: str
    eligible_legs: tuple[str, ...]
    ineligible_legs: tuple[str, ...]
    legs: tuple[S21LegDecision, ...]
    evidence_complete: bool
    evidence_gaps: tuple[str, ...]


class S21StrategyEngine:
    """Pure S21 business engine.

    No broker, scheduler, dashboard, persistence or authentication dependency.
    The same engine can be called by replay and by the live runtime once
    certification is complete.
    """

    def eligible_legs(self, monthly_status: MonthlyStatus) -> tuple[str, ...]:
        return tuple(
            code
            for code in S21_BRANCHES
            if monthly_status in get_s21_leg_rule(code).allowed_monthly_statuses
        )

    def required_candidate_symbols(
        self,
        evidence: S21StrategyEvidence,
    ) -> dict[str, tuple[str, ...]]:
        status = MonthlyStatus(evidence.monthly_status)
        result: dict[str, tuple[str, ...]] = {}
        for code in self.eligible_legs(status):
            leg = get_s21_leg_rule(code)
            params = evidence.branch_parameters[code]
            spot_ref = self._reference(evidence, leg.spot_reference_alias)
            start, end = self._strike_range(
                option_type=leg.option_type,
                spot_ref=spot_ref,
                buffer_pct=float(params["strike_buffer_pct"]),
                strike_step=float(params["strike_step"]),
            )
            expiries = self._expiry_order(evidence)
            symbols: list[str] = []
            for expiry in expiries:
                for row in self._contracts(
                    evidence,
                    expiry=expiry,
                    option_type=leg.option_type,
                    start=start,
                    end=end,
                ):
                    symbols.append(row.symbol)
            result[code] = tuple(symbols)
        return result

    def evaluate(self, evidence: S21StrategyEvidence) -> S21StrategyDecision:
        status = MonthlyStatus(evidence.monthly_status)
        eligible = self.eligible_legs(status)
        ineligible = tuple(code for code in S21_BRANCHES if code not in eligible)
        leg_decisions = tuple(self._evaluate_leg(code, evidence) for code in eligible)

        gaps: list[str] = []
        for leg in leg_decisions:
            gaps.extend(f"{leg.unique_code}:{gap}" for gap in leg.evidence_gaps)

        return S21StrategyDecision(
            session_date=evidence.session_date,
            monthly_status=status.value,
            monthly_status_source=evidence.monthly_status_source,
            eligible_legs=eligible,
            ineligible_legs=ineligible,
            legs=leg_decisions,
            evidence_complete=not gaps,
            evidence_gaps=tuple(gaps),
        )

    def _evaluate_leg(
        self,
        unique_code: str,
        evidence: S21StrategyEvidence,
    ) -> S21LegDecision:
        leg = get_s21_leg_rule(unique_code)
        params = evidence.branch_parameters[unique_code]
        spot_ref = self._reference(evidence, leg.spot_reference_alias)
        step = float(params["strike_step"])
        start, end = self._strike_range(
            option_type=leg.option_type,
            spot_ref=spot_ref,
            buffer_pct=float(params["strike_buffer_pct"]),
            strike_step=step,
        )
        ideal = spot_ref * float(params["ideal_premium_pct"]) / 100.0
        minimum = spot_ref * float(params["minimum_premium_pct"]) / 100.0
        min_oi = float(params["minimum_lots"]) * float(params["lot_size"])

        candidate_decisions: list[CandidateDecision] = []
        selected: OptionContractEvidence | None = None
        selected_refs: dict[str, float] | None = None
        selected_phase: str | None = None
        missing_chain_premium_symbols: set[str] = set()

        # S21 and S23 share the same option-selling contract-selection semantics:
        #   strike-range candidate -> exact contract premium + exact contract OI
        #   -> workbook preference order -> final contract.
        #
        # Historical OPT_PRV references belong to Entry/SL calculation AFTER a
        # contract is finalized; they must not be reused as the candidate premium.
        for expiry in self._expiry_order(evidence):
            forward = self._contracts(
                evidence,
                expiry=expiry,
                option_type=leg.option_type,
                start=start,
                end=end,
            )

            for phase, rows, required_premium in (
                ("IDEAL_START_TO_END", forward, ideal),
                ("MINIMUM_END_TO_START", list(reversed(forward)), minimum),
            ):
                for row in rows:
                    oi_pass = row.oi is not None and float(row.oi) >= min_oi
                    premium_value = (
                        None if row.chain_ltp is None else float(row.chain_ltp)
                    )

                    # Missing premium on an otherwise OI-eligible candidate is
                    # material because search order is authoritative. Do not
                    # silently skip a candidate that might have been selected.
                    if oi_pass and premium_value is None:
                        missing_chain_premium_symbols.add(row.symbol)

                    premium_pass = (
                        premium_value is not None
                        and premium_value >= float(required_premium)
                    )
                    reasons: list[str] = []
                    if not oi_pass:
                        reasons.append("OI_BELOW_500_LOT_THRESHOLD")
                    if premium_value is None:
                        reasons.append("MISSING_OPTION_CHAIN_PREMIUM")
                    elif not premium_pass:
                        reasons.append("PREMIUM_THRESHOLD_NOT_MET")

                    candidate_decisions.append(
                        CandidateDecision(
                            symbol=row.symbol,
                            expiry=row.expiry,
                            strike=row.strike,
                            option_type=row.option_type,
                            phase=phase,
                            oi=row.oi,
                            required_oi=min_oi,
                            candidate_premium=premium_value,
                            premium_source="OPTION_CHAIN_LTP",
                            required_premium=float(required_premium),
                            oi_pass=oi_pass,
                            premium_pass=premium_pass,
                            status=(
                                "QUALIFIED"
                                if oi_pass and premium_pass
                                else "REJECTED"
                            ),
                            reasons=tuple(reasons),
                        )
                    )

                    if oi_pass and premium_pass:
                        # If an earlier OI-eligible candidate in this same
                        # authoritative traversal had no premium, selection is
                        # not trustworthy. Fail closed below rather than select
                        # around missing evidence.
                        if missing_chain_premium_symbols:
                            break
                        selected = row
                        selected_phase = phase
                        break
                if selected is not None or missing_chain_premium_symbols:
                    break
            if selected is not None or missing_chain_premium_symbols:
                break

        if missing_chain_premium_symbols:
            gaps = tuple(
                f"MISSING_OPTION_CHAIN_PREMIUM:{symbol}"
                for symbol in sorted(missing_chain_premium_symbols)
            )
            return S21LegDecision(
                unique_code=unique_code,
                option_type=leg.option_type.value,
                spot_reference_alias=leg.spot_reference_alias,
                spot_reference_value=spot_ref,
                start_strike=start,
                end_strike=end,
                ideal_premium=ideal,
                minimum_premium=minimum,
                minimum_oi_units=min_oi,
                candidate_decisions=tuple(candidate_decisions),
                selected_contract=None,
                selected_expiry=None,
                selected_strike=None,
                selection_phase=None,
                selected_option_references=None,
                entry=None,
                target=None,
                stoploss=None,
                orpt_status="NOT_EVALUATED",
                rc_status="NOT_EVALUATED",
                order_time=None,
                evidence_gaps=gaps,
                verdict="EVIDENCE_INCOMPLETE",
            )

        if selected is None:
            return S21LegDecision(
                unique_code=unique_code,
                option_type=leg.option_type.value,
                spot_reference_alias=leg.spot_reference_alias,
                spot_reference_value=spot_ref,
                start_strike=start,
                end_strike=end,
                ideal_premium=ideal,
                minimum_premium=minimum,
                minimum_oi_units=min_oi,
                candidate_decisions=tuple(candidate_decisions),
                selected_contract=None,
                selected_expiry=None,
                selected_strike=None,
                selection_phase=None,
                selected_option_references=None,
                entry=None,
                target=None,
                stoploss=None,
                orpt_status="NOT_EVALUATED",
                rc_status="NOT_EVALUATED",
                order_time=None,
                evidence_gaps=(),
                verdict="NO_QUALIFYING_CONTRACT",
            )

        selected_history = evidence.option_historical_references.get(selected.symbol)
        if selected_history is None:
            gap = f"MISSING_SELECTED_CONTRACT_HISTORY:{selected.symbol}"
            return S21LegDecision(
                unique_code=unique_code,
                option_type=leg.option_type.value,
                spot_reference_alias=leg.spot_reference_alias,
                spot_reference_value=spot_ref,
                start_strike=start,
                end_strike=end,
                ideal_premium=ideal,
                minimum_premium=minimum,
                minimum_oi_units=min_oi,
                candidate_decisions=tuple(candidate_decisions),
                selected_contract=selected.symbol,
                selected_expiry=selected.expiry,
                selected_strike=selected.strike,
                selection_phase=selected_phase,
                selected_option_references=None,
                entry=None,
                target=None,
                stoploss=None,
                orpt_status="NOT_EVALUATED",
                rc_status="NOT_EVALUATED",
                order_time=None,
                evidence_gaps=(gap,),
                verdict="EVIDENCE_INCOMPLETE",
            )
        selected_refs = dict(selected_history.references)

        entry_ref = self._required_selected_ref(
            selected_refs,
            leg.entry_reference_alias,
            selected.symbol,
        )
        sl_ref = self._required_selected_ref(
            selected_refs,
            leg.structure_sl_reference_alias,
            selected.symbol,
        )
        entry = entry_ref * (1.0 - float(params["entry_discount_pct"]) / 100.0)
        target = entry * (1.0 - float(params["target_pct"]) / 100.0)
        stoploss = min(
            entry * (1.0 + float(params["sl_entry_pct"]) / 100.0),
            sl_ref * (1.0 + float(params["sl_reference_pct"]) / 100.0),
        )

        selected_bars = evidence.option_minute_bars.get(selected.symbol, ())
        orpt = self._bar_at(selected_bars, "09:24")
        rc = self._bar_at(selected_bars, "09:29")
        gaps: list[str] = []

        if orpt is None:
            gaps.append(f"MISSING_ORPT_BAR:{selected.symbol}")
            orpt_status = "EVIDENCE_INCOMPLETE"
            rc_status = "NOT_EVALUATED"
            order_time = None
            verdict = "EVIDENCE_INCOMPLETE"
        else:
            missed = self._base_entry_missed(
                option_type=leg.option_type,
                entry=entry,
                bar=orpt,
            )
            if not missed:
                orpt_status = "BASE_ENTRY_VALID"
                rc_status = "NOT_REQUIRED"
                order_time = "09:25"
                verdict = "NORMAL_ORDER_READY_AT_09_25"
            else:
                orpt_status = "RECALCULATION_REQUIRED"
                order_time = None
                if rc is None:
                    gaps.append(f"MISSING_RC_BAR:{selected.symbol}")
                    rc_status = "EVIDENCE_INCOMPLETE"
                    verdict = "EVIDENCE_INCOMPLETE"
                else:
                    # Timing is known, but numerical S21 RC formula authority
                    # has not yet been ported into the pure engine.
                    rc_status = "S21_RC_RULE_NOT_YET_PORTED"
                    verdict = "RC_RULE_PENDING"

        return S21LegDecision(
            unique_code=unique_code,
            option_type=leg.option_type.value,
            spot_reference_alias=leg.spot_reference_alias,
            spot_reference_value=spot_ref,
            start_strike=start,
            end_strike=end,
            ideal_premium=ideal,
            minimum_premium=minimum,
            minimum_oi_units=min_oi,
            candidate_decisions=tuple(candidate_decisions),
            selected_contract=selected.symbol,
            selected_expiry=selected.expiry,
            selected_strike=selected.strike,
            selection_phase=selected_phase,
            selected_option_references=selected_refs,
            entry=entry,
            target=target,
            stoploss=stoploss,
            orpt_status=orpt_status,
            rc_status=rc_status,
            order_time=order_time,
            evidence_gaps=tuple(gaps),
            verdict=verdict,
        )

    def _contracts(
        self,
        evidence: S21StrategyEvidence,
        *,
        expiry: str,
        option_type: OptionType,
        start: float,
        end: float,
    ) -> list[OptionContractEvidence]:
        lower, upper = min(start, end), max(start, end)
        wanted = "CALL" if option_type is OptionType.CALL else "PUT"
        rows = [
            row
            for row in evidence.option_chain
            if row.expiry == expiry
            and row.option_type.upper() == wanted
            and lower <= row.strike <= upper
        ]
        ascending = end >= start
        return sorted(
            rows,
            key=lambda row: (row.strike, row.symbol),
            reverse=not ascending,
        )

    @staticmethod
    def _expiry_order(evidence: S21StrategyEvidence) -> tuple[str, ...]:
        session_date = date.fromisoformat(evidence.session_date)
        expiries = sorted(
            {
                row.expiry
                for row in evidence.option_chain
                if date.fromisoformat(row.expiry) >= session_date
            }
        )
        return tuple(expiries[:S21_NUMBER_OF_EXPIRIES_TO_CHECK])

    @staticmethod
    def _strike_range(
        *,
        option_type: OptionType,
        spot_ref: float,
        buffer_pct: float,
        strike_step: float,
    ) -> tuple[float, float]:
        if option_type is OptionType.CALL:
            start = _round_down(
                spot_ref * (1.0 + buffer_pct / 100.0),
                strike_step,
            )
            end = _round_down(spot_ref, strike_step) - strike_step
            return start, end
        start = _round_up(
            spot_ref * (1.0 - buffer_pct / 100.0),
            strike_step,
        )
        end = _round_up(spot_ref, strike_step) + strike_step
        return start, end

    @staticmethod
    def _base_entry_missed(
        *,
        option_type: OptionType,
        entry: float,
        bar: MinuteBarEvidence,
    ) -> bool:
        # AB6 OS entry-missed authority is the same for short Call and short Put:
        # "Check If 09:24:59 AM LL < <Option> Sell Entry".
        # Directional Call/Put differences belong to strike/reference formulas,
        # not to this already-crossed short-option entry test.
        return bar.low is not None and float(bar.low) < entry

    @staticmethod
    def _bar_at(
        bars: tuple[MinuteBarEvidence, ...],
        prefix: str,
    ) -> MinuteBarEvidence | None:
        marker = f"T{prefix}:"
        for row in bars:
            if marker in row.bar_start:
                return row
        return None

    @staticmethod
    def _reference(evidence: S21StrategyEvidence, alias: str) -> float:
        try:
            return float(evidence.underlying_references[alias])
        except KeyError as exc:
            raise S21StrategyEngineError(
                f"Missing required underlying reference: {alias}"
            ) from exc

    @staticmethod
    def _required_selected_ref(
        refs: dict[str, float],
        alias: str,
        symbol: str,
    ) -> float:
        try:
            return float(refs[alias])
        except KeyError as exc:
            raise S21StrategyEngineError(
                f"Selected contract {symbol} is missing {alias}"
            ) from exc


def _round_down(value: float, step: float) -> float:
    return math.floor(value / step + 1e-12) * step


def _round_up(value: float, step: float) -> float:
    return math.ceil(value / step - 1e-12) * step


def decision_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: decision_to_dict(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, dict):
        return {str(k): decision_to_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [decision_to_dict(v) for v in value]
    return value
