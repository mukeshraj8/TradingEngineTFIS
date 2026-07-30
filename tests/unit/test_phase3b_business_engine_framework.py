from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tfis.domain import (
    AuditEvidence,
    BusinessEngineCapability,
    BusinessEngineContext,
    BusinessEngineEvidence,
    BusinessEngineInput,
    BusinessEngineMetrics,
    BusinessEngineQuality,
    BusinessEngineRegistry,
    BusinessEngineRegistryError,
    BusinessEngineResult,
    BusinessEngineStatus,
    BusinessEngineValidation,
    EvidenceAvailability,
    EvidenceProvenance,
    ProvenancedValue,
    TFISProductType,
    business_engine_catalog_json,
    load_business_engine_registry,
    validate_business_engine_invocation,
)


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "config" / "business_engines" / "catalog.yaml"


def test_phase3b_catalog_loads_with_deterministic_dependency_order() -> None:
    first = load_business_engine_registry(CATALOG)
    second = load_business_engine_registry(CATALOG)

    assert set(first.execution_order) == {
        "market_structure",
        "monthly_status",
        "gap",
        "entry",
        "contract_selection",
        "risk",
        "lifecycle",
        "execution_intent",
    }
    assert first.execution_order.index("market_structure") < first.execution_order.index("monthly_status")
    assert first.execution_order.index("monthly_status") < first.execution_order.index("entry")
    assert first.execution_order.index("monthly_status") < first.execution_order.index("gap")
    assert first.execution_order.index("contract_selection") < first.execution_order.index("risk")
    assert first.execution_order.index("risk") < first.execution_order.index("lifecycle")
    assert first.execution_order.index("lifecycle") < first.execution_order.index("execution_intent")
    assert business_engine_catalog_json(first) == business_engine_catalog_json(second)
    assert len(first.definitions) == 8


def test_engine_definitions_and_registry_are_immutable() -> None:
    registry = load_business_engine_registry(CATALOG)
    definition = registry.get("entry")

    with pytest.raises(FrozenInstanceError):
        definition.purpose = "changed"
    with pytest.raises(TypeError):
        registry.definitions["new_engine"] = definition
    assert definition.required_capabilities == (
        BusinessEngineCapability.MARKET_STRUCTURE,
        BusinessEngineCapability.MONTHLY_STATUS,
    )
    assert definition.provided_capabilities == (
        BusinessEngineCapability.ENTRY,
        BusinessEngineCapability.BASE_ENTRY,
        BusinessEngineCapability.EFFECTIVE_ENTRY,
        BusinessEngineCapability.ENTRY_QUALIFICATION,
        BusinessEngineCapability.RECALCULATED_ENTRY,
    )


def test_duplicate_engine_ids_fail_closed(tmp_path: Path) -> None:
    duplicate_catalog = tmp_path / "catalog.yaml"
    duplicate_catalog.write_text(
        """
schema_version: test
engines:
  - engine_id: duplicate
    display_name: One
    purpose: one
    stage: MARKET_STRUCTURE
    schema_version: test
    required_inputs: []
    optional_inputs: []
    produced_outputs: []
    evidence_outputs: []
    validation_rules: []
    failure_modes: []
    quality_metrics: []
    state_requirements: STATELESS
    dependencies: []
    required_capabilities: []
    provided_capabilities: [MARKET_STRUCTURE]
    supported_products: [FUTURES]
    supported_strategy_families: ["*"]
    performance: &perf
      expected_execution_frequency: once
      expected_input_size: bounded
      cacheable: true
      deterministic: true
      parallel_safe: true
      state_requirement: STATELESS
      criticality: LOW
  - engine_id: duplicate
    display_name: Two
    purpose: two
    stage: MARKET_STRUCTURE
    schema_version: test
    required_inputs: []
    optional_inputs: []
    produced_outputs: []
    evidence_outputs: []
    validation_rules: []
    failure_modes: []
    quality_metrics: []
    state_requirements: STATELESS
    dependencies: []
    required_capabilities: []
    provided_capabilities: [MARKET_STRUCTURE]
    supported_products: [FUTURES]
    supported_strategy_families: ["*"]
    performance: *perf
""",
        encoding="utf-8",
    )

    with pytest.raises(BusinessEngineRegistryError) as error:
        load_business_engine_registry(duplicate_catalog)

    assert [issue.code for issue in error.value.issues] == ["DUPLICATE_ENGINE_ID"]


