from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping

from tfis.domain.opening_market_context import (
    OpeningBarEvidence,
    OpeningConsumerReadiness,
    OpeningContextStatus,
    OpeningFailure,
    OpeningFreshnessStatus,
    OpeningGapClassification,
    OpeningGapContext,
    OpeningGapDirection,
    OpeningMarketContext,
    OpeningObservationAvailability,
    OpeningQuoteEvidence,
    OpeningTimestampClassification,
    TimedOpeningObservation,
)
from tfis.domain.premarket_plan import PreMarketStrategyPlan


@dataclass(frozen=True, slots=True)
class OpeningGapPolicy:
    policy_identity: str
    comparison_reference: str
    comparison_value: float | None
    no_gap_threshold_points: float = 0.0
    abnormal_gap_threshold_pct: float | None = None


@dataclass(frozen=True, slots=True)
class OpeningContextObservations:
    scheduled_exchange_open_time: time | None
    official_exchange_open_timestamp: datetime | None
    first_local_quote_timestamp: datetime | None
    opening_bar_timestamp: datetime | None
    timestamp_classification: OpeningTimestampClassification
    underlying_opening: OpeningQuoteEvidence | OpeningBarEvidence | None
    selected_contract_opening: OpeningQuoteEvidence | None
    orpt_underlying: OpeningQuoteEvidence | OpeningBarEvidence | None
    orpt_selected_contract: OpeningQuoteEvidence | None
    rc_underlying: OpeningQuoteEvidence | OpeningBarEvidence | None = None
    rc_selected_contract: OpeningQuoteEvidence | None = None
    rc_required: bool = True
    oi_required: bool = True
    allowed_window_seconds: int = 60
    evidence_classification: str = "SYNTHETIC_FIXTURE"
    derived_fields: tuple[str, ...] = ()
    supplemented_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OpeningContextBuildInput:
    context_id: str
    exchange: str
    session_id: str
    source_plan: PreMarketStrategyPlan
    observations: OpeningContextObservations
    gap_policy: OpeningGapPolicy
    expected_source_plan_hash: str | None = None
    observed_trading_date: Any | None = None
    performance_diagnostics: Mapping[str, float | int] = MappingProxyType({})


