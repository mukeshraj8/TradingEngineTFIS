from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tfis.paper import live_decision_runner as module


def test_prepare_live_decision_runtime_environment_uses_shared_runtime_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_config = SimpleNamespace(
        broker=SimpleNamespace(provider="fyers", timezone="Asia/Kolkata"),
    )
    calls: list[tuple[object, object, bool]] = []

    monkeypatch.setattr(
        module.PaperLifecycleRuntimeConfig,
        "from_yaml",
        staticmethod(lambda path: runtime_config),
    )

    def _fake_prepare(config, *, tfis_root, skip_refresh):
        calls.append((config, tfis_root, skip_refresh))

    monkeypatch.setattr(module, "prepare_paper_broker_runtime_environment", _fake_prepare)

    module.prepare_live_decision_runtime_environment(
        tfis_root=tmp_path,
        config_path="config/paper.s23.fyers_connect_test.yaml",
        skip_refresh=True,
    )

    assert calls == [(runtime_config, tmp_path, True)]
