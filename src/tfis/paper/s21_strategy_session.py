from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Any, Callable

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.importers import load_strategy_rule
from tfis.rules import get_s21_leg_rule

from .fyers_snapshot_collector import PaperFyersSnapshotCollector
from .live_decision_schedule import build_schedule_note, compute_schedule_delay_seconds
from .live_decision_timeline import PaperLiveDecisionTimelineBuilder
from .live_ingress import PaperLiveIngressConfig
from .live_decision_runner import prepare_live_decision_runtime_environment
from .order_state import PaperOrderStateStore
from .position_state import PaperPositionStateStore
from .runtime_input_derivation import load_paper_decision_reference_packet
from .s21_live_decision import S21PaperLiveDecisionBuilder


@dataclass(frozen=True, slots=True)
class S21StrategySessionResult:
    """One S21 strategy session containing its eligible call/put legs."""

    session_directory: Path
    timeline_json: Path
    timeline_markdown: Path
    final_summary_json: Path | None
    final_summary_markdown: Path | None
    branch_final_summary_json: dict[str, str] = field(default_factory=dict)
    branch_final_summary_markdown: dict[str, str] = field(default_factory=dict)
    branch_order_state_json: dict[str, str] = field(default_factory=dict)
    branch_position_state_json: dict[str, str] = field(default_factory=dict)
    branch_order_placement_blocked: dict[str, bool] = field(default_factory=dict)
    branch_order_placement_block_reason: dict[str, str] = field(default_factory=dict)


def eligible_s21_unique_codes(
    *,
    status: MonthlyStatus,
    strategy_rules: tuple[Any, ...],
) -> tuple[str, ...]:
    """Return only the two S21 legs belonging to the resolved monthly family."""
    return tuple(
        rule.unique_code
        for rule in strategy_rules
        if status in get_s21_leg_rule(rule.unique_code).allowed_monthly_statuses
    )


def s21_orpt_requires_recalculation(
    *,
    option_type: OptionType,
    base_entry: float,
    option_low: float | None,
    option_high: float | None,
) -> bool:
    """Apply the existing S21/S23 legacy missed-entry test to the *09:16 base plan*.

    Important: this function does not recalculate the plan. It only decides at ORPT
    whether the normal 09:16 plan remains usable or must enter the RC path.
    """
    if option_type in (OptionType.CALL, OptionType.PUT):
        # AB6 OS uses 09:24:59 LL for both Call Sell Entry and Put Sell Entry.
        return float(option_low or 0.0) < float(base_entry)
    raise ValueError(f"Unsupported S21 option type: {option_type}")


