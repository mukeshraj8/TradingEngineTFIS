from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.broker.authentication import BrokerSessionStatus
from tfis.broker.authentication.fyers import FyersAuthenticationAdapter
from tfis.fyers_read_only import FyersReadOnlyAdapter, FyersReadOnlyStatus
from tfis.runtime.multi_strategy.fast_track_development import (
    build_current_entry_actions,
    write_fast_track_reports,
)
from tfis.runtime.multi_strategy.live_contract_selection import build_authoritative_historical_selection
from tfis.runtime.multi_strategy.registry import load_enabled_strategy_registry
from tfis.runtime.multi_strategy.session_reconstruction import (
    MARKET_OPEN,
    StrategyTimingPolicy,
    classify_market_session_state,
    reconstruct_option_selling_entry,
)


IST = ZoneInfo("Asia/Calcutta")

UNDERLYING_SYMBOLS = {
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "RELIANCE": "NSE:RELIANCE-EQ",
    "NIFTY": "NSE:NIFTY50-INDEX",
}

TIMING_SOURCES: dict[str, dict[str, Any]] = {
    "S21_BANKNIFTY_INTERNAL_PAPER_A": {
        "policy": StrategyTimingPolicy(market_open=MARKET_OPEN, orpt_time=datetime.strptime("09:24:59.400000", "%H:%M:%S.%f").time(), rc_time=datetime.strptime("09:29:59.400000", "%H:%M:%S.%f").time()),
        "revised_entry": None,
    },
    "S22_RELIANCE_INTERNAL_PAPER_A": {
        "policy": StrategyTimingPolicy(market_open=MARKET_OPEN, orpt_time=datetime.strptime("09:24:59.400000", "%H:%M:%S.%f").time(), rc_time=datetime.strptime("09:29:59.400000", "%H:%M:%S.%f").time()),
        "revised_entry": "57.00",
    },
    "S23_NIFTY_INTERNAL_PAPER_A": {
        "policy": StrategyTimingPolicy(market_open=MARKET_OPEN, orpt_time=datetime.strptime("09:24:59.400000", "%H:%M:%S.%f").time(), rc_time=datetime.strptime("09:29:59.400000", "%H:%M:%S.%f").time()),
        "revised_entry": None,
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Complete fast-track development reconstruction and current-time internal-paper simulation using FYERS read-only evidence.")
    parser.add_argument("--session-date", type=date.fromisoformat, default=date(2026, 8, 4))
    parser.add_argument("--registry", default="config/internal_paper_strategy_instances.yaml")
    parser.add_argument("--report-dir", default="reports/fast_track_development")
    args = parser.parse_args(argv)

    now = datetime.now(tz=IST)
    registry = load_enabled_strategy_registry(REPO_ROOT / args.registry)

    auth_adapter = FyersAuthenticationAdapter(tfis_root=REPO_ROOT, logical_account_ref="fast-track-development")
    auth_result = auth_adapter.authenticate(allow_refresh=False, validate_session=True)
    refreshed = False
    if auth_result.status is BrokerSessionStatus.SESSION_VALIDATION_FAILED:
        auth_result = auth_adapter.authenticate(allow_refresh=True, validate_session=True)
        refreshed = auth_result.status is BrokerSessionStatus.AUTHENTICATED
    if auth_result.status is not BrokerSessionStatus.AUTHENTICATED or auth_result.session is None:
        payload = {
            "verdict": "FAST_TRACK_DEVELOPMENT_BLOCKED",
            "reason": auth_result.status.value,
            "refreshed": refreshed,
            "external_broker_order_authority": "NONE",
        }
        print(json.dumps(payload, indent=2))
        return 2

    adapter = FyersReadOnlyAdapter.from_validated_session(
        auth_result.session,
        now_provider=lambda: datetime.now(tz=IST),
        timeout_seconds=3.0,
        max_retries=0,
    )
    symbol_master = adapter.fetch_symbol_master("NSEFO")
    instrument_records = symbol_master.payload if symbol_master.status is FyersReadOnlyStatus.SUCCESS else ()
    baseline_results: dict[str, Any] = {}
    continuities: dict[str, Any] = {}

    for instance in registry.enabled_instances:
        selection = build_authoritative_historical_selection(
            repo_root=REPO_ROOT,
            instance=instance,
            adapter=adapter,
            instrument_records=instrument_records,
            session_date=args.session_date,
            now=now,
        )
        underlying_history = adapter.fetch_historical_candles(
            symbol=UNDERLYING_SYMBOLS.get(instance.symbol, f"NSE:{instance.symbol}-EQ"),
            resolution="1",
            range_from=args.session_date,
            range_to=args.session_date,
            exclude_incomplete_after=now,
        )
        option_history = None
        current_quote = None
        if selection.selected_contract:
            option_history = adapter.fetch_historical_candles(
                symbol=selection.selected_contract,
                resolution="1",
                range_from=args.session_date,
                range_to=args.session_date,
                exclude_incomplete_after=now,
            )
            current_quote_result = adapter.fetch_quotes((selection.selected_contract,))
            if current_quote_result.status is FyersReadOnlyStatus.SUCCESS and current_quote_result.payload:
                current_quote = current_quote_result.payload[0]

        timing_source = TIMING_SOURCES[instance.strategy_instance_id]
        reconstruction = reconstruct_option_selling_entry(
            strategy_instance_id=instance.strategy_instance_id,
            timing_policy=timing_source["policy"],
            now=now,
            invalid_runtime_classification="HISTORICAL_RECONSTRUCTION_ALLOWED",
            selected_contract_authoritative=bool(selection.selected_contract),
            base_entry=Decimal(str(selection.entry or instance.deterministic_projection.get("entry") or "0")),
            revised_entry=Decimal(str(timing_source["revised_entry"])) if timing_source["revised_entry"] is not None else None,
            underlying_bars=underlying_history.payload if underlying_history.status is FyersReadOnlyStatus.SUCCESS else None,
            option_bars=option_history.payload if option_history and option_history.status is FyersReadOnlyStatus.SUCCESS else None,
            current_quote=current_quote,
        )
        continuities[instance.strategy_instance_id] = {
            **selection.to_dict(),
            **{
                "current_entry_state": reconstruction.current_entry_state,
                "orpt_result": reconstruction.orpt_result,
                "rc_result": reconstruction.rc_result,
                "reconstruction": reconstruction.to_dict(),
            },
        }
        baseline_results[instance.strategy_instance_id] = {
            "selection": selection.to_dict(),
            "reconstruction": reconstruction.to_dict(),
            "market_session_state": classify_market_session_state(now),
        }

    current_entry_actions = build_current_entry_actions(
        registry_instances=registry.enabled_instances,
        continuities=continuities,
        now=now,
        trading_session_id=f"NSE:{args.session_date.isoformat()}:FAST_TRACK_DEVELOPMENT",
    )

    tcs_result = _development_candidate_result(
        symbol="TCS",
        decision_pack=_read_json(REPO_ROOT / "reports" / "s22_multi_stock" / "candidate_activation_decision_pack.json"),
        contract_selection=_read_json(REPO_ROOT / "reports" / "contract_selection" / "actual_strike_set_contract.json"),
        now=now,
    )
    infy_result = _development_candidate_result(
        symbol="INFY",
        decision_pack=_read_json(REPO_ROOT / "reports" / "s22_multi_stock" / "candidate_activation_decision_pack.json"),
        contract_selection=_read_json(REPO_ROOT / "reports" / "contract_selection" / "infy_actual_chain_selection.json"),
        now=now,
    )

    written = write_fast_track_reports(
        report_dir=REPO_ROOT / args.report_dir,
        session_date=args.session_date,
        trading_session_id=f"NSE:{args.session_date.isoformat()}:FAST_TRACK_DEVELOPMENT",
        baseline_results=baseline_results,
        current_entry_actions=current_entry_actions,
        tcs_result=tcs_result,
        infy_result=infy_result,
    )
    payload = {
        "verdict": "FAST_TRACK_DEVELOPMENT_REPORTS_WRITTEN",
        "captured_at": now.isoformat(),
        "report_dir": str(REPO_ROOT / args.report_dir),
        "report_count": len(written),
        "baseline_states": {
            key: value["reconstruction"]["current_entry_state"]
            for key, value in baseline_results.items()
        },
        "current_entry_actions": {
            key: value.get("decision")
            for key, value in current_entry_actions["outcomes"].items()
        },
        "external_broker_order_authority": "NONE",
    }
    print(json.dumps(payload, indent=2))
    return 0


def _development_candidate_result(
    *,
    symbol: str,
    decision_pack: Mapping[str, Any],
    contract_selection: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    candidate = (decision_pack.get("candidates") or {}).get(symbol) if isinstance(decision_pack.get("candidates"), Mapping) else {}
    return {
        "schema_version": "tfis.fast_track.s22_candidate_development_result.v1",
        "captured_at": now.isoformat(),
        "symbol": symbol,
        "status": "DEVELOPMENT_READY_BUT_NOT_ACTIVATED",
        "reason": "Candidate metadata and actual listed contract evidence exist, but this slice did not add a generic source-closed S22 multi-stock execution-plan builder.",
        "recommendation": candidate.get("recommendation"),
        "selected_contract": candidate.get("selected_contract") or contract_selection.get("selected_contract"),
        "remaining_gap": ["GENERIC_S22_MULTI_STOCK_EXECUTION_PLAN_PENDING"],
        "external_broker_order_authority": "NONE",
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
