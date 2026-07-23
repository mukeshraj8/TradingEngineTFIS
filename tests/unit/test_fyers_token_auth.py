from __future__ import annotations

import json
from pathlib import Path

from tfis.brokers import fyers_token


def _write_env(path: Path) -> None:
    env_path = path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "FYERS_APP_ID=TESTAPP-100",
                "FYERS_CLIENT_ID=CLIENT123",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_token(path: Path, token: str) -> Path:
    token_path = path / "data" / "token_store.json"
    token_path.parent.mkdir(parents=True)
    token_path.write_text(json.dumps({"access_token": token}), encoding="utf-8")
    return token_path


def test_prepare_fyers_env_from_tfis_uses_tfis_token_store(tmp_path, monkeypatch) -> None:
    _write_env(tmp_path)
    token_path = _write_token(tmp_path, "tfis-token")
    verify_calls: list[str] = []

    def _fake_verify(*_args) -> None:
        verify_calls.append("verify")

    monkeypatch.setattr(fyers_token, "_verify_token", _fake_verify)
    monkeypatch.delenv("FYERS_APP_ID", raising=False)
    monkeypatch.delenv("FYERS_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FYERS_CLIENT_ID", raising=False)

    prepared = fyers_token.prepare_fyers_env_from_tfis(
        tfis_root=tmp_path,
        skip_refresh=True,
    )

    assert prepared.token_store == token_path
    assert prepared.refreshed is False
    assert prepared.app_id == "TESTAPP-100"
    assert prepared.client_id == "CLIENT123"
    assert fyers_token.default_token_paths(tmp_path).token_store == token_path
    assert verify_calls == []


def test_prepare_fyers_env_from_tfis_reuses_verified_existing_token(tmp_path, monkeypatch) -> None:
    _write_env(tmp_path)
    token_path = _write_token(tmp_path, "valid-token")
    verify_calls: list[tuple[str, str]] = []
    refresh_calls: list[str] = []

    def _fake_verify(_paths, access_token, app_id) -> None:
        verify_calls.append((access_token, app_id))

    def _fake_refresh(*, paths) -> Path:
        refresh_calls.append(str(paths.token_store))
        return paths.token_store

    monkeypatch.setattr(fyers_token, "_verify_token", _fake_verify)
    monkeypatch.setattr(fyers_token, "refresh_fyers_token", _fake_refresh)
    monkeypatch.delenv("FYERS_ACCESS_TOKEN", raising=False)

    prepared = fyers_token.prepare_fyers_env_from_tfis(
        tfis_root=tmp_path,
        skip_refresh=False,
    )

    assert prepared.token_store == token_path
    assert prepared.refreshed is False
    assert verify_calls == [("valid-token", "TESTAPP-100")]
    assert refresh_calls == []
    assert fyers_token.os.environ["FYERS_ACCESS_TOKEN"] == "valid-token"


def test_prepare_fyers_env_from_tfis_refreshes_only_when_existing_token_invalid(
    tmp_path,
    monkeypatch,
) -> None:
    _write_env(tmp_path)
    token_path = _write_token(tmp_path, "expired-token")
    verify_calls: list[str] = []
    refresh_calls: list[str] = []

    def _fake_verify(_paths, access_token, _app_id) -> None:
        verify_calls.append(access_token)
        if access_token == "expired-token":
            raise fyers_token.FyersTokenRefreshError("profile rejected token")

    def _fake_refresh(*, paths) -> Path:
        refresh_calls.append(str(paths.token_store))
        paths.token_store.write_text(
            json.dumps({"access_token": "fresh-token"}),
            encoding="utf-8",
        )
        return paths.token_store

    monkeypatch.setattr(fyers_token, "_verify_token", _fake_verify)
    monkeypatch.setattr(fyers_token, "refresh_fyers_token", _fake_refresh)
    monkeypatch.delenv("FYERS_ACCESS_TOKEN", raising=False)

    prepared = fyers_token.prepare_fyers_env_from_tfis(
        tfis_root=tmp_path,
        skip_refresh=False,
    )

    assert prepared.token_store == token_path
    assert prepared.refreshed is True
    assert refresh_calls == [str(token_path)]
    assert verify_calls == ["expired-token", "expired-token"]
    assert fyers_token.os.environ["FYERS_ACCESS_TOKEN"] == "fresh-token"


def test_refresh_token_if_needed_rechecks_token_inside_refresh_lock(
    tmp_path,
    monkeypatch,
) -> None:
    _write_env(tmp_path)
    token_path = _write_token(tmp_path, "token-refreshed-by-other-process")
    validity = iter([False, True])
    refresh_calls: list[str] = []

    def _fake_stored_token_is_valid(_paths, _access_token, _app_id) -> bool:
        return next(validity)

    def _fake_refresh(*, paths) -> Path:
        refresh_calls.append(str(paths.token_store))
        return paths.token_store

    monkeypatch.setattr(fyers_token, "_stored_token_is_valid", _fake_stored_token_is_valid)
    monkeypatch.setattr(fyers_token, "refresh_fyers_token", _fake_refresh)

    prepared = fyers_token.prepare_fyers_env_from_tfis(
        tfis_root=tmp_path,
        skip_refresh=False,
    )

    assert prepared.token_store == token_path
    assert prepared.refreshed is False
    assert refresh_calls == []