def test_unknown_dependency_and_unsatisfied_capability_are_validation_errors() -> None:
    registry = load_business_engine_registry(CATALOG)
    entry = registry.get("entry")
    broken_dependency = replace(entry, engine_id="broken_dependency", dependencies=("missing",))
    broken_capability = replace(
        entry,
        engine_id="broken_capability",
        dependencies=("market_structure",),
        required_capabilities=(BusinessEngineCapability.MONTHLY_STATUS,),
    )

    with pytest.raises(BusinessEngineRegistryError) as dependency_error:
        BusinessEngineRegistry({"broken_dependency": broken_dependency})
    with pytest.raises(BusinessEngineRegistryError) as capability_error:
        BusinessEngineRegistry({"market_structure": registry.get("market_structure"), "broken_capability": broken_capability})

    assert "UNKNOWN_ENGINE_DEPENDENCY" in {issue.code for issue in dependency_error.value.issues}
    assert "UNSATISFIED_ENGINE_CAPABILITY" in {issue.code for issue in capability_error.value.issues}


def test_circular_dependencies_are_rejected() -> None:
    registry = load_business_engine_registry(CATALOG)
    first = replace(registry.get("market_structure"), dependencies=("monthly_status",))
    second = registry.get("monthly_status")

    with pytest.raises(BusinessEngineRegistryError) as error:
        BusinessEngineRegistry({"market_structure": first, "monthly_status": second})

    assert "CIRCULAR_ENGINE_DEPENDENCY" in {issue.code for issue in error.value.issues}


def test_invocation_validation_covers_inputs_product_family_capability_config_and_state() -> None:
    registry = load_business_engine_registry(CATALOG)
    definition = replace(
        registry.get("lifecycle"),
        supported_products=(TFISProductType.OPTION_SELLING,),
        supported_strategy_families=("option_selling",),
    )
    context = BusinessEngineContext(
        evaluation_id="eval-1",
        strategy_family_id="unsupported_family",
        strategy_definition_id="strategy-1",
        strategy_version="1.0.0",
        strategy_instance_id="instance-1",
        product_type=TFISProductType.FUTURES,
        evaluation_timestamp=datetime(2026, 7, 29, 9, 30, tzinfo=timezone.utc),
        configuration_hash="",
        available_capabilities=(),
        state_refs={},
    )
    engine_input = BusinessEngineInput(
        engine_id="different",
        payload={"risk_state": "available"},
        input_completeness=BusinessEngineQuality.PARTIAL,
    )

    validation = validate_business_engine_invocation(definition, context, engine_input)

    assert validation.passed is False
    assert {
        "ENGINE_INPUT_MISMATCH",
        "MISSING_REQUIRED_INPUT",
        "UNSUPPORTED_PRODUCT",
        "UNSUPPORTED_STRATEGY_FAMILY",
        "MISSING_CAPABILITY",
        "INCOMPATIBLE_CONFIGURATION",
        "MISSING_STATE",
    }.issubset({issue.code for issue in validation.issues})


def test_engine_result_allows_no_confidence_and_preserves_metrics_and_provenance() -> None:
    evidence = BusinessEngineEvidence(
        raw_evidence_refs=("source.price_context",),
        derived_evidence_refs=("entry_state",),
        formula_references=("workbook.requirement.ENTRY",),
        requirement_references=("TFIS.PHASE3B.ENTRY.CONTRACT",),
        intermediate_values={"entry": {"value": "203.5"}},
        quality_notes=("no confidence model defined",),
        data_warnings=("reference-only placeholder",),
        missing_inputs=("option_chain",),
        provenance={"catalog": "phase3b"},
    )

    result = BusinessEngineResult(
        engine_id="entry",
        status=BusinessEngineStatus.BLOCKED,
        quality=BusinessEngineQuality.PARTIAL,
        confidence=None,
        warnings=("missing option chain",),
        errors=(),
        evidence=evidence,
        intermediate_values={"entry": "blocked"},
        metrics=BusinessEngineMetrics(
            processing_duration_seconds=0.001,
            dependency_versions={"catalog": "phase3b.business_engine_catalog.v1"},
        ),
        validation=BusinessEngineValidation(),
        input_completeness=BusinessEngineQuality.PARTIAL,
        capability_usage=(BusinessEngineCapability.ENTRY,),
        provenance={"engine_definition": "entry"},
    )

    fragment = result.evidence.to_decision_evidence_fragment(result.engine_id)
    audit = AuditEvidence(
        policy_keys=(),
        requirement_ids=("TFIS.PHASE3B.ENTRY.CONTRACT",),
        formula_expressions=(),
        intermediate_values=(
            (
                "business_engine.entry",
                ProvenancedValue(
                    "entry",
                    EvidenceAvailability.AVAILABLE,
                    EvidenceProvenance.DERIVED,
                    "business_engine",
                ),
            ),
        ),
        data_quality_warnings=result.warnings,
        evidence_classifications=(EvidenceProvenance.DERIVED,),
        compatibility_payload={"business_engine_fragment": fragment["engine_id"]},
    )

    assert result.confidence is None
    assert fragment["engine_id"] == "entry"
    assert fragment["evidence"]["intermediate_values"]["entry"]["value"] == "203.5"
    assert audit.compatibility_payload["business_engine_fragment"] == "entry"
