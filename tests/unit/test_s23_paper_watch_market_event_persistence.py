from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path

from tfis.domain.enums import OptionType
from tfis.normalized_events import EventEnvelope, PaperEventType, SelectedContractQuoteEvent


def _load_watch_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_s23_paper_position_watch.py"
    spec = importlib.util.spec_from_file_location("run_s23_paper_position_watch", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_selected_contract_market_events_are_appended_as_jsonl(tmp_path: Path) -> None:
    module = _load_watch_module()
    observed_at = datetime(2026, 7, 3, 9, 31, 5)
    event = SelectedContractQuoteEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            session_date=date(2026, 7, 3),
            effective_timestamp=datetime(2026, 7, 3, 9, 31, 4),
            captured_at=observed_at,
            timezone="Asia/Kolkata",
            source_type="test",
            source_id="quote",
            synthetic_fixture=True,
            normalized_by="test",
        ),
        symbol="NIFTY_20260707_24100_CE",
        option_type=OptionType.CALL,
        strike=24100.0,
        expiry=date(2026, 7, 7),
        bid=285.5,
        ask=286.9,
        ltp=286.85,
        oi=3734250.0,
        volume=100.0,
    )

    path = module._append_selected_contract_market_events(
        tmp_path,
        events=(event,),
        observed_at=observed_at,
        watcher_pid=12345,
        trade_id="trade-1",
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert path.name == "selected_contract_market_events.jsonl"
    assert len(rows) == 1
    assert rows[0]["event_kind"] == "selected_contract_quote"
    assert rows[0]["observed_at"] == "2026-07-03T09:31:05"
    assert rows[0]["watcher_pid"] == 12345
    assert rows[0]["trade_id"] == "trade-1"
    assert rows[0]["symbol"] == "NIFTY_20260707_24100_CE"
    assert rows[0]["payload"]["ltp"] == 286.85
    assert rows[0]["payload"]["envelope"]["event_type"] == "SELECTED_CONTRACT_QUOTE"
