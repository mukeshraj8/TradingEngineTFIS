from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from tfis.domain import StrategyExpiryPolicy, StrategyRule
from tfis.domain.enums import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment
from tfis.paper import (
    EventEnvelope,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperContractSelectionFailureCode,
    PaperEventType,
    PaperTradePlanEvent,
    S23PaperContractSelectionRequest,
    S23PaperContractSelector,
)


IST = ZoneInfo("Asia/Kolkata")


def _ts(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, 27, hour, minute, second, tzinfo=IST)


def _envelope() -> EventEnvelope:
    effective = _ts(9, 29, 59)
    return EventEnvelope(
        event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
        session_date=effective.date(),
        effective_timestamp=effective,
        captured_at=effective + timedelta(seconds=1),
        timezone="Asia/Kolkata",
        source_type="test_fixture",
        source_id="chain-source",
        synthetic_fixture=True,
        normalized_by="test-fixture",
    )


def _contract(
    *,
    symbol: str,
    strike: float,
    ltp: float | None,
    oi: float | None,
    expiry: date = date(2026, 5, 28),
    option_type: OptionType = OptionType.PUT,
) -> OptionChainContract:
    return OptionChainContract(
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        bid=ltp - 1 if ltp is not None else None,
        ask=ltp + 1 if ltp is not None else None,
        ltp=ltp,
        oi=oi,
        volume=100.0,
    )


def _snapshot(*contracts: OptionChainContract, expiry: date = date(2026, 5, 28)) -> OptionChainSnapshotEvent:
    return OptionChainSnapshotEvent(
        envelope=_envelope(),
        underlying_symbol="NIFTY",
        expiry=expiry,
        contracts=contracts,
    )


def _request(**overrides: object) -> S23PaperContractSelectionRequest:
    base = {
        "underlying_symbol": "NIFTY",
        "expiry_date": date(2026, 5, 28),
        "option_type": OptionType.PUT,
        "start_strike": 22300.0,
        "end_strike": 22500.0,
        "ideal_premium": 200.0,
        "minimum_premium": 180.0,
        "minimum_oi": 500.0,
    }
    base.update(overrides)
    return S23PaperContractSelectionRequest(**base)


def _strategy_rule() -> StrategyRule:
    return StrategyRule(
        strategy_code="S23",
        unique_code="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        segment=Segment.OPTIONS_SELL,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
            forced_close_time=time(15, 15),
            no_carry_past_expiry=True,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        option_type=OptionType.PUT,
        entry_time=time(9, 25),
        recalculation_time=time(9, 30),
        start_strike_formula="X",
        end_strike_formula="Y",
        ideal_premium_formula="Z",
        minimum_premium_formula="A",
        minimum_oi=500,
        entry_formula="B",
        target_formula="C",
        stoploss_formula="D",
        carry_forward_allowed=True,
    )


def _trade_plan() -> PaperTradePlanEvent:
    effective = _ts(9, 29, 59)
    return PaperTradePlanEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.TRADE_PLAN_INPUT,
            session_date=effective.date(),
            effective_timestamp=effective,
            captured_at=effective + timedelta(seconds=1),
            timezone="Asia/Kolkata",
            source_type="test_fixture",
            source_id="trade-plan-source",
            synthetic_fixture=True,
            normalized_by="test-fixture",
        ),
        strategy_branch="S23_BEAR_PUT",
        order_side="SELL",
        lots=1,
        quantity=50,
        planned_entry_price=199.0,
        target_price=80.0,
        stoploss_price=320.0,
        order_reference_time=effective,
        order_reference_label="ORPT",
        start_strike=22300.0,
        end_strike=22500.0,
        ideal_premium=200.0,
        minimum_premium=180.0,
        source_workbook_rule="AB6_OS_Z184",
        workbook_row_number=184,
        fsl_price=352.0,
    )


def test_selects_best_contract_by_ideal_premium_proximity() -> None:
    selector = S23PaperContractSelector()

    result = selector.select(
        _request(),
        _snapshot(
            _contract(symbol="NIFTY_20260528_22300_PE", strike=22300.0, ltp=198.0, oi=900.0),
            _contract(symbol="NIFTY_20260528_22400_PE", strike=22400.0, ltp=201.0, oi=700.0),
            _contract(symbol="NIFTY_20260528_22500_PE", strike=22500.0, ltp=205.0, oi=1400.0),
        ),
    )

    assert result.selected is True
    assert result.selected_contract_symbol == "NIFTY_20260528_22400_PE"
    assert result.premium_used == 201.0
    assert result.oi_used == 700.0
    assert result.ranking is not None
    assert result.ranking.premium_distance == 1.0


def test_rejects_missing_oi() -> None:
    selector = S23PaperContractSelector()

    result = selector.select(
        _request(),
        _snapshot(
            _contract(symbol="NIFTY_20260528_22400_PE", strike=22400.0, ltp=200.0, oi=None),
        ),
    )

    assert result.selected is False
    assert result.failure_code is PaperContractSelectionFailureCode.MISSING_CONTRACT_OI
    assert result.rejected_candidate_counts["missing_oi"] == 1


