from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


PRELUDE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "s23_fyers_prelude.jsonl"
)
PAYLOAD_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "fyers_market_data_payloads.json"
)


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "paper.s23.yaml"
    payload = {
        "source_mode": "broker_fyers_live_paper_ingress",
        "broker": {
            "provider": "fyers",
            "timezone": "Asia/Kolkata",
            "payload_fixture_path": str(PAYLOAD_FIXTURE),
            "capture_stream_events": False,
        },
        "paper": {
            "strategy_code": "S23",
            "symbol": "NIFTY",
            "contract_cycle": "WEEKLY",
            "mode": "paper",
            "operator_id": "cli-test-operator",
            "paper_mode_enabled": True,
            "same_day_square_off_only": True,
            "allow_recalculation": False,
            "allow_current_day_fsl_trp": True,
            "kill_switch_enabled": True,
            "session_kill_switch_active": False,
            "no_live_orders_allowed": True,
        },
        "market": {
            "underlying_symbol": "NIFTY",
            "weekly_expiry": "2026-05-12",
            "selected_contract_symbol": "NIFTY_20260512_25000_PE",
        },
        "costs": {
            "brokerage_per_lot": 20.0,
            "slippage_entry_points": 1.0,
            "slippage_exit_points": 1.0,
            "spread_buffer_policy": "bid_ask_guard",
            "version_label": "paper-cost-v1",
        },
        "thresholds": {
            "max_quote_age_seconds": 5.0,
            "max_timing_drift_seconds": 5.0,
            "max_stale_events": 0,
            "max_missing_chains": 0,
            "required_selected_contract_availability_ratio": 1.0,
            "max_no_trade_rate": 0.0,
        },
    }
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return config_path


def test_run_s23_fyers_paper_ingress_cli_writes_outputs(tmp_path: Path) -> None:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "run_s23_fyers_paper_ingress.py"
    )
    config_path = _write_config(tmp_path)
    out_json = tmp_path / "ingress.json"
    out_md = tmp_path / "ingress.md"
    artifact_root = tmp_path / "artifacts"

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--config",
            str(config_path),
            "--prelude-jsonl",
            str(PRELUDE_PATH),
            "--artifact-root",
            str(artifact_root),
            "--session-id",
            "cli-fyers-ingress",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert out_json.exists()
    assert out_md.exists()

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")

    assert payload["broker_name"] == "fyers"
    assert payload["terminal_state"] == "ORDER_PLANNED"
    assert payload["operational_readiness"] == "PASS"
    assert "Broker market-data only" in markdown
    assert "No broker order-placement path exists" in markdown


def test_run_s23_fyers_paper_ingress_cli_preflight_only_writes_outputs(
    tmp_path: Path,
) -> None:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "run_s23_fyers_paper_ingress.py"
    )
    config_path = _write_config(tmp_path)
    out_json = tmp_path / "preflight.json"
    out_md = tmp_path / "preflight.md"
    artifact_root = tmp_path / "artifacts"

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--config",
            str(config_path),
            "--prelude-jsonl",
            str(PRELUDE_PATH),
            "--artifact-root",
            str(artifact_root),
            "--session-id",
            "cli-fyers-preflight",
            "--preflight-only",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert out_json.exists()
    assert out_md.exists()

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")

    assert payload["preflight_status"] == "WARNING"
    assert payload["can_run"] is True
    assert payload["will_connect_to_broker"] is False
    assert "Preflight only never connects to FYERS" in markdown
