from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Mapping

from .enums import MonthlyStatus, OptionType, Segment
from .runtime_contracts import (
    TFISContractIdentity,
    TFISDirection,
    TFISExecutionSide,
    TFISProductType,
    TFISTradeResult,
)


class EvidenceAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceProvenance(str, Enum):
    CAPTURED = "CAPTURED"
    IMPORTED = "IMPORTED"
    DERIVED = "DERIVED"
    SYNTHETIC = "SYNTHETIC"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DecisionEvidenceCompleteness(str, Enum):
    FULL_DECISION_EVIDENCE = "FULL_DECISION_EVIDENCE"
    PARTIAL_DECISION_EVIDENCE = "PARTIAL_DECISION_EVIDENCE"
    CAPTURED_WITH_SYNTHETIC_SUPPLEMENT = "CAPTURED_WITH_SYNTHETIC_SUPPLEMENT"
    INVALID_DECISION_EVIDENCE = "INVALID_DECISION_EVIDENCE"


@dataclass(frozen=True, slots=True)
class ProvenancedValue:
    value: Decimal | str | bool | int | None
    availability: EvidenceAvailability
    provenance: EvidenceProvenance
    source: str | None = None

    def __post_init__(self) -> None:
        if self.availability is EvidenceAvailability.AVAILABLE and self.value is None:
            raise ValueError("available evidence must carry a value")
        if self.availability is not EvidenceAvailability.AVAILABLE and self.value is not None:
            raise ValueError("unavailable/not-applicable evidence must not carry a value")


@dataclass(frozen=True, slots=True)
class TimeWindowEvidence:
    market_start: time
    market_end: time
    orpt_time: time
    rc_time: time
    evaluation_trigger: str
    evaluation_reason: str


@dataclass(frozen=True, slots=True)
class IdentityEvidence:
    packet_schema_version: str
    packet_id: str
    evaluation_id: str
    strategy_instance_id: str
    strategy_unique_code: str
    strategy_branch: str
    configuration_version: str
    configuration_hash: str
    trading_date: date
    evaluation_timestamp: datetime
    event_timestamp: datetime
    processing_timestamp: datetime

    def __post_init__(self) -> None:
        for name in (
            "packet_schema_version",
            "packet_id",
            "evaluation_id",
            "strategy_instance_id",
            "strategy_unique_code",
            "strategy_branch",
            "configuration_version",
            "configuration_hash",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True, slots=True)
class SessionEvidence:
    exchange: str
    segment: Segment
    timezone: str
    time_window: TimeWindowEvidence


@dataclass(frozen=True, slots=True)
class InstrumentProductEvidence:
    underlying_identity: str
    price_source_identity: str
    product_type: TFISProductType
    contract_identity: TFISContractIdentity | None
    expiry: date | None
    rollover_context: str
    contract_availability: EvidenceAvailability


@dataclass(frozen=True, slots=True)
class MonthlyStatusEvidence:
    previous_persisted_status: MonthlyStatus | None
    resolved_current_status: MonthlyStatus | None
    status_evidence: str
    pmh: ProvenancedValue
    pml: ProvenancedValue
    pwh: ProvenancedValue
    pwl: ProvenancedValue
    cwh: ProvenancedValue
    cwl: ProvenancedValue
    cmh: ProvenancedValue
    cml: ProvenancedValue
    parameter_a_pct: ProvenancedValue
    parameter_b_pct: ProvenancedValue
    parameter_c_pct: ProvenancedValue
    transition_condition: str
    transition_reason: str
    status_quality: str


