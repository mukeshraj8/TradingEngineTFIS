from __future__ import annotations

import json
import time
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import yaml

from tfis.broker.authentication import BrokerAuthenticationResult, BrokerSessionStatus
from tfis.broker.authentication.fyers import FyersAuthenticationAdapter
from tfis.accounting import (
    AccountingQuality,
    ChargeEvidence,
    InstrumentDimensions,
    MarkSnapshot,
    PnLFactBuilder,
    TradeFactBuilder,
    build_accounting_result,
)
from tfis.execution_intent import IntentValidationDecision
from tfis.execution_intent.reports import build_validation_input
from tfis.execution_intent.validation import ExecutionIntentValidator
from tfis.fyers_read_only import FyersReadOnlyAdapter, FyersReadOnlyStatus, classify_monthly_expiries, normalize_symbol_master_rows
from tfis.internal_paper import (
    AccountCoordinator,
    ClientOrder,
    DeterministicExecutionScenarioDefinition,
    DeterministicInternalPaperAdapter,
    DeterministicMarketEvidence,
    InternalPaperExecutionScenario,
    InternalPaperOrderState,
    SimulatedPaperAccountSnapshot,
    create_creation_event,
    margin_after_reservation,
)
from tfis.internal_position import PositionCycleCoordinator
from tfis.persistence import (
    PersistenceDatabase,
    PersistenceRepositories,
    UnitOfWork,
    apply_migrations,
    assess_recovery,
    canonical_hash,
    from_canonical_json,
    run_integrity_scan,
)
from tfis.read_models.operations.models import OperationalReadModel
from tfis.read_models.operations.projection import build_unified_dashboard_projection
from tfis.runtime import ProcessLockError, ProcessLockHandle, acquire_process_lock
from tfis.runtime.process_lock import _process_exists, _process_matches_payload, _read_lock_payload
from tfis.runtime.coordination import RuntimeSubscriptionIndex

from .live_contract_selection import (
    build_authoritative_historical_selection,
    build_authoritative_live_selection,
    supports_authoritative_live_selection,
)
from .fast_track_development import (
    _action_explanation_fact,
    _build_account_snapshot,
    _build_entry_intent,
    _build_internal_paper_grant,
    build_explanation_facts,
)
from .registry import EnabledStrategyInstance, EnabledStrategyRegistry, load_enabled_strategy_registry
from .session_reconstruction import StrategyTimingPolicy, reconstruct_option_selling_entry, selected_contract_is_authoritative
from .s22_stock_fast_track import build_s22_stock_historical_selection


IST = ZoneInfo("Asia/Calcutta")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
ORPT_TIME = time(9, 24, 59, 400000)
RC_TIME = time(9, 29, 59, 400000)
EOD_DECISION = time(15, 0)
RULE_MATRIX_VERSION = "tfis_authoritative_workbook_rule_matrix.v1"
DEFAULT_HEALTH = {"status": "UNKNOWN", "broker_order_authority": "NONE"}
DEFAULT_AUTH_REVALIDATE_INTERVAL_SECONDS = 300.0
DEFAULT_RECOVERY_REFRESH_INTERVAL_SECONDS = 60.0
DEFAULT_OPTION_CHAIN_REFRESH_INTERVAL_SECONDS = 60.0
DEFAULT_SNAPSHOT_WRITE_INTERVAL_SECONDS = 15.0
DEFAULT_CHECKPOINT_WRITE_INTERVAL_SECONDS = 30.0
DEFAULT_REPORT_WRITE_INTERVAL_SECONDS = 300.0
DEFAULT_PERFORMANCE_RETENTION_CYCLES = 240
SYMBOL_MASTER_CACHE_FILENAME = "nsefo_symbol_master_cache.json"
REQUIRED_SUPERVISOR_STATES = (
    "CREATED",
    "PREFLIGHT",
    "RECOVERY_CHECK",
    "BROKER_DIAGNOSTICS",
    "PREMARKET_PREPARING",
    "WAITING_FOR_MARKET",
    "LIVE_OBSERVATION",
    "WAITING_FOR_ORPT",
    "WAITING_FOR_RC",
    "ENTRY_PROCESSING",
    "POSITION_MONITORING",
    "EOD_PROCESSING",
    "CHECKPOINTING",
    "SHUTTING_DOWN",
    "STOPPED",
    "DEGRADED",
    "BLOCKED",
    "LATE_START_NO_NEW_ENTRY",
)


@dataclass(frozen=True, slots=True)
class ContinuousSupervisorConfig:
    repo_root: Path
    registry_path: Path
    report_dir: Path
    state_root: Path
    dashboard_output_root: Path
    db_path: Path
    dashboard_port: int = 8766
    poll_seconds: float = 5.0
    max_iterations: int = 0
    until_time: time = MARKET_CLOSE
    session_date: date | None = None
    auth_revalidate_interval_seconds: float = DEFAULT_AUTH_REVALIDATE_INTERVAL_SECONDS
    recovery_refresh_interval_seconds: float = DEFAULT_RECOVERY_REFRESH_INTERVAL_SECONDS
    option_chain_refresh_interval_seconds: float = DEFAULT_OPTION_CHAIN_REFRESH_INTERVAL_SECONDS
    snapshot_write_interval_seconds: float = DEFAULT_SNAPSHOT_WRITE_INTERVAL_SECONDS
    checkpoint_write_interval_seconds: float = DEFAULT_CHECKPOINT_WRITE_INTERVAL_SECONDS
    report_write_interval_seconds: float = DEFAULT_REPORT_WRITE_INTERVAL_SECONDS
    performance_retention_cycles: int = DEFAULT_PERFORMANCE_RETENTION_CYCLES


@dataclass(frozen=True, slots=True)
class ContinuousSupervisorRunResult:
    verdict: str
    session_id: str
    report_dir: Path
    snapshot_json: Path
    heartbeat_json: Path
    db_path: Path
    iterations: int
    final_state: str
    files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompleteSessionPreflightResult:
    verdict: str
    reasons: tuple[str, ...]
    report_path: Path


@dataclass(frozen=True, slots=True)
class AuthoritativeReadinessProjectionResult:
    verdict: str
    report_path: Path
    operator_package_json: Path
    operator_package_md: Path


@dataclass(frozen=True, slots=True)
class StageMetric:
    stage: str
    status: str
    duration_ms: float
    started_at: str
    ended_at: str
    scope: str = "SESSION"
    details: Mapping[str, Any] | None = None