def run_s21_strategy_session(
    *,
    tfis_root: str | Path | None,
    config_path: str | Path,
    strategy_paths: tuple[str | Path, ...],
    reference_packet_path: str | Path,
    artifact_root: str | Path,
    session_id_prefix: str,
    carry_forward_state_dir: str | Path | None = None,
    enable_smoke_override: bool = False,
    skip_refresh: bool = False,
    timezone_name: str = "Asia/Kolkata",
    if_past: str = "run_now",
    dashboard_output_root: str | Path | None = None,
    now_provider: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> S21StrategySessionResult:
    """Run S21 as one strategy session rather than four independent pseudo-strategies.

    Authoritative timing model:
      09:16 - prepare one S21 base plan and determine the eligible monthly family.
      09:25 - ORPT gate. Normal-valid base plans create paper orders here.
               Plans requiring the gap/missed-entry RC path are deferred.
      09:30 - RC gate. Only deferred legs are recalculated/evaluated and may create orders.

    The 09:16 selected contract/entry is retained for the normal path. It is not
    re-selected at 09:25 merely because a new option-chain snapshot exists.
    """
    from zoneinfo import ZoneInfo
    import time as time_module

    if not strategy_paths:
        raise RuntimeError("S21 requires the four configured leg strategy paths.")

    rules = tuple(load_strategy_rule(path) for path in strategy_paths)
    if any(rule.strategy_code.upper() != "S21" for rule in rules):
        raise RuntimeError("run_s21_strategy_session accepts S21 strategy rules only.")

    timezone = ZoneInfo(timezone_name)
    now_fn = now_provider or (lambda: datetime.now(timezone))
    sleep_fn = sleeper or time_module.sleep

    prepare_live_decision_runtime_environment(
        tfis_root=tfis_root,
        config_path=config_path,
        skip_refresh=skip_refresh,
    )

    ingress_config = PaperLiveIngressConfig.from_yaml(config_path)
    reference_packet = load_paper_decision_reference_packet(reference_packet_path)
    collector = PaperFyersSnapshotCollector(artifact_root=artifact_root)
    decision_builder = S21PaperLiveDecisionBuilder(config_path=str(config_path))
    timeline_builder = PaperLiveDecisionTimelineBuilder(decision_builder=decision_builder)
    carry_forward_position = (
        PaperPositionStateStore().load_state(carry_forward_state_dir)
        if carry_forward_state_dir is not None
        else None
    )

    # One durable S21 session directory; leg folders are children, not independent sessions.
    opening_trigger = _wait_for(
        hour=9,
        minute=16,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
        if_past=if_past,
    )
    session_date = opening_trigger.date()
    session_directory = (
        Path(artifact_root)
        / session_date.isoformat()
        / f"{session_id_prefix}-{session_date.isoformat()}"
    )
    session_directory.mkdir(parents=True, exist_ok=True)

    strategy_trace: dict[str, Any] = {
        "strategy_code": "S21",
        "session_date": session_date.isoformat(),
        "flow_version": "S21_SINGLE_STRATEGY_FLOW_V1",
        "timing": {
            "base_calculation": "09:16",
            "orpt_gate": "09:25",
            "rc_gate": "09:30",
        },
        "monthly_status": None,
        "eligible_legs": [],
        "ineligible_legs": [],
        "legs": {},
        "orders_created_at_orpt": [],
        "legs_deferred_to_rc": [],
        "orders_created_at_rc": [],
    }

    # ------------------------------------------------------------------
    # 09:16 BASE CALCULATION
    # ------------------------------------------------------------------
    opening_snapshot = collector.collect_from_files(
        config_path=config_path,
        strategy_path=strategy_paths[0],
        carry_forward_state_dir=carry_forward_state_dir,
        session_id=f"{session_id_prefix}-0916-{session_date.isoformat()}",
        adapter=None,
    )
    if opening_snapshot.collected_inputs is None:
        raise RuntimeError("S21 09:16 snapshot did not return collected inputs.")

    # Monthly status is strategy-level. Use one anchor stage only to resolve it.
    anchor_rule = rules[0]
    anchor_stage = timeline_builder.build_stage(
        stage_name="Opening Snapshot",
        stage_time=time(9, 16),
        strategy_rule=anchor_rule,
        reference_packet=reference_packet.__class__(
            **{
                **reference_packet.__dict__,
                "strategy_branch": anchor_rule.unique_code,
            }
        ) if hasattr(reference_packet, "__dict__") else reference_packet,
        collected_inputs=opening_snapshot.collected_inputs,
        carry_forward_position=carry_forward_position,
        smoke_override_enabled=enable_smoke_override,
        smoke_override_selected_contract_symbol=(
            ingress_config.market.selected_contract_symbol if enable_smoke_override else None
        ),
        allow_branch_pinned_unknown_monthly_status=True,
        require_orpt_rc_timing_bars=False,
    )
    try:
        resolved_status = MonthlyStatus(anchor_stage.stage.monthly_status)
    except ValueError as exc:
        raise RuntimeError(
            f"S21 09:16 monthly status is not a supported business state: "
            f"{anchor_stage.stage.monthly_status}"
        ) from exc

    eligible_codes = eligible_s21_unique_codes(status=resolved_status, strategy_rules=rules)
    if len(eligible_codes) != 2:
        raise RuntimeError(
            f"S21 monthly status {resolved_status.value} must resolve exactly two eligible "
            f"legs, got {eligible_codes}."
        )
    eligible_rules = tuple(rule for rule in rules if rule.unique_code in eligible_codes)
    strategy_trace["monthly_status"] = resolved_status.value
    strategy_trace["eligible_legs"] = list(eligible_codes)
    strategy_trace["ineligible_legs"] = [
        rule.unique_code for rule in rules if rule.unique_code not in eligible_codes
    ]

    base_decisions: dict[str, Any] = {}
    base_selected_symbols: dict[str, str] = {}
    for rule in eligible_rules:
        leg_dir = session_directory / "legs" / rule.unique_code
        leg_dir.mkdir(parents=True, exist_ok=True)
        leg_packet = _replace_reference_branch(reference_packet, rule.unique_code)
        build = timeline_builder.build_stage(
            stage_name="Base Calculation 09:16",
            stage_time=time(9, 16),
            strategy_rule=rule,
            reference_packet=leg_packet,
            collected_inputs=opening_snapshot.collected_inputs,
            carry_forward_position=carry_forward_position,
            smoke_override_enabled=enable_smoke_override,
            smoke_override_selected_contract_symbol=(
                ingress_config.market.selected_contract_symbol if enable_smoke_override else None
            ),
            allow_branch_pinned_unknown_monthly_status=True,
            require_orpt_rc_timing_bars=False,
        )
        timeline_builder.write_stage_artifacts(
            session_date=session_date,
            strategy_code="S21",
            strategy_branch=rule.unique_code,
            stage=build.stage,
            output_dir=leg_dir,
        )
        if build.decision_result is None:
            strategy_trace["legs"][rule.unique_code] = {
                "base_status": "NO_BASE_DECISION",
                "failure_code": build.stage.decision_failure_code,
                "failure_message": build.stage.decision_failure_message,
            }
            continue
        decision = build.decision_result
        base_decisions[rule.unique_code] = decision
        if decision.summary.selected_contract_symbol:
            base_selected_symbols[rule.unique_code] = decision.summary.selected_contract_symbol
        strategy_trace["legs"][rule.unique_code] = {
            "base_status": decision.summary.status,
            "selected_contract": decision.summary.selected_contract_symbol,
            "entry": decision.summary.planned_entry_price,
            "target": decision.summary.target_price,
            "stoploss": decision.summary.stoploss_price,
            "base_calculated_at": opening_trigger.isoformat(),
            "orpt_state": "PENDING",
            "rc_state": "NOT_REQUIRED_YET",
        }

    # ------------------------------------------------------------------
    # 09:25 ORPT / GAP-MISSED-ENTRY GATE
    # ------------------------------------------------------------------
    orpt_trigger = _wait_for(
        hour=9,
        minute=25,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
        if_past=if_past,
    )
    # Capture shared market context once at ORPT.
    orpt_snapshot = collector.collect_from_files(
        config_path=config_path,
        strategy_path=strategy_paths[0],
        carry_forward_state_dir=carry_forward_state_dir,
        session_id=f"{session_id_prefix}-0925-{session_date.isoformat()}",
        adapter=None,
    )
    if orpt_snapshot.collected_inputs is None:
        raise RuntimeError("S21 09:25 snapshot did not return collected inputs.")

    rc_pending: list[Any] = []
    branch_final_summary_json: dict[str, str] = {}
    branch_final_summary_markdown: dict[str, str] = {}
    branch_order_state_json: dict[str, str] = {}
    first_summary_json: Path | None = None
    first_summary_md: Path | None = None

    for rule in eligible_rules:
        code = rule.unique_code
        decision = base_decisions.get(code)
        if decision is None or not decision.summary.selected_contract_symbol:
            continue
        symbol = decision.summary.selected_contract_symbol
        bars = collector.collect_selected_contract_bars_from_files(
            config_path=config_path,
            option_symbol=symbol,
            session_date=session_date,
            from_time=time(9, 24),
            to_time=time(9, 24),
        )
        orpt_bar = _find_bar(bars, start=time(9, 24))
        if orpt_bar is None:
            strategy_trace["legs"][code]["orpt_state"] = "BLOCKED_MISSING_ORPT_OPTION_BAR"
            continue

        requires_rc = s21_orpt_requires_recalculation(
            option_type=rule.option_type,
            base_entry=float(decision.summary.planned_entry_price),
            option_low=orpt_bar.low,
            option_high=orpt_bar.high,
        )
        strategy_trace["legs"][code]["orpt_observation"] = {
            "symbol": symbol,
            "option_low": orpt_bar.low,
            "option_high": orpt_bar.high,
            "base_entry": decision.summary.planned_entry_price,
            "observed_at": orpt_trigger.isoformat(),
        }

        if requires_rc:
            strategy_trace["legs"][code]["orpt_state"] = "RECALCULATION_REQUIRED"
            strategy_trace["legs"][code]["rc_state"] = "PENDING_09_30"
            strategy_trace["legs_deferred_to_rc"].append(code)
            rc_pending.append(rule)
            continue

        # Normal path: use the 09:16 decision unchanged and place at ORPT.
        strategy_trace["legs"][code]["orpt_state"] = "NORMAL_BASE_ENTRY_VALID"
        strategy_trace["legs"][code]["rc_state"] = "NOT_REQUIRED"
        leg_dir = session_directory / "legs" / code
        summary_json, summary_md = decision_builder.write_artifacts(
            decision,
            output_dir=leg_dir,
        )
        branch_final_summary_json[code] = str(summary_json)
        branch_final_summary_markdown[code] = str(summary_md)
        if first_summary_json is None:
            first_summary_json, first_summary_md = summary_json, summary_md

        if (
            decision.summary.status == "READY"
            and not decision.summary.order_placement_blocked
            and decision.summary.selected_contract_symbol
            and decision.summary.planned_entry_price is not None
        ):
            _, order_state_path, _ = PaperOrderStateStore().create_waiting_order_from_live_decision(
                leg_dir,
                strategy_rule=rule,
                decision=decision,
                created_at=orpt_trigger,
                provenance_source_ids=(str(summary_json),),
            )
            branch_order_state_json[code] = str(order_state_path)
            strategy_trace["orders_created_at_orpt"].append(code)

    # ------------------------------------------------------------------
    # 09:30 RC - only deferred legs are recalculated/evaluated.
    # ------------------------------------------------------------------
    rc_trigger = _wait_for(
        hour=9,
        minute=30,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
        if_past=if_past,
    )

    if rc_pending:
        rc_snapshot = collector.collect_from_files(
            config_path=config_path,
            strategy_path=strategy_paths[0],
            carry_forward_state_dir=carry_forward_state_dir,
            session_id=f"{session_id_prefix}-0930-{session_date.isoformat()}",
            adapter=None,
        )
        if rc_snapshot.collected_inputs is None:
            raise RuntimeError("S21 09:30 snapshot did not return collected inputs.")

        for rule in rc_pending:
            code = rule.unique_code
            base_symbol = base_selected_symbols.get(code)
            enriched_inputs = rc_snapshot.collected_inputs
            if base_symbol:
                bars = collector.collect_selected_contract_bars_from_files(
                    config_path=config_path,
                    option_symbol=base_symbol,
                    session_date=session_date,
                    from_time=time(9, 24),
                    to_time=time(9, 29),
                )
                if bars:
                    from dataclasses import replace
                    enriched_inputs = replace(
                        enriched_inputs,
                        selected_contract_bars=tuple(bars),
                    )

            leg_dir = session_directory / "legs" / code
            leg_packet = _replace_reference_branch(reference_packet, code)
            build = timeline_builder.build_stage(
                stage_name="RC Recalculation 09:30",
                stage_time=time(9, 30),
                strategy_rule=rule,
                reference_packet=leg_packet,
                collected_inputs=enriched_inputs,
                carry_forward_position=carry_forward_position,
                smoke_override_enabled=enable_smoke_override,
                smoke_override_selected_contract_symbol=(
                    ingress_config.market.selected_contract_symbol if enable_smoke_override else None
                ),
                allow_branch_pinned_unknown_monthly_status=True,
                require_orpt_rc_timing_bars=True,
            )
            timeline_builder.write_stage_artifacts(
                session_date=session_date,
                strategy_code="S21",
                strategy_branch=code,
                stage=build.stage,
                output_dir=leg_dir,
            )
            if build.decision_result is None:
                strategy_trace["legs"][code]["rc_state"] = "RC_DECISION_FAILED"
                strategy_trace["legs"][code]["rc_failure_code"] = build.stage.decision_failure_code
                strategy_trace["legs"][code]["rc_failure_message"] = build.stage.decision_failure_message
                continue

            decision = build.decision_result
            timing_status = str(
                decision.explanation.get("orpt_rc_timing", {}).get("status", "")
            )
            strategy_trace["legs"][code]["rc_state"] = timing_status or "RC_EVALUATED"
            strategy_trace["legs"][code]["rc_selected_contract"] = (
                decision.summary.selected_contract_symbol
            )
            strategy_trace["legs"][code]["rc_entry"] = decision.summary.planned_entry_price

            summary_json, summary_md = decision_builder.write_artifacts(
                decision,
                output_dir=leg_dir,
            )
            branch_final_summary_json[code] = str(summary_json)
            branch_final_summary_markdown[code] = str(summary_md)
            if first_summary_json is None:
                first_summary_json, first_summary_md = summary_json, summary_md

            if (
                decision.summary.status == "READY"
                and not decision.summary.order_placement_blocked
                and decision.summary.selected_contract_symbol
                and decision.summary.planned_entry_price is not None
            ):
                _, order_state_path, _ = PaperOrderStateStore().create_waiting_order_from_live_decision(
                    leg_dir,
                    strategy_rule=rule,
                    decision=decision,
                    created_at=rc_trigger,
                    provenance_source_ids=(str(summary_json),),
                )
                branch_order_state_json[code] = str(order_state_path)
                strategy_trace["orders_created_at_rc"].append(code)

    # One strategy-level audit instead of four independent strategy timelines.
    strategy_trace["completed_at"] = rc_trigger.isoformat()
    timeline_json = session_directory / "s21_strategy_session.json"
    timeline_md = session_directory / "s21_strategy_session.md"
    timeline_json.write_text(
        json.dumps(strategy_trace, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    timeline_md.write_text(_render_strategy_markdown(strategy_trace), encoding="utf-8")

    return S21StrategySessionResult(
        session_directory=session_directory,
        timeline_json=timeline_json,
        timeline_markdown=timeline_md,
        final_summary_json=first_summary_json,
        final_summary_markdown=first_summary_md,
        branch_final_summary_json=branch_final_summary_json,
        branch_final_summary_markdown=branch_final_summary_markdown,
        branch_order_state_json=branch_order_state_json,
    )


def _wait_for(
    *,
    hour: int,
    minute: int,
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
    if_past: str,
) -> datetime:
    now = now_fn()
    delay = compute_schedule_delay_seconds(
        now=now,
        target_hour=hour,
        target_minute=minute,
        if_past=if_past,
    )
    _ = build_schedule_note(
        now=now,
        target_hour=hour,
        target_minute=minute,
        delay_seconds=delay,
    )
    if delay > 0:
        sleep_fn(delay)
    return now_fn()


def _replace_reference_branch(packet: Any, unique_code: str) -> Any:
    from dataclasses import replace
    return replace(packet, strategy_branch=unique_code)


def _find_bar(bars: tuple[Any, ...], *, start: time) -> Any | None:
    for bar in sorted(bars, key=lambda item: item.bar_start):
        if bar.bar_start.timetz().replace(tzinfo=None) == start:
            return bar
    return None


def _render_strategy_markdown(trace: dict[str, Any]) -> str:
    lines = [
        "# S21 Strategy Session",
        "",
        f"- Session: `{trace['session_date']}`",
        f"- Monthly Status: `{trace['monthly_status']}`",
        f"- Eligible Legs: `{', '.join(trace['eligible_legs'])}`",
        "",
        "## Timing Flow",
        "- `09:16`: one strategy-level base calculation; no order placement.",
        "- `09:25`: ORPT normal-vs-recalculation gate.",
        "- Normal path: place the unchanged 09:16 base order at ORPT.",
        "- Recalculation path: do not place at ORPT; defer to RC.",
        "- `09:30`: evaluate/place only the legs that were deferred to RC.",
        "",
        "## Leg Results",
    ]
    for code, leg in trace["legs"].items():
        lines.extend(
            [
                f"### {code}",
                f"- Base: `{leg.get('base_status')}`",
                f"- Contract: `{leg.get('selected_contract')}`",
                f"- Entry: `{leg.get('entry')}`",
                f"- ORPT: `{leg.get('orpt_state')}`",
                f"- RC: `{leg.get('rc_state')}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "S21StrategySessionResult",
    "eligible_s21_unique_codes",
    "run_s21_strategy_session",
    "s21_orpt_requires_recalculation",
]
