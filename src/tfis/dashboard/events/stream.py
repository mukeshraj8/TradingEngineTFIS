from __future__ import annotations

import json
from typing import Any, Mapping


def build_sse_event_stream(projection: Mapping[str, Any], *, after_watermark: str | None = None) -> str:
    event = {
        "event_id": "event:snapshot-ready",
        "event_type": "SNAPSHOT_READY",
        "after_watermark": after_watermark,
        "projection_hash": projection["projection_hash"],
        "raw_tick_stream": False,
    }
    return "event: snapshot\n" + "data: " + json.dumps(event, sort_keys=True) + "\n\n"
