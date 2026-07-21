from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .session_discovery import iter_trade_decision_summary_paths


@dataclass(frozen=True, slots=True)
class PaperTradeDecisionSummaryCandidate:
    session_directory: Path
    branch_directory: Path
    summary_path: Path
    order_state_path: Path | None
    branch: str
    payload: dict[str, Any]
    summary: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PaperFinalTradeDecisionSummary:
    session_directory: Path
    artifact_directory: Path
    summary_path: Path | None
    payload: dict[str, Any] | None
    summary: dict[str, Any] | None


def discover_trade_decision_summaries(
    session_dir: Path,
) -> tuple[PaperTradeDecisionSummaryCandidate, ...]:
    candidates: list[PaperTradeDecisionSummaryCandidate] = []
    for summary_path in iter_trade_decision_summary_paths(session_dir):
        candidate = _load_summary_candidate(
            session_dir=session_dir,
            summary_path=summary_path,
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def discover_trade_decision_summary_symbols(
    session_dir: Path,
) -> tuple[str, ...]:
    symbols: list[str] = []
    for candidate in discover_trade_decision_summaries(session_dir):
        symbol = str(candidate.summary.get("selected_contract_symbol") or "").strip()
        if not symbol or symbol == "n/a" or symbol in symbols:
            continue
        symbols.append(symbol)
    return tuple(symbols)


def resolve_trade_decision_summary_candidate(
    session_dir: Path | None,
    *,
    preferred_branch: str | None = None,
) -> PaperTradeDecisionSummaryCandidate | None:
    if session_dir is None or not session_dir.exists():
        return None
    top_level_summary = session_dir / "trade_decision_summary.json"
    if top_level_summary.exists():
        return _load_summary_candidate(
            session_dir=session_dir,
            summary_path=top_level_summary,
        )
    candidates = discover_trade_decision_summaries(session_dir)
    if preferred_branch:
        for candidate in candidates:
            if candidate.branch == preferred_branch:
                return candidate
    if len(candidates) == 1:
        return candidates[0]
    return None


def resolve_trade_decision_artifact_dir(
    session_dir: Path | None,
    *,
    preferred_branch: str | None = None,
) -> Path | None:
    if session_dir is None or not session_dir.exists():
        return None
    candidate = resolve_trade_decision_summary_candidate(
        session_dir,
        preferred_branch=preferred_branch,
    )
    if candidate is not None:
        return candidate.branch_directory
    return session_dir


def _load_summary_candidate(
    *,
    session_dir: Path,
    summary_path: Path,
) -> PaperTradeDecisionSummaryCandidate | None:
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary", payload)
    if not isinstance(summary, dict):
        return None
    return PaperTradeDecisionSummaryCandidate(
        session_directory=session_dir,
        branch_directory=summary_path.parent,
        summary_path=summary_path,
        order_state_path=(
            summary_path.parent / "paper_order_state.json"
            if (summary_path.parent / "paper_order_state.json").exists()
            else None
        ),
        branch=str(summary.get("strategy_branch") or summary_path.parent.name),
        payload=payload,
        summary=summary,
    )


def resolve_final_trade_decision_summary(
    session_dir: Path | None,
    *,
    preferred_branch: str | None = None,
) -> PaperFinalTradeDecisionSummary | None:
    artifact_directory = resolve_trade_decision_artifact_dir(
        session_dir,
        preferred_branch=preferred_branch,
    )
    if artifact_directory is None:
        return None
    summary_path = artifact_directory / "trade_decision_summary.json"
    if not summary_path.exists():
        return PaperFinalTradeDecisionSummary(
            session_directory=Path(session_dir) if session_dir is not None else artifact_directory,
            artifact_directory=artifact_directory,
            summary_path=None,
            payload=None,
            summary=None,
        )
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = None
    summary = payload.get("summary", payload) if isinstance(payload, dict) else None
    if summary is not None and not isinstance(summary, dict):
        summary = None
    return PaperFinalTradeDecisionSummary(
        session_directory=Path(session_dir) if session_dir is not None else artifact_directory,
        artifact_directory=artifact_directory,
        summary_path=summary_path,
        payload=payload if isinstance(payload, dict) else None,
        summary=summary,
    )
