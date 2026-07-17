from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time as time_module
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.brokers import BrokerAdapter, BrokerAdapterError
from tfis.brokers.fyers_token import prepare_fyers_env_from_tfis
from tfis.dashboard import TfisOperatorDashboardBuilder
from tfis.dashboard.config_loader import load_dashboard_strategy_configs
from tfis.paper import (
    DeterministicExpiryCalendar,
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
    S23PaperExpiryGovernance,
    S23PaperPositionManager,
    PaperLifecycleRuntimeConfig,
    build_paper_live_state_store_from_yaml,
    build_paper_broker_adapter,
    load_paper_lifecycle_supervisor_target_specs,
    paper_live_state_owner_id,
)
from tfis.paper.models import SelectedContractBarEvent, SelectedContractQuoteEvent
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
    prepare_fyers_env_from_tfis(tfis_root=args.tfis_root, skip_refresh=args.skip_refresh)
    for runtime in runtimes:
        runtime.adapter.connect()

    iterations = 0
    try:
        while True:
            iterations += 1
            active_keys: set[tuple[str, str]] = set()
            any_targets = False
            now_by_strategy: dict[str, datetime] = {}

            for runtime in runtimes:
                evaluated_at = datetime.now(runtime.timezone)
                now_by_strategy[runtime.spec.strategy_code] = evaluated_at
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
            if (not any_targets) and (not args.no_targets_ok):
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
        config = PaperLifecycleRuntimeConfig.from_yaml(spec.config_path)
        timezone_name = config.broker.timezone
        timezone = ZoneInfo(timezone_name)
        live_state_store = build_paper_live_state_store_from_yaml(spec.config_path)
        runtimes.append(
            _TargetRuntime(
                spec=spec,
                config=config,
                timezone_name=timezone_name,
                timezone=timezone,
                adapter=build_paper_broker_adapter(config),
                live_state_store=live_state_store,
                supervisor=PaperLifecycleSupervisor(
                    order_store=PaperOrderStateStore(),
                    position_manager=S23PaperPositionManager(
                        live_state_store=live_state_store,
                        slippage_exit_points=config.costs.slippage_exit_points or 0.0,
                    ),
                ),
            )
        )
    return tuple(runtimes)


def _process_target(
    *,
    runtime: _TargetRuntime,
    target,
    held_trade_ids: dict[tuple[str, str], str],
    lock_ttl_seconds: int,
    watch_cutoff_time: time,
    dashboard_rebuild_disabled: bool,
    evaluated_at: datetime,
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
        runtime.live_state_store.release_trade_lock(
            trade_id=held_trade_ids.pop(key, context.trade_id),
            owner_id=owner_id,
        )
        return

    events = _fetch_selected_contract_events(
        adapter=runtime.adapter,
        selected_contract_symbol=context.selected_contract_symbol,
        session_date=context.session_date,
        evaluated_at=evaluated_at,
        state=context.position_state,
    )
    _append_selected_contract_market_events(
        context.session_directory,
        events=events,
        observed_at=evaluated_at,
        watcher_pid=os.getpid(),
        trade_id=context.trade_id,
    )
    previous_trade_id = context.trade_id
    lifecycle_result = runtime.supervisor.supervise(
        context,
        market_events=events,
        evaluated_at=evaluated_at,
        watch_cutoff_time=watch_cutoff_time,
        expiry_governance=S23PaperExpiryGovernance(DeterministicExpiryCalendar()),
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
        runtime.live_state_store.release_trade_lock(
            trade_id=held_trade_ids.pop(key, context.trade_id),
            owner_id=owner_id,
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


def _fetch_selected_contract_events(
    *,
    adapter: BrokerAdapter,
    selected_contract_symbol: str,
    session_date: date,
    evaluated_at: datetime,
    state: PaperPositionState | None,
) -> tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...]:
    events: list[SelectedContractQuoteEvent | SelectedContractBarEvent] = []
    if (
        state is not None
        and getattr(state, "stoploss_reset_pending", False)
        and not getattr(state, "stoploss_active", True)
        and session_date > (getattr(state, "stoploss_reset_session_date", None) or state.entry_date)
    ):
        rc_time = getattr(state, "stoploss_reset_rc_time", None) or time(9, 29, 59)
        to_time = max(evaluated_at.timetz().replace(tzinfo=None), rc_time)
        try:
            events.extend(
                adapter.get_option_bars(
                    selected_contract_symbol,
                    session_date=session_date,
                    from_time=time(9, 15),
                    to_time=to_time,
                    interval_minutes=1,
                )
            )
        except (AttributeError, BrokerAdapterError) as exc:
            print(
                f"{evaluated_at.isoformat()} WARNING sl_reset_bar_fetch_failed "
                f"{exc}; target-only watch continues",
                flush=True,
            )
    quote = adapter.get_option_quote(
        selected_contract_symbol,
        session_date=session_date,
    )
    events.append(quote)
    return tuple(events)


def _append_selected_contract_market_events(
    directory: Path,
    *,
    events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    observed_at: datetime,
    watcher_pid: int,
    trade_id: str,
) -> Path:
    path = directory / "selected_contract_market_events.jsonl"
    if not events:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            payload = _serialize_selected_contract_market_event(
                event,
                observed_at=observed_at,
                watcher_pid=watcher_pid,
                trade_id=trade_id,
            )
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


def _serialize_selected_contract_market_event(
    event: SelectedContractQuoteEvent | SelectedContractBarEvent,
    *,
    observed_at: datetime,
    watcher_pid: int,
    trade_id: str,
) -> dict[str, Any]:
    payload = _to_jsonable(asdict(event) if is_dataclass(event) else event)
    event_kind = (
        "selected_contract_quote"
        if isinstance(event, SelectedContractQuoteEvent)
        else "selected_contract_bar"
    )
    return {
        "artifact_version": 1,
        "event_kind": event_kind,
        "observed_at": observed_at.isoformat(),
        "watcher_pid": watcher_pid,
        "trade_id": trade_id,
        "symbol": event.symbol,
        "payload": payload,
    }


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


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
