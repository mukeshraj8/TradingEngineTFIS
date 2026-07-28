from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from time import sleep as _sleep
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tfis.brokers.base import BrokerAdapter, BrokerAdapterError
from tfis.domain import ExpiryType, MarketLevels, StrategyRule
from tfis.domain.enums import MonthlyStatus
from tfis.importers import load_strategy_rule
from tfis.market_data import UnderlyingHistoryBar
from tfis.monthly_status import MonthlyStatusResult
from tfis.storage import atomic_write_text

from .expiry_governance import DeterministicExpiryCalendar, PaperExpiryGovernance
from .live_ingress import PaperLiveIngressConfig
from .lifecycle_runtime_config import (
    PaperLifecycleBrokerConfig,
    PaperLifecycleRuntimeConfigError,
    build_paper_broker_adapter_from_broker_config,
    paper_broker_credentials_available,
)
from .live_prelude import (
    PaperLivePreludeBuilder,
    PaperLivePreludeError,
    PaperLivePreludeRequest,
    PaperLivePreludeResult,
    PaperPreludeSessionContext,
    PaperSnapshotInput,
)
from .models import (
    EventEnvelope,
    OptionChainContract,
    OptionChainSnapshotEvent,
    SelectedContractBarEvent,
    SnapshotLabel,
    UnderlyingQuoteEvent,
)
from .position_state import PaperPositionStateStore


_ARTIFACT_VERSION = 1
_DEFAULT_ARTIFACT_ROOT = Path("tmp/s23_fyers_snapshot_preflight")
_DEFAULT_SNAPSHOT_FETCH_ATTEMPTS = 3
_DEFAULT_SNAPSHOT_FETCH_RETRY_DELAY_SECONDS = 0.5


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
    normalized_underlying_bars_path: Path
    normalized_underlying_daily_bars_path: Path
    normalized_option_chain_snapshot_path: Path
    summary: S23FyersSnapshotPreflightSummary
    generated_prelude_events_path: Path | None = None
    generated_prelude_provenance_path: Path | None = None
    generated_governance_events_path: Path | None = None
    collected_inputs: S23CollectedSnapshotInputs | None = None
    prelude_result: PaperLivePreludeResult | None = None


@dataclass(frozen=True, slots=True)
class S23CollectedSnapshotInputs:
    session_context: PaperPreludeSessionContext
    strategy_rule: StrategyRule
    underlying_quote: UnderlyingQuoteEvent
    underlying_bars: tuple[UnderlyingHistoryBar, ...]
    daily_bars: tuple[UnderlyingHistoryBar, ...]
    option_chain_snapshot: OptionChainSnapshotEvent
    expiry_governance: PaperExpiryGovernance
    weekly_expiry: date
    selected_contract_bars: tuple[SelectedContractBarEvent, ...] = ()


PaperCollectedSnapshotInputs = S23CollectedSnapshotInputs
PaperFyersSnapshotCollectorError = S23FyersSnapshotCollectorError
PaperFyersSnapshotPreflightIssue = S23FyersSnapshotPreflightIssue
PaperFyersSnapshotPreludeProvenance = S23FyersSnapshotPreludeProvenance
PaperFyersSnapshotPreflightSummary = S23FyersSnapshotPreflightSummary
PaperFyersSnapshotArtifactSet = S23FyersSnapshotArtifactSet


