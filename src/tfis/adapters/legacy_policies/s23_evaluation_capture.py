from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from uuid import uuid4

from tfis.domain import TFISDecision, TFISDecisionEvidencePacket
from tfis.normalized_events import OptionChainSnapshotEvent


SCHEMA_VERSION = "tfis.s23.evaluation_capture_packet.v1"
SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "auth_header",
    "cookie",
    "password",
    "secret",
    "session_cookie",
    "token",
)


class S23CaptureError(RuntimeError):
    """Capture failed outside decision authority."""


class EvaluationCaptureObserver(Protocol):
    def record(self, packet: "S23EvaluationCapturePacket") -> None:
        ...


@dataclass(frozen=True, slots=True)
class S23CaptureIdentity:
    schema_version: str
    capture_id: str
    evaluation_id: str
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance: str
    resolved_configuration_hash: str
    trading_date: date
    source_session_identity: str


@dataclass(frozen=True, slots=True)
class S23CaptureMarketContext:
    monthly_status: str | None
    resolved_branch: str
    source_timestamps: Mapping[str, str]
    underlying_references: Mapping[str, Any]
    reference_identities: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class S23CaptureContractSelection:
    option_chain_snapshot: OptionChainSnapshotEvent
    expiry_candidates: tuple[str, ...]
    strike_candidates: tuple[float, ...]
    premium_fields: Mapping[str, Any]
    oi_values: Mapping[str, Any]
    oi_units: str
    quote_timestamps: Mapping[str, str]
    qualification_outcomes: tuple[Mapping[str, Any], ...]
    selected_expiry: str
    selected_strike: float
    selected_contract: str
    selected_contract_quote: Mapping[str, Any]
    non_selected_rejection_reasons: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class S23CaptureEntryEvidence:
    selected_contract_historical_references: Mapping[str, Any]
    orpt_observation: Mapping[str, Any]
    rc_observation: Mapping[str, Any]
    base_entry_inputs: Mapping[str, Any]
    base_entry_result: Any
    gap_missed_entry_inputs: Mapping[str, Any]
    gap_missed_entry_result: Mapping[str, Any]
    effective_entry_inputs: Mapping[str, Any]
    effective_entry_result: Any
    downstream_permission: str


@dataclass(frozen=True, slots=True)
class S23CaptureRiskCompatibility:
    target_inputs: Mapping[str, Any]
    target_result: Any
    msl_inputs: Mapping[str, Any]
    msl_result: Any


@dataclass(frozen=True, slots=True)
class S23CaptureProvenance:
    evidence_classification: str
    section_sources: Mapping[str, str]
    capture_timestamp: datetime
    source_event_timestamps: Mapping[str, str]
    supplemented_fields: tuple[str, ...]
    missing_real_world_fields: tuple[str, ...]
    redaction_metadata: Mapping[str, Any]
    capture_locations_for_missing_fields: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class S23EvaluationCapturePacket:
    identity: S23CaptureIdentity
    market_context: S23CaptureMarketContext
    contract_selection: S23CaptureContractSelection
    entry: S23CaptureEntryEvidence
    risk_compatibility: S23CaptureRiskCompatibility
    decision: TFISDecision
    decision_evidence_packet: TFISDecisionEvidencePacket
    final_rejection_reason: str | None
    provenance: S23CaptureProvenance

    def __post_init__(self) -> None:
        _assert_no_sensitive_keys(self.to_dict(validate=False))
        if self.provenance.evidence_classification != "LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT":
            raise ValueError("S23 fixture capture packets must disclose LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT")

    def to_dict(self, *, validate: bool = True) -> dict[str, Any]:
        payload = _serializable(self)
        if validate:
            _assert_no_sensitive_keys(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )


@dataclass(frozen=True, slots=True)
class S23CaptureAttempt:
    attempted: bool
    success: bool
    capture_id: str | None = None
    output_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class InMemoryS23EvaluationCaptureObserver:
    def __init__(self) -> None:
        self.packets: list[S23EvaluationCapturePacket] = []

    def record(self, packet: S23EvaluationCapturePacket) -> None:
        self.packets.append(packet)


class S23EvaluationCaptureFileSink:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        if self.output_dir.is_absolute() and not _is_safe_absolute_path(self.output_dir):
            raise ValueError("capture output directory must stay inside the repository or tmp")

    def record(self, packet: S23EvaluationCapturePacket) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{packet.identity.capture_id}.json"
        if output_path.exists():
            raise S23CaptureError(f"duplicate capture identity: {packet.identity.capture_id}")
        atomic_write_text(output_path, packet.to_json() + "\n")


