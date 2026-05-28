from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tfis.domain import MarketLevels, StrategyExpiryPolicy, StrategyRule
from tfis.domain.enums import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment
from tfis.monthly_status import MonthlyStatusResult
from tfis.paper import (
    DeterministicExpiryCalendar,
    EventEnvelope,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperContractSelectionFailureCode,
    PaperEventType,
    S23CollectedSnapshotInputs,
    S23FyersSnapshotArtifactSet,
    S23FyersSnapshotCollectorError,
    S23FyersSnapshotPreflightSummary,
    S23PaperContractSelectionRanking,
    S23PaperContractSelectionResult,
    S23PaperExpiryGovernance,
    S23PaperLivePreludeResult,
    S23PaperPreludeMode,
    S23PaperPreludeSessionContext,
    S23SnapshotValidationHarness,
    S23SnapshotValidationWarning,
)


IST = ZoneInfo("Asia/Kolkata")


def _ts(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, 8, 9, minute, second, tzinfo=IST)


def _strategy() -> StrategyRule:
    return StrategyRule(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        segment=Segment.OPTIONS_SELL,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
            forced_close_time=time(15, 15),
            no_carry_past_expiry=True,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        option_type=OptionType.PUT,
        entry_time=time(9, 25),
        recalculation_time=time(9, 30),
        start_strike_formula="PRV_2DLL",
        end_strike_formula="PRV_2DHH",
        ideal_premium_formula="ENTRY",
        minimum_premium_formula="ENTRY - 10%",
        minimum_oi=500,
        entry_formula="ENTRY",
        target_formula="80",
        stoploss_formula="320",
        carry_forward_allowed=True,
    )


def _context(at: datetime) -> S23PaperPreludeSessionContext:
    return S23PaperPreludeSessionContext(
        session_date=at.date(),
        timezone="Asia/Kolkata",
        generated_at=at,
        source_type="unit_test_snapshot_validation",
        source_id_prefix="snapshot-validation",
    )


def _chain(
    *,
    captured_at: datetime,
    selected_symbol: str,
    selected_ltp: float,
    selected_oi: float,
) -> OptionChainSnapshotEvent:
    contracts = (
        OptionChainContract(
            symbol=selected_symbol,
            option_type=OptionType.PUT,
            strike=22400.0,
            expiry=date(2026, 5, 12),
            bid=selected_ltp - 1.0,
            ask=selected_ltp + 1.0,
            ltp=selected_ltp,
            oi=selected_oi,
            volume=120.0,
        ),
        OptionChainContract(
            symbol="NIFTY_20260512_22500_PE",
            option_type=OptionType.PUT,
            strike=22500.0,
            expiry=date(2026, 5, 12),
            bid=196.0,
            ask=198.0,
            ltp=197.0,
            oi=900.0,
            volume=80.0,
        ),
    )
    return OptionChainSnapshotEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
            session_date=captured_at.date(),
            effective_timestamp=captured_at - timedelta(seconds=1),
            captured_at=captured_at,
            timezone="Asia/Kolkata",
            source_type="unit_test",
            source_id="unit-test-chain",
            synthetic_fixture=True,
            normalized_by="unit-test",
        ),
        underlying_symbol="NIFTY",
        expiry=date(2026, 5, 12),
        contracts=contracts,
    )


def _selection(symbol: str, premium: float, oi: float, rejected: dict[str, int] | None = None) -> S23PaperContractSelectionResult:
    return S23PaperContractSelectionResult(
        selected=True,
        failure_code=None,
        selection_reason="Selected contract closest to ideal premium.",
        selected_contract_symbol=symbol,
        expiry_date=date(2026, 5, 12),
        strike=22400.0 if "22400" in symbol else 22500.0,
        option_type=OptionType.PUT,
        premium_used=premium,
        oi_used=oi,
        ranked_candidate_count=2,
        rejected_candidate_counts=rejected or {"option_type_mismatch": 1},
        ranking=S23PaperContractSelectionRanking(
            premium_distance=0.0,
            oi_used=oi,
            tie_break_strike=22400.0 if "22400" in symbol else 22500.0,
            tie_break_symbol=symbol,
        ),
        selected_contract=OptionChainContract(
            symbol=symbol,
            option_type=OptionType.PUT,
            strike=22400.0 if "22400" in symbol else 22500.0,
            expiry=date(2026, 5, 12),
            bid=premium - 1.0,
            ask=premium + 1.0,
            ltp=premium,
            oi=oi,
            volume=100.0,
        ),
    )


