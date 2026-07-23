from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.brokers import BrokerAdapter, BrokerAdapterError
from tfis.dashboard import TfisOperatorDashboardBuilder
from tfis.dashboard.config_loader import load_dashboard_strategy_configs
from tfis.paper import (
    DeterministicExpiryCalendar,
    PaperMorningSupervisedTaskSpec,
    PaperLifecycleSupervisor,
    PaperLifecycleSupervisorContext,
    PaperLifecycleSupervisorTargetDiscovery,
    PaperLifecycleSupervisorTargetSpec,
    PaperOrderState,
    PaperOrderStateStore,
    PaperOrderStatus,
    PaperPositionState,
    PaperPositionStateStore,
    PaperTradeLedgerStore,
    build_paper_expiry_governance,
    build_paper_morning_task_spec_from_target,
    build_paper_morning_runner_arguments,
    build_paper_position_manager,
    build_paper_live_state_store_from_yaml,
    connect_paper_broker_runtime,
    ensure_paper_broker_runtime_healthy,
    inspect_paper_live_state_store_from_yaml,
    fetch_selected_contract_market_events,
    append_selected_contract_market_events,
    handoff_fresh_entry_requirement,
    load_paper_lifecycle_supervisor_target_specs,
    load_paper_broker_runtime,
    promote_blocked_fresh_entries,
    paper_live_state_owner_id,
    PaperSelectedContractEventRequest,
    prepare_paper_broker_runtime_environment,
    validate_paper_lifecycle_runtime_guardrails,
)
from tfis.paper.models import SelectedContractBarEvent, SelectedContractQuoteEvent
from tfis.paper.operator_controls import load_paper_runtime_control_state_from_root
from tfis.runtime import ProcessLockError, ProcessLockHandle, acquire_process_lock