@dataclass(frozen=True, slots=True)
class MarketStructureEvidence:
    prv_1d_hh: ProvenancedValue
    prv_1d_ll: ProvenancedValue
    prv_2d_hh: ProvenancedValue
    prv_2d_ll: ProvenancedValue
    prv_3d_hh: ProvenancedValue
    prv_3d_ll: ProvenancedValue
    prv_4d_hh: ProvenancedValue
    prv_4d_ll: ProvenancedValue
    included_candle_dates: tuple[date, ...]
    current_day_high: ProvenancedValue
    current_day_low: ProvenancedValue
    source_contract: str
    quality: str
    provenance: EvidenceProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "included_candle_dates", tuple(self.included_candle_dates))


@dataclass(frozen=True, slots=True)
class PriceContextEvidence:
    cmp: ProvenancedValue
    cmp_source: str
    event_timestamp: datetime
    freshness_seconds: Decimal
    bid: ProvenancedValue
    ask: ProvenancedValue
    ltp: ProvenancedValue


@dataclass(frozen=True, slots=True)
class GapMissedEntryBusinessEngineFragment:
    engine_id: str
    policy_key: str
    profile: str
    timing_applicability: str
    chronology_status: str
    gap_classification: str
    gap_direction: str
    missed_entry_status: str
    comparison_source: str | None
    comparison_operator: str | None
    observed_value: ProvenancedValue
    reference_value: ProvenancedValue
    recalculation_status: str
    recalculation_branch: str | None
    downstream_action: str
    compatibility_outputs: Mapping[str, ProvenancedValue] = MappingProxyType({})
    unresolved_issue_codes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "compatibility_outputs",
            MappingProxyType(
                {
                    str(key): value
                    for key, value in sorted(
                        self.compatibility_outputs.items(),
                        key=lambda pair: str(pair[0]),
                    )
                }
            ),
        )
        object.__setattr__(self, "unresolved_issue_codes", tuple(self.unresolved_issue_codes))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(
            self,
            "provenance",
            MappingProxyType({str(key): str(value) for key, value in sorted(self.provenance.items())}),
        )


@dataclass(frozen=True, slots=True)
class GapMissedEntryEvidence:
    opening_price: ProvenancedValue
    reference_price: ProvenancedValue
    orpt_observation: ProvenancedValue
    rc_observation: ProvenancedValue
    gap_classification: str
    missed_entry_classification: str
    recalculation_branch: str
    formulas: tuple[str, ...]
    intermediate_values: tuple[tuple[str, ProvenancedValue], ...]
    business_engine_fragment: GapMissedEntryBusinessEngineFragment | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "formulas", tuple(self.formulas))
        object.__setattr__(self, "intermediate_values", tuple(self.intermediate_values))


@dataclass(frozen=True, slots=True)
class OptionProductReferenceEvidence:
    option_reference_values: tuple[tuple[str, ProvenancedValue], ...]
    expiry_candidates: tuple[date, ...]
    strike_range_start: ProvenancedValue
    strike_range_end: ProvenancedValue
    ideal_premium: ProvenancedValue
    minimum_premium: ProvenancedValue
    minimum_oi: ProvenancedValue
    expiries_to_check: int
    availability: EvidenceAvailability

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_reference_values", tuple(self.option_reference_values))
        object.__setattr__(self, "expiry_candidates", tuple(self.expiry_candidates))


@dataclass(frozen=True, slots=True)
class OptionChainCandidateEvidence:
    contract_identity: TFISContractIdentity
    strike: ProvenancedValue
    option_type: OptionType | None
    expiry: date | None
    ltp: ProvenancedValue
    bid: ProvenancedValue
    ask: ProvenancedValue
    oi: ProvenancedValue
    quote_timestamp: datetime
    quality: str
    freshness_seconds: Decimal


@dataclass(frozen=True, slots=True)
class OptionChainEvidence:
    candidates: tuple[OptionChainCandidateEvidence, ...]
    rejected_candidate_reasons: tuple[tuple[str, int], ...]
    availability: EvidenceAvailability

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "rejected_candidate_reasons", tuple(self.rejected_candidate_reasons))