class SubscriptionOwner:
    def __init__(self) -> None:
        self._underlying: dict[str, dict[str, set[str]]] = {}
        self._contracts: dict[str, dict[str, set[str]]] = {}

    def pin_underlying(self, strategy_instance_id: str, symbol: str, *, reason: str) -> None:
        self._underlying.setdefault(symbol, {}).setdefault(strategy_instance_id, set()).add(reason)

    def pin_contract(self, strategy_instance_id: str, contract: str, *, reason: str) -> None:
        self._contracts.setdefault(contract, {}).setdefault(strategy_instance_id, set()).add(reason)

    def release_strategy(self, strategy_instance_id: str) -> None:
        for mapping in (self._underlying, self._contracts):
            empty: list[str] = []
            for symbol, owners in mapping.items():
                owners.pop(strategy_instance_id, None)
                if not owners:
                    empty.append(symbol)
            for symbol in empty:
                del mapping[symbol]

    def runtime_index(self) -> RuntimeSubscriptionIndex:
        index = RuntimeSubscriptionIndex()
        for symbol, owners in sorted(self._underlying.items()):
            for strategy_instance_id in sorted(owners):
                index.add_strategy(strategy_instance_id, underlying=symbol)
        for contract, owners in sorted(self._contracts.items()):
            for strategy_instance_id in sorted(owners):
                index.add_strategy(strategy_instance_id, contract=contract)
        return index

    def to_dict(self) -> dict[str, Any]:
        return {
            "underlyings": {
                symbol: {
                    strategy_instance_id: sorted(reasons)
                    for strategy_instance_id, reasons in sorted(owners.items())
                }
                for symbol, owners in sorted(self._underlying.items())
            },
            "contracts": {
                contract: {
                    strategy_instance_id: sorted(reasons)
                    for strategy_instance_id, reasons in sorted(owners.items())
                }
                for contract, owners in sorted(self._contracts.items())
            },
            "duplicate_provider_subscriptions": False,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SubscriptionOwner":
        owner = cls()
        for symbol, owners in (payload.get("underlyings") or {}).items():
            if not isinstance(owners, Mapping):
                continue
            for strategy_instance_id, reasons in owners.items():
                if not isinstance(reasons, list):
                    continue
                for reason in reasons:
                    owner.pin_underlying(str(strategy_instance_id), str(symbol), reason=str(reason))
        for contract, owners in (payload.get("contracts") or {}).items():
            if not isinstance(owners, Mapping):
                continue
            for strategy_instance_id, reasons in owners.items():
                if not isinstance(reasons, list):
                    continue
                for reason in reasons:
                    owner.pin_contract(str(strategy_instance_id), str(contract), reason=str(reason))
        return owner


class UnifiedInternalPaperSupervisor:
    def __init__(
        self,
        config: ContinuousSupervisorConfig,
        *,
        now_provider: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        auth_factory: Callable[[Path], FyersAuthenticationAdapter] | None = None,
    ) -> None:
        self.config = config
        self.now_provider = now_provider or (lambda: datetime.now(tz=IST))
        self.sleep_fn = sleep_fn or time_module.sleep
        self.auth_factory = auth_factory or (
            lambda root: FyersAuthenticationAdapter(tfis_root=root, logical_account_ref="unified-internal-paper-supervisor")
        )
        self.registry = load_enabled_strategy_registry(config.registry_path)
        self.session_date = config.session_date or self.now_provider().date()
        self.session_id = f"NSE:{self.session_date.isoformat()}:UNIFIED_INTERNAL_PAPER"
        self._session_started_at = self.now_provider()
        self.session_file_stem = self.session_id.replace(":", "_")
        self.subscription_owner = SubscriptionOwner()
        self.lock_handle: ProcessLockHandle | None = None
        self.iterations = 0
        self._projection: dict[str, Any] | None = None
        self._latest_dashboard_health = DEFAULT_HEALTH
        self._checkpoint_path = self.config.state_root / f"{self.session_file_stem}.checkpoint.json"
        self._heartbeat_path = self.config.state_root / "heartbeat.json"
        self._pid_metadata_path = self.config.state_root / "continuous_unified_supervisor.pid.json"
        self._stop_signal_path = self.config.state_root / "continuous_unified_supervisor.stop"
        self._symbol_master_cache_path = self.config.state_root / SYMBOL_MASTER_CACHE_FILENAME
        self._underlying_symbols = _load_underlying_symbols(self.config.repo_root)
        self._timeline: list[dict[str, Any]] = []
        self._late_start_mode = False
        self._latest_auth: BrokerAuthenticationResult | None = None
        self._latest_auth_checked_at: datetime | None = None
        self._last_projection_hash = ""
        self._cached_nsefo_records: tuple[Any, ...] = _read_symbol_master_cache(self._symbol_master_cache_path)
        self._cached_option_chain_by_underlying: dict[str, dict[str, Any]] = {}
        self._cached_recovery_snapshot_value: dict[str, Any] | None = None
        self._cached_recovery_snapshot_at: datetime | None = None
        self._latest_cycle_metrics: list[StageMetric] = []
        self._cycle_metrics_history: list[dict[str, Any]] = []
        self._last_snapshot_write_at: datetime | None = None
        self._last_snapshot_projection_hash: str | None = None
        self._last_checkpoint_write_at: datetime | None = None
        self._last_checkpoint_semantic_hash: str | None = None
        self._last_report_write_at: datetime | None = None
        self._last_report_state: str | None = None
        self._selected_contract_history: dict[str, list[dict[str, Any]]] = {}
        self._paper_execution_state: dict[str, dict[str, Any]] = {}
        self._paper_account_snapshots: dict[str, dict[str, Any]] = {}
        self._ledger_recovery_errors: list[str] = []
        self._restore_checkpoint_if_available()

    def run(self) -> ContinuousSupervisorRunResult:
        self._acquire_process_lock()
        self.config.report_dir.mkdir(parents=True, exist_ok=True)
        self.config.state_root.mkdir(parents=True, exist_ok=True)
        self.config.dashboard_output_root.mkdir(parents=True, exist_ok=True)
        self._restore_checkpoint_if_available()
        final_state = "CREATED"
        next_poll_deadline_monotonic = time_module.monotonic()
        try:
            while True:
                self.iterations += 1
                now = self.now_provider()
                if self._stop_signal_path.exists():
                    final_state = "STOPPED"
                    self._append_timeline("SHUTTING_DOWN", "STOP_SIGNAL_DETECTED", now=now)
                    break
                final_state = self._run_once(now)
                if final_state in {"STOPPED", "BLOCKED"}:
                    break
                if self.config.max_iterations and self.iterations >= self.config.max_iterations:
                    break
                if now.timetz().replace(tzinfo=None) >= self.config.until_time:
                    break
                next_poll_deadline_monotonic += self.config.poll_seconds
                sleep_seconds = _next_sleep_seconds(
                    now=self.now_provider(),
                    current_monotonic=time_module.monotonic(),
                    next_poll_deadline_monotonic=next_poll_deadline_monotonic,
                    late_start=self._late_start_mode,
                )
                if sleep_seconds > 0:
                    self.sleep_fn(sleep_seconds)
            final_now = self.now_provider()
            if final_state not in {"STOPPED", "BLOCKED"} and final_now.timetz().replace(tzinfo=None) >= self.config.until_time:
                final_state = "STOPPED"
            elif final_state not in {"STOPPED", "BLOCKED"}:
                final_state = self._state_for_time(final_now)
            self._write_reports(final_now, final_state, stage_metrics=[])
            return ContinuousSupervisorRunResult(
                verdict="TFIS_CONTINUOUS_SUPERVISOR_CONDITIONAL",
                session_id=self.session_id,
                report_dir=self.config.report_dir,
                snapshot_json=self.config.dashboard_output_root / "api" / "snapshot.json",
                heartbeat_json=self._heartbeat_path,
                db_path=self.config.db_path,
                iterations=self.iterations,
                final_state=final_state,
                files=tuple(sorted(path.name for path in self.config.report_dir.iterdir() if path.is_file())),
            )
        finally:
            self._write_heartbeat(state="STOPPED", now=self.now_provider())
            try:
                self._stop_signal_path.unlink()
            except FileNotFoundError:
                pass
            if self.lock_handle is not None:
                self.lock_handle.release()

    def _run_once(self, now: datetime) -> str:
        self._timeline = []
        cycle_started_at = time_module.monotonic()
        stage_metrics: list[StageMetric] = []
        self._write_heartbeat(state="PREFLIGHT", now=now)
        self._append_timeline("PREFLIGHT", "STARTED", now=now)
        self._record_stage(stage_metrics, "cycle_start", "EXECUTED", started_at=now, ended_at=now)

        self._write_heartbeat(state="BROKER_DIAGNOSTICS", now=now)
        auth_result = self._auth_result_for_cycle(now=now, stage_metrics=stage_metrics)
        self._latest_auth = auth_result
        self._append_timeline("BROKER_DIAGNOSTICS", auth_result.status.value, now=now)

        late_start = self._detect_late_start(now)
        if late_start:
            self._late_start_mode = True

        self._write_heartbeat(state="LIVE_OBSERVATION", now=now)
        live_context = self._collect_live_context(now, auth_result, stage_metrics=stage_metrics)
        final_state = self._state_for_time(now)
        projection_started_at = self.now_provider()
        projection = self._build_projection(now, live_context=live_context, final_state=final_state)
        self._record_stage(stage_metrics, "dashboard_projection_build", "EXECUTED", started_at=projection_started_at, ended_at=self.now_provider())
        self._projection = projection
        self._last_projection_hash = projection["projection_hash"]
        self._latest_dashboard_health = {
            "status": projection["command_centre"]["system_state"],
            "broker_order_authority": projection["system"]["broker_order_authority"],
            "projection_hash": projection["projection_hash"],
        }
        self._write_heartbeat(state="CHECKPOINTING", now=now)
        self._write_dashboard_snapshot(projection, now=now, stage_metrics=stage_metrics)
        self._append_timeline(final_state, "CAPTURED", now=now, projection_hash=projection["projection_hash"])
        self._persist_runtime_state(now=now, final_state=final_state, projection=projection, live_context=live_context, stage_metrics=stage_metrics)
        cycle_ended_at = self.now_provider()
        self._record_stage(
            stage_metrics,
            "cycle_total",
            "EXECUTED",
            started_at=now,
            ended_at=cycle_ended_at,
            details={
                "poll_interval_seconds": self.config.poll_seconds,
                "cycle_duration_ms": round((time_module.monotonic() - cycle_started_at) * 1000.0, 3),
            },
        )
        self._latest_cycle_metrics = stage_metrics
        self._write_heartbeat(state=final_state, now=self.now_provider())
        self._write_reports(now, final_state, stage_metrics=stage_metrics)
        self._append_cycle_history(now=now, final_state=final_state, stage_metrics=stage_metrics)
        return final_state

    def _collect_live_context(
        self,
        now: datetime,
        auth_result: BrokerAuthenticationResult,
        *,
        stage_metrics: list[StageMetric],
    ) -> dict[str, Any]:
        live_context: dict[str, Any] = {
            "market_session_state": _market_session_state(now),
            "read_status": auth_result.status.value,
            "underlying_reads": {},
            "selected_contract_reads": {},
            "option_chains": {},
            "continuity": {},
            "timing": {},
            "account_risk_matrix": {},
            "recovery": {},
        }
        self.subscription_owner = SubscriptionOwner.from_dict(self._load_checkpoint_payload().get("subscription_owner", {}))
        underlying_symbols = _load_underlying_symbols(self.config.repo_root)
        for instance in self.registry.enabled_instances:
            self.subscription_owner.release_strategy(instance.strategy_instance_id)
            symbol = _resolve_underlying_symbol(instance.symbol, underlying_symbols)
            self.subscription_owner.pin_underlying(instance.strategy_instance_id, symbol, reason="UNDERLYING_OBSERVATION")

        live_context["timing"] = _timing_matrix(self.registry, now=now, late_start=self._late_start_mode)
        live_context["recovery"] = self._recovery_snapshot(now=now, stage_metrics=stage_metrics)

        if auth_result.status is not BrokerSessionStatus.AUTHENTICATED or auth_result.session is None:
            for instance in self.registry.enabled_instances:
                live_context["continuity"][instance.strategy_instance_id] = {
                    "status": "AUTHENTICATION_FAILED",
                    "selected_contract": None,
                    "evidence": "NO_BROKER_SESSION",
                }
            return live_context

        adapter = FyersReadOnlyAdapter.from_validated_session(
            auth_result.session,
            now_provider=lambda: self.now_provider(),
            timeout_seconds=1.0,
            max_retries=0,
        )
        call_started_at = self.now_provider()
        quotes = adapter.fetch_quotes(tuple(sorted(set(underlying_symbols.values()))))
        self._record_stage(
            stage_metrics,
            "provider_underlying_quotes",
            "EXECUTED",
            started_at=call_started_at,
            ended_at=self.now_provider(),
            details={"symbol_count": len(set(underlying_symbols.values())), "status": quotes.status.value},
        )
        live_context["underlying_reads"] = quotes.to_dict()
        if self._cached_nsefo_records:
            records = self._cached_nsefo_records
            self._record_stage(
                stage_metrics,
                "provider_symbol_master_nsefo",
                "CACHED",
                started_at=now,
                ended_at=now,
                details={"record_count": len(records)},
            )
        else:
            call_started_at = self.now_provider()
            nsefo_master = adapter.fetch_symbol_master("NSEFO")
            self._record_stage(
                stage_metrics,
                "provider_symbol_master_nsefo",
                "EXECUTED",
                started_at=call_started_at,
                ended_at=self.now_provider(),
                details={"status": nsefo_master.status.value},
            )
            if nsefo_master.status is FyersReadOnlyStatus.SUCCESS:
                records = tuple(nsefo_master.payload)
                self._cached_nsefo_records = records
                _write_symbol_master_cache(
                    self._symbol_master_cache_path,
                    exchange="NSEFO",
                    source_version=str(getattr(records[0], "source_version", "FYERS_READ_ONLY_CACHE")) if records else "FYERS_READ_ONLY_CACHE",
                    downloaded_at=getattr(records[0], "downloaded_at", self.now_provider()) if records else self.now_provider(),
                    records=records,
                )
            else:
                records = self._cached_nsefo_records

        for instance in self.registry.enabled_instances:
            continuity = self._continuity_for_instance(
                instance=instance,
                now=now,
                adapter=adapter,
                instrument_records=records,
                stage_metrics=stage_metrics,
            )
            live_context["continuity"][instance.strategy_instance_id] = continuity
            live_context["selected_contract_reads"][instance.strategy_instance_id] = list(
                self._selected_contract_history.get(instance.strategy_instance_id, [])
            )
            selected_contract = continuity.get("selected_contract")
            if selected_contract:
                self.subscription_owner.pin_contract(
                    instance.strategy_instance_id,
                    str(selected_contract),
                    reason="SELECTED_CONTRACT_PINNED",
                )

        live_context["account_risk_matrix"] = _account_risk_matrix(self.registry, live_context["continuity"], late_start=self._late_start_mode)
        live_context["subscription_owner"] = self.subscription_owner.to_dict()
        return live_context

    def _continuity_for_instance(
        self,
        *,
        instance: EnabledStrategyInstance,
        now: datetime,
        adapter: FyersReadOnlyAdapter,
        instrument_records: tuple[Any, ...],
        stage_metrics: list[StageMetric],
    ) -> dict[str, Any]:
        if self._late_start_mode:
            if instance.strategy_definition_id == "S22_STOCKS_OP_SELL_MONTHLY_DIFF_2D_4D":
                reconstruction = build_s22_stock_historical_selection(
                    repo_root=self.config.repo_root,
                    instance=instance,
                    adapter=adapter,
                    session_date=self.session_date,
                    now=now,
                )
            else:
                reconstruction = build_authoritative_historical_selection(
                    repo_root=self.config.repo_root,
                    instance=instance,
                    adapter=adapter,
                    instrument_records=instrument_records,
                    session_date=self.session_date,
                    now=now,
                )
            continuity = {
                "status": reconstruction.status,
                "selected_contract": reconstruction.selected_contract,
                "selected_branch": reconstruction.selected_branch,
                "selected_option_type": reconstruction.selected_option_type,
                "selected_expiry": reconstruction.selected_expiry,
                "selected_strike": reconstruction.selected_strike,
                "monthly_status": reconstruction.monthly_status,
                "entry": reconstruction.entry,
                "target": reconstruction.target,
                "original_sl": reconstruction.original_sl,
                "evidence": reconstruction.evidence,
                "selected_contract_quote": reconstruction.quote,
                "live_plan": reconstruction.plan_payload,
                "option_history_status": reconstruction.option_history_status,
                "recovery_mode": reconstruction.recovery_mode,
                "candidate_count": reconstruction.candidate_count,
                "rejected_candidates": list(reconstruction.rejected_candidates),
                "unresolved_gap": reconstruction.unresolved_gap,
            }
            if reconstruction.selected_contract:
                continuity.update(
                    self._reconstructed_entry_context(
                        instance=instance,
                        now=now,
                        adapter=adapter,
                        selected_contract=reconstruction.selected_contract,
                        continuity=continuity,
                    )
                )
            self._append_selected_contract_history(
                instance.strategy_instance_id,
                reconstruction.quote,
            )
            return continuity

        selected_contract = str(instance.deterministic_projection.get("selected_contract") or "")
        if not selected_contract:
            return {
                "status": "SELECTION_MISSING",
                "selected_contract": None,
                "evidence": "BLOCKED_CONFIGURATION",
            }

        if supports_authoritative_live_selection(instance):
            result = build_authoritative_live_selection(
                repo_root=self.config.repo_root,
                instance=instance,
                adapter=adapter,
                instrument_records=instrument_records,
                session_date=self.session_date,
                now=now,
            )
            continuity = {
                "status": result.status,
                "selected_contract": result.selected_contract,
                "selected_branch": result.selected_branch,
                "selected_option_type": result.selected_option_type,
                "selected_expiry": result.selected_expiry,
                "selected_strike": result.selected_strike,
                "monthly_status": result.monthly_status,
                "entry": result.entry,
                "target": result.target,
                "original_sl": result.original_sl,
                "evidence": result.evidence,
                "selected_contract_quote": result.quote,
                "live_plan": result.plan_payload,
                "option_history_status": result.option_history_status,
            }
            if result.selected_contract and now.timetz().replace(tzinfo=None) >= ORPT_TIME:
                continuity.update(
                    self._reconstructed_entry_context(
                        instance=instance,
                        now=now,
                        adapter=adapter,
                        selected_contract=result.selected_contract,
                        continuity=continuity,
                    )
                )
            self._append_selected_contract_history(
                instance.strategy_instance_id,
                result.quote,
            )
            return continuity

        if instance.symbol == "RELIANCE":
            selected_contract = _latest_reliance_snapshot_contract(self.config.repo_root) or selected_contract
            call_started_at = self.now_provider()
            quote_result = adapter.fetch_quotes((selected_contract,))
            self._record_stage(
                stage_metrics,
                "provider_selected_contract_quote",
                "EXECUTED",
                started_at=call_started_at,
                ended_at=self.now_provider(),
                scope=instance.strategy_instance_id,
                details={"symbol": selected_contract, "status": quote_result.status.value},
            )
            records_for_underlying = tuple(record for record in instrument_records if getattr(record, "underlying", None) == "RELIANCE")
            if records_for_underlying:
                cache_key = "RELIANCE"
                cached_chain = self._cached_option_chain_by_underlying.get(cache_key)
                if cached_chain is not None and self._cache_is_fresh(
                    cached_at=cached_chain["captured_at"],
                    now=now,
                    ttl_seconds=self.config.option_chain_refresh_interval_seconds,
                ):
                    option_chain = cached_chain["result"]
                    self._record_stage(
                        stage_metrics,
                        "provider_option_chain",
                        "CACHED",
                        started_at=now,
                        ended_at=now,
                        scope=instance.strategy_instance_id,
                        details={"underlying": "RELIANCE"},
                    )
                else:
                    expiry = classify_monthly_expiries(records_for_underlying, underlying="RELIANCE", as_of=now.date())
                    call_started_at = self.now_provider()
                    option_chain = adapter.fetch_option_chain(
                        underlying="NSE:RELIANCE-EQ",
                        expiry=expiry.near_monthly_expiry,
                        strike_count=25,
                        instrument_records=records_for_underlying,
                    )
                    self._cached_option_chain_by_underlying[cache_key] = {
                        "captured_at": now,
                        "result": option_chain,
                    }
                    self._record_stage(
                        stage_metrics,
                        "provider_option_chain",
                        "EXECUTED",
                        started_at=call_started_at,
                        ended_at=self.now_provider(),
                        scope=instance.strategy_instance_id,
                        details={"underlying": "RELIANCE", "status": option_chain.status.value},
                    )
            else:
                option_chain = None
            return {
                "status": "IDENTIFIABLE",
                "selected_contract": selected_contract,
                "evidence": "LIVE_FYERS_READ_ONLY_CAPTURE",
                "selected_contract_quote": quote_result.to_dict(),
                "option_chain_status": option_chain.to_dict() if option_chain is not None else {"status": "UNAVAILABLE"},
                **(
                    self._reconstructed_entry_context(
                        instance=instance,
                        now=now,
                        adapter=adapter,
                        selected_contract=selected_contract,
                        continuity={
                            "status": "IDENTIFIABLE",
                            "selected_contract": selected_contract,
                            "evidence": "LIVE_FYERS_READ_ONLY_CAPTURE",
                        },
                    )
                    if now.timetz().replace(tzinfo=None) >= ORPT_TIME
                    else {}
                ),
            }

        call_started_at = self.now_provider()
        quote_result = adapter.fetch_quotes((selected_contract,))
        self._record_stage(
            stage_metrics,
            "provider_selected_contract_quote",
            "EXECUTED",
            started_at=call_started_at,
            ended_at=self.now_provider(),
            scope=instance.strategy_instance_id,
            details={"symbol": selected_contract, "status": quote_result.status.value},
        )
        self._append_selected_contract_history(
            instance.strategy_instance_id,
            {
                "symbol": selected_contract,
                "quote_result": quote_result.to_dict(),
                "receipt_timestamp": now.isoformat(),
            },
        )
        continuity = {
            "status": "PREMARKET_SELECTED_CONTRACT_PINNED" if not self._late_start_mode else "IDENTIFIABLE",
            "selected_contract": selected_contract,
            "evidence": "FIXTURE_BACKED" if instance.evidence_quality == "FIXTURE_BACKED" else instance.evidence_quality,
            "selected_contract_quote": quote_result.to_dict(),
        }
        if now.timetz().replace(tzinfo=None) >= ORPT_TIME:
            continuity.update(
                self._reconstructed_entry_context(
                    instance=instance,
                    now=now,
                    adapter=adapter,
                    selected_contract=selected_contract,
                    continuity=continuity,
                )
            )
        return continuity

    def _reconstructed_entry_context(
        self,
        *,
        instance: EnabledStrategyInstance,
        now: datetime,
        adapter: FyersReadOnlyAdapter,
        selected_contract: str,
        continuity: Mapping[str, Any],
    ) -> dict[str, Any]:
        underlying_symbol = _resolve_underlying_symbol(instance.symbol, self._underlying_symbols)
        underlying_history = adapter.fetch_historical_candles(
            symbol=underlying_symbol,
            resolution="1",
            range_from=self.session_date,
            range_to=self.session_date,
            exclude_incomplete_after=now,
        )
        option_history = adapter.fetch_historical_candles(
            symbol=selected_contract,
            resolution="1",
            range_from=self.session_date,
            range_to=self.session_date,
            exclude_incomplete_after=now,
        )
        quote_result = adapter.fetch_quotes((selected_contract,))
        current_quote = None
        if quote_result.status is FyersReadOnlyStatus.SUCCESS and quote_result.payload:
            current_quote = quote_result.payload[0]
        reconstructed = reconstruct_option_selling_entry(
            strategy_instance_id=instance.strategy_instance_id,
            timing_policy=StrategyTimingPolicy(
                market_open=MARKET_OPEN,
                orpt_time=ORPT_TIME,
                rc_time=RC_TIME,
            ),
            now=now,
            invalid_runtime_classification="INVALID_RUNTIME_CLASSIFICATION",
            selected_contract_authoritative=selected_contract_is_authoritative(selected_contract),
            base_entry=Decimal(str(instance.deterministic_projection.get("entry") or "0")),
            revised_entry=_revised_entry_for_instance(instance, continuity=continuity),
            underlying_bars=underlying_history.payload if underlying_history.status is FyersReadOnlyStatus.SUCCESS else None,
            option_bars=option_history.payload if option_history.status is FyersReadOnlyStatus.SUCCESS else None,
            current_quote=current_quote,
        )
        return {
            "current_entry_state": reconstructed.current_entry_state,
            "orpt_result": reconstructed.orpt_result,
            "rc_result": reconstructed.rc_result,
            "underlying_evidence_quality": reconstructed.underlying_evidence_quality,
            "option_evidence_quality": reconstructed.option_evidence_quality,
            "reconstruction": reconstructed.to_dict(),
        }

    def _append_selected_contract_history(
        self,
        strategy_instance_id: str,
        payload: Mapping[str, Any] | None,
    ) -> None:
        if not payload:
            return
        event = dict(payload)
        symbol = str(event.get("symbol") or "")
        if not symbol:
            return
        history = self._selected_contract_history.setdefault(strategy_instance_id, [])
        if history and canonical_hash(history[-1]) == canonical_hash(event):
            return
        history.append(event)
        if len(history) > 240:
            del history[:-240]

    def _evaluate_internal_paper_actions(
        self,
        *,
        now: datetime,
        live_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        account_snapshots = {
            account_reference: _account_snapshot_from_dict(snapshot)
            for account_reference, snapshot in self._paper_account_snapshots.items()
        }
        execution_state = {strategy_instance_id: dict(state) for strategy_instance_id, state in self._paper_execution_state.items()}
        outcomes: dict[str, dict[str, Any]] = {}
        explanation_facts: list[dict[str, Any]] = []
        adapter = DeterministicInternalPaperAdapter()
        instances = {item.strategy_instance_id: item for item in self.registry.enabled_instances}

        for sequence, strategy_instance_id in enumerate(sorted(instances), start=1):
            instance = instances[strategy_instance_id]
            continuity = _action_ready_continuity(live_context["continuity"].get(strategy_instance_id) or {})
            current_state = dict(execution_state.get(strategy_instance_id) or {})
            explanation_facts.extend(
                build_explanation_facts(
                    instance=instance,
                    continuity=continuity,
                    now=now,
                    trading_session_id=self.session_id,
                )
            )
            outcome = self._evaluate_single_internal_paper_action(
                now=now,
                instance=instance,
                continuity=continuity,
                current_state=current_state,
                account_snapshots=account_snapshots,
                adapter=adapter,
                sequence=sequence,
            )
            execution_state[strategy_instance_id] = dict(outcome["state"])
            outcomes[strategy_instance_id] = dict(outcome["outcome"])
            explanation_facts.append(
                _action_explanation_fact(
                    instance=instance,
                    continuity=continuity,
                    outcome=outcome["outcome"],
                    now=now,
                    trading_session_id=self.session_id,
                )
            )

        self._paper_execution_state = execution_state
        self._paper_account_snapshots = {
            account_reference: snapshot.to_dict()
            for account_reference, snapshot in account_snapshots.items()
        }
        return {
            "outcomes": outcomes,
            "states": execution_state,
            "explanation_facts": explanation_facts,
        }

    def _evaluate_single_internal_paper_action(
        self,
        *,
        now: datetime,
        instance: EnabledStrategyInstance,
        continuity: Mapping[str, Any],
        current_state: Mapping[str, Any],
        account_snapshots: dict[str, SimulatedPaperAccountSnapshot],
        adapter: DeterministicInternalPaperAdapter,
        sequence: int,
    ) -> dict[str, Any]:
        current_entry_state = str(continuity.get("current_entry_state") or "")
        selected_contract = str(continuity.get("selected_contract") or "")
        evidence_mode = str(continuity.get("recovery_mode") or "LIVE_OBSERVED")
        filled_state = str(current_state.get("final_state") or "")
        if filled_state == "FILLED_INTERNAL" and bool(current_state.get("authoritative_state")):
            refreshed = _refresh_open_position_state(current_state=current_state, continuity=continuity, now=now)
            return {
                "state": refreshed,
                "outcome": _outcome_from_state(instance=instance, state=refreshed, decision="PROCESSED_INTERNAL_PAPER"),
            }
        if filled_state == "FILLED_INTERNAL":
            blocked_state = _blocked_paper_state(
                current_state=current_state,
                continuity=continuity,
                reason="AUTHORITATIVE_FILL_EVIDENCE_MISSING",
                now=now,
            )
            return {
                "state": blocked_state,
                "outcome": _outcome_from_state(instance=instance, state=blocked_state, decision="NO_ORDER"),
            }

        if self._late_start_mode and evidence_mode != "HISTORICALLY_RECONSTRUCTED":
            blocked_state = _blocked_paper_state(
                current_state=current_state,
                continuity=continuity,
                reason="LATE_START_NO_NEW_ENTRY",
                now=now,
            )
            return {
                "state": blocked_state,
                "outcome": _outcome_from_state(instance=instance, state=blocked_state, decision="NO_ORDER"),
            }

        if current_entry_state not in {"NORMAL_ENTRY_STILL_VALID", "RC_ENTRY_STILL_VALID"}:
            waiting_state = _blocked_paper_state(
                current_state=current_state,
                continuity=continuity,
                reason=current_entry_state or str(continuity.get("status") or "WAITING"),
                now=now,
            )
            return {
                "state": waiting_state,
                "outcome": _outcome_from_state(instance=instance, state=waiting_state, decision="NO_ORDER"),
            }

        if not selected_contract:
            missing_state = _blocked_paper_state(
                current_state=current_state,
                continuity=continuity,
                reason="SELECTED_CONTRACT_MISSING",
                now=now,
            )
            return {
                "state": missing_state,
                "outcome": _outcome_from_state(instance=instance, state=missing_state, decision="NO_ORDER"),
            }

        intent = _build_entry_intent(
            instance=instance,
            continuity=continuity,
            now=now,
            trading_session_id=self.session_id,
        )
        grant = _build_internal_paper_grant(intent)
        position_identity = self._build_position_cycle_identity(
            instance=instance,
            intent=intent,
            continuity=continuity,
        )
        validation = ExecutionIntentValidator().validate(
            build_validation_input(intent, validation_id=f"live-supervisor:{instance.strategy_instance_id}:{sequence}")
        )
        if validation.decision is not IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE:
            failed_state = _blocked_paper_state(
                current_state=current_state,
                continuity=continuity,
                reason=f"VALIDATION_{validation.decision.value}",
                now=now,
            )
            return {
                "state": failed_state,
                "outcome": _outcome_from_state(
                    instance=instance,
                    state=failed_state,
                    decision="NO_ORDER",
                    extra={"validation_failures": [item.code for item in validation.failures]},
                ),
            }

        snapshot = account_snapshots.get(intent.broker_account_id) or _build_account_snapshot(intent.broker_account_id)
        required_margin = snapshot.margin_per_quantity * Decimal(intent.action.requested_quantity)
        available_margin = snapshot.available_paper_margin + snapshot.active_order_reservation
        effective_available_margin = available_margin - snapshot.active_order_reservation
        if effective_available_margin < required_margin:
            warning_state = _blocked_paper_state(
                current_state=current_state,
                continuity=continuity,
                reason="INSUFFICIENT_MARGIN",
                now=now,
            )
            return {
                "state": warning_state,
                "outcome": _outcome_from_state(
                    instance=instance,
                    state=warning_state,
                    decision="ORDER_NOT_SUBMITTED_INSUFFICIENT_MARGIN",
                    extra={
                        "required_margin": str(required_margin),
                        "available_margin": str(available_margin),
                        "effective_available_margin": str(effective_available_margin),
                        "shortfall": str(required_margin - effective_available_margin),
                    },
                ),
            }

        state = dict(current_state)
        if not state.get("client_order_id"):
            coordinator = AccountCoordinator(
                AccountCoordinator.build_identity(
                    broker_account_id=intent.broker_account_id,
                    trading_session_id=intent.trading_session_id,
                ),
                snapshot,
            )
            client_order = coordinator.create_client_order(
                intent=intent,
                validation_result=validation,
                grant=grant,
                evaluated_at=now,
            )
            creation_event = create_creation_event(client_order, now)
            coordinator.record_event(creation_event)
            coordinator.account_snapshot = margin_after_reservation(coordinator.account_snapshot, client_order.quantity)
            snapshot = coordinator.account_snapshot
            account_snapshots[intent.broker_account_id] = snapshot
            self._persist_internal_paper_client_order(
                instance=instance,
                intent=intent,
                grant=grant,
                client_order=client_order,
                creation_event=creation_event,
                account_snapshot=snapshot,
            )
            state = {
                "client_order_id": client_order.client_order_id,
                "execution_intent_id": intent.execution_intent_id,
                "selected_contract": selected_contract,
                "order_state": "READY_INTERNAL",
                "fill_state": "NO_FILL",
                "final_state": "READY_INTERNAL",
                "position_cycle_id": position_identity.position_cycle_id,
                "filled_quantity": 0,
                "remaining_quantity": 0,
                "average_entry": "0.00",
                "entry_price": str(intent.action.limit_price or continuity.get("entry") or "0.00"),
                "entry_time": now.isoformat(),
                "exit_time": None,
                "latest_event": "CLIENT_ORDER_CREATED",
                "failure": None,
                "decision": "ORDER_ACCEPTED_PENDING_FILL",
                "quantity": intent.action.requested_quantity,
                "required_margin": str(required_margin),
                "available_margin": str(available_margin),
                "effective_available_margin": str(effective_available_margin),
                "account_reference": intent.broker_account_id,
                "authoritative_state": True,
            }
        else:
            account_snapshots[intent.broker_account_id] = snapshot

        limit_price = Decimal(str(state.get("entry_price") or continuity.get("entry") or "0.00"))
        if _quote_allows_limit_sell_fill(continuity.get("quote") or {}, limit_price):
            coordinator = AccountCoordinator(
                AccountCoordinator.build_identity(
                    broker_account_id=intent.broker_account_id,
                    trading_session_id=intent.trading_session_id,
                ),
                snapshot,
            )
            restored_order = _client_order_from_state(intent=intent, state=state)
            coordinator.restore_client_order(restored_order)
            coordinator.record_event(create_creation_event(restored_order, _optional_datetime(state.get("entry_time")) or now))
            scenario = _build_live_fill_scenario(intent=intent, continuity=continuity, now=now)
            result = adapter.execute(
                restored_order,
                scenario,
                snapshot,
                starting_state=InternalPaperOrderState.READY_FOR_INTERNAL_PAPER,
            )
            coordinator.apply_result(result)
            account_snapshots[intent.broker_account_id] = coordinator.account_snapshot
            self._persist_internal_paper_fill_ledger(
                instance=instance,
                intent=intent,
                grant=grant,
                continuity=continuity,
                result=result,
                now=now,
                position_identity=position_identity,
            )
            filled_state_payload = {
                **state,
                "order_state": "FILLED_INTERNAL",
                "fill_state": "FILLED_INTERNAL",
                "final_state": "FILLED_INTERNAL",
                "filled_quantity": intent.action.requested_quantity,
                "remaining_quantity": intent.action.requested_quantity,
                "average_entry": str(result.fills[-1].fill_price if result.fills else limit_price),
                "entry_price": str(result.fills[-1].fill_price if result.fills else limit_price),
                "entry_time": result.fills[-1].recorded_timestamp.isoformat() if result.fills else now.isoformat(),
                "latest_event": "INTERNAL_FULL_FILL",
                "failure": None,
                "decision": "PROCESSED_INTERNAL_PAPER",
                "mark": str((continuity.get("quote") or {}).get("ltp") or result.fills[-1].fill_price if result.fills else limit_price),
                "position_open": True,
                "authoritative_state": True,
            }
            refreshed = _refresh_open_position_state(current_state=filled_state_payload, continuity=continuity, now=now)
            return {
                "state": refreshed,
                "outcome": _outcome_from_state(instance=instance, state=refreshed, decision="PROCESSED_INTERNAL_PAPER"),
            }

        pending_state = {
            **state,
            "order_state": "READY_INTERNAL",
            "fill_state": "NO_FILL",
            "final_state": "READY_INTERNAL",
            "latest_event": "WAITING_FOR_FILL",
            "decision": "ORDER_ACCEPTED_PENDING_FILL",
            "mark": str((continuity.get("quote") or {}).get("ltp") or ""),
            "authoritative_state": True,
        }
        return {
            "state": pending_state,
            "outcome": _outcome_from_state(instance=instance, state=pending_state, decision="ORDER_ACCEPTED_PENDING_FILL"),
        }

    def _persist_internal_paper_client_order(
        self,
        *,
        instance: EnabledStrategyInstance,
        intent: Any,
        grant: Any,
        client_order: Any,
        creation_event: Any,
        account_snapshot: SimulatedPaperAccountSnapshot,
    ) -> None:
        db = PersistenceDatabase(self.config.db_path)
        with UnitOfWork(db) as uow:
            self._ensure_authoritative_runtime_identity(uow=uow, instance=instance, broker_account_id=intent.broker_account_id)
            uow.repo.put_internal_paper_client_order(
                grant=grant,
                client_order=client_order,
                creation_event=creation_event,
                account_snapshot=account_snapshot,
                expected_account_projection_version=None,
            )

    def _persist_internal_paper_fill_ledger(
        self,
        *,
        instance: EnabledStrategyInstance,
        intent: Any,
        grant: Any,
        continuity: Mapping[str, Any],
        result: Any,
        now: datetime,
        position_identity: Any,
    ) -> None:
        position_transition = self._build_entry_position_transition(
            instance=instance,
            intent=intent,
            continuity=continuity,
            result=result,
            position_identity=position_identity,
        )
        accounting_result = self._build_open_position_accounting_result(
            instance=instance,
            intent=intent,
            continuity=continuity,
            result=result,
            position_transition=position_transition,
            now=now,
        )
        db = PersistenceDatabase(self.config.db_path)
        with UnitOfWork(db) as uow:
            self._ensure_authoritative_runtime_identity(uow=uow, instance=instance, broker_account_id=intent.broker_account_id)
            uow.repo.put_internal_paper_result(
                grant=grant,
                result=result,
                expected_account_projection_version=None,
            )
            uow.repo.put_position_cycle_identity(
                position_cycle_id=position_identity.position_cycle_id,
                strategy_instance_id=instance.strategy_instance_id,
                trading_session_id=self.session_id,
                payload=position_identity.to_dict(),
            )
            uow.repo.put_internal_position_transition(
                transition=position_transition.to_dict(),
                expected_projection_version=None,
            )
            uow.repo.put_accounting_build_result(
                build_result=accounting_result.to_dict(),
                expected_projection_version=None,
            )

    def _ensure_authoritative_runtime_identity(
        self,
        *,
        uow: Any,
        instance: EnabledStrategyInstance,
        broker_account_id: str,
    ) -> None:
        uow.repo.put_trading_session(
            trading_session_id=self.session_id,
            trading_date=self.session_date,
            market="NSE",
            timezone_name="Asia/Calcutta",
            payload={
                "session_id": self.session_id,
                "state": "LIVE_INTERNAL_PAPER",
                "authority": "INTERNAL_PAPER_ONLY",
            },
        )
        account_payload = self._account_payload_for_reference(instance.account_reference)
        uow.repo.put_broker_account_identity(
            broker_account_id=broker_account_id,
            provider=str(account_payload.get("broker") or "INTERNAL_PAPER"),
            environment="internal_paper",
            account_hash=canonical_hash(account_payload),
            payload=account_payload,
        )
        uow.repo.put_strategy_instance(
            strategy_instance_id=instance.strategy_instance_id,
            strategy_definition_id=instance.strategy_definition_id,
            strategy_version=instance.strategy_version,
            configuration_hash=instance.rule_config_hash,
            payload=instance.to_dict(),
        )

    def _account_payload_for_reference(self, account_reference: str) -> dict[str, Any]:
        for account in self.registry.accounts:
            if str(account.get("account_reference") or "") == account_reference:
                return dict(account)
        return {"account_reference": account_reference, "broker": "INTERNAL_PAPER"}

    def _build_position_cycle_identity(
        self,
        *,
        instance: EnabledStrategyInstance,
        intent: Any,
        continuity: Mapping[str, Any],
    ) -> Any:
        coordinator = PositionCycleCoordinator()
        return coordinator.build_identity(
            trading_session_id=self.session_id,
            originating_trading_date=self.session_date,
            broker_account_id=intent.broker_account_id,
            logical_account_reference=instance.account_reference,
            strategy_family_id=intent.strategy_family_id,
            strategy_definition_id=intent.strategy_definition_id,
            strategy_version=intent.strategy_version,
            strategy_instance_id=intent.strategy_instance_id,
            originating_execution_plan_id=intent.source_artifact_id,
            originating_entry_execution_intent_id=intent.execution_intent_id,
            normalized_contract=intent.instrument.contract,
            direction=str(continuity.get("selected_branch") or instance.deterministic_projection.get("branch") or "UNKNOWN"),
            side=intent.action.side,
        )

    def _build_entry_position_transition(
        self,
        *,
        instance: EnabledStrategyInstance,
        intent: Any,
        continuity: Mapping[str, Any],
        result: Any,
        position_identity: Any,
    ) -> Any:
        fill = result.fills[-1]
        client_order_payload = result.client_order.to_dict() | {
            "lot_size": intent.instrument.lot_size,
            "multiplier": str(intent.instrument.multiplier),
            "currency": intent.instrument.currency,
        }
        lifecycle_prices = {
            "target": continuity.get("target") or instance.deterministic_projection.get("target"),
            "original_sl": continuity.get("original_sl") or instance.deterministic_projection.get("original_sl"),
        }
        return PositionCycleCoordinator().apply_entry_fill(
            None,
            identity=position_identity,
            client_order=client_order_payload,
            fill=fill.to_dict(),
            requested_quantity=intent.action.requested_quantity,
            source_rule_ids=tuple(intent.evidence.source_rule_ids),
            lifecycle_prices=lifecycle_prices,
        )

    def _build_open_position_accounting_result(
        self,
        *,
        instance: EnabledStrategyInstance,
        intent: Any,
        continuity: Mapping[str, Any],
        result: Any,
        position_transition: Any,
        now: datetime,
    ) -> Any:
        quote = continuity.get("quote") if isinstance(continuity.get("quote"), Mapping) else {}
        projection = position_transition.projection.to_dict()
        option_type = intent.instrument.option_type
        if option_type == "CE":
            option_type = "CALL"
        elif option_type == "PE":
            option_type = "PUT"
        instrument = InstrumentDimensions(
            exchange=intent.instrument.exchange,
            product=intent.instrument.product,
            underlying=intent.instrument.underlying,
            contract=intent.instrument.contract,
            expiry=intent.instrument.expiry.isoformat() if intent.instrument.expiry else None,
            strike=intent.instrument.strike,
            option_type=option_type,
            direction=str(continuity.get("selected_branch") or instance.deterministic_projection.get("branch") or "UNKNOWN"),
            lot_size=intent.instrument.lot_size,
            multiplier=intent.instrument.multiplier,
            tick_size=intent.instrument.tick_size,
            currency=intent.instrument.currency,
            metadata_version=str(continuity.get("evidence") or instance.evidence_quality),
        )
        charge_evidence = ChargeEvidence(
            charges=Decimal("0.00"),
            quality=AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES,
            source="UNIFIED_INTERNAL_PAPER_SUPERVISOR",
        )
        mark_snapshot = MarkSnapshot(
            contract=intent.instrument.contract,
            trading_date=self.session_date,
            bid=_optional_decimal(quote.get("bid")),
            ask=_optional_decimal(quote.get("ask")),
            ltp=_optional_decimal(quote.get("ltp")),
            source_timestamp=_optional_datetime(quote.get("source_timestamp")) or now,
            captured_timestamp=_optional_datetime(quote.get("receipt_timestamp")) or now,
            freshness_seconds=0,
            snapshot_hash=canonical_hash({"contract": intent.instrument.contract, "quote": dict(quote)}),
        )
        trade_fact = TradeFactBuilder().build(
            projection=projection,
            instrument=instrument,
            requested_entry_quantity=intent.action.requested_quantity,
            entry_fills=tuple(fill.to_dict() for fill in result.fills),
            exit_fills=(),
            lifecycle_requirements=tuple(item.to_dict() for item in position_transition.requirements),
            charge_evidence=charge_evidence,
            decision_context={
                "normal_gap_path": str(continuity.get("current_entry_state") or "UNKNOWN"),
                "orpt_rc_path": "RC" if str(continuity.get("current_entry_state") or "").startswith("RC_") else "NORMAL",
                "strategy_branch": str(continuity.get("selected_branch") or instance.deterministic_projection.get("branch") or "UNKNOWN"),
                "configured_lots": int(instance.configured_quantity.get("lots", 0) or 0),
                "lot_size": int(intent.instrument.lot_size),
                "exchange_quantity": int(intent.action.requested_quantity),
                "capital_or_margin_estimate": str(Decimal("100") * Decimal(int(intent.action.requested_quantity))),
                "contract_observations": (),
                "source_plan_context_decision_hashes": {
                    "premarket": str((continuity.get("live_plan") or {}).get("plan_hash") or intent.source_artifact_hash),
                    "opening": canonical_hash({"quote": dict(quote), "selected_contract": intent.instrument.contract}),
                    "effective_plan": canonical_hash(
                        {
                            "entry": str(continuity.get("entry") or ""),
                            "target": str(continuity.get("target") or ""),
                            "original_sl": str(continuity.get("original_sl") or ""),
                        }
                    ),
                },
            },
            source_hashes={
                "intent_hash": intent.intent_hash,
                "result_hash": result.result_hash,
                "position_cycle_hash": position_transition.projection.projection_hash,
                "position_event_ids": (position_transition.event.event_id,),
            },
            mark_snapshot=mark_snapshot,
            exit_order_purpose=None,
            configuration_hash=intent.evidence.configuration_hash,
            rule_matrix_version=intent.evidence.rule_matrix_version,
        )
        pnl_facts = PnLFactBuilder().build(
            trade_fact=trade_fact,
            as_of_timestamp=now,
            charge_evidence=charge_evidence,
        )
        return build_accounting_result(trade_fact=trade_fact, pnl_facts=pnl_facts)

    def _build_projection(self, now: datetime, *, live_context: Mapping[str, Any], final_state: str) -> dict[str, Any]:
        action_bundle = self._evaluate_internal_paper_actions(now=now, live_context=live_context)
        instance_results = {
            item.strategy_instance_id: _live_instance_result(
                item,
                now=now,
                session_id=self.session_id,
                continuity=live_context["continuity"].get(item.strategy_instance_id) or {},
                timing=live_context["timing"]["instances"].get(item.strategy_instance_id) or {},
                selected_contract_reads=tuple(live_context["selected_contract_reads"].get(item.strategy_instance_id) or ()),
                late_start=self._late_start_mode,
                action_state=action_bundle["states"].get(item.strategy_instance_id) or {},
            )
            for item in self.registry.enabled_instances
        }
        projection = build_unified_dashboard_projection(
            self.registry,
            instance_results,
            scenario_id="continuous_supervisor_live" if live_context["market_session_state"] == "LIVE" else "continuous_supervisor",
        ).to_dict()
        projection["system"].update(
            {
                "runtime": "CONTINUOUS_UNIFIED_S21_S22_S23_INTERNAL_PAPER_SUPERVISOR",
                "session_id": self.session_id,
                "trading_date": self.session_date.isoformat(),
                "market_state": live_context["market_session_state"],
                "supervisor_state": final_state,
                "supervisor_mode": "INTERNAL_PAPER_LATE_START_NO_NEW_ENTRY" if self._late_start_mode else "INTERNAL_PAPER_OBSERVATION_ONLY",
                "fyers_market_data_authority": "READ_ONLY",
                "tfis_execution_authority": "INTERNAL_PAPER_ONLY",
                "external_order_submission": False,
                "live_money_authority": False,
                "no_external_order_authority": True,
                "source_timestamp": now.isoformat(),
                "receipt_timestamp": now.isoformat(),
                "subscription_hash": self.subscription_owner.runtime_index().snapshot().subscription_hash,
            }
        )
        projection["command_centre"].update(
            {
                "system_state": "DEGRADED" if self._late_start_mode else projection["command_centre"]["system_state"],
                "market_state": live_context["market_session_state"],
                "broker_sessions": self._latest_auth.status.value if self._latest_auth is not None else "UNKNOWN",
                "plans_prepared": sum(1 for item in instance_results.values() if item["plan"]["plan_status"] == "PREPARED"),
                "blocked_instances": sum(1 for item in instance_results.values() if item["plan"]["plan_status"] == "BLOCKED"),
                "active_orders": sum(1 for item in instance_results.values() if item["execution"]["order_state"] not in {"NO_ORDER", "REJECTED_INTERNAL"}),
            }
        )
        projection["analytics"].update(
            {
                "live_session_timeline_events": len(self._timeline),
                "account_risk_matrix": live_context.get("account_risk_matrix", {}),
                "subscription_owner": self.subscription_owner.to_dict(),
            }
        )
        projection["decision_explanations"] = list(projection["decision_explanations"]) + list(action_bundle["explanation_facts"])
        projection["audit"] = list(projection["audit"]) + list(self._timeline)
        projection["alerts"] = list(projection["alerts"]) + _global_alerts(
            late_start=self._late_start_mode,
            auth_status=self._latest_auth.status.value if self._latest_auth is not None else "UNKNOWN",
            continuity=live_context.get("continuity") or {},
        )
        projection["projection_hash"] = canonical_hash(
            {
                "system": projection["system"],
                "command_centre": projection["command_centre"],
                "strategies": projection["strategies"],
                "orders": projection["orders"],
                "positions": projection["positions"],
                "alerts": projection["alerts"],
                "audit": projection["audit"],
            }
        )
        return projection

    def _persist_runtime_state(
        self,
        *,
        now: datetime,
        final_state: str,
        projection: Mapping[str, Any],
        live_context: Mapping[str, Any],
        stage_metrics: list[StageMetric],
    ) -> None:
        self.config.state_root.mkdir(parents=True, exist_ok=True)
        checkpoint_payload = {
            "session_id": self.session_id,
            "session_date": self.session_date.isoformat(),
            "session_started_at": self._session_started_at.isoformat(),
            "state": final_state,
            "late_start_mode": self._late_start_mode,
            "iteration": self.iterations,
            "projection_hash": projection["projection_hash"],
            "subscription_owner": self.subscription_owner.to_dict(),
            "continuity": live_context.get("continuity", {}),
            "selected_contract_reads": live_context.get("selected_contract_reads", {}),
            "paper_execution_state": self._paper_execution_state,
            "paper_account_snapshots": self._paper_account_snapshots,
            "timing": live_context.get("timing", {}),
            "market_state": live_context.get("market_session_state"),
            "updated_at": now.isoformat(),
            "authority": {
                "fyers_market_data": "READ_ONLY",
                "tfis_execution": "INTERNAL_PAPER_ONLY",
                "external_broker_orders": "NONE",
            },
        }
        semantic_hash = canonical_hash(
            {
                "state": checkpoint_payload["state"],
                "late_start_mode": checkpoint_payload["late_start_mode"],
                "projection_hash": checkpoint_payload["projection_hash"],
                "subscription_owner": checkpoint_payload["subscription_owner"],
                "continuity": checkpoint_payload["continuity"],
                "selected_contract_reads": checkpoint_payload["selected_contract_reads"],
                "paper_execution_state": checkpoint_payload["paper_execution_state"],
                "paper_account_snapshots": checkpoint_payload["paper_account_snapshots"],
                "timing": checkpoint_payload["timing"],
                "market_state": checkpoint_payload["market_state"],
                "authority": checkpoint_payload["authority"],
            }
        )
        should_write_checkpoint = (
            self._last_checkpoint_semantic_hash != semantic_hash
            or self._last_checkpoint_write_at is None
            or not self._cache_is_fresh(
                cached_at=self._last_checkpoint_write_at,
                now=now,
                ttl_seconds=self.config.checkpoint_write_interval_seconds,
            )
        )
        checkpoint_started_at = self.now_provider()
        if should_write_checkpoint:
            self._checkpoint_path.write_text(json.dumps(checkpoint_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._last_checkpoint_semantic_hash = semantic_hash
            self._last_checkpoint_write_at = now
            checkpoint_status = "EXECUTED"
        else:
            checkpoint_status = "SKIPPED_NO_CHANGE"
        self._record_stage(
            stage_metrics,
            "checkpoint_write",
            checkpoint_status,
            started_at=checkpoint_started_at,
            ended_at=self.now_provider(),
        )

        persistence_started_at = self.now_provider()
        if should_write_checkpoint:
            db = PersistenceDatabase(self.config.db_path)
            with UnitOfWork(db) as uow:
                repo = uow.repo
                repo.put_trading_session(
                    trading_session_id=self.session_id,
                    trading_date=self.session_date,
                    market="NSE",
                    timezone_name="Asia/Calcutta",
                    payload={
                        "session_id": self.session_id,
                        "state": final_state,
                        "late_start_mode": self._late_start_mode,
                    },
                )
                for instance in self.registry.enabled_instances:
                    repo.put_strategy_instance(
                        strategy_instance_id=instance.strategy_instance_id,
                        strategy_definition_id=instance.strategy_definition_id,
                        strategy_version=instance.strategy_version,
                        configuration_hash=instance.rule_config_hash,
                        payload=instance.to_dict(),
                    )
                    checkpoint_id = f"{self.session_id}:{instance.strategy_instance_id}:iteration:{self.iterations}"
                    repo.put_runtime_checkpoint(
                        checkpoint_id=checkpoint_id,
                        stream_identity=instance.strategy_instance_id,
                        session_source_id=self.session_id,
                        source_offset=self.iterations,
                        current_state=final_state,
                        consumed_event_ids=tuple(item["event_id"] for item in self._timeline),
                        snapshot_hashes={"projection_hash": projection["projection_hash"]},
                        artifact_hashes={"checkpoint_payload": canonical_hash(checkpoint_payload)},
                        configuration_hash=self.registry.registry_hash,
                        rule_matrix_version=RULE_MATRIX_VERSION,
                    )
                    expected_version = _load_projection_version(self.config.db_path, instance.strategy_instance_id)
                    repo.upsert_runtime_projection(
                        projection_id=f"unified-supervisor:{instance.strategy_instance_id}",
                        strategy_instance_id=instance.strategy_instance_id,
                        trading_session_id=self.session_id,
                        latest_state=final_state,
                        latest_checkpoint_id=checkpoint_id,
                        latest_artifact_hashes={"projection_hash": projection["projection_hash"]},
                        consumed_event_watermark=self.iterations,
                        expected_version=expected_version,
                    )
            persistence_status = "EXECUTED"
        else:
            persistence_status = "SKIPPED_NO_CHANGE"
        self._record_stage(
            stage_metrics,
            "sqlite_runtime_persistence",
            persistence_status,
            started_at=persistence_started_at,
            ended_at=self.now_provider(),
        )

    def _write_dashboard_snapshot(self, projection: Mapping[str, Any], *, now: datetime, stage_metrics: list[StageMetric]) -> None:
        api_dir = self.config.dashboard_output_root / "api"
        api_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = api_dir / "snapshot.json"
        should_write_snapshot = (
            self._last_snapshot_write_at is None
            or projection["projection_hash"] != self._last_snapshot_projection_hash
            or not self._cache_is_fresh(
                cached_at=self._last_snapshot_write_at,
                now=now,
                ttl_seconds=self.config.snapshot_write_interval_seconds,
            )
        )
        snapshot_started_at = self.now_provider()
        if should_write_snapshot:
            snapshot_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_path = self.config.dashboard_output_root / "dashboard_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "dashboard": "TFIS Professional Operations Dashboard",
                        "projection_hash": projection["projection_hash"],
                        "snapshot": "api/snapshot.json",
                        "broker_order_authority": projection["system"]["broker_order_authority"],
                        "frontend_formula_calculation": False,
                        "session_id": self.session_id,
                        "trading_date": self.session_date.isoformat(),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            self._last_snapshot_write_at = now
            self._last_snapshot_projection_hash = str(projection["projection_hash"])
            status = "EXECUTED"
        else:
            status = "SKIPPED_NO_CHANGE"
        self._record_stage(stage_metrics, "dashboard_snapshot_write", status, started_at=snapshot_started_at, ended_at=self.now_provider())

    def _write_heartbeat(self, *, state: str, now: datetime) -> None:
        payload = {
            "session_id": self.session_id,
            "state": state,
            "timestamp": now.isoformat(),
            "session_started_at": self._session_started_at.isoformat(),
            "projection_hash": self._last_projection_hash,
            "late_start_mode": self._late_start_mode,
            "pid": self.lock_handle.pid if self.lock_handle is not None else None,
            "db_path": str(self.config.db_path),
            "report_dir": str(self.config.report_dir),
        }
        self._heartbeat_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_reports(self, now: datetime, final_state: str, *, stage_metrics: list[StageMetric]) -> None:
        self.config.report_dir.mkdir(parents=True, exist_ok=True)
        should_write_reports = (
            self._last_report_write_at is None
            or self._last_report_state != final_state
            or not self._cache_is_fresh(
                cached_at=self._last_report_write_at,
                now=now,
                ttl_seconds=self.config.report_write_interval_seconds,
            )
        )
        reports_started_at = self.now_provider()
        if not should_write_reports:
            self._record_stage(stage_metrics, "live_supervisor_reports", "SKIPPED_NO_CHANGE", started_at=reports_started_at, ended_at=self.now_provider())
            return

        existing_preflight = self._load_existing_preflight_report()
        preflight_verdict = existing_preflight.get("verdict", "NOT_RUN_IN_HOT_LOOP")
        preflight_reasons = existing_preflight.get("reasons", [])
        preflight_captured_at = existing_preflight.get("captured_at", "UNKNOWN")
        files = {
            "continuous_supervisor_contract.json": {
                "schema_version": "tfis.live_supervisor.contract.v1",
                "session_id": self.session_id,
                "states": list(REQUIRED_SUPERVISOR_STATES),
                "configuration_driven": True,
                "strategy_specific_formulas_in_supervisor": False,
                "final_state": final_state,
                "runtime": "CONTINUOUS_UNIFIED_S21_S22_S23_INTERNAL_PAPER_SUPERVISOR",
            },
            "subscription_owner_state.json": {
                "schema_version": "tfis.live_supervisor.subscription_owner_state.v1",
                "captured_at": now.isoformat(),
                "session_id": self.session_id,
                **self.subscription_owner.to_dict(),
                "runtime_subscription_snapshot": self.subscription_owner.runtime_index().snapshot().to_dict(),
            },
            "scheduler_contract.json": {
                "schema_version": "tfis.live_supervisor.scheduler_contract.v1",
                "captured_at": now.isoformat(),
                "session_id": self.session_id,
                "timezone": "Asia/Calcutta",
                "market_open": MARKET_OPEN.isoformat(),
                "eod_decision": EOD_DECISION.isoformat(),
                "market_close": MARKET_CLOSE.isoformat(),
                "late_start_mode": self._late_start_mode,
            },
            "checkpoint_resume_contract.json": {
                "schema_version": "tfis.live_supervisor.checkpoint_resume_contract.v1",
                "checkpoint_path": str(self._checkpoint_path),
                "heartbeat_path": str(self._heartbeat_path),
                "db_path": str(self.config.db_path),
                "late_start_mode": self._late_start_mode,
                "resume_policy": "NO_NEW_ENTRY_UNTIL_TIMING_AND_SELECTION_REVALIDATED",
            },
            "late_start_safety_result.json": {
                "schema_version": "tfis.live_supervisor.late_start_safety.v1",
                "captured_at": now.isoformat(),
                "session_id": self.session_id,
                "late_start_mode": self._late_start_mode,
                "mode": "INTERNAL_PAPER_LATE_START_NO_NEW_ENTRY" if self._late_start_mode else "NORMAL_SESSION",
                "retroactive_entry_blocked": True,
            },
            "multi_strategy_live_routing.json": {
                "schema_version": "tfis.live_supervisor.live_routing.v1",
                "captured_at": now.isoformat(),
                "session_id": self.session_id,
                "projection_hash": self._last_projection_hash,
                "timeline_events": self._timeline,
            },
            "dashboard_evidence_label_audit.json": {
                "schema_version": "tfis.live_supervisor.dashboard_evidence_label_audit.v1",
                "captured_at": now.isoformat(),
                "session_id": self.session_id,
                "required_labels_all": [
                    "FIXTURE_BACKED",
                    "LIVE_FYERS_READ_ONLY_CAPTURE",
                    "LIVE_SUPERVISOR_OBSERVED",
                    "DETERMINISTIC_TIMING_SUPPLEMENT",
                    "MISSED_BEFORE_SUPERVISOR_START",
                    "INTERNAL_PAPER_SIMULATED",
                    "FYERS_METADATA_CAPTURED",
                    "NO_EXTERNAL_ORDER_AUTHORITY",
                ],
                "required_capture_classification_any_of": [
                    "PARTIAL_CAPTURE",
                    "COMPLETE_CAPTURE",
                ],
                "projection_labels": sorted(_collect_projection_labels(self._projection or {})),
                "capture_classification_present": any(
                    label in _collect_projection_labels(self._projection or {})
                    for label in ("PARTIAL_CAPTURE", "COMPLETE_CAPTURE")
                ),
                "meets_required_labels": _projection_meets_required_labels(self._projection or {}),
                "misrepresents_fixture_as_live": False,
            },
            "account_risk_acceptance_matrix.json": {
                "schema_version": "tfis.live_supervisor.account_risk_acceptance_matrix.v1",
                "captured_at": now.isoformat(),
                "session_id": self.session_id,
                "matrix": _account_risk_matrix(self.registry, _continuity_map_from_projection(self._projection or {}), late_start=self._late_start_mode),
            },
            "failure_isolation_matrix.json": {
                "schema_version": "tfis.live_supervisor.failure_isolation_matrix.v1",
                "captured_at": now.isoformat(),
                "session_id": self.session_id,
                "scenarios": [
                    {"failure": "S21 data missing", "survivors": ["S22", "S23"], "status": "SUPPORTED_BY_INSTANCE_ISOLATION"},
                    {"failure": "S22 quote stale", "survivors": ["S21", "S23"], "status": "SUPPORTED_BY_INSTANCE_ISOLATION"},
                    {"failure": "S23 selection blocked", "survivors": ["S21", "S22"], "status": "SUPPORTED_BY_INSTANCE_ISOLATION"},
                    {"failure": "dashboard disconnected", "survivors": ["supervisor", "positions"], "status": "SUPPORTED_BY_FILE_BACKED_SNAPSHOT"},
                ],
            },
            "complete_session_preflight.json": {
                "schema_version": "tfis.live_supervisor.complete_session_preflight.v1",
                "captured_at": preflight_captured_at,
                "reported_at": now.isoformat(),
                "session_id": self.session_id,
                "verdict": preflight_verdict,
                "reasons": list(preflight_reasons),
                "source": "STORED_EXPLICIT_PREFLIGHT_REPORT",
            },
            "next_session_startup_plan.json": {
                "schema_version": "tfis.live_supervisor.next_session_startup_plan.v1",
                "session_id": self.session_id,
                "operator_start_command": (
                    ".\\.venv\\Scripts\\python.exe scripts\\run_tfis_internal_paper.py "
                    "--continuous-supervisor --poll-seconds 5 --dashboard-port 8766"
                ),
                "dashboard_command": ".\\.venv\\Scripts\\python.exe scripts\\run_tfis_dashboard.py --serve --port 8766",
                "expected_result": "CONTINUOUS UNIFIED S21/S22/S23 INTERNAL-PAPER SUPERVISOR",
            },
            "performance_metrics.json": {
                **self._performance_payload(now=now, final_state=final_state, stage_metrics=stage_metrics),
            },
            "gap_register.json": {
                "schema_version": "tfis.live_supervisor.gap_register.v1",
                "session_id": self.session_id,
                "gaps": _supervisor_gaps(self._projection or {}, late_start=self._late_start_mode),
            },
            "validation_summary.json": {
                "schema_version": "tfis.live_supervisor.validation_summary.v1",
                "captured_at": now.isoformat(),
                "session_id": self.session_id,
                "projection_hash": self._last_projection_hash,
                "dashboard_snapshot_path": str(self.config.dashboard_output_root / "api" / "snapshot.json"),
                "db_integrity": self._recovery_snapshot(now=now)["integrity"],
                "recovery": self._recovery_snapshot(now=now)["recovery"],
            },
        }
        for name, payload in files.items():
            (self.config.report_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary = (
            "# Continuous Unified Internal-Paper Supervisor\n\n"
            f"- Session: `{self.session_id}`\n"
            f"- Final State: `{final_state}`\n"
            f"- Projection Hash: `{self._last_projection_hash}`\n"
            f"- Dashboard Snapshot: `{self.config.dashboard_output_root / 'api' / 'snapshot.json'}`\n"
            f"- Checkpoint: `{self._checkpoint_path}`\n"
            f"- Late Start Mode: `{self._late_start_mode}`\n"
            f"- Stored Explicit Preflight: `{preflight_verdict}` (captured `{preflight_captured_at}`)\n"
        )
        (self.config.report_dir / "continuous_supervisor_summary.md").write_text(summary, encoding="utf-8")
        self._last_report_write_at = now
        self._last_report_state = final_state
        self._record_stage(stage_metrics, "live_supervisor_reports", "EXECUTED", started_at=reports_started_at, ended_at=self.now_provider())

    def _performance_payload(
        self,
        *,
        now: datetime,
        final_state: str,
        stage_metrics: list[StageMetric],
    ) -> dict[str, Any]:
        current_sample = self._build_cycle_sample(now=now, final_state=final_state, stage_metrics=stage_metrics)
        retained_samples = list(self._cycle_metrics_history)
        if not retained_samples or retained_samples[-1]["iteration"] != current_sample["iteration"]:
            retained_samples.append(current_sample)
        durations = sorted(float(item["cycle_duration_ms"]) for item in retained_samples)
        overruns = [float(item["overrun_ms"]) for item in retained_samples]
        return {
            "schema_version": "tfis.live_supervisor.performance_metrics.v2",
            "iterations": self.iterations,
            "poll_seconds": self.config.poll_seconds,
            "projection_hash": self._last_projection_hash,
            "event_count": len(self._timeline),
            "production_scale_claimed": False,
            "sample_count": len(retained_samples),
            "current_cycle": current_sample,
            "cycle_duration_ms": {
                "minimum": round(min(durations), 3),
                "median": round(_percentile(durations, 0.5), 3),
                "p90": round(_percentile(durations, 0.9), 3),
                "p95": round(_percentile(durations, 0.95), 3),
                "maximum": round(max(durations), 3),
            },
            "overrun_count": sum(1 for item in overruns if item > 0),
            "consecutive_overruns": int(retained_samples[-1]["consecutive_overruns"]),
        }

    def _append_timeline(self, event_type: str, result: str, *, now: datetime, **extra: Any) -> None:
        sequence = len(self._timeline) + 1
        event = {
            "event_id": f"supervisor:{sequence:04d}",
            "operator": "SYSTEM",
            "timestamp": now.isoformat(),
            "command": event_type,
            "scope": self.session_id,
            "reason": result,
            "preview": True,
            "result": result,
            "previous_state": self._timeline[-1]["command"] if self._timeline else "NONE",
            "new_state": event_type,
            "evidence_hash": canonical_hash({"event_type": event_type, "result": result, "sequence": sequence, **extra}),
        }
        event.update(extra)
        self._timeline.append(event)

    def _restore_checkpoint_if_available(self) -> None:
        payload = self._load_checkpoint_payload()
        if payload and payload.get("session_date") == self.session_date.isoformat():
            session_started_at = payload.get("session_started_at")
            if isinstance(session_started_at, str):
                try:
                    self._session_started_at = datetime.fromisoformat(session_started_at)
                except ValueError:
                    pass
            self._late_start_mode = bool(payload.get("late_start_mode"))
            self.subscription_owner = SubscriptionOwner.from_dict(payload.get("subscription_owner") or {})
            restored_reads = payload.get("selected_contract_reads") or {}
            if isinstance(restored_reads, Mapping):
                self._selected_contract_history = {
                    str(strategy_instance_id): [dict(item) for item in values if isinstance(item, Mapping)]
                    for strategy_instance_id, values in restored_reads.items()
                    if isinstance(values, list)
                }
            restored_execution = payload.get("paper_execution_state") or {}
            if isinstance(restored_execution, Mapping):
                self._paper_execution_state = {
                    str(strategy_instance_id): dict(state)
                    for strategy_instance_id, state in restored_execution.items()
                    if isinstance(state, Mapping)
                }
            restored_accounts = payload.get("paper_account_snapshots") or {}
            if isinstance(restored_accounts, Mapping):
                self._paper_account_snapshots = {
                    str(account_reference): dict(snapshot)
                    for account_reference, snapshot in restored_accounts.items()
                    if isinstance(snapshot, Mapping)
                }
        self._restore_internal_paper_state_from_ledger()

    def _restore_internal_paper_state_from_ledger(self) -> None:
        if not self.config.db_path.exists():
            return
        db = PersistenceDatabase(self.config.db_path, read_only=True)
        try:
            with db.connect() as connection:
                repo = PersistenceRepositories(connection)
                restored_order_states: dict[str, dict[str, Any]] = {}
                for instance in self.registry.enabled_instances:
                    order_rows = repo.get_internal_client_order_records_by_session(
                        trading_session_id=self.session_id,
                        strategy_instance_id=instance.strategy_instance_id,
                    )
                    if not order_rows:
                        continue
                    order_row = order_rows[0]
                    restored = self._reconstruct_internal_paper_execution_state_from_order_rows(
                        instance=instance,
                        order_row=order_row,
                        fills=repo.get_internal_paper_fills_for_order(client_order_id=str(order_row["client_order_id"])),
                        position_projection=repo.get_latest_internal_paper_position_projection(
                            trading_session_id=self.session_id,
                            strategy_instance_id=instance.strategy_instance_id,
                        ),
                    )
                    if restored:
                        restored_order_states[instance.strategy_instance_id] = restored
                # Ledger-backed financial state replaces checkpoint financial state for
                # every instance for which authoritative ledger rows exist.
                if restored_order_states:
                    self._paper_execution_state.update(restored_order_states)

                account_rows = repo.get_internal_paper_account_projections_for_session(
                    trading_session_id=self.session_id,
                )
                # Rows are ordered oldest-to-newest so the last row for an account is
                # the authoritative latest projection.
                for row in account_rows:
                    account_reference = str(row.get("broker_account_id") or "")
                    if not account_reference:
                        continue
                    payload = self._decode_canonical_payload(row.get("payload_json"))
                    if not isinstance(payload, Mapping):
                        self._ledger_recovery_errors.append(
                            f"ACCOUNT_PROJECTION_PAYLOAD_INVALID:{account_reference}"
                        )
                        continue
                    self._paper_account_snapshots[account_reference] = self._normalize_account_snapshot_payload(payload)
        except Exception as exc:
            # Recovery failures must remain observable; silently swallowing them can
            # make checkpoint state look authoritative. The supervisor can continue
            # for unaffected instances, but the error is retained for reporting/tests.
            self._ledger_recovery_errors.append(
                f"LEDGER_RECOVERY_FAILED:{type(exc).__name__}:{exc}"
            )

    def _reconstruct_internal_paper_execution_state_from_order_rows(
        self,
        *,
        instance: EnabledStrategyInstance,
        order_row: Mapping[str, Any],
        fills: list[dict[str, Any]],
        position_projection: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        order_payload = self._decode_canonical_payload(order_row.get("payload_json"))
        if not isinstance(order_payload, Mapping):
            return None

        order_state = str(
            order_row.get("projected_state")
            if order_row.get("projected_state") is not None
            else order_row.get("current_state") or ""
        )
        selected_contract = str(order_payload.get("normalized_contract") or "")
        base_state: dict[str, Any] = {
            "selected_contract": selected_contract,
            "client_order_id": str(order_row.get("client_order_id") or ""),
            "execution_intent_id": str(order_row.get("execution_intent_id") or ""),
            "position_cycle_id": str(order_row.get("position_cycle_id") or ""),
            "quantity": int(order_payload.get("quantity") or 0),
            "entry_price": str(order_payload.get("limit_price") or order_payload.get("entry_price") or "0.00"),
            "latest_event": "LEDGER_RECOVERY",
            "filled_quantity": int(order_row.get("cumulative_filled_quantity") or 0),
            "entry_time": "",
            "exit_time": None,
            "position_open": False,
            "mark": "",
            "average_entry": "",
            "decision": "RESTORED_FROM_LEDGER",
            "account_reference": str(order_row.get("broker_account_id") or ""),
            "authoritative_state": True,
        }

        if not selected_contract:
            return _blocked_paper_state(
                current_state=base_state,
                continuity={},
                reason="AUTHORITATIVE_ORDER_CONTRACT_MISSING",
                now=self.now_provider(),
            ) | {"authoritative_state": True}

        position_payload = (
            self._decode_canonical_payload(position_projection.get("payload_json"))
            if isinstance(position_projection, Mapping)
            else None
        )
        lifecycle_state = str(position_projection.get("lifecycle_state") or "") if isinstance(position_projection, Mapping) else ""
        remaining_quantity = int(position_projection.get("remaining_quantity") or 0) if isinstance(position_projection, Mapping) else 0

        decoded_fills: list[Mapping[str, Any]] = []
        for fill_row in fills:
            payload = self._decode_canonical_payload(fill_row.get("payload_json"))
            if not isinstance(payload, Mapping):
                continue
            if str(fill_row.get("client_order_id") or "") != base_state["client_order_id"]:
                continue
            if str(fill_row.get("position_cycle_id") or "") not in {"", base_state["position_cycle_id"]}:
                continue
            decoded_fills.append(payload)

        if order_state == "FILLED_INTERNAL":
            if not decoded_fills:
                return _blocked_paper_state(
                    current_state=base_state,
                    continuity={"selected_contract": selected_contract},
                    reason="AUTHORITATIVE_FILL_EVIDENCE_MISSING",
                    now=self.now_provider(),
                ) | {"authoritative_state": True}
            if not isinstance(position_projection, Mapping):
                return _blocked_paper_state(
                    current_state=base_state,
                    continuity={"selected_contract": selected_contract},
                    reason="AUTHORITATIVE_POSITION_EVIDENCE_MISSING",
                    now=self.now_provider(),
                ) | {"authoritative_state": True}
            if str(position_projection.get("position_cycle_id") or "") != base_state["position_cycle_id"]:
                return _blocked_paper_state(
                    current_state=base_state,
                    continuity={"selected_contract": selected_contract},
                    reason="AUTHORITATIVE_POSITION_IDENTITY_CONFLICT",
                    now=self.now_provider(),
                ) | {"authoritative_state": True}

            latest_fill = decoded_fills[-1]
            fill_time = latest_fill.get("recorded_timestamp")
            base_state.update(
                {
                    "order_state": "FILLED_INTERNAL",
                    "fill_state": "FILLED_INTERNAL",
                    "final_state": "FILLED_INTERNAL",
                    "failure": None,
                    "average_entry": str(latest_fill.get("fill_price") or base_state["entry_price"]),
                    "entry_time": fill_time.isoformat() if hasattr(fill_time, "isoformat") else str(fill_time or order_row.get("created_timestamp") or ""),
                    "remaining_quantity": remaining_quantity,
                    "position_open": lifecycle_state.startswith("OPEN_"),
                    "position_lifecycle_state": lifecycle_state,
                    "position_projection": dict(position_payload) if isinstance(position_payload, Mapping) else {},
                }
            )
            return base_state

        if order_state in {
            "PARTIALLY_FILLED_INTERNAL",
            "READY_FOR_INTERNAL_PAPER",
            "VALIDATION_PENDING",
            "ACKNOWLEDGED_INTERNAL",
            "SUBMISSION_PENDING_INTERNAL",
        }:
            base_state.update(
                {
                    "order_state": "READY_INTERNAL",
                    "fill_state": "PARTIALLY_FILLED_INTERNAL" if decoded_fills else "NO_FILL",
                    "final_state": "READY_INTERNAL",
                    "failure": None,
                    "remaining_quantity": remaining_quantity,
                }
            )
            return base_state

        if order_state in {
            "REJECTED_INTERNAL",
            "CANCEL_PENDING_INTERNAL",
            "CANCELLED_INTERNAL",
            "EXPIRED_INTERNAL",
            "TERMINAL_ERROR",
            "UNKNOWN_INTERNAL_REVIEW_REQUIRED",
        }:
            return _blocked_paper_state(
                current_state=base_state,
                continuity={"selected_contract": selected_contract},
                reason=f"AUTHORITATIVE_ORDER_{order_state}",
                now=self.now_provider(),
            ) | {"authoritative_state": True}

        return _blocked_paper_state(
            current_state=base_state,
            continuity={"selected_contract": selected_contract},
            reason=f"UNHANDLED_AUTH_ORDER_STATE_{order_state}",
            now=self.now_provider(),
        ) | {"authoritative_state": True}

    def _decode_canonical_payload(self, payload_json: Any) -> Any:
        if not isinstance(payload_json, str) or not payload_json:
            return None
        try:
            return from_canonical_json(payload_json)
        except Exception:
            try:
                return json.loads(payload_json)
            except Exception:
                return None

    def _normalize_account_snapshot_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "broker_account_id": str(payload.get("broker_account_id") or ""),
            "opening_paper_cash": str(payload.get("opening_paper_cash") or "0"),
            "reserved_margin": str(payload.get("reserved_margin") or "0"),
            "released_margin": str(payload.get("released_margin") or "0"),
            "available_paper_margin": str(payload.get("available_paper_margin") or "0"),
            "simulated_charges": str(payload.get("simulated_charges") or "0"),
            "active_order_reservation": str(payload.get("active_order_reservation") or "0"),
            "margin_per_quantity": str(payload.get("margin_per_quantity") or "0"),
            "account_enabled": bool(payload.get("account_enabled", True)),
            "account_blocked": bool(payload.get("account_blocked", False)),
            "active_order_count": int(payload.get("active_order_count") or 0),
            "max_active_order_count": int(payload.get("max_active_order_count") or 10),
        }

    def _load_checkpoint_payload(self) -> dict[str, Any]:
        try:
            return json.loads(self._checkpoint_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}

    def _acquire_process_lock(self) -> None:
        try:
            self.lock_handle = acquire_process_lock(
                self.config.state_root / "continuous_unified_supervisor.pid.json",
                label="continuous-unified-internal-paper-supervisor",
                metadata={
                    "registry_path": str(self.config.registry_path),
                    "dashboard_output_root": str(self.config.dashboard_output_root),
                },
            )
        except ProcessLockError as exc:
            raise RuntimeError(str(exc)) from exc

    def _detect_late_start(self, now: datetime) -> bool:
        if self._late_start_mode:
            return True
        started = self._session_started_at.timetz().replace(tzinfo=None)
        return started > MARKET_OPEN

    def _state_for_time(self, now: datetime) -> str:
        current = now.timetz().replace(tzinfo=None)
        if self._late_start_mode:
            if current >= EOD_DECISION:
                return "EOD_PROCESSING"
            return "LATE_START_NO_NEW_ENTRY"
        if current < MARKET_OPEN:
            return "WAITING_FOR_MARKET"
        if current < EOD_DECISION:
            return "LIVE_OBSERVATION"
        if current <= MARKET_CLOSE:
            return "EOD_PROCESSING"
        return "STOPPED"

    def _recovery_snapshot(self, *, now: datetime, stage_metrics: list[StageMetric] | None = None) -> dict[str, Any]:
        if (
            self._cached_recovery_snapshot_value is not None
            and self._cached_recovery_snapshot_at is not None
            and self._cache_is_fresh(
                cached_at=self._cached_recovery_snapshot_at,
                now=now,
                ttl_seconds=self.config.recovery_refresh_interval_seconds,
            )
        ):
            if stage_metrics is not None:
                self._record_stage(stage_metrics, "recovery_snapshot", "CACHED", started_at=now, ended_at=now)
            return self._cached_recovery_snapshot_value

        started_at = self.now_provider()
        db = PersistenceDatabase(self.config.db_path)
        with db.connect() as connection:
            apply_migrations(connection)
            connection.commit()
            recovery = assess_recovery(
                connection,
                expected_configuration_hash=self.registry.registry_hash,
                expected_rule_matrix_version=RULE_MATRIX_VERSION,
            ).to_dict()
            integrity = run_integrity_scan(connection)
        snapshot = {"recovery": recovery, "integrity": integrity}
        self._cached_recovery_snapshot_value = snapshot
        self._cached_recovery_snapshot_at = now
        if stage_metrics is not None:
            self._record_stage(stage_metrics, "recovery_snapshot", "EXECUTED", started_at=started_at, ended_at=self.now_provider())
        return snapshot

    def _auth_result_for_cycle(self, *, now: datetime, stage_metrics: list[StageMetric]) -> BrokerAuthenticationResult:
        if (
            self._latest_auth is not None
            and self._latest_auth_checked_at is not None
            and self._latest_auth.status is BrokerSessionStatus.AUTHENTICATED
            and self._cache_is_fresh(
                cached_at=self._latest_auth_checked_at,
                now=now,
                ttl_seconds=self.config.auth_revalidate_interval_seconds,
            )
        ):
            self._record_stage(stage_metrics, "broker_authentication", "CACHED", started_at=now, ended_at=now)
            return self._latest_auth
        started_at = self.now_provider()
        auth_adapter = self.auth_factory(self.config.repo_root)
        auth_result = auth_adapter.authenticate(allow_refresh=False, validate_session=True)
        refresh_recovered = False
        if (
            auth_result.status is BrokerSessionStatus.SESSION_VALIDATION_FAILED
            and self._stored_preflight_ready_for_session()
        ):
            retry_result = auth_adapter.authenticate(allow_refresh=True, validate_session=True)
            if retry_result.status is BrokerSessionStatus.AUTHENTICATED:
                auth_result = retry_result
                refresh_recovered = True
        self._latest_auth_checked_at = now
        self._record_stage(
            stage_metrics,
            "broker_authentication",
            "EXECUTED",
            started_at=started_at,
            ended_at=self.now_provider(),
            details={"status": auth_result.status.value, "refresh_recovered": refresh_recovered},
        )
        return auth_result

    def _stored_preflight_ready_for_session(self) -> bool:
        preflight_path = self.config.report_dir / "complete_session_preflight.json"
        try:
            payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return False
        if str(payload.get("verdict") or "") != "READY_FOR_COMPLETE_UNIFIED_SESSION":
            return False
        session_id = payload.get("session_id")
        return session_id is None or str(session_id) == self.session_id

    def _cache_is_fresh(self, *, cached_at: datetime, now: datetime, ttl_seconds: float) -> bool:
        return (now - cached_at).total_seconds() < ttl_seconds

    def _record_stage(
        self,
        stage_metrics: list[StageMetric],
        stage: str,
        status: str,
        *,
        started_at: datetime,
        ended_at: datetime,
        scope: str = "SESSION",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        stage_metrics.append(
            StageMetric(
                stage=stage,
                status=status,
                duration_ms=round((ended_at - started_at).total_seconds() * 1000.0, 3),
                started_at=started_at.isoformat(),
                ended_at=ended_at.isoformat(),
                scope=scope,
                details=details,
            )
        )

    def _build_cycle_sample(
        self,
        *,
        now: datetime,
        final_state: str,
        stage_metrics: list[StageMetric],
    ) -> dict[str, Any]:
        total_metric = next((item for item in stage_metrics if item.stage == "cycle_total"), None)
        if total_metric is None:
            total_ms = 0.0
        else:
            total_ms = float((total_metric.details or {}).get("cycle_duration_ms", total_metric.duration_ms))
        overrun_ms = max(0.0, total_ms - (self.config.poll_seconds * 1000.0))
        previous_overruns = self._cycle_metrics_history[-1]["consecutive_overruns"] if self._cycle_metrics_history else 0
        consecutive_overruns = previous_overruns + 1 if overrun_ms > 0 else 0
        return {
            "iteration": self.iterations,
            "captured_at": now.isoformat(),
            "final_state": final_state,
            "poll_seconds": self.config.poll_seconds,
            "cycle_duration_ms": total_ms,
            "overrun_ms": round(overrun_ms, 3),
            "consecutive_overruns": consecutive_overruns,
            "stage_metrics": [
                {
                    "stage": item.stage,
                    "status": item.status,
                    "duration_ms": item.duration_ms,
                    "started_at": item.started_at,
                    "ended_at": item.ended_at,
                    "scope": item.scope,
                    "details": dict(item.details or {}),
                }
                for item in stage_metrics
            ],
        }

    def _append_cycle_history(self, *, now: datetime, final_state: str, stage_metrics: list[StageMetric]) -> None:
        sample = self._build_cycle_sample(now=now, final_state=final_state, stage_metrics=stage_metrics)
        self._cycle_metrics_history.append(sample)
        if len(self._cycle_metrics_history) > self.config.performance_retention_cycles:
            self._cycle_metrics_history = self._cycle_metrics_history[-self.config.performance_retention_cycles :]

    def _load_existing_preflight_report(self) -> dict[str, Any]:
        report_path = self.config.report_dir / "complete_session_preflight.json"
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"verdict": "NOT_RUN_IN_HOT_LOOP", "reasons": ["RUN_EXPLICIT_PREFLIGHT_COMMAND"]}
        except json.JSONDecodeError:
            return {"verdict": "INVALID_EXISTING_PREFLIGHT_REPORT", "reasons": ["PREFLIGHT_REPORT_MALFORMED"]}
        return payload if isinstance(payload, dict) else {"verdict": "INVALID_EXISTING_PREFLIGHT_REPORT", "reasons": ["PREFLIGHT_REPORT_NOT_OBJECT"]}


def run_continuous_supervisor(
    *,
    repo_root: str | Path,
    registry_path: str | Path,
    report_dir: str | Path,
    state_root: str | Path,
    dashboard_output_root: str | Path,
    db_path: str | Path,
    dashboard_port: int = 8766,
    poll_seconds: float = 5.0,
    max_iterations: int = 0,
    session_date: date | None = None,
    reconstruct_if_late: bool = False,
) -> ContinuousSupervisorRunResult:
    config = ContinuousSupervisorConfig(
        repo_root=Path(repo_root),
        registry_path=Path(repo_root) / registry_path,
        report_dir=Path(repo_root) / report_dir,
        state_root=Path(repo_root) / state_root,
        dashboard_output_root=Path(repo_root) / dashboard_output_root,
        db_path=Path(repo_root) / db_path,
        dashboard_port=dashboard_port,
        poll_seconds=poll_seconds,
        max_iterations=max_iterations,
        session_date=session_date,
    )
    _ = reconstruct_if_late
    return UnifiedInternalPaperSupervisor(config).run()


def run_complete_session_preflight(
    *,
    repo_root: str | Path,
    registry_path: str | Path,
    report_dir: str | Path,
    db_path: str | Path,
    now_provider: Callable[[], datetime] | None = None,
    auth_factory: Callable[[Path], FyersAuthenticationAdapter] | None = None,
    allow_existing_lock: bool = False,
) -> CompleteSessionPreflightResult:
    root = Path(repo_root)
    now = (now_provider or (lambda: datetime.now(tz=IST)))()
    registry = load_enabled_strategy_registry(root / registry_path)
    reasons: list[str] = []
    auth_adapter = (auth_factory or (lambda tfis_root: FyersAuthenticationAdapter(tfis_root=tfis_root, logical_account_ref="unified-preflight")))(root)
    auth_result = auth_adapter.authenticate(allow_refresh=False, validate_session=True)
    if auth_result.status is not BrokerSessionStatus.AUTHENTICATED:
        reasons.append(f"AUTHENTICATION_{auth_result.status.value}")
    if now.tzinfo is None or str(now.tzinfo) not in {"Asia/Calcutta", "Asia/Kolkata"}:
        reasons.append("CLOCK_TIMEZONE_INVALID")
    db = PersistenceDatabase(root / db_path)
    with db.connect() as connection:
        integrity = run_integrity_scan(connection)
        recovery = assess_recovery(
            connection,
            expected_configuration_hash=registry.registry_hash,
            expected_rule_matrix_version=RULE_MATRIX_VERSION,
        )
    if integrity["status"] != "PASS":
        reasons.append("DB_INTEGRITY_FAILED")
    if recovery.status.value in {"UNSUPPORTED_SCHEMA", "CORRUPTED_STATE"}:
        reasons.append(f"RECOVERY_{recovery.status.value}")
    if not allow_existing_lock:
        lock_path = root / "tmp" / "tfis_supervisor_state" / "continuous_unified_supervisor.pid.json"
        if _pid_metadata_is_active(lock_path):
            reasons.append("DUPLICATE_SUPERVISOR_PROCESS_LOCK_PRESENT")
    verdict = "READY_FOR_COMPLETE_UNIFIED_SESSION" if not reasons else "FAIL_CLOSED"
    payload = {
        "schema_version": "tfis.live_supervisor.complete_session_preflight.v1",
        "captured_at": now.isoformat(),
        "verdict": verdict,
        "reasons": reasons,
        "registry_hash": registry.registry_hash,
        "session_date": now.date().isoformat(),
        "auth_status": auth_result.status.value,
        "db_integrity_status": integrity["status"],
        "recovery_status": recovery.status.value,
    }
    report_path = Path(report_dir) / "complete_session_preflight.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return CompleteSessionPreflightResult(verdict=verdict, reasons=tuple(reasons), report_path=report_path)


def build_authoritative_readiness_projection(
    *,
    repo_root: str | Path,
    report_dir: str | Path,
    now_provider: Callable[[], datetime] | None = None,
) -> AuthoritativeReadinessProjectionResult:
    root = Path(repo_root)
    report_root = Path(report_dir)
    report_root.mkdir(parents=True, exist_ok=True)
    now = (now_provider or (lambda: datetime.now(tz=IST)))()

    dashboard_readiness_path = root / "reports" / "dashboard_v1" / "market_session_readiness.json"
    runtime_readiness_path = root / "reports" / "runtime_performance" / "next_session_readiness.json"
    preflight_path = root / "reports" / "live_supervisor" / "complete_session_preflight.json"
    heartbeat_path = root / "tmp" / "tfis_supervisor_state" / "heartbeat.json"
    pid_metadata_path = root / "tmp" / "tfis_supervisor_state" / "continuous_unified_supervisor.pid.json"

    dashboard_readiness = _read_json_object(dashboard_readiness_path)
    runtime_readiness = _read_json_object(runtime_readiness_path)
    preflight = _read_json_object(preflight_path)
    heartbeat = _read_json_object(heartbeat_path)
    pid_metadata = _read_json_object(pid_metadata_path)

    blocking_reasons: list[str] = []
    warnings: list[str] = []

    preflight_verdict = str(preflight.get("verdict") or "MISSING")
    preflight_reasons = [str(item) for item in (preflight.get("reasons") or [])]
    if preflight_verdict != "READY_FOR_COMPLETE_UNIFIED_SESSION":
        if preflight_reasons:
            blocking_reasons.extend(preflight_reasons)
        else:
            blocking_reasons.append(f"PREFLIGHT_{preflight_verdict}")

    runtime_verdict = str(runtime_readiness.get("verdict") or "MISSING")
    runtime_reasons = [str(item) for item in (runtime_readiness.get("reasons") or [])]
    if runtime_verdict != "READY_FOR_COMPLETE_UNIFIED_SESSION":
        if runtime_reasons:
            blocking_reasons.extend(runtime_reasons)
        else:
            blocking_reasons.append(f"RUNTIME_READINESS_{runtime_verdict}")

    deterministic_readiness = str(dashboard_readiness.get("readiness") or "UNKNOWN")
    if deterministic_readiness == "READY_FOR_UNIFIED_MARKET_SESSION" and blocking_reasons:
        warnings.append("DETERMINISTIC_DASHBOARD_READINESS_IS_SUPPORTING_EVIDENCE_ONLY")

    heartbeat_state = str(heartbeat.get("state") or "MISSING")
    heartbeat_session_id = str(heartbeat.get("session_id") or "UNKNOWN")
    active_process_lock = _pid_metadata_is_active(pid_metadata_path)
    if active_process_lock and "DUPLICATE_SUPERVISOR_PROCESS_LOCK_PRESENT" not in blocking_reasons:
        blocking_reasons.append("DUPLICATE_SUPERVISOR_PROCESS_LOCK_PRESENT")
    if heartbeat_state == "LIVE_OBSERVATION":
        warnings.append("CURRENT_SUPERVISOR_SESSION_IS_LATE_START_OBSERVATION_MODE")

    deduped_blocking = list(dict.fromkeys(blocking_reasons))
    deduped_warnings = list(dict.fromkeys(warnings))
    verdict = "GO_FOR_NEXT_COMPLETE_UNIFIED_SESSION" if not deduped_blocking else "NO_GO_FOR_NEXT_COMPLETE_UNIFIED_SESSION"

    projection = {
        "schema_version": "tfis.unified_internal_paper.authoritative_readiness_projection.v1",
        "captured_at": now.isoformat(),
        "verdict": verdict,
        "authority_mode": "INTERNAL_PAPER_ONLY",
        "external_broker_order_authority": "NONE",
        "go_for_next_complete_session": verdict == "GO_FOR_NEXT_COMPLETE_UNIFIED_SESSION",
        "governing_inputs": {
            "dashboard_market_session_readiness": {
                "path": str(dashboard_readiness_path),
                "readiness": deterministic_readiness,
                "verdict": dashboard_readiness.get("verdict"),
            },
            "runtime_next_session_readiness": {
                "path": str(runtime_readiness_path),
                "verdict": runtime_verdict,
                "reasons": runtime_reasons,
            },
            "complete_session_preflight": {
                "path": str(preflight_path),
                "captured_at": preflight.get("captured_at"),
                "verdict": preflight_verdict,
                "reasons": preflight_reasons,
            },
            "current_supervisor_heartbeat": {
                "path": str(heartbeat_path),
                "state": heartbeat_state,
                "timestamp": heartbeat.get("timestamp"),
                "session_id": heartbeat_session_id,
                "late_start_mode": heartbeat.get("late_start_mode"),
            },
            "current_supervisor_pid_metadata": {
                "path": str(pid_metadata_path),
                "pid": pid_metadata.get("pid"),
                "created_at": pid_metadata.get("created_at"),
                "active_process_lock": active_process_lock,
            },
        },
        "blocking_reasons": deduped_blocking,
        "warnings": deduped_warnings,
        "next_required_actions": [
            "Refresh FYERS read-only authentication until diagnostics return AUTHENTICATED.",
            "Gracefully stop the current late-start supervisor if it is still active.",
            "Re-run complete-session preflight and require READY_FOR_COMPLETE_UNIFIED_SESSION.",
            "Start one fresh before-market-open unified supervisor run on the optimized code path.",
        ],
    }

    operator_package = {
        "schema_version": "tfis.unified_internal_paper.clean_start_operator_package.v1",
        "captured_at": now.isoformat(),
        "authoritative_readiness_verdict": verdict,
        "authority_mode": "INTERNAL_PAPER_ONLY",
        "external_broker_order_authority": "NONE",
        "commands": [
            {
                "step": 1,
                "name": "refresh_fyers_token",
                "command": ".\\.venv\\Scripts\\python.exe scripts\\fyers_token_refresh.py --prepare",
                "expect": "Token/session prepared for read-only diagnostics.",
            },
            {
                "step": 2,
                "name": "run_broker_diagnostics",
                "command": ".\\.venv\\Scripts\\python.exe scripts\\run_broker_diagnostics.py --broker fyers",
                "expect": "authentication_status=AUTHENTICATED and order_write_status=NOT_AUTHORIZED",
            },
            {
                "step": 3,
                "name": "graceful_stop_existing_supervisor_if_active",
                "command": "New-Item -ItemType File -Force tmp\\tfis_supervisor_state\\continuous_unified_supervisor.stop",
                "expect": "Existing late-start supervisor shuts down cleanly and the active lock clears.",
            },
            {
                "step": 4,
                "name": "run_complete_session_preflight",
                "command": ".\\.venv\\Scripts\\python.exe scripts\\run_tfis_internal_paper.py --preflight-complete-session",
                "expect": "READY_FOR_COMPLETE_UNIFIED_SESSION",
            },
            {
                "step": 5,
                "name": "start_unified_supervisor",
                "command": ".\\.venv\\Scripts\\python.exe scripts\\run_tfis_internal_paper.py --continuous-supervisor --poll-seconds 5 --dashboard-port 8766",
                "expect": "Fresh before-market-open unified supervisor session starts on the optimized path.",
            },
            {
                "step": 6,
                "name": "start_dashboard",
                "command": ".\\.venv\\Scripts\\python.exe scripts\\run_tfis_dashboard.py --serve --port 8766",
                "expect": "Local read-only dashboard available at http://127.0.0.1:8766/index.html",
            },
        ],
        "must_verify": [
            "reports/unified_readiness/authoritative_readiness_projection.json",
            "reports/live_supervisor/complete_session_preflight.json",
            "tmp/tfis_supervisor_state/heartbeat.json",
            "tmp/tfis_dashboard_v1/api/snapshot.json",
        ],
    }

    report_path = report_root / "authoritative_readiness_projection.json"
    package_json_path = report_root / "clean_start_operator_package.json"
    package_md_path = report_root / "clean_start_operator_package.md"
    report_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    package_json_path.write_text(json.dumps(operator_package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    package_md_path.write_text(_clean_start_operator_package_markdown(operator_package), encoding="utf-8")
    return AuthoritativeReadinessProjectionResult(
        verdict=verdict,
        report_path=report_path,
        operator_package_json=package_json_path,
        operator_package_md=package_md_path,
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean_start_operator_package_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Clean-Start Operator Package",
        "",
        f"- Captured At: `{payload['captured_at']}`",
        f"- Authoritative Readiness Verdict: `{payload['authoritative_readiness_verdict']}`",
        f"- External Broker Order Authority: `{payload['external_broker_order_authority']}`",
        "",
        "## Commands",
        "",
    ]
    for item in payload["commands"]:
        lines.extend(
            [
                f"{item['step']}. `{item['name']}`",
                f"   - Command: `{item['command']}`",
                f"   - Expect: {item['expect']}",
            ]
        )
    lines.extend(["", "## Must Verify", ""])
    for item in payload["must_verify"]:
        lines.append(f"- `{item}`")
    lines.append("")
    return "\n".join(lines)


def _live_instance_result(
    instance: EnabledStrategyInstance,
    *,
    now: datetime,
    session_id: str,
    continuity: Mapping[str, Any],
    timing: Mapping[str, Any],
    selected_contract_reads: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    late_start: bool,
    action_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    selected_contract = continuity.get("selected_contract")
    selected_contract_text = str(selected_contract) if selected_contract else None
    live_plan = continuity.get("live_plan") if isinstance(continuity.get("live_plan"), Mapping) else {}
    quote = continuity.get("selected_contract_quote") if isinstance(continuity.get("selected_contract_quote"), Mapping) else {}
    recovery_mode = str(continuity.get("recovery_mode") or ("LIVE_OBSERVED" if not late_start else "LATE_START_UNRECOVERED"))
    current_entry_state = str(continuity.get("current_entry_state") or "")
    recovered_late_start = recovery_mode == "HISTORICALLY_RECONSTRUCTED"
    entry_still_valid = current_entry_state in {"NORMAL_ENTRY_STILL_VALID", "RC_ENTRY_STILL_VALID"}
    late_start_blocked = late_start and not recovered_late_start
    action_state = action_state or {}
    entry = str(continuity.get("entry") or live_plan.get("entry") or instance.deterministic_projection.get("entry") or "")
    target = str(continuity.get("target") or live_plan.get("target") or instance.deterministic_projection.get("target") or "")
    sl = str(
        continuity.get("original_sl")
        or live_plan.get("original_sl")
        or instance.deterministic_projection.get("original_sl")
        or ""
    )
    blocked_reason = None if selected_contract_text and current_entry_state != "BLOCKED_INSUFFICIENT_HISTORICAL_EVIDENCE" else continuity.get("status", "SELECTED_CONTRACT_MISSING")
    if selected_contract_text and recovered_late_start and not blocked_reason:
        plan_status = "PREPARED"
    else:
        plan_status = "PREPARED" if selected_contract_text and not blocked_reason else "BLOCKED"
    runtime_stage = "LATE_START_NO_NEW_ENTRY" if late_start_blocked else _instance_runtime_stage(timing)
    evidence_quality = str(continuity.get("evidence") or instance.evidence_quality)
    alert_items = list(_instance_alerts(instance, continuity, late_start=late_start))
    quantity = int(instance.configured_quantity["lots"]) * int(instance.configured_quantity["lot_size"])
    has_action_state = bool(action_state)
    risk_result = (
        str(action_state.get("risk_result") or "ACCEPTED")
        if has_action_state
        else ("DEFERRED" if late_start_blocked else ("ACCEPTED" if entry_still_valid else "BLOCKED_BY_RULE"))
    )
    order_state = (
        str(action_state.get("order_state") or "NO_ORDER")
        if has_action_state
        else ("NO_ORDER" if late_start_blocked or not entry_still_valid else "NO_ORDER")
    )
    fill_state = str(action_state.get("fill_state") or "NO_FILL") if has_action_state else "NO_FILL"
    live_market_references = live_plan.get("market_references") if isinstance(live_plan.get("market_references"), Mapping) else {}
    live_timing = live_plan.get("timing") if isinstance(live_plan.get("timing"), Mapping) else {}
    first_read = selected_contract_reads[0] if selected_contract_reads else {}
    last_read = selected_contract_reads[-1] if selected_contract_reads else {}
    option_type = continuity.get("selected_option_type") or quote.get("option_type")
    expiry = continuity.get("selected_expiry")
    strike = continuity.get("selected_strike")
    plan_hash = str(live_plan.get("plan_hash") or "")
    if not plan_hash:
        plan_hash = canonical_hash(
            {
                "strategy_instance_id": instance.strategy_instance_id,
                "selected_contract": selected_contract_text,
                "monthly_status": continuity.get("monthly_status") or live_plan.get("monthly_status") or instance.deterministic_projection.get("monthly_status"),
            }
        )
    return {
        "trading_session_id": session_id,
        "runtime_stage": runtime_stage,
        "health": "DEGRADED_EVIDENCE" if blocked_reason else "HEALTHY",
        "last_update": now.isoformat(),
        "plan": {
            "market_references": dict(live_market_references or instance.deterministic_projection.get("market_references") or {}),
            "expiry_candidates": list(instance.deterministic_projection.get("expiry_candidates") or []),
            "selected_contract": selected_contract_text,
            "selected_option_type": option_type,
            "selected_expiry": expiry,
            "selected_strike": strike,
            "premium": str(quote.get("ltp") or entry or ""),
            "oi": str(quote.get("oi") or ("LIVE_READ_REQUIRED" if evidence_quality.startswith("LIVE") else "SOURCE_PROJECTION")),
            "base_entry": entry,
            "target": target,
            "original_sl": sl,
            "orpt": str(live_timing.get("orpt") or instance.deterministic_projection.get("orpt") or "09:24:59.400000"),
            "rc": str(live_timing.get("rc") or instance.deterministic_projection.get("rc") or "09:29:59.400000"),
            "plan_status": plan_status,
            "block_reason": blocked_reason,
            "monthly_status": continuity.get("monthly_status") or live_plan.get("monthly_status") or instance.deterministic_projection.get("monthly_status"),
            "branch": continuity.get("selected_branch") or live_plan.get("selected_branch") or instance.deterministic_projection.get("branch"),
            "plan_hash": plan_hash,
            "evidence_quality": evidence_quality,
            "selection_timestamp": str(quote.get("source_timestamp") or first_read.get("source_timestamp") or now.isoformat()),
            "source_timestamp": str(quote.get("source_timestamp") or now.isoformat()),
            "receipt_timestamp": str(quote.get("receipt_timestamp") or last_read.get("receipt_timestamp") or now.isoformat()),
            "chain_quality_state": continuity.get("status"),
            "subscription_state": "PINNED" if selected_contract_text else "NOT_PINNED",
            "first_quote_timestamp": str(first_read.get("receipt_timestamp") or quote.get("receipt_timestamp") or now.isoformat()),
            "latest_quote_timestamp": str(last_read.get("receipt_timestamp") or quote.get("receipt_timestamp") or now.isoformat()),
            "history_completeness": continuity.get("option_history_status") or ("CAPTURED" if selected_contract_reads else "NOT_CAPTURED"),
        },
        "execution": {
            "selected_contract": selected_contract_text,
            "opening_context": "HISTORICALLY_RECONSTRUCTED" if recovered_late_start else ("MISSED_BEFORE_SUPERVISOR_START" if late_start else instance.deterministic_projection.get("opening_context")),
            "orpt_state": continuity.get("orpt_result") or timing.get("orpt"),
            "rc_state": continuity.get("rc_result") or timing.get("rc"),
            "effective_entry": entry,
            "execution_intent": (
                "VALIDATED_NOT_SUBMITTABLE"
                if order_state in {"READY_INTERNAL", "FILLED_INTERNAL"}
                else ("PENDING_VALIDATION" if entry_still_valid else ("NOT_CREATED_LATE_START" if late_start_blocked else "NOT_CREATED_RECONSTRUCTED_MISSED"))
            ),
            "risk_result": risk_result,
            "order_state": order_state,
            "fill_state": fill_state,
            "order_purpose": "ENTRY",
            "filled_quantity": int(action_state.get("filled_quantity") or 0),
            "protection_generation": 1 if fill_state == "FILLED_INTERNAL" else 0,
            "order_age": _age_from_iso_timestamp(action_state.get("entry_time"), now=now) if action_state.get("entry_time") else "00:00:00",
            "latest_event": str(action_state.get("latest_event") or timing.get("market_open")),
            "failure": str(action_state.get("failure") or blocked_reason) if (action_state.get("failure") or blocked_reason) else None,
            "simulated_or_observed": "INTERNAL_PAPER_SIMULATED",
        },
        "position": {
            "position_cycle": str(action_state.get("position_cycle_id") or f"pc:{canonical_hash(instance.strategy_instance_id)[:16]}"),
            "selected_contract": selected_contract_text,
            "quantity": quantity,
            "average_entry": str(action_state.get("average_entry") or ("0.00" if fill_state != "FILLED_INTERNAL" else entry)),
            "remaining_quantity": int(action_state.get("remaining_quantity") or (quantity if fill_state == "FILLED_INTERNAL" else 0)),
            "mark": str(action_state.get("mark") or quote.get("ltp") or ""),
            "target": target,
            "active_protection": sl,
            "protection_status": "PROTECTED" if fill_state == "FILLED_INTERNAL" else "NO_POSITION",
            "fresh_or_carried": "CARRIED" if bool(instance.deterministic_projection.get("scenario_flags", {}).get("carried_position_candidate")) else "FRESH",
            "carried_state": "OBSERVATION_ONLY" if late_start_blocked else "NOT_CARRIED",
            "exit_reason": "OPEN" if fill_state == "FILLED_INTERNAL" else ("NO_NEW_ENTRY" if late_start_blocked else "PENDING_ENTRY"),
            "exit_deadline": EOD_DECISION.isoformat(),
            "health": "OPEN_PROTECTED" if fill_state == "FILLED_INTERNAL" else "NO_POSITION",
            "entry_time": action_state.get("entry_time"),
            "exit_time": action_state.get("exit_time"),
        },
        "accounting": {
            "selected_contract": selected_contract_text,
            "realized_pnl": "0.00",
            "unrealized_pnl": _live_unrealized_pnl(
                entry_price=action_state.get("average_entry") or action_state.get("entry_price"),
                mark_price=action_state.get("mark") or quote.get("ltp"),
                quantity=int(action_state.get("remaining_quantity") or 0),
                side="SELL",
            ) if fill_state == "FILLED_INTERNAL" else "0.00",
            "charges_quality": "PROVISIONAL_INTERNAL_PAPER",
            "trade_classification": (
                "NO_TRADE_LATE_START"
                if late_start_blocked
                else (
                    current_entry_state
                    if recovered_late_start and current_entry_state
                    else str(instance.deterministic_projection.get("trade_classification") or "OPEN")
                )
            ),
            "accounting_quality": "INTERNAL_PAPER_SIMULATED",
        },
        "operations": {
            "alerts": alert_items,
            "reconciliation": "READ_ONLY_RECOVERY_PENDING" if late_start_blocked else "READY",
            "checkpoint": f"{session_id}:{instance.strategy_instance_id}:iteration",
            "broker_data_health": continuity.get("status", "UNKNOWN"),
            "authority_mode": instance.authority_mode,
            "evidence_label": evidence_quality,
            "entry_time": action_state.get("entry_time"),
            "exit_time": action_state.get("exit_time"),
            "lots": int(instance.configured_quantity["lots"]),
        },
    }


def _pid_metadata_is_active(pid_metadata_path: Path) -> bool:
    payload = _read_lock_payload(pid_metadata_path)
    if not payload:
        return False
    pid = payload.get("pid")
    try:
        resolved_pid = int(pid)
    except (TypeError, ValueError):
        return False
    return _process_exists(resolved_pid) and _process_matches_payload(resolved_pid, payload)


def _instance_runtime_stage(timing: Mapping[str, Any]) -> str:
    if timing.get("market_open") == "FUTURE_WINDOW":
        return "WAITING_FOR_MARKET"
    if timing.get("orpt") == "FUTURE_WINDOW":
        return "WAITING_FOR_ORPT"
    if timing.get("rc") == "FUTURE_WINDOW":
        return "WAITING_FOR_RC"
    if timing.get("eod_carry") == "FUTURE_WINDOW":
        return "POSITION_MONITORING"
    return "EOD_PROCESSING"


def _instance_alerts(instance: EnabledStrategyInstance, continuity: Mapping[str, Any], *, late_start: bool) -> tuple[dict[str, Any], ...]:
    alerts: list[dict[str, Any]] = []
    if late_start and continuity.get("recovery_mode") != "HISTORICALLY_RECONSTRUCTED":
        alerts.append(
            {
                "severity": "WARNING",
                "code": "LATE_START_NO_NEW_ENTRY",
                "message": f"{instance.strategy_instance_id} started after authoritative timing windows; no retroactive entry allowed.",
            }
        )
    if continuity.get("recovery_mode") == "HISTORICALLY_RECONSTRUCTED":
        alerts.append(
            {
                "severity": "INFO",
                "code": "HISTORICAL_RECONSTRUCTION_ACTIVE",
                "message": f"{instance.strategy_instance_id} was recovered from timestamped FYERS historical evidence.",
            }
        )
    if continuity.get("status") == "CURRENT_SESSION_SELECTION_NOT_OBSERVED_BY_SUPERVISOR":
        alerts.append(
            {
                "severity": "WARNING",
                "code": "SELECTED_CONTRACT_NOT_OBSERVED",
                "message": f"{instance.strategy_instance_id} could not safely claim a current-session selected contract.",
            }
        )
    if continuity.get("status") == "AUTHENTICATION_FAILED":
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "FYERS_SESSION_EXPIRED",
                "message": "FYERS read-only authentication is unavailable.",
            }
        )
    return tuple(alerts)


def _global_alerts(*, late_start: bool, auth_status: str, continuity: Mapping[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if auth_status != "AUTHENTICATED":
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "TOKEN_SESSION_EXPIRED",
                "message": f"Broker authentication status is {auth_status}.",
            }
        )
    if late_start:
        unrecovered = [item for item in continuity.values() if item.get("recovery_mode") != "HISTORICALLY_RECONSTRUCTED"]
        if unrecovered:
            alerts.append(
                {
                    "severity": "WARNING",
                    "code": "LATE_START_PARTIAL_BLOCK",
                    "message": "One or more strategy instances started late and could not be fully reconstructed.",
                }
            )
    if any(item.get("status") == "CURRENT_SESSION_SELECTION_NOT_OBSERVED_BY_SUPERVISOR" for item in continuity.values()):
        alerts.append(
            {
                "severity": "WARNING",
                "code": "SELECTED_CONTRACT_MISSING",
                "message": "One or more strategy instances do not have safe current-session selected-contract continuity.",
            }
        )
    return alerts


def _timing_matrix(registry: EnabledStrategyRegistry, *, now: datetime, late_start: bool) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for item in registry.enabled_instances:
        rows[item.strategy_instance_id] = {
            "market_open": _classify_window(now, MARKET_OPEN, late_start=late_start),
            "orpt": _classify_window(now, ORPT_TIME, late_start=late_start),
            "rc": _classify_window(now, RC_TIME, late_start=late_start),
            "eod_carry": _classify_window(now, EOD_DECISION, late_start=False),
            "shutdown_checkpoint": "FUTURE_WINDOW" if now.timetz().replace(tzinfo=None) < MARKET_CLOSE else "CURRENT_WINDOW",
        }
    return {
        "schema_version": "tfis.live_supervisor.timing_matrix.v1",
        "captured_at": now.isoformat(),
        "instances": rows,
    }


def _classify_window(now: datetime, event_time: time, *, late_start: bool) -> str:
    current = now.timetz().replace(tzinfo=None)
    if current < event_time:
        return "FUTURE_WINDOW"
    if late_start:
        return "MISSED_BEFORE_SUPERVISOR_START"
    return "CURRENT_WINDOW" if current == event_time else "CAPTURED"


def _next_sleep_seconds(
    *,
    now: datetime,
    current_monotonic: float,
    next_poll_deadline_monotonic: float,
    late_start: bool,
) -> float:
    poll_sleep = max(0.0, next_poll_deadline_monotonic - current_monotonic)
    critical_sleep = _seconds_until_next_critical_event(now, late_start=late_start)
    if critical_sleep is None:
        return poll_sleep
    return max(0.0, min(poll_sleep, critical_sleep))


def _seconds_until_next_critical_event(now: datetime, *, late_start: bool) -> float | None:
    current = now.timetz().replace(tzinfo=None)
    candidates: list[time] = []
    if not late_start and current < MARKET_OPEN:
        candidates.append(MARKET_OPEN)
    if not late_start and current < ORPT_TIME:
        candidates.append(ORPT_TIME)
    if not late_start and current < RC_TIME:
        candidates.append(RC_TIME)
    if current < EOD_DECISION:
        candidates.append(EOD_DECISION)
    if current < MARKET_CLOSE:
        candidates.append(MARKET_CLOSE)
    if not candidates:
        return None
    target = min(candidates)
    target_dt = now.replace(
        hour=target.hour,
        minute=target.minute,
        second=target.second,
        microsecond=target.microsecond,
    )
    return max(0.0, (target_dt - now).total_seconds())


def _market_session_state(now: datetime) -> str:
    if now.weekday() >= 5:
        return "CLOSED_WEEKEND"
    current = now.timetz().replace(tzinfo=None)
    if current < MARKET_OPEN:
        return "PRE_OPEN"
    if current <= MARKET_CLOSE:
        return "LIVE"
    return "POST_MARKET"


def _load_underlying_symbols(root: Path) -> dict[str, str]:
    data = yaml.safe_load((root / "config" / "monthly_status_instruments.yaml").read_text(encoding="utf-8")) or {}
    instruments = data.get("instruments") or {}
    symbols = {
        str(symbol): str(details.get("spot_symbol"))
        for symbol, details in instruments.items()
        if isinstance(details, Mapping) and details.get("spot_symbol")
    }
    symbols.setdefault("RELIANCE", "NSE:RELIANCE-EQ")
    return symbols


def _resolve_underlying_symbol(symbol: str, underlying_symbols: Mapping[str, str]) -> str:
    return str(underlying_symbols.get(symbol) or f"NSE:{symbol}-EQ")


def _revised_entry_for_instance(instance: EnabledStrategyInstance, *, continuity: Mapping[str, Any]) -> Decimal | None:
    raw_value = continuity.get("revised_entry")
    if raw_value in (None, ""):
        live_plan = continuity.get("live_plan") if isinstance(continuity.get("live_plan"), Mapping) else {}
        raw_prices = live_plan.get("raw_prices") if isinstance(live_plan.get("raw_prices"), Mapping) else {}
        raw_value = raw_prices.get("revised_entry")
    if raw_value in (None, ""):
        if instance.strategy_instance_id == "S22_RELIANCE_INTERNAL_PAPER_A":
            return Decimal("57.00")
        return None
    return Decimal(str(raw_value))


def _latest_reliance_snapshot_contract(root: Path) -> str | None:
    base = root / "data" / "strategies" / "S22" / "fyers_read_only_snapshots" / date.today().isoformat()
    snapshots = sorted(base.glob("s22-reliance-fyers-*/snapshot.json"))
    if not snapshots:
        return None
    payload = json.loads(snapshots[-1].read_text(encoding="utf-8"))
    selected = payload.get("selected_contract") or payload.get("selected_contract_symbol")
    return str(selected) if selected else None


def _read_symbol_master_cache(path: Path) -> tuple[Any, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ()
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return ()
    rows = payload.get("rows")
    downloaded_at_raw = payload.get("downloaded_at")
    if not isinstance(rows, list) or not downloaded_at_raw:
        return ()
    try:
        downloaded_at = datetime.fromisoformat(str(downloaded_at_raw))
    except ValueError:
        return ()
    try:
        return normalize_symbol_master_rows(
            rows,
            exchange=str(payload.get("exchange") or "NSEFO"),
            source_version=str(payload.get("source_version") or "LOCAL_SYMBOL_MASTER_CACHE"),
            downloaded_at=downloaded_at,
        )
    except Exception:
        return ()


def _write_symbol_master_cache(
    path: Path,
    *,
    exchange: str,
    source_version: str,
    downloaded_at: datetime,
    records: tuple[Any, ...],
) -> None:
    payload = {
        "exchange": exchange,
        "source_version": source_version,
        "downloaded_at": downloaded_at.isoformat(),
        "record_count": len(records),
        "rows": [dict(getattr(record, "source_row", {})) for record in records],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _account_risk_matrix(
    registry: EnabledStrategyRegistry,
    continuity: Mapping[str, Any],
    *,
    late_start: bool,
) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for instance in registry.enabled_instances:
        continuity_payload = continuity.get(instance.strategy_instance_id, {}) if isinstance(continuity.get(instance.strategy_instance_id), Mapping) else {}
        status = continuity_payload.get("status")
        selected_contract = continuity_payload.get("selected_contract")
        entry = continuity_payload.get("entry")
        if late_start:
            decision = "DEFERRED_INTENT"
        elif status in {"IDENTIFIABLE", "PREMARKET_SELECTED_CONTRACT_PINNED"}:
            decision = "ACCEPTED_INTENT"
        elif selected_contract and entry and not str(status or "").startswith("BLOCKED"):
            decision = "ACCEPTED_INTENT"
        else:
            decision = "BLOCKED_ACCOUNT"
        rows[instance.strategy_instance_id] = {
            "decision": decision,
            "max_margin_usage_pct": instance.risk_allocation.get("max_margin_usage_pct"),
            "max_positions": instance.risk_allocation.get("max_positions"),
            "aggregate_option_selling_exposure": registry.risk.get("aggregate_option_selling_exposure"),
        }
    return rows


def _supervisor_gaps(projection: Mapping[str, Any], *, late_start: bool) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for strategy in projection.get("strategies", []):
        plan = strategy.get("plan", {})
        if plan.get("block_reason"):
            gaps.append(
                {
                    "gap_id": f"SUPERVISOR-{strategy['identity']['instance']}",
                    "classification": str(plan["block_reason"]),
                    "description": f"{strategy['identity']['instance']} remains blocked in the current supervisor session.",
                }
            )
    if late_start:
        gaps.append(
            {
                "gap_id": "SUPERVISOR-LATE-START",
                "classification": "LATE_START_NO_NEW_ENTRY",
                "description": "Current session started after authoritative fresh-entry windows.",
            }
        )
    return gaps


def _collect_projection_labels(projection: Mapping[str, Any]) -> set[str]:
    labels: set[str] = {"LIVE_SUPERVISOR_OBSERVED", "NO_EXTERNAL_ORDER_AUTHORITY"}
    for strategy in projection.get("strategies", []):
        state = strategy.get("state", {})
        plan = strategy.get("plan", {})
        for value in (state.get("evidence_quality"), plan.get("evidence_quality"), strategy.get("execution", {}).get("simulated_or_observed")):
            if value:
                labels.add(str(value))
    if "LIVE_FYERS_READ_ONLY_CAPTURE" in labels:
        labels.add("FYERS_METADATA_CAPTURED")
    if any("HISTORICAL" in str(label) for label in tuple(labels)):
        labels.add("HISTORICALLY_RECONSTRUCTED")
    if "MISSED_BEFORE_SUPERVISOR_START" in labels or "DETERMINISTIC_TIMING_SUPPLEMENT" in labels:
        labels.add("PARTIAL_CAPTURE")
    elif "LIVE_FYERS_READ_ONLY_CAPTURE" in labels:
        labels.add("COMPLETE_CAPTURE")
    return labels


def _projection_meets_required_labels(projection: Mapping[str, Any]) -> bool:
    labels = _collect_projection_labels(projection)
    required_all = {
        "FIXTURE_BACKED",
        "FYERS_METADATA_CAPTURED",
        "LIVE_FYERS_READ_ONLY_CAPTURE",
        "LIVE_SUPERVISOR_OBSERVED",
        "DETERMINISTIC_TIMING_SUPPLEMENT",
        "MISSED_BEFORE_SUPERVISOR_START",
        "INTERNAL_PAPER_SIMULATED",
        "NO_EXTERNAL_ORDER_AUTHORITY",
    }
    if not required_all.issubset(labels):
        return False
    return bool({"PARTIAL_CAPTURE", "COMPLETE_CAPTURE"} & labels)


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    index = ratio * (len(values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    fraction = index - lower
    return float(values[lower] + ((values[upper] - values[lower]) * fraction))


def _continuity_map_from_projection(projection: Mapping[str, Any]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for strategy in projection.get("strategies", []):
        rows[strategy["identity"]["strategy_instance_id"]] = {
            "status": strategy["plan"].get("block_reason") or "IDENTIFIABLE",
            "selected_contract": strategy["plan"].get("selected_contract"),
            "evidence": strategy["state"].get("evidence_quality"),
        }
    return rows


def _load_projection_version(db_path: Path, strategy_instance_id: str) -> int | None:
    if not db_path.exists():
        return 0
    db = PersistenceDatabase(db_path, read_only=True)
    try:
        with db.connect() as connection:
            row = connection.execute(
                "SELECT version FROM current_runtime_stream_projection WHERE projection_id = ?",
                (f"unified-supervisor:{strategy_instance_id}",),
            ).fetchone()
            return int(row["version"]) if row is not None else 0
    except Exception:
        return 0


def _action_ready_continuity(payload: Mapping[str, Any]) -> dict[str, Any]:
    continuity = dict(payload)
    if "plan_payload" not in continuity and isinstance(payload.get("live_plan"), Mapping):
        continuity["plan_payload"] = dict(payload["live_plan"])
    if "quote" not in continuity and isinstance(payload.get("selected_contract_quote"), Mapping):
        continuity["quote"] = dict(payload["selected_contract_quote"])
    return continuity


def _account_snapshot_from_dict(payload: Mapping[str, Any]) -> SimulatedPaperAccountSnapshot:
    return SimulatedPaperAccountSnapshot(
        broker_account_id=str(payload.get("broker_account_id") or ""),
        opening_paper_cash=Decimal(str(payload.get("opening_paper_cash") or "0")),
        reserved_margin=Decimal(str(payload.get("reserved_margin") or "0")),
        released_margin=Decimal(str(payload.get("released_margin") or "0")),
        available_paper_margin=Decimal(str(payload.get("available_paper_margin") or "0")),
        simulated_charges=Decimal(str(payload.get("simulated_charges") or "0")),
        active_order_reservation=Decimal(str(payload.get("active_order_reservation") or "0")),
        margin_per_quantity=Decimal(str(payload.get("margin_per_quantity") or "0")),
        account_enabled=bool(payload.get("account_enabled", True)),
        account_blocked=bool(payload.get("account_blocked", False)),
        active_order_count=int(payload.get("active_order_count") or 0),
        max_active_order_count=int(payload.get("max_active_order_count") or 10),
    )


def _optional_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _optional_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _quote_allows_limit_sell_fill(quote: Mapping[str, Any], limit_price: Decimal) -> bool:
    for key in ("bid", "ltp", "ask"):
        value = quote.get(key)
        if value in (None, ""):
            continue
        try:
            if Decimal(str(value)) >= limit_price:
                return True
        except Exception:
            continue
    return False


def _client_order_from_state(*, intent: Any, state: Mapping[str, Any]) -> ClientOrder:
    coordinator_identity = AccountCoordinator.build_identity(
        broker_account_id=intent.broker_account_id,
        trading_session_id=intent.trading_session_id,
    )
    idempotency_payload = {
        "account_coordinator_id": coordinator_identity.account_coordinator_id,
        "execution_intent_id": intent.execution_intent_id,
        "broker_account_id": intent.broker_account_id,
        "purpose": intent.action.purpose.value,
        "protection_generation": intent.action.protection_generation,
        "intent_hash": intent.intent_hash,
    }
    return ClientOrder(
        client_order_id=str(state.get("client_order_id") or ""),
        execution_intent_id=intent.execution_intent_id,
        account_coordinator_id=coordinator_identity.account_coordinator_id,
        broker_account_id=intent.broker_account_id,
        strategy_instance_id=intent.strategy_instance_id,
        trading_session_id=intent.trading_session_id,
        position_cycle_id=intent.position_cycle_id,
        idempotency_key="client-order:" + canonical_hash(idempotency_payload),
        normalized_contract=intent.instrument.contract,
        side=intent.action.side,
        quantity=intent.action.requested_quantity,
        order_purpose=intent.action.purpose.value,
        order_type=intent.action.order_type,
        limit_price=intent.action.limit_price,
        trigger_price=intent.action.trigger_price,
        time_in_force=intent.action.time_in_force,
        authorized_time=intent.action.authorized_not_before,
        protection_generation=intent.action.protection_generation,
        source_intent_hash=intent.intent_hash,
    )


def _build_live_fill_scenario(
    *,
    intent: Any,
    continuity: Mapping[str, Any],
    now: datetime,
) -> DeterministicExecutionScenarioDefinition:
    quote = continuity.get("quote") or {}
    limit_price = intent.action.limit_price or Decimal(str(continuity.get("entry") or "0.00"))
    return DeterministicExecutionScenarioDefinition(
        scenario_id=f"live-supervisor:{intent.strategy_instance_id}:{now.isoformat()}",
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        market_evidence=DeterministicMarketEvidence(
            bid=Decimal(str(quote.get("bid") or limit_price)),
            ask=Decimal(str(quote.get("ask") or limit_price)),
            ltp=Decimal(str(quote.get("ltp") or limit_price)),
            high=Decimal(str(quote.get("ltp") or limit_price)),
            low=Decimal(str(quote.get("ltp") or limit_price)),
            source_timestamp=now,
            snapshot_hash=canonical_hash({"contract": intent.instrument.contract, "quote": dict(quote), "at": now.isoformat()}),
        ),
        event_time=now,
        fill_quantity=intent.action.requested_quantity,
        fill_price=limit_price,
        rejection_reason=None,
        cancel_reason=None,
    )


def _blocked_paper_state(
    *,
    current_state: Mapping[str, Any],
    continuity: Mapping[str, Any],
    reason: str,
    now: datetime,
) -> dict[str, Any]:
    return {
        **dict(current_state),
        "selected_contract": continuity.get("selected_contract"),
        "order_state": "NO_ORDER",
        "fill_state": "NO_FILL",
        "final_state": "NO_ORDER",
        "failure": reason,
        "latest_event": reason,
        "decision": "NO_ORDER",
        "mark": str(((continuity.get("quote") or {}).get("ltp") or "")),
        "updated_at": now.isoformat(),
    }


def _refresh_open_position_state(
    *,
    current_state: Mapping[str, Any],
    continuity: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    state = dict(current_state)
    quote = continuity.get("quote") or {}
    if quote.get("ltp") not in (None, ""):
        state["mark"] = str(quote.get("ltp"))
    state["updated_at"] = now.isoformat()
    state.setdefault("position_open", True)
    state.setdefault("order_state", "FILLED_INTERNAL")
    state.setdefault("fill_state", "FILLED_INTERNAL")
    state.setdefault("final_state", "FILLED_INTERNAL")
    state.setdefault("latest_event", "POSITION_MONITORING")
    return state


def _outcome_from_state(
    *,
    instance: EnabledStrategyInstance,
    state: Mapping[str, Any],
    decision: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "execution_intent_id": state.get("execution_intent_id"),
        "strategy_instance_id": instance.strategy_instance_id,
        "broker_account_id": instance.account_reference,
        "instrument": state.get("selected_contract") or instance.symbol,
        "queue_position": 1,
        "decision": decision,
        "required_margin": state.get("required_margin"),
        "available_margin": state.get("available_margin"),
        "effective_available_margin": state.get("effective_available_margin"),
        "shortfall": state.get("shortfall"),
        "reservation_created": decision == "ORDER_ACCEPTED_PENDING_FILL",
        "reservation_released": decision == "PROCESSED_INTERNAL_PAPER",
        "reservation_reconciled": decision == "PROCESSED_INTERNAL_PAPER",
        "client_order_id": state.get("client_order_id"),
        "final_state": state.get("final_state"),
        "result_hash": canonical_hash({"strategy_instance_id": instance.strategy_instance_id, "state": dict(state), "decision": decision}),
        "reason": state.get("failure"),
    }
    if extra:
        payload.update(dict(extra))
    return payload


def _live_unrealized_pnl(
    *,
    entry_price: Any,
    mark_price: Any,
    quantity: int,
    side: str,
) -> str:
    if quantity <= 0 or entry_price in (None, "") or mark_price in (None, ""):
        return "0.00"
    entry = Decimal(str(entry_price))
    mark = Decimal(str(mark_price))
    diff = (entry - mark) if side.upper() == "SELL" else (mark - entry)
    return str(diff * Decimal(quantity))


def _age_from_iso_timestamp(timestamp: Any, *, now: datetime) -> str:
    if not timestamp:
        return "00:00:00"
    try:
        observed = datetime.fromisoformat(str(timestamp))
    except ValueError:
        return "00:00:00"
    seconds = max(0, int((now - observed).total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
