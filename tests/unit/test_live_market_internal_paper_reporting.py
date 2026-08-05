from __future__ import annotations

import json
from pathlib import Path

from tfis.runtime.multi_strategy.live_market_internal_paper import build_live_market_internal_paper_reports


def test_build_live_market_internal_paper_reports_exports_expected_files_and_flags_gaps(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "tmp" / "tfis_dashboard_v1" / "api"
    snapshot_root.mkdir(parents=True)
    live_supervisor_root = tmp_path / "reports" / "live_supervisor"
    live_supervisor_root.mkdir(parents=True)
    readiness_root = tmp_path / "reports" / "unified_readiness"
    readiness_root.mkdir(parents=True)

    snapshot = {
        "projection_hash": "hash-1",
        "system": {
            "session": "NSE:2026-08-05:LIVE_MARKET_INTERNAL_PAPER",
            "session_id": "NSE:2026-08-05:UNIFIED_INTERNAL_PAPER",
            "source_timestamp": "2026-08-05T08:31:51.833286+05:30",
            "generated_at": "2026-08-05T08:31:51.833286+05:30",
            "supervisor_state": "WAITING_FOR_MARKET",
            "broker_order_authority": "NONE",
            "external_order_submission": False,
            "tfis_execution_authority": "INTERNAL_PAPER_ONLY",
            "trading_date": "2026-08-05",
            "projection_mode": "LIVE_SUPERVISOR",
        },
        "accounts": [{"account_reference": "INTERNAL_PAPER_ACCOUNT_A"}],
        "analytics": {
            "account_risk_matrix": {
                "S21_BANKNIFTY_INTERNAL_PAPER_A": {"decision": "BLOCKED_ACCOUNT"},
            }
        },
        "orders": [{"strategy_instance_id": "S21_BANKNIFTY_INTERNAL_PAPER_A", "state": "READY_INTERNAL"}],
        "positions": [{"strategy_instance_id": "S21_BANKNIFTY_INTERNAL_PAPER_A", "status": "NO_POSITION"}],
        "strategies": [
            {
                "identity": {
                    "strategy_instance_id": "S21_BANKNIFTY_INTERNAL_PAPER_A",
                    "instrument": "BANKNIFTY",
                    "configured_lots": 1,
                    "lot_size": 15,
                },
                "state": {
                    "monthly_status": "BULL_CF",
                    "monthly_status_label": "Bull Cf",
                    "branch": "BULL_CALL",
                    "entry_eligibility": "WAITING_FOR_MARKET",
                    "entry_eligibility_label": "Waiting For Market",
                    "current_action": "READY_INTERNAL",
                    "current_action_label": "Ready Internal",
                    "runtime_stage": "WAITING_FOR_MARKET",
                    "evidence_quality": "LIVE_READ_ONLY_RUNTIME_SELECTION",
                },
                "plan": {
                    "selected_contract": "NSE:BANKNIFTY26AUG57000CE",
                    "selected_expiry": "2026-08-25",
                    "selected_option_type": "CE",
                    "selected_strike": "57000",
                    "premium": "774.60",
                    "oi": "100 lots minimum satisfied",
                    "base_entry": "774.60",
                    "target": "309.85",
                    "original_sl": "1239.35",
                    "orpt": "09:24:59.400000",
                    "rc": "09:29:59.400000",
                },
                "execution": {
                    "effective_entry": "774.60",
                    "risk_result": "ACCEPTED",
                    "order_state": "READY_INTERNAL",
                    "fill_state": "NO_FILL",
                    "filled_quantity": 0,
                    "latest_event": "FUTURE_WINDOW",
                    "mode_label": "Simulated Fill - No Broker Confirmation",
                    "orpt_state": "FUTURE_WINDOW",
                    "rc_state": "FUTURE_WINDOW",
                    "opening_context": "LIVE_SELECTION_PENDING",
                },
                "position": {
                    "quantity": 15,
                    "average_entry": "0.00",
                    "mark": "0.00",
                    "target": "309.85",
                    "active_protection": "Not placed",
                },
                "accounting": {"realized_pnl": "0.00", "unrealized_pnl": "0.00"},
                "operations": {},
            }
        ],
        "decision_explanations": [
            {
                "strategy_instance_id": "S21_BANKNIFTY_INTERNAL_PAPER_A",
                "stage": "MONTHLY_STATUS",
                "rule_id": "MONTHLY_STATUS.GENERIC.ENGINE.001",
                "workbook_source": "MONTHLY_STATUS_ENGINE_AUTHORITY_PACKET",
                "formula_text": "Monthly Status formula",
                "input_values": {"current_price": 58247.95},
                "output_value": "BULL_CF",
                "candidate_evidence": {
                    "derivation": {
                        "steps": [{"step": 1, "title": "Collect levels"}],
                    }
                },
            },
            {
                "strategy_instance_id": "S21_BANKNIFTY_INTERNAL_PAPER_A",
                "stage": "CONTRACT_SELECTION",
                "rule_id": "S21.CONTRACT.001",
                "formula_text": "Select contract",
                "candidate_evidence": {"selected_contract": "NSE:BANKNIFTY26AUG57000CE"},
            },
            {
                "strategy_instance_id": "S21_BANKNIFTY_INTERNAL_PAPER_A",
                "stage": "ENTRY_ELIGIBILITY",
                "rule_id": "GLOBAL.HISTORICAL.RECONSTRUCTION.ENTRY.001",
                "formula_text": "Entry eligibility",
            },
        ],
    }
    (snapshot_root / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    (live_supervisor_root / "validation_summary.json").write_text(
        json.dumps({"db_integrity": {"status": "PASS"}, "recovery": {"status": "CONFIGURATION_MISMATCH"}}),
        encoding="utf-8",
    )
    (live_supervisor_root / "performance_metrics.json").write_text(
        json.dumps(
            {
                "current_cycle": {
                    "cycle_duration_ms": 71749.735,
                    "poll_seconds": 1.0,
                    "stage_metrics": [
                        {"stage": "provider_symbol_master_nsefo", "duration_ms": 65371.409},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    for name in (
        "multi_strategy_live_routing.json",
        "subscription_owner_state.json",
        "checkpoint_resume_contract.json",
        "late_start_safety_result.json",
        "account_risk_acceptance_matrix.json",
        "gap_register.json",
        "failure_isolation_matrix.json",
        "scheduler_contract.json",
        "complete_session_preflight.json",
    ):
        (live_supervisor_root / name).write_text(json.dumps({}), encoding="utf-8")
    (readiness_root / "authoritative_readiness_projection.json").write_text(
        json.dumps({"verdict": "NO_GO_FOR_NEXT_COMPLETE_UNIFIED_SESSION", "blocking_reasons": ["cadence blocker"]}),
        encoding="utf-8",
    )

    result = build_live_market_internal_paper_reports(
        repo_root=tmp_path,
        authentication_diagnostics={"authentication_status": "AUTHENTICATED", "order_write_status": "NOT_AUTHORIZED"},
    )

    assert result.verdict == "LIVE_MARKET_INTERNAL_PAPER_CONDITIONAL"
    assert (result.report_dir / "monthly_status_results.json").exists()
    assert (result.report_dir / "authentication_diagnostics.json").exists()
    assert (result.report_dir / "live_market_internal_paper_summary.md").exists()

    gap_register = json.loads((result.report_dir / "gap_register.json").read_text(encoding="utf-8"))
    gap_ids = {item["gap_id"] for item in gap_register["gaps"]}
    assert "LIVE-IP-GAP-RISK-S21_BANKNIFTY_INTERNAL_PAPER_A" in gap_ids
    assert "LIVE-IP-GAP-PERF-001" in gap_ids

    monthly = json.loads((result.report_dir / "monthly_status_results.json").read_text(encoding="utf-8"))
    assert monthly["results"][0]["explanation_steps"][0]["title"] == "Collect levels"
