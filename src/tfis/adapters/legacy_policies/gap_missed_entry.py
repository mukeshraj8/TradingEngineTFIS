from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from tfis.backtest import EntryMissedInput, S23EntryMissedDetector
from tfis.domain import (
    MonthlyStatus,
    OptionType,
    TradePlan,
    TFISProductType,
)
from tfis.domain.gap_missed_entry import (
    ComparisonOperator,
    CompetingRuleBehavior,
    GapClassification,
    GapClassificationResult,
    GapDirection,
    GapMeasurement,
    GapMissedEntryEngine,
    GapMissedEntryEngineInput,
    GapMissedEntryEvidence,
    GapMissedEntryFailure,
    GapMissedEntryPolicyOutcome,
    GapMissedEntryQuality,
    GapObservation,
    GapReference,
    MissedEntryClassificationResult,
    MissedEntryComparisonRule,
    MissedEntryObservationSource,
    MissedEntryState,
    ObservationValue,
    RecalculationDownstreamAction,
    RecalculationInstruction,
    RecalculationStatus,
    RuleExecutionPermission,
    RuleIssueClassification,
    SessionTimingEvidence,
    TimingObservationRequirement,
    TimingWindowState,
    UnresolvedRuleIssue,
)
from tfis.domain.market_levels import MarketLevels
from tfis.strategy.s23_recalculation import (
    IntradaySnapshot,
    RecalculationInput,
    S23RecalculationEngine,
)


S21_COMPATIBILITY_POLICY_KEY = "legacy.s21.gap_missed_entry.evidence_only_v1"
S21_UNRESOLVED_TIMING_POLICY_KEY = "legacy.s21.gap_missed_entry.unresolved_timing_v1"
S23_BACKTEST_LOW_POLICY_KEY = "legacy.s23.gap_missed_entry.backtest_low_v1"
S23_PAPER_LIVE_HIGH_POLICY_KEY = "legacy.s23.gap_missed_entry.paper_live_high_v1"
S23_UNRESOLVED_POLICY_KEY = "legacy.s23.gap_missed_entry.unresolved_put_v1"

S21_DEFINITION_ID = "S21_BANKNIFTY_OP_SELL_MONTHLY"
S23_DEFINITION_ID = "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
SUPPORTED_VERSION = "1.0.0"

S23_BULL_CALL_BRANCH = "NIFTY_OP_SELL_WK_DIFF_2D_3D"
S23_BEAR_CALL_BRANCH = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
S23_BULL_PUT_BRANCH = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT"
S23_BEAR_PUT_BRANCH = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
S23_BRANCHES = (
    S23_BULL_CALL_BRANCH,
    S23_BEAR_CALL_BRANCH,
    S23_BULL_PUT_BRANCH,
    S23_BEAR_PUT_BRANCH,
)
S23_PUT_BRANCHES = (S23_BULL_PUT_BRANCH, S23_BEAR_PUT_BRANCH)


class GapMissedEntryPolicyResolutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LegacyGapMissedEntryComposition:
    strategy_definition_id: str
    strategy_version: str
    policy_key: str


@dataclass(frozen=True, slots=True)
class LegacyGapMissedEntryCompositionConfig:
    version: str
    records: Mapping[tuple[str, str], LegacyGapMissedEntryComposition]

    def policy_for_definition_version(
        self,
        strategy_definition_id: str,
        strategy_version: str,
    ) -> LegacyGapMissedEntryComposition:
        key = (strategy_definition_id, strategy_version)
        try:
            return self.records[key]
        except KeyError as exc:
            raise GapMissedEntryPolicyResolutionError(
                f"No gap/missed-entry policy configured for {strategy_definition_id}@{strategy_version}"
            ) from exc


@dataclass(frozen=True, slots=True)
class LegacyGapMissedEntryEvaluationInput:
    strategy_family_id: str
    strategy_definition_id: str
    strategy_version: str
    strategy_instance_id: str
    product_type: TFISProductType
    configuration_hash: str
    branch_key: str
    option_type: OptionType | None
    monthly_status: MonthlyStatus | str | None
    timing: SessionTimingEvidence
    base_entry_price: Decimal | float | int | str | None
    market_levels: MarketLevels | None = None
    option_levels: Mapping[str, float] = MappingProxyType({})
    strategy_parameters: Mapping[str, float] = MappingProxyType({})
    base_trade_plan: TradePlan | None = None
    orpt_snapshot: IntradaySnapshot | None = None
    rc_snapshot: IntradaySnapshot | None = None
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_levels", MappingProxyType(dict(self.option_levels)))
        object.__setattr__(self, "strategy_parameters", MappingProxyType(dict(self.strategy_parameters)))
        object.__setattr__(self, "provenance", MappingProxyType({str(key): str(value) for key, value in self.provenance.items()}))


