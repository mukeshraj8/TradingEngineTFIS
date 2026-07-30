from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tfis.adapters.legacy_policies import s23_call_captured_evidence as m5
from tfis.adapters.legacy_policies import s23_opening_context as opening
from tfis.adapters.legacy_policies import s23_premarket_plan as premarket
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.domain import (
    OpeningContextStatus,
    OpeningFreshnessStatus,
    OpeningGapClassification,
    OpeningQuoteEvidence,
    OpeningTimestampClassification,
)
from tfis.opening import OpeningContextBuildInput, OpeningContextObservations, OpeningGapPolicy, OpeningMarketContextBuilder


BULL_M3_HASH = "4d2e514f05f873c17b7077ce6710c559dac54422ed6898cbb51e6ed9bbb24b84"
BULL_M9_PLAN_HASH = "873a7662f321b70af350a5d3b2e0b9fccf72852ae0bfc88e4471faca4cd91f22"
BEAR_M9_PLAN_HASH = "cfb09a5b41ee667a045e89d36cf4167dfe3acb46630bf76dd03e16f51e3e576b"
BULL_M5_HASH = "4e327a977aeaad6841891b2a044155ca8a1f644c1b11a261e255252506deaa1c"
BEAR_M5_HASH = "3a8dbc6b507ac7603f2c0a4b289f3ecf9855f17206b3d96744b3291af8f20d41"


def test_bull_complete_context() -> None:
    ctx = opening.build_s23_bull_call_opening_context()

    assert ctx.context_status is OpeningContextStatus.COMPLETE
    assert ctx.source_plan_hash == BULL_M9_PLAN_HASH
    assert ctx.selected_contract.symbol == "NIFTY_20260806_22250_CALL"
    assert ctx.timestamp_classification is OpeningTimestampClassification.OFFICIAL_EXCHANGE_OPEN
    assert ctx.gap_context.classification is OpeningGapClassification.GAP_UP
    assert ctx.orpt_observation.availability.value == "AVAILABLE"
    assert ctx.rc_observation.availability.value == "AVAILABLE"
    assert ctx.execution_permission == "NONE"
    assert ctx.lifecycle_action == "NONE"


def test_bear_complete_context() -> None:
    ctx = opening.build_s23_bear_call_opening_context()

    assert ctx.context_status is OpeningContextStatus.COMPLETE
    assert ctx.source_plan_hash == BEAR_M9_PLAN_HASH
    assert ctx.selected_contract.symbol == "NIFTY_20260806_22150_CALL"
    assert ctx.gap_context.classification is OpeningGapClassification.GAP_DOWN


def test_bull_partial_real_context_remains_partial() -> None:
    ctx = opening.build_s23_partial_real_opening_context()

    assert ctx.context_status is OpeningContextStatus.PARTIAL
    assert ctx.evidence_classification == "PARTIAL_CAPTURE"
    assert ctx.gap_context.classification is OpeningGapClassification.INSUFFICIENT_EVIDENCE
    assert "orpt_observation" in ctx.missing_fields
    assert "selected_contract_opening.oi" in ctx.missing_fields
    assert ctx.rc_observation.availability.value == "AVAILABLE"


def test_same_generic_builder_serves_bull_and_bear(monkeypatch) -> None:
    calls: list[str] = []
    original = OpeningMarketContextBuilder.build

    def observe(self, build_input):
        calls.append(type(self).__name__)
        return original(self, build_input)

    monkeypatch.setattr(OpeningMarketContextBuilder, "build", observe)

    opening.build_s23_bull_call_opening_context()
    opening.build_s23_bear_call_opening_context()

    assert calls == ["OpeningMarketContextBuilder", "OpeningMarketContextBuilder"]


def test_contexts_are_deterministic_and_immutable() -> None:
    first = opening.build_s23_bull_call_opening_context()
    second = opening.build_s23_bull_call_opening_context()

    assert first.context_hash == second.context_hash
    assert first._business_payload() == second._business_payload()
    with pytest.raises(FrozenInstanceError):
        first.context_status = OpeningContextStatus.PARTIAL