def build_s23_evaluation_capture_packet(result: Any, *, case: Any | None = None) -> S23EvaluationCapturePacket:
    context = _stage_payloads(result)
    if case is not None:
        context["case"] = case
    decision = result.decision
    case_metadata = dict(decision.compatibility_payload.get("m5_evidence") or {})
    selected = decision.selected_instrument
    if selected is None:
        raise ValueError("capture packet requires a selected contract")
    chain = context["case"].option_chain_snapshot
    entry_fragment = result.evidence_packet.entry
    if entry_fragment is None:
        raise ValueError("capture packet requires Entry evidence")
    capture_id = _capture_id(decision.evaluation_id, decision.strategy_branch)
    metadata_missing = tuple(case_metadata.get("missing_fields") or ())
    metadata_supplements = tuple(case_metadata.get("synthetic_supplements") or ())
    ts = decision.decided_at.isoformat()
    trade_plan = dict(context["trade_plan"])
    contract_selection = context["contract_selection"]
    gap_result = context["gap_missed_entry"]
    base_entry = context["base_entry"]
    effective_entry = context["effective_entry"]
    return S23EvaluationCapturePacket(
        identity=S23CaptureIdentity(
            schema_version=SCHEMA_VERSION,
            capture_id=capture_id,
            evaluation_id=decision.evaluation_id,
            strategy_family=decision.strategy_family_id or "S23",
            strategy_definition=decision.strategy_definition_id or decision.strategy_branch,
            strategy_version=decision.strategy_version_identity or "1.0.0",
            strategy_instance=decision.strategy_instance_id or "REDACTED_STRATEGY_INSTANCE",
            resolved_configuration_hash=decision.resolved_configuration_hash or "",
            trading_date=decision.decided_at.date(),
            source_session_identity=str(context["case"].runtime_input.session_label or "offline-fixture"),
        ),
        market_context=S23CaptureMarketContext(
            monthly_status=decision.monthly_status_branch,
            resolved_branch=decision.strategy_branch,
            source_timestamps={
                "evaluation": ts,
                "option_chain": chain.envelope.effective_timestamp.isoformat(),
            },
            underlying_references=dict(context["case"].runtime_input.market_structure_references),
            reference_identities={
                key: f"market_structure:{key}"
                for key in context["case"].runtime_input.market_structure_references
            },
        ),
        contract_selection=S23CaptureContractSelection(
            option_chain_snapshot=chain,
            expiry_candidates=tuple(item.isoformat() for item in result.evidence_packet.option_product_references.expiry_candidates),
            strike_candidates=(float(trade_plan["start_strike"]), float(trade_plan["end_strike"])),
            premium_fields={
                "ideal_premium": trade_plan["ideal_premium"],
                "minimum_premium": trade_plan["minimum_premium"],
                "selected_ltp": selected.metadata.get("ltp"),
                "selected_bid": selected.metadata.get("bid"),
                "selected_ask": selected.metadata.get("ask"),
            },
            oi_values={"selected_contract": selected.metadata.get("oi")},
            oi_units="contracts",
            quote_timestamps={"selected_contract": ts},
            qualification_outcomes=(
                {
                    "contract": selected.symbol,
                    "status": "QUALIFIED",
                    "reason": contract_selection.reason,
                },
            ),
            selected_expiry=selected.expiry.isoformat(),
            selected_strike=float(selected.strike),
            selected_contract=selected.symbol,
            selected_contract_quote={
                "symbol": selected.symbol,
                "ltp": selected.metadata.get("ltp"),
                "bid": selected.metadata.get("bid"),
                "ask": selected.metadata.get("ask"),
                "oi": selected.metadata.get("oi"),
                "timestamp": ts,
            },
            non_selected_rejection_reasons=tuple(
                {"reason": item}
                for item in getattr(contract_selection, "rejected_candidate_counts", {}) or ()
            ),
        ),
        entry=S23CaptureEntryEvidence(
            selected_contract_historical_references=dict(context["case"].runtime_values["OPT_LEVELS"]),
            orpt_observation=_observation_dict(gap_result.evidence.timing.orpt_observation),
            rc_observation=_observation_dict(gap_result.evidence.timing.rc_observation),
            base_entry_inputs={
                "formula": context["case"].strategy_rule.entry_formula,
                "legacy_entry_value": context["legacy_entry"].entry_value,
            },
            base_entry_result=str(base_entry.base_entry.value),
            gap_missed_entry_inputs={
                "policy_key": "legacy.s23.gap_missed_entry.backtest_low",
                "base_entry_price": str(base_entry.base_entry.value),
            },
            gap_missed_entry_result=gap_result.evidence.to_decision_evidence_fragment(),
            effective_entry_inputs={
                "base_entry": str(base_entry.base_entry.value),
                "gap_missed_entry_status": gap_result.missed_entry.status.value,
            },
            effective_entry_result=str(effective_entry.effective_entry.value),
            downstream_permission=effective_entry.downstream_permission.value,
        ),
        risk_compatibility=S23CaptureRiskCompatibility(
            target_inputs=context["target"].to_dict(),
            target_result=context["target"].calculated_value,
            msl_inputs=context["msl"].to_dict(),
            msl_result=context["msl"].calculated_value,
        ),
        decision=decision,
        decision_evidence_packet=result.evidence_packet,
        final_rejection_reason=decision.rejection_reason,
        provenance=S23CaptureProvenance(
            evidence_classification="LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT",
            section_sources={
                "identity": "strategy_config",
                "market_context": "fixture_runtime_input",
                "contract_selection": "fixture_option_chain",
                "entry": "legacy_fixture_adapter",
                "risk_compatibility": "legacy_fixture_adapter",
                "decision": "tfis_vertical_result",
                "decision_evidence_packet": "tfis_vertical_result",
            },
            capture_timestamp=decision.decided_at,
            source_event_timestamps={
                "evaluation": ts,
                "option_chain": chain.envelope.effective_timestamp.isoformat(),
            },
            supplemented_fields=metadata_supplements,
            missing_real_world_fields=metadata_missing,
            redaction_metadata={
                "account_id": "not_captured",
                "broker_auth_material": "rejected_by_key_scan",
                "raw_http_auth_material": "rejected_by_key_scan",
            },
            capture_locations_for_missing_fields={
                "real trading date": "capture identity.trading_date from runtime session date",
                "captured option-chain snapshot": "contract_selection.option_chain_snapshot",
                "captured selected-contract quote": "contract_selection.selected_contract_quote",
                "captured ORPT option observation": "entry.orpt_observation",
                "captured RC option observation": "entry.rc_observation",
                "captured legacy/runtime decision packet": "decision and decision_evidence_packet",
            },
        ),
    )