def _prelude_result(symbol: str, premium: float, oi: float) -> S23PaperLivePreludeResult:
    context = _context(_ts(30))
    envelope = EventEnvelope(
        event_type=PaperEventType.CALENDAR_CONTEXT,
        session_date=context.session_date,
        effective_timestamp=context.generated_at,
        captured_at=context.generated_at,
        timezone=context.timezone,
        source_type="unit_test",
        source_id="unit-test-calendar",
        synthetic_fixture=True,
        normalized_by="unit-test",
    )
    monthly_envelope = EventEnvelope(
        event_type=PaperEventType.MONTHLY_STATUS_INPUT,
        session_date=context.session_date,
        effective_timestamp=context.generated_at,
        captured_at=context.generated_at,
        timezone=context.timezone,
        source_type="unit_test",
        source_id="unit-test-monthly",
        synthetic_fixture=True,
        normalized_by="unit-test",
    )
    from tfis.paper.models import CalendarContextEvent, MonthlyStatusInputEvent

    return S23PaperLivePreludeResult(
        mode=S23PaperPreludeMode.FRESH_ENTRY,
        selected_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        calendar_context_event=CalendarContextEvent(
            envelope=envelope,
            is_holiday=False,
            is_expiry_day=False,
            weekly_expiry=date(2026, 5, 12),
            market_open=time(9, 15),
            market_close=time(15, 30),
        ),
        monthly_status_event=MonthlyStatusInputEvent(
            envelope=monthly_envelope,
            monthly_status=MonthlyStatus.BEAR,
            status_source="unit_test",
            reference_date=date(2026, 5, 8),
            threshold_version="v1",
        ),
        snapshot_events=(),
        trade_plan_event=None,
        selected_contract_event=None,
        governance_events=(),
        resume_event=None,
        contract_selection=_selection(symbol, premium, oi),
        trade_plan=None,
        selected_contract_provenance="runtime_option_chain_selection",
    )


def _artifact(sample_dir: Path, *, at: datetime, symbol: str, premium: float, oi: float, stale: bool = False) -> S23FyersSnapshotArtifactSet:
    context = _context(at)
    captured_at = at - timedelta(seconds=10 if stale else 1)
    chain = _chain(
        captured_at=captured_at,
        selected_symbol=symbol,
        selected_ltp=premium,
        selected_oi=oi,
    )
    governance = S23PaperExpiryGovernance(
        DeterministicExpiryCalendar(
            explicit_expiries={(ExpiryType.WEEKLY, context.session_date): date(2026, 5, 12)}
        )
    )
    from tfis.paper.models import UnderlyingQuoteEvent

    quote = UnderlyingQuoteEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.UNDERLYING_QUOTE,
            session_date=context.session_date,
            effective_timestamp=at,
            captured_at=at,
            timezone="Asia/Kolkata",
            source_type="unit_test",
            source_id="unit-test-underlying",
            synthetic_fixture=True,
            normalized_by="unit-test",
        ),
        symbol="NIFTY",
        ltp=22440.0,
    )
    return S23FyersSnapshotArtifactSet(
        session_directory=sample_dir,
        summary_path=sample_dir / "summary.json",
        normalized_underlying_snapshot_path=sample_dir / "underlying.json",
        normalized_underlying_bars_path=sample_dir / "underlying_bars.json",
        normalized_option_chain_snapshot_path=sample_dir / "chain.json",
        summary=S23FyersSnapshotPreflightSummary(
            artifact_version=1,
            provider="fake",
            session_id=sample_dir.name,
            session_date=context.session_date,
            config_path="config/paper.s23.yaml",
            strategy_path="strategy",
            runtime_fixture_path="runtime_fixture.json",
            expected_session_directory=str(sample_dir),
            artifact_root=str(sample_dir.parent),
            uses_payload_fixture=True,
            will_connect_to_broker=False,
            strategy_code="S23",
            strategy_branch_reference="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
            symbol="NIFTY",
            contract_cycle="WEEKLY",
            mode="paper",
            paper_mode_enabled=True,
            no_live_orders_allowed=True,
            kill_switch_enabled=True,
            session_kill_switch_active=False,
            weekly_expiry=date(2026, 5, 12),
            underlying_quote_collected=True,
            option_chain_collected=True,
            option_chain_contract_count=len(chain.contracts),
            option_chain_has_complete_oi=True,
            dry_run_build_prelude_requested=True,
            prelude_generated=True,
            preflight_status="READY",
            can_run=True,
            issues=(),
            explicit_disclaimer="test",
        ),
        generated_prelude_events_path=sample_dir / "generated.jsonl",
        generated_prelude_provenance_path=sample_dir / "provenance.json",
        generated_governance_events_path=None,
        collected_inputs=S23CollectedSnapshotInputs(
            session_context=context,
            strategy_rule=_strategy(),
            underlying_quote=quote,
            underlying_bars=(),
            option_chain_snapshot=chain,
            expiry_governance=governance,
            weekly_expiry=date(2026, 5, 12),
        ),
        prelude_result=_prelude_result(symbol, premium, oi),
    )


