from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from tfis.backtest.option_chain import OptionSelectionResult
from tfis.backtest.trade_lifecycle import TradeLifecycleResult


@dataclass(frozen=True, slots=True)
class ExpiryDayLifecycleReview:
    evaluation_date: date
    expiry_date: date | None
    selected_contract_symbol: str | None
    expiry_date_source: str
    applicable: bool
    is_expiry_day: bool | None
    full_exit_required: bool | None
    exit_satisfied: bool | None
    warning: str | None
    notes: tuple[str, ...]


def build_expiry_day_lifecycle_review(
    *,
    evaluation_timestamp: datetime,
    selection_result: OptionSelectionResult | None,
    lifecycle_result: TradeLifecycleResult | None,
) -> ExpiryDayLifecycleReview:
    evaluation_date = evaluation_timestamp.date()
    selected_contract = (
        selection_result.selected_contract
        if selection_result is not None
        else None
    )
    if selected_contract is None:
        return ExpiryDayLifecycleReview(
            evaluation_date=evaluation_date,
            expiry_date=None,
            selected_contract_symbol=None,
            expiry_date_source="selected_contract_unavailable",
            applicable=False,
            is_expiry_day=None,
            full_exit_required=None,
            exit_satisfied=None,
            warning=(
                "Expiry-day review was not applicable because no selected option-chain contract was available."
            ),
            notes=(
                "Expiry-day review depends on selected contract expiry metadata from option-chain selection.",
            ),
        )

    expiry_date = selected_contract.expiry
    is_expiry_day = expiry_date == evaluation_date
    if not is_expiry_day:
        return ExpiryDayLifecycleReview(
            evaluation_date=evaluation_date,
            expiry_date=expiry_date,
            selected_contract_symbol=selected_contract.symbol,
            expiry_date_source="selected_contract_expiry",
            applicable=True,
            is_expiry_day=False,
            full_exit_required=False,
            exit_satisfied=None,
            warning=None,
            notes=(
                "Selected contract expiry does not match the evaluation date, so no expiry-day full-exit requirement applied.",
            ),
        )

    if lifecycle_result is None:
        return ExpiryDayLifecycleReview(
            evaluation_date=evaluation_date,
            expiry_date=expiry_date,
            selected_contract_symbol=selected_contract.symbol,
            expiry_date_source="selected_contract_expiry",
            applicable=True,
            is_expiry_day=True,
            full_exit_required=True,
            exit_satisfied=None,
            warning=(
                "Expiry-day contract identified but no lifecycle result was available for exit review."
            ),
            notes=(
                "S23 option strategies require full exit on expiry day and do not roll to the next option contract.",
            ),
        )

    exit_reason = lifecycle_result.exit_reason
    if exit_reason == "NO_ENTRY":
        return ExpiryDayLifecycleReview(
            evaluation_date=evaluation_date,
            expiry_date=expiry_date,
            selected_contract_symbol=selected_contract.symbol,
            expiry_date_source="selected_contract_expiry",
            applicable=True,
            is_expiry_day=True,
            full_exit_required=True,
            exit_satisfied=True,
            warning=None,
            notes=(
                "No position was entered on the expiry day candidate, so no expiry-day exit action was required.",
            ),
        )

    if exit_reason in {"TARGET_HIT", "STOPLOSS_HIT", "EOD_SQUARE_OFF"}:
        return ExpiryDayLifecycleReview(
            evaluation_date=evaluation_date,
            expiry_date=expiry_date,
            selected_contract_symbol=selected_contract.symbol,
            expiry_date_source="selected_contract_expiry",
            applicable=True,
            is_expiry_day=True,
            full_exit_required=True,
            exit_satisfied=True,
            warning=None,
            notes=(
                "Expiry-day full-exit requirement was satisfied.",
            ),
        )

    return ExpiryDayLifecycleReview(
        evaluation_date=evaluation_date,
        expiry_date=expiry_date,
        selected_contract_symbol=selected_contract.symbol,
        expiry_date_source="selected_contract_expiry",
        applicable=True,
        is_expiry_day=True,
        full_exit_required=True,
        exit_satisfied=False,
        warning=(
            "Expiry-day candidate remained open in lifecycle review; S23 requires full exit and no option rollover."
        ),
        notes=(
            "This is a reporting and audit warning, not an automatic rollover or futures-style carry action.",
        ),
    )
