from __future__ import annotations

import json
import time
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import yaml

from tfis.broker.authentication import BrokerAuthenticationResult, BrokerSessionStatus
from tfis.broker.authentication.fyers import FyersAuthenticationAdapter
from tfis.fyers_read_only import FyersReadOnlyAdapter, FyersReadOnlyStatus, classify_monthly_expiries
from tfis.persistence import (
    PersistenceDatabase,
    UnitOfWork,
    apply_migrations,
    assess_recovery,
    canonical_hash,
    run_integrity_scan,
)
from tfis.read_models.operations import OperationalReadModel, build_unified_dashboard_projection
from tfis.runtime import ProcessLockError, ProcessLockHandle, acquire_process_lock
from tfis.runtime.process_lock import _process_exists, _process_matches_payload, _read_lock_payload
from tfis.runtime.coordination import RuntimeSubscriptionIndex

from .registry import EnabledStrategyInstance, EnabledStrategyRegistry, load_enabled_strategy_registry


IST = ZoneInfo("Asia/Calcutta")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
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
        self._timeline: list[dict[str, Any]] = []
        self._late_start_mode = False
        self._latest_auth: BrokerAuthenticationResult | None = None
        self._latest_auth_checked_at: datetime | None = None
        self._last_projection_hash = ""
        self._cached_nsefo_records: tuple[Any, ...] = ()
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

    def run(self) -> ContinuousSupervisorRunResult:
        self._acquire_process_lock()
        self.config.report_dir.mkdir(parents=True, exist_ok=True)
        self.config.state_root.mkdir(parents=True, exist_ok=True)
        self.config.dashboard_output_root.mkdir(parents=True, exist_ok=True)
        self._restore_checkpoint_if_available()
        final_state = "CREATED"
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
                self.sleep_fn(max(1.0, self.config.poll_seconds))
            final_now = self.now_provider()
            if final_state not in {"STOPPED", "BLOCKED"}:
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
        self._write_heartbeat(state=final_state, now=now)
        self._write_reports(now, final_state, stage_metrics=stage_metrics)
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
        if self._late_start_mode and instance.strategy_instance_id != "S22_RELIANCE_INTERNAL_PAPER_A":
            return {
                "status": "CURRENT_SESSION_SELECTION_NOT_OBSERVED_BY_SUPERVISOR",
                "selected_contract": None,
                "evidence": "MISSED_BEFORE_SUPERVISOR_START",
            }

        selected_contract = str(instance.deterministic_projection.get("selected_contract") or "")
        if not selected_contract:
            return {
                "status": "SELECTION_MISSING",
                "selected_contract": None,
                "evidence": "BLOCKED_CONFIGURATION",
            }

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
        return {
            "status": "PREMARKET_SELECTED_CONTRACT_PINNED" if not self._late_start_mode else "IDENTIFIABLE",
            "selected_contract": selected_contract,
            "evidence": "FIXTURE_BACKED" if instance.evidence_quality == "FIXTURE_BACKED" else instance.evidence_quality,
            "selected_contract_quote": quote_result.to_dict(),
        }

    def _build_projection(self, now: datetime, *, live_context: Mapping[str, Any], final_state: str) -> dict[str, Any]:
        instance_results = {
            item.strategy_instance_id: _live_instance_result(
                item,
                now=now,
                session_id=self.session_id,
                continuity=live_context["continuity"].get(item.strategy_instance_id) or {},
                timing=live_context["timing"]["instances"].get(item.strategy_instance_id) or {},
                late_start=self._late_start_mode,
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
            "state": final_state,
            "late_start_mode": self._late_start_mode,
            "iteration": self.iterations,
            "projection_hash": projection["projection_hash"],
            "subscription_owner": self.subscription_owner.to_dict(),
            "continuity": live_context.get("continuity", {}),
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
                "required_labels": [
                    "FIXTURE_BACKED",
                    "FYERS_METADATA_CAPTURED",
                    "LIVE_FYERS_READ_ONLY_CAPTURE",
                    "LIVE_SUPERVISOR_OBSERVED",
                    "DETERMINISTIC_TIMING_SUPPLEMENT",
                    "MISSED_BEFORE_SUPERVISOR_START",
                    "INTERNAL_PAPER_SIMULATED",
                    "PARTIAL_CAPTURE",
                    "COMPLETE_CAPTURE",
                    "NO_EXTERNAL_ORDER_AUTHORITY",
                ],
                "projection_labels": sorted(_collect_projection_labels(self._projection or {})),
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
                "schema_version": "tfis.live_supervisor.performance_metrics.v1",
                "iterations": self.iterations,
                "poll_seconds": self.config.poll_seconds,
                "projection_hash": self._last_projection_hash,
                "event_count": len(self._timeline),
                "production_scale_claimed": False,
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
        if not payload:
            return
        if payload.get("session_date") != self.session_date.isoformat():
            return
        self._late_start_mode = bool(payload.get("late_start_mode"))
        self.subscription_owner = SubscriptionOwner.from_dict(payload.get("subscription_owner") or {})

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
        current = now.timetz().replace(tzinfo=None)
        return current > MARKET_OPEN

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
        auth_result = self.auth_factory(self.config.repo_root).authenticate(allow_refresh=False, validate_session=True)
        self._latest_auth_checked_at = now
        self._record_stage(
            stage_metrics,
            "broker_authentication",
            "EXECUTED",
            started_at=started_at,
            ended_at=self.now_provider(),
            details={"status": auth_result.status.value},
        )
        return auth_result

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

    def _append_cycle_history(self, *, now: datetime, final_state: str, stage_metrics: list[StageMetric]) -> None:
        total_metric = next((item for item in stage_metrics if item.stage == "cycle_total"), None)
        if total_metric is None:
            total_ms = 0.0
        else:
            total_ms = float((total_metric.details or {}).get("cycle_duration_ms", total_metric.duration_ms))
        overrun_ms = max(0.0, total_ms - (self.config.poll_seconds * 1000.0))
        previous_overruns = self._cycle_metrics_history[-1]["consecutive_overruns"] if self._cycle_metrics_history else 0
        consecutive_overruns = previous_overruns + 1 if overrun_ms > 0 else 0
        sample = {
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
    )
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
    late_start: bool,
) -> dict[str, Any]:
    selected_contract = continuity.get("selected_contract")
    selected_contract_text = str(selected_contract) if selected_contract else None
    entry = str(instance.deterministic_projection.get("entry") or "")
    target = str(instance.deterministic_projection.get("target") or "")
    sl = str(instance.deterministic_projection.get("original_sl") or "")
    plan_status = "PREPARED" if selected_contract_text else "BLOCKED"
    blocked_reason = None if selected_contract_text else continuity.get("status", "SELECTED_CONTRACT_MISSING")
    runtime_stage = "LATE_START_NO_NEW_ENTRY" if late_start else _instance_runtime_stage(timing)
    evidence_quality = str(continuity.get("evidence") or instance.evidence_quality)
    alert_items = list(_instance_alerts(instance, continuity, late_start=late_start))
    quantity = int(instance.configured_quantity["lots"]) * int(instance.configured_quantity["lot_size"])
    risk_result = "DEFERRED" if late_start else "ACCEPTED"
    order_state = "NO_ORDER" if late_start else "READY_INTERNAL"
    fill_state = "NO_FILL"
    return {
        "trading_session_id": session_id,
        "runtime_stage": runtime_stage,
        "health": "DEGRADED_EVIDENCE" if blocked_reason else "HEALTHY",
        "last_update": now.isoformat(),
        "plan": {
            "market_references": dict(instance.deterministic_projection.get("market_references") or {}),
            "expiry_candidates": list(instance.deterministic_projection.get("expiry_candidates") or []),
            "selected_contract": selected_contract_text,
            "premium": entry,
            "oi": "LIVE_READ_REQUIRED" if evidence_quality.startswith("LIVE") else "SOURCE_PROJECTION",
            "base_entry": entry,
            "target": target,
            "original_sl": sl,
            "orpt": instance.deterministic_projection.get("orpt") or "09:24:59.400000",
            "rc": instance.deterministic_projection.get("rc") or "09:29:59.400000",
            "plan_status": plan_status,
            "block_reason": blocked_reason,
            "monthly_status": instance.deterministic_projection.get("monthly_status"),
            "branch": instance.deterministic_projection.get("branch"),
            "plan_hash": canonical_hash(
                {
                    "strategy_instance_id": instance.strategy_instance_id,
                    "selected_contract": selected_contract_text,
                    "monthly_status": instance.deterministic_projection.get("monthly_status"),
                }
            ),
            "evidence_quality": evidence_quality,
            "source_timestamp": now.isoformat(),
            "receipt_timestamp": now.isoformat(),
        },
        "execution": {
            "selected_contract": selected_contract_text,
            "opening_context": "MISSED_BEFORE_SUPERVISOR_START" if late_start else instance.deterministic_projection.get("opening_context"),
            "orpt_state": timing.get("orpt"),
            "rc_state": timing.get("rc"),
            "effective_entry": entry,
            "execution_intent": "NOT_CREATED_LATE_START" if late_start else "PENDING_VALIDATION",
            "risk_result": risk_result,
            "order_state": order_state,
            "fill_state": fill_state,
            "order_purpose": "ENTRY",
            "filled_quantity": 0,
            "protection_generation": 0,
            "order_age": "00:00:00",
            "latest_event": timing.get("market_open"),
            "failure": blocked_reason,
            "simulated_or_observed": "INTERNAL_PAPER_SIMULATED",
        },
        "position": {
            "position_cycle": f"pc:{canonical_hash(instance.strategy_instance_id)[:16]}",
            "selected_contract": selected_contract_text,
            "quantity": quantity,
            "average_entry": entry,
            "remaining_quantity": 0,
            "mark": "",
            "target": target,
            "active_protection": sl,
            "protection_status": "NO_POSITION",
            "fresh_or_carried": "CARRIED" if bool(instance.deterministic_projection.get("scenario_flags", {}).get("carried_position_candidate")) else "FRESH",
            "carried_state": "OBSERVATION_ONLY" if late_start else "NOT_CARRIED",
            "exit_reason": "OPEN" if not late_start else "NO_NEW_ENTRY",
            "exit_deadline": EOD_DECISION.isoformat(),
            "health": "NO_POSITION",
        },
        "accounting": {
            "selected_contract": selected_contract_text,
            "realized_pnl": "0.00" if late_start else str(instance.deterministic_projection.get("realized_pnl") or "0.00"),
            "unrealized_pnl": "0.00" if late_start else str(instance.deterministic_projection.get("unrealized_pnl") or "0.00"),
            "charges_quality": "PROVISIONAL_INTERNAL_PAPER",
            "trade_classification": "NO_TRADE_LATE_START" if late_start else str(instance.deterministic_projection.get("trade_classification") or "OPEN"),
            "accounting_quality": "INTERNAL_PAPER_SIMULATED",
        },
        "operations": {
            "alerts": alert_items,
            "reconciliation": "READ_ONLY_RECOVERY_PENDING" if late_start else "READY",
            "checkpoint": f"{session_id}:{instance.strategy_instance_id}:iteration",
            "broker_data_health": continuity.get("status", "UNKNOWN"),
            "authority_mode": instance.authority_mode,
            "evidence_label": evidence_quality,
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
    if late_start:
        alerts.append(
            {
                "severity": "WARNING",
                "code": "LATE_START_NO_NEW_ENTRY",
                "message": f"{instance.strategy_instance_id} started after authoritative timing windows; no retroactive entry allowed.",
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
        alerts.append(
            {
                "severity": "WARNING",
                "code": "LATE_START_NO_NEW_ENTRY",
                "message": "Supervisor is preserving observation/lifecycle mode and blocking retroactive fresh entry.",
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
            "orpt": _classify_window(now, time(9, 24, 59, 400000), late_start=late_start),
            "rc": _classify_window(now, time(9, 29, 59, 400000), late_start=late_start),
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
    return {
        "NIFTY": str(instruments["NIFTY"]["spot_symbol"]),
        "BANKNIFTY": str(instruments["BANKNIFTY"]["spot_symbol"]),
        "RELIANCE": "NSE:RELIANCE-EQ",
    }


def _resolve_underlying_symbol(symbol: str, underlying_symbols: Mapping[str, str]) -> str:
    if symbol == "RELIANCE":
        return "NSE:RELIANCE-EQ"
    return str(underlying_symbols[symbol])


def _latest_reliance_snapshot_contract(root: Path) -> str | None:
    base = root / "data" / "strategies" / "S22" / "fyers_read_only_snapshots" / date.today().isoformat()
    snapshots = sorted(base.glob("s22-reliance-fyers-*/snapshot.json"))
    if not snapshots:
        return None
    payload = json.loads(snapshots[-1].read_text(encoding="utf-8"))
    selected = payload.get("selected_contract") or payload.get("selected_contract_symbol")
    return str(selected) if selected else None


def _account_risk_matrix(
    registry: EnabledStrategyRegistry,
    continuity: Mapping[str, Any],
    *,
    late_start: bool,
) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for instance in registry.enabled_instances:
        status = continuity.get(instance.strategy_instance_id, {}).get("status")
        if late_start:
            decision = "DEFERRED_INTENT"
        elif status in {"IDENTIFIABLE", "PREMARKET_SELECTED_CONTRACT_PINNED"}:
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
    labels: set[str] = {"NO_EXTERNAL_ORDER_AUTHORITY"}
    for strategy in projection.get("strategies", []):
        state = strategy.get("state", {})
        plan = strategy.get("plan", {})
        for value in (state.get("evidence_quality"), plan.get("evidence_quality"), strategy.get("execution", {}).get("simulated_or_observed")):
            if value:
                labels.add(str(value))
    return labels


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
