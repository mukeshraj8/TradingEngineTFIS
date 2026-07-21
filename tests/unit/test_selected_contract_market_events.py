from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from tfis.domain.enums import OptionType
from tfis.normalized_events import (
    EventEnvelope,
    PaperEventType,
    SelectedContractQuoteEvent,
)
from tfis.paper import (
    append_selected_contract_market_events,
    load_selected_contract_market_events,
    selected_contract_market_event_paths,
    selected_contract_market_event_process_pid,
)


def test_append_selected_contract_market_events_writes_supervisor_and_legacy_pid_fields(
    tmp_path: Path,
) -> None:
    observed_at = datetime(2026, 7, 21, 9, 31, 5)
    event = _quote_event(observed_at=observed_at)

    path = append_selected_contract_market_events(
        tmp_path,
        events=(event,),
        observed_at=observed_at,
        process_pid=14172,
        trade_id="trade-1",
        process_role="supervisor",
    )

    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert row["supervisor_pid"] == 14172
    assert row["watcher_pid"] == 14172
    assert selected_contract_market_event_process_pid(row) == 14172


def test_append_selected_contract_market_events_preserves_watcher_shape_for_legacy_writer(
    tmp_path: Path,
) -> None:
    observed_at = datetime(2026, 7, 21, 9, 31, 5)
    event = _quote_event(observed_at=observed_at)

    path = append_selected_contract_market_events(
        tmp_path,
        events=(event,),
        observed_at=observed_at,
        process_pid=12345,
        trade_id="trade-2",
        process_role="watcher",
    )

    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert "supervisor_pid" not in row
    assert row["watcher_pid"] == 12345
    assert selected_contract_market_event_process_pid(row) == 12345


def test_load_selected_contract_market_events_reads_all_matching_jsonl_files(
    tmp_path: Path,
) -> None:
    base = tmp_path / "selected_contract_market_events.jsonl"
    extra = tmp_path / "selected_contract_market_events.1.jsonl"
    base.write_text(
        json.dumps({"symbol": "NIFTY_20260723_24100_CE", "watcher_pid": 1}) + "\n",
        encoding="utf-8",
    )
    extra.write_text(
        json.dumps({"symbol": "NIFTY_20260723_24150_CE", "supervisor_pid": 2}) + "\n",
        encoding="utf-8",
    )

    paths = selected_contract_market_event_paths(tmp_path)
    rows = load_selected_contract_market_events(tmp_path)

    assert paths == (base, extra)
    assert [row["symbol"] for row in rows] == [
        "NIFTY_20260723_24100_CE",
        "NIFTY_20260723_24150_CE",
    ]


def _quote_event(*, observed_at: datetime) -> SelectedContractQuoteEvent:
    return SelectedContractQuoteEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            session_date=date(2026, 7, 21),
            effective_timestamp=observed_at,
            captured_at=observed_at,
            timezone="Asia/Kolkata",
            source_type="test",
            source_id="quote",
            synthetic_fixture=True,
            normalized_by="test",
        ),
        symbol="NIFTY_20260723_24100_CE",
        option_type=OptionType.CALL,
        strike=24100.0,
        expiry=date(2026, 7, 23),
        bid=285.5,
        ask=286.9,
        ltp=286.85,
        oi=3734250.0,
        volume=100.0,
    )
