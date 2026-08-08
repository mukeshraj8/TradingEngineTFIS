from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from tfis.strategy_engine.s21 import (
    MinuteBarEvidence,
    OptionContractEvidence,
    OptionHistoricalReferences,
    S21_BRANCHES,
    S21StrategyEvidence,
)


class S21EvidenceError(RuntimeError):
    pass


def load_s21_replay_evidence(path: str | Path) -> S21StrategyEvidence:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8-sig"))

    option_chain = tuple(
        OptionContractEvidence(
            symbol=str(row["symbol"]),
            option_type=str(row["option_type"]),
            strike=float(row["strike"]),
            expiry=str(row["expiry"]),
            oi=None if row.get("oi") is None else float(row["oi"]),
            chain_ltp=(
                None if row.get("chain_ltp") is None else float(row["chain_ltp"])
            ),
        )
        for row in payload.get("option_chain", [])
    )

    historical = {
        str(symbol): OptionHistoricalReferences(
            symbol=str(symbol),
            references={
                str(k): float(v)
                for k, v in (row.get("references") or {}).items()
            },
            source=str(row.get("source") or "UNKNOWN"),
        )
        for symbol, row in (payload.get("option_historical_references") or {}).items()
    }

    minute_bars = {
        str(symbol): tuple(
            MinuteBarEvidence(
                symbol=str(symbol),
                bar_start=str(row["bar_start"]),
                high=None if row.get("high") is None else float(row["high"]),
                low=None if row.get("low") is None else float(row["low"]),
                open=None if row.get("open") is None else float(row["open"]),
                close=None if row.get("close") is None else float(row["close"]),
            )
            for row in rows
        )
        for symbol, rows in (payload.get("option_minute_bars") or {}).items()
    }

    return S21StrategyEvidence(
        session_date=str(payload["session_date"]),
        monthly_status=str(payload["monthly_status"]),
        monthly_status_source=str(payload["monthly_status_source"]),
        underlying_references={
            str(k): float(v)
            for k, v in payload["underlying_references"].items()
        },
        option_chain=option_chain,
        option_historical_references=historical,
        option_minute_bars=minute_bars,
        spot_bars=dict(payload.get("spot_bars") or {}),
        branch_parameters={
            str(code): {str(k): float(v) for k, v in params.items()}
            for code, params in payload["branch_parameters"].items()
        },
        metadata=dict(payload.get("metadata") or {}),
    )


