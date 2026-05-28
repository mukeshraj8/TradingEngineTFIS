from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from tfis.brokers import (
    BrokerAdapter,
    BrokerAdapterError,
    BrokerCredentialsError,
    FyersBrokerAdapter,
)
from tfis.brokers.fyers import FyersCredentials

from .ingress_dry_run import (
    S23NormalizedPaperEventLoader,
    S23PaperIngressDryRunArtifactSet,
    S23PaperIngressDryRunRunner,
    S23PaperIngressDryRunThresholds,
)
from .models import (
    CostSlippageSettingsEvent,
    EventEnvelope,
    PaperEventType,
    PaperSessionConfigEvent,
    PaperSessionState,
    SnapshotLabel,
)
from .validation import PaperEvent, required_snapshot_labels_for_config


_ARTIFACT_VERSION = 1
_DEFAULT_ARTIFACT_ROOT = Path("tmp/s23_fyers_paper_ingress")
_PRELUDE_ALLOWED_EVENT_TYPES = {
    PaperEventType.CALENDAR_CONTEXT,
    PaperEventType.MONTHLY_STATUS_INPUT,
    PaperEventType.UNDERLYING_SNAPSHOT,
    PaperEventType.TRADE_PLAN_INPUT,
}


class S23LivePaperIngressError(RuntimeError):
    """Raised when broker-backed S23 paper ingress cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class S23LivePaperIngressPreflightIssue:
    code: str
    message: str
    severity: str


@dataclass(frozen=True, slots=True)
class S23BrokerAdapterConfig:
    provider: str
    timezone: str
    payload_fixture_path: str | None = None
    capture_stream_events: bool = False


@dataclass(frozen=True, slots=True)
class S23PaperBrokerScopeConfig:
    strategy_code: str
    symbol: str
    contract_cycle: str
    mode: str
    operator_id: str
    paper_mode_enabled: bool
    same_day_square_off_only: bool
    allow_recalculation: bool
    allow_current_day_fsl_trp: bool
    kill_switch_enabled: bool
    session_kill_switch_active: bool
    no_live_orders_allowed: bool


@dataclass(frozen=True, slots=True)
class S23BrokerSelectionConfig:
    underlying_symbol: str
    weekly_expiry: date
    selected_contract_symbol: str


@dataclass(frozen=True, slots=True)
class S23BrokerCostSettingsConfig:
    brokerage_per_lot: float | None
    slippage_entry_points: float | None
    slippage_exit_points: float | None
    spread_buffer_policy: str
    version_label: str


@dataclass(frozen=True, slots=True)
class S23BrokerIngressThresholdConfig:
    max_quote_age_seconds: float
    max_timing_drift_seconds: float
    max_stale_events: int
    max_missing_chains: int
    required_selected_contract_availability_ratio: float
    max_no_trade_rate: float


@dataclass(frozen=True, slots=True)
class S23LivePaperIngressConfig:
    broker: S23BrokerAdapterConfig
    paper: S23PaperBrokerScopeConfig
    market: S23BrokerSelectionConfig
    costs: S23BrokerCostSettingsConfig
    thresholds: S23BrokerIngressThresholdConfig
    source_mode: str = "broker_fyers_live_paper_ingress"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "S23LivePaperIngressConfig":
        target = Path(path)
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise S23LivePaperIngressError(
                f"Live-paper ingress config must be a YAML object: {target}"
            )
        broker = data.get("broker") or {}
        paper = data.get("paper") or {}
        market = data.get("market") or {}
        costs = data.get("costs") or {}
        thresholds = data.get("thresholds") or {}
        payload_fixture_path = _optional_text(broker.get("payload_fixture_path"))
        if payload_fixture_path is not None:
            payload_path = Path(payload_fixture_path)
            if not payload_path.is_absolute():
                payload_fixture_path = str((target.parent / payload_path).resolve())
        return cls(
            broker=S23BrokerAdapterConfig(
                provider=str(broker.get("provider", "fyers")).strip().lower(),
                timezone=str(broker.get("timezone", "Asia/Kolkata")),
                payload_fixture_path=payload_fixture_path,
                capture_stream_events=bool(broker.get("capture_stream_events", False)),
            ),
            paper=S23PaperBrokerScopeConfig(
                strategy_code=str(paper.get("strategy_code", "S23")),
                symbol=str(paper.get("symbol", "NIFTY")),
                contract_cycle=str(paper.get("contract_cycle", "WEEKLY")),
                mode=str(paper.get("mode", "paper")),
                operator_id=str(paper.get("operator_id", "s23-paper-ingress")),
                paper_mode_enabled=bool(paper.get("paper_mode_enabled", True)),
                same_day_square_off_only=bool(paper.get("same_day_square_off_only", True)),
                allow_recalculation=bool(paper.get("allow_recalculation", False)),
                allow_current_day_fsl_trp=bool(
                    paper.get("allow_current_day_fsl_trp", True)
                ),
                kill_switch_enabled=bool(paper.get("kill_switch_enabled", True)),
                session_kill_switch_active=bool(
                    paper.get("session_kill_switch_active", False)
                ),
                no_live_orders_allowed=bool(paper.get("no_live_orders_allowed", True)),
            ),
            market=S23BrokerSelectionConfig(
                underlying_symbol=str(market.get("underlying_symbol", "NIFTY")),
                weekly_expiry=_parse_date_required(
                    market.get("weekly_expiry"),
                    field_name="market.weekly_expiry",
                ),
                selected_contract_symbol=str(
                    market.get("selected_contract_symbol", "")
                ).strip(),
            ),
            costs=S23BrokerCostSettingsConfig(
                brokerage_per_lot=_optional_float(costs.get("brokerage_per_lot")),
                slippage_entry_points=_optional_float(costs.get("slippage_entry_points")),
                slippage_exit_points=_optional_float(costs.get("slippage_exit_points")),
                spread_buffer_policy=str(
                    costs.get("spread_buffer_policy", "bid_ask_guard")
                ),
                version_label=str(costs.get("version_label", "paper-cost-v1")),
            ),
            thresholds=S23BrokerIngressThresholdConfig(
                max_quote_age_seconds=float(thresholds.get("max_quote_age_seconds", 5.0)),
                max_timing_drift_seconds=float(
                    thresholds.get("max_timing_drift_seconds", 5.0)
                ),
                max_stale_events=int(thresholds.get("max_stale_events", 0)),
                max_missing_chains=int(thresholds.get("max_missing_chains", 0)),
                required_selected_contract_availability_ratio=float(
                    thresholds.get(
                        "required_selected_contract_availability_ratio",
                        1.0,
                    )
                ),
                max_no_trade_rate=float(thresholds.get("max_no_trade_rate", 0.0)),
            ),
            source_mode=str(
                data.get("source_mode", "broker_fyers_live_paper_ingress")
            ).strip(),
        )

    def build_paper_session_config_event(
        self,
        *,
        session_date: date,
        source_id: str,
        timezone: str,
    ) -> PaperSessionConfigEvent:
        envelope = EventEnvelope(
            event_type=PaperEventType.PAPER_SESSION_CONFIG,
            session_date=session_date,
            effective_timestamp=_session_datetime(session_date, time(9, 0, 40), timezone),
            captured_at=_session_datetime(session_date, time(9, 0, 41), timezone),
            timezone=timezone,
            source_type="live_paper_config",
            source_id=source_id,
            synthetic_fixture=self.broker.payload_fixture_path is not None,
            normalized_by="live-paper-config-v1",
            source_sequence=3,
            data_quality_flags=(),
        )
        return PaperSessionConfigEvent(
            envelope=envelope,
            strategy_code=self.paper.strategy_code,
            paper_mode_enabled=self.paper.paper_mode_enabled,
            same_day_square_off_only=self.paper.same_day_square_off_only,
            allow_recalculation=self.paper.allow_recalculation,
            allow_current_day_fsl_trp=self.paper.allow_current_day_fsl_trp,
            kill_switch_enabled=self.paper.session_kill_switch_active,
            operator_id=self.paper.operator_id,
            symbol=self.paper.symbol,
            contract_cycle=self.paper.contract_cycle,
            mode=self.paper.mode,
        )

    def build_cost_settings_event(
        self,
        *,
        session_date: date,
        source_id: str,
        timezone: str,
    ) -> CostSlippageSettingsEvent:
        envelope = EventEnvelope(
            event_type=PaperEventType.COST_SLIPPAGE_SETTINGS,
            session_date=session_date,
            effective_timestamp=_session_datetime(session_date, time(9, 0, 50), timezone),
            captured_at=_session_datetime(session_date, time(9, 0, 51), timezone),
            timezone=timezone,
            source_type="live_paper_config",
            source_id=source_id,
            synthetic_fixture=self.broker.payload_fixture_path is not None,
            normalized_by="live-paper-config-v1",
            source_sequence=4,
            data_quality_flags=(),
        )
        return CostSlippageSettingsEvent(
            envelope=envelope,
            brokerage_per_lot=self.costs.brokerage_per_lot,
            slippage_entry_points=self.costs.slippage_entry_points,
            slippage_exit_points=self.costs.slippage_exit_points,
            spread_buffer_policy=self.costs.spread_buffer_policy,
            version_label=self.costs.version_label,
        )


@dataclass(frozen=True, slots=True)
class S23LivePaperIngressSummary:
    artifact_version: int
    broker_name: str
    source_mode: str
    session_id: str
    session_date: date
    config_path: str
    prelude_path: str
    broker_health_path: str
    normalized_events_path: str
    selected_contract_symbol: str
    weekly_expiry: date
    terminal_state: str
    readiness_status: str | None
    operational_readiness: str
    subscribed_symbols: tuple[str, ...]
    engine_event_count: int
    observed_stream_event_count: int
    uses_broker_market_data: bool
    review_md_path: str
    selected_contract_audit_path: str
    no_trade_or_order_plan_summary_path: str
    explicit_disclaimer: str


@dataclass(frozen=True, slots=True)
class S23LivePaperIngressPreflightSummary:
    artifact_version: int
    broker_name: str
    provider: str
    source_mode: str
    session_id: str
    session_date: date
    current_local_date: date
    session_date_matches_local_date: bool
    config_path: str
    prelude_path: str
    expected_session_directory: str
    strategy_code: str
    symbol: str
    contract_cycle: str
    mode: str
    paper_mode_enabled: bool
    no_live_orders_allowed: bool
    kill_switch_enabled: bool
    session_kill_switch_active: bool
    selected_contract_symbol: str
    weekly_expiry: date
    subscribed_symbols: tuple[str, ...]
    required_snapshot_labels: tuple[str, ...]
    present_snapshot_labels: tuple[str, ...]
    credentials_present: bool
    uses_payload_fixture: bool
    will_connect_to_broker: bool
    preflight_status: str
    can_run: bool
    issues: tuple[S23LivePaperIngressPreflightIssue, ...]
    explicit_disclaimer: str


@dataclass(frozen=True, slots=True)
class S23LivePaperIngressArtifactSet:
    session_directory: Path
    dry_run_artifacts: S23PaperIngressDryRunArtifactSet
    broker_health_path: Path
    normalized_events_path: Path
    ingress_summary_path: Path
    no_trade_or_order_plan_summary_path: Path
    summary: S23LivePaperIngressSummary


class S23BrokerPaperIngressRunner:
    def __init__(
        self,
        *,
        loader: S23NormalizedPaperEventLoader | None = None,
        dry_run_runner_factory: type[S23PaperIngressDryRunRunner] = S23PaperIngressDryRunRunner,
        artifact_root: str | Path = _DEFAULT_ARTIFACT_ROOT,
    ) -> None:
        self._loader = loader or S23NormalizedPaperEventLoader()
        self._dry_run_runner_factory = dry_run_runner_factory
        self._artifact_root = Path(artifact_root)

    def run(
        self,
        *,
        config_path: str | Path,
        prelude_jsonl: str | Path,
        session_id: str | None = None,
        adapter: BrokerAdapter | None = None,
    ) -> S23LivePaperIngressArtifactSet:
        config, prelude_events, session_date = self._load_config_and_prelude(
            config_path=config_path,
            prelude_jsonl=prelude_jsonl,
        )
        self._require_safe_preflight(
            config_path=config_path,
            prelude_jsonl=prelude_jsonl,
            session_id=session_id,
            loaded=(config, prelude_events, session_date),
            adapter_supplied=adapter is not None,
        )
        assert session_date is not None

        config_event = config.build_paper_session_config_event(
            session_date=session_date,
            source_id=str(Path(config_path)),
            timezone=config.broker.timezone,
        )
        cost_event = config.build_cost_settings_event(
            session_date=session_date,
            source_id=str(Path(config_path)),
            timezone=config.broker.timezone,
        )

        active_adapter = adapter or self._build_adapter(config)
        fetch_warnings: list[str] = []
        try:
            active_adapter.connect()
            subscribed_symbols = active_adapter.subscribe_symbols(
                (
                    config.market.underlying_symbol,
                    config.market.selected_contract_symbol,
                )
            )
            initial_health = active_adapter.health()
            broker_events = tuple(
                event
                for event in (
                    self._safe_fetch_market_event(
                        lambda: active_adapter.get_underlying_quote(
                            config.market.underlying_symbol,
                            session_date=session_date,
                        ),
                        warning_sink=fetch_warnings,
                        event_name="underlying_quote",
                    ),
                    self._safe_fetch_market_event(
                        lambda: active_adapter.get_option_chain(
                            config.market.underlying_symbol,
                            config.market.weekly_expiry,
                            session_date=session_date,
                        ),
                        warning_sink=fetch_warnings,
                        event_name="option_chain",
                    ),
                    self._safe_fetch_market_event(
                        lambda: active_adapter.get_option_quote(
                            config.market.selected_contract_symbol,
                            session_date=session_date,
                        ),
                        warning_sink=fetch_warnings,
                        event_name="selected_contract_quote",
                    ),
                )
                if event is not None
            )
            stream_events = ()
            if config.broker.capture_stream_events:
                try:
                    stream_events = active_adapter.stream_ticks()
                except BrokerAdapterError as exc:
                    fetch_warnings.append(f"stream_ticks:{exc}")
            final_health = active_adapter.health()
        except BrokerAdapterError as exc:
            raise S23LivePaperIngressError(str(exc)) from exc
        finally:
            try:
                active_adapter.disconnect()
            except Exception:
                pass

        engine_events = self._sort_events(
            (
                *prelude_events,
                config_event,
                cost_event,
                *broker_events,
            )
        )
        all_observed_events = self._sort_events((*engine_events, *stream_events))

        dry_run_runner = self._dry_run_runner_factory(
            artifact_writer=self._artifact_writer(),
            thresholds=S23PaperIngressDryRunThresholds(
                max_stale_events=config.thresholds.max_stale_events,
                max_timing_drift_seconds=config.thresholds.max_timing_drift_seconds,
                max_missing_chains=config.thresholds.max_missing_chains,
                required_selected_contract_availability_ratio=(
                    config.thresholds.required_selected_contract_availability_ratio
                ),
                max_no_trade_rate=config.thresholds.max_no_trade_rate,
            ),
            max_quote_age=timedelta(seconds=config.thresholds.max_quote_age_seconds),
            source_mode=config.source_mode,
        )
        artifact_set = dry_run_runner.run_events(
            engine_events,
            source_path=prelude_jsonl,
            session_id=session_id,
        )

        broker_health_path = artifact_set.session_directory / "broker_health.json"
        normalized_events_path = artifact_set.session_directory / "normalized_events.jsonl"
        ingress_summary_path = artifact_set.session_directory / "ingress_summary.json"
        no_trade_or_order_plan_summary_path = (
            artifact_set.session_directory / "no_trade_or_order_plan_summary.json"
        )

        self._write_json(
            broker_health_path,
            {
                "artifact_version": _ARTIFACT_VERSION,
                "broker_name": final_health.broker_name,
                "provider": config.broker.provider,
                "selected_contract_symbol": config.market.selected_contract_symbol,
                "subscribed_symbols": subscribed_symbols,
                "initial_health": initial_health,
                "final_health": final_health,
                "uses_payload_fixture": config.broker.payload_fixture_path is not None,
                "fetch_warnings": tuple(fetch_warnings),
            },
        )
        self._write_normalized_events(normalized_events_path, all_observed_events)
        no_trade_or_order_plan_summary = self._build_no_trade_or_order_plan_summary(
            session_directory=artifact_set.session_directory,
            terminal_state=artifact_set.summary.terminal_state,
        )
        self._write_json(
            no_trade_or_order_plan_summary_path,
            no_trade_or_order_plan_summary,
        )

        summary = S23LivePaperIngressSummary(
            artifact_version=_ARTIFACT_VERSION,
            broker_name=final_health.broker_name,
            source_mode=config.source_mode,
            session_id=artifact_set.session_artifacts.session_id,
            session_date=artifact_set.summary.session_date,
            config_path=str(Path(config_path)),
            prelude_path=str(Path(prelude_jsonl)),
            broker_health_path=str(broker_health_path),
            normalized_events_path=str(normalized_events_path),
            selected_contract_symbol=config.market.selected_contract_symbol,
            weekly_expiry=config.market.weekly_expiry,
            terminal_state=artifact_set.summary.terminal_state.value,
            readiness_status=(
                artifact_set.summary.readiness_status.value
                if artifact_set.summary.readiness_status is not None
                else None
            ),
            operational_readiness=artifact_set.summary.operational_readiness.value,
            subscribed_symbols=subscribed_symbols,
            engine_event_count=len(engine_events),
            observed_stream_event_count=max(0, len(all_observed_events) - len(engine_events)),
            uses_broker_market_data=True,
            review_md_path=str(artifact_set.review_md_path),
            selected_contract_audit_path=str(artifact_set.selected_contract_audit_path),
            no_trade_or_order_plan_summary_path=str(no_trade_or_order_plan_summary_path),
            explicit_disclaimer=(
                "Broker market-data only: no order was placed, no fill was simulated, "
                "and no lifecycle monitoring occurred."
            ),
        )
        self._write_json(ingress_summary_path, summary)

        return S23LivePaperIngressArtifactSet(
            session_directory=artifact_set.session_directory,
            dry_run_artifacts=artifact_set,
            broker_health_path=broker_health_path,
            normalized_events_path=normalized_events_path,
            ingress_summary_path=ingress_summary_path,
            no_trade_or_order_plan_summary_path=no_trade_or_order_plan_summary_path,
            summary=summary,
        )

    def preflight(
        self,
        *,
        config_path: str | Path,
        prelude_jsonl: str | Path,
        session_id: str | None = None,
    ) -> S23LivePaperIngressPreflightSummary:
        config, prelude_events, session_date = self._load_config_and_prelude(
            config_path=config_path,
            prelude_jsonl=prelude_jsonl,
        )
        return self._build_preflight_summary(
            config=config,
            prelude_events=prelude_events,
            session_date=session_date,
            config_path=config_path,
            prelude_jsonl=prelude_jsonl,
            session_id=session_id,
        )

    def render_json(self, summary: S23LivePaperIngressSummary) -> str:
        return json.dumps(_normalize(summary), indent=2, sort_keys=True) + "\n"

    def render_preflight_json(
        self,
        summary: S23LivePaperIngressPreflightSummary,
    ) -> str:
        return json.dumps(_normalize(summary), indent=2, sort_keys=True) + "\n"

    def render_markdown(self, summary: S23LivePaperIngressSummary) -> str:
        lines = [
            "# S23 Fyers Live-Paper Ingress Summary",
            "",
            f"- broker: `{summary.broker_name}`",
            f"- source mode: `{summary.source_mode}`",
            f"- session id: `{summary.session_id}`",
            f"- session date: `{summary.session_date.isoformat()}`",
            f"- selected contract: `{summary.selected_contract_symbol}`",
            f"- weekly expiry: `{summary.weekly_expiry.isoformat()}`",
            f"- terminal state: `{summary.terminal_state}`",
            f"- readiness status: `{summary.readiness_status or 'unknown'}`",
            f"- operational readiness: `{summary.operational_readiness}`",
            "",
            "## Inputs",
            "",
            f"- config path: `{summary.config_path}`",
            f"- prelude path: `{summary.prelude_path}`",
            f"- subscribed symbols: `{', '.join(summary.subscribed_symbols)}`",
            "",
            "## Outputs",
            "",
            f"- broker health: `{summary.broker_health_path}`",
            f"- normalized events: `{summary.normalized_events_path}`",
            f"- selected contract audit: `{summary.selected_contract_audit_path}`",
            f"- session review: `{summary.review_md_path}`",
            f"- terminal summary: `{summary.no_trade_or_order_plan_summary_path}`",
            "",
            "## Safety Note",
            "",
            f"- {summary.explicit_disclaimer}",
            "- Kill switch is expected to remain enabled by default.",
            "- No broker order-placement path exists in this ingress runner.",
        ]
        return "\n".join(lines) + "\n"

    def render_preflight_markdown(
        self,
        summary: S23LivePaperIngressPreflightSummary,
    ) -> str:
        lines = [
            "# S23 Fyers Live-Paper Ingress Preflight",
            "",
            f"- provider: `{summary.provider}`",
            f"- session id: `{summary.session_id}`",
            f"- session date: `{summary.session_date.isoformat()}`",
            f"- local operator date: `{summary.current_local_date.isoformat()}`",
            f"- preflight status: `{summary.preflight_status}`",
            f"- can run: `{str(summary.can_run).lower()}`",
            f"- uses payload fixture: `{str(summary.uses_payload_fixture).lower()}`",
            f"- would connect to broker: `{str(summary.will_connect_to_broker).lower()}`",
            "",
            "## Scope Checks",
            "",
            f"- strategy: `{summary.strategy_code}`",
            f"- symbol: `{summary.symbol}`",
            f"- contract cycle: `{summary.contract_cycle}`",
            f"- mode: `{summary.mode}`",
            f"- paper mode enabled: `{str(summary.paper_mode_enabled).lower()}`",
            f"- no live orders allowed: `{str(summary.no_live_orders_allowed).lower()}`",
            f"- kill switch enabled: `{str(summary.kill_switch_enabled).lower()}`",
            f"- session kill switch active: `{str(summary.session_kill_switch_active).lower()}`",
            "",
            "## Market Inputs",
            "",
            f"- selected contract: `{summary.selected_contract_symbol}`",
            f"- weekly expiry: `{summary.weekly_expiry.isoformat()}`",
            f"- subscribed symbols: `{', '.join(summary.subscribed_symbols)}`",
            f"- required snapshots: `{', '.join(summary.required_snapshot_labels)}`",
            f"- present snapshots: `{', '.join(summary.present_snapshot_labels)}`",
            f"- credentials present: `{str(summary.credentials_present).lower()}`",
            f"- expected session directory: `{summary.expected_session_directory}`",
            "",
            "## Issues",
            "",
        ]
        if summary.issues:
            lines.extend(
                f"- `{issue.severity}` `{issue.code}`: {issue.message}"
                for issue in summary.issues
            )
        else:
            lines.append("- none")
        lines.extend(
            [
                "",
                "## Safety Note",
                "",
                f"- {summary.explicit_disclaimer}",
                "- Preflight only never connects to FYERS and never places orders.",
            ]
        )
        return "\n".join(lines) + "\n"

    def _build_adapter(self, config: S23LivePaperIngressConfig) -> BrokerAdapter:
        if config.broker.provider != "fyers":
            raise S23LivePaperIngressError(
                f"Unsupported broker provider for the first live-paper ingress rollout: "
                f"{config.broker.provider}"
            )
        if config.broker.payload_fixture_path:
            return FyersBrokerAdapter.from_payload_file(
                config.broker.payload_fixture_path,
                source_timezone=config.broker.timezone,
            )
        return FyersBrokerAdapter(source_timezone=config.broker.timezone)

    def _artifact_writer(self):
        from .artifacts import S23PaperSessionArtifactWriter

        return S23PaperSessionArtifactWriter(self._artifact_root)

    def _safe_fetch_market_event(
        self,
        fetcher,
        *,
        warning_sink: list[str],
        event_name: str,
    ):
        try:
            return fetcher()
        except BrokerAdapterError as exc:
            warning_sink.append(f"{event_name}:{exc}")
            return None

    def _validate_prelude_events(self, events: tuple[PaperEvent, ...]) -> None:
        if not events:
            raise S23LivePaperIngressError("Prelude event stream is empty.")
        session_dates = {event.envelope.session_date for event in events}
        if len(session_dates) != 1:
            raise S23LivePaperIngressError(
                "Prelude event stream must contain exactly one session date."
            )
        invalid_types = {
            event.envelope.event_type for event in events
            if event.envelope.event_type not in _PRELUDE_ALLOWED_EVENT_TYPES
        }
        if invalid_types:
            joined = ", ".join(sorted(event_type.value for event_type in invalid_types))
            raise S23LivePaperIngressError(
                "Prelude JSONL must contain only normalized non-broker planning events. "
                f"Found unsupported event types: {joined}"
            )

    def _load_config_and_prelude(
        self,
        *,
        config_path: str | Path,
        prelude_jsonl: str | Path,
    ) -> tuple[S23LivePaperIngressConfig, tuple[PaperEvent, ...], date | None]:
        config = S23LivePaperIngressConfig.from_yaml(config_path)
        prelude_events = self._loader.load_jsonl(prelude_jsonl)
        session_date = prelude_events[0].envelope.session_date if prelude_events else None
        return config, prelude_events, session_date

    def _require_safe_preflight(
        self,
        *,
        config_path: str | Path,
        prelude_jsonl: str | Path,
        session_id: str | None,
        loaded: tuple[S23LivePaperIngressConfig, tuple[PaperEvent, ...], date | None] | None = None,
        adapter_supplied: bool = False,
    ) -> S23LivePaperIngressPreflightSummary:
        if loaded is None:
            summary = self.preflight(
                config_path=config_path,
                prelude_jsonl=prelude_jsonl,
                session_id=session_id,
            )
        else:
            config, prelude_events, session_date = loaded
            summary = self._build_preflight_summary(
                config=config,
                prelude_events=prelude_events,
                session_date=session_date,
                config_path=config_path,
                prelude_jsonl=prelude_jsonl,
                session_id=session_id,
                adapter_supplied=adapter_supplied,
            )
        if not summary.can_run:
            blocking = [
                f"{issue.code}: {issue.message}"
                for issue in summary.issues
                if issue.severity == "NO_GO"
            ]
            raise S23LivePaperIngressError(
                "Live-paper ingress preflight failed: " + "; ".join(blocking)
            )
        return summary

    def _build_preflight_summary(
        self,
        *,
        config: S23LivePaperIngressConfig,
        prelude_events: tuple[PaperEvent, ...],
        session_date: date | None,
        config_path: str | Path,
        prelude_jsonl: str | Path,
        session_id: str | None,
        adapter_supplied: bool = False,
    ) -> S23LivePaperIngressPreflightSummary:
        issues = self._collect_preflight_issues(
            config=config,
            prelude_events=prelude_events,
            session_date=session_date,
            adapter_supplied=adapter_supplied,
        )
        current_local_date = datetime.now(ZoneInfo(config.broker.timezone)).date()
        effective_session_date = session_date or current_local_date
        required_labels = self._required_snapshot_labels(config, effective_session_date)
        present_labels = tuple(
            snapshot.value
            for snapshot in self._present_snapshot_labels(prelude_events)
        )
        resolved_session_id = session_id or self._derive_session_id(
            strategy_code=config.paper.strategy_code,
            symbol=config.paper.symbol,
            contract_cycle=config.paper.contract_cycle,
            mode=config.paper.mode,
            session_date=effective_session_date,
        )
        expected_session_directory = (
            self._artifact_root / effective_session_date.isoformat() / resolved_session_id
        )
        preflight_status = self._derive_preflight_status(issues)
        return S23LivePaperIngressPreflightSummary(
            artifact_version=_ARTIFACT_VERSION,
            broker_name=config.broker.provider,
            provider=config.broker.provider,
            source_mode=config.source_mode,
            session_id=resolved_session_id,
            session_date=effective_session_date,
            current_local_date=current_local_date,
            session_date_matches_local_date=effective_session_date == current_local_date,
            config_path=str(Path(config_path)),
            prelude_path=str(Path(prelude_jsonl)),
            expected_session_directory=str(expected_session_directory),
            strategy_code=config.paper.strategy_code,
            symbol=config.paper.symbol,
            contract_cycle=config.paper.contract_cycle,
            mode=config.paper.mode,
            paper_mode_enabled=config.paper.paper_mode_enabled,
            no_live_orders_allowed=config.paper.no_live_orders_allowed,
            kill_switch_enabled=config.paper.kill_switch_enabled,
            session_kill_switch_active=config.paper.session_kill_switch_active,
            selected_contract_symbol=config.market.selected_contract_symbol,
            weekly_expiry=config.market.weekly_expiry,
            subscribed_symbols=(
                config.market.underlying_symbol,
                config.market.selected_contract_symbol,
            ),
            required_snapshot_labels=tuple(label.value for label in required_labels),
            present_snapshot_labels=present_labels,
            credentials_present=self._credentials_present(config),
            uses_payload_fixture=config.broker.payload_fixture_path is not None,
            will_connect_to_broker=(
                adapter_supplied or config.broker.payload_fixture_path is None
            ),
            preflight_status=preflight_status,
            can_run=preflight_status != "NO_GO",
            issues=issues,
            explicit_disclaimer=(
                "Preflight validates S23 paper ingress safety only. It never connects "
                "to FYERS, never places orders, and never enables fill or lifecycle "
                "simulation."
            ),
        )

    def _collect_preflight_issues(
        self,
        *,
        config: S23LivePaperIngressConfig,
        prelude_events: tuple[PaperEvent, ...],
        session_date: date | None,
        adapter_supplied: bool = False,
    ) -> tuple[S23LivePaperIngressPreflightIssue, ...]:
        issues: list[S23LivePaperIngressPreflightIssue] = []
        if config.broker.provider != "fyers":
            issues.append(
                self._issue(
                    "unsupported_broker_provider",
                    "Live-paper ingress preflight currently supports broker.provider=fyers only.",
                )
            )
        if not config.paper.no_live_orders_allowed:
            issues.append(
                self._issue(
                    "live_order_block_disabled",
                    "Live-paper ingress requires no_live_orders_allowed=true.",
                )
            )
        if not config.paper.kill_switch_enabled:
            issues.append(
                self._issue(
                    "kill_switch_default_disabled",
                    "Live-paper ingress requires kill_switch_enabled=true by default.",
                )
            )
        if config.paper.session_kill_switch_active:
            issues.append(
                self._issue(
                    "session_kill_switch_active",
                    "Live-paper ingress cannot start while session_kill_switch_active=true.",
                )
            )
        if config.paper.strategy_code != "S23":
            issues.append(
                self._issue(
                    "unsupported_strategy",
                    "Live-paper ingress is scoped to S23 only.",
                )
            )
        if config.paper.symbol != "NIFTY":
            issues.append(
                self._issue(
                    "unsupported_symbol",
                    "Live-paper ingress is scoped to NIFTY only.",
                )
            )
        if config.market.underlying_symbol != "NIFTY":
            issues.append(
                self._issue(
                    "unsupported_underlying_symbol",
                    "Live-paper ingress requires market.underlying_symbol=NIFTY.",
                )
            )
        if config.paper.contract_cycle != "WEEKLY":
            issues.append(
                self._issue(
                    "unsupported_contract_cycle",
                    "Live-paper ingress is scoped to weekly options only.",
                )
            )
        if config.paper.mode != "paper":
            issues.append(
                self._issue(
                    "non_paper_mode",
                    "Live-paper ingress requires mode=paper.",
                )
            )
        if not config.paper.paper_mode_enabled:
            issues.append(
                self._issue(
                    "paper_mode_disabled",
                    "Live-paper ingress requires paper_mode_enabled=true.",
                )
            )
        if not config.paper.same_day_square_off_only:
            issues.append(
                self._issue(
                    "same_day_only_disabled",
                    "Live-paper ingress requires same_day_square_off_only=true.",
                )
            )
        if not config.market.selected_contract_symbol:
            issues.append(
                self._issue(
                    "missing_selected_contract_symbol",
                    "Live-paper ingress requires market.selected_contract_symbol.",
                )
            )
        if config.broker.payload_fixture_path is None and not adapter_supplied:
            try:
                FyersCredentials.from_env()
            except BrokerCredentialsError as exc:
                issues.append(
                    self._issue(
                        "missing_broker_credentials",
                        str(exc),
                    )
                )
        else:
            issues.append(
                self._issue(
                    "payload_fixture_mode_enabled",
                    "Payload fixture mode is enabled; preflight is safe, but this is not a live FYERS data run.",
                    severity="WARNING",
                )
            )

        if session_date is not None:
            local_date = datetime.now(ZoneInfo(config.broker.timezone)).date()
            if config.broker.payload_fixture_path is None and session_date != local_date:
                issues.append(
                    self._issue(
                        "session_date_mismatch_with_local_clock",
                        "Prelude session_date does not match the local operator date in the broker timezone.",
                        severity="WARNING",
                    )
                )
        issues.extend(
            self._collect_prelude_issues(
                config=config,
                prelude_events=prelude_events,
                session_date=session_date,
            )
        )
        return tuple(issues)

    def _collect_prelude_issues(
        self,
        *,
        config: S23LivePaperIngressConfig,
        prelude_events: tuple[PaperEvent, ...],
        session_date: date | None,
    ) -> tuple[S23LivePaperIngressPreflightIssue, ...]:
        issues: list[S23LivePaperIngressPreflightIssue] = []
        if not prelude_events:
            issues.append(
                self._issue(
                    "empty_prelude_stream",
                    "Prelude JSONL is empty.",
                )
            )
            return tuple(issues)
        session_dates = {event.envelope.session_date for event in prelude_events}
        if len(session_dates) != 1:
            issues.append(
                self._issue(
                    "mixed_session_dates",
                    "Prelude JSONL must contain exactly one session date.",
                )
            )
        invalid_types = {
            event.envelope.event_type
            for event in prelude_events
            if event.envelope.event_type not in _PRELUDE_ALLOWED_EVENT_TYPES
        }
        if invalid_types:
            issues.append(
                self._issue(
                    "invalid_prelude_event_types",
                    "Prelude JSONL contains unsupported event types: "
                    + ", ".join(
                        sorted(event_type.value for event_type in invalid_types)
                    ),
                )
            )
        if session_date is None:
            issues.append(
                self._issue(
                    "missing_session_date",
                    "Prelude stream does not expose a usable session date.",
                )
            )
            return tuple(issues)
        event_types = {event.envelope.event_type for event in prelude_events}
        required_event_types = {
            PaperEventType.CALENDAR_CONTEXT,
            PaperEventType.MONTHLY_STATUS_INPUT,
            PaperEventType.TRADE_PLAN_INPUT,
        }
        missing_event_types = sorted(
            required_event_type.value
            for required_event_type in required_event_types
            if required_event_type not in event_types
        )
        if missing_event_types:
            issues.append(
                self._issue(
                    "missing_prelude_event_types",
                    "Prelude JSONL is missing required event types: "
                    + ", ".join(missing_event_types),
                )
            )
        required_labels = set(self._required_snapshot_labels(config, session_date))
        present_labels = self._present_snapshot_labels(prelude_events)
        missing_labels = sorted(
            label.value for label in required_labels if label not in present_labels
        )
        if missing_labels:
            issues.append(
                self._issue(
                    "missing_required_snapshots",
                    "Prelude JSONL is missing required underlying snapshots: "
                    + ", ".join(missing_labels),
                )
            )
        return tuple(issues)

    def _required_snapshot_labels(
        self,
        config: S23LivePaperIngressConfig,
        session_date: date,
    ) -> tuple[SnapshotLabel, ...]:
        config_event = config.build_paper_session_config_event(
            session_date=session_date,
            source_id="preflight",
            timezone=config.broker.timezone,
        )
        return required_snapshot_labels_for_config(config_event)

    def _present_snapshot_labels(
        self,
        prelude_events: tuple[PaperEvent, ...],
    ) -> tuple[SnapshotLabel, ...]:
        labels = []
        for event in prelude_events:
            if event.envelope.event_type is PaperEventType.UNDERLYING_SNAPSHOT:
                labels.append(event.snapshot_label)
        return tuple(dict.fromkeys(labels))

    def _credentials_present(self, config: S23LivePaperIngressConfig) -> bool:
        if config.broker.payload_fixture_path is not None:
            return False
        try:
            from tfis.brokers.fyers import FyersCredentials

            FyersCredentials.from_env()
        except BrokerCredentialsError:
            return False
        return True

    def _derive_preflight_status(
        self,
        issues: tuple[S23LivePaperIngressPreflightIssue, ...],
    ) -> str:
        severities = {issue.severity for issue in issues}
        if "NO_GO" in severities:
            return "NO_GO"
        if "WARNING" in severities:
            return "WARNING"
        return "PASS"

    def _derive_session_id(
        self,
        *,
        strategy_code: str,
        symbol: str,
        contract_cycle: str,
        mode: str,
        session_date: date,
    ) -> str:
        return (
            f"{strategy_code.lower()}-"
            f"{symbol.lower()}-"
            f"{contract_cycle.lower()}-"
            f"{mode.lower()}-"
            f"{session_date.isoformat()}"
        )

    def _issue(
        self,
        code: str,
        message: str,
        *,
        severity: str = "NO_GO",
    ) -> S23LivePaperIngressPreflightIssue:
        return S23LivePaperIngressPreflightIssue(
            code=code,
            message=message,
            severity=severity,
        )

    def _sort_events(self, events: tuple[PaperEvent, ...]) -> tuple[PaperEvent, ...]:
        return tuple(
            sorted(
                events,
                key=lambda event: (
                    event.envelope.captured_at,
                    event.envelope.effective_timestamp,
                    event.envelope.source_sequence or 0,
                    event.envelope.event_type.value,
                ),
            )
        )

    def _write_normalized_events(
        self,
        path: Path,
        events: tuple[PaperEvent, ...],
    ) -> None:
        serialized = "\n".join(
            json.dumps(self._serialize_event(event), sort_keys=True)
            for event in events
        )
        self._atomic_write_text(path, serialized + ("\n" if serialized else ""))

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
        body = _normalize(event)
        body.pop("envelope", None)
        payload["payload"] = body
        return payload

    def _build_no_trade_or_order_plan_summary(
        self,
        *,
        session_directory: Path,
        terminal_state: PaperSessionState,
    ) -> dict[str, Any]:
        decision_summary = self._load_json(session_directory / "decision_summary.json")
        payload: dict[str, Any] = {
            "artifact_version": _ARTIFACT_VERSION,
            "terminal_state": terminal_state.value,
            "session_id": decision_summary.get("session_id"),
            "strategy_code": decision_summary.get("strategy_code"),
            "readiness_status": decision_summary.get("readiness_status"),
        }
        if terminal_state is PaperSessionState.ORDER_PLANNED:
            payload["summary_kind"] = "order_plan"
            payload["artifact_path"] = str(session_directory / "paper_order_plan.json")
            payload["artifact"] = self._load_json(session_directory / "paper_order_plan.json")
        elif terminal_state is PaperSessionState.NO_TRADE:
            payload["summary_kind"] = "no_trade"
            payload["artifact_path"] = str(session_directory / "no_trade_summary.json")
            payload["artifact"] = self._load_json(session_directory / "no_trade_summary.json")
        else:
            payload["summary_kind"] = "abort"
            payload["artifact_path"] = str(session_directory / "abort_summary.json")
            payload["artifact"] = self._load_json(session_directory / "abort_summary.json")
        return payload

    def _load_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Any) -> None:
        self._atomic_write_text(path, json.dumps(_normalize(payload), indent=2, sort_keys=True) + "\n")

    def _atomic_write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.tmp")
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(path)


def _session_datetime(session_date: date, clock_time: time, timezone: str) -> datetime:
    tzinfo = ZoneInfo(timezone)
    return datetime.combine(session_date, clock_time, tzinfo=tzinfo)


def _parse_date_required(value: Any, *, field_name: str) -> date:
    if value in (None, ""):
        raise S23LivePaperIngressError(f"Missing required config field: {field_name}")
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _normalize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return getattr(value, "value")
    return value