class LegacyGapMissedEntryPolicyRegistry:
    def __init__(self, policies: Mapping[str, Any]) -> None:
        duplicates = _duplicate_keys(tuple(policies))
        if duplicates:
            raise GapMissedEntryPolicyResolutionError(
                "duplicate gap/missed-entry policy key(s): " + ", ".join(duplicates)
            )
        self._policies = MappingProxyType(dict(sorted(policies.items())))

    @classmethod
    def default(cls) -> LegacyGapMissedEntryPolicyRegistry:
        return cls(
            {
                S21_COMPATIBILITY_POLICY_KEY: S21GapMissedEntryCompatibilityPolicy(
                    S21_COMPATIBILITY_POLICY_KEY,
                    TimingObservationRequirement.NOT_APPLICABLE,
                ),
                S21_UNRESOLVED_TIMING_POLICY_KEY: S21GapMissedEntryCompatibilityPolicy(
                    S21_UNRESOLVED_TIMING_POLICY_KEY,
                    TimingObservationRequirement.UNRESOLVED,
                ),
                S23_BACKTEST_LOW_POLICY_KEY: S23GapMissedEntryCompatibilityPolicy(
                    S23_BACKTEST_LOW_POLICY_KEY,
                    MissedEntryObservationSource.OPTION_LOW,
                ),
                S23_PAPER_LIVE_HIGH_POLICY_KEY: S23GapMissedEntryCompatibilityPolicy(
                    S23_PAPER_LIVE_HIGH_POLICY_KEY,
                    MissedEntryObservationSource.OPTION_HIGH,
                ),
                S23_UNRESOLVED_POLICY_KEY: UnresolvedS23PutGapMissedEntryCompatibilityPolicy(),
            }
        )

    @property
    def policy_keys(self) -> tuple[str, ...]:
        return tuple(self._policies)

    def get(self, policy_key: str) -> Any:
        try:
            return self._policies[policy_key]
        except KeyError as exc:
            raise GapMissedEntryPolicyResolutionError(
                f"Unknown gap/missed-entry policy key {policy_key!r}"
            ) from exc


class S21GapMissedEntryCompatibilityPolicy:
    def __init__(
        self,
        policy_key: str = S21_COMPATIBILITY_POLICY_KEY,
        timing_requirement: TimingObservationRequirement = TimingObservationRequirement.NOT_APPLICABLE,
    ) -> None:
        self.policy_key = policy_key
        self._timing_requirement = timing_requirement

    def evaluate(self, engine_input: GapMissedEntryEngineInput) -> GapMissedEntryPolicyOutcome:
        unresolved = ()
        failures = ()
        if self._timing_requirement is TimingObservationRequirement.UNRESOLVED:
            unresolved = (
                UnresolvedRuleIssue(
                    issue_code="S21_ORPT_RC_APPLICABILITY_UNRESOLVED",
                    classification=RuleIssueClassification.INSUFFICIENT_EVIDENCE,
                    affected_strategy_definition_id=engine_input.strategy_definition_id,
                    affected_strategy_version=engine_input.strategy_version,
                    affected_branch=str(engine_input.policy_configuration.get("branch_key") or "UNKNOWN"),
                    competing_observed_behaviors=(),
                    authoritative_source_status=RuleIssueClassification.USER_CLARIFICATION_REQUIRED,
                    execution_permission=RuleExecutionPermission.FAIL_CLOSED,
                    fail_closed_reason="S21 ORPT/RC applicability is unresolved.",
                ),
            )
            failures = (GapMissedEntryFailure.UNRESOLVED_COMPARISON_POLICY,)
        return GapMissedEntryPolicyOutcome(
            gap=_gap_result(
                engine_input,
                GapClassification.INVALID if failures else GapClassification.NOT_APPLICABLE,
                GapDirection.UNKNOWN if failures else GapDirection.NOT_APPLICABLE,
                applicable=False,
                quality=GapMissedEntryQuality.INVALID if failures else GapMissedEntryQuality.NOT_APPLICABLE,
                requirement_reference="S21_ORPT_RC_APPLICABILITY",
            ),
            missed_entry=MissedEntryClassificationResult(
                applicable=False,
                status=MissedEntryState.NOT_APPLICABLE if not failures else MissedEntryState.INVALID,
                comparison_rule=None,
                observed_value=None,
                entry_reference_value=engine_input.entry_reference_value,
                branch_key=str(engine_input.policy_configuration.get("branch_key") or "UNKNOWN"),
                direction=GapDirection.NOT_APPLICABLE,
                quality=GapMissedEntryQuality.NOT_APPLICABLE if not failures else GapMissedEntryQuality.INVALID,
                warnings=("S21 gap/missed-entry timing is evidence-only in this profile.",),
                provenance={"policy_key": self.policy_key, "timing_requirement": self._timing_requirement.value},
            ),
            recalculation=RecalculationInstruction(
                applicable=False,
                status=RecalculationStatus.NOT_REQUIRED if not failures else RecalculationStatus.INVALID,
                branch_key=str(engine_input.policy_configuration.get("branch_key") or "UNKNOWN"),
                policy_key=self.policy_key,
                downstream_action=RecalculationDownstreamAction.NONE if not failures else RecalculationDownstreamAction.FAIL_CLOSED,
                failures=failures,
                warnings=("No S21 gap-up/gap-down formula is declared confirmed.",),
                provenance={"policy_key": self.policy_key},
            ),
            unresolved_issues=unresolved,
            warnings=("S21 ORPT/RC applicability is not inferred from timing fields.",),
            failures=failures,
            provenance={"policy_key": self.policy_key, "strategy": "S21"},
        )


