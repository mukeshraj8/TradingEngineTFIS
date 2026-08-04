from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import replace
from datetime import date, datetime, time
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
from tfis.fyers_read_only.models import CompletedCandleSet, FyersQuote
from tfis.persistence import canonical_hash
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance, load_enabled_strategy_registry
from tfis.runtime.multi_strategy.live_contract_selection import build_authoritative_historical_selection
from tfis.runtime.multi_strategy.session_reconstruction import (
    MARKET_OPEN,
    StrategyTimingPolicy,
    classify_market_session_state,
    reconstruct_option_selling_entry,
)


IST = ZoneInfo("Asia/Calcutta")
REPORT_DIR = REPO_ROOT / "reports" / "historical_reconstruction"
STATE_ROOT = REPO_ROOT / "tmp" / "tfis_supervisor_state"
DASHBOARD_ROOT = REPO_ROOT / "tmp" / "tfis_dashboard_v1" / "api"


TIMING_SOURCES: dict[str, dict[str, Any]] = {
    "S21_BANKNIFTY_INTERNAL_PAPER_A": {
        "policy": StrategyTimingPolicy(
            market_open=MARKET_OPEN,
            orpt_time=time(9, 24, 59, 400000),
            rc_time=time(9, 29, 59, 400000),
        ),
        "timing_source": {
            "orpt_rule_id": "S21.FRESH_ENTRY_ORPT_RC.001",
            "orpt_source": "TFISRulesAndSpec/AB6 OS.xlsx!AB6 OS:B114 = 09:24:59.400000",
            "rc_rule_id": "S21.FRESH_ENTRY_ORPT_RC.001",
            "rc_source": "TFISRulesAndSpec/AB6 OS.xlsx!AB6 OS:C114 and L114 = 09:29:59.400000",
        },
        "revised_entry": None,
    },
    "S22_RELIANCE_INTERNAL_PAPER_A": {
        "policy": StrategyTimingPolicy(market_open=MARKET_OPEN, orpt_time=time(9, 24, 59, 400000), rc_time=time(9, 29, 59, 400000)),
        "timing_source": {
            "orpt_rule_id": "S22.ENTRY_ORPT_RC.001",
            "orpt_source": "src/tfis/adapters/phase5e/s22_reliance.py:92, 844-851",
            "rc_rule_id": "S22.ENTRY_ORPT_RC.001",
            "rc_source": "src/tfis/adapters/phase5e/s22_reliance.py:93, 844-851",
        },
        "revised_entry": Decimal("57.00"),
    },
    "S23_NIFTY_INTERNAL_PAPER_A": {
        "policy": StrategyTimingPolicy(
            market_open=MARKET_OPEN,
            orpt_time=time(9, 24, 59, 400000),
            rc_time=time(9, 29, 59, 400000),
        ),
        "timing_source": {
            "orpt_rule_id": "S23.PUT_ORPT_RC.001 / S23 call-side equivalent",
            "orpt_source": "TFISRulesAndSpec/AB6 OS.xlsx!AB6 OS:B176 = 09:24:59.400000",
            "rc_rule_id": "S23.PUT_ORPT_RC.001 / S23 call-side equivalent",
            "rc_source": "TFISRulesAndSpec/AB6 OS.xlsx!AB6 OS:C176 and L176 = 09:29:59.400000",
        },
        "revised_entry": None,
    },
}