def test_rejects_oi_below_minimum() -> None:
    selector = S23PaperContractSelector()

    result = selector.select(
        _request(minimum_oi=1000.0),
        _snapshot(
            _contract(symbol="NIFTY_20260528_22400_PE", strike=22400.0, ltp=200.0, oi=999.0),
        ),
    )

    assert result.selected is False
    assert result.failure_code is PaperContractSelectionFailureCode.MINIMUM_OI_NOT_MET
    assert result.rejected_candidate_counts["minimum_oi_not_met"] == 1


def test_rejects_premium_below_minimum() -> None:
    selector = S23PaperContractSelector()

    result = selector.select(
        _request(minimum_premium=220.0),
        _snapshot(
            _contract(symbol="NIFTY_20260528_22400_PE", strike=22400.0, ltp=210.0, oi=1200.0),
        ),
    )

    assert result.selected is False
    assert result.failure_code is PaperContractSelectionFailureCode.MINIMUM_PREMIUM_NOT_MET
    assert result.rejected_candidate_counts["minimum_premium_not_met"] == 1


def test_falls_back_to_next_weekly_expiry_when_near_weekly_fails() -> None:
    selector = S23PaperContractSelector()

    result = selector.select(
        _request(
            expiry_date=date(2026, 5, 28),
            fallback_expiry_dates=(date(2026, 6, 4),),
            minimum_premium=220.0,
        ),
        _snapshot(
            _contract(
                symbol="NIFTY_20260528_22400_PE",
                strike=22400.0,
                ltp=210.0,
                oi=1200.0,
                expiry=date(2026, 5, 28),
            ),
            _contract(
                symbol="NIFTY_20260604_22400_PE",
                strike=22400.0,
                ltp=225.0,
                oi=1200.0,
                expiry=date(2026, 6, 4),
            ),
        ),
    )

    assert result.selected is True
    assert result.selected_contract_symbol == "NIFTY_20260604_22400_PE"
    assert result.expiry_date == date(2026, 6, 4)
    assert result.attempted_expiries == (date(2026, 5, 28), date(2026, 6, 4))
    assert "Near expiry 2026-05-28 failed" in result.selection_reason


def test_uses_deterministic_tie_breaking() -> None:
    selector = S23PaperContractSelector()

    result = selector.select(
        _request(ideal_premium=200.0),
        _snapshot(
            _contract(symbol="NIFTY_20260528_22500_PE", strike=22500.0, ltp=200.0, oi=1200.0),
            _contract(symbol="NIFTY_20260528_22300_PE", strike=22300.0, ltp=200.0, oi=1200.0),
            _contract(symbol="NIFTY_20260528_22400_PE", strike=22400.0, ltp=200.0, oi=1200.0),
        ),
    )

    assert result.selected is True
    assert result.selected_contract_symbol == "NIFTY_20260528_22300_PE"


def test_filters_by_expiry() -> None:
    selector = S23PaperContractSelector()

    result = selector.select(
        _request(expiry_date=date(2026, 5, 28)),
        _snapshot(
            _contract(
                symbol="NIFTY_20260604_22400_PE",
                strike=22400.0,
                ltp=200.0,
                oi=1200.0,
                expiry=date(2026, 6, 4),
            ),
        ),
    )

    assert result.selected is False
    assert result.failure_code is PaperContractSelectionFailureCode.NO_CONTRACT_SELECTED
    assert result.rejected_candidate_counts["expiry_mismatch"] == 1


def test_filters_by_option_type() -> None:
    selector = S23PaperContractSelector()

    result = selector.select(
        _request(option_type=OptionType.PUT),
        _snapshot(
            _contract(
                symbol="NIFTY_20260528_22400_CE",
                strike=22400.0,
                ltp=200.0,
                oi=1200.0,
                option_type=OptionType.CALL,
            ),
        ),
    )

    assert result.selected is False
    assert result.failure_code is PaperContractSelectionFailureCode.NO_CONTRACT_SELECTED
    assert result.rejected_candidate_counts["option_type_mismatch"] == 1


def test_empty_chain_fails_safely() -> None:
    selector = S23PaperContractSelector()

    result = selector.select(_request(), _snapshot())

    assert result.selected is False
    assert result.failure_code is PaperContractSelectionFailureCode.OPTION_CHAIN_MISSING


def test_request_can_be_built_from_strategy_and_trade_plan() -> None:
    request = S23PaperContractSelectionRequest.from_strategy_and_trade_plan(
        strategy=_strategy_rule(),
        trade_plan=_trade_plan(),
        expiry_date=date(2026, 5, 28),
    )

    assert request.underlying_symbol == "NIFTY"
    assert request.option_type is OptionType.PUT
    assert request.minimum_oi == 500.0
    assert request.start_strike == 22300.0
    assert request.end_strike == 22500.0
