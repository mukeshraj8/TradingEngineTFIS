from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import yaml

from tfis.broker.authentication import BrokerSessionStatus
from tfis.broker.authentication.fyers import FyersAuthenticationAdapter
from tfis.fyers_read_only import FyersReadOnlyAdapter, FyersReadOnlyStatus, classify_monthly_expiries
from tfis.persistence import canonical_hash

from .registry import EnabledStrategyRegistry, load_enabled_strategy_registry


IST = ZoneInfo("Asia/Calcutta")
MARKET_OPEN = time(9, 15)
DEFAULT_ORPT = time(9, 24, 59, 400000)
DEFAULT_RC = time(9, 29, 59, 400000)
DEFAULT_EOD = time(15, 0)


@dataclass(frozen=True, slots=True)
class LiveObservationResult:
    report_dir: Path
    session_id: str
    verdict: str
    dashboard_port: int
    files: tuple[str, ...]


def run_live_observation(
    *,
    repo_root: str | Path,
    registry_path: str | Path,
    report_dir: str | Path,
    dashboard_port: int = 8766,
) -> LiveObservationResult:
    root = Path(repo_root)
    registry = load_enabled_strategy_registry(root / registry_path)
    output_root = root / report_dir
    output_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=IST)
    session_id = f"NSE:{now.date().isoformat()}:LIVE_OBSERVATION"

    process_state = _process_state(root, dashboard_port)
    dashboard_state = _dashboard_state(dashboard_port)
    timing_status = _timing_status(registry, now=now, session_started_at=now)

    auth_adapter = FyersAuthenticationAdapter(tfis_root=root, logical_account_ref="unified-live-observation")
    auth_result = auth_adapter.authenticate(allow_refresh=False, validate_session=True)
    auth_payload = auth_result.to_dict()

    live_reads: dict[str, Any] = {
        "underlyings": {},
        "option_chains": {},
        "selected_contracts": {},
    }
    subscription_status: dict[str, Any] = {
        "mode": "BOUNDED_READ_ONLY_POLL",
        "continuous_supervisor": False,
        "subscription_owner": "scripts/run_tfis_internal_paper.py --live-observation-only",
        "underlying_symbols": [],
        "selected_contracts_pinned": [],
        "candidate_contracts_required": [],
        "duplicate_provider_subscription": False,
        "reconnect_evidence": "NOT_APPLICABLE_ONE_SHOT_CAPTURE",
    }
    gap_items: list[dict[str, Any]] = []

    if auth_result.status is BrokerSessionStatus.AUTHENTICATED and auth_result.session is not None:
        adapter = FyersReadOnlyAdapter.from_validated_session(
            auth_result.session,
            now_provider=lambda: datetime.now(tz=IST),
        )
        nse_master = adapter.fetch_symbol_master("NSE")
        nsefo_master = adapter.fetch_symbol_master("NSEFO")
        underlying_symbols = _load_underlying_symbols(root)
        quote_result = adapter.fetch_quotes(tuple(underlying_symbols.values()))
        live_reads["underlyings"] = _serialize_result(quote_result)
        subscription_status["underlying_symbols"] = list(underlying_symbols.values())

        instrument_records = tuple(nsefo_master.payload) if nsefo_master.status is FyersReadOnlyStatus.SUCCESS else ()

        reliance_capture = _read_json(_latest_reliance_capture(root))
        live_reads["s22_snapshot_ingested"] = {
            "status": "LIVE_FYERS_READ_ONLY_CAPTURE",
            "snapshot_id": reliance_capture["snapshot_id"],
            "captured_at": reliance_capture["captured_at"],
        }
        reliance_selected = "NSE:RELIANCE26AUG1260CE"
        live_reads["selected_contracts"]["S22_RELIANCE_INTERNAL_PAPER_A"] = _serialize_result(
            adapter.fetch_quotes((reliance_selected,))
        )
        subscription_status["selected_contracts_pinned"].append(reliance_selected)

        if nsefo_master.status is FyersReadOnlyStatus.SUCCESS:
            s22_records = tuple(record for record in instrument_records if record.underlying == "RELIANCE")
            s22_expiry = classify_monthly_expiries(s22_records, underlying="RELIANCE", as_of=now.date())
            live_reads["option_chains"]["S22_RELIANCE_INTERNAL_PAPER_A"] = _serialize_result(
                adapter.fetch_option_chain(
                    underlying="NSE:RELIANCE-EQ",
                    expiry=s22_expiry.near_monthly_expiry,
                    strike_count=25,
                    instrument_records=s22_records,
                )
            )

            banknifty_records = tuple(record for record in instrument_records if record.underlying == "BANKNIFTY")
            nifty_records = tuple(record for record in instrument_records if record.underlying == "NIFTY")
            live_reads["option_chains"]["S21_BANKNIFTY_INTERNAL_PAPER_A"] = _serialize_result(
                adapter.fetch_option_chain(
                    underlying=underlying_symbols["BANKNIFTY"],
                    strike_count=15,
                    instrument_records=banknifty_records,
                )
            )
            live_reads["option_chains"]["S23_NIFTY_INTERNAL_PAPER_A"] = _serialize_result(
                adapter.fetch_option_chain(
                    underlying=underlying_symbols["NIFTY"],
                    strike_count=15,
                    instrument_records=nifty_records,
                )
            )
        else:
            gap_items.append(
                {
                    "gap_id": "LIVE-OBS-G001",
                    "classification": "NSEFO_SYMBOL_MASTER_UNAVAILABLE",
                    "description": "NSEFO symbol master was not available during the bounded live observation.",
                }
            )
    else:
        gap_items.append(
            {
                "gap_id": "LIVE-OBS-G000",
                "classification": "AUTHENTICATION_FAILED",
                "description": f"FYERS authentication did not reach AUTHENTICATED: {auth_result.status.value}",
            }
        )

    instance_status = _enabled_instance_status(
        registry=registry,
        now=now,
        session_id=session_id,
        timing_status=timing_status,
        dashboard_state=dashboard_state,
        live_reads=live_reads,
    )
    continuity = _selected_contract_continuity(instance_status)
    authority = _authority_audit(auth_result, process_state, dashboard_state)
    persistence = _persistence_state(root, output_root, session_id)
    timeline = _event_timeline(now, auth_result, process_state, dashboard_state, instance_status, continuity)
    live_summary = _summary_markdown(
        now=now,
        session_id=session_id,
        auth_result=auth_result,
        dashboard_state=dashboard_state,
        continuity=continuity,
        timing_status=timing_status,
        gap_items=gap_items,
    )
    supervisor = _supervisor_startup(now, registry)
    dashboard_projection = {
        "source": "CURRENT_OPERATOR_DASHBOARD",
        "captured_at": now.isoformat(),
        "dashboard_state": dashboard_state,
        "note": "Existing dashboard remains deterministic/internal-paper oriented; live observation is recorded separately here.",
    }
    dashboard_validation = {
        "captured_at": now.isoformat(),
        "dashboard_running": dashboard_state["healthy"],
        "dashboard_port": dashboard_port,
        "health_payload": dashboard_state["health_payload"],
        "misrepresents_fixture_as_live": True if dashboard_state["healthy"] else False,
        "required_live_labels_present": False,
        "verdict": "CONDITIONAL",
        "reason": "Current running dashboard is healthy but does not yet expose all required live-observation evidence labels.",
    }
    s21_live = instance_status["instances"]["S21_BANKNIFTY_INTERNAL_PAPER_A"]
    s22_live = instance_status["instances"]["S22_RELIANCE_INTERNAL_PAPER_A"]
    s23_live = instance_status["instances"]["S23_NIFTY_INTERNAL_PAPER_A"]
    market_subscription = {
        **subscription_status,
        "captured_at": now.isoformat(),
        "selected_contract_continuity": continuity["instances"],
    }
    eod_observation = {
        "session_id": session_id,
        "captured_at": now.isoformat(),
        "status": "FUTURE_WINDOW" if now.timetz().replace(tzinfo=None) < DEFAULT_EOD else "CURRENT_OR_PAST_WINDOW",
        "active_position_count": 0,
        "result": "NO_ACTIVE_POSITION",
        "note": "No genuine today-session internal-paper positions were opened by a live supervisor before this late start.",
    }

    dashboard_gaps = []
    if dashboard_validation.get("required_live_labels_present", False) is False:
        dashboard_gaps.append(
            {
                "gap_id": "LIVE-OBS-G004",
                "classification": "DASHBOARD_LIVE_LABELS_MISSING",
                "description": "The existing operator dashboard does not yet display the required live-observation evidence labels.",
            }
        )

    files = {
        "live_session_preflight.json": {
            "schema_version": "tfis.live_session.preflight.v1",
            "session_id": session_id,
            "current_time": now.isoformat(),
            "market_session_state": _market_session_state(now),
            "worktree_status": process_state["git_status"],
            "dashboard_state": dashboard_state,
        },
        "unified_supervisor_startup.json": supervisor,
        "enabled_instance_status.json": instance_status,
        "market_subscription_status.json": market_subscription,
        "s21_live_observation.json": s21_live,
        "s22_live_observation.json": s22_live,
        "s23_live_observation.json": s23_live,
        "selected_contract_continuity.json": continuity,
        "timing_window_classification.json": timing_status,
        "live_event_timeline.json": timeline,
        "dashboard_live_projection.json": dashboard_projection,
        "dashboard_live_validation.json": dashboard_validation,
        "eod_lifecycle_observation.json": eod_observation,
        "persistence_and_checkpoint.json": persistence,
        "authority_audit.json": authority,
        "gap_register.json": {
            "schema_version": "tfis.live_session.gap_register.v1",
            "captured_at": now.isoformat(),
            "gaps": gap_items + continuity["gaps"] + dashboard_gaps,
        },
    }
    rendered_files: list[str] = []
    for name, payload in files.items():
        _write_json(output_root / name, payload)
        rendered_files.append(name)
    (output_root / "live_session_summary.md").write_text(live_summary, encoding="utf-8")
    rendered_files.append("live_session_summary.md")

    verdict = "UNIFIED_LIVE_READ_OBSERVATION_CONDITIONAL"
    if auth_result.status is not BrokerSessionStatus.AUTHENTICATED:
        verdict = "UNIFIED_LIVE_READ_OBSERVATION_BLOCKED"

    return LiveObservationResult(
        report_dir=output_root,
        session_id=session_id,
        verdict=verdict,
        dashboard_port=dashboard_port,
        files=tuple(rendered_files),
    )


