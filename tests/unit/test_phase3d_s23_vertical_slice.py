from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.decision import MSLPolicyResult, PolicyStatus, TargetPolicyResult
from tfis.domain import (
    BusinessEngineStatus,
    EntryFailure,
    TFISProductType,
    TFISTradeResult,
    validate_decision_evidence_packet,
)
from tfis.domain.gap_missed_entry import (
    RecalculationDownstreamAction,
    RecalculationStatus,
)
from tfis.entry import EntryEngine


EXPECTED_ORDER = (
    "strategy_resolution",
    "monthly_status_and_branch",
    "underlying_references",
    "contract_selection",
    "base_entry",
    "gap_missed_entry",
    "effective_entry",
    "target_msl",
    "decision",
    "evidence_packet",
    "legacy_comparison",
)


def test_s23_bull_call_vertical_slice_emits_trade_decision_and_full_packet() -> None:
    result = vertical.run_s23_bull_call_vertical_slice()

    assert tuple(stage.stage_name for stage in result.stages) == EXPECTED_ORDER
    assert all(stage.status == "PASSED" for stage in result.stages)
    assert result.decision.trade_result is TFISTradeResult.TRADE
    assert result.decision.product_type is TFISProductType.OPTION_SELLING
    assert result.decision.selected_instrument is not None
    assert result.decision.selected_instrument.option_type == "CALL"
    assert result.evidence_packet.entry is not None
    assert result.evidence_packet.entry.base_entry.value == result.evidence_packet.calculated_decision.entry.value
    assert validate_decision_evidence_packet(result.evidence_packet).is_full


def test_s23_vertical_slice_is_deterministic_and_matches_legacy_adapters() -> None:
    first = vertical.run_s23_bull_call_vertical_slice()
    second = vertical.run_s23_bull_call_vertical_slice()

    assert first.deterministic_hash == second.deterministic_hash
    assert first.decision.comparison_key() == second.decision.comparison_key()
    assert first.evidence_packet.to_json() == second.evidence_packet.to_json()
    assert first.mismatch_classifications == {}
    assert {
        field: row["classification"]
        for field, row in first.field_comparison.items()
    } == {
        "branch": "MATCH",
        "selected_strike": "MATCH",
        "base_entry": "MATCH",
        "effective_entry": "MATCH",
        "target": "MATCH",
        "msl": "MATCH",
        "trade_result": "MATCH",
    }


def test_s23_vertical_slice_blocks_when_contract_selection_has_no_qualifying_contract() -> None:
    case = vertical.build_s23_bull_call_vertical_case()
    expiry = case.runtime_input.product_specific["expiry_date"]
    bad_chain = vertical._option_chain(
        case.strategy_rule.symbol,
        expiry,
        case.strategy_rule.option_type,
        22250.0,
        280.0,
        1.0,
        case.runtime_input.evaluated_at,
    )
    runtime_input = replace(
        case.runtime_input,
        product_specific={"option_chain_snapshot": bad_chain, "expiry_date": expiry},
    )
    context = _context_through(
        vertical._underlying_references,
        replace(case, runtime_input=runtime_input, option_chain_snapshot=bad_chain),
    )

    result = vertical._contract_selection(context)

    assert result.status == "BLOCKED"
    assert result.failure_code == "NO_QUALIFYING_CONTRACT"


def test_s23_vertical_slice_blocks_base_entry_without_selected_contract_reference() -> None:
    context = _context_through(vertical._contract_selection)
    selected = replace(context["selected_contract"], strike=None)

    result = vertical._base_entry({**context, "selected_contract": selected})

    assert result.status == "BLOCKED"
    assert result.payload["base_entry"].status is BusinessEngineStatus.BLOCKED
    assert EntryFailure.MISSING_SELECTED_OPTION_CONTRACT in result.payload["base_entry"].failures


def test_s23_vertical_slice_blocks_unknown_entry_policy_before_effective_entry() -> None:
    context = _context_through(vertical._contract_selection)
    engine_input = replace(
        vertical._entry_input(
            context["case"],
            context["selected_contract"],
            context["legacy_entry"],
            None,
        ),
        entry_policy_key="missing.entry.policy",
    )

    result = EntryEngine({}).execute(engine_input)

    assert result.status is BusinessEngineStatus.BLOCKED
    assert EntryFailure.UNKNOWN_ENTRY_POLICY in result.failures


