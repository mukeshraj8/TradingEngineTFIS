from __future__ import annotations

import json
import shutil
from pathlib import Path

from tfis.paper.tradingengine_capture_ingress_suite import (
    S23TradingEngineCaptureIngressSuiteRunner,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "tradingengine_capture_adapter"
)
CONTEXT_SESSION_DIR = FIXTURE_ROOT / "context_session"
OPTION_QUOTES_CSV = FIXTURE_ROOT / "NIFTY50_option_quotes_20260527.csv"


def _build_tradingdata_root(tmp_path: Path) -> Path:
    tradingdata_root = tmp_path / "TradingData"
    context_target = (
        tradingdata_root
        / "captures"
        / "context_sessions"
        / "2026-05-27"
        / CONTEXT_SESSION_DIR.name
    )
    context_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CONTEXT_SESSION_DIR, context_target)

    option_target = (
        tradingdata_root
        / "data"
        / "nifty"
        / "20260527"
        / "options"
        / "index"
    )
    option_target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OPTION_QUOTES_CSV, option_target / OPTION_QUOTES_CSV.name)
    return tradingdata_root


def test_capture_ingress_suite_runner_produces_pass_summary(tmp_path: Path) -> None:
    tradingdata_root = _build_tradingdata_root(tmp_path)
    out_root = tmp_path / "suite_out"
    runner = S23TradingEngineCaptureIngressSuiteRunner(out_root=out_root)

    summary = runner.run(
        data_root=tradingdata_root,
        dates=("2026-05-27",),
    )

    assert summary.total_sessions == 1
    assert summary.pass_count == 1
    assert summary.warning_count == 0
    assert summary.no_go_count == 0
    assert summary.rollout_recommendation == "GO_FOR_CONTROLLED_PAPER"

    session = summary.sessions[0]
    assert session.conversion_status == "SUCCESS"
    assert session.operational_classification == "PASS"
    assert session.terminal_state == "ORDER_PLANNED"
    assert session.fill_or_lifecycle_artifacts_present is False
    assert session.prelude_jsonl_path is not None
    assert session.market_events_jsonl_path is not None
    assert session.combined_events_jsonl_path is not None
    assert Path(session.prelude_jsonl_path).exists()
    assert Path(session.market_events_jsonl_path).exists()
    assert Path(session.combined_events_jsonl_path).exists()
    assert (out_root / "summary.json").exists()
    assert (out_root / "summary.md").exists()


def test_capture_ingress_suite_runner_supports_audit_only(tmp_path: Path) -> None:
    tradingdata_root = _build_tradingdata_root(tmp_path)
    out_root = tmp_path / "suite_out"
    runner = S23TradingEngineCaptureIngressSuiteRunner(out_root=out_root)

    summary = runner.run(
        data_root=tradingdata_root,
        dates=("2026-05-27",),
        audit_only=True,
    )

    assert summary.total_sessions == 1
    session = summary.sessions[0]
    assert session.conversion_status == "AUDIT_ONLY"
    assert session.market_events_jsonl_path is None
    assert session.prelude_jsonl_path is None
    assert session.combined_events_jsonl_path is None

    summary_payload = json.loads((out_root / "summary.json").read_text(encoding="utf-8"))
    assert summary_payload["sessions"][0]["conversion_status"] == "AUDIT_ONLY"