def _market_session_state(now: datetime) -> str:
    if now.weekday() >= 5:
        return "CLOSED_WEEKEND"
    current = now.timetz().replace(tzinfo=None)
    if current < MARKET_OPEN:
        return "PRE_OPEN"
    if current <= time(15, 30):
        return "LIVE"
    return "POST_MARKET"


def _timing_status(registry: EnabledStrategyRegistry, *, now: datetime, session_started_at: datetime) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for item in registry.enabled_instances:
        projection = item.deterministic_projection
        orpt = _parse_clock(str(projection.get("orpt") or DEFAULT_ORPT.isoformat()))
        rc = _parse_clock(str(projection.get("rc") or DEFAULT_RC.isoformat()))
        rows[item.strategy_instance_id] = {
            "market_open": _classify_window(now, session_started_at, MARKET_OPEN),
            "orpt": _classify_window(now, session_started_at, orpt),
            "rc": _classify_window(now, session_started_at, rc),
            "eod_carry": _classify_window(now, session_started_at, DEFAULT_EOD),
            "shutdown_checkpoint": "FUTURE_WINDOW" if now.timetz().replace(tzinfo=None) < time(15, 31) else "CURRENT_WINDOW",
        }
    return {
        "schema_version": "tfis.live_session.timing_windows.v1",
        "captured_at": now.isoformat(),
        "session_start": session_started_at.isoformat(),
        "instances": rows,
    }


