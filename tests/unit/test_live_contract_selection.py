from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from tfis.fyers_read_only import FyersReadOnlyStatus
from tfis.fyers_read_only.models import FyersOptionChainSnapshot, FyersOptionContractQuote
from tfis.runtime.multi_strategy.live_contract_selection import (
    _json_safe,
    _select_from_actual_chain,
    build_authoritative_historical_selection,
)
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance


IST = ZoneInfo("Asia/Calcutta")


def _contract(
    symbol: str,
    *,
    underlying: str = "NIFTY50-INDEX",
    expiry: date = date(2026, 8, 6),
    strike: str,
    option_type: str,
    ltp: str | None,
    oi: str | None,
) -> FyersOptionContractQuote:
    return FyersOptionContractQuote(
        symbol=symbol,
        underlying=underlying,
        expiry=expiry,
        strike=Decimal(strike),
        option_type=option_type,
        ltp=Decimal(ltp) if ltp is not None else None,
        bid=Decimal("10"),
        ask=Decimal("11"),
        quote_timestamp=datetime(2026, 8, 4, 9, 10, tzinfo=IST),
        oi=Decimal(oi) if oi is not None else None,
        oi_quality="EXPLICIT",
        oi_unit="LOTS",
        volume=Decimal("100"),
        lot_size=50,
        tick_size=Decimal("0.05"),
        source_quality="LIVE_READ",
    )


def _chain(*contracts: FyersOptionContractQuote) -> FyersOptionChainSnapshot:
    return FyersOptionChainSnapshot(
        underlying="NIFTY50-INDEX",
        expiry=date(2026, 8, 6),
        captured_at=datetime(2026, 8, 4, 9, 10, tzinfo=IST),
        contracts=contracts,
        source_hash="source-hash",
        warnings=(),
    )


def test_select_from_actual_chain_picks_first_ideal_contract_in_traversal_order() -> None:
    result = _select_from_actual_chain(
        chain=_chain(
            _contract("NSE:NIFTY26AUG22600CE", strike="22600", option_type="CALL", ltp="240", oi="50000"),
            _contract("NSE:NIFTY26AUG22550CE", strike="22550", option_type="CALL", ltp="250", oi="55000"),
            _contract("NSE:NIFTY26AUG22500CE", strike="22500", option_type="CALL", ltp="260", oi="60000"),
        ),
        expected_underlying="NIFTY50-INDEX",
        expiry=date(2026, 8, 6),
        option_type="CALL",
        start_reference=Decimal("22600"),
        end_reference=Decimal("22500"),
        traversal_policy={
            "traversal_direction": "DESCENDING_START_TO_END",
            "start_round_mode": "DOWN",
            "end_round_mode": "DOWN",
            "end_offset_steps": 0,
        },
        ideal_premium=Decimal("245"),
        minimum_premium=Decimal("230"),
        minimum_oi=Decimal("32500"),
    )

    assert result["decision"] == "SELECTED"
    assert result["qualification_phase"] == "IDEAL_PREMIUM"
    assert result["selected_contract"]["symbol"] == "NSE:NIFTY26AUG22550CE"


def test_select_from_actual_chain_blocks_option_type_mismatch_without_cross_consuming_contracts() -> None:
    result = _select_from_actual_chain(
        chain=_chain(
            _contract("NSE:NIFTY26AUG22500PE", strike="22500", option_type="PUT", ltp="260", oi="60000"),
        ),
        expected_underlying="NIFTY50-INDEX",
        expiry=date(2026, 8, 6),
        option_type="CALL",
        start_reference=Decimal("22600"),
        end_reference=Decimal("22500"),
        traversal_policy={
            "traversal_direction": "DESCENDING_START_TO_END",
            "start_round_mode": "DOWN",
            "end_round_mode": "DOWN",
            "end_offset_steps": 0,
        },
        ideal_premium=Decimal("245"),
        minimum_premium=Decimal("230"),
        minimum_oi=Decimal("32500"),
    )

    assert result["decision"] == "NO_QUALIFYING_CONTRACT"
    assert result["selected_contract"] is None


