from __future__ import annotations

import json
from pathlib import Path

import yaml

from tfis.paper import load_paper_runtime_strategy_trust_statuses


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_s21_runtime_strategy_trust_status_passes_for_configured_controlled_paper() -> None:
    statuses = load_paper_runtime_strategy_trust_statuses(
        REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml",
        repo_root=REPO_ROOT,
    )

    status = next(item for item in statuses if item.strategy_code == "S21")

    assert status.status == "PASS"
    assert status.trust_level == "CONTROLLED_PAPER_NOT_LIVE_MONEY"
    assert status.checked_rule_count == 4
    assert status.issue_count == 0
    assert "not live-money approval" in status.message


def test_s21_runtime_strategy_trust_status_fails_reference_packet_quantity_drift(
    tmp_path: Path,
) -> None:
    reference_packet_path = (
        REPO_ROOT
        / "config"
        / "reference_packets"
        / "s21_banknifty_monthly_live_decision_reference.json"
    )
    packet = json.loads(reference_packet_path.read_text(encoding="utf-8"))
    packet["quantity"] = 30
    mutated_packet_path = tmp_path / "s21_reference_packet.json"
    mutated_packet_path.write_text(json.dumps(packet), encoding="utf-8")

    targets_config = {
        "targets": [
            {
                "strategy_code": "S21",
                "config_path": "config/paper.s21.fyers_connect_test.yaml",
                "artifact_root": "data/strategies/S21/fyers_morning_supervised_decision",
                "process_lock_root": "tmp/process_locks/s21_paper_watch",
                "strategy_path": (
                    "config/strategies/options_sell/banknifty/"
                    "S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL"
                ),
                "reference_packet_path": str(mutated_packet_path),
                "session_id_prefix": "s21-fyers-morning-supervised-decision",
                "executor": "paper_morning_supervised",
                "runner_script_path": "scripts/run_s21_banknifty_0916_supervised_decision.py",
                "wrapper_script_path": "scripts/start_s21_fyers_morning_supervised_decision.ps1",
            }
        ]
    }
    targets_config_path = tmp_path / "targets.yaml"
    targets_config_path.write_text(yaml.safe_dump(targets_config), encoding="utf-8")

    statuses = load_paper_runtime_strategy_trust_statuses(targets_config_path, repo_root=REPO_ROOT)

    assert len(statuses) == 1
    assert statuses[0].status == "FAIL"
    assert statuses[0].issue_count == 1
    assert "quantity expected configured BankNifty lot size 35" in statuses[0].message
