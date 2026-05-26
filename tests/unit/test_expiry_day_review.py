from __future__ import annotations

from datetime import date, datetime

from tfis.backtest.expiry_day import build_expiry_day_lifecycle_review
from tfis.backtest.option_chain import OptionChainContract, OptionSelectionResult
from tfis.backtest.trade_lifecycle import TradeLifecycleResult
from tfis.domain.enums import OptionType


def _selection_result(*, expiry: date, symbol: str = "NIFTY_20260523_22100_CE") -> OptionSelectionResult:
    return OptionSelectionResult(
        selected=True,
        selected_contract=OptionChainContract(
            timestamp=datetime(2026, 5, 23, 15, 30),
            symbol=symbol,
            option_type=OptionType.CALL,
            strike=22100,
            expiry=expiry,
            bid=261.0,
            ask=265.0,
            ltp=263.0,
            oi=1200,
            volume=800,
        ),
        selection_reason="Selected contract closest to ideal premium.",
        candidate_count=2,
    )


def _lifecycle(exit_reason: str, *, entered: bool = True) -> TradeLifecycleResult:
    return TradeLifecycleResult(
        entered=entered,
        entry_price=200.0 if entered else None,
        exit_price=80.0 if exit_reason != "NO_EXIT" else None,
        entry_timestamp=datetime(2026, 5, 23, 9, 25) if entered else None,
        exit_timestamp=datetime(2026, 5, 23, 9, 30) if exit_reason not in {"NO_EXIT", "CARRY_FORWARD_PENDING"} else None,
        bars_held=2 if entered else 0,
        exit_reason=exit_reason,
        pnl_points=120.0 if exit_reason in {"TARGET_HIT", "EOD_SQUARE_OFF"} else None,
        max_favorable_excursion=10.0 if entered else None,
        max_adverse_excursion=5.0 if entered else None,
        notes="test",
    )


def test_expiry_day_review_marks_full_exit_satisfied_on_expiry_day() -> None:
    review = build_expiry_day_lifecycle_review(
        evaluation_timestamp=datetime(2026, 5, 23, 15, 30),
        selection_result=_selection_result(expiry=date(2026, 5, 23)),
        lifecycle_result=_lifecycle("EOD_SQUARE_OFF"),
    )

    assert review.is_expiry_day is True
    assert review.full_exit_required is True
    assert review.exit_satisfied is True
    assert review.warning is None


def test_expiry_day_review_marks_pending_open_position_as_warning() -> None:
    review = build_expiry_day_lifecycle_review(
        evaluation_timestamp=datetime(2026, 5, 23, 15, 30),
        selection_result=_selection_result(expiry=date(2026, 5, 23)),
        lifecycle_result=_lifecycle("NO_EXIT"),
    )

    assert review.is_expiry_day is True
    assert review.exit_satisfied is False
    assert "requires full exit" in str(review.warning)


def test_expiry_day_review_is_not_applicable_without_selected_contract() -> None:
    review = build_expiry_day_lifecycle_review(
        evaluation_timestamp=datetime(2026, 5, 23, 15, 30),
        selection_result=OptionSelectionResult(
            selected=False,
            selected_contract=None,
            selection_reason="No match",
            candidate_count=0,
        ),
        lifecycle_result=None,
    )

    assert review.applicable is False
    assert review.is_expiry_day is None
    assert "not applicable" in str(review.warning)
