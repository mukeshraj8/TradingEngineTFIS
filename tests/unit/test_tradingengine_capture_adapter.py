from __future__ import annotations

import json
from pathlib import Path

import pytest

from tfis.paper.tradingengine_capture_adapter import (
    TradingEngineCaptureAdapterError,
    build_capture_audit,
    convert_capture_to_normalized_market_events,
    discover_context_session_dir,
    infer_option_quotes_path,
    normalize_tradingengine_option_symbol,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "tradingengine_capture_adapter"
)
CONTEXT_SESSION_DIR = FIXTURE_ROOT / "context_session"
OPTION_QUOTES_CSV = FIXTURE_ROOT / "NIFTY50_option_quotes_20260527.csv"
SELECTED_SYMBOL = "NSE:NIFTY2660223200CE"


def test_build_capture_audit_reports_usable_market_leg() -> None:
    audit = build_capture_audit(
        context_session_dir=CONTEXT_SESSION_DIR,
        option_quotes_path=OPTION_QUOTES_CSV,
    )

    assert audit.session_date == "2026-05-27"
    assert audit.covers_0915 is True
    assert audit.covers_orpt is True
    assert audit.covers_rc is True
    assert audit.has_option_quotes_archive is True
    assert audit.option_chain_contract_count_at_rc == 3
    assert audit.selected_contract_observed_at_rc == SELECTED_SYMBOL
    assert audit.sample_normalized_option_symbol == "NIFTY_20260602_23200_CE"
    assert audit.recommendation == "usable"


def test_convert_capture_to_normalized_market_events_emits_ingress_events(
    tmp_path: Path,
) -> None:
    artifact = convert_capture_to_normalized_market_events(
        context_session_dir=CONTEXT_SESSION_DIR,
        option_quotes_path=OPTION_QUOTES_CSV,
        selected_contract_symbol=SELECTED_SYMBOL,
        output_jsonl_path=tmp_path / "market_events.jsonl",
    )

    assert artifact.output_event_count == 6
    lines = [
        json.loads(line)
        for line in artifact.output_jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [line["event_type"] for line in lines] == [
        "UNDERLYING_SNAPSHOT",
        "UNDERLYING_SNAPSHOT",
        "UNDERLYING_SNAPSHOT",
        "UNDERLYING_QUOTE",
        "OPTION_CHAIN_SNAPSHOT",
        "SELECTED_CONTRACT_QUOTE",
    ]
    option_chain_payload = lines[4]["payload"]
    selected_payload = lines[5]["payload"]
    assert option_chain_payload["underlying_symbol"] == "NIFTY"
    assert len(option_chain_payload["contracts"]) == 3
    assert selected_payload["symbol"] == "NIFTY_20260602_23200_CE"
    assert selected_payload["option_type"] == "CALL"
    assert selected_payload["bid"] == pytest.approx(787.0)


def test_normalize_tradingengine_option_symbol_decodes_weekly_format() -> None:
    assert (
        normalize_tradingengine_option_symbol("NSE:NIFTY2660223200CE")
        == "NIFTY_20260602_23200_CE"
    )


def test_normalize_tradingengine_option_symbol_decodes_monthly_format() -> None:
    assert (
        normalize_tradingengine_option_symbol("NSE:NIFTY26MAY22650CE")
        == "NIFTY_20260528_22650_CE"
    )


def test_convert_capture_requires_selected_quote_presence(tmp_path: Path) -> None:
    with pytest.raises(TradingEngineCaptureAdapterError):
        convert_capture_to_normalized_market_events(
            context_session_dir=CONTEXT_SESSION_DIR,
            option_quotes_path=OPTION_QUOTES_CSV,
            selected_contract_symbol="NSE:NIFTY2660229999CE",
            output_jsonl_path=tmp_path / "market_events.jsonl",
        )


def test_root_discovery_finds_context_session_and_option_quotes(tmp_path: Path) -> None:
    tradingdata_root = tmp_path / "TradingData"
    context_target = (
        tradingdata_root
        / "captures"
        / "context_sessions"
        / "2026-05-27"
        / CONTEXT_SESSION_DIR.name
    )
    context_target.mkdir(parents=True)
    for source in CONTEXT_SESSION_DIR.iterdir():
        context_target.joinpath(source.name).write_text(
            source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    option_target = (
        tradingdata_root
        / "data"
        / "nifty"
        / "20260527"
        / "options"
        / "index"
    )
    option_target.mkdir(parents=True)
    option_file = option_target / OPTION_QUOTES_CSV.name
    option_file.write_text(OPTION_QUOTES_CSV.read_text(encoding="utf-8"), encoding="utf-8")

    discovered_session = discover_context_session_dir(
        tradingdata_root=tradingdata_root,
        session_date="2026-05-27",
    )
    discovered_option_quotes = infer_option_quotes_path(
        tradingdata_root=tradingdata_root,
        session_date="2026-05-27",
    )

    assert discovered_session == context_target
    assert discovered_option_quotes == option_file
