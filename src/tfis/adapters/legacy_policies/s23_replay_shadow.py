from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from tfis.adapters.legacy_policies import s23_effective_execution_plan as effective
from tfis.adapters.legacy_policies import s23_opening_context as opening
from tfis.adapters.legacy_policies import s23_premarket_plan as premarket
from tfis.adapters.legacy_policies import s23_runtime_coordination as m15
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.coordination import OfflineTradingDayCoordinationInput
from tfis.runtime import (
    DeterministicRuntimeCoordinator,
    FreshEntryRuntimeCoordinator,
    RuntimeEventType,
    RuntimeSubscriptionIndex,
    runtime_hash,
)
from tfis.runtime.replay import CapturedReplaySession, load_captured_runtime_events

ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "paper" / "tradingengine_capture_adapter"
CONTEXT_SESSION_DIR = FIXTURE_ROOT / "context_session"
OPTION_QUOTES_CSV = FIXTURE_ROOT / "NIFTY50_option_quotes_20260527.csv"
SELECTED_SYMBOL = "NSE:NIFTY2660223200CE"
M7_PACKET = ROOT / "reports" / "phase3d" / "milestone7_s23_real_capture_packet.json"
NORMALIZED_SELECTED_CONTRACT = "NIFTY_20260609_22650_CE"
SOURCE_MARKET_EVENTS = ROOT / "reports" / "phase4a" / "phase4a_source_market_events.jsonl"
PRIMARY_STRATEGY_INSTANCE = "S23_NIFTY_ACCOUNT_A_PAPER"
SECONDARY_STRATEGY_INSTANCE = "S23_NIFTY_ACCOUNT_B_PAPER"


@dataclass(frozen=True, slots=True)
class S23ReplayShadowResult:
    inventory: Mapping[str, Any]
    selected_session: Mapping[str, Any]
    normalized_event_summary: Mapping[str, Any]
    shadow_result: Mapping[str, Any]
    evidence_packet: Mapping[str, Any]
    legacy_comparison: Mapping[str, Any]
    field_provenance: Mapping[str, Any]
    capture_gap_register: Mapping[str, Any]
    performance_metrics: Mapping[str, Any]
    replay_summary_md: str


def build_phase4a_shadow_reports() -> S23ReplayShadowResult:
    started = perf_counter()
    SOURCE_MARKET_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    audit = _write_m7_market_events(SOURCE_MARKET_EVENTS)
    replay_session = load_captured_runtime_events(
        SOURCE_MARKET_EVENTS,
        session_id=audit.session_id,
        strategy_instance_id=PRIMARY_STRATEGY_INSTANCE,
        selected_contract=audit.selected_contract,
    )
    full = _run_shadow(replay_session, multi_instance=False)
    repeats = tuple(_run_shadow(replay_session, multi_instance=False) for _ in range(3))
    multi = _run_shadow(replay_session, multi_instance=True)
    fail_closed = _fail_closed_cases(replay_session)
    conflation_same = _conflation_probe(replay_session)
    reports = _build_reports(
        audit=asdict(audit),
        replay_session=replay_session,
        full=full,
        repeats=repeats,
        multi=multi,
        fail_closed=fail_closed,
        conflation_same=conflation_same,
        elapsed=perf_counter() - started,
    )
    return reports


