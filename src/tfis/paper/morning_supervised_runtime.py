from __future__ import annotations

import hashlib
from pathlib import Path


_MARKET_CLOSED_NO_CANDLE_MESSAGES = (
    "FYERS underlying history payload returned no candles",
    "No underlying history candles matched the requested TFIS session window",
)


def paper_morning_supervised_market_closed_no_action(*, code: str, message: str) -> bool:
    return code == "BROKER_SNAPSHOT_FAILED" and any(
        marker in message for marker in _MARKET_CLOSED_NO_CANDLE_MESSAGES
    )


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
]