class OpeningMarketContextBuilder:
    schema_version = "tfis.opening_market_context.v1"

    def build(self, build_input: OpeningContextBuildInput) -> OpeningMarketContext:
        started = perf_counter()
        plan = build_input.source_plan
        obs = build_input.observations
        failures = self._failures(build_input)
        gap_started = perf_counter()
        gap = self._classify_gap(obs.underlying_opening, build_input.gap_policy)
        gap_seconds = perf_counter() - gap_started
        readiness = self._readiness(obs, failures, gap)
        status = self._status(readiness, failures)
        missing = tuple(failure.field for failure in failures)
        stale = tuple(failure.field for failure in failures if failure.code == "STALE_QUOTE")
        selected = plan.contract_resolution.selected_contract
        if selected is None:
            raise ValueError("source plan must contain selected contract")
        first_ts = obs.first_local_quote_timestamp or _quote_ts(obs.underlying_opening)
        official = obs.official_exchange_open_timestamp
        opening_bar_ts = obs.opening_bar_timestamp or (obs.underlying_opening.bar_timestamp if isinstance(obs.underlying_opening, OpeningBarEvidence) else None)
        perf = {
            "observation_normalization_seconds": 0.0,
            "gap_classification_seconds": gap_seconds,
            "context_construction_seconds": perf_counter() - started,
            "evidence_serialization_bytes": 0,
            "hash_generation_seconds": 0.0,
            **dict(build_input.performance_diagnostics),
        }
        return OpeningMarketContext(
            context_id=build_input.context_id,
            schema_version=self.schema_version,
            trading_date=plan.trading_date,
            exchange=build_input.exchange,
            session_id=build_input.session_id,
            underlying_instrument=plan.underlying_instrument or "",
            selected_contract=selected,
            source_plan_id=plan.plan_id,
            source_plan_hash=plan.plan_hash,
            scheduled_exchange_open_time=obs.scheduled_exchange_open_time,
            official_exchange_open_timestamp=official,
            first_local_quote_timestamp=first_ts,
            opening_bar_timestamp=opening_bar_ts,
            timestamp_classification=obs.timestamp_classification,
            underlying_opening_evidence=obs.underlying_opening,
            selected_contract_opening_evidence=obs.selected_contract_opening,
            gap_context=gap,
            orpt_observation=self._timed("ORPT", plan.planned_values.normal_orpt, obs.orpt_underlying, obs.orpt_selected_contract),
            rc_observation=self._timed("RC", plan.planned_values.rc_time, obs.rc_underlying, obs.rc_selected_contract, applicable=obs.rc_required),
            consumer_readiness=readiness,
            context_status=status,
            missing_fields=missing,
            derived_fields=obs.derived_fields,
            supplemented_fields=obs.supplemented_fields,
            stale_fields=stale,
            data_quality_failures=tuple(failures),
            evidence_classification=obs.evidence_classification,
            performance=perf,
        )

    def _failures(self, build_input: OpeningContextBuildInput) -> list[OpeningFailure]:
        plan = build_input.source_plan
        obs = build_input.observations
        failures: list[OpeningFailure] = []
        if not plan.plan_id or not plan.plan_hash:
            failures.append(OpeningFailure("MISSING_SOURCE_PLAN", "source_plan", "Source PreMarketStrategyPlan is required."))
        if build_input.expected_source_plan_hash and build_input.expected_source_plan_hash != plan.plan_hash:
            failures.append(OpeningFailure("PLAN_HASH_MISMATCH", "source_plan_hash", "Expected source plan hash does not match source plan."))
        if build_input.observed_trading_date is not None and build_input.observed_trading_date != plan.trading_date:
            failures.append(OpeningFailure("TRADING_DATE_MISMATCH", "trading_date", "Observed trading date does not match source plan."))
        if build_input.gap_policy.comparison_value is None:
            failures.append(OpeningFailure("INSUFFICIENT_GAP_REFERENCE", "gap_reference", "Gap comparison value is required."))
        if plan.underlying_instrument and obs.underlying_opening and obs.underlying_opening.instrument != plan.underlying_instrument:
            failures.append(OpeningFailure("UNDERLYING_INSTRUMENT_MISMATCH", "underlying_opening", "Underlying observation does not match plan."))
        selected = plan.contract_resolution.selected_contract
        if selected and obs.selected_contract_opening and obs.selected_contract_opening.instrument != selected.symbol:
            failures.append(OpeningFailure("SELECTED_CONTRACT_MISMATCH", "selected_contract_opening", "Selected-contract observation does not match plan."))
        if obs.underlying_opening is None:
            failures.append(OpeningFailure("OPENING_QUOTE_MISSING", "underlying_opening", "Underlying opening observation is required."))
        if obs.underlying_opening and _freshness(obs.underlying_opening) is OpeningFreshnessStatus.STALE:
            failures.append(OpeningFailure("STALE_QUOTE", "underlying_opening", "Underlying opening observation is stale."))
        if obs.official_exchange_open_timestamp is None:
            failures.append(OpeningFailure("OFFICIAL_OPEN_UNAVAILABLE", "official_exchange_open_timestamp", "Official exchange open was unavailable; local/derived evidence is preserved."))
        if obs.orpt_underlying is None or obs.orpt_selected_contract is None:
            failures.append(OpeningFailure("ORPT_OBSERVATION_MISSING", "orpt_observation", "ORPT underlying and selected-contract observations are required for ORPT flow."))
        if obs.rc_required and (obs.rc_underlying is None or obs.rc_selected_contract is None):
            failures.append(OpeningFailure("RC_OBSERVATION_MISSING", "rc_observation", "RC underlying and selected-contract observations are required for RC flow."))
        if obs.oi_required and (obs.selected_contract_opening is None or obs.selected_contract_opening.oi is None):
            failures.append(OpeningFailure("OI_UNAVAILABLE", "selected_contract_opening.oi", "Selected-contract opening OI is required by this context."))
        for field, quote in (
            ("selected_contract_opening", obs.selected_contract_opening),
            ("orpt_selected_contract", obs.orpt_selected_contract),
            ("rc_selected_contract", obs.rc_selected_contract),
        ):
            if quote and quote.provenance is None:
                failures.append(OpeningFailure("DATA_PROVENANCE_MISSING", field, "Observation provenance is required."))
        if obs.timestamp_classification is OpeningTimestampClassification.UNSUPPORTED:
            failures.append(OpeningFailure("UNSUPPORTED_TIMESTAMP_CLASSIFICATION", "timestamp_classification", "Timestamp classification is unsupported."))
        if obs.orpt_underlying and plan.planned_values.normal_orpt:
            self._window_failure(failures, "orpt_underlying", obs.orpt_underlying, plan.planned_values.normal_orpt, obs.allowed_window_seconds)
        if obs.rc_underlying and obs.rc_required and plan.planned_values.rc_time:
            self._window_failure(failures, "rc_underlying", obs.rc_underlying, plan.planned_values.rc_time, obs.allowed_window_seconds)
        self._duplicate_failure(failures, obs.orpt_selected_contract, "orpt_selected_contract")
        self._duplicate_failure(failures, obs.rc_selected_contract, "rc_selected_contract")
        return failures

    def _window_failure(self, failures: list[OpeningFailure], field: str, obs: Any, expected: time, allowed: int) -> None:
        ts = _quote_ts(obs)
        if ts is None:
            return
        expected_dt = ts.replace(hour=expected.hour, minute=expected.minute, second=expected.second, microsecond=0)
        if abs((ts - expected_dt).total_seconds()) > allowed:
            failures.append(OpeningFailure("OBSERVATION_OUTSIDE_WINDOW", field, "Observation timestamp is outside the permitted window."))

    def _duplicate_failure(self, failures: list[OpeningFailure], quote: OpeningQuoteEvidence | None, field: str) -> None:
        if quote and len(set(quote.candidate_timestamps)) != len(quote.candidate_timestamps):
            failures.append(OpeningFailure("DUPLICATE_CONFLICTING_OBSERVATION", field, "Candidate timestamps contain a duplicate/conflict."))

    def _classify_gap(self, opening: Any, policy: OpeningGapPolicy) -> OpeningGapContext:
        value = _opening_value(opening)
        if value is None or policy.comparison_value is None:
            return OpeningGapContext(OpeningGapClassification.INSUFFICIENT_EVIDENCE, OpeningGapDirection.UNKNOWN, policy.comparison_reference, policy.comparison_value, None, None, None, policy.policy_identity)
        amount = float(value) - float(policy.comparison_value)
        pct = (amount / float(policy.comparison_value)) * 100 if policy.comparison_value else None
        if policy.abnormal_gap_threshold_pct is not None and pct is not None and abs(pct) >= policy.abnormal_gap_threshold_pct:
            return OpeningGapContext(OpeningGapClassification.ABNORMAL_OPENING, OpeningGapDirection.UP if amount > 0 else OpeningGapDirection.DOWN, policy.comparison_reference, policy.comparison_value, amount, pct, "ABNORMAL_GAP_THRESHOLD", policy.policy_identity)
        if abs(amount) <= policy.no_gap_threshold_points:
            classification = OpeningGapClassification.NO_GAP
            direction = OpeningGapDirection.NONE
        elif amount > 0:
            classification = OpeningGapClassification.GAP_UP
            direction = OpeningGapDirection.UP
        else:
            classification = OpeningGapClassification.GAP_DOWN
            direction = OpeningGapDirection.DOWN
        return OpeningGapContext(classification, direction, policy.comparison_reference, policy.comparison_value, amount, pct, None, policy.policy_identity)

    def _readiness(self, obs: OpeningContextObservations, failures: list[OpeningFailure], gap: OpeningGapContext) -> OpeningConsumerReadiness:
        codes = {item.code for item in failures}
        normal = OpeningContextStatus.COMPLETE if not ({"OPENING_QUOTE_MISSING", "UNDERLYING_INSTRUMENT_MISMATCH"} & codes) else OpeningContextStatus.BLOCKED_OPENING_CONTEXT
        gme = OpeningContextStatus.COMPLETE if gap.classification is not OpeningGapClassification.INSUFFICIENT_EVIDENCE and "ORPT_OBSERVATION_MISSING" not in codes else OpeningContextStatus.PARTIAL
        orpt = OpeningContextStatus.COMPLETE if "ORPT_OBSERVATION_MISSING" not in codes else OpeningContextStatus.PARTIAL
        rc = OpeningContextStatus.NOT_APPLICABLE if not obs.rc_required else (OpeningContextStatus.COMPLETE if "RC_OBSERVATION_MISSING" not in codes else OpeningContextStatus.PARTIAL)
        carried = normal
        return OpeningConsumerReadiness(normal, gme, orpt, rc, carried, {item.field: item.reason for item in failures})

    def _status(self, readiness: OpeningConsumerReadiness, failures: list[OpeningFailure]) -> OpeningContextStatus:
        hard = {"MISSING_SOURCE_PLAN", "PLAN_HASH_MISMATCH", "TRADING_DATE_MISMATCH", "UNDERLYING_INSTRUMENT_MISMATCH", "SELECTED_CONTRACT_MISMATCH", "OPENING_QUOTE_MISSING", "UNSUPPORTED_TIMESTAMP_CLASSIFICATION", "OBSERVATION_OUTSIDE_WINDOW", "DUPLICATE_CONFLICTING_OBSERVATION"}
        if hard & {item.code for item in failures}:
            return OpeningContextStatus.BLOCKED_OPENING_CONTEXT
        if failures:
            return OpeningContextStatus.PARTIAL
        return OpeningContextStatus.COMPLETE

    def _timed(self, label: str, configured: time | None, underlying: Any, selected: Any, *, applicable: bool = True) -> TimedOpeningObservation:
        if not applicable:
            return TimedOpeningObservation(label, None, availability=OpeningObservationAvailability.NOT_APPLICABLE, policy_applicability="NOT_APPLICABLE")
        configured_dt = _quote_ts(underlying) or _quote_ts(selected)
        if configured and configured_dt:
            configured_dt = configured_dt.replace(hour=configured.hour, minute=configured.minute, second=configured.second, microsecond=0)
        availability = OpeningObservationAvailability.AVAILABLE if underlying and selected else OpeningObservationAvailability.MISSING
        return TimedOpeningObservation(label, configured_dt, underlying, selected, availability, "opening_context_builder", "APPLICABLE")


def _opening_value(opening: Any) -> float | None:
    if opening is None:
        return None
    if isinstance(opening, OpeningQuoteEvidence):
        return opening.ltp
    return opening.open


def _quote_ts(opening: Any) -> datetime | None:
    if opening is None:
        return None
    return getattr(opening, "source_timestamp", None) or getattr(opening, "bar_timestamp", None)


def _freshness(opening: Any) -> OpeningFreshnessStatus:
    return getattr(opening, "freshness", OpeningFreshnessStatus.FRESH)
