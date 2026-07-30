from __future__ import annotations

import json
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies import s23_call_captured_evidence as m5
from tfis.adapters.legacy_policies import s23_evaluation_capture as capture
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.domain import TFISTradeResult


BULL_M5_HASH = "4e327a977aeaad6841891b2a044155ca8a1f644c1b11a261e255252506deaa1c"
BEAR_M5_HASH = "3a8dbc6b507ac7603f2c0a4b289f3ecf9855f17206b3d96744b3291af8f20d41"


def test_bull_call_complete_capture_packet() -> None:
    observer = capture.InMemoryS23EvaluationCaptureObserver()
    result = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture", capture_observer=observer)

    assert result.decision.trade_result is TFISTradeResult.TRADE
    assert len(observer.packets) == 1
    packet = observer.packets[0]
    assert packet.identity.schema_version == capture.SCHEMA_VERSION
    assert packet.identity.strategy_family == "S23"
    assert packet.market_context.monthly_status == "BULL"
    assert packet.contract_selection.selected_contract == "NIFTY_20260806_22250_CALL"
    assert packet.entry.base_entry_result == "203.5"
    assert packet.risk_compatibility.target_result == 81.4
    assert packet.risk_compatibility.msl_result == 321.0
    assert packet.decision_evidence_packet.to_json() == result.evidence_packet.to_json()


def test_bear_call_complete_capture_packet() -> None:
    observer = capture.InMemoryS23EvaluationCaptureObserver()
    result = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture", capture_observer=observer)

    packet = observer.packets[0]
    assert result.decision.trade_result is TFISTradeResult.TRADE
    assert packet.market_context.monthly_status == "BEAR"
    assert packet.contract_selection.selected_contract == "NIFTY_20260806_22150_CALL"
    assert packet.entry.effective_entry_result == "194.25"
    assert packet.risk_compatibility.target_result == 77.7
    assert packet.risk_compatibility.msl_result == 310.8


def test_disabled_mode_produces_no_file_and_preserves_m5_hashes(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())

    bull = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture")
    bear = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")

    assert set(tmp_path.iterdir()) == before
    assert bull.deterministic_hash == BULL_M5_HASH
    assert bear.deterministic_hash == BEAR_M5_HASH


def test_enabled_capture_preserves_decision_result_and_hash() -> None:
    baseline = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")
    observer = capture.InMemoryS23EvaluationCaptureObserver()

    captured = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture", capture_observer=observer)

    assert captured.deterministic_hash == baseline.deterministic_hash
    assert captured.decision.comparison_key() == baseline.decision.comparison_key()
    assert captured.evidence_packet.to_json() == baseline.evidence_packet.to_json()
    assert len(observer.packets) == 1


def test_capture_packet_retains_option_chain_selected_quote_orpt_rc_and_final_packet() -> None:
    observer = capture.InMemoryS23EvaluationCaptureObserver()
    result = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture", capture_observer=observer)
    packet = observer.packets[0]

    assert len(packet.contract_selection.option_chain_snapshot.contracts) == 1
    assert packet.contract_selection.selected_contract_quote["symbol"] == result.decision.selected_instrument.symbol
    assert packet.entry.orpt_observation["source"] == "OPTION_LOW"
    assert packet.entry.rc_observation["source"] == "OPTION_LOW"
    assert json.loads(packet.decision_evidence_packet.to_json()) == json.loads(result.evidence_packet.to_json())


def test_capture_provenance_is_complete_and_discloses_synthetic_supplementation() -> None:
    observer = capture.InMemoryS23EvaluationCaptureObserver()
    m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture", capture_observer=observer)
    provenance = observer.packets[0].provenance

    assert provenance.evidence_classification == "LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT"
    assert set(provenance.section_sources) == {
        "identity",
        "market_context",
        "contract_selection",
        "entry",
        "risk_compatibility",
        "decision",
        "decision_evidence_packet",
    }
    assert "single qualifying option-chain candidate" in provenance.supplemented_fields
    assert "captured selected-contract quote" in provenance.missing_real_world_fields