class S23GapMissedEntryCompatibilityPolicy:
    def __init__(
        self,
        policy_key: str,
        put_observed_source: MissedEntryObservationSource,
        *,
        detector: S23EntryMissedDetector | None = None,
        recalculator: S23RecalculationEngine | None = None,
    ) -> None:
        if put_observed_source not in (
            MissedEntryObservationSource.OPTION_LOW,
            MissedEntryObservationSource.OPTION_HIGH,
        ):
            raise ValueError("S23 PUT profile must select OPTION_LOW or OPTION_HIGH")
        self.policy_key = policy_key
        self._put_observed_source = put_observed_source
        self._detector = detector or S23EntryMissedDetector()
        self._recalculator = recalculator or S23RecalculationEngine()

    def evaluate(self, engine_input: GapMissedEntryEngineInput) -> GapMissedEntryPolicyOutcome:
        branch = str(engine_input.policy_configuration.get("branch_key") or "")
        option_type = str(engine_input.policy_configuration.get("option_type") or "")
        failures = _basic_s23_failures(engine_input, branch, option_type)
        observed_source = self._observed_source(option_type)
        observed_value = _observation_value(engine_input, observed_source)
        if observed_value is None:
            failures = failures + (GapMissedEntryFailure.REQUIRED_OBSERVATION_MISSING,)
        entry_value = engine_input.entry_reference_value
        if entry_value is None:
            failures = failures + (GapMissedEntryFailure.REQUIRED_OBSERVATION_MISSING,)
        missed = False
        legacy_entry_missed = None
        if not failures and observed_value is not None and entry_value is not None:
            missed = observed_value < entry_value
            legacy_entry_missed = _legacy_low_missed(engine_input)
        rule = MissedEntryComparisonRule(
            rule_id=f"{self.policy_key}.missed_entry",
            observed_source=observed_source,
            operator=ComparisonOperator.LESS_THAN,
            reference_key="entry_price",
            branch_key=branch or "UNKNOWN",
            policy_key=self.policy_key,
            formula_reference="S23_ORPT_RC_COMPATIBILITY",
            requirement_reference="S23_ORPT_RC",
            compatibility_metadata={
                "profile": self.policy_key,
                "legacy_low_detector_result": str(legacy_entry_missed.entry_missed) if legacy_entry_missed else "UNAVAILABLE",
            },
        )
        recalculation = _s23_recalculation_instruction(
            engine_input,
            policy_key=self.policy_key,
            missed=missed,
            failures=failures,
        )
        return GapMissedEntryPolicyOutcome(
            gap=_gap_result(
                engine_input,
                _gap_classification(engine_input),
                _gap_direction(engine_input),
                applicable=True,
                quality=GapMissedEntryQuality.INVALID if failures else GapMissedEntryQuality.VALID,
                requirement_reference="S23_GAP_COMPATIBILITY",
            ),
            missed_entry=MissedEntryClassificationResult(
                applicable=True,
                status=MissedEntryState.INVALID if failures else (MissedEntryState.MISSED if missed else MissedEntryState.NOT_MISSED),
                comparison_rule=rule,
                observed_value=observed_value,
                entry_reference_value=entry_value,
                branch_key=branch or "UNKNOWN",
                direction=GapDirection.DOWN if missed else GapDirection.FLAT,
                quality=GapMissedEntryQuality.INVALID if failures else GapMissedEntryQuality.VALID,
                provenance={"policy_key": self.policy_key, "profile": self.policy_key},
            ),
            recalculation=recalculation,
            warnings=(),
            failures=failures,
            provenance={"policy_key": self.policy_key, "strategy": "S23"},
        )

    def _observed_source(self, option_type: str) -> MissedEntryObservationSource:
        if option_type == OptionType.PUT.value:
            return self._put_observed_source
        return MissedEntryObservationSource.OPTION_LOW


