from __future__ import annotations

import json
from pathlib import Path

from tfis.brokers import fyers_token


def test_prepare_fyers_env_from_tfis_uses_tfis_token_store(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    token_path = tmp_path / "data" / "token_store.json"
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
    token_path.parent.mkdir(parents=True)
    token_path.write_text(json.dumps({"access_token": "tfis-token"}), encoding="utf-8")
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
