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
from tfis.runtime.multi_strategy.supervisor import (
    ContinuousSupervisorConfig,
    SubscriptionOwner,
    UnifiedInternalPaperSupervisor,
    run_complete_session_preflight,
)


IST = ZoneInfo("Asia/Calcutta")


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


def _write_test_repo_files(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "tmp" / "tfis_dashboard_v1" / "api").mkdir(parents=True, exist_ok=True)
    (root / "reports" / "live_supervisor").mkdir(parents=True, exist_ok=True)
    (root / "data" / "internal_paper").mkdir(parents=True, exist_ok=True)
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
