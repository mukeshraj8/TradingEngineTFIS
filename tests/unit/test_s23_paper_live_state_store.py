from __future__ import annotations

import json
import sys
from datetime import date
from types import SimpleNamespace

import pytest

from tfis.paper import (
    FilesystemS23PaperLiveStateStore,
    InMemoryS23PaperLiveStateStore,
    NullS23PaperLiveStateStore,
    RedisS23PaperLiveStateStore,
    S23PaperLiveStateSettings,
    build_s23_paper_live_state_store,
    inspect_s23_paper_live_state_store,
)


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.ops = []

    def set(self, key, value, ex=None):
        self.ops.append(("set", key, value, ex))
        return self

    def rpush(self, key, value):
        self.ops.append(("rpush", key, value))
        return self

    def ltrim(self, key, start, end):
        self.ops.append(("ltrim", key, start, end))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))
        return self

    def execute(self):
        for op in self.ops:
            if op[0] == "set":
                _, key, value, ex = op
                self.client.set(key, value, ex=ex)
            elif op[0] == "rpush":
                _, key, value = op
                self.client.rpush(key, value)
            elif op[0] == "ltrim":
                _, key, start, end = op
                self.client.ltrim(key, start, end)
            elif op[0] == "expire":
                _, key, ttl = op
                self.client.expire(key, ttl)
        return True


class FakeRedis:
    last_instance = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.kv = {}
        self.lists = {}
        self.expiry = {}
        FakeRedis.last_instance = self

    def ping(self):
        return True

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        if ex is not None:
            self.expiry[key] = ex
        return True

    def get(self, key):
        return self.kv.get(key)

    def delete(self, key):
        self.kv.pop(key, None)

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def ltrim(self, key, start, end):
        values = self.lists.get(key, [])
        normalized_start = len(values) + start if start < 0 else start
        normalized_end = len(values) + end if end < 0 else end
        self.lists[key] = values[max(0, normalized_start) : normalized_end + 1]

    def lrange(self, key, start, end):
        return self.lists.get(key, [])[start : end + 1]

    def expire(self, key, ttl):
        self.expiry[key] = ttl

    def pipeline(self):
        return FakePipeline(self)


def _settings(**overrides) -> S23PaperLiveStateSettings:
    base = {
        "enabled": True,
        "provider": "redis",
        "root": "tmp/live_state",
        "namespace": "tfis",
        "environment": "paper",
        "strategy_id": "s23",
        "ttl_hours": 168,
        "series_maxlen": 3,
        "redis_host": "localhost",
        "redis_port": 6379,
        "redis_db": 1,
        "redis_password": None,
    }
    base.update(overrides)
    return S23PaperLiveStateSettings(**base)


def test_redis_live_state_uses_tfis_namespace_and_db(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=FakeRedis))
    store = RedisS23PaperLiveStateStore(_settings())

    store.mirror_position_state(
        session_date=date(2026, 6, 23),
        trade_id="trade-1",
        payload={"status": "OPEN"},
    )
    store.mirror_trade_event(
        session_date=date(2026, 6, 23),
        trade_id="trade-1",
        payload={"event": "OPEN"},
    )
    assert store.acquire_trade_lock(trade_id="trade-1", owner_id="owner-a", ttl_seconds=30) is True
    assert store.acquire_trade_lock(trade_id="trade-1", owner_id="owner-a", ttl_seconds=45) is True
    assert store.acquire_trade_lock(trade_id="trade-1", owner_id="owner-b", ttl_seconds=30) is False

    client = FakeRedis.last_instance
    assert client.kwargs["db"] == 1
    assert "tfis:paper:session:2026-06-23:strategy:s23:state:open_position:trade-1" in client.kv
    assert "tfis:paper:session:2026-06-23:strategy:s23:snapshot:latest_trade_status" in client.kv
    assert "tfis:paper:session:2026-06-23:strategy:s23:series:trade_events" in client.lists
    assert "tfis:paper:lock:s23:trade-1" in client.kv
    assert client.expiry["tfis:paper:lock:s23:trade-1"] == 45
    assert not any(key.startswith("nte") for key in [*client.kv.keys(), *client.lists.keys()])


