from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from tfis.domain import MarketLevels, StrategyRule
from tfis.formulas import FormulaEngine
from tfis.market_data import UnderlyingHistoryBar
from tfis.monthly_status import (
    MonthlyStatusHistoricalBar,
    MonthlyStatusEngine,
    MonthlyStatusLookbackResolver,
    MonthlyStatusLookbackWindow,
    MonthlyStatusReferenceLevels,
    MonthlyStatusResolutionResult,
    build_monthly_weekly_context_lookback_windows,
)

from .fyers_snapshot_collector import S23CollectedSnapshotInputs
from .live_reference_derivation import S23LiveReferenceDeriver
from .live_decision import (
    S23PaperLiveDecisionBuilder,
    S23PaperLiveDecisionError,
    S23PaperLiveDecisionResult,
)
from .live_prelude import S23LivePreludeError
from .models import SnapshotLabel
from .position_state import S23PaperPositionState
from .runtime_input_derivation import S23DecisionReferencePacket, S23RuntimeInputDerivationError


_CHECKPOINT_LABELS = {
    time(9, 14): "0915",
    time(9, 15): "0915",
    time(9, 24): "ORPT",
    time(9, 29): "RC",
}
_STAGE_CHECKPOINT_REQUIREMENTS = ("0915", "ORPT", "RC")
_FORMULA_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True, slots=True)
class S23LiveDecisionTimelineCheckpoint:
    label: str
    bar_start: str
    bar_end: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    included_in_stage: bool


@dataclass(frozen=True, slots=True)
class S23LiveDecisionTimelineStage:
    stage_name: str
    stage_time: str
    captured_at: str
    underlying_spot_value: float | None
    available_checkpoint_labels: tuple[str, ...]
    waiting_for_checkpoint_labels: tuple[str, ...]
    checkpoint_observations: tuple[S23LiveDecisionTimelineCheckpoint, ...]
    current_day_high_so_far: float | None
    current_day_low_so_far: float | None
    monthly_status_price_used: float | None
    monthly_status: str
    monthly_status_trigger: str
    monthly_status_notes: str
    monthly_status_lookback_used: bool
    monthly_status_resolution_reason: str
    monthly_status_trace: tuple[dict[str, Any], ...]
    can_finalize_trade_decision: bool
    market_reference_values: dict[str, Any]
    option_reference_values: dict[str, Any]
    provisional_formula_evaluation: tuple[dict[str, Any], ...]
    decision_summary: dict[str, Any] | None
    decision_explanation: dict[str, Any] | None
    decision_failure_code: str | None
    decision_failure_message: str | None
    decision_failure_attempted_expiries: tuple[str, ...] = ()
    decision_failure_rejected_counts: dict[str, int] | None = None


@dataclass(frozen=True, slots=True)
class S23LiveDecisionTimelineResult:
    session_date: date
    strategy_code: str
    strategy_branch: str
    stages: tuple[S23LiveDecisionTimelineStage, ...]


@dataclass(frozen=True, slots=True)
class S23LiveDecisionTimelineStageBuild:
    stage: S23LiveDecisionTimelineStage
    decision_result: S23PaperLiveDecisionResult | None