@dataclass(frozen=True, slots=True)
class SelectedContractEvidence:
    selected_identity: TFISContractIdentity | None
    selection_reason: str
    selected_quote: OptionChainCandidateEvidence | None
    rejected_candidate_reasons: tuple[tuple[str, int], ...]
    availability: EvidenceAvailability

    def __post_init__(self) -> None:
        object.__setattr__(self, "rejected_candidate_reasons", tuple(self.rejected_candidate_reasons))


@dataclass(frozen=True, slots=True)
class CalculatedDecisionEvidence:
    entry: ProvenancedValue
    targets: tuple[ProvenancedValue, ...]
    msl: ProvenancedValue
    tsl_plan: ProvenancedValue
    aps_plan: ProvenancedValue
    lots: ProvenancedValue
    quantity: ProvenancedValue
    direction: TFISDirection | None
    execution_side: TFISExecutionSide | None
    trade_result: TFISTradeResult
    final_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(self.targets))


@dataclass(frozen=True, slots=True)
class AuditEvidence:
    policy_keys: tuple[tuple[str, str], ...]
    requirement_ids: tuple[str, ...]
    formula_expressions: tuple[tuple[str, str], ...]
    intermediate_values: tuple[tuple[str, ProvenancedValue], ...]
    data_quality_warnings: tuple[str, ...]
    evidence_classifications: tuple[EvidenceProvenance, ...]
    compatibility_payload: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_keys", tuple(self.policy_keys))
        object.__setattr__(self, "requirement_ids", tuple(self.requirement_ids))
        object.__setattr__(self, "formula_expressions", tuple(self.formula_expressions))
        object.__setattr__(self, "intermediate_values", tuple(self.intermediate_values))
        object.__setattr__(self, "data_quality_warnings", tuple(self.data_quality_warnings))
        object.__setattr__(self, "evidence_classifications", tuple(self.evidence_classifications))
        object.__setattr__(
            self,
            "compatibility_payload",
            MappingProxyType({str(key): str(value) for key, value in self.compatibility_payload.items()}),
        )


@dataclass(frozen=True, slots=True)
class TFISDecisionEvidencePacket:
    identity: IdentityEvidence
    session: SessionEvidence
    instrument_product: InstrumentProductEvidence
    monthly_status: MonthlyStatusEvidence
    market_structure: MarketStructureEvidence
    price_context: PriceContextEvidence
    gap_missed_entry: GapMissedEntryEvidence
    option_product_references: OptionProductReferenceEvidence
    option_chain: OptionChainEvidence
    selected_contract: SelectedContractEvidence
    calculated_decision: CalculatedDecisionEvidence
    audit: AuditEvidence

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TFISDecisionEvidencePacket:
        return _packet_from_dict(value)

    @classmethod
    def from_json(cls, value: str) -> TFISDecisionEvidencePacket:
        return cls.from_dict(json.loads(value))


@dataclass(frozen=True, slots=True)
class DecisionEvidenceValidationIssue:
    code: str
    message: str
    field_name: str


@dataclass(frozen=True, slots=True)
class DecisionEvidenceValidationResult:
    completeness: DecisionEvidenceCompleteness
    issues: tuple[DecisionEvidenceValidationIssue, ...]

    @property
    def is_full(self) -> bool:
        return self.completeness is DecisionEvidenceCompleteness.FULL_DECISION_EVIDENCE

    @property
    def is_valid(self) -> bool:
        return self.completeness is not DecisionEvidenceCompleteness.INVALID_DECISION_EVIDENCE


