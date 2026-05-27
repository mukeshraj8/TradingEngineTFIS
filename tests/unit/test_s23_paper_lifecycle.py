from __future__ import annotations

from datetime import date, timedelta

from tfis.domain.enums import OptionType
from tfis.paper import (
    EventEnvelope,
    PaperEventType,
    S23PaperFillSimulator,
    S23PaperGuardrailSettings,
    S23PaperLifecycleSimulator,
    S23PaperSessionReviewer,
    SelectedContractBarEvent,
    compare_paper_session_to_historical,
)

from test_s23_paper_fill_simulator import (
    CONTRACT_SYMBOL,
    _envelope,
    _handoff_ready_session,
    _historical_report_path,
    _read_json,
    _selected_contract_quote,
    _ts,
)


def _selected_contract_bar(
    *,
    effective_timestamp,
    symbol: str = CONTRACT_SYMBOL,
    open: float | None = 200.0,
    high: float | None = 210.0,
    low: float | None = 190.0,
    close: float | None = 200.0,
) -> SelectedContractBarEvent:
    return SelectedContractBarEvent(
        envelope=_envelope(
            PaperEventType.SELECTED_CONTRACT_BAR,
            effective_timestamp=effective_timestamp,
            source_id=f"selected-contract-bar-{symbol}",
        ),
        symbol=symbol,
        open=open,
        high=high,
        low=low,
        close=close,
        bar_start=effective_timestamp - timedelta(minutes=1),
        bar_end=effective_timestamp,
        volume=250.0,
    )


def _filled_session(tmp_path, *, session_id: str) -> object:
    session_dir = _handoff_ready_session(tmp_path, session_id=session_id)
    fill_simulator = S23PaperFillSimulator()
    fill_simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                bid=201.0,
                ask=202.0,
            ),
        ),
        created_at=_ts(9, 30, 57),
    )
    return session_dir


def test_fill_starts_position_then_target_hit_closes_position(tmp_path) -> None:
    session_dir = _filled_session(tmp_path, session_id="target-hit")
    simulator = S23PaperLifecycleSimulator()

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 31, 31),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    pnl = _read_json(artifact_set.paper_pnl_summary_path)
    assert summary["status"] == "PAPER_POSITION_CLOSED"
    assert summary["lifecycle_status"] == "PAPER_POSITION_CLOSED"
    assert summary["exit_reason_code"] == "target_hit"
    assert summary["exit_price"] == 81.0
    assert summary["position_opened"] is True
    assert summary["position_closed"] is True
    assert summary["gross_pnl_rupees"] == 11900.0
    assert summary["net_pnl_rupees"] == 11860.0
    assert pnl["gross_pnl_rupees"] == 11900.0
    assert pnl["net_pnl_rupees"] == 11860.0


def test_stoploss_hit_closes_position(tmp_path) -> None:
    session_dir = _filled_session(tmp_path, session_id="stoploss-hit")
    simulator = S23PaperLifecycleSimulator()

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 32, 0),
                bid=320.0,
                ask=321.0,
                ltp=320.5,
            ),
        ),
        created_at=_ts(9, 32, 1),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_POSITION_CLOSED"
    assert summary["exit_reason_code"] == "stoploss_or_fsl_hit"
    assert summary["exit_price"] == 322.0
    assert summary["net_pnl_rupees"] == -12240.0


def test_eod_square_off_closes_position(tmp_path) -> None:
    session_dir = _filled_session(tmp_path, session_id="eod-square-off")
    simulator = S23PaperLifecycleSimulator()

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(15, 28, 30),
                bid=149.0,
                ask=150.0,
                ltp=149.5,
            ),
        ),
        created_at=_ts(15, 28, 31),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_EOD_SQUARE_OFF"
    assert summary["exit_reason_code"] == "eod_square_off"
    assert summary["exit_price"] == 151.0


def test_same_bar_target_stop_conflict_chooses_conservative_stoploss(tmp_path) -> None:
    session_dir = _filled_session(tmp_path, session_id="bar-conflict")
    simulator = S23PaperLifecycleSimulator()

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_bar(
                effective_timestamp=_ts(10, 0, 0),
                high=330.0,
                low=70.0,
                close=200.0,
            ),
        ),
        created_at=_ts(10, 0, 1),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_POSITION_CLOSED"
    assert summary["exit_reason_code"] == "same_bar_target_stop_conflict_stoploss_wins"
    assert summary["exit_price"] == 321.0
    assert "same_bar_target_stop_conflict_stoploss_wins" in summary["lifecycle_warning_flags"]


def test_missing_lifecycle_data_aborts(tmp_path) -> None:
    session_dir = _filled_session(tmp_path, session_id="missing-lifecycle-data")
    simulator = S23PaperLifecycleSimulator()

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(),
        created_at=_ts(10, 5, 0),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_LIFECYCLE_ABORTED"
    assert summary["lifecycle_reason_code"] == "missing_selected_contract_lifecycle_market_data"
    assert artifact_set.paper_pnl_summary_path is None


def test_duplicate_lifecycle_start_is_blocked(tmp_path) -> None:
    session_dir = _filled_session(tmp_path, session_id="duplicate-lifecycle")
    simulator = S23PaperLifecycleSimulator()
    simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 31, 31),
    )

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 32, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 32, 31),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_LIFECYCLE_ABORTED"
    assert summary["guardrail_code"] == "duplicate_lifecycle_start"


def test_multiple_exit_signals_do_not_create_duplicate_exit(tmp_path) -> None:
    session_dir = _filled_session(tmp_path, session_id="duplicate-exit")
    simulator = S23PaperLifecycleSimulator()

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
            _selected_contract_quote(
                effective_timestamp=_ts(9, 32, 30),
                bid=320.0,
                ask=321.0,
                ltp=320.5,
            ),
        ),
        created_at=_ts(9, 32, 31),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    lifecycle_rows = (session_dir / "lifecycle_events.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert summary["status"] == "PAPER_POSITION_CLOSED"
    assert summary["exit_reason_code"] == "target_hit"
    assert len([row for row in lifecycle_rows if row.strip()]) == 3


def test_review_shows_lifecycle_and_pnl(tmp_path) -> None:
    session_dir = _filled_session(tmp_path, session_id="review-lifecycle")
    simulator = S23PaperLifecycleSimulator()
    simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 31, 31),
    )

    reviewer = S23PaperSessionReviewer()
    review_summary = reviewer.review_session(session_dir, bundle_directory=session_dir)
    markdown = reviewer.render_review_markdown(review_summary)

    assert review_summary.lifecycle_phase is not None
    assert review_summary.lifecycle_phase.status == "PAPER_POSITION_CLOSED"
    assert review_summary.lifecycle_phase.net_pnl_rupees == 11860.0
    assert "## Lifecycle Phase 2" in markdown
    assert "PAPER_POSITION_CLOSED" in markdown
    assert "Gross P&L" in markdown


def test_paper_vs_historical_includes_lifecycle_outcome(tmp_path) -> None:
    session_dir = _filled_session(tmp_path, session_id="historical-lifecycle")
    simulator = S23PaperLifecycleSimulator()
    simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 31, 31),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        _historical_report_path(tmp_path),
        bundle_directory=session_dir,
        session_date=date(2026, 5, 27),
    )

    assert summary.paper_lifecycle_status == "PAPER_POSITION_CLOSED"
    assert summary.paper_exit_reason_code == "target_hit"
    assert summary.paper_exit_price == 81.0
    assert "lifecycle" in summary.comparison_reason.lower() or summary.status.value in {
        "MATCH",
        "PARTIAL_MATCH",
    }