class UnresolvedS23PutGapMissedEntryCompatibilityPolicy:
    policy_key = S23_UNRESOLVED_POLICY_KEY

    def evaluate(self, engine_input: GapMissedEntryEngineInput) -> GapMissedEntryPolicyOutcome:
        issue = UnresolvedRuleIssue(
            issue_code="S23_PUT_MISSED_ENTRY_PROFILE_UNRESOLVED",
            classification=RuleIssueClassification.USER_CLARIFICATION_REQUIRED,
            affected_strategy_definition_id=engine_input.strategy_definition_id,
            affected_strategy_version=engine_input.strategy_version,
            affected_branch=str(engine_input.policy_configuration.get("branch_key") or "UNKNOWN"),
            competing_observed_behaviors=(
                CompetingRuleBehavior(
                    "legacy_backtest_low_profile",
                    MissedEntryObservationSource.OPTION_LOW,
                    ComparisonOperator.LESS_THAN,
                    "backtest",
                ),
                CompetingRuleBehavior(
                    "legacy_paper_live_high_profile",
                    MissedEntryObservationSource.OPTION_HIGH,
                    ComparisonOperator.LESS_THAN,
                    "paper_live",
                ),
            ),
            authoritative_source_status=RuleIssueClassification.WORKBOOK_VERIFICATION_REQUIRED,
            execution_permission=RuleExecutionPermission.FAIL_CLOSED,
            fail_closed_reason="Executable S23 PUT configuration did not select a compatibility profile.",
        )
        return GapMissedEntryPolicyOutcome(
            gap=_gap_result(
                engine_input,
                GapClassification.INVALID,
                GapDirection.UNKNOWN,
                applicable=True,
                quality=GapMissedEntryQuality.INVALID,
                requirement_reference="S23_PUT_PROFILE_UNRESOLVED",
            ),
            missed_entry=MissedEntryClassificationResult(
                applicable=True,
                status=MissedEntryState.INVALID,
                comparison_rule=None,
                observed_value=None,
                entry_reference_value=engine_input.entry_reference_value,
                branch_key=str(engine_input.policy_configuration.get("branch_key") or "UNKNOWN"),
                direction=GapDirection.UNKNOWN,
                quality=GapMissedEntryQuality.INVALID,
            ),
            recalculation=RecalculationInstruction(
                applicable=True,
                status=RecalculationStatus.INVALID,
                branch_key=str(engine_input.policy_configuration.get("branch_key") or "UNKNOWN"),
                policy_key=self.policy_key,
                downstream_action=RecalculationDownstreamAction.FAIL_CLOSED,
                failures=(GapMissedEntryFailure.UNRESOLVED_COMPARISON_POLICY,),
            ),
            unresolved_issues=(issue,),
            failures=(GapMissedEntryFailure.UNRESOLVED_COMPARISON_POLICY,),
            provenance={"policy_key": self.policy_key, "strategy": "S23"},
        )


def evaluate_legacy_gap_missed_entry(
    compatibility_input: LegacyGapMissedEntryEvaluationInput,
    *,
    policy_key: str,
    registry: LegacyGapMissedEntryPolicyRegistry | None = None,
) -> Any:
    engine_input = gap_missed_entry_engine_input_from_legacy(compatibility_input, policy_key=policy_key)
    policy = (registry or LegacyGapMissedEntryPolicyRegistry.default()).get(policy_key)
    return GapMissedEntryEngine(policy).execute(engine_input)


