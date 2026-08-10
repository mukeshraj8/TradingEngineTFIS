from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tfis.backtest.hsre_s23_final_order_decision import (
    HsreS23FinalOrderDecisionPacket,
    HsreS23TimingAuthority,
)
from tfis.backtest.hsre_s23_trade_lifecycle import (
    HsreS23TradeLifecycleBuilder,
    hsre_s23_trade_lifecycle_packet_to_dict,
)
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


def _write_options(
    root: Path,
    session: date,
    rows: list[tuple[str, str, float, float, float, float, int, int]],
) -> None:
    path = root / "options" / f"{session.year}" / f"{session.month}" / f"nifty_options_{session:%d_%m_%Y}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,time,symbol,open,high,low,close,oi,volume"]
    for raw_time, symbol, open_, high, low, close, oi, volume in rows:
        lines.append(
            f"{session.isoformat()},{raw_time},{symbol},{open_},{high},{low},{close},{oi},{volume}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _final_order(
    *,
    contract: str = "NIFTY04JAN2450CE",
    entry: float = 100.0,
    target: float = 50.0,
    stoploss: float = 150.0,
) -> HsreS23FinalOrderDecisionPacket:
    return HsreS23FinalOrderDecisionPacket(
        session_date="2024-01-01",
        monthly_status="BULL_CF",
        branch="NIFTY_OP_SELL_WK_DIFF_2D_3D",
        status="NORMAL_ORDER_READY",
        status_reason="test",
        timing_authority=HsreS23TimingAuthority(
            planning_time="09:16:00",
            orpt_cutoff="09:24:59",
            rc_cutoff="09:29:59",
            effective_order_time="09:24:59",
            source_strategy_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
            source_config_paths=(),
        ),
        base_packet_hash="base",
        base_contract=contract,
        base_entry=entry,
        base_target=target,
        base_stoploss=stoploss,
        orpt_evidence=None,
        entry_missed_result=None,
        recalculation_required=False,
        recalculation_inputs={},
        recalculation_result=None,
        recalculated_contract=None,
        recalculated_option_reference_packet=None,
        rc_required=False,
        rc_evidence=None,
        final_effective_contract=contract,
        final_effective_entry=entry,
        final_effective_target=target,
        final_effective_stoploss=stoploss,
        final_decision_verdict="NORMAL_ORDER_READY",
        provenance={},
        no_lookahead_evidence=(),
    )


def _builder(root: Path) -> HsreS23TradeLifecycleBuilder:
    return HsreS23TradeLifecycleBuilder(
        NiftyHsreHistoricalMarketDataProvider(root, max_cached_sessions=16)
    )


def test_pre_order_bar_cannot_fill_waiting_order(tmp_path: Path) -> None:
    _write_options(
        tmp_path,
        date(2024, 1, 1),
        [
            ("09:24:00", "NIFTY04JAN2450CE", 110.0, 120.0, 90.0, 100.0, 1000, 1),
            ("09:25:00", "NIFTY04JAN2450CE", 160.0, 170.0, 151.0, 160.0, 1000, 1),
        ],
    )

    packet = _builder(tmp_path).build_from_final_order(_final_order())

    assert packet.status == "ENTRY_NOT_TRIGGERED"
    assert packet.entry_triggered is False
    assert packet.contract_series_audit is not None
    assert packet.contract_series_audit.bar_count == 1
    assert packet.contract_series_audit.first_usable_bar.timestamp == "2024-01-01T09:25:00"


def test_entry_and_target_process_chronologically_after_fill(tmp_path: Path) -> None:
    _write_options(
        tmp_path,
        date(2024, 1, 1),
        [
            ("09:25:00", "NIFTY04JAN2450CE", 160.0, 170.0, 151.0, 160.0, 1000, 1),
            ("09:26:00", "NIFTY04JAN2450CE", 110.0, 120.0, 95.0, 100.0, 1000, 1),
            ("09:27:00", "NIFTY04JAN2450CE", 80.0, 90.0, 45.0, 60.0, 1000, 1),
        ],
    )

    packet = _builder(tmp_path).build_from_final_order(_final_order())

    assert packet.status == "TRADE_CLOSED"
    assert packet.entry_triggered is True
    assert packet.trigger_time == "2024-01-01T09:26:00"
    assert packet.fill_price == 100.0
    assert packet.exit_time == "2024-01-01T09:27:00"
    assert packet.exit_reason == "TARGET_HIT"
    assert packet.pnl.gross_points == pytest.approx(50.0)
    assert packet.pnl.net_points == pytest.approx(50.0)


def test_same_bar_target_stoploss_ambiguity_uses_existing_conservative_stop(
    tmp_path: Path,
) -> None:
    _write_options(
        tmp_path,
        date(2024, 1, 1),
        [
            ("09:25:00", "NIFTY04JAN2450CE", 100.0, 160.0, 40.0, 100.0, 1000, 1),
        ],
    )

    packet = _builder(tmp_path).build_from_final_order(_final_order())

    assert packet.status == "TRADE_CLOSED"
    assert packet.exit_reason == "STOPLOSS_HIT"
    assert packet.exit_price == 150.0
    assert packet.pnl.gross_points == pytest.approx(-50.0)
    assert "conservative stoploss" in packet.lifecycle_events[-1].notes


def test_future_extreme_does_not_retroactively_change_entry_or_exit(tmp_path: Path) -> None:
    _write_options(
        tmp_path,
        date(2024, 1, 1),
        [
            ("09:25:00", "NIFTY04JAN2450CE", 110.0, 120.0, 95.0, 100.0, 1000, 1),
            ("09:26:00", "NIFTY04JAN2450CE", 80.0, 90.0, 45.0, 60.0, 1000, 1),
            ("09:27:00", "NIFTY04JAN2450CE", 200.0, 999.0, 1.0, 200.0, 1000, 1),
        ],
    )

    packet = _builder(tmp_path).build_from_final_order(_final_order())

    assert packet.exit_reason == "TARGET_HIT"
    assert packet.exit_time == "2024-01-01T09:26:00"
    assert packet.pnl.gross_points == pytest.approx(50.0)
    assert packet.contract_series_audit is not None
    assert packet.contract_series_audit.session_high == 999.0


def test_deterministic_lifecycle_hash(tmp_path: Path) -> None:
    _write_options(
        tmp_path,
        date(2024, 1, 1),
        [
            ("09:25:00", "NIFTY04JAN2450CE", 110.0, 120.0, 95.0, 100.0, 1000, 1),
            ("09:26:00", "NIFTY04JAN2450CE", 80.0, 90.0, 45.0, 60.0, 1000, 1),
        ],
    )
    builder = _builder(tmp_path)

    first = builder.build_from_final_order(_final_order())
    second = builder.build_from_final_order(_final_order())

    assert builder.stable_packet_hash(first) == builder.stable_packet_hash(second)
    assert hsre_s23_trade_lifecycle_packet_to_dict(first) == hsre_s23_trade_lifecycle_packet_to_dict(second)
