from __future__ import annotations

import json
import os
from hashlib import sha256
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class S23PaperLiveStateSettings:
    enabled: bool = False
    provider: str = "redis"
    root: str = "tmp/live_state"
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
            root=str(live_state.get("root", "tmp/live_state")),
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
        settings = cls.from_mapping(data)
        root_path = Path(settings.root)
        if not root_path.is_absolute():
            root_path = (target.parent / root_path).resolve()
        return cls(
            enabled=settings.enabled,
            provider=settings.provider,
            root=str(root_path),
            namespace=settings.namespace,
            environment=settings.environment,
            strategy_id=settings.strategy_id,
            ttl_hours=settings.ttl_hours,
            series_maxlen=settings.series_maxlen,
            redis_host=settings.redis_host,
            redis_port=settings.redis_port,
            redis_db=settings.redis_db,
            redis_password=settings.redis_password,
        )


@dataclass(frozen=True, slots=True)
class S23PaperLiveStateStoreDiagnostics:
    enabled: bool
    provider: str
    backend: str
    status: str
    message: str
    exception_type: str | None = None


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


class FilesystemS23PaperLiveStateStore(S23PaperLiveStateStore):
    def __init__(self, settings: S23PaperLiveStateSettings) -> None:
        super().__init__(settings)
        self._root = Path(settings.root)
        self._root.mkdir(parents=True, exist_ok=True)

    def mirror_position_state(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        rendered = json.dumps(self._normalize(payload), sort_keys=True)
        self._write_text(
            self._value_path(self._key(session_date, "state", f"open_position:{trade_id}")),
            rendered,
        )
        self._write_text(
            self._value_path(self._key(session_date, "snapshot", "latest_trade_status")),
            rendered,
        )

    def mirror_trade_event(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        key = self._key(session_date, "series", "trade_events")
        path = self._series_path(key)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = existing.splitlines()
        lines.append(json.dumps(self._normalize(payload), sort_keys=True))
        lines = lines[-self.settings.series_maxlen :]
        self._write_text(path, "\n".join(lines) + "\n")

    def set_watch_heartbeat(
        self,
        *,
        session_date: date,
        trade_id: str,
        payload: dict[str, Any],
    ) -> None:
        self._write_text(
            self._value_path(self._key(session_date, "watch", f"{trade_id}:heartbeat")),
            json.dumps(self._normalize(payload), sort_keys=True),
        )

    def acquire_trade_lock(
        self,
        *,
        trade_id: str,
        owner_id: str,
        ttl_seconds: int,
    ) -> bool:
        ttl = max(1, ttl_seconds)
        path = self._lock_path(self._lock_key(trade_id))
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl)
        payload = {
            "trade_id": trade_id,
            "owner_id": owner_id,
            "acquired_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        existing = self._read_json(path)
        if isinstance(existing, dict):
            existing_owner = str(existing.get("owner_id") or "").strip()
            if existing_owner == owner_id:
                self._write_text(path, json.dumps(payload, sort_keys=True))
                return True
            if not self._lock_is_expired(existing, now=now):
                return False
            try:
                path.unlink()
            except FileNotFoundError:
                pass

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        return True

    def release_trade_lock(self, *, trade_id: str, owner_id: str) -> None:
        path = self._lock_path(self._lock_key(trade_id))
        existing = self._read_json(path)
        if isinstance(existing, dict) and str(existing.get("owner_id") or "").strip() == owner_id:
            try:
                path.unlink()
            except FileNotFoundError:
                return

    def _value_path(self, key: str) -> Path:
        return self._root / "values" / f"{self._key_digest(key)}.json"

    def _series_path(self, key: str) -> Path:
        return self._root / "series" / f"{self._key_digest(key)}.jsonl"

    def _lock_path(self, key: str) -> Path:
        return self._root / "locks" / f"{self._key_digest(key)}.json"

    @staticmethod
    def _key_digest(key: str) -> str:
        return sha256(key.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): FilesystemS23PaperLiveStateStore._normalize(val) for key, val in value.items()}
        if isinstance(value, tuple | list):
            return [FilesystemS23PaperLiveStateStore._normalize(item) for item in value]
        if isinstance(value, datetime | date):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value

    @staticmethod
    def _lock_is_expired(payload: dict[str, Any], *, now: datetime) -> bool:
        raw = str(payload.get("expires_at") or "").strip()
        if not raw:
            return True
        try:
            return datetime.fromisoformat(raw) <= now
        except ValueError:
            return True

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.parent / f".{path.name}.tmp"
        try:
            temp_path.write_text(content, encoding="utf-8", newline="\n")
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def inspect_s23_paper_live_state_store(
    settings: S23PaperLiveStateSettings,
) -> S23PaperLiveStateStoreDiagnostics:
    if not settings.enabled:
        return S23PaperLiveStateStoreDiagnostics(
            enabled=False,
            provider=settings.provider,
            backend="null",
            status="PASS",
            message="Live-state mirroring is disabled by configuration.",
        )
    if settings.namespace.lower().startswith("nte"):
        return S23PaperLiveStateStoreDiagnostics(
            enabled=True,
            provider=settings.provider,
            backend="null",
            status="FAIL",
            message=(
                "TFIS live-state namespace must not use TradingEngineProd prefixes "
                "such as nte/nte_money/nte_dev."
            ),
        )
    if settings.provider.lower() != "redis":
        if settings.provider.lower() in {"filesystem", "file", "local"}:
            try:
                root = Path(settings.root)
                root.mkdir(parents=True, exist_ok=True)
                probe_path = root / ".healthcheck.tmp"
                probe_path.write_text("ok\n", encoding="utf-8")
                probe_path.unlink(missing_ok=True)
            except Exception as exc:
                return S23PaperLiveStateStoreDiagnostics(
                    enabled=True,
                    provider=settings.provider,
                    backend="null",
                    status="FAIL",
                    message=(
                        "Configured TFIS live-state storage is unavailable: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    exception_type=type(exc).__name__,
                )
            return S23PaperLiveStateStoreDiagnostics(
                enabled=True,
                provider=settings.provider,
                backend="filesystem",
                status="PASS",
                message=f"Live-state provider '{settings.provider}' is ready under {root}.",
            )
        return S23PaperLiveStateStoreDiagnostics(
            enabled=True,
            provider=settings.provider,
            backend="null",
            status="FAIL",
            message=(
                f"Unsupported TFIS live-state provider '{settings.provider}'. "
                "Configured live-state storage must resolve to a supported backend."
            ),
        )
    try:
        RedisS23PaperLiveStateStore(settings)
    except Exception as exc:
        return S23PaperLiveStateStoreDiagnostics(
            enabled=True,
            provider=settings.provider,
            backend="null",
            status="FAIL",
            message=(
                "Configured TFIS live-state storage is unavailable: "
                f"{type(exc).__name__}: {exc}"
            ),
            exception_type=type(exc).__name__,
        )
    return S23PaperLiveStateStoreDiagnostics(
        enabled=True,
        provider=settings.provider,
        backend="redis",
        status="PASS",
        message=(
            f"Live-state provider '{settings.provider}' is reachable at "
            f"{settings.redis_host}:{settings.redis_port}/{settings.redis_db}."
        ),
    )


def inspect_s23_paper_live_state_store_from_yaml(
    path: str | Path,
) -> S23PaperLiveStateStoreDiagnostics:
    return inspect_s23_paper_live_state_store(S23PaperLiveStateSettings.from_yaml(path))


def build_s23_paper_live_state_store(
    settings: S23PaperLiveStateSettings,
    *,
    strict: bool = False,
) -> S23PaperLiveStateStore:
    if settings.enabled and settings.namespace.lower().startswith("nte"):
        raise ValueError(
            "TFIS live-state namespace must not use TradingEngineProd prefixes such as "
            "nte/nte_money/nte_dev."
        )
    diagnostics = inspect_s23_paper_live_state_store(settings)
    if diagnostics.status != "PASS":
        if strict:
            raise RuntimeError(diagnostics.message)
        return NullS23PaperLiveStateStore(settings)
    if diagnostics.backend == "redis":
        return RedisS23PaperLiveStateStore(settings)
    if diagnostics.backend == "filesystem":
        return FilesystemS23PaperLiveStateStore(settings)
    return NullS23PaperLiveStateStore(settings)


def build_s23_paper_live_state_store_from_yaml(
    path: str | Path,
    *,
    strict: bool = False,
) -> S23PaperLiveStateStore:
    return build_s23_paper_live_state_store(
        S23PaperLiveStateSettings.from_yaml(path),
        strict=strict,
    )


def s23_live_state_owner_id(prefix: str = "tfis-s23-paper-watch") -> str:
    return f"{prefix}:{os.getpid()}"


PaperLiveStateSettings = S23PaperLiveStateSettings
PaperLiveStateStore = S23PaperLiveStateStore
PaperLiveStateStoreDiagnostics = S23PaperLiveStateStoreDiagnostics
InMemoryPaperLiveStateStore = InMemoryS23PaperLiveStateStore
FilesystemPaperLiveStateStore = FilesystemS23PaperLiveStateStore
NullPaperLiveStateStore = NullS23PaperLiveStateStore
RedisPaperLiveStateStore = RedisS23PaperLiveStateStore


def build_paper_live_state_store(
    settings: PaperLiveStateSettings,
    *,
    strict: bool = False,
) -> PaperLiveStateStore:
    return build_s23_paper_live_state_store(settings, strict=strict)


def inspect_paper_live_state_store(
    settings: PaperLiveStateSettings,
) -> PaperLiveStateStoreDiagnostics:
    return inspect_s23_paper_live_state_store(settings)


def inspect_paper_live_state_store_from_yaml(
    path: str | Path,
) -> PaperLiveStateStoreDiagnostics:
    return inspect_s23_paper_live_state_store_from_yaml(path)


def build_paper_live_state_store_from_yaml(
    path: str | Path,
    *,
    strict: bool = False,
) -> PaperLiveStateStore:
    return build_s23_paper_live_state_store_from_yaml(path, strict=strict)


def paper_live_state_owner_id(prefix: str = "tfis-paper-watch") -> str:
    return s23_live_state_owner_id(prefix)


__all__ = [
    "InMemoryS23PaperLiveStateStore",
    "NullS23PaperLiveStateStore",
    "RedisS23PaperLiveStateStore",
    "FilesystemS23PaperLiveStateStore",
    "S23PaperLiveStateSettings",
    "S23PaperLiveStateStore",
    "S23PaperLiveStateStoreDiagnostics",
    "build_s23_paper_live_state_store",
    "build_s23_paper_live_state_store_from_yaml",
    "inspect_s23_paper_live_state_store",
    "inspect_s23_paper_live_state_store_from_yaml",
    "s23_live_state_owner_id",
    "PaperLiveStateSettings",
    "PaperLiveStateStore",
    "PaperLiveStateStoreDiagnostics",
    "InMemoryPaperLiveStateStore",
    "FilesystemPaperLiveStateStore",
    "NullPaperLiveStateStore",
    "RedisPaperLiveStateStore",
    "build_paper_live_state_store",
    "build_paper_live_state_store_from_yaml",
    "inspect_paper_live_state_store",
    "inspect_paper_live_state_store_from_yaml",
    "paper_live_state_owner_id",
]
