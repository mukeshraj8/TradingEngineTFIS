from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tfis.broker.authentication import (
    BrokerAuthenticationResult,
    BrokerCredentialReference,
    BrokerSessionIdentity,
    BrokerSessionStatus,
    ValidatedBrokerSession,
    canonical_hash,
)
from tfis.broker.diagnostics import BrokerDiagnosticSnapshot, DiagnosticStatus
from tfis.broker.diagnostics.fyers import FyersDiagnosticProbeConfig, run_fyers_broker_diagnostic


NOW = datetime(2026, 8, 2, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


class FakeClient:
    def get_profile(self):
        return {"s": "ok"}

    def history(self, request):
        return {"s": "ok", "candles": [[1785527100, 100, 110, 90, 105, 1]]}

    def quotes(self, request):
        return {"s": "ok", "d": [{"n": request["symbols"], "v": {"lp": 100}}]}

    def optionchain(self, request):
        return {
            "s": "ok",
            "data": {
                "optionsChain": [
                    {"symbol": "NSE:RELIANCE26AUG3000CE", "expiry": "2026-08-27", "strike": "3000", "option_type": "CE"}
                ]
            },
        }


class FakeAuthAdapter:
    def __init__(self, result: BrokerAuthenticationResult) -> None:
        self._result = result
        self.credential_reference = result.credential_reference

    def authenticate(self, *, allow_refresh=False, validate_session=True):
        return self._result


def _credential_ref(tmp_path: Path) -> BrokerCredentialReference:
    return BrokerCredentialReference("LOCAL_TOKEN_STORE", str(tmp_path / "data" / "token_store.json"), "json.access_token", True)


def _auth_result(tmp_path: Path, *, status: BrokerSessionStatus = BrokerSessionStatus.AUTHENTICATED) -> BrokerAuthenticationResult:
    credential = _credential_ref(tmp_path)
    identity = BrokerSessionIdentity(
        broker="fyers",
        logical_account_ref="acct",
        environment="test",
        app_id_prefix="TESTAPP",
        client_id_fingerprint="abc123",
        credential_reference=credential,
        authenticated_at=NOW,
        expires_at=None,
        identity_hash=canonical_hash({"broker": "fyers", "acct": "acct"}),
    )
    session = ValidatedBrokerSession(identity, FakeClient(), {"s": "ok"}) if status == BrokerSessionStatus.AUTHENTICATED else None
    return BrokerAuthenticationResult(
        broker="fyers",
        logical_account_ref="acct",
        environment="test",
        observed_at=NOW,
        status=status,
        credential_reference=credential,
        session_identity=identity if session else None,
        session=session,
    )


def test_configuration_only_diagnostic_does_not_authenticate(tmp_path: Path) -> None:
    snapshot = run_fyers_broker_diagnostic(
        logical_account_ref="acct",
        environment="test",
        configuration_only=True,
        auth_adapter=FakeAuthAdapter(_auth_result(tmp_path)),
    )

    assert snapshot.configuration_status == DiagnosticStatus.READY
    assert snapshot.order_write_status == DiagnosticStatus.NOT_AUTHORIZED
    assert snapshot.reference_data_status == DiagnosticStatus.NOT_CHECKED
    assert snapshot.blocking_reasons == ()


def test_authenticated_read_only_diagnostic_separates_write_authority(tmp_path: Path) -> None:
    snapshot = run_fyers_broker_diagnostic(
        logical_account_ref="acct",
        environment="test",
        auth_adapter=FakeAuthAdapter(_auth_result(tmp_path)),
        probe_config=FyersDiagnosticProbeConfig(check_historical_data=True, check_quote=True, check_option_chain=True),
    )

    assert snapshot.authentication_status == BrokerSessionStatus.AUTHENTICATED
    assert snapshot.historical_data_status == DiagnosticStatus.READABLE
    assert snapshot.quote_status == DiagnosticStatus.READABLE
    assert snapshot.option_chain_status == DiagnosticStatus.READABLE
    assert snapshot.order_write_status == DiagnosticStatus.NOT_AUTHORIZED


def test_authentication_failure_blocks_read_checks(tmp_path: Path) -> None:
    result = BrokerAuthenticationResult(
        broker="fyers",
        logical_account_ref="acct",
        environment="test",
        observed_at=NOW,
        status=BrokerSessionStatus.TOKEN_MISSING,
        credential_reference=_credential_ref(tmp_path),
    )

    snapshot = run_fyers_broker_diagnostic(auth_adapter=FakeAuthAdapter(result))

    assert snapshot.authentication_status == BrokerSessionStatus.TOKEN_MISSING
    assert snapshot.blocking_reasons == ("TOKEN_MISSING",)
    assert snapshot.order_write_status == DiagnosticStatus.NOT_AUTHORIZED


def test_diagnostic_hash_excludes_observed_at() -> None:
    first = BrokerDiagnosticSnapshot(
        broker="fyers",
        account_ref="acct",
        environment="test",
        observed_at=NOW,
        configuration_status=DiagnosticStatus.READY,
        credential_status=DiagnosticStatus.PRESENT,
        authentication_status=BrokerSessionStatus.AUTHENTICATED,
        session_expiry_status=DiagnosticStatus.NOT_CHECKED,
        reference_data_status=DiagnosticStatus.READABLE,
        historical_data_status=DiagnosticStatus.READABLE,
        quote_status=DiagnosticStatus.READABLE,
        option_chain_status=DiagnosticStatus.READABLE,
        account_read_status=DiagnosticStatus.NOT_CHECKED,
        order_write_status=DiagnosticStatus.NOT_AUTHORIZED,
        websocket_status=DiagnosticStatus.NOT_CHECKED,
        degraded_reasons=(),
        blocking_reasons=(),
        operator_action="NONE",
        evidence={"access_token": "secret-a"},
    )
    second = BrokerDiagnosticSnapshot(
        broker="fyers",
        account_ref="acct",
        environment="test",
        observed_at=NOW.replace(hour=12),
        configuration_status=DiagnosticStatus.READY,
        credential_status=DiagnosticStatus.PRESENT,
        authentication_status=BrokerSessionStatus.AUTHENTICATED,
        session_expiry_status=DiagnosticStatus.NOT_CHECKED,
        reference_data_status=DiagnosticStatus.READABLE,
        historical_data_status=DiagnosticStatus.READABLE,
        quote_status=DiagnosticStatus.READABLE,
        option_chain_status=DiagnosticStatus.READABLE,
        account_read_status=DiagnosticStatus.NOT_CHECKED,
        order_write_status=DiagnosticStatus.NOT_AUTHORIZED,
        websocket_status=DiagnosticStatus.NOT_CHECKED,
        degraded_reasons=(),
        blocking_reasons=(),
        operator_action="NONE",
        evidence={"access_token": "secret-b"},
    )

    assert first.diagnostic_hash == second.diagnostic_hash
    assert "secret" not in str(first.to_dict()).lower()