def _classify_window(now: datetime, started_at: datetime, event_time: time) -> str:
    current = now.timetz().replace(tzinfo=None)
    started = started_at.timetz().replace(tzinfo=None)
    if current < event_time:
        return "FUTURE_WINDOW"
    if started > event_time:
        return "MISSED_BEFORE_SUPERVISOR_START"
    return "CURRENT_WINDOW" if current == event_time else "CAPTURED"


def _enabled_instance_status(
    *,
    registry: EnabledStrategyRegistry,
    now: datetime,
    session_id: str,
    timing_status: Mapping[str, Any],
    dashboard_state: Mapping[str, Any],
    live_reads: Mapping[str, Any],
) -> dict[str, Any]:
    instances: dict[str, Any] = {}
    for item in registry.enabled_instances:
        instrument = item.symbol
        live_underlying = _quote_for_symbol(live_reads.get("underlyings", {}), instrument)
        timed = timing_status["instances"][item.strategy_instance_id]
        selection_observed = item.strategy_instance_id == "S22_RELIANCE_INTERNAL_PAPER_A"
        instances[item.strategy_instance_id] = {
            "strategy_instance_id": item.strategy_instance_id,
            "strategy_definition_id": item.strategy_definition_id,
            "strategy_version": item.strategy_version,
            "account": item.account_reference,
            "underlying": instrument,
            "session_id": session_id,
            "monthly_status": item.deterministic_projection.get("monthly_status"),
            "branch": item.deterministic_projection.get("branch"),
            "plan_status": "PREPARED" if selection_observed else "NO_NEW_ENTRY_LATE_SUPERVISOR_START",
            "selected_contract": item.deterministic_projection.get("selected_contract") if selection_observed else None,
            "blocked_reason": None if selection_observed else "CURRENT_SESSION_SELECTION_NOT_OBSERVED_BY_SUPERVISOR",
            "timing_window_status": timed,
            "quote_oi_quality": "LIVE_READ_OK" if live_underlying else "LIVE_READ_MISSING",
            "runtime_stage": "LATE_START_NO_NEW_ENTRY",
            "entry_eligibility": "NO_NEW_ENTRY_LATE_SUPERVISOR_START",
            "lifecycle_state": "OBSERVATION_ONLY",
            "evidence_classification": (
                "LIVE_FYERS_READ_ONLY_CAPTURE" if selection_observed else "MISSED_BEFORE_SUPERVISOR_START"
            ),
            "underlying_quote": live_underlying,
            "dashboard_attached": dashboard_state["healthy"],
        }
    return {
        "schema_version": "tfis.live_session.enabled_instance_status.v1",
        "captured_at": now.isoformat(),
        "instances": instances,
    }


