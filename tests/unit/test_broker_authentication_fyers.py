from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tfis.broker.authentication import BrokerSessionStatus
from tfis.broker.authentication.fyers import FyersAuthenticationAdapter
from tfis.brokers.fyers_token import FyersPreparedEnvironment


NOW = datetime(2026, 8, 2, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


class FakeClient:
    def __init__(self, payload=None, exc: Exception | None = None) -> None:
        self.payload = payload or {"s": "ok", "data": {"name": "fixture"}}
        self.exc = exc

    def get_profile(self):
        if self.exc:
            raise self.exc
        return self.payload


def _write_env(root: Path, *, full: bool = False) -> None:
    lines = ["FYERS_APP_ID=TESTAPP-100", "FYERS_CLIENT_ID=CLIENT123"]
    if full:
        lines.extend(
            [
                "FYERS_APP_SECRET=APPSECRET",
                "FYERS_PIN=1234",
                "FYERS_TOTP_SECRET=JBSWY3DPEHPK3PXP",
            ]
        )
    (root / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_token(root: Path, payload: dict) -> None:
    path = root / "data" / "token_store.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_gitignore(root: Path) -> None:
    (root / ".gitignore").write_text("data/token_store.json\n", encoding="utf-8")


def test_token_missing_maps_to_specific_failure_without_refresh(tmp_path: Path) -> None:
    _write_env(tmp_path)
    _write_gitignore(tmp_path)
    _write_token(tmp_path, {})
    adapter = FyersAuthenticationAdapter(tfis_root=tmp_path, now_provider=lambda: NOW)

    result = adapter.authenticate(allow_refresh=False)

    assert result.status == BrokerSessionStatus.TOKEN_MISSING
    assert result.credential_reference.ignored_by_git is True
    assert result.failure is not None
    assert "fyers_token_refresh.py --prepare" in result.failure.operator_action_required


def test_allow_refresh_reuses_canonical_prepare_and_validates_session(tmp_path: Path, monkeypatch) -> None:
    _write_env(tmp_path)
    _write_gitignore(tmp_path)
    calls: list[tuple[str, bool]] = []

    def fake_prepare(*, tfis_root, skip_refresh):
        calls.append((str(tfis_root), skip_refresh))
        monkeypatch.setenv("FYERS_ACCESS_TOKEN", "fresh-token")
        return FyersPreparedEnvironment(
            app_id="TESTAPP-100",
            client_id="CLIENT123",
            token_store=tmp_path / "data" / "token_store.json",
            refreshed=True,
        )

    adapter = FyersAuthenticationAdapter(
        tfis_root=tmp_path,
        now_provider=lambda: NOW,
        prepare_environment=fake_prepare,
        session_client_factory=lambda app_id, token: FakeClient(),
    )

    result = adapter.authenticate(allow_refresh=True)

    assert result.status == BrokerSessionStatus.AUTHENTICATED
    assert result.refreshed is True
    assert calls == [(str(tmp_path), False)]
    assert result.session is not None
    assert result.session.to_dict()["client"] == "REDACTED_SESSION_HANDLE"


def test_rejected_profile_maps_to_token_rejected(tmp_path: Path, monkeypatch) -> None:
    _write_env(tmp_path)
    _write_gitignore(tmp_path)
    _write_token(tmp_path, {"access_token": "bad-token"})

    def fake_prepare(*, tfis_root, skip_refresh):
        monkeypatch.setenv("FYERS_ACCESS_TOKEN", "bad-token")
        return FyersPreparedEnvironment("TESTAPP-100", "CLIENT123", tmp_path / "data" / "token_store.json", False)

    adapter = FyersAuthenticationAdapter(
        tfis_root=tmp_path,
        now_provider=lambda: NOW,
        prepare_environment=fake_prepare,
        session_client_factory=lambda app_id, token: FakeClient({"s": "error", "code": 401, "message": "unauthorized"}),
    )

    result = adapter.authenticate(allow_refresh=False)

    assert result.status == BrokerSessionStatus.TOKEN_REJECTED
    assert result.failure is not None
    assert "refresh" in result.failure.operator_action_required.lower()


def test_malformed_token_store_is_blocked_before_prepare(tmp_path: Path) -> None:
    _write_env(tmp_path)
    _write_gitignore(tmp_path)
    token_path = tmp_path / "data" / "token_store.json"
    token_path.parent.mkdir(parents=True)
    token_path.write_text("{bad-json", encoding="utf-8")
    adapter = FyersAuthenticationAdapter(tfis_root=tmp_path, now_provider=lambda: NOW)

    result = adapter.authenticate(allow_refresh=True)

    assert result.status == BrokerSessionStatus.TOKEN_SCHEMA_INVALID


def test_app_configuration_missing_is_distinct(tmp_path: Path) -> None:
    _write_gitignore(tmp_path)
    adapter = FyersAuthenticationAdapter(tfis_root=tmp_path, now_provider=lambda: NOW)

    result = adapter.authenticate()

    assert result.status == BrokerSessionStatus.APP_CONFIGURATION_MISSING


def test_network_failure_during_profile_validation_is_classified(tmp_path: Path, monkeypatch) -> None:
    _write_env(tmp_path)
    _write_gitignore(tmp_path)
    _write_token(tmp_path, {"access_token": "token"})

    def fake_prepare(*, tfis_root, skip_refresh):
        monkeypatch.setenv("FYERS_ACCESS_TOKEN", "token")
        return FyersPreparedEnvironment("TESTAPP-100", "CLIENT123", tmp_path / "data" / "token_store.json", False)

    adapter = FyersAuthenticationAdapter(
        tfis_root=tmp_path,
        now_provider=lambda: NOW,
        prepare_environment=fake_prepare,
        session_client_factory=lambda app_id, token: FakeClient(exc=TimeoutError("network timeout")),
    )

    result = adapter.authenticate()

    assert result.status == BrokerSessionStatus.NETWORK_UNAVAILABLE


def test_authentication_result_hash_and_dict_do_not_expose_token(tmp_path: Path, monkeypatch) -> None:
    _write_env(tmp_path)
    _write_gitignore(tmp_path)

    def fake_prepare(*, tfis_root, skip_refresh):
        monkeypatch.setenv("FYERS_ACCESS_TOKEN", "secret-token")
        return FyersPreparedEnvironment("TESTAPP-100", "CLIENT123", tmp_path / "data" / "token_store.json", False)

    adapter = FyersAuthenticationAdapter(
        tfis_root=tmp_path,
        now_provider=lambda: NOW,
        prepare_environment=fake_prepare,
        session_client_factory=lambda app_id, token: FakeClient({"s": "ok", "access_token": "secret-token"}),
    )

    rendered = json.dumps(adapter.authenticate(allow_refresh=True).to_dict(), sort_keys=True)

    assert "secret-token" not in rendered
    assert "REDACTED" in rendered
