from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from tfis.broker.authentication import (
    BrokerAuthenticationResult,
    BrokerCredentialReference,
    BrokerSessionStatus,
)
from tfis.persistence import PersistenceDatabase, apply_migrations
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance
from tfis.runtime.multi_strategy.supervisor import (
    ContinuousSupervisorConfig,
    SubscriptionOwner,
    UnifiedInternalPaperSupervisor,
    _collect_projection_labels,
    _live_instance_result,
    _next_sleep_seconds,
    _projection_meets_required_labels,
    _seconds_until_next_critical_event,
    build_authoritative_readiness_projection,
    run_complete_session_preflight,
)


IST = ZoneInfo("Asia/Calcutta")


def test_live_instance_result_prefers_authoritative_live_plan_values_over_fixture_projection() -> None:
    instance = EnabledStrategyInstance(
        strategy_definition_id="S21_BANKNIFTY_OP_SELL_MONTHLY",
        strategy_version="s21.test.v1",
        strategy_instance_id="S21_BANKNIFTY_INTERNAL_PAPER_A",
        account_reference="INTERNAL_PAPER_ACCOUNT_A",
        underlying={"exchange": "NSE", "symbol": "BANKNIFTY", "instrument_type": "INDEX"},
        product="OPTION_SELLING",
        enabled=True,
        configured_quantity={"lots": 1, "lot_size": 15},
        authority_mode="INTERNAL_PAPER_CONTROLLED",
        market_data_source="FYERS_READ_ONLY",
        rule_config_hash="test-hash",
        risk_allocation={"max_positions": 1, "max_margin_usage_pct": 25},
        operator_approval_status="APPROVED_INTERNAL_PAPER",
        evidence_quality="FIXTURE_BACKED",
        deterministic_projection={
            "branch": "BULL_CALL",
            "selected_contract": "BANKNIFTY24JAN47000CE",
            "entry": "925.00",
            "target": "370.00",
            "original_sl": "1337.50",
            "monthly_status": "BULL_CF",
            "market_references": {"2DHH": "47200.00"},
        },
    )

    result = _live_instance_result(
        instance,
        now=datetime(2026, 8, 4, 9, 12, tzinfo=IST),
        session_id="NSE:2026-08-04:UNIFIED_INTERNAL_PAPER",
        continuity={
            "status": "LIVE_AUTHORITATIVE_SELECTED_CONTRACT",
            "selected_contract": "NSE:BANKNIFTY26AUG47000CE",
            "selected_branch": "BEAR_CALL",
            "monthly_status": "BEAR_CF",
            "entry": "812.00",
            "target": "301.00",
            "original_sl": "1184.10",
            "evidence": "LIVE_READ_ONLY_RUNTIME_SELECTION",
            "selected_contract_quote": {
                "symbol": "NSE:BANKNIFTY26AUG47000CE",
                "ltp": "810.50",
                "oi": "84000",
                "source_timestamp": "2026-08-04T09:12:00+05:30",
                "receipt_timestamp": "2026-08-04T09:12:01+05:30",
            },
            "live_plan": {
                "plan_hash": "live-plan-hash",
                "market_references": {"2DHH": "52120.00", "2DLL": "51780.00"},
                "timing": {"orpt": "09:24:59.400000", "rc": "09:29:59.400000"},
            },
            "option_history_status": "SUCCESS",
        },
        timing={"market_open": "FUTURE_WINDOW", "orpt": "FUTURE_WINDOW", "rc": "FUTURE_WINDOW", "eod_carry": "FUTURE_WINDOW"},
        selected_contract_reads=(
            {"symbol": "NSE:BANKNIFTY26AUG47000CE", "receipt_timestamp": "2026-08-04T09:12:01+05:30"},
            {"symbol": "NSE:BANKNIFTY26AUG47000CE", "receipt_timestamp": "2026-08-04T09:12:05+05:30"},
        ),
        late_start=False,
    )

    assert result["plan"]["selected_contract"] == "NSE:BANKNIFTY26AUG47000CE"
    assert result["plan"]["branch"] == "BEAR_CALL"
    assert result["plan"]["monthly_status"] == "BEAR_CF"
    assert result["plan"]["base_entry"] == "812.00"
    assert result["plan"]["target"] == "301.00"
    assert result["plan"]["original_sl"] == "1184.10"
    assert result["plan"]["premium"] == "810.50"
    assert result["plan"]["oi"] == "84000"
    assert result["plan"]["plan_hash"] == "live-plan-hash"
    assert result["plan"]["history_completeness"] == "SUCCESS"
    assert result["plan"]["subscription_state"] == "PINNED"
    assert result["plan"]["first_quote_timestamp"] == "2026-08-04T09:12:01+05:30"
    assert result["plan"]["latest_quote_timestamp"] == "2026-08-04T09:12:05+05:30"