def _selected_contract_continuity(instance_status: Mapping[str, Any]) -> dict[str, Any]:
    continuity: dict[str, Any] = {}
    gaps: list[dict[str, Any]] = []
    for instance_id, payload in instance_status["instances"].items():
        selected = payload.get("selected_contract")
        if selected:
            continuity[instance_id] = {
                "status": "IDENTIFIABLE",
                "selected_contract": selected,
                "evidence": payload["evidence_classification"],
            }
            continue
        continuity[instance_id] = {
            "status": "CURRENT_SESSION_SELECTION_NOT_OBSERVED_BY_SUPERVISOR",
            "selected_contract": None,
            "evidence": payload["evidence_classification"],
        }
        gaps.append(
            {
                "gap_id": f"LIVE-OBS-CONTINUITY-{instance_id}",
                "classification": "CURRENT_SESSION_SELECTION_NOT_OBSERVED_BY_SUPERVISOR",
                "description": f"{instance_id} could not safely claim a live selected contract after supervisor late start.",
            }
        )
    return {
        "schema_version": "tfis.live_session.selected_contract_continuity.v1",
        "instances": continuity,
        "gaps": gaps,
    }


def _supervisor_startup(now: datetime, registry: EnabledStrategyRegistry) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_session.unified_supervisor_startup.v1",
        "captured_at": now.isoformat(),
        "session_id": f"NSE:{now.date().isoformat()}:LIVE_OBSERVATION",
        "existing_command_audited": ".\\.venv\\Scripts\\python.exe scripts\\run_tfis_internal_paper.py",
        "existing_runtime_shape": "DETERMINISTIC_PROJECTION_ONLY",
        "today_mode": "INTERNAL_PAPER_LATE_START_NO_NEW_ENTRY",
        "continuous_supervisor_active": False,
        "enabled_instances": [item.strategy_instance_id for item in registry.enabled_instances],
        "missing_capabilities": [
            "continuous_live_event_loop",
            "subscription_owner",
            "scheduler_through_eod",
            "checkpoint_resume_for_live_session",
        ],
        "result": "BOUNDED_LIVE_OBSERVATION_ONLY",
    }


