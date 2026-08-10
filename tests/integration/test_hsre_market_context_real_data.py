from __future__ import annotations

from datetime import datetime, time
from pathlib import Path

import pytest

from tfis.backtest.hsre_market_context import NiftyHsreMarketContextBuilder
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


REAL_NIFTY_ROOT = Path(r"D:\HistoricalData\Nifty")


@pytest.mark.skipif(
    not REAL_NIFTY_ROOT.exists(),
    reason="Real HSRE NIFTY data root is not available on this machine.",
)
def test_real_january_2024_context_packet_report() -> None:
    provider = NiftyHsreHistoricalMarketDataProvider(REAL_NIFTY_ROOT)
    builder = NiftyHsreMarketContextBuilder(provider)

    eligibility = builder.discover_january_eligibility(
        year=2024,
        evaluation_time=time(9, 16),
    )

    assert eligibility.first_underlying_lookback_ready is not None
    assert eligibility.first_monthly_status_ready is not None
    assert eligibility.first_fully_context_ready is not None

    first_ready = datetime.fromisoformat(eligibility.first_fully_context_ready).date()
    packet = builder.build_context(session_date=first_ready, evaluation_time=time(9, 16))

    assert packet.context_status == "READY"
    assert packet.market_levels is not None
    assert packet.current_day_provenance is not None
    assert datetime.fromisoformat(packet.current_day_provenance.last_timestamp) <= datetime.fromisoformat(
        packet.evaluation_timestamp
    )
    assert all(
        datetime.fromisoformat(item.last_timestamp) <= datetime.fromisoformat(packet.evaluation_timestamp)
        for item in packet.weekly_context_provenance
        if item.last_timestamp is not None
    )
    assert all(
        datetime.fromisoformat(item.last_timestamp) <= datetime.fromisoformat(packet.evaluation_timestamp)
        for item in packet.monthly_context_provenance
        if item.last_timestamp is not None
    )

    packet_hash = builder.stable_packet_hash(packet)
    print(
        "HSRE_M1B_REAL_CONTEXT "
        f"first_underlying={eligibility.first_underlying_lookback_ready} "
        f"first_monthly={eligibility.first_monthly_status_ready} "
        f"first_ready={eligibility.first_fully_context_ready} "
        f"status={packet.context_status} "
        f"monthly_status={packet.monthly_status} "
        f"monthly_trigger={packet.monthly_status_trigger} "
        f"hash={packet_hash} "
        f"PRV_2DHH={packet.market_levels.d2hh} "
        f"PRV_2DLL={packet.market_levels.d2ll} "
        f"PRV_3DHH={packet.market_levels.d3hh} "
        f"PRV_3DLL={packet.market_levels.d3ll} "
        f"PRV_4DHH={packet.market_levels.d4hh} "
        f"PRV_4DLL={packet.market_levels.d4ll} "
        f"current_high={packet.current_day_high_through_evaluation} "
        f"current_low={packet.current_day_low_through_evaluation} "
        f"completed_prior={','.join(packet.completed_prior_sessions_used)} "
        f"current_last={packet.current_day_provenance.last_timestamp}"
    )
