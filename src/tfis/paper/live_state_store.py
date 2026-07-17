from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class S23PaperLiveStateSettings:
    enabled: bool = False
    provider: str = "redis"
    namespace: str = "tfis"
    environment: str = "paper"
    strategy_id: str = "s23"
    ttl_hours: int = 168
    series_maxlen: int = 1000
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 1
    redis_password: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "S23PaperLiveStateSettings":
        root = data or {}
        storage = root.get("storage") if isinstance(root.get("storage"), dict) else {}
        live_state = storage.get("live_state") if isinstance(storage.get("live_state"), dict) else {}
        redis_cfg = storage.get("redis") if isinstance(storage.get("redis"), dict) else {}
        return cls(
            enabled=bool(live_state.get("enabled", False)),
            provider=str(live_state.get("provider", "redis")),
            namespace=str(live_state.get("namespace", "tfis")),
            environment=str(live_state.get("environment", "paper")),
            strategy_id=str(live_state.get("strategy_id", "s23")),
            ttl_hours=max(1, int(live_state.get("ttl_hours", 168) or 168)),
            series_maxlen=max(1, int(live_state.get("series_maxlen", 1000) or 1000)),
            redis_host=str(redis_cfg.get("host", "localhost")),
            redis_port=int(redis_cfg.get("port", 6379) or 6379),
            redis_db=int(redis_cfg.get("db", 1) or 1),
            redis_password=redis_cfg.get("password"),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "S23PaperLiveStateSettings":
        target = Path(path)
        if not target.exists():
            return cls()
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return cls()
        return cls.from_mapping(data)


class S23PaperLiveStateStore:
    def __init__(self, settings: S23PaperLiveStateSettings) -> None:
        self.settings = settings

    def mirror_position_state(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        raise NotImplementedError

    def mirror_trade_event(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        raise NotImplementedError

    def set_watch_heartbeat(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        raise NotImplementedError

    def acquire_trade_lock(
        self,
        *,
        trade_id: str,
        owner_id: str,
        ttl_seconds: int,
    ) -> bool:
        raise NotImplementedError

    def release_trade_lock(self, *, trade_id: str, owner_id: str) -> None:
        raise NotImplementedError

    def _key(self, session_date: date, kind: str, domain: str) -> str:
        return (
            f"{self.settings.namespace}:{self.settings.environment}:"
            f"session:{session_date.isoformat()}:strategy:{self.settings.strategy_id}:"
            f"{kind}:{domain}"
        )

    def _lock_key(self, trade_id: str) -> str:
        return (
            f"{self.settings.namespace}:{self.settings.environment}:"
            f"lock:{self.settings.strategy_id}:{trade_id}"
        )


class NullS23PaperLiveStateStore(S23PaperLiveStateStore):
    def __init__(self, settings: S23PaperLiveStateSettings | None = None) -> None:
        super().__init__(settings or S23PaperLiveStateSettings())

    def mirror_position_state(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        return None

    def mirror_trade_event(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        return None

    def set_watch_heartbeat(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        return None

    def acquire_trade_lock(
        self,
        *,
        trade_id: str,
        owner_id: str,
        ttl_seconds: int,
    ) -> bool:
        return True

    def release_trade_lock(self, *, trade_id: str, owner_id: str) -> None:
        return None


class InMemoryS23PaperLiveStateStore(S23PaperLiveStateStore):
    def __init__(self, settings: S23PaperLiveStateSettings | None = None) -> None:
        super().__init__(settings or S23PaperLiveStateSettings(enabled=True))
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.locks: dict[str, str] = {}

    def mirror_position_state(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        self.values[self._key(session_date, "state", f"open_position:{trade_id}")] = json.dumps(payload, sort_keys=True)
        self.values[self._key(session_date, "snapshot", "latest_trade_status")] = json.dumps(payload, sort_keys=True)

    def mirror_trade_event(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        key = self._key(session_date, "series", "trade_events")
        self.lists.setdefault(key, []).append(json.dumps(payload, sort_keys=True))
        self.lists[key] = self.lists[key][-self.settings.series_maxlen :]

    def set_watch_heartbeat(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        self.values[self._key(session_date, "watch", f"{trade_id}:heartbeat")] = json.dumps(payload, sort_keys=True)

    def acquire_trade_lock(
        self,
        *,
        trade_id: str,
        owner_id: str,
        ttl_seconds: int,
    ) -> bool:
        key = self._lock_key(trade_id)
        existing = self.locks.get(key)
        if existing and existing != owner_id:
            return False
        self.locks[key] = owner_id
        return True

    def release_trade_lock(self, *, trade_id: str, owner_id: str) -> None:
        key = self._lock_key(trade_id)
        if self.locks.get(key) == owner_id:
            self.locks.pop(key, None)


class RedisS23PaperLiveStateStore(S23PaperLiveStateStore):
    def __init__(self, settings: S23PaperLiveStateSettings) -> None:
        super().__init__(settings)
        import redis

        self._client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        self._ttl_seconds = max(1, settings.ttl_hours) * 3600
        self._client.ping()

    def mirror_position_state(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        rendered = json.dumps(self._normalize(payload), sort_keys=True)
        pipe = self._client.pipeline()
        pipe.set(self._key(session_date, "state", f"open_position:{trade_id}"), rendered, ex=self._ttl_seconds)
        pipe.set(self._key(session_date, "snapshot", "latest_trade_status"), rendered, ex=self._ttl_seconds)
        pipe.execute()

    def mirror_trade_event(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        key = self._key(session_date, "series", "trade_events")
        pipe = self._client.pipeline()
        pipe.rpush(key, json.dumps(self._normalize(payload), sort_keys=True))
        pipe.ltrim(key, -self.settings.series_maxlen, -1)
        pipe.expire(key, self._ttl_seconds)
        pipe.execute()

    def set_watch_heartbeat(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        self._client.set(
            self._key(session_date, "watch", f"{trade_id}:heartbeat"),
            json.dumps(self._normalize(payload), sort_keys=True),
            ex=self._ttl_seconds,
        )

    def acquire_trade_lock(
        self,
        *,
        trade_id: str,
        owner_id: str,
        ttl_seconds: int,
    ) -> bool:
        key = self._lock_key(trade_id)
        ttl = max(1, ttl_seconds)
        if self._client.set(key, owner_id, nx=True, ex=ttl):
            return True
        if self._client.get(key) == owner_id:
            self._client.expire(key, ttl)
            return True
        return False

    def release_trade_lock(self, *, trade_id: str, owner_id: str) -> None:
        key = self._lock_key(trade_id)
        if self._client.get(key) == owner_id:
            self._client.delete(key)

    @staticmethod
    def _normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): RedisS23PaperLiveStateStore._normalize(val) for key, val in value.items()}
        if isinstance(value, tuple | list):
            return [RedisS23PaperLiveStateStore._normalize(item) for item in value]
        if isinstance(value, datetime | date):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value


def build_s23_paper_live_state_store(
    settings: S23PaperLiveStateSettings,
) -> S23PaperLiveStateStore:
    if not settings.enabled:
        return NullS23PaperLiveStateStore(settings)
    if settings.namespace.lower().startswith("nte"):
        raise ValueError(
            "TFIS live-state namespace must not use TradingEngineProd prefixes such as nte/nte_money/nte_dev"
        )
    if settings.provider.lower() != "redis":
        return NullS23PaperLiveStateStore(settings)
    try:
        return RedisS23PaperLiveStateStore(settings)
    except Exception:
        return NullS23PaperLiveStateStore(settings)


def build_s23_paper_live_state_store_from_yaml(path: str | Path) -> S23PaperLiveStateStore:
    return build_s23_paper_live_state_store(S23PaperLiveStateSettings.from_yaml(path))


def s23_live_state_owner_id(prefix: str = "tfis-s23-paper-watch") -> str:
    return f"{prefix}:{os.getpid()}"


PaperLiveStateSettings = S23PaperLiveStateSettings
PaperLiveStateStore = S23PaperLiveStateStore
InMemoryPaperLiveStateStore = InMemoryS23PaperLiveStateStore
NullPaperLiveStateStore = NullS23PaperLiveStateStore
RedisPaperLiveStateStore = RedisS23PaperLiveStateStore


def build_paper_live_state_store(settings: PaperLiveStateSettings) -> PaperLiveStateStore:
    return build_s23_paper_live_state_store(settings)


def build_paper_live_state_store_from_yaml(path: str | Path) -> PaperLiveStateStore:
    return build_s23_paper_live_state_store_from_yaml(path)


def paper_live_state_owner_id(prefix: str = "tfis-paper-watch") -> str:
    return s23_live_state_owner_id(prefix)


__all__ = [
    "InMemoryS23PaperLiveStateStore",
    "NullS23PaperLiveStateStore",
    "RedisS23PaperLiveStateStore",
    "S23PaperLiveStateSettings",
    "S23PaperLiveStateStore",
    "build_s23_paper_live_state_store",
    "build_s23_paper_live_state_store_from_yaml",
    "s23_live_state_owner_id",
    "PaperLiveStateSettings",
    "PaperLiveStateStore",
    "InMemoryPaperLiveStateStore",
    "NullPaperLiveStateStore",
    "RedisPaperLiveStateStore",
    "build_paper_live_state_store",
    "build_paper_live_state_store_from_yaml",
    "paper_live_state_owner_id",
]
