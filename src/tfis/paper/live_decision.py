from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from tfis.domain import StrategyRule

from .fyers_snapshot_collector import S23CollectedSnapshotInputs
from .live_prelude import (
    S23PaperLivePreludeBuilder,
    S23PaperLivePreludeRequest,
    S23PaperLivePreludeResult,
    S23PaperPreludeMode,
)
from .position_state import S23PaperPositionState
from .runtime_input_derivation import (
    S23DecisionReferencePacket,
    S23DerivedRuntimeInputs,
    S23RuntimeInputDeriver,
)


class S23PaperLiveDecisionError(RuntimeError):
    """Raised when TFIS cannot build a supervised S23 paper decision safely."""


@dataclass(frozen=True, slots=True)
class S23PaperTradeDecisionSummary:
    status: str
    session_date: date
    mode: str
    strategy_code: str
    strategy_branch: str
    monthly_status: str
    monthly_status_trigger: str
    monthly_status_notes: str
    required_market_aliases: tuple[str, ...]
    required_option_aliases: tuple[str, ...]
    checkpoint_labels: tuple[str, ...]
    market_levels: dict[str, float | None]
    runtime_values: dict[str, float]
    lots: int
    quantity: int
    selected_contract_symbol: str | None
    selected_contract_expiry: str | None
    selected_contract_strike: float | None
    selected_contract_option_type: str | None
    selected_contract_ltp: float | None
    selected_contract_oi: float | None
    contract_selection_reason: str | None
    contract_selection_failure_code: str | None
    rejected_candidate_counts: dict[str, int]
    ranked_candidates: tuple[dict[str, Any], ...]
    planned_entry_price: float | None
    target_price: float | None
    stoploss_price: float | None
    fsl_price: float | None
    source_workbook_rule: str | None
    workbook_row_number: int | None
    governance_event_types: tuple[str, ...] = ()
    resume_event_type: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class S23PaperLiveDecisionResult:
    derived_runtime_inputs: S23DerivedRuntimeInputs
    prelude_result: S23PaperLivePreludeResult
    summary: S23PaperTradeDecisionSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "derived_runtime_inputs": {
                "monthly_status_result": {
                    "status": self.derived_runtime_inputs.monthly_status_result.status.value,
                    "trigger_name": self.derived_runtime_inputs.monthly_status_result.trigger_name,
                    "threshold_value": self.derived_runtime_inputs.monthly_status_result.threshold_value,
                    "reversal_dominated": self.derived_runtime_inputs.monthly_status_result.reversal_dominated,
                    "notes": self.derived_runtime_inputs.monthly_status_result.notes,
                },
                "market_levels": asdict(self.derived_runtime_inputs.market_levels),
                "runtime_values": dict(self.derived_runtime_inputs.runtime_values),
                "checkpoint_labels": list(self.derived_runtime_inputs.checkpoint_labels),
            },
            "summary": asdict(self.summary),
        }