@dataclass
class _FakeCollector:
    sequence: list[object]
    calls: int = 0

    def collect_from_files(self, **kwargs) -> S23FyersSnapshotArtifactSet:
        item = self.sequence[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def _runtime_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "runtime_fixture.json"
    path.write_text(
        '{"session_date":"2026-05-08","generated_at":"2026-05-08T09:30:03+05:30"}',
        encoding="utf-8",
    )
    return path


def test_harness_generates_stable_report(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path)
    collector = _FakeCollector(
        [
            _artifact(tmp_path / "sample1", at=_ts(30, 1), symbol="NIFTY_20260512_22400_PE", premium=200.0, oi=1200.0),
            _artifact(tmp_path / "sample2", at=_ts(31, 1), symbol="NIFTY_20260512_22400_PE", premium=201.0, oi=1210.0),
        ]
    )
    harness = S23SnapshotValidationHarness(
        artifact_root=tmp_path / "artifacts",
        collector=collector,
        sleep_fn=lambda _: None,
    )

    artifact_set = harness.run_from_files(
        config_path="config/paper.s23.yaml",
        strategy_path="strategy",
        runtime_fixture_path=fixture,
        samples=2,
        interval_seconds=0,
    )

    assert artifact_set.report.aggregate_metrics.total_samples == 2
    assert artifact_set.report.aggregate_metrics.successful_samples == 2
    assert artifact_set.report.aggregate_metrics.contract_change_count == 0
    assert artifact_set.report.samples[1].premium_drift == pytest.approx(1.0)
    assert artifact_set.report_json_path.exists()
    assert artifact_set.report_markdown_path.exists()
    assert artifact_set.samples_jsonl_path.exists()


def test_harness_detects_contract_oscillation(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path)
    collector = _FakeCollector(
        [
            _artifact(tmp_path / "sample1", at=_ts(30, 1), symbol="NIFTY_20260512_22400_PE", premium=200.0, oi=1200.0),
            _artifact(tmp_path / "sample2", at=_ts(31, 1), symbol="NIFTY_20260512_22500_PE", premium=199.0, oi=1400.0),
        ]
    )
    harness = S23SnapshotValidationHarness(
        artifact_root=tmp_path / "artifacts",
        collector=collector,
        sleep_fn=lambda _: None,
    )

    report = harness.run_from_files(
        config_path="config/paper.s23.yaml",
        strategy_path="strategy",
        runtime_fixture_path=fixture,
        samples=2,
        interval_seconds=0,
    ).report

    assert report.aggregate_metrics.contract_change_count == 1
    assert S23SnapshotValidationWarning.CONTRACT_OSCILLATION in report.samples[1].warnings


def test_harness_warns_on_missing_oi_failure(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path)
    collector = _FakeCollector(
        [S23FyersSnapshotCollectorError("MISSING_CONTRACT_OI", "Option-chain candidates are missing OI.")]
    )
    harness = S23SnapshotValidationHarness(
        artifact_root=tmp_path / "artifacts",
        collector=collector,
        sleep_fn=lambda _: None,
    )

    report = harness.run_from_files(
        config_path="config/paper.s23.yaml",
        strategy_path="strategy",
        runtime_fixture_path=fixture,
        samples=1,
        interval_seconds=0,
    ).report

    assert report.aggregate_metrics.missing_oi_count == 1
    assert report.samples[0].warnings == (S23SnapshotValidationWarning.MISSING_OI,)


def test_harness_warns_on_empty_chain_failure(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path)
    collector = _FakeCollector(
        [S23FyersSnapshotCollectorError("OPTION_CHAIN_MISSING", "No contracts were returned.")]
    )
    harness = S23SnapshotValidationHarness(
        artifact_root=tmp_path / "artifacts",
        collector=collector,
        sleep_fn=lambda _: None,
    )

    report = harness.run_from_files(
        config_path="config/paper.s23.yaml",
        strategy_path="strategy",
        runtime_fixture_path=fixture,
        samples=1,
        interval_seconds=0,
    ).report

    assert report.aggregate_metrics.empty_chain_count == 1
    assert report.samples[0].warnings == (S23SnapshotValidationWarning.EMPTY_CHAIN,)


def test_harness_warns_on_stale_chain_and_prelude_failure(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path)
    collector = _FakeCollector(
        [
            _artifact(tmp_path / "sample1", at=_ts(30, 1), symbol="NIFTY_20260512_22400_PE", premium=200.0, oi=1200.0, stale=True),
            S23FyersSnapshotCollectorError("UNSUPPORTED_WORKBOOK_PATH", "Blocked workbook path."),
        ]
    )
    harness = S23SnapshotValidationHarness(
        artifact_root=tmp_path / "artifacts",
        collector=collector,
        sleep_fn=lambda _: None,
    )

    report = harness.run_from_files(
        config_path="config/paper.s23.yaml",
        strategy_path="strategy",
        runtime_fixture_path=fixture,
        samples=2,
        interval_seconds=0,
    ).report

    assert S23SnapshotValidationWarning.STALE_CHAIN in report.samples[0].warnings
    assert report.aggregate_metrics.prelude_build_failure_count == 1
    assert report.samples[1].warnings == (S23SnapshotValidationWarning.PRELUDE_BUILD_FAILURE,)
