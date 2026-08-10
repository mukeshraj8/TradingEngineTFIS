from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from tfis.backtest.hsre_s23_trade_lifecycle import HsreS23TradeLifecycleBuilder
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


REAL_NIFTY_ROOT = Path(r"D:\HistoricalData\Nifty")


@pytest.mark.skipif(
    not REAL_NIFTY_ROOT.exists(),
    reason="Real HSRE NIFTY data root is not available on this machine.",
)
def test_real_jan_3_2024_s23_trade_lifecycle() -> None:
    provider = NiftyHsreHistoricalMarketDataProvider(
        REAL_NIFTY_ROOT,
        max_cached_sessions=128,
    )
    builder = HsreS23TradeLifecycleBuilder(provider)

    first = builder.build_for_session(
        session_date=date(2024, 1, 3),
        planning_time=time(9, 16),
    )
    second = builder.build_for_session(
        session_date=date(2024, 1, 3),
        planning_time=time(9, 16),
    )

    assert builder.stable_packet_hash(first) == builder.stable_packet_hash(second)
    assert first.status == "ENTRY_NOT_TRIGGERED"
    assert first.contract == "NIFTY04JAN2421900PE"
    assert first.entry_threshold == pytest.approx(85.60875)
    assert first.contract_series_audit is not None
    assert first.contract_series_audit.bar_count == 365
    assert first.contract_series_audit.session_low == pytest.approx(279.0)
    assert first.contract_series_audit.session_low_timestamp == "2024-01-03T09:32:00"
    assert first.contract_series_audit.session_high == pytest.approx(419.0)
    assert first.contract_series_audit.session_high_timestamp == "2024-01-03T15:16:00"
    assert first.pnl.gross_points == pytest.approx(0.0)
    assert first.pnl.net_points == pytest.approx(0.0)

    print(
        "HSRE_M4_REAL_LIFECYCLE "
        f"session={first.session_date} "
        f"hash={builder.stable_packet_hash(first)} "
        f"status={first.status} "
        f"contract={first.contract} "
        f"entry={first.entry_threshold} "
        f"min_low={first.contract_series_audit.session_low} "
        f"min_low_time={first.contract_series_audit.session_low_timestamp} "
        f"max_high={first.contract_series_audit.session_high} "
        f"max_high_time={first.contract_series_audit.session_high_timestamp} "
        f"triggered={first.entry_triggered} "
        f"exit_reason={first.exit_reason} "
        f"gross_points={first.pnl.gross_points} "
        f"net_points={first.pnl.net_points}"
    )