def build_base_evidence_from_certification(
    *,
    repo_root: str | Path,
    certification_root: str | Path,
    session_date: str,
    output_path: str | Path,
) -> Path:
    """Build a replay evidence file from archived TFIS facts only.

    This function never calls FYERS. Candidate option histories that were not
    archived remain absent and are surfaced by the strategy engine as explicit
    evidence gaps.
    """
    repo_root = Path(repo_root)
    certification_root = Path(certification_root)
    day_root = certification_root / session_date
    archive = day_root / "archived_runtime_evidence"
    if not archive.exists():
        raise S21EvidenceError(f"Missing archived evidence: {archive}")

    snap0916 = _snapshot_dir(archive, "0916", session_date)
    session_dir = _strategy_session_dir(archive, session_date)

    chain_payload = _load_json(
        snap0916 / "normalized_option_chain_snapshot.json"
    )
    daily_payload = _load_json(
        snap0916 / "normalized_underlying_daily_bars.json"
    )

    monthly_status, monthly_source = _monthly_status(session_dir)
    underlying_refs = _underlying_refs(
        list(daily_payload.get("bars") or []),
        session_date=session_date,
    )
    branch_parameters = _branch_parameters(repo_root)

    # Reuse any actually archived selected-contract minute events, but do not
    # treat old static reference-packet values as candidate historical evidence.
    option_minute_bars: dict[str, list[dict[str, Any]]] = {}
    for branch_dir in session_dir.iterdir():
        if not branch_dir.is_dir():
            continue
        event_path = branch_dir / "selected_contract_market_events.jsonl"
        if not event_path.exists():
            continue
        for row in _iter_jsonl(event_path):
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
            symbol = payload.get("symbol")
            if not symbol:
                continue
            bar_start = payload.get("bar_start") or payload.get("source_timestamp")
            if not bar_start:
                continue
            option_minute_bars.setdefault(str(symbol), []).append(
                {
                    "bar_start": str(bar_start),
                    "open": payload.get("open"),
                    "high": payload.get("high"),
                    "low": payload.get("low"),
                    "close": payload.get("close"),
                }
            )

    contracts = [
        {
            "symbol": str(row["symbol"]),
            "option_type": str(row["option_type"]),
            "strike": float(row["strike"]),
            "expiry": str(row["expiry"]),
            "oi": row.get("oi"),
            "chain_ltp": row.get("ltp"),
        }
        for row in chain_payload["payload"]["contracts"]
    ]

    evidence = {
        "schema": "tfis.s21.strategy_evidence.v1",
        "session_date": session_date,
        "monthly_status": monthly_status,
        "monthly_status_source": monthly_source,
        "underlying_references": underlying_refs,
        "option_chain": contracts,
        "option_historical_references": {},
        "option_minute_bars": option_minute_bars,
        "spot_bars": _spot_checkpoint_bars(archive, session_date),
        "branch_parameters": branch_parameters,
        "metadata": {
            "source": "ARCHIVED_TFIS_CERTIFICATION_EVIDENCE",
            "candidate_history_policy": (
                "No static TFIS reference-packet OPT_PRV values are imported."
            ),
        },
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


def merge_option_evidence(
    *,
    evidence_path: str | Path,
    option_evidence_dir: str | Path,
) -> Path:
    """Merge independently collected option evidence into the replay pack.

    Expected files:
      <option_evidence_dir>/<SYMBOL>/daily_references.json
      <option_evidence_dir>/<SYMBOL>/minute_bars.json
    """
    evidence_path = Path(evidence_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    option_evidence_dir = Path(option_evidence_dir)

    historical = evidence.setdefault("option_historical_references", {})
    minute_bars = evidence.setdefault("option_minute_bars", {})

    if option_evidence_dir.exists():
        for symbol_dir in option_evidence_dir.iterdir():
            if not symbol_dir.is_dir():
                continue

            symbol = symbol_dir.name
            identity_path = symbol_dir / "symbol.json"
            if identity_path.exists():
                identity = _load_json(identity_path)
                symbol = str(identity.get("symbol") or symbol)

            daily = symbol_dir / "daily_references.json"
            minute = symbol_dir / "minute_bars.json"
            if daily.exists():
                payload = _load_json(daily)
                historical[symbol] = {
                    "references": payload.get("references") or {},
                    "source": payload.get("source") or "EXTERNAL_READ_ONLY_EVIDENCE",
                }
            if minute.exists():
                payload = _load_json(minute)
                minute_bars[symbol] = list(payload.get("bars") or [])

    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return evidence_path


def _snapshot_dir(root: Path, label: str, session_date: str) -> Path:
    matches = [
        p for p in root.iterdir()
        if p.is_dir() and label in p.name and session_date in p.name
    ]
    if not matches:
        raise S21EvidenceError(f"Missing {label} snapshot under {root}")
    return sorted(matches)[0]


def _strategy_session_dir(root: Path, session_date: str) -> Path:
    matches = [
        p for p in root.iterdir()
        if p.is_dir()
        and session_date in p.name
        and not any(tag in p.name for tag in ("0916", "0925", "0930"))
    ]
    if not matches:
        raise S21EvidenceError(f"Missing strategy session under {root}")
    return sorted(matches)[0]


def _monthly_status(session_dir: Path) -> tuple[str, str]:
    statuses: set[str] = set()
    sources: list[str] = []
    for code in S21_BRANCHES:
        path = session_dir / code / "monthly_status_stage_0916.json"
        if not path.exists():
            continue
        payload = _load_json(path)

        # Current archived S21 artifacts store:
        #   {"monthly_status": {"status": "BULL_CF", ...}}
        # Older/development artifacts may expose stage.monthly_status instead.
        monthly_status_payload = payload.get("monthly_status")
        status = None
        if isinstance(monthly_status_payload, dict):
            status = monthly_status_payload.get("status")
        elif isinstance(monthly_status_payload, str):
            status = monthly_status_payload

        if not status:
            stage_payload = payload.get("stage")
            if isinstance(stage_payload, dict):
                nested = stage_payload.get("monthly_status")
                if isinstance(nested, dict):
                    status = nested.get("status")
                elif isinstance(nested, str):
                    status = nested

        if status:
            statuses.add(str(status))
            sources.append(str(path))
    if len(statuses) != 1:
        discovered = []
        for code in S21_BRANCHES:
            path = session_dir / code / "monthly_status_stage_0916.json"
            discovered.append(
                {
                    "branch": code,
                    "path": str(path),
                    "exists": path.exists(),
                }
            )
        raise S21EvidenceError(
            "Expected one consistent 09:16 Monthly Status; "
            f"resolved={sorted(statuses)}; artifacts={discovered}"
        )
    return next(iter(statuses)), "ARCHIVED_0916_MONTHLY_STATUS:" + "|".join(sources)


def _underlying_refs(
    bars: list[dict[str, Any]],
    *,
    session_date: str,
) -> dict[str, float]:
    completed = [
        row for row in bars
        if str(row.get("bar_start", ""))[:10] < session_date
    ]
    if len(completed) < 4:
        raise S21EvidenceError("At least four completed underlying daily bars are required.")
    refs: dict[str, float] = {}
    for window in (2, 3, 4):
        rows = completed[-window:]
        refs[f"PRV_{window}DHH"] = max(float(row["high"]) for row in rows)
        refs[f"PRV_{window}DLL"] = min(float(row["low"]) for row in rows)
    return refs


def _branch_parameters(repo_root: Path) -> dict[str, dict[str, float]]:
    root = (
        repo_root
        / "config"
        / "strategies"
        / "options_sell"
        / "banknifty"
    )
    result: dict[str, dict[str, float]] = {}
    for code in S21_BRANCHES:
        matches = list(root.glob(f"S21_{code}/parameters.yaml"))
        if not matches:
            matches = [
                p for p in root.glob("S21_*/parameters.yaml")
                if code in p.parent.name
            ]
        if not matches:
            raise S21EvidenceError(f"Missing parameters.yaml for {code}")
        payload = yaml.safe_load(matches[0].read_text(encoding="utf-8")) or {}
        result[code] = {str(k): float(v) for k, v in payload.items()}
    return result


def _spot_checkpoint_bars(
    archive: Path,
    session_date: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for label in ("0925", "0930"):
        try:
            snap = _snapshot_dir(archive, label, session_date)
        except S21EvidenceError:
            continue
        payload = _load_json(snap / "normalized_underlying_bars.json")
        bars = list(payload.get("bars") or [])
        result[label] = bars[-1] if bars else {}
    return result


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            text = line.strip()
            if text:
                payload = json.loads(text)
                if isinstance(payload, dict):
                    yield payload


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise S21EvidenceError(f"Missing evidence file: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))