def test_select_from_actual_chain_keeps_valid_contract_despite_other_contract_missing_oi() -> None:
    result = _select_from_actual_chain(
        chain=_chain(
            _contract("NSE:NIFTY26AUG22550CE", strike="22550", option_type="CALL", ltp="250", oi=None),
            _contract("NSE:NIFTY26AUG22500CE", strike="22500", option_type="CALL", ltp="260", oi="60000"),
        ),
        expected_underlying="NIFTY50-INDEX",
        expiry=date(2026, 8, 6),
        option_type="CALL",
        start_reference=Decimal("22550"),
        end_reference=Decimal("22500"),
        traversal_policy={
            "traversal_direction": "DESCENDING_START_TO_END",
            "start_round_mode": "DOWN",
            "end_round_mode": "DOWN",
            "end_offset_steps": 0,
        },
        ideal_premium=Decimal("255"),
        minimum_premium=Decimal("230"),
        minimum_oi=Decimal("32500"),
    )

    assert result["decision"] == "SELECTED"
    assert result["selected_contract"]["symbol"] == "NSE:NIFTY26AUG22500CE"


def test_json_safe_converts_nested_runtime_objects_to_json_friendly_values() -> None:
    payload = {
        "captured_at": datetime(2026, 8, 4, 9, 10, tzinfo=IST),
        "expiry": date(2026, 8, 6),
        "strike": Decimal("22500"),
        "items": ({1, 2}, _contract("NSE:NIFTY26AUG22500CE", strike="22500", option_type="CALL", ltp="250", oi="50000")),
    }

    safe = _json_safe(payload)

    assert json.loads(json.dumps(safe))["strike"] == "22500"


def test_historical_selection_uses_s22_report_trace_and_fetches_real_contract_history(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports" / "s22_reliance"
    report_dir.mkdir(parents=True)
    (report_dir / "s22_reliance_contract_selection.json").write_text(
        json.dumps(
            {
                "monthly_status": "BEAR_CF",
                "selected_branch": "BEAR_CALL",
                "selected_contract": {
                    "symbol": "NSE:RELIANCE26AUG1260CE",
                    "option_type": "CALL",
                    "expiry": "2026-08-27",
                    "strike": "1260",
                },
                "branch_candidates": [{"branch_id": "BEAR_CALL", "expiry_attempts": [{"rejected_candidates": [{"reason": "IDEAL_PREMIUM_NOT_MET"}]}]}],
            }
        ),
        encoding="utf-8",
    )

    class _Adapter:
        def fetch_historical_candles(self, **_kwargs):
            return type("Result", (), {"status": FyersReadOnlyStatus.SUCCESS, "payload": None})()

        def fetch_quotes(self, _symbols):
            quote = type(
                "Quote",
                (),
                {
                    "symbol": "NSE:RELIANCE26AUG1260CE",
                    "ltp": Decimal("57.60"),
                    "bid": Decimal("57.50"),
                    "ask": Decimal("58.05"),
                    "oi": Decimal("632500"),
                    "timestamp": datetime(2026, 8, 4, 12, 15, tzinfo=IST),
                },
            )()
            return type("Result", (), {"status": FyersReadOnlyStatus.SUCCESS, "payload": (quote,)})()

    instance = EnabledStrategyInstance(
        strategy_definition_id="S22_STOCKS_OP_SELL_MONTHLY_DIFF_2D_4D",
        strategy_version="s22.reliance.stage1.v1",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        account_reference="INTERNAL_PAPER_ACCOUNT_A",
        underlying={"exchange": "NSE", "symbol": "RELIANCE", "instrument_type": "STOCK"},
        product="OPTION_SELLING",
        enabled=True,
        configured_quantity={"lots": 1, "lot_size": 500},
        authority_mode="INTERNAL_PAPER_CONTROLLED",
        market_data_source="FYERS_READ_ONLY",
        rule_config_hash="rule-hash",
        risk_allocation={"max_positions": 1, "max_margin_usage_pct": 20},
        operator_approval_status="APPROVED_INTERNAL_PAPER",
        evidence_quality="DETERMINISTIC_TIMING_SUPPLEMENT",
        deterministic_projection={"entry": "57.50", "target": "23.00", "original_sl": "92.00"},
    )

    result = build_authoritative_historical_selection(
        repo_root=tmp_path,
        instance=instance,
        adapter=_Adapter(),
        instrument_records=(),
        session_date=date(2026, 8, 4),
        now=datetime(2026, 8, 4, 12, 15, tzinfo=IST),
    )

    assert result.status == "SELECTED_CONTRACT_RECONSTRUCTED"
    assert result.selected_contract == "NSE:RELIANCE26AUG1260CE"
    assert result.recovery_mode == "HISTORICALLY_RECONSTRUCTED"
    assert result.candidate_count == 1
