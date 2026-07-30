from __future__ import annotations

from datetime import date, datetime, time
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from tfis.adapters.legacy_policies.s23_premarket_plan import (
    build_s23_bear_call_premarket_plan,
    build_s23_bull_call_premarket_plan,
)
from tfis.domain import OptionType, Segment, TFISContractIdentity, TFISProductType
from tfis.domain.opening_market_context import (
    OpeningBarEvidence,
    OpeningFreshnessStatus,
    OpeningMarketContext,
    OpeningQuoteEvidence,
    OpeningTimestampClassification,
)
from tfis.opening import OpeningContextBuildInput, OpeningContextObservations, OpeningGapPolicy, OpeningMarketContextBuilder


ROOT = Path(__file__).resolve().parents[4]
M7_PACKET = ROOT / "reports" / "phase3d" / "milestone7_s23_real_capture_packet.json"
S23_OPENING_GAP_POLICY = "legacy.s23.opening_gap.fixture_v1"


def build_s23_bull_call_opening_context() -> OpeningMarketContext:
    plan = build_s23_bull_call_premarket_plan()
    return _build_fixture_context("S23_BULL_CALL_OPENING", plan, opening_price=22440.0, selected_ltp=265.0, comparison_value=22400.0)


def build_s23_bear_call_opening_context() -> OpeningMarketContext:
    plan = build_s23_bear_call_premarket_plan()
    return _build_fixture_context("S23_BEAR_CALL_OPENING", plan, opening_price=22360.0, selected_ltp=263.5, comparison_value=22400.0)


def build_s23_partial_real_opening_context() -> OpeningMarketContext:
    payload = json.loads(M7_PACKET.read_text(encoding="utf-8"))
    plan = build_s23_bull_call_premarket_plan()
    plan_selected = TFISContractIdentity(
        symbol="NIFTY_20260609_22650_CE",
        segment=Segment.OPTIONS_SELL,
        product_type=TFISProductType.OPTION_SELLING,
        expiry=date(2026, 6, 9),
        strike=22650.0,
        option_type=OptionType.CALL.value,
        metadata={"source": "M7_PARTIAL_REAL_CAPTURE"},
    )
    plan = _replace_plan_selected_contract_for_partial_real(plan, plan_selected, date(2026, 6, 5), "m7-partial-real-plan-hash")
    opening = payload["opening_context"]
    orpt = payload["orpt_observation"]
    rc = payload["rc_observation"]
    opening_bar = opening["underlying_opening_price"]
    open_ts = datetime.fromisoformat(opening_bar["captured_at"])
    observations = OpeningContextObservations(
        scheduled_exchange_open_time=time(9, 15),
        official_exchange_open_timestamp=None,
        first_local_quote_timestamp=open_ts,
        opening_bar_timestamp=open_ts,
        timestamp_classification=OpeningTimestampClassification.DERIVED_OPENING_BAR,
        underlying_opening=OpeningBarEvidence(
            "NSE:NIFTY",
            opening_bar["open"],
            opening_bar["high"],
            opening_bar["low"],
            opening_bar["close"],
            open_ts,
            "M7_PARTIAL_REAL_CAPTURE",
        ),
        selected_contract_opening=None,
        orpt_underlying=_bar_from_m7("NSE:NIFTY", orpt["underlying_observation"], OpeningTimestampClassification.ORPT_OBSERVATION),
        orpt_selected_contract=None,
        rc_underlying=_bar_from_m7("NSE:NIFTY", rc["underlying_observation"], OpeningTimestampClassification.RC_OBSERVATION),
        rc_selected_contract=_quote_from_m7(rc["selected_contract_observation"], OpeningTimestampClassification.RC_OBSERVATION),
        evidence_classification="PARTIAL_CAPTURE",
        derived_fields=("exchange_open_timestamp_from_configured_market_open", "opening_underlying_bar_from_first_capture_window"),
        supplemented_fields=(),
    )
    return OpeningMarketContextBuilder().build(
        OpeningContextBuildInput(
            "m10-s23-partial-real-opening-context",
            "NSE",
            payload["enablement"]["session_id"],
            plan,
            observations,
            OpeningGapPolicy(S23_OPENING_GAP_POLICY, "M7_PREVIOUS_CLOSE_UNAVAILABLE", None),
            expected_source_plan_hash=plan.plan_hash,
            observed_trading_date=date(2026, 6, 5),
        )
    )