UNDERLYING_SYMBOLS = {
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "RELIANCE": "NSE:RELIANCE-EQ",
    "NIFTY": "NSE:NIFTY50-INDEX",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstruct current intraday entry eligibility from authoritative market evidence.")
    parser.add_argument("--session-date", type=date.fromisoformat, default=date(2026, 8, 4))
    args = parser.parse_args(argv)

    now = datetime.now(tz=IST)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    preserved = preserve_current_session_evidence(now=now)
    registry = load_enabled_strategy_registry(REPO_ROOT / "config" / "internal_paper_strategy_instances.yaml")
    heartbeat = _read_json(STATE_ROOT / "heartbeat.json")
    checkpoint = _read_json(STATE_ROOT / f"NSE_{args.session_date.isoformat()}_UNIFIED_INTERNAL_PAPER.checkpoint.json")
    summary = {
        "schema_version": "tfis.session_reconstruction.rule.v1",
        "captured_at": now.isoformat(),
        "trading_date": args.session_date.isoformat(),
        "current_time": now.isoformat(),
        "market_session_state": classify_market_session_state(now),
        "invalid_runtime_classification": {
            "classification": "INVALID_RUNTIME_CLASSIFICATION",
            "timestamp": heartbeat.get("timestamp"),
            "previous_state": "WAITING_FOR_MARKET",
            "incorrect_state": "LATE_START_NO_NEW_ENTRY",
            "root_cause": "Cycle timestamp after 09:15 was used as late-start proxy instead of persisted supervisor session start time.",
            "affected_strategy_instances": [item.strategy_instance_id for item in registry.enabled_instances],
        },
        "preserved_artifacts": preserved,
        "session_start_authority": {
            "session_started_at": heartbeat.get("session_started_at") or checkpoint.get("session_started_at") or _read_json(REPO_ROOT / "reports" / "live_supervisor" / "complete_session_preflight.json").get("captured_at"),
            "process_start_source": "heartbeat/checkpoint/preflight explicit evidence",
            "market_open_time": MARKET_OPEN.isoformat(),
            "current_cycle_time": heartbeat.get("timestamp"),
            "late_start_state_persisted": heartbeat.get("late_start_mode"),
            "checkpoint_late_start_state": checkpoint.get("late_start_mode"),
        },
    }
    _write_json(REPORT_DIR / "session_reconstruction_rule.json", summary)

    auth_adapter = FyersAuthenticationAdapter(tfis_root=REPO_ROOT, logical_account_ref="session-reconstruction")
    auth_result = auth_adapter.authenticate(allow_refresh=False, validate_session=True)
    refresh_recovered = False
    if auth_result.status is BrokerSessionStatus.SESSION_VALIDATION_FAILED:
        auth_result = auth_adapter.authenticate(allow_refresh=True, validate_session=True)
        refresh_recovered = auth_result.status is BrokerSessionStatus.AUTHENTICATED
    if auth_result.status != BrokerSessionStatus.AUTHENTICATED or auth_result.session is None:
        failure = {
            "verdict": "INTRADAY_SESSION_RECONSTRUCTION_BLOCKED",
            "reason": auth_result.status.value,
            "external_broker_order_authority": "NONE",
            "refresh_recovered": refresh_recovered,
        }
        _write_json(REPORT_DIR / "baseline_recovery_assessment.json", failure)
        print(json.dumps(failure, indent=2))
        return 2

    adapter = FyersReadOnlyAdapter.from_validated_session(auth_result.session, now_provider=lambda: datetime.now(tz=IST), timeout_seconds=3.0, max_retries=0)
    symbol_master = adapter.fetch_symbol_master("NSEFO")
    instrument_records = symbol_master.payload if symbol_master.status is FyersReadOnlyStatus.SUCCESS else ()
    today_evidence: dict[str, Any] = {"captured_at": now.isoformat(), "market_state": classify_market_session_state(now), "instances": {}}
    entry_results: dict[str, Any] = {}
    option_path_results: dict[str, Any] = {}
    checkpoint_payload = _load_json_if_exists(STATE_ROOT / "NSE_2026-08-04_UNIFIED_INTERNAL_PAPER.checkpoint.json")
    checkpoint_continuity = checkpoint_payload.get("continuity") if isinstance(checkpoint_payload, dict) else {}
    checkpoint_reads = checkpoint_payload.get("selected_contract_reads") if isinstance(checkpoint_payload, dict) else {}

    for instance in registry.enabled_instances:
        symbol = instance.symbol
        selection = build_authoritative_historical_selection(
            repo_root=REPO_ROOT,
            instance=instance,
            adapter=adapter,
            instrument_records=instrument_records,
            session_date=args.session_date,
            now=now,
        )
        underlying_symbol = UNDERLYING_SYMBOLS.get(symbol, f"NSE:{symbol}-EQ")
        timing = TIMING_SOURCES[instance.strategy_instance_id]
        underlying_history = adapter.fetch_historical_candles(
            symbol=underlying_symbol,
            resolution="1",
            range_from=args.session_date,
            range_to=args.session_date,
            exclude_incomplete_after=now,
        )
        option_history = None
        current_quote = None
        selected_contract = selection.selected_contract
        if selected_contract:
            option_history = adapter.fetch_historical_candles(
                symbol=selected_contract,
                resolution="1",
                range_from=args.session_date,
                range_to=args.session_date,
                exclude_incomplete_after=now,
            )
            current_quote_result = adapter.fetch_quotes((selected_contract,))
            if current_quote_result.status is FyersReadOnlyStatus.SUCCESS and current_quote_result.payload:
                current_quote = current_quote_result.payload[0]
        reconstructed = reconstruct_option_selling_entry(
            strategy_instance_id=instance.strategy_instance_id,
            timing_policy=timing["policy"],
            now=now,
            invalid_runtime_classification="INVALID_RUNTIME_CLASSIFICATION",
            selected_contract_authoritative=bool(selected_contract),
            base_entry=Decimal(str(selection.entry or instance.deterministic_projection.get("entry") or "0")),
            revised_entry=timing["revised_entry"],
            underlying_bars=underlying_history.payload if underlying_history and underlying_history.status is FyersReadOnlyStatus.SUCCESS else None,
            option_bars=option_history.payload if option_history and option_history.status is FyersReadOnlyStatus.SUCCESS else None,
            current_quote=current_quote,
        )
        today_evidence["instances"][instance.strategy_instance_id] = {
            "underlying_symbol": underlying_symbol,
            "selected_contract": selected_contract or None,
            "selected_contract_source": selection.evidence,
            "underlying_history_status": underlying_history.status.value,
            "option_history_status": option_history.status.value if option_history else "NOT_REQUESTED",
            "current_quote_status": "SUCCESS" if current_quote is not None else "NOT_REQUESTED",
            "timing_source": timing["timing_source"],
            "selection": selection.to_dict(),
            "selected_contract_reads": (
                checkpoint_reads.get(instance.strategy_instance_id, [])
                if isinstance(checkpoint_reads, Mapping)
                else []
            ),
            "underlying_history": underlying_history.to_dict(),
            "option_history": option_history.to_dict() if option_history else None,
            "current_quote": current_quote.to_dict() if current_quote else None,
        }
        entry_results[instance.strategy_instance_id] = reconstructed.to_dict()
        option_path_results[instance.strategy_instance_id] = _path_analysis(reconstructed, current_quote)

    _write_json(REPORT_DIR / "reconstruction_evidence_contract.json", today_evidence)
    _write_json(REPORT_DIR / "selected_contract_history.json", option_path_results)
    _write_json(REPORT_DIR / "entry_eligibility.json", {"captured_at": now.isoformat(), "instances": entry_results})
    _write_json(REPORT_DIR / "orpt_rc_reconstruction.json", {"orpt": _slice_by_key(entry_results, "orpt_result"), "rc": _slice_by_key(entry_results, "rc_result")})
    _write_json(REPORT_DIR / "s21_historical_selection.json", today_evidence["instances"]["S21_BANKNIFTY_INTERNAL_PAPER_A"])
    _write_json(REPORT_DIR / "s22_historical_selection.json", today_evidence["instances"]["S22_RELIANCE_INTERNAL_PAPER_A"])
    _write_json(REPORT_DIR / "s23_historical_selection.json", today_evidence["instances"]["S23_NIFTY_INTERNAL_PAPER_A"])

    assessment = _baseline_assessment(entry_results, summary["session_start_authority"])
    _write_json(REPORT_DIR / "august4_baseline_reassessment.json", assessment)
    _write_json(REPORT_DIR / "dashboard_explainability_projection.json", _dashboard_projection(entry_results, summary["session_start_authority"], now))
    _write_json(REPORT_DIR / "gap_register.json", _gap_register(entry_results))
    _write_json(REPORT_DIR / "legacy_reference_audit.json", _legacy_reference_audit())
    (REPORT_DIR / "historical_reconstruction_summary.md").write_text(_summary_md(now, summary, entry_results, assessment), encoding="utf-8")

    result = {
        "verdict": assessment["verdict"],
        "market_session_state": classify_market_session_state(now),
        "current_time": now.isoformat(),
        "instances": {key: value["current_entry_state"] for key, value in entry_results.items()},
        "external_broker_order_authority": "NONE",
        "refresh_recovered": refresh_recovered,
        "tcs_infy_activation_status": "DISABLED_PENDING_BASELINE_PASS",
    }
    print(json.dumps(result, indent=2))
    return 0


def _selected_contract_from_live_checkpoint(
    *,
    instance_id: str,
    checkpoint_continuity: Mapping[str, Any],
    registry_contract: str,
) -> str:
    continuity = checkpoint_continuity.get(instance_id)
    if isinstance(continuity, Mapping):
        selected = continuity.get("selected_contract")
        if selected:
            return str(selected)
    return registry_contract


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def preserve_current_session_evidence(*, now: datetime) -> dict[str, Any]:
    preserved: dict[str, Any] = {}
    artifacts = {
        "heartbeat": STATE_ROOT / "heartbeat.json",
        "checkpoint": STATE_ROOT / "NSE_2026-08-04_UNIFIED_INTERNAL_PAPER.checkpoint.json",
        "dashboard_snapshot": DASHBOARD_ROOT / "snapshot.json",
        "continuous_supervisor_summary": REPO_ROOT / "reports" / "live_supervisor" / "continuous_supervisor_summary.md",
        "complete_session_preflight": REPO_ROOT / "reports" / "live_supervisor" / "complete_session_preflight.json",
        "performance_metrics": REPO_ROOT / "reports" / "live_supervisor" / "performance_metrics.json",
        "gap_register": REPO_ROOT / "reports" / "live_supervisor" / "gap_register.json",
    }
    preserve_root = REPORT_DIR / "preserved_live_session"
    preserve_root.mkdir(parents=True, exist_ok=True)
    for key, source in artifacts.items():
        if source.exists():
            target = preserve_root / source.name
            shutil.copy2(source, target)
            preserved[key] = str(target)
    return preserved


def _path_analysis(reconstructed: Any, current_quote: FyersQuote | None) -> dict[str, Any]:
    return {
        "current_entry_state": reconstructed.current_entry_state,
        "normal_entry": reconstructed.normal_entry.details if reconstructed.normal_entry else None,
        "revised_entry": reconstructed.revised_entry.details if reconstructed.revised_entry else None,
        "current_quote_ltp": str(current_quote.ltp) if current_quote and current_quote.ltp is not None else None,
    }


def _baseline_assessment(entry_results: dict[str, Any], session_start_authority: dict[str, Any]) -> dict[str, Any]:
    states = {key: value["current_entry_state"] for key, value in entry_results.items()}
    if all(state.endswith("STILL_VALID") or state.endswith("ALREADY_MISSED") for state in states.values()):
        verdict = "AUGUST4_BASELINE_RECOVERED"
    elif any(state == "BLOCKED_INSUFFICIENT_HISTORICAL_EVIDENCE" for state in states.values()):
        verdict = "AUGUST4_BASELINE_PARTIALLY_RECOVERED"
    else:
        verdict = "AUGUST4_BASELINE_NOT_RECOVERABLE"
    return {
        "schema_version": "tfis.historical_reconstruction.baseline_assessment.v1",
        "verdict": verdict,
        "session_started_at": session_start_authority.get("session_started_at"),
        "instance_states": states,
        "reason": "Per-instance reconstruction replaces the invalid global late-start classification.",
    }


def _dashboard_projection(entry_results: dict[str, Any], session_start_authority: dict[str, Any], now: datetime) -> dict[str, Any]:
    strategies = []
    for instance_id, payload in entry_results.items():
        strategies.append(
            {
                "strategy_instance_id": instance_id,
                "session_started_at": session_start_authority.get("session_started_at"),
                "opening_evidence_source": "HISTORICALLY_RECONSTRUCTED" if payload["opening_price"] is not None else "MISSING",
                "orpt_status": payload["orpt_result"],
                "rc_status": payload["rc_result"],
                "current_entry_validity": payload["current_entry_state"],
                "reconstruction_evidence_quality": payload["option_evidence_quality"],
                "evidence_label": (
                    "HISTORICALLY_RECONSTRUCTED"
                    if payload["current_entry_state"] != "BLOCKED_INSUFFICIENT_HISTORICAL_EVIDENCE"
                    else "MISSING"
                ),
            }
        )
    return {
        "schema_version": "tfis.dashboard.historical_reconstruction_projection.v1",
        "captured_at": now.isoformat(),
        "strategies": strategies,
    }


def _gap_register(entry_results: dict[str, Any]) -> dict[str, Any]:
    gaps = []
    for instance_id, payload in entry_results.items():
        if payload["current_entry_state"] == "BLOCKED_INSUFFICIENT_HISTORICAL_EVIDENCE":
            gaps.append(
                {
                    "strategy_instance_id": instance_id,
                    "classification": "INSUFFICIENT_RECONSTRUCTION_EVIDENCE",
                    "reason": payload.get("block_reason"),
                }
            )
    return {"schema_version": "tfis.historical_reconstruction.gap_register.v1", "gaps": gaps}


def _slice_by_key(entry_results: dict[str, Any], key: str) -> dict[str, Any]:
    return {
        "schema_version": f"tfis.historical_reconstruction.{key}.v1",
        "instances": {instance_id: value[key] for instance_id, value in entry_results.items()},
    }


def _legacy_reference_audit() -> dict[str, Any]:
    references = (
        {
            "source": "D:\\TradingEngineTFIS\\docs\\strategy\\backtesting_and_experiments.md",
            "function_or_section": "historical option-chain selection and contract-specific lifecycle sections",
            "reusable_idea": "Reconstruct from actual listed contracts, preserve rejected candidates, then fetch selected-contract-specific path.",
            "old_rule_risk": "Legacy backtest documentation is plumbing-only and not business-rule authority.",
            "disposition": "ADAPTED_AS_PLUMBING_IDEA",
            "target_component": "src/tfis/runtime/multi_strategy/live_contract_selection.py",
        },
        {
            "source": "D:\\TradingEngineTFIS\\src\\tfis\\brokers\\fyers.py",
            "function_or_section": "_normalize_option_history_payload",
            "reusable_idea": "Contract-specific historical candle normalization and session-window filtering.",
            "old_rule_risk": "Transport/normalization only; no strategy thresholds or trade decisions copied.",
            "disposition": "ADAPTED_AS_PLUMBING_IDEA",
            "target_component": "src/tfis/fyers_read_only/adapter.py",
        },
        {
            "source": "D:\\TradingEngineTFIS\\src\\tfis\\paper\\validation.py",
            "function_or_section": "option-chain presence and contract-identity validation",
            "reusable_idea": "Fail closed when selected contract is not proven present in chain evidence.",
            "old_rule_risk": "Validation semantics only; not a replacement for workbook-sourced TFIS rules.",
            "disposition": "ADAPTED_AS_GUARDRAIL",
            "target_component": "src/tfis/runtime/multi_strategy/session_reconstruction.py",
        },
    )
    payload = {
        "schema_version": "tfis.historical_reconstruction.legacy_reference_audit.v1",
        "captured_at": datetime.now(tz=IST).isoformat(),
        "references": references,
    }
    payload["audit_hash"] = canonical_hash(payload["references"])
    return payload


def _summary_md(now: datetime, summary: dict[str, Any], entry_results: dict[str, Any], assessment: dict[str, Any]) -> str:
    lines = [
        "# Historical Reconstruction Summary",
        "",
        f"- Captured at: `{now.isoformat()}`",
        f"- Market state: `{classify_market_session_state(now)}`",
        f"- Session started at: `{summary['session_start_authority'].get('session_started_at')}`",
        f"- Invalid runtime classification preserved: `{summary['invalid_runtime_classification']['classification']}`",
        f"- Baseline recovery verdict: `{assessment['verdict']}`",
        "",
    ]
    for instance_id, payload in entry_results.items():
        lines.extend(
            [
                f"## {instance_id}",
                f"- Current state: `{payload['current_entry_state']}`",
                f"- ORPT: `{payload['orpt_result']}`",
                f"- RC: `{payload['rc_result']}`",
                f"- Option evidence: `{payload['option_evidence_quality']}`",
                f"- Block reason: `{payload.get('block_reason')}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