def test_official_first_local_and_derived_timestamp_classifications() -> None:
    official = opening.build_s23_bull_call_opening_context()
    partial = opening.build_s23_partial_real_opening_context()
    first_local = _build_context(timestamp_classification=OpeningTimestampClassification.FIRST_LOCAL_TICK, official=False)

    assert official.official_exchange_open_timestamp is not None
    assert official.timestamp_classification is OpeningTimestampClassification.OFFICIAL_EXCHANGE_OPEN
    assert first_local.timestamp_classification is OpeningTimestampClassification.FIRST_LOCAL_TICK
    assert first_local.context_status is OpeningContextStatus.PARTIAL
    assert partial.timestamp_classification is OpeningTimestampClassification.DERIVED_OPENING_BAR


def test_gap_up_gap_down_no_gap_and_insufficient_evidence() -> None:
    assert _build_context(opening_price=22410.0, comparison_value=22400.0).gap_context.classification is OpeningGapClassification.GAP_UP
    assert _build_context(opening_price=22390.0, comparison_value=22400.0).gap_context.classification is OpeningGapClassification.GAP_DOWN
    assert _build_context(opening_price=22400.0, comparison_value=22400.0).gap_context.classification is OpeningGapClassification.NO_GAP
    assert _build_context(opening_price=22400.0, comparison_value=None).gap_context.classification is OpeningGapClassification.INSUFFICIENT_EVIDENCE
    assert _build_context(opening_price=24000.0, comparison_value=22400.0, abnormal_pct=5.0).gap_context.classification is OpeningGapClassification.ABNORMAL_OPENING


def test_orpt_rc_capture_and_rc_not_applicable() -> None:
    full = opening.build_s23_bull_call_opening_context()
    no_rc = _build_context(rc_required=False)

    assert full.orpt_observation.configured_timestamp.time().isoformat() == "09:19:59"
    assert full.rc_observation.configured_timestamp.time().isoformat() == "09:29:59"
    assert no_rc.rc_observation.availability.value == "NOT_APPLICABLE"
    assert no_rc.consumer_readiness.orpt_plus_rc_flow is OpeningContextStatus.NOT_APPLICABLE


def test_stale_quote_handling() -> None:
    ctx = _build_context(freshness=OpeningFreshnessStatus.STALE)

    assert ctx.context_status is OpeningContextStatus.PARTIAL
    assert "underlying_opening" in ctx.stale_fields


def test_selected_contract_underlying_plan_hash_and_trading_date_mismatches_block() -> None:
    assert _build_context(selected_symbol="NIFTY_OTHER").context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT
    assert _build_context(underlying="NSE:BANKNIFTY").context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT
    assert _build_context(expected_hash="wrong").context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT
    assert _build_context(observed_date=date(2026, 7, 31)).context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT


def test_missing_opening_or_orpt_or_rc_or_oi_blocks_or_partials_explicitly() -> None:
    assert _build_context(opening_quote=False).context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT
    assert _build_context(orpt=False).consumer_readiness.orpt_only_flow is OpeningContextStatus.PARTIAL
    assert _build_context(rc=False).consumer_readiness.orpt_plus_rc_flow is OpeningContextStatus.PARTIAL
    assert _build_context(oi=False).context_status is OpeningContextStatus.PARTIAL


def test_timestamp_window_duplicate_unsupported_and_missing_provenance_fail_closed() -> None:
    assert _build_context(orpt_offset_seconds=300).context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT
    assert _build_context(duplicate_candidates=True).context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT
    assert _build_context(timestamp_classification=OpeningTimestampClassification.UNSUPPORTED).context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT
    assert _build_context(provenance=None).context_status is OpeningContextStatus.PARTIAL


def test_multiple_strategy_instance_reuse_proof() -> None:
    plan_a = premarket.build_s23_bull_call_premarket_plan()
    plan_b = replace(plan_a, plan_id=f"{plan_a.plan_id}:second-instance", strategy_instance_id="S23_NIFTY_ACCOUNT_B_PAPER")
    shared_underlying = _quote(plan_a.underlying_instrument, 22420.0, _ts(plan_a.planned_values.normal_orpt), OpeningTimestampClassification.ORPT_OBSERVATION)

    ctx_a = _build_context_from_plan(plan_a, orpt_underlying=shared_underlying)
    ctx_b = _build_context_from_plan(plan_b, context_id="m10-second-instance", orpt_underlying=shared_underlying)

    assert ctx_a.orpt_observation.underlying_observation is shared_underlying
    assert ctx_b.orpt_observation.underlying_observation is shared_underlying
    assert ctx_a.context_id != ctx_b.context_id
    assert ctx_a.source_plan_id != ctx_b.source_plan_id
    assert ctx_a.context_hash != ctx_b.context_hash


