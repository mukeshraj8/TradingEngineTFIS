from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar


_MARKET_CLOSED_NO_CANDLE_MESSAGES = (
    "FYERS underlying history payload returned no candles",
    "No underlying history candles matched the requested TFIS session window",
)
_ResultT = TypeVar("_ResultT")


def paper_morning_supervised_market_closed_no_action(*, code: str, message: str) -> bool:
    return code == "BROKER_SNAPSHOT_FAILED" and any(
        marker in message for marker in _MARKET_CLOSED_NO_CANDLE_MESSAGES
    )


def run_paper_morning_supervised_decision_with_no_candle_retries(
    run_once: Callable[[], _ResultT],
    *,
    no_candle_retries: int,
    retry_delay_seconds: float,
    sleeper: Callable[[float], None] = time.sleep,
    retry_logger: Callable[[str], None] | None = None,
) -> _ResultT:
    retries = max(0, int(no_candle_retries))
    delay_seconds = max(0.0, float(retry_delay_seconds))
    attempt = 0
    while True:
        try:
            return run_once()
        except Exception as exc:
            code = getattr(exc, "code", "MORNING_SUPERVISED_DECISION_FAILED")
            is_no_candle = paper_morning_supervised_market_closed_no_action(
                code=code,
                message=str(exc),
            )
            if not is_no_candle or attempt >= retries:
                raise
            attempt += 1
            if retry_logger is not None:
                retry_logger(
                    "BROKER_SNAPSHOT_NO_CANDLES_RETRY: "
                    f"attempt={attempt} remaining={retries - attempt} "
                    f"delay_seconds={delay_seconds:g}"
                )
            if delay_seconds > 0:
                sleeper(delay_seconds)


def paper_morning_supervised_process_lock_path(
    *,
    artifact_root: Path,
    session_id_prefix: str,
    lock_root: Path,
    strategy_code: str,
) -> Path:
    identity = f"{artifact_root.resolve()}::{session_id_prefix}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    slug = strategy_code.strip().lower() or "paper"
    return lock_root / f"{slug}_supervised_decision_{digest}.pid.json"


__all__ = [
    "paper_morning_supervised_market_closed_no_action",
    "paper_morning_supervised_process_lock_path",
    "run_paper_morning_supervised_decision_with_no_candle_retries",
]
