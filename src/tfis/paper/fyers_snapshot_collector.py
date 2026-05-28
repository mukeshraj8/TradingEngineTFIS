from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tfis.brokers.base import BrokerAdapter, BrokerAdapterError, BrokerCredentialsError
from tfis.brokers.fyers import FyersBrokerAdapter, FyersCredentials
from tfis.domain import ExpiryType, MarketLevels, StrategyRule
from tfis.domain.enums import MonthlyStatus
from tfis.importers import load_strategy_rule
from tfis.monthly_status import MonthlyStatusResult

from .expiry_governance import DeterministicExpiryCalendar, S23PaperExpiryGovernance
from .live_ingress import S23LivePaperIngressConfig
from .live_prelude import (
    S23LivePreludeError,
    S23PaperLivePreludeBuilder,
    S23PaperLivePreludeRequest,
    S23PaperLivePreludeResult,
    S23PaperPreludeSessionContext,
    S23PaperSnapshotInput,
)
from .models import EventEnvelope, OptionChainSnapshotEvent, SnapshotLabel, UnderlyingQuoteEvent
from .position_state import S23PaperPositionStateStore


_ARTIFACT_VERSION = 1
_DEFAULT_ARTIFACT_ROOT = Path("tmp/s23_fyers_snapshot_preflight")


