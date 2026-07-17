from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable

from tfis.brokers import BrokerAdapter, BrokerAdapterError

from .models import SelectedContractBarEvent, SelectedContractQuoteEvent


@dataclass(frozen=True, slots=True)
class PaperSelectedContractEventRequest:
    selected_contract_symbol: str
    session_date: date
    evaluated_at: datetime
    stoploss_reset_pending: bool = False
    stoploss_active: bool = True
    stoploss_reset_session_date: date | None = None
    entry_date: date | None = None
    stoploss_reset_rc_time: time | None = None
    bar_interval_minutes: int = 1


def fetch_selected_contract_market_events(
    adapter: BrokerAdapter,
    request: PaperSelectedContractEventRequest,
    *,
    on_bar_fetch_error: Callable[[BrokerAdapterError], None] | None = None,
) -> tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...]:
    events: list[SelectedContractQuoteEvent | SelectedContractBarEvent] = []
    if _should_fetch_stoploss_reset_bars(request):
        rc_time = request.stoploss_reset_rc_time or time(9, 29, 59)
        to_time = max(request.evaluated_at.timetz().replace(tzinfo=None), rc_time)
        try:
            events.extend(
                adapter.get_option_bars(
                    request.selected_contract_symbol,
                    session_date=request.session_date,
                    from_time=time(9, 15),
                    to_time=to_time,
                    interval_minutes=request.bar_interval_minutes,
                )
            )
        except AttributeError:
            pass
        except BrokerAdapterError as exc:
            if on_bar_fetch_error is not None:
                on_bar_fetch_error(exc)
    events.append(
        adapter.get_option_quote(
            request.selected_contract_symbol,
            session_date=request.session_date,
        )
    )
    return tuple(events)


def _should_fetch_stoploss_reset_bars(request: PaperSelectedContractEventRequest) -> bool:
    reference_session_date = request.stoploss_reset_session_date or request.entry_date
    return (
        request.stoploss_reset_pending
        and (not request.stoploss_active)
        and reference_session_date is not None
        and request.session_date > reference_session_date
    )


__all__ = [
    "PaperSelectedContractEventRequest",
    "fetch_selected_contract_market_events",
]