def test_live_instance_result_uses_capture_state_when_no_authoritative_history_exists() -> None:
    instance = EnabledStrategyInstance(
        strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_FOUR_BRANCH",
        strategy_version="s23.test.v1",
        strategy_instance_id="S23_NIFTY_INTERNAL_PAPER_A",
        account_reference="INTERNAL_PAPER_ACCOUNT_A",
        underlying={"exchange": "NSE", "symbol": "NIFTY", "instrument_type": "INDEX"},
        product="OPTION_SELLING",
        enabled=True,
        configured_quantity={"lots": 1, "lot_size": 50},
        authority_mode="INTERNAL_PAPER_CONTROLLED",
        market_data_source="FYERS_READ_ONLY",
        rule_config_hash="test-hash",
        risk_allocation={"max_positions": 1, "max_margin_usage_pct": 25},
        operator_approval_status="APPROVED_INTERNAL_PAPER",
        evidence_quality="FIXTURE_BACKED",
        deterministic_projection={
            "branch": "BULL_PUT",
            "entry": "194.25",
            "target": "77.70",
            "original_sl": "310.80",
            "monthly_status": "BULL_CF",
        },
    )

    result = _live_instance_result(
        instance,
        now=datetime(2026, 8, 4, 9, 5, tzinfo=IST),
        session_id="NSE:2026-08-04:UNIFIED_INTERNAL_PAPER",
        continuity={"status": "BLOCKED_OPTION_CHAIN_UNAVAILABLE", "selected_contract": None, "evidence": "LIVE_ACTUAL_CHAIN_SELECTION_FAILED_CLOSED"},
        timing={"market_open": "FUTURE_WINDOW", "orpt": "FUTURE_WINDOW", "rc": "FUTURE_WINDOW", "eod_carry": "FUTURE_WINDOW"},
        selected_contract_reads=(),
        late_start=False,
    )

    assert result["plan"]["plan_status"] == "BLOCKED"
    assert result["plan"]["block_reason"] == "BLOCKED_OPTION_CHAIN_UNAVAILABLE"
    assert result["plan"]["history_completeness"] == "NOT_CAPTURED"
    assert result["plan"]["subscription_state"] == "NOT_PINNED"


def test_live_instance_result_allows_reconstructed_late_start_entry_to_continue() -> None:
    instance = EnabledStrategyInstance(
        strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_FOUR_BRANCH",
        strategy_version="s23.test.v1",
        strategy_instance_id="S23_NIFTY_INTERNAL_PAPER_A",
        account_reference="INTERNAL_PAPER_ACCOUNT_A",
        underlying={"exchange": "NSE", "symbol": "NIFTY", "instrument_type": "INDEX"},
        product="OPTION_SELLING",
        enabled=True,
        configured_quantity={"lots": 1, "lot_size": 50},
        authority_mode="INTERNAL_PAPER_CONTROLLED",
        market_data_source="FYERS_READ_ONLY",
        rule_config_hash="test-hash",
        risk_allocation={"max_positions": 1, "max_margin_usage_pct": 25},
        operator_approval_status="APPROVED_INTERNAL_PAPER",
        evidence_quality="FIXTURE_BACKED",
        deterministic_projection={"branch": "BULL_PUT", "entry": "194.25", "target": "77.70", "original_sl": "310.80", "monthly_status": "BULL_CF"},
    )

    result = _live_instance_result(
        instance,
        now=datetime(2026, 8, 4, 10, 0, tzinfo=IST),
        session_id="NSE:2026-08-04:UNIFIED_INTERNAL_PAPER",
        continuity={
            "status": "SELECTED_CONTRACT_RECONSTRUCTED",
            "recovery_mode": "HISTORICALLY_RECONSTRUCTED",
            "current_entry_state": "NORMAL_ENTRY_STILL_VALID",
            "selected_contract": "NSE:NIFTY26AUG22500PE",
            "selected_branch": "BULL_PUT",
            "entry": "194.25",
            "target": "77.70",
            "original_sl": "310.80",
            "evidence": "HISTORICAL_UNDERLYING_PLUS_CURRENT_CHAIN_RECONSTRUCTION",
            "selected_contract_quote": {
                "symbol": "NSE:NIFTY26AUG22500PE",
                "ltp": "201.00",
                "oi": "45000",
                "source_timestamp": "2026-08-04T10:00:00+05:30",
                "receipt_timestamp": "2026-08-04T10:00:01+05:30",
            },
            "orpt_result": "ORPT_ENTRY_NOT_MISSED",
            "rc_result": "RC_NOT_REQUIRED",
            "option_history_status": "SUCCESS",
            "live_plan": {"plan_hash": "historical-plan"},
        },
        timing={"market_open": "MISSED_BEFORE_SUPERVISOR_START", "orpt": "MISSED_BEFORE_SUPERVISOR_START", "rc": "MISSED_BEFORE_SUPERVISOR_START", "eod_carry": "FUTURE_WINDOW"},
        selected_contract_reads=(),
        late_start=True,
    )

    assert result["runtime_stage"] == "POSITION_MONITORING"
    assert result["execution"]["opening_context"] == "HISTORICALLY_RECONSTRUCTED"
    assert result["execution"]["execution_intent"] == "PENDING_VALIDATION"
    assert result["execution"]["risk_result"] == "ACCEPTED"
    assert result["accounting"]["trade_classification"] == "NORMAL_ENTRY_STILL_VALID"