def gap_missed_entry_engine_input_from_legacy(
    compatibility_input: LegacyGapMissedEntryEvaluationInput,
    *,
    policy_key: str,
) -> GapMissedEntryEngineInput:
    return GapMissedEntryEngineInput(
        strategy_family_id=compatibility_input.strategy_family_id,
        strategy_definition_id=compatibility_input.strategy_definition_id,
        strategy_version=compatibility_input.strategy_version,
        strategy_instance_id=compatibility_input.strategy_instance_id,
        product_type=compatibility_input.product_type,
        resolved_configuration_hash=compatibility_input.configuration_hash,
        policy_key=policy_key,
        timing=compatibility_input.timing,
        monthly_status=_monthly_status_value(compatibility_input.monthly_status),
        market_structure_refs=_market_structure_refs(compatibility_input.market_levels),
        entry_reference_value=compatibility_input.base_entry_price,
        policy_configuration={
            "branch_key": compatibility_input.branch_key,
            "option_type": compatibility_input.option_type.value if compatibility_input.option_type else None,
            "option_levels": dict(compatibility_input.option_levels),
            "strategy_parameters": dict(compatibility_input.strategy_parameters),
            "orpt_snapshot": _snapshot_mapping(compatibility_input.orpt_snapshot),
            "rc_snapshot": _snapshot_mapping(compatibility_input.rc_snapshot),
            "base_trade_plan": _trade_plan_mapping(compatibility_input.base_trade_plan),
            "required_market_structure_refs": _required_market_refs(compatibility_input.branch_key),
            "supported_monthly_statuses": _supported_monthly_statuses(compatibility_input.strategy_definition_id),
        },
        provenance=compatibility_input.provenance,
    )


def load_legacy_gap_missed_entry_composition_config(
    path: str | Path,
) -> LegacyGapMissedEntryCompositionConfig:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    identity = payload.get("identity_compositions")
    if not isinstance(identity, dict) or not identity:
        raise GapMissedEntryPolicyResolutionError("identity_compositions are required")
    records: dict[tuple[str, str], LegacyGapMissedEntryComposition] = {}
    for raw_key, data in identity.items():
        if not isinstance(data, dict):
            raise GapMissedEntryPolicyResolutionError(f"composition for {raw_key} must be a mapping")
        if "@" not in str(raw_key):
            raise GapMissedEntryPolicyResolutionError("composition keys must use strategy_definition_id@strategy_version")
        definition_id, version = str(raw_key).split("@", 1)
        policy_key = str(data.get("gap_missed_entry_policy") or "").strip()
        if not policy_key:
            raise GapMissedEntryPolicyResolutionError(f"composition for {raw_key} requires gap_missed_entry_policy")
        if policy_key == S23_UNRESOLVED_POLICY_KEY:
            raise GapMissedEntryPolicyResolutionError("unresolved executable S23 PUT profile is not allowed in composition")
        record_key = (definition_id, version)
        if record_key in records:
            raise GapMissedEntryPolicyResolutionError(f"duplicate composition for {raw_key}")
        records[record_key] = LegacyGapMissedEntryComposition(definition_id, version, policy_key)
    return LegacyGapMissedEntryCompositionConfig(
        version=str(payload.get("version") or "unknown"),
        records=MappingProxyType(records),
    )


def resolve_legacy_gap_missed_entry_policy(
    config: LegacyGapMissedEntryCompositionConfig,
    *,
    strategy_definition_id: str,
    strategy_version: str,
    strategy_family_id: str | None = None,
) -> Any:
    if not strategy_definition_id or not strategy_version:
        raise GapMissedEntryPolicyResolutionError("strategy definition and version are required")
    if strategy_family_id and strategy_definition_id == strategy_family_id:
        raise GapMissedEntryPolicyResolutionError("family-only gap/missed-entry policy resolution is not allowed")
    record = config.policy_for_definition_version(strategy_definition_id, strategy_version)
    return LegacyGapMissedEntryPolicyRegistry.default().get(record.policy_key)