def validate_decision_evidence_packet(
    packet: TFISDecisionEvidencePacket,
) -> DecisionEvidenceValidationResult:
    issues: list[DecisionEvidenceValidationIssue] = []
    _validate_timestamps(packet, issues)
    _validate_identities(packet, issues)
    _validate_formula_inputs(packet, issues)
    _validate_gap_evidence(packet, issues)
    _validate_option_chain(packet, issues)
    _validate_final_decision(packet, issues)
    invalid_codes = {"INVALID_TIMESTAMP_ORDER", "IDENTITY_MISMATCH", "SELECTED_CONTRACT_NOT_IN_CANDIDATES"}
    if any(issue.code in invalid_codes for issue in issues):
        completeness = DecisionEvidenceCompleteness.INVALID_DECISION_EVIDENCE
    elif any(item is EvidenceProvenance.SYNTHETIC for item in packet.audit.evidence_classifications):
        completeness = (
            DecisionEvidenceCompleteness.CAPTURED_WITH_SYNTHETIC_SUPPLEMENT
            if any(item is EvidenceProvenance.CAPTURED for item in packet.audit.evidence_classifications)
            else DecisionEvidenceCompleteness.FULL_DECISION_EVIDENCE
        )
    elif issues:
        completeness = DecisionEvidenceCompleteness.PARTIAL_DECISION_EVIDENCE
    else:
        completeness = DecisionEvidenceCompleteness.FULL_DECISION_EVIDENCE
    return DecisionEvidenceValidationResult(
        completeness=completeness,
        issues=tuple(sorted(issues, key=lambda item: (item.code, item.field_name))),
    )


def _validate_timestamps(
    packet: TFISDecisionEvidencePacket,
    issues: list[DecisionEvidenceValidationIssue],
) -> None:
    identity = packet.identity
    if identity.event_timestamp > identity.evaluation_timestamp:
        issues.append(_issue("INVALID_TIMESTAMP_ORDER", "event timestamp is after evaluation timestamp", "identity.event_timestamp"))
    if identity.evaluation_timestamp > identity.processing_timestamp:
        issues.append(_issue("INVALID_TIMESTAMP_ORDER", "evaluation timestamp is after processing timestamp", "identity.evaluation_timestamp"))


def _validate_identities(
    packet: TFISDecisionEvidencePacket,
    issues: list[DecisionEvidenceValidationIssue],
) -> None:
    if packet.session.segment is Segment.OPTIONS_SELL and packet.instrument_product.product_type is not TFISProductType.OPTION_SELLING:
        issues.append(_issue("IDENTITY_MISMATCH", "segment and product type are inconsistent", "instrument_product.product_type"))


def _validate_formula_inputs(
    packet: TFISDecisionEvidencePacket,
    issues: list[DecisionEvidenceValidationIssue],
) -> None:
    required = (
        ("market_structure.prv_2d_hh", packet.market_structure.prv_2d_hh),
        ("market_structure.prv_2d_ll", packet.market_structure.prv_2d_ll),
        ("market_structure.prv_3d_hh", packet.market_structure.prv_3d_hh),
        ("market_structure.prv_3d_ll", packet.market_structure.prv_3d_ll),
        ("calculated_decision.entry", packet.calculated_decision.entry),
        ("calculated_decision.msl", packet.calculated_decision.msl),
    )
    for field_name, value in required:
        if value.availability is not EvidenceAvailability.AVAILABLE:
            issues.append(_issue("MISSING_FORMULA_INPUT", "required formula evidence is unavailable", field_name))
    if not packet.option_product_references.option_reference_values:
        issues.append(_issue("MISSING_FORMULA_INPUT", "option reference values are unavailable", "option_product_references.option_reference_values"))


def _validate_gap_evidence(
    packet: TFISDecisionEvidencePacket,
    issues: list[DecisionEvidenceValidationIssue],
) -> None:
    if packet.gap_missed_entry.orpt_observation.availability is not EvidenceAvailability.AVAILABLE:
        issues.append(_issue("MISSING_ORPT_RC_EVIDENCE", "ORPT evidence is unavailable", "gap_missed_entry.orpt_observation"))
    if packet.gap_missed_entry.rc_observation.availability is not EvidenceAvailability.AVAILABLE:
        issues.append(_issue("MISSING_ORPT_RC_EVIDENCE", "RC evidence is unavailable", "gap_missed_entry.rc_observation"))


