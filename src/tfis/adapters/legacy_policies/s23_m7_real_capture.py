from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Mapping


SCHEMA_VERSION = "tfis.phase3d.m7.real_s23_capture.v1"
DEFAULT_CAPTURE_STATE = "DISABLED"
REQUIRED_PACKET_SECTIONS = (
    "enablement",
    "source_session",
    "pre_market_plan",
    "opening_context",
    "orpt_observation",
    "rc_observation",
    "authoritative_legacy_result",
    "refactored_shadow_result",
    "parity",
    "carried_position",
    "provenance",
    "execution_authority",
)
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


@dataclass(frozen=True, slots=True)
class S23RealCaptureEnablement:
    enabled: bool
    method: str
    output_dir: str | None
    strategy_instance: str | None
    trading_date: date | None
    session_id: str | None
    reason: str

    @classmethod
    def disabled(cls) -> "S23RealCaptureEnablement":
        return cls(
            enabled=False,
            method="DEFAULT_DISABLED",
            output_dir=None,
            strategy_instance=None,
            trading_date=None,
            session_id=None,
            reason="Capture is disabled unless an explicit debug/session override is supplied.",
        )


def explicit_session_capture_enablement(
    *,
    output_dir: str,
    strategy_instance: str,
    trading_date: date,
    session_id: str,
    reason: str,
) -> S23RealCaptureEnablement:
    if not output_dir or not strategy_instance or not session_id or not reason:
        raise ValueError("M7 capture enablement requires output_dir, strategy_instance, session_id, and reason.")
    return S23RealCaptureEnablement(
        enabled=True,
        method="EXPLICIT_SESSION_DEBUG_OVERRIDE",
        output_dir=output_dir,
        strategy_instance=strategy_instance,
        trading_date=trading_date,
        session_id=session_id,
        reason=reason,
    )


def capture_enabled_for_session(
    enablement: S23RealCaptureEnablement,
    *,
    strategy_instance: str,
    trading_date: date,
    session_id: str,
) -> bool:
    return (
        enablement.enabled
        and enablement.strategy_instance == strategy_instance
        and enablement.trading_date == trading_date
        and enablement.session_id == session_id
    )


def normalize_real_capture_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize(packet)
    _assert_no_sensitive_values(normalized)
    return normalized


def validate_real_capture_packet(packet: Mapping[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if packet.get("schema_version") != SCHEMA_VERSION:
        issues.append("INVALID_SCHEMA_VERSION")
    for section in REQUIRED_PACKET_SECTIONS:
        if section not in packet:
            issues.append(f"MISSING_SECTION:{section}")
    provenance = packet.get("provenance")
    if not isinstance(provenance, Mapping):
        issues.append("MISSING_PROVENANCE")
    else:
        fields = packet.get("field_provenance", {})
        if not isinstance(fields, Mapping) or not fields:
            issues.append("MISSING_FIELD_PROVENANCE")
    if packet.get("execution_authority", {}).get("refactored_authority") != "NONE":
        issues.append("REFACTORED_EXECUTION_AUTHORITY_NOT_NONE")
    if packet.get("refactored_shadow_result", {}).get("execution_intent") not in (None, "NONE"):
        issues.append("SHADOW_RESULT_HAS_EXECUTION_INTENT")
    return tuple(issues)


def classify_real_capture_packet(packet: Mapping[str, Any]) -> str:
    missing = tuple(packet.get("missing_or_derived_fields", {}).get("missing", ()))
    derived = tuple(packet.get("missing_or_derived_fields", {}).get("derived", ()))
    supplemented = tuple(packet.get("missing_or_derived_fields", {}).get("supplemented", ()))
    if packet.get("session_comparable") is False:
        return "SESSION_NOT_COMPARABLE"
    if missing:
        return "PARTIAL_CAPTURE"
    if supplemented:
        return "CAPTURED_WITH_SYNTHETIC_SUPPLEMENT"
    if derived:
        return "CAPTURED_WITH_DERIVED_FIELDS"
    return "FULLY_CAPTURED"


def compare_reference_to_shadow(
    *,
    reference: Mapping[str, Any],
    shadow: Mapping[str, Any],
    fields: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    compared: dict[str, dict[str, Any]] = {}
    for field in fields:
        reference_has = field in reference and reference.get(field) is not None
        shadow_has = field in shadow and shadow.get(field) is not None
        if not reference_has and not shadow_has:
            classification = "NOT_COMPARABLE"
        elif not reference_has:
            classification = "MISSING_LEGACY_OUTPUT"
        elif not shadow_has:
            classification = "MISSING_CAPTURED_INPUT"
        elif reference.get(field) == shadow.get(field):
            classification = "MATCH"
        else:
            classification = "IMPLEMENTATION_MISMATCH"
        compared[field] = {
            "legacy": reference.get(field),
            "shadow": shadow.get(field),
            "classification": classification,
        }
    return compared


def build_real_capture_gap_matrix(packet: Mapping[str, Any]) -> dict[str, Any]:
    missing = tuple(packet.get("missing_or_derived_fields", {}).get("missing", ()))
    derived = tuple(packet.get("missing_or_derived_fields", {}).get("derived", ()))
    supplemented = tuple(packet.get("missing_or_derived_fields", {}).get("supplemented", ()))
    return {
        "schema_version": "tfis.phase3d.m7.real_capture_gap_matrix.v1",
        "evidence_classification": packet.get("evidence_classification"),
        "gaps": [
            {"field": field, "classification": "MISSING_CAPTURED_INPUT"}
            for field in missing
        ],
        "derived_fields": [
            {"field": field, "classification": "CAPTURED_WITH_DERIVED_FIELDS"}
            for field in derived
        ],
        "supplemented_fields": [
            {"field": field, "classification": "CAPTURED_WITH_SYNTHETIC_SUPPLEMENT"}
            for field in supplemented
        ],
    }


def shadow_trade_is_observation_only(shadow_result: Mapping[str, Any]) -> bool:
    if shadow_result.get("final_decision_status") != "SHADOW_DECISION_TRADE":
        return True
    return shadow_result.get("execution_intent") in (None, "NONE")


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            text = str(key).lower()
            result[str(key)] = (
                "REDACTED"
                if any(fragment in text for fragment in SENSITIVE_KEY_FRAGMENTS)
                else _normalize(item)
            )
        return result
    if isinstance(value, tuple | list):
        return [_normalize(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _assert_no_sensitive_values(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            text = str(key).lower()
            if any(fragment in text for fragment in SENSITIVE_KEY_FRAGMENTS):
                if item != "REDACTED":
                    raise ValueError(f"sensitive capture field rejected: {key}")
            _assert_no_sensitive_values(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_sensitive_values(item)
