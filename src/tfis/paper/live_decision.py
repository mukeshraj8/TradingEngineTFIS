from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
import re
from typing import Any

from tfis.domain import StrategyRule
from tfis.formulas import FormulaEngine

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
    explanation: dict[str, Any]

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
            "explanation": self.explanation,
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
        explanation = self._build_explanation(
            strategy_rule=strategy_rule,
            reference_packet=reference_packet,
            derived_inputs=derived_inputs,
            prelude_result=prelude_result,
            collected_inputs=collected_inputs,
            summary=summary,
        )
        return S23PaperLiveDecisionResult(
            derived_runtime_inputs=derived_inputs,
            prelude_result=prelude_result,
            summary=summary,
            explanation=explanation,
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
        explainer_json_path = target / "trade_decision_explainer.json"
        explainer_md_path = target / "trade_decision_explainer.md"
        json_path.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        md_path.write_text(self.render_markdown(result), encoding="utf-8")
        explainer_json_path.write_text(
            json.dumps(result.explanation, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        explainer_md_path.write_text(
            self.render_explainer_markdown(result),
            encoding="utf-8",
        )
        return json_path, md_path

    def render_explainer_markdown(self, result: S23PaperLiveDecisionResult) -> str:
        explanation = result.explanation
        lines = [
            "# S23 Trade Decision Explainer",
            "",
            "## Session",
            f"- Strategy: `{explanation['strategy_code']}` / `{explanation['strategy_branch']}`",
            f"- Session Date: `{explanation['session_date']}`",
            f"- Underlying Spot: `{explanation['underlying_spot_value']}`",
            "",
            "## Checkpoints",
        ]
        for checkpoint in explanation.get("checkpoints", ()):
            lines.append(
                f"- `{checkpoint['label']}`: open `{checkpoint['open']}`, high `{checkpoint['high']}`, "
                f"low `{checkpoint['low']}`, close `{checkpoint['close']}`"
            )
        lines.extend(
            [
                "",
                "## Monthly Status",
                f"- Current Price Used: `{explanation['monthly_status']['current_price']}`",
                f"- Trigger: `{explanation['monthly_status']['trigger_name']}`",
                f"- Result: `{explanation['monthly_status']['status']}`",
                f"- Notes: `{explanation['monthly_status']['notes']}`",
                "",
                "## Reference Levels",
            ]
        )
        for alias, payload in explanation.get("market_reference_values", {}).items():
            lines.append(f"- `{alias}` = `{payload['value']}` from `{payload['source']}`")
        lines.extend(
            [
                "",
                "## Derived Current-Day Levels",
                f"- `CDHH`: `{explanation['derived_current_day_levels']['CDHH']['formula']}` = `{explanation['derived_current_day_levels']['CDHH']['value']}`",
                f"- `CDLL`: `{explanation['derived_current_day_levels']['CDLL']['formula']}` = `{explanation['derived_current_day_levels']['CDLL']['value']}`",
                "",
                "## Option Reference Values",
            ]
        )
        for alias, payload in explanation.get("option_reference_values", {}).items():
            lines.append(f"- `{alias}` = `{payload['value']}` from `{payload['source']}`")
        lines.extend(["", "## Formula Evaluation"])
        for item in explanation.get("formula_evaluation", ()):
            lines.extend(
                [
                    f"- `{item['name']}`",
                    f"  Formula: `{item['formula']}`",
                    f"  Resolved: `{item['resolved_formula']}`",
                    f"  Result: `{item['result']}`",
                ]
            )
        lines.extend(["", "## Contract Selection"])
        request = explanation.get("contract_selection_request", {})
        thresholds = explanation.get("contract_selection_thresholds", {})
        if request:
            lines.append(
                f"- Range `{request['start_strike']}` to `{request['end_strike']}`, ideal premium `{request['ideal_premium']}`, "
                f"minimum premium `{request['minimum_premium']}`, minimum OI `{thresholds.get('minimum_oi')}`"
            )
        lines.append(
            f"- Selected: `{explanation['contract_selection']['selected_contract_symbol']}`"
        )
        lines.append(
            f"- Reason: `{explanation['contract_selection']['selection_reason']}`"
        )
        if explanation["contract_selection"].get("failure_code") is not None:
            lines.append(
                f"- Failure Code: `{explanation['contract_selection']['failure_code']}`"
            )
        lines.append("")
        lines.append("## Candidates")
        for candidate in explanation.get("contract_candidates", ()):
            reason_text = ", ".join(candidate.get("failure_reasons", ())) or "passed"
            lines.append(
                f"- `{candidate['symbol']}` strike `{candidate['strike']}` premium `{candidate['ltp']}` "
                f"OI `{candidate['oi']}` -> `{candidate['status']}` ({reason_text})"
            )
        return "\n".join(lines) + "\n"

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

    def _build_explanation(
        self,
        *,
        strategy_rule: StrategyRule,
        reference_packet: S23DecisionReferencePacket,
        derived_inputs: S23DerivedRuntimeInputs,
        prelude_result: S23PaperLivePreludeResult,
        collected_inputs: S23CollectedSnapshotInputs,
        summary: S23PaperTradeDecisionSummary,
    ) -> dict[str, Any]:
        formula_items = self._build_formula_explanations(
            strategy_rule=strategy_rule,
            derived_inputs=derived_inputs,
        )
        return {
            "strategy_code": strategy_rule.strategy_code,
            "strategy_branch": prelude_result.selected_branch,
            "session_date": prelude_result.calendar_context_event.envelope.session_date.isoformat(),
            "underlying_spot_value": collected_inputs.underlying_quote.ltp,
            "checkpoints": [
                {
                    "label": snapshot.snapshot_label.value,
                    "open": snapshot.open,
                    "high": snapshot.high,
                    "low": snapshot.low,
                    "close": snapshot.close,
                    "bar_start": snapshot.bar_start.isoformat(),
                    "bar_end": snapshot.bar_end.isoformat(),
                }
                for snapshot in derived_inputs.snapshots
            ],
            "monthly_status": {
                "current_price": collected_inputs.underlying_quote.ltp,
                "status": derived_inputs.monthly_status_result.status.value,
                "trigger_name": derived_inputs.monthly_status_result.trigger_name,
                "notes": derived_inputs.monthly_status_result.notes,
                "reference_levels": asdict(reference_packet.monthly_status_levels),
            },
            "market_reference_values": self._build_market_reference_values(
                reference_packet=reference_packet,
                derived_inputs=derived_inputs,
            ),
            "derived_current_day_levels": self._build_current_day_level_explanations(
                derived_inputs=derived_inputs,
            ),
            "option_reference_values": {
                alias: {
                    "value": value,
                    "source": "tfis_reference_packet",
                }
                for alias, value in sorted(derived_inputs.runtime_values.items())
                if alias in FormulaEngine.OPTION_ALIAS_NAMES or alias == "ENTRY"
            },
            "formula_evaluation": formula_items,
            "contract_selection_request": self._build_contract_selection_request(prelude_result),
            "contract_selection_thresholds": {
                "minimum_oi": strategy_rule.minimum_oi,
            },
            "contract_selection": {
                "selected_contract_symbol": summary.selected_contract_symbol,
                "selection_reason": summary.contract_selection_reason,
                "failure_code": summary.contract_selection_failure_code,
                "selected_contract_expiry": summary.selected_contract_expiry,
                "selected_contract_strike": summary.selected_contract_strike,
                "selected_contract_option_type": summary.selected_contract_option_type,
                "selected_contract_premium": summary.selected_contract_ltp,
                "selected_contract_oi": summary.selected_contract_oi,
                "rejected_candidate_counts": dict(summary.rejected_candidate_counts),
            },
            "contract_candidates": self._build_contract_candidate_explanations(
                strategy_rule=strategy_rule,
                prelude_result=prelude_result,
                option_chain_snapshot=collected_inputs.option_chain_snapshot,
                summary=summary,
            ),
            "trade_plan_outputs": {
                "entry_price": summary.planned_entry_price,
                "target_price": summary.target_price,
                "stoploss_price": summary.stoploss_price,
                "fsl_price": summary.fsl_price,
                "lots": summary.lots,
                "quantity": summary.quantity,
                "source_workbook_rule": summary.source_workbook_rule,
                "workbook_row_number": summary.workbook_row_number,
            },
        }

    def _build_market_reference_values(
        self,
        *,
        reference_packet: S23DecisionReferencePacket,
        derived_inputs: S23DerivedRuntimeInputs,
    ) -> dict[str, dict[str, Any]]:
        values: dict[str, dict[str, Any]] = {}
        for alias, field_name in sorted(FormulaEngine.ALIAS_TO_MARKET_LEVEL.items()):
            value = getattr(derived_inputs.market_levels, field_name)
            if value is None:
                continue
            source = (
                "derived_from_checkpoints"
                if alias in {"CDHH", "CDLL"}
                else "tfis_reference_packet"
            )
            values[alias] = {"value": value, "source": source}
        return values

    def _build_current_day_level_explanations(
        self,
        *,
        derived_inputs: S23DerivedRuntimeInputs,
    ) -> dict[str, dict[str, Any]]:
        high_terms = ", ".join(
            f"{snapshot.snapshot_label.value}.high={snapshot.high}"
            for snapshot in derived_inputs.snapshots
        )
        low_terms = ", ".join(
            f"{snapshot.snapshot_label.value}.low={snapshot.low}"
            for snapshot in derived_inputs.snapshots
        )
        return {
            "CDHH": {
                "formula": f"max({high_terms})",
                "value": derived_inputs.market_levels.current_day_high,
            },
            "CDLL": {
                "formula": f"min({low_terms})",
                "value": derived_inputs.market_levels.current_day_low,
            },
        }

    def _build_formula_explanations(
        self,
        *,
        strategy_rule: StrategyRule,
        derived_inputs: S23DerivedRuntimeInputs,
    ) -> tuple[dict[str, Any], ...]:
        return tuple(
            self._explain_formula(
                name=name,
                formula=formula,
                strategy_rule=strategy_rule,
                derived_inputs=derived_inputs,
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
        name: str,
        formula: str,
        strategy_rule: StrategyRule,
        derived_inputs: S23DerivedRuntimeInputs,
    ) -> dict[str, Any]:
        resolved_formula = self._resolve_formula_text(
            formula=formula,
            market_levels=derived_inputs.market_levels,
            runtime_values=derived_inputs.runtime_values,
            parameters=strategy_rule.parameters,
        )
        result = FormulaEngine().evaluate(
            formula,
            market_levels=derived_inputs.market_levels,
            runtime_values=derived_inputs.runtime_values,
            parameters=strategy_rule.parameters,
        )
        return {
            "name": name,
            "formula": formula,
            "resolved_formula": resolved_formula,
            "result": result,
        }

    def _resolve_formula_text(
        self,
        *,
        formula: str,
        market_levels: Any,
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
                value = getattr(market_levels, field_name)
                return str(value)
            return token

        return re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\b", replace_alias, text)

    def _build_contract_selection_request(
        self,
        prelude_result: S23PaperLivePreludeResult,
    ) -> dict[str, Any]:
        trade_plan = prelude_result.trade_plan
        if trade_plan is None:
            return {}
        return {
            "start_strike": trade_plan.start_strike,
            "end_strike": trade_plan.end_strike,
            "ideal_premium": trade_plan.ideal_premium,
            "minimum_premium": trade_plan.minimum_premium,
        }

    def _build_contract_candidate_explanations(
        self,
        *,
        strategy_rule: StrategyRule,
        prelude_result: S23PaperLivePreludeResult,
        option_chain_snapshot: Any,
        summary: S23PaperTradeDecisionSummary,
    ) -> tuple[dict[str, Any], ...]:
        if prelude_result.trade_plan is None or prelude_result.contract_selection is None:
            return ()
        request_lower = min(
            float(prelude_result.trade_plan.start_strike or 0.0),
            float(prelude_result.trade_plan.end_strike or 0.0),
        )
        request_upper = max(
            float(prelude_result.trade_plan.start_strike or 0.0),
            float(prelude_result.trade_plan.end_strike or 0.0),
        )
        ideal_premium = float(prelude_result.trade_plan.ideal_premium or 0.0)
        minimum_premium = float(prelude_result.trade_plan.minimum_premium or 0.0)
        minimum_oi = float(strategy_rule.minimum_oi)
        if prelude_result.contract_selection.selected_contract is not None:
            selected_expiry = prelude_result.contract_selection.selected_contract.expiry
        else:
            selected_expiry = None
        items: list[dict[str, Any]] = []
        for contract in option_chain_snapshot.contracts:
            reasons: list[str] = []
            if contract.expiry != selected_expiry:
                reasons.append("expiry_mismatch")
            if contract.option_type is not strategy_rule.option_type:
                reasons.append("option_type_mismatch")
            if contract.strike is None or not (request_lower <= contract.strike <= request_upper):
                reasons.append("strike_out_of_range")
            if contract.ltp is None:
                reasons.append("missing_premium")
            elif contract.ltp < minimum_premium:
                reasons.append("minimum_premium_not_met")
            if contract.oi is None:
                reasons.append("missing_oi")
            elif contract.oi < minimum_oi:
                reasons.append("minimum_oi_not_met")
            status = "PASSED" if not reasons else "REJECTED"
            items.append(
                {
                    "symbol": contract.symbol,
                    "strike": contract.strike,
                    "option_type": contract.option_type.value,
                    "expiry": contract.expiry.isoformat(),
                    "ltp": contract.ltp,
                    "oi": contract.oi,
                    "premium_distance_to_ideal": (
                        abs(float(contract.ltp) - ideal_premium) if contract.ltp is not None else None
                    ),
                    "status": "SELECTED" if contract.symbol == summary.selected_contract_symbol else status,
                    "failure_reasons": tuple(reasons),
                }
            )
        return tuple(items)