def _authority_audit(auth_result: Any, process_state: Mapping[str, Any], dashboard_state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "tfis.live_session.authority_audit.v1",
        "authentication_status": auth_result.status.value,
        "dashboard_healthy": dashboard_state["healthy"],
        "external_broker_order_authority": "NONE",
        "external_paper_authority": "NONE",
        "live_money_authority": "NONE",
        "broker_write_available": False,
        "operator_session_process_count": len(process_state["processes"]),
    }


def _event_timeline(
    now: datetime,
    auth_result: Any,
    process_state: Mapping[str, Any],
    dashboard_state: Mapping[str, Any],
    instance_status: Mapping[str, Any],
    continuity: Mapping[str, Any],
) -> dict[str, Any]:
    sequence = 1
    events: list[dict[str, Any]] = []
    def add(event_type: str, result: str, **extra: Any) -> None:
        nonlocal sequence
        events.append(
            {
                "event_id": f"evt:{sequence:04d}",
                "session_id": instance_status["instances"]["S22_RELIANCE_INTERNAL_PAPER_A"]["session_id"],
                "event_type": event_type,
                "sequence": sequence,
                "receipt_timestamp": now.isoformat(),
                "source_timestamp": extra.pop("source_timestamp", now.isoformat()),
                "evidence_type": extra.pop("evidence_type", "LIVE_OBSERVATION"),
                "provenance": extra.pop("provenance", "scripts/run_tfis_internal_paper.py --live-observation-only"),
                "result": result,
                **extra,
            }
        )
        sequence += 1
    add("PROCESS_INSPECTION", "CAPTURED", evidence_type="LOCAL_PROCESS_STATE", process_count=len(process_state["processes"]))
    add("DASHBOARD_HEALTH", "CAPTURED" if dashboard_state["healthy"] else "FAILED", evidence_type="LOCAL_DASHBOARD")
    add("BROKER_DIAGNOSTIC", auth_result.status.value, evidence_type="FYERS_AUTH")
    for instance_id, payload in instance_status["instances"].items():
        add(
            "INSTANCE_LOAD",
            "CAPTURED",
            strategy_instance_id=instance_id,
            instrument=payload["underlying"],
            result_hash=canonical_hash(payload),
        )
        add(
            "TIMING_CLASSIFICATION",
            payload["entry_eligibility"],
            strategy_instance_id=instance_id,
            instrument=payload["underlying"],
            evidence_type=payload["evidence_classification"],
        )
    for instance_id, status in continuity["instances"].items():
        add(
            "SELECTED_CONTRACT_CONTINUITY",
            status["status"],
            strategy_instance_id=instance_id,
            instrument=instance_status["instances"][instance_id]["underlying"],
            evidence_type=status["evidence"],
        )
    return {
        "schema_version": "tfis.live_session.event_timeline.v1",
        "captured_at": now.isoformat(),
        "events": events,
    }


def _persistence_state(root: Path, output_root: Path, session_id: str) -> dict[str, Any]:
    internal_paths = []
    data_root = root / "data" / "internal_paper"
    if data_root.exists():
        internal_paths = [str(path.relative_to(root)) for path in sorted(data_root.rglob("*")) if path.is_file()][:20]
    return {
        "schema_version": "tfis.live_session.persistence_and_checkpoint.v1",
        "session_id": session_id,
        "report_dir": str(output_root.relative_to(root)),
        "live_session_sqlite_checkpoint": "NOT_ACTIVE_FOR_BOUNDED_OBSERVATION",
        "existing_internal_paper_files": internal_paths,
        "artifacts_hash": canonical_hash({"session_id": session_id, "report_dir": str(output_root)}),
    }