def _validate_option_chain(
    packet: TFISDecisionEvidencePacket,
    issues: list[DecisionEvidenceValidationIssue],
) -> None:
    if packet.option_product_references.availability is EvidenceAvailability.NOT_APPLICABLE:
        return
    if packet.option_chain.availability is not EvidenceAvailability.AVAILABLE or not packet.option_chain.candidates:
        issues.append(_issue("INCOMPLETE_OPTION_CHAIN_EVIDENCE", "option-chain candidate set is unavailable", "option_chain.candidates"))
    if packet.selected_contract.availability is not EvidenceAvailability.AVAILABLE:
        issues.append(_issue("MISSING_SELECTED_CONTRACT", "selected contract evidence is unavailable", "selected_contract"))
        return
    selected = packet.selected_contract.selected_identity
    if selected is None:
        issues.append(_issue("MISSING_SELECTED_CONTRACT", "selected contract identity is unavailable", "selected_contract.selected_identity"))
        return
    selected_key = _canonical_json(selected.to_dict())
    if not any(_canonical_json(candidate.contract_identity.to_dict()) == selected_key for candidate in packet.option_chain.candidates):
        issues.append(_issue("SELECTED_CONTRACT_NOT_IN_CANDIDATES", "selected contract is absent from the candidate set", "selected_contract.selected_identity"))


def _validate_final_decision(
    packet: TFISDecisionEvidencePacket,
    issues: list[DecisionEvidenceValidationIssue],
) -> None:
    if not packet.calculated_decision.final_reason.strip():
        issues.append(_issue("MISSING_FINAL_LEGACY_DECISION", "final decision reason is missing", "calculated_decision.final_reason"))


def _issue(code: str, message: str, field_name: str) -> DecisionEvidenceValidationIssue:
    return DecisionEvidenceValidationIssue(code=code, message=message, field_name=field_name)


def _packet_from_dict(data: Mapping[str, Any]) -> TFISDecisionEvidencePacket:
    return TFISDecisionEvidencePacket(
        identity=IdentityEvidence(
            packet_schema_version=str(data["identity"]["packet_schema_version"]),
            packet_id=str(data["identity"]["packet_id"]),
            evaluation_id=str(data["identity"]["evaluation_id"]),
            strategy_instance_id=str(data["identity"]["strategy_instance_id"]),
            strategy_unique_code=str(data["identity"]["strategy_unique_code"]),
            strategy_branch=str(data["identity"]["strategy_branch"]),
            configuration_version=str(data["identity"]["configuration_version"]),
            configuration_hash=str(data["identity"]["configuration_hash"]),
            trading_date=date.fromisoformat(data["identity"]["trading_date"]),
            evaluation_timestamp=datetime.fromisoformat(data["identity"]["evaluation_timestamp"]),
            event_timestamp=datetime.fromisoformat(data["identity"]["event_timestamp"]),
            processing_timestamp=datetime.fromisoformat(data["identity"]["processing_timestamp"]),
        ),
        session=SessionEvidence(
            exchange=str(data["session"]["exchange"]),
            segment=Segment(data["session"]["segment"]),
            timezone=str(data["session"]["timezone"]),
            time_window=TimeWindowEvidence(
                market_start=time.fromisoformat(data["session"]["time_window"]["market_start"]),
                market_end=time.fromisoformat(data["session"]["time_window"]["market_end"]),
                orpt_time=time.fromisoformat(data["session"]["time_window"]["orpt_time"]),
                rc_time=time.fromisoformat(data["session"]["time_window"]["rc_time"]),
                evaluation_trigger=str(data["session"]["time_window"]["evaluation_trigger"]),
                evaluation_reason=str(data["session"]["time_window"]["evaluation_reason"]),
            ),
        ),
        instrument_product=InstrumentProductEvidence(
            underlying_identity=str(data["instrument_product"]["underlying_identity"]),
            price_source_identity=str(data["instrument_product"]["price_source_identity"]),
            product_type=TFISProductType(data["instrument_product"]["product_type"]),
            contract_identity=(
                _contract_from_dict(data["instrument_product"]["contract_identity"])
                if data["instrument_product"]["contract_identity"] is not None
                else None
            ),
            expiry=_date_or_none(data["instrument_product"]["expiry"]),
            rollover_context=str(data["instrument_product"]["rollover_context"]),
            contract_availability=EvidenceAvailability(data["instrument_product"]["contract_availability"]),
        ),
        monthly_status=_monthly_from_dict(data["monthly_status"]),
        market_structure=_market_structure_from_dict(data["market_structure"]),
        price_context=_price_context_from_dict(data["price_context"]),
        gap_missed_entry=_gap_from_dict(data["gap_missed_entry"]),
        option_product_references=_option_refs_from_dict(data["option_product_references"]),
        option_chain=_chain_from_dict(data["option_chain"]),
        selected_contract=_selected_from_dict(data["selected_contract"]),
        calculated_decision=_calculated_from_dict(data["calculated_decision"]),
        audit=_audit_from_dict(data["audit"]),
    )