def test_multiple_instrument_isolation() -> None:
    ctx = _build_context(underlying="NSE:BANKNIFTY", selected_symbol="BANKNIFTY_FAKE_CALL")

    assert ctx.context_status is OpeningContextStatus.BLOCKED_OPENING_CONTEXT
    assert {"UNDERLYING_INSTRUMENT_MISMATCH", "SELECTED_CONTRACT_MISMATCH"} <= {item.code for item in ctx.data_quality_failures}


def test_observation_order_for_equivalent_candidates_does_not_change_hash_and_material_changes_do() -> None:
    plan = premarket.build_s23_bull_call_premarket_plan()
    t1 = _ts(plan.planned_values.normal_orpt)
    t2 = t1 + timedelta(seconds=1)
    a = _build_context(candidate_timestamps=(t1, t2))
    b = _build_context(candidate_timestamps=(t2, t1))
    changed = _build_context(opening_price=22425.0)

    assert a.context_hash == b.context_hash
    assert a.context_hash != changed.context_hash


def test_diagnostics_file_paths_and_strategy_mutable_state_do_not_enter_hash() -> None:
    a = _build_context(performance={"diagnostic_path": "C:/tmp/a", "duration": 1})
    b = _build_context(performance={"diagnostic_path": "D:/other/b", "duration": 999})

    assert a.context_hash == b.context_hash


def test_no_broker_execution_lifecycle_filesystem_or_runtime_in_generic_builder() -> None:
    source = Path("src/tfis/opening/context_builder.py").read_text(encoding="utf-8")

    assert "S23" not in source
    assert "S21" not in source
    assert "tfis.paper" not in source
    assert "broker" not in source.lower()
    assert "place_order" not in source
    assert "Lifecycle" not in source
    assert "Target" not in source
    assert "MSL" not in source
    assert "evaluate_legacy_gap_missed_entry" not in source
    assert "write_text" not in source
    assert "eval(" not in source
    assert "exec(" not in source


def test_no_filesystem_persistence_when_building_context(monkeypatch) -> None:
    def fail_write(self, *args, **kwargs):
        raise AssertionError(f"unexpected write: {self}")

    monkeypatch.setattr(Path, "write_text", fail_write)

    assert opening.build_s23_bear_call_opening_context().context_status is OpeningContextStatus.COMPLETE


def test_existing_s23_premarket_and_vertical_hashes_remain_unchanged() -> None:
    assert premarket.build_s23_bull_call_premarket_plan().plan_hash == BULL_M9_PLAN_HASH
    assert premarket.build_s23_bear_call_premarket_plan().plan_hash == BEAR_M9_PLAN_HASH
    assert vertical.run_s23_bull_call_vertical_slice().deterministic_hash == BULL_M3_HASH
    assert m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture").deterministic_hash == BULL_M5_HASH
    assert m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture").deterministic_hash == BEAR_M5_HASH


def _build_context(**kwargs):
    plan = premarket.build_s23_bull_call_premarket_plan()
    return _build_context_from_plan(plan, **kwargs)