def _build_fixture_context(label: str, plan, *, opening_price: float, selected_ltp: float, comparison_value: float) -> OpeningMarketContext:
    tz = ZoneInfo("Asia/Kolkata")
    open_ts = datetime.combine(plan.trading_date, time(9, 15), tzinfo=tz)
    orpt_ts = datetime.combine(plan.trading_date, plan.planned_values.normal_orpt, tzinfo=tz)
    rc_ts = datetime.combine(plan.trading_date, plan.planned_values.rc_time, tzinfo=tz)
    selected = plan.contract_resolution.selected_contract
    observations = OpeningContextObservations(
        scheduled_exchange_open_time=time(9, 15),
        official_exchange_open_timestamp=open_ts,
        first_local_quote_timestamp=open_ts,
        opening_bar_timestamp=open_ts,
        timestamp_classification=OpeningTimestampClassification.OFFICIAL_EXCHANGE_OPEN,
        underlying_opening=_quote(plan.underlying_instrument, opening_price, open_ts, OpeningTimestampClassification.OFFICIAL_EXCHANGE_OPEN),
        selected_contract_opening=_quote(selected.symbol, selected_ltp, open_ts, OpeningTimestampClassification.FIRST_COMPLETE_LOCAL_QUOTE, bid=selected_ltp - 1, ask=selected_ltp + 1, oi=plan.contract_resolution.oi),
        orpt_underlying=_quote(plan.underlying_instrument, opening_price + 5, orpt_ts, OpeningTimestampClassification.ORPT_OBSERVATION),
        orpt_selected_contract=_quote(selected.symbol, selected_ltp + 1, orpt_ts, OpeningTimestampClassification.ORPT_OBSERVATION, bid=selected_ltp, ask=selected_ltp + 2, oi=plan.contract_resolution.oi),
        rc_underlying=_quote(plan.underlying_instrument, opening_price + 8, rc_ts, OpeningTimestampClassification.RC_OBSERVATION),
        rc_selected_contract=_quote(selected.symbol, selected_ltp + 1.5, rc_ts, OpeningTimestampClassification.RC_OBSERVATION, bid=selected_ltp + 0.5, ask=selected_ltp + 2.5, oi=plan.contract_resolution.oi),
        evidence_classification="SYNTHETIC_FIXTURE",
    )
    return OpeningMarketContextBuilder().build(
        OpeningContextBuildInput(
            f"m10-{label.lower()}",
            "NSE",
            f"{label}_FIXTURE_SESSION",
            plan,
            observations,
            OpeningGapPolicy(S23_OPENING_GAP_POLICY, "PREVIOUS_CLOSE_FIXTURE", comparison_value, abnormal_gap_threshold_pct=5.0),
            expected_source_plan_hash=plan.plan_hash,
            observed_trading_date=plan.trading_date,
        )
    )


def _quote(instrument: str, ltp: float, ts: datetime, classification: OpeningTimestampClassification, *, bid: float | None = None, ask: float | None = None, oi: float | None = None) -> OpeningQuoteEvidence:
    return OpeningQuoteEvidence(instrument, ltp, bid, ask, oi, "LOTS" if oi is not None else None, ts, OpeningFreshnessStatus.FRESH, "S23_OPENING_FIXTURE", classification, candidate_timestamps=(ts,), selection_policy_identity="exact_timestamp_fixture", selection_reason="exact configured timestamp")


def _quote_from_m7(data: dict, classification: OpeningTimestampClassification) -> OpeningQuoteEvidence:
    return OpeningQuoteEvidence(data["symbol"], data.get("ltp"), data.get("bid"), data.get("ask"), data.get("oi"), "LOTS", datetime.fromisoformat(data["timestamp"]), OpeningFreshnessStatus.FRESH, "M7_PARTIAL_REAL_CAPTURE", classification, source_label=data.get("source_symbol"))


def _bar_from_m7(instrument: str, data: dict, classification: OpeningTimestampClassification) -> OpeningBarEvidence:
    return OpeningBarEvidence(instrument, data.get("open"), data.get("high"), data.get("low"), data.get("close"), datetime.fromisoformat(data["captured_at"]), "M7_PARTIAL_REAL_CAPTURE", classification)


def _replace_plan_selected_contract_for_partial_real(plan, selected: TFISContractIdentity, trading_date: date, plan_hash: str):
    from dataclasses import replace
    from tfis.domain.premarket_plan import PreMarketContractResolution, PreMarketPlannedValues

    return replace(
        plan,
        trading_date=trading_date,
        planned_values=replace(plan.planned_values, normal_orpt=time(9, 24, 59), rc_time=time(9, 29, 59)),
        contract_resolution=PreMarketContractResolution(
            expiry_candidates=(selected.expiry,),
            strike_candidates=(selected.strike,),
            selected_expiry=selected.expiry,
            selected_strike=selected.strike,
            selected_contract=selected,
            premium=None,
            oi=None,
            oi_unit="LOTS",
            qualification_evidence={"source": "M7_PARTIAL_REAL_CAPTURE"},
        ),
        plan_hash=plan_hash,
        business_hash=plan_hash,
    )
