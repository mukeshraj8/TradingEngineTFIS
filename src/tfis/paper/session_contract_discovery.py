from __future__ import annotations

import json
from pathlib import Path

from .decision_summary_discovery import discover_trade_decision_summary_symbols
from .order_state import (
    PaperOrderStateDiscovery,
    paper_order_state_candidate_paths,
)


def discover_session_contract_symbols(
    session_dir: Path,
    *,
    order_discovery: PaperOrderStateDiscovery | None = None,
) -> tuple[str, ...]:
    if not session_dir.exists():
        return ()
    effective_order_discovery = order_discovery or PaperOrderStateDiscovery()
    contracts: list[str] = []
    discovered_order_dirs: set[Path] = set()
    for order_candidate in effective_order_discovery.find_orders((session_dir,)):
        discovered_order_dirs.add(order_candidate.state_directory.resolve())
        symbol = str(order_candidate.state.selected_contract_symbol or "").strip()
        if symbol and symbol != "n/a" and symbol not in contracts:
            contracts.append(symbol)
    for order_path in paper_order_state_candidate_paths((session_dir,)):
        try:
            state_directory = order_path.parent.resolve()
        except OSError:
            continue
        if state_directory in discovered_order_dirs:
            continue
        try:
            raw = json.loads(order_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("selected_contract_symbol") or "").strip()
        if symbol and symbol != "n/a" and symbol not in contracts:
            contracts.append(symbol)
    for symbol in discover_trade_decision_summary_symbols(session_dir):
        if symbol not in contracts:
            contracts.append(symbol)
    return tuple(contracts)