class S23FyersSnapshotCollector:
    def __init__(
        self,
        *,
        artifact_root: str | Path = _DEFAULT_ARTIFACT_ROOT,
        prelude_builder: PaperLivePreludeBuilder | None = None,
        position_state_store: PaperPositionStateStore | None = None,
        snapshot_fetch_attempts: int = _DEFAULT_SNAPSHOT_FETCH_ATTEMPTS,
        snapshot_fetch_retry_delay_seconds: float = _DEFAULT_SNAPSHOT_FETCH_RETRY_DELAY_SECONDS,
        sleeper: Callable[[float], None] = _sleep,
    ) -> None:
        self._artifact_root = Path(artifact_root)
        self._prelude_builder = prelude_builder or PaperLivePreludeBuilder()
        self._position_state_store = position_state_store or PaperPositionStateStore()
        self._snapshot_fetch_attempts = max(1, int(snapshot_fetch_attempts))
        self._snapshot_fetch_retry_delay_seconds = max(
            0.0, float(snapshot_fetch_retry_delay_seconds)
        )
        self._sleeper = sleeper

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
        config = PaperLiveIngressConfig.from_yaml(config_path)
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
        issues = list(
            self._collect_preflight_issues(
                config=config,
                strategy=strategy,
                session_date=session_context.session_date,
                dry_run_build_prelude=dry_run_build_prelude,
                runtime_fixture=runtime_fixture,
                adapter_supplied=adapter is not None,
            )
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
        underlying_bars: tuple[UnderlyingHistoryBar, ...]
        daily_bars: tuple[UnderlyingHistoryBar, ...]
        option_chain_snapshot: OptionChainSnapshotEvent
        prelude_result: PaperLivePreludeResult | None = None
        try:
            active_adapter.connect()
            underlying_quote = self._fetch_snapshot_input_with_retries(
                lambda: active_adapter.get_underlying_quote(
                    config.market.underlying_symbol,
                    session_date=session_context.session_date,
                ),
                input_name="underlying_quote",
                issues=issues,
            )
            underlying_bars = self._fetch_snapshot_input_with_retries(
                lambda: active_adapter.get_underlying_bars(
                    config.market.underlying_symbol,
                    session_date=session_context.session_date,
                    from_time=time(9, 14),
                    to_time=time(9, 30),
                    interval_minutes=1,
                ),
                input_name="underlying_bars",
                issues=issues,
            )
            daily_bars = self._fetch_snapshot_input_with_retries(
                lambda: active_adapter.get_underlying_daily_bars(
                    config.market.underlying_symbol,
                    session_date=session_context.session_date,
                    lookback_days=180,
                ),
                input_name="underlying_daily_bars",
                issues=issues,
            )
            option_chain_snapshot = self._collect_option_chains(
                active_adapter=active_adapter,
                symbol=config.market.underlying_symbol,
                near_expiry=weekly_expiry,
                session_date=session_context.session_date,
                expiry_type=strategy.expiry_policy.expiry_type,
                issues=issues,
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
        normalized_underlying_bars_path = (
            session_directory / "normalized_underlying_bars.json"
        )
        normalized_underlying_daily_bars_path = (
            session_directory / "normalized_underlying_daily_bars.json"
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
            normalized_underlying_bars_path,
            {
                "session_date": session_context.session_date.isoformat(),
                "symbol": underlying_quote.symbol,
                "bars": [self._serialize_history_bar(bar) for bar in underlying_bars],
            },
        )
        self._write_json(
            normalized_underlying_daily_bars_path,
            {
                "session_date": session_context.session_date.isoformat(),
                "symbol": underlying_quote.symbol,
                "bars": [self._serialize_history_bar(bar) for bar in daily_bars],
            },
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
            except PaperLivePreludeError as exc:
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
            issues=tuple(issues),
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
            normalized_underlying_bars_path=normalized_underlying_bars_path,
            normalized_underlying_daily_bars_path=normalized_underlying_daily_bars_path,
            normalized_option_chain_snapshot_path=normalized_option_chain_snapshot_path,
            summary=summary,
            generated_prelude_events_path=generated_prelude_events_path,
            generated_prelude_provenance_path=generated_prelude_provenance_path,
            generated_governance_events_path=generated_governance_events_path,
            collected_inputs=PaperCollectedSnapshotInputs(
                session_context=session_context,
                strategy_rule=strategy,
                underlying_quote=underlying_quote,
                underlying_bars=underlying_bars,
                daily_bars=daily_bars,
                option_chain_snapshot=option_chain_snapshot,
                expiry_governance=governance,
                weekly_expiry=weekly_expiry,
            ),
            prelude_result=prelude_result,
        )

    def _collect_preflight_issues(
        self,
        *,
        config: PaperLiveIngressConfig,
        strategy: StrategyRule,
        session_date: date,
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
        if config.paper.strategy_code != strategy.strategy_code:
            issues.append(
                self._issue(
                    "unsupported_strategy",
                    "Snapshot preflight requires matching paper.strategy_code and strategy.strategy_code. "
                    f"Received {config.paper.strategy_code} vs {strategy.strategy_code}.",
                )
            )
        if config.paper.symbol != strategy.symbol:
            issues.append(
                self._issue(
                    "unsupported_symbol",
                    "Snapshot preflight requires matching paper.symbol and strategy.symbol. "
                    f"Received {config.paper.symbol} vs {strategy.symbol}.",
                )
            )
        if config.market.underlying_symbol != strategy.symbol:
            issues.append(
                self._issue(
                    "unsupported_underlying_symbol",
                    "Snapshot preflight requires market.underlying_symbol to match strategy.symbol. "
                    f"Received {config.market.underlying_symbol} vs {strategy.symbol}.",
                )
            )
        expected_contract_cycle = strategy.expiry_policy.expiry_type.value
        if config.paper.contract_cycle != expected_contract_cycle:
            issues.append(
                self._issue(
                    "unsupported_contract_cycle",
                    "Snapshot preflight requires paper.contract_cycle to match strategy expiry policy. "
                    f"Received {config.paper.contract_cycle} vs {expected_contract_cycle}.",
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
                    "Snapshot preflight is scoped to supported option-selling strategies only.",
                )
            )
        if strategy.option_type is None:
            issues.append(
                self._issue(
                    "missing_option_type",
                    "Snapshot preflight requires an option strategy with option_type.",
                )
            )
        if (
            runtime_fixture is None
            and strategy.symbol == "NIFTY"
            and strategy.expiry_policy.expiry_type is ExpiryType.WEEKLY
            and config.market.weekly_expiry < session_date
        ):
            resolved_expiry = self._resolve_live_nifty_weekly_expiry(session_date)
            issues.append(
                self._issue(
                    "configured_weekly_expiry_stale",
                    "Configured market.weekly_expiry "
                    f"{config.market.weekly_expiry.isoformat()} is before session date "
                    f"{session_date.isoformat()}; live snapshot collection will use "
                    f"{resolved_expiry.isoformat()} for S23/NIFTY weekly expiry.",
                    severity="WARNING",
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
            credentials_ready, message = paper_broker_credentials_available(
                PaperLifecycleBrokerConfig(
                    provider=config.broker.provider,
                    timezone=config.broker.timezone,
                    payload_fixture_path=config.broker.payload_fixture_path,
                    capture_stream_events=config.broker.capture_stream_events,
                    option_chain_strike_count=config.broker.option_chain_strike_count,
                )
            )
            if not credentials_ready:
                issues.append(
                    self._issue(
                        "missing_broker_credentials",
                        message or "Broker credentials are unavailable.",
                    )
                )
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
        config: PaperLiveIngressConfig,
        runtime_fixture: dict[str, Any] | None,
    ) -> PaperPreludeSessionContext:
        if runtime_fixture is not None:
            session_date = self._parse_date(runtime_fixture["session_date"])
            generated_at = self._parse_datetime(runtime_fixture["generated_at"])
            return PaperPreludeSessionContext(
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
        return PaperPreludeSessionContext(
            session_date=now.date(),
            timezone=config.broker.timezone,
            generated_at=now,
            source_type="fyers_snapshot_preflight",
            source_id_prefix="fyers-snapshot-preflight",
        )

    def _build_expiry_governance(
        self,
        *,
        config: PaperLiveIngressConfig,
        strategy: StrategyRule,
        session_date: date,
        runtime_fixture: dict[str, Any] | None,
    ) -> tuple[PaperExpiryGovernance, date]:
        weekly_expiry = (
            self._optional_date(runtime_fixture.get("weekly_expiry"))
            if runtime_fixture is not None
            else None
        )
        if weekly_expiry is None:
            weekly_expiry = self._resolve_configured_weekly_expiry(
                config=config,
                strategy=strategy,
                session_date=session_date,
            )
        explicit_expiries = {
            (strategy.expiry_policy.expiry_type, session_date): weekly_expiry,
        }
        governance = PaperExpiryGovernance(
            DeterministicExpiryCalendar(explicit_expiries=explicit_expiries)
        )
        return governance, weekly_expiry

    def _resolve_configured_weekly_expiry(
        self,
        *,
        config: PaperLiveIngressConfig,
        strategy: StrategyRule,
        session_date: date,
    ) -> date:
        configured_expiry = config.market.weekly_expiry
        if configured_expiry >= session_date:
            return configured_expiry
        if strategy.expiry_policy.expiry_type is ExpiryType.WEEKLY and strategy.symbol == "NIFTY":
            return self._resolve_live_nifty_weekly_expiry(session_date)
        raise S23FyersSnapshotCollectorError(
            "STALE_WEEKLY_EXPIRY",
            "Configured market.weekly_expiry "
            f"{configured_expiry.isoformat()} is before session date "
            f"{session_date.isoformat()}.",
        )

    @staticmethod
    def _resolve_live_nifty_weekly_expiry(session_date: date) -> date:
        cursor = session_date
        while cursor.weekday() != 1:
            cursor += timedelta(days=1)
        return cursor

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

    def _collect_option_chains(
        self,
        *,
        active_adapter: BrokerAdapter,
        symbol: str,
        near_expiry: date,
        session_date: date,
        expiry_type: ExpiryType,
        issues: list[S23FyersSnapshotPreflightIssue],
    ) -> OptionChainSnapshotEvent:
        near_chain = self._fetch_snapshot_input_with_retries(
            lambda: active_adapter.get_option_chain(
                symbol,
                near_expiry,
                session_date=session_date,
            ),
            input_name=f"option_chain:{near_expiry.isoformat()}",
            issues=issues,
        )
        near_chain = self._chain_with_symbol_expiries(
            near_chain,
            requested_expiry=near_expiry,
        )
        if not near_chain.contracts:
            raise S23FyersSnapshotCollectorError(
                "OPTION_CHAIN_MISSING",
                "Normalized option-chain snapshot has no contracts.",
            )
        next_expiry = self._next_expiry_after(near_expiry, expiry_type=expiry_type)
        next_chain = self._fetch_snapshot_input_with_retries(
            lambda: active_adapter.get_option_chain(
                symbol,
                next_expiry,
                session_date=session_date,
            ),
            input_name=f"option_chain:{next_expiry.isoformat()}",
            issues=issues,
        )
        next_chain = self._chain_with_symbol_expiries(
            next_chain,
            requested_expiry=next_expiry,
        )
        if next_chain.underlying_symbol != near_chain.underlying_symbol:
            raise S23FyersSnapshotCollectorError(
                "OPTION_CHAIN_SYMBOL_MISMATCH",
                "Near and next weekly option chains do not belong to the same underlying.",
            )
        next_expiry_contract_count = sum(
            1 for contract in next_chain.contracts if contract.expiry == next_expiry
        )
        if next_expiry_contract_count == 0:
            observed_expiries = sorted({contract.expiry for contract in next_chain.contracts})
            observed_text = ", ".join(item.isoformat() for item in observed_expiries) or "none"
            raise S23FyersSnapshotCollectorError(
                "NEXT_WEEKLY_OPTION_CHAIN_UNAVAILABLE",
                "FYERS did not return any true next-expiry contracts for requested expiry "
                f"{next_expiry.isoformat()}. Observed contract expiries after symbol "
                f"normalization: {observed_text}. TFIS cannot safely perform near-then-next "
                "expiry fallback without real next-expiry option-chain data.",
            )
        quality_flags = list(near_chain.envelope.data_quality_flags)
        quality_flags.extend(
            flag
            for flag in next_chain.envelope.data_quality_flags
            if flag not in quality_flags
        )
        quality_flags.append(
            "next_option_chain_verified:"
            f"requested={next_expiry.isoformat()};contracts={next_expiry_contract_count}"
        )
        merged_contracts = tuple(
            {
                (
                    contract.symbol,
                    contract.expiry,
                    contract.option_type,
                    contract.strike,
                ): contract
                for contract in (*near_chain.contracts, *next_chain.contracts)
            }.values()
        )
        return OptionChainSnapshotEvent(
            envelope=replace(
                near_chain.envelope,
                data_quality_flags=tuple(quality_flags),
            ),
            underlying_symbol=near_chain.underlying_symbol,
            expiry=near_chain.expiry,
            contracts=merged_contracts,
        )

    def _fetch_snapshot_input_with_retries(
        self,
        fetcher: Callable[[], Any],
        *,
        input_name: str,
        issues: list[S23FyersSnapshotPreflightIssue],
    ) -> Any:
        last_error: BrokerAdapterError | OSError | ValueError | None = None
        for attempt in range(1, self._snapshot_fetch_attempts + 1):
            try:
                result = fetcher()
            except (BrokerAdapterError, OSError, ValueError) as exc:
                last_error = exc
                if attempt >= self._snapshot_fetch_attempts:
                    break
                if self._snapshot_fetch_retry_delay_seconds > 0:
                    self._sleeper(self._snapshot_fetch_retry_delay_seconds)
                continue
            if attempt > 1:
                issues.append(
                    S23FyersSnapshotPreflightIssue(
                        code="broker_snapshot_retry_succeeded",
                        message=(
                            f"{input_name} succeeded on attempt {attempt} after "
                            f"{attempt - 1} failed attempt(s)."
                        ),
                        severity="WARN",
                    )
                )
            return result
        assert last_error is not None
        raise BrokerAdapterError(
            f"{input_name} failed after {self._snapshot_fetch_attempts} attempt(s): "
            f"{last_error}"
        ) from last_error

    def collect_selected_contract_bars_from_files(
        self,
        *,
        config_path: str | Path,
        option_symbol: str,
        session_date: date,
        from_time: time = time(9, 24),
        to_time: time = time(9, 29),
        interval_minutes: int = 1,
        adapter: BrokerAdapter | None = None,
    ) -> tuple[SelectedContractBarEvent, ...]:
        config = PaperLiveIngressConfig.from_yaml(config_path)
        active_adapter = adapter or self._build_adapter(config)
        connected_here = False
        try:
            if adapter is None:
                active_adapter.connect()
                connected_here = True
            return active_adapter.get_option_bars(
                option_symbol,
                session_date=session_date,
                from_time=from_time,
                to_time=to_time,
                interval_minutes=interval_minutes,
            )
        except BrokerAdapterError as exc:
            raise S23FyersSnapshotCollectorError(
                "SELECTED_CONTRACT_BARS_FAILED",
                f"Selected-contract ORPT/RC bar collection failed: {exc}",
            ) from exc
        finally:
            if connected_here:
                active_adapter.disconnect()

    @staticmethod
    def _next_expiry_after(expiry: date, *, expiry_type: ExpiryType) -> date:
        if expiry_type is ExpiryType.WEEKLY:
            return expiry + timedelta(days=7)
        month = expiry.month + 1
        year = expiry.year
        if month == 13:
            month = 1
            year += 1
        cursor = date(year, month, 1)
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        candidate = next_month - timedelta(days=1)
        while candidate.weekday() != expiry.weekday():
            candidate -= timedelta(days=1)
        return candidate

    @classmethod
    def _chain_with_symbol_expiries(
        cls,
        option_chain: OptionChainSnapshotEvent,
        *,
        requested_expiry: date,
    ) -> OptionChainSnapshotEvent:
        sanitized_contracts: list[OptionChainContract] = []
        flags = list(option_chain.envelope.data_quality_flags)
        mismatched_count = 0
        for contract in option_chain.contracts:
            symbol_expiry = cls._normalized_option_symbol_expiry(contract.symbol)
            if symbol_expiry is not None and contract.expiry != symbol_expiry:
                mismatched_count += 1
                sanitized_contracts.append(replace(contract, expiry=symbol_expiry))
            else:
                sanitized_contracts.append(contract)
        if mismatched_count:
            flags.append(
                "option_chain_contract_expiry_corrected_from_symbol:"
                f"requested={requested_expiry.isoformat()};count={mismatched_count}"
            )
        return OptionChainSnapshotEvent(
            envelope=replace(option_chain.envelope, data_quality_flags=tuple(flags)),
            underlying_symbol=option_chain.underlying_symbol,
            expiry=option_chain.expiry,
            contracts=tuple(sanitized_contracts),
        )

    @staticmethod
    def _normalized_option_symbol_expiry(symbol: str) -> date | None:
        parts = symbol.split("_")
        if len(parts) < 4:
            return None
        expiry_text = parts[1]
        if len(expiry_text) != 8 or not expiry_text.isdigit():
            return None
        try:
            return date.fromisoformat(
                f"{expiry_text[0:4]}-{expiry_text[4:6]}-{expiry_text[6:8]}"
            )
        except ValueError:
            return None

    def _build_adapter(self, config: PaperLiveIngressConfig) -> BrokerAdapter:
        try:
            return build_paper_broker_adapter_from_broker_config(
                PaperLifecycleBrokerConfig(
                    provider=config.broker.provider,
                    timezone=config.broker.timezone,
                    payload_fixture_path=config.broker.payload_fixture_path,
                    capture_stream_events=config.broker.capture_stream_events,
                    option_chain_strike_count=config.broker.option_chain_strike_count,
                )
            )
        except PaperLifecycleRuntimeConfigError as exc:
            raise S23FyersSnapshotCollectorError(
                "UNSUPPORTED_BROKER_PROVIDER",
                "Snapshot preflight currently supports broker.provider=fyers only.",
            ) from exc

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

    def _serialize_history_bar(self, bar: UnderlyingHistoryBar) -> dict[str, Any]:
        return self._normalize(bar)

    def _write_json(self, path: Path, payload: Any) -> None:
        self._atomic_write_text(
            path,
            json.dumps(self._normalize(payload), indent=2, sort_keys=True) + "\n",
        )

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


PaperFyersSnapshotCollector = S23FyersSnapshotCollector