def _basic_s23_failures(
    engine_input: GapMissedEntryEngineInput,
    branch: str,
    option_type: str,
) -> tuple[GapMissedEntryFailure, ...]:
    failures: list[GapMissedEntryFailure] = []
    if engine_input.product_type is not TFISProductType.OPTION_SELLING:
        failures.append(GapMissedEntryFailure.UNSUPPORTED_PRODUCT)
    if branch not in S23_BRANCHES:
        failures.append(GapMissedEntryFailure.UNSUPPORTED_STRATEGY_FAMILY)
    if option_type not in (OptionType.CALL.value, OptionType.PUT.value):
        failures.append(GapMissedEntryFailure.STRATEGY_COMPOSITION_MISMATCH)
    if engine_input.monthly_status in (None, MonthlyStatus.UNKNOWN.value, "UNKNOWN"):
        failures.append(GapMissedEntryFailure.UNSUPPORTED_MONTHLY_STATUS_BRANCH)
    if engine_input.timing.orpt_observation is None:
        failures.append(GapMissedEntryFailure.REQUIRED_OBSERVATION_MISSING)
    if engine_input.timing.rc_observation is None:
        failures.append(GapMissedEntryFailure.REQUIRED_OBSERVATION_MISSING)
    return tuple(failures)


def _legacy_low_missed(engine_input: GapMissedEntryEngineInput) -> Any:
    snapshot = _snapshot_from_config(engine_input.policy_configuration.get("orpt_snapshot"))
    option_type = OptionType(str(engine_input.policy_configuration.get("option_type")))
    if snapshot is None or engine_input.entry_reference_value is None:
        return None
    return S23EntryMissedDetector().detect(
        EntryMissedInput(
            option_type=option_type,
            entry_price=float(engine_input.entry_reference_value),
            orpt_snapshot=snapshot,
        )
    )