class S23PaperLiveDecisionBuilder:
    def __init__(
        self,
        *,
        runtime_input_deriver: S23RuntimeInputDeriver | None = None,
        prelude_builder: S23PaperLivePreludeBuilder | None = None,
    ) -> None:
        self._runtime_input_deriver = runtime_input_deriver or S23RuntimeInputDeriver()
        self._prelude_builder = prelude_builder or S23PaperLivePreludeBuilder()

    def build(
        self,
        *,
        strategy_rule: StrategyRule,
        reference_packet: S23DecisionReferencePacket,
        collected_inputs: S23CollectedSnapshotInputs,
        carry_forward_position: S23PaperPositionState | None = None,
        smoke_override_enabled: bool = False,
        smoke_override_selected_contract_symbol: str | None = None,
    ) -> S23PaperLiveDecisionResult:
        derived_inputs = self._runtime_input_deriver.derive(
            strategy_rule=strategy_rule,
            reference_packet=reference_packet,
            underlying_quote=collected_inputs.underlying_quote,
            underlying_bars=collected_inputs.underlying_bars,
            session_context=collected_inputs.session_context,
        )
        prelude_result = self._prelude_builder.build(
            S23PaperLivePreludeRequest(
                strategy_rule=strategy_rule,
                strategy_branch=reference_packet.strategy_branch or strategy_rule.unique_code,
                monthly_status_result=derived_inputs.monthly_status_result,
                market_levels=derived_inputs.market_levels,
                runtime_values=derived_inputs.runtime_values,
                option_chain_snapshot=collected_inputs.option_chain_snapshot,
                snapshots=derived_inputs.snapshots,
                session_context=collected_inputs.session_context,
                expiry_governance=collected_inputs.expiry_governance,
                lots=reference_packet.lots,
                quantity=reference_packet.quantity,
                monthly_status_reference_date=reference_packet.monthly_status_reference_date,
                monthly_status_source=reference_packet.monthly_status_source,
                monthly_status_threshold_version=reference_packet.monthly_status_threshold_version,
                source_workbook_rule=reference_packet.source_workbook_rule,
                workbook_row_number=reference_packet.workbook_row_number,
                fsl_price=reference_packet.fsl_price,
                carry_forward_position=carry_forward_position,
                smoke_override_enabled=smoke_override_enabled,
                smoke_override_selected_contract_symbol=smoke_override_selected_contract_symbol,
            )
        )
        summary = self._build_summary(
            strategy_rule=strategy_rule,
            reference_packet=reference_packet,
            derived_inputs=derived_inputs,
            prelude_result=prelude_result,
        )
        return S23PaperLiveDecisionResult(
            derived_runtime_inputs=derived_inputs,
            prelude_result=prelude_result,
            summary=summary,
        )

    def render_markdown(self, result: S23PaperLiveDecisionResult) -> str:
        summary = result.summary
        lines = [
            "# S23 Paper Live Decision Summary",
            "",
            "## Status",
            f"- Status: `{summary.status}`",
            f"- Session Date: `{summary.session_date.isoformat()}`",
            f"- Mode: `{summary.mode}`",
            f"- Strategy: `{summary.strategy_code}` / `{summary.strategy_branch}`",
            f"- Monthly Status: `{summary.monthly_status}` via `{summary.monthly_status_trigger}`",
        ]
        if summary.selected_contract_symbol:
            lines.extend(
                [
                    "",
                    "## Contract",
                    f"- Symbol: `{summary.selected_contract_symbol}`",
                    f"- Expiry: `{summary.selected_contract_expiry}`",
                    f"- Strike: `{summary.selected_contract_strike}`",
                    f"- Option Type: `{summary.selected_contract_option_type}`",
                    f"- Premium: `{summary.selected_contract_ltp}`",
                    f"- OI: `{summary.selected_contract_oi}`",
                    f"- Selection Reason: `{summary.contract_selection_reason}`",
                ]
            )
        lines.extend(
            [
                "",
                "## Trade Plan",
                f"- Entry: `{summary.planned_entry_price}`",
                f"- Target: `{summary.target_price}`",
                f"- Stoploss: `{summary.stoploss_price}`",
                f"- FSL: `{summary.fsl_price}`",
                f"- Lots / Quantity: `{summary.lots}` / `{summary.quantity}`",
                f"- Workbook Rule: `{summary.source_workbook_rule or 'n/a'}` row `{summary.workbook_row_number}`",
                "",
                "## Inputs",
                f"- Required Market Aliases: `{', '.join(summary.required_market_aliases) or 'none'}`",
                f"- Required Option Aliases: `{', '.join(summary.required_option_aliases) or 'none'}`",
                f"- Checkpoints: `{', '.join(summary.checkpoint_labels)}`",
            ]
        )
        if summary.governance_event_types:
            lines.extend(
                [
                    "",
                    "## Carry-Forward Governance",
                    f"- Resume Event: `{summary.resume_event_type}`",
                    f"- Governance Events: `{', '.join(summary.governance_event_types)}`",
                ]
            )
        if summary.notes:
            lines.extend(["", "## Notes", *[f"- {note}" for note in summary.notes]])
        return "\n".join(lines) + "\n"

    def write_artifacts(
        self,
        result: S23PaperLiveDecisionResult,
        *,
        output_dir: str | Path,
    ) -> tuple[Path, Path]:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        json_path = target / "trade_decision_summary.json"
        md_path = target / "trade_decision_summary.md"
        json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        md_path.write_text(self.render_markdown(result), encoding="utf-8")
        return json_path, md_path

    def _build_summary(
        self,
        *,
        strategy_rule: StrategyRule,
        reference_packet: S23DecisionReferencePacket,
        derived_inputs: S23DerivedRuntimeInputs,
        prelude_result: S23PaperLivePreludeResult,
    ) -> S23PaperTradeDecisionSummary:
        contract_selection = prelude_result.contract_selection
        selected_contract = prelude_result.selected_contract_event
        ranked_candidates = (
            (
                {
                    "symbol": contract_selection.selected_contract.symbol,
                    "premium_distance": contract_selection.ranking.premium_distance,
                    "oi": contract_selection.ranking.oi_used,
                    "strike": contract_selection.ranking.tie_break_strike,
                    "premium": contract_selection.premium_used,
                    "rank_position": 1,
                },
            )
            if contract_selection is not None
            and contract_selection.selected_contract is not None
            and contract_selection.ranking is not None
            else ()
        )
        notes: list[str] = []
        if prelude_result.mode is S23PaperPreludeMode.CARRY_FORWARD_RESUME:
            notes.append("Fresh entry planning was skipped because an open carry-forward position exists.")
        if prelude_result.contract_selection is not None and prelude_result.contract_selection.failure_code is not None:
            notes.append("Contract selection failed closed.")
        return S23PaperTradeDecisionSummary(
            status="READY" if selected_contract is not None or prelude_result.mode is S23PaperPreludeMode.CARRY_FORWARD_RESUME else "NO_GO",
            session_date=prelude_result.calendar_context_event.envelope.session_date,
            mode=prelude_result.mode.value,
            strategy_code=strategy_rule.strategy_code,
            strategy_branch=prelude_result.selected_branch,
            monthly_status=derived_inputs.monthly_status_result.status.value,
            monthly_status_trigger=derived_inputs.monthly_status_result.trigger_name,
            monthly_status_notes=derived_inputs.monthly_status_result.notes,
            required_market_aliases=derived_inputs.required_market_aliases,
            required_option_aliases=derived_inputs.required_option_aliases,
            checkpoint_labels=derived_inputs.checkpoint_labels,
            market_levels=asdict(derived_inputs.market_levels),
            runtime_values=dict(derived_inputs.runtime_values),
            lots=reference_packet.lots,
            quantity=reference_packet.quantity,
            selected_contract_symbol=selected_contract.symbol if selected_contract is not None else None,
            selected_contract_expiry=selected_contract.expiry.isoformat() if selected_contract and selected_contract.expiry else None,
            selected_contract_strike=selected_contract.strike if selected_contract is not None else None,
            selected_contract_option_type=selected_contract.option_type.value if selected_contract and selected_contract.option_type else None,
            selected_contract_ltp=selected_contract.ltp if selected_contract is not None else None,
            selected_contract_oi=selected_contract.oi if selected_contract is not None else None,
            contract_selection_reason=contract_selection.selection_reason if contract_selection is not None else None,
            contract_selection_failure_code=(
                contract_selection.failure_code.value
                if contract_selection is not None and contract_selection.failure_code is not None
                else None
            ),
            rejected_candidate_counts=(
                dict(contract_selection.rejected_candidate_counts)
                if contract_selection is not None
                else {}
            ),
            ranked_candidates=ranked_candidates,
            planned_entry_price=prelude_result.trade_plan.entry_price if prelude_result.trade_plan is not None else None,
            target_price=prelude_result.trade_plan.target_price if prelude_result.trade_plan is not None else None,
            stoploss_price=prelude_result.trade_plan.stoploss_price if prelude_result.trade_plan is not None else None,
            fsl_price=reference_packet.fsl_price,
            source_workbook_rule=reference_packet.source_workbook_rule,
            workbook_row_number=reference_packet.workbook_row_number,
            governance_event_types=tuple(item.event_type.value for item in prelude_result.governance_events),
            resume_event_type=(
                prelude_result.resume_event.event_type.value
                if prelude_result.resume_event is not None
                else None
            ),
            notes=tuple(notes),
        )