DEFAULT_TARGETS_CONFIG = REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml"
@dataclass(slots=True)
class _TargetRuntime:
    spec: PaperLifecycleSupervisorTargetSpec
    config: PaperLifecycleRuntimeConfig
    timezone_name: str
    timezone: ZoneInfo
    adapter: BrokerAdapter
    live_state_store: Any
    supervisor: PaperLifecycleSupervisor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one TFIS paper lifecycle supervisor process across every configured "
            "strategy artifact root, managing waiting orders and open positions from "
            "shared persisted paper artifacts."
        )
    )
    parser.add_argument("--tfis-root", default=str(REPO_ROOT))
    parser.add_argument("--targets-config", default=str(DEFAULT_TARGETS_CONFIG))
    parser.add_argument("--session-date", help="YYYY-MM-DD. Defaults to current date in target timezone.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-iterations", type=int, default=0, help="0 means run until --until.")
    parser.add_argument("--until", default="15:30", help="Local HH:MM cutoff for the supervisor loop.")
    parser.add_argument("--dashboard-output-root", default="tmp/operator_dashboard")
    parser.add_argument("--dashboard-config", default="config/operator_dashboard_strategies.yaml")
    parser.add_argument(
        "--disable-dashboard-rebuild",
        action="store_true",
        help="Do not rebuild the static operator dashboard after each supervisor loop.",
    )
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run one supervisor cycle and exit.")
    parser.add_argument(
        "--control-root",
        default="tmp/operator_controls",
        help="Directory containing global or per-strategy TFIS operator pause markers.",
    )
    parser.add_argument(
        "--no-targets-ok",
        action="store_true",
        help="Allow the supervisor to start cleanly even when no watchable targets exist yet.",
    )
    parser.add_argument(
        "--process-lock-root",
        default="tmp/process_locks/tfis_paper_lifecycle_supervisor",
        help="Directory for the shared TFIS paper lifecycle supervisor process lock.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    targets = load_paper_lifecycle_supervisor_target_specs(
        args.targets_config,
        repo_root=REPO_ROOT,
    )
    runtimes = _build_runtimes(targets)
    if not runtimes:
        print("No TFIS lifecycle supervisor targets were configured.", file=sys.stderr, flush=True)
        return 1

    until_time = _parse_hhmm(args.until)
    process_lock_handle: ProcessLockHandle | None = None
    held_watch_locks: dict[tuple[str, str], Any] = {}
    held_trade_ids: dict[tuple[str, str], str] = {}
    discovery = PaperLifecycleSupervisorTargetDiscovery(order_store=PaperOrderStateStore())
    last_control_signature: tuple[bool, tuple[str, ...]] | None = None

    try:
        process_lock_handle = acquire_process_lock(
            Path(args.process_lock_root) / "tfis_paper_lifecycle_supervisor.pid.json",
            label="tfis-paper-lifecycle-supervisor",
            metadata={
                "targets_config": str(Path(args.targets_config).resolve()),
                "dashboard_output_root": str((REPO_ROOT / args.dashboard_output_root).resolve()),
            },
            logger=lambda message: print(message, file=sys.stderr, flush=True),
        )
    except ProcessLockError as exc:
        print(f"INFO: {exc}", flush=True)
        return 0

    _print_start_banner(args=args, runtimes=runtimes)
    _prepare_runtime_environments(
        runtimes,
        tfis_root=args.tfis_root,
        skip_refresh=args.skip_refresh,
    )
    _connect_runtime_adapters(runtimes)

    iterations = 0
    try:
        while True:
            iterations += 1
            active_keys: set[tuple[str, str]] = set()
            any_targets = False
            now_by_strategy: dict[str, datetime] = {}
            control_state = load_paper_runtime_control_state_from_root(REPO_ROOT / args.control_root)
            control_signature = _control_signature(control_state)
            if control_signature != last_control_signature:
                _log_control_state_transition(control_state)
                last_control_signature = control_signature

            for runtime in runtimes:
                evaluated_at = datetime.now(runtime.timezone)
                now_by_strategy[runtime.spec.strategy_code] = evaluated_at
                if control_state.strategy_paused(runtime.spec.strategy_code):
                    continue
                effective_session_date = (
                    date.fromisoformat(args.session_date)
                    if args.session_date
                    else evaluated_at.date()
                )
                targets_for_runtime = discovery.discover_targets(
                    runtime.spec,
                    effective_session_date=effective_session_date,
                )
                if targets_for_runtime:
                    any_targets = True
                    _ensure_runtime_adapter_health(runtime=runtime, evaluated_at=evaluated_at)
                for target in targets_for_runtime:
                    key = (runtime.spec.strategy_code, str(target.directory))
                    active_keys.add(key)
                    if not _ensure_watch_lock(held_watch_locks, key=key, directory=target.directory):
                        continue
                    _process_target(
                        runtime=runtime,
                        target=target,
                        held_trade_ids=held_trade_ids,
                        lock_ttl_seconds=max(30, int(args.poll_seconds * 6)),
                        watch_cutoff_time=until_time,
                        dashboard_rebuild_disabled=args.disable_dashboard_rebuild,
                        evaluated_at=evaluated_at,
                        tfis_root=Path(args.tfis_root),
                    )

            _release_stale_handles(
                held_watch_locks=held_watch_locks,
                held_trade_ids=held_trade_ids,
                active_keys=active_keys,
                runtimes=runtimes,
            )

            if any_targets and not args.disable_dashboard_rebuild:
                _rebuild_dashboard(
                    output_root=Path(args.dashboard_output_root),
                    dashboard_config_path=Path(args.dashboard_config),
                )

            if args.once:
                return 0
            if args.max_iterations and iterations >= args.max_iterations:
                return 0
            if _all_targets_past_cutoff(now_by_strategy=now_by_strategy, until_time=until_time):
                return 0
            if (not any_targets) and (not args.no_targets_ok) and (not control_state.global_pause_active):
                print(
                    f"{datetime.now().isoformat()} WARNING no_watchable_targets_found; "
                    "supervisor remains alive",
                    flush=True,
                )
            time_module.sleep(max(1.0, args.poll_seconds))
    except (BrokerAdapterError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        for handle in held_watch_locks.values():
            _release_watch_file_lock(handle)
        held_watch_locks.clear()
        for runtime in runtimes:
            for trade_id in tuple(
                trade_id
                for (strategy_code, _directory), trade_id in held_trade_ids.items()
                if strategy_code == runtime.spec.strategy_code
            ):
                runtime.live_state_store.release_trade_lock(
                    trade_id=trade_id,
                    owner_id=_owner_id_for_spec(runtime.spec),
                )
            try:
                runtime.adapter.disconnect()
            except Exception:
                pass
        if process_lock_handle is not None:
            process_lock_handle.release()


def _build_runtimes(
    targets: tuple[PaperLifecycleSupervisorTargetSpec, ...],
) -> tuple[_TargetRuntime, ...]:
    runtimes: list[_TargetRuntime] = []
    for spec in targets:
        broker_runtime = load_paper_broker_runtime(spec.config_path)
        config = broker_runtime.config
        guardrail_failures = validate_paper_lifecycle_runtime_guardrails(config)
        if guardrail_failures:
            raise RuntimeError(
                f"{spec.strategy_code} runtime guardrail check failed: "
                + "; ".join(guardrail_failures)
            )
        timezone_name = broker_runtime.timezone_name
        timezone = broker_runtime.timezone
        live_state_diagnostics = inspect_paper_live_state_store_from_yaml(spec.config_path)
        if live_state_diagnostics.status != "PASS":
            raise RuntimeError(
                f"{spec.strategy_code} live-state bootstrap failed: {live_state_diagnostics.message}"
            )
        print(
            f"INFO live_state_ready strategy={spec.strategy_code} "
            f"provider={live_state_diagnostics.provider} "
            f"backend={live_state_diagnostics.backend}",
            flush=True,
        )
        live_state_store = build_paper_live_state_store_from_yaml(
            spec.config_path,
            strict=True,
        )
        runtimes.append(
            _TargetRuntime(
                spec=spec,
                config=config,
                timezone_name=timezone_name,
                timezone=timezone,
                adapter=broker_runtime.adapter,
                live_state_store=live_state_store,
                supervisor=PaperLifecycleSupervisor(
                    order_store=PaperOrderStateStore(),
                    position_manager=build_paper_position_manager(
                        strategy_code=spec.strategy_code,
                        live_state_store=live_state_store,
                        slippage_exit_points=config.costs.slippage_exit_points or 0.0,
                    ),
                ),
            )
        )
    return tuple(runtimes)


def _control_signature(state) -> tuple[bool, tuple[str, ...]]:
    return state.global_pause_active, tuple(sorted(state.paused_strategies))


def _log_control_state_transition(state) -> None:
    if state.global_pause_active:
        print(
            "INFO operator_pause_active scope=global strategy=ALL "
            f"control_root={state.control_root}",
            flush=True,
        )
        return
    if state.paused_strategies:
        strategies = ",".join(sorted(state.paused_strategies))
        print(
            "INFO operator_pause_active scope=strategy "
            f"strategies={strategies} control_root={state.control_root}",
            flush=True,
        )
        return
    print("INFO operator_pause_cleared", flush=True)


def _append_supervisor_audit_event(
    directory: Path,
    *,
    event_timestamp: datetime,
    strategy_code: str,
    trade_id: str,
    event_type: str,
    status: str,
    reason_code: str,
    message: str,
    selected_contract_symbol: str | None = None,
    provider: str | None = None,
) -> Path:
    path = directory / "paper_lifecycle_supervisor_events.jsonl"
    row = {
        "artifact_version": 1,
        "event_timestamp": event_timestamp.isoformat(),
        "strategy_code": strategy_code,
        "trade_id": trade_id,
        "event_type": event_type,
        "status": status,
        "reason_code": reason_code,
        "message": message,
        "selected_contract_symbol": selected_contract_symbol,
        "provider": provider,
        "state_directory": str(directory),
        "supervisor_pid": os.getpid(),
    }
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rendered = existing + json.dumps(row, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.tmp"
    try:
        temp_path.write_text(rendered, encoding="utf-8", newline="\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return path


def _prepare_runtime_environments(
    runtimes: tuple[_TargetRuntime, ...],
    *,
    tfis_root: str,
    skip_refresh: bool,
) -> None:
    prepared_providers: set[str] = set()
    for runtime in runtimes:
        provider = runtime.config.broker.provider.strip().lower()
        if provider in prepared_providers:
            continue
        prepare_paper_broker_runtime_environment(
            runtime.config,
            tfis_root=tfis_root,
            skip_refresh=skip_refresh,
        )
        prepared_providers.add(provider)


def _connect_runtime_adapters(
    runtimes: tuple[_TargetRuntime, ...],
) -> None:
    for runtime in runtimes:
        health = connect_paper_broker_runtime(
            strategy_code=runtime.spec.strategy_code,
            provider=runtime.config.broker.provider,
            adapter=runtime.adapter,
        )
        print(
            f"INFO broker_runtime_ready strategy={runtime.spec.strategy_code} "
            f"provider={runtime.config.broker.provider} "
            f"state={health.connection_state.value}",
            flush=True,
        )


def _ensure_runtime_adapter_health(
    *,
    runtime: _TargetRuntime,
    evaluated_at: datetime,
):
    try:
        initial_health = runtime.adapter.health()
    except Exception as exc:
        raise RuntimeError(
            f"{runtime.spec.strategy_code} broker health check failed for "
            f"{runtime.config.broker.provider}: {type(exc).__name__}: {exc}"
        ) from exc
    if _broker_health_is_healthy(initial_health):
        return initial_health
    print(
        f"{evaluated_at.isoformat()} WARNING broker_runtime_degraded "
        f"strategy={runtime.spec.strategy_code} "
        f"provider={runtime.config.broker.provider} "
        f"{_describe_broker_health(initial_health)}",
        flush=True,
    )
    recovered_health = ensure_paper_broker_runtime_healthy(
        strategy_code=runtime.spec.strategy_code,
        provider=runtime.config.broker.provider,
        adapter=runtime.adapter,
        initial_health=initial_health,
    )
    print(
        f"{evaluated_at.isoformat()} INFO broker_runtime_recovered "
        f"strategy={runtime.spec.strategy_code} "
        f"provider={runtime.config.broker.provider} "
        f"{_describe_broker_health(recovered_health)}",
        flush=True,
    )
    return recovered_health


def _process_target(
    *,
    runtime: _TargetRuntime,
    target,
    held_trade_ids: dict[tuple[str, str], str],
    lock_ttl_seconds: int,
    watch_cutoff_time: time,
    dashboard_rebuild_disabled: bool,
    evaluated_at: datetime,
    tfis_root: Path,
) -> None:
    key = (runtime.spec.strategy_code, str(target.directory))
    context = _build_lifecycle_context(target, session_date=target.session_date)
    if context is None:
        return

    owner_id = _owner_id_for_spec(runtime.spec)
    previous_locked_trade_id = held_trade_ids.get(key)
    if previous_locked_trade_id != context.trade_id:
        if previous_locked_trade_id is not None:
            runtime.live_state_store.release_trade_lock(
                trade_id=previous_locked_trade_id,
                owner_id=owner_id,
            )
        if not runtime.live_state_store.acquire_trade_lock(
            trade_id=context.trade_id,
            owner_id=owner_id,
            ttl_seconds=lock_ttl_seconds,
        ):
            _append_supervisor_audit_event(
                context.session_directory,
                event_timestamp=evaluated_at,
                strategy_code=runtime.spec.strategy_code,
                trade_id=context.trade_id,
                event_type="LOCK_BUSY",
                status="SKIPPED",
                reason_code="trade_lock_busy",
                message="Another TFIS supervisor owner currently holds the trade lock.",
                selected_contract_symbol=context.selected_contract_symbol,
                provider=runtime.config.broker.provider,
            )
            print(
                f"{evaluated_at.isoformat()} INFO lock_busy "
                f"strategy={runtime.spec.strategy_code} trade_id={context.trade_id} "
                f"directory={context.session_directory}",
                flush=True,
            )
            return
        held_trade_ids[key] = context.trade_id

    previous_session_result = runtime.supervisor.expire_waiting_order_from_previous_session(
        context,
        evaluated_at=evaluated_at,
    )
    if previous_session_result is not None:
        final_step = previous_session_result.final_step
        print(
            f"{evaluated_at.isoformat()} {runtime.spec.strategy_code} {final_step.status} "
            f"{final_step.reason_code} fill={final_step.fill_price}",
            flush=True,
        )
        _append_supervisor_audit_event(
            context.session_directory,
            event_timestamp=evaluated_at,
            strategy_code=runtime.spec.strategy_code,
            trade_id=context.trade_id,
            event_type="PREVIOUS_SESSION_ORDER_EXPIRED",
            status=final_step.status,
            reason_code=final_step.reason_code,
            message=getattr(final_step, "message", "") or "",
            selected_contract_symbol=context.selected_contract_symbol,
            provider=runtime.config.broker.provider,
        )
        runtime.live_state_store.release_trade_lock(
            trade_id=held_trade_ids.pop(key, context.trade_id),
            owner_id=owner_id,
        )
        return

    try:
        events = _fetch_selected_contract_events(
            adapter=runtime.adapter,
            selected_contract_symbol=context.selected_contract_symbol,
            session_date=context.session_date,
            evaluated_at=evaluated_at,
            state=context.position_state,
        )
    except BrokerAdapterError as exc:
        _record_market_data_unavailable(
            runtime=runtime,
            context=context,
            evaluated_at=evaluated_at,
            reason_code="selected_contract_event_fetch_failed",
            message=f"{type(exc).__name__}: {exc}",
        )
        return
    append_selected_contract_market_events(
        context.session_directory,
        events=events,
        observed_at=evaluated_at,
        process_pid=os.getpid(),
        trade_id=context.trade_id,
    )
    previous_trade_id = context.trade_id
    lifecycle_result = runtime.supervisor.supervise(
        context,
        market_events=events,
        evaluated_at=evaluated_at,
        watch_cutoff_time=watch_cutoff_time,
        expiry_governance=build_paper_expiry_governance(
            strategy_code=runtime.spec.strategy_code,
            calendar=DeterministicExpiryCalendar(),
        ),
        allow_reverse_on_stoploss=True,
        provenance_source_ids=("tfis_paper_lifecycle_supervisor", runtime.spec.strategy_code),
    )
    context = lifecycle_result.context
    if context.trade_id != previous_trade_id:
        runtime.live_state_store.release_trade_lock(
            trade_id=previous_trade_id,
            owner_id=owner_id,
        )
        runtime.live_state_store.acquire_trade_lock(
            trade_id=context.trade_id,
            owner_id=owner_id,
            ttl_seconds=lock_ttl_seconds,
        )
        held_trade_ids[key] = context.trade_id

    for step in lifecycle_result.steps:
        detail_name = (
            "fill"
            if step.fill_price is not None
            else "entry"
            if step.entry_price is not None
            else "exit"
        )
        detail_value = step.fill_price
        if detail_value is None:
            detail_value = step.entry_price
        if detail_value is None:
            detail_value = step.exit_price
        print(
            f"{evaluated_at.isoformat()} {runtime.spec.strategy_code} {step.status} "
            f"{step.reason_code} {detail_name}={detail_value} "
            f"directory={context.session_directory}",
            flush=True,
        )
        _append_supervisor_audit_event(
            context.session_directory,
            event_timestamp=evaluated_at,
            strategy_code=runtime.spec.strategy_code,
            trade_id=context.trade_id,
            event_type="LIFECYCLE_STEP",
            status=step.status,
            reason_code=step.reason_code,
            message=getattr(step, "message", "") or "",
            selected_contract_symbol=context.selected_contract_symbol,
            provider=runtime.config.broker.provider,
        )
    runtime.live_state_store.set_watch_heartbeat(
        session_date=context.session_date,
        trade_id=context.trade_id,
        payload={
            "trade_id": context.trade_id,
            "owner_id": owner_id,
            "timestamp": evaluated_at.isoformat(),
            "status": lifecycle_result.final_step.status,
            "selected_contract_symbol": context.selected_contract_symbol,
            "state_directory": str(context.session_directory),
            "strategy_code": runtime.spec.strategy_code,
            "supervisor_pid": os.getpid(),
        },
    )
    runtime.live_state_store.acquire_trade_lock(
        trade_id=context.trade_id,
        owner_id=owner_id,
        ttl_seconds=lock_ttl_seconds,
    )
    if lifecycle_result.terminal:
        _launch_fresh_decision_if_required(
            runtime=runtime,
            context=context,
            lifecycle_result=lifecycle_result,
            tfis_root=tfis_root,
            evaluated_at=evaluated_at,
        )
        runtime.live_state_store.release_trade_lock(
            trade_id=held_trade_ids.pop(key, context.trade_id),
            owner_id=owner_id,
        )


def _record_market_data_unavailable(
    *,
    runtime: _TargetRuntime,
    context: PaperLifecycleSupervisorContext,
    evaluated_at: datetime,
    reason_code: str,
    message: str,
) -> None:
    print(
        f"{evaluated_at.isoformat()} WARNING market_data_unavailable "
        f"strategy={runtime.spec.strategy_code} "
        f"provider={runtime.config.broker.provider} "
        f"trade_id={context.trade_id} "
        f"selected_contract_symbol={context.selected_contract_symbol} "
        f"reason={reason_code} message={message}",
        flush=True,
    )
    _append_supervisor_audit_event(
        context.session_directory,
        event_timestamp=evaluated_at,
        strategy_code=runtime.spec.strategy_code,
        trade_id=context.trade_id,
        event_type="MARKET_DATA_UNAVAILABLE",
        status="SKIPPED",
        reason_code=reason_code,
        message=message,
        selected_contract_symbol=context.selected_contract_symbol,
        provider=runtime.config.broker.provider,
    )
    runtime.live_state_store.set_watch_heartbeat(
        session_date=context.session_date,
        trade_id=context.trade_id,
        payload={
            "trade_id": context.trade_id,
            "owner_id": _owner_id_for_spec(runtime.spec),
            "timestamp": evaluated_at.isoformat(),
            "status": "MARKET_DATA_UNAVAILABLE",
            "reason_code": reason_code,
            "message": message,
            "selected_contract_symbol": context.selected_contract_symbol,
            "state_directory": str(context.session_directory),
            "strategy_code": runtime.spec.strategy_code,
            "provider": runtime.config.broker.provider,
            "supervisor_pid": os.getpid(),
        },
    )


def _build_lifecycle_context(
    target,
    *,
    session_date: date,
) -> PaperLifecycleSupervisorContext | None:
    directory = target.directory
    state_path = directory / "paper_position_state.json"
    order_path = directory / "paper_order_state.json"
    position_state: PaperPositionState | None = target.position_state
    order_state: PaperOrderState | None = target.order_state
    if target.mode == "state" and position_state is None and state_path.exists():
        try:
            position_state = PaperPositionStateStore().load_state(directory)
        except Exception:
            position_state = None
    if target.mode == "order" and order_state is None and order_path.exists():
        try:
            order_state = PaperOrderStateStore().load_state(directory)
        except Exception:
            order_state = None
    if position_state is None and order_state is None:
        return None
    trade_id = (
        PaperTradeLedgerStore.trade_id_for_state(position_state)
        if position_state is not None
        else _order_id_for_state(order_state)
    )
    selected_contract_symbol = (
        position_state.selected_contract_symbol
        if position_state is not None
        else order_state.selected_contract_symbol
    )
    return PaperLifecycleSupervisorContext(
        session_directory=directory,
        session_date=session_date,
        trade_id=trade_id,
        selected_contract_symbol=selected_contract_symbol,
        order_state=order_state,
        position_state=position_state,
    )


def _build_fresh_decision_task_spec(
    *,
    spec: PaperLifecycleSupervisorTargetSpec,
    tfis_root: Path,
    carry_forward_state_dir: Path | None,
) -> PaperMorningSupervisedTaskSpec | None:
    if not spec.executor:
        return None
    return build_paper_morning_task_spec_from_target(
        target=spec,
        repo_root=REPO_ROOT,
        tfis_root=tfis_root,
        carry_forward_state_dir=carry_forward_state_dir,
    )


def _launch_fresh_decision_if_required(
    *,
    runtime: _TargetRuntime,
    context: PaperLifecycleSupervisorContext,
    lifecycle_result,
    tfis_root: Path,
    evaluated_at: datetime,
) -> None:
    if lifecycle_result.final_step.status != "PAPER_POSITION_FRESH_ENTRY_REQUIRED":
        return
    task_spec = _build_fresh_decision_task_spec(
        spec=runtime.spec,
        tfis_root=tfis_root,
        carry_forward_state_dir=None,
    )

    def _spawn_runner() -> int | None:
        assert task_spec is not None
        args = build_paper_morning_runner_arguments(task_spec)
        process = subprocess.Popen(args, cwd=str(REPO_ROOT))
        return getattr(process, "pid", None)

    result = handoff_fresh_entry_requirement(
        strategy_code=runtime.spec.strategy_code,
        session_directory=context.session_directory,
        session_date=context.session_date,
        trade_id=context.trade_id,
        final_step_status=lifecycle_result.final_step.status,
        evaluated_at=evaluated_at,
        artifact_root=runtime.spec.artifact_root,
        session_id_prefix=runtime.spec.session_id_prefix,
        promotion_loader=lambda artifact_root, **kwargs: promote_blocked_fresh_entries(
            artifact_root,
            **kwargs,
        ),
        runner_name=task_spec.runner_script_path.name if task_spec is not None else None,
        spawn_runner=_spawn_runner if task_spec is not None else None,
    )
    if result.action == "not_required":
        return
    if result.action == "already_recorded":
        print(
            f"{evaluated_at.isoformat()} INFO fresh_decision_launch_already_recorded "
            f"strategy={runtime.spec.strategy_code} directory={context.session_directory}",
            flush=True,
        )
        return
    if result.action == "promoted_existing_blocked_decision":
        assert result.promotion_summary is not None
        print(
            f"{evaluated_at.isoformat()} INFO blocked_fresh_decision_promoted "
            f"strategy={runtime.spec.strategy_code} directory={context.session_directory} "
            f"promotion_session={result.promotion_summary.session_dir}",
            flush=True,
        )
        return
    if result.action == "launch_unavailable":
        print(
            f"{evaluated_at.isoformat()} WARNING fresh_decision_launch_unavailable "
            f"strategy={runtime.spec.strategy_code} directory={context.session_directory}",
            flush=True,
        )
        return
    assert result.action == "spawned_fresh_supervised_runner"
    assert task_spec is not None
    print(
        f"{evaluated_at.isoformat()} INFO fresh_decision_launched "
        f"strategy={runtime.spec.strategy_code} directory={context.session_directory} "
        f"runner={task_spec.runner_script_path.name}",
        flush=True,
    )


def _fetch_selected_contract_events(
    *,
    adapter: BrokerAdapter,
    selected_contract_symbol: str,
    session_date: date,
    evaluated_at: datetime,
    state: PaperPositionState | None,
) -> tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...]:
    request = PaperSelectedContractEventRequest(
        selected_contract_symbol=selected_contract_symbol,
        session_date=session_date,
        evaluated_at=evaluated_at,
        stoploss_reset_pending=bool(getattr(state, "stoploss_reset_pending", False)),
        stoploss_active=bool(getattr(state, "stoploss_active", True)),
        stoploss_reset_session_date=getattr(state, "stoploss_reset_session_date", None),
        entry_date=getattr(state, "entry_date", None),
        stoploss_reset_rc_time=getattr(state, "stoploss_reset_rc_time", None),
    )
    return fetch_selected_contract_market_events(
        adapter,
        request,
        on_bar_fetch_error=lambda exc: print(
            f"{evaluated_at.isoformat()} WARNING sl_reset_bar_fetch_failed "
            f"{exc}; target-only watch continues",
            flush=True,
        ),
    )


def _broker_health_is_healthy(health) -> bool:
    return health.is_connected and health.connection_state.value == "CONNECTED"


def _describe_broker_health(health) -> str:
    warnings = ",".join(health.warnings) if getattr(health, "warnings", ()) else "none"
    diagnostics = ",".join(health.diagnostics) if getattr(health, "diagnostics", ()) else "none"
    return (
        f"state={health.connection_state.value} "
        f"is_connected={health.is_connected} "
        f"reconnect_attempts={health.reconnect_attempts} "
        f"warnings={warnings} "
        f"diagnostics={diagnostics}"
    )


def _rebuild_dashboard(*, output_root: Path, dashboard_config_path: Path) -> None:
    resolved_output_root = REPO_ROOT / output_root
    try:
        lock_handle = _acquire_dashboard_build_lock(resolved_output_root)
    except OSError as exc:
        print(
            f"{datetime.now().isoformat()} WARNING dashboard_rebuild_skipped "
            f"lock_error={exc}; supervisor remains alive",
            flush=True,
        )
        return
    try:
        strategy_configs = load_dashboard_strategy_configs(
            dashboard_config_path,
            repo_root=REPO_ROOT,
        )
        TfisOperatorDashboardBuilder(
            strategy_configs=strategy_configs,
        ).build(output_root=resolved_output_root)
    finally:
        _release_watch_file_lock(lock_handle)


def _acquire_dashboard_build_lock(output_root: Path):
    lock_path = output_root / ".operator_dashboard_build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        return handle
    except OSError:
        handle.close()
        raise


def _ensure_watch_lock(
    held_watch_locks: dict[tuple[str, str], Any],
    *,
    key: tuple[str, str],
    directory: Path,
) -> bool:
    if key in held_watch_locks:
        return True
    try:
        held_watch_locks[key] = _acquire_watch_file_lock(directory)
        return True
    except RuntimeError as exc:
        print(f"{datetime.now().isoformat()} INFO {exc}", flush=True)
        return False


def _acquire_watch_file_lock(state_directory: Path):
    lock_path = state_directory / ".tfis_paper_lifecycle_supervisor.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        return handle
    except OSError as exc:
        handle.close()
        raise RuntimeError(
            f"Another TFIS paper lifecycle supervisor or legacy watcher already holds {lock_path}."
        ) from exc


def _release_watch_file_lock(handle) -> None:
    if handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _release_stale_handles(
    *,
    held_watch_locks: dict[tuple[str, str], Any],
    held_trade_ids: dict[tuple[str, str], str],
    active_keys: set[tuple[str, str]],
    runtimes: tuple[_TargetRuntime, ...],
) -> None:
    runtime_by_strategy = {runtime.spec.strategy_code: runtime for runtime in runtimes}
    stale_keys = [key for key in held_watch_locks if key not in active_keys]
    for key in stale_keys:
        handle = held_watch_locks.pop(key, None)
        if handle is not None:
            _release_watch_file_lock(handle)
        trade_id = held_trade_ids.pop(key, None)
        if trade_id is not None:
            runtime = runtime_by_strategy[key[0]]
            runtime.live_state_store.release_trade_lock(
                trade_id=trade_id,
                owner_id=_owner_id_for_spec(runtime.spec),
            )


def _owner_id_for_spec(spec: PaperLifecycleSupervisorTargetSpec) -> str:
    return paper_live_state_owner_id(f"tfis-paper-lifecycle-supervisor:{spec.strategy_code.lower()}")


def _all_targets_past_cutoff(*, now_by_strategy: dict[str, datetime], until_time: time) -> bool:
    if not now_by_strategy:
        return False
    return all(now.timetz().replace(tzinfo=None) >= until_time for now in now_by_strategy.values())


def _order_id_for_state(state: PaperOrderState | None) -> str:
    if state is None:
        return "unknown-order"
    timestamp = state.order_timestamp.strftime("%Y%m%dT%H%M%S")
    return (
        f"{state.strategy_code}-{state.strategy_branch}-"
        f"{state.selected_contract_symbol}-ORDER-{timestamp}"
    )


def _parse_hhmm(value: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(int(hour_text), int(minute_text))
    except Exception as exc:
        raise argparse.ArgumentTypeError("--until must be HH:MM") from exc


def _print_start_banner(*, args, runtimes: tuple[_TargetRuntime, ...]) -> None:
    print("=" * 60, flush=True)
    print("TFIS PAPER LIFECYCLE SUPERVISOR", flush=True)
    print(f"Process ID       : {os.getpid()}", flush=True)
    print(f"Targets config   : {Path(args.targets_config).resolve()}", flush=True)
    print(f"Dashboard output : {args.dashboard_output_root}", flush=True)
    print(f"Poll seconds     : {args.poll_seconds}", flush=True)
    print(f"Cutoff time      : {args.until}", flush=True)
    print("Strategies       : " + ", ".join(runtime.spec.strategy_code for runtime in runtimes), flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