class S23FyersSnapshotCollectorError(RuntimeError):
    """Raised when FYERS-backed paper snapshot collection cannot proceed safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class S23FyersSnapshotPreflightIssue:
    code: str
    message: str
    severity: str


@dataclass(frozen=True, slots=True)
class S23FyersSnapshotPreludeProvenance:
    prelude_source: str
    contract_selection_source: str | None
    carry_forward_state_source: str | None
    snapshot_collection_source: str
    strategy_path: str
    ingress_config_path: str
    runtime_fixture_path: str
    generated_mode: str
    smoke_override_enabled: bool


@dataclass(frozen=True, slots=True)
class S23FyersSnapshotPreflightSummary:
    artifact_version: int
    provider: str
    session_id: str
    session_date: date
    config_path: str
    strategy_path: str
    runtime_fixture_path: str | None
    expected_session_directory: str
    artifact_root: str
    uses_payload_fixture: bool
    will_connect_to_broker: bool
    strategy_code: str
    strategy_branch_reference: str
    symbol: str
    contract_cycle: str
    mode: str
    paper_mode_enabled: bool
    no_live_orders_allowed: bool
    kill_switch_enabled: bool
    session_kill_switch_active: bool
    weekly_expiry: date
    underlying_quote_collected: bool
    option_chain_collected: bool
    option_chain_contract_count: int
    option_chain_has_complete_oi: bool
    dry_run_build_prelude_requested: bool
    prelude_generated: bool
    preflight_status: str
    can_run: bool
    issues: tuple[S23FyersSnapshotPreflightIssue, ...]
    explicit_disclaimer: str


@dataclass(frozen=True, slots=True)
class S23FyersSnapshotArtifactSet:
    session_directory: Path
    summary_path: Path
    normalized_underlying_snapshot_path: Path
    normalized_option_chain_snapshot_path: Path
    summary: S23FyersSnapshotPreflightSummary
    generated_prelude_events_path: Path | None = None
    generated_prelude_provenance_path: Path | None = None
    generated_governance_events_path: Path | None = None


@dataclass(frozen=True, slots=True)
class S23CollectedSnapshotInputs:
    session_context: S23PaperPreludeSessionContext
    strategy_rule: StrategyRule
    underlying_quote: UnderlyingQuoteEvent
    option_chain_snapshot: OptionChainSnapshotEvent
    expiry_governance: S23PaperExpiryGovernance
    weekly_expiry: date


class S23FyersSnapshotCollector:
    def __init__(
        self,
        *,
        artifact_root: str | Path = _DEFAULT_ARTIFACT_ROOT,
        prelude_builder: S23PaperLivePreludeBuilder | None = None,
        position_state_store: S23PaperPositionStateStore | None = None,
    ) -> None:
        self._artifact_root = Path(artifact_root)
        self._prelude_builder = prelude_builder or S23PaperLivePreludeBuilder()
        self._position_state_store = position_state_store or S23PaperPositionStateStore()

    def collect_from_files(
        self,
        *,
        config_path: str | Path,
        strategy_path: str | Path,
        runtime_fixture_path: str | Path | None = None,
        carry_forward_state_dir: str | Path | None = None,
        session_id: str | None = None,
        dry_run_build_prelude: bool = False,
        enable_smoke_override: bool = False,
        adapter: BrokerAdapter | None = None,
    ) -> S23FyersSnapshotArtifactSet:
        config = S23LivePaperIngressConfig.from_yaml(config_path)
        strategy = load_strategy_rule(strategy_path)
        runtime_fixture = (
            self._load_runtime_fixture(runtime_fixture_path)
            if runtime_fixture_path is not None
            else None
        )
        session_context = self._resolve_session_context(
            config=config,
            runtime_fixture=runtime_fixture,
        )
        if dry_run_build_prelude and runtime_fixture is None:
            raise S23FyersSnapshotCollectorError(
                "MISSING_RUNTIME_FIXTURE",
                "--dry-run-build-prelude requires --runtime-fixture.",
            )
        issues = self._collect_preflight_issues(
            config=config,
            strategy=strategy,
            dry_run_build_prelude=dry_run_build_prelude,
            runtime_fixture=runtime_fixture,
            adapter_supplied=adapter is not None,
        )
        if any(issue.severity == "NO_GO" for issue in issues):
            raise S23FyersSnapshotCollectorError(
                "PRECHECK_FAILED",
                "Snapshot preflight failed: "
                + "; ".join(f"{issue.code}: {issue.message}" for issue in issues),
            )

        resolved_session_id = session_id or self._derive_session_id(
            strategy_code=config.paper.strategy_code,
            symbol=config.paper.symbol,
            contract_cycle=config.paper.contract_cycle,
            mode=config.paper.mode,
            session_date=session_context.session_date,
        )
        session_directory = (
            self._artifact_root / session_context.session_date.isoformat() / resolved_session_id
        )
        active_adapter = adapter or self._build_adapter(config)
        governance, weekly_expiry = self._build_expiry_governance(
            config=config,
            strategy=strategy,
            session_date=session_context.session_date,
            runtime_fixture=runtime_fixture,
        )

        underlying_quote: UnderlyingQuoteEvent
        option_chain_snapshot: OptionChainSnapshotEvent
        prelude_result: S23PaperLivePreludeResult | None = None
        try:
            active_adapter.connect()
            underlying_quote = active_adapter.get_underlying_quote(
                config.market.underlying_symbol,
                session_date=session_context.session_date,
            )
            option_chain_snapshot = active_adapter.get_option_chain(
                config.market.underlying_symbol,
                weekly_expiry,
                session_date=session_context.session_date,
            )
        except (BrokerAdapterError, OSError, ValueError) as exc:
            raise S23FyersSnapshotCollectorError(
                "BROKER_SNAPSHOT_FAILED",
                f"Unable to collect normalized FYERS snapshot inputs safely: {exc}",
            ) from exc
        finally:
            active_adapter.disconnect()

        self._validate_normalized_snapshot(
            underlying_quote=underlying_quote,
            option_chain_snapshot=option_chain_snapshot,
            expected_symbol=config.market.underlying_symbol,
            expected_expiry=weekly_expiry,
        )

        normalized_underlying_snapshot_path = (
            session_directory / "normalized_underlying_snapshot.json"
        )
        normalized_option_chain_snapshot_path = (
            session_directory / "normalized_option_chain_snapshot.json"
        )
        summary_path = session_directory / "snapshot_preflight_summary.json"
        generated_prelude_events_path: Path | None = None
        generated_prelude_provenance_path: Path | None = None
        generated_governance_events_path: Path | None = None

        self._write_json(
            normalized_underlying_snapshot_path,
            self._serialize_event(underlying_quote),
        )
        self._write_json(
            normalized_option_chain_snapshot_path,
            self._serialize_event(option_chain_snapshot),
        )

        if dry_run_build_prelude:
            assert runtime_fixture is not None
            carry_forward_state = (
                self._position_state_store.load_state(carry_forward_state_dir)
                if carry_forward_state_dir is not None
                else None
            )
            if runtime_fixture["session_date"] != session_context.session_date.isoformat():
                raise S23FyersSnapshotCollectorError(
                    "SESSION_DATE_MISMATCH",
                    "Runtime fixture session_date must match the collected snapshot session date.",
                )
            try:
                prelude_result = self._prelude_builder.build(
                    S23PaperLivePreludeRequest(
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
                        expiry_governance=governance,
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
            except S23LivePreludeError as exc:
                raise S23FyersSnapshotCollectorError(exc.code, str(exc)) from exc

            generated_prelude_events_path = session_directory / "generated_live_prelude_events.jsonl"
            generated_prelude_provenance_path = (
                session_directory / "generated_live_prelude_provenance.json"
            )
            governance_rows = tuple(
                item
                for item in (
                    *(prelude_result.governance_events),
                    prelude_result.resume_event,
                )
                if item is not None
            )
            if governance_rows:
                generated_governance_events_path = (
                    session_directory / "generated_live_prelude_governance_events.jsonl"
                )
                self._write_jsonl(generated_governance_events_path, governance_rows)
            self._write_jsonl(
                generated_prelude_events_path,
                tuple(self._serialize_event(event) for event in prelude_result.prelude_events),
            )
            provenance = S23FyersSnapshotPreludeProvenance(
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
                snapshot_collection_source="fyers_snapshot_preflight",
                strategy_path=str(Path(strategy_path)),
                ingress_config_path=str(Path(config_path)),
                runtime_fixture_path=str(Path(runtime_fixture_path)),
                generated_mode=prelude_result.mode.value,
                smoke_override_enabled=enable_smoke_override,
            )
            self._write_json(generated_prelude_provenance_path, provenance)

        summary = S23FyersSnapshotPreflightSummary(
            artifact_version=_ARTIFACT_VERSION,
            provider=config.broker.provider,
            session_id=resolved_session_id,
            session_date=session_context.session_date,
            config_path=str(Path(config_path)),
            strategy_path=str(Path(strategy_path)),
            runtime_fixture_path=(
                str(Path(runtime_fixture_path)) if runtime_fixture_path is not None else None
            ),
            expected_session_directory=str(session_directory),
            artifact_root=str(self._artifact_root),
            uses_payload_fixture=config.broker.payload_fixture_path is not None,
            will_connect_to_broker=adapter is not None or config.broker.payload_fixture_path is None,
            strategy_code=strategy.strategy_code,
            strategy_branch_reference=strategy.unique_code,
            symbol=strategy.symbol,
            contract_cycle=config.paper.contract_cycle,
            mode=config.paper.mode,
            paper_mode_enabled=config.paper.paper_mode_enabled,
            no_live_orders_allowed=config.paper.no_live_orders_allowed,
            kill_switch_enabled=config.paper.kill_switch_enabled,
            session_kill_switch_active=config.paper.session_kill_switch_active,
            weekly_expiry=weekly_expiry,
            underlying_quote_collected=True,
            option_chain_collected=True,
            option_chain_contract_count=len(option_chain_snapshot.contracts),
            option_chain_has_complete_oi=all(
                contract.oi is not None for contract in option_chain_snapshot.contracts
            ),
            dry_run_build_prelude_requested=dry_run_build_prelude,
            prelude_generated=prelude_result is not None,
            preflight_status="READY",
            can_run=True,
            issues=issues,
            explicit_disclaimer=(
                "Snapshot preflight collects one-shot FYERS normalized inputs for S23 paper "
                "readiness only. It never starts a socket loop, never executes lifecycle "
                "logic, and never places broker orders."
            ),
        )
        self._write_json(summary_path, summary)

        return S23FyersSnapshotArtifactSet(
            session_directory=session_directory,
            summary_path=summary_path,
            normalized_underlying_snapshot_path=normalized_underlying_snapshot_path,
            normalized_option_chain_snapshot_path=normalized_option_chain_snapshot_path,
            summary=summary,
            generated_prelude_events_path=generated_prelude_events_path,
            generated_prelude_provenance_path=generated_prelude_provenance_path,
            generated_governance_events_path=generated_governance_events_path,
        )

    def _collect_preflight_issues(
        self,
        *,
        config: S23LivePaperIngressConfig,
        strategy: StrategyRule,
        dry_run_build_prelude: bool,
        runtime_fixture: dict[str, Any] | None,
        adapter_supplied: bool,
    ) -> tuple[S23FyersSnapshotPreflightIssue, ...]:
        issues: list[S23FyersSnapshotPreflightIssue] = []
        if self._resolve_timezone(config.broker.timezone) is None:
            issues.append(
                self._issue(
                    "invalid_broker_timezone",
                    f"Snapshot preflight requires a valid broker.timezone. Received: {config.broker.timezone}",
                )
            )
        if config.broker.provider != "fyers":
            issues.append(
                self._issue(
                    "unsupported_broker_provider",
                    "Snapshot preflight currently supports broker.provider=fyers only.",
                )
            )
        if config.paper.strategy_code != "S23" or strategy.strategy_code != "S23":
            issues.append(
                self._issue(
                    "unsupported_strategy",
                    "Snapshot preflight is scoped to S23 only.",
                )
            )
        if config.paper.symbol != "NIFTY" or strategy.symbol != "NIFTY":
            issues.append(
                self._issue(
                    "unsupported_symbol",
                    "Snapshot preflight is scoped to NIFTY only.",
                )
            )
        if config.market.underlying_symbol != "NIFTY":
            issues.append(
                self._issue(
                    "unsupported_underlying_symbol",
                    "Snapshot preflight requires market.underlying_symbol=NIFTY.",
                )
            )
        if config.paper.contract_cycle != "WEEKLY":
            issues.append(
                self._issue(
                    "unsupported_contract_cycle",
                    "Snapshot preflight is scoped to weekly options only.",
                )
            )
        if config.paper.mode != "paper":
            issues.append(
                self._issue(
                    "non_paper_mode",
                    "Snapshot preflight requires mode=paper.",
                )
            )
        if not config.paper.paper_mode_enabled:
            issues.append(
                self._issue(
                    "paper_mode_disabled",
                    "Snapshot preflight requires paper_mode_enabled=true.",
                )
            )
        if not config.paper.no_live_orders_allowed:
            issues.append(
                self._issue(
                    "live_order_block_disabled",
                    "Snapshot preflight requires no_live_orders_allowed=true.",
                )
            )
        if not config.paper.kill_switch_enabled:
            issues.append(
                self._issue(
                    "kill_switch_default_disabled",
                    "Snapshot preflight requires kill_switch_enabled=true by default.",
                )
            )
        if config.paper.session_kill_switch_active:
            issues.append(
                self._issue(
                    "session_kill_switch_active",
                    "Snapshot preflight cannot start while session_kill_switch_active=true.",
                )
            )
        if strategy.segment.value != "OPTIONS_SELL":
            issues.append(
                self._issue(
                    "unsupported_strategy_segment",
                    "Snapshot preflight is scoped to S23 option-selling strategies only.",
                )
            )
        if strategy.option_type is None:
            issues.append(
                self._issue(
                    "missing_option_type",
                    "Snapshot preflight requires an option strategy with option_type.",
                )
            )
        if dry_run_build_prelude and runtime_fixture is None:
            issues.append(
                self._issue(
                    "missing_runtime_fixture",
                    "--dry-run-build-prelude requires a runtime fixture.",
                )
            )
        if config.broker.payload_fixture_path is None and not adapter_supplied:
            try:
                FyersCredentials.from_env()
            except BrokerCredentialsError as exc:
                issues.append(self._issue("missing_broker_credentials", str(exc)))
        else:
            issues.append(
                self._issue(
                    "payload_fixture_mode_enabled",
                    "Payload fixture mode is enabled; snapshot preflight remains safe, but this is not a live FYERS data run.",
                    severity="WARNING",
                )
            )
        return tuple(issues)

    def _resolve_session_context(
        self,
        *,
        config: S23LivePaperIngressConfig,
        runtime_fixture: dict[str, Any] | None,
    ) -> S23PaperPreludeSessionContext:
        if runtime_fixture is not None:
            session_date = self._parse_date(runtime_fixture["session_date"])
            generated_at = self._parse_datetime(runtime_fixture["generated_at"])
            return S23PaperPreludeSessionContext(
                session_date=session_date,
                timezone=str(runtime_fixture.get("timezone", config.broker.timezone)),
                generated_at=generated_at,
                market_open=self._optional_time(runtime_fixture.get("market_open")) or time(9, 15),
                market_close=self._optional_time(runtime_fixture.get("market_close")) or time(15, 30),
                is_holiday=bool(runtime_fixture.get("is_holiday", False)),
                source_type=str(
                    runtime_fixture.get("source_type", "fyers_snapshot_preflight")
                ),
                source_id_prefix=str(
                    runtime_fixture.get("source_id_prefix", "fyers-snapshot-preflight")
                ),
            )
        timezone = self._resolve_timezone(config.broker.timezone)
        now = datetime.now(timezone) if timezone is not None else datetime.now()
        return S23PaperPreludeSessionContext(
            session_date=now.date(),
            timezone=config.broker.timezone,
            generated_at=now,
            source_type="fyers_snapshot_preflight",
            source_id_prefix="fyers-snapshot-preflight",
        )

    def _build_expiry_governance(
        self,
        *,
        config: S23LivePaperIngressConfig,
        strategy: StrategyRule,
        session_date: date,
        runtime_fixture: dict[str, Any] | None,
    ) -> tuple[S23PaperExpiryGovernance, date]:
        weekly_expiry = (
            self._optional_date(runtime_fixture.get("weekly_expiry"))
            if runtime_fixture is not None
            else None
        ) or config.market.weekly_expiry
        explicit_expiries = {
            (strategy.expiry_policy.expiry_type, session_date): weekly_expiry,
        }
        governance = S23PaperExpiryGovernance(
            DeterministicExpiryCalendar(explicit_expiries=explicit_expiries)
        )
        return governance, weekly_expiry

    def _validate_normalized_snapshot(
        self,
        *,
        underlying_quote: UnderlyingQuoteEvent,
        option_chain_snapshot: OptionChainSnapshotEvent,
        expected_symbol: str,
        expected_expiry: date,
    ) -> None:
        if underlying_quote.symbol != expected_symbol:
            raise S23FyersSnapshotCollectorError(
                "UNDERLYING_SYMBOL_MISMATCH",
                f"Expected normalized underlying symbol {expected_symbol}, received {underlying_quote.symbol}.",
            )
        if option_chain_snapshot.underlying_symbol != expected_symbol:
            raise S23FyersSnapshotCollectorError(
                "OPTION_CHAIN_SYMBOL_MISMATCH",
                "Normalized option-chain underlying symbol does not match the requested underlying.",
            )
        if option_chain_snapshot.expiry != expected_expiry:
            raise S23FyersSnapshotCollectorError(
                "OPTION_CHAIN_EXPIRY_MISMATCH",
                "Normalized option-chain expiry does not match the resolved weekly expiry.",
            )
        if not option_chain_snapshot.contracts:
            raise S23FyersSnapshotCollectorError(
                "OPTION_CHAIN_MISSING",
                "Runtime option-chain selection requires a non-empty normalized option-chain snapshot.",
            )
        missing_oi = [
            contract.symbol
            for contract in option_chain_snapshot.contracts
            if contract.oi is None
        ]
        if missing_oi:
            raise S23FyersSnapshotCollectorError(
                "MISSING_CONTRACT_OI",
                "Normalized option-chain snapshot is missing OI for one or more contracts: "
                + ", ".join(missing_oi[:5]),
            )

    def _build_adapter(self, config: S23LivePaperIngressConfig) -> BrokerAdapter:
        if config.broker.provider != "fyers":
            raise S23FyersSnapshotCollectorError(
                "UNSUPPORTED_BROKER_PROVIDER",
                "Snapshot preflight currently supports broker.provider=fyers only.",
            )
        if config.broker.payload_fixture_path:
            return FyersBrokerAdapter.from_payload_file(
                config.broker.payload_fixture_path,
                source_timezone=config.broker.timezone,
            )
        return FyersBrokerAdapter(source_timezone=config.broker.timezone)

    @staticmethod
    def _derive_session_id(
        *,
        strategy_code: str,
        symbol: str,
        contract_cycle: str,
        mode: str,
        session_date: date,
    ) -> str:
        return (
            f"{strategy_code.lower()}-{symbol.lower()}-{contract_cycle.lower()}-"
            f"{mode.lower()}-snapshot-{session_date.isoformat()}"
        )

    @staticmethod
    def _issue(code: str, message: str, *, severity: str = "NO_GO") -> S23FyersSnapshotPreflightIssue:
        return S23FyersSnapshotPreflightIssue(code=code, message=message, severity=severity)

    @staticmethod
    def _resolve_timezone(value: str) -> ZoneInfo | None:
        try:
            return ZoneInfo(value)
        except ZoneInfoNotFoundError:
            return None

    def _load_runtime_fixture(self, path: str | Path) -> dict[str, Any]:
        target = Path(path)
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise S23FyersSnapshotCollectorError(
                "INVALID_RUNTIME_FIXTURE",
                f"Runtime fixture must be a JSON object: {target}",
            )
        return data

    def _build_monthly_status_result(
        self,
        payload: dict[str, Any],
    ) -> MonthlyStatusResult:
        return MonthlyStatusResult(
            status=MonthlyStatus(str(payload["status"])),
            trigger_name=str(payload.get("trigger_name", "SNAPSHOT_PREFLIGHT_TRIGGER")),
            threshold_value=self._optional_float(payload.get("threshold_value")),
            reversal_dominated=bool(payload.get("reversal_dominated", False)),
            candidates=[],
            notes=str(payload.get("notes", "snapshot_preflight")),
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
    ) -> tuple[S23PaperSnapshotInput, ...]:
        snapshots: list[S23PaperSnapshotInput] = []
        for item in payload:
            snapshots.append(
                S23PaperSnapshotInput(
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

    def _serialize_event(self, event: Any) -> dict[str, Any]:
        if not hasattr(event, "envelope") or not isinstance(event.envelope, EventEnvelope):
            raise TypeError("serialize_event expects a normalized event dataclass with an envelope")
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
        self._atomic_write_text(
            path,
            json.dumps(self._normalize(payload), indent=2, sort_keys=True) + "\n",
        )

    def _write_jsonl(self, path: Path, rows: tuple[Any, ...]) -> None:
        rendered = "".join(json.dumps(self._normalize(row), sort_keys=True) + "\n" for row in rows)
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
    def _parse_date(value: object) -> date:
        return date.fromisoformat(str(value))

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        return datetime.fromisoformat(str(value))

    @staticmethod
    def _optional_date(value: object) -> date | None:
        if value in (None, ""):
            return None
        return date.fromisoformat(str(value))

    @staticmethod
    def _optional_time(value: object) -> time | None:
        if value in (None, ""):
            return None
        return time.fromisoformat(str(value))

    @staticmethod
    def _optional_text(value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value in (None, ""):
            return None
        return float(value)