def _monthly_from_dict(data: Mapping[str, Any]) -> MonthlyStatusEvidence:
    return MonthlyStatusEvidence(
        previous_persisted_status=_monthly_or_none(data["previous_persisted_status"]),
        resolved_current_status=_monthly_or_none(data["resolved_current_status"]),
        status_evidence=str(data["status_evidence"]),
        pmh=_pv(data["pmh"]),
        pml=_pv(data["pml"]),
        pwh=_pv(data["pwh"]),
        pwl=_pv(data["pwl"]),
        cwh=_pv(data["cwh"]),
        cwl=_pv(data["cwl"]),
        cmh=_pv(data["cmh"]),
        cml=_pv(data["cml"]),
        parameter_a_pct=_pv(data["parameter_a_pct"]),
        parameter_b_pct=_pv(data["parameter_b_pct"]),
        parameter_c_pct=_pv(data["parameter_c_pct"]),
        transition_condition=str(data["transition_condition"]),
        transition_reason=str(data["transition_reason"]),
        status_quality=str(data["status_quality"]),
    )


def _market_structure_from_dict(data: Mapping[str, Any]) -> MarketStructureEvidence:
    return MarketStructureEvidence(
        prv_1d_hh=_pv(data["prv_1d_hh"]),
        prv_1d_ll=_pv(data["prv_1d_ll"]),
        prv_2d_hh=_pv(data["prv_2d_hh"]),
        prv_2d_ll=_pv(data["prv_2d_ll"]),
        prv_3d_hh=_pv(data["prv_3d_hh"]),
        prv_3d_ll=_pv(data["prv_3d_ll"]),
        prv_4d_hh=_pv(data["prv_4d_hh"]),
        prv_4d_ll=_pv(data["prv_4d_ll"]),
        included_candle_dates=tuple(date.fromisoformat(item) for item in data["included_candle_dates"]),
        current_day_high=_pv(data["current_day_high"]),
        current_day_low=_pv(data["current_day_low"]),
        source_contract=str(data["source_contract"]),
        quality=str(data["quality"]),
        provenance=EvidenceProvenance(data["provenance"]),
    )


def _price_context_from_dict(data: Mapping[str, Any]) -> PriceContextEvidence:
    return PriceContextEvidence(
        cmp=_pv(data["cmp"]),
        cmp_source=str(data["cmp_source"]),
        event_timestamp=datetime.fromisoformat(data["event_timestamp"]),
        freshness_seconds=Decimal(str(data["freshness_seconds"])),
        bid=_pv(data["bid"]),
        ask=_pv(data["ask"]),
        ltp=_pv(data["ltp"]),
    )