def test_subscription_owner_deduplicates_and_builds_runtime_index() -> None:
    owner = SubscriptionOwner()
    owner.pin_underlying("S21_A", "NSE:NIFTYBANK-INDEX", reason="UNDERLYING_OBSERVATION")
    owner.pin_underlying("S21_A", "NSE:NIFTYBANK-INDEX", reason="UNDERLYING_OBSERVATION")
    owner.pin_contract("S21_A", "BANKNIFTY26AUG47000CE", reason="SELECTED_CONTRACT_PINNED")
    owner.pin_contract("S21_A", "BANKNIFTY26AUG47000CE", reason="SELECTED_CONTRACT_PINNED")

    payload = owner.to_dict()
    snapshot = owner.runtime_index().snapshot()

    assert payload["underlyings"]["NSE:NIFTYBANK-INDEX"]["S21_A"] == ["UNDERLYING_OBSERVATION"]
    assert payload["contracts"]["BANKNIFTY26AUG47000CE"]["S21_A"] == ["SELECTED_CONTRACT_PINNED"]
    assert snapshot.underlying_to_strategy_instances["NSE:NIFTYBANK-INDEX"] == ("S21_A",)
    assert snapshot.contract_to_strategy_instances["BANKNIFTY26AUG47000CE"] == ("S21_A",)


def test_next_sleep_seconds_uses_remaining_poll_budget_instead_of_fixed_post_work_sleep() -> None:
    now = datetime(2026, 8, 3, 9, 20, 0, tzinfo=IST)
    sleep_seconds = _next_sleep_seconds(
        now=now,
        current_monotonic=102.2,
        next_poll_deadline_monotonic=105.0,
        late_start=False,
    )
    assert round(sleep_seconds, 3) == 2.8


def test_next_sleep_seconds_prefers_critical_event_boundary_over_later_poll_deadline() -> None:
    now = datetime(2026, 8, 3, 9, 24, 58, tzinfo=IST)
    sleep_seconds = _next_sleep_seconds(
        now=now,
        current_monotonic=200.0,
        next_poll_deadline_monotonic=205.0,
        late_start=False,
    )
    assert round(sleep_seconds, 3) == 1.4


def test_seconds_until_next_critical_event_in_late_start_mode_skips_orpt_and_rc_but_keeps_eod() -> None:
    now = datetime(2026, 8, 3, 14, 27, 16, 917352, tzinfo=IST)
    seconds_until_event = _seconds_until_next_critical_event(now, late_start=True)
    assert round(seconds_until_event or 0.0, 3) == round((datetime(2026, 8, 3, 15, 0, tzinfo=IST) - now).total_seconds(), 3)


