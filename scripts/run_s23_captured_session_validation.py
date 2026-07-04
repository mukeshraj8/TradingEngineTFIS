from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.domain.enums import OptionType
from tfis.paper.contract_selection import S23PaperContractSelectionRequest, S23PaperContractSelector
from tfis.paper.models import EventEnvelope, OptionChainContract, OptionChainSnapshotEvent, PaperEventType


DEFAULT_ARTIFACT_ROOT = Path("data/strategies/S23/fyers_morning_supervised_decision")
DEFAULT_OUT_JSON = Path("tmp/s23_captured_session_validation.json")
DEFAULT_OUT_MD = Path("tmp/s23_captured_session_validation.md")
EXPECTED_SNAPSHOT_STAGES = ("0916", "0925", "0930")


@dataclass(frozen=True)
class CapturedBranchSummary:
    branch: str
    status: str
    selected_contract_symbol: str | None
    selected_contract_expiry: str | None
    selected_contract_option_type: str | None
    selected_contract_strike: float | None
    selected_contract_ltp: float | None
    selected_contract_oi: float | None
    planned_entry_price: float | None
    target_price: float | None
    stoploss_price: float | None
    monthly_status: str | None
    selection_reason: str | None
    failure_code: str | None
    calculation_source: str
    order_placement_blocked: bool
    order_placement_blocked_reason: str | None
    selected_contract_market_event_count: int
    latest_selected_contract_market_event_at: str | None
    replay_order_verdict: str | None
    replay_order_reason: str | None
    replay_fill_price: float | None
    replay_fill_timestamp: str | None
    replay_position_verdict: str | None
    replay_position_reason: str | None
    replay_position_exit_price: float | None
    replay_position_exit_timestamp: str | None
    order_status: str | None
    order_fill_price: float | None
    position_status: str | None
    position_last_updated: str | None
    attempted_expiries: tuple[str, ...]
    evidence_files: tuple[str, ...]
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class CapturedSessionSummary:
    session_date: str
    session_directory: str
    stage_coverage: tuple[str, ...]
    branch_count: int
    selected_branch_count: int
    order_count: int
    position_count: int
    replay_readiness: str
    branches: tuple[CapturedBranchSummary, ...]
    gaps: tuple[str, ...]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate captured S23 supervised-session artifacts without live broker access."
    )
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    parser.add_argument("--date", action="append", dest="dates")
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    args = parser.parse_args(argv)

    root = Path(args.artifact_root)
    sessions = validate_captured_sessions(root, dates=tuple(args.dates or ()))
    report = {
        "artifact_root": str(root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "session_count": len(sessions),
        "sessions": [_session_to_dict(session) for session in sessions],
    }

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    out_md.write_text(render_markdown_report(report), encoding="utf-8")

    print(f"Captured S23 validation sessions: {len(sessions)}")
    print(f"JSON report: {out_json}")
    print(f"Markdown report: {out_md}")
    for session in sessions:
        print(
            f"{session.session_date}: {session.replay_readiness} "
            f"branches={session.branch_count} selected={session.selected_branch_count} "
            f"orders={session.order_count} positions={session.position_count}"
        )
    return 0


def validate_captured_sessions(root: Path, *, dates: tuple[str, ...] = ()) -> tuple[CapturedSessionSummary, ...]:
    if not root.exists():
        return ()
    wanted_dates = set(dates)
    sessions: list[CapturedSessionSummary] = []
    for day_dir in sorted(item for item in root.iterdir() if item.is_dir()):
        if wanted_dates and day_dir.name not in wanted_dates:
            continue
        session_dir = day_dir / f"s23-fyers-morning-supervised-decision-{day_dir.name}"
        if not session_dir.exists():
            continue
        sessions.append(_summarize_session(day_dir=day_dir, session_dir=session_dir))
    return tuple(sessions)


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# S23 Captured Session Validation",
        "",
        f"- artifact root: `{report['artifact_root']}`",
        f"- generated at: `{report['generated_at']}`",
        f"- sessions: `{report['session_count']}`",
        "",
    ]
    for session in report["sessions"]:
        lines.extend(
            [
                f"## {session['session_date']} - {session['replay_readiness']}",
                "",
                f"- stage coverage: `{', '.join(session['stage_coverage']) or 'none'}`",
                f"- branches: `{session['branch_count']}`",
                f"- selected branches: `{session['selected_branch_count']}`",
                f"- paper orders: `{session['order_count']}`",
                f"- paper positions: `{session['position_count']}`",
            ]
        )
        if session["gaps"]:
            lines.append(f"- gaps: `{'; '.join(session['gaps'])}`")
        lines.extend(
            [
                "",
                "| Branch | Status | Contract | Expiry | LTP | OI | Entry | Target | SL | Market Events | Latest Market Event | Order Replay | Position Replay | Order | Position | Reason |",
                "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---|",
            ]
        )
        for branch in session["branches"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        branch["branch"],
                        branch["status"],
                        branch["selected_contract_symbol"] or "n/a",
                        branch["selected_contract_expiry"] or "n/a",
                        _fmt(branch["selected_contract_ltp"]),
                        _fmt(branch["selected_contract_oi"]),
                        _fmt(branch["planned_entry_price"]),
                        _fmt(branch["target_price"]),
                        _fmt(branch["stoploss_price"]),
                        str(branch["selected_contract_market_event_count"]),
                        branch["latest_selected_contract_market_event_at"] or "n/a",
                        branch["replay_order_verdict"] or "n/a",
                        branch["replay_position_verdict"] or "n/a",
                        branch["order_status"]
                        or ("BLOCKED" if branch["order_placement_blocked"] else "n/a"),
                        branch["position_status"] or "n/a",
                        _escape_table(_branch_reason(branch)),
                    ]
                )
                + " |"
            )
        lines.append("")
        for branch in session["branches"]:
            if branch["gaps"]:
                lines.append(f"- `{branch['branch']}` gaps: `{'; '.join(branch['gaps'])}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _summarize_session(*, day_dir: Path, session_dir: Path) -> CapturedSessionSummary:
    stages = tuple(
        stage
        for stage in EXPECTED_SNAPSHOT_STAGES
        if (day_dir / f"s23-fyers-morning-supervised-decision-{stage}-{day_dir.name}").exists()
    )
    option_chain = _load_latest_stage_option_chain(day_dir)
    branches = tuple(
        _summarize_branch(branch_dir, option_chain=option_chain)
        for branch_dir in sorted(item for item in session_dir.iterdir() if item.is_dir())
        if (branch_dir / "trade_decision_summary.json").exists()
    )
    selected_count = sum(1 for branch in branches if branch.selected_contract_symbol)
    order_count = sum(1 for branch in branches if branch.order_status)
    position_count = sum(1 for branch in branches if branch.position_status)
    gaps: list[str] = []
    for stage in EXPECTED_SNAPSHOT_STAGES:
        if stage not in stages:
            gaps.append(f"missing_snapshot_stage_{stage}")
    if not branches:
        gaps.append("missing_trade_decision_summaries")
    if selected_count and not order_count:
        if any(branch.order_placement_blocked for branch in branches if branch.selected_contract_symbol):
            gaps.append("selected_contracts_reconstructed_but_order_placement_blocked")
        else:
            gaps.append("selected_contracts_have_no_paper_order_state")

    readiness = "DECISION_RECONSTRUCTABLE"
    if gaps:
        readiness = "PARTIAL_CAPTURE"
    if selected_count and not order_count and any(branch.order_placement_blocked for branch in branches):
        readiness = "CALCULATION_RECONSTRUCTED_ORDER_BLOCKED"
    if position_count:
        readiness = "PARTIAL_LIFECYCLE_EVIDENCE"
    if selected_count and order_count == selected_count and not gaps:
        readiness = "ORDER_REVIEWABLE"

    if selected_count and not any("selected_contract_market_events" in file for branch in branches for file in branch.evidence_files):
        gaps.append("selected_contract_intraday_price_stream_not_persisted")
        if readiness == "ORDER_REVIEWABLE":
            readiness = "ORDER_REVIEWABLE_PRICE_STREAM_MISSING"

    return CapturedSessionSummary(
        session_date=day_dir.name,
        session_directory=str(session_dir),
        stage_coverage=stages,
        branch_count=len(branches),
        selected_branch_count=selected_count,
        order_count=order_count,
        position_count=position_count,
        replay_readiness=readiness,
        branches=branches,
        gaps=tuple(gaps),
    )


def _summarize_branch(
    branch_dir: Path,
    *,
    option_chain: OptionChainSnapshotEvent | None,
) -> CapturedBranchSummary:
    summary_payload = _read_json(branch_dir / "trade_decision_summary.json")
    summary = summary_payload.get("summary", {})
    explanation = summary_payload.get("explanation", {})
    order_state = _read_json(branch_dir / "paper_order_state.json")
    position_state = _read_json(branch_dir / "paper_position_state.json")
    evidence_files = tuple(sorted(path.name for path in branch_dir.iterdir() if path.is_file()))
    selected_market_events = _load_selected_contract_market_events(branch_dir)
    market_event_count, latest_market_event_at = _selected_contract_market_event_stats(selected_market_events)
    gaps: list[str] = []
    selected_symbol = _as_optional_str(summary.get("selected_contract_symbol"))
    selected_expiry = _as_optional_str(summary.get("selected_contract_expiry"))
    selected_option_type = _as_optional_str(summary.get("selected_contract_option_type"))
    selected_strike = _as_optional_float(summary.get("selected_contract_strike"))
    selected_ltp = _as_optional_float(summary.get("selected_contract_ltp"))
    selected_oi = _as_optional_float(summary.get("selected_contract_oi"))
    planned_entry = _as_optional_float(summary.get("planned_entry_price"))
    target = _as_optional_float(summary.get("target_price"))
    stoploss = _as_optional_float(summary.get("stoploss_price"))
    selection_reason = _as_optional_str(summary.get("contract_selection_reason"))
    failure_code = _as_optional_str(summary.get("contract_selection_failure_code"))
    attempted_expiries = tuple(str(item) for item in summary.get("contract_selection_attempted_expiries") or ())
    calculation_source = "persisted_decision_summary"
    order_placement_blocked = bool(summary.get("order_placement_blocked"))
    order_placement_blocked_reason = _as_optional_str(summary.get("order_placement_blocked_reason"))

    if not selected_symbol:
        reconstructed = _reconstruct_branch_selection(
            branch_name=branch_dir.name,
            summary=summary,
            explanation=explanation,
            option_chain=option_chain,
        )
        if reconstructed is not None:
            selected_symbol = reconstructed["selected_contract_symbol"]
            selected_expiry = reconstructed["selected_contract_expiry"]
            selected_option_type = reconstructed["selected_contract_option_type"]
            selected_strike = reconstructed["selected_contract_strike"]
            selected_ltp = reconstructed["selected_contract_ltp"]
            selected_oi = reconstructed["selected_contract_oi"]
            planned_entry = reconstructed["planned_entry_price"]
            target = reconstructed["target_price"]
            stoploss = reconstructed["stoploss_price"]
            selection_reason = reconstructed["selection_reason"]
            failure_code = reconstructed["failure_code"]
            attempted_expiries = tuple(reconstructed["attempted_expiries"])
            calculation_source = reconstructed["calculation_source"]
            order_placement_blocked = True
            order_placement_blocked_reason = (
                order_placement_blocked_reason
                or _first_note(summary)
                or "Fresh order placement was blocked in the captured run; reconstructed for review only."
            )

    if selected_symbol and not order_state:
        if order_placement_blocked:
            gaps.append("order_placement_blocked_no_paper_order_expected")
        else:
            gaps.append("missing_paper_order_state")
    if order_state and not (branch_dir / "paper_order_events.jsonl").exists():
        gaps.append("missing_paper_order_events")
    if position_state and not (branch_dir / "paper_position_state_events.jsonl").exists():
        gaps.append("missing_paper_position_state_events")
    if selected_symbol and market_event_count <= 0:
        gaps.append("missing_selected_contract_price_stream")

    replay = _replay_waiting_order_from_market_events(
        order_state=order_state,
        selected_contract_symbol=selected_symbol,
        planned_entry_price=planned_entry,
        events=selected_market_events,
    )
    if replay.get("gap"):
        gaps.append(str(replay["gap"]))
    position_replay = _replay_position_from_market_events(
        position_state=position_state,
        selected_contract_symbol=selected_symbol,
        events=selected_market_events,
    )
    if position_replay.get("gap"):
        gaps.append(str(position_replay["gap"]))

    return CapturedBranchSummary(
        branch=branch_dir.name,
        status=str(summary.get("status") or "UNKNOWN"),
        selected_contract_symbol=selected_symbol,
        selected_contract_expiry=selected_expiry,
        selected_contract_option_type=selected_option_type,
        selected_contract_strike=selected_strike,
        selected_contract_ltp=selected_ltp,
        selected_contract_oi=selected_oi,
        planned_entry_price=planned_entry,
        target_price=target,
        stoploss_price=stoploss,
        monthly_status=_as_optional_str(summary.get("monthly_status")),
        selection_reason=selection_reason,
        failure_code=failure_code,
        calculation_source=calculation_source,
        order_placement_blocked=order_placement_blocked,
        order_placement_blocked_reason=order_placement_blocked_reason,
        selected_contract_market_event_count=market_event_count,
        latest_selected_contract_market_event_at=latest_market_event_at,
        replay_order_verdict=_as_optional_str(replay.get("verdict")),
        replay_order_reason=_as_optional_str(replay.get("reason")),
        replay_fill_price=_as_optional_float(replay.get("fill_price")),
        replay_fill_timestamp=_as_optional_str(replay.get("fill_timestamp")),
        replay_position_verdict=_as_optional_str(position_replay.get("verdict")),
        replay_position_reason=_as_optional_str(position_replay.get("reason")),
        replay_position_exit_price=_as_optional_float(position_replay.get("exit_price")),
        replay_position_exit_timestamp=_as_optional_str(position_replay.get("exit_timestamp")),
        order_status=_as_optional_str(order_state.get("status")),
        order_fill_price=_as_optional_float(order_state.get("fill_price")),
        position_status=_as_optional_str(position_state.get("lifecycle_status")),
        position_last_updated=_as_optional_str(position_state.get("last_updated_timestamp")),
        attempted_expiries=attempted_expiries,
        evidence_files=evidence_files,
        gaps=tuple(gaps),
    )


def _reconstruct_branch_selection(
    *,
    branch_name: str,
    summary: dict[str, Any],
    explanation: dict[str, Any],
    option_chain: OptionChainSnapshotEvent | None,
) -> dict[str, Any] | None:
    if option_chain is None:
        return None
    option_type = _option_type_from_branch(branch_name)
    if option_type is None:
        return None
    formula_values = _formula_results(explanation)
    required = ("start_strike", "end_strike", "ideal_premium", "minimum_premium")
    if any(formula_values.get(name) is None for name in required):
        return None
    expiries = tuple(
        sorted(
            {
                contract.expiry
                for contract in option_chain.contracts
                if contract.expiry is not None and contract.option_type is option_type
            }
        )
    )
    if not expiries:
        return None
    minimum_oi = _as_optional_float(
        ((explanation.get("contract_selection_thresholds") or {}).get("minimum_oi"))
    )
    request = S23PaperContractSelectionRequest(
        underlying_symbol=option_chain.underlying_symbol,
        expiry_date=expiries[0],
        fallback_expiry_dates=expiries[1:],
        option_type=option_type,
        start_strike=float(formula_values["start_strike"]),
        end_strike=float(formula_values["end_strike"]),
        ideal_premium=float(formula_values["ideal_premium"]),
        minimum_premium=float(formula_values["minimum_premium"]),
        minimum_oi=float(minimum_oi or 0.0),
    )
    result = S23PaperContractSelector().select(request, option_chain)
    if result.selected:
        return {
            "selected_contract_symbol": result.selected_contract_symbol,
            "selected_contract_expiry": result.expiry_date.isoformat() if result.expiry_date else None,
            "selected_contract_option_type": result.option_type.value if result.option_type else None,
            "selected_contract_strike": result.strike,
            "selected_contract_ltp": result.premium_used,
            "selected_contract_oi": result.oi_used,
            "planned_entry_price": formula_values.get("entry"),
            "target_price": formula_values.get("target"),
            "stoploss_price": formula_values.get("stoploss"),
            "selection_reason": f"Review-only reconstruction from captured 09:30 snapshot: {result.selection_reason}",
            "failure_code": None,
            "attempted_expiries": [item.isoformat() for item in result.attempted_expiries],
            "calculation_source": "review_reconstructed_from_captured_snapshot",
        }
    selection_reason = _dedupe_sentence_parts(result.selection_reason)
    return {
        "selected_contract_symbol": None,
        "selected_contract_expiry": None,
        "selected_contract_option_type": option_type.value,
        "selected_contract_strike": None,
        "selected_contract_ltp": None,
        "selected_contract_oi": None,
        "planned_entry_price": formula_values.get("entry"),
        "target_price": formula_values.get("target"),
        "stoploss_price": formula_values.get("stoploss"),
        "selection_reason": f"Review-only reconstruction from captured 09:30 snapshot: {selection_reason}",
        "failure_code": result.failure_code.value if result.failure_code else None,
        "attempted_expiries": [item.isoformat() for item in result.attempted_expiries],
        "calculation_source": "review_reconstructed_from_captured_snapshot",
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_selected_contract_market_events(branch_dir: Path) -> tuple[dict[str, Any], ...]:
    paths = sorted(branch_dir.glob("selected_contract_market_events*.jsonl"))
    events: list[dict[str, Any]] = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
    return tuple(events)


def _selected_contract_market_event_stats(events: tuple[dict[str, Any], ...]) -> tuple[int, str | None]:
    latest: str | None = None
    for payload in events:
        observed_at = _event_timestamp(payload)
        if observed_at and (latest is None or observed_at > latest):
            latest = observed_at
    return len(events), latest


def _replay_waiting_order_from_market_events(
    *,
    order_state: dict[str, Any],
    selected_contract_symbol: str | None,
    planned_entry_price: float | None,
    events: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    if not order_state:
        return {}
    order_status = _as_optional_str(order_state.get("status"))
    if order_status not in {"PAPER_ORDER_WAITING_FOR_TRIGGER", "PAPER_ORDER_FILLED", "PAPER_ORDER_NOT_FILLED"}:
        return {}
    symbol = _as_optional_str(order_state.get("selected_contract_symbol")) or selected_contract_symbol
    entry = _as_optional_float(order_state.get("planned_entry_price")) or planned_entry_price
    if not symbol or entry is None:
        return {
            "verdict": "REPLAY_INCOMPLETE",
            "reason": "Cannot replay order trigger because selected contract or entry price is missing.",
            "gap": "order_replay_missing_symbol_or_entry",
        }
    matching_events = tuple(event for event in events if _event_symbol(event) == symbol)
    if not matching_events:
        return {
            "verdict": "REPLAY_INCOMPLETE",
            "reason": "No selected-contract market events match the paper order symbol.",
            "gap": "order_replay_missing_matching_selected_contract_events",
        }

    trigger = _first_order_trigger(symbol=symbol, entry=entry, events=matching_events)
    if trigger is not None:
        expected_status = "PAPER_ORDER_FILLED"
        if order_status == expected_status:
            return {
                "verdict": "REPLAY_CONFIRMED_FILLED",
                "reason": (
                    f"Selected-contract stream reached entry at {trigger['timestamp']}: "
                    f"{trigger['basis']} {trigger['market_price']:.2f} <= entry {entry:.2f}."
                ),
                "fill_price": trigger["fill_price"],
                "fill_timestamp": trigger["timestamp"],
            }
        return {
            "verdict": "REPLAY_MISMATCH_SHOULD_HAVE_FILLED",
            "reason": (
                f"Selected-contract stream reached entry at {trigger['timestamp']}: "
                f"{trigger['basis']} {trigger['market_price']:.2f} <= entry {entry:.2f}, "
                f"but persisted order status is {order_status}."
            ),
            "fill_price": trigger["fill_price"],
            "fill_timestamp": trigger["timestamp"],
            "gap": "order_replay_mismatch_should_have_filled",
        }

    latest = _selected_contract_market_event_stats(matching_events)[1]
    if order_status == "PAPER_ORDER_FILLED":
        return {
            "verdict": "REPLAY_MISMATCH_FILLED_WITHOUT_TRIGGER",
            "reason": (
                f"Selected-contract stream never reached entry {entry:.2f}, "
                "but persisted order status is PAPER_ORDER_FILLED."
            ),
            "gap": "order_replay_mismatch_filled_without_trigger",
        }
    if order_status == "PAPER_ORDER_NOT_FILLED":
        return {
            "verdict": "REPLAY_CONFIRMED_NOT_FILLED",
            "reason": (
                f"Selected-contract stream did not reach entry {entry:.2f} through {latest or 'the latest event'}; "
                "persisted status is PAPER_ORDER_NOT_FILLED."
            ),
        }
    return {
        "verdict": "REPLAY_CONFIRMED_WAITING",
        "reason": (
            f"Selected-contract stream did not reach entry {entry:.2f} through {latest or 'the latest event'}; "
            "persisted status remains PAPER_ORDER_WAITING_FOR_TRIGGER."
        ),
    }


def _first_order_trigger(
    *,
    symbol: str,
    entry: float,
    events: tuple[dict[str, Any], ...],
) -> dict[str, Any] | None:
    for event in sorted(events, key=lambda item: (_event_timestamp(item) or "", item.get("observed_at") or "")):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_kind = _as_optional_str(event.get("event_kind")) or ""
        if _event_symbol(event) != symbol:
            continue
        if "bar" in event_kind:
            low = _as_optional_float(payload.get("low"))
            if low is not None and low <= entry:
                return {
                    "timestamp": _event_timestamp(event) or "n/a",
                    "basis": "bar low",
                    "market_price": low,
                    "fill_price": entry,
                }
            continue
        market_price = _as_optional_float(payload.get("ltp"))
        if market_price is None:
            market_price = _as_optional_float(payload.get("bid"))
        if market_price is not None and market_price <= entry:
            bid = _as_optional_float(payload.get("bid"))
            return {
                "timestamp": _event_timestamp(event) or "n/a",
                "basis": "quote price",
                "market_price": market_price,
                "fill_price": bid if bid is not None else market_price,
            }
    return None


def _replay_position_from_market_events(
    *,
    position_state: dict[str, Any],
    selected_contract_symbol: str | None,
    events: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    if not position_state:
        return {}
    lifecycle_status = _as_optional_str(position_state.get("lifecycle_status"))
    if not lifecycle_status:
        return {}
    symbol = _as_optional_str(position_state.get("selected_contract_symbol")) or selected_contract_symbol
    target = _as_optional_float(position_state.get("target_price"))
    stoploss = _as_optional_float(position_state.get("stoploss_price"))
    fsl = _as_optional_float(position_state.get("fsl_price"))
    stop_active = bool(position_state.get("stoploss_active", True))
    if not symbol or target is None or stoploss is None:
        return {
            "verdict": "POSITION_REPLAY_INCOMPLETE",
            "reason": "Cannot replay position lifecycle because selected contract, target, or stoploss is missing.",
            "gap": "position_replay_missing_symbol_or_levels",
        }
    matching_events = tuple(event for event in events if _event_symbol(event) == symbol)
    if not matching_events:
        return {
            "verdict": "POSITION_REPLAY_INCOMPLETE",
            "reason": "No selected-contract market events match the paper position symbol.",
            "gap": "position_replay_missing_matching_selected_contract_events",
        }

    exit_event = _first_position_exit_event(
        symbol=symbol,
        target=target,
        stop_price=min([item for item in (stoploss, fsl) if item is not None]),
        stop_active=stop_active,
        events=matching_events,
    )
    if exit_event is not None:
        expected_status = {
            "target_hit": "PAPER_FRESH_ENTRY_REQUIRED",
            "stoploss_or_fsl_hit": "PAPER_REVERSE_ENTRY_REQUIRED",
            "same_bar_target_stop_conflict_stoploss_wins": "PAPER_REVERSE_ENTRY_REQUIRED",
        }[exit_event["reason_code"]]
        if lifecycle_status == expected_status:
            return {
                "verdict": "POSITION_REPLAY_CONFIRMED_EXIT",
                "reason": (
                    f"Selected-contract stream confirms {exit_event['reason_code']} at "
                    f"{exit_event['timestamp']}: {exit_event['basis']} {exit_event['market_price']:.2f}."
                ),
                "exit_price": exit_event["exit_price"],
                "exit_timestamp": exit_event["timestamp"],
            }
        return {
            "verdict": "POSITION_REPLAY_MISMATCH_SHOULD_HAVE_EXITED",
            "reason": (
                f"Selected-contract stream indicates {exit_event['reason_code']} at "
                f"{exit_event['timestamp']}, but persisted lifecycle status is {lifecycle_status}."
            ),
            "exit_price": exit_event["exit_price"],
            "exit_timestamp": exit_event["timestamp"],
            "gap": "position_replay_mismatch_should_have_exited",
        }

    latest = _selected_contract_market_event_stats(matching_events)[1]
    if lifecycle_status in {"PAPER_POSITION_OPEN", "PAPER_POSITION_CARRIED_FORWARD", "PAPER_POSITION_RESUMED"}:
        return {
            "verdict": "POSITION_REPLAY_CONFIRMED_OPEN",
            "reason": (
                f"Selected-contract stream did not hit target {target:.2f} or active stop "
                f"{stoploss:.2f} through {latest or 'the latest event'}; persisted position remains open/carry-forward."
            ),
        }
    return {
        "verdict": "POSITION_REPLAY_MISMATCH_CLOSED_WITHOUT_STREAM_EXIT",
        "reason": (
            f"Selected-contract stream did not hit target {target:.2f} or active stop {stoploss:.2f}, "
            f"but persisted lifecycle status is {lifecycle_status}."
        ),
        "gap": "position_replay_mismatch_closed_without_stream_exit",
    }


def _first_position_exit_event(
    *,
    symbol: str,
    target: float,
    stop_price: float,
    stop_active: bool,
    events: tuple[dict[str, Any], ...],
) -> dict[str, Any] | None:
    for event in sorted(events, key=lambda item: (_event_timestamp(item) or "", item.get("observed_at") or "")):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_kind = _as_optional_str(event.get("event_kind")) or ""
        if _event_symbol(event) != symbol:
            continue
        timestamp = _event_timestamp(event) or "n/a"
        if "bar" in event_kind:
            high = _as_optional_float(payload.get("high"))
            low = _as_optional_float(payload.get("low"))
            if high is None or low is None:
                continue
            stop_hit = stop_active and high >= stop_price
            target_hit = low <= target
            if stop_hit:
                return {
                    "reason_code": "same_bar_target_stop_conflict_stoploss_wins" if target_hit else "stoploss_or_fsl_hit",
                    "timestamp": timestamp,
                    "basis": "bar high",
                    "market_price": high,
                    "exit_price": stop_price,
                }
            if target_hit:
                return {
                    "reason_code": "target_hit",
                    "timestamp": timestamp,
                    "basis": "bar low",
                    "market_price": low,
                    "exit_price": target,
                }
            continue
        stop_reference = _as_optional_float(payload.get("ask"))
        if stop_reference is None:
            stop_reference = _as_optional_float(payload.get("ltp"))
        target_reference = _as_optional_float(payload.get("bid"))
        if target_reference is None:
            target_reference = _as_optional_float(payload.get("ltp"))
        if stop_active and stop_reference is not None and stop_reference >= stop_price:
            return {
                "reason_code": "stoploss_or_fsl_hit",
                "timestamp": timestamp,
                "basis": "quote ask/ltp",
                "market_price": stop_reference,
                "exit_price": max(stop_price, stop_reference),
            }
        if target_reference is not None and target_reference <= target:
            return {
                "reason_code": "target_hit",
                "timestamp": timestamp,
                "basis": "quote bid/ltp",
                "market_price": target_reference,
                "exit_price": max(target, target_reference),
            }
    return None


def _event_symbol(event: dict[str, Any]) -> str | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return _as_optional_str(event.get("symbol")) or _as_optional_str(payload.get("symbol"))


def _event_timestamp(event: dict[str, Any]) -> str | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    envelope = payload.get("envelope") if isinstance(payload.get("envelope"), dict) else {}
    return (
        _as_optional_str(envelope.get("effective_timestamp"))
        or _as_optional_str(event.get("observed_at"))
        or _as_optional_str(payload.get("bar_end"))
    )


def _load_latest_stage_option_chain(day_dir: Path) -> OptionChainSnapshotEvent | None:
    for stage in reversed(EXPECTED_SNAPSHOT_STAGES):
        path = day_dir / f"s23-fyers-morning-supervised-decision-{stage}-{day_dir.name}" / "normalized_option_chain_snapshot.json"
        snapshot = _load_option_chain(path)
        if snapshot is not None:
            return snapshot
    return None


def _load_option_chain(path: Path) -> OptionChainSnapshotEvent | None:
    payload = _read_json(path)
    chain_payload = payload.get("payload")
    if not isinstance(chain_payload, dict):
        return None
    contracts: list[OptionChainContract] = []
    for item in chain_payload.get("contracts") or ():
        if not isinstance(item, dict):
            continue
        try:
            option_type = OptionType(str(item["option_type"]))
        except (KeyError, ValueError):
            option_type = None
        contracts.append(
            OptionChainContract(
                symbol=str(item.get("symbol") or ""),
                option_type=option_type,
                strike=_as_optional_float(item.get("strike")),
                expiry=_as_optional_date(item.get("expiry")),
                bid=_as_optional_float(item.get("bid")),
                ask=_as_optional_float(item.get("ask")),
                ltp=_as_optional_float(item.get("ltp")),
                oi=_as_optional_float(item.get("oi")),
                volume=_as_optional_float(item.get("volume")),
            )
        )
    session_date = _as_optional_date(payload.get("session_date")) or date.today()
    effective_timestamp = _as_optional_datetime(payload.get("effective_timestamp")) or datetime.combine(session_date, datetime.min.time())
    captured_at = _as_optional_datetime(payload.get("captured_at")) or effective_timestamp
    expiry = _as_optional_date(chain_payload.get("expiry"))
    if expiry is None or not contracts:
        return None
    return OptionChainSnapshotEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
            session_date=session_date,
            effective_timestamp=effective_timestamp,
            captured_at=captured_at,
            timezone=str(payload.get("timezone") or "Asia/Kolkata"),
            source_type=str(payload.get("source_type") or "captured_artifact"),
            source_id=str(payload.get("source_id") or path.name),
            synthetic_fixture=bool(payload.get("synthetic_fixture", False)),
            normalized_by=str(payload.get("normalized_by") or "captured_artifact"),
            source_sequence=payload.get("source_sequence"),
            data_quality_flags=tuple(str(item) for item in payload.get("data_quality_flags") or ()),
        ),
        underlying_symbol=str(chain_payload.get("underlying_symbol") or "NIFTY"),
        expiry=expiry,
        contracts=tuple(contracts),
    )


def _session_to_dict(session: CapturedSessionSummary) -> dict[str, Any]:
    return {
        "session_date": session.session_date,
        "session_directory": session.session_directory,
        "stage_coverage": list(session.stage_coverage),
        "branch_count": session.branch_count,
        "selected_branch_count": session.selected_branch_count,
        "order_count": session.order_count,
        "position_count": session.position_count,
        "replay_readiness": session.replay_readiness,
        "branches": [_branch_to_dict(branch) for branch in session.branches],
        "gaps": list(session.gaps),
    }


def _branch_to_dict(branch: CapturedBranchSummary) -> dict[str, Any]:
    return {
        "branch": branch.branch,
        "status": branch.status,
        "selected_contract_symbol": branch.selected_contract_symbol,
        "selected_contract_expiry": branch.selected_contract_expiry,
        "selected_contract_option_type": branch.selected_contract_option_type,
        "selected_contract_strike": branch.selected_contract_strike,
        "selected_contract_ltp": branch.selected_contract_ltp,
        "selected_contract_oi": branch.selected_contract_oi,
        "planned_entry_price": branch.planned_entry_price,
        "target_price": branch.target_price,
        "stoploss_price": branch.stoploss_price,
        "monthly_status": branch.monthly_status,
        "selection_reason": branch.selection_reason,
        "failure_code": branch.failure_code,
        "calculation_source": branch.calculation_source,
        "order_placement_blocked": branch.order_placement_blocked,
        "order_placement_blocked_reason": branch.order_placement_blocked_reason,
        "selected_contract_market_event_count": branch.selected_contract_market_event_count,
        "latest_selected_contract_market_event_at": branch.latest_selected_contract_market_event_at,
        "replay_order_verdict": branch.replay_order_verdict,
        "replay_order_reason": branch.replay_order_reason,
        "replay_fill_price": branch.replay_fill_price,
        "replay_fill_timestamp": branch.replay_fill_timestamp,
        "replay_position_verdict": branch.replay_position_verdict,
        "replay_position_reason": branch.replay_position_reason,
        "replay_position_exit_price": branch.replay_position_exit_price,
        "replay_position_exit_timestamp": branch.replay_position_exit_timestamp,
        "order_status": branch.order_status,
        "order_fill_price": branch.order_fill_price,
        "position_status": branch.position_status,
        "position_last_updated": branch.position_last_updated,
        "attempted_expiries": list(branch.attempted_expiries),
        "evidence_files": list(branch.evidence_files),
        "gaps": list(branch.gaps),
    }


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _as_optional_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _option_type_from_branch(branch_name: str) -> OptionType | None:
    if branch_name.endswith("_CALL"):
        return OptionType.CALL
    if branch_name.endswith("_PUT"):
        return OptionType.PUT
    return None


def _formula_results(explanation: dict[str, Any]) -> dict[str, float]:
    results: dict[str, float] = {}
    for item in explanation.get("formula_evaluation") or ():
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = _as_optional_float(item.get("result"))
        if name and value is not None:
            results[str(name)] = value
    return results


def _first_note(summary: dict[str, Any]) -> str | None:
    notes = summary.get("notes")
    if isinstance(notes, list) and notes:
        return str(notes[0])
    return None


def _branch_reason(branch: dict[str, Any]) -> str:
    parts = []
    if branch.get("selection_reason") or branch.get("failure_code"):
        parts.append(str(branch.get("selection_reason") or branch.get("failure_code")))
    if branch.get("order_placement_blocked"):
        parts.append("Order blocked: " + str(branch.get("order_placement_blocked_reason") or "blocked in captured run"))
    if branch.get("calculation_source") == "review_reconstructed_from_captured_snapshot":
        parts.append("Calculation source: reconstructed from captured 09:30 option chain")
    if branch.get("replay_order_reason"):
        parts.append("Order replay: " + str(branch.get("replay_order_reason")))
    if branch.get("replay_position_reason"):
        parts.append("Position replay: " + str(branch.get("replay_position_reason")))
    return " ".join(parts)


def _dedupe_sentence_parts(value: str) -> str:
    parts = [part.strip() for part in value.split(";") if part.strip()]
    if not parts:
        return value
    unique: list[str] = []
    for part in parts:
        if part not in unique:
            unique.append(part)
    return "; ".join(unique)


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