class S23LiveDecisionTimelineBuilder:
    def __init__(
        self,
        *,
        decision_builder: S23PaperLiveDecisionBuilder | None = None,
        monthly_status_engine: MonthlyStatusEngine | None = None,
        monthly_status_lookback_resolver: MonthlyStatusLookbackResolver | None = None,
        live_reference_deriver: S23LiveReferenceDeriver | None = None,
    ) -> None:
        self._decision_builder = decision_builder or S23PaperLiveDecisionBuilder()
        self._monthly_status_engine = monthly_status_engine or MonthlyStatusEngine()
        self._monthly_status_lookback_resolver = (
            monthly_status_lookback_resolver
            or MonthlyStatusLookbackResolver(
                monthly_status_engine=self._monthly_status_engine
            )
        )
        self._live_reference_deriver = live_reference_deriver or S23LiveReferenceDeriver()

    def build_stage(
        self,
        *,
        stage_name: str,
        stage_time: time,
        strategy_rule: StrategyRule,
        reference_packet: S23DecisionReferencePacket,
        collected_inputs: S23CollectedSnapshotInputs,
        carry_forward_position: S23PaperPositionState | None = None,
        smoke_override_enabled: bool = False,
        smoke_override_selected_contract_symbol: str | None = None,
        allow_branch_pinned_unknown_monthly_status: bool = False,
        require_orpt_rc_timing_bars: bool = True,
    ) -> S23LiveDecisionTimelineStageBuild:
        effective_reference_packet = self._live_reference_deriver.derive(
            base_reference_packet=reference_packet,
            collected_inputs=collected_inputs,
        ).effective_reference_packet
        checkpoint_observations = self._checkpoint_observations(
            collected_inputs=collected_inputs,
            stage_time=stage_time,
        )
        available_labels = tuple(
            item.label for item in checkpoint_observations if item.included_in_stage
        )
        waiting_for = tuple(
            label for label in _STAGE_CHECKPOINT_REQUIREMENTS if label not in available_labels
        )
        monthly_status_price = self._stage_monthly_status_price(
            checkpoint_observations,
            fallback_price=collected_inputs.underlying_quote.ltp,
        )
        monthly_status = self._classify_monthly_status(
            reference_packet=effective_reference_packet,
            current_price=monthly_status_price,
            current_reference_timestamp=self._stage_reference_timestamp(
                checkpoint_observations,
                fallback_timestamp=collected_inputs.session_context.generated_at,
            ),
            daily_bars=collected_inputs.daily_bars,
        )
        current_day_high_so_far, current_day_low_so_far = self._current_day_levels_so_far(
            checkpoint_observations
        )
        stage_market_levels = self._stage_market_levels(
            reference_packet=effective_reference_packet,
            current_day_high_so_far=current_day_high_so_far,
            current_day_low_so_far=current_day_low_so_far,
        )
        stage_runtime_values = self._stage_runtime_values(effective_reference_packet)
        provisional_formula_evaluation = self._build_formula_explanations(
            strategy_rule=strategy_rule,
            market_levels=stage_market_levels,
            runtime_values=stage_runtime_values,
        )

        can_evaluate_decision = not waiting_for or self._can_evaluate_orpt_stage(
            stage_name=stage_name,
            available_labels=available_labels,
        )
        required_snapshot_labels = self._required_snapshot_labels_for_decision(
            stage_name=stage_name,
            waiting_for=waiting_for,
        )
        can_finalize = not waiting_for
        decision: S23PaperLiveDecisionResult | None = None
        decision_failure_code: str | None = None
        decision_failure_message: str | None = None
        decision_failure_attempted_expiries: tuple[str, ...] = ()
        decision_failure_rejected_counts: dict[str, int] | None = None
        if can_evaluate_decision:
            try:
                decision = self._decision_builder.build(
                    strategy_rule=strategy_rule,
                    reference_packet=effective_reference_packet,
                    collected_inputs=collected_inputs,
                    carry_forward_position=carry_forward_position,
                    smoke_override_enabled=smoke_override_enabled,
                    smoke_override_selected_contract_symbol=smoke_override_selected_contract_symbol,
                    allow_branch_pinned_unknown_monthly_status=allow_branch_pinned_unknown_monthly_status,
                    require_orpt_rc_timing_bars=require_orpt_rc_timing_bars,
                    required_snapshot_labels=required_snapshot_labels,
                )
            except (
                S23PaperLiveDecisionError,
                S23LivePreludeError,
                S23RuntimeInputDerivationError,
            ) as exc:
                decision_failure_code = getattr(exc, "code", "LIVE_DECISION_FAILED")
                decision_failure_message = str(exc)
                selection = getattr(exc, "contract_selection", None)
                if selection is not None:
                    decision_failure_attempted_expiries = tuple(
                        expiry.isoformat() for expiry in selection.attempted_expiries
                    )
                    decision_failure_rejected_counts = dict(selection.rejected_candidate_counts)
        if decision is not None:
            can_finalize = self._can_finalize_stage_decision(
                stage_name=stage_name,
                waiting_for=waiting_for,
                decision=decision,
            )

        stage = S23LiveDecisionTimelineStage(
            stage_name=stage_name,
            stage_time=stage_time.strftime("%H:%M"),
            captured_at=collected_inputs.session_context.generated_at.isoformat(),
            underlying_spot_value=collected_inputs.underlying_quote.ltp,
            available_checkpoint_labels=available_labels,
            waiting_for_checkpoint_labels=waiting_for,
            checkpoint_observations=checkpoint_observations,
            current_day_high_so_far=current_day_high_so_far,
            current_day_low_so_far=current_day_low_so_far,
            monthly_status_price_used=monthly_status_price,
            monthly_status=monthly_status.resolved_result.status.value,
            monthly_status_trigger=monthly_status.resolved_result.trigger_name,
            monthly_status_notes=monthly_status.resolved_result.notes,
            monthly_status_lookback_used=monthly_status.lookback_used,
            monthly_status_resolution_reason=monthly_status.reason,
            monthly_status_trace=tuple(
                {
                    "lookback_index": item.lookback_index,
                    "window_label": item.window_label,
                    "reference_timestamp": item.reference_timestamp.isoformat(),
                    "context_month_label": item.context_month_label,
                    "context_week_label": item.context_week_label,
                    "PMH": item.PMH,
                    "PML": item.PML,
                    "CMH": item.CMH,
                    "CML": item.CML,
                    "PWH": item.PWH,
                    "PWL": item.PWL,
                    "CWH": item.CWH,
                    "CWL": item.CWL,
                    "current_price": item.current_price,
                    "status": item.status.value,
                    "normalized_status": (
                        item.normalized_status.value
                        if item.normalized_status is not None
                        else None
                    ),
                    "trigger_name": item.trigger_name,
                    "threshold_value": item.threshold_value,
                    "notes": item.notes,
                    "used_for_resolution": item.used_for_resolution,
                }
                for item in monthly_status.trace
            ),
            can_finalize_trade_decision=can_finalize,
            market_reference_values=self._reference_values(
                reference_packet=effective_reference_packet,
                current_day_high_so_far=current_day_high_so_far,
                current_day_low_so_far=current_day_low_so_far,
            ),
            option_reference_values={
                key: {"value": value, "source": "tfis_reference_packet"}
                for key, value in sorted(effective_reference_packet.option_reference_values.items())
            },
            provisional_formula_evaluation=provisional_formula_evaluation,
            decision_summary=asdict(decision.summary) if decision is not None else None,
            decision_explanation=decision.explanation if decision is not None else None,
            decision_failure_code=decision_failure_code,
            decision_failure_message=decision_failure_message,
            decision_failure_attempted_expiries=decision_failure_attempted_expiries,
            decision_failure_rejected_counts=decision_failure_rejected_counts,
        )
        return S23LiveDecisionTimelineStageBuild(
            stage=stage,
            decision_result=decision,
        )

    @staticmethod
    def _can_evaluate_orpt_stage(
        *,
        stage_name: str,
        available_labels: tuple[str, ...],
    ) -> bool:
        return stage_name == "ORPT Snapshot" and {"0915", "ORPT"}.issubset(set(available_labels))

    @staticmethod
    def _required_snapshot_labels_for_decision(
        *,
        stage_name: str,
        waiting_for: tuple[str, ...],
    ) -> tuple[SnapshotLabel, ...] | None:
        if stage_name == "ORPT Snapshot" and waiting_for == ("RC",):
            return (SnapshotLabel.AT_0915, SnapshotLabel.ORPT)
        return None

    @staticmethod
    def _can_finalize_stage_decision(
        *,
        stage_name: str,
        waiting_for: tuple[str, ...],
        decision: S23PaperLiveDecisionResult,
    ) -> bool:
        if not waiting_for:
            return True
        timing_status = str(
            decision.explanation.get("orpt_rc_timing", {}).get("status", "")
        )
        return stage_name == "ORPT Snapshot" and timing_status == "BASE_ENTRY_VALID"

    def build_timeline(
        self,
        *,
        session_date: date,
        strategy_rule: StrategyRule,
        strategy_branch: str,
        stages: tuple[S23LiveDecisionTimelineStage, ...],
    ) -> S23LiveDecisionTimelineResult:
        return S23LiveDecisionTimelineResult(
            session_date=session_date,
            strategy_code=strategy_rule.strategy_code,
            strategy_branch=strategy_branch,
            stages=stages,
        )

    def write_artifacts(
        self,
        result: S23LiveDecisionTimelineResult,
        *,
        output_dir: str | Path,
    ) -> tuple[Path, Path]:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        json_path = target / "trade_decision_explainer.json"
        md_path = target / "trade_decision_explainer.md"
        json_path.write_text(
            json.dumps(
                {
                    "session_date": result.session_date.isoformat(),
                    "strategy_code": result.strategy_code,
                    "strategy_branch": result.strategy_branch,
                    "stages": [asdict(stage) for stage in result.stages],
                },
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        md_path.write_text(self.render_markdown(result), encoding="utf-8")
        return json_path, md_path

    def write_stage_artifacts(
        self,
        *,
        session_date: date,
        strategy_code: str,
        strategy_branch: str,
        stage: S23LiveDecisionTimelineStage,
        output_dir: str | Path,
    ) -> tuple[Path, Path, Path, Path]:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        stage_suffix = stage.stage_time.replace(":", "")
        stage_json_path = target / f"trade_decision_explainer_stage_{stage_suffix}.json"
        stage_md_path = target / f"trade_decision_explainer_stage_{stage_suffix}.md"
        monthly_status_json_path = target / f"monthly_status_stage_{stage_suffix}.json"
        monthly_status_md_path = target / f"monthly_status_stage_{stage_suffix}.md"
        stage_json_path.write_text(
            json.dumps(
                {
                    "session_date": session_date.isoformat(),
                    "strategy_code": strategy_code,
                    "strategy_branch": strategy_branch,
                    "stage": asdict(stage),
                },
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        stage_md_path.write_text(
            self.render_stage_markdown(
                session_date=session_date,
                strategy_code=strategy_code,
                strategy_branch=strategy_branch,
                stage=stage,
            ),
            encoding="utf-8",
        )
        monthly_status_json_path.write_text(
            json.dumps(
                {
                    "session_date": session_date.isoformat(),
                    "strategy_code": strategy_code,
                    "strategy_branch": strategy_branch,
                    "stage_name": stage.stage_name,
                    "stage_time": stage.stage_time,
                    "captured_at": stage.captured_at,
                    "monthly_status": {
                        "price_used": stage.monthly_status_price_used,
                        "status": stage.monthly_status,
                        "trigger_name": stage.monthly_status_trigger,
                        "notes": stage.monthly_status_notes,
                        "lookback_used": stage.monthly_status_lookback_used,
                        "resolution_reason": stage.monthly_status_resolution_reason,
                        "trace": list(stage.monthly_status_trace),
                    },
                },
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        monthly_status_md_path.write_text(
            self.render_stage_monthly_status_markdown(
                session_date=session_date,
                strategy_code=strategy_code,
                strategy_branch=strategy_branch,
                stage=stage,
            ),
            encoding="utf-8",
        )
        return (
            stage_json_path,
            stage_md_path,
            monthly_status_json_path,
            monthly_status_md_path,
        )

    def render_markdown(self, result: S23LiveDecisionTimelineResult) -> str:
        lines = [
            "# S23 Trade Decision Explainer",
            "",
            f"- Session Date: `{result.session_date.isoformat()}`",
            f"- Strategy: `{result.strategy_code}` / `{result.strategy_branch}`",
            "- This report explains what TFIS knows at `09:16`, `09:25`, and `09:30`, and it only finalizes the trade once all required checkpoints are available.",
        ]
        for stage in result.stages:
            lines.extend(["", *self._render_stage_lines(stage)])
        return "\n".join(lines) + "\n"

    def render_stage_markdown(
        self,
        *,
        session_date: date,
        strategy_code: str,
        strategy_branch: str,
        stage: S23LiveDecisionTimelineStage,
    ) -> str:
        lines = [
            "# S23 Trade Decision Stage Explainer",
            "",
            f"- Session Date: `{session_date.isoformat()}`",
            f"- Strategy: `{strategy_code}` / `{strategy_branch}`",
            f"- Stage: `{stage.stage_name}` at `{stage.stage_time}`",
            "- This report is written immediately after the stage completes so monthly status can be checked without waiting for later checkpoints.",
            "",
            *self._render_stage_lines(stage),
        ]
        return "\n".join(lines) + "\n"

    def render_stage_monthly_status_markdown(
        self,
        *,
        session_date: date,
        strategy_code: str,
        strategy_branch: str,
        stage: S23LiveDecisionTimelineStage,
    ) -> str:
        lines = [
            "# S23 Monthly Status Stage Summary",
            "",
            f"- Session Date: `{session_date.isoformat()}`",
            f"- Strategy: `{strategy_code}` / `{strategy_branch}`",
            f"- Stage: `{stage.stage_name}` at `{stage.stage_time}`",
            f"- Captured At: `{stage.captured_at}`",
            f"- Monthly Status Price Used: `{stage.monthly_status_price_used}`",
            f"- Monthly Status: `{stage.monthly_status}` via `{stage.monthly_status_trigger}`",
            f"- Monthly Status Notes: `{stage.monthly_status_notes}`",
            f"- Monthly Status Lookback Used: `{stage.monthly_status_lookback_used}`",
            f"- Monthly Status Resolution Reason: `{stage.monthly_status_resolution_reason}`",
            "",
            "## Trace",
        ]
        for trace_item in stage.monthly_status_trace:
            lines.append(
                f"- `{trace_item['window_label']}` "
                f"({trace_item['context_month_label']} / {trace_item['context_week_label']}) "
                f"@ `{trace_item['reference_timestamp']}` -> "
                f"base=`{trace_item['status']}` normalized=`{trace_item['normalized_status']}` "
                f"via `{trace_item['trigger_name']}`"
            )
            lines.append(
                f"  Levels: PMH `{trace_item['PMH']}`, PML `{trace_item['PML']}`, "
                f"CMH `{trace_item['CMH']}`, CML `{trace_item['CML']}`, "
                f"PWH `{trace_item['PWH']}`, PWL `{trace_item['PWL']}`, "
                f"CWH `{trace_item['CWH']}`, CWL `{trace_item['CWL']}`, "
                f"close `{trace_item['current_price']}`"
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_stage_lines(stage: S23LiveDecisionTimelineStage) -> list[str]:
        lines = [
            f"## {stage.stage_name} ({stage.stage_time})",
            f"- Captured At: `{stage.captured_at}`",
            f"- NIFTY Spot Used: `{stage.underlying_spot_value}`",
            f"- Available Checkpoints: `{', '.join(stage.available_checkpoint_labels) or 'none'}`",
            f"- Waiting For: `{', '.join(stage.waiting_for_checkpoint_labels) or 'none'}`",
            f"- Current Day High So Far (`CDHH`): `{stage.current_day_high_so_far}`",
            f"- Current Day Low So Far (`CDLL`): `{stage.current_day_low_so_far}`",
            f"- Monthly Status Price Used: `{stage.monthly_status_price_used}`",
            f"- Monthly Status: `{stage.monthly_status}` via `{stage.monthly_status_trigger}`",
            f"- Monthly Status Notes: `{stage.monthly_status_notes}`",
            f"- Monthly Status Lookback Used: `{stage.monthly_status_lookback_used}`",
            f"- Monthly Status Resolution Reason: `{stage.monthly_status_resolution_reason}`",
            f"- Can Finalize Trade Decision: `{stage.can_finalize_trade_decision}`",
            "",
            "### Snapshot Logic",
        ]
        for checkpoint in stage.checkpoint_observations:
            inclusion = "used at this stage" if checkpoint.included_in_stage else "not available yet"
            lines.append(
                f"- `{checkpoint.label}` from `{checkpoint.bar_start}` to `{checkpoint.bar_end}`: "
                f"open `{checkpoint.open}`, high `{checkpoint.high}`, low `{checkpoint.low}`, close `{checkpoint.close}` -> {inclusion}"
            )
        lines.extend(["", "### Monthly Status Trace"])
        for trace_item in stage.monthly_status_trace:
            lines.append(
                f"- `{trace_item['window_label']}` "
                f"({trace_item['context_month_label']} / {trace_item['context_week_label']}) "
                f"@ `{trace_item['reference_timestamp']}` -> "
                f"base=`{trace_item['status']}` normalized=`{trace_item['normalized_status']}` "
                f"via `{trace_item['trigger_name']}` (used=`{trace_item['used_for_resolution']}`)"
            )
            lines.append(
                f"  Levels: PMH `{trace_item['PMH']}`, PML `{trace_item['PML']}`, "
                f"CMH `{trace_item['CMH']}`, CML `{trace_item['CML']}`, "
                f"PWH `{trace_item['PWH']}`, PWL `{trace_item['PWL']}`, "
                f"CWH `{trace_item['CWH']}`, CWL `{trace_item['CWL']}`, "
                f"close `{trace_item['current_price']}`"
            )
        lines.extend(["", "### Market Reference Values"])
        for alias, payload in stage.market_reference_values.items():
            lines.append(f"- `{alias}` = `{payload['value']}` from `{payload['source']}`")
        lines.extend(["", "### Option Reference Values"])
        for alias, payload in stage.option_reference_values.items():
            lines.append(f"- `{alias}` = `{payload['value']}` from `{payload['source']}`")
        lines.extend(["", "### Provisional Formula Evaluation"])
        for item in stage.provisional_formula_evaluation:
            lines.extend(
                [
                    f"- `{item['name']}`",
                    f"  Formula: `{item['formula']}`",
                    f"  Resolved: `{item['resolved_formula']}`",
                    f"  Result: `{item['result']}`",
                ]
            )
        if stage.decision_summary is not None:
            lines.extend(
                [
                    "",
                    "### Final Decision At This Stage",
                    f"- Selected Contract: `{stage.decision_summary.get('selected_contract_symbol')}`",
                    f"- Expiry: `{stage.decision_summary.get('selected_contract_expiry')}`",
                    f"- Strike: `{stage.decision_summary.get('selected_contract_strike')}`",
                    f"- Option Type: `{stage.decision_summary.get('selected_contract_option_type')}`",
                    f"- Premium: `{stage.decision_summary.get('selected_contract_ltp')}`",
                    f"- OI: `{stage.decision_summary.get('selected_contract_oi')}`",
                    f"- Entry: `{stage.decision_summary.get('planned_entry_price')}`",
                    f"- Target: `{stage.decision_summary.get('target_price')}`",
                    f"- Stoploss: `{stage.decision_summary.get('stoploss_price')}`",
                    f"- Selection Reason: `{stage.decision_summary.get('contract_selection_reason')}`",
                ]
            )
        elif stage.decision_failure_code is not None:
            lines.extend(
                [
                    "",
                    "### Final Decision At This Stage",
                    f"- Final decision could not be produced: `{stage.decision_failure_code}`",
                    f"- Reason: `{stage.decision_failure_message}`",
                    "- Attempted Expiries: `"
                    + (", ".join(stage.decision_failure_attempted_expiries) or "none")
                    + "`",
                    f"- Rejected Candidate Counts: `{stage.decision_failure_rejected_counts or {}}`",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "### Final Decision At This Stage",
                    "- TFIS does not finalize the trade yet because later checkpoint data is still pending.",
                ]
            )
        return lines

    def _checkpoint_observations(
        self,
        *,
        collected_inputs: S23CollectedSnapshotInputs,
        stage_time: time,
    ) -> tuple[S23LiveDecisionTimelineCheckpoint, ...]:
        observations: list[S23LiveDecisionTimelineCheckpoint] = []
        for bar in collected_inputs.underlying_bars:
            label = _CHECKPOINT_LABELS.get(bar.bar_start.timetz().replace(tzinfo=None))
            if label is None:
                continue
            included = bar.bar_end.timetz().replace(tzinfo=None) <= stage_time
            observations.append(
                S23LiveDecisionTimelineCheckpoint(
                    label=label,
                    bar_start=bar.bar_start.isoformat(),
                    bar_end=bar.bar_end.isoformat(),
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    included_in_stage=included,
                )
            )
        return tuple(observations)

    @staticmethod
    def _current_day_levels_so_far(
        checkpoint_observations: tuple[S23LiveDecisionTimelineCheckpoint, ...],
    ) -> tuple[float | None, float | None]:
        included = [item for item in checkpoint_observations if item.included_in_stage]
        highs = [float(item.high) for item in included if item.high is not None]
        lows = [float(item.low) for item in included if item.low is not None]
        return (
            max(highs) if highs else None,
            min(lows) if lows else None,
        )

    def _classify_monthly_status(
        self,
        *,
        reference_packet: S23DecisionReferencePacket,
        current_price: float | None,
        current_reference_timestamp: datetime,
        daily_bars: tuple[UnderlyingHistoryBar, ...],
    ) -> MonthlyStatusResolutionResult:
        levels = MonthlyStatusReferenceLevels(
            PMH=reference_packet.monthly_status_levels.PMH,
            PML=reference_packet.monthly_status_levels.PML,
            CMH=reference_packet.monthly_status_levels.CMH,
            CML=reference_packet.monthly_status_levels.CML,
            PWH=reference_packet.monthly_status_levels.PWH,
            PWL=reference_packet.monthly_status_levels.PWL,
            CWH=reference_packet.monthly_status_levels.CWH,
            CWL=reference_packet.monthly_status_levels.CWL,
            current_price=float(current_price or 0.0),
        )
        return self._monthly_status_lookback_resolver.resolve(
            reference_packet.instrument_group.strip().lower(),
            levels,
            current_reference_timestamp=current_reference_timestamp,
            lookback_windows=self._build_live_lookback_windows(
                daily_bars=daily_bars,
                current_reference_timestamp=current_reference_timestamp,
            ),
        )

    @staticmethod
    def _stage_monthly_status_price(
        checkpoint_observations: tuple[S23LiveDecisionTimelineCheckpoint, ...],
        *,
        fallback_price: float | None,
    ) -> float | None:
        included = [item for item in checkpoint_observations if item.included_in_stage]
        if included:
            latest = max(included, key=lambda item: item.bar_end)
            if latest.close is not None:
                return float(latest.close)
        return fallback_price

    @staticmethod
    def _stage_reference_timestamp(
        checkpoint_observations: tuple[S23LiveDecisionTimelineCheckpoint, ...],
        *,
        fallback_timestamp: datetime,
    ) -> datetime:
        included = [item for item in checkpoint_observations if item.included_in_stage]
        if included:
            latest = max(included, key=lambda item: item.bar_end)
            return datetime.fromisoformat(latest.bar_end)
        return fallback_timestamp

    def _build_live_lookback_windows(
        self,
        *,
        daily_bars: tuple[UnderlyingHistoryBar, ...],
        current_reference_timestamp: datetime,
    ) -> tuple[MonthlyStatusLookbackWindow, ...]:
        historical_bars = tuple(
            MonthlyStatusHistoricalBar(
                timestamp=bar.bar_end,
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
            )
            for bar in daily_bars
            if None not in (bar.high, bar.low, bar.close)
        )
        return build_monthly_weekly_context_lookback_windows(
            historical_bars=historical_bars,
            current_reference_timestamp=current_reference_timestamp,
        )

    @staticmethod
    def _stage_runtime_values(reference_packet: S23DecisionReferencePacket) -> dict[str, float]:
        runtime_values = {
            key.upper(): float(value)
            for key, value in reference_packet.option_reference_values.items()
        }
        for key, value in (reference_packet.runtime_value_overrides or {}).items():
            runtime_values[key.upper()] = float(value)
        return runtime_values

    @staticmethod
    def _stage_market_levels(
        *,
        reference_packet: S23DecisionReferencePacket,
        current_day_high_so_far: float | None,
        current_day_low_so_far: float | None,
    ) -> MarketLevels:
        return MarketLevels(
            d2hh=reference_packet.market_reference_levels.d2hh,
            d2ll=reference_packet.market_reference_levels.d2ll,
            d3hh=reference_packet.market_reference_levels.d3hh,
            d3ll=reference_packet.market_reference_levels.d3ll,
            d4hh=reference_packet.market_reference_levels.d4hh,
            d4ll=reference_packet.market_reference_levels.d4ll,
            current_day_high=current_day_high_so_far,
            current_day_low=current_day_low_so_far,
        )

    @staticmethod
    def _reference_values(
        *,
        reference_packet: S23DecisionReferencePacket,
        current_day_high_so_far: float | None,
        current_day_low_so_far: float | None,
    ) -> dict[str, dict[str, Any]]:
        return {
            "PRV_2DHH": {
                "value": reference_packet.market_reference_levels.d2hh,
                "source": "tfis_live_daily_history",
            },
            "PRV_2DLL": {
                "value": reference_packet.market_reference_levels.d2ll,
                "source": "tfis_live_daily_history",
            },
            "PRV_3DHH": {
                "value": reference_packet.market_reference_levels.d3hh,
                "source": "tfis_live_daily_history",
            },
            "PRV_3DLL": {
                "value": reference_packet.market_reference_levels.d3ll,
                "source": "tfis_live_daily_history",
            },
            "PRV_4DHH": {
                "value": reference_packet.market_reference_levels.d4hh,
                "source": "tfis_live_daily_history",
            },
            "PRV_4DLL": {
                "value": reference_packet.market_reference_levels.d4ll,
                "source": "tfis_live_daily_history",
            },
            "CDHH": {
                "value": current_day_high_so_far,
                "source": "derived_from_available_checkpoints",
            },
            "CDLL": {
                "value": current_day_low_so_far,
                "source": "derived_from_available_checkpoints",
            },
        }

    def _build_formula_explanations(
        self,
        *,
        strategy_rule: StrategyRule,
        market_levels: MarketLevels,
        runtime_values: dict[str, float],
    ) -> tuple[dict[str, Any], ...]:
        formula_engine = FormulaEngine()
        materialized_runtime_values = dict(runtime_values)
        needs_entry = any(
            "ENTRY" in _FORMULA_TOKEN_PATTERN.findall(formula.upper())
            for formula in (
                strategy_rule.target_formula,
                strategy_rule.stoploss_formula,
            )
        )
        if needs_entry and "ENTRY" not in materialized_runtime_values:
            materialized_runtime_values["ENTRY"] = formula_engine.evaluate(
                strategy_rule.entry_formula,
                market_levels=market_levels,
                runtime_values=materialized_runtime_values,
                parameters=strategy_rule.parameters,
            )
        return tuple(
            self._explain_formula(
                formula_engine=formula_engine,
                name=name,
                formula=formula,
                market_levels=market_levels,
                runtime_values=materialized_runtime_values,
                parameters=strategy_rule.parameters,
            )
            for name, formula in (
                ("start_strike", strategy_rule.start_strike_formula),
                ("end_strike", strategy_rule.end_strike_formula),
                ("ideal_premium", strategy_rule.ideal_premium_formula),
                ("minimum_premium", strategy_rule.minimum_premium_formula),
                ("entry", strategy_rule.entry_formula),
                ("target", strategy_rule.target_formula),
                ("stoploss", strategy_rule.stoploss_formula),
            )
        )

    def _explain_formula(
        self,
        *,
        formula_engine: FormulaEngine,
        name: str,
        formula: str,
        market_levels: MarketLevels,
        runtime_values: dict[str, float],
        parameters: dict[str, float],
    ) -> dict[str, Any]:
        return {
            "name": name,
            "formula": formula,
            "resolved_formula": self._resolve_formula_text(
                formula=formula,
                market_levels=market_levels,
                runtime_values=runtime_values,
                parameters=parameters,
            ),
            "result": formula_engine.evaluate(
                formula,
                market_levels=market_levels,
                runtime_values=runtime_values,
                parameters=parameters,
            ),
        }

    def _resolve_formula_text(
        self,
        *,
        formula: str,
        market_levels: MarketLevels,
        runtime_values: dict[str, float],
        parameters: dict[str, float],
    ) -> str:
        text = str(formula)
        text = re.sub(
            r"PARAM\(([A-Za-z_][A-Za-z0-9_]*)\)",
            lambda match: str(parameters.get(match.group(1), match.group(0))),
            text,
        )

        def replace_alias(match: re.Match[str]) -> str:
            token = match.group(0)
            upper = token.upper()
            if upper in {"MIN", "MAX", "ROUND_UP", "ROUND_DOWN", "PARAM"}:
                return token
            if upper == "ENTRY" and "ENTRY" in runtime_values:
                return str(runtime_values["ENTRY"])
            if upper in FormulaEngine.OPTION_ALIAS_NAMES and upper in runtime_values:
                return str(runtime_values[upper])
            field_name = FormulaEngine.ALIAS_TO_MARKET_LEVEL.get(upper)
            if field_name is not None:
                return str(getattr(market_levels, field_name))
            return token

        return re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\b", replace_alias, text)


__all__ = [
    "S23LiveDecisionTimelineBuilder",
    "S23LiveDecisionTimelineCheckpoint",
    "S23LiveDecisionTimelineResult",
    "S23LiveDecisionTimelineStage",
    "S23LiveDecisionTimelineStageBuild",
]