def _gap_from_dict(data: Mapping[str, Any]) -> GapMissedEntryEvidence:
    return GapMissedEntryEvidence(
        opening_price=_pv(data["opening_price"]),
        reference_price=_pv(data["reference_price"]),
        orpt_observation=_pv(data["orpt_observation"]),
        rc_observation=_pv(data["rc_observation"]),
        gap_classification=str(data["gap_classification"]),
        missed_entry_classification=str(data["missed_entry_classification"]),
        recalculation_branch=str(data["recalculation_branch"]),
        formulas=tuple(str(item) for item in data["formulas"]),
        intermediate_values=tuple((str(key), _pv(value)) for key, value in data["intermediate_values"]),
        business_engine_fragment=(
            _business_gap_fragment_from_dict(data["business_engine_fragment"])
            if data.get("business_engine_fragment") is not None
            else None
        ),
    )


def _business_gap_fragment_from_dict(data: Mapping[str, Any]) -> GapMissedEntryBusinessEngineFragment:
    return GapMissedEntryBusinessEngineFragment(
        engine_id=str(data["engine_id"]),
        policy_key=str(data["policy_key"]),
        profile=str(data["profile"]),
        timing_applicability=str(data["timing_applicability"]),
        chronology_status=str(data["chronology_status"]),
        gap_classification=str(data["gap_classification"]),
        gap_direction=str(data["gap_direction"]),
        missed_entry_status=str(data["missed_entry_status"]),
        comparison_source=str(data["comparison_source"]) if data["comparison_source"] is not None else None,
        comparison_operator=str(data["comparison_operator"]) if data["comparison_operator"] is not None else None,
        observed_value=_pv(data["observed_value"]),
        reference_value=_pv(data["reference_value"]),
        recalculation_status=str(data["recalculation_status"]),
        recalculation_branch=(
            str(data["recalculation_branch"])
            if data["recalculation_branch"] is not None
            else None
        ),
        downstream_action=str(data["downstream_action"]),
        compatibility_outputs={
            str(key): _pv(value)
            for key, value in data["compatibility_outputs"].items()
        },
        unresolved_issue_codes=tuple(str(item) for item in data["unresolved_issue_codes"]),
        warnings=tuple(str(item) for item in data["warnings"]),
        failures=tuple(str(item) for item in data["failures"]),
        provenance=data["provenance"],
    )


def _option_refs_from_dict(data: Mapping[str, Any]) -> OptionProductReferenceEvidence:
    return OptionProductReferenceEvidence(
        option_reference_values=tuple((str(key), _pv(value)) for key, value in data["option_reference_values"]),
        expiry_candidates=tuple(date.fromisoformat(item) for item in data["expiry_candidates"]),
        strike_range_start=_pv(data["strike_range_start"]),
        strike_range_end=_pv(data["strike_range_end"]),
        ideal_premium=_pv(data["ideal_premium"]),
        minimum_premium=_pv(data["minimum_premium"]),
        minimum_oi=_pv(data["minimum_oi"]),
        expiries_to_check=int(data["expiries_to_check"]),
        availability=EvidenceAvailability(data["availability"]),
    )


def _chain_from_dict(data: Mapping[str, Any]) -> OptionChainEvidence:
    return OptionChainEvidence(
        candidates=tuple(_candidate_from_dict(item) for item in data["candidates"]),
        rejected_candidate_reasons=tuple((str(key), int(value)) for key, value in data["rejected_candidate_reasons"]),
        availability=EvidenceAvailability(data["availability"]),
    )


