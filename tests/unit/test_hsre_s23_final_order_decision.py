from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tfis.backtest.hsre_s23_final_order_decision import (
    HsreS23FinalOrderDecisionBuilder,
    hsre_s23_final_order_decision_packet_to_dict,
)
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


ROOT = Path(__file__).resolve().parents[2]
S23_ROOT = ROOT / "config" / "strategies" / "options_sell" / "nifty"


def _write_spot(
    root: Path,
    session: date,
    rows: list[tuple[str, float, float, float, float]],
) -> None:
    path = root / "spot" / f"{session.year}" / f"{session.month}" / f"nifty_spot{session:%d_%m_%Y}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,time,symbol,open,high,low,close"]
    for raw_time, open_, high, low, close in rows:
        lines.append(f"{session.isoformat()},{raw_time},NIFTY,{open_},{high},{low},{close}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def _write_base_context(root: Path) -> None:
    for session in [date(2023, 12, 26), date(2023, 12, 27), date(2023, 12, 28), date(2023, 12, 29)]:
        _write_spot(
            root,
            session,
            [("09:15:00", 95.0, 100.0, 90.0, 96.0), ("15:30:00", 96.0, 96.0, 96.0, 96.0)],
        )
    _write_spot(
        root,
        date(2024, 1, 1),
        [
            ("09:15:00", 100.0, 101.0, 99.0, 100.0),
            ("09:16:00", 100.0, 103.0, 99.0, 102.0),
            ("09:24:59", 102.0, 104.0, 98.0, 103.0),
            ("09:29:59", 103.0, 105.0, 89.0, 100.0),
            ("09:30:00", 100.0, 999.0, 1.0, 100.0),
        ],
    )


def _write_prior_contract_history(root: Path) -> None:
    rows = {
        date(2023, 12, 26): (20.0, 30.0, 10.0, 20.0),
        date(2023, 12, 27): (21.0, 31.0, 11.0, 21.0),
        date(2023, 12, 28): (22.0, 32.0, 12.0, 22.0),
        date(2023, 12, 29): (23.0, 33.0, 13.0, 23.0),
    }
    for session, (open_, high, low, close) in rows.items():
        _write_options(
            root,
            session,
            [
                ("09:16:00", "NIFTY04JAN2450CE", open_, high, low, close, 100000, 2),
                ("09:16:00", "NIFTY04JAN2490CE", 40.0, 50.0, 15.0, 40.0, 100000, 2),
            ],
        )


def _write_decision_session(root: Path, *, orpt_low: float = 9.0) -> None:
    _write_options(
        root,
        date(2024, 1, 1),
        [
            ("09:16:00", "NIFTY04JAN2450CE", 2.0, 2.0, 2.0, 2.0, 100000, 99),
            ("09:16:00", "NIFTY04JAN2400CE", 0.5, 0.5, 0.5, 0.5, 100000, 1),
            ("09:16:00", "NIFTY04JAN2450PE", 2.0, 2.0, 2.0, 2.0, 100000, 1),
            ("09:16:00", "NIFTY11JAN2450CE", 0.5, 0.5, 0.5, 0.5, 100000, 1),
            ("09:24:59", "NIFTY04JAN2450CE", 12.0, 13.0, orpt_low, 12.0, 100000, 4),
            ("09:29:59", "NIFTY04JAN2450CE", 10.0, 11.0, 8.0, 10.0, 100000, 4),
            ("09:29:59", "NIFTY04JAN2490CE", 2.0, 2.0, 2.0, 2.0, 100000, 10),
            ("09:30:00", "NIFTY04JAN2450CE", 1000.0, 1000.0, 1.0, 1000.0, 100000, 1),
            ("09:30:00", "NIFTY04JAN2490CE", 1000.0, 1000.0, 1.0, 1000.0, 100000, 1),
        ],
    )


def _builder(root: Path) -> HsreS23FinalOrderDecisionBuilder:
    provider = NiftyHsreHistoricalMarketDataProvider(root, max_cached_sessions=32)
    from tfis.backtest.hsre_s23_base_decision import HsreS23BaseDecisionBuilder

    return HsreS23FinalOrderDecisionBuilder(
        provider,
        base_decision_builder=HsreS23BaseDecisionBuilder(provider, strategy_root=S23_ROOT),
    )


def _ready_dataset(root: Path, *, orpt_low: float = 9.0) -> None:
    _write_base_context(root)
    _write_prior_contract_history(root)
    _write_decision_session(root, orpt_low=orpt_low)


def test_not_missed_final_decision_keeps_base_order(tmp_path: Path) -> None:
    _ready_dataset(tmp_path, orpt_low=11.0)

    packet = _builder(tmp_path).build_for_session(session_date=date(2024, 1, 1))

    assert packet.status == "NORMAL_ORDER_READY"
    assert packet.entry_missed_result is not None
    assert packet.entry_missed_result.entry_missed is False
    assert packet.final_effective_contract == "NIFTY04JAN2450CE"
    assert packet.final_effective_entry == pytest.approx(10.175)
    assert packet.rc_required is False


def test_missed_entry_recalculates_selects_new_contract_and_rebuilds_references(
    tmp_path: Path,
) -> None:
    _ready_dataset(tmp_path, orpt_low=9.0)

    packet = _builder(tmp_path).build_for_session(session_date=date(2024, 1, 1))

    assert packet.status == "RECALCULATED_ORDER_READY"
    assert packet.entry_missed_result is not None
    assert packet.entry_missed_result.entry_missed is True
    assert packet.entry_missed_result.comparison == "9.0 < 10.175"
    assert packet.recalculation_result is not None
    assert packet.recalculation_result.recalculated_start_strike == 93
    assert packet.recalculation_result.recalculated_end_strike == 88
    assert packet.recalculation_result.selection_audit is not None
    assert packet.recalculation_result.selection_audit.search_direction == "descending"
    assert packet.recalculation_result.selection_audit.qualified_count == 1
    assert packet.recalculated_contract == "NIFTY04JAN2490CE"
    assert packet.recalculated_option_reference_packet is not None
    assert packet.recalculated_option_reference_packet.prior_sessions_used == (
        "2023-12-27",
        "2023-12-28",
        "2023-12-29",
    )
    assert packet.recalculated_option_reference_packet.opt_prv_3dhh == 50.0
    assert packet.recalculated_option_reference_packet.opt_prv_3dll == 15.0
    assert packet.final_effective_contract == "NIFTY04JAN2490CE"
    assert packet.final_effective_entry == pytest.approx(7.4)
    assert packet.final_effective_target == pytest.approx(2.96)
    assert packet.final_effective_stoploss == pytest.approx(11.77)


def test_orpt_rc_and_reference_no_lookahead_ignore_later_extremes(tmp_path: Path) -> None:
    _ready_dataset(tmp_path, orpt_low=9.0)

    packet = _builder(tmp_path).build_for_session(session_date=date(2024, 1, 1))

    assert packet.orpt_evidence is not None
    assert packet.orpt_evidence.option_bar.low == 9.0
    assert packet.orpt_evidence.option_low_through_cutoff == 2.0
    assert packet.orpt_evidence.spot_high_through_cutoff == 104.0
    assert all(ts <= "2024-01-01T09:24:59" for ts in packet.orpt_evidence.option_source_timestamps)
    assert packet.rc_evidence is not None
    assert packet.rc_evidence.rc_snapshot.option_bar.low == 8.0
    assert packet.rc_evidence.rc_snapshot.option_low_through_cutoff == 2.0
    assert packet.rc_evidence.rc_snapshot.spot_high_through_cutoff == 105.0
    assert all(
        ts <= "2024-01-01T09:29:59"
        for ts in packet.rc_evidence.rc_snapshot.option_source_timestamps
    )
    assert packet.recalculated_option_reference_packet is not None
    assert packet.recalculated_option_reference_packet.opt_prv_3dhh == 50.0
    assert packet.recalculated_option_reference_packet.opt_prv_3dll == 15.0


def test_deterministic_final_decision_hash(tmp_path: Path) -> None:
    _ready_dataset(tmp_path, orpt_low=9.0)
    builder = _builder(tmp_path)

    first = builder.build_for_session(session_date=date(2024, 1, 1))
    second = builder.build_for_session(session_date=date(2024, 1, 1))

    assert builder.stable_packet_hash(first) == builder.stable_packet_hash(second)
    assert hsre_s23_final_order_decision_packet_to_dict(first) == hsre_s23_final_order_decision_packet_to_dict(second)