def test_secret_fields_are_rejected() -> None:
    observer = capture.InMemoryS23EvaluationCaptureObserver()
    m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture", capture_observer=observer)
    packet = observer.packets[0]
    bad = {
        **packet.to_dict(),
        "provenance": {
            **packet.to_dict()["provenance"],
            "access_token": "should-not-pass",
        },
    }

    with pytest.raises(ValueError, match="sensitive capture field rejected"):
        capture._assert_no_sensitive_keys(bad)


def test_file_sink_writes_json_when_explicitly_enabled(tmp_path: Path) -> None:
    sink = capture.S23EvaluationCaptureFileSink(tmp_path)

    result = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture", capture_observer=sink)

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["identity"]["schema_version"] == capture.SCHEMA_VERSION
    assert payload["decision"]["trade_result"] == result.decision.trade_result.value


def test_duplicate_capture_identity_fails_capture_only(tmp_path: Path) -> None:
    sink = capture.S23EvaluationCaptureFileSink(tmp_path)
    baseline = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")

    first = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture", capture_observer=sink)
    second = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture", capture_observer=sink)

    assert first.deterministic_hash == baseline.deterministic_hash
    assert second.deterministic_hash == baseline.deterministic_hash
    assert len(list(tmp_path.glob("*.json"))) == 1


@pytest.mark.parametrize(
    "observer",
    (
        object(),
        None,
    ),
)
def test_invalid_observer_or_none_cannot_affect_decision(observer) -> None:
    baseline = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture")

    result = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture", capture_observer=observer)

    assert result.deterministic_hash == baseline.deterministic_hash
    assert result.decision.trade_result is TFISTradeResult.TRADE


def test_invalid_capture_packet_fails_capture_only(monkeypatch) -> None:
    def invalid_packet(result):
        raise ValueError("invalid capture packet")

    monkeypatch.setattr(capture, "build_s23_evaluation_capture_packet", invalid_packet)
    baseline = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")

    result = m5.run_s23_call_evidence_fixture(
        "s23_bear_call_workbook_fixture",
        capture_observer=capture.InMemoryS23EvaluationCaptureObserver(),
    )

    assert result.deterministic_hash == baseline.deterministic_hash


def test_write_permission_failure_is_isolated(monkeypatch, tmp_path: Path) -> None:
    def fail_write(path, text):
        raise PermissionError("blocked")

    monkeypatch.setattr(capture, "atomic_write_text", fail_write)
    baseline = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture")

    result = m5.run_s23_call_evidence_fixture(
        "s23_bull_call_workbook_fixture",
        capture_observer=capture.S23EvaluationCaptureFileSink(tmp_path),
    )

    assert result.deterministic_hash == baseline.deterministic_hash
    assert result.decision.trade_result is TFISTradeResult.TRADE


def test_output_directory_unavailable_is_isolated(tmp_path: Path) -> None:
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("occupied", encoding="utf-8")
    baseline = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")

    result = m5.run_s23_call_evidence_fixture(
        "s23_bear_call_workbook_fixture",
        capture_observer=capture.S23EvaluationCaptureFileSink(output_file),
    )

    assert result.deterministic_hash == baseline.deterministic_hash


def test_observer_exception_is_isolated() -> None:
    class FailingObserver:
        def record(self, packet):
            raise RuntimeError("observer failed")

    baseline = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture")

    result = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture", capture_observer=FailingObserver())

    assert result.deterministic_hash == baseline.deterministic_hash


def test_no_filesystem_write_from_disabled_business_evaluation(monkeypatch) -> None:
    def fail_write(*args, **kwargs):
        raise AssertionError("unexpected write")

    monkeypatch.setattr(capture, "atomic_write_text", fail_write)

    result = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")

    assert result.deterministic_hash == BEAR_M5_HASH


def test_architecture_boundary_for_capture_hook() -> None:
    vertical_source = Path(vertical.__file__).read_text(encoding="utf-8")
    capture_source = Path(capture.__file__).read_text(encoding="utf-8")
    orchestrator_source = Path("src/tfis/orchestration/offline_strategy_decision.py").read_text(encoding="utf-8")

    assert "S23" not in orchestrator_source
    assert "Fyers" not in capture_source
    assert "fyers" not in capture_source
    assert "place_order" not in capture_source
    assert "position_state" not in capture_source
    assert "eval(" not in capture_source
    assert "exec(" not in capture_source
    assert "record_s23_capture_safely" in vertical_source