def test_complete_session_preflight_is_ready_with_fake_auth_and_clean_db(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    db = PersistenceDatabase(tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite")
    with db.connect() as connection:
        apply_migrations(connection)
        connection.commit()

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=datetime(2026, 8, 3, 8, 50, tzinfo=IST),
                status=BrokerSessionStatus.AUTHENTICATED,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    result = run_complete_session_preflight(
        repo_root=tmp_path,
        registry_path="config/internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        db_path="data/internal_paper/unified_supervisor.sqlite",
        now_provider=lambda: datetime(2026, 8, 3, 8, 50, tzinfo=IST),
        auth_factory=lambda _root: _Auth(),
    )

    assert result.verdict == "READY_FOR_COMPLETE_UNIFIED_SESSION"
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["verdict"] == "READY_FOR_COMPLETE_UNIFIED_SESSION"
    assert payload["reasons"] == []


def test_complete_session_preflight_does_not_require_prebuilt_dashboard_snapshot(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path, include_snapshot=False)
    db = PersistenceDatabase(tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite")
    with db.connect() as connection:
        apply_migrations(connection)
        connection.commit()

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=datetime(2026, 8, 3, 8, 50, tzinfo=IST),
                status=BrokerSessionStatus.AUTHENTICATED,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    result = run_complete_session_preflight(
        repo_root=tmp_path,
        registry_path="config/internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        db_path="data/internal_paper/unified_supervisor.sqlite",
        now_provider=lambda: datetime(2026, 8, 3, 8, 50, tzinfo=IST),
        auth_factory=lambda _root: _Auth(),
    )

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert result.verdict == "READY_FOR_COMPLETE_UNIFIED_SESSION"
    assert "DASHBOARD_SNAPSHOT_MISSING" not in payload["reasons"]


def test_complete_session_preflight_ignores_stale_pid_metadata(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    db = PersistenceDatabase(tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite")
    with db.connect() as connection:
        apply_migrations(connection)
        connection.commit()

    state_root = tmp_path / "tmp" / "tfis_supervisor_state"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "continuous_unified_supervisor.pid.json").write_text(
        json.dumps(
            {
                "pid": 999999,
                "created_at": "2026-08-03T04:49:05.912094+00:00",
                "label": "continuous-unified-internal-paper-supervisor",
            }
        ),
        encoding="utf-8",
    )

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=datetime(2026, 8, 3, 8, 50, tzinfo=IST),
                status=BrokerSessionStatus.AUTHENTICATED,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    result = run_complete_session_preflight(
        repo_root=tmp_path,
        registry_path="config/internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        db_path="data/internal_paper/unified_supervisor.sqlite",
        now_provider=lambda: datetime(2026, 8, 3, 8, 50, tzinfo=IST),
        auth_factory=lambda _root: _Auth(),
    )

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert result.verdict == "READY_FOR_COMPLETE_UNIFIED_SESSION"
    assert "DUPLICATE_SUPERVISOR_PROCESS_LOCK_PRESENT" not in payload["reasons"]


def test_supervisor_persists_late_start_mode_and_snapshot_without_network(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    now = datetime(2026, 8, 3, 9, 45, tzinfo=IST)

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=now,
                status=BrokerSessionStatus.NETWORK_UNAVAILABLE,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    config = ContinuousSupervisorConfig(
        repo_root=tmp_path,
        registry_path=tmp_path / "config" / "internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        state_root=tmp_path / "tmp" / "tfis_supervisor_state",
        dashboard_output_root=tmp_path / "tmp" / "tfis_dashboard_v1",
        db_path=tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite",
        max_iterations=1,
        poll_seconds=0.01,
    )
    supervisor = UnifiedInternalPaperSupervisor(
        config,
        now_provider=lambda: now,
        sleep_fn=lambda _seconds: None,
        auth_factory=lambda _root: _Auth(),
    )

    result = supervisor.run()

    checkpoint_path = config.state_root / f"{result.session_id.replace(':', '_')}.checkpoint.json"
    snapshot_path = config.dashboard_output_root / "api" / "snapshot.json"
    heartbeat_path = config.state_root / "heartbeat.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))

    assert result.final_state == "LATE_START_NO_NEW_ENTRY"
    assert checkpoint["late_start_mode"] is True
    assert snapshot["system"]["supervisor_mode"] == "INTERNAL_PAPER_LATE_START_NO_NEW_ENTRY"
    assert heartbeat["late_start_mode"] is True
    assert snapshot["system"]["fyers_market_data_authority"] == "READ_ONLY"
    assert snapshot["system"]["broker_order_authority"] == "NONE"


def test_supervisor_clears_stale_checkpoint_contract_pins_when_current_cycle_does_not_reselect_contracts(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    now = datetime(2026, 8, 4, 11, 45, tzinfo=IST)

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=now,
                status=BrokerSessionStatus.NETWORK_UNAVAILABLE,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    config = ContinuousSupervisorConfig(
        repo_root=tmp_path,
        registry_path=tmp_path / "config" / "internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        state_root=tmp_path / "tmp" / "tfis_supervisor_state",
        dashboard_output_root=tmp_path / "tmp" / "tfis_dashboard_v1",
        db_path=tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite",
        max_iterations=1,
        poll_seconds=0.01,
    )
    config.state_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = config.state_root / "NSE_2026-08-04_UNIFIED_INTERNAL_PAPER.checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "session_id": "NSE:2026-08-04:UNIFIED_INTERNAL_PAPER",
                "subscription_owner": {
                    "underlyings": {
                        "NSE:NIFTYBANK-INDEX": {"S21_BANKNIFTY_INTERNAL_PAPER_A": ["UNDERLYING_OBSERVATION"]},
                    },
                    "contracts": {
                        "BANKNIFTY24JAN47000CE": {"S21_BANKNIFTY_INTERNAL_PAPER_A": ["SELECTED_CONTRACT_PINNED"]},
                    },
                    "duplicate_provider_subscriptions": False,
                },
            }
        ),
        encoding="utf-8",
    )

    supervisor = UnifiedInternalPaperSupervisor(
        config,
        now_provider=lambda: now,
        sleep_fn=lambda _seconds: None,
        auth_factory=lambda _root: _Auth(),
    )

    supervisor.run()

    snapshot = json.loads((config.dashboard_output_root / "api" / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["analytics"]["subscription_owner"]["contracts"] == {}


def test_supervisor_started_before_open_does_not_flip_to_late_start_at_open_microseconds(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    current = {"value": datetime(2026, 8, 3, 9, 14, 59, 900000, tzinfo=IST)}

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=current["value"],
                status=BrokerSessionStatus.AUTHENTICATED,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    config = ContinuousSupervisorConfig(
        repo_root=tmp_path,
        registry_path=tmp_path / "config" / "internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        state_root=tmp_path / "tmp" / "tfis_supervisor_state",
        dashboard_output_root=tmp_path / "tmp" / "tfis_dashboard_v1",
        db_path=tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite",
        max_iterations=1,
        poll_seconds=0.01,
    )
    supervisor = UnifiedInternalPaperSupervisor(
        config,
        now_provider=lambda: current["value"],
        sleep_fn=lambda _seconds: None,
        auth_factory=lambda _root: _Auth(),
    )
    current["value"] = datetime(2026, 8, 3, 9, 15, 0, 176, tzinfo=IST)

    result = supervisor.run()

    checkpoint_path = config.state_root / f"{result.session_id.replace(':', '_')}.checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    heartbeat = json.loads((config.state_root / "heartbeat.json").read_text(encoding="utf-8"))

    assert result.final_state == "LIVE_OBSERVATION"
    assert checkpoint["late_start_mode"] is False
    assert checkpoint["session_started_at"] == "2026-08-03T09:14:59.900000+05:30"
    assert heartbeat["late_start_mode"] is False
    assert heartbeat["session_started_at"] == "2026-08-03T09:14:59.900000+05:30"


def test_supervisor_skips_no_change_snapshot_checkpoint_and_reports_within_intervals(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    now = datetime(2026, 8, 3, 9, 45, tzinfo=IST)

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=now,
                status=BrokerSessionStatus.NETWORK_UNAVAILABLE,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    config = ContinuousSupervisorConfig(
        repo_root=tmp_path,
        registry_path=tmp_path / "config" / "internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        state_root=tmp_path / "tmp" / "tfis_supervisor_state",
        dashboard_output_root=tmp_path / "tmp" / "tfis_dashboard_v1",
        db_path=tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite",
        max_iterations=2,
        poll_seconds=0.01,
    )
    supervisor = UnifiedInternalPaperSupervisor(
        config,
        now_provider=lambda: now,
        sleep_fn=lambda _seconds: None,
        auth_factory=lambda _root: _Auth(),
    )

    supervisor.run()

    second_cycle = supervisor._cycle_metrics_history[-1]["stage_metrics"]
    statuses = {item["stage"]: item["status"] for item in second_cycle}

    assert statuses["recovery_snapshot"] == "CACHED"
    assert statuses["dashboard_snapshot_write"] == "SKIPPED_NO_CHANGE"
    assert statuses["checkpoint_write"] == "SKIPPED_NO_CHANGE"
    assert statuses["sqlite_runtime_persistence"] == "SKIPPED_NO_CHANGE"
    assert statuses["live_supervisor_reports"] == "SKIPPED_NO_CHANGE"


def test_supervisor_reports_stopped_final_state_when_stop_signal_exists_before_cycle(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    now = datetime(2026, 8, 3, 9, 10, tzinfo=IST)

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=now,
                status=BrokerSessionStatus.AUTHENTICATED,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    config = ContinuousSupervisorConfig(
        repo_root=tmp_path,
        registry_path=tmp_path / "config" / "internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        state_root=tmp_path / "tmp" / "tfis_supervisor_state",
        dashboard_output_root=tmp_path / "tmp" / "tfis_dashboard_v1",
        db_path=tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite",
        max_iterations=1,
        poll_seconds=0.01,
    )
    config.state_root.mkdir(parents=True, exist_ok=True)
    (config.state_root / "continuous_unified_supervisor.stop").write_text("", encoding="utf-8")

    supervisor = UnifiedInternalPaperSupervisor(
        config,
        now_provider=lambda: now,
        sleep_fn=lambda _seconds: None,
        auth_factory=lambda _root: _Auth(),
    )

    result = supervisor.run()

    assert result.final_state == "STOPPED"


def test_supervisor_reports_stopped_final_state_after_until_time_boundary(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    times = [
        datetime(2026, 8, 3, 15, 29, 58, tzinfo=IST),
        datetime(2026, 8, 3, 15, 30, 1, tzinfo=IST),
        datetime(2026, 8, 3, 15, 30, 1, tzinfo=IST),
        datetime(2026, 8, 3, 15, 30, 1, tzinfo=IST),
    ]
    time_index = {"value": 0}

    def _now_provider() -> datetime:
        index = time_index["value"]
        if index < len(times) - 1:
            time_index["value"] = index + 1
        return times[index]

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=datetime(2026, 8, 3, 15, 29, 58, tzinfo=IST),
                status=BrokerSessionStatus.AUTHENTICATED,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    config = ContinuousSupervisorConfig(
        repo_root=tmp_path,
        registry_path=tmp_path / "config" / "internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        state_root=tmp_path / "tmp" / "tfis_supervisor_state",
        dashboard_output_root=tmp_path / "tmp" / "tfis_dashboard_v1",
        db_path=tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite",
        max_iterations=0,
        poll_seconds=0.01,
    )
    supervisor = UnifiedInternalPaperSupervisor(
        config,
        now_provider=_now_provider,
        sleep_fn=lambda _seconds: None,
        auth_factory=lambda _root: _Auth(),
    )

    result = supervisor.run()

    assert result.final_state == "STOPPED"
    summary = (config.report_dir / "continuous_supervisor_summary.md").read_text(encoding="utf-8")
    assert "Final State: `STOPPED`" in summary


def test_supervisor_summary_labels_stored_explicit_preflight_with_original_timestamp(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    now = datetime(2026, 8, 3, 9, 45, tzinfo=IST)
    report_dir = tmp_path / "reports" / "live_supervisor"
    (report_dir / "complete_session_preflight.json").write_text(
        json.dumps(
            {
                "schema_version": "tfis.live_supervisor.complete_session_preflight.v1",
                "captured_at": "2026-08-03T08:50:00+05:30",
                "verdict": "READY_FOR_COMPLETE_UNIFIED_SESSION",
                "reasons": [],
            }
        ),
        encoding="utf-8",
    )

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=now,
                status=BrokerSessionStatus.NETWORK_UNAVAILABLE,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    config = ContinuousSupervisorConfig(
        repo_root=tmp_path,
        registry_path=tmp_path / "config" / "internal_paper_strategy_instances.yaml",
        report_dir=report_dir,
        state_root=tmp_path / "tmp" / "tfis_supervisor_state",
        dashboard_output_root=tmp_path / "tmp" / "tfis_dashboard_v1",
        db_path=tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite",
        max_iterations=1,
        poll_seconds=0.01,
    )
    supervisor = UnifiedInternalPaperSupervisor(
        config,
        now_provider=lambda: now,
        sleep_fn=lambda _seconds: None,
        auth_factory=lambda _root: _Auth(),
    )

    supervisor.run()

    summary = (report_dir / "continuous_supervisor_summary.md").read_text(encoding="utf-8")
    preflight = json.loads((report_dir / "complete_session_preflight.json").read_text(encoding="utf-8"))

    assert "Stored Explicit Preflight" in summary
    assert "2026-08-03T08:50:00+05:30" in summary
    assert preflight["captured_at"] == "2026-08-03T08:50:00+05:30"
    assert preflight["source"] == "STORED_EXPLICIT_PREFLIGHT_REPORT"
    assert preflight["reported_at"] == now.isoformat()


def test_supervisor_auth_retries_with_canonical_refresh_after_ready_preflight(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    now = datetime(2026, 8, 4, 8, 23, tzinfo=IST)
    report_dir = tmp_path / "reports" / "live_supervisor"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "complete_session_preflight.json").write_text(
        json.dumps(
            {
                "schema_version": "tfis.live_supervisor.complete_session_preflight.v1",
                "captured_at": "2026-08-04T08:21:29.058659+05:30",
                "verdict": "READY_FOR_COMPLETE_UNIFIED_SESSION",
                "reasons": [],
                "session_id": "NSE:2026-08-04:UNIFIED_INTERNAL_PAPER",
            }
        ),
        encoding="utf-8",
    )

    class _Auth:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            self.calls.append(allow_refresh)
            if not allow_refresh:
                return BrokerAuthenticationResult(
                    broker="fyers",
                    logical_account_ref="test",
                    environment="local",
                    observed_at=now,
                    status=BrokerSessionStatus.SESSION_VALIDATION_FAILED,
                    credential_reference=BrokerCredentialReference(
                        source_type="LOCAL_TOKEN_STORE",
                        path="data/token_store.json",
                        schema="json.access_token",
                        ignored_by_git=True,
                    ),
                )
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=now,
                status=BrokerSessionStatus.AUTHENTICATED,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    auth = _Auth()
    config = ContinuousSupervisorConfig(
        repo_root=tmp_path,
        registry_path=tmp_path / "config" / "internal_paper_strategy_instances.yaml",
        report_dir=report_dir,
        state_root=tmp_path / "tmp" / "tfis_supervisor_state",
        dashboard_output_root=tmp_path / "tmp" / "tfis_dashboard_v1",
        db_path=tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite",
        max_iterations=1,
        poll_seconds=0.01,
    )
    supervisor = UnifiedInternalPaperSupervisor(
        config,
        now_provider=lambda: now,
        sleep_fn=lambda _seconds: None,
        auth_factory=lambda _root: auth,
    )

    result = supervisor.run()
    payload = json.loads((report_dir / "performance_metrics.json").read_text(encoding="utf-8"))
    auth_metric = next(item for item in payload["current_cycle"]["stage_metrics"] if item["stage"] == "broker_authentication")

    assert result.final_state == "WAITING_FOR_MARKET"
    assert auth.calls == [False, True]
    assert auth_metric["details"]["status"] == "AUTHENTICATED"
    assert auth_metric["details"]["refresh_recovered"] is True


def test_authoritative_readiness_projection_prefers_live_preflight_and_runtime_gate(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    (tmp_path / "reports" / "dashboard_v1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports" / "runtime_performance").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports" / "live_supervisor").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tmp" / "tfis_supervisor_state").mkdir(parents=True, exist_ok=True)

    (tmp_path / "reports" / "dashboard_v1" / "market_session_readiness.json").write_text(
        json.dumps(
            {
                "schema_version": "tfis.dashboard_v1.market_session_readiness.v1",
                "readiness": "READY_FOR_UNIFIED_MARKET_SESSION",
                "verdict": "TFIS_RUNTIME_VALIDATION_ACCEPT",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "reports" / "runtime_performance" / "next_session_readiness.json").write_text(
        json.dumps(
            {
                "schema_version": "tfis.runtime_performance.next_session_readiness.v1",
                "verdict": "BLOCKED_BY_RUNTIME_CADENCE",
                "reasons": ["Cadence still unproven on fresh before-market-open session."],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "reports" / "live_supervisor" / "complete_session_preflight.json").write_text(
        json.dumps(
            {
                "schema_version": "tfis.live_supervisor.complete_session_preflight.v1",
                "captured_at": "2026-08-03T08:55:00+05:30",
                "verdict": "FAIL_CLOSED",
                "reasons": ["AUTHENTICATION_SESSION_VALIDATION_FAILED"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tmp" / "tfis_supervisor_state" / "heartbeat.json").write_text(
        json.dumps(
            {
                "session_id": "NSE:2026-08-03:UNIFIED_INTERNAL_PAPER",
                "state": "LIVE_OBSERVATION",
                "timestamp": "2026-08-03T12:37:23.064580+05:30",
                "late_start_mode": True,
            }
        ),
        encoding="utf-8",
    )

    result = build_authoritative_readiness_projection(
        repo_root=tmp_path,
        report_dir=tmp_path / "reports" / "unified_readiness",
        now_provider=lambda: datetime(2026, 8, 3, 12, 50, tzinfo=IST),
    )

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    package = json.loads(result.operator_package_json.read_text(encoding="utf-8"))

    assert result.verdict == "NO_GO_FOR_NEXT_COMPLETE_UNIFIED_SESSION"
    assert payload["go_for_next_complete_session"] is False
    assert "AUTHENTICATION_SESSION_VALIDATION_FAILED" in payload["blocking_reasons"]
    assert "Cadence still unproven on fresh before-market-open session." in payload["blocking_reasons"]
    assert "DETERMINISTIC_DASHBOARD_READINESS_IS_SUPPORTING_EVIDENCE_ONLY" in payload["warnings"]
    assert package["commands"][3]["name"] == "run_complete_session_preflight"
    assert payload["governing_inputs"]["dashboard_market_session_readiness"]["readiness"] == "READY_FOR_UNIFIED_MARKET_SESSION"


def test_collect_projection_labels_adds_supervisor_and_partial_capture_labels() -> None:
    projection = {
        "strategies": [
            {
                "state": {"evidence_quality": "FIXTURE_BACKED"},
                "plan": {"evidence_quality": "LIVE_FYERS_READ_ONLY_CAPTURE"},
                "execution": {"simulated_or_observed": "INTERNAL_PAPER_SIMULATED"},
            },
            {
                "state": {"evidence_quality": "DETERMINISTIC_TIMING_SUPPLEMENT"},
                "plan": {"evidence_quality": "MISSED_BEFORE_SUPERVISOR_START"},
                "execution": {"simulated_or_observed": "INTERNAL_PAPER_SIMULATED"},
            },
        ]
    }

    labels = _collect_projection_labels(projection)

    assert "LIVE_SUPERVISOR_OBSERVED" in labels
    assert "FYERS_METADATA_CAPTURED" in labels
    assert "PARTIAL_CAPTURE" in labels
    assert "COMPLETE_CAPTURE" not in labels
    assert _projection_meets_required_labels(projection) is True


def test_supervisor_performance_report_includes_current_cycle_metrics(tmp_path: Path) -> None:
    _write_test_repo_files(tmp_path)
    now = datetime(2026, 8, 3, 9, 45, tzinfo=IST)

    class _Auth:
        def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
            return BrokerAuthenticationResult(
                broker="fyers",
                logical_account_ref="test",
                environment="local",
                observed_at=now,
                status=BrokerSessionStatus.NETWORK_UNAVAILABLE,
                credential_reference=BrokerCredentialReference(
                    source_type="LOCAL_TOKEN_STORE",
                    path="data/token_store.json",
                    schema="json.access_token",
                    ignored_by_git=True,
                ),
            )

    config = ContinuousSupervisorConfig(
        repo_root=tmp_path,
        registry_path=tmp_path / "config" / "internal_paper_strategy_instances.yaml",
        report_dir=tmp_path / "reports" / "live_supervisor",
        state_root=tmp_path / "tmp" / "tfis_supervisor_state",
        dashboard_output_root=tmp_path / "tmp" / "tfis_dashboard_v1",
        db_path=tmp_path / "data" / "internal_paper" / "unified_supervisor.sqlite",
        max_iterations=1,
        poll_seconds=0.01,
    )
    supervisor = UnifiedInternalPaperSupervisor(
        config,
        now_provider=lambda: now,
        sleep_fn=lambda _seconds: None,
        auth_factory=lambda _root: _Auth(),
    )

    supervisor.run()

    payload = json.loads((config.report_dir / "performance_metrics.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == "tfis.live_supervisor.performance_metrics.v2"
    assert payload["sample_count"] == 1
    assert payload["current_cycle"]["iteration"] == 1
    assert payload["current_cycle"]["final_state"] == "LATE_START_NO_NEW_ENTRY"
    assert payload["cycle_duration_ms"]["maximum"] >= payload["cycle_duration_ms"]["minimum"]


def _write_test_repo_files(root: Path, *, include_snapshot: bool = True) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "tmp" / "tfis_dashboard_v1" / "api").mkdir(parents=True, exist_ok=True)
    (root / "reports" / "live_supervisor").mkdir(parents=True, exist_ok=True)
    (root / "data" / "internal_paper").mkdir(parents=True, exist_ok=True)
    if include_snapshot:
        (root / "tmp" / "tfis_dashboard_v1" / "api" / "snapshot.json").write_text(
            json.dumps(
                {
                    "projection_hash": "bootstrap",
                    "system": {"broker_order_authority": "NONE"},
                    "command_centre": {"system_state": "HEALTHY"},
                }
            ),
            encoding="utf-8",
        )
    (root / "config" / "monthly_status_instruments.yaml").write_text(
        "\n".join(
            (
                "instruments:",
                "  NIFTY:",
                "    spot_symbol: NSE:NIFTY50-INDEX",
                "  BANKNIFTY:",
                "    spot_symbol: NSE:NIFTYBANK-INDEX",
            )
        ),
        encoding="utf-8",
    )
    (root / "config" / "internal_paper_strategy_instances.yaml").write_text(
        "\n".join(
            (
                "schema_version: tfis.enabled_strategy_instances.v1",
                "session_scope:",
                "  trading_session_id: NSE:2026-08-03:INTERNAL_PAPER",
                "  timezone: Asia/Calcutta",
                "  authority_mode: INTERNAL_PAPER_CONTROLLED",
                "accounts:",
                "  - account_reference: INTERNAL_PAPER_ACCOUNT_A",
                "risk:",
                "  maximum_new_entries_per_session: 3",
                "  maximum_concurrent_positions: 3",
                "  maximum_account_margin_usage_pct: 70",
                "  aggregate_option_selling_exposure: 3",
                "  daily_loss_limit: 50000",
                "  global_halt: false",
                "instances:",
                "  - strategy_definition_id: S21_BANKNIFTY_OP_SELL_MONTHLY",
                "    strategy_version: s21.test.v1",
                "    strategy_instance_id: S21_BANKNIFTY_INTERNAL_PAPER_A",
                "    account_reference: INTERNAL_PAPER_ACCOUNT_A",
                "    underlying:",
                "      exchange: NSE",
                "      symbol: BANKNIFTY",
                "      instrument_type: INDEX",
                "    product: OPTION_SELLING",
                "    enabled: true",
                "    configured_quantity:",
                "      lots: 1",
                "      lot_size: 15",
                "    authority_mode: INTERNAL_PAPER_CONTROLLED",
                "    market_data_source: CERTIFICATION_FIXTURE",
                "    rule_config_hash: cfg-s21",
                "    risk_allocation:",
                "      max_positions: 1",
                "      max_margin_usage_pct: 25",
                "    operator_approval_status: APPROVED_INTERNAL_PAPER",
                "    evidence_quality: FIXTURE_BACKED",
                "    source_reports: {}",
                "    deterministic_projection:",
                "      branch: BULL_CALL",
                "      selected_contract: BANKNIFTY24JAN47000CE",
                "      entry: '925.00'",
                "      target: '370.00'",
                "      original_sl: '1337.50'",
                "      monthly_status: BULL_CF",
                "      market_references: {}",
                "      expiry_candidates: []",
            )
        ),
        encoding="utf-8",
    )