def test_trading_engine_prod_namespace_is_rejected() -> None:
    with pytest.raises(ValueError, match="TradingEngineProd"):
        build_s23_paper_live_state_store(_settings(namespace="nte_money"))


def test_disabled_or_unavailable_redis_uses_null_store(monkeypatch) -> None:
    assert isinstance(
        build_s23_paper_live_state_store(_settings(enabled=False)),
        NullS23PaperLiveStateStore,
    )

    class BrokenRedis:
        def __init__(self, **kwargs):
            raise RuntimeError("redis unavailable")

    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=BrokenRedis))
    assert isinstance(build_s23_paper_live_state_store(_settings()), NullS23PaperLiveStateStore)


def test_live_state_diagnostics_fail_when_enabled_backend_is_unavailable(monkeypatch) -> None:
    class BrokenRedis:
        def __init__(self, **kwargs):
            raise RuntimeError("redis unavailable")

    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=BrokenRedis))
    diagnostics = inspect_s23_paper_live_state_store(_settings())

    assert diagnostics.status == "FAIL"
    assert diagnostics.backend == "null"
    assert diagnostics.exception_type == "RuntimeError"
    assert "unavailable" in diagnostics.message.lower()


def test_strict_live_state_build_raises_when_enabled_backend_is_unavailable(monkeypatch) -> None:
    class BrokenRedis:
        def __init__(self, **kwargs):
            raise RuntimeError("redis unavailable")

    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=BrokenRedis))

    with pytest.raises(RuntimeError, match="live-state storage is unavailable"):
        build_s23_paper_live_state_store(_settings(), strict=True)


def test_in_memory_live_state_uses_same_key_shape() -> None:
    store = InMemoryS23PaperLiveStateStore(_settings(provider="memory"))

    store.mirror_position_state(
        session_date=date(2026, 6, 23),
        trade_id="trade-2",
        payload={"status": "OPEN"},
    )

    raw = store.values["tfis:paper:session:2026-06-23:strategy:s23:state:open_position:trade-2"]
    assert json.loads(raw) == {"status": "OPEN"}


def test_filesystem_live_state_persists_values_and_locks(tmp_path) -> None:
    settings = _settings(provider="filesystem", root=str(tmp_path / "live_state"))
    store = build_s23_paper_live_state_store(settings, strict=True)

    assert isinstance(store, FilesystemS23PaperLiveStateStore)
    store.mirror_position_state(
        session_date=date(2026, 6, 23),
        trade_id="trade-3",
        payload={"status": "OPEN"},
    )
    store.mirror_trade_event(
        session_date=date(2026, 6, 23),
        trade_id="trade-3",
        payload={"status": "OPEN"},
    )
    assert store.acquire_trade_lock(trade_id="trade-3", owner_id="owner-a", ttl_seconds=30) is True
    assert store.acquire_trade_lock(trade_id="trade-3", owner_id="owner-b", ttl_seconds=30) is False
    store.release_trade_lock(trade_id="trade-3", owner_id="owner-a")
    assert store.acquire_trade_lock(trade_id="trade-3", owner_id="owner-b", ttl_seconds=30) is True

    files = list((tmp_path / "live_state").rglob("*"))
    assert any(path.name.endswith(".json") for path in files)
    assert any(path.name.endswith(".jsonl") for path in files)


def test_live_state_diagnostics_pass_for_filesystem_provider(tmp_path) -> None:
    diagnostics = inspect_s23_paper_live_state_store(
        _settings(provider="filesystem", root=str(tmp_path / "live_state"))
    )

    assert diagnostics.status == "PASS"
    assert diagnostics.backend == "filesystem"