def _s23_recalculation_instruction(
    engine_input: GapMissedEntryEngineInput,
    *,
    policy_key: str,
    missed: bool,
    failures: tuple[GapMissedEntryFailure, ...],
) -> RecalculationInstruction:
    branch = str(engine_input.policy_configuration.get("branch_key") or "UNKNOWN")
    if failures:
        return RecalculationInstruction(
            applicable=True,
            status=RecalculationStatus.INVALID,
            branch_key=branch,
            policy_key=policy_key,
            downstream_action=RecalculationDownstreamAction.FAIL_CLOSED,
            failures=failures,
        )
    if not missed:
        return RecalculationInstruction(
            applicable=False,
            status=RecalculationStatus.NOT_REQUIRED,
            branch_key=branch,
            policy_key=policy_key,
            downstream_action=RecalculationDownstreamAction.NONE,
        )
    try:
        result = S23RecalculationEngine().recalculate(
            RecalculationInput(
                branch_unique_code=branch,
                option_type=OptionType(str(engine_input.policy_configuration["option_type"])),
                monthly_status=MonthlyStatus(str(engine_input.monthly_status)),
                base_trade_plan=_trade_plan_from_config(engine_input.policy_configuration["base_trade_plan"]),
                market_levels=_market_levels_from_refs(engine_input.market_structure_refs),
                option_levels={key: float(value) for key, value in dict(engine_input.policy_configuration.get("option_levels") or {}).items()},
                parameters={key: float(value) for key, value in dict(engine_input.policy_configuration.get("strategy_parameters") or {}).items()},
                intraday_snapshot_at_orpt=_snapshot_from_config(engine_input.policy_configuration["orpt_snapshot"]),
                intraday_snapshot_at_recalc=_snapshot_from_config(engine_input.policy_configuration["rc_snapshot"]),
                entry_missed=True,
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        return RecalculationInstruction(
            applicable=True,
            status=RecalculationStatus.REQUIRED_INPUT_MISSING,
            branch_key=branch,
            policy_key=policy_key,
            downstream_action=RecalculationDownstreamAction.FAIL_CLOSED,
            failures=(GapMissedEntryFailure.RECALCULATION_INPUT_MISSING,),
            warnings=(str(exc),),
        )
    return RecalculationInstruction(
        applicable=True,
        status=RecalculationStatus.COMPLETED_BY_COMPATIBILITY_POLICY if result.recalculated else RecalculationStatus.NOT_REQUIRED,
        branch_key=branch,
        required_input_refs=("market_structure_refs", "option_levels", "strategy_parameters", "rc_snapshot"),
        supplied_values={
            "branch": branch,
            "source_rule": result.source_rule,
            "reason": result.reason,
        },
        policy_key=policy_key,
        formula_reference=result.source_rule,
        requirement_reference="S23_RECALCULATION_COMPATIBILITY",
        intermediate_evidence={"audit_notes": result.audit_notes},
        compatibility_outputs={
            "recalculated_start_strike": result.recalculated_start_strike,
            "recalculated_end_strike": result.recalculated_end_strike,
            "recalculated_ideal_premium": result.recalculated_ideal_premium,
            "recalculated_minimum_premium": result.recalculated_minimum_premium,
            "recalculated_entry_price": result.recalculated_entry_price,
        },
        downstream_action=RecalculationDownstreamAction.USE_COMPATIBILITY_OUTPUT,
    )


def _gap_result(
    engine_input: GapMissedEntryEngineInput,
    classification: GapClassification,
    direction: GapDirection,
    *,
    applicable: bool,
    quality: GapMissedEntryQuality,
    requirement_reference: str,
) -> GapClassificationResult:
    opening = engine_input.timing.orpt_observation or engine_input.timing.current_day_high
    reference = None
    if engine_input.entry_reference_value is not None:
        reference = GapReference(
            "entry_price",
            engine_input.entry_reference_value,
            MissedEntryObservationSource.LTP,
            requirement_reference=requirement_reference,
            provenance={"policy_key": engine_input.policy_key},
        )
    measurement = GapMeasurement(
        absolute_gap=_difference(opening.value, engine_input.entry_reference_value) if opening else None,
        percentage_gap=None,
        comparison_operator=ComparisonOperator.NOT_APPLICABLE if not applicable else ComparisonOperator.GREATER_THAN,
        threshold_buffer=None,
    )
    return GapClassificationResult(
        applicable=applicable,
        classification=classification,
        direction=direction,
        observation=GapObservation(
            applicable=applicable,
            opening_price=opening,
            reference=reference,
            policy_key=engine_input.policy_key,
            provenance={"policy_key": engine_input.policy_key},
        ),
        measurement=measurement,
        requirement_reference=requirement_reference,
        quality=quality,
        provenance={"policy_key": engine_input.policy_key},
    )


def _gap_classification(engine_input: GapMissedEntryEngineInput) -> GapClassification:
    high = engine_input.timing.current_day_high.value if engine_input.timing.current_day_high else None
    low = engine_input.timing.current_day_low.value if engine_input.timing.current_day_low else None
    entry = engine_input.entry_reference_value
    if high is None or low is None or entry is None:
        return GapClassification.UNAVAILABLE
    if low > entry:
        return GapClassification.GAP_UP
    if high < entry:
        return GapClassification.GAP_DOWN
    return GapClassification.NORMAL_OR_NO_GAP


def _gap_direction(engine_input: GapMissedEntryEngineInput) -> GapDirection:
    classification = _gap_classification(engine_input)
    if classification is GapClassification.GAP_UP:
        return GapDirection.UP
    if classification is GapClassification.GAP_DOWN:
        return GapDirection.DOWN
    if classification is GapClassification.NORMAL_OR_NO_GAP:
        return GapDirection.FLAT
    return GapDirection.UNKNOWN


def _observation_value(
    engine_input: GapMissedEntryEngineInput,
    source: MissedEntryObservationSource,
) -> Decimal | None:
    observation = {
        MissedEntryObservationSource.OPTION_LOW: engine_input.timing.orpt_observation,
        MissedEntryObservationSource.OPTION_HIGH: engine_input.timing.orpt_observation,
        MissedEntryObservationSource.CURRENT_DAY_HIGH: engine_input.timing.current_day_high,
        MissedEntryObservationSource.CURRENT_DAY_LOW: engine_input.timing.current_day_low,
    }.get(source)
    if observation is not None and observation.source is source:
        return observation.value
    snapshot = _snapshot_from_config(engine_input.policy_configuration.get("orpt_snapshot"))
    if snapshot is None:
        return None
    if source is MissedEntryObservationSource.OPTION_LOW:
        if snapshot.option_low is None:
            return None
        return Decimal(str(snapshot.option_low))
    if source is MissedEntryObservationSource.OPTION_HIGH:
        if snapshot.option_high is None:
            return None
        return Decimal(str(snapshot.option_high))
    return None


def _market_structure_refs(market_levels: MarketLevels | None) -> Mapping[str, str]:
    if market_levels is None:
        return MappingProxyType({})
    refs: dict[str, str] = {}
    for key in ("d2hh", "d2ll", "d3hh", "d3ll", "current_day_high", "current_day_low"):
        value = getattr(market_levels, key)
        if value is not None:
            refs[key] = str(value)
    return MappingProxyType(refs)


def _market_levels_from_refs(refs: Mapping[str, Any]) -> MarketLevels:
    return MarketLevels(
        d2hh=_float_or_none(refs.get("d2hh")),
        d2ll=_float_or_none(refs.get("d2ll")),
        d3hh=_float_or_none(refs.get("d3hh")),
        d3ll=_float_or_none(refs.get("d3ll")),
        current_day_high=_float_or_none(refs.get("current_day_high")),
        current_day_low=_float_or_none(refs.get("current_day_low")),
    )


def _snapshot_mapping(snapshot: IntradaySnapshot | None) -> Mapping[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "timestamp": snapshot.timestamp,
        "spot_low": snapshot.spot_low,
        "spot_high": snapshot.spot_high,
        "option_low": snapshot.option_low,
        "option_high": snapshot.option_high,
    }


def _snapshot_from_config(value: Any) -> IntradaySnapshot | None:
    if not isinstance(value, Mapping):
        return None
    timestamp = value.get("timestamp")
    if not isinstance(timestamp, datetime):
        timestamp = datetime.fromisoformat(str(timestamp))
    return IntradaySnapshot(
        timestamp=timestamp,
        spot_low=float(value["spot_low"]),
        spot_high=float(value["spot_high"]),
        option_low=_float_or_none(value["option_low"]),
        option_high=_float_or_none(value["option_high"]),
    )


def _trade_plan_mapping(plan: TradePlan | None) -> Mapping[str, Any] | None:
    if plan is None:
        return None
    return {
        "strategy_code": plan.strategy_code,
        "symbol": plan.symbol,
        "option_type": plan.option_type.value,
        "start_strike": plan.start_strike,
        "end_strike": plan.end_strike,
        "ideal_premium": plan.ideal_premium,
        "minimum_premium": plan.minimum_premium,
        "entry_price": plan.entry_price,
        "stoploss_price": plan.stoploss_price,
        "target_price": plan.target_price,
    }


def _trade_plan_from_config(data: Any) -> TradePlan:
    if not isinstance(data, Mapping):
        raise ValueError("base trade plan is required")
    return TradePlan(
        strategy_code=str(data["strategy_code"]),
        symbol=str(data["symbol"]),
        option_type=OptionType(str(data["option_type"])),
        start_strike=float(data["start_strike"]),
        end_strike=float(data["end_strike"]),
        ideal_premium=float(data["ideal_premium"]),
        minimum_premium=float(data["minimum_premium"]),
        entry_price=float(data["entry_price"]),
        stoploss_price=float(data["stoploss_price"]),
        target_price=float(data["target_price"]),
    )


def _required_market_refs(branch: str) -> tuple[str, ...]:
    if branch == S23_BULL_CALL_BRANCH:
        return ("d3ll",)
    if branch == S23_BEAR_CALL_BRANCH:
        return ("d2ll",)
    if branch == S23_BULL_PUT_BRANCH:
        return ("d2hh",)
    if branch == S23_BEAR_PUT_BRANCH:
        return ("d3hh",)
    return ()


def _supported_monthly_statuses(definition_id: str) -> tuple[str, ...]:
    if definition_id == S21_DEFINITION_ID:
        return (MonthlyStatus.BULL.value, MonthlyStatus.BEAR.value, MonthlyStatus.BULL_CF.value, MonthlyStatus.BEAR_CF.value)
    if definition_id == S23_DEFINITION_ID:
        return (MonthlyStatus.BULL.value, MonthlyStatus.BEAR.value, MonthlyStatus.BULL_CF.value, MonthlyStatus.BEAR_CF.value)
    return ()


def _monthly_status_value(value: MonthlyStatus | str | None) -> str | None:
    if isinstance(value, MonthlyStatus):
        return value.value
    if value is None:
        return None
    text = str(value)
    aliases = {"BULLISH": MonthlyStatus.BULL.value, "BEARISH": MonthlyStatus.BEAR.value}
    return aliases.get(text, text)


def _difference(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left - right


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _duplicate_keys(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen:
            duplicates.append(value)
        seen.add(value)
    return tuple(duplicates)