def _build_context_from_plan(plan, **kwargs):
    open_ts = _ts(time(9, 15))
    orpt_ts = _ts(plan.planned_values.normal_orpt) + timedelta(seconds=kwargs.get("orpt_offset_seconds", 0))
    rc_ts = _ts(plan.planned_values.rc_time)
    selected = plan.contract_resolution.selected_contract
    opening_quote = kwargs.get("opening_quote", True)
    selected_symbol = kwargs.get("selected_symbol", selected.symbol)
    underlying = kwargs.get("underlying", plan.underlying_instrument)
    candidate_timestamps = kwargs.get("candidate_timestamps", (orpt_ts,))
    orpt_underlying = kwargs.get("orpt_underlying", _quote(plan.underlying_instrument, 22420.0, orpt_ts, OpeningTimestampClassification.ORPT_OBSERVATION, candidate_timestamps=candidate_timestamps))
    observations = OpeningContextObservations(
        scheduled_exchange_open_time=time(9, 15),
        official_exchange_open_timestamp=open_ts if kwargs.get("official", True) else None,
        first_local_quote_timestamp=open_ts,
        opening_bar_timestamp=open_ts if kwargs.get("timestamp_classification") is OpeningTimestampClassification.DERIVED_OPENING_BAR else None,
        timestamp_classification=kwargs.get("timestamp_classification", OpeningTimestampClassification.OFFICIAL_EXCHANGE_OPEN),
        underlying_opening=_quote(underlying, kwargs.get("opening_price", 22410.0), open_ts, kwargs.get("timestamp_classification", OpeningTimestampClassification.OFFICIAL_EXCHANGE_OPEN), freshness=kwargs.get("freshness", OpeningFreshnessStatus.FRESH)) if opening_quote else None,
        selected_contract_opening=_quote(selected_symbol, 265.0, open_ts, OpeningTimestampClassification.FIRST_COMPLETE_LOCAL_QUOTE, bid=264.0, ask=266.0, oi=999999.0 if kwargs.get("oi", True) else None, provenance=kwargs.get("provenance", "TEST_FIXTURE")),
        orpt_underlying=orpt_underlying if kwargs.get("orpt", True) else None,
        orpt_selected_contract=_quote(selected.symbol, 266.0, orpt_ts, OpeningTimestampClassification.ORPT_OBSERVATION, bid=265.0, ask=267.0, oi=999999.0, candidate_timestamps=candidate_timestamps if kwargs.get("duplicate_candidates") else (orpt_ts,)) if kwargs.get("orpt", True) else None,
        rc_underlying=_quote(plan.underlying_instrument, 22425.0, rc_ts, OpeningTimestampClassification.RC_OBSERVATION) if kwargs.get("rc", True) else None,
        rc_selected_contract=_quote(selected.symbol, 266.5, rc_ts, OpeningTimestampClassification.RC_OBSERVATION, bid=265.5, ask=267.5, oi=999999.0) if kwargs.get("rc", True) else None,
        rc_required=kwargs.get("rc_required", True),
    )
    if kwargs.get("duplicate_candidates"):
        observations = replace(
            observations,
            orpt_selected_contract=replace(observations.orpt_selected_contract, candidate_timestamps=(orpt_ts, orpt_ts)),
        )
    return OpeningMarketContextBuilder().build(
        OpeningContextBuildInput(
            kwargs.get("context_id", "m10-test-context"),
            "NSE",
            "TEST_SESSION",
            plan,
            observations,
            OpeningGapPolicy("test.opening_gap", "fixture_previous_close", kwargs.get("comparison_value", 22400.0), abnormal_gap_threshold_pct=kwargs.get("abnormal_pct")),
            expected_source_plan_hash=kwargs.get("expected_hash", plan.plan_hash),
            observed_trading_date=kwargs.get("observed_date", plan.trading_date),
            performance_diagnostics=kwargs.get("performance", {}),
        )
    )


def _quote(instrument, ltp, ts, classification, *, bid=None, ask=None, oi=None, freshness=OpeningFreshnessStatus.FRESH, provenance="TEST_FIXTURE", candidate_timestamps=None):
    return OpeningQuoteEvidence(
        instrument,
        ltp,
        bid,
        ask,
        oi,
        "LOTS" if oi is not None else None,
        ts,
        freshness,
        provenance,
        classification,
        candidate_timestamps=tuple(candidate_timestamps or (ts,)),
        selection_policy_identity="test.exact_timestamp",
        selection_reason="test fixture",
    )


def _ts(value) -> datetime:
    if isinstance(value, time):
        return datetime.combine(date(2026, 7, 30), value, tzinfo=ZoneInfo("Asia/Kolkata"))
    return datetime.combine(date(2026, 7, 30), value, tzinfo=ZoneInfo("Asia/Kolkata"))
