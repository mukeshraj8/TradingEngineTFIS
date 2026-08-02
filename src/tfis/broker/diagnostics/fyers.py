from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from tfis.broker.authentication import BrokerAuthenticationResult, BrokerSessionStatus
from tfis.broker.authentication.fyers import FyersAuthenticationAdapter
from tfis.broker.diagnostics.models import BrokerDiagnosticSnapshot, DiagnosticStatus, snapshot_from_authentication_result
from tfis.fyers_read_only import FyersReadOnlyAdapter, FyersReadOnlyStatus


@dataclass(frozen=True, slots=True)
class FyersDiagnosticProbeConfig:
    check_reference_data: bool = False
    check_historical_data: bool = False
    check_quote: bool = False
    check_option_chain: bool = False
    check_account_read: bool = False
    underlying_symbol: str = "NSE:RELIANCE-EQ"
    history_from: date | None = None
    history_to: date | None = None
    strike_count: int = 5


def run_fyers_broker_diagnostic(
    *,
    tfis_root: str | Path | None = None,
    logical_account_ref: str = "default",
    environment: str = "local",
    allow_refresh: bool = False,
    configuration_only: bool = False,
    probe_config: FyersDiagnosticProbeConfig | None = None,
    auth_adapter: FyersAuthenticationAdapter | None = None,
) -> BrokerDiagnosticSnapshot:
    adapter = auth_adapter or FyersAuthenticationAdapter(
        tfis_root=tfis_root,
        logical_account_ref=logical_account_ref,
        environment=environment,
    )
    if configuration_only:
        credential_ref = adapter.credential_reference
        return BrokerDiagnosticSnapshot(
            broker="fyers",
            account_ref=logical_account_ref,
            environment=environment,
            observed_at=datetime.now(),
            configuration_status=DiagnosticStatus.READY,
            credential_status=DiagnosticStatus.PRESENT if credential_ref.ignored_by_git is not False else DiagnosticStatus.DEGRADED,
            authentication_status=BrokerSessionStatus.SESSION_VALIDATION_FAILED,
            session_expiry_status=DiagnosticStatus.NOT_CHECKED,
            reference_data_status=DiagnosticStatus.NOT_CHECKED,
            historical_data_status=DiagnosticStatus.NOT_CHECKED,
            quote_status=DiagnosticStatus.NOT_CHECKED,
            option_chain_status=DiagnosticStatus.NOT_CHECKED,
            account_read_status=DiagnosticStatus.NOT_CHECKED,
            order_write_status=DiagnosticStatus.NOT_AUTHORIZED,
            websocket_status=DiagnosticStatus.NOT_CHECKED,
            degraded_reasons=(),
            blocking_reasons=(),
            operator_action="Run authentication diagnostic for session state.",
            evidence={"configuration_only": True, "credential_reference": credential_ref.to_dict()},
        )

    auth_result = adapter.authenticate(allow_refresh=allow_refresh, validate_session=True)
    if auth_result.status != BrokerSessionStatus.AUTHENTICATED or auth_result.session is None:
        return snapshot_from_authentication_result(auth_result, evidence={"read_checks_skipped": "authentication_not_valid"})

    probe = probe_config or FyersDiagnosticProbeConfig()
    read_adapter = FyersReadOnlyAdapter.from_validated_session(auth_result.session)
    statuses: dict[str, DiagnosticStatus] = {
        "reference": DiagnosticStatus.NOT_CHECKED,
        "history": DiagnosticStatus.NOT_CHECKED,
        "quote": DiagnosticStatus.NOT_CHECKED,
        "option_chain": DiagnosticStatus.NOT_CHECKED,
        "account": DiagnosticStatus.NOT_CHECKED,
    }
    evidence: dict[str, Any] = {"authentication": auth_result.to_dict()}
    if probe.check_reference_data:
        result = read_adapter.fetch_symbol_master("NSEFO")
        statuses["reference"] = _read_status(result.status)
        evidence["reference_data"] = {"status": result.status.value, "warnings": list(result.warnings)}
    if probe.check_historical_data:
        result = read_adapter.fetch_historical_candles(
            symbol=probe.underlying_symbol,
            resolution="D",
            range_from=probe.history_from or date.today(),
            range_to=probe.history_to or date.today(),
        )
        statuses["history"] = _read_status(result.status)
        evidence["historical_data"] = {"status": result.status.value, "warnings": list(result.warnings)}
    if probe.check_quote:
        result = read_adapter.fetch_quotes((probe.underlying_symbol,))
        statuses["quote"] = _read_status(result.status)
        evidence["quote"] = {"status": result.status.value, "warnings": list(result.warnings)}
    if probe.check_option_chain:
        result = read_adapter.fetch_option_chain(underlying=probe.underlying_symbol, strike_count=probe.strike_count)
        statuses["option_chain"] = _read_status(result.status)
        evidence["option_chain"] = {"status": result.status.value, "warnings": list(result.warnings)}
    if probe.check_account_read:
        statuses["account"] = DiagnosticStatus.NOT_CONFIGURED
    blocking = [key for key, status in statuses.items() if status in {DiagnosticStatus.FAILED, DiagnosticStatus.UNAVAILABLE}]
    snapshot = snapshot_from_authentication_result(
        auth_result,
        reference_data_status=statuses["reference"],
        historical_data_status=statuses["history"],
        quote_status=statuses["quote"],
        option_chain_status=statuses["option_chain"],
        account_read_status=statuses["account"],
        evidence=evidence,
    )
    if blocking:
        return BrokerDiagnosticSnapshot(
            broker=snapshot.broker,
            account_ref=snapshot.account_ref,
            environment=snapshot.environment,
            observed_at=snapshot.observed_at,
            configuration_status=snapshot.configuration_status,
            credential_status=snapshot.credential_status,
            authentication_status=snapshot.authentication_status,
            session_expiry_status=snapshot.session_expiry_status,
            reference_data_status=snapshot.reference_data_status,
            historical_data_status=snapshot.historical_data_status,
            quote_status=snapshot.quote_status,
            option_chain_status=snapshot.option_chain_status,
            account_read_status=snapshot.account_read_status,
            order_write_status=snapshot.order_write_status,
            websocket_status=snapshot.websocket_status,
            degraded_reasons=tuple(blocking),
            blocking_reasons=tuple(blocking),
            operator_action=snapshot.operator_action,
            evidence=evidence,
        )
    return snapshot


def _read_status(status: FyersReadOnlyStatus) -> DiagnosticStatus:
    if status == FyersReadOnlyStatus.SUCCESS:
        return DiagnosticStatus.READABLE
    if status in {FyersReadOnlyStatus.RATE_LIMITED, FyersReadOnlyStatus.TIMEOUT, FyersReadOnlyStatus.UNAVAILABLE}:
        return DiagnosticStatus.UNAVAILABLE
    return DiagnosticStatus.FAILED


__all__ = ["FyersDiagnosticProbeConfig", "run_fyers_broker_diagnostic"]