def record_s23_capture_safely(
    observer: EvaluationCaptureObserver | None,
    result: Any,
    *,
    case: Any | None = None,
) -> S23CaptureAttempt:
    if observer is None:
        return S23CaptureAttempt(attempted=False, success=False)
    try:
        packet = build_s23_evaluation_capture_packet(result, case=case)
        observer.record(packet)
        return S23CaptureAttempt(attempted=True, success=True, capture_id=packet.identity.capture_id)
    except Exception as exc:  # capture diagnostics must not affect decision authority
        return S23CaptureAttempt(
            attempted=True,
            success=False,
            error_code=type(exc).__name__,
            error_message=str(exc),
        )


def _stage_payloads(result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for stage in result.stages:
        payload.update(dict(stage.payload))
    return payload


def _capture_id(evaluation_id: str, branch: str) -> str:
    digest = sha256(f"{evaluation_id}:{branch}".encode("utf-8")).hexdigest()[:24]
    return f"s23-evaluation-capture-{digest}"


def _observation_dict(observation: Any) -> dict[str, Any]:
    return {
        "source": observation.source.value,
        "value": str(observation.value),
        "timestamp": observation.observed_at.isoformat(),
    }


def _assert_no_sensitive_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            text = str(key).lower()
            if any(fragment in text for fragment in SENSITIVE_KEY_FRAGMENTS):
                if item == "REDACTED":
                    continue
                raise ValueError(f"sensitive capture field rejected: {path}.{key}")
            _assert_no_sensitive_keys(item, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _assert_no_sensitive_keys(item, f"{path}[{index}]")


def _is_safe_absolute_path(path: Path) -> bool:
    resolved = path.resolve()
    cwd = Path.cwd().resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    return str(resolved).startswith(str(cwd)) or str(resolved).startswith(str(temp_root))


def atomic_write_text(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = "\n",
    attempts: int = 5,
    retry_delay_seconds: float = 0.05,
) -> Path:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.parent / f".{target_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    try:
        temp_path.write_text(content, encoding=encoding, newline=newline)
        for attempt in range(attempts):
            try:
                os.replace(temp_path, target_path)
                return target_path
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(retry_delay_seconds * (attempt + 1))
        return target_path
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _serializable(value: Any) -> Any:
    if hasattr(value, "to_dict") and not isinstance(value, S23EvaluationCapturePacket):
        return _serializable(value.to_dict())
    if is_dataclass(value):
        return {
            field.name: _serializable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        result = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            text = str(key).lower()
            result[str(key)] = (
                "REDACTED"
                if any(fragment in text for fragment in SENSITIVE_KEY_FRAGMENTS)
                else _serializable(item)
            )
        return result
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value
