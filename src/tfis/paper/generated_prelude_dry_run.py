from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from tfis.domain import MarketLevels
from tfis.domain.enums import MonthlyStatus
from tfis.importers import load_strategy_rule
from tfis.monthly_status import MonthlyStatusResult
from tfis.storage import atomic_write_text

from .ingress_dry_run import (
    PaperEvent,
    PaperNormalizedEventLoader,
    PaperIngressDryRunArtifactSet,
    PaperIngressDryRunRunner,
)
from .live_ingress import PaperLiveIngressConfig
from .live_prelude import (
    PaperLivePreludeBuilder,
    PaperLivePreludeError,
    PaperLivePreludeRequest,
    PaperPreludeMode,
    PaperPreludeSessionContext,
    PaperSnapshotInput,
)
from .models import (
    OptionChainSnapshotEvent,
    PaperEventType,
    SelectedContractQuoteEvent,
    SnapshotLabel,
    UnderlyingQuoteEvent,
)
from .position_state import PaperPositionStateStore
from .review import PaperSessionReviewer
from .expiry_governance import DeterministicExpiryCalendar, PaperExpiryGovernance


class S23GeneratedPreludeDryRunError(RuntimeError):
    """Raised when generated-prelude dry runs cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class S23GeneratedPreludeDryRunProvenance:
    prelude_source: str
    contract_selection_source: str | None
    carry_forward_state_source: str | None
    strategy_path: str
    ingress_config_path: str
    runtime_fixture_path: str
    market_events_path: str
    generated_mode: str
    smoke_override_enabled: bool


@dataclass(frozen=True, slots=True)
class S23GeneratedPreludeDryRunArtifactSet:
    ingress_artifacts: PaperIngressDryRunArtifactSet
    generated_prelude_events_path: Path
    combined_events_path: Path
    provenance_path: Path
    governance_events_path: Path | None
    provenance: S23GeneratedPreludeDryRunProvenance


PaperGeneratedPreludeDryRunError = S23GeneratedPreludeDryRunError
PaperGeneratedPreludeDryRunProvenance = S23GeneratedPreludeDryRunProvenance
PaperGeneratedPreludeDryRunArtifactSet = S23GeneratedPreludeDryRunArtifactSet


class S23GeneratedPreludeDryRunRunner:
    def __init__(
        self,
        *,
        dry_run_runner: PaperIngressDryRunRunner | None = None,
        prelude_builder: PaperLivePreludeBuilder | None = None,
        reviewer: PaperSessionReviewer | None = None,
        position_state_store: PaperPositionStateStore | None = None,
    ) -> None:
        self._dry_run_runner = dry_run_runner or PaperIngressDryRunRunner(
            source_mode="generated_live_prelude_dry_run"
        )
        self._prelude_builder = prelude_builder or PaperLivePreludeBuilder()
        self._reviewer = reviewer or PaperSessionReviewer()
        self._position_state_store = position_state_store or PaperPositionStateStore()

    def run_from_files(
        self,
        *,
        strategy_path: str | Path,
        ingress_config_path: str | Path,
        runtime_fixture_path: str | Path,
        market_events_jsonl: str | Path,
        carry_forward_state_dir: str | Path | None = None,
        session_id: str | None = None,
        enable_smoke_override: bool = False,
    ) -> S23GeneratedPreludeDryRunArtifactSet:
        strategy = load_strategy_rule(strategy_path)
        config = PaperLiveIngressConfig.from_yaml(ingress_config_path)
        runtime_fixture = self._load_runtime_fixture(runtime_fixture_path)
        market_events = PaperNormalizedEventLoader().load_jsonl(market_events_jsonl)

        session_context = self._build_session_context(runtime_fixture)
        option_chain_snapshot = self._select_option_chain_snapshot(
            market_events,
            session_date=session_context.session_date,
        )
        carry_forward_state = (
            self._position_state_store.load_state(carry_forward_state_dir)
            if carry_forward_state_dir is not None
            else None
        )

        try:
            prelude_result = self._prelude_builder.build(
                PaperLivePreludeRequest(
                    strategy_rule=strategy,
                    strategy_branch=str(runtime_fixture["strategy_branch"]),
                    monthly_status_result=self._build_monthly_status_result(
                        runtime_fixture["monthly_status_result"]
                    ),
                    market_levels=self._build_market_levels(runtime_fixture["market_levels"]),
                    runtime_values=dict(runtime_fixture.get("runtime_values", {})),
                    option_chain_snapshot=option_chain_snapshot,
                    snapshots=self._build_snapshots(runtime_fixture["snapshots"]),
                    session_context=session_context,
                    expiry_governance=self._build_expiry_governance(runtime_fixture),
                    lots=int(runtime_fixture["lots"]),
                    quantity=int(runtime_fixture["quantity"]),
                    monthly_status_reference_date=self._optional_date(
                        runtime_fixture.get("monthly_status_reference_date")
                    ),
                    monthly_status_source=str(
                        runtime_fixture.get("monthly_status_source", "monthly_status_engine")
                    ),
                    monthly_status_threshold_version=str(
                        runtime_fixture.get("monthly_status_threshold_version", "v1")
                    ),
                    source_workbook_rule=self._optional_text(
                        runtime_fixture.get("source_workbook_rule")
                    ),
                    workbook_row_number=self._optional_int(
                        runtime_fixture.get("workbook_row_number")
                    ),
                    fsl_price=self._optional_float(runtime_fixture.get("fsl_price")),
                    carry_forward_position=carry_forward_state,
                    smoke_override_enabled=enable_smoke_override,
                    smoke_override_selected_contract_symbol=(
                        config.market.selected_contract_symbol if enable_smoke_override else None
                    ),
                )
            )
        except PaperLivePreludeError as exc:
            raise S23GeneratedPreludeDryRunError(str(exc)) from exc

        generated_events = self._build_generated_event_stream(
            config=config,
            prelude_result=prelude_result,
            session_context=session_context,
        )
        combined_events = self._combine_events(
            generated_events=generated_events,
            market_events=market_events,
            session_date=session_context.session_date,
            mode=prelude_result.mode,
        )

        artifact_set = self._dry_run_runner.run_events(
            combined_events,
            source_path=runtime_fixture_path,
            session_id=session_id,
        )
        session_directory = artifact_set.session_directory
        generated_prelude_events_path = session_directory / "generated_live_prelude_events.jsonl"
        combined_events_path = session_directory / "generated_live_prelude_combined_events.jsonl"
        provenance_path = session_directory / "generated_live_prelude_provenance.json"
        governance_events_path = (
            session_directory / "generated_live_prelude_governance_events.jsonl"
            if prelude_result.resume_event is not None or prelude_result.governance_events
            else None
        )

        self._write_paper_events(generated_prelude_events_path, generated_events)
        self._write_paper_events(combined_events_path, combined_events)
        provenance = S23GeneratedPreludeDryRunProvenance(
            prelude_source="generated_live_prelude",
            contract_selection_source=(
                "explicit_smoke_override"
                if prelude_result.selected_contract_provenance == "smoke_override"
                else "runtime_option_chain_selector"
                if prelude_result.selected_contract_provenance == "runtime_option_chain_selection"
                else None
            ),
            carry_forward_state_source=(
                str(Path(carry_forward_state_dir)) if carry_forward_state_dir is not None else None
            ),
            strategy_path=str(Path(strategy_path)),
            ingress_config_path=str(Path(ingress_config_path)),
            runtime_fixture_path=str(Path(runtime_fixture_path)),
            market_events_path=str(Path(market_events_jsonl)),
            generated_mode=prelude_result.mode.value,
            smoke_override_enabled=enable_smoke_override,
        )
        self._write_json(provenance_path, provenance)
        if governance_events_path is not None:
            governance_rows = tuple(
                item
                for item in (
                    *(prelude_result.governance_events),
                    prelude_result.resume_event,
                )
                if item is not None
            )
            self._write_jsonl(governance_events_path, governance_rows)

        return S23GeneratedPreludeDryRunArtifactSet(
            ingress_artifacts=artifact_set,
            generated_prelude_events_path=generated_prelude_events_path,
            combined_events_path=combined_events_path,
            provenance_path=provenance_path,
            governance_events_path=governance_events_path,
            provenance=provenance,
        )

    def render_json(self, artifact_set: S23GeneratedPreludeDryRunArtifactSet) -> str:
        return self._dry_run_runner.render_json(artifact_set.ingress_artifacts.summary)

    def render_markdown(self, artifact_set: S23GeneratedPreludeDryRunArtifactSet) -> str:
        return self._dry_run_runner.render_markdown(artifact_set.ingress_artifacts.summary)

    def _build_generated_event_stream(
        self,
        *,
        config: PaperLiveIngressConfig,
        prelude_result: Any,
        session_context: PaperPreludeSessionContext,
    ) -> tuple[PaperEvent, ...]:
        config_event = config.build_paper_session_config_event(
            session_date=session_context.session_date,
            source_id=f"{session_context.source_id_prefix}:paper-config",
            timezone=session_context.timezone,
        )
        cost_event = config.build_cost_settings_event(
            session_date=session_context.session_date,
            source_id=f"{session_context.source_id_prefix}:cost-settings",
            timezone=session_context.timezone,
        )
        events: list[PaperEvent] = [
            prelude_result.calendar_context_event,
            prelude_result.monthly_status_event,
            config_event,
            cost_event,
            *prelude_result.snapshot_events,
        ]
        if prelude_result.trade_plan_event is not None:
            events.append(prelude_result.trade_plan_event)
        if prelude_result.selected_contract_event is not None:
            events.append(prelude_result.selected_contract_event)
        return tuple(events)

    def _combine_events(
        self,
        *,
        generated_events: tuple[PaperEvent, ...],
        market_events: tuple[PaperEvent, ...],
        session_date: date,
        mode: PaperPreludeMode,
    ) -> tuple[PaperEvent, ...]:
        filtered_market_events: list[PaperEvent] = []
        for event in market_events:
            if event.envelope.session_date != session_date:
                continue
            if event.envelope.event_type is PaperEventType.UNDERLYING_QUOTE:
                filtered_market_events.append(event)
            elif event.envelope.event_type is PaperEventType.OPTION_CHAIN_SNAPSHOT:
                filtered_market_events.append(event)

        generated_selected = [
            event
            for event in generated_events
            if isinstance(event, SelectedContractQuoteEvent)
        ]
        ordered = [
            event
            for event in generated_events
            if not isinstance(event, SelectedContractQuoteEvent)
        ]
        ordered.extend(
            event for event in filtered_market_events if event.envelope.event_type is PaperEventType.UNDERLYING_QUOTE
        )
        ordered.extend(
            event for event in filtered_market_events if event.envelope.event_type is PaperEventType.OPTION_CHAIN_SNAPSHOT
        )
        if mode is PaperPreludeMode.FRESH_ENTRY:
            ordered.extend(generated_selected)
        return tuple(ordered)

    def _load_runtime_fixture(self, path: str | Path) -> dict[str, Any]:
        target = Path(path)
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise S23GeneratedPreludeDryRunError(
                f"Runtime fixture must be a JSON object: {target}"
            )
        return data

    def _build_session_context(
        self,
        payload: dict[str, Any],
    ) -> PaperPreludeSessionContext:
        session_date = self._parse_date(payload["session_date"])
        generated_at = self._parse_datetime(payload["generated_at"])
        return PaperPreludeSessionContext(
            session_date=session_date,
            timezone=str(payload["timezone"]),
            generated_at=generated_at,
            market_open=self._optional_time(payload.get("market_open")) or time(9, 15),
            market_close=self._optional_time(payload.get("market_close")) or time(15, 30),
            is_holiday=bool(payload.get("is_holiday", False)),
            source_type=str(payload.get("source_type", "generated_live_prelude_fixture")),
            source_id_prefix=str(payload.get("source_id_prefix", "generated-live-prelude")),
        )

    def _build_monthly_status_result(
        self,
        payload: dict[str, Any],
    ) -> MonthlyStatusResult:
        return MonthlyStatusResult(
            status=MonthlyStatus(str(payload["status"])),
            trigger_name=str(payload.get("trigger_name", "FIXTURE_TRIGGER")),
            threshold_value=self._optional_float(payload.get("threshold_value")),
            reversal_dominated=bool(payload.get("reversal_dominated", False)),
            candidates=[],
            notes=str(payload.get("notes", "fixture")),
        )

    def _build_market_levels(self, payload: dict[str, Any]) -> MarketLevels:
        return MarketLevels(
            previous_month_high=self._optional_float(payload.get("previous_month_high")),
            previous_month_low=self._optional_float(payload.get("previous_month_low")),
            previous_week_high=self._optional_float(payload.get("previous_week_high")),
            previous_week_low=self._optional_float(payload.get("previous_week_low")),
            d2hh=self._optional_float(payload.get("d2hh")),
            d2ll=self._optional_float(payload.get("d2ll")),
            d3hh=self._optional_float(payload.get("d3hh")),
            d3ll=self._optional_float(payload.get("d3ll")),
            d4hh=self._optional_float(payload.get("d4hh")),
            d4ll=self._optional_float(payload.get("d4ll")),
            current_day_high=self._optional_float(payload.get("current_day_high")),
            current_day_low=self._optional_float(payload.get("current_day_low")),
        )

    def _build_snapshots(
        self,
        payload: list[dict[str, Any]],
    ) -> tuple[PaperSnapshotInput, ...]:
        snapshots: list[PaperSnapshotInput] = []
        for item in payload:
            snapshots.append(
                PaperSnapshotInput(
                    snapshot_label=SnapshotLabel(str(item["snapshot_label"])),
                    open=self._optional_float(item.get("open")),
                    high=self._optional_float(item.get("high")),
                    low=self._optional_float(item.get("low")),
                    close=self._optional_float(item.get("close")),
                    bar_start=self._parse_datetime(item["bar_start"]),
                    bar_end=self._parse_datetime(item["bar_end"]),
                    complete=bool(item.get("complete", True)),
                )
            )
        return tuple(snapshots)

    def _build_expiry_governance(
        self,
        payload: dict[str, Any],
    ) -> PaperExpiryGovernance:
        weekly_expiry = self._optional_date(payload.get("weekly_expiry"))
        session_date = self._parse_date(payload["session_date"])
        explicit = {}
        if weekly_expiry is not None:
            from tfis.domain import ExpiryType

            explicit = {(ExpiryType.WEEKLY, session_date): weekly_expiry}
        return PaperExpiryGovernance(
            DeterministicExpiryCalendar(explicit_expiries=explicit)
        )

    def _select_option_chain_snapshot(
        self,
        events: tuple[PaperEvent, ...],
        *,
        session_date: date,
    ) -> OptionChainSnapshotEvent | None:
        candidates = [
            event
            for event in events
            if isinstance(event, OptionChainSnapshotEvent)
            and event.envelope.session_date == session_date
        ]
        return candidates[-1] if candidates else None

    def _write_paper_events(self, path: Path, events: tuple[PaperEvent, ...]) -> None:
        rows = tuple(self._serialize_event(event) for event in events)
        self._write_jsonl(path, rows)

    def _serialize_event(self, event: PaperEvent) -> dict[str, Any]:
        payload = {
            "event_type": event.envelope.event_type.value,
            "session_date": event.envelope.session_date.isoformat(),
            "effective_timestamp": event.envelope.effective_timestamp.isoformat(),
            "captured_at": event.envelope.captured_at.isoformat(),
            "timezone": event.envelope.timezone,
            "source_type": event.envelope.source_type,
            "source_id": event.envelope.source_id,
            "synthetic_fixture": event.envelope.synthetic_fixture,
            "normalized_by": event.envelope.normalized_by,
            "source_sequence": event.envelope.source_sequence,
            "data_quality_flags": list(event.envelope.data_quality_flags),
        }
        if event.envelope.integrity_hash is not None:
            payload["integrity_hash"] = event.envelope.integrity_hash
        body = self._normalize(event)
        body.pop("envelope", None)
        payload["payload"] = body
        return payload

    def _write_json(self, path: Path, payload: Any) -> None:
        self._atomic_write_text(path, json.dumps(self._normalize(payload), indent=2, sort_keys=True) + "\n")

    def _write_jsonl(self, path: Path, rows: tuple[Any, ...]) -> None:
        rendered = "".join(json.dumps(self._normalize(row), sort_keys=True) + "\n" for row in rows)
        self._atomic_write_text(path, rendered)

    def _atomic_write_text(self, path: Path, content: str) -> None:
        atomic_write_text(path, content)

    def _normalize(self, value: Any) -> Any:
        if is_dataclass(value):
            return {
                field.name: self._normalize(getattr(value, field.name))
                for field in fields(value)
            }
        if isinstance(value, dict):
            return {str(key): self._normalize(val) for key, val in value.items()}
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

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        return datetime.fromisoformat(str(value))

    @staticmethod
    def _parse_date(value: Any) -> date:
        return date.fromisoformat(str(value))

    @staticmethod
    def _optional_date(value: Any) -> date | None:
        if value in (None, ""):
            return None
        return date.fromisoformat(str(value))

    @staticmethod
    def _optional_time(value: Any) -> time | None:
        if value in (None, ""):
            return None
        return time.fromisoformat(str(value))

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)


PaperGeneratedPreludeDryRunRunner = S23GeneratedPreludeDryRunRunner