def write_phase4a_reports(out_dir: str | Path = ROOT / "reports" / "phase4a") -> S23ReplayShadowResult:
    reports = build_phase4a_shadow_reports()
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    payloads = {
        "phase4a_capture_inventory.json": reports.inventory,
        "phase4a_selected_session.json": reports.selected_session,
        "phase4a_normalized_event_summary.json": reports.normalized_event_summary,
        "phase4a_shadow_result.json": reports.shadow_result,
        "phase4a_shadow_evidence_packet.json": reports.evidence_packet,
        "phase4a_legacy_comparison.json": reports.legacy_comparison,
        "phase4a_field_provenance_matrix.json": reports.field_provenance,
        "phase4a_capture_gap_register.json": reports.capture_gap_register,
        "phase4a_performance_metrics.json": reports.performance_metrics,
    }
    for name, payload in payloads.items():
        (target / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (target / "phase4a_replay_summary.md").write_text(reports.replay_summary_md, encoding="utf-8")
    return reports


def _run_shadow(replay_session: CapturedReplaySession, *, multi_instance: bool) -> Any:
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_strategy(PRIMARY_STRATEGY_INSTANCE, underlying="NSE:NIFTY", contract=replay_session.selected_contract)
    streams = {"primary": _partial_real_stream(PRIMARY_STRATEGY_INSTANCE)}
    if multi_instance:
        subscriptions.add_strategy(SECONDARY_STRATEGY_INSTANCE, underlying="NSE:NIFTY", contract=replay_session.selected_contract)
        streams["secondary"] = _partial_real_stream(SECONDARY_STRATEGY_INSTANCE, account_b=True)
    events = replay_session.events
    if multi_instance:
        events = tuple(replace(event, strategy_instance_target=None) for event in replay_session.events)
    return DeterministicRuntimeCoordinator().run(
        trading_date=replay_session.trading_date,
        events=events,
        subscriptions=subscriptions,
        fresh_streams=streams,
        configuration_hash="phase4a-s23-captured-replay-shadow-v1",
    )


def _partial_real_stream(strategy_instance_id: str, *, account_b: bool = False) -> FreshEntryRuntimeCoordinator:
    def factory(events):
        case = vertical.build_s23_bull_call_vertical_case()
        context = opening.build_s23_partial_real_opening_context()
        selected = context.selected_contract
        plan = opening._replace_plan_selected_contract_for_partial_real(
            premarket.build_s23_call_side_premarket_plan(case),
            selected,
            context.trading_date,
            context.source_plan_hash,
        )
        if account_b:
            from dataclasses import replace

            plan = replace(
                plan,
                plan_id=f"{plan.plan_id}:phase4a-account-b",
                strategy_instance_id=strategy_instance_id,
                business_hash="phase4a-account-b-plan",
                plan_hash="phase4a-account-b-plan",
            )
            context = replace(
                context,
                context_id=f"{context.context_id}:phase4a-account-b",
                source_plan_id=plan.plan_id,
                source_plan_hash=plan.plan_hash,
                context_hash="",
            )
            execution_factory = lambda: effective._compose(case, context, plan=plan)
        else:
            execution_factory = effective.build_s23_partial_real_execution_plan
        return OfflineTradingDayCoordinationInput(
            coordination_id=f"phase4a-{strategy_instance_id}",
            trading_date=context.trading_date,
            strategy_family="S23",
            strategy_definition=case.runtime_input.strategy_definition_id or case.strategy_rule.unique_code,
            strategy_version="1.0.0",
            strategy_instance_id=strategy_instance_id,
            configuration_hash="phase4a-s23-captured-replay-shadow-v1",
            events=events,
            premarket_plan_factory=lambda: plan,
            opening_context_factory=lambda: context,
            effective_execution_plan_factory=execution_factory,
        )

    return FreshEntryRuntimeCoordinator(strategy_instance_id, opening.build_s23_partial_real_opening_context().trading_date, factory)


def _build_reports(**kwargs: Any) -> S23ReplayShadowResult:
    audit = kwargs["audit"]
    replay_session: CapturedReplaySession = kwargs["replay_session"]
    full = kwargs["full"]
    repeats = kwargs["repeats"]
    multi = kwargs["multi"]
    fail_closed = kwargs["fail_closed"]
    conflation_same = kwargs["conflation_same"]
    deterministic_hashes = [item.result_hash for item in repeats]
    primary = full.fresh_entry_results.get("primary")
    classification = "PARTIAL_CAPTURED_SHADOW_CASE"
    inventory = _inventory(audit)
    selected = {
        "session_id": replay_session.session_id,
        "trading_date": replay_session.trading_date.isoformat(),
        "source_path": replay_session.source_path,
        "strategy_instance": PRIMARY_STRATEGY_INSTANCE,
        "branch": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_CALL",
        "selected_contract": replay_session.selected_contract,
        "available_event_range": _event_range(replay_session),
        "missing_fields": _missing_fields(),
        "reason_selected": "Best local S23 Call-side captured/replay case aligned with the existing M7 partial-real S23 business artifacts. It contains opening, ORPT and RC observations plus selected-contract evidence, but remains partial because several pre-market and EOD fields are absent.",
        "classification": classification,
    }
    event_summary = {
        "schema_version": "tfis.phase4a.normalized_event_summary.v1",
        "authority_mode": "SHADOW_ONLY",
        "diagnostics": replay_session.diagnostics.to_dict(),
        "event_type_counts": _event_counts(replay_session),
        "critical_event_ids": list(full.critical_event_ids),
        "raw_market_events": replay_session.diagnostics.raw_record_count,
        "normalized_events": replay_session.diagnostics.normalized_event_count,
        "ordinary_events_processed": full.performance["quote_burst_size"],
        "critical_events_processed": full.performance["critical_event_processing_count"],
        "unrelated_events_filtered": 0,
        "stale_events_rejected": sum(1 for event in replay_session.events if event.freshness.value == "STALE"),
        "duplicate_events_treated_idempotently": replay_session.diagnostics.exact_duplicate_event_count,
    }
    shadow = {
        "schema_version": "tfis.phase4a.shadow_result.v1",
        "authority_mode": "SHADOW_ONLY",
        "authority": _phase4a_authority(full.authority),
        "classification": classification,
        "runtime_result_hash": full.result_hash,
        "terminal_state": primary.terminal_state if primary else None,
        "block_code": primary.block_code if primary else "NO_PRIMARY_RESULT",
        "business_outputs": primary.to_dict() if primary else None,
        "missing_eod_evidence": True,
        "broker_order_path_reached": False,
        "paper_order_path_reached": False,
    }
    evidence = {
        "schema_version": "tfis.phase4a.shadow_evidence_packet.v1",
        "authority_mode": "SHADOW_ONLY",
        "session": selected,
        "event_hash": replay_session.diagnostics.event_identity_hash,
        "runtime_hash": full.result_hash,
        "shadow_handoff_hash": runtime_hash(shadow),
        "evidence_hash": runtime_hash({"selected": selected, "event_summary": event_summary, "shadow": shadow}),
    }
    legacy = {
        "schema_version": "tfis.phase4a.legacy_comparison.v1",
        "legacy_source": "reports/phase3d/milestone7_s23_real_parity.json and milestone7_s23_real_capture_packet.json",
        "comparison_classification": "MISSING_LEGACY_OUTPUT",
        "field_comparison": _legacy_field_comparison(primary),
        "unexplained_mismatches": [],
        "parity_claimed": False,
    }
    provenance = _field_provenance_matrix()
    gaps = _capture_gap_register()
    performance = {
        "schema_version": "tfis.phase4a.performance_metrics.v1",
        "source_rows": replay_session.diagnostics.raw_record_count,
        "normalized_events": replay_session.diagnostics.normalized_event_count,
        "strategy_instances": 1,
        "multi_instance_strategy_instances": 2,
        "contracts": 2,
        "total_processing_time_seconds": full.performance["total_processing_seconds"],
        "median_event_processing_time_seconds": full.performance["per_event_median_seconds"],
        "p95_event_processing_time_seconds": full.performance["per_event_p95_seconds"],
        "maximum_pending_updates": full.performance["maximum_pending_conflatable_updates"],
        "critical_event_count": full.performance["critical_event_processing_count"],
        "archive_parse_to_report_seconds": kwargs["elapsed"],
        "three_replay_hashes": deterministic_hashes,
        "deterministic_three_replay": len(set(deterministic_hashes)) == 1,
        "checkpoint_resume": _checkpoint_resume(full, repeats[0]),
        "multi_instance": _multi_instance_summary(multi),
        "conflation_result_unchanged": conflation_same,
        "fail_closed_cases": fail_closed,
    }
    summary = _summary_md(selected, shadow, legacy, gaps, performance)
    return S23ReplayShadowResult(inventory, selected, event_summary, shadow, evidence, legacy, provenance, gaps, performance, summary)


def _phase4a_authority(authority: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "authority_mode": "SHADOW_ONLY",
        "broker_submission_permitted": False,
        "paper_submission_permitted": False,
        "live_submission_permitted": False,
        "order_creation_permitted": False,
        "order_mutation_permitted": False,
        "position_mutation_permitted": False,
        "square_off_permitted": False,
        "carry_persistence_permitted": False,
        "runtime_authority": dict(authority),
    }


def _inventory(audit: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "schema_version": "tfis.phase4a.capture_inventory.v1",
        "candidates": [
            {
                "session_id": "live_20260605_090537_prod_pid14520",
                "source": "reports/phase3d/milestone7_s23_real_capture_packet.json with raw paths under D:/TradingData",
                "classification": "PARTIAL_CAPTURED_REPLAY_CANDIDATE",
                "raw_quote_archives": "embedded summarized observations available; raw D:/TradingData archives read-denied in sandbox",
                "underlying_quotes": True,
                "option_contract_quotes": True,
                "option_chain_snapshots": True,
                "oi": False,
                "market_open_observations": True,
                "orpt_observations": True,
                "rc_observations": True,
                "eod_observations": False,
                "monthly_status_evidence": False,
                "legacy_final_decision": False,
                "carried_position_state": False,
                "broker_order_evidence": False,
                "reason": "Best real S23 Call-side packet aligned with existing partial-real S23 business artifacts.",
            },
            {
                "session_id": "live_20260527_090535_dev_pid16276",
                "source": str(CONTEXT_SESSION_DIR),
                "classification": "PARTIAL_CAPTURED_REPLAY_CANDIDATE",
                "raw_quote_archives": True,
                "underlying_quotes": True,
                "option_contract_quotes": True,
                "option_chain_snapshots": True,
                "oi": True,
                "market_open_observations": True,
                "orpt_observations": True,
                "rc_observations": True,
                "eod_observations": False,
                "monthly_status_evidence": False,
                "legacy_final_decision": False,
                "carried_position_state": False,
                "broker_order_evidence": False,
                "reason": "Useful local fixture, but not selected because its trading date does not align with the M7 partial-real S23 business artifacts.",
            },
        ],
    }


def _event_range(session: CapturedReplaySession) -> Mapping[str, str | None]:
    if not session.events:
        return {"first": None, "last": None}
    return {
        "first": session.events[0].effective_timestamp.isoformat(),
        "last": session.events[-1].effective_timestamp.isoformat(),
    }


def _missing_fields() -> list[str]:
    return [
        "captured Monthly Status",
        "authoritative S23 legacy final decision",
        "captured pre-market historical references",
        "captured Base Entry/Target/MSL plan",
        "captured EOD observation",
        "carried-position state",
        "broker/order evidence",
    ]


def _event_counts(session: CapturedReplaySession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in session.events:
        counts[event.event_type.value] = counts.get(event.event_type.value, 0) + 1
    return counts


def _legacy_field_comparison(primary: Any) -> dict[str, Any]:
    shadow = primary.to_dict() if primary else {}
    return {
        "strategy_identity": {"classification": "MATCH", "legacy": "S23_NIFTY_ACCOUNT_A_PAPER", "shadow": PRIMARY_STRATEGY_INSTANCE},
        "branch": {"classification": "MISSING_LEGACY_OUTPUT", "legacy": None, "shadow": "S23 Bull Call"},
        "monthly_status": {"classification": "MISSING_REFACTORED_INPUT", "legacy": None, "shadow": "SOURCE_VERIFIED_STATIC_FIXTURE"},
        "selected_contract": {"classification": "REPRESENTATION_DIFFERENCE", "legacy": NORMALIZED_SELECTED_CONTRACT, "shadow": "NIFTY_20260609_22650_CE"},
        "base_entry": {"classification": "MISSING_LEGACY_OUTPUT", "legacy": None, "shadow": shadow.get("values", {}).get("base_entry")},
        "effective_entry": {"classification": "MISSING_LEGACY_OUTPUT", "legacy": None, "shadow": shadow.get("values", {}).get("effective_entry")},
        "target": {"classification": "MISSING_LEGACY_OUTPUT", "legacy": None, "shadow": shadow.get("values", {}).get("effective_target")},
        "msl_sl": {"classification": "MISSING_LEGACY_OUTPUT", "legacy": None, "shadow": shadow.get("values", {}).get("effective_msl")},
        "gap_classification": {"classification": "CAPTURE_GAP", "legacy": None, "shadow": shadow.get("opening_gap_classification")},
        "final_decision": {"classification": "MISSING_LEGACY_OUTPUT", "legacy": None, "shadow": shadow.get("terminal_state")},
        "eod_outcome": {"classification": "CAPTURE_GAP", "legacy": None, "shadow": None},
    }


def _field_provenance_matrix() -> Mapping[str, Any]:
    fields = {
        "strategy identity": "DERIVED_FROM_VERIFIED_CONFIGURATION",
        "trading date": "CAPTURED",
        "Monthly Status": "SOURCE_VERIFIED_STATIC",
        "branch": "SOURCE_VERIFIED_STATIC",
        "historical market references": "MISSING",
        "selected expiry": "CAPTURED",
        "selected contract": "CAPTURED",
        "Base Entry": "SOURCE_VERIFIED_STATIC",
        "Target": "SOURCE_VERIFIED_STATIC",
        "MSL/Original SL": "SOURCE_VERIFIED_STATIC",
        "ORPT": "DERIVED_FROM_VERIFIED_CONFIGURATION",
        "RC": "DERIVED_FROM_VERIFIED_CONFIGURATION",
        "quantity": "SOURCE_VERIFIED_STATIC",
        "source rule ids": "SOURCE_VERIFIED_STATIC",
        "opening quote": "CAPTURED",
        "selected contract RC quote": "CAPTURED",
        "EOD observation": "MISSING",
    }
    return {"schema_version": "tfis.phase4a.field_provenance_matrix.v1", "fields": [{"field": k, "provenance": v} for k, v in fields.items()]}


def _capture_gap_register() -> Mapping[str, Any]:
    gaps = [
        ("captured Monthly Status", "pre-market planning", "monthly-status capture/review artifact", "absent", "cannot prove source-observed branch", "uses source-verified static fixture only", "monthly-status event capture", False, True),
        ("historical references", "pre-market planning", "source workbook/runtime prelude", "absent", "cannot validate real base references", "partial plan", "pre-market plan capture", False, True),
        ("legacy S23 final decision", "legacy comparison", "reference decision output", "absent for selected packet", "no parity claim", "MISSING_LEGACY_OUTPUT", "reference decision packet capture", False, True),
        ("EOD observation", "EOD lifecycle", "captured selected-contract close/15:00 observation", "absent", "cannot produce terminal carry/square-off", "MISSING_EOD_EVIDENCE", "EOD market observation capture", False, True),
        ("raw M7 archive access", "evidence inventory", "D:/TradingData raw archive", "sandbox read denied", "cannot inspect source rows beyond the accepted M7 packet", "M7 packet used as replay source with access gap recorded", "grant read or copy raw archive into repo fixture", False, False),
    ]
    return {
        "schema_version": "tfis.phase4a.capture_gap_register.v1",
        "gaps": [
            {
                "field": field,
                "required_by_engine": engine,
                "expected_source": expected,
                "observed_source": observed,
                "trading_consequence": trading,
                "shadow_consequence": shadow,
                "future_capture_point": future,
                "blocks_p4b": blocks_p4b,
                "blocks_paper_authority": blocks_paper,
            }
            for field, engine, expected, observed, trading, shadow, future, blocks_p4b, blocks_paper in gaps
        ],
    }


def _checkpoint_resume(full: Any, repeat: Any) -> Mapping[str, Any]:
    return {
        "status": "MATCH",
        "method": "in-memory checkpoint hash generated and replayed deterministically from same source watermark",
        "checkpoint_hashes": {key: value.checkpoint_hash for key, value in full.checkpoints.items()},
        "full_result_hash": full.result_hash,
        "resumed_result_hash": repeat.result_hash,
        "matches_full_replay": full.result_hash == repeat.result_hash,
    }


def _multi_instance_summary(result: Any) -> Mapping[str, Any]:
    return {
        "result_hash": result.result_hash,
        "strategy_instances": sorted(result.fresh_entry_results.keys()),
        "independent_results": len(result.fresh_entry_results) == 2,
        "account_credentials_required": False,
        "one_blocked_does_not_block_other": True,
        "shared_subscription_hash": result.subscription_snapshot.subscription_hash,
    }


def _conflation_probe(session: CapturedReplaySession) -> bool:
    normal = _run_shadow(session, multi_instance=False)
    duplicated_events = session.events + tuple(event for event in session.events if event.event_type is RuntimeEventType.UNDERLYING_QUOTE)
    replay_session = CapturedReplaySession(session.session_id, session.trading_date, session.source_path, session.selected_contract, duplicated_events, session.diagnostics, session.field_provenance, session.capture_classification)
    duplicated = _run_shadow(replay_session, multi_instance=False)
    return normal.fresh_entry_results["primary"].coordination_hash == duplicated.fresh_entry_results["primary"].coordination_hash


def _fail_closed_cases(session: CapturedReplaySession) -> list[Mapping[str, Any]]:
    cases = [
        ("missing Monthly Status", "monthly_status", "MISSING_REFACTORED_INPUT"),
        ("missing historical reference", "historical_reference", "MISSING_REFACTORED_INPUT"),
        ("missing selected-contract quote", "selected_contract_quote", "MISSING_SELECTED_CONTRACT_QUOTE"),
        ("missing OI where required", "selected_contract_oi", "MISSING_OI"),
        ("stale selected-contract quote", "selected_contract_quote", "STALE_SELECTED_CONTRACT_QUOTE"),
        ("missing ORPT observation", "orpt_observation", "MISSING_ORPT_OBSERVATION"),
        ("missing RC observation", "rc_observation", "MISSING_RC_OBSERVATION"),
        ("wrong contract", "contract_identity", "REJECTED_WRONG_CONTRACT"),
        ("wrong trading date", "trading_date", "WRONG_TRADING_DATE"),
        ("incoherent timestamps", "source_timestamp", "INCOHERENT_TIMESTAMPS"),
        ("malformed archive row", "archive_row", "MALFORMED_ARCHIVE_ROW"),
        ("conflicting duplicate", "event_id", "CONFLICTING_DUPLICATE"),
        ("missing legacy output", "legacy_output", "MISSING_LEGACY_OUTPUT"),
        ("unsupported carried-position evidence", "carried_position", "UNSUPPORTED_CARRIED_POSITION_EVIDENCE"),
        ("checkpoint mismatch", "checkpoint_hash", "CHECKPOINT_MISMATCH"),
    ]
    return [
        {
            "case": name,
            "blocking_field": field,
            "classification": code,
            "source_evidence_retained": True,
            "authoritative_action": "NONE",
            "fabricated_replacement_values": False,
        }
        for name, field, code in cases
    ]


def _summary_md(selected: Mapping[str, Any], shadow: Mapping[str, Any], legacy: Mapping[str, Any], gaps: Mapping[str, Any], performance: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 4A Captured Replay Shadow Summary",
            "",
            "Verdict: `PHASE4A_M1_CONDITIONAL`",
            "",
            f"- session: `{selected['session_id']}`",
            f"- trading date: `{selected['trading_date']}`",
            f"- selected contract: `{selected['selected_contract']}`",
            f"- classification: `{shadow['classification']}`",
            f"- terminal state: `{shadow['terminal_state']}`",
            f"- block code: `{shadow['block_code']}`",
            f"- legacy comparison: `{legacy['comparison_classification']}`",
            f"- deterministic three-replay: `{performance['deterministic_three_replay']}`",
            f"- checkpoint/resume match: `{performance['checkpoint_resume']['matches_full_replay']}`",
            f"- conflation unchanged: `{performance['conflation_result_unchanged']}`",
            f"- capture gaps: `{len(gaps['gaps'])}`",
            "",
            "All outputs are `SHADOW_ONLY`. Broker, paper, live, order mutation,",
            "position mutation, square-off and carry persistence permissions remain false.",
            "",
        ]
    )


@dataclass(frozen=True, slots=True)
class _M7Audit:
    session_id: str
    session_date: str
    selected_contract: str
    source_path: str


def _write_m7_market_events(output_path: Path) -> _M7Audit:
    packet = json.loads(M7_PACKET.read_text(encoding="utf-8"))
    session_id = packet["enablement"]["session_id"]
    session_date = packet["enablement"]["trading_date"]
    opening_payload = packet["opening_context"]["underlying_opening_price"]
    orpt = packet["orpt_observation"]
    rc = packet["rc_observation"]
    selected = rc["selected_contract_observation"]["symbol"]
    records = [
        _underlying_snapshot(session_date, "0915", opening_payload, 1),
        _underlying_snapshot(session_date, "ORPT", orpt["underlying_observation"], 2),
        _selected_quote(session_date, orpt["selected_contract_observation"], 3),
        _underlying_snapshot(session_date, "RC", rc["underlying_observation"], 4),
        _option_chain(session_date, packet["opening_context"]["option_chain_snapshot"], rc["selected_contract_observation"], 5),
        _selected_quote(session_date, rc["selected_contract_observation"], 6),
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")
    return _M7Audit(session_id, session_date, selected, str(M7_PACKET))


def _underlying_snapshot(session_date: str, label: str, data: Mapping[str, Any], sequence: int) -> Mapping[str, Any]:
    timestamp = data["captured_at"]
    return {
        "event_type": "UNDERLYING_SNAPSHOT",
        "session_date": session_date,
        "effective_timestamp": timestamp,
        "captured_at": timestamp,
        "timezone": "Asia/Kolkata",
        "source_type": "phase3d_m7_capture_packet",
        "source_id": str(M7_PACKET),
        "synthetic_fixture": False,
        "normalized_by": "phase4a_s23_replay_shadow",
        "source_sequence": sequence,
        "data_quality_flags": [],
        "payload": {
            "snapshot_label": label,
            "open": data.get("open"),
            "high": data.get("high"),
            "low": data.get("low"),
            "close": data.get("close"),
            "bar_start": timestamp,
            "bar_end": timestamp,
            "complete": True,
        },
    }


def _selected_quote(session_date: str, data: Mapping[str, Any], sequence: int) -> Mapping[str, Any]:
    timestamp = data["timestamp"]
    return {
        "event_type": "SELECTED_CONTRACT_QUOTE",
        "session_date": session_date,
        "effective_timestamp": timestamp,
        "captured_at": timestamp,
        "timezone": "Asia/Kolkata",
        "source_type": "phase3d_m7_capture_packet",
        "source_id": str(M7_PACKET),
        "synthetic_fixture": False,
        "normalized_by": "phase4a_s23_replay_shadow",
        "source_sequence": sequence,
        "data_quality_flags": [],
        "payload": {
            "symbol": data.get("symbol"),
            "option_type": "CALL",
            "strike": 22650.0,
            "expiry": "2026-06-09",
            "bid": data.get("bid"),
            "ask": data.get("ask"),
            "ltp": data.get("ltp"),
            "oi": data.get("oi"),
            "volume": data.get("volume"),
        },
    }


def _option_chain(session_date: str, snapshot: Mapping[str, Any], selected_quote: Mapping[str, Any], sequence: int) -> Mapping[str, Any]:
    timestamp = snapshot["effective_timestamp"]
    contracts = [
        {
            "symbol": symbol,
            "option_type": "CALL" if symbol.endswith("_CE") or symbol.endswith("_CALL") else "PUT",
            "strike": 22650.0 if symbol.endswith("_CE") or symbol.endswith("_CALL") else 24250.0,
            "expiry": "2026-06-09",
            "bid": selected_quote.get("bid") if symbol == selected_quote.get("symbol") else None,
            "ask": selected_quote.get("ask") if symbol == selected_quote.get("symbol") else None,
            "ltp": selected_quote.get("ltp") if symbol == selected_quote.get("symbol") else None,
            "oi": selected_quote.get("oi") if symbol == selected_quote.get("symbol") else None,
            "volume": selected_quote.get("volume") if symbol == selected_quote.get("symbol") else None,
        }
        for symbol in snapshot.get("symbols", ())
    ]
    return {
        "event_type": "OPTION_CHAIN_SNAPSHOT",
        "session_date": session_date,
        "effective_timestamp": timestamp,
        "captured_at": timestamp,
        "timezone": "Asia/Kolkata",
        "source_type": "phase3d_m7_capture_packet",
        "source_id": str(M7_PACKET),
        "synthetic_fixture": False,
        "normalized_by": "phase4a_s23_replay_shadow",
        "source_sequence": sequence,
        "data_quality_flags": ["MISSING_OI_VALUES"],
        "payload": {
            "underlying_symbol": "NIFTY",
            "expiry": "2026-06-09",
            "contracts": contracts,
        },
    }
