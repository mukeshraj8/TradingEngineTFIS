from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "fyers_token_refresh.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("fyers_token_refresh_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepare_mode_validates_or_refreshes_existing_token(tmp_path, monkeypatch, capsys) -> None:
    module = _load_script_module()
    calls: list[tuple[str, bool]] = []

    class _Prepared:
        refreshed = False
        token_store = tmp_path / "data" / "token_store.json"

    def _fake_prepare(*, tfis_root, skip_refresh):
        calls.append((str(tfis_root), skip_refresh))
        return _Prepared()

    monkeypatch.setattr(module, "prepare_fyers_env_from_tfis", _fake_prepare)

    exit_code = module.main(["--prepare", "--tfis-root", str(tmp_path)])

    assert exit_code == 0
    assert calls == [(str(tmp_path), False)]
    assert "FYERS token prepared: reused" in capsys.readouterr().out


def test_default_mode_still_forces_token_refresh(monkeypatch) -> None:
    module = _load_script_module()
    refresh_calls: list[str] = []

    def _fake_refresh():
        refresh_calls.append("refresh")

    monkeypatch.setattr(module, "refresh_fyers_token", _fake_refresh)

    exit_code = module.main([])

    assert exit_code == 0
    assert refresh_calls == ["refresh"]