def test_s23_vertical_slice_gap_not_missed_keeps_effective_entry_equal_to_base() -> None:
    context = _context_through(vertical._gap_missed_entry)

    assert context["gap_missed_entry"].missed_entry.status.value == "NOT_MISSED"
    result = vertical._effective_entry(context)

    assert result.status == "PASSED"
    assert result.payload["effective_entry"].effective_entry.value == context["base_entry"].base_entry.value
    assert result.payload["effective_entry"].effective_entry.status.value == "ENTRY_NOT_MISSED"


def test_s23_vertical_slice_blocks_when_recalculation_is_required_but_missing() -> None:
    context = _context_through(vertical._gap_missed_entry)
    recalculation = replace(
        context["gap_missed_entry"].recalculation,
        applicable=True,
        status=RecalculationStatus.REQUIRED,
        compatibility_outputs={},
        downstream_action=RecalculationDownstreamAction.DEFER_TO_ENTRY_ENGINE,
    )
    context = {
        **context,
        "gap_missed_entry": replace(context["gap_missed_entry"], recalculation=recalculation),
    }

    result = vertical._effective_entry(context)

    assert result.status == "BLOCKED"
    assert result.failure_code == "EFFECTIVE_ENTRY_FAILURE"
    assert EntryFailure.RECALCULATION_REQUIRED_BUT_MISSING in result.payload["effective_entry"].failures


def test_s23_vertical_slice_blocks_target_adapter_failure(monkeypatch) -> None:
    context = _context_through(vertical._effective_entry)

    def fail_target(self, policy_input):
        return TargetPolicyResult(
            policy_name="fixture.target",
            evaluated_at=policy_input.runtime_input.evaluated_at,
            status=PolicyStatus.BLOCKED,
            applicable=True,
            reason="target fixture failure",
        )

    monkeypatch.setattr(vertical.S23TargetPolicyAdapter, "evaluate", fail_target)

    result = vertical._target_msl(context)

    assert result.status == "BLOCKED"
    assert result.failure_code == "TARGET_ADAPTER_FAILURE"


def test_s23_vertical_slice_blocks_msl_adapter_failure(monkeypatch) -> None:
    context = _context_through(vertical._effective_entry)

    def fail_msl(self, policy_input):
        return MSLPolicyResult(
            policy_name="fixture.msl",
            evaluated_at=policy_input.runtime_input.evaluated_at,
            status=PolicyStatus.BLOCKED,
            applicable=True,
            reason="msl fixture failure",
        )

    monkeypatch.setattr(vertical.S23MSLPolicyAdapter, "evaluate", fail_msl)

    result = vertical._target_msl(context)

    assert result.status == "BLOCKED"
    assert result.failure_code == "MSL_ADAPTER_FAILURE"


def test_s23_vertical_packet_round_trips_without_persistence() -> None:
    result = vertical.run_s23_bull_call_vertical_slice()
    packet = result.evidence_packet.from_json(result.evidence_packet.to_json())

    assert packet.to_json() == result.evidence_packet.to_json()
    assert isinstance(result.decision.decided_at, datetime)
    assert result.performance["evidence_packet_size_bytes"] == len(result.evidence_packet.to_json().encode("utf-8"))


def _context_through(stage, case=None) -> dict[str, object]:
    context: dict[str, object] = {"case": case or vertical.build_s23_bull_call_vertical_case()}
    for current in (
        vertical._strategy_resolution,
        vertical._monthly_status_and_branch,
        vertical._underlying_references,
        vertical._contract_selection,
        vertical._base_entry,
        vertical._gap_missed_entry,
        vertical._effective_entry,
        vertical._target_msl,
        vertical._decision,
        vertical._evidence_packet,
        vertical._legacy_comparison,
    ):
        result = current(context)
        context.update(dict(result.payload))
        if result.status != "PASSED":
            raise AssertionError(f"{result.stage_name} did not pass: {result.failure_code} {result.reason}")
        if current is stage:
            return context
    raise AssertionError(f"stage was not reached: {stage}")
