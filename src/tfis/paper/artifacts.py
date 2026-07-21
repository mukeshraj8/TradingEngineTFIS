from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from .models import PaperSessionManifest
from .orchestrator import S23PaperSessionSnapshot as PaperSessionSnapshot


@dataclass(frozen=True, slots=True)
class S23PaperArtifactSet:
    artifact_root: Path
    session_directory: Path
    session_id: str
    session_manifest_path: Path
    audit_events_path: Path
    decision_summary_path: Path
    selected_contract_path: Path | None
    paper_order_plan_path: Path | None
    no_trade_summary_path: Path | None
    abort_summary_path: Path | None


class S23PaperSessionArtifactWriter:
    def __init__(self, artifact_root: str | Path = Path("tmp/paper_sessions")) -> None:
        self._artifact_root = Path(artifact_root)

    @property
    def artifact_root(self) -> Path:
        return self._artifact_root

    def write_snapshot(
        self,
        snapshot: PaperSessionSnapshot,
        *,
        session_id: str | None = None,
    ) -> S23PaperArtifactSet:
        if snapshot.manifest is None:
            raise ValueError(
                "S23 paper session artifacts require a session manifest before persistence."
            )

        resolved_session_id = session_id or self._derive_session_id(snapshot.manifest)
        session_directory = (
            self._artifact_root
            / snapshot.manifest.session_date.isoformat()
            / resolved_session_id
        )
        session_directory.mkdir(parents=True, exist_ok=True)

        manifest_path = session_directory / "session_manifest.json"
        audit_path = session_directory / "audit_events.jsonl"
        decision_summary_path = session_directory / "decision_summary.json"

        self._write_json(manifest_path, snapshot.manifest)
        self._write_jsonl(audit_path, snapshot.audit_events)
        self._write_json(
            decision_summary_path,
            self._build_decision_summary(snapshot, resolved_session_id),
        )

        selected_contract_path: Path | None = None
        if snapshot.selected_contract_quote is not None:
            selected_contract_path = session_directory / "selected_contract.json"
            self._write_json(selected_contract_path, snapshot.selected_contract_quote)

        paper_order_plan_path: Path | None = None
        no_trade_summary_path: Path | None = None
        abort_summary_path: Path | None = None

        if snapshot.state.value == "ORDER_PLANNED" and snapshot.order_plan is not None:
            paper_order_plan_path = session_directory / "paper_order_plan.json"
            self._write_json(
                paper_order_plan_path,
                self._build_order_plan_summary(snapshot, resolved_session_id),
            )
        elif snapshot.state.value == "NO_TRADE":
            no_trade_summary_path = session_directory / "no_trade_summary.json"
            self._write_json(
                no_trade_summary_path,
                self._build_terminal_summary(snapshot, resolved_session_id, "NO_TRADE"),
            )
        elif snapshot.state.value == "ABORTED":
            abort_summary_path = session_directory / "abort_summary.json"
            self._write_json(
                abort_summary_path,
                self._build_terminal_summary(snapshot, resolved_session_id, "ABORTED"),
            )

        return S23PaperArtifactSet(
            artifact_root=self._artifact_root,
            session_directory=session_directory,
            session_id=resolved_session_id,
            session_manifest_path=manifest_path,
            audit_events_path=audit_path,
            decision_summary_path=decision_summary_path,
            selected_contract_path=selected_contract_path,
            paper_order_plan_path=paper_order_plan_path,
            no_trade_summary_path=no_trade_summary_path,
            abort_summary_path=abort_summary_path,
        )

    def _derive_session_id(self, manifest: PaperSessionManifest) -> str:
        return (
            f"{manifest.strategy_code.lower()}-"
            f"{manifest.symbol.lower()}-"
            f"{manifest.contract_cycle.lower()}-"
            f"{manifest.mode.lower()}-"
            f"{manifest.session_date.isoformat()}"
        )

    def _build_decision_summary(
        self,
        snapshot: PaperSessionSnapshot,
        session_id: str,
    ) -> dict[str, Any]:
        manifest = snapshot.manifest
        assert manifest is not None
        validation = snapshot.latest_validation_result
        return {
            "artifact_version": 1,
            "session_id": session_id,
            "session_date": manifest.session_date,
            "state": snapshot.state,
            "readiness_status": manifest.readiness_status,
            "evaluated_state": manifest.evaluated_state,
            "strategy_code": manifest.strategy_code,
            "symbol": manifest.symbol,
            "contract_cycle": manifest.contract_cycle,
            "mode": manifest.mode,
            "selected_contract_available": snapshot.selected_contract_quote is not None,
            "selected_contract_symbol": (
                snapshot.selected_contract_quote.symbol
                if snapshot.selected_contract_quote is not None
                else None
            ),
            "paper_order_planned": snapshot.order_plan is not None,
            "required_snapshot_labels": (
                validation.required_snapshot_labels if validation is not None else ()
            ),
            "missing_snapshot_labels": (
                validation.missing_snapshot_labels if validation is not None else ()
            ),
            "overlays_enabled": manifest.overlays_enabled,
            "synthetic_fixture_used": manifest.synthetic_fixture_used,
            "warning_flags": manifest.warnings,
            "no_trade_reasons": manifest.no_trade_reasons,
            "abort_reasons": manifest.abort_reasons,
            "terminal_reason_code": self._terminal_reason_code(snapshot),
            "data_sources": manifest.data_sources,
            **self._guardrail_fields(snapshot),
        }

    def _build_order_plan_summary(
        self,
        snapshot: PaperSessionSnapshot,
        session_id: str,
    ) -> dict[str, Any]:
        assert snapshot.order_plan is not None
        return {
            "artifact_version": 1,
            "session_id": session_id,
            "state": snapshot.state,
            "selected_contract_symbol": snapshot.order_plan.selected_contract_symbol,
            "selected_contract_quote_present": snapshot.selected_contract_quote is not None,
            "order_plan": snapshot.order_plan,
            "execution_started": False,
            "fill_simulation_started": False,
            **self._guardrail_fields(snapshot),
        }

    def _build_terminal_summary(
        self,
        snapshot: PaperSessionSnapshot,
        session_id: str,
        terminal_state: str,
    ) -> dict[str, Any]:
        manifest = snapshot.manifest
        assert manifest is not None
        return {
            "artifact_version": 1,
            "session_id": session_id,
            "session_date": manifest.session_date,
            "state": snapshot.state,
            "terminal_state": terminal_state,
            "terminal_reason_code": self._terminal_reason_code(snapshot),
            "no_trade_reasons": manifest.no_trade_reasons,
            "abort_reasons": manifest.abort_reasons,
            "warnings": manifest.warnings,
            "selected_contract_symbol": (
                snapshot.selected_contract_quote.symbol
                if snapshot.selected_contract_quote is not None
                else None
            ),
            "selected_contract_quote_present": snapshot.selected_contract_quote is not None,
            "execution_started": False,
            "fill_simulation_started": False,
            "provenance_sources": manifest.data_sources,
            **self._guardrail_fields(snapshot),
        }

    def _guardrail_fields(self, snapshot: PaperSessionSnapshot) -> dict[str, Any]:
        decision = snapshot.latest_guardrail_decision
        if decision is None:
            return {
                "guardrail_code": None,
                "guardrail_message": None,
                "blocking_event_type": None,
                "blocking_source_id": None,
                "operator_action_required": None,
            }
        return {
            "guardrail_code": decision.code,
            "guardrail_message": decision.message,
            "blocking_event_type": decision.blocking_event_type,
            "blocking_source_id": decision.blocking_source_id,
            "operator_action_required": decision.operator_action_required,
        }

    def _terminal_reason_code(self, snapshot: PaperSessionSnapshot) -> str | None:
        validation = snapshot.latest_validation_result
        if validation is not None:
            if validation.abort_reasons:
                return validation.abort_reasons[0]
            if validation.no_trade_reasons:
                return validation.no_trade_reasons[0]
        for entry in reversed(snapshot.audit_events):
            if entry.terminal_code is not None:
                return entry.terminal_code
        return None

    def _write_json(self, path: Path, payload: Any) -> None:
        rendered = json.dumps(
            self._normalize(payload),
            indent=2,
            sort_keys=True,
        ) + "\n"
        self._atomic_write_text(path, rendered)

    def _write_jsonl(self, path: Path, rows: tuple[Any, ...]) -> None:
        rendered = "".join(
            json.dumps(self._normalize(row), sort_keys=True) + "\n"
            for row in rows
        )
        self._atomic_write_text(path, rendered)

    def _atomic_write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.parent / f".{path.name}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _normalize(self, value: Any) -> Any:
        if is_dataclass(value):
            return {
                field.name: self._normalize(getattr(value, field.name))
                for field in fields(value)
            }
        if isinstance(value, dict):
            return {
                str(key): self._normalize(value[key])
                for key in sorted(value, key=lambda item: str(item))
            }
        if isinstance(value, tuple | list):
            return [self._normalize(item) for item in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date | time):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value
