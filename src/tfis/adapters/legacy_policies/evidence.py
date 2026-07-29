from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True, slots=True)
class SavedDecisionEvidence:
    path: Path
    captured: bool
    strategy_branch: str | None
    monthly_status: str | None
    trade_plan: dict[str, Any] | None
    orpt_snapshot: dict[str, Any] | None
    rc_snapshot: dict[str, Any] | None
    has_option_chain: bool


def load_saved_paper_prelude_evidence(path: str | Path) -> SavedDecisionEvidence:
    source = Path(path)
    monthly_status = None
    trade_plan = None
    orpt_snapshot = None
    rc_snapshot = None
    captured = False
    has_option_chain = False
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        payload = dict(event.get("payload") or {})
        captured = captured or not bool(event.get("synthetic_fixture", True))
        event_type = str(event.get("event_type") or "")
        if event_type == "MONTHLY_STATUS_INPUT":
            monthly_status = payload.get("monthly_status")
        elif event_type == "TRADE_PLAN_INPUT":
            trade_plan = payload
        elif event_type == "UNDERLYING_SNAPSHOT":
            label = str(payload.get("snapshot_label") or "").upper()
            if label == "ORPT":
                orpt_snapshot = payload
            elif label == "RC":
                rc_snapshot = payload
        elif event_type == "OPTION_CHAIN_SNAPSHOT":
            has_option_chain = True
    return SavedDecisionEvidence(
        path=source,
        captured=captured,
        strategy_branch=trade_plan.get("strategy_branch") if trade_plan else None,
        monthly_status=monthly_status,
        trade_plan=trade_plan,
        orpt_snapshot=orpt_snapshot,
        rc_snapshot=rc_snapshot,
        has_option_chain=has_option_chain,
    )