def _candidate_from_dict(data: Mapping[str, Any]) -> OptionChainCandidateEvidence:
    return OptionChainCandidateEvidence(
        contract_identity=_contract_from_dict(data["contract_identity"]),
        strike=_pv(data["strike"]),
        option_type=OptionType(data["option_type"]) if data["option_type"] is not None else None,
        expiry=_date_or_none(data["expiry"]),
        ltp=_pv(data["ltp"]),
        bid=_pv(data["bid"]),
        ask=_pv(data["ask"]),
        oi=_pv(data["oi"]),
        quote_timestamp=datetime.fromisoformat(data["quote_timestamp"]),
        quality=str(data["quality"]),
        freshness_seconds=Decimal(str(data["freshness_seconds"])),
    )


def _selected_from_dict(data: Mapping[str, Any]) -> SelectedContractEvidence:
    return SelectedContractEvidence(
        selected_identity=_contract_from_dict(data["selected_identity"]) if data["selected_identity"] is not None else None,
        selection_reason=str(data["selection_reason"]),
        selected_quote=_candidate_from_dict(data["selected_quote"]) if data["selected_quote"] is not None else None,
        rejected_candidate_reasons=tuple((str(key), int(value)) for key, value in data["rejected_candidate_reasons"]),
        availability=EvidenceAvailability(data["availability"]),
    )


def _calculated_from_dict(data: Mapping[str, Any]) -> CalculatedDecisionEvidence:
    return CalculatedDecisionEvidence(
        entry=_pv(data["entry"]),
        targets=tuple(_pv(item) for item in data["targets"]),
        msl=_pv(data["msl"]),
        tsl_plan=_pv(data["tsl_plan"]),
        aps_plan=_pv(data["aps_plan"]),
        lots=_pv(data["lots"]),
        quantity=_pv(data["quantity"]),
        direction=TFISDirection(data["direction"]) if data["direction"] is not None else None,
        execution_side=TFISExecutionSide(data["execution_side"]) if data["execution_side"] is not None else None,
        trade_result=TFISTradeResult(data["trade_result"]),
        final_reason=str(data["final_reason"]),
    )


def _audit_from_dict(data: Mapping[str, Any]) -> AuditEvidence:
    return AuditEvidence(
        policy_keys=tuple((str(key), str(value)) for key, value in data["policy_keys"]),
        requirement_ids=tuple(str(item) for item in data["requirement_ids"]),
        formula_expressions=tuple((str(key), str(value)) for key, value in data["formula_expressions"]),
        intermediate_values=tuple((str(key), _pv(value)) for key, value in data["intermediate_values"]),
        data_quality_warnings=tuple(str(item) for item in data["data_quality_warnings"]),
        evidence_classifications=tuple(EvidenceProvenance(item) for item in data["evidence_classifications"]),
        compatibility_payload=data["compatibility_payload"],
    )


def _contract_from_dict(data: Mapping[str, Any]) -> TFISContractIdentity:
    return TFISContractIdentity(
        symbol=data["symbol"],
        exchange=data["exchange"],
        segment=Segment(data["segment"]) if data["segment"] is not None else None,
        product_type=TFISProductType(data["product_type"]) if data["product_type"] is not None else None,
        expiry=_date_or_none(data["expiry"]),
        strike=float(data["strike"]) if data["strike"] is not None else None,
        option_type=data["option_type"],
        token=data["token"],
        metadata=data["metadata"],
    )


def _pv(data: Mapping[str, Any]) -> ProvenancedValue:
    raw = data["value"]
    if isinstance(raw, str) and data["availability"] == EvidenceAvailability.AVAILABLE.value:
        value: Decimal | str | bool | int | None
        try:
            value = Decimal(raw)
        except Exception:
            value = raw
    else:
        value = raw
    return ProvenancedValue(
        value=value,
        availability=EvidenceAvailability(data["availability"]),
        provenance=EvidenceProvenance(data["provenance"]),
        source=data["source"],
    )


def _date_or_none(value: Any) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(str(value))


def _monthly_or_none(value: Any) -> MonthlyStatus | None:
    if value is None:
        return None
    return MonthlyStatus(value)


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _serializable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _serializable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _serializable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