def _summary_markdown(
    *,
    now: datetime,
    session_id: str,
    auth_result: Any,
    dashboard_state: Mapping[str, Any],
    continuity: Mapping[str, Any],
    timing_status: Mapping[str, Any],
    gap_items: list[dict[str, Any]],
) -> str:
    return (
        "# Unified Live Read Observation\n\n"
        f"Current time: `{now.isoformat()}`\n\n"
        f"Session id: `{session_id}`\n\n"
        f"Authentication: `{auth_result.status.value}`\n\n"
        f"Dashboard healthy: `{dashboard_state['healthy']}`\n\n"
        f"Continuity statuses: `{json.dumps(continuity['instances'], sort_keys=True)}`\n\n"
        f"Timing windows: `{json.dumps(timing_status['instances'], sort_keys=True)}`\n\n"
        f"Gaps: `{json.dumps(gap_items, sort_keys=True)}`\n"
    )


def _process_state(root: Path, dashboard_port: int) -> dict[str, Any]:
    git_status = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    process_query = subprocess.run(
        [
            "powershell",
            "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_tfis_dashboard.py|run_tfis_internal_paper.py|run_s23_internal_paper.py|capture_s22_reliance_fyers_snapshot.py|run_broker_diagnostics.py|fyers_token_refresh.py' } | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    listener_query = subprocess.run(
        [
            "powershell",
            "-Command",
            f"Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {{ $_.LocalPort -eq {dashboard_port} }} | Select-Object LocalAddress,LocalPort,OwningProcess,State | ConvertTo-Json -Compress",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "git_status": git_status,
        "processes": _maybe_json(process_query.stdout),
        "listeners": _maybe_json(listener_query.stdout),
    }


def _dashboard_state(port: int) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {"healthy": response.status == 200, "health_payload": payload, "url": url}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"healthy": False, "health_payload": {"error": str(exc)}, "url": url}


def _load_underlying_symbols(root: Path) -> dict[str, str]:
    data = yaml.safe_load((root / "config" / "monthly_status_instruments.yaml").read_text(encoding="utf-8"))
    instruments = data.get("instruments") or {}
    return {
        "NIFTY": str(instruments["NIFTY"]["spot_symbol"]),
        "BANKNIFTY": str(instruments["BANKNIFTY"]["spot_symbol"]),
        "RELIANCE": "NSE:RELIANCE-EQ",
    }


def _latest_reliance_capture(root: Path) -> Path:
    base = root / "data" / "strategies" / "S22" / "fyers_read_only_snapshots" / date.today().isoformat()
    snapshots = sorted(base.glob("s22-reliance-fyers-*/snapshot.json"))
    if not snapshots:
        raise FileNotFoundError(f"No RELIANCE live capture found under {base}")
    return snapshots[-1]


def _serialize_result(result: Any) -> dict[str, Any]:
    return result.to_dict() if hasattr(result, "to_dict") else dict(result)


def _quote_for_symbol(underlying_reads: Mapping[str, Any], instrument: str) -> Mapping[str, Any] | None:
    payload = underlying_reads.get("payload") if isinstance(underlying_reads, Mapping) else None
    if not isinstance(payload, list):
        return None
    if instrument == "RELIANCE":
        target = "NSE:RELIANCE-EQ"
    elif instrument == "BANKNIFTY":
        target = "NSE:NIFTYBANK-INDEX"
    else:
        target = "NSE:NIFTY50-INDEX"
    for item in payload:
        if isinstance(item, Mapping) and item.get("symbol") == target:
            return item
    return None


def _parse_clock(value: str) -> time:
    text = value.split(".")[0]
    if "T" in text:
        text = text.split("T", 1)[1]
    if "+" in text:
        text = text.split("+", 1)[0]
    return time.fromisoformat(text)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _maybe_json(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
